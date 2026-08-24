#!/usr/bin/env python3
"""Unit tests for fetch_sources.py's retry/classification behavior.

Run directly: python3 scripts/test_fetch_sources.py
No real network access; urlopen is mocked. No third-party dependencies.
"""

from __future__ import annotations

import hashlib
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import fetch_sources


class FakeResponse:
    """Minimal stand-in for the object urlopen() returns, used as a context manager."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        end = len(self._data) if size is None or size < 0 else self._pos + size
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk


def scripted_urlopen(actions):
    """Returns a fake urlopen(request, timeout=...) that pops one action per call.

    Each action is either an Exception instance (raised) or bytes (wrapped in a
    successful FakeResponse).
    """
    calls = {"count": 0}

    def _urlopen(request, timeout=None):
        index = calls["count"]
        calls["count"] += 1
        if index >= len(actions):
            raise AssertionError("scripted_urlopen called more times than scripted")
        action = actions[index]
        if isinstance(action, BaseException):
            raise action
        return FakeResponse(action)

    _urlopen.calls = calls
    return _urlopen


def make_source(url="https://example.invalid/file.bin", content=b"hello world"):
    expected = hashlib.sha256(content).hexdigest()
    return {
        "id": "fake_source",
        "download_url": url,
        "expected_sha256": expected,
        "fetch": {},
    }, content


class RetryClassificationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.destination = Path(self.tmpdir.name) / "raw" / "file.bin"
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        self.logs.append(message)

    def _leftover_temp_files(self) -> list[Path]:
        parent = self.destination.parent
        if not parent.exists():
            return []
        return [p for p in parent.iterdir() if p != self.destination]

    def test_first_timeout_then_success(self):
        source, content = make_source()
        opener = scripted_urlopen([TimeoutError("timed out"), content])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            fetch_sources.download(source, self.destination, log=self.log)

        self.assertTrue(self.destination.exists())
        self.assertEqual(fetch_sources.sha256(self.destination), source["expected_sha256"])
        self.assertEqual(opener.calls["count"], 2)
        sleep_mock.assert_called_once_with(2)
        self.assertEqual(self._leftover_temp_files(), [])

    def test_exhausts_retries_on_consecutive_timeouts(self):
        source, _content = make_source()
        opener = scripted_urlopen([
            TimeoutError("timed out"),
            socket.timeout("timed out"),
            TimeoutError("timed out"),
        ])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            with self.assertRaises(SystemExit):
                fetch_sources.download(source, self.destination, log=self.log)

        self.assertEqual(opener.calls["count"], fetch_sources.MAX_ATTEMPTS)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self._leftover_temp_files(), [])
        sleep_mock.assert_any_call(2)
        sleep_mock.assert_any_call(5)
        self.assertEqual(sleep_mock.call_count, fetch_sources.MAX_ATTEMPTS - 1)

    def test_http_500_retries_then_succeeds(self):
        source, content = make_source()
        error = urllib.error.HTTPError(source["download_url"], 500, "Internal Server Error", {}, None)
        opener = scripted_urlopen([error, content])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            fetch_sources.download(source, self.destination, log=self.log)

        self.assertTrue(self.destination.exists())
        self.assertEqual(opener.calls["count"], 2)
        sleep_mock.assert_called_once_with(2)

    def test_http_404_does_not_retry(self):
        source, _content = make_source()
        error = urllib.error.HTTPError(source["download_url"], 404, "Not Found", {}, None)
        opener = scripted_urlopen([error])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                fetch_sources.download(source, self.destination, log=self.log)

        self.assertEqual(ctx.exception.code, 404)
        self.assertEqual(opener.calls["count"], 1)
        sleep_mock.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.assertEqual(self._leftover_temp_files(), [])

    def test_hash_mismatch_does_not_retry(self):
        source, _content = make_source(content=b"expected content")
        wrong_bytes = b"not the expected bytes at all"
        opener = scripted_urlopen([wrong_bytes])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            with self.assertRaises(SystemExit) as ctx:
                fetch_sources.download(source, self.destination, log=self.log)

        self.assertIn("does not match the reviewed SHA-256", str(ctx.exception))
        self.assertEqual(opener.calls["count"], 1)
        sleep_mock.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.assertEqual(self._leftover_temp_files(), [])

    def test_no_leftover_artifacts_after_any_failure(self):
        source, _content = make_source()
        scenarios = [
            [TimeoutError("t"), TimeoutError("t"), TimeoutError("t")],
            [urllib.error.HTTPError(source["download_url"], 403, "Forbidden", {}, None)],
            [b"wrong bytes that will fail the hash check"],
        ]
        for actions in scenarios:
            opener = scripted_urlopen(list(actions))
            with patch.object(fetch_sources, "urlopen", opener), \
                 patch.object(fetch_sources.time, "sleep"):
                with self.assertRaises((SystemExit, urllib.error.HTTPError)):
                    fetch_sources.download(source, self.destination, log=self.log)
            self.assertFalse(self.destination.exists())
            self.assertEqual(self._leftover_temp_files(), [])

    def test_connection_reset_url_error_is_retryable(self):
        source, content = make_source()
        reset_error = urllib.error.URLError(ConnectionResetError("connection reset"))
        opener = scripted_urlopen([reset_error, content])
        with patch.object(fetch_sources, "urlopen", opener), \
             patch.object(fetch_sources.time, "sleep") as sleep_mock:
            fetch_sources.download(source, self.destination, log=self.log)

        self.assertTrue(self.destination.exists())
        sleep_mock.assert_called_once_with(2)


class IsRetryableErrorTests(unittest.TestCase):
    def test_http_408_and_429_and_5xx_are_retryable(self):
        for code in (408, 429, 500, 502, 503):
            error = urllib.error.HTTPError("u", code, "msg", {}, None)
            self.assertTrue(fetch_sources.is_retryable_error(error), f"code {code} should be retryable")

    def test_http_4xx_non_special_are_not_retryable(self):
        for code in (400, 401, 403, 404):
            error = urllib.error.HTTPError("u", code, "msg", {}, None)
            self.assertFalse(fetch_sources.is_retryable_error(error), f"code {code} should not be retryable")

    def test_timeout_variants_are_retryable(self):
        self.assertTrue(fetch_sources.is_retryable_error(TimeoutError("t")))
        self.assertTrue(fetch_sources.is_retryable_error(socket.timeout("t")))

    def test_generic_url_error_with_os_error_reason_is_retryable(self):
        self.assertTrue(fetch_sources.is_retryable_error(urllib.error.URLError(OSError("boom"))))

    def test_url_error_with_non_os_reason_is_not_retryable(self):
        self.assertFalse(fetch_sources.is_retryable_error(urllib.error.URLError("bad url syntax")))

    def test_unrelated_exception_is_not_retryable(self):
        self.assertFalse(fetch_sources.is_retryable_error(ValueError("unrelated")))


if __name__ == "__main__":
    unittest.main()
