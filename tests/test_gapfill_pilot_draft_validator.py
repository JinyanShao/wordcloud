import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_gapfill_pilot_draft import is_bound_sourced_example


class GapfillDraftValidatorTests(unittest.TestCase):
    def test_accepts_exact_or_leading_attributed_excerpt(self):
        sources = ["Magasin d’antiquités. — Marchand d’antiquités."]
        self.assertTrue(is_bound_sourced_example("Magasin d’antiquités.", sources))
        self.assertTrue(is_bound_sourced_example(sources[0], sources))

    def test_rejects_unattributed_or_internal_fragment(self):
        sources = ["Magasin d’antiquités. — Marchand d’antiquités."]
        self.assertFalse(is_bound_sourced_example("Marchand d’antiquités.", sources))
        self.assertFalse(is_bound_sourced_example("Une boutique d’antiquités.", sources))


if __name__ == "__main__":
    unittest.main()
