#!/usr/bin/env python3
"""Regression tests for the public relation quality gate.

The content-trust reset (see build_graph.py's has_real_review_evidence and
export_runtime.py's dedupe_public_relations) means only relations with real
human review evidence -- explanation, >=2 examples, reviewer, reviewed_at --
may reach the public GRAPH_OFFICIAL_EDGES payload. Everything else (auto-
sourced DBnary/Démonette edges, the un-reviewed legacy prototype seed) must
stay database-only. These tests exercise the gate and the export-time dedup
directly, plus check the specific pairs a real user flagged as wrong before
the reset (faire-égarer, dire-interdire, voir-voyant, etc.) against the
built database, so the fix stays proven rather than just plausible.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_graph import has_real_review_evidence  # noqa: E402
from export_runtime import dedupe_public_relations  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"

# Word pairs a real user confirmed were wrong/misleading before the reset.
# None of these may ever appear as a public (review_status='reviewed')
# relation again, regardless of which lemma/pos or column order they land in.
KNOWN_BAD_PAIRS = [
    ("faire", "égarer"),
    ("faire", "évacuer"),
    ("faire", "faction"),
    ("faire", "facture"),
    ("dire", "interdire"),
    ("voir", "distinguer"),
    ("voir", "remarquer"),
    ("voir", "voyant"),
]


class HasRealReviewEvidence(unittest.TestCase):
    def base_item(self, **overrides):
        item = {
            "explanation": "Voir marque la perception visuelle.",
            "examples": ["Je vois une lumière.", "Je regarde le tableau."],
            "reviewer": "wordcloud editorial",
            "reviewed_at": "2026-08-04",
        }
        item.update(overrides)
        return item

    def test_complete_editorial_item_is_reviewed(self):
        self.assertTrue(has_real_review_evidence(self.base_item()))

    def test_missing_explanation_is_not_reviewed(self):
        self.assertFalse(has_real_review_evidence(self.base_item(explanation=None)))
        self.assertFalse(has_real_review_evidence(self.base_item(explanation="")))
        self.assertFalse(has_real_review_evidence(self.base_item(explanation="   ")))

    def test_placeholder_explanation_is_not_reviewed(self):
        self.assertFalse(has_real_review_evidence(self.base_item(
            explanation="Prototype editorial seed; requires production re-review.",
        )))

    def test_fewer_than_two_examples_is_not_reviewed(self):
        self.assertFalse(has_real_review_evidence(self.base_item(examples=[])))
        self.assertFalse(has_real_review_evidence(self.base_item(examples=["Only one."])))

    def test_missing_reviewer_is_not_reviewed(self):
        self.assertFalse(has_real_review_evidence(self.base_item(reviewer=None)))
        self.assertFalse(has_real_review_evidence(self.base_item(reviewer="")))

    def test_missing_reviewed_at_is_not_reviewed(self):
        self.assertFalse(has_real_review_evidence(self.base_item(reviewed_at=None)))
        self.assertFalse(has_real_review_evidence(self.base_item(reviewed_at="")))

    def test_prototype_seed_style_item_is_not_reviewed(self):
        # This is exactly the shape of an item from data.js's EDGES array:
        # only a short label, no explanation/examples/reviewer/reviewedAt.
        self.assertFalse(has_real_review_evidence({
            "explanation": None, "examples": [], "reviewer": None, "reviewed_at": None,
        }))


class DedupePublicRelations(unittest.TestCase):
    def row(self, a, b, relation, **overrides):
        base = {
            "a_id": a, "b_id": b, "relation": relation, "dimension": "d",
            "subtype": None, "direction": None, "label": "label",
            "explanation": "explanation", "examples_json": "[]",
            "confidence": 0.9, "review_status": "reviewed",
        }
        base.update(overrides)
        return base

    def test_syn_dropped_when_compare_exists_for_same_pair(self):
        rows = [self.row(1, 2, "synonym"), self.row(1, 2, "compare")]
        kept = dedupe_public_relations(rows)
        self.assertEqual([row["relation"] for row in kept], ["compare"])

    def test_syn_kept_when_no_compare_for_that_pair(self):
        rows = [self.row(1, 2, "synonym")]
        kept = dedupe_public_relations(rows)
        self.assertEqual([row["relation"] for row in kept], ["synonym"])

    def test_unrelated_pairs_are_independent(self):
        rows = [self.row(1, 2, "synonym"), self.row(3, 4, "compare")]
        kept = dedupe_public_relations(rows)
        self.assertEqual(len(kept), 2)

    def test_non_syn_relations_for_same_pair_are_not_deduped(self):
        rows = [self.row(1, 2, "derivation"), self.row(1, 2, "antonym")]
        kept = dedupe_public_relations(rows)
        self.assertEqual({row["relation"] for row in kept}, {"derivation", "antonym"})

    def test_output_is_sorted_and_deterministic(self):
        rows = [self.row(3, 4, "antonym"), self.row(1, 2, "compare"), self.row(1, 2, "synonym")]
        kept = dedupe_public_relations(rows)
        self.assertEqual(
            [(row["a_id"], row["b_id"], row["relation"]) for row in kept],
            [(1, 2, "compare"), (3, 4, "antonym")],
        )


@unittest.skipUnless(DB_PATH.exists(), "requires a built database (run pnpm data:build first)")
class BuiltDatabaseInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(DB_PATH)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def public_rows(self):
        return self.conn.execute(
            """
            SELECT oe.*
            FROM official_edges oe WHERE oe.review_status='reviewed'
            """
        ).fetchall()

    def test_every_public_relation_has_full_review_evidence(self):
        import json
        for row in self.public_rows():
            self.assertTrue((row["explanation"] or "").strip(), row["explanation"])
            examples = json.loads(row["examples_json"])
            self.assertGreaterEqual(len(examples), 2, (row["a_id"], row["b_id"]))
            self.assertTrue((row["reviewed_at"] or "").strip(), (row["a_id"], row["b_id"]))

    def test_no_duplicate_or_conflicting_relation_per_pair(self):
        seen = {}
        for row in self.public_rows():
            key = (row["a_id"], row["b_id"])
            self.assertNotIn(
                key, seen,
                f"pair {key} has both {seen.get(key)} and {row['relation']} as public relations",
            )
            seen[key] = row["relation"]

    def test_syn_relations_bind_a_sense_dimension(self):
        for row in self.public_rows():
            if row["relation"] == "synonym":
                self.assertTrue((row["dimension"] or "").strip(), (row["a_id"], row["b_id"]))

    def lexeme(self, lemma, pos):
        return self.conn.execute(
            "SELECT id,lemma,pos,gloss_zh FROM lexemes WHERE normalized=? AND pos=?",
            (lemma, pos),
        ).fetchone()

    def public_relation(self, left, right):
        a, b = sorted((left, right))
        return self.conn.execute(
            "SELECT * FROM official_edges WHERE a_id=? AND b_id=? AND review_status='reviewed'",
            (a, b),
        ).fetchone()

    def test_faire_fait_adjective_is_not_nominal_or_derivational(self):
        faire = self.lexeme("faire", "VER")
        fait_adj = self.lexeme("fait", "ADJ")
        fait_nom = self.lexeme("fait", "NOM")
        self.assertEqual(fait_adj["gloss_zh"], "做好的；既成的")
        self.assertNotEqual(fait_adj["gloss_zh"], fait_nom["gloss_zh"])
        edge = self.public_relation(faire["id"], fait_adj["id"])
        self.assertEqual(edge["relation"], "conversion_or_lexicalization")
        self.assertNotIn("fait accompli", edge["examples_json"])

    def test_dire_dit_adjective_is_conversion_not_inflection_node_claim(self):
        dire = self.lexeme("dire", "VER")
        dit = self.lexeme("dit", "ADJ")
        self.assertEqual(dit["gloss_zh"], "所说的；上述的")
        edge = self.public_relation(dire["id"], dit["id"])
        self.assertEqual(edge["relation"], "conversion_or_lexicalization")
        self.assertEqual(edge["example_status"], "edited_example")

    def test_voir_vision_is_etymological_family_not_derivation(self):
        voir = self.lexeme("voir", "VER")
        vision = self.lexeme("vision", "NOM")
        edge = self.public_relation(voir["id"], vision["id"])
        self.assertEqual(edge["relation"], "etymological_family")
        self.assertEqual(edge["productive_rule"], 0)
        self.assertIn("不是现代法语里把 voir 加 -ion", edge["label"])

    def test_public_relations_use_formal_vocabulary_and_sources(self):
        allowed = {"derivation", "conversion_or_lexicalization", "etymological_family", "synonym", "antonym", "compare", "trap"}
        for row in self.public_rows():
            self.assertIn(row["relation"], allowed, (row["a_id"], row["b_id"], row["relation"]))
            sources = self.conn.execute("SELECT COUNT(*) FROM official_edge_sources WHERE edge_id=(SELECT id FROM official_edges WHERE a_id=? AND b_id=? AND relation=? LIMIT 1)", (row["a_id"], row["b_id"], row["relation"])).fetchone()[0]
            self.assertGreater(sources, 0)

    def test_reviewed_relations_are_always_backed_by_editorial_review(self):
        # An auto-source (Démonette/DBnary) may additionally corroborate an
        # already-reviewed editorial relation -- that's fine, multiple
        # sources agreeing is a strength. What must never happen is a
        # relation reaching review_status='reviewed' on auto-source
        # attribution alone, with no wordcloud_editorial review behind it.
        reviewed_ids = [row["id"] for row in self.conn.execute(
            "SELECT id FROM official_edges WHERE review_status='reviewed'"
        )]
        for edge_id in reviewed_ids:
            sources = {
                row["source_id"] for row in self.conn.execute(
                    "SELECT source_id FROM official_edge_sources WHERE edge_id=?", (edge_id,)
                )
            }
            self.assertIn("wordcloud_editorial", sources, edge_id)

    def test_sourced_relations_never_have_full_review_evidence(self):
        # The inverse sanity check: every row left as 'sourced' must be
        # explainable as lacking real review evidence -- review_status is a
        # function of evidence, not of which table inserted the row first.
        import json
        rows = self.conn.execute(
            "SELECT a_id,b_id,explanation,examples_json,reviewed_at "
            "FROM official_edges WHERE review_status='sourced'"
        ).fetchall()
        for row in rows:
            examples = json.loads(row["examples_json"] or "[]")
            has_full_evidence = (
                bool((row["explanation"] or "").strip())
                and len(examples) >= 2
                and bool((row["reviewed_at"] or "").strip())
            )
            self.assertFalse(
                has_full_evidence,
                f"({row['a_id']},{row['b_id']}) has full review evidence but wasn't promoted to reviewed",
            )

    def test_known_bad_pairs_are_absent_from_public_relations(self):
        public = {(row["a_id"], row["b_id"]) for row in self.public_rows()}
        lemma_ids: dict[str, list[int]] = {}
        for row in self.conn.execute("SELECT id, lemma FROM lexemes"):
            lemma_ids.setdefault(row["lemma"], []).append(row["id"])
        for word_a, word_b in KNOWN_BAD_PAIRS:
            for id_a in lemma_ids.get(word_a, []):
                for id_b in lemma_ids.get(word_b, []):
                    pair = (id_a, id_b) if id_a < id_b else (id_b, id_a)
                    self.assertNotIn(pair, public, f"{word_a}-{word_b} must not be a public relation")


if __name__ == "__main__":
    unittest.main()
