#!/usr/bin/env python3
"""Regression tests for the 100 core-family product data."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
CORE = ROOT / "data" / "processed" / "core-families-100.json"
APP = ROOT / "app.js"


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

    def test_dangerous_pairs_are_not_default_modern_derivation(self):
        dangerous = {tuple(sorted(pair)) for pair in [
            ("faire", "facture"),
            ("faire", "faction"),
            ("dire", "interdire"),
        ]}
        for edge in self.all_edges():
            pair = tuple(sorted((edge["a"]["lemma"], edge["b"]["lemma"])))
            if pair in dangerous:
                self.assertNotEqual(edge["relation"], "derivation", edge)
                self.assertEqual(edge["familyScope"], "extended", edge)

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
