#!/usr/bin/env python3
"""Build Phase 2C's 100-record reviewer input without learner content.

Ordering is intentional and enforced in code: learner-relevant lexemes are
selected from SQLite, a conservative learner-priority sense is proposed using
only source-sense metadata, then DBnary candidates are joined.  Candidates
never participate in lexeme or sense selection and are never approved here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from build_learner_content import stable_key
from learner_candidate_policy import candidate_context_for_selected_sense

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
CANDIDATES = ROOT / "data" / "processed" / "dbnary-zh-translation-candidates.json"
OUT = ROOT / "data" / "learner-content-100-review-input.json"
REVIEW_DIR = ROOT / "data" / "review"
DEFAULT = "default_learner_chinese"

# Fixed curriculum strata: 50 A1, 30 A2, 15 B1, 5 B2; 33 verbs, 28 nouns,
# 25 adjectives and 14 adverbs.  The sole explicit stress lexeme is selected
# by its known dated-sense regression, not by translation availability.
QUOTAS = {
    "A1": {"VER": 17, "NOM": 14, "ADJ": 12, "ADV": 7},
    "A2": {"VER": 10, "NOM": 8, "ADJ": 8, "ADV": 4},
    "B1": {"VER": 5, "NOM": 4, "ADJ": 4, "ADV": 2},
    "B2": {"VER": 1, "NOM": 2, "ADJ": 1, "ADV": 1},
}
STRESS_KEYS = {"antenne|NOM"}
DATED = ("vieilli", "désuet", "desuet", "archaïque", "archaique", "ancien")
SPECIALIZED = (
    "marine", "botanique", "zoologie", "entomologie", "chimie", "physique",
    "médecine", "medecine", "droit", "linguistique", "technique", "histoire",
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def norm(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("’", "'").strip().lower())


def sense_penalty(definition: str) -> tuple[int, list[str]]:
    lower = definition.lower()
    reasons: list[str] = []
    score = 0
    if any(term in lower for term in DATED):
        score += 100
        reasons.append("dated_or_historical_marker")
    if any(term in lower for term in SPECIALIZED):
        score += 15
        reasons.append("specialized_domain_marker")
    return score, reasons


def source_senses(conn: sqlite3.Connection, lexeme_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """SELECT s.entry_id,s.id,s.sense_number,s.definition_fr,s.examples_json,s.source_id
           FROM lexeme_senses s JOIN lexical_entries le ON le.id=s.entry_id
           WHERE s.lexeme_id=?
           ORDER BY le.entry_rank,s.entry_id,CAST(s.sense_number AS REAL),s.sense_number,s.id""",
        (lexeme_id,),
    ).fetchall()
    return [
        {
            "entry_id": entry,
            "sense_id": sid,
            "sense_number": number,
            "source_order": index + 1,
            "definition_fr": definition,
            "sourced_examples": json.loads(examples)[:2],
            "source_id": source_id,
        }
        for index, (entry, sid, number, definition, examples, source_id) in enumerate(rows)
    ]


def propose_primary_sense(senses: list[dict[str, object]]) -> tuple[dict[str, object], str, str]:
    """Make a deliberately review-required proposal from source data only."""
    ranked = []
    for sense in senses:
        penalty, flags = sense_penalty(str(sense["definition_fr"]))
        ranked.append((penalty, int(sense["source_order"]), sense, flags))
    _, _, selected, flags = min(ranked, key=lambda row: (row[0], row[1]))
    reason = "candidate-independent lowest policy penalty; source-order tiebreaker"
    if flags:
        reason += f"; selected sense still has {', '.join(flags)}"
    return selected, reason, "mechanical proposal; frequency and semantic fitness require external review"


def sourced_relations(conn: sqlite3.Connection, lexeme_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """SELECT e.subtype,e.direction,e.label,e.review_status,e.dimension,
                  a.normalized,a.pos,b.normalized,b.pos,x.source_id
           FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id
           JOIN lexemes a ON a.id=e.a_id JOIN lexemes b ON b.id=e.b_id
           WHERE e.relation='fam' AND e.dimension='derivational_morphology'
             AND e.review_status='sourced' AND x.source_id='demonette_2'
             AND (e.a_id=? OR e.b_id=?)
           ORDER BY a.normalized,a.pos,b.normalized,b.pos,e.subtype""",
        (lexeme_id, lexeme_id),
    ).fetchall()
    return [
        {
            "stable_relation_key": stable_key(f"{norm(a)}|{a_pos}", f"{norm(b)}|{b_pos}", subtype),
            "subtype": subtype,
            "direction": direction,
            "label": label,
            "source_boundary": {
                "source_id": source_id,
                "review_status": review_status,
                "relation": "fam",
                "dimension": dimension,
            },
        }
        for subtype, direction, label, review_status, dimension, a, a_pos, b, b_pos, source_id in rows
    ]


def select_lexemes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Select the fixed curriculum strata before the candidate file is read."""
    selected: list[sqlite3.Row] = []
    selected_ids: set[int] = set()
    for level, pos_quotas in QUOTAS.items():
        for pos, quota in pos_quotas.items():
            rows = conn.execute(
                """SELECT id,lemma,normalized,pos,cefr_level,flelex_frequency,lexique_frequency,
                          contextual_diversity
                   FROM lexemes WHERE status='eligible' AND cefr_level=? AND pos=?
                     AND EXISTS (SELECT 1 FROM lexeme_senses s WHERE s.lexeme_id=lexemes.id)
                   ORDER BY COALESCE(flelex_frequency,0) DESC,COALESCE(lexique_frequency,0) DESC,id""",
                (level, pos),
            ).fetchall()
            picked = [row for row in rows if row["id"] not in selected_ids][:quota]
            if len(picked) != quota:
                raise SystemExit(f"insufficient eligible lexemes for {level}/{pos}")
            selected.extend(picked)
            selected_ids.update(row["id"] for row in picked)

    # Preserve the antenna regression in the B2/NOM stress slice by replacing
    # its lowest-frequency non-forced peer; no candidate data is consulted.
    antenna = conn.execute(
        """SELECT id,lemma,normalized,pos,cefr_level,flelex_frequency,lexique_frequency,
                  contextual_diversity FROM lexemes WHERE normalized='antenne' AND pos='NOM'"""
    ).fetchone()
    if antenna and antenna["id"] not in selected_ids:
        replacement = min(
            (row for row in selected if row["cefr_level"] == "B2" and row["pos"] == "NOM"),
            key=lambda row: (row["flelex_frequency"] or 0, row["id"]),
        )
        selected.remove(replacement)
        selected.append(antenna)
    return sorted(selected, key=lambda row: ("A1 A2 B1 B2".split().index(row["cefr_level"]), row["pos"], -(row["flelex_frequency"] or 0), row["id"]))


def proposals_from_sqlite() -> list[dict[str, object]]:
    """The candidate-independent first phase of the pipeline."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        items = []
        for lexeme in select_lexemes(conn):
            senses = source_senses(conn, lexeme["id"])
            if not senses:
                raise SystemExit(f"selected lexeme has no senses: {lexeme['id']}")
            proposed, reason, uncertainty = propose_primary_sense(senses)
            items.append(
                {
                    "stable_lexeme_key": f"{norm(lexeme['normalized'])}|{lexeme['pos']}",
                    "runtime_lexeme_id": lexeme["id"],
                    "lemma": lexeme["lemma"],
                    "pos": lexeme["pos"],
                    "cefr": lexeme["cefr_level"],
                    "frequency_signals": {
                        "flelex_frequency": lexeme["flelex_frequency"],
                        "lexique_frequency": lexeme["lexique_frequency"],
                        "contextual_diversity": lexeme["contextual_diversity"],
                    },
                    "all_source_senses": senses,
                    "proposed_primary_learner_sense": {
                        "entry_id": proposed["entry_id"],
                        "sense_id": proposed["sense_id"],
                    },
                    "selection_status": "needs_semantic_review",
                    "selection_reason": reason,
                    "uncertainty": uncertainty,
                    "relevant_sourced_family_relations": sourced_relations(conn, lexeme["id"]),
                }
            )
        return items
    finally:
        conn.close()


def join_candidates(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Second phase: attach context; never alter selected senses."""
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["items"]
    by_entry: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        if candidate.get("entry_id"):
            by_entry[str(candidate["entry_id"])].append(candidate)
    for item in items:
        selected = item["proposed_primary_learner_sense"]
        entry_id = selected["entry_id"]
        selected_sense_id = str(selected["sense_id"])
        context = []
        for candidate in sorted(by_entry.get(str(entry_id), []), key=lambda c: str(c["translation_stable_ref"])):
            context.append(
                {
                    "candidate_stable_ref": candidate["translation_stable_ref"],
                    "candidate_class": candidate["candidate_class"],
                    "chinese_written_form": candidate["chinese_written_form"],
                    "target_language_code": candidate["target_language_code"],
                    "learner_language_eligibility": candidate["learner_language_eligibility"],
                    "translation_gloss": candidate["translation_gloss"],
                    "mapped_sense_id": candidate["mapped_sense_id"],
                    **candidate_context_for_selected_sense(selected_sense_id, candidate),
                }
            )
        item["selected_sense_chinese_candidates"] = context
        default = [c for c in context if c["learner_language_eligibility"] == DEFAULT]
        mapped = [c for c in default if c["structural_match_for_selected_sense"]]
        if mapped:
            item["candidate_review_bucket"] = "source_friendly"
        elif default:
            item["candidate_review_bucket"] = "ambiguous"
        else:
            item["candidate_review_bucket"] = "no_candidate"
        item["input_hash"] = digest(item)
    return items


def build() -> dict[str, object]:
    items = join_candidates(proposals_from_sqlite())
    payload = {
        "schema_version": 1,
        "scope": "Phase 2C reviewer facts and candidate context only; no learner gloss, example, or semantic approval.",
        "items": items,
    }
    payload["artifact_hash"] = digest(payload)
    return payload


def packet(payload: dict[str, object], index: int) -> dict[str, object]:
    start = (index - 1) * 25
    body = {"schema_version": 1, "part": index, "parent_artifact_hash": payload["artifact_hash"], "items": payload["items"][start:start + 25]}
    body["artifact_hash"] = digest(body)
    return body


def write() -> dict[str, object]:
    payload = build()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for index in range(1, 5):
        (REVIEW_DIR / f"learner-content-100-part-{index:02}.json").write_text(json.dumps(packet(payload, index), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = write()
    print(json.dumps({"items": len(result["items"]), "cefr": Counter(x["cefr"] for x in result["items"]), "pos": Counter(x["pos"] for x in result["items"]), "buckets": Counter(x["candidate_review_bucket"] for x in result["items"])}, ensure_ascii=False))
