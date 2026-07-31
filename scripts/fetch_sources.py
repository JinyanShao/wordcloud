#!/usr/bin/env python3
"""Fetch or verify the exact raw snapshots declared in data/sources.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "sources.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected: str, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing locked source for {label}: {path.relative_to(ROOT)}")
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"source lock mismatch for {label}: expected {expected}, got {actual}")


def download(source: dict[str, object], destination: Path) -> None:
    url = str(source["download_url"])
    fetch = source.get("fetch") if isinstance(source.get("fetch"), dict) else {}
    form = fetch.get("form", [])
    data = urlencode(form).encode("utf-8") if form else None
    request = Request(url, data=data, headers={"User-Agent": "maillage-source-lock/1"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            expected = str(source["expected_sha256"])
            if sha256(temporary) != expected:
                raise SystemExit(f"downloaded {source['id']} does not match the reviewed SHA-256")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def verify_archive_members(source: dict[str, object], archive: Path) -> None:
    fetch = source.get("fetch") if isinstance(source.get("fetch"), dict) else {}
    members = fetch.get("archive_members", {})
    if not members:
        return
    with zipfile.ZipFile(archive) as bundle:
        for name, expected in members.items():
            target = archive.parent / name
            if not target.exists() or sha256(target) != expected:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    try:
                        with bundle.open(name) as origin:
                            while chunk := origin.read(1024 * 1024):
                                stream.write(chunk)
                        if sha256(temporary) != expected:
                            raise SystemExit(f"archive member lock mismatch for {source['id']}:{name}")
                        os.replace(temporary, target)
                    finally:
                        temporary.unlink(missing_ok=True)
            verify_file(target, str(expected), f"{source['id']}:{name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="fetch missing or mismatched remote sources into data/raw")
    args = parser.parse_args()
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    verified = []
    for source in sources:
        path = ROOT / str(source["local_path"])
        expected = str(source.get("expected_sha256", ""))
        if not expected:
            raise SystemExit(f"source has no expected_sha256: {source['id']}")
        if (not path.exists() or sha256(path) != expected) and args.download and source.get("download_url"):
            download(source, path)
        verify_file(path, expected, str(source["id"]))
        verify_archive_members(source, path)
        verified.append(str(source["id"]))
    print(json.dumps({"verified": verified}, ensure_ascii=False))


if __name__ == "__main__":
    main()
