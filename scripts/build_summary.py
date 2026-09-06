#!/usr/bin/env python3
"""Write a small checked-build manifest from the browser runtime payload."""

from __future__ import annotations

import json
import sys

from runtime_graph import PIPELINE_PATH, README_PATH, SUMMARY_PATH, build_summary, docs_expected_lines, load_runtime


def main() -> None:
    summary = build_summary(load_runtime())
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if "--check-docs" in sys.argv:
        readme_line, pipeline_line = docs_expected_lines(summary)
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
