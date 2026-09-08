#!/usr/bin/env python3
"""Validate pilot structure and fact references; semantic correctness needs review."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from build_learner_content_pilot import DB_PATH, OUTPUT_PATH, build

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "data" / "learner-content-pilot.json"
STATUSES = {"ai_draft", "reviewed", "blocked"}
EXAMPLE_TYPES = {"sourced", "ai_generated"}


def norm(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("’", "'")).lower()


def tokens(text: str) -> set[str]:
    result = set()
    for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ’']+", norm(text)):
        result.add(token)
        if "'" in token:
            result.add(token.rsplit("'", 1)[1])
        if "’" in token:
            result.add(token.rsplit("’", 1)[1])
    return result


def attested_forms(conn: sqlite3.Connection, lexeme_id: int, lemma: str, pos: str) -> set[str]:
    forms = {norm(lemma)}
    forms.update(row[0] for row in conn.execute("SELECT normalized FROM aliases WHERE lexeme_id=?", (lexeme_id,)))
    forms.update(row[0] for row in conn.execute(
        "SELECT normalized_form FROM lexique_entries WHERE normalized_lemma=? AND pos=?", (norm(lemma), pos)
    ))
    return forms


def validate(draft: dict, facts: dict) -> tuple[list[str], int]:
    errors: list[str] = []
    unknown_forms = 0
    if draft.get("schema_version") != 2 or len(draft.get("items", [])) != 20:
        return ["pilot must have schema version 2 and exactly 20 items"], unknown_forms
    if draft.get("provenance", {}).get("input_facts_sha256") != facts.get("input_facts_sha256"):
        errors.append("draft provenance does not match the reviewable input facts")
    if draft.get("provenance", {}).get("actual_model") != "unknown":
        errors.append("actual model must be unknown unless reliably available")
    fact_by_id = {tuple(x["identity"][key] for key in ("stable_lexeme_key", "entry_id", "sense_id")): x for x in facts["items"]}
    conn = sqlite3.connect(DB_PATH)
    try:
        seen = set()
        for item in draft["items"]:
            identity = item.get("identity", {})
            key = tuple(identity.get(name) for name in ("stable_lexeme_key", "entry_id", "sense_id"))
            if key in seen: errors.append(f"duplicate learner identity {key}")
            seen.add(key)
            fact = fact_by_id.get(key)
            if not fact:
                errors.append(f"orphan learner identity {key}"); continue
            if identity.get("runtime_lexeme_id") != fact["identity"]["runtime_lexeme_id"]:
                errors.append(f"runtime id mismatch {key}")
            status = item.get("content_status")
            if status not in STATUSES: errors.append(f"invalid status {key}")
            rels = set(item.get("relation_stable_keys", []))
            known_rels = {x["stable_relation_key"] for x in fact["relevant_sourced_relations"]}
            if not rels <= known_rels: errors.append(f"unknown sourced relation key {key}")
            if bool(item.get("relation_explanation_zh")) != bool(rels):
                errors.append(f"relation explanation/key mismatch {key}")
            if status == "blocked":
                if any(item.get(field) for field in ("gloss_zh_short", "usage_note_zh", "relation_explanation_zh", "example_fr", "example_zh")):
                    errors.append(f"blocked item contains learner draft {key}")
                continue
            if not item.get("gloss_zh_short") or not item.get("example_fr") or not item.get("example_zh"):
                errors.append(f"draft lacks required learner fields {key}")
            if item.get("example_source_type") not in EXAMPLE_TYPES:
                errors.append(f"invalid example source type {key}")
            if item.get("example_source_type") == "sourced":
                if item["example_fr"] not in fact["sourced_examples"]:
                    errors.append(f"sourced example not present in bound sense {key}")
                source = item.get("example_provenance", {})
                if source.get("source_id") != fact["sense_source"]["source_id"]:
                    errors.append(f"sourced example attribution mismatch {key}")
            forms = attested_forms(conn, identity["runtime_lexeme_id"], fact["lemma"], fact["pos"])
            if not forms:
                unknown_forms += 1
            elif not (tokens(item["example_fr"]) & forms):
                errors.append(f"example lacks an attested target form {key}")
    finally:
        conn.close()
    return errors, unknown_forms


if __name__ == "__main__":
    facts = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    errors, unknown = validate(draft, facts)
    if errors: raise SystemExit("\n".join(errors))
    print(json.dumps({"ok": True, "items": len(draft["items"]), "form_validation_unknown": unknown,
                      "semantic_review": "required"}))
