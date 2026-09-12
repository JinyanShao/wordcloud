import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_phase4d_learner_content import load, validate

FINAL_V2 = ROOT / "data/phase4/learner-candidate-final-v2.json"
CANON = ROOT / "data/phase4/learner-content-156-authored.json"
REVIEW = ROOT / "data/phase4/learner-content-156-review.jsonl"


def _records():
    canon = json.loads(CANON.read_text(encoding="utf-8"))
    return {r["stable_lexeme_key"]: r for r in canon["records"]}


class Phase4DStructuralValidatorTests(unittest.TestCase):
    def test_validator_passes_with_no_errors(self):
        final, canon, review = load()
        errors, _warnings = validate(final, canon, review)
        self.assertEqual(errors, [])

    def test_exactly_156_authored_records_no_blockers(self):
        canon = json.loads(CANON.read_text(encoding="utf-8"))
        self.assertEqual(len(canon["records"]), 156)
        self.assertEqual(canon["semantic_blockers"], [])

    def test_drop_keys_absent(self):
        recs = _records()
        for key in ("rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM"):
            self.assertNotIn(key, recs)

    def test_review_jsonl_matches_line_count(self):
        lines = [l for l in REVIEW.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 156)


class Phase4DRegressionCorrectionsTests(unittest.TestCase):
    """Locks in the 8 wording/sense-drift corrections from the independent review pass.

    These assertions exist to prevent the specific defects that were found from
    silently reappearing (e.g. via a future full re-author). They check
    observable prose properties, not semantic correctness in general.
    """

    @classmethod
    def setUpClass(cls):
        cls.recs = _records()

    def test_reprendre_no_longer_uses_sibling_sense_example(self):
        r = self.recs["reprendre|VER"]
        self.assertEqual(r["sense_id"], "__ws_1_reprendre__verb__1")
        self.assertNotIn("reprennent", r["example_fr"])
        self.assertNotIn("cours", r["example_fr"])
        self.assertIn("repris", r["example_fr"])
        self.assertNotIn("重新开始", r["gloss_zh_short"])

    def test_adolescent_example_uses_noun_not_adjective(self):
        r = self.recs["adolescent|NOM"]
        self.assertEqual(r["pos"], "NOM")
        self.assertNotIn("adolescente", r["example_fr"])
        self.assertIn("adolescent", r["example_fr"])
        # "cet adolescent" / "un adolescent" is unambiguous noun usage
        self.assertTrue(
            "cet adolescent" in r["example_fr"].lower() or "un adolescent" in r["example_fr"].lower()
        )

    def test_russe_example_is_nationality_not_language(self):
        r = self.recs["russe|ADJ"]
        self.assertEqual(r["sense_id"], "__ws_1_russe__adj__1")
        self.assertNotIn("langue russe", r["example_fr"])
        self.assertIn("俄罗斯人", r["example_zh"])

    def test_tendance_gloss_drops_trend_wording(self):
        r = self.recs["tendance|NOM"]
        self.assertNotIn("趋势", r["gloss_zh_short"])
        self.assertIn("倾向", r["gloss_zh_short"])

    def test_employer_example_is_general_not_language_sense(self):
        r = self.recs["employer|VER"]
        self.assertEqual(r["sense_id"], "__ws_1_employer__verb__1")
        self.assertNotIn("mots", r["example_fr"])
        self.assertNotIn("s'exprimer", r["example_fr"])

    def test_signifier_example_is_general_not_language_sense(self):
        r = self.recs["signifier|VER"]
        self.assertEqual(r["sense_id"], "__ws_1_signifier__verb__1")
        self.assertNotIn("mot signifie", r["example_fr"])
        self.assertNotIn("en français", r["example_fr"])

    def test_plaire_translation_is_natural_wording(self):
        r = self.recs["plaire|VER"]
        # French example (and its exact activated sense) is unchanged
        self.assertEqual(r["example_fr"], "Ce cadeau va lui plaire, j'en suis sûr.")
        self.assertEqual(r["example_zh"], "我敢肯定，她会喜欢这份礼物。")

    def test_policier_translation_is_natural_wording(self):
        r = self.recs["policier|NOM"]
        self.assertEqual(r["example_fr"], "Un policier surveille le carrefour.")
        self.assertNotIn("监视", r["example_zh"])


if __name__ == "__main__":
    unittest.main()
