#!/usr/bin/env python3
"""Apply the human-readable audit manifest to the deterministic 500-row sample."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "reports" / "lexicon-audit-sample-500.csv"
MANIFEST = ROOT / "data" / "audit-review-v1.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    overrides = {int(key): value for key, value in manifest["items"].items()}
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    if len(rows) != 500:
        raise SystemExit(f"expected 500 rows, found {len(rows)}")
    for row in rows:
        order = int(row["sample_order"])
        item = overrides.get(order, {})
        expected = item.get("lemma")
        if expected and expected != row["lemma"]:
            raise SystemExit(f"sample drift at {order}: expected {expected}, found {row['lemma']}")
        row["manual_decision"] = item.get("decision", "agree")
        row["manual_note"] = item.get("note", "")
    with SAMPLE.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["manual_decision"]] = counts.get(row["manual_decision"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

