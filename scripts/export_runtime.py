#!/usr/bin/env python3
"""Import stable coordinates into SQLite and export the compact browser payload."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from learning_lexicon import learning_lexeme_rows


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
POSITIONS_PATH = ROOT / "data" / "processed" / "layout-positions.json"
RUNTIME_PATH = ROOT / "graph-data.js"
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
CORE_FAMILIES_PATH = ROOT / "data" / "processed" / "core-families-100.json"

SIGNAL_BITS = {
    "semantic": 1,
    "derivation": 2,
    "spelling": 4,
    "phonetic": 8,
    "editorial_seed": 16,
    "skeleton": 32,
    "morphology": 64,
}


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def dedupe_public_relations(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Collapse duplicate/conflicting relations for the same word pair.

    A pair may carry both a vague synonym relation and a richer teaching
    "compare" contrast (e.g. from an older auto-sourced pass alongside a
    newer editorial review); keep only the more informative one. Every row
    passed in must already be review_status == "reviewed" -- this function
    only resolves conflicts between reviewed rows, it does not gate review
    status itself (see has_real_review_evidence in build_graph.py)."""
    by_pair: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_pair[(row["a_id"], row["b_id"])].append(row)
    kept: list[dict[str, object]] = []
    for pair_rows in by_pair.values():
        relations = {row["relation"] for row in pair_rows}
        kept.extend(
            row for row in pair_rows
            if not (row["relation"] in {"syn", "synonym"} and "compare" in relations)
        )
    kept.sort(key=lambda row: (row["a_id"], row["b_id"], row["relation"]))
    return kept


def main() -> None:
    layout = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    positions = {item["id"]: item for item in layout["positions"]}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    all_nodes = conn.execute(
        """
        SELECT id,lemma,pos,cefr_level,gloss_zh,flelex_frequency,
               eligibility_score,has_cfdict,status,editorial_note
        FROM lexemes ORDER BY id
        """
    ).fetchall()
    nodes = [row for row in all_nodes if row["id"] in positions]
    if len(nodes) != len(positions):
        raise SystemExit(f"layout has {len(positions)} positions but only {len(nodes)} lexemes")
    missing = [row["id"] for row in nodes if row["id"] not in positions]
    if missing:
        raise SystemExit(f"missing {len(missing)} layout positions")
    learning_rows = learning_lexeme_rows(conn)
    learning_ids = {row["id"] for row in learning_rows}
    # Search-only terms deliberately remain outside Canvas while retaining the
    # same dictionary and review contract as graph terms.
    search_only_rows = [row for row in learning_rows if row["id"] not in positions]
    runtime_search_lexemes = [
        [row["id"], row["lemma"], row["pos"], row["cefr_level"], row["gloss_zh"] or "",
         round(max(0, row["flelex_frequency"] or 0), 4), row["status"], row["editorial_note"] or ""]
        for row in search_only_rows
    ]
    conn.execute("DELETE FROM positions")
    conn.executemany(
        """
        INSERT INTO positions(
          lexeme_id,x,y,degree,weighted_degree,community,layout_version,created_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        [
            (
                node_id, item["x"], item["y"], item["degree"], item["weightedDegree"],
                item["community"], layout["meta"]["version"], layout["meta"]["created_at"],
            )
            for node_id, item in positions.items()
        ],
    )

    grouped_links: dict[tuple[int, int], list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT a_id,b_id,signal,weight FROM layout_links ORDER BY a_id,b_id,signal"):
        grouped_links[(row["a_id"], row["b_id"])].append(row)
    runtime_links = []
    for (a, b), rows in grouped_links.items():
        mask = 0
        remaining = 1.0
        for row in rows:
            mask |= SIGNAL_BITS[row["signal"]]
            remaining *= 1 - min(0.95, row["weight"])
        runtime_links.append([a, b, mask, round(max(0.01, 1 - remaining), 4)])

    runtime_nodes = []
    for row in nodes:
        pos = positions[row["id"]]
        frequency = max(0, row["flelex_frequency"] or 0)
        visual_size = 1.45 + min(
            3.8,
            math.log1p(pos["weightedDegree"]) * 0.78 + math.log1p(frequency) * 0.16,
        )
        runtime_nodes.append(
            [
                row["id"], row["lemma"], row["pos"], row["cefr_level"],
                row["gloss_zh"] or "", pos["x"], pos["y"], round(visual_size, 3),
                pos["community"], round(frequency, 4), int(row["has_cfdict"]),
                row["status"], row["editorial_note"] or "",
            ]
        )

    # Only relations with genuine human review evidence (see
    # has_real_review_evidence in build_graph.py) are fit to show learners as
    # language fact. Everything else -- auto-sourced DBnary/Démonette edges,
    # the un-reviewed legacy prototype seed -- stays in the database for
    # audit but must never reach the public runtime payload.
    reviewed_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT a_id,b_id,relation,dimension,subtype,direction,label,
                   explanation,examples_json,confidence,review_status,
                   key_sense_a,key_sense_b
            FROM official_edges WHERE review_status='reviewed' ORDER BY id
            """
        )
    ]
    official = [
        [
            row["a_id"], row["b_id"], row["relation"], row["dimension"] or "",
            row["subtype"] or "", row["direction"] or "", row["label"],
            row["explanation"] or "", row["examples_json"], row["confidence"], row["review_status"],
            row["key_sense_a"] or "", row["key_sense_b"] or "",
        ]
        for row in dedupe_public_relations(reviewed_rows)
    ]
    sense_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    sense_rows = conn.execute(
        """
        SELECT le.lexeme_id,le.id AS entry_id,le.entry_rank,le.source_url,
               s.sense_number,s.definition_fr,s.examples_json
        FROM lexical_entries le
        JOIN lexeme_senses s ON s.entry_id=le.id
        ORDER BY le.lexeme_id,le.entry_rank,le.id,
                 CAST(s.sense_number AS INTEGER),s.sense_number
        """
    ).fetchall()
    current_entry: tuple[int, str] | None = None
    current_group: dict[str, object] | None = None
    runtime_lexeme_ids = learning_ids
    for row in sense_rows:
        if row["lexeme_id"] not in runtime_lexeme_ids:
            continue
        entry_key = (row["lexeme_id"], row["entry_id"])
        if entry_key != current_entry:
            current_group = {
                "entry": row["entry_rank"],
                "sourceUrl": row["source_url"],
                "senses": [],
            }
            sense_groups[str(row["lexeme_id"])].append(current_group)
            current_entry = entry_key
        current_group["senses"].append({
            "number": row["sense_number"],
            "definition": row["definition_fr"],
            "examples": json.loads(row["examples_json"]),
        })
    content_status = {
        str(lexeme_id): ("has_definition" if str(lexeme_id) in sense_groups else "pending_definition")
        for lexeme_id in runtime_lexeme_ids
    }
    learning: dict[str, dict[str, object]] = {}
    for row in conn.execute(
        "SELECT lexeme_id,explanation_zh,source_label,reviewer,reviewed_at FROM lexeme_etymologies ORDER BY lexeme_id"
    ):
        if row["lexeme_id"] in positions:
            learning[str(row["lexeme_id"])] = {
                "etymology": {
                    "text": row["explanation_zh"],
                    "source": row["source_label"],
                    "reviewer": row["reviewer"],
                    "reviewedAt": row["reviewed_at"],
                },
                "collocations": [],
            }
    for row in conn.execute(
        "SELECT lexeme_id,expression_fr,gloss_zh FROM lexeme_collocations ORDER BY lexeme_id,id"
    ):
        entry = learning.get(str(row["lexeme_id"]))
        if entry:
            entry["collocations"].append({"expression": row["expression_fr"], "gloss": row["gloss_zh"]})
    aliases: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(
        "SELECT lexeme_id,form FROM aliases ORDER BY lexeme_id,form",
    ):
        if row["lexeme_id"] in runtime_lexeme_ids:
            aliases[str(row["lexeme_id"])].append(row["form"])
    signal_counts = dict(conn.execute("SELECT signal,COUNT(*) FROM layout_links GROUP BY signal").fetchall())
    foundational_core_ids = [
        str(row[0])
        for row in conn.execute(
            "SELECT id FROM lexemes WHERE decision_reason LIKE 'editorial_foundational_core:%' ORDER BY id"
        )
    ]
    teaching_examples: dict[str, list[dict[str, str]]] = {}
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    node_ids_by_key = {(str(row["lemma"]).lower(), str(row["pos"])): str(row["id"]) for row in nodes}
    for item in seed.get("editorialTeachingExamples", []):
        key = (str(item["id"]).replace("’", "'").lower(), str(item["pos"]).upper())
        node_id = node_ids_by_key.get(key)
        if node_id:
            teaching_examples[node_id] = [
                {"text": str(example["text"]), "gloss": str(example["gloss"])}
                for example in item["examples"]
            ]
    meta = {
        **layout["meta"],
        "node_count": len(runtime_nodes),
        "eligible_count": sum(row["status"] == "eligible" for row in nodes),
        "support_node_count": sum(row["status"] != "eligible" for row in nodes),
        "search_lexeme_count": len(runtime_search_lexemes),
        "learning_lexeme_count": len(learning_rows),
        "alias_count": sum(len(values) for values in aliases.values()),
        "layout_link_count": len(runtime_links),
        "official_edge_count": len(official),
        "sense_count": len(sense_rows),
        "sense_lexeme_count": len(sense_groups),
        "editorial_learning_lexeme_count": len(learning),
        "teaching_example_lexeme_count": len(teaching_examples),
        "foundational_core_ids": foundational_core_ids,
        "signal_counts": signal_counts,
        "source_notice": "FLELex/Beacco CC BY-NC-SA 4.0 · Lexique 4 CC BY-SA 4.0 · Démonette 2 CC BY-SA 4.0 · Wiktionnaire/DBnary CC BY-SA · CFDICT CC BY-SA 3.0",
    }
    core_families = json.loads(CORE_FAMILIES_PATH.read_text(encoding="utf-8")) if CORE_FAMILIES_PATH.exists() else {"meta": {}, "families": []}
    payload = (
        "/* Runtime lexical payload. */\n"
        f"const GRAPH_META={compact_json(meta)};\n"
        f"const GRAPH_NODES={compact_json(runtime_nodes)};\n"
        f"const GRAPH_SEARCH_LEXEMES={compact_json(runtime_search_lexemes)};\n"
        f"const GRAPH_LINKS={compact_json(runtime_links)};\n"
        f"const GRAPH_OFFICIAL_EDGES={compact_json(official)};\n"
        f"const GRAPH_SENSES={compact_json(sense_groups)};\n"
        f"const GRAPH_CONTENT_STATUS={compact_json(content_status)};\n"
        f"const GRAPH_ALIASES={compact_json(aliases)};\n"
        f"const GRAPH_LEARNING={compact_json(learning)};\n"
        f"const GRAPH_TEACHING_EXAMPLES={compact_json(teaching_examples)};\n"
        f"const GRAPH_CORE_FAMILIES={compact_json(core_families)};\n"
    )
    RUNTIME_PATH.write_text(payload, encoding="utf-8")
    conn.execute("INSERT OR REPLACE INTO build_metadata VALUES('layout_version',?)", (layout["meta"]["version"],))
    conn.execute("INSERT OR REPLACE INTO build_metadata VALUES('runtime_export','graph-data.js')")
    conn.commit()
    conn.close()
    print(compact_json(meta))


if __name__ == "__main__":
    main()
