#!/usr/bin/env python3
"""Build reviewable facts for the bounded Phase 2 pilot; never writes learner drafts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path

from build_learner_content import stable_key

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
OUTPUT_PATH = ROOT / "data" / "learner-content-pilot-input.json"

# Fixed identities preserve the reviewed 20-sample scope. No teaching text here.
IDENTITIES = [
    (14232, "être__verb__1", "__ws_1_être__verb__1", "high_frequency_multisense_no_family"), (1157, "avoir__verb__1", "__ws_1_avoir__verb__1", "high_frequency_multisense_no_family"),
    (9976, "pouvoir__verb__1", "__ws_1_pouvoir__verb__1", "high_frequency_multisense_no_family"), (1034, "aujourd’hui__adv__1", "__ws_1_aujourd’hui__adv__1", "high_frequency_multisense_no_family"),
    (2339, "chose__nom__1", "__ws_1_chose__nom__1", "high_frequency_multisense_no_family"), (406, "aller__verb__1", "__ws_1_aller__verb__1", "high_frequency_multisense_with_nonfamily_relation"),
    (5859, "grand__adj__1", "__ws_1_grand__adj__1", "sourced_suffix_form_observable"), (5866, "grandeur__nom__1", "__ws_1_grandeur__nom__1", "sourced_suffix_form_observable"),
    (9495, "petit__adj__1", "__ws_1_petit__adj__1", "sourced_suffix_form_observable"), (9504, "petitesse__nom__1", "__ws_1_petitesse__nom__1", "sourced_suffix_form_observable"),
    (1515, "bon__adj__1", "__ws_1_bon__adj__1", "sourced_suffix_form_observable"), (1533, "bonté__nom__1", "__ws_1_bonté__nom__1", "sourced_suffix_form_observable"),
    (351, "aimer__verb__1", "__ws_1_aimer__verb__1", "sourced_suffix_form_observable"), (348, "aimable__adj__1", "__ws_3_aimable__adj__1", "sourced_suffix_form_observable"),
    (5081, "faire__verb__1", "__ws_1_faire__verb__1", "opaque_sourced_family"), (5163, "façon__nom__1", "__ws_1_façon__nom__1", "opaque_sourced_family"),
    (13641, "voir__verb__1", "__ws_1_voir__verb__1", "opaque_sourced_family"), (13594, "vision__nom__1", "__ws_1_vision__nom__1", "opaque_sourced_family"),
    (6194, "Homme__nom__1", "__ws_1_Homme__nom__1", "opaque_sourced_family"), (6259, "humain__adj__1", "__ws_1_humain__adj__1", "opaque_sourced_family"),
]


def norm(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("’", "'").strip().lower())


def relation_facts(conn: sqlite3.Connection, lexeme_id: int) -> list[dict]:
    rows = conn.execute("""
        SELECT e.subtype,e.direction,e.label,e.review_status,e.dimension,a.lemma,a.pos,b.lemma,b.pos,x.source_id
        FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id
        JOIN lexemes a ON a.id=e.a_id JOIN lexemes b ON b.id=e.b_id
        WHERE e.relation='fam' AND e.dimension='derivational_morphology' AND e.review_status='sourced'
          AND x.source_id='demonette_2' AND (e.a_id=? OR e.b_id=?)
        ORDER BY a.normalized,a.pos,b.normalized,b.pos,e.subtype
    """, (lexeme_id, lexeme_id)).fetchall()
    return [{"stable_relation_key": stable_key(f"{norm(a_lemma)}|{a_pos}", f"{norm(b_lemma)}|{b_pos}", subtype),
             "subtype": subtype, "direction": direction, "label": label,
             "source_boundary": {"source_id": source_id, "review_status": review_status,
                                 "relation": "fam", "dimension": dimension}}
            for subtype, direction, label, review_status, dimension, a_lemma, a_pos, b_lemma, b_pos, source_id in rows]


def build() -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        items = []
        for lexeme_id, entry_id, sense_id, sample_type in IDENTITIES:
            row = conn.execute("""
                SELECT l.lemma,l.normalized,l.pos,l.gloss_zh,s.definition_fr,s.examples_json,s.source_id,le.source_url
                FROM lexemes l JOIN lexeme_senses s ON s.lexeme_id=l.id JOIN lexical_entries le ON le.id=s.entry_id
                WHERE l.id=? AND s.entry_id=? AND s.id=?
            """, (lexeme_id, entry_id, sense_id)).fetchone()
            if not row: raise SystemExit(f"missing pilot sense: {lexeme_id}/{entry_id}/{sense_id}")
            lemma, normalized, pos, hint, definition, examples, source_id, source_url = row
            items.append({"identity": {"stable_lexeme_key": f"{norm(normalized)}|{pos}", "runtime_lexeme_id": lexeme_id,
                                        "entry_id": entry_id, "sense_id": sense_id}, "sample_type": sample_type,
                          "lemma": lemma, "pos": pos, "definition_fr": definition, "sourced_examples": json.loads(examples),
                          "sense_source": {"source_id": source_id, "source_url": source_url},
                          "existing_zh_hint": {"value": hint, "status": "hint_only_not_sense_fact"},
                          "relevant_sourced_relations": relation_facts(conn, lexeme_id)})
    finally:
        conn.close()
    payload = {"schema_version": 2, "scope": "Facts for exactly 20 pilot identities; not learner text or runtime data.", "items": items}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["input_facts_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


if __name__ == "__main__":
    payload = build()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(payload["items"]), "input_facts_sha256": payload["input_facts_sha256"]}))
