#!/usr/bin/env python3
"""Analyze Démonette against maillage and gate sourced family-edge publication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "demonette-2.0"
DB_PATH = ROOT / "data" / "processed" / "maillage.sqlite"
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
ANALYSIS_PATH = ROOT / "data" / "processed" / "demonette-analysis.json"
APPROVED_PATH = ROOT / "data" / "processed" / "demonette-approved.json"
REPORT_PATH = ROOT / "data" / "reports" / "demonette-coverage-conflicts.md"
SOURCE_ID = "demonette_2"
CREATED_AT = "2026-07-27T00:00:00Z"

POS_MAP = {
    "Nm": "NOM", "Nf": "NOM", "Npx": "NOM", "Nfp": "NOM",
    "Nmp": "NOM", "Npf": "NOM", "Nx": "NOM",
    "V": "VER", "Adj": "ADJ", "Adv": "ADV",
}
PUBLISHABLE_COMPLEXITY = {"simple", "motiv-sem"}
# When merged sources disagree, retain the less expansive claim: motiv-sem says
# the semantic link is direct while the surface formation is not regular.
COMPLEXITY_RANK = {"motiv-sem": 0, "simple": 1}
ORIGIN_RANK = {"derif": 0, "demonette1": 1, "nouveau": 2}


def normalize(value: object) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "—"


def seed_keys() -> set[tuple[str, str]]:
    if not SEED_PATH.exists():
        return set()
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    result = set()
    for item in payload.get("nodes", []):
        raw_pos = str(item.get("pos", "")).lower()
        pos = "VER" if raw_pos.startswith("v") else "NOM" if raw_pos.startswith("n") else "ADJ" if raw_pos.startswith("adj") else "ADV" if raw_pos.startswith("adv") else None
        if pos:
            result.add((normalize(item["id"]), pos))
    return result


def load_maillage(conn: sqlite3.Connection) -> tuple[dict[tuple[str, str], dict[str, object]], list[dict[str, object]]]:
    conn.row_factory = sqlite3.Row
    support = seed_keys()
    rows = conn.execute(
        """
        SELECT id,lemma,normalized,pos,cefr_level,status,decision_reason
        FROM lexemes ORDER BY id
        """
    ).fetchall()
    rendered = [
        dict(row) for row in rows
        if row["status"] == "eligible" or (row["normalized"], row["pos"]) in support
    ]
    return {(row["normalized"], row["pos"]): row for row in rendered}, rendered


def load_demonette_lexemes() -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    path = RAW / "lexemes.csv"
    lexemes: dict[str, dict[str, str]] = {}
    duplicate_ids = 0
    mapped_pos = Counter()
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            row = {key: value.strip() for key, value in row.items()}
            lid = row["lid"]
            if lid in lexemes:
                duplicate_ids += 1
                continue
            pos = POS_MAP.get(row["cat"])
            mapped_pos[pos or "OTHER"] += 1
            lexemes[lid] = {
                "lid": lid,
                "fid": row["fid"],
                "lemma": row["graphie"],
                "normalized": normalize(row["graphie"]),
                "cat": row["cat"],
                "pos": pos or "",
                "origin": row["ori_graphie"],
            }
    return lexemes, {
        "rows": len(lexemes) + duplicate_ids,
        "unique_ids": len(lexemes),
        "duplicate_ids": duplicate_ids,
        "mapped_pos": dict(mapped_pos),
        "sha256": sha256(path),
    }


def subtype_for(row: dict[str, str]) -> str:
    if row["orientation"] == "NA":
        return "conversion"
    if row["complexite"] == "motiv-sem":
        return "semantic_derivation"
    construction = row["type_cstr_2"]
    return {
        "suf": "suffixation",
        "pre": "prefixation",
        "pre-suf": "prefix_suffix",
        "conv": "conversion",
    }.get(construction, "derivation")


def affix_label(subtype: str, scheme: str) -> str:
    if subtype == "conversion":
        return "词性转换"
    if subtype == "semantic_derivation":
        suffix = scheme[1:] if scheme.startswith("X") else scheme
        return f"异形词族 · -{suffix}" if suffix else "异形词族"
    if subtype == "suffixation":
        suffix = scheme[1:] if scheme.startswith("X") else scheme
        return f"后缀 · -{suffix}" if suffix else "后缀派生"
    if subtype == "prefixation":
        prefix = scheme[:-1] if scheme.endswith("X") else scheme
        return f"前缀 · {prefix}-" if prefix else "前缀派生"
    if subtype == "prefix_suffix":
        return f"前后缀 · {scheme}"
    return "直接派生"


def choose_variant(rows: list[dict[str, object]]) -> dict[str, object]:
    return min(
        rows,
        key=lambda item: (
            COMPLEXITY_RANK.get(str(item["complexity"]), 9),
            ORIGIN_RANK.get(str(item["origin"]), 9),
            str(item["rid"]),
        ),
    )


def analyze() -> dict[str, object]:
    required = [RAW / name for name in ("demonette-2.0.zip", "lexemes.csv", "relations.csv", "families.csv", "readme.txt")]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("missing Démonette files: " + ", ".join(missing))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    maillage, rendered = load_maillage(conn)
    source = conn.execute("SELECT * FROM sources WHERE id=?", (SOURCE_ID,)).fetchone()
    source_hash_ok = bool(source and source["sha256"] == sha256(ROOT / source["local_path"]))
    demonette, lexeme_profile = load_demonette_lexemes()

    maillage_lids: dict[str, dict[str, object]] = {}
    for lid, item in demonette.items():
        if item["pos"] and (item["normalized"], item["pos"]) in maillage:
            maillage_lids[lid] = maillage[(item["normalized"], item["pos"])]

    relation_path = RAW / "relations.csv"
    relation_rows = 0
    relation_ids: set[str] = set()
    duplicate_relation_ids = 0
    missing_lids = 0
    row_identity_mismatches = 0
    matched_rows = 0
    matched_cross_pos_rows = 0
    matched_same_pos_rows = 0
    orientation_counts = Counter()
    complexity_counts = Counter()
    withheld_rows = Counter()
    candidate_rows: list[dict[str, object]] = []

    with relation_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            relation_rows += 1
            rid = row["rid"]
            if rid in relation_ids:
                duplicate_relation_ids += 1
                continue
            relation_ids.add(rid)
            left = demonette.get(row["lid_1"])
            right = demonette.get(row["lid_2"])
            if not left or not right:
                missing_lids += 1
                continue
            if (
                normalize(row["graph_1"]) != left["normalized"]
                or normalize(row["graph_2"]) != right["normalized"]
                or row["cat_1"] != left["cat"]
                or row["cat_2"] != right["cat"]
            ):
                row_identity_mismatches += 1
            orientation_counts[row["orientation"] or "EMPTY"] += 1
            complexity_counts[row["complexite"] or "EMPTY"] += 1
            left_match = maillage_lids.get(row["lid_1"])
            right_match = maillage_lids.get(row["lid_2"])
            if not left_match or not right_match:
                withheld_rows["endpoint_not_in_rendered_lexicon"] += 1
                continue
            matched_rows += 1
            same_pos = left_match["pos"] == right_match["pos"]
            if same_pos:
                matched_same_pos_rows += 1
            else:
                matched_cross_pos_rows += 1
            orientation = row["orientation"]
            complexity = row["complexite"]
            is_cross_pos_direct = (
                not same_pos and orientation == "as2des" and complexity in PUBLISHABLE_COMPLEXITY
            )
            is_same_pos_direct = (
                same_pos and orientation == "as2des" and complexity == "simple"
                and row["type_cstr_2"] in {"pre", "suf"}
            )
            is_direct = is_cross_pos_direct or is_same_pos_direct
            is_undirected_conversion = (
                not same_pos and orientation == "NA" and complexity == "simple"
                and row["type_cstr_1"] == "conv" and row["type_cstr_2"] == "conv"
            )
            if not (is_direct or is_undirected_conversion):
                if orientation == "indirect":
                    reason = "indirect"
                elif complexity in {"complexe", "motiv-form", "accidentel"}:
                    reason = complexity
                elif orientation == "des2as":
                    reason = "reverse_record"
                elif same_pos:
                    reason = "same_pos_not_simple_affix"
                else:
                    reason = "unsupported_direct_type"
                withheld_rows[reason] += 1
                continue

            if is_direct:
                base_id = int(left_match["id"])
                derived_id = int(right_match["id"])
            else:
                base_id = None
                derived_id = None
            a_id, b_id = sorted((int(left_match["id"]), int(right_match["id"])))
            if a_id == b_id:
                withheld_rows["collapsed_same_lexeme"] += 1
                continue
            subtype = subtype_for(row)
            candidate_rows.append({
                "a_id": a_id,
                "b_id": b_id,
                "base_id": base_id,
                "derived_id": derived_id,
                "a_lemma": left_match["lemma"] if int(left_match["id"]) == a_id else right_match["lemma"],
                "b_lemma": right_match["lemma"] if int(right_match["id"]) == b_id else left_match["lemma"],
                "a_pos": left_match["pos"] if int(left_match["id"]) == a_id else right_match["pos"],
                "b_pos": right_match["pos"] if int(right_match["id"]) == b_id else left_match["pos"],
                "rid": rid,
                "fid": row["fid"],
                "lid_1": row["lid_1"],
                "lid_2": row["lid_2"],
                "orientation": orientation,
                "complexity": complexity,
                "type_cstr_1": row["type_cstr_1"],
                "type_cstr_2": row["type_cstr_2"],
                "scheme_1": row["cstr_1"],
                "scheme_2": row["cstr_2"],
                "subtype": subtype,
                "origin": row["ori_orientation"],
            })

    grouped: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for item in candidate_rows:
        grouped[(int(item["a_id"]), int(item["b_id"]))].append(item)

    approved: list[dict[str, object]] = []
    direction_conflicts: list[dict[str, object]] = []
    classification_variants = 0
    for pair, rows in sorted(grouped.items()):
        directed = {(row["base_id"], row["derived_id"]) for row in rows if row["base_id"] is not None}
        if len(directed) > 1:
            direction_conflicts.append({
                "a_id": pair[0], "b_id": pair[1],
                "directions": [list(value) for value in sorted(directed)],
                "rids": sorted({str(row["rid"]) for row in rows}),
            })
            continue
        signatures = {(row["complexity"], row["subtype"], row["scheme_2"]) for row in rows}
        if len(signatures) > 1:
            classification_variants += 1
        chosen = choose_variant(rows)
        source_records = sorted({str(row["rid"]) for row in rows})
        approved.append({
            **chosen,
            "label": affix_label(str(chosen["subtype"]), str(chosen["scheme_2"])),
            "confidence": 0.98 if chosen["complexity"] == "simple" else 0.93,
            "weight": 0.98 if chosen["complexity"] == "simple" else 0.9,
            "source_records": source_records,
            "source_record_count": len(source_records),
        })

    existing_fam = conn.execute(
        """
        SELECT e.a_id,e.b_id,e.direction
        FROM official_edges e
        WHERE e.relation='fam'
          AND NOT EXISTS (
            SELECT 1 FROM official_edge_sources s
            WHERE s.edge_id=e.id AND s.source_id='demonette_2'
          )
        """
    ).fetchall()
    before_pairs = {(row["a_id"], row["b_id"]) for row in existing_fam}
    existing_other = {
        (row["a_id"], row["b_id"], row["relation"])
        for row in conn.execute("SELECT a_id,b_id,relation FROM official_edges WHERE relation!='fam'")
    }
    # A clean data rebuild has not yet materialized the editorial seed into
    # official_edges, so include that source directly in the conflict baseline.
    if SEED_PATH.exists():
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        seed_pos_by_word: dict[str, str] = {}
        for item in seed.get("nodes", []):
            raw_pos = str(item.get("pos", "")).lower()
            pos = "VER" if raw_pos.startswith("v") else "NOM" if raw_pos.startswith("n") else "ADJ" if raw_pos.startswith("adj") else "ADV" if raw_pos.startswith("adv") else ""
            if pos:
                seed_pos_by_word[normalize(item["id"])] = pos
        for edge in seed.get("edges", []):
            left_word, right_word = normalize(edge["a"]), normalize(edge["b"])
            left = maillage.get((left_word, seed_pos_by_word.get(left_word, "")))
            right = maillage.get((right_word, seed_pos_by_word.get(right_word, "")))
            if not left or not right or left["id"] == right["id"]:
                continue
            pair = tuple(sorted((int(left["id"]), int(right["id"]))))
            relation = "compare" if edge["type"] == "axis" else edge["type"]
            if relation == "fam":
                before_pairs.add(pair)
            else:
                existing_other.add((pair[0], pair[1], relation))
    trap_conflicts = [row for row in approved if (row["a_id"], row["b_id"], "trap") in existing_other]
    drift_coexistences = [row for row in approved if (row["a_id"], row["b_id"], "drift") in existing_other]
    if trap_conflicts:
        conflict_pairs = {(row["a_id"], row["b_id"]) for row in trap_conflicts}
        approved = [row for row in approved if (row["a_id"], row["b_id"]) not in conflict_pairs]

    eligible_ids = {int(row["id"]) for row in rendered if row["status"] == "eligible"}
    before_nodes = {node for pair in before_pairs for node in pair if node in eligible_ids}
    approved_nodes = {node for row in approved for node in (int(row["a_id"]), int(row["b_id"])) if node in eligible_ids}
    after_nodes = before_nodes | approved_nodes
    matched_node_ids = {int(row["id"]) for row in maillage_lids.values()}

    pos_transitions = Counter()
    subtype_counts = Counter()
    complexity_published = Counter()
    for row in approved:
        if row["base_id"] is not None:
            base = next(item for item in rendered if int(item["id"]) == int(row["base_id"]))
            derived = next(item for item in rendered if int(item["id"]) == int(row["derived_id"]))
            transition = f"{base['pos']}→{derived['pos']}"
        else:
            transition = "↔".join(sorted((str(row["a_pos"]), str(row["b_pos"]))))
        pos_transitions[transition] += 1
        subtype_counts[str(row["subtype"])] += 1
        complexity_published[str(row["complexity"])] += 1

    def find_pair(base_word: str, base_pos: str, derived_word: str, derived_pos: str) -> dict[str, object] | None:
        base = maillage.get((normalize(base_word), base_pos))
        derived = maillage.get((normalize(derived_word), derived_pos))
        if not base or not derived:
            return None
        for row in approved:
            if row["base_id"] == base["id"] and row["derived_id"] == derived["id"]:
                return row
        return None

    known_pairs = {
        "affirmer_VER→affirmation_NOM": find_pair("affirmer", "VER", "affirmation", "NOM"),
        "voir_VER→vision_NOM": find_pair("voir", "VER", "vision", "NOM"),
        "poli_ADJ→impoli_ADJ": find_pair("poli", "ADJ", "impoli", "ADJ"),
    }
    direction_conflict_rate = len(direction_conflicts) / max(1, len(grouped))
    gates = {
        "official_source_registered_and_hashed": bool(source and source_hash_ok),
        "source_volume_is_plausible": lexeme_profile["rows"] >= 350_000 and relation_rows >= 200_000,
        "source_ids_are_unique": lexeme_profile["duplicate_ids"] == 0 and duplicate_relation_ids == 0,
        "relation_foreign_keys_are_complete": missing_lids == 0,
        "row_identity_matches_lexeme_table": row_identity_mismatches == 0,
        "direction_conflict_rate_below_0_5pct": direction_conflict_rate <= 0.005,
        "publishable_cross_pos_edges_exist": len(approved) >= 100,
        "affirmer_affirmation_regression": known_pairs["affirmer_VER→affirmation_NOM"] is not None,
        "voir_vision_regression": known_pairs["voir_VER→vision_NOM"] is not None,
        "poli_impoli_same_pos_regression": known_pairs["poli_ADJ→impoli_ADJ"] is not None,
    }

    analysis = {
        "meta": {
            "version": "demonette-import-v1",
            "created_at": CREATED_AT,
            "source_id": SOURCE_ID,
            "source_registered": bool(source),
            "source_hash_ok": source_hash_ok,
            "archive_sha256": sha256(RAW / "demonette-2.0.zip"),
            "relations_sha256": sha256(relation_path),
            "gate_passed": all(gates.values()),
        },
        "gates": gates,
        "source_profile": {
            "lexemes": lexeme_profile,
            "relation_rows": relation_rows,
            "unique_relation_ids": len(relation_ids),
            "duplicate_relation_ids": duplicate_relation_ids,
            "missing_relation_lids": missing_lids,
            "row_identity_mismatches": row_identity_mismatches,
            "orientation_counts": dict(orientation_counts),
            "complexity_counts": dict(complexity_counts),
        },
        "alignment": {
            "rendered_lexemes": len(rendered),
            "eligible_lexemes": len(eligible_ids),
            "matched_rendered_lexemes": len(matched_node_ids),
            "matched_relation_rows": matched_rows,
            "matched_cross_pos_rows": matched_cross_pos_rows,
            "matched_same_pos_rows": matched_same_pos_rows,
            "raw_publishable_rows": len(candidate_rows),
            "unique_publishable_edges": len(approved),
            "duplicate_source_rows_collapsed": len(candidate_rows) - len(grouped),
            "classification_variant_pairs": classification_variants,
            "direction_conflicts": len(direction_conflicts),
            "direction_conflict_rate": direction_conflict_rate,
            "existing_trap_conflicts_withheld": len(trap_conflicts),
            "existing_drift_coexistences": len(drift_coexistences),
            "withheld_rows": dict(withheld_rows),
        },
        "coverage": {
            "eligible_total": len(eligible_ids),
            "eligible_with_official_family_before": len(before_nodes),
            "eligible_with_official_family_after": len(after_nodes),
            "eligible_gaining_family_relation": len(after_nodes - before_nodes),
            "before_rate": len(before_nodes) / max(1, len(eligible_ids)),
            "after_rate": len(after_nodes) / max(1, len(eligible_ids)),
        },
        "breakdowns": {
            "pos_transitions": dict(pos_transitions.most_common()),
            "subtypes": dict(subtype_counts.most_common()),
            "published_complexity": dict(complexity_published.most_common()),
        },
        "known_pairs": known_pairs,
        "direction_conflict_examples": direction_conflicts[:25],
        "trap_conflict_examples": trap_conflicts[:25],
        "drift_coexistence_examples": drift_coexistences[:25],
        "approved_edges": approved,
    }
    ANALYSIS_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(analysis)
    conn.close()
    return analysis


def write_report(analysis: dict[str, object]) -> None:
    meta = analysis["meta"]
    profile = analysis["source_profile"]
    align = analysis["alignment"]
    coverage = analysis["coverage"]
    breakdowns = analysis["breakdowns"]
    gates = analysis["gates"]
    known = analysis["known_pairs"]
    lines = [
        "# Démonette 2.0 覆盖率与冲突报告",
        "",
        f"> 结论：**{'通过自动发布质量门' if meta['gate_passed'] else '未通过自动发布质量门'}**。报告粒度为 maillage 当前可渲染 lemma+POS 与 Démonette 直接关系的精确对齐。",
        "",
        "## 核心结果",
        "",
        f"- Démonette 原始规模：{profile['lexemes']['rows']:,} 个 lexeme、{profile['relation_rows']:,} 条有向关系记录。",
        f"- 当前 {align['rendered_lexemes']:,} 个可渲染词汇单位中，{align['matched_rendered_lexemes']:,} 个可与 Démonette lemma+POS 精确对齐（{pct(align['matched_rendered_lexemes'], align['rendered_lexemes'])}）。",
        f"- 经过跨词性、方向、复杂度和去重规则后，可发布 {align['unique_publishable_edges']:,} 条来源确认的词族边。",
        f"- eligible 词的正式词族覆盖预计由 {coverage['eligible_with_official_family_before']:,}/{coverage['eligible_total']:,}（{100*coverage['before_rate']:.1f}%）提升到 {coverage['eligible_with_official_family_after']:,}/{coverage['eligible_total']:,}（{100*coverage['after_rate']:.1f}%），净新增覆盖 {coverage['eligible_gaining_family_relation']:,} 个词。",
        "",
        "## 发布口径",
        "",
        "- 发布 `orientation=as2des` 且 `complexite` 为 `simple` 或 `motiv-sem` 的跨词性关系。",
        "- 同词性只发布方向明确、`simple`、且构式为前缀或后缀的直接派生；例如 `poli → impoli`。",
        "- `simple` 表示直接、形式与语义一致的派生；`motiv-sem` 表示语义上直接但形式不规则，前端标为“异形词族”。",
        "- 无法定向但两端均为 conversion 的 `simple` 跨词性关系，发布为无方向“词性转换”。",
        "- `indirect`、`complexe`、`motiv-form`、`accidentel` 以及非简单词缀的同词性关系不发布。",
        "",
        "## 跨词性覆盖",
        "",
        "| 方向 | 正式边数 |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value:,} |" for key, value in breakdowns["pos_transitions"].items())
    lines += ["", "### 关系类型", "", "| 类型 | 边数 |", "|---|---:|"]
    lines.extend(f"| {key} | {value:,} |" for key, value in breakdowns["subtypes"].items())
    lines += [
        "",
        "## 完整性与冲突",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
        f"| lexeme / relation 主键重复 | {profile['lexemes']['duplicate_ids']} / {profile['duplicate_relation_ids']} |",
        f"| relation 引用缺失 lid | {profile['missing_relation_lids']} |",
        f"| relation 文本/词性与 lexeme 表不一致 | {profile['row_identity_mismatches']} |",
        f"| 原始可发布记录折叠 | {align['raw_publishable_rows']:,} → {align['unique_publishable_edges']:,} 条唯一边 |",
        f"| 同一词对方向冲突 | {align['direction_conflicts']}（{100*align['direction_conflict_rate']:.3f}%） |",
        f"| 同一词对分类存在多个版本 | {align['classification_variant_pairs']} |",
        f"| 与现有 trap 冲突并暂缓 | {align['existing_trap_conflicts_withheld']} |",
        f"| 与现有语义漂移边并存 | {align['existing_drift_coexistences']} |",
        "",
        "多条原始记录通常来自 Démonette 合并的不同上游来源，不会在产品里重复成多条线；发布清单保留全部 `rid` 作为追溯记录。方向冲突词对整组暂缓，不参与发布。",
        "",
        "## 三个回归样例",
        "",
        "| 词对 | 是否进入发布清单 | Démonette 分类 | 产品显示 |",
        "|---|---|---|---|",
    ]
    for key, row in known.items():
        label = key.replace("_VER→", " → ").replace("_NOM", "")
        lines.append(
            f"| {label} | {'是' if row else '否'} | {row['complexity'] + ' / ' + row['subtype'] if row else '—'} | {row['label'] if row else '—'} |"
        )
    lines += [
        "",
        "## 自动发布质量门",
        "",
        "| 门槛 | 结果 |",
        "|---|---|",
    ]
    lines.extend(f"| {key} | {'通过' if passed else '失败'} |" for key, passed in gates.items())
    lines += [
        "",
        "## 限制与下一步",
        "",
        "- 本报告只衡量 maillage 当前词表与 Démonette 的精确 lemma+POS 对齐；未命中不等于 Démonette 无该词，可能是词性粒度或词表范围不同。",
        "- 同词性只放行简单前/后缀直接派生；间接同族和复杂构词仍暂缓。",
        "- `motiv-sem` 对学习者有价值，但必须保持“异形词族”标签，不能解释成规则性的拼写变化。",
        "- 发布后应再次验证官方边来源完整、全图连通、运行时导出以及样例词的焦点图。",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def approve() -> dict[str, object]:
    if not ANALYSIS_PATH.exists():
        raise SystemExit("run analyze before approve")
    analysis = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    failed = [name for name, passed in analysis["gates"].items() if not passed]
    if failed:
        raise SystemExit("Démonette quality gate failed: " + ", ".join(failed))
    payload = {
        "meta": analysis["meta"],
        "gates": analysis["gates"],
        "alignment": analysis["alignment"],
        "coverage": analysis["coverage"],
        "breakdowns": analysis["breakdowns"],
        "known_pairs": analysis["known_pairs"],
        "direction_conflict_examples": analysis["direction_conflict_examples"],
        "edges": analysis["approved_edges"],
    }
    APPROVED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyze", "approve"), nargs="?", default="analyze")
    args = parser.parse_args()
    result = analyze() if args.command == "analyze" else approve()
    if args.command == "analyze":
        summary = {
            "gate_passed": result["meta"]["gate_passed"],
            "matched_lexemes": result["alignment"]["matched_rendered_lexemes"],
            "approved_edges": result["alignment"]["unique_publishable_edges"],
            "coverage_after": result["coverage"]["after_rate"],
            "report": str(REPORT_PATH.relative_to(ROOT)),
        }
    else:
        summary = {"approved_edges": len(result["edges"]), "output": str(APPROVED_PATH.relative_to(ROOT))}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
