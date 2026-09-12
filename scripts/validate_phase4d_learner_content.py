"""Structural validator for Phase 4D learner content.

This script performs structural validation ONLY. It does not generate,
translate, or judge semantic prose, and it does not prove semantic
correctness -- it proves that the canonical authored artifact and its
derived review projection are internally consistent with the frozen
Phase 4C-v2 sense selections and free of known packaging defects
(duplicate keys, empty required fields, forbidden characters, drift
between canonical and review, leaked drops).

Usage:
    python3 scripts/validate_phase4d_learner_content.py
Exits non-zero and prints every failure if any check fails.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL_V2 = ROOT / "data/phase4/learner-candidate-final-v2.json"
CANON = ROOT / "data/phase4/learner-content-156-authored.json"
REVIEW = ROOT / "data/phase4/learner-content-156-review.jsonl"

DROP_KEYS = {"rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM"}

REQUIRED_RECORD_FIELDS = (
    "stable_lexeme_key", "runtime_lexeme_id", "lemma", "pos", "cefr",
    "entry_id", "sense_id", "sense_number",
    "gloss_zh_short", "usage_note_zh", "example_fr", "example_zh",
    "content_status", "cohort",
)

REQUIRED_NON_EMPTY_FIELDS = ("gloss_zh_short", "example_fr", "example_zh")

FORBIDDEN_SUBSTRINGS = ("的的", "地地")


def load():
    final = json.loads(FINAL_V2.read_text(encoding="utf-8"))
    canon = json.loads(CANON.read_text(encoding="utf-8"))
    review = [json.loads(line) for line in REVIEW.read_text(encoding="utf-8").splitlines() if line.strip()]
    return final, canon, review


def validate(final, canon, review):
    errors = []
    warnings = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    records = canon.get("records", [])
    blockers = canon.get("semantic_blockers", [])

    # 1. final-v2 KEEP is exactly 156
    check(len(final) == 156, f"final-v2 KEEP count != 156 (got {len(final)})")

    # 2. authored records + blockers account for all 156
    check(len(records) + len(blockers) == 156,
          f"authored records ({len(records)}) + blockers ({len(blockers)}) != 156")
    if blockers:
        warnings.append(f"{len(blockers)} semantic_blockers present")
    else:
        check(len(records) == 156, f"authored records != 156 with no blockers (got {len(records)})")

    # 3. required record fields present, no unknown-shape records
    for r in records:
        missing = [f for f in REQUIRED_RECORD_FIELDS if f not in r]
        check(not missing, f"{r.get('stable_lexeme_key')}: missing fields {missing}")

    canon_keys = {r["stable_lexeme_key"] for r in records}
    blocker_keys = {b["key"] for b in blockers} if blockers else set()
    final_keys = {r["key"] for r in final}

    # 4. exact stable-key equality between (canonical + blockers) and final-v2 KEEP set
    check(canon_keys | blocker_keys == final_keys,
          f"key set mismatch vs final-v2: {(canon_keys | blocker_keys) ^ final_keys}")

    # 5. the 4 frozen DROP keys are absent everywhere
    check(canon_keys.isdisjoint(DROP_KEYS), f"DROP keys leaked into canonical records: {canon_keys & DROP_KEYS}")
    review_keys = {r["stable_lexeme_key"] for r in review}
    check(review_keys.isdisjoint(DROP_KEYS), f"DROP keys leaked into review jsonl: {review_keys & DROP_KEYS}")

    # 6. no duplicate stable keys in canonical
    check(len(canon_keys) == len(records), "duplicate stable_lexeme_key in canonical records")

    # 7. entry_id / sense_id / sense_number / runtime_lexeme_id / lemma / pos / cefr
    #    are 100% frozen to final-v2 -- no silent reselection.
    final_by_key = {r["key"]: r for r in final}
    for r in records:
        k = r["stable_lexeme_key"]
        fr = final_by_key.get(k)
        if fr is None:
            continue  # already reported by the key-set check above
        check(r["entry_id"] == fr["selected_entry_id"], f"{k}: entry_id drifted from final-v2")
        check(r["sense_id"] == fr["selected_sense_id"], f"{k}: sense_id drifted from final-v2")
        check(r["sense_number"] == fr["selected_sense_number"], f"{k}: sense_number drifted from final-v2")
        check(r["runtime_lexeme_id"] == fr["runtime_lexeme_id"], f"{k}: runtime_lexeme_id mismatch")
        check(r["lemma"] == fr["lemma"], f"{k}: lemma mismatch")
        check(r["pos"] == fr["pos"], f"{k}: pos mismatch")
        check(r["cefr"] == fr["cefr"], f"{k}: cefr mismatch")

    # 8. required semantic fields non-empty (usage_note_zh may be null/empty)
    for r in records:
        k = r["stable_lexeme_key"]
        for field in REQUIRED_NON_EMPTY_FIELDS:
            val = r.get(field)
            check(bool(val) and str(val).strip() != "", f"{k}: empty required field {field}")

    # 9. content_status must be the authoring label, never "reviewed"
    for r in records:
        k = r["stable_lexeme_key"]
        check(r.get("content_status") == "external_semantic_authored", f"{k}: unexpected content_status")
        check(r.get("content_status") != "reviewed", f"{k}: content_status must not claim 'reviewed'")

    # 10. no forbidden repeated-character typos in Chinese fields
    for r in records:
        k = r["stable_lexeme_key"]
        blob = " ".join(str(r.get(f) or "") for f in ("gloss_zh_short", "usage_note_zh", "example_zh"))
        for bad in FORBIDDEN_SUBSTRINGS:
            check(bad not in blob, f"{k}: contains forbidden substring '{bad}'")

    # 11. review jsonl is an exact, deterministic projection of canonical + final-v2
    check(len(review) == len(records), "review jsonl length != canonical records length")
    rev_by_key = {r["stable_lexeme_key"]: r for r in review}
    rederived = []
    for r in records:
        k = r["stable_lexeme_key"]
        fr = final_by_key.get(k)
        if fr is None:
            continue
        expected = {
            "stable_lexeme_key": k,
            "lemma": r["lemma"], "pos": r["pos"], "cefr": r["cefr"],
            "confidence": fr["confidence"],
            "entry_id": r["entry_id"], "sense_id": r["sense_id"], "sense_number": r["sense_number"],
            "selected_definition_fr": fr["selected_definition_fr"],
            "gloss_zh_short": r["gloss_zh_short"], "usage_note_zh": r["usage_note_zh"],
            "example_fr": r["example_fr"], "example_zh": r["example_zh"],
        }
        rederived.append(expected)
        actual = rev_by_key.get(k)
        check(actual is not None, f"{k}: missing from review jsonl")
        if actual is not None:
            check(actual == expected, f"{k}: review jsonl row is not an exact projection of canonical + final-v2")

    # 12. no duplicate example_fr / example_zh (anti-template signal, not semantic proof)
    fr_examples = [r["example_fr"] for r in records]
    dupes = [s for s, c in Counter(fr_examples).items() if c > 1]
    check(not dupes, f"duplicate example_fr found: {dupes}")
    zh_examples = [r["example_zh"] for r in records]
    dupes_zh = [s for s, c in Counter(zh_examples).items() if c > 1]
    check(not dupes_zh, f"duplicate example_zh found: {dupes_zh}")

    return errors, warnings


def main() -> int:
    final, canon, review = load()
    errors, warnings = validate(final, canon, review)

    for w in warnings:
        print(f"WARNING: {w}")

    if errors:
        print(f"FAILED: {len(errors)} structural error(s)")
        for e in errors:
            print(f" - {e}")
        return 1

    print(f"OK: {len(canon.get('records', []))} authored records, "
          f"{len(canon.get('semantic_blockers', []))} semantic_blockers -- "
          "structural checks passed (this does not prove semantic correctness)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
