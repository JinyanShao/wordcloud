#!/usr/bin/env python3
"""Regression tests for the 100 core-family product data.

Core families read directly from official_edges (not just the reviewed-only
GRAPH_OFFICIAL_EDGES export), so they must not become a second, weaker path
to the map's default learner-facing view. build_core_families.py's own rule
(see its main()) is: an edge/member may be "default" (highlighted, connected
by default) only if it is review_status='reviewed' -- the exact same bar
has_real_review_evidence already holds GRAPH_OFFICIAL_EDGES to. A 'sourced'
relation is real data with a real citation, but a source is not the same
claim as a reviewed teaching explanation. These tests check that rule holds
structurally (not just "these specific pairs happen to be excluded today"),
and reuse test_relation_quality's KNOWN_BAD_PAIRS as a shared, single list
so both the reviewed-only export and the core-family payload are checked
against the same regression list rather than two lists that can drift apart.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
CORE = ROOT / "data" / "processed" / "core-families-100.json"
APP = ROOT / "app.js"

sys.path.insert(0, str(ROOT / "scripts"))
from test_relation_quality import KNOWN_BAD_PAIRS  # noqa: E402


class CoreFamilies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CORE.read_text(encoding="utf-8"))
        cls.conn = sqlite3.connect(DB)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def all_edges(self):
        return [edge for family in self.payload["families"] for edge in family["edges"]]

    def all_default_members(self):
        return [member for family in self.payload["families"] for member in family["defaultMembers"]]

    def test_frontend_reads_core_families_without_synthesizing_edges(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("GRAPH_CORE_FAMILIES", app)
        self.assertIn("familyFor(node.id)", app)
        self.assertNotIn('label: "同一词族"', app)
        self.assertNotIn('review: "reviewed"', app)

    def test_frontend_family_focus_filters_to_default_scope_only(self):
        # familyFor() is what decides which family members/edges actually
        # light up and connect on the map for a searched word. It must only
        # ever do that for familyScope 'default' edges -- concatenating
        # defaultMembers and extendedMembers unconditionally into what gets
        # highlighted (the pre-fix shape of this function) is exactly the bug
        # this milestone closes, so guard against it coming back by isolating
        # familyFor's own body rather than string-matching the whole file
        # (familyByMember's membership index legitimately merges both lists
        # for a different purpose -- "which family is this word in" is not
        # "should this word's family be highlighted").
        app = APP.read_text(encoding="utf-8")
        start = app.index("function familyFor(id) {")
        end = app.index("\n  function ", start + 1)
        body = app[start:end]
        self.assertIn('(rawEdge.familyScope || "default") === "default"', body)
        self.assertNotIn(
            "family.defaultMembers", body,
            "familyFor must reach members only by walking default-scope edges, "
            "not by reading defaultMembers/extendedMembers directly",
        )

    def test_each_family_exports_real_edges(self):
        for family in self.payload["families"]:
            self.assertGreater(len(family["edges"]), 0, family["core"])
            ids = {str(member["id"]) for member in family["defaultMembers"] + family["extendedMembers"]}
            for edge in family["edges"]:
                self.assertIn(str(edge["a"]["id"]), ids)
                self.assertIn(str(edge["b"]["id"]), ids)
                self.assertIn(edge["relation"], {"derivation", "conversion_or_lexicalization", "etymological_family"})
                self.assertIn(edge["status"], {"editorial", "sourced"})
                self.assertTrue(edge["sources"], edge)
                self.assertIn("productiveRule", edge)
                self.assertIn(edge["familyScope"], {"default", "extended"})

    def test_semantic_relations_never_connect_families(self):
        forbidden = {"synonym", "antonym", "compare", "trap"}
        self.assertFalse(any(edge["relation"] in forbidden for edge in self.all_edges()))

    def test_known_bad_pairs_are_never_default_scope(self):
        # Same regression list test_relation_quality.py holds GRAPH_OFFICIAL_EDGES
        # to, checked here against the *other* runtime path a learner can see
        # a relation through. A pair on this list re-entering as a default,
        # highlighted family edge -- via Démonette re-approval, a future
        # heuristic change, or anything else -- must fail here even if
        # test_relation_quality.py's own check (which only looks at
        # review_status='reviewed' rows) would not catch it.
        dangerous = {tuple(sorted(pair)) for pair in KNOWN_BAD_PAIRS}
        for edge in self.all_edges():
            pair = tuple(sorted((edge["a"]["lemma"], edge["b"]["lemma"])))
            if pair in dangerous:
                self.assertEqual(edge["familyScope"], "extended", edge)

    def test_default_family_scope_implies_reviewed_status(self):
        # familyScope 'default' must never be looser than review status
        # ('editorial' here already means review_status='reviewed', see
        # edge_status in build_core_families.py) -- never a per-pair
        # exception list, and never looser than the bar GRAPH_OFFICIAL_EDGES
        # already holds. (The converse does not hold: a reviewed edge whose
        # word itself has no real gloss to show still ends up 'extended' --
        # see test_default_members_are_reachable_via_default_edges, which
        # checks that stronger, member-quality-aware invariant.)
        for edge in self.all_edges():
            if edge["familyScope"] == "default":
                self.assertEqual(edge["status"], "editorial", edge)

    def test_default_members_are_reachable_via_default_edges(self):
        # Every defaultMember must be able to trace a path back to the family
        # using only 'default' edges -- otherwise the frontend would light up
        # a node with nothing but a sourced (unreviewed) edge actually
        # connecting it, which is the exact bug this milestone closes.
        for family in self.payload["families"]:
            default_ids = {member["id"] for member in family["defaultMembers"]}
            self.assertGreaterEqual(len(default_ids), 2, family["core"])
            default_edges = [edge for edge in family["edges"] if edge["familyScope"] == "default"]
            self.assertTrue(default_edges, family["core"])
            adjacency: dict[int, set[int]] = {}
            for edge in default_edges:
                a, b = edge["a"]["id"], edge["b"]["id"]
                adjacency.setdefault(a, set()).add(b)
                adjacency.setdefault(b, set()).add(a)
            start = next(iter(default_ids))
            reachable = {start}
            queue = [start]
            while queue:
                current = queue.pop()
                for other in adjacency.get(current, ()):
                    if other not in reachable:
                        reachable.add(other)
                        queue.append(other)
            self.assertEqual(reachable, default_ids, family["core"])

    def test_default_member_gloss_quality(self):
        bad = {"", "弊", "出厂价；单据"}
        for member in self.all_default_members():
            self.assertNotIn(member["gloss"].strip(), bad, member)
            self.assertIn(member["pos"], {"NOM", "VER", "ADJ", "ADV"}, member)

    def test_known_pos_specific_glosses(self):
        rows = {
            (row["lemma"], row["pos"]): row["gloss_zh"]
            for row in self.conn.execute(
                "SELECT lemma,pos,gloss_zh FROM lexemes WHERE normalized IN ('faire','fait','dire','dit','défaite','facture')"
            )
        }
        self.assertEqual(rows[("fait", "ADJ")], "做好的；既成的")
        self.assertEqual(rows[("fait", "NOM")], "事实；功绩")
        self.assertEqual(rows[("dit", "ADJ")], "所说的；上述的")
        self.assertEqual(rows[("défaite", "NOM")], "失败；战败")
        self.assertEqual(rows[("facture", "NOM")], "发票；账单")


if __name__ == "__main__":
    unittest.main()
