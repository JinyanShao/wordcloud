import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_phase4_product_gap_audit import build


class Phase4ProductGapAuditTests(unittest.TestCase):
    def test_production_counts_and_missing_lists(self):
        audit = build()
        overall = audit["coverage"]["overall"]
        self.assertEqual((overall["searchable"], overall["eligible_content"], overall["learner_aids"]), (9067, 9046, 598))
        self.assertEqual((overall["phase2c"], overall["phase3"]), (99, 499))
        self.assertTrue(all(len(rows) <= 50 for rows in audit["top_missing_by_cefr"].values()))
        self.assertTrue(all(not row["has_learner_aid"] for rows in audit["top_missing_by_cefr"].values() for row in rows))

    def test_build_is_deterministic(self):
        self.assertEqual(build(), build())
