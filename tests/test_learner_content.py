"""Keep Phase 1 learner classifications conservative and stable."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_learner_content import classify, pattern_key, stable_key


class LearnerContentTests(unittest.TestCase):
    def test_simple_direct_suffix_is_observed_not_productive(self):
        relation_type, transparency, observed = classify(
            "suffixation", {"complexity": "simple", "orientation": "as2des"}, True
        )
        self.assertEqual((relation_type, transparency, observed), ("suffix", "observed_structure", True))
        self.assertEqual(pattern_key(relation_type, {"scheme_1": "X", "scheme_2": "Xment"}, "VER", "NOM"), "suffix|X>Xment|VER>NOM")

    def test_semantic_derivation_is_opaque_and_has_no_observed_pattern(self):
        self.assertEqual(
            classify("semantic_derivation", {"complexity": "simple", "orientation": "as2des"}, True),
            ("irregular_family", "opaque", False),
        )

    def test_stable_key_uses_lexical_identity_not_database_id(self):
        self.assertEqual(
            stable_key("faire|VER", "refaire|VER", "prefixation"),
            stable_key("refaire|VER", "faire|VER", "prefixation"),
        )


if __name__ == "__main__":
    unittest.main()
