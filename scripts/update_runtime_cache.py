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


def version() -> str:
    digest = hashlib.sha256()
    digest.update(RUNTIME.read_bytes())
    digest.update(APP.read_bytes())
    digest.update(SERVICE_WORKER.read_bytes())
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
