import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_learner_content_pilot import DB_PATH, build
from validate_learner_content_pilot import attested_forms, tokens, validate


class LearnerPilotTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.draft = json.loads((root / "data" / "learner-content-pilot.json").read_text())
        self.facts = build()

    def test_input_is_facts_only_and_deterministic(self):
        self.assertEqual(self.facts, build())
        self.assertNotIn("gloss_zh_short", self.facts["items"][0])
        self.assertIn("definition_fr", self.facts["items"][0])

    def test_stable_relation_key_is_the_durable_reference(self):
        self.assertTrue(self.draft["items"][6]["relation_stable_keys"][0].startswith("fam|derivational_morphology|"))
        self.assertNotIn("relation_edge_ids", self.draft["items"][6])

    def test_forms_come_from_sqlite_not_a_pilot_allowlist(self):
        conn = sqlite3.connect(DB_PATH)
        try:
            forms = attested_forms(conn, 9976, "pouvoir", "VER")
        finally:
            conn.close()
        self.assertIn("peux", forms)
        self.assertTrue(tokens("Je peux venir.") & forms)

    def test_provenance_and_input_separation_are_valid(self):
        errors, unknown = validate(self.draft, self.facts)
        self.assertEqual(errors, [])
        self.assertEqual(unknown, 0)
        self.assertEqual(self.draft["provenance"]["actual_model"], "unknown")


if __name__ == "__main__":
    unittest.main()
