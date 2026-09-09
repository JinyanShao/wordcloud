#!/usr/bin/env python3
"""Structural validation for Phase 2C reviewer packets; no semantic claims."""
from __future__ import annotations

import json
from pathlib import Path

from build_learner_content_100_review_input import CANDIDATES, DATED, OUT, REVIEW_DIR, build, compact_packet, digest


def main() -> None:
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    rebuilt = build()  # SQLite + processed candidate artifact only; never raw DBnary.
    if payload != rebuilt:
        raise SystemExit("main artifact is not deterministic from SQLite and candidate artifact")
    if payload.get("artifact_hash") != digest({k: v for k, v in payload.items() if k != "artifact_hash"}):
        raise SystemExit("main artifact hash mismatch")
    items = payload.get("items", [])
    if len(items) != 100 or len({x["runtime_lexeme_id"] for x in items}) != 100:
        raise SystemExit("must contain exactly 100 distinct lexemes")
    source_candidates = {
        x["translation_stable_ref"]: x
        for x in json.loads(CANDIDATES.read_text(encoding="utf-8"))["items"]
    }
    joined = []
    for index in range(1, 5):
        packet = json.loads((REVIEW_DIR / f"learner-content-100-part-{index:02}.json").read_text(encoding="utf-8"))
        if packet.get("part") != index or packet.get("parent_artifact_hash") != payload["artifact_hash"] or len(packet.get("items", [])) != 25:
            raise SystemExit(f"invalid review packet {index}")
        if packet.get("artifact_hash") != digest({k: v for k, v in packet.items() if k != "artifact_hash"}):
            raise SystemExit(f"packet hash mismatch {index}")
        joined.extend(packet["items"])
    if joined != items:
        raise SystemExit("review packets do not exactly reconstruct main artifact")
    for index in range(1, 5):
        path = REVIEW_DIR / "compact" / f"learner-content-100-compact-part-{index:02}.json"
        compact = json.loads(path.read_text(encoding="utf-8"))
        if compact != compact_packet(payload, index):
            raise SystemExit(f"compact packet is not an exact deterministic projection: {index}")
    mismatched_structural = 0
    antenna = None
    for item in items:
        selected = item["proposed_primary_learner_sense"]
        senses = {(s["entry_id"], s["sense_id"]) for s in item["all_source_senses"]}
        if (selected["entry_id"], selected["sense_id"]) not in senses:
            raise SystemExit(f"orphan proposed sense: {item['stable_lexeme_key']}")
        if item["selection_status"] != "needs_semantic_review":
            raise SystemExit("mechanical proposals must retain semantic-review status")
        selected_definition = next(
            s["definition_fr"] for s in item["all_source_senses"] if s["sense_id"] == selected["sense_id"]
        ).lower()
        has_plain_alternative = any(
            not any(marker in s["definition_fr"].lower() for marker in DATED)
            for s in item["all_source_senses"]
        )
        if has_plain_alternative and any(marker in selected_definition for marker in DATED):
            raise SystemExit(f"dated sense selected despite a plain alternative: {item['stable_lexeme_key']}")
        if item["stable_lexeme_key"] == "antenne|NOM":
            antenna = item
        for candidate in item["selected_sense_chinese_candidates"]:
            raw = source_candidates.get(candidate["candidate_stable_ref"])
            if not raw or raw["entry_id"] != selected["entry_id"]:
                raise SystemExit(f"invalid candidate reference: {item['stable_lexeme_key']}")
            if candidate["automatic_learner_gloss_approval"] is not False:
                raise SystemExit("candidate mapping must not auto-approve learner gloss")
            if candidate["candidate_class"] == "sense_mapped_candidate" and candidate["semantic_status"] != "requires_semantic_review":
                raise SystemExit("structural mapping must require semantic review")
            if candidate["candidate_class"] == "sense_mapped_candidate" and not candidate["structural_match_for_selected_sense"]:
                mismatched_structural += 1
    if not antenna or not any(
        c["candidate_class"] == "sense_mapped_candidate" and not c["structural_match_for_selected_sense"]
        for c in antenna["selected_sense_chinese_candidates"]
    ):
        raise SystemExit("antenne structural-mismatch regression fixture missing")
    if mismatched_structural < 3:
        raise SystemExit("insufficient structural-mismatch stress records")
    print(json.dumps({"ok": True, "items": 100, "packets": 4, "semantic_review": "required"}))


if __name__ == "__main__":
    main()
