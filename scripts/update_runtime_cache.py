#!/usr/bin/env python3
"""Version runtime graph assets from their content hash for PWA cache safety."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "graph-data.js"
APP = ROOT / "app.js"
INDEX = ROOT / "index.html"
SERVICE_WORKER = ROOT / "sw.js"


def normalized_service_worker_bytes() -> bytes:
    """Strip the embedded version markers so hashing sw.js is a fixed point.

    sw.js's own bytes include the previously computed version string
    (CACHE_NAME plus the two ?v= query strings). Hashing it as-is would make
    the version depend on the version already written into the file, which
    can never converge. Normalizing those markers to a constant placeholder
    before hashing means the digest reflects sw.js's actual logic, not
    whatever version tag happens to be embedded right now.
    """
    text = SERVICE_WORKER.read_text(encoding="utf-8")
    text = re.sub(r'const CACHE_NAME = "wordcloud-learning-[^"]+";', 'const CACHE_NAME = "";', text)
    text = re.sub(r'graph-data\.js\?v=[^"\s]+', "graph-data.js", text)
    text = re.sub(r'app\.js\?v=[^"\s]+', "app.js", text)
    return text.encode("utf-8")


def version() -> str:
    digest = hashlib.sha256()
    digest.update(RUNTIME.read_bytes())
    digest.update(APP.read_bytes())
    digest.update(normalized_service_worker_bytes())
    return digest.hexdigest()[:12]


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"expected exactly one runtime-cache marker in {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    current = version()
    replace_once(INDEX, r'graph-data\.js\?v=[^"\s]+', f"graph-data.js?v={current}")
    replace_once(INDEX, r'app\.js\?v=[^"\s]+', f"app.js?v={current}")
    replace_once(SERVICE_WORKER, r'const CACHE_NAME = "wordcloud-learning-[^"]+";', f'const CACHE_NAME = "wordcloud-learning-{current}";')
    replace_once(SERVICE_WORKER, r'graph-data\.js\?v=[^"\s]+', f"graph-data.js?v={current}")
    replace_once(SERVICE_WORKER, r'app\.js\?v=[^"\s]+', f"app.js?v={current}")
    print(current)


if __name__ == "__main__":
    main()
