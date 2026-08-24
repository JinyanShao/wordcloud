#!/usr/bin/env python3
"""Fetch or verify the exact raw snapshots declared in data/sources.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import tempfile
import time
import urllib.error
import zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "sources.json"

MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (2, 5)  # delay before attempt 2, then before attempt 3
RETRYABLE_HTTP_STATUSES = {408, 429}


class NonRetryableDownloadError(Exception):
    """A download failure that must not be retried (deterministic/config error)."""


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


def is_retryable_error(error: BaseException) -> bool:
    """Transient network/server failures worth a limited retry.

    Retried: connect/read timeouts, connection-level OSErrors (refused, reset,
    DNS hiccups) surfaced as URLError, and HTTP 408/429/5xx.
    Not retried: any other HTTPError (400/401/403/404/...), and anything else
    (bad local config, unexpected exceptions) — those are deterministic and
    retrying them would just waste the attempt budget.
    """
    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_HTTP_STATUSES or 500 <= error.code < 600
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, urllib.error.URLError):
        return isinstance(error.reason, OSError)
    return False


def download(source: dict[str, object], destination: Path, *, log=print) -> None:
    source_id = str(source["id"])
    url = str(source["download_url"])
    fetch = source.get("fetch") if isinstance(source.get("fetch"), dict) else {}
    raw_form = fetch.get("form", [])
    form = [tuple(item) for item in raw_form] if isinstance(raw_form, list) else []
    expected = str(source["expected_sha256"])
    destination.parent.mkdir(parents=True, exist_ok=True)

    last_error: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"[{source_id}] download attempt {attempt}/{MAX_ATTEMPTS}: {url}")
        # A fresh Request and a fresh temp file every attempt: never resume or
        # reuse a connection/response/partial file from a previous try.
        data = urlencode(form).encode("utf-8") if form else None
        request = Request(url, data=data, headers={"User-Agent": "wordcloud-source-lock/1"})
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                with urlopen(request, timeout=120) as response:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())

            actual = sha256(temporary)
            if actual != expected:
                raise NonRetryableDownloadError(
                    f"downloaded {source_id} does not match the reviewed SHA-256 "
                    f"(expected {expected}, got {actual})"
                )
            os.replace(temporary, destination)
            temporary = None
            log(f"[{source_id}] download attempt {attempt}/{MAX_ATTEMPTS}: succeeded")
            return
        except NonRetryableDownloadError as error:
            log(f"[{source_id}] download attempt {attempt}/{MAX_ATTEMPTS}: hash mismatch, not retrying")
            raise SystemExit(str(error)) from error
        except Exception as error:  # noqa: BLE001 - classified below, re-raised if not retryable
            if not is_retryable_error(error):
                log(f"[{source_id}] download attempt {attempt}/{MAX_ATTEMPTS}: non-retryable error: {error!r}")
                raise
            last_error = error
            log(f"[{source_id}] download attempt {attempt}/{MAX_ATTEMPTS}: transient error: {error!r}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

        if attempt < MAX_ATTEMPTS:
            delay = RETRY_DELAYS_SECONDS[min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)]
            log(f"[{source_id}] retrying in {delay}s")
            time.sleep(delay)

    log(f"[{source_id}] all {MAX_ATTEMPTS} attempts failed: {last_error!r}")
    raise SystemExit(f"failed to download {source_id} after {MAX_ATTEMPTS} attempts: {last_error!r}")


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
                        stream.flush()
                        os.fsync(stream.fileno())
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
        source_id = str(source["id"])
        path = ROOT / str(source["local_path"])
        expected = str(source.get("expected_sha256", ""))
        if not expected:
            raise SystemExit(f"source has no expected_sha256: {source_id}")
        url = source.get("download_url")
        needs_fetch = not path.exists() or sha256(path) != expected
        if needs_fetch and args.download and url:
            print(f"[{source_id}] url: {url}")
            print(f"[{source_id}] mode: download (up to {MAX_ATTEMPTS} attempts)")
            download(source, path)
        else:
            if not path.exists():
                mode = "missing, no download requested"
            elif needs_fetch:
                mode = "verify local file (present but hash mismatch, no download requested)"
            else:
                mode = "verify local file (already matches locked hash)"
            print(f"[{source_id}] url: {url or '(local only)'}")
            print(f"[{source_id}] mode: {mode}")
        verify_file(path, expected, source_id)
        verify_archive_members(source, path)
        verified.append(source_id)
    print(json.dumps({"verified": verified}, ensure_ascii=False))


if __name__ == "__main__":
    main()
