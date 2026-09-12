#!/usr/bin/env python3
"""Build a deterministic, static product-gap audit from production inputs only."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data/build-summary.json"
LEXICON = ROOT / "data/processed/eligible-lexicon.csv"
GRAPH = ROOT / "graph-data.js"
RUNTIME = ROOT / "learner-sense-content.js"
OUT = ROOT / "data/phase4/product-gap-audit.json"
DOC = ROOT / "docs/phase4-product-gap-audit.md"

CORE_POS = ("NOM", "VER", "ADJ", "ADV")
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
FREQUENCY_BANDS = (
    ("flelex_50_plus", 50.0, None),
    ("flelex_10_to_49_999", 10.0, 50.0),
    ("flelex_1_to_9_999", 1.0, 10.0),
    ("flelex_below_1", None, 1.0),
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def graph_constant(name: str) -> object:
    raw = GRAPH.read_text(encoding="utf-8")
    prefix = f"const {name}="
    start = raw.index(prefix) + len(prefix)
    try:
        end = raw.index(";\nconst ", start)
    except ValueError:
        end = raw.rindex(";")
    return json.loads(raw[start:end])


def load_runtime() -> dict[str, object]:
    raw = RUNTIME.read_text(encoding="utf-8")
    match = re.search(r"const LEARNER_SENSE_CONTENT=(.*);\n$", raw, re.S)
    if not match:
        raise SystemExit("missing learner runtime payload")
    return json.loads(match.group(1))


def percentage(numerator: int, denominator: int) -> float:
    return round((100 * numerator / denominator) if denominator else 0.0, 2)


def bucket(frequency: float) -> str:
    for name, lower, upper in FREQUENCY_BANDS:
        if (lower is None or frequency >= lower) and (upper is None or frequency < upper):
            return name
    raise AssertionError(frequency)


def count_shape(rows: list[dict[str, object]], aid_ids: set[int]) -> dict[str, int | float]:
    total = len(rows)
    aids = sum(int(row["id"]) in aid_ids for row in rows)
    return {"searchable": total, "learner_aids": aids, "coverage_percent": percentage(aids, total)}


def missing_record(row: dict[str, object], family_ids: set[int], senses: dict[str, object]) -> dict[str, object]:
    lexeme_id = int(row["id"])
    stable_key = f"{row['lemma']}|{row['pos']}"
    return {
        "stable_lexeme_key": stable_key,
        "runtime_lexeme_id": lexeme_id,
        "lemma": row["lemma"],
        "pos": row["pos"],
        "cefr": row["cefr_level"],
        "flelex_frequency": float(row["flelex_frequency"] or 0),
        "lexique_frequency": float(row["lexique_frequency"] or 0),
        "contextual_diversity": float(row["contextual_diversity"] or 0),
        "runtime_status": "eligible",
        "has_sourced_family": lexeme_id in family_ids,
        "source_sense_count": sum(len(entry["senses"]) for entry in senses.get(str(lexeme_id), [])),
        "has_learner_aid": False,
        "learner_aid_status": "blocked_search_only" if stable_key in {"travers|NOM", "cesse|NOM"} else "missing",
    }


def markdown_table(rows: list[dict[str, object]], limit: int = 12) -> list[str]:
    lines = ["| 词条 | POS | CEFR | FLELex | Lexique | CD | family | senses |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows[:limit]:
        key = row["stable_lexeme_key"].replace("|", "\\|")
        lines.append(
            f"| {key} | {row['pos']} | {row['cefr']} | "
            f"{row['flelex_frequency']:.3f} | {row['lexique_frequency']:.3f} | "
            f"{row['contextual_diversity']:.3f} | {'yes' if row['has_sourced_family'] else 'no'} | {row['source_sense_count']} |"
        )
    return lines


def build() -> dict[str, object]:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    with LEXICON.open(encoding="utf-8", newline="") as source:
        lexicon = list(csv.DictReader(source))
    runtime = load_runtime()
    nodes = graph_constant("GRAPH_NODES")
    edges = graph_constant("GRAPH_OFFICIAL_EDGES")
    senses = graph_constant("GRAPH_SENSES")

    aid_records = runtime["records"]
    aid_ids = {int(item["lexeme_id"]) for item in aid_records}
    aid_keys = {item["stable_lexeme_key"] for item in aid_records}
    if len(aid_records) != 598 or len(aid_ids) != 598 or len(aid_keys) != 598:
        raise SystemExit("unexpected production learner runtime identities")
    phase2 = sum(item["cohort"] == "phase2c" for item in aid_records)
    phase3 = sum(item["cohort"] == "phase3" for item in aid_records)
    if phase2 != 99 or phase3 != 499:
        raise SystemExit("unexpected learner runtime cohorts")

    if len(lexicon) != summary["eligible_nodes"] or len(nodes) != summary["rendered_nodes"]:
        raise SystemExit("production denominators do not match build summary")
    eligible_ids = {int(row["id"]) for row in lexicon}
    if not aid_ids <= eligible_ids:
        raise SystemExit("learner aid outside eligible lexical entries")

    family_edges = [
        edge for edge in edges
        if edge[2] == "fam" and edge[3] == "derivational_morphology" and edge[9] == "sourced"
    ]
    family_ids = {int(endpoint) for edge in family_edges for endpoint in edge[:2]}
    if len(family_edges) != 3077 or len(family_ids) != 4652:
        raise SystemExit("unexpected sourced family boundary")

    by_level = {level: [row for row in lexicon if row["cefr_level"] == level] for level in LEVELS}
    by_pos = {pos: [row for row in lexicon if row["pos"] == pos] for pos in CORE_POS}
    coverage = {
        "denominator_definition": {
            "searchable": "all 9,067 rendered lexical entries, including 21 support entries",
            "eligible_content": "9,046 eligible main-map lexical entries; this is the CEFR/POS coverage denominator",
        },
        "overall": {
            "searchable": summary["rendered_nodes"],
            "eligible_content": summary["eligible_nodes"],
            "support": summary["support_nodes"],
            "learner_aids": len(aid_records),
            "searchable_coverage_percent": percentage(len(aid_records), summary["rendered_nodes"]),
            "eligible_content_coverage_percent": percentage(len(aid_records), summary["eligible_nodes"]),
            "phase2c": phase2,
            "phase3": phase3,
        },
        "cefr": {level: count_shape(by_level[level], aid_ids) for level in LEVELS},
        "pos": {pos: count_shape(by_pos[pos], aid_ids) for pos in CORE_POS},
        "cefr_by_pos": {
            level: {pos: count_shape([row for row in by_level[level] if row["pos"] == pos], aid_ids) for pos in CORE_POS}
            for level in LEVELS
        },
        "flelex_frequency_bands": {
            name: count_shape([row for row in lexicon if bucket(float(row["flelex_frequency"] or 0)) == name], aid_ids)
            for name, _, _ in FREQUENCY_BANDS
        },
    }

    missing_by_level = {}
    for level in ("A1", "A2", "B1", "B2"):
        rows = [row for row in by_level[level] if int(row["id"]) not in aid_ids]
        rows.sort(key=lambda row: (-float(row["flelex_frequency"] or 0), -float(row["lexique_frequency"] or 0), -float(row["contextual_diversity"] or 0), row["lemma"], row["pos"]))
        missing_by_level[level] = [missing_record(row, family_ids, senses) for row in rows[:50]]

    all_missing = [row for row in lexicon if int(row["id"]) not in aid_ids]
    high_family = [row for row in all_missing if int(row["id"]) in family_ids]
    high_family.sort(key=lambda row: (-float(row["flelex_frequency"] or 0), -float(row["lexique_frequency"] or 0), row["lemma"], row["pos"]))
    family_cross = {
        "aid_and_sourced_family": sum(identifier in aid_ids and identifier in family_ids for identifier in eligible_ids),
        "aid_without_sourced_family": sum(identifier in aid_ids and identifier not in family_ids for identifier in eligible_ids),
        "sourced_family_without_aid": sum(identifier not in aid_ids and identifier in family_ids for identifier in eligible_ids),
        "neither_on_eligible_content": sum(identifier not in aid_ids and identifier not in family_ids for identifier in eligible_ids),
        "high_value_family_gaps": [missing_record(row, family_ids, senses) for row in high_family[:50]],
    }

    polysemous = [row for row in lexicon if sum(len(entry["senses"]) for entry in senses.get(row["id"], [])) >= 4]
    structural_gaps = {
        "interpretation": "Static proxies only: no user clicks, completion, or retention analytics are available.",
        "polysemy": {
            "four_or_more_source_senses": count_shape(polysemous, aid_ids),
            "under_four_source_senses": count_shape([row for row in lexicon if row not in polysemous], aid_ids),
        },
        "family": {
            "eligible_with_sourced_family": count_shape([row for row in lexicon if int(row["id"]) in family_ids], aid_ids),
            "eligible_without_sourced_family": count_shape([row for row in lexicon if int(row["id"]) not in family_ids], aid_ids),
        },
        "frequency": coverage["flelex_frequency_bands"],
    }
    recommendations = {
        "proxies_not_user_analytics": ["CEFR", "FLELex frequency", "Lexique frequency", "contextual diversity", "source-sense count", "sourced family membership"],
        "strategies": {
            "A_expand_500": {"learner_value": "broad but increasingly diluted", "semantic_authoring_cost": "very high", "qa_cost": "very high", "implementation_complexity": "medium", "risk": "high sense-priority and quality risk", "diminishing_returns": "high"},
            "B_target_100_200_gaps": {"learner_value": "high: closes frequent A1/A2 and family-connected gaps", "semantic_authoring_cost": "medium", "qa_cost": "medium", "implementation_complexity": "low", "risk": "manageable with learner-first review", "diminishing_returns": "low to medium"},
            "C_deepen_598": {"learner_value": "medium, concentrated on current users", "semantic_authoring_cost": "medium", "qa_cost": "medium", "implementation_complexity": "medium", "risk": "feature scope may outpace coverage need", "diminishing_returns": "medium"},
            "D_family_learning_first": {"learner_value": "medium-high for connected vocabulary", "semantic_authoring_cost": "low-medium", "qa_cost": "medium", "implementation_complexity": "medium", "risk": "must not overstate sourced morphology as productive rules", "diminishing_returns": "medium"},
            "E_targeted_mix": {"learner_value": "highest: targeted gap closure plus limited family context", "semantic_authoring_cost": "medium", "qa_cost": "medium", "implementation_complexity": "medium", "risk": "requires fixed scope and separate semantic review", "diminishing_returns": "low"},
        },
        "recommendation": "Strategy E, led by Strategy B: review a bounded 100–200 high-frequency A1/A2/B1 gap list first, then add family-learning context only where an existing sourced relation is pedagogically useful. Do not start another undifferentiated 500-item batch.",
    }
    result = {
        "schema_version": 1,
        "scope": "Phase 4A static production gap audit; no learner prose or sense selection is generated.",
        "inputs": {"build_summary_sha256": hashlib.sha256(SUMMARY.read_bytes()).hexdigest(), "runtime_sha256": hashlib.sha256(RUNTIME.read_bytes()).hexdigest(), "eligible_lexicon_sha256": hashlib.sha256(LEXICON.read_bytes()).hexdigest(), "graph_runtime_sha256": hashlib.sha256(GRAPH.read_bytes()).hexdigest()},
        "coverage": coverage,
        "top_missing_by_cefr": missing_by_level,
        "family_x_learner": family_cross,
        "coverage_quality": structural_gaps,
        "recommendation": recommendations,
    }
    result["artifact_hash"] = sha256(result)
    return result


def write_markdown(audit: dict[str, object]) -> str:
    coverage = audit["coverage"]
    overall = coverage["overall"]
    family = audit["family_x_learner"]
    lines = [
        "# Phase 4A — Product Gap Audit",
        "",
        "这是对 production 静态输入的覆盖审计，不是用户行为分析；不生成 learner content，也不改变任何事实数据。",
        "",
        "## 覆盖现状",
        "",
        f"- searchable lexical entries：{overall['searchable']}；eligible main-map entries：{overall['eligible_content']}；support entries：{overall['support']}。",
        f"- learner aids：{overall['learner_aids']}（eligible content 的 {overall['eligible_content_coverage_percent']}%；全部 searchable 的 {overall['searchable_coverage_percent']}%）。",
        f"- cohorts：Phase 2C {overall['phase2c']} reviewed；Phase 3 {overall['phase3']} externally semantic-authored。",
        "",
        "| CEFR | eligible entries | learner aids | coverage |",
        "|---|---:|---:|---:|",
    ]
    for level, values in coverage["cefr"].items():
        lines.append(f"| {level} | {values['searchable']} | {values['learner_aids']} | {values['coverage_percent']}% |")
    lines += [
        "",
        "## 最大结构性缺口",
        "",
        f"- 整体覆盖仍只有 {overall['eligible_content_coverage_percent']}%；A1、A2 并非已覆盖完毕，且 B1/B2 覆盖明显更低。",
        f"- POS 不均衡：NOM 的覆盖低于 VER、ADJ 和 ADV；完整 CEFR × POS 与 frequency band 明细见 JSON。",
        f"- {family['sourced_family_without_aid']} 个 sourced-family members 没有 learner aid；现有 {family['aid_and_sourced_family']} 条 learner aids 有 sourced family，{family['aid_without_sourced_family']} 条没有。",
        "- 没有生产点击、完成或留存数据；CEFR、FLELex、Lexique、contextual diversity、多义性和 family 连通性只是静态排序 proxy，不能称作用户需求。",
        "",
        "## Raw frequency-ranked gaps（非 production-ready；每组展示前 12，完整前 50 在 JSON）",
        "",
        "该列表只按 FLELex、Lexique 和 contextual diversity 排序；raw frequency rank 不等于 learner-priority semantic rank。`source_sense_count = 0` 的词不能直接进入 exact-sense production，已知 blocked records 也不能进入 production candidate set。",
        "",
    ]
    for level in ("A1", "A2", "B1", "B2"):
        lines += [f"### {level}", ""] + markdown_table(audit["top_missing_by_cefr"][level]) + [""]
    lines += [
        "## 策略比较与推荐",
        "",
        "| 策略 | learner value | authoring / QA 成本 | 风险与边际收益 |",
        "|---|---|---|---|",
        "| A 再扩 500 | 覆盖面大但递减 | 很高 / 很高 | sense-priority 与质量风险高，边际收益高递减 |",
        "| B 补 100–200 高价值缺口 | 高 | 中 / 中 | learner-first review 可控，递减低到中 |",
        "| C 加深现有 598 | 中 | 中 / 中 | 价值集中于已覆盖词，可能回避真正缺口 |",
        "| D family-learning 优先 | 中高 | 低中 / 中 | 不能把 sourced morphology 夸大为机械规则 |",
        "| E 有界混合 | 最高 | 中 / 中 | 需固定范围与独立 semantic review，递减低 |",
        "",
        "**推荐：Strategy E，但由 Strategy B 主导。** 先对 100–200 个高频 A1/A2/B1 缺口做 learner-first sense review；只在已有 sourced relation 对学习确有价值时补充 family context。不要再启动无差别的 500 条批次。",
        "",
        "**Phase 4A conclusion：Phase 3 is closed.**",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    audit = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOC.write_text(write_markdown(audit), encoding="utf-8")
    print(json.dumps({"ok": True, "artifact": str(OUT.relative_to(ROOT)), "hash": audit["artifact_hash"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
