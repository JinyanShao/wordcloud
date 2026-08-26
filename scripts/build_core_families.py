#!/usr/bin/env python3
"""Select the reproducible 100 high-value French word families."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
OUT_JSON = ROOT / "data" / "processed" / "core-families-100.json"
OUT_MD = ROOT / "data" / "reports" / "core-families-100.md"
FAMILY_RELATIONS = {"derivation", "conversion_or_lexicalization", "etymological_family"}
CORE_RELATIONS = FAMILY_RELATIONS | {"synonym", "antonym", "compare", "trap"}
CEFR_WEIGHT = {"A1": 6, "A2": 5, "B1": 4, "B2": 3, "C1": 2, "C2": 1}


def family_components(conn: sqlite3.Connection) -> list[set[int]]:
    adj: dict[int, set[int]] = defaultdict(set)
    for row in conn.execute("SELECT a_id,b_id FROM official_edges WHERE relation IN (?,?,?)", tuple(FAMILY_RELATIONS)):
        adj[row["a_id"]].add(row["b_id"])
        adj[row["b_id"]].add(row["a_id"])
    seen: set[int] = set()
    components: list[set[int]] = []
    for node_id in sorted(adj):
        if node_id in seen:
            continue
        component: set[int] = set()
        queue = deque([node_id])
        seen.add(node_id)
        while queue:
            current = queue.popleft()
            component.add(current)
            for other in adj[current]:
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
        if len(component) >= 2:
            components.append(component)
    return components


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    lexemes = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM lexemes")}
    source_counts = dict(conn.execute("SELECT review_status,COUNT(*) FROM official_edges GROUP BY review_status"))
    rows: list[dict[str, object]] = []
    for component in family_components(conn):
        members = [lexemes[item] for item in component if item in lexemes]
        default = [m for m in members if m["cefr_level"] in CEFR_WEIGHT and m["status"] in {"eligible", "auxiliary"}]
        extended = [m for m in members if m not in default]
        if not default:
            continue
        pos = Counter(m["pos"] for m in default)
        edges = conn.execute(
            f"""
            SELECT relation,review_status,COUNT(*) AS n
            FROM official_edges
            WHERE a_id IN ({','.join('?' for _ in component)})
              AND b_id IN ({','.join('?' for _ in component)})
              AND relation IN ({','.join('?' for _ in CORE_RELATIONS)})
            GROUP BY relation,review_status
            """,
            [*component, *component, *CORE_RELATIONS],
        ).fetchall()
        rel = Counter()
        reviewed = sourced = 0
        for edge in edges:
            rel[edge["relation"]] += edge["n"]
            if edge["review_status"] == "reviewed":
                reviewed += edge["n"]
            else:
                sourced += edge["n"]
        core = max(default, key=lambda m: (
            CEFR_WEIGHT.get(m["cefr_level"], 0),
            m["flelex_frequency"] or 0,
            pos[m["pos"]],
            -m["id"],
        ))
        common_members = sum(1 for m in default if (m["flelex_frequency"] or 0) >= 1 or m["cefr_level"] in {"A1", "A2", "B1"})
        score = (
            (core["flelex_frequency"] or 0) * 0.08
            + sum(CEFR_WEIGHT.get(m["cefr_level"], 0) for m in default) * 0.45
            + common_members * 1.4
            + len(pos) * 3.0
            + rel["derivation"] * 1.2
            + rel["conversion_or_lexicalization"] * 1.0
            + rel["etymological_family"] * 0.7
            + reviewed * 1.5
        )
        reason = []
        if core["cefr_level"] in {"A1", "A2"}:
            reason.append("入口词高频低级别")
        if len(pos) >= 3:
            reason.append("覆盖动词/名词/形容词等多词性")
        if rel["derivation"]:
            reason.append("含现代派生规律")
        if rel["conversion_or_lexicalization"]:
            reason.append("含词类转换/词汇化提醒")
        if rel["etymological_family"]:
            reason.append("含历史同源但非规则派生")
        if reviewed:
            reason.append("有编辑审校关系可直接教学")
        rows.append({
            "core": {"id": core["id"], "lemma": core["lemma"], "pos": core["pos"], "cefr": core["cefr_level"], "gloss": core["gloss_zh"] or ""},
            "score": round(score, 4),
            "reason": "；".join(reason[:4]) or "频率、CEFR 和来源完整度综合较高",
            "defaultMembers": [
                {"id": m["id"], "lemma": m["lemma"], "pos": m["pos"], "cefr": m["cefr_level"], "gloss": m["gloss_zh"] or ""}
                for m in sorted(default, key=lambda m: (m["cefr_level"] or "Z", m["lemma"], m["pos"]))
            ],
            "extendedMembers": [
                {"id": m["id"], "lemma": m["lemma"], "pos": m["pos"], "cefr": m["cefr_level"], "gloss": m["gloss_zh"] or ""}
                for m in sorted(extended, key=lambda m: (m["lemma"], m["pos"]))
            ],
            "relationCounts": dict(sorted(rel.items())),
            "reviewedRelations": reviewed,
            "sourcedRelations": sourced,
        })
    selected = sorted(rows, key=lambda item: (-item["score"], item["core"]["lemma"], item["core"]["pos"]))[:100]
    payload = {
        "meta": {
            "version": "core-families-100-v1",
            "selection_count": len(selected),
            "independent_lexeme_count": len({m["id"] for f in selected for m in f["defaultMembers"] + f["extendedMembers"]}),
            "default_member_count": sum(len(f["defaultMembers"]) for f in selected),
            "extended_member_count": sum(len(f["extendedMembers"]) for f in selected),
            "public_review_status_counts": source_counts,
            "selection_basis": ["FLELex frequency", "CEFR", "modern member count", "POS coverage", "teaching value", "source completeness"],
        },
        "families": selected,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 100 个高频核心词族",
        "",
        f"- 独立词条：{payload['meta']['independent_lexeme_count']}",
        f"- 默认成员：{payload['meta']['default_member_count']}",
        f"- 扩展成员：{payload['meta']['extended_member_count']}",
        "",
        "| # | 核心词 | 分数 | 默认/扩展 | 关系 | 选择理由 |",
        "|---:|---|---:|---:|---|---|",
    ]
    for index, family in enumerate(selected, start=1):
        rels = ", ".join(f"{k}×{v}" for k, v in family["relationCounts"].items()) or "—"
        core = family["core"]
        lines.append(
            f"| {index} | {core['lemma']} / {core['pos']} / {core['cefr']} | {family['score']:.2f} | "
            f"{len(family['defaultMembers'])}/{len(family['extendedMembers'])} | {rels} | {family['reason']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["meta"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
