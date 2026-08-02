#!/usr/bin/env python3
"""Run the existing pipeline in its reviewed, deterministic release order."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ["python3", "scripts/fetch_sources.py"],
    ["pnpm", "data:build"],
    ["pnpm", "data:review"],
    ["pnpm", "demonette:analyze"],
    ["pnpm", "demonette:approve"],
    ["pnpm", "dbnary:analyze"],
    ["pnpm", "dbnary:approve"],
    ["pnpm", "wiktextract:p0:approve"],
    ["pnpm", "graph:candidates"],
    ["pnpm", "graph:layout"],
    ["pnpm", "graph:export"],
    ["pnpm", "check"],
    ["python3", "scripts/build_gap_list.py"],
    ["python3", "scripts/write_build_manifest.py", "write"],
    ["python3", "scripts/write_build_manifest.py", "verify"],
]


def main() -> None:
    for step in STEPS:
        print("+", " ".join(step), flush=True)
        subprocess.run(step, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
