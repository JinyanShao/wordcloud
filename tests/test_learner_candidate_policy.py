import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from learner_candidate_policy import candidate_context_for_selected_sense


class LearnerCandidatePolicyTests(unittest.TestCase):
    def test_structural_mapping_cannot_choose_or_approve_a_learner_sense(self):
        # Real regression shape: DBnary's insect-domain "触角" candidate maps
        # by sense number to a dated nautical antenna sense.  A separately
        # selected modern sense must not inherit it.
        candidate = {
            "candidate_class": "sense_mapped_candidate",
            "mapped_sense_id": "__ws_3_antenne__nom__1",
            "chinese_written_form": "触角",
            "translation_gloss": "(Entomologie) Appendice sensoriel.",
        }
        decision = candidate_context_for_selected_sense(
            "__ws_1_antenne__nom__1", candidate
        )
        self.assertFalse(decision["structural_match_for_selected_sense"])
        self.assertFalse(decision["automatic_learner_gloss_approval"])
        self.assertEqual(decision["semantic_status"], "requires_semantic_review")

    def test_even_matching_structural_mapping_requires_semantic_review(self):
        candidate = {
            "candidate_class": "sense_mapped_candidate",
            "mapped_sense_id": "__ws_3_antenne__nom__1",
        }
        decision = candidate_context_for_selected_sense(
            "__ws_3_antenne__nom__1", candidate
        )
        self.assertTrue(decision["structural_match_for_selected_sense"])
        self.assertFalse(decision["automatic_learner_gloss_approval"])
        self.assertEqual(decision["semantic_status"], "requires_semantic_review")


if __name__ == "__main__":
    unittest.main()
