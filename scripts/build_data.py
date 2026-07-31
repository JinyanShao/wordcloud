#!/usr/bin/env python3
"""Build maillage's inspectable SQLite lexicon and deterministic audit sample."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DB_PATH = PROCESSED / "maillage.sqlite"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
SOURCES_PATH = ROOT / "data" / "sources.json"
SEED_PATH = PROCESSED / "editorial-seed.json"
AUDIT_ID = "lexicon-v1-2026-07-27"
BUILD_TIME = "2026-07-27T00:00:00Z"

CONTENT_POS = {"NOM", "VER", "ADJ", "ADV"}
TARGET_LEVELS = {"B1", "B2", "C1"}
MIN_UNGLOSSED_FREQUENCY = 1.0
FOUNDATIONAL_CORE_VERSION = "v1"
VALID_WORD = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿŒœÆæÇç'’ -]+$")
FUNCTIONAL_ADVERBS = {
    "ainsi", "alors", "assez", "aussi", "autant", "beaucoup", "bien",
    "bientôt", "certes", "ci", "comme", "comment", "davantage", "déjà",
    "demain", "désormais", "donc", "encore", "enfin", "ensemble", "ensuite",
    "environ", "hier", "ici", "jamais", "là", "longtemps", "maintenant",
    "même", "moins", "non", "oui", "partout", "peu", "plus", "plutôt",
    "pourquoi", "pourtant", "presque", "puis", "quand", "quelquefois",
    "seulement", "si", "sinon", "souvent", "tant", "tard", "tôt", "toujours",
    "tout", "toute", "très", "trop", "vite", "volontiers", "vraiment", "çà",
}


def normalize(value: object) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nullable(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def number(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_cfdict() -> dict[str, list[str]]:
    text = (ROOT / "dict.js").read_text(encoding="utf-8")
    start = text.index("{")
    end = text.rindex("};") + 1
    payload = json.loads(text[start:end])
    return {normalize(word): list(glosses) for word, glosses in payload.items()}


def register_sources(conn: sqlite3.Connection) -> None:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    for source in sources:
        local = ROOT / source["local_path"] if source.get("local_path") else None
        source_hash = sha256(local) if local and local.exists() else None
        expected_hash = source.get("expected_sha256")
        if expected_hash and source_hash != expected_hash:
            raise SystemExit(
                f"source lock mismatch for {source['id']}: expected {expected_hash}, got {source_hash or 'missing'}; "
                "run scripts/fetch_sources.py --download or refresh the reviewed source lock"
            )
        conn.execute(
            """
            INSERT INTO sources(
              id, name, version, homepage_url, download_url, license_id,
              license_url, attribution, commercial_use, redistribution,
              local_path, sha256, downloaded_at, notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source["id"], source["name"], source["version"],
                source["homepage_url"], source.get("download_url"),
                source["license_id"], source.get("license_url"),
                source["attribution"], source["commercial_use"],
                source["redistribution"], source.get("local_path"),
                source_hash, source.get("downloaded_at"), source.get("notes", ""),
            ),
        )


def import_flelex(conn: sqlite3.Connection) -> pd.DataFrame:
    frame = pd.read_csv(RAW / "FleLex_TT_Beacco.tsv", sep="\t")
    rows = []
    for row in frame.itertuples(index=False):
        rows.append(
            (
                row.word, normalize(row.word), row.tag,
                number(row.freq_A1), number(row.freq_A2), number(row.freq_B1),
                number(row.freq_B2), number(row.freq_C1), number(row.freq_C2),
                number(row.freq_total), row.level, "flelex_beacco_tt",
            )
        )
    conn.executemany(
        """
        INSERT INTO flelex_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    return frame


def import_lexique(conn: sqlite3.Connection) -> pd.DataFrame:
    frame = pd.read_csv(RAW / "Lexique400.tsv", sep="\t", low_memory=False)
    columns = [
        "1_Mot", "2_Phono", "3_Phono_IPA", "4_Lemme", "5_Cgram", "6_CgramOrtho",
        "7_Genre", "8_Nombre", "10_FreqMot", "11_FreqOrtho", "12_FreqLemme",
        "13_CDOrtho", "14_IsLem", "30_MorphoBase", "31_MorphoStruct",
        "32_MorphoDecomp", "33_Preval",
    ]
    rows = []
    for values in frame[columns].itertuples(index=False, name=None):
        (
            form, phono, ipa, lemma, pos, pos_ortho, gender, grammatical_number,
            freq_form, freq_ortho, freq_lemma, cd_ortho, is_lemma,
            morph_base, morph_structure, morph_decomposition, prevalence,
        ) = values
        rows.append(
            (
                str(form), normalize(form), str(lemma), normalize(lemma), str(pos),
                nullable(pos_ortho), nullable(gender), nullable(grammatical_number),
                nullable(phono), nullable(ipa), number(freq_form), number(freq_ortho),
                number(freq_lemma), number(cd_ortho), int(number(is_lemma)),
                nullable(morph_base), nullable(morph_structure),
                nullable(morph_decomposition), number(prevalence, default=math.nan),
                "lexique_400",
            )
        )
    conn.executemany(
        """
        INSERT INTO lexique_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    return frame


def import_cfdict(conn: sqlite3.Connection) -> dict[str, list[str]]:
    payload = parse_cfdict()
    conn.executemany(
        "INSERT INTO cfdict_entries VALUES(?,?,?,?)",
        [
            (word, normalize(word), json.dumps(glosses, ensure_ascii=False), "cfdict_reverse_local")
            for word, glosses in payload.items()
        ],
    )
    return payload


def choose_lexique_rows(frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    content = frame[frame["5_Cgram"].isin(CONTENT_POS)].copy()
    content["_norm"] = content["4_Lemme"].map(normalize)
    content["_is_lemma"] = pd.to_numeric(content["14_IsLem"], errors="coerce").fillna(0)
    content["_freq_form"] = pd.to_numeric(content["10_FreqMot"], errors="coerce").fillna(0)
    content = content.sort_values(["_is_lemma", "_freq_form"], ascending=[False, False])
    result: dict[tuple[str, str], dict[str, object]] = {}
    for (lemma, pos), group in content.groupby(["_norm", "5_Cgram"], sort=False):
        row = group.iloc[0]
        def most_common(column: str) -> str | None:
            values = [str(v).strip() for v in group[column].dropna() if str(v).strip()]
            return Counter(values).most_common(1)[0][0] if values else None
        result[(lemma, pos)] = {
            "lemma": str(row["4_Lemme"]),
            "phonetic_ipa": nullable(row["3_Phono_IPA"]),
            "freq_lemma": number(group["12_FreqLemme"].max()),
            "contextual_diversity": number(group["13_CDOrtho"].max()),
            "morph_base": most_common("30_MorphoBase"),
            "morph_structure": most_common("31_MorphoStruct"),
            "morph_decomposition": most_common("32_MorphoDecomp"),
            "aliases": sorted({str(v) for v in group["1_Mot"].dropna()}),
        }
    return result


def classify(row: object, lexique: dict[str, object] | None, glosses: list[str] | None) -> tuple[str, str, float]:
    word = str(row.word)
    normalized = normalize(word)
    if row.tag not in CONTENT_POS:
        if row.tag in {"PRO", "PRP", "PRP:det", "KON", "DET:ART", "DET:POS"}:
            return "auxiliary", "closed_class", 0.05
        return "excluded", "non_content_pos", 0.0
    if len(normalized) < 2 or not VALID_WORD.fullmatch(word):
        return "excluded", "invalid_surface", 0.0
    if row.tag == "ADV" and normalized in FUNCTIONAL_ADVERBS:
        return "auxiliary", "functional_adverb", 0.08
    if normalized.count("-") >= 3:
        return "needs_review", "complex_expression", 0.08
    if not lexique:
        if row.level in TARGET_LEVELS:
            return "needs_review", "missing_lexique_alignment", 0.1
        return "excluded", "missing_lexique_alignment_outside_target", 0.0
    frequency = number(row.freq_total)
    has_gloss = bool(glosses)
    has_morph = bool(lexique.get("morph_base"))
    canonical = str(lexique.get("lemma") or word)
    if canonical[:1].isupper():
        return "excluded", "capitalized_or_proper", 0.0
    if row.level in {"A1", "A2"}:
        return "auxiliary", "foundational_content", 0.2
    if row.level == "C2":
        if has_gloss or frequency >= 0.1:
            return "needs_review", "advanced_tail", 0.15
        return "excluded", "outside_target_cefr", 0.0
    if row.level not in TARGET_LEVELS:
        return "excluded", "outside_target_cefr", 0.0
    level_weight = {"B1": 1.0, "B2": 0.82, "C1": 0.7}.get(row.level, 0.0)
    frequency_score = min(1.0, math.log1p(frequency) / math.log(51))
    evidence_score = 0.22 * has_gloss + 0.12 * has_morph
    score = round(0.48 * level_weight + 0.18 * frequency_score + evidence_score, 6)
    if has_gloss or frequency >= MIN_UNGLOSSED_FREQUENCY:
        reason = "target_content_with_gloss" if has_gloss else "target_content_high_frequency_missing_gloss"
        return "eligible", reason, score
    return "needs_review", "low_frequency_missing_gloss", score


def build_lexemes(
    conn: sqlite3.Connection,
    flelex: pd.DataFrame,
    lexique_rows: dict[tuple[str, str], dict[str, object]],
    cfdict: dict[str, list[str]],
) -> None:
    for row in flelex.itertuples(index=False):
        normalized = normalize(row.word)
        lexique = lexique_rows.get((normalized, row.tag))
        canonical = str(lexique.get("lemma")) if lexique else str(row.word)
        canonical_normalized = normalize(canonical)
        glosses = cfdict.get(normalized) or cfdict.get(canonical_normalized)
        status, reason, score = classify(row, lexique, glosses)
        cursor = conn.execute(
            """
            INSERT INTO lexemes(
              lemma, normalized, pos, cefr_level, flelex_frequency,
              lexique_frequency, contextual_diversity, phonetic_ipa,
              morph_base, morph_structure, morph_decomposition, gloss_zh,
              editorial_note, status, decision_reason, eligibility_score,
              has_flelex, has_lexique, has_cfdict, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                canonical, canonical_normalized, row.tag, row.level, number(row.freq_total),
                lexique.get("freq_lemma") if lexique else None,
                lexique.get("contextual_diversity") if lexique else None,
                lexique.get("phonetic_ipa") if lexique else None,
                lexique.get("morph_base") if lexique else None,
                lexique.get("morph_structure") if lexique else None,
                lexique.get("morph_decomposition") if lexique else None,
                "；".join(glosses) if glosses else None,
                None, status, reason, score, 1, int(bool(lexique)), int(bool(glosses)), BUILD_TIME,
            ),
        )
        lexeme_id = cursor.lastrowid
        if lexique:
            aliases = lexique.get("aliases", [])
            conn.executemany(
                "INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)",
                [
                    (lexeme_id, alias, normalize(alias), "inflection", "lexique_400")
                    for alias in aliases
                ],
            )


def seed_pos(value: str) -> str | None:
    value = value.lower()
    if value.startswith("v"):
        return "VER"
    if value.startswith("n"):
        return "NOM"
    if value.startswith("adj"):
        return "ADJ"
    if value.startswith("adv"):
        return "ADV"
    return None


def add_editorial_seed_support(
    conn: sqlite3.Connection,
    lexique_rows: dict[tuple[str, str], dict[str, object]],
    cfdict: dict[str, list[str]],
) -> None:
    """Preserve reviewed prototype vocabulary without counting it as main coverage."""
    if not SEED_PATH.exists():
        return
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for item in seed.get("nodes", []):
        lemma = str(item["id"])
        normalized = normalize(lemma)
        pos = seed_pos(str(item.get("pos", "")))
        if not pos:
            continue
        existing = conn.execute(
            "SELECT id,gloss_zh FROM lexemes WHERE normalized=? AND pos=?",
            (normalized, pos),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE lexemes
                SET editorial_note=?, gloss_zh=COALESCE(?, gloss_zh)
                WHERE id=?
                """,
                (item.get("note"), item.get("gloss"), existing[0]),
            )
            continue

        bare = re.sub(r"^(?:s'|se )", "", normalized)
        lexique = lexique_rows.get((normalized, pos)) or lexique_rows.get((bare, pos))
        glosses = cfdict.get(normalized) or cfdict.get(bare)
        conn.execute(
            """
            INSERT INTO lexemes(
              lemma, normalized, pos, cefr_level, flelex_frequency,
              lexique_frequency, contextual_diversity, phonetic_ipa,
              morph_base, morph_structure, morph_decomposition, gloss_zh,
              editorial_note, status, decision_reason, eligibility_score,
              has_flelex, has_lexique, has_cfdict, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lemma, normalized, pos, None, 0,
                lexique.get("freq_lemma") if lexique else None,
                lexique.get("contextual_diversity") if lexique else None,
                lexique.get("phonetic_ipa") if lexique else None,
                lexique.get("morph_base") if lexique else None,
                lexique.get("morph_structure") if lexique else None,
                lexique.get("morph_decomposition") if lexique else None,
                item.get("gloss") or ("；".join(glosses) if glosses else None),
                item.get("note"), "auxiliary", "editorial_seed_support", 0.2,
                0, int(bool(lexique)), int(bool(glosses)), BUILD_TIME,
            ),
        )


def foundational_core(seed: dict[str, object]) -> list[dict[str, str]]:
    """Read the deliberately small, human-reviewed A1/A2 promotion list."""
    entries = seed.get("foundationalCore", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed foundationalCore must be a list")
    seen: set[tuple[str, str]] = set()
    normalized_entries: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            raise SystemExit("editorial-seed foundationalCore entries must be objects")
        lemma = str(item.get("id", "")).strip()
        pos = str(item.get("pos", "")).strip().upper()
        gloss = str(item.get("gloss", "")).strip()
        reviewer = str(item.get("reviewer", "")).strip()
        reviewed_at = str(item.get("reviewedAt", "")).strip()
        if not lemma or pos not in CONTENT_POS or not gloss or not reviewer or not reviewed_at:
            raise SystemExit(f"invalid foundational core entry: {item!r}")
        key = (normalize(lemma), pos)
        if key in seen:
            raise SystemExit(f"duplicate foundational core entry: {lemma}/{pos}")
        seen.add(key)
        normalized_entries.append({
            "id": lemma,
            "normalized": key[0],
            "pos": pos,
            "gloss": gloss,
            "reviewer": reviewer,
            "reviewedAt": reviewed_at,
        })
    return normalized_entries


def apply_foundational_core(conn: sqlite3.Connection) -> None:
    """Promote reviewed beginner essentials without widening the automatic A1/A2 rule."""
    if not SEED_PATH.exists():
        return
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    entries = foundational_core(seed)
    for item in entries:
        row = conn.execute(
            "SELECT id FROM lexemes WHERE normalized=? AND pos=?",
            (item["normalized"], item["pos"]),
        ).fetchone()
        if not row:
            raise SystemExit(
                f"foundational core entry missing from FLELex/Lexique alignment: {item['id']}/{item['pos']}"
            )
        conn.execute(
            """
            UPDATE lexemes
            SET status='eligible',
                decision_reason=?,
                eligibility_score=MAX(eligibility_score, 1.01),
                gloss_zh=?,
                editorial_note=COALESCE(editorial_note, ?)
            WHERE id=?
            """,
            (
                f"editorial_foundational_core:{FOUNDATIONAL_CORE_VERSION}:{item['reviewer']}:{item['reviewedAt']}",
                item["gloss"],
                "A1/A2 基础核心词；中文提示经人工审校，按 lemma + POS 覆盖自动词形匹配。",
                row[0],
            ),
        )
    conn.execute(
        "INSERT OR REPLACE INTO build_metadata(key,value) VALUES(?,?)",
        ("foundational_core", json.dumps({"version": FOUNDATIONAL_CORE_VERSION, "count": len(entries)}, ensure_ascii=False)),
    )


def apply_editorial_gloss_overrides(conn: sqlite3.Connection) -> None:
    """Apply reviewed Chinese prompts only to their exact lemma and part of speech."""
    if not SEED_PATH.exists():
        return
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    entries = seed.get("glossOverrides", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed glossOverrides must be a list")
    seen: set[tuple[str, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise SystemExit("editorial-seed glossOverrides entries must be objects")
        lemma = str(item.get("id", "")).strip()
        pos = str(item.get("pos", "")).strip().upper()
        gloss = str(item.get("gloss", "")).strip()
        reviewer = str(item.get("reviewer", "")).strip()
        reviewed_at = str(item.get("reviewedAt", "")).strip()
        key = (normalize(lemma), pos)
        if not lemma or pos not in CONTENT_POS or not gloss or not reviewer or not reviewed_at:
            raise SystemExit(f"invalid gloss override: {item!r}")
        if key in seen:
            raise SystemExit(f"duplicate gloss override: {lemma}/{pos}")
        seen.add(key)
        result = conn.execute(
            "UPDATE lexemes SET gloss_zh=? WHERE normalized=? AND pos=?",
            (gloss, key[0], pos),
        )
        if result.rowcount != 1:
            raise SystemExit(f"gloss override must match exactly one lexeme: {lemma}/{pos}")


def apply_editorial_learning(conn: sqlite3.Connection) -> None:
    """Load reviewed etymology and collocations as distinct teaching surfaces."""
    if not SEED_PATH.exists():
        return
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    entries = seed.get("editorialLearning", [])
    if not isinstance(entries, list):
        raise SystemExit("editorial-seed editorialLearning must be a list")
    seen: set[tuple[str, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise SystemExit("editorialLearning entries must be objects")
        lemma = str(item.get("id", "")).strip()
        pos = str(item.get("pos", "")).strip().upper()
        source = str(item.get("source", "")).strip()
        reviewer = str(item.get("reviewer", "")).strip()
        reviewed_at = str(item.get("reviewedAt", "")).strip()
        key = (normalize(lemma), pos)
        if not lemma or pos not in CONTENT_POS or not source or not reviewer or not reviewed_at:
            raise SystemExit(f"invalid editorial learning entry: {item!r}")
        if key in seen:
            raise SystemExit(f"duplicate editorial learning entry: {lemma}/{pos}")
        seen.add(key)
        row = conn.execute("SELECT id FROM lexemes WHERE normalized=? AND pos=?", key).fetchone()
        if not row:
            raise SystemExit(f"editorial learning entry missing from lexicon: {lemma}/{pos}")
        lexeme_id = row[0]
        etymology = str(item.get("etymology", "")).strip()
        collocations = item.get("collocations", [])
        if not etymology or not isinstance(collocations, list) or not collocations:
            raise SystemExit(f"editorial learning requires etymology and collocations: {lemma}/{pos}")
        conn.execute(
            "INSERT OR REPLACE INTO lexeme_etymologies VALUES(?,?,?,?,?)",
            (lexeme_id, etymology, source, reviewer, reviewed_at),
        )
        conn.execute("DELETE FROM lexeme_collocations WHERE lexeme_id=?", (lexeme_id,))
        rows = []
        for collocation in collocations:
            if not isinstance(collocation, dict):
                raise SystemExit(f"invalid collocation for {lemma}/{pos}")
            expression = str(collocation.get("expression", "")).strip()
            gloss = str(collocation.get("gloss", "")).strip()
            if not expression or not gloss:
                raise SystemExit(f"invalid collocation for {lemma}/{pos}: {collocation!r}")
            rows.append((lexeme_id, expression, gloss, source, reviewer, reviewed_at))
        conn.executemany(
            "INSERT INTO lexeme_collocations(lexeme_id,expression_fr,gloss_zh,source_label,reviewer,reviewed_at) VALUES(?,?,?,?,?,?)",
            rows,
        )


def allocate_stratified(rows: list[sqlite3.Row], target: int, seed: int) -> list[sqlite3.Row]:
    rng = random.Random(seed)
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = f"{row['status']}|{row['decision_reason']}|{row['cefr_level']}|{row['pos']}"
        groups[key].append(row)
    for values in groups.values():
        rng.shuffle(values)
    total = len(rows)
    allocations = {key: min(len(values), max(1, round(target * len(values) / total))) for key, values in groups.items()}
    while sum(allocations.values()) > target:
        candidates = [key for key, count in allocations.items() if count > 1]
        key = max(candidates, key=lambda item: allocations[item] / len(groups[item]))
        allocations[key] -= 1
    while sum(allocations.values()) < target:
        candidates = [key for key, count in allocations.items() if count < len(groups[key])]
        key = max(candidates, key=lambda item: len(groups[item]) - allocations[item])
        allocations[key] += 1
    sample = []
    for key in sorted(groups):
        sample.extend(groups[key][: allocations[key]])
    rng.shuffle(sample)
    return sample


def create_audit_sample(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, lemma, pos, cefr_level, flelex_frequency, gloss_zh,
               status, decision_reason, has_lexique, has_cfdict
        FROM lexemes
        ORDER BY id
        """
    ).fetchall()
    sample = allocate_stratified(rows, 500, seed=20260727)
    conn.executemany(
        """
        INSERT INTO audit_samples(
          audit_id, sample_order, lexeme_id, stratum,
          automated_status, automated_reason
        ) VALUES(?,?,?,?,?,?)
        """,
        [
            (
                AUDIT_ID, order, row["id"],
                f"{row['status']}|{row['decision_reason']}|{row['cefr_level']}|{row['pos']}",
                row["status"], row["decision_reason"],
            )
            for order, row in enumerate(sample, start=1)
        ],
    )
    path = REPORTS / "lexicon-audit-sample-500.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([
            "audit_id", "sample_order", "lexeme_id", "lemma", "pos", "cefr_level",
            "flelex_frequency", "gloss_zh", "automated_status", "automated_reason",
            "manual_decision", "manual_note",
        ])
        for order, row in enumerate(sample, start=1):
            writer.writerow([
                AUDIT_ID, order, row["id"], row["lemma"], row["pos"], row["cefr_level"],
                row["flelex_frequency"], row["gloss_zh"] or "", row["status"],
                row["decision_reason"], "", "",
            ])


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "—"


def write_report(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM lexemes").fetchone()[0]
    statuses = dict(conn.execute("SELECT status, COUNT(*) FROM lexemes GROUP BY status").fetchall())
    source_counts = {
        "flelex": conn.execute("SELECT COUNT(*) FROM flelex_entries").fetchone()[0],
        "lexique": conn.execute("SELECT COUNT(*) FROM lexique_entries").fetchone()[0],
        "cfdict": conn.execute("SELECT COUNT(*) FROM cfdict_entries").fetchone()[0],
    }
    join = conn.execute(
        """
        SELECT
          SUM(has_lexique) AS lexique_matches,
          SUM(has_cfdict) AS cfdict_matches,
          SUM(has_lexique * has_cfdict) AS three_way
        FROM lexemes
        WHERE pos IN ('NOM','VER','ADJ','ADV') AND cefr_level IN ('B1','B2','C1')
        """
    ).fetchone()
    target_total = conn.execute(
        "SELECT COUNT(*) FROM lexemes WHERE pos IN ('NOM','VER','ADJ','ADV') AND cefr_level IN ('B1','B2','C1')"
    ).fetchone()[0]
    by_level_pos = conn.execute(
        """
        SELECT cefr_level, pos, COUNT(*) AS n
        FROM lexemes WHERE status='eligible'
        GROUP BY cefr_level, pos ORDER BY cefr_level, pos
        """
    ).fetchall()
    reasons = conn.execute(
        "SELECT status, decision_reason, COUNT(*) AS n FROM lexemes GROUP BY status, decision_reason ORDER BY n DESC"
    ).fetchall()
    missing_common = conn.execute(
        """
        SELECT lemma, pos, cefr_level, ROUND(flelex_frequency, 3) AS freq
        FROM lexemes
        WHERE status='eligible' AND has_cfdict=0
        ORDER BY flelex_frequency DESC LIMIT 25
        """
    ).fetchall()
    review_counts = dict(
        conn.execute(
            """
            SELECT COALESCE(manual_decision, 'unreviewed'), COUNT(*)
            FROM audit_samples GROUP BY COALESCE(manual_decision, 'unreviewed')
            """
        ).fetchall()
    )
    reviewed_total = sum(count for decision, count in review_counts.items() if decision != "unreviewed")
    override_total = sum(count for decision, count in review_counts.items() if decision.startswith("override_"))
    defer_total = review_counts.get("defer", 0)
    gloss_flags = conn.execute(
        "SELECT COUNT(*) FROM audit_samples WHERE manual_note LIKE '%CFDICT%' OR manual_note LIKE '%gloss%'"
    ).fetchone()[0]
    lines = [
        "# 有效词表审计 · v1",
        "",
        f"> 构建时间：{BUILD_TIME}  ",
        f"> 数据粒度：FLELex lemma + TreeTagger 词性；总计 {total:,} 个候选词汇单位。",
        "",
        "## Intended use 与判定规则",
        "",
        "自动进入主词表的词，必须是 B1–C1 的名词、动词、形容词或实义副词，能与 Lexique 4 的 lemma+POS 对齐，并满足以下至少一项：",
        "",
        "- CFDICT 有中文释义候选；",
        f"- FLELex 总频率 ≥ {MIN_UNGLOSSED_FREQUENCY}/百万。",
        "",
        "封闭类虚词与大多数 A1/A2 实词进入 auxiliary，不计入自动主覆盖率；`editorial-seed.json` 的 foundationalCore 是逐项审校的例外，会以 lemma+POS 和人工中文提示进入主图。只有已审核官方关系实际用到的其他 auxiliary 才作为支撑节点进入星图。人工抽检覆盖可以修正自动状态，所有例外都保留可追溯原因。",
        "",
        "## 数据源与规模",
        "",
        "| 数据源 | 原始行数/词条 | 用途 |",
        "|---|---:|---|",
        f"| FLELex / Beacco | {source_counts['flelex']:,} | CEFR、词性、学习语料频率 |",
        f"| Lexique 4.00 | {source_counts['lexique']:,} | lemma、频率、IPA、形态 |",
        f"| CFDICT 本地反向索引 | {source_counts['cfdict']:,} | 中文释义候选 |",
        "",
        "## 对齐质量",
        "",
        f"在 {target_total:,} 个 B1–C1 实词候选中：",
        "",
        f"- Lexique lemma+POS 精确匹配：{join['lexique_matches']:,}（{pct(join['lexique_matches'], target_total)}）",
        f"- CFDICT 词形匹配：{join['cfdict_matches']:,}（{pct(join['cfdict_matches'], target_total)}）",
        f"- 三方同时匹配：{join['three_way']:,}（{pct(join['three_way'], target_total)}）",
        "",
        "**高风险发现：CFDICT 覆盖不是随机缺失。它遗漏了一批常用 B1/B2 词，因此不能把“CFDICT 无释义”直接等同于低价值。当前规则用 FLELex 频率兜底，并将这些词保留为 eligible、标记待补释义。**",
        "",
        "## 自动判定结果",
        "",
        "| 状态 | 数量 | 占比 |",
        "|---|---:|---:|",
    ]
    for status in ("eligible", "needs_review", "auxiliary", "excluded"):
        count = statuses.get(status, 0)
        lines.append(f"| {status} | {count:,} | {pct(count, total)} |")
    lines += ["", "### eligible：CEFR × 词性", "", "| CEFR | POS | 数量 |", "|---|---|---:|"]
    lines.extend(f"| {row['cefr_level']} | {row['pos']} | {row['n']:,} |" for row in by_level_pos)
    lines += ["", "### 判定原因", "", "| 状态 | 原因 | 数量 |", "|---|---|---:|"]
    lines.extend(f"| {row['status']} | {row['decision_reason']} | {row['n']:,} |" for row in reasons)
    lines += [
        "",
        "## CFDICT 缺失但因高频保留的示例",
        "",
        "| lemma | POS | CEFR | FLELex freq/百万 |",
        "|---|---|---|---:|",
    ]
    lines.extend(f"| {row['lemma']} | {row['pos']} | {row['cefr_level']} | {row['freq']} |" for row in missing_common)
    lines += [
        "",
        "## 500 条分层人工抽检",
        "",
        "`lexicon-audit-sample-500.csv` 使用固定随机种子 20260727，按 status × reason × CEFR × POS 分层抽取。空白不代表通过；只有 reviewer 与 reviewed_at 完整才算完成抽检。",
        "",
        f"- 已人工检查：{reviewed_total}/500",
        f"- 同意自动状态：{review_counts.get('agree', 0)}（{pct(review_counts.get('agree', 0), reviewed_total)}）",
        f"- 覆盖自动状态：{override_total}（{pct(override_total, reviewed_total)}）",
        f"- 暂缓判断：{defer_total}",
        f"- 明确标记 CFDICT/释义问题：{gloss_flags}",
        "",
        "## 自动化质量门",
        "",
        "- sources.sha256 必须完整；",
        "- lexemes(normalized, pos) 唯一；",
        "- 自动 eligible 必须为 B1–C1 实词且存在 Lexique 对齐；基础核心词与人工抽检覆盖例外必须带可追溯 decision_reason；",
        "- 自动 eligible 若缺 CFDICT，FLELex frequency 必须 ≥ 1/百万；人工覆盖例外同上；",
        "- audit sample 必须恰好 500 条且无重复 lexeme；",
        "- 任何 layout link 和 official edge 必须满足端点存在、a_id < b_id。",
        "",
        "## 当前限制",
        "",
        "- FLELex 为 CC BY-NC-SA 4.0，当前成果仅适用于非商业原型；",
        "- CFDICT 释义质量尚未逐条验证；",
        "- 多义词目前仍按 lemma+POS 合并；",
        "- eligibility 的 1/百万阈值是 v1 可解释规则，需要结合 500 条抽检结果再校准。",
    ]
    (REPORTS / "lexicon-audit-v1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_eligible(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, lemma, normalized, pos, cefr_level, flelex_frequency,
               lexique_frequency, contextual_diversity, phonetic_ipa,
               morph_base, morph_structure, morph_decomposition, gloss_zh,
               decision_reason, eligibility_score, has_cfdict
        FROM lexemes WHERE status='eligible'
        ORDER BY eligibility_score DESC, flelex_frequency DESC, id
        """
    ).fetchall()
    path = PROCESSED / "eligible-lexicon.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(rows[0].keys() if rows else [])
        writer.writerows([tuple(row) for row in rows])


def build() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        register_sources(conn)
        flelex = import_flelex(conn)
        lexique = import_lexique(conn)
        cfdict = import_cfdict(conn)
        lexique_rows = choose_lexique_rows(lexique)
        build_lexemes(conn, flelex, lexique_rows, cfdict)
        create_audit_sample(conn)
        add_editorial_seed_support(conn, lexique_rows, cfdict)
        apply_foundational_core(conn)
        apply_editorial_gloss_overrides(conn)
        apply_editorial_learning(conn)
        conn.executemany(
            "INSERT INTO build_metadata(key, value) VALUES(?,?)",
            [
                ("schema_version", "1"),
                ("audit_id", AUDIT_ID),
                ("min_unglossed_frequency", str(MIN_UNGLOSSED_FREQUENCY)),
                ("built_at", BUILD_TIME),
            ],
        )
        write_report(conn)
        export_eligible(conn)
        conn.commit()
    finally:
        conn.close()
    print(f"built {DB_PATH.relative_to(ROOT)}")


def sync_review() -> None:
    path = REPORTS / "lexicon-audit-sample-500.csv"
    conn = sqlite3.connect(DB_PATH)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if len(rows) != 500:
        raise SystemExit(f"expected 500 audit rows, found {len(rows)}")
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        decision = row["manual_decision"].strip() or None
        reviewer = "Jinyan Shao" if decision else None
        lexeme_id = int(row["lexeme_id"])
        conn.execute(
            """
            UPDATE audit_samples
            SET manual_decision=?, manual_note=?, reviewer=?, reviewed_at=?
            WHERE audit_id=? AND sample_order=?
            """,
            (
                decision, row["manual_note"].strip(), reviewer, now if decision else None,
                row["audit_id"], int(row["sample_order"]),
            ),
        )
        if decision and decision.startswith("override_"):
            target_status = decision.removeprefix("override_")
            conn.execute(
                """
                UPDATE lexemes
                SET status=?, decision_reason='manual_audit_override:' || decision_reason
                WHERE id=?
                """,
                (target_status, lexeme_id),
            )
        elif decision == "defer":
            conn.execute(
                """
                UPDATE lexemes
                SET status='needs_review', decision_reason='manual_audit_defer:' || decision_reason
                WHERE id=?
                """,
                (lexeme_id,),
            )
    apply_foundational_core(conn)
    apply_editorial_gloss_overrides(conn)
    apply_editorial_learning(conn)
    conn.commit()
    write_report(conn)
    export_eligible(conn)
    conn.commit()
    conn.close()
    print(f"synced {sum(bool(row['manual_decision'].strip()) for row in rows)} reviews")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "sync-review"), nargs="?", default="build")
    args = parser.parse_args()
    if args.command == "build":
        build()
    else:
        sync_review()


if __name__ == "__main__":
    main()
