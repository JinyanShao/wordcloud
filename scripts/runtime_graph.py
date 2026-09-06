#!/usr/bin/env python3
"""Shared helpers for validating and summarizing the committed runtime graph."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "graph-data.js"
SUMMARY_PATH = ROOT / "data" / "build-summary.json"
README_PATH = ROOT / "README.md"
PIPELINE_PATH = ROOT / "DATA_PIPELINE.md"

VALID_REVIEW_STATUSES = {"sourced", "editorial_seed", "ai_reviewed", "editorial_reviewed", "human_reviewed"}


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def extract_const(text: str, name: str, next_name: str) -> Any:
    pattern = rf"const {re.escape(name)}=(.*?);\nconst {re.escape(next_name)}="
    match = re.search(pattern, text, flags=re.S)
    if not match:
        raise SystemExit(f"Could not find {name} in {RUNTIME_PATH}")
    return json.loads(match.group(1))


def load_runtime(path: Path = RUNTIME_PATH) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "meta": extract_const(text, "GRAPH_META", "GRAPH_NODES"),
        "nodes": extract_const(text, "GRAPH_NODES", "GRAPH_LINKS"),
        "links": extract_const(text, "GRAPH_LINKS", "GRAPH_OFFICIAL_EDGES"),
        "official_edges": extract_const(text, "GRAPH_OFFICIAL_EDGES", "GRAPH_SENSES"),
        "senses": json.loads(re.search(r"const GRAPH_SENSES=(.*?);\n?$", text, flags=re.S).group(1)),
    }


class UnionFind:
    def __init__(self, ids: list[int]):
        self.parent = {item: item for item in ids}

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        a_root, b_root = self.find(a), self.find(b)
        if a_root != b_root:
            self.parent[b_root] = a_root


def connectivity(node_ids: list[int], links: list[list[Any]]) -> dict[str, int | bool]:
    uf = UnionFind(node_ids)
    degree = Counter()
    node_set = set(node_ids)
    for edge in links:
        a, b = edge[0], edge[1]
        if a in node_set and b in node_set:
            uf.union(a, b)
            degree[a] += 1
            degree[b] += 1
    component_count = len({uf.find(node_id) for node_id in node_ids}) if node_ids else 0
    isolated_count = sum(1 for node_id in node_ids if degree[node_id] == 0)
    return {
        "component_count": component_count,
        "isolated_count": isolated_count,
        "single_connected_component": component_count == 1 and isolated_count == 0,
    }


def build_summary(runtime: dict[str, Any]) -> dict[str, Any]:
    nodes = runtime["nodes"]
    links = runtime["links"]
    official_edges = runtime["official_edges"]
    meta = runtime["meta"]
    node_ids = [node[0] for node in nodes]

    official_endpoint_ids = set()
    for edge in official_edges:
        official_endpoint_ids.add(edge[0])
        official_endpoint_ids.add(edge[1])

    eligible_nodes = [node for node in nodes if node[11] == "eligible"]
    eligible_with_formal_relations = [
        node for node in eligible_nodes if node[0] in official_endpoint_ids
    ]
    formal_relation_coverage = (
        len(eligible_with_formal_relations) / len(eligible_nodes) if eligible_nodes else 0
    )
    graph_connectivity = connectivity(node_ids, links)

    return {
        "source": "graph-data.js",
        "layout_version": meta["version"],
        "created_at": meta["created_at"],
        "rendered_nodes": len(nodes),
        "eligible_nodes": len(eligible_nodes),
        "support_nodes": len(nodes) - len(eligible_nodes),
        "formal_relations": len(official_edges),
        "layout_links": len(links),
        "french_definitions": meta["sense_count"],
        "formal_relation_coverage": round(formal_relation_coverage, 6),
        "eligible_words_with_formal_relations": len(eligible_with_formal_relations),
        **graph_connectivity,
        "signal_counts": meta["signal_counts"],
    }


def docs_expected_lines(summary: dict[str, Any]) -> tuple[str, str]:
    coverage = summary["formal_relation_coverage"] * 100
    connected = (
        "全图单连通分量"
        if summary["single_connected_component"]
        else f"{summary['component_count']} 个连通分量"
    )
    readme_line = (
        f"当前规模（见 `data/build-summary.json`）：{summary['rendered_nodes']:,} 个渲染节点 · "
        f"{summary['formal_relations']:,} 条正式关系 · {summary['layout_links']:,} 条布局连接 · "
        f"{summary['french_definitions']:,} 条法语义项定义 · {coverage:.1f}% 主词至少有一条正式关系 · "
        f"{connected}。"
    )
    component_text = (
        "one connected component"
        if summary["component_count"] == 1
        else f"{summary['component_count']} connected components"
    )
    pipeline_line = (
        "The current checked build is recorded in `data/build-summary.json`: "
        f"{summary['rendered_nodes']:,} rendered nodes, including {summary['eligible_nodes']:,} "
        f"eligible lexemes and {summary['support_nodes']:,} support lexemes; "
        f"{summary['formal_relations']:,} formal relations; {summary['layout_links']:,} "
        f"browser layout links; {summary['french_definitions']:,} French definitions; "
        f"{coverage:.1f}% formal-relation coverage for eligible rendered words; "
        f"{component_text}."
    )
    return readme_line, pipeline_line
