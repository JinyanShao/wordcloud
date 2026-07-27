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
DB_PATH = ROOT / "data" / "processed" / "maillage.sqlite"
GRAPH_INPUT = ROOT / "data" / "processed" / "graph-input.json"
SEED_PATH = ROOT / "data" / "processed" / "editorial-seed.json"
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
            for char in chinese:
                if char not in ZH_STOP:
                    features.add("char:" + char)
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
    return {"semantic": "syn", "derivation": "fam", "spelling": "trap", "phonetic": "trap"}[signal]


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
    def resolve(word: str) -> int | None:
        normalized = normalize(word)
        pos = seed_pos.get(normalized)
        if pos and (normalized, pos) in by_key:
            return by_key[(normalized, pos)]
        values = by_word.get(normalized, [])
        return values[0] if len(values) == 1 else None
    layout: list[tuple[int, int, float]] = []
    official: list[dict[str, object]] = []
    for edge in seed["edges"]:
        original_a, original_b = resolve(edge["a"]), resolve(edge["b"])
        if original_a is None or original_b is None or original_a == original_b:
            continue
        a, b = sorted((original_a, original_b))
        layout.append((a, b, 1.0))
        relation = "compare" if edge["type"] == "axis" else edge["type"]
        official.append(
            {
                "a": a, "b": b, "relation": relation,
                "dimension": "prototype-axis" if edge["type"] == "axis" else None,
                "subtype": None,
                "direction": f"{original_a}->{original_b}" if edge["type"] in {"axis", "cause"} else None,
                "label": edge.get("label") or relation,
            }
        )
    return layout, official


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
        if row["status"] == "eligible" or (row["normalized"], row["pos"]) in seed_keys
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

    layouts: dict[str, list[tuple[int, int, float]]] = {}
    fallback_edges: list[tuple[int, int, float, str]] = []
    feature_builders = {
        "semantic": lambda row: semantic_features(row["gloss_zh"]),
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

    by_lemma: dict[str, list[int]] = defaultdict(list)
    for row in nodes:
        by_lemma[row["normalized"]].append(row["id"])
    derivation_weights: dict[tuple[int, int], float] = {}
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
                derivation_weights[(a, b)] = max(0.94, derivation_weights.get((a, b), 0))
    for base, derived in derived_by_base.items():
        if base in by_lemma or len(derived) < 2:
            continue
        anchor = max(derived, key=lambda node_id: score_by_id[node_id])
        for other in derived:
            if anchor != other:
                a, b = sorted((anchor, other))
                derivation_weights[(a, b)] = max(0.76, derivation_weights.get((a, b), 0))
    layouts["derivation"] = [(a, b, weight) for (a, b), weight in sorted(derivation_weights.items())]

    editorial_layout, official = seed_edges(nodes)
    layouts["editorial_seed"] = editorial_layout

    candidate_rows = []
    layout_rows = []
    for signal, edges in layouts.items():
        for a, b, weight in edges:
            if a not in id_set or b not in id_set:
                continue
            layout_rows.append((a, b, signal, weight, "{}", CREATED_AT))
            if signal in {"semantic", "derivation", "spelling", "phonetic"}:
                source = SIGNAL_CONFIG.get(signal, {}).get("source", "lexique_400")
                candidate_rows.append(
                    (
                        a, b, relation_candidate(signal), signal, weight, source,
                        json.dumps({"generator": "mutual_sparse_tfidf" if signal != "derivation" else "lexique_morph_base"}),
                        "candidate", CREATED_AT,
                    )
                )
    conn.executemany(
        """
        INSERT OR IGNORE INTO edge_candidates(
          a_id,b_id,relation,signal,weight,source_id,details_json,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        candidate_rows,
    )
    conn.executemany("INSERT OR IGNORE INTO layout_links VALUES(?,?,?,?,?,?)", layout_rows)

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
                item["direction"], item["label"], "Prototype editorial seed; requires production re-review.",
                "[]", 0.9, "reviewed", CREATED_AT, CREATED_AT,
            ),
        )
        if cursor.lastrowid:
            conn.execute(
                "INSERT OR IGNORE INTO official_edge_sources VALUES(?,?,?)",
                (cursor.lastrowid, "maillage_editorial", f"{item['a']}:{item['b']}"),
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
        "semantic": 1.0, "derivation": 1.15, "spelling": 0.55,
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
            }
        )
    signal_counts = dict(conn.execute("SELECT signal,COUNT(*) FROM layout_links GROUP BY signal").fetchall())
    payload = {
        "meta": {
            "version": "layout-v1",
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
