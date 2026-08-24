#!/usr/bin/env python3
"""Regression tests for build_graph.py's ForceAtlas2-input determinism.

Python randomizes str hashing per process (PYTHONHASHSEED), which changes
set[str] iteration order across separate runs. build_graph.py's candidate
generation used to iterate token sets directly, so two builds of the exact
same lexicon could pick different (but equally scored) edges. These tests
run the affected functions in fresh subprocesses with different explicit
PYTHONHASHSEED values -- the same way two independent CI runs would differ
-- and assert the output is byte-identical regardless.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_GRAPH = ROOT / "scripts" / "build_graph.py"


def run_sparse_neighbors_in_subprocess(hash_seed: str) -> str:
    """Run sparse_neighbors() on a fixed input in a fresh process with a
    pinned PYTHONHASHSEED, and return its JSON-serialized result."""
    script = f"""
import sys
sys.path.insert(0, {str(ROOT / "scripts")!r})
import json
from build_graph import sparse_neighbors

# A features set deliberately sized so genuine near-ties in cosine score
# are likely: many nodes share overlapping 3-gram tokens with only tiny
# weight differences, the same shape as real spelling/phonetic candidates.
features = {{
    1: {{"a", "b", "c", "d", "e"}},
    2: {{"a", "b", "c", "d", "f"}},
    3: {{"a", "b", "c", "e", "f"}},
    4: {{"a", "b", "d", "e", "f"}},
    5: {{"a", "c", "d", "e", "f"}},
    6: {{"b", "c", "d", "e", "f"}},
    7: {{"a", "b", "c", "d", "g"}},
    8: {{"a", "b", "c", "d", "h"}},
}}
directed, fallback = sparse_neighbors(features, k=3, threshold=0.0, max_df=140)
result = {{
    "directed": {{str(k): v for k, v in sorted(directed.items())}},
    "fallback": sorted(fallback),
}}
print(json.dumps(result, sort_keys=True))
"""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        cwd=ROOT,
    )
    return completed.stdout.strip()


class SparseNeighborsHashSeedDeterminism(unittest.TestCase):
    def test_identical_output_across_different_hash_seeds(self):
        outputs = {
            seed: run_sparse_neighbors_in_subprocess(seed)
            for seed in ("0", "1", "2", "42", "12345")
        }
        baseline_seed, baseline = next(iter(outputs.items()))
        for seed, output in outputs.items():
            self.assertEqual(
                output, baseline,
                f"sparse_neighbors output differs between PYTHONHASHSEED={baseline_seed} "
                f"and PYTHONHASHSEED={seed}; a set[str] is likely being iterated "
                f"without sorting somewhere in the candidate-generation path.",
            )

    def test_source_sorts_every_token_set_iteration(self):
        # The subprocess test above is a real end-to-end check, but a tie
        # sharp enough to flip on a hash-seed change is a narrow floating
        # point target to hit reliably in a small fixture. Pin the fix at
        # the source level too: every place sparse_neighbors iterates a
        # set[str] token collection (as opposed to a list or dict, which
        # are already insertion-ordered) must go through sorted().
        source = BUILD_GRAPH.read_text(encoding="utf-8")
        start = source.index("def sparse_neighbors(")
        end = source.index("\ndef ", start + 1)
        body = source[start:end]
        self.assertIn(
            "for token in sorted(tokens):",
            body,
            "postings construction must iterate sorted(tokens), not the raw set",
        )
        self.assertIn(
            "for token in sorted(tokens) if token in weights",
            body,
            "the norm sum must iterate sorted(tokens), not the raw set -- "
            "summing floats in a hash-randomized order changes the result "
            "in its last bit and can flip an exact-score tie downstream",
        )
        self.assertNotIn(
            "for token in tokens:",
            body,
            "found an unsorted iteration over a token set inside sparse_neighbors",
        )


class LayoutLinksQueryOrdering(unittest.TestCase):
    """build_graph.py reads layout_links back out to build graph-data.js.
    Without an explicit ORDER BY, SQLite does not guarantee row order is
    stable across runs, which fed non-determinism into edge/community
    assignment downstream. Guard the source directly against regressing."""

    def test_source_selects_layout_links_with_explicit_order_by(self):
        source = BUILD_GRAPH.read_text(encoding="utf-8")
        self.assertIn(
            "FROM layout_links ORDER BY a_id, b_id, signal",
            source,
            "the layout_links SELECT must keep its ORDER BY; removing it "
            "reintroduces run-to-run non-determinism in graph-data.js",
        )

    def test_query_returns_sorted_rows_regardless_of_insertion_order(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE layout_links (
              a_id INTEGER NOT NULL, b_id INTEGER NOT NULL, signal TEXT NOT NULL,
              weight REAL NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            )
            """
        )
        rows = [
            (3, 9, "spelling", 0.5, "{}", "t"),
            (1, 2, "phonetic", 0.4, "{}", "t"),
            (1, 2, "morphology", 0.9, "{}", "t"),
            (2, 5, "semantic", 0.3, "{}", "t"),
        ]
        conn.executemany("INSERT INTO layout_links VALUES(?,?,?,?,?,?)", rows)
        conn.commit()
        result = conn.execute(
            "SELECT a_id,b_id,signal,weight FROM layout_links ORDER BY a_id, b_id, signal"
        ).fetchall()
        expected = [
            (1, 2, "morphology", 0.9),
            (1, 2, "phonetic", 0.4),
            (2, 5, "semantic", 0.3),
            (3, 9, "spelling", 0.5),
        ]
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
