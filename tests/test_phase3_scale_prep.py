import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3_scale_prep as build


class Phase3ScalePrepTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(build.OUT.read_text())

    def test_exactly_500_new_lexemes(self):
        items = self.payload["items"]
        production = build.production_keys()
        self.assertEqual(len(items), 500)
        self.assertEqual(len({item["stable_lexeme_key"] for item in items}), 500)
        self.assertFalse(production & {item["stable_lexeme_key"] for item in items})

    def test_risk_projections_are_exact(self):
        for tier in build.TIERS:
            projection = json.loads((build.OUT.parent / f"{tier}.json").read_text())
            self.assertEqual(projection["parent_artifact_hash"], self.payload["artifact_hash"])
            self.assertEqual(projection["items"], [item for item in self.payload["items"] if item["risk_tier"] == tier])

    def test_candidate_does_not_select_sense(self):
        for item in self.payload["items"]:
            selected = item["proposed_primary_learner_sense"]
            self.assertIn((selected["entry_id"], selected["sense_id"]), {(sense["entry_id"], sense["sense_id"]) for sense in item["all_source_senses"]})
            self.assertIn("candidate-independent", item["selection_reason"])

    def test_phase2c_regressions_are_not_low_risk(self):
        report = json.loads((build.OUT.parent / "phase2c-calibration-report.json").read_text())
        self.assertEqual(report["dangerous_low_risk_false_negatives"], [])
        tiers = {item["stable_lexeme_key"]: item["risk_tier"] for item in report["records"]}
        self.assertEqual(tiers["antenne|NOM"], "high_risk")
        self.assertEqual(tiers["chef|NOM"], "high_risk")
        self.assertNotEqual(tiers["devoir|VER"], "low_risk")
