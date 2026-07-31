#!/usr/bin/env python3
"""Write or verify the exact inputs and outputs of a maillage build."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "reports" / "build-manifest.json"
INPUTS = [
    "data/sources.json", "data/audit-review-v1.json", "data/processed/editorial-seed.json",
    "data.js", "dict.js", "sql/schema.sql", "requirements-build.txt", "package.json", "pnpm-lock.yaml",
]
INPUTS += [str(path.relative_to(ROOT)) for path in sorted((ROOT / "scripts").glob("*.py"))]
INPUTS += [str(path.relative_to(ROOT)) for path in sorted((ROOT / "scripts").glob("*.mjs"))]
OUTPUTS = [
    "graph-data.js", "data/processed/eligible-lexicon.csv", "data/reports/build-validation.md",
    "data/reports/core-word-gap-list.csv", "data/reports/core-word-gap-list.md",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashes(paths: list[str]) -> dict[str, str]:
    result = {}
    for relative in paths:
        path = ROOT / relative
        if not path.exists():
            raise SystemExit(f"manifest input/output is missing: {relative}")
        result[relative] = sha256(path)
    return result


def command_version(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "toolchain": {
            "node": command_version(["node", "--version"]),
            "pnpm": command_version(["pnpm", "--version"]),
            "python": command_version(["python3", "--version"]),
        },
        "inputs": hashes(INPUTS),
        "outputs": hashes(OUTPUTS),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "verify"))
    args = parser.parse_args()
    current = payload()
    if args.action == "write":
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"written": str(MANIFEST.relative_to(ROOT))}, ensure_ascii=False))
        return
    if not MANIFEST.exists():
        raise SystemExit("missing build manifest; run write_build_manifest.py write")
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if recorded != current:
        raise SystemExit("build manifest differs from the current locked inputs or generated outputs")
    print(json.dumps({"verified": str(MANIFEST.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
