#!/usr/bin/env python3
"""Validate the bounded learner-content pilot against the SQLite fact source."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from build_learner_content_pilot import DB_PATH, OUTPUT_PATH, build, fact_hash

STATUSES = {"ai_draft", "reviewed", "blocked"}
EXAMPLE_TYPES = {"sourced", "ai_generated"}
REQUIRED = {"model", "generation_version", "input_facts_sha256"}
# Deliberately tiny review list for the 20 pilot examples, not a morphology engine.
ALLOWED_FORMS = {"être": {"est"}, "avoir": {"ai", "j'ai"}, "pouvoir": {"peux"},
                 "aller": {"allons"}, "aimer": {"aime", "j'aime"}, "faire": {"fais"},
                 "voir": {"vois"}, "grand": {"grande"}}


def normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value).lower()


def contains_target(item: dict, lemma: str) -> bool:
    tokens = set(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ’']+", normalized(item["example_fr"])))
    return normalized(lemma) in tokens or bool(tokens & ALLOWED_FORMS.get(normalized(lemma), set()))


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1 or len(payload.get("items", [])) != 20:
        return ["pilot must have schema version 1 and exactly 20 items"]
    if payload != build():
        errors.append("pilot is not the deterministic output of its generator")
    conn = sqlite3.connect(DB_PATH)
    try:
        seen = set()
        for item in payload["items"]:
            key = (item.get("lexeme_id"), item.get("entry_id"), item.get("sense_id"))
            if key in seen: errors.append(f"duplicate item {key}")
            seen.add(key)
            row = conn.execute("SELECT l.lemma FROM lexemes l JOIN lexeme_senses s ON s.lexeme_id=l.id WHERE l.id=? AND s.entry_id=? AND s.id=?", key).fetchone()
            if not row:
                errors.append(f"missing lexeme/sense {key}"); continue
            status = item.get("content_status")
            if status not in STATUSES: errors.append(f"invalid status {key}")
            provenance = item.get("provenance", {})
            if not REQUIRED <= provenance.keys(): errors.append(f"incomplete provenance {key}")
            edge_ids = item.get("relation_edge_ids", [])
            explanation = item.get("relation_explanation_zh")
            if bool(explanation) != bool(edge_ids): errors.append(f"relation explanation/edge mismatch {key}")
            for edge_id in edge_ids:
                edge = conn.execute("""SELECT 1 FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id AND x.source_id='demonette_2'
                    WHERE e.id=? AND e.relation='fam' AND e.dimension='derivational_morphology' AND e.review_status='sourced'
                      AND (e.a_id=? OR e.b_id=?)""", (edge_id, key[0], key[0])).fetchone()
                if not edge: errors.append(f"unsourced or unrelated relation edge {edge_id} for {key}")
            if provenance.get("input_facts_sha256") != fact_hash(conn, key[0], key[1], key[2], edge_ids): errors.append(f"fact hash mismatch {key}")
            if status == "blocked":
                if any(item.get(field) for field in ("gloss_zh_short", "usage_note_zh", "relation_explanation_zh", "example_fr", "example_zh")):
                    errors.append(f"blocked item contains learner content {key}")
            else:
                if not item.get("gloss_zh_short") or not item.get("example_fr") or not item.get("example_zh"):
                    errors.append(f"draft lacks required learner fields {key}")
                if item.get("example_source_type") not in EXAMPLE_TYPES: errors.append(f"invalid example source {key}")
                if not contains_target(item, row[0]): errors.append(f"example misses lemma or approved form {key}")
    finally:
        conn.close()
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    errors = validate(payload)
    if errors: raise SystemExit("\n".join(errors))
    print(json.dumps({"ok": True, "items": len(payload["items"]), "blocked": sum(x["content_status"] == "blocked" for x in payload["items"])}))
