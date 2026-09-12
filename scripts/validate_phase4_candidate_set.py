#!/usr/bin/env python3
"""Structural validation for the Phase 4B candidate set; it makes no semantic judgement."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase4_candidate_set as builder


def main() -> None:
    records = [json.loads(line) for line in builder.JSONL.read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(builder.MANIFEST.read_text(encoding="utf-8"))
    gaps = json.loads(builder.SOURCE_GAPS.read_text(encoding="utf-8"))
    expected, expected_manifest, expected_gaps = builder.build()
    expected_raw = builder.serialize_jsonl(expected)
    expected_manifest["jsonl_sha256"] = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()
    expected_manifest["candidate_union_hash"] = builder.digest_value(expected)
    if records != expected or gaps != {**expected_gaps, "artifact_hash": builder.digest_value(expected_gaps)}:
        raise SystemExit("candidate artifact is stale or non-deterministic")
    if manifest != expected_manifest:
        raise SystemExit("candidate manifest hash mismatch")
    if len(records) != 160 or len({item["key"] for item in records}) != 160 or len({item["runtime_lexeme_id"] for item in records}) != 160:
        raise SystemExit("candidate count or identity failure")
    if Counter(item["cefr"] for item in records) != Counter({"A1": 50, "A2": 35, "B1": 50, "B2": 25}):
        raise SystemExit("CEFR quota failure")
    if sum(item["pos"] == "NOM" for item in records) > 96 or any(item["key"] in builder.BLOCKED or not item["source_senses"] for item in records):
        raise SystemExit("candidate readiness failure")
    gap_keys = {item["key"] for section in ("no_source_sense", "blocked") for item in gaps[section]}
    if gap_keys & {item["key"] for item in records}:
        raise SystemExit("source gap leaked into candidates")
    forbidden = {"gloss_zh_short", "usage_note_zh", "example_fr", "example_zh"}
    if any(forbidden & set(item) for item in records):
        raise SystemExit("learner prose leaked into candidate set")
    print(json.dumps({"ok": True, "candidates": 160, "source_gaps": len(gaps["no_source_sense"]), "blocked": len(gaps["blocked"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
