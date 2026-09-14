import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_graph import load_runtime  # noqa: E402

SOURCE = ROOT / "data/phase4/learner-content-156-authored.json"

BLOCKED_KEYS = {"rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM"}


def _load():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    return data, {r["stable_lexeme_key"]: r for r in data["records"]}


class Phase4FinalContentTests(unittest.TestCase):
    def test_exactly_156_records_no_blockers(self):
        data, by = _load()
        self.assertEqual(len(data["records"]), 156)
        self.assertEqual(len(by), 156)
        self.assertEqual(data["semantic_blockers"], [])

    def test_unique_identities(self):
        _data, by = _load()
        rows = list(by.values())
        self.assertEqual(len({r["stable_lexeme_key"] for r in rows}), 156)
        self.assertEqual(len({r["runtime_lexeme_id"] for r in rows}), 156)

    def test_blocked_and_dropped_keys_absent(self):
        _data, by = _load()
        for key in BLOCKED_KEYS:
            self.assertNotIn(key, by)

    def test_status_and_cohort(self):
        _data, by = _load()
        for r in by.values():
            self.assertEqual(r["content_status"], "external_semantic_authored")
            self.assertEqual(r["cohort"], "phase4")

    def test_required_fields_present_and_non_empty(self):
        _data, by = _load()
        required = {
            "stable_lexeme_key", "runtime_lexeme_id", "lemma", "pos", "cefr",
            "entry_id", "sense_id", "entry_rank", "sense_number",
            "gloss_zh_short", "example_fr", "example_zh",
        }
        for r in by.values():
            self.assertTrue(required <= set(r), r["stable_lexeme_key"])
            for field in required:
                self.assertTrue(r[field] not in (None, ""), (r["stable_lexeme_key"], field))
        # usage_note_zh is allowed to be null
        self.assertTrue(any(r["usage_note_zh"] is None for r in by.values()))

    def test_no_forbidden_repeated_characters(self):
        _data, by = _load()
        for r in by.values():
            blob = (r["gloss_zh_short"] or "") + (r["usage_note_zh"] or "") + (r["example_zh"] or "")
            self.assertNotIn("的的", blob, r["stable_lexeme_key"])
            self.assertNotIn("地地", blob, r["stable_lexeme_key"])

    def test_exact_graph_senses_binding(self):
        _data, by = _load()
        senses = load_runtime()["senses"]
        for r in by.values():
            key = r["stable_lexeme_key"]
            lid = str(r["runtime_lexeme_id"])
            groups = senses.get(lid)
            self.assertTrue(groups, f"{key}: lexeme {lid} missing from GRAPH_SENSES")
            group = next((g for g in groups if g["entry"] == r["entry_rank"]), None)
            self.assertIsNotNone(group, f"{key}: no entry group == {r['entry_rank']}")
            sense = next((s for s in group["senses"] if s["number"] == r["sense_number"]), None)
            self.assertIsNotNone(sense, f"{key}: no sense numbered {r['sense_number']}")


class Phase4CorrectionRegressionTests(unittest.TestCase):
    """Locks in the 8 corrections made by the independent review pass."""

    @classmethod
    def setUpClass(cls):
        _data, cls.by = _load()

    def test_reprendre(self):
        r = self.by["reprendre|VER"]
        self.assertEqual(r["sense_id"], "__ws_1_reprendre__verb__1")
        self.assertNotIn("重新开始", r["gloss_zh_short"])
        self.assertNotIn("Les cours reprennent", r["example_fr"])

    def test_adolescent_uses_noun_example(self):
        r = self.by["adolescent|NOM"]
        self.assertIn("Cet adolescent", r["example_fr"])
        self.assertNotIn("adolescente", r["example_fr"])

    def test_russe_does_not_reintroduce_language_sense(self):
        r = self.by["russe|ADJ"]
        self.assertNotIn("langue russe", r["example_fr"])

    def test_tendance_gloss_has_no_trend_wording(self):
        r = self.by["tendance|NOM"]
        self.assertNotIn("趋势", r["gloss_zh_short"])

    def test_employer_example_not_language_sense(self):
        r = self.by["employer|VER"]
        self.assertNotIn("mots", r["example_fr"])
        self.assertNotIn("s'exprimer", r["example_fr"])

    def test_signifier_example_not_language_sense(self):
        r = self.by["signifier|VER"]
        self.assertNotIn("Ce mot signifie", r["example_fr"])

    def test_plaire_natural_chinese(self):
        r = self.by["plaire|VER"]
        self.assertEqual(r["example_zh"], "我敢肯定，她会喜欢这份礼物。")

    def test_policier_natural_chinese(self):
        r = self.by["policier|NOM"]
        self.assertNotIn("监视这个路口", r["example_zh"])


if __name__ == "__main__":
    unittest.main()
