#!/usr/bin/env python3
"""Standalone validation for the clean production Phase 4 semantic source.

Depends only on production files (this repo's data/phase4 canonical source
and the committed graph-data.js). Does not read any phase4-product-gap-audit
research artifact. Proves structural/identity integrity and exact binding
to a real sense in graph-data.js -- it does not prove semantic correctness.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_graph import load_runtime  # noqa: E402

SOURCE = ROOT / "data/phase4/learner-content-156-authored.json"

BLOCKED_KEYS = {"rien|NOM", "grâce|NOM", "téléviser|VER", "événement|NOM"}

REQUIRED_FIELDS = {
    "stable_lexeme_key", "runtime_lexeme_id", "lemma", "pos", "cefr",
    "entry_id", "sense_id", "entry_rank", "sense_number",
    "gloss_zh_short", "example_fr", "example_zh",
    "content_status", "cohort",
}

# The 8 wording/sense-drift corrections found by independent review, locked
# against regression here (mirrored by tests/test_phase4_final_content.py).
EXPECTED_CORRECTIONS = {
    "reprendre|VER": {
        "sense_id": "__ws_1_reprendre__verb__1",
        "gloss_not_contains": "重新开始",
        "example_fr_not_contains": "Les cours reprennent",
    },
    "adolescent|NOM": {
        "example_fr_contains": "Cet adolescent",
        "example_fr_not_contains": "adolescente",
    },
    "russe|ADJ": {
        "example_fr_not_contains": "langue russe",
    },
    "tendance|NOM": {
        "gloss_not_contains": "趋势",
    },
    "employer|VER": {
        "example_fr_not_contains": "mots",
    },
    "signifier|VER": {
        "example_fr_not_contains": "Ce mot signifie",
    },
    "plaire|VER": {
        "example_zh_equals": "我敢肯定，她会喜欢这份礼物。",
    },
    "policier|NOM": {
        "example_zh_not_contains": "监视这个路口",
    },
}


def fail(msg: str):
    raise SystemExit(f"Phase 4 validation failed: {msg}")


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = data["records"]
    by_key = {r["stable_lexeme_key"]: r for r in rows}

    # --- source integrity ---
    if data.get("semantic_blockers") != []:
        fail(f"expected semantic_blockers == [], got {data.get('semantic_blockers')}")
    if len(rows) != 156:
        fail(f"expected 156 records, got {len(rows)}")
    if len(by_key) != 156:
        fail("duplicate stable_lexeme_key in Phase 4 source")
    if len({r["runtime_lexeme_id"] for r in rows}) != 156:
        fail("duplicate runtime_lexeme_id in Phase 4 source")

    # --- excluded drops absent ---
    leaked = BLOCKED_KEYS & set(by_key)
    if leaked:
        fail(f"blocked/dropped keys leaked into Phase 4 source: {leaked}")

    # --- per-record checks: required fields, status/cohort, content hygiene ---
    for r in rows:
        key = r["stable_lexeme_key"]
        missing = REQUIRED_FIELDS - set(r)
        if missing:
            fail(f"{key}: missing required fields {missing}")
        for field in REQUIRED_FIELDS - {"usage_note_zh"}:
            if r[field] in (None, ""):
                fail(f"{key}: required field '{field}' is empty")
        if r["content_status"] != "external_semantic_authored":
            fail(f"{key}: content_status must be external_semantic_authored, got {r['content_status']!r}")
        if r["cohort"] != "phase4":
            fail(f"{key}: cohort must be phase4, got {r['cohort']!r}")
        blob = (r["gloss_zh_short"] or "") + (r["usage_note_zh"] or "") + (r["example_zh"] or "")
        for bad in ("的的", "地地"):
            if bad in blob:
                fail(f"{key}: contains forbidden substring {bad!r}")

    # --- exact GRAPH_SENSES binding ---
    senses = load_runtime()["senses"]
    for r in rows:
        key = r["stable_lexeme_key"]
        lid = str(r["runtime_lexeme_id"])
        groups = senses.get(lid)
        if not groups:
            fail(f"{key}: runtime_lexeme_id {lid} not present in graph-data.js GRAPH_SENSES")
        group = next((g for g in groups if g["entry"] == r["entry_rank"]), None)
        if group is None:
            fail(f"{key}: no entry group with entry=={r['entry_rank']} for lexeme {lid} "
                 f"(available: {[g['entry'] for g in groups]})")
        sense = next((s for s in group["senses"] if s["number"] == r["sense_number"]), None)
        if sense is None:
            fail(f"{key}: no sense numbered {r['sense_number']!r} in entry {r['entry_rank']} for lexeme {lid} "
                 f"(available: {[s['number'] for s in group['senses']]})")

    # --- 8 correction regressions ---
    for key, checks in EXPECTED_CORRECTIONS.items():
        r = by_key.get(key)
        if r is None:
            fail(f"regression check target missing: {key}")
        if "sense_id" in checks and r["sense_id"] != checks["sense_id"]:
            fail(f"{key}: sense_id drifted, expected {checks['sense_id']}, got {r['sense_id']}")
        if "gloss_not_contains" in checks and checks["gloss_not_contains"] in r["gloss_zh_short"]:
            fail(f"{key}: gloss_zh_short regressed to contain {checks['gloss_not_contains']!r}")
        if "example_fr_contains" in checks and checks["example_fr_contains"] not in r["example_fr"]:
            fail(f"{key}: example_fr regressed, missing {checks['example_fr_contains']!r}")
        if "example_fr_not_contains" in checks and checks["example_fr_not_contains"] in r["example_fr"]:
            fail(f"{key}: example_fr regressed to contain {checks['example_fr_not_contains']!r}")
        if "example_zh_equals" in checks and r["example_zh"] != checks["example_zh_equals"]:
            fail(f"{key}: example_zh regressed, expected {checks['example_zh_equals']!r}")
        if "example_zh_not_contains" in checks and checks["example_zh_not_contains"] in r["example_zh"]:
            fail(f"{key}: example_zh regressed to contain {checks['example_zh_not_contains']!r}")

    print(json.dumps({"ok": True, "phase4": 156, "corrections_locked": len(EXPECTED_CORRECTIONS)}))


if __name__ == "__main__":
    main()
