#!/usr/bin/env python3
"""Regression test for the DBnary definition-citation-prefix cleanup.

DBnary occasionally embeds a stray numbered cross-reference fragment before
the real definition text (e.g. "Faire (2) à manger.\n Créer, produire,
fabriquer..."). clean_definition() strips that fragment; these tests pin
the known-bad cases found in the raw dump and guard against stripping
legitimate definitions that merely start with a parenthetical register/
domain tag like "(Argot poilu)".
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_dbnary import clean_definition  # noqa: E402


class CleanDefinition(unittest.TestCase):
    def test_strips_faire_citation_fragment(self):
        self.assertEqual(
            clean_definition(
                "Faire (2) à manger.\n Créer, produire, fabriquer, en parlant de toute œuvre matérielle."
            ),
            "Créer, produire, fabriquer, en parlant de toute œuvre matérielle.",
        )

    def test_strips_tirer_citation_fragments(self):
        self.assertEqual(
            clean_definition(
                "Tirer (26) une fusée.\n (Photographie) Réaliser une épreuve sur papier "
                "à partir d'une image originale sur film ou support informatique."
            ),
            "(Photographie) Réaliser une épreuve sur papier à partir d'une image "
            "originale sur film ou support informatique.",
        )
        self.assertEqual(
            clean_definition("Tirer (41) des câbles de fibre optique.\n (Par métonymie) (Construction) Installer des câbles."),
            "(Par métonymie) (Construction) Installer des câbles.",
        )

    def test_leaves_parenthetical_register_tag_untouched(self):
        text = "(Argot poilu) N'avoir rien à manger."
        self.assertEqual(clean_definition(text), text)

    def test_leaves_plain_definition_untouched(self):
        text = "Percevoir l'image des objets par l'organe de la vue."
        self.assertEqual(clean_definition(text), text)

    def test_leaves_multiline_definition_without_citation_marker_untouched(self):
        # No "(digits)" marker on the first line -- nothing to strip.
        text = "Première ligne sans référence numérotée.\n Deuxième ligne."
        self.assertEqual(clean_definition(text), text)


if __name__ == "__main__":
    unittest.main()
