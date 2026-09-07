#!/usr/bin/env python3
"""Build deterministic learner-facing structure from sourced family facts only."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
OUTPUT_PATH = ROOT / "learner-content.js"
OVERRIDES_PATH = ROOT / "data" / "learner-content-overrides.json"
STATUS_VALUES = ("source_fact", "deterministic", "ai_draft", "reviewed", "blocked")


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("’", "'").strip().lower())


def identity(row: dict[str, object]) -> str:
    return f"{normalize(str(row['lemma']))}|{row['pos']}"


def stable_key(left: str, right: str, subtype: str) -> str:
    a, b = sorted((left, right))
    return f"fam|derivational_morphology|{subtype}|{a}|{b}"


def classify(subtype: str, record: dict[str, object], direction_known: bool) -> tuple[str, str, bool]:
    if subtype == "semantic_derivation":
        return "irregular_family", "opaque", False
    if subtype == "conversion":
        return "conversion", "observed_form_variation", False
    if subtype in {"prefixation", "suffixation"} and record.get("complexity") == "simple" and record.get("orientation") == "as2des" and direction_known:
        return ("prefix" if subtype == "prefixation" else "suffix"), "observed_structure", True
    return "irregular_family", "opaque", False


def pattern_key(relation_type: str, record: dict[str, object], from_pos: str, to_pos: str) -> str:
    scheme = f"{record.get('scheme_1', '')}>{record.get('scheme_2', '')}"
    return f"{relation_type}|{scheme}|{from_pos}>{to_pos}"


def load_overrides() -> dict[str, object]:
    payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("relations"), dict) or not isinstance(payload.get("patterns"), dict):
        raise SystemExit("invalid learner-content overrides format")
    return payload


def build_projection(conn: sqlite3.Connection) -> dict[str, object]:
    conn.row_factory = sqlite3.Row
    overrides = load_overrides()
    rows = conn.execute(
        """
        SELECT e.id,e.a_id,e.b_id,e.subtype,e.direction,e.review_status,
               a.lemma AS a_lemma,a.pos AS a_pos,b.lemma AS b_lemma,b.pos AS b_pos,
               s.source_id,s.source_record
        FROM official_edges e
        JOIN official_edge_sources s ON s.edge_id=e.id
        JOIN lexemes a ON a.id=e.a_id
        JOIN lexemes b ON b.id=e.b_id
        WHERE e.relation='fam'
          AND e.dimension='derivational_morphology'
          AND e.review_status='sourced'
          AND s.source_id='demonette_2'
        ORDER BY a.normalized,a.pos,b.normalized,b.pos,e.subtype,e.id
        """
    ).fetchall()
    relations: dict[str, dict[str, object]] = {}
    lexeme_ids: set[int] = set()
    patterns: dict[str, list[str]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        left = identity({"lemma": row["a_lemma"], "pos": row["a_pos"]})
        right = identity({"lemma": row["b_lemma"], "pos": row["b_pos"]})
        key = stable_key(left, right, str(row["subtype"]))
        record = json.loads(row["source_record"] or "{}")
        direction = str(row["direction"] or "")
        ids = direction.split("->") if direction else []
        direction_known = len(ids) == 2 and set(ids) == {str(row["a_id"]), str(row["b_id"])}
        relation_type, transparency, observed = classify(str(row["subtype"]), record, direction_known)
        from_id, to_id = (int(ids[0]), int(ids[1])) if direction_known else (None, None)
        from_pos = row["a_pos"] if from_id == row["a_id"] else row["b_pos"] if from_id == row["b_id"] else ""
        to_pos = row["a_pos"] if to_id == row["a_id"] else row["b_pos"] if to_id == row["b_id"] else ""
        observed_key = pattern_key(relation_type, record, from_pos, to_pos) if observed else None
        override = overrides["relations"].get(key, {})
        teaching_status = override.get("teaching_status", "deterministic")
        if teaching_status not in STATUS_VALUES:
            raise SystemExit(f"invalid relation teaching status: {key}")
        if teaching_status not in {"deterministic", "blocked"}:
            raise SystemExit(f"Phase 1 relation override may only be deterministic or blocked: {key}")
        relation = {
            "stable_key": key,
            "quality_status": "source_fact",
            "teaching_status": teaching_status,
            "a_id": row["a_id"], "b_id": row["b_id"],
            "relation_type": relation_type,
            "transparency": transparency,
            "direction": {"known": direction_known, "from_id": from_id, "to_id": to_id},
            "from_pos": from_pos or None, "to_pos": to_pos or None,
            "observed_pattern_key": observed_key,
        }
        if override.get("teaching_note"):
            relation["teaching_note"] = str(override["teaching_note"])
        relations[key] = relation
        lexeme_ids.update((int(row["a_id"]), int(row["b_id"])))
        if observed_key and teaching_status == "deterministic":
            patterns[observed_key].append(key)
    observed_patterns = {}
    for key, relation_keys in sorted(patterns.items()):
        relation = relations[relation_keys[0]]
        override = overrides["patterns"].get(key, {})
        status = override.get("teaching_status", "deterministic")
        if status not in {"deterministic", "blocked"}:
            raise SystemExit(f"Phase 1 pattern override may only be deterministic or blocked: {key}")
        observed_patterns[key] = {
            "pattern_key": key,
            "quality_status": "deterministic",
            "teaching_status": status,
            "relation_type": relation["relation_type"],
            "from_pos": relation["from_pos"], "to_pos": relation["to_pos"],
            "observed_pair_count": len(relation_keys),
            "example_relation_keys": relation_keys[:5],
        }
    return {
        "version": 1,
        "quality_statuses": list(STATUS_VALUES),
        "scope": "Observed structure from direct sourced Démonette family edges; not a productive-rule claim.",
        "lexeme_ids": sorted(lexeme_ids),
        "relations": dict(sorted(relations.items())),
        "observed_patterns": observed_patterns,
    }


def serialize(payload: dict[str, object]) -> str:
    return "/* Generated by scripts/build_learner_content.py. Do not edit by hand. */\n" + f"const LEARNER_CONTENT={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))};\n"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("missing SQLite fact source; run the data build first")
    conn = sqlite3.connect(DB_PATH)
    try:
        payload = build_projection(conn)
    finally:
        conn.close()
    OUTPUT_PATH.write_text(serialize(payload), encoding="utf-8")
    print(json.dumps({"lexical_entries": len(payload["lexeme_ids"]), "direct_relations": len(payload["relations"]), "observed_pattern_groups": len(payload["observed_patterns"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
