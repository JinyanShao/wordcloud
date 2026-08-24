#!/usr/bin/env python3
"""Unit tests for the sync-review manual-decision reason-prefix idempotency fix.

Run directly: python3 scripts/test_build_data_sync_review.py
Uses only an in-memory SQLite DB (a minimal lexemes/audit_samples fixture) —
no real production database or files are touched.
"""

from __future__ import annotations

import sqlite3
import unittest

import build_data


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE lexemes (
          id INTEGER PRIMARY KEY,
          status TEXT NOT NULL,
          decision_reason TEXT NOT NULL
        );
        CREATE TABLE audit_samples (
          audit_id TEXT NOT NULL,
          sample_order INTEGER NOT NULL,
          lexeme_id INTEGER NOT NULL,
          manual_decision TEXT,
          manual_note TEXT,
          reviewer TEXT,
          reviewed_at TEXT
        );
        """
    )
    return conn


def make_row(sample_order=1, lexeme_id=1, decision="", note="", audit_id="a1"):
    return {
        "audit_id": audit_id,
        "sample_order": str(sample_order),
        "lexeme_id": str(lexeme_id),
        "manual_decision": decision,
        "manual_note": note,
    }


class PrefixNormalizationTests(unittest.TestCase):
    """Pure-function coverage for the prefix stripping/application helpers."""

    def test_no_prefix_gets_one_prefix_added(self):
        result = build_data.with_single_manual_prefix(
            "low_frequency_missing_gloss", "manual_audit_override:"
        )
        self.assertEqual(result, "manual_audit_override:low_frequency_missing_gloss")

    def test_already_one_prefix_stays_one(self):
        once = "manual_audit_override:low_frequency_missing_gloss"
        result = build_data.with_single_manual_prefix(once, "manual_audit_override:")
        self.assertEqual(result, once)

    def test_two_or_three_stacked_prefixes_normalize_to_one(self):
        twice = "manual_audit_override:manual_audit_override:low_frequency_missing_gloss"
        thrice = (
            "manual_audit_override:manual_audit_override:manual_audit_override:"
            "low_frequency_missing_gloss"
        )
        expected = "manual_audit_override:low_frequency_missing_gloss"
        self.assertEqual(
            build_data.with_single_manual_prefix(twice, "manual_audit_override:"), expected
        )
        self.assertEqual(
            build_data.with_single_manual_prefix(thrice, "manual_audit_override:"), expected
        )

    def test_original_reason_after_prefix_is_preserved(self):
        original = "target_content_high_frequency_missing_gloss"
        stacked = f"manual_audit_override:manual_audit_override:{original}"
        result = build_data.with_single_manual_prefix(stacked, "manual_audit_override:")
        self.assertTrue(result.endswith(original))
        self.assertEqual(result, f"manual_audit_override:{original}")

    def test_mixed_override_and_defer_prefixes_collapse_to_the_requested_one(self):
        mixed = "manual_audit_defer:manual_audit_override:manual_audit_defer:base_reason"
        result = build_data.with_single_manual_prefix(mixed, "manual_audit_override:")
        self.assertEqual(result, "manual_audit_override:base_reason")

    def test_does_not_touch_legitimate_text_that_is_not_a_prefix(self):
        # The known prefixes must only be stripped when anchored at the start.
        reason = "some_reason_mentions manual_audit_override: in the middle"
        result = build_data.strip_manual_reason_prefixes(reason)
        self.assertEqual(result, reason)


class ApplyManualDecisionsTests(unittest.TestCase):
    """Exercises the real SQL update path against a minimal in-memory DB."""

    def setUp(self):
        self.conn = make_conn()
        self.addCleanup(self.conn.close)

    def _insert_lexeme(self, lexeme_id, status, decision_reason):
        self.conn.execute(
            "INSERT INTO lexemes(id, status, decision_reason) VALUES(?,?,?)",
            (lexeme_id, status, decision_reason),
        )

    def _insert_sample(self, sample_order, lexeme_id, audit_id="a1"):
        self.conn.execute(
            "INSERT INTO audit_samples(audit_id, sample_order, lexeme_id) VALUES(?,?,?)",
            (audit_id, sample_order, lexeme_id),
        )

    def _reason(self, lexeme_id):
        return self.conn.execute(
            "SELECT decision_reason FROM lexemes WHERE id=?", (lexeme_id,)
        ).fetchone()[0]

    def _status(self, lexeme_id):
        return self.conn.execute(
            "SELECT status FROM lexemes WHERE id=?", (lexeme_id,)
        ).fetchone()[0]

    def test_first_run_adds_single_prefix(self):
        self._insert_lexeme(1, "excluded", "low_frequency_missing_gloss")
        self._insert_sample(1, 1)
        rows = [make_row(sample_order=1, lexeme_id=1, decision="override_eligible")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")

        self.assertEqual(self._reason(1), "manual_audit_override:low_frequency_missing_gloss")
        self.assertEqual(self._status(1), "eligible")

    def test_non_override_records_are_unaffected(self):
        self._insert_lexeme(2, "eligible", "target_content_high_frequency_missing_gloss")
        self._insert_sample(1, 2)
        rows = [make_row(sample_order=1, lexeme_id=2, decision="agree")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")

        self.assertEqual(self._reason(2), "target_content_high_frequency_missing_gloss")
        self.assertEqual(self._status(2), "eligible")

    def test_empty_decision_leaves_lexeme_untouched(self):
        self._insert_lexeme(3, "excluded", "non_content_pos")
        self._insert_sample(1, 3)
        rows = [make_row(sample_order=1, lexeme_id=3, decision="")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")

        self.assertEqual(self._reason(3), "non_content_pos")
        self.assertEqual(self._status(3), "excluded")

    def test_consecutive_runs_are_byte_identical(self):
        self._insert_lexeme(4, "excluded", "low_frequency_missing_gloss")
        self._insert_sample(1, 4)
        rows = [make_row(sample_order=1, lexeme_id=4, decision="override_eligible", note="ok")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")
        first_reason = self._reason(4)
        first_status = self._status(4)

        # Re-run the exact same rows against the DB state left by the first run,
        # simulating pnpm data:review being invoked twice in a row.
        build_data.apply_manual_decisions(self.conn, rows, "2026-01-02T00:00:00Z")
        second_reason = self._reason(4)
        second_status = self._status(4)

        self.assertEqual(first_reason, "manual_audit_override:low_frequency_missing_gloss")
        self.assertEqual(first_reason, second_reason)
        self.assertEqual(first_status, second_status)

    def test_pre_existing_stacked_prefix_from_a_prior_buggy_run_self_heals(self):
        # Simulates a lexeme already corrupted by the old bug (three stacked
        # prefixes from repeated sync-review runs before this fix existed).
        stacked = (
            "manual_audit_override:manual_audit_override:manual_audit_override:"
            "low_frequency_missing_gloss"
        )
        self._insert_lexeme(5, "eligible", stacked)
        self._insert_sample(1, 5)
        rows = [make_row(sample_order=1, lexeme_id=5, decision="override_eligible")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")

        self.assertEqual(self._reason(5), "manual_audit_override:low_frequency_missing_gloss")

    def test_defer_prefix_is_also_idempotent(self):
        self._insert_lexeme(6, "eligible", "target_content_high_frequency_missing_gloss")
        self._insert_sample(1, 6)
        rows = [make_row(sample_order=1, lexeme_id=6, decision="defer")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")
        first_reason = self._reason(6)
        build_data.apply_manual_decisions(self.conn, rows, "2026-01-02T00:00:00Z")
        second_reason = self._reason(6)

        self.assertEqual(
            first_reason,
            "manual_audit_defer:target_content_high_frequency_missing_gloss",
        )
        self.assertEqual(first_reason, second_reason)
        self.assertEqual(self._status(6), "needs_review")

    def test_audit_samples_row_is_also_stable_across_reruns(self):
        self._insert_lexeme(7, "excluded", "non_content_pos")
        self._insert_sample(1, 7)
        rows = [make_row(sample_order=1, lexeme_id=7, decision="override_eligible", note="x")]

        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")
        first = self.conn.execute(
            "SELECT manual_decision, manual_note, reviewer FROM audit_samples WHERE sample_order=1"
        ).fetchone()
        build_data.apply_manual_decisions(self.conn, rows, "2026-01-01T00:00:00Z")
        second = self.conn.execute(
            "SELECT manual_decision, manual_note, reviewer FROM audit_samples WHERE sample_order=1"
        ).fetchone()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
