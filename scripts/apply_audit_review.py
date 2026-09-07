#!/usr/bin/env python3
"""Carry forward review decisions only when the sampled lemma still matches.

The deterministic sample changes when the eligibility policy changes.  Sample
positions are therefore not an identity: applying an old decision by row
number would silently review a different word.  Unmatched rows remain
unreviewed for a later audit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "reports" / "lexicon-audit-sample-500.csv"
MANIFEST = ROOT / "data" / "audit-review-v1.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    overrides = [value for value in manifest["items"].values()]
    by_lemma: dict[str, list[dict[str, object]]] = {}
    for item in overrides:
        lemma = str(item.get("lemma", "")).strip()
        if lemma:
            by_lemma.setdefault(lemma, []).append(item)
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    if len(rows) != 500:
        raise SystemExit(f"expected 500 rows, found {len(rows)}")
    carried = 0
    ambiguous = 0
    for row in rows:
        matches = by_lemma.get(row["lemma"], [])
        if len(matches) > 1:
            ambiguous += 1
            row["manual_decision"] = ""
            row["manual_note"] = ""
            continue
        item = matches[0] if matches else {}
        row["manual_decision"] = item.get("decision", "agree") if item else ""
        row["manual_note"] = item.get("note", "") if item else ""
        carried += bool(item)
    with SAMPLE.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["manual_decision"]] = counts.get(row["manual_decision"], 0) + 1
    print(json.dumps({"carried_by_lemma": carried, "ambiguous": ambiguous, "decisions": counts}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
