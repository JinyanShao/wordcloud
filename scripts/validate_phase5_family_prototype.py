#!/usr/bin/env python3
"""Structural validation for the Phase 5B family-learning prototype.

This script performs structural validation ONLY: it does not author, judge,
or generate semantic prose (explanation_zh, interaction prompts, alignment
labels). It proves that the 20 prototype families and their teaching
relations are anchored in real, committed, sourced derivational_morphology
family edges and real production exact-sense learner aids -- not that the
authored pedagogy is correct.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_graph import load_runtime, UnionFind  # noqa: E402

PROTOTYPE_PATH = ROOT / "data/phase5/family-learning-prototype.json"

BLOCKED_KEYS = {
    "rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM",
    "travers|NOM", "cesse|NOM",
}

ALLOWED_ALIGNMENTS = {"transparent", "shifted", "opaque"}

REQUIRED_RELATION_TEXT_FIELDS = ("explanation_zh", "interaction_prompt_zh", "interaction_answer_zh")


def fail(msg: str):
    raise SystemExit(f"Phase 5 prototype validation failed: {msg}")


def build_family_graph(runtime):
    nodes = {n[0]: n for n in runtime["nodes"]}
    fam_edges = [
        e for e in runtime["official_edges"]
        if e[2] == "fam" and e[9] == "sourced" and e[3] == "derivational_morphology"
    ]
    ids = sorted({v for e in fam_edges for v in e[:2]})
    uf = UnionFind(ids)
    for e in fam_edges:
        uf.union(e[0], e[1])
    groups: dict[int, list[int]] = {}
    for i in ids:
        groups.setdefault(uf.find(i), []).append(i)
    return nodes, fam_edges, uf, groups


def main() -> None:
    data = json.loads(PROTOTYPE_PATH.read_text(encoding="utf-8"))
    families = data["families"]

    # 1. exactly 20 prototype families
    if data.get("semantic_blockers") != []:
        fail(f"expected semantic_blockers == [], got {data.get('semantic_blockers')}")
    if len(families) != 20:
        fail(f"expected exactly 20 families, got {len(families)}")

    runtime = load_runtime()
    nodes, fam_edges, uf, groups = build_family_graph(runtime)
    fam_edge_set = {(e[0], e[1], e[4]) for e in fam_edges} | {(e[1], e[0], e[4]) for e in fam_edges}

    raw = (ROOT / "learner-sense-content.js").read_text(encoding="utf-8")
    import re
    match = re.search(r"const LEARNER_SENSE_CONTENT=(.*);\n$", raw, re.S)
    if not match:
        fail("could not parse learner-sense-content.js")
    learner_rows = json.loads(match.group(1))["records"]
    learner_by_id = {r["lexeme_id"]: r for r in learner_rows}
    if len(learner_rows) != 754:
        fail(f"existing learner runtime must remain 754 records, found {len(learner_rows)}")

    seen_family_ids = set()
    seen_anchor_ids = set()
    seen_relation_keys = set()

    for fam in families:
        fid = fam["family_id"]
        if fid in seen_family_ids:
            fail(f"duplicate family_id: {fid}")
        seen_family_ids.add(fid)

        anchor_id = fam["anchor_lexeme_id"]
        if anchor_id in seen_anchor_ids:
            fail(f"duplicate anchor lexeme id: {anchor_id}")
        seen_anchor_ids.add(anchor_id)

        if anchor_id not in nodes:
            fail(f"{fid}: anchor lexeme id {anchor_id} not found in production graph")
        node = nodes[anchor_id]
        if fam["anchor_lemma"] != node[1] or fam["anchor_pos"] != node[2] or fam["anchor_cefr"] != node[3]:
            fail(f"{fid}: anchor lemma/pos/cefr does not match production graph node")

        # 2. every family exists in the sourced derivational family graph
        if anchor_id not in uf.parent:
            fail(f"{fid}: anchor {fam['anchor_lemma']}|{fam['anchor_pos']} has no sourced derivational_morphology family")
        root = uf.find(anchor_id)
        real_members = set(groups[root])

        # source family size matches runtime
        if fam["total_sourced_family_size"] != len(real_members):
            fail(f"{fid}: total_sourced_family_size {fam['total_sourced_family_size']} != runtime family size {len(real_members)}")
        if set(fam["all_member_ids"]) != real_members:
            fail(f"{fid}: all_member_ids does not match the real sourced family membership")

        anchor_key = f"{fam['anchor_lemma']}|{fam['anchor_pos']}"
        if anchor_key in BLOCKED_KEYS:
            fail(f"{fid}: anchor is a blocked/dropped key: {anchor_key}")
        anchor_aid = learner_by_id.get(anchor_id)
        if anchor_aid is None:
            fail(f"{fid}: anchor has no production learner aid")
        exp = fam["anchor_learner_sense"]
        if (exp["entry_id"] != anchor_aid["entry_id"] or exp["sense_id"] != anchor_aid["sense_id"]
                or exp["entry_rank"] != anchor_aid["entry_rank"] or exp["sense_number"] != anchor_aid["sense_number"]
                or exp["gloss_zh_short"] != anchor_aid["gloss_zh_short"]):
            fail(f"{fid}: anchor_learner_sense does not exactly match production learner-sense-content.js")

        # selected_core_members subset of actual family, no falsely-attributed learner aid
        core_ids = set()
        for cm in fam["selected_core_members"]:
            cid = cm["lexeme_id"]
            if cid not in real_members:
                fail(f"{fid}: core member {cm['lemma']}|{cm['pos']} is not in the real sourced family")
            core_ids.add(cid)
            cm_key = f"{cm['lemma']}|{cm['pos']}"
            aid = learner_by_id.get(cid)
            if cm_key in BLOCKED_KEYS and cm.get("learner_sense") is not None:
                fail(f"{fid}: blocked key {cm_key} falsely carries a learner_sense")
            if cm.get("learner_sense") is not None:
                if aid is None:
                    fail(f"{fid}: core member {cm_key} claims a learner_sense that does not exist in production runtime")
                if cm["learner_sense"]["sense_id"] != aid["sense_id"]:
                    fail(f"{fid}: core member {cm_key} learner_sense drifted from production runtime")
            else:
                if aid is not None:
                    fail(f"{fid}: core member {cm_key} has a real learner aid but was not attributed one (data omission)")
        if not core_ids <= real_members:
            fail(f"{fid}: selected_core_members not a subset of the real family")

        relations = fam["teaching_relations"]
        if len(relations) == 0:
            fail(f"{fid}: family has zero teaching relations")

        for rel in relations:
            a, b, subtype = rel["edge_a_id"], rel["edge_b_id"], rel["construction_subtype"]
            # 3. every teaching edge is a real sourced edge; no invented edge
            if (a, b, subtype) not in fam_edge_set:
                fail(f"{fid}: teaching relation {rel['from_lemma']}->{rel['to_lemma']} ({subtype}) "
                     f"is not a real committed sourced derivational_morphology edge")
            if {a, b} != {rel["from_lexeme_id"], rel["to_lexeme_id"]}:
                fail(f"{fid}: teaching relation endpoints inconsistent with edge identity")
            if not ({a, b} <= real_members):
                fail(f"{fid}: teaching relation endpoints not both inside the anchor's family")

            rel_key = (fid, frozenset({a, b}), subtype)
            if rel_key in seen_relation_keys:
                fail(f"{fid}: duplicate teaching relation {rel['from_lemma']}->{rel['to_lemma']} ({subtype})")
            seen_relation_keys.add(rel_key)

            # 4. semantic_alignment only permitted enum
            if rel["semantic_alignment"] not in ALLOWED_ALIGNMENTS:
                fail(f"{fid}: invalid semantic_alignment {rel['semantic_alignment']!r}")

            # 5. all learner-facing authored fields nonempty
            for field in REQUIRED_RELATION_TEXT_FIELDS:
                if not rel.get(field) or not rel[field].strip():
                    fail(f"{fid}: relation {rel['from_lemma']}->{rel['to_lemma']} has empty {field}")
            if rel.get("authored_status") != "external_semantic_authored":
                fail(f"{fid}: relation authored_status must be external_semantic_authored")

            # every exact sense identity resolves against current production runtime;
            # no blocked/search-only record falsely treated as a learner aid
            for side, lemma, pos, sense in (
                ("from", rel["from_lemma"], rel["from_pos"], rel["from_learner_sense"]),
                ("to", rel["to_lemma"], rel["to_pos"], rel["to_learner_sense"]),
            ):
                key = f"{lemma}|{pos}"
                if key in BLOCKED_KEYS:
                    fail(f"{fid}: teaching relation uses blocked/dropped key {key} as a learner aid")
                lid = sense["runtime_lexeme_id"]
                aid = learner_by_id.get(lid)
                if aid is None:
                    fail(f"{fid}: relation {side}-side {key} has no production learner aid")
                if (sense["entry_id"] != aid["entry_id"] or sense["sense_id"] != aid["sense_id"]
                        or sense["entry_rank"] != aid["entry_rank"] or sense["sense_number"] != aid["sense_number"]):
                    fail(f"{fid}: relation {side}-side {key} exact sense drifted from production runtime")

    print(json.dumps({
        "ok": True,
        "family_count": len(families),
        "teaching_relations": sum(len(f["teaching_relations"]) for f in families),
        "learner_runtime_total": len(learner_rows),
    }))


if __name__ == "__main__":
    main()
