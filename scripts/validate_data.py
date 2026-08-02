#!/usr/bin/env python3
"""Validate generated wordcloud artifacts and write an inspectable build report."""

from __future__ import annotations

import hashlib
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from learning_lexicon import learning_lexeme_rows


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
REPORT = ROOT / "data" / "reports" / "build-validation.md"
SEED = ROOT / "data" / "processed" / "editorial-seed.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_cache_errors(runtime: Path) -> list[str]:
    digest = hashlib.sha256()
    digest.update(runtime.read_bytes())
    digest.update((ROOT / "app.js").read_bytes())
    version = digest.hexdigest()[:12]
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    service_worker = (ROOT / "sw.js").read_text(encoding="utf-8")
    expected_url = f"graph-data.js?v={version}"
    expected_app_url = f"app.js?v={version}"
    expected_cache = f'const CACHE_NAME = "wordcloud-learning-{version}";'
    errors = []
    if expected_url not in index:
        errors.append("index.html does not reference current graph-data hash")
    if expected_url not in service_worker:
        errors.append("sw.js does not precache current graph-data hash")
    if expected_app_url not in index or expected_app_url not in service_worker:
        errors.append("app.js does not share current runtime cache version")
    if expected_cache not in service_worker:
        errors.append("sw.js cache name does not match current graph-data hash")
    return errors


def runtime_constant(runtime_text: str, name: str) -> object:
    match = re.search(rf"^const {name}=(.+);$", runtime_text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing runtime constant: {name}")
    return json.loads(match.group(1))


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


def foundational_core() -> list[dict[str, str]]:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    entries = payload.get("foundationalCore", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed foundationalCore must be a list")
    return [
        {"id": str(item["id"]), "pos": str(item["pos"]), "gloss": str(item["gloss"])}
        for item in entries
    ]


def editorial_learning() -> list[dict[str, object]]:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    entries = payload.get("editorialLearning", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed editorialLearning must be a list")
    return entries


def editorial_teaching_examples() -> list[dict[str, object]]:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    entries = payload.get("editorialTeachingExamples", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed editorialTeachingExamples must be a list")
    return entries


def editorial_teaching_example_errors() -> list[str]:
    core = {(item["id"].replace("’", "'").lower(), item["pos"].upper()) for item in foundational_core()}
    seen: set[tuple[str, str]] = set()
    errors: list[str] = []
    for item in editorial_teaching_examples():
        key = (str(item.get("id", "")).replace("’", "'").lower(), str(item.get("pos", "")).upper())
        if key in seen:
            errors.append(f"{key[0]}/{key[1]}: duplicate")
        seen.add(key)
        if key not in core:
            errors.append(f"{key[0]}/{key[1]}: not a foundational core lexeme")
        if any(not str(item.get(field, "")).strip() for field in ("source", "reviewer", "reviewedAt")):
            errors.append(f"{key[0]}/{key[1]}: missing review provenance")
        examples = item.get("examples")
        if not isinstance(examples, list) or len(examples) < 2:
            errors.append(f"{key[0]}/{key[1]}: requires at least two teaching examples")
            continue
        for example in examples:
            text = str(example.get("text", "")).strip() if isinstance(example, dict) else ""
            gloss = str(example.get("gloss", "")).strip() if isinstance(example, dict) else ""
            if not text or not gloss or len(text) > 110:
                errors.append(f"{key[0]}/{key[1]}: invalid or overlong teaching example")
                break
    return errors


def editorial_relation_errors() -> list[str]:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    errors: list[str] = []
    for item in payload.get("editorialRelations", []):
        key = f"{item.get('a')}:{item.get('b')}"
        required = ("a", "aPos", "b", "bPos", "type", "dimension", "label", "explanation", "source", "reviewer", "reviewedAt")
        if any(not str(item.get(field) or "").strip() for field in required):
            errors.append(f"{key}: missing required metadata")
        if item.get("type") != "compare":
            errors.append(f"{key}: only reviewed compare relations are allowed in this core slice")
        examples = item.get("examples")
        if not isinstance(examples, list) or len(examples) < 2 or not all(str(example).strip() for example in examples):
            errors.append(f"{key}: requires two minimal-context examples")
    return errors


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
          AND decision_reason NOT LIKE 'editorial_foundational_core:%'
          AND (cefr_level NOT IN ('B1','B2','C1') OR pos NOT IN ('NOM','VER','ADJ','ADV') OR has_lexique=0)
        """
    ).fetchone()[0]
    invalid_unglossed = conn.execute(
        """
        SELECT COUNT(*) FROM lexemes
        WHERE status='eligible' AND has_cfdict=0 AND flelex_frequency < 1
          AND decision_reason NOT LIKE 'manual_audit_override:%'
          AND decision_reason NOT LIKE 'editorial_foundational_core:%'
        """
    ).fetchone()[0]
    check("自动 eligible 规则", invalid_auto == 0 and invalid_unglossed == 0,
          f"结构违规={invalid_auto}, 无释义低频违规={invalid_unglossed}; 人工覆盖例外另有记录")

    core_errors = []
    for item in foundational_core():
        row = conn.execute(
            """
            SELECT l.id,l.status,l.gloss_zh,
                   EXISTS(SELECT 1 FROM lexical_entries le WHERE le.lexeme_id=l.id) AS has_definition,
                   EXISTS(SELECT 1 FROM positions p WHERE p.lexeme_id=l.id) AS rendered
            FROM lexemes l WHERE l.normalized=lower(?) AND l.pos=?
            """,
            (item["id"].replace("’", "'").strip(), item["pos"]),
        ).fetchone()
        if not row:
            core_errors.append(f"{item['id']}/{item['pos']}: missing")
        elif row["status"] != "eligible" or row["gloss_zh"] != item["gloss"] or not row["has_definition"] or not row["rendered"]:
            core_errors.append(
                f"{item['id']}/{item['pos']}: status={row['status']}, gloss={row['gloss_zh']!r}, "
                f"definition={row['has_definition']}, rendered={row['rendered']}"
            )
    check(
        "基础核心词词性、释义、义项与渲染回归",
        not core_errors,
        "; ".join(core_errors) or f"{len(foundational_core())} entries verified",
    )

    learning_errors = []
    learning_collocations = 0
    for item in editorial_learning():
        row = conn.execute(
            """
            SELECT l.id,
                   EXISTS(SELECT 1 FROM lexeme_etymologies e WHERE e.lexeme_id=l.id) AS has_etymology,
                   (SELECT COUNT(*) FROM lexeme_collocations c WHERE c.lexeme_id=l.id) AS collocations
            FROM lexemes l WHERE l.normalized=lower(?) AND l.pos=?
            """,
            (str(item["id"]).replace("’", "'").strip(), str(item["pos"]).upper()),
        ).fetchone()
        expected_collocations = item.get("collocations", [])
        if not row or not row["has_etymology"] or row["collocations"] != len(expected_collocations):
            learning_errors.append(f"{item.get('id')}/{item.get('pos')}: missing or incomplete")
        learning_collocations += len(expected_collocations)
    example_count = conn.execute("SELECT COUNT(*) FROM lexeme_senses WHERE examples_json != '[]'").fetchone()[0]
    check(
        "审校词源、搭配与义项例句",
        not learning_errors and example_count > 0,
        "; ".join(learning_errors) or f"learning entries={len(editorial_learning())}, collocations={learning_collocations}, sourced sense examples={example_count:,}",
    )
    teaching_example_errors = editorial_teaching_example_errors()
    runtime_text = (ROOT / "graph-data.js").read_text(encoding="utf-8")
    try:
        runtime_teaching_examples = runtime_constant(runtime_text, "GRAPH_TEACHING_EXAMPLES")
    except ValueError:
        runtime_teaching_examples = {}
    expected_teaching_example_count = sum(len(item["examples"]) for item in editorial_teaching_examples())
    exported_teaching_example_count = sum(len(examples) for examples in runtime_teaching_examples.values())
    check(
        "基础核心词教学例句",
        not teaching_example_errors
        and len(runtime_teaching_examples) == len(editorial_teaching_examples())
        and exported_teaching_example_count == expected_teaching_example_count,
        "; ".join(teaching_example_errors) or f"{len(editorial_teaching_examples())} 个基础词、{exported_teaching_example_count} 条短例句已导出",
    )

    expected_search_ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT id FROM lexemes
            WHERE status='auxiliary' AND cefr_level IN ('A1','A2')
              AND pos IN ('NOM','VER','ADJ','ADV') AND has_cfdict=1
              AND NOT EXISTS (SELECT 1 FROM positions p WHERE p.lexeme_id=lexemes.id)
            ORDER BY flelex_frequency DESC, lemma, pos
            """
        )
    ]
    try:
        runtime_search_lexemes = runtime_constant(runtime_text, "GRAPH_SEARCH_LEXEMES")
    except ValueError:
        runtime_search_lexemes = []
    exported_search_ids = [row[0] for row in runtime_search_lexemes]
    appartenir = conn.execute(
        "SELECT id FROM lexemes WHERE normalized='appartenir' AND pos='VER'"
    ).fetchone()
    graph_ids = {row[0] for row in conn.execute("SELECT lexeme_id FROM positions")}
    check(
        "A1/A2 实词可检索但不强行入图",
        set(exported_search_ids) == set(expected_search_ids)
        and appartenir is not None
        and appartenir[0] in exported_search_ids
        and not graph_ids.intersection(exported_search_ids),
        f"search-only={len(exported_search_ids):,}, appartenir/VER={'present' if appartenir and appartenir[0] in exported_search_ids else 'missing'}, overlap={len(graph_ids.intersection(exported_search_ids))}",
    )
    runtime_nodes = runtime_constant(runtime_text, "GRAPH_NODES")
    runtime_ids = {row[0] for row in runtime_nodes} | set(exported_search_ids)
    expected_learning_ids = {row["id"] for row in learning_lexeme_rows(conn)}
    runtime_status = runtime_constant(runtime_text, "GRAPH_CONTENT_STATUS")
    runtime_aliases = runtime_constant(runtime_text, "GRAPH_ALIASES")
    source_alias_count = sum(
        1 for row in conn.execute("SELECT lexeme_id FROM aliases") if row["lexeme_id"] in expected_learning_ids
    )
    exported_alias_count = sum(len(values) for values in runtime_aliases.values())
    check(
        "运行时学习词范围、内容状态与词形搜索回归",
        runtime_ids == expected_learning_ids
        and set(runtime_status) == {str(item) for item in runtime_ids}
        and set(runtime_status.values()) <= {"has_definition", "pending_definition"}
        and exported_alias_count == source_alias_count,
        f"learning={len(runtime_ids):,}, statuses={len(runtime_status):,}, aliases={exported_alias_count:,}",
    )

    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    reversed_edges = conn.execute(
        "SELECT (SELECT COUNT(*) FROM layout_links WHERE a_id>=b_id) + (SELECT COUNT(*) FROM official_edges WHERE a_id>=b_id)"
    ).fetchone()[0]
    check("图端点与方向约束", not fk_errors and reversed_edges == 0, f"foreign-key errors={len(fk_errors)}, invalid order={reversed_edges}")

    official_count = conn.execute("SELECT COUNT(*) FROM official_edges").fetchone()[0]
    sourced_count = conn.execute("SELECT COUNT(DISTINCT edge_id) FROM official_edge_sources").fetchone()[0]
    check("官方边来源完整", official_count > 0 and official_count == sourced_count, f"{sourced_count}/{official_count} 条有来源")

    editorial_errors = editorial_relation_errors()
    core_relation_count = conn.execute(
        """
        SELECT COUNT(*) FROM official_edge_sources
        WHERE source_id='wordcloud_editorial' AND json_valid(source_record)
          AND json_extract(source_record, '$.origin')='editorial_relation'
          AND COALESCE(TRIM(json_extract(source_record, '$.reviewer')), '') != ''
          AND COALESCE(TRIM(json_extract(source_record, '$.reviewed_at')), '') != ''
        """
    ).fetchone()[0]
    expected_core_relations = len(json.loads(SEED.read_text(encoding="utf-8")).get("editorialRelations", []))
    check(
        "核心词审校对比关系",
        not editorial_errors and core_relation_count == expected_core_relations,
        "; ".join(editorial_errors) or f"{core_relation_count}/{expected_core_relations} 条具完整审校、来源与例句",
    )

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
    required_signals = {"semantic", "derivation", "morphology", "spelling", "phonetic", "editorial_seed", "skeleton"}
    check("七类制图信号", required_signals <= set(signal_counts),
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

    demonette_candidates = conn.execute(
        "SELECT COUNT(*) FROM edge_candidates WHERE source_id='demonette_2' AND signal='derivation' AND status='sourced'"
    ).fetchone()[0]
    demonette_official = conn.execute(
        "SELECT COUNT(*) FROM official_edge_sources WHERE source_id='demonette_2'"
    ).fetchone()[0]
    demonette_same_pos = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_edge_sources s
        JOIN official_edges e ON e.id=s.edge_id
        JOIN lexemes a ON a.id=e.a_id
        JOIN lexemes b ON b.id=e.b_id
        WHERE s.source_id='demonette_2' AND a.pos=b.pos
        """
    ).fetchone()[0]
    demonette_invalid_same_pos = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_edge_sources s
        JOIN official_edges e ON e.id=s.edge_id
        JOIN lexemes a ON a.id=e.a_id
        JOIN lexemes b ON b.id=e.b_id
        WHERE s.source_id='demonette_2' AND a.pos=b.pos
          AND (
            e.subtype NOT IN ('prefixation','suffixation')
            OR json_extract(s.source_record, '$.complexity')!='simple'
            OR json_extract(s.source_record, '$.orientation')!='as2des'
          )
        """
    ).fetchone()[0]
    demonette_report = ROOT / "data" / "processed" / "demonette-analysis.json"
    report_gate = False
    if demonette_report.exists():
        report_gate = bool(json.loads(demonette_report.read_text(encoding="utf-8"))["meta"]["gate_passed"])
    check(
        "Démonette 直接派生通过质量门",
        report_gate
        and demonette_candidates >= 1_500
        and demonette_candidates == demonette_official
        and demonette_same_pos >= 100
        and demonette_invalid_same_pos == 0,
        f"gate={report_gate}, candidates={demonette_candidates:,}, sourced_official={demonette_official:,}, "
        f"same_pos={demonette_same_pos}, invalid_same_pos={demonette_invalid_same_pos}",
    )

    pair_regressions = {}
    for left, left_pos, right, right_pos in (
        ("affirmer", "VER", "affirmation", "NOM"),
        ("voir", "VER", "vision", "NOM"),
        ("poli", "ADJ", "impoli", "ADJ"),
    ):
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM official_edges e
            JOIN official_edge_sources s ON s.edge_id=e.id AND s.source_id='demonette_2'
            JOIN lexemes a ON a.id=e.a_id
            JOIN lexemes b ON b.id=e.b_id
            WHERE e.relation='fam'
              AND ((a.normalized=? AND a.pos=? AND b.normalized=? AND b.pos=?)
                OR (b.normalized=? AND b.pos=? AND a.normalized=? AND a.pos=?))
            """,
            (left, left_pos, right, right_pos, left, left_pos, right, right_pos),
        ).fetchone()[0]
        pair_regressions[f"{left}↔{right}"] = count
    check(
        "核心词族回归",
        all(count == 1 for count in pair_regressions.values()),
        ", ".join(f"{pair}={count}" for pair, count in pair_regressions.items()),
    )

    dbnary_candidates = conn.execute(
        "SELECT COUNT(*) FROM edge_candidates WHERE source_id='dbnary_fr' AND signal='semantic' AND status='sourced'"
    ).fetchone()[0]
    dbnary_official = conn.execute(
        "SELECT COUNT(*) FROM official_edge_sources WHERE source_id='dbnary_fr'"
    ).fetchone()[0]
    dbnary_semantic_layout = conn.execute(
        "SELECT COUNT(*) FROM layout_links WHERE signal='semantic'"
    ).fetchone()[0]
    cfdict_semantic_candidates = conn.execute(
        "SELECT COUNT(*) FROM edge_candidates WHERE source_id='cfdict_reverse_local' AND signal='semantic' AND status='candidate'"
    ).fetchone()[0]
    dbnary_contradictions = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_edges syn
        JOIN official_edge_sources ss ON ss.edge_id=syn.id AND ss.source_id='dbnary_fr'
        JOIN official_edges ant ON ant.a_id=syn.a_id AND ant.b_id=syn.b_id AND ant.relation='ant'
        JOIN official_edge_sources sa ON sa.edge_id=ant.id AND sa.source_id='dbnary_fr'
        WHERE syn.relation='syn'
        """
    ).fetchone()[0]
    entry_count, sense_count, sense_lexemes = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM lexical_entries),
          (SELECT COUNT(*) FROM lexeme_senses),
          (SELECT COUNT(DISTINCT lexeme_id) FROM lexeme_senses)
        """
    ).fetchone()
    dbnary_report = ROOT / "data" / "processed" / "dbnary-analysis.json"
    dbnary_gate = False
    if dbnary_report.exists():
        dbnary_gate = bool(json.loads(dbnary_report.read_text(encoding="utf-8"))["meta"]["gate_passed"])
    check(
        "DBnary 义项与语义关系通过质量门",
        dbnary_gate
        and entry_count >= 7_000
        and sense_count >= 30_000
        and sense_lexemes >= 7_000
        and dbnary_candidates >= 2_500
        and dbnary_candidates == dbnary_official == dbnary_semantic_layout
        and dbnary_contradictions == 0,
        f"gate={dbnary_gate}, entries={entry_count:,}, definitions={sense_count:,}, sense_lexemes={sense_lexemes:,}, "
        f"semantic={dbnary_candidates:,}/{dbnary_official:,}/{dbnary_semantic_layout:,}, contradictions={dbnary_contradictions}",
    )
    check(
        "中文释义相似只保留为候选",
        cfdict_semantic_candidates > 0 and dbnary_semantic_layout == dbnary_official,
        f"CFDICT candidates={cfdict_semantic_candidates:,}; visible semantic layout={dbnary_semantic_layout:,} (DBnary only)",
    )

    semantic_regressions = {}
    for left, right, relation, expected in (
        ("poli", "respectueux", "syn", 1),
        ("poli", "impoli", "ant", 1),
        ("seau", "nager", "syn", 0),
    ):
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM official_edges e
            JOIN official_edge_sources s ON s.edge_id=e.id AND s.source_id='dbnary_fr'
            JOIN lexemes a ON a.id=e.a_id
            JOIN lexemes b ON b.id=e.b_id
            WHERE e.relation=?
              AND ((a.normalized=? AND b.normalized=?) OR (a.normalized=? AND b.normalized=?))
            """,
            (relation, left, right, right, left),
        ).fetchone()[0]
        semantic_regressions[f"{left}↔{right} {relation}"] = (count, expected)
    poli_entries, poli_senses = conn.execute(
        """
        SELECT
          COUNT(DISTINCT le.id),
          COUNT(DISTINCT ls.id)
        FROM lexemes l
        JOIN lexical_entries le ON le.lexeme_id=l.id
        JOIN lexeme_senses ls ON ls.entry_id=le.id
        WHERE l.normalized='poli' AND l.pos='ADJ'
        """
    ).fetchone()
    check(
        "语义样例与多义词回归",
        all(count == expected for count, expected in semantic_regressions.values())
        and poli_entries >= 2
        and poli_senses >= 4,
        ", ".join(f"{pair}={count} (expected {expected})" for pair, (count, expected) in semantic_regressions.items())
        + f", poli entries/senses={poli_entries}/{poli_senses}",
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
    check(
        "学习表层已导出",
        "GRAPH_LEARNING" in runtime.read_text(encoding="utf-8")
        and "GRAPH_SEARCH_LEXEMES" in runtime.read_text(encoding="utf-8")
        and "sense.examples" in frontend_text,
        "词源、搭配、DBnary 义项例句与可检索学习词进入静态运行时",
    )
    cache_errors = runtime_cache_errors(runtime)
    check(
        "运行时图数据缓存按内容版本化",
        not cache_errors,
        "; ".join(cache_errors) or "index.html 与 Service Worker 均引用当前 graph-data.js SHA-256 版本",
    )

    alignment_path = ROOT / "data" / "processed" / "dbnary-alignment-review-queue.json"
    alignment_csv = ROOT / "data" / "reports" / "dbnary-alignment-review-queue.csv"
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    alignment_items = alignment["items"]
    with alignment_csv.open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    alignment_hash = alignment["meta"].get("aligned_dbnary_source_sha256")
    production_hash = json.loads(dbnary_report.read_text(encoding="utf-8"))["meta"]["source_sha256"]
    check(
        "DBnary 同快照审校队列可复现且禁止误导入",
        len(alignment_items) == len(csv_rows) == 203
        and alignment_hash == production_hash
        and all(item["alignment_decision"] != "pending_aligned_dbnary_snapshot" for item in alignment_items)
        and all(
            item["import_eligibility"] == "parser_fix_candidate"
            if item["alignment_decision"] == "dbnary_parser_capture_gap"
            else item["import_eligibility"] == "blocked"
            for item in alignment_items
        ),
        f"items/csv={len(alignment_items)}/{len(csv_rows)}, aligned_sha256={alignment_hash}, production_sha256={production_hash}",
    )

    p0_path = ROOT / "data" / "processed" / "wiktextract-p0-review.json"
    p0_csv = ROOT / "data" / "reports" / "wiktextract-p0-review.csv"
    p0 = json.loads(p0_path.read_text(encoding="utf-8"))
    with p0_csv.open(encoding="utf-8", newline="") as stream:
        p0_csv_rows = list(csv.DictReader(stream))
    p0_items = p0["items"]
    check(
        "Wiktextract P0 候选完整且人工批准门关闭",
        len(p0_items) == len(p0_csv_rows) == 59
        and all(p0["gates"].values())
        and all(item["candidate_entries"] for item in p0_items)
        and all(item["review"]["status"] != "accepted" or (item["review"].get("approved_sense_ids") and item["review"].get("reviewer") and item["review"].get("reviewed_at")) for item in p0_items),
        f"items/csv={len(p0_items)}/{len(p0_csv_rows)}, pending={sum(item['review']['status'] == 'pending' for item in p0_items)}",
    )

    passed = sum(result for _, result, _ in checks)
    lines = [
        "# wordcloud 构建验证",
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
