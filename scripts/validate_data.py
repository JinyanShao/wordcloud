#!/usr/bin/env python3
"""Validate generated maillage artifacts and write an inspectable build report."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "maillage.sqlite"
REPORT = ROOT / "data" / "reports" / "build-validation.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UnionFind:
    def __init__(self, ids: list[int]):
        self.parent = {item: item for item in ids}

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append((name, bool(passed), detail))

    sources = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    source_errors = []
    for source in sources:
        if not source["license_id"] or not source["attribution"]:
            source_errors.append(f"{source['id']}: missing license/attribution")
        if source["local_path"]:
            path = ROOT / source["local_path"]
            if not path.exists():
                source_errors.append(f"{source['id']}: local file missing")
            elif source["sha256"] != sha256(path):
                source_errors.append(f"{source['id']}: SHA-256 mismatch")
    check("来源登记、许可与哈希", not source_errors, "; ".join(source_errors) or f"{len(sources)} 个来源均完整")

    total, unique = conn.execute("SELECT COUNT(*), COUNT(DISTINCT normalized || char(31) || pos) FROM lexemes").fetchone()
    check("词汇单位唯一", total == unique, f"{total:,} rows / {unique:,} unique lemma+POS")

    audit = conn.execute(
        """
        SELECT COUNT(*) AS n, COUNT(DISTINCT lexeme_id) AS unique_n,
               SUM(manual_decision IS NOT NULL AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL) AS reviewed
        FROM audit_samples
        """
    ).fetchone()
    check("500 条分层人工抽检", audit["n"] == 500 and audit["unique_n"] == 500 and audit["reviewed"] == 500,
          f"sample={audit['n']}, unique={audit['unique_n']}, reviewed={audit['reviewed']}")

    invalid_auto = conn.execute(
        """
        SELECT COUNT(*) FROM lexemes
        WHERE status='eligible'
          AND decision_reason NOT LIKE 'manual_audit_override:%'
          AND (cefr_level NOT IN ('B1','B2','C1') OR pos NOT IN ('NOM','VER','ADJ','ADV') OR has_lexique=0)
        """
    ).fetchone()[0]
    invalid_unglossed = conn.execute(
        """
        SELECT COUNT(*) FROM lexemes
        WHERE status='eligible' AND has_cfdict=0 AND flelex_frequency < 1
          AND decision_reason NOT LIKE 'manual_audit_override:%'
        """
    ).fetchone()[0]
    check("自动 eligible 规则", invalid_auto == 0 and invalid_unglossed == 0,
          f"结构违规={invalid_auto}, 无释义低频违规={invalid_unglossed}; 人工覆盖例外另有记录")

    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    reversed_edges = conn.execute(
        "SELECT (SELECT COUNT(*) FROM layout_links WHERE a_id>=b_id) + (SELECT COUNT(*) FROM official_edges WHERE a_id>=b_id)"
    ).fetchone()[0]
    check("图端点与方向约束", not fk_errors and reversed_edges == 0, f"foreign-key errors={len(fk_errors)}, invalid order={reversed_edges}")

    official_count = conn.execute("SELECT COUNT(*) FROM official_edges").fetchone()[0]
    sourced_count = conn.execute("SELECT COUNT(DISTINCT edge_id) FROM official_edge_sources").fetchone()[0]
    check("官方边来源完整", official_count > 0 and official_count == sourced_count, f"{sourced_count}/{official_count} 条有来源")

    positions = conn.execute("SELECT lexeme_id FROM positions ORDER BY lexeme_id").fetchall()
    position_ids = [row[0] for row in positions]
    layout_edges = conn.execute("SELECT a_id,b_id,signal FROM layout_links").fetchall()
    uf = UnionFind(position_ids)
    position_set = set(position_ids)
    for edge in layout_edges:
        if edge[0] in position_set and edge[1] in position_set:
            uf.union(edge[0], edge[1])
    components = len({uf.find(item) for item in position_ids}) if position_ids else 0
    isolated = conn.execute(
        """
        SELECT COUNT(*) FROM positions p
        WHERE NOT EXISTS (SELECT 1 FROM layout_links l WHERE l.a_id=p.lexeme_id OR l.b_id=p.lexeme_id)
        """
    ).fetchone()[0]
    check("稳定坐标与全图连通", len(position_ids) > 0 and components == 1 and isolated == 0,
          f"nodes={len(position_ids):,}, components={components}, isolated={isolated}")

    signal_counts = Counter(row[2] for row in layout_edges)
    required_signals = {"semantic", "morphology", "spelling", "phonetic", "editorial_seed", "skeleton"}
    check("六类制图信号", required_signals <= set(signal_counts),
          ", ".join(f"{name}={signal_counts[name]:,}" for name in sorted(signal_counts)))

    morphbase_promoted = conn.execute(
        """
        SELECT COUNT(*) FROM edge_candidates
        WHERE source_id='lexique_400' AND signal='derivation'
        """
    ).fetchone()[0]
    regression = conn.execute(
        """
        SELECT
          SUM(l.signal='morphology') AS morphology_n,
          SUM(l.signal='derivation') AS derivation_n
        FROM layout_links l
        JOIN lexemes a ON a.id=l.a_id
        JOIN lexemes b ON b.id=l.b_id
        WHERE (a.normalized='division' AND b.normalized='voir')
           OR (a.normalized='voir' AND b.normalized='division')
        """
    ).fetchone()
    check(
        "Lexique MorphoBase 不冒充派生关系",
        morphbase_promoted == 0 and regression["morphology_n"] == 1 and not regression["derivation_n"],
        f"promoted={morphbase_promoted}, division↔voir morphology={regression['morphology_n'] or 0}, derivation={regression['derivation_n'] or 0}",
    )

    eligible = conn.execute("SELECT COUNT(*) FROM lexemes WHERE status='eligible'").fetchone()[0]
    supports = conn.execute(
        "SELECT COUNT(*) FROM positions p JOIN lexemes l ON l.id=p.lexeme_id WHERE l.status!='eligible'"
    ).fetchone()[0]
    check("主词与支撑词分账", len(position_ids) == eligible + supports,
          f"eligible={eligible:,}, support={supports}, rendered={len(position_ids):,}")

    runtime = ROOT / "graph-data.js"
    frontend_text = (ROOT / "app.js").read_text(encoding="utf-8") + (ROOT / "index.html").read_text(encoding="utf-8")
    check("静态运行时已导出", runtime.exists() and runtime.stat().st_size > 100_000, f"graph-data.js={runtime.stat().st_size if runtime.exists() else 0:,} bytes")
    check(
        "前端不再依赖 CLUSTERS",
        "CLUSTERS" not in frontend_text and 'src="data.js"' not in frontend_text,
        "canvas 读取 graph-data.js 固定坐标",
    )

    passed = sum(result for _, result, _ in checks)
    lines = [
        "# maillage 构建验证",
        "",
        f"> {passed}/{len(checks)} 项通过。验证对象为当前 SQLite、稳定坐标与浏览器导出物。",
        "",
        "| 检查 | 结果 | 证据 |",
        "|---|---|---|",
    ]
    for name, result, detail in checks:
        lines.append(f"| {name} | {'通过' if result else '失败'} | {detail} |")
    lines += [
        "",
        "## 边界",
        "",
        "这份验证证明构建一致性、许可登记完整性和制图连通性，不证明自动候选等同于可靠语言学关系。只有 `official_edges` 才是产品可陈述关系；其余边继续保留候选或布局身份。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    conn.close()
    print(json.dumps({"passed": passed, "total": len(checks), "report": str(REPORT.relative_to(ROOT))}, ensure_ascii=False))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
