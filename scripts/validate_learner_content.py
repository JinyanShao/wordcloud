#!/usr/bin/env python3
"""Validate the deterministic learner projection against runtime and, when present, SQLite facts."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from build_learner_content import DB_PATH, OUTPUT_PATH, build_projection, serialize, stable_key
from runtime_graph import load_runtime


ROOT = Path(__file__).resolve().parents[1]
VALID_TYPES = {"prefix", "suffix", "conversion", "irregular_family"}
VALID_TRANSPARENCY = {"observed_structure", "observed_form_variation", "opaque"}


def load_content() -> dict[str, object]:
    text = OUTPUT_PATH.read_text(encoding="utf-8")
    match = re.search(r"const LEARNER_CONTENT=(.*?);\n?$", text, flags=re.S)
    if not match:
        raise SystemExit("invalid learner-content.js")
    return json.loads(match.group(1))


def identity(word: str, pos: str) -> str:
    normalized = word.replace("’", "'").strip().lower()
    return f"{normalized}|{pos}"


def validate_runtime(payload: dict[str, object]) -> None:
    runtime = load_runtime()
    nodes = {node[0]: node for node in runtime["nodes"]}
    official = {
        stable_key(identity(nodes[edge[0]][1], nodes[edge[0]][2]), identity(nodes[edge[1]][1], nodes[edge[1]][2]), edge[4]): edge
        for edge in runtime["official_edges"]
        if edge[2] == "fam" and edge[3] == "derivational_morphology" and edge[9] == "sourced"
    }
    relations = payload.get("relations", {})
    patterns = payload.get("observed_patterns", {})
    lexeme_ids = payload.get("lexeme_ids", [])
    if len(lexeme_ids) != len(set(lexeme_ids)):
        raise SystemExit("duplicate learner lexeme id")
    observed_by_pattern: dict[str, list[str]] = {}
    for key, relation in relations.items():
        if key not in official:
            raise SystemExit(f"learner relation is not a sourced runtime family edge: {key}")
        edge = official[key]
        if relation["relation_type"] not in VALID_TYPES or relation["transparency"] not in VALID_TRANSPARENCY:
            raise SystemExit(f"invalid teaching classification: {key}")
        if relation["quality_status"] != "source_fact":
            raise SystemExit(f"Phase 1 relation is not source_fact: {key}")
        if relation["a_id"] not in nodes or relation["b_id"] not in nodes:
            raise SystemExit(f"orphan learner endpoint: {key}")
        if relation["a_id"] not in lexeme_ids or relation["b_id"] not in lexeme_ids:
            raise SystemExit(f"learner endpoint missing from lexeme ids: {key}")
        direction = relation["direction"]
        if direction["known"] and {direction["from_id"], direction["to_id"]} != {relation["a_id"], relation["b_id"]}:
            raise SystemExit(f"learner direction does not use relation endpoints: {key}")
        if relation["relation_type"] == "irregular_family" and relation["observed_pattern_key"]:
            raise SystemExit(f"irregular relation entered observed pattern teaching: {key}")
        if relation["observed_pattern_key"]:
            observed_by_pattern.setdefault(relation["observed_pattern_key"], []).append(key)
    for key, pattern in patterns.items():
        if pattern["quality_status"] != "deterministic":
            raise SystemExit(f"Phase 1 pattern is not deterministic: {key}")
        if pattern["teaching_status"] != "deterministic":
            continue
        if pattern["observed_pair_count"] != len(observed_by_pattern.get(key, [])):
            raise SystemExit(f"pattern count does not match sourced observed pairs: {key}")
        for relation_key in pattern["example_relation_keys"]:
            relation = relations.get(relation_key)
            if not relation or relation["observed_pattern_key"] != key or relation["relation_type"] == "irregular_family":
                raise SystemExit(f"invalid observed pattern example: {key}")
    if set(observed_by_pattern) != set(patterns):
        raise SystemExit("orphan observed pattern reference")


def validate_sqlite(payload: dict[str, object]) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        expected = build_projection(conn)
    finally:
        conn.close()
    if serialize(expected) != OUTPUT_PATH.read_text(encoding="utf-8"):
        raise SystemExit("learner-content.js is stale or non-deterministic")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", action="store_true", help="validate against committed static runtime only")
    args = parser.parse_args()
    payload = load_content()
    if payload.get("version") != 1:
        raise SystemExit("unsupported learner projection version")
    validate_runtime(payload)
    if not args.runtime and DB_PATH.exists():
        validate_sqlite(payload)
    print(json.dumps({"ok": True, "lexical_entries": len(payload["lexeme_ids"]), "direct_relations": len(payload["relations"]), "observed_pattern_groups": len(payload["observed_patterns"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
