#!/usr/bin/env python3
"""Build and approve a human-reviewed P0 Wiktextract definition queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from learning_lexicon import normalize

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
DUMP = ROOT / "data" / "raw" / "wiktextract" / "frwiktionary-20260701-pages-articles.xml.bz2"
RAW_JSONL = ROOT / "data" / "processed" / "wiktextract-gap-audit.jsonl"
ALIGNMENT_QUEUE = ROOT / "data" / "processed" / "dbnary-alignment-review-queue.json"
REVIEW_QUEUE = ROOT / "data" / "processed" / "wiktextract-p0-review.json"
APPROVED = ROOT / "data" / "processed" / "wiktextract-p0-approved.json"
CSV_QUEUE = ROOT / "data" / "reports" / "wiktextract-p0-review.csv"
REPORT = ROOT / "data" / "reports" / "wiktextract-p0-review.md"
SOURCE_ID = "wiktionary_fr_wiktextract"
EXPECTED_DUMP_SHA256 = "040166ced172cacd029202fd98f99abe81cfaf91c5978fbe79137738a840aaec"
EXTRACTOR_COMMIT = "d9fa2335957c9089ce2c3fb110a075cf072903da"
POS = {"noun": "NOM", "verb": "VER", "adjective": "ADJ", "adverb": "ADV"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def p0_targets() -> dict[tuple[str, str], dict[str, object]]:
    queue = json.loads(ALIGNMENT_QUEUE.read_text(encoding="utf-8"))
    return {(normalize(item["lemma"]), str(item["pos"])): item for item in queue["items"] if item["review_priority"] == "P0"}


def source_records(targets: dict[tuple[str, str], dict[str, object]]) -> dict[tuple[str, str], list[dict[str, object]]]:
    records: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    with RAW_JSONL.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (normalize(row.get("word")), POS.get(str(row.get("pos"))))
            if row.get("lang_code") == "fr" and key in targets:
                records[key].append(row)
    return records


def existing_reviews() -> dict[int, dict[str, object]]:
    reviews: dict[int, dict[str, object]] = {}
    if REVIEW_QUEUE.exists():
        payload = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
        reviews.update({int(item["lexeme_id"]): item["review"] for item in payload.get("items", [])})
    if CSV_QUEUE.exists():
        with CSV_QUEUE.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                reviews[int(row["lexeme_id"])] = {
                    "status": row.get("review_status") or "pending",
                    "approved_sense_ids": [value for value in (row.get("approved_sense_ids") or "").split("|") if value],
                    "reviewer": row.get("reviewer") or None,
                    "reviewed_at": row.get("reviewed_at") or None,
                    "notes": row.get("notes") or None,
                }
    return reviews


def clean_examples(sense: dict[str, object]) -> list[str]:
    examples = []
    for example in sense.get("examples", []):
        text = str(example.get("text") or "").strip()
        if text and text not in examples:
            examples.append(text)
        if len(examples) == 2:
            break
    return examples


def analyze() -> dict[str, object]:
    if not DUMP.exists() or not RAW_JSONL.exists():
        raise SystemExit("run the pinned Wiktextract audit before P0 analysis")
    dump_hash = sha256(DUMP)
    if dump_hash != EXPECTED_DUMP_SHA256:
        raise SystemExit(f"Wiktionary dump hash mismatch: {dump_hash}")
    targets, reviews = p0_targets(), existing_reviews()
    records = source_records(targets)
    items = []
    for key, target in sorted(targets.items()):
        candidates = []
        for entry_rank, entry in enumerate(records.get(key, []), start=1):
            senses = []
            for sense_rank, sense in enumerate(entry.get("senses", []), start=1):
                glosses = [str(value).strip() for value in sense.get("glosses", []) if str(value).strip()]
                if not glosses:
                    continue
                senses.append({
                    "candidate_id": f"wikt-p0-{target['lexeme_id']}-{entry_rank}-{sense_rank}",
                    "sense_number": str(sense_rank), "definition_fr": glosses[0],
                    "raw_glosses": [str(value) for value in sense.get("raw_glosses", [])],
                    "tags": [str(value) for value in sense.get("tags", [])],
                    "examples": clean_examples(sense),
                })
            if senses:
                candidates.append({"entry_rank": entry_rank, "senses": senses})
        items.append({
            "lexeme_id": int(target["lexeme_id"]), "lemma": target["lemma"], "pos": target["pos"],
            "cefr_level": target["cefr_level"],
            "source_url": "https://fr.wiktionary.org/wiki/" + quote(str(target["lemma"])),
            "candidate_entries": candidates,
            "review": reviews.get(int(target["lexeme_id"]), {"status": "pending", "approved_sense_ids": [], "reviewer": None, "reviewed_at": None, "notes": None}),
        })
    payload = {
        "meta": {"version": "wiktextract-p0-review-v1", "source_id": SOURCE_ID, "dump_path": str(DUMP.relative_to(ROOT)), "dump_sha256": dump_hash, "extractor": "Wiktextract 1.99.7", "extractor_commit": EXTRACTOR_COMMIT, "license_id": "CC-BY-SA-3.0-or-later", "purpose": "human review queue; never publish pending candidates"},
        "gates": {
            "exactly_59_p0_lexemes": len(items) == 59,
            "all_p0_lexemes_have_candidates": all(item["candidate_entries"] for item in items),
            "all_candidate_senses_have_french_definitions": all(sense["definition_fr"] for item in items for entry in item["candidate_entries"] for sense in entry["senses"]),
            "official_dump_hash_matches": dump_hash == EXPECTED_DUMP_SHA256,
        },
        "review_counts": dict(Counter(item["review"]["status"] for item in items)), "items": items,
    }
    if not all(payload["gates"].values()):
        raise SystemExit("P0 analysis gate failed: " + ", ".join(name for name, passed in payload["gates"].items() if not passed))
    REVIEW_QUEUE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(payload)
    write_report(payload)
    return payload


def write_csv(payload: dict[str, object]) -> None:
    fields = ["lexeme_id", "lemma", "pos", "cefr_level", "candidate_senses", "review_status", "approved_sense_ids", "reviewer", "reviewed_at", "notes"]
    with CSV_QUEUE.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in payload["items"]:
            review = item["review"]
            writer.writerow({"lexeme_id": item["lexeme_id"], "lemma": item["lemma"], "pos": item["pos"], "cefr_level": item["cefr_level"], "candidate_senses": sum(len(entry["senses"]) for entry in item["candidate_entries"]), "review_status": review["status"], "approved_sense_ids": "|".join(review.get("approved_sense_ids", [])), "reviewer": review.get("reviewer"), "reviewed_at": review.get("reviewed_at"), "notes": review.get("notes")})


def write_report(payload: dict[str, object]) -> None:
    items = payload["items"]
    sense_count = sum(len(entry["senses"]) for item in items for entry in item["candidate_entries"])
    example_count = sum(len(sense["examples"]) for item in items for entry in item["candidate_entries"] for sense in entry["senses"])
    counts = Counter(item["review"]["status"] for item in items)
    lines = ["# Wiktextract P0 法语定义审校队列", "", "> 59 个 A1–A2 DBnary 未覆盖词。候选来自固定日期法语 Wiktionnaire dump，经 Wiktextract 提取；未审核内容不得进入运行时。", "", f"- 候选词：{len(items)}", f"- 候选义项：{sense_count}", f"- 候选例句：{example_count}", f"- dump SHA-256：`{payload['meta']['dump_sha256']}`", f"- Wiktextract commit：`{payload['meta']['extractor_commit']}`", "", "## 审核方法", "", "1. 在 JSON 中查看每个词的候选义项及例句。", "2. 在 CSV 中将 `review_status` 改为 `accepted` 或 `rejected`。", "3. 接受时填写以 `|` 分隔的 `approved_sense_ids`、`reviewer`、`reviewed_at`；可在 `notes` 记录删改理由。", "4. 重新运行 analyze 合并审核字段，再运行 approve；approve 会拒绝任何 pending 或无署名记录。", "", "## 当前状态", "", "| 状态 | 数量 |", "|---|---:|", f"| pending | {counts['pending']} |", f"| accepted | {counts['accepted']} |", f"| rejected | {counts['rejected']} |"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def approve() -> dict[str, object]:
    payload = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
    if not all(payload["gates"].values()):
        raise SystemExit("P0 review queue failed source gates")
    pending = [item["lemma"] for item in payload["items"] if item["review"]["status"] == "pending"]
    if pending:
        raise SystemExit(f"P0 review incomplete: {len(pending)} pending lexemes")
    entries, senses = [], []
    for item in payload["items"]:
        review = item["review"]
        if review["status"] == "rejected":
            continue
        if review["status"] != "accepted" or not review.get("reviewer") or not review.get("reviewed_at"):
            raise SystemExit(f"invalid review metadata for {item['lemma']}")
        available = {sense["candidate_id"]: sense for entry in item["candidate_entries"] for sense in entry["senses"]}
        approved_ids = review.get("approved_sense_ids", [])
        if not approved_ids or any(candidate_id not in available for candidate_id in approved_ids):
            raise SystemExit(f"invalid approved senses for {item['lemma']}")
        entry_id = f"wikt-p0-entry-{item['lexeme_id']}"
        entries.append({"id": entry_id, "lexeme_id": item["lexeme_id"], "entry_rank": 1, "source_id": SOURCE_ID, "source_url": item["source_url"], "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"]})
        for rank, candidate_id in enumerate(approved_ids, start=1):
            sense = available[candidate_id]
            senses.append({"id": f"wikt-p0-sense-{item['lexeme_id']}-{rank}", "entry_id": entry_id, "lexeme_id": item["lexeme_id"], "sense_number": str(rank), "definition_fr": sense["definition_fr"], "examples": sense["examples"], "source_id": SOURCE_ID, "source_candidate_id": candidate_id})
    approved = {"meta": payload["meta"], "entries": entries, "senses": senses}
    APPROVED.write_text(json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return approved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyze", "approve"))
    args = parser.parse_args()
    payload = analyze() if args.command == "analyze" else approve()
    item_count = len(payload.get("items", payload.get("entries", [])))
    sense_count = len(payload.get("senses", [])) or sum(
        len(entry["senses"])
        for item in payload.get("items", [])
        for entry in item["candidate_entries"]
    )
    print(json.dumps({"items": item_count, "senses": sense_count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
