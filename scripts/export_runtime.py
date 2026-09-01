#!/usr/bin/env python3
"""Import stable coordinates into SQLite and export the compact browser payload."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
POSITIONS_PATH = ROOT / "data" / "processed" / "layout-positions.json"
RUNTIME_PATH = ROOT / "graph-data.js"

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

    official = [
        [
            row["a_id"], row["b_id"], row["relation"], row["dimension"] or "",
            row["subtype"] or "", row["direction"] or "", row["label"],
            row["explanation"] or "", row["confidence"], row["review_status"],
        ]
        for row in conn.execute(
            """
            SELECT a_id,b_id,relation,dimension,subtype,direction,label,
                   explanation,confidence,review_status
            FROM official_edges ORDER BY id
            """
        )
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
    for row in sense_rows:
        if row["lexeme_id"] not in positions:
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
    signal_counts = dict(conn.execute("SELECT signal,COUNT(*) FROM layout_links GROUP BY signal").fetchall())
    meta = {
        **layout["meta"],
        "node_count": len(runtime_nodes),
        "eligible_count": sum(row["status"] == "eligible" for row in nodes),
        "support_node_count": sum(row["status"] != "eligible" for row in nodes),
        "layout_link_count": len(runtime_links),
        "official_edge_count": len(official),
        "sense_count": len(sense_rows),
        "sense_lexeme_count": len(sense_groups),
        "signal_counts": signal_counts,
        "source_notice": "FLELex/Beacco CC BY-NC-SA 4.0 · Lexique 4 CC BY-SA 4.0 · Démonette 2 CC BY-SA 4.0 · Wiktionnaire/DBnary CC BY-SA · CFDICT CC BY-SA 3.0",
    }
    payload = (
        "/* Generated by scripts/export_runtime.py. Do not edit by hand. */\n"
        f"const GRAPH_META={compact_json(meta)};\n"
        f"const GRAPH_NODES={compact_json(runtime_nodes)};\n"
        f"const GRAPH_LINKS={compact_json(runtime_links)};\n"
        f"const GRAPH_OFFICIAL_EDGES={compact_json(official)};\n"
        f"const GRAPH_SENSES={compact_json(sense_groups)};\n"
    )
    RUNTIME_PATH.write_text(payload, encoding="utf-8")
    conn.execute("INSERT OR REPLACE INTO build_metadata VALUES('layout_version',?)", (layout["meta"]["version"],))
    conn.execute("INSERT OR REPLACE INTO build_metadata VALUES('runtime_export','graph-data.js')")
    conn.commit()
    conn.close()
    print(compact_json(meta))


if __name__ == "__main__":
    main()
