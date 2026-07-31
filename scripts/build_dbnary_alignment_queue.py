#!/usr/bin/env python3
"""Build or resolve a human-review queue for DBnary/Wiktionary differences.

This adapter does not import Wiktextract glosses.  It only records evidence and,
when a DBnary extract made from the same Wikimedia dump is supplied, classifies
whether the existing DBnary importer captured a definition from that extract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from learning_lexicon import learning_lexeme_rows, normalize


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "maillage.sqlite"
WIKT_OUTPUT = ROOT / "data" / "processed" / "wiktextract-gap-audit.jsonl"
WIKT_DUMP = ROOT / "data" / "raw" / "wiktextract" / "frwiktionary-20260701-pages-articles.xml.bz2"
QUEUE = ROOT / "data" / "processed" / "dbnary-alignment-review-queue.json"
REPORT = ROOT / "data" / "reports" / "dbnary-alignment-review-queue.md"
POS = {"noun": "NOM", "verb": "VER", "adjective": "ADJ", "adverb": "ADV"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_glossed_sense(entry: dict[str, object]) -> bool:
    senses = entry.get("senses")
    return isinstance(senses, list) and any(
        isinstance(sense, dict) and bool(sense.get("glosses")) for sense in senses
    )


def pending_rows() -> dict[tuple[str, str], dict[str, object]]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = learning_lexeme_rows(conn)
    pending = {
        (str(row["normalized"]), str(row["pos"])): dict(row)
        for row in rows
        if not conn.execute("SELECT 1 FROM lexeme_senses WHERE lexeme_id=? LIMIT 1", (row["id"],)).fetchone()
    }
    conn.close()
    return pending


def wiktextract_records() -> dict[str, list[dict[str, object]]]:
    records: dict[str, list[dict[str, object]]] = defaultdict(list)
    with WIKT_OUTPUT.open(encoding="utf-8") as stream:
        for line in stream:
            entry = json.loads(line)
            if entry.get("lang_code") == "fr":
                records[normalize(entry.get("word"))].append(entry)
    return records


def build_queue(aligned_analysis: Path | None) -> dict[str, object]:
    if not WIKT_OUTPUT.exists() or not WIKT_DUMP.exists():
        raise SystemExit("run the pinned Wiktextract audit before building this queue")
    if aligned_analysis and not aligned_analysis.exists():
        raise SystemExit(f"missing aligned DBnary analysis: {aligned_analysis}")
    pending = pending_rows()
    records = wiktextract_records()
    dump_hash = sha256(WIKT_DUMP)
    analysis = json.loads(aligned_analysis.read_text(encoding="utf-8")) if aligned_analysis else None
    parsed_senses = defaultdict(list)
    raw_unparsed = defaultdict(list)
    entries = defaultdict(list)
    if analysis:
        for row in analysis["senses"]:
            parsed_senses[int(row["lexeme_id"])].append(row)
        for row in analysis.get("unparsed_senses", []):
            raw_unparsed[str(row["entry_id"])].append(row)
        for row in analysis["entries"]:
            entries[int(row["lexeme_id"])].append(row)

    queue = []
    for (lemma, pos), lexeme in sorted(pending.items()):
        matches = [entry for entry in records.get(lemma, []) if POS.get(entry.get("pos")) == pos and has_glossed_sense(entry)]
        if not matches:
            continue
        decision = "pending_aligned_dbnary_snapshot"
        if analysis:
            lexeme_id = int(lexeme["id"])
            matching_entries = entries[lexeme_id]
            if parsed_senses[lexeme_id]:
                decision = "dbnary_aligned_extract_captured"
            elif any(item["raw_contains_definition"] for entry in matching_entries for item in raw_unparsed[str(entry["id"])]):
                decision = "dbnary_parser_capture_gap"
            elif matching_entries:
                decision = "dbnary_extract_entry_without_definition"
            else:
                decision = "dbnary_source_uncovered_same_snapshot"
        queue.append({
            "lexeme_id": int(lexeme["id"]),
            "lemma": lexeme["lemma"],
            "pos": pos,
            "cefr_level": lexeme["cefr_level"],
            "status": "pending_human_review",
            "alignment_decision": decision,
            "wiktextract_evidence": {
                "dump_path": str(WIKT_DUMP.relative_to(ROOT)),
                "dump_sha256": dump_hash,
                "matching_entries": len(matches),
                "glossed_senses": sum(len(entry.get("senses", [])) for entry in matches),
            },
            "dbnary_evidence": {
                "aligned_analysis": str(aligned_analysis.relative_to(ROOT)) if aligned_analysis else None,
                "parsed_senses": len(parsed_senses[int(lexeme["id"])]),
                "matched_entries": len(entries[int(lexeme["id"])]),
            },
            "review": {"status": "pending", "reviewer": None, "reviewed_at": None, "notes": None},
        })
    payload = {
        "meta": {
            "version": "dbnary-alignment-review-v1",
            "purpose": "audit only; never publish Wiktextract records directly",
            "wiktextract_dump_sha256": dump_hash,
            "aligned_dbnary_analysis": str(aligned_analysis.relative_to(ROOT)) if aligned_analysis else None,
        },
        "items": queue,
    }
    QUEUE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(payload)
    return payload


def write_report(payload: dict[str, object]) -> None:
    items = payload["items"]
    counts = defaultdict(int)
    for item in items:
        counts[item["alignment_decision"]] += 1
    lines = [
        "# DBnary 同快照复核队列",
        "",
        f"> 共 {len(items):,} 项：Wiktextract 在同 lemma/POS 下有释义、而当前运行时 DBnary 没有定义的候选。此文件不含可发布释义。",
        "",
        "## 当前结论",
        "",
        "| 分类 | 数量 | 含义 |",
        "|---|---:|---|",
    ]
    labels = {
        "pending_aligned_dbnary_snapshot": "等待从与 Wiktextract dump 同日期的 DBnary 历史提取物复核；不得判断为解析问题",
        "dbnary_aligned_extract_captured": "同快照 DBnary 已被现有导入器捕获；应调查当前生产快照/构建范围",
        "dbnary_parser_capture_gap": "同快照原始 DBnary 含定义信号但现有解析未捕获；修解析器后仍须审核内容",
        "dbnary_extract_entry_without_definition": "同快照 DBnary 有词条但未给可解析定义；属于 DBnary 提取覆盖限制",
        "dbnary_source_uncovered_same_snapshot": "同快照 DBnary 无匹配词条；属于 DBnary 来源覆盖限制",
    }
    for name in labels:
        lines.append(f"| {name} | {counts[name]:,} | {labels[name]} |")
    lines += [
        "",
        "## 审核规则",
        "",
        "- 只有 `dbnary_parser_capture_gap` 可以进入导入器修复任务；修复后仍需重新构建和人工审校。",
        "- 任何 Wiktextract 定义都不能直接进入 SQLite、运行时数据或教学内容。",
        "- `review` 字段必须由具备法语词典审核资格的编辑填写；自动分类不是发布许可。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aligned-analysis", type=Path, help="analysis JSON from import_dbnary.py against a same-date DBnary extract")
    args = parser.parse_args()
    payload = build_queue(args.aligned_analysis)
    counts = defaultdict(int)
    for item in payload["items"]:
        counts[item["alignment_decision"]] += 1
    print(json.dumps({"items": len(payload["items"]), **counts}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
