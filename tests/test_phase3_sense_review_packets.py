import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3_sense_review_packets as packets


class Phase3SenseReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((packets.OUT / "manifest.json").read_text())

    def test_exact_tier_packet_counts(self):
        self.assertEqual(self.manifest["tier_counts"], {"low": 34, "medium": 318, "high": 148})
        self.assertEqual(len(self.manifest["packets"]), 13)

    def test_union_reconstructs_all_parent_keys(self):
        parent = json.loads(packets.INPUT.read_text())
        keys = []
        for entry in self.manifest["packets"]:
            payload = json.loads((packets.OUT / entry["filename"]).read_text())
            keys.extend(row["stable_lexeme_key"] for row in payload["items"])
        self.assertEqual(len(keys), 500)
        self.assertEqual(set(keys), {row["stable_lexeme_key"] for row in parent["items"]})

    def test_compact_records_exclude_non_sense_context(self):
        forbidden = {"sourced_examples", "selected_sense_chinese_candidates", "relevant_sourced_family_relations", "translation_flags", "content_authoring_flags"}
        for entry in self.manifest["packets"]:
            rows = json.loads((packets.OUT / entry["filename"]).read_text())["items"]
            for row in rows:
                self.assertFalse(forbidden & set(row))
                self.assertIn("current_proposed_sense", row)
                self.assertIn("all_source_senses", row)
