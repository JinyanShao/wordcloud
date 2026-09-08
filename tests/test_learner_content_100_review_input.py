import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_learner_content_100_review_input import build, proposals_from_sqlite, propose_primary_sense


class LearnerContent100ReviewInputTests(unittest.TestCase):
    def test_build_is_deterministic_and_stratified(self):
        first, second = build(), build()
        self.assertEqual(first, second)
        self.assertEqual(len(first["items"]), 100)
        self.assertEqual(len({x["runtime_lexeme_id"] for x in first["items"]}), 100)

    def test_dated_source_sense_is_not_preferred_when_a_plain_sense_exists(self):
        senses = [
            {"entry_id": "e", "sense_id": "old", "source_order": 1, "definition_fr": "(Vieilli) Sens maritime.", "sense_number": "1", "sourced_examples": [], "source_id": "dbnary_fr"},
            {"entry_id": "e", "sense_id": "modern", "source_order": 2, "definition_fr": "Appareil moderne.", "sense_number": "2", "sourced_examples": [], "source_id": "dbnary_fr"},
        ]
        selected, _, _ = propose_primary_sense(senses)
        self.assertEqual(selected["sense_id"], "modern")

    def test_candidate_context_never_approves_glosses(self):
        payload = build()
        for item in payload["items"]:
            for candidate in item["selected_sense_chinese_candidates"]:
                self.assertFalse(candidate["automatic_learner_gloss_approval"])

    def test_sense_proposals_are_available_before_candidate_join(self):
        proposals = proposals_from_sqlite()
        self.assertEqual(len(proposals), 100)
        self.assertNotIn("selected_sense_chinese_candidates", proposals[0])
        self.assertTrue(all(x["selection_status"] == "needs_semantic_review" for x in proposals))


if __name__ == "__main__":
    unittest.main()
