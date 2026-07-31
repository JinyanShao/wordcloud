#!/usr/bin/env python3
"""Classify DBnary definition gaps with Wiktextract's JSONL output.

This is an audit-only adapter: Wiktextract remains the extractor and its
Wiktionary-derived records are never silently promoted into runtime content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from learning_lexicon import learning_lexeme_rows, normalize


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "maillage.sqlite"
DUMP = ROOT / "data" / "raw" / "wiktextract" / "frwiktionary-20260701-pages-articles.xml.bz2"
OUTPUT = ROOT / "data" / "processed" / "wiktextract-gap-audit.jsonl"
REPORT = ROOT / "data" / "reports" / "wiktextract-gap-audit.md"
WIKTWORDS_ENV = "WIKTWORDS_BIN"
POS = {"noun": "NOM", "verb": "VER", "adjective": "ADJ", "adverb": "ADV"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gaps() -> dict[tuple[str, str], dict[str, object]]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = learning_lexeme_rows(conn)
    missing = {
        (str(row["normalized"]), str(row["pos"])): dict(row)
        for row in rows
        if not conn.execute("SELECT 1 FROM lexeme_senses WHERE lexeme_id=? LIMIT 1", (row["id"],)).fetchone()
    }
    conn.close()
    return missing


def wiktwords_bin() -> str:
    """Resolve the upstream CLI without baking a machine-specific venv path in."""
    configured = os.environ.get(WIKTWORDS_ENV)
    if configured:
        return configured
    discovered = shutil.which("wiktwords")
    if discovered:
        return discovered
    raise SystemExit(
        "missing Wiktextract CLI. Install the pinned audit dependency, activate its "
        f"environment, or set {WIKTWORDS_ENV}=/path/to/wiktwords"
    )


def has_glossed_sense(entry: dict[str, object]) -> bool:
    senses = entry.get("senses")
    return isinstance(senses, list) and any(
        isinstance(sense, dict) and bool(sense.get("glosses")) for sense in senses
    )


def run() -> None:
    if not DUMP.exists():
        raise SystemExit(f"missing official dump: {DUMP}")
    pending = gaps()
    pages = sorted({row["lemma"] for row in pending.values()})
    command = [wiktwords_bin(), "--dump-file-language-code", "fr", "--language-code", "fr", "--all", "--out", str(OUTPUT)]
    command.extend(part for page in pages for part in ("--page", page))
    command.append(str(DUMP))
    subprocess.run(command, cwd=ROOT, check=True)


def report() -> None:
    if not OUTPUT.exists():
        raise SystemExit("run audit_wiktextract.py run first")
    pending = gaps()
    records: dict[str, list[dict[str, object]]] = defaultdict(list)
    with OUTPUT.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("lang_code") == "fr":
                records[normalize(row.get("word"))].append(row)
    buckets: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for (lemma, pos), row in pending.items():
        entries = records.get(lemma, [])
        matching = [entry for entry in entries if POS.get(entry.get("pos")) == pos]
        if matching and any(has_glossed_sense(entry) for entry in matching):
            bucket = "wiktionary_usable_differential"
        elif matching:
            bucket = "matched_without_definition"
        elif entries:
            bucket = "lemma_found_pos_mismatch"
        else:
            bucket = "not_found_in_dump"
        buckets[bucket] += 1
        if len(examples[bucket]) < 12:
            examples[bucket].append(f"{row['lemma']} · {pos} · {row['cefr_level'] or '—'}")
    total = len(pending)
    lines = [
        "# Wiktextract 与 DBnary 缺口差异审计",
        "",
        f"> 审计 {total:,} 个运行时学习词中缺少 DBnary 定义的词。Wiktextract 仅用于分类，不自动发布其结果。",
        "",
        "## 可复现输入",
        "",
        f"- dump：`{DUMP.relative_to(ROOT)}`",
        f"- SHA-256：`{sha256(DUMP)}`",
        "- extractor：Wiktextract 1.99.7，Git commit `d9fa2335957c9089ce2c3fb110a075cf072903da`（MIT 代码）",
        "- lexical data：French Wiktionary；后续任何发布仍须按 Wiktionary/CC BY-SA 要求归属与许可。",
        "",
        "## 分类",
        "",
        "| 分类 | 数量 | 占缺口比例 | 含义与处理建议 |",
        "|---|---:|---:|---|",
    ]
    remedies = {
        "wiktionary_usable_differential": "较新 Wiktionary 快照有同词性释义；属 DBnary 快照/解析差异候选，须同版本复核后才能认定解析漏捕",
        "matched_without_definition": "检查模板、重定向或词形条目；不得自动补定义",
        "lemma_found_pos_mismatch": "进入 lemma/POS 映射审计队列",
        "not_found_in_dump": "标为来源未覆盖，进入独立来源或人工编纂队列",
    }
    for name in ("wiktionary_usable_differential", "matched_without_definition", "lemma_found_pos_mismatch", "not_found_in_dump"):
        count = buckets[name]
        lines.append(f"| {name} | {count:,} | {count / max(1, total):.1%} | {remedies[name]} |")
    lines += ["", "## 每类样本", ""]
    for name, values in examples.items():
        lines += [f"### {name}", "", *[f"- {value}" for value in values], ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pending": total, **buckets, "report": str(REPORT.relative_to(ROOT))}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "report"))
    args = parser.parse_args()
    if args.command == "run":
        run()
    else:
        report()


if __name__ == "__main__":
    main()
