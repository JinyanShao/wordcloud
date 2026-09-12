#!/usr/bin/env python3
"""Prepare a bounded, source-ready Phase 4B semantic-review set; do not select senses."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "data/processed/eligible-lexicon.csv"
RUNTIME = ROOT / "learner-sense-content.js"
DBNARY = ROOT / "data/processed/dbnary-approved.json"
GRAPH = ROOT / "graph-data.js"
AUDIT = ROOT / "data/phase4/product-gap-audit.json"
JSONL = ROOT / "data/phase4/learner-candidate-160-review.jsonl"
MANIFEST = ROOT / "data/phase4/learner-candidate-160-manifest.json"
SOURCE_GAPS = ROOT / "data/phase4/source-gap-high-value.json"

LEVELS = ("A1", "A2", "B1", "B2")
QUOTAS = {"A1": 50, "A2": 35, "B1": 50, "B2": 25}
BLOCKED = {"travers|NOM", "cesse|NOM"}
NOUN_MAX = 96
MARKERS = ("vieilli", "désuet", "archaïque", "botanique", "zoologie", "religion", "technique", "médicine", "médecine", "droit", "militaire", "marine", "linguistique", "chimie", "physique")


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_value(value: object) -> str:
    return digest_bytes(canonical(value).encode("utf-8"))


def graph_constant(name: str) -> object:
    raw = GRAPH.read_text(encoding="utf-8")
    prefix = f"const {name}="
    start = raw.index(prefix) + len(prefix)
    try:
        end = raw.index(";\nconst ", start)
    except ValueError:
        end = raw.rindex(";")
    return json.loads(raw[start:end])


def runtime_aids() -> set[int]:
    raw = RUNTIME.read_text(encoding="utf-8")
    match = re.search(r"const LEARNER_SENSE_CONTENT=(.*);\n$", raw, re.S)
    if not match:
        raise SystemExit("missing learner runtime payload")
    payload = json.loads(match.group(1))
    rows = payload["records"]
    if len(rows) != 598 or sum(item["cohort"] == "phase2c" for item in rows) != 99 or sum(item["cohort"] == "phase3" for item in rows) != 499:
        raise SystemExit("unexpected production learner runtime")
    return {int(item["lexeme_id"]) for item in rows}


def priority(row: dict[str, str]) -> tuple[float, float, float, str, str]:
    return (-float(row["flelex_frequency"] or 0), -float(row["lexique_frequency"] or 0), -float(row["contextual_diversity"] or 0), row["lemma"], row["pos"])


def source_data() -> tuple[dict[int, list[dict[str, object]]], dict[int, int]]:
    approved = json.loads(DBNARY.read_text(encoding="utf-8"))
    ranks = {entry["id"]: entry["entry_rank"] for entry in approved["entries"]}
    senses: dict[int, list[dict[str, object]]] = defaultdict(list)
    for sense in approved["senses"]:
        senses[int(sense["lexeme_id"])].append({
            "entry_id": sense["entry_id"],
            "entry_rank": ranks[sense["entry_id"]],
            "sense_id": sense["id"],
            "sense_number": sense["sense_number"],
            "definition_fr": sense["definition_fr"],
        })
    for rows in senses.values():
        rows.sort(key=lambda item: (int(item["entry_rank"]), 0, int(item["sense_number"]), item["sense_id"]) if str(item["sense_number"]).isdigit() else (int(item["entry_rank"]), 1, str(item["sense_number"]), item["sense_id"]))
    return senses, ranks


def family_ids() -> set[int]:
    edges = graph_constant("GRAPH_OFFICIAL_EDGES")
    return {
        int(endpoint) for edge in edges
        if edge[2] == "fam" and edge[3] == "derivational_morphology" and edge[9] == "sourced"
        for endpoint in edge[:2]
    }


def review_flags(senses: list[dict[str, object]], other_pos: list[dict[str, object]]) -> list[str]:
    flags = []
    if other_pos:
        flags.append("same_lemma_multiple_pos")
    if len(senses) >= 20:
        flags.append("very_polysemous")
    elif len(senses) >= 10:
        flags.append("many_source_senses")
    if len(senses) == 1:
        flags.append("single_source_sense")
    labels = [label.casefold() for sense in senses for label in re.findall(r"\(([^)]*)\)", str(sense["definition_fr"]))]
    if any(marker in label for label in labels for marker in MARKERS):
        flags.append("marked_or_specialized_sense_present")
    return flags


def compact_record(row: dict[str, str], senses: list[dict[str, object]], family: set[int], lemma_rows: dict[str, list[dict[str, str]]]) -> dict[str, object]:
    ident = int(row["id"])
    key = f"{row['lemma']}|{row['pos']}"
    other_pos = [
        {"stable_lexeme_key": f"{other['lemma']}|{other['pos']}", "pos": other["pos"], "runtime_lexeme_id": int(other["id"]), "cefr": other["cefr_level"]}
        for other in lemma_rows[row["lemma"]]
        if int(other["id"]) != ident
    ]
    other_pos.sort(key=lambda item: (item["pos"], item["runtime_lexeme_id"]))
    return {
        "key": key,
        "lemma": row["lemma"],
        "pos": row["pos"],
        "cefr": row["cefr_level"],
        "runtime_lexeme_id": ident,
        "flelex_frequency": float(row["flelex_frequency"] or 0),
        "lexique_frequency": float(row["lexique_frequency"] or 0),
        "contextual_diversity": float(row["contextual_diversity"] or 0),
        "has_sourced_family": ident in family,
        "entry_count": len({sense["entry_id"] for sense in senses}),
        "source_sense_count": len(senses),
        "same_lemma_other_pos": other_pos,
        "review_flags": review_flags(senses, other_pos),
        "source_senses": senses,
    }


def select(rows_by_level: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    selected = {level: rows_by_level[level][:QUOTAS[level]] for level in LEVELS}
    shortages = {level: QUOTAS[level] - len(selected[level]) for level in LEVELS if len(selected[level]) < QUOTAS[level]}
    if shortages:
        # The documented fallback only matters if future production inputs shrink.
        for level in ("A1", "B1", "A2", "B2"):
            available = rows_by_level[level][len(selected[level]):]
            while available and shortages:
                target = next(iter(shortages))
                selected[level].append(available.pop(0))
                shortages[target] -= 1
                if shortages[target] == 0:
                    del shortages[target]
    if sum(map(len, selected.values())) != 160:
        raise SystemExit("cannot fill 160 candidate quota")

    # Enforce only the stated global NOM maximum. Replacement stays in the same
    # CEFR stratum and chooses the next frequency-ranked non-NOM candidate.
    noun_count = sum(row["pos"] == "NOM" for rows in selected.values() for row in rows)
    if noun_count > NOUN_MAX:
        caps = {level: int(QUOTAS[level] * 0.60) for level in LEVELS}
        for level in LEVELS:
            while sum(row["pos"] == "NOM" for row in selected[level]) > caps[level]:
                replace_index = max(index for index, row in enumerate(selected[level]) if row["pos"] == "NOM")
                used_ids = {row["id"] for row in selected[level]}
                replacement = next((row for row in rows_by_level[level] if row["id"] not in used_ids and row["pos"] != "NOM"), None)
                if replacement is None:
                    raise SystemExit(f"cannot meet NOM maximum in {level}")
                selected[level][replace_index] = replacement
    result = [row for level in LEVELS for row in sorted(selected[level], key=priority)]
    if sum(row["pos"] == "NOM" for row in result) > NOUN_MAX:
        raise SystemExit("NOM maximum not met")
    return result


def build() -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    with LEXICON.open(encoding="utf-8", newline="") as source:
        lexicon = list(csv.DictReader(source))
    aids = runtime_aids()
    senses, _ = source_data()
    family = family_ids()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit["coverage"]["overall"]["learner_aids"] != 598:
        raise SystemExit("Phase 4A production baseline changed")
    lemma_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in lexicon:
        lemma_rows[row["lemma"]].append(row)
    raw = [row for row in lexicon if row["cefr_level"] in LEVELS and int(row["id"]) not in aids]
    blocked = [row for row in raw if f"{row['lemma']}|{row['pos']}" in BLOCKED]
    no_sense = [row for row in raw if not senses.get(int(row["id"]))]
    source_ready = [row for row in raw if senses.get(int(row["id"])) and f"{row['lemma']}|{row['pos']}" not in BLOCKED]
    by_level = {level: sorted([row for row in source_ready if row["cefr_level"] == level], key=priority) for level in LEVELS}
    selected = select(by_level)
    records = [compact_record(row, senses[int(row["id"])], family, lemma_rows) for row in selected]
    if len(records) != 160 or len({record["key"] for record in records}) != 160 or len({record["runtime_lexeme_id"] for record in records}) != 160:
        raise SystemExit("candidate identity failure")
    selected_keys = {record["key"] for record in records}
    if selected_keys & BLOCKED:
        raise SystemExit("blocked candidate leak")
    no_sense.sort(key=lambda row: (LEVELS.index(row["cefr_level"]),) + priority(row))
    blocked.sort(key=lambda row: (LEVELS.index(row["cefr_level"]),) + priority(row))
    source_gaps = {
        "schema_version": 1,
        "scope": "Missing high-value entries excluded from exact-sense semantic review; not learner content.",
        "no_source_sense": [{**compact_record(row, [], family, lemma_rows), "reason": "no_source_sense"} for row in no_sense],
        "blocked": [{**compact_record(row, senses.get(int(row["id"]), []), family, lemma_rows), "reason": "blocked"} for row in blocked],
    }
    manifest = {
        "schema_version": 1,
        "scope": "Phase 4B compact French-sense review candidates; no primary sense is proposed.",
        "total": len(records),
        "cefr_distribution": dict(Counter(record["cefr"] for record in records)),
        "pos_distribution": dict(Counter(record["pos"] for record in records)),
        "family_member_count": sum(record["has_sourced_family"] for record in records),
        "review_flag_counts": dict(Counter(flag for record in records for flag in record["review_flags"])),
        "source_ready_filtering": {
            "raw_missing_by_cefr": dict(Counter(row["cefr_level"] for row in raw)),
            "source_ready_by_cefr": dict(Counter(row["cefr_level"] for row in source_ready)),
            "selected_by_cefr": dict(Counter(record["cefr"] for record in records)),
            "no_source_sense": len(no_sense),
            "blocked": len(blocked),
        },
        "blocked_exclusions": sorted(BLOCKED),
        "selection_policy": "Stratified CEFR quotas A1=50, A2=35, B1=50, B2=25; within each CEFR sort by FLELex desc, Lexique desc, contextual diversity desc, stable key. Enforce NOM <= 96 by same-CEFR frequency-ranked non-NOM replacement. Sourced family membership is metadata only.",
        "input_hashes": {path.name: digest_bytes(path.read_bytes()) for path in (LEXICON, RUNTIME, DBNARY, GRAPH, AUDIT)},
    }
    return records, manifest, source_gaps


def serialize_jsonl(records: list[dict[str, object]]) -> str:
    return "".join(canonical(record) + "\n" for record in records)


def write() -> None:
    records, manifest, source_gaps = build()
    raw_jsonl = serialize_jsonl(records)
    manifest["jsonl_sha256"] = digest_bytes(raw_jsonl.encode("utf-8"))
    manifest["candidate_union_hash"] = digest_value(records)
    source_gaps["artifact_hash"] = digest_value(source_gaps)
    JSONL.write_text(raw_jsonl, encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SOURCE_GAPS.write_text(json.dumps(source_gaps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "candidates": len(records), "source_gaps": len(source_gaps["no_source_sense"]), "blocked": len(source_gaps["blocked"])}, ensure_ascii=False))


if __name__ == "__main__":
    write()
