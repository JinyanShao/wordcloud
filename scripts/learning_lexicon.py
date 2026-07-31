"""Single source of truth for lexemes that may be searched and studied at runtime."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
CONTENT_POS = {"NOM", "VER", "ADJ", "ADV"}


def normalize(value: object) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text))


def pos_from_seed(value: object) -> str | None:
    value = str(value or "").lower()
    if value.startswith("v"):
        return "VER"
    if value.startswith("n"):
        return "NOM"
    if value.startswith("adj"):
        return "ADJ"
    if value.startswith("adv"):
        return "ADV"
    return None


def seed_keys() -> set[tuple[str, str]]:
    if not SEED_PATH.exists():
        return set()
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return {
        (normalize(item.get("id")), pos)
        for item in payload.get("nodes", [])
        if (pos := pos_from_seed(item.get("pos"))) is not None
    }


def learning_lexeme_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every lexeme the runtime promises can be searched or studied.

    Canvas membership is intentionally not consulted: layout is a presentation
    choice, whereas dictionary coverage is a learner-content contract.
    """
    keys = seed_keys()
    rows = conn.execute("SELECT * FROM lexemes ORDER BY id").fetchall()
    return [
        row for row in rows
        if row["status"] == "eligible"
        or (row["normalized"], row["pos"]) in keys
        or (
            row["status"] == "auxiliary"
            and row["cefr_level"] in {"A1", "A2"}
            and row["pos"] in CONTENT_POS
            and row["has_cfdict"]
        )
    ]
