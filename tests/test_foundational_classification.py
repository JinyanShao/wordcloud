"""Regression coverage for foundational words admitted to the main map."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_data import classify


class FoundationalClassificationTests(unittest.TestCase):
    def row(self, word, tag="NOM", level="A1"):
        return SimpleNamespace(word=word, tag=tag, level=level, freq_total=10)

    def test_aligned_a1_content_word_is_eligible(self):
        self.assertEqual(
            classify(self.row("école"), {"lemma": "école"}, ["école"])[0:2],
            ("eligible", "foundational_content"),
        )

    def test_negation_words_stay_out_of_main_map(self):
        for word in ("ne", "pas"):
            self.assertEqual(
                classify(self.row(word, tag="ADV"), {"lemma": word}, [word])[0:2],
                ("auxiliary", "functional_adverb"),
            )

    def test_cardinal_mislabelled_as_noun_requires_numeral_model(self):
        self.assertEqual(
            classify(self.row("quatre"), {"lemma": "quatre"}, ["quatre"])[0:2],
            ("needs_review", "unsupported_numeral"),
        )


if __name__ == "__main__":
    unittest.main()
