#!/usr/bin/env python3
"""Validate committed static runtime artifacts in a clean checkout."""

from __future__ import annotations

import json
import math
from collections import Counter

from runtime_graph import (
    PIPELINE_PATH,
    README_PATH,
    SUMMARY_PATH,
    VALID_REVIEW_STATUSES,
    build_summary,
    docs_expected_lines,
    load_runtime,
)


VALID_RELATIONS = {"syn", "compare", "fam", "drift", "trap", "ant", "cause"}


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    runtime = load_runtime()
    nodes = runtime["nodes"]
    links = runtime["links"]
    official_edges = runtime["official_edges"]
    senses = runtime["senses"]
    node_ids = [node[0] for node in nodes]
    node_set = set(node_ids)

    if len(node_ids) != len(node_set):
        counts = Counter(node_ids)
        duplicate = next(node_id for node_id, count in counts.items() if count > 1)
        fail(f"duplicate runtime node id: {duplicate}")

    for edge in links:
        a, b = edge[0], edge[1]
        if a == b:
            fail(f"layout self-loop: {a}")
        if a not in node_set or b not in node_set:
            fail(f"layout edge endpoint missing: {a}, {b}")

    relation_keys = set()
    for edge in official_edges:
        a, b, relation, dimension, subtype = edge[0], edge[1], edge[2], edge[3], edge[4]
        if a == b:
            fail(f"official self-loop: {a}")
        if a not in node_set or b not in node_set:
            fail(f"official edge endpoint missing: {a}, {b}")
        if relation not in VALID_RELATIONS:
            fail(f"invalid official relation: {relation}")
        if edge[9] not in VALID_REVIEW_STATUSES:
            fail(f"invalid review status: {edge[9]}")
        key = (min(a, b), max(a, b), relation, dimension, subtype)
        if key in relation_keys:
            fail(f"duplicate official relation: {key}")
        relation_keys.add(key)

    for lexeme_id in senses:
        if int(lexeme_id) not in node_set:
            fail(f"sense group references missing lexeme: {lexeme_id}")

    computed = build_summary(runtime)
    recorded = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    meta = runtime["meta"]
    meta_expected = {
        "node_count": len(nodes),
        "layout_link_count": len(links),
        "official_edge_count": len(official_edges),
        "sense_count": recorded["french_definitions"],
    }
    for key, expected in meta_expected.items():
        if meta.get(key) != expected:
            fail(f"GRAPH_META.{key}={meta.get(key)!r}, expected {expected!r}")
    if computed != recorded:
        fail(f"{SUMMARY_PATH} does not match graph-data.js")

    readme_line, pipeline_line = docs_expected_lines(recorded)
    if readme_line not in README_PATH.read_text(encoding="utf-8"):
        fail("README.md public scale line is not in sync with data/build-summary.json")
    if pipeline_line not in PIPELINE_PATH.read_text(encoding="utf-8"):
        fail("DATA_PIPELINE.md public scale line is not in sync with data/build-summary.json")

    coverage = recorded["formal_relation_coverage"]
    if not math.isclose(coverage, computed["formal_relation_coverage"], rel_tol=0, abs_tol=0.000001):
        fail("formal relation coverage drifted")
    if recorded["component_count"] != computed["component_count"]:
        fail("connected component count drifted")
    if recorded["isolated_count"] != computed["isolated_count"]:
        fail("isolated count drifted")
    if recorded["single_connected_component"] != computed["single_connected_component"]:
        fail("single connected component flag drifted")

    print(json.dumps({
        "ok": True,
        "nodes": len(nodes),
        "layout_links": len(links),
        "official_edges": len(official_edges),
        "components": recorded["component_count"],
        "isolated": recorded["isolated_count"],
    }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
