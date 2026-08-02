#!/usr/bin/env python3
"""Generate explainable layout links and a connected graph for stable layout."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
GRAPH_INPUT = ROOT / "data" / "processed" / "graph-input.json"
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
DEMONETTE_APPROVED_PATH = ROOT / "data" / "processed" / "demonette-approved.json"
DBNARY_APPROVED_PATH = ROOT / "data" / "processed" / "dbnary-approved.json"
WIKTEXTRACT_P0_APPROVED_PATH = ROOT / "data" / "processed" / "wiktextract-p0-approved.json"
CREATED_AT = "2026-07-27T00:00:00Z"

SIGNAL_CONFIG = {
    "semantic": {"k": 6, "threshold": 0.24, "max_df": 70, "relation": "syn", "source": "cfdict_reverse_local"},
    "spelling": {"k": 3, "threshold": 0.42, "max_df": 140, "relation": "trap", "source": "lexique_400"},
    "phonetic": {"k": 3, "threshold": 0.48, "max_df": 140, "relation": "trap", "source": "lexique_400"},
}

ZH_STOP = set("的一了是在人有和与或为把被所及等又可不很更最也于从到中上下内外用作个种者性化")


def normalize(value: str) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text))


def fold(value: str) -> str:
    text = unicodedata.normalize("NFD", normalize(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z'-]", "", text)


def semantic_features(gloss: str | None) -> set[str]:
    if not gloss:
        return set()
    features: set[str] = set()
    for segment in re.split(r"[；;/,，、。()（）\s]+", gloss):
        segment = segment.strip()
        if not segment:
            continue
        chinese = "".join(char for char in segment if "\u3400" <= char <= "\u9fff")
        if chinese:
            if 1 < len(chinese) <= 6:
                features.add("whole:" + chinese)
            for index in range(len(chinese) - 1):
                gram = chinese[index : index + 2]
                if not all(char in ZH_STOP for char in gram):
                    features.add("bigram:" + gram)
        for token in re.findall(r"[a-zA-ZÀ-ÖØ-öø-ÿ]{3,}", segment.lower()):
            features.add("latin:" + fold(token))
    return features


def spelling_features(word: str) -> set[str]:
    text = "^" + fold(word).replace("'", "").replace("-", "") + "$"
    if len(text) < 5:
        return {"spell:" + text}
    return {"spell:" + text[index : index + 3] for index in range(len(text) - 2)}


def phonetic_features(ipa: str | None) -> set[str]:
    if not ipa:
        return set()
    text = "^" + re.sub(r"[\s.\-]", "", ipa) + "$"
    return {"phone:" + text[index : index + 3] for index in range(max(0, len(text) - 2))}


def clean_morph_base(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("{", "").replace("}", "")
    match = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœÆæÇç'-]+", text)
    return normalize(max(match, key=len)) if match else ""


def push_top(heap: list[tuple[float, int]], score: float, neighbor: int, k: int) -> None:
    item = (score, neighbor)
    if len(heap) < k:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def sparse_neighbors(
    features: dict[int, set[str]],
    *,
    k: int,
    threshold: float,
    max_df: int,
) -> tuple[dict[int, list[tuple[int, float]]], list[tuple[int, int, float]]]:
    postings: dict[str, list[int]] = defaultdict(list)
    for node_id, tokens in features.items():
        for token in tokens:
            postings[token].append(node_id)
    total = max(1, len(features))
    weights = {
        token: math.log((1 + total) / (1 + len(ids))) + 1
        for token, ids in postings.items()
        if 2 <= len(ids) <= max_df
    }
    norms: dict[int, float] = defaultdict(float)
    for node_id, tokens in features.items():
        norms[node_id] = math.sqrt(sum(weights[token] ** 2 for token in tokens if token in weights))
    pair_scores: dict[tuple[int, int], float] = defaultdict(float)
    for token, weight in weights.items():
        ids = postings[token]
        contribution = weight * weight
        for a, b in combinations(ids, 2):
            pair_scores[(a, b) if a < b else (b, a)] += contribution
    heaps: dict[int, list[tuple[float, int]]] = defaultdict(list)
    fallback_heaps: dict[int, list[tuple[float, int]]] = defaultdict(list)
    scored_pairs: list[tuple[int, int, float]] = []
    for (a, b), dot in pair_scores.items():
        denominator = norms[a] * norms[b]
        if not denominator:
            continue
        score = min(1.0, dot / denominator)
        push_top(fallback_heaps[a], score, b, max(k * 2, 6))
        push_top(fallback_heaps[b], score, a, max(k * 2, 6))
        if score >= threshold:
            push_top(heaps[a], score, b, k)
            push_top(heaps[b], score, a, k)
            scored_pairs.append((a, b, score))
    directed = {
        node_id: sorted(((neighbor, score) for score, neighbor in heap), key=lambda item: (-item[1], item[0]))
        for node_id, heap in heaps.items()
    }
    fallback: list[tuple[int, int, float]] = []
    seen: set[tuple[int, int]] = set()
    for a, heap in fallback_heaps.items():
        for score, b in heap:
            pair = (a, b) if a < b else (b, a)
            if pair not in seen:
                seen.add(pair)
                fallback.append((pair[0], pair[1], score))
    return directed, fallback


def mutual_edges(directed: dict[int, list[tuple[int, float]]]) -> list[tuple[int, int, float]]:
    lookup = {a: {b: score for b, score in values} for a, values in directed.items()}
    edges: list[tuple[int, int, float]] = []
    for a, values in lookup.items():
        for b, score in values.items():
            if a < b and a in lookup.get(b, {}):
                edges.append((a, b, min(score, lookup[b][a])))
    return edges


class UnionFind:
    def __init__(self, ids: list[int]):
        self.parent = {value: value for value in ids}
        self.size = {value: 1 for value in ids}
        self.components = len(ids)

    def find(self, value: int) -> int:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            parent = self.parent[value]
            self.parent[value] = root
            value = parent
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.components -= 1
        return True


def relation_candidate(signal: str) -> str:
    return {"semantic": "syn", "morphology": "fam", "spelling": "trap", "phonetic": "trap"}[signal]


def pos_from_seed(value: str) -> str | None:
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


def seed_edges(nodes: list[sqlite3.Row]) -> tuple[list[tuple[int, int, float]], list[dict[str, object]]]:
    if not SEED_PATH.exists():
        return [], []
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    by_key = {(row["normalized"], row["pos"]): row["id"] for row in nodes}
    by_word: dict[str, list[int]] = defaultdict(list)
    for row in nodes:
        by_word[row["normalized"]].append(row["id"])
    seed_pos = {normalize(item["id"]): pos_from_seed(item.get("pos", "")) for item in seed["nodes"]}
    def resolve(word: str, explicit_pos: str | None = None) -> int | None:
        normalized = normalize(word)
        pos = explicit_pos or seed_pos.get(normalized)
        if pos and (normalized, pos) in by_key:
            return by_key[(normalized, pos)]
        values = by_word.get(normalized, [])
        return values[0] if len(values) == 1 else None
    layout: list[tuple[int, int, float]] = []
    official: list[dict[str, object]] = []
    editorial_edges = [
        {**edge, "_kind": "prototype"} for edge in seed["edges"]
    ] + [
        {**edge, "_kind": "editorial"} for edge in seed.get("editorialRelations", [])
    ]
    for edge in editorial_edges:
        original_a = resolve(edge["a"], edge.get("aPos"))
        original_b = resolve(edge["b"], edge.get("bPos"))
        if original_a is None or original_b is None or original_a == original_b:
            continue
        a, b = sorted((original_a, original_b))
        layout.append((a, b, 1.0))
        relation = "compare" if edge["type"] == "axis" else edge["type"]
        official.append(
            {
                "a": a, "b": b, "relation": relation,
                "dimension": edge.get("dimension") or ("prototype-axis" if edge["type"] == "axis" else None),
                "subtype": None,
                "direction": f"{original_a}->{original_b}" if edge["type"] in {"axis", "cause"} else None,
                "label": edge.get("label") or relation,
                "explanation": edge.get("explanation"),
                "examples": edge.get("examples", []),
                "reviewer": edge.get("reviewer"),
                "reviewed_at": edge.get("reviewedAt"),
                "source_note": edge.get("source"),
                "kind": edge["_kind"],
            }
        )
    return layout, official


def demonette_edges(nodes: list[sqlite3.Row]) -> list[dict[str, object]]:
    if not DEMONETTE_APPROVED_PATH.exists():
        return []
    payload = json.loads(DEMONETTE_APPROVED_PATH.read_text(encoding="utf-8"))
    if not payload.get("meta", {}).get("gate_passed"):
        raise SystemExit("Démonette approved payload does not carry a passing quality gate")
    by_id = {int(row["id"]): row for row in nodes}
    result = []
    for edge in payload.get("edges", []):
        a_id, b_id = int(edge["a_id"]), int(edge["b_id"])
        if a_id not in by_id or b_id not in by_id:
            raise SystemExit(f"Démonette edge endpoint drift: {a_id}, {b_id}")
        if by_id[a_id]["pos"] == by_id[b_id]["pos"] and not (
            edge.get("complexity") == "simple" and edge.get("subtype") in {"prefixation", "suffixation"}
        ):
            raise SystemExit(f"Démonette same-POS edge is outside the approved simple-affix scope: {a_id}, {b_id}")
        result.append(edge)
    return result


def dbnary_payload(nodes: list[sqlite3.Row]) -> dict[str, object]:
    if not DBNARY_APPROVED_PATH.exists():
        return {"entries": [], "senses": [], "edges": []}
    payload = json.loads(DBNARY_APPROVED_PATH.read_text(encoding="utf-8"))
    if not payload.get("meta", {}).get("gate_passed"):
        raise SystemExit("DBnary approved payload does not carry a passing quality gate")
    by_id = {int(row["id"]): row for row in nodes}
    graph_edges = []
    for edge in payload.get("edges", []):
        a_id, b_id = int(edge["a_id"]), int(edge["b_id"])
        # Dictionary coverage includes search-only learning terms. Only edges
        # with two Canvas endpoints become graph edges; the rest remain in the
        # lexical payload and must not force a layout membership change.
        if a_id not in by_id or b_id not in by_id:
            continue
        if by_id[a_id]["pos"] != by_id[b_id]["pos"]:
            raise SystemExit(f"DBnary semantic relation crossed POS unexpectedly: {a_id}, {b_id}")
        if edge.get("relation") not in {"syn", "ant"}:
            raise SystemExit(f"DBnary relation outside approved scope: {edge.get('relation')}")
        graph_edges.append(edge)
    return {**payload, "edges": graph_edges}


def wiktextract_p0_payload() -> dict[str, object]:
    if not WIKTEXTRACT_P0_APPROVED_PATH.exists():
        return {"entries": [], "senses": []}
    payload = json.loads(WIKTEXTRACT_P0_APPROVED_PATH.read_text(encoding="utf-8"))
    if payload.get("meta", {}).get("source_id") != "wiktionary_fr_wiktextract":
        raise SystemExit("Wiktextract P0 approved payload has an unexpected source")
    return payload


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    all_nodes = conn.execute(
        """
        SELECT id, lemma, normalized, pos, cefr_level, flelex_frequency,
               lexique_frequency, contextual_diversity, phonetic_ipa,
               morph_base, morph_structure, morph_decomposition,
               gloss_zh, eligibility_score, has_cfdict, status
        FROM lexemes ORDER BY id
        """
    ).fetchall()
    seed_keys: set[tuple[str, str]] = set()
    if SEED_PATH.exists():
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for item in seed.get("nodes", []):
            pos = pos_from_seed(item.get("pos", ""))
            if pos:
                seed_keys.add((normalize(item["id"]), pos))
    nodes = [
        row for row in all_nodes
        if row["status"] == "eligible"
        or (row["normalized"], row["pos"]) in seed_keys
    ]
    ids = [row["id"] for row in nodes]
    id_set = set(ids)
    if not nodes:
        raise SystemExit("no eligible lexemes; run build_data.py first")

    conn.execute("DELETE FROM official_edge_sources")
    conn.execute("DELETE FROM official_edges")
    conn.execute("DELETE FROM edge_candidates")
    conn.execute("DELETE FROM layout_links")
    conn.execute("DELETE FROM positions")
    conn.execute("DELETE FROM lexeme_senses")
    conn.execute("DELETE FROM lexical_entries")

    layouts: dict[str, list[tuple[int, int, float]]] = {}
    fallback_edges: list[tuple[int, int, float, str]] = []
    feature_builders = {
        "spelling": lambda row: spelling_features(row["lemma"]),
        "phonetic": lambda row: phonetic_features(row["phonetic_ipa"]),
    }
    for signal, builder in feature_builders.items():
        config = SIGNAL_CONFIG[signal]
        features = {row["id"]: builder(row) for row in nodes}
        directed, fallback = sparse_neighbors(
            features, k=config["k"], threshold=config["threshold"], max_df=config["max_df"]
        )
        edges = mutual_edges(directed)
        layouts[signal] = edges
        fallback_edges.extend((a, b, score, signal) for a, b, score in fallback)

    # CFDICT gloss overlap remains auditable as a candidate only. It no longer
    # determines global geometry or the learner-visible focus graph.
    gloss_features = {row["id"]: semantic_features(row["gloss_zh"]) for row in nodes}
    gloss_directed, _ = sparse_neighbors(
        gloss_features,
        k=SIGNAL_CONFIG["semantic"]["k"],
        threshold=SIGNAL_CONFIG["semantic"]["threshold"],
        max_df=SIGNAL_CONFIG["semantic"]["max_df"],
    )
    gloss_candidate_edges = mutual_edges(gloss_directed)

    by_lemma: dict[str, list[int]] = defaultdict(list)
    for row in nodes:
        by_lemma[row["normalized"]].append(row["id"])
    morphology_weights: dict[tuple[int, int], float] = {}
    score_by_id = {row["id"]: row["eligibility_score"] for row in nodes}
    derived_by_base: dict[str, list[int]] = defaultdict(list)
    for row in nodes:
        base = clean_morph_base(row["morph_base"])
        if not base or base == row["normalized"]:
            continue
        derived_by_base[base].append(row["id"])
        for base_id in by_lemma.get(base, [])[:3]:
            if base_id != row["id"]:
                a, b = sorted((base_id, row["id"]))
                morphology_weights[(a, b)] = max(0.94, morphology_weights.get((a, b), 0))
    for base, derived in derived_by_base.items():
        if base in by_lemma or len(derived) < 2:
            continue
        anchor = max(derived, key=lambda node_id: score_by_id[node_id])
        for other in derived:
            if anchor != other:
                a, b = sorted((anchor, other))
                morphology_weights[(a, b)] = max(0.76, morphology_weights.get((a, b), 0))
    # Lexique MorphoBase is a useful recall signal, but it mixes direct
    # derivation, broader root analysis and occasional over-segmentation. Keep
    # it auditable without promoting it to a learner-visible derivation claim.
    layouts["morphology"] = [(a, b, weight) for (a, b), weight in sorted(morphology_weights.items())]

    sourced_derivations = demonette_edges(nodes)
    layouts["derivation"] = [
        (int(edge["a_id"]), int(edge["b_id"]), float(edge["weight"]))
        for edge in sourced_derivations
    ]

    sourced_semantics = dbnary_payload(nodes)
    sourced_p0 = wiktextract_p0_payload()
    layouts["semantic"] = [
        (int(edge["a_id"]), int(edge["b_id"]), float(edge["weight"]))
        for edge in sourced_semantics.get("edges", [])
    ]

    editorial_layout, official = seed_edges(nodes)
    layouts["editorial_seed"] = editorial_layout

    candidate_rows = []
    layout_rows = []
    for signal, edges in layouts.items():
        for a, b, weight in edges:
            if a not in id_set or b not in id_set:
                continue
            layout_rows.append((a, b, signal, weight, "{}", CREATED_AT))
            if signal in {"morphology", "spelling", "phonetic"}:
                source = SIGNAL_CONFIG.get(signal, {}).get("source", "lexique_400")
                candidate_rows.append(
                    (
                        a, b, relation_candidate(signal), signal, weight, source,
                        json.dumps({"generator": "mutual_sparse_tfidf" if signal != "morphology" else "lexique_morph_base"}),
                        "candidate", CREATED_AT,
                    )
                )
    sourced_semantic_pairs = {
        (int(edge["a_id"]), int(edge["b_id"])) for edge in sourced_semantics.get("edges", [])
    }
    conn.executemany(
        """
        INSERT OR IGNORE INTO edge_candidates(
          a_id,b_id,relation,signal,weight,source_id,details_json,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        candidate_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO edge_candidates(
          a_id,b_id,relation,signal,weight,source_id,details_json,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                a, b, "syn", "semantic", weight, "cfdict_reverse_local",
                json.dumps({"generator": "cfdict_gloss_overlap_candidate_only"}),
                "candidate", CREATED_AT,
            )
            for a, b, weight in gloss_candidate_edges
            if (a, b) not in sourced_semantic_pairs
        ],
    )
    conn.executemany("INSERT OR IGNORE INTO layout_links VALUES(?,?,?,?,?,?)", layout_rows)

    conn.executemany(
        """
        INSERT OR IGNORE INTO edge_candidates(
          a_id,b_id,relation,signal,weight,source_id,details_json,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                int(edge["a_id"]), int(edge["b_id"]), "fam", "derivation",
                float(edge["weight"]), "demonette_2",
                json.dumps({
                    "generator": "demonette_2_exact_lemma_pos",
                    "fid": edge["fid"], "rids": edge["source_records"],
                    "complexity": edge["complexity"], "orientation": edge["orientation"],
                    "subtype": edge["subtype"], "scheme": edge["scheme_2"],
                }, ensure_ascii=False),
                "sourced", CREATED_AT,
            )
            for edge in sourced_derivations
        ],
    )

    conn.executemany(
        """
        INSERT OR IGNORE INTO edge_candidates(
          a_id,b_id,relation,signal,weight,source_id,details_json,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                int(edge["a_id"]), int(edge["b_id"]), edge["relation"], "semantic",
                float(edge["weight"]), "dbnary_fr",
                json.dumps({
                    "generator": "dbnary_explicit_lexical_relation",
                    "subtype": edge["subtype"],
                    "source_entries": edge["source_entry_ids"],
                    "predicates": edge["source_predicates"],
                }, ensure_ascii=False),
                "sourced", CREATED_AT,
            )
            for edge in sourced_semantics.get("edges", [])
        ],
    )

    conn.executemany(
        "INSERT INTO lexical_entries(id,lexeme_id,entry_rank,source_id,source_url) VALUES(?,?,?,?,?)",
        [
            (
                entry["id"], int(entry["lexeme_id"]), int(entry["entry_rank"]),
                entry.get("source_id", "dbnary_fr"), entry["source_url"],
            )
            for entry in sourced_semantics.get("entries", []) + sourced_p0.get("entries", [])
        ],
    )
    conn.executemany(
        """
        INSERT INTO lexeme_senses(
          id,entry_id,lexeme_id,sense_number,definition_fr,examples_json,source_id
        ) VALUES(?,?,?,?,?,?,?)
        """,
        [
            (
                sense["id"], sense["entry_id"], int(sense["lexeme_id"]),
                str(sense["sense_number"]), sense["definition_fr"],
                json.dumps(sense.get("examples", []), ensure_ascii=False), sense.get("source_id", "dbnary_fr"),
            )
            for sense in sourced_semantics.get("senses", []) + sourced_p0.get("senses", [])
        ],
    )

    for item in official:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO official_edges(
              a_id,b_id,relation,dimension,subtype,direction,label,explanation,
              examples_json,confidence,review_status,reviewed_at,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item["a"], item["b"], item["relation"], item["dimension"], item["subtype"],
                item["direction"], item["label"], item.get("explanation") or "Prototype editorial seed; requires production re-review.",
                json.dumps(item.get("examples", []), ensure_ascii=False), 0.9, "reviewed", item.get("reviewed_at") or CREATED_AT, CREATED_AT,
            ),
        )
        if cursor.lastrowid:
            conn.execute(
                "INSERT OR IGNORE INTO official_edge_sources VALUES(?,?,?)",
                (
                    cursor.lastrowid, "wordcloud_editorial",
                    json.dumps({
                        "origin": "editorial_relation" if item.get("kind") == "editorial" else "prototype_seed",
                        "reviewer": item.get("reviewer"), "reviewed_at": item.get("reviewed_at"),
                        "source_note": item.get("source_note"),
                    }, ensure_ascii=False),
                ),
            )

    for item in sourced_derivations:
        a_id, b_id = int(item["a_id"]), int(item["b_id"])
        existing = conn.execute(
            "SELECT id FROM official_edges WHERE a_id=? AND b_id=? AND relation='fam' ORDER BY review_status='reviewed' DESC, id LIMIT 1",
            (a_id, b_id),
        ).fetchone()
        if existing:
            edge_id = existing["id"]
        else:
            direction = None
            if item["base_id"] is not None:
                direction = f"{int(item['base_id'])}->{int(item['derived_id'])}"
            explanation = (
                "Démonette 2.0：语义上是直接词族关系，但表面形式不是规则构词。"
                if item["complexity"] == "motiv-sem"
                else "Démonette 2.0 确认的直接派生或词性转换关系。"
            )
            cursor = conn.execute(
                """
                INSERT INTO official_edges(
                  a_id,b_id,relation,dimension,subtype,direction,label,explanation,
                  examples_json,confidence,review_status,reviewed_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    a_id, b_id, "fam", "derivational_morphology", item["subtype"],
                    direction, item["label"], explanation, "[]", float(item["confidence"]),
                    "sourced", None, CREATED_AT,
                ),
            )
            edge_id = cursor.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO official_edge_sources(edge_id,source_id,source_record) VALUES(?,?,?)",
            (
                edge_id, "demonette_2",
                json.dumps({
                    "fid": item["fid"], "rids": item["source_records"],
                    "complexity": item["complexity"], "orientation": item["orientation"],
                    "scheme_1": item["scheme_1"], "scheme_2": item["scheme_2"],
                }, ensure_ascii=False),
            ),
        )

    for item in sourced_semantics.get("edges", []):
        a_id, b_id = int(item["a_id"]), int(item["b_id"])
        existing = conn.execute(
            "SELECT id FROM official_edges WHERE a_id=? AND b_id=? AND relation=? ORDER BY review_status='reviewed' DESC, id LIMIT 1",
            (a_id, b_id, item["relation"]),
        ).fetchone()
        if existing:
            edge_id = existing["id"]
        else:
            explanation = (
                "Wiktionnaire 通过 DBnary 明示标注的近义关系。"
                if item["relation"] == "syn"
                else "Wiktionnaire 通过 DBnary 明示标注的反义关系。"
            )
            cursor = conn.execute(
                """
                INSERT INTO official_edges(
                  a_id,b_id,relation,dimension,subtype,direction,label,explanation,
                  examples_json,confidence,review_status,reviewed_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    a_id, b_id, item["relation"], "lexical_semantics", item["subtype"],
                    None, item["label"], explanation, "[]", float(item["confidence"]),
                    "sourced", None, CREATED_AT,
                ),
            )
            edge_id = cursor.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO official_edge_sources(edge_id,source_id,source_record) VALUES(?,?,?)",
            (
                edge_id, "dbnary_fr",
                json.dumps({
                    "entries": item["source_entry_ids"],
                    "predicates": item["source_predicates"],
                }, ensure_ascii=False),
            ),
        )

    if DEMONETTE_APPROVED_PATH.exists():
        approved_payload = json.loads(DEMONETTE_APPROVED_PATH.read_text(encoding="utf-8"))
        import_summary = {key: value for key, value in approved_payload.items() if key != "edges"}
        conn.execute(
            "INSERT OR REPLACE INTO build_metadata(key,value) VALUES('demonette_import_summary',?)",
            (json.dumps(import_summary, ensure_ascii=False, separators=(",", ":")),),
        )
    if DBNARY_APPROVED_PATH.exists():
        import_summary = {
            key: value for key, value in sourced_semantics.items()
            if key not in {"entries", "senses", "edges"}
        }
        conn.execute(
            "INSERT OR REPLACE INTO build_metadata(key,value) VALUES('dbnary_import_summary',?)",
            (json.dumps(import_summary, ensure_ascii=False, separators=(",", ":")),),
        )

    uf = UnionFind(ids)
    for edges in layouts.values():
        for a, b, _ in edges:
            uf.union(a, b)
    for a, b, score, signal in sorted(fallback_edges, key=lambda item: (-item[2], item[0], item[1])):
        if uf.union(a, b):
            weight = max(0.08, min(0.32, score * 0.42))
            conn.execute(
                "INSERT OR IGNORE INTO layout_links VALUES(?,?,?,?,?,?)",
                (a, b, "skeleton", weight, json.dumps({"method": "nonmutual", "signal": signal}), CREATED_AT),
            )
        if uf.components == 1:
            break

    if uf.components > 1:
        ordered = sorted(nodes, key=lambda row: (fold(row["lemma"]), row["id"]))
        candidates = []
        for left, right in zip(ordered, ordered[1:]):
            if uf.find(left["id"]) != uf.find(right["id"]):
                left_fold, right_fold = fold(left["lemma"]), fold(right["lemma"])
                common = 0
                for a_char, b_char in zip(left_fold, right_fold):
                    if a_char != b_char:
                        break
                    common += 1
                score = common / max(1, max(len(left_fold), len(right_fold)))
                candidates.append((score, left["id"], right["id"]))
        for score, a, b in sorted(candidates, reverse=True):
            if uf.union(a, b):
                a, b = sorted((a, b))
                conn.execute(
                    "INSERT OR IGNORE INTO layout_links VALUES(?,?,?,?,?,?)",
                    (a, b, "skeleton", max(0.03, score * 0.15), json.dumps({"method": "lexical_component_bridge"}), CREATED_AT),
                )
            if uf.components == 1:
                break

    if uf.components != 1:
        representatives: dict[int, int] = {}
        for node_id in ids:
            representatives.setdefault(uf.find(node_id), node_id)
        reps = sorted(representatives.values())
        for a, b in zip(reps, reps[1:]):
            if uf.union(a, b):
                conn.execute(
                    "INSERT OR IGNORE INTO layout_links VALUES(?,?,?,?,?,?)",
                    (min(a, b), max(a, b), "skeleton", 0.02, json.dumps({"method": "last_resort_component_chain"}), CREATED_AT),
                )

    conn.commit()

    combined: dict[tuple[int, int], list[tuple[str, float]]] = defaultdict(list)
    for row in conn.execute("SELECT a_id,b_id,signal,weight FROM layout_links"):
        combined[(row["a_id"], row["b_id"])].append((row["signal"], row["weight"]))
    signal_factor = {
        "semantic": 1.0, "derivation": 1.15, "morphology": 0.35, "spelling": 0.55,
        "phonetic": 0.6, "editorial_seed": 1.3, "skeleton": 0.22,
    }
    graph_edges = []
    for (a, b), signals in combined.items():
        remaining = 1.0
        for signal, weight in signals:
            remaining *= 1 - min(0.95, weight * signal_factor[signal])
        graph_edges.append(
            {
                "source": str(a), "target": str(b), "weight": round(max(0.01, 1 - remaining), 6),
                "signals": [signal for signal, _ in sorted(signals)],
                "signal_weights": {signal: round(weight, 6) for signal, weight in sorted(signals)},
            }
        )
    graph_nodes = []
    for row in nodes:
        digest = hashlib.sha256(f"{row['id']}:{row['normalized']}".encode()).digest()
        angle = int.from_bytes(digest[:4], "big") / 2**32 * math.tau
        radius = 0.1 + int.from_bytes(digest[4:8], "big") / 2**32
        graph_nodes.append(
            {
                "key": str(row["id"]),
                "x": round(math.cos(angle) * radius, 6),
                "y": round(math.sin(angle) * radius, 6),
                "size": round(1 + math.log1p(max(0, row["flelex_frequency"] or 0)) * 0.35, 4),
                "level": row["cefr_level"] or "",
                "frequency": round(max(0, row["flelex_frequency"] or 0), 6),
                "diversity": round(max(0, row["contextual_diversity"] or 0), 6),
                "status": row["status"],
            }
        )
    signal_counts = dict(conn.execute("SELECT signal,COUNT(*) FROM layout_links GROUP BY signal").fetchall())
    payload = {
        "meta": {
            "version": "layout-input-v2-learning-space",
            "created_at": CREATED_AT,
            "node_count": len(graph_nodes),
            "eligible_count": sum(row["status"] == "eligible" for row in nodes),
            "support_node_count": sum(row["status"] != "eligible" for row in nodes),
            "edge_count": len(graph_edges),
            "signal_counts": signal_counts,
            "components": uf.components,
        },
        "nodes": graph_nodes,
        "edges": graph_edges,
    }
    GRAPH_INPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    conn.close()
    print(json.dumps(payload["meta"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
