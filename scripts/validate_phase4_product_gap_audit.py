#!/usr/bin/env python3
"""Validate the deterministic Phase 4A audit artifact without changing production data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase4_product_gap_audit as builder

ARTIFACT = ROOT / "data/phase4/product-gap-audit.json"


def main() -> None:
    actual = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    expected = builder.build()
    if actual != expected:
        raise SystemExit("Phase 4A audit is stale or non-deterministic")
    overall = actual["coverage"]["overall"]
    if (overall["searchable"], overall["eligible_content"], overall["learner_aids"], overall["phase2c"], overall["phase3"]) != (9067, 9046, 598, 99, 499):
        raise SystemExit("production denominator mismatch")
    aid_keys = set()
    for rows in actual["top_missing_by_cefr"].values():
        for row in rows:
            if row["stable_lexeme_key"] in aid_keys or row["has_learner_aid"]:
                raise SystemExit("invalid missing-list learner identity")
            aid_keys.add(row["stable_lexeme_key"])
    print(json.dumps({"ok": True, "records": 598, "missing_lists": 4}, ensure_ascii=False))


if __name__ == "__main__":
    main()
