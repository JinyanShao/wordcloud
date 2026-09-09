import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3_risk_decomposition as risk


class Phase3RiskDecompositionTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(risk.OUT.read_text())

    def test_preserves_parent_identities_and_proposals(self):
        parent = {x["stable_lexeme_key"]: x for x in json.loads(risk.PARENT.read_text())["items"]}
        self.assertEqual(len(self.payload["items"]), 500)
        for row in self.payload["items"]:
            source = parent[row["stable_lexeme_key"]]
            self.assertEqual(row["parent_input_hash"], source["input_hash"])
            self.assertEqual(row["proposed_primary_learner_sense"], {k: source["proposed_primary_learner_sense"][k] for k in ("entry_id", "sense_id")})

    def test_translation_signals_never_contaminate_sense_axis(self):
        forbidden = {"no_default_chinese_candidate", "multiple_chinese_candidates", "candidate_not_sense_mapped", "structural_mapping_only", "nondefault_language_variant_present", "candidate_gloss_domain_mismatch_possible"}
        for row in self.payload["items"]:
            self.assertFalse(forbidden & set(row["sense_selection_flags"]))

    def test_routes_are_exact_projections(self):
        joined = []
        for route in risk.ROUTES:
            projection = json.loads((risk.OUT.parent / risk.ROUTE_FILES[route]).read_text())
            joined.extend(projection["items"])
        self.assertEqual({x["stable_lexeme_key"] for x in joined}, {x["stable_lexeme_key"] for x in self.payload["items"]})

    def test_phase2c_calibration(self):
        report = json.loads((risk.OUT.parent / "phase2c-risk-axis-calibration.json").read_text())
        self.assertEqual(report["dangerous_low_sense_false_negatives"], [])
        rows = {x["stable_lexeme_key"]: x for x in report["records"]}
        self.assertEqual(rows["antenne|NOM"]["sense_selection_tier"], "high")
        self.assertEqual(rows["chef|NOM"]["sense_selection_tier"], "high")
        self.assertNotEqual(rows["devoir|VER"]["sense_selection_tier"], "low")
        self.assertEqual(rows["personne|NOM"]["content_authoring_tier"], "high")
        self.assertNotEqual(rows["personne|NOM"]["sense_selection_tier"], "high")
