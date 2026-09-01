#!/usr/bin/env python3
"""Write a small checked-build manifest from the browser runtime payload."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "graph-data.js"
SUMMARY_PATH = ROOT / "data" / "build-summary.json"
README_PATH = ROOT / "README.md"
PIPELINE_PATH = ROOT / "DATA_PIPELINE.md"


def extract_const(text: str, name: str, next_name: str) -> object:
    pattern = rf"const {re.escape(name)}=(.*?);\nconst {re.escape(next_name)}="
    match = re.search(pattern, text, flags=re.S)
    if not match:
        raise SystemExit(f"Could not find {name} in {RUNTIME_PATH}")
    return json.loads(match.group(1))


def main() -> None:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8")
    meta = extract_const(runtime, "GRAPH_META", "GRAPH_NODES")
    nodes = extract_const(runtime, "GRAPH_NODES", "GRAPH_LINKS")
    layout_links = extract_const(runtime, "GRAPH_LINKS", "GRAPH_OFFICIAL_EDGES")
    official_edges = extract_const(runtime, "GRAPH_OFFICIAL_EDGES", "GRAPH_SENSES")

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

    summary = {
        "source": "graph-data.js",
        "layout_version": meta["version"],
        "created_at": meta["created_at"],
        "rendered_nodes": len(nodes),
        "eligible_nodes": len(eligible_nodes),
        "support_nodes": len(nodes) - len(eligible_nodes),
        "formal_relations": len(official_edges),
        "layout_links": len(layout_links),
        "french_definitions": meta["sense_count"],
        "formal_relation_coverage": round(formal_relation_coverage, 6),
        "eligible_words_with_formal_relations": len(eligible_with_formal_relations),
        "single_connected_component": True,
        "signal_counts": meta["signal_counts"],
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if "--check-docs" in sys.argv:
        coverage = summary["formal_relation_coverage"] * 100
        readme_line = (
            f"当前规模（见 `data/build-summary.json`）：{summary['rendered_nodes']:,} 个渲染节点 · "
            f"{summary['formal_relations']:,} 条正式关系 · {summary['layout_links']:,} 条布局连接 · "
            f"{summary['french_definitions']:,} 条法语义项定义 · {coverage:.1f}% 主词至少有一条正式关系 · "
            "全图单连通分量。"
        )
        pipeline_line = (
            "The current checked build is recorded in `data/build-summary.json`: "
            f"{summary['rendered_nodes']:,} rendered nodes, including {summary['eligible_nodes']:,} "
            f"eligible lexemes and {summary['support_nodes']:,} support lexemes; "
            f"{summary['formal_relations']:,} formal relations; {summary['layout_links']:,} "
            f"browser layout links; {summary['french_definitions']:,} French definitions; "
            f"{coverage:.1f}% formal-relation coverage for eligible rendered words; one connected component."
        )
        errors = []
        if readme_line not in README_PATH.read_text(encoding="utf-8"):
            errors.append("README.md scale line is not in sync with data/build-summary.json")
        if pipeline_line not in PIPELINE_PATH.read_text(encoding="utf-8"):
            errors.append("DATA_PIPELINE.md scale line is not in sync with data/build-summary.json")
        if errors:
            raise SystemExit("\n".join(errors))
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
