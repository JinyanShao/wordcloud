#!/usr/bin/env python3
"""Validate Phase 2B learner draft structure against the 30-record fact input.

This validator deliberately does not judge Chinese semantic correctness.
It never scans the raw DBnary dump.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "learner-content-gapfill-pilot-input.json"
DRAFT = ROOT / "data" / "learner-content-gapfill-pilot.json"
STRATEGIES = {"sourced_reuse", "sourced_normalized", "ai_disambiguated", "ai_gap_fill", "blocked"}
STATUSES = {"ai_draft", "blocked"}
EXAMPLE_TYPES = {"sourced", "ai_generated"}


def canonical_hash(payload: dict) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def is_bound_sourced_example(example: str, source_examples: list[str]) -> bool:
    """Accept an exact source example or its leading standalone excerpt.

    A concise learner display may retain the first sentence/phrase of a
    longer attributed source example.  This remains an attribution check, not
    a semantic check; arbitrary internal substrings are intentionally refused.
    """
    normalized = example.strip()
    return any(
        normalized == source.strip() or source.strip().startswith(normalized)
        for source in source_examples
    )


def main() -> None:
    facts = json.loads(INPUT.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    errors: list[str] = []

    if draft.get("schema_version") != 1 or len(draft.get("items", [])) != 30:
        errors.append("draft must be schema version 1 with exactly 30 items")
    if draft.get("provenance", {}).get("input_artifact_hash") != facts.get("artifact_hash"):
        errors.append("draft provenance does not match input artifact hash")
    if draft.get("artifact_hash") != canonical_hash(draft):
        errors.append("draft artifact hash mismatch")

    fact_by_key = {
        (x["group"], x["stable_lexeme_key"], x["entry_id"], x["sense_id"]): x
        for x in facts.get("items", [])
    }
    seen = set()

    for item in draft.get("items", []):
        ident = item.get("identity", {})
        key = (item.get("group"), ident.get("stable_lexeme_key"), ident.get("entry_id"), ident.get("sense_id"))
        if key in seen:
            errors.append(f"duplicate draft identity {key}")
        seen.add(key)
        fact = fact_by_key.get(key)
        if not fact:
            errors.append(f"orphan draft identity {key}")
            continue
        if ident.get("runtime_lexeme_id") != fact.get("runtime_lexeme_id"):
            errors.append(f"runtime lexeme id mismatch {key}")
        if item.get("input_hash") != fact.get("input_hash"):
            errors.append(f"per-item input hash mismatch {key}")

        strategy = item.get("gloss_source_strategy")
        status = item.get("content_status")
        if strategy not in STRATEGIES:
            errors.append(f"invalid strategy {key}: {strategy}")
        if status not in STATUSES:
            errors.append(f"invalid status {key}: {status}")

        available = {
            c["candidate_stable_ref"]: c
            for c in fact.get("matching_chinese_candidates", [])
        }
        used = item.get("used_candidate_refs", [])
        rejected = item.get("rejected_candidates", [])
        rejected_refs = [x.get("candidate_ref") for x in rejected]
        for ref in used + rejected_refs:
            if ref not in available:
                errors.append(f"unknown candidate ref {ref} for {key}")
        if set(used) & set(rejected_refs):
            errors.append(f"candidate both used and rejected for {key}")
        if strategy in {"sourced_reuse", "sourced_normalized"} and not used:
            errors.append(f"source-based strategy without used candidate for {key}")
        for ref in used:
            if available[ref].get("learner_language_eligibility") != "default_learner_chinese":
                errors.append(f"non-default Chinese candidate used for {key}: {ref}")

        if status == "blocked" or strategy == "blocked":
            if status != "blocked" or strategy != "blocked":
                errors.append(f"blocked strategy/status mismatch {key}")
            if any(item.get(field) for field in ("gloss_zh_short", "usage_note_zh", "example_fr", "example_zh")):
                errors.append(f"blocked item contains learner content {key}")
            continue

        if not item.get("gloss_zh_short") or not item.get("example_fr") or not item.get("example_zh"):
            errors.append(f"draft lacks required learner content {key}")
        if item.get("example_source_type") not in EXAMPLE_TYPES:
            errors.append(f"invalid example source type {key}")
        if item.get("example_source_type") == "sourced" and not is_bound_sourced_example(
            item.get("example_fr", ""), fact.get("sourced_examples", [])
        ):
            errors.append(f"sourced example not present in bound sense {key}")

    if set(fact_by_key) != seen:
        errors.append("draft identities do not exactly cover the 30 input identities")
    if [sum(x.get("group") == g for x in draft.get("items", [])) for g in "ABC"] != [10, 10, 10]:
        errors.append("draft groups must each contain 10 items")

    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps({"ok": True, "items": 30, "semantic_review": "external model review only; human/expert review not claimed"}))


if __name__ == "__main__":
    main()
