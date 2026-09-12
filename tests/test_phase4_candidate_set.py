import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_phase4_candidate_set import JSONL, build


class Phase4CandidateSetTests(unittest.TestCase):
    def test_candidate_shape_and_gate(self):
        records, _, gaps = build()
        self.assertEqual(len(records), 160)
        self.assertEqual(Counter(item["cefr"] for item in records), Counter({"A1": 50, "A2": 35, "B1": 50, "B2": 25}))
        self.assertLessEqual(sum(item["pos"] == "NOM" for item in records), 96)
        self.assertTrue(all(item["source_sense_count"] >= 1 for item in records))
        self.assertFalse({"travers|NOM", "cesse|NOM"} & {item["key"] for item in records})
        self.assertTrue(all(item["reason"] == "no_source_sense" for item in gaps["no_source_sense"]))

    def test_jsonl_matches_deterministic_build(self):
        records, _, _ = build()
        actual = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(actual, records)
