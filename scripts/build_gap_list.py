#!/usr/bin/env python3
"""Build the core-word gap list: which eligible words most lack official relations.

Reads `data/processed/wordcloud.sqlite` and writes:

- `data/reports/core-word-gap-list.csv`: sortable per-word gap table
- `data/reports/core-word-gap-list.md`: summary report with bucket counts and examples

Buckets follow the priority order in `handover/7.27-handover.md` §九:

1. `P1_no_official`   高频且没有任何官方关系
2. `P2_single_edge`   高频且只有一条官方关系
3. `P3_bridge`        多义项但连接稀少、可桥接不同词群
4. `P4_confusable`    有形音候选但没有正式 trap/compare 关系
5. `P5_b2c1_synset`   B2–C1 有 DBnary 义项但没有明示近义/反义
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
REPORT_CSV = ROOT / "data" / "reports" / "core-word-gap-list.csv"
REPORT_MD = ROOT / "data" / "reports" / "core-word-gap-list.md"

CORE_TARGET = 1000
BRIDGE_MIN_SENSES = 4
BRIDGE_MAX_EDGES = 2

BUCKET_ORDER = ["P1_no_official", "P2_single_edge", "P3_bridge", "P4_confusable", "P5_b2c1_synset"]
BUCKET_LABELS = {
    "P1_no_official": "高频且没有任何官方关系",
    "P2_single_edge": "高频且只有一条官方关系",
    "P3_bridge": "多义项桥接词（义项多、连接少）",
    "P4_confusable": "易混淆候选（有形音候选、无正式 trap/compare）",
    "P5_b2c1_synset": "B2–C1 近义集合缺口（有义项、无近/反义边）",
}
BUCKET_ACTIONS = {
    "P1_no_official": "先查 Démonette 直接词族与 DBnary 明示近/反义，再人工补第一条正式关系",
    "P2_single_edge": "补第二条正式关系，形成最小学习语境",
    "P3_bridge": "按义项梳理，为不同义项各连接对应词群",
    "P4_confusable": "人工判断形音候选，审校后发布 trap/compare",
    "P5_b2c1_synset": "从 DBnary 义项挖掘近义集合，人工补辨析维度",
}


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    lexemes = conn.execute(
        """
        SELECT id, lemma, pos, cefr_level, flelex_frequency, lexique_frequency, gloss_zh
        FROM lexemes WHERE status='eligible'
        """
    ).fetchall()

    official: dict[int, Counter] = {}
    for row in conn.execute(
        """
        SELECT lexeme_id, relation, COUNT(*) AS n FROM (
          SELECT a_id AS lexeme_id, relation FROM official_edges
          UNION ALL
          SELECT b_id AS lexeme_id, relation FROM official_edges
        ) GROUP BY lexeme_id, relation
        """
    ):
        official.setdefault(row["lexeme_id"], Counter())[row["relation"]] = row["n"]

    senses = {
        row["lexeme_id"]: row["n"]
        for row in conn.execute("SELECT lexeme_id, COUNT(*) AS n FROM lexeme_senses GROUP BY lexeme_id")
    }
    has_dbnary = {row["lexeme_id"] for row in conn.execute("SELECT DISTINCT lexeme_id FROM lexical_entries")}

    candidates: dict[int, Counter] = {}
    for row in conn.execute(
        """
        SELECT lexeme_id, signal, COUNT(*) AS n FROM (
          SELECT a_id AS lexeme_id, signal FROM edge_candidates WHERE status='candidate'
          UNION ALL
          SELECT b_id AS lexeme_id, signal FROM edge_candidates WHERE status='candidate'
        ) GROUP BY lexeme_id, signal
        """
    ):
        candidates.setdefault(row["lexeme_id"], Counter())[row["signal"]] = row["n"]

    rows = []
    for lex in lexemes:
        rel = official.get(lex["id"], Counter())
        cand = candidates.get(lex["id"], Counter())
        n_official = sum(rel.values())
        n_senses = senses.get(lex["id"], 0)
        n_syn_ant = rel.get("syn", 0) + rel.get("ant", 0)
        n_other = n_official - rel.get("fam", 0) - n_syn_ant
        freq = lex["flelex_frequency"] if lex["flelex_frequency"] is not None else (lex["lexique_frequency"] or 0.0)

        flags = []
        if n_official == 0:
            flags.append("P1_no_official")
        if n_official == 1:
            flags.append("P2_single_edge")
        if n_senses >= BRIDGE_MIN_SENSES and n_official <= BRIDGE_MAX_EDGES:
            flags.append("P3_bridge")
        if (cand.get("spelling", 0) or cand.get("phonetic", 0)) and not (rel.get("trap") or rel.get("compare")):
            flags.append("P4_confusable")
        if lex["cefr_level"] in ("B2", "C1", "C2") and lex["id"] in has_dbnary and n_syn_ant == 0:
            flags.append("P5_b2c1_synset")
        if not flags:
            continue

        bucket = next(b for b in BUCKET_ORDER if b in flags)
        rows.append({
            "lemma": lex["lemma"],
            "pos": lex["pos"],
            "cefr_level": lex["cefr_level"] or "",
            "frequency": round(freq, 4),
            "n_official": n_official,
            "n_fam": rel.get("fam", 0),
            "n_syn": rel.get("syn", 0),
            "n_ant": rel.get("ant", 0),
            "n_other": n_other,
            "n_senses": n_senses,
            "has_dbnary": int(lex["id"] in has_dbnary),
            "n_cand_morphology": cand.get("morphology", 0),
            "n_cand_spelling": cand.get("spelling", 0),
            "n_cand_phonetic": cand.get("phonetic", 0),
            "bucket": bucket,
            "flags": "|".join(b for b in BUCKET_ORDER if b in flags),
            "gloss_zh": (lex["gloss_zh"] or "").replace("\n", " "),
        })

    rows.sort(key=lambda r: (BUCKET_ORDER.index(r["bucket"]), -r["frequency"], r["lemma"]))
    for i, row in enumerate(rows):
        row["rank"] = i + 1
        row["in_core"] = int(i < CORE_TARGET)
        row["suggested_action"] = BUCKET_ACTIONS[row["bucket"]]

    fieldnames = [
        "rank", "lemma", "pos", "cefr_level", "frequency",
        "n_official", "n_fam", "n_syn", "n_ant", "n_other",
        "n_senses", "has_dbnary",
        "n_cand_morphology", "n_cand_spelling", "n_cand_phonetic",
        "bucket", "flags", "in_core", "suggested_action", "gloss_zh",
    ]
    with REPORT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    bucket_counts = Counter(r["bucket"] for r in rows)
    bucket_core = Counter(r["bucket"] for r in rows if r["in_core"])
    flag_counts = Counter(flag for r in rows for flag in r["flags"].split("|"))
    eligible_total = len(lexemes)

    lines = [
        "# 核心词缺口清单",
        "",
        "> 生成命令：`python3 scripts/build_gap_list.py`。明细见 `core-word-gap-list.csv`（可排序，`in_core=1` 为本轮核心词）。",
        "",
        "## 总览",
        "",
        f"- eligible 主词：{eligible_total:,}",
        f"- 存在至少一类缺口的词：{len(rows):,}（{len(rows) / eligible_total:.1%}）",
        f"- 本轮核心词目标：{CORE_TARGET:,} 个，按缺口优先级与频率排序取前 {CORE_TARGET:,}",
        "",
        "| 优先级 | 缺口类型 | 全部 | 进入核心词 |",
        "|---|---|---:|---:|",
    ]
    for bucket in BUCKET_ORDER:
        lines.append(f"| {bucket} | {BUCKET_LABELS[bucket]} | {bucket_counts.get(bucket, 0):,} | {bucket_core.get(bucket, 0):,} |")

    lines += [
        "",
        "一词可命中多类缺口；命中各类的总词数（不限主桶）如下：",
        "",
        "| 缺口类型 | 命中词数（含非主桶） |",
        "|---|---:|",
    ]
    for bucket in BUCKET_ORDER:
        lines.append(f"| {bucket} | {flag_counts.get(bucket, 0):,} |")

    lines += [
        "",
        "## 判定规则",
        "",
        f"- P1：官方关系数 = 0；P2：官方关系数 = 1。",
        f"- P3：法语义项数 ≥ {BRIDGE_MIN_SENSES} 且官方关系数 ≤ {BRIDGE_MAX_EDGES}。",
        "- P4：存在 spelling/phonetic 候选，但没有任何正式 trap/compare 边。",
        "- P5：CEFR 为 B2–C2、能对齐 DBnary 义项，但没有任何明示 syn/ant 边。",
        "- 一词可同时命中多类（见 CSV 的 `flags`），`bucket` 取最高优先级；同优先级内按频率降序。",
        "- 频率取 FleLex 频率，缺失时回退 Lexique 词元频率。",
        "",
        "## P1 高频零关系 Top 20",
        "",
        "| 词 | 词性 | CEFR | 频率 | 义项数 | 形音候选 | 中文提示 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in [r for r in rows if r["bucket"] == "P1_no_official"][:20]:
        lines.append(
            f"| {row['lemma']} | {row['pos']} | {row['cefr_level']} | {row['frequency']:.1f} "
            f"| {row['n_senses']} | {row['n_cand_spelling'] + row['n_cand_phonetic']} | {row['gloss_zh']} |"
        )

    lines += [
        "",
        "## P2 高频单关系 Top 20",
        "",
        "| 词 | 词性 | CEFR | 频率 | 已有关系 | 中文提示 |",
        "|---|---|---|---:|---|---|",
    ]
    for row in [r for r in rows if r["bucket"] == "P2_single_edge"][:20]:
        existing = ", ".join(f"{k}×{v}" for k, v in [("fam", row["n_fam"]), ("syn", row["n_syn"]), ("ant", row["n_ant"]), ("other", row["n_other"])] if v)
        lines.append(
            f"| {row['lemma']} | {row['pos']} | {row['cefr_level']} | {row['frequency']:.1f} "
            f"| {existing} | {row['gloss_zh']} |"
        )

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"eligible={eligible_total:,} with_gaps={len(rows):,} core={sum(bucket_core.values()):,}")
    for bucket in BUCKET_ORDER:
        print(f"  {bucket}: total={bucket_counts.get(bucket, 0):,} core={bucket_core.get(bucket, 0):,}")
    print(f"wrote {REPORT_CSV.relative_to(ROOT)} and {REPORT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
