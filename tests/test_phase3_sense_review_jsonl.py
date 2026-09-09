import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3_sense_review_jsonl as jsonl


class Phase3SenseReviewJsonlTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads(jsonl.INDEX.read_text())
        self.rows = [json.loads(line) for line in jsonl.JSONL.read_text().splitlines()]

    def test_exact_line_count_and_ranges(self):
        self.assertEqual(len(self.rows), 500)
        self.assertEqual(self.index["total"], 500)
        self.assertEqual(self.index["low_range"], {"start_line": 1, "end_line": 34})
        self.assertEqual(self.index["medium_range"], {"start_line": 35, "end_line": 352})
        self.assertEqual(self.index["high_range"], {"start_line": 353, "end_line": 500})

    def test_each_line_has_only_reader_fields(self):
        expected = {"key", "lemma", "pos", "cefr", "tier", "proposed", "senses", "flags"}
        self.assertTrue(all(set(row) == expected for row in self.rows))
        self.assertEqual(len({row["key"] for row in self.rows}), 500)
