#!/usr/bin/env python3
"""Import sense-aware French lexical relations from the official DBnary dump."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from learning_lexicon import learning_lexeme_rows


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "dbnary" / "fr_dbnary_ontolex.ttl.bz2"
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
ANALYSIS_PATH = ROOT / "data" / "processed" / "dbnary-analysis.json"
APPROVED_PATH = ROOT / "data" / "processed" / "dbnary-approved.json"
REPORT_PATH = ROOT / "data" / "reports" / "dbnary-sense-relations.md"
SOURCE_ID = "dbnary_fr"
EXPECTED_SHA256 = "aeb243f402c0acedade522842736e5885b025b5eb77894c45817b8f1bd12062f"
CREATED_AT = "2026-07-27T00:00:00Z"

POS_MAP = {
    "noun": "NOM",
    "verb": "VER",
    "adjective": "ADJ",
    "adverb": "ADV",
}
RELATION_MAP = {
    "synonym": ("syn", "exact", "近义"),
    "approximateSynonym": ("syn", "approximate", "近义·近似"),
    "antonym": ("ant", "exact", "反义"),
}
RELATION_RANK = {"exact": 0, "approximate": 1}


def normalize(value: object) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "—"


def turtle_text(raw: str) -> str:
    try:
        return json.loads('"' + raw + '"')
    except json.JSONDecodeError:
        return raw.replace(r'\"', '"').replace(r"\n", " ").replace(r"\t", " ").replace("\\\\", "\\")


def stream_blocks(path: Path):
    block: list[str] = []
    with bz2.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                block.append(line)
            elif block:
                yield "".join(block)
                block = []
    if block:
        yield "".join(block)


def subject_token(block: str) -> str:
    return block.split(None, 1)[0] if block and not block.startswith("@prefix") else ""


def local_name(token: str) -> str | None:
    token = token.strip().rstrip(";,.\n")
    if token.startswith("fra:"):
        return unquote(token[4:])
    if token.startswith("<") and token.endswith(">"):
        url = token[1:-1]
        marker = "/dbnary/fra/"
        if marker in url:
            return unquote(url.split(marker, 1)[1])
    return None


def page_lemma(token: str) -> str | None:
    local = local_name(token)
    if not local or local.startswith("__"):
        return None
    if re.search(r"__(?:nom|verb|adj|adv)__\d+$", local):
        local = re.sub(r"__(?:nom|verb|adj|adv)__\d+$", "", local)
    return normalize(local.replace("_", " "))


def predicate_values(block: str, predicate: str) -> list[str]:
    match = re.search(rf"{re.escape(predicate)}\s+(.+?)(?=;\s*\n|\s+\.\s*$)", block, re.S)
    if not match:
        return []
    return [item.strip() for item in re.split(r"\s*,\s*", match.group(1)) if item.strip()]


def load_rendered(conn: sqlite3.Connection) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in learning_lexeme_rows(conn)]


def analyze(
    raw_path: Path = RAW_PATH,
    analysis_path: Path = ANALYSIS_PATH,
    report_path: Path = REPORT_PATH,
    expected_sha256: str | None = EXPECTED_SHA256,
) -> dict[str, object]:
    """Analyze a DBnary extract without publishing it.

    Alternate historical extracts are supported for source-difference audits.
    `approve()` remains intentionally bound to the locked production analysis.
    """
    if not raw_path.exists():
        raise SystemExit(f"missing DBnary source: {raw_path}")
    conn = sqlite3.connect(DB_PATH)
    rendered = load_rendered(conn)
    by_key = {(str(row["normalized"]), str(row["pos"])): row for row in rendered}
    current_hash = sha256(raw_path)

    entries: dict[str, dict[str, object]] = {}
    wanted_senses: dict[str, str] = {}
    senses: dict[str, dict[str, object]] = {}
    block_count = 0
    lexical_entry_blocks = 0
    relation_mentions = Counter()

    unparsed_senses: list[dict[str, object]] = []
    for block in stream_blocks(raw_path):
        block_count += 1
        subject = subject_token(block)
        if not subject:
            continue
        if "ontolex:LexicalEntry" in block:
            lexical_entry_blocks += 1
            label_match = re.search(r'rdfs:label\s+"((?:[^"\\]|\\.)*)"@fr', block)
            pos_match = re.search(r"lexinfo:partOfSpeech\s+lexinfo:([A-Za-z]+)", block)
            if not label_match or not pos_match:
                continue
            label = turtle_text(label_match.group(1))
            pos = POS_MAP.get(pos_match.group(1))
            lexeme = by_key.get((normalize(label), pos or ""))
            if not lexeme:
                continue
            entry_local = local_name(subject)
            if not entry_local:
                continue
            rank_match = re.search(r"__(\d+)$", entry_local)
            entry_rank = int(rank_match.group(1)) if rank_match else 1
            relation_rows = []
            for predicate, (relation, subtype, label_zh) in RELATION_MAP.items():
                for target in predicate_values(block, f"dbnary:{predicate}"):
                    target_lemma = page_lemma(target)
                    if not target_lemma:
                        continue
                    relation_mentions[predicate] += 1
                    relation_rows.append({
                        "predicate": predicate,
                        "relation": relation,
                        "subtype": subtype,
                        "label": label_zh,
                        "target_lemma": target_lemma,
                        "target_token": target,
                    })
            sense_tokens = predicate_values(block, "ontolex:sense")
            entry = {
                "id": entry_local,
                "lexeme_id": int(lexeme["id"]),
                "lemma": str(lexeme["lemma"]),
                "pos": str(lexeme["pos"]),
                "entry_rank": entry_rank,
                "source_url": "https://fr.wiktionary.org/wiki/" + quote(str(lexeme["lemma"])),
                "relations": relation_rows,
            }
            entries[entry_local] = entry
            for token in sense_tokens:
                sense_local = local_name(token)
                if sense_local:
                    wanted_senses[sense_local] = entry_local
            continue

        subject_local = local_name(subject)
        if not subject_local or subject_local not in wanted_senses or "ontolex:LexicalSense" not in block:
            continue
        number_match = re.search(r'dbnary:senseNumber\s+"((?:[^"\\]|\\.)*)"', block)
        definition_match = re.search(
            r'skos:definition\s+\[\s*rdf:value\s+"((?:[^"\\]|\\.)*)"@fr\s*\]', block, re.S
        )
        if not definition_match:
            unparsed_senses.append({
                "id": subject_local,
                "entry_id": wanted_senses[subject_local],
                "raw_contains_definition": "skos:definition" in block,
                "raw_contains_rdf_value": "rdf:value" in block,
            })
            continue
        examples = [
            turtle_text(raw) for raw in re.findall(
                r'skos:example\s+\[\s*rdf:value\s+"((?:[^"\\]|\\.)*)"@fr', block, re.S
            )[:2]
        ]
        entry_id = wanted_senses[subject_local]
        senses[subject_local] = {
            "id": subject_local,
            "entry_id": entry_id,
            "lexeme_id": int(entries[entry_id]["lexeme_id"]),
            "sense_number": turtle_text(number_match.group(1)) if number_match else "?",
            "definition_fr": turtle_text(definition_match.group(1)),
            "examples": examples,
        }

    relation_candidates: list[dict[str, object]] = []
    entries_by_lexeme: dict[int, list[dict[str, object]]] = defaultdict(list)
    for entry in entries.values():
        entries_by_lexeme[int(entry["lexeme_id"])].append(entry)
    for grouped_entries in entries_by_lexeme.values():
        for display_rank, entry in enumerate(
            sorted(grouped_entries, key=lambda row: (int(row["entry_rank"]), str(row["id"]))), start=1
        ):
            entry["entry_rank"] = display_rank

    unresolved_targets = Counter()
    self_relations = 0
    for entry in entries.values():
        source_id = int(entry["lexeme_id"])
        source_pos = str(entry["pos"])
        for row in entry["relations"]:
            target = by_key.get((str(row["target_lemma"]), source_pos))
            if not target:
                unresolved_targets[str(row["predicate"])] += 1
                continue
            target_id = int(target["id"])
            if source_id == target_id:
                self_relations += 1
                continue
            a_id, b_id = sorted((source_id, target_id))
            relation_candidates.append({
                "a_id": a_id,
                "b_id": b_id,
                "a_lemma": next(item["lemma"] for item in rendered if int(item["id"]) == a_id),
                "b_lemma": next(item["lemma"] for item in rendered if int(item["id"]) == b_id),
                "pos": source_pos,
                "relation": row["relation"],
                "subtype": row["subtype"],
                "label": row["label"],
                "source_entry_id": entry["id"],
                "source_predicate": row["predicate"],
                "target_lemma": row["target_lemma"],
            })

    grouped: dict[tuple[int, int, str], list[dict[str, object]]] = defaultdict(list)
    for row in relation_candidates:
        grouped[(int(row["a_id"]), int(row["b_id"]), str(row["relation"]))].append(row)
    contradictory_pairs = {
        (a, b) for a, b, relation in grouped
        if (a, b, "syn") in grouped and (a, b, "ant") in grouped
    }
    approved_edges: list[dict[str, object]] = []
    duplicate_rows_collapsed = 0
    for (a_id, b_id, relation), rows in sorted(grouped.items()):
        if (a_id, b_id) in contradictory_pairs:
            continue
        chosen = sorted(rows, key=lambda row: (RELATION_RANK[str(row["subtype"])], str(row["source_entry_id"])))[0]
        source_entries = sorted({str(row["source_entry_id"]) for row in rows})
        predicates = sorted({str(row["source_predicate"]) for row in rows})
        duplicate_rows_collapsed += len(rows) - 1
        approved_edges.append({
            **chosen,
            "source_entry_ids": source_entries,
            "source_predicates": predicates,
            "confidence": 0.96 if chosen["subtype"] == "exact" else 0.86,
            "weight": 0.96 if relation == "syn" and chosen["subtype"] == "exact" else 0.86,
        })

    entry_ids_with_senses = {row["entry_id"] for row in senses.values()}
    lexemes_with_entries = {int(row["lexeme_id"]) for row in entries.values()}
    lexemes_with_senses = {int(row["lexeme_id"]) for row in senses.values()}
    lexemes_with_semantic_edges = {node for row in approved_edges for node in (int(row["a_id"]), int(row["b_id"]))}

    def pair(left: str, right: str, relation: str) -> dict[str, object] | None:
        left_ids = {int(row["id"]) for row in rendered if row["normalized"] == normalize(left)}
        right_ids = {int(row["id"]) for row in rendered if row["normalized"] == normalize(right)}
        return next((row for row in approved_edges if row["relation"] == relation and {int(row["a_id"]), int(row["b_id"])} == left_ids | right_ids), None)

    poli_entries = sorted(
        [row for row in entries.values() if row["lemma"] == "poli" and row["pos"] == "ADJ"],
        key=lambda row: int(row["entry_rank"]),
    )
    poli_senses = [row for row in senses.values() if any(row["entry_id"] == item["id"] for item in poli_entries)]
    known_pairs = {
        "poli_respectueux_syn": pair("poli", "respectueux", "syn"),
        "poli_impoli_ant": pair("poli", "impoli", "ant"),
        "seau_nager_syn": pair("seau", "nager", "syn"),
    }
    conflict_rate = len(contradictory_pairs) / max(1, len({(a, b) for a, b, _ in grouped}))
    gates = {
        "official_snapshot_hash_matches": expected_sha256 is None or current_hash == expected_sha256,
        "rendered_lexeme_alignment_above_80pct": len(lexemes_with_entries) / max(1, len(rendered)) >= 0.8,
        "sense_definitions_exist": len(senses) >= 5_000,
        "explicit_semantic_edges_exist": len(approved_edges) >= 500,
        "contradiction_rate_below_1pct": conflict_rate < 0.01,
        "poli_has_multiple_sense_groups": len(poli_entries) >= 2 and len(poli_senses) >= 3,
        "poli_respectueux_is_synonym": known_pairs["poli_respectueux_syn"] is not None,
        "poli_impoli_is_antonym": known_pairs["poli_impoli_ant"] is not None,
        "seau_nager_is_not_synonym": known_pairs["seau_nager_syn"] is None,
    }
    analysis = {
        "meta": {
            "version": "dbnary-import-v1",
            "created_at": CREATED_AT,
            "source_id": SOURCE_ID,
            "source_sha256": current_hash,
            "gate_passed": all(gates.values()),
        },
        "gates": gates,
        "source_profile": {
            "compressed_bytes": raw_path.stat().st_size,
            "turtle_blocks": block_count,
            "lexical_entry_blocks": lexical_entry_blocks,
            "matched_entries": len(entries),
            "matched_senses_with_definition": len(senses),
            "entry_ids_with_senses": len(entry_ids_with_senses),
            "relation_mentions": dict(relation_mentions),
        },
        "alignment": {
            "rendered_lexemes": len(rendered),
            "lexemes_with_entries": len(lexemes_with_entries),
            "lexemes_with_senses": len(lexemes_with_senses),
            "lexemes_with_semantic_edges": len(lexemes_with_semantic_edges),
            "unresolved_targets": dict(unresolved_targets),
            "self_relations_withheld": self_relations,
        },
        "relations": {
            "raw_aligned_rows": len(relation_candidates),
            "unique_published_edges": len(approved_edges),
            "duplicate_rows_collapsed": duplicate_rows_collapsed,
            "contradictory_pairs_withheld": len(contradictory_pairs),
            "contradiction_rate": conflict_rate,
            "published_by_relation": dict(Counter(str(row["relation"]) for row in approved_edges)),
            "published_by_subtype": dict(Counter(str(row["subtype"]) for row in approved_edges)),
        },
        "known_pairs": known_pairs,
        "poli_entries": poli_entries,
        "poli_senses": sorted(poli_senses, key=lambda row: (str(row["entry_id"]), str(row["sense_number"]))),
        "unparsed_senses": sorted(unparsed_senses, key=lambda row: (str(row["entry_id"]), str(row["id"]))),
        "contradiction_examples": [
            {"a_id": a, "b_id": b} for a, b in sorted(contradictory_pairs)[:25]
        ],
        "entries": sorted(entries.values(), key=lambda row: (int(row["lexeme_id"]), int(row["entry_rank"]), str(row["id"]))),
        "senses": sorted(senses.values(), key=lambda row: (int(row["lexeme_id"]), str(row["entry_id"]), str(row["sense_number"]))),
        "approved_edges": approved_edges,
    }
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(analysis, report_path)
    conn.close()
    return analysis


def write_report(analysis: dict[str, object], report_path: Path = REPORT_PATH) -> None:
    profile = analysis["source_profile"]
    alignment = analysis["alignment"]
    relations = analysis["relations"]
    gates = analysis["gates"]
    lines = [
        "# DBnary 义项与语义关系质量报告",
        "",
        f"> 结论：**{'通过发布质量门' if analysis['meta']['gate_passed'] else '未通过发布质量门'}**。粒度为当前可渲染 lemma+POS、DBnary 词条组和具体义项。",
        "",
        "## 覆盖率",
        "",
        f"- 当前 {alignment['rendered_lexemes']:,} 个可渲染词汇单位中，{alignment['lexemes_with_entries']:,} 个能对齐至 DBnary 词条（{pct(alignment['lexemes_with_entries'], alignment['rendered_lexemes'])}）。",
        f"- {alignment['lexemes_with_senses']:,} 个词有至少一条法语义项定义，共 {profile['matched_senses_with_definition']:,} 条定义。",
        f"- 输入关系折叠为 {relations['unique_published_edges']:,} 条唯一语义边，覆盖 {alignment['lexemes_with_semantic_edges']:,} 个词。",
        "",
        "## 语义关系",
        "",
        "| 关系 | 条数 |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value:,} |" for key, value in relations["published_by_relation"].items())
    lines += [
        "",
        "## 关键词例",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
        f"| poli 多义项 | {len(analysis['poli_entries'])} 个词条组 / {len(analysis['poli_senses'])} 条定义 |",
        f"| poli–respectueux 近义 | {'通过' if analysis['known_pairs']['poli_respectueux_syn'] else '失败'} |",
        f"| poli–impoli 反义 | {'通过' if analysis['known_pairs']['poli_impoli_ant'] else '失败'} |",
        f"| seau–nager 不得成为近义 | {'通过' if not analysis['known_pairs']['seau_nager_syn'] else '失败'} |",
        "",
        "## 完整性与冲突",
        "",
        f"- 对齐后原始关系 {relations['raw_aligned_rows']:,} 行，去重后 {relations['unique_published_edges']:,} 条。",
        f"- 同一词对同时标为近义与反义的 {relations['contradictory_pairs_withheld']} 组，全部暂缓发布。",
        f"- 未对齐目标：{json.dumps(alignment['unresolved_targets'], ensure_ascii=False)}。这些不会自动扩充当前词表。",
        "",
        "## 自动发布质量门",
        "",
        "| 门槛 | 结果 |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | {'通过' if passed else '失败'} |" for name, passed in gates.items())
    lines += [
        "",
        "## 限制",
        "",
        "- DBnary 反映 Wiktionnaire 的明示关系，有来源但不等于已经 wordcloud 人工辨析。前端必须显示为“来源确认”，不得冒充“已审校”。",
        "- 语义关系只在目标词以相同词性存在于当前词表时发布，避免多词性词误连。",
        "- 本轮不导入 DBnary `derivedFrom`；构词关系仍由 Démonette 负责。",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def approve() -> dict[str, object]:
    if not ANALYSIS_PATH.exists():
        raise SystemExit("run analyze before approve")
    analysis = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    failed = [name for name, passed in analysis["gates"].items() if not passed]
    if failed:
        raise SystemExit("DBnary quality gate failed: " + ", ".join(failed))
    payload = {
        "meta": analysis["meta"],
        "gates": analysis["gates"],
        "source_profile": analysis["source_profile"],
        "alignment": analysis["alignment"],
        "relations": analysis["relations"],
        "known_pairs": analysis["known_pairs"],
        "entries": analysis["entries"],
        "senses": analysis["senses"],
        "edges": analysis["approved_edges"],
    }
    APPROVED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyze", "approve"))
    parser.add_argument("--raw", type=Path, help="historical DBnary extract for read-only analysis")
    parser.add_argument("--analysis-output", type=Path, help="analysis JSON destination; requires --raw")
    parser.add_argument("--report-output", type=Path, help="report destination; requires --raw")
    parser.add_argument("--expected-sha256", help="optional integrity lock for --raw")
    args = parser.parse_args()
    if args.command == "approve" and any((args.raw, args.analysis_output, args.report_output, args.expected_sha256)):
        raise SystemExit("approve only accepts the locked production analysis")
    if args.command == "analyze":
        if any((args.analysis_output, args.report_output, args.expected_sha256)) and not args.raw:
            raise SystemExit("--analysis-output, --report-output and --expected-sha256 require --raw")
        payload = analyze(
            raw_path=args.raw or RAW_PATH,
            analysis_path=args.analysis_output or ANALYSIS_PATH,
            report_path=args.report_output or REPORT_PATH,
            expected_sha256=args.expected_sha256 if args.raw else EXPECTED_SHA256,
        )
    else:
        payload = approve()
    if args.command == "analyze":
        summary = {
            "gate_passed": payload["meta"]["gate_passed"],
            "entries": payload["source_profile"]["matched_entries"],
            "senses": payload["source_profile"]["matched_senses_with_definition"],
            "edges": payload["relations"]["unique_published_edges"],
        }
    else:
        summary = {"gate_passed": payload["meta"]["gate_passed"], "edges": len(payload["edges"])}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
