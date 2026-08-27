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
CEFR_WEIGHT = {"A1": 6, "A2": 5, "B1": 4, "B2": 3, "C1": 2, "C2": 1}
BAD_GLOSSES = {"弊", "出厂价；单据"}


def edge_status(row: sqlite3.Row) -> str:
    sources = set(str(row["source_ids"] or "").split(","))
    return "editorial" if row["review_status"] == "reviewed" and "wordcloud_editorial" in sources else "sourced"


def quality_member(row: dict[str, object]) -> bool:
    gloss = str(row.get("gloss_zh") or "").strip()
    if not gloss or gloss in BAD_GLOSSES or len(gloss) < 2:
        return False
    if row.get("pos") not in {"NOM", "VER", "ADJ", "ADV"}:
        return False
    return bool(row.get("has_cfdict") or str(row.get("decision_reason") or "").startswith(("editorial_", "manual_audit_override")))


def is_productive_simple_edge(row: sqlite3.Row) -> bool:
    records = row["source_records"] or ""
    if '"complexity": "simple"' not in records:
        return False
    scheme = records.replace(" ", "")
    return (
        row["subtype"] in {"prefixation", "suffixation"}
        or "scheme_2\":\"reX" in scheme
        or "scheme_2\":\"préX" in scheme
        or "scheme_2\":\"dé1X" in scheme
        or "scheme_2\":\"Xeur" in scheme
        or "scheme_2\":\"Xion" in scheme
    )


def trustworthy_family_edges(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT e.*,
               a.lemma AS a_lemma,a.pos AS a_pos,a.gloss_zh AS a_gloss,
               b.lemma AS b_lemma,b.pos AS b_pos,b.gloss_zh AS b_gloss,
               group_concat(s.source_id) AS source_ids,
               group_concat(src.version) AS source_versions,
               group_concat(s.source_record, ' || ') AS source_records
        FROM official_edges e
        JOIN lexemes a ON a.id=e.a_id
        JOIN lexemes b ON b.id=e.b_id
        JOIN official_edge_sources s ON s.edge_id=e.id
        JOIN sources src ON src.id=s.source_id
        WHERE e.relation IN ('derivation','conversion_or_lexicalization','etymological_family')
        GROUP BY e.id
        ORDER BY e.a_id,e.b_id,e.relation
        """
    ).fetchall()
    accepted = []
    for row in rows:
        sources = set(str(row["source_ids"] or "").split(","))
        records = row["source_records"] or ""
        if row["review_status"] == "reviewed":
            # Already passed has_real_review_evidence in build_graph.py (real
            # explanation, >=2 examples, a named reviewer and review date) --
            # a strictly higher bar than any mechanical check below, so trust
            # it unconditionally rather than re-deriving a weaker opinion.
            accepted.append(row)
            continue
        # Below applies only to 'sourced' (never human-reviewed) rows. This is
        # a mechanical plausibility gate for the broader/"extended" candidate
        # pool -- it does not, and must not, decide what is fit to show a
        # learner as a default/highlighted relation. See main() for that split,
        # which keys strictly on review_status.
        if row["relation"] == "derivation":
            if "demonette_2" not in sources or '"complexity": "simple"' not in records:
                continue
            if row["a_pos"] == row["b_pos"] and not is_productive_simple_edge(row):
                continue
        elif row["relation"] == "conversion_or_lexicalization":
            if row["a_pos"] == row["b_pos"]:
                continue
            if "demonette_2" not in sources:
                continue
        elif row["relation"] == "etymological_family":
            if not ("demonette_2" in sources and '"complexity": "motiv-sem"' in records):
                continue
        accepted.append(row)
    return accepted


def family_components(conn: sqlite3.Connection, edges: list[sqlite3.Row]) -> list[set[int]]:
    adj: dict[int, set[int]] = defaultdict(set)
    for row in edges:
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


def default_subclusters(component_edges: list[sqlite3.Row], quality_eligible: dict[int, bool]) -> list[set[int]]:
    """Connected components reachable using *only* reviewed (editorial) edges
    between quality-eligible members.

    A broader word family (grouped below via the mechanically-vetted sourced+
    reviewed pool) can contain more than one of these -- e.g. voir/revoir/
    vision is one reviewed cluster and prévoir/prévision is another, joined
    to the first only through a sourced Démonette prefix edge, never a
    reviewed one. Bundling both under a single "voir" family would either
    silently hide prévoir/prévision's real reviewed content (if only the
    cluster reachable from the chosen core were kept) or mislabel members as
    "default" that share no actual default-scope path to each other. Each
    reviewed cluster gets its own family entry instead.
    """
    adjacency: dict[int, set[int]] = defaultdict(set)
    default_ids: set[int] = set()
    for edge in component_edges:
        if edge_status(edge) != "editorial":
            continue
        a_id, b_id = edge["a_id"], edge["b_id"]
        if not (quality_eligible.get(a_id) and quality_eligible.get(b_id)):
            continue
        adjacency[a_id].add(b_id)
        adjacency[b_id].add(a_id)
        default_ids.add(a_id)
        default_ids.add(b_id)
    seen: set[int] = set()
    clusters: list[set[int]] = []
    for node_id in sorted(default_ids):
        if node_id in seen:
            continue
        cluster: set[int] = set()
        queue = deque([node_id])
        seen.add(node_id)
        while queue:
            current = queue.popleft()
            cluster.add(current)
            for other in adjacency[current]:
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
        if len(cluster) >= 2:
            clusters.append(cluster)
    return clusters


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    lexemes = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM lexemes")}
    candidate_count = conn.execute("SELECT COUNT(*) FROM edge_candidates WHERE status='candidate'").fetchone()[0]
    trusted_edges = trustworthy_family_edges(conn)
    rows: list[dict[str, object]] = []
    for component in family_components(conn, trusted_edges):
        component_edges = [edge for edge in trusted_edges if edge["a_id"] in component and edge["b_id"] in component]
        members = [lexemes[item] for item in component if item in lexemes]
        # Word-level quality (real gloss, allowed POS, eligible/auxiliary
        # status) is necessary but not sufficient for a member to be
        # highlighted by default. It must ALSO be reachable, using only real
        # reviewed (editorial) relations, from every other default member of
        # its own family -- `review_status` (has_real_review_evidence in
        # build_graph.py) is the one gate this whole product already trusts
        # for "fit to teach", and it must be the same gate here as it is for
        # GRAPH_OFFICIAL_EDGES. A "sourced" Démonette/DBnary relation is real
        # data with a real source, but a source is not the same claim as a
        # reviewed teaching explanation, so it can group a family (via the
        # broader trustworthy_family_edges pool, below) without ever making
        # that family's default, learner-facing view.
        quality_eligible = {
            m["id"]: m["cefr_level"] in CEFR_WEIGHT and m["status"] in {"eligible", "auxiliary"} and quality_member(m)
            for m in members
        }
        clusters = default_subclusters(component_edges, quality_eligible)
        if not clusters:
            # No pair of members here is connected by a real reviewed
            # relation -- there is nothing to responsibly highlight as a
            # default word family, even if Démonette independently groups
            # these words. Skip rather than pad the page with sourced-only
            # content dressed up as a teachable family.
            continue
        for default_ids in clusters:
            default = [m for m in members if m["id"] in default_ids]
            extended = [m for m in members if m["id"] not in default_ids]
            pos = Counter(m["pos"] for m in default)
            rel = Counter()
            editorial = sourced = 0
            for edge in component_edges:
                rel[edge["relation"]] += 1
                if edge_status(edge) == "editorial":
                    editorial += 1
                else:
                    sourced += 1
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
                + editorial * 1.5
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
            if editorial:
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
                "edges": [
                    {
                        "a": {"id": edge["a_id"], "lemma": edge["a_lemma"], "pos": edge["a_pos"], "sense": edge["key_sense_a"] or ""},
                        "b": {"id": edge["b_id"], "lemma": edge["b_lemma"], "pos": edge["b_pos"], "sense": edge["key_sense_b"] or ""},
                        "relation": edge["relation"],
                        "label": edge["label"] or "",
                        "explanation": edge["explanation"] or "",
                        "sources": [
                            {"id": source_id, "version": version}
                            for source_id, version in zip(str(edge["source_ids"] or "").split(","), str(edge["source_versions"] or "").split(","))
                            if source_id
                        ],
                        "status": edge_status(edge),
                        "productiveRule": bool(edge["productive_rule"]) or is_productive_simple_edge(edge),
                        # A reviewed relation (status "editorial") is necessary
                        # for an edge to be "default", but not sufficient on its
                        # own: both endpoints must also actually be default
                        # members of *this* cluster (real reviewed evidence
                        # binds the relation, but a word with no real gloss to
                        # show still should not light up as a confirmed family
                        # member). Keying off `default_ids` -- the same set
                        # defaultMembers was built from -- keeps the two fields
                        # structurally unable to drift apart.
                        "familyScope": "default" if edge["a_id"] in default_ids and edge["b_id"] in default_ids else "extended",
                        "hasZhExplanation": bool(str(edge["label"] or "").strip() or str(edge["explanation"] or "").strip()),
                        "hasExamples": bool(json.loads(edge["examples_json"] or "[]")),
                    }
                    for edge in component_edges
                ],
                "relationCounts": dict(sorted(rel.items())),
                "editorialRelations": editorial,
                "sourcedRelations": sourced,
            })
    selected = sorted(rows, key=lambda item: (-item["score"], item["core"]["lemma"], item["core"]["pos"]))[:100]
    selected_status_counts = Counter(
        edge["status"]
        for family in selected
        for edge in family["edges"]
    )
    selected_status_counts["candidate"] = candidate_count
    payload = {
        "meta": {
            "version": "core-families-100-v1",
            "selection_count": len(selected),
            "independent_lexeme_count": len({m["id"] for f in selected for m in f["defaultMembers"] + f["extendedMembers"]}),
            "default_member_count": sum(len(f["defaultMembers"]) for f in selected),
            "extended_member_count": sum(len(f["extendedMembers"]) for f in selected),
            "relation_status_counts": dict(sorted(selected_status_counts.items())),
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
