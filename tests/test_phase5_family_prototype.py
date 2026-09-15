import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_phase5_family_prototype as validator  # noqa: E402

PROTOTYPE_PATH = ROOT / "data/phase5/family-learning-prototype.json"


def _load():
    return json.loads(PROTOTYPE_PATH.read_text(encoding="utf-8"))


class Phase5PrototypeStructuralTests(unittest.TestCase):
    def test_validator_runs_clean(self):
        # Running main() should not raise SystemExit.
        try:
            validator.main()
        except SystemExit as exc:
            self.fail(f"validator raised: {exc}")

    def test_exactly_20_families_no_blockers(self):
        data = _load()
        self.assertEqual(len(data["families"]), 20)
        self.assertEqual(data["semantic_blockers"], [])

    def test_no_duplicate_family_or_relation(self):
        data = _load()
        family_ids = [f["family_id"] for f in data["families"]]
        self.assertEqual(len(family_ids), len(set(family_ids)))
        anchor_ids = [f["anchor_lexeme_id"] for f in data["families"]]
        self.assertEqual(len(anchor_ids), len(set(anchor_ids)))
        seen = set()
        for fam in data["families"]:
            for rel in fam["teaching_relations"]:
                key = (fam["family_id"], frozenset({rel["edge_a_id"], rel["edge_b_id"]}), rel["construction_subtype"])
                self.assertNotIn(key, seen)
                seen.add(key)

    def test_semantic_alignment_enum(self):
        data = _load()
        allowed = {"transparent", "shifted", "opaque"}
        for fam in data["families"]:
            for rel in fam["teaching_relations"]:
                self.assertIn(rel["semantic_alignment"], allowed)

    def test_blocked_keys_never_used_as_learner_aid(self):
        data = _load()
        blocked = {"rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM", "travers|NOM", "cesse|NOM"}
        for fam in data["families"]:
            self.assertNotIn(f"{fam['anchor_lemma']}|{fam['anchor_pos']}", blocked)
            for rel in fam["teaching_relations"]:
                self.assertNotIn(f"{rel['from_lemma']}|{rel['from_pos']}", blocked)
                self.assertNotIn(f"{rel['to_lemma']}|{rel['to_pos']}", blocked)

    def test_construction_and_alignment_coverage(self):
        data = _load()
        subtypes = {rel["construction_subtype"] for fam in data["families"] for rel in fam["teaching_relations"]}
        self.assertEqual(subtypes, {"suffixation", "prefixation", "conversion", "semantic_derivation"})
        alignments = {rel["semantic_alignment"] for fam in data["families"] for rel in fam["teaching_relations"]}
        self.assertEqual(alignments, {"transparent", "shifted", "opaque"})

    def test_size_buckets_present(self):
        data = _load()
        sizes = [f["total_sourced_family_size"] for f in data["families"]]
        self.assertTrue(any(s <= 4 for s in sizes), "no small (<=4) family present")
        self.assertTrue(any(s >= 5 for s in sizes), "no large (5+) family present")

    def test_cefr_and_pos_coverage(self):
        data = _load()
        cefrs = {f["anchor_cefr"] for f in data["families"]}
        self.assertTrue({"A1", "A2", "B1", "B2"} <= cefrs)
        pos_set = {f["anchor_pos"] for f in data["families"]}
        self.assertTrue({"VER", "NOM", "ADJ"} <= pos_set)

    def test_existing_754_learner_runtime_unchanged(self):
        raw = (ROOT / "learner-sense-content.js").read_text(encoding="utf-8")
        import re
        match = re.search(r"const LEARNER_SENSE_CONTENT=(.*);\n$", raw, re.S)
        rows = json.loads(match.group(1))["records"]
        self.assertEqual(len(rows), 754)
        cohorts = {}
        for r in rows:
            cohorts[r["cohort"]] = cohorts.get(r["cohort"], 0) + 1
        self.assertEqual(cohorts, {"phase2c": 99, "phase3": 499, "phase4": 156})


class Phase5NamedRiskCaseTests(unittest.TestCase):
    """Locks in the specific risk cases the spec called out by name."""

    @classmethod
    def setUpClass(cls):
        data = _load()
        cls.by_anchor = {f["anchor_lemma"]: f for f in data["families"]}

    def _relation(self, family, from_lemma, to_lemma):
        for rel in family["teaching_relations"]:
            if rel["from_lemma"] == from_lemma and rel["to_lemma"] == to_lemma:
                return rel
        self.fail(f"relation {from_lemma}->{to_lemma} not found")

    def test_emploi_employer_is_not_falsely_transparent(self):
        fam = self.by_anchor["emploi"]
        rel = self._relation(fam, "emploi", "employer")
        self.assertEqual(rel["semantic_alignment"], "opaque")
        self.assertIn("使用", rel["to_learner_sense"]["gloss_zh_short"])

    def test_faire_fait_is_not_falsely_transparent(self):
        fam = self.by_anchor["faire"]
        rel = self._relation(fam, "faire", "fait")
        self.assertNotEqual(rel["semantic_alignment"], "transparent")

    def test_public_publicite_is_not_falsely_transparent(self):
        fam = self.by_anchor["public"]
        rel = self._relation(fam, "public", "publicité")
        self.assertNotEqual(rel["semantic_alignment"], "transparent")

    def test_tenir_retenir_is_not_falsely_transparent(self):
        fam = self.by_anchor["tenir"]
        rel = self._relation(fam, "tenir", "retenir")
        self.assertNotEqual(rel["semantic_alignment"], "transparent")

    def test_etrange_etranger_is_opaque(self):
        fam = self.by_anchor["étrange"]
        rel = self._relation(fam, "étrange", "étranger")
        self.assertEqual(rel["semantic_alignment"], "opaque")

    def test_possible_family_is_transparent(self):
        fam = self.by_anchor["possible"]
        for rel in fam["teaching_relations"]:
            self.assertEqual(rel["semantic_alignment"], "transparent")

    def test_porter_family_flags_emporter_prefix_trap(self):
        fam = self.by_anchor["porter"]
        rel = self._relation(fam, "porter", "emporter")
        self.assertNotEqual(rel["semantic_alignment"], "transparent")


if __name__ == "__main__":
    unittest.main()
