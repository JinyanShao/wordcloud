import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_learner_content_pilot import build
from validate_learner_content_pilot import contains_target, validate


class LearnerPilotTests(unittest.TestCase):
    def test_approved_conjugated_form_counts_as_target(self):
        self.assertTrue(contains_target({"example_fr": "Je peux venir."}, "pouvoir"))

    def test_unrelated_example_does_not_count(self):
        self.assertFalse(contains_target({"example_fr": "Nous arrivons demain."}, "pouvoir"))

    def test_relation_edge_must_stay_sourced_and_connected(self):
        payload = build()
        payload["items"][6]["relation_edge_ids"] = [999999]
        self.assertTrue(any("unsourced or unrelated relation edge" in error for error in validate(payload)))


if __name__ == "__main__":
    unittest.main()
