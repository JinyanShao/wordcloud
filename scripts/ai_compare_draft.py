#!/usr/bin/env python3
"""Draft `compare` teaching relations for high-frequency synonym pairs via a completion API.

Pipeline position:

1. `pairs`  — inspect candidate pairs (official syn edges, both endpoints in the
              top-2000 most frequent eligible lexemes, no existing compare edge).
2. `draft`  — call an OpenAI-compatible chat completion endpoint in small batches,
              validate the JSON, and append drafts to
              `data/processed/ai-compare-drafts.json` (idempotent: known keys skip).
3. Review   — a human flips `review.status` to `accepted` / `rejected` in that file.
4. `build_graph.py` re-applies accepted drafts into `official_edges` on every
              rebuild, so the JSON file — not the SQLite rows — is the durable store.

Endpoint configuration (never hardcode secrets in this file — it is git-tracked):

- Environment variables `WORDCLOUD_API_KEY` and `WORDCLOUD_MODEL` (required for `draft`),
  plus optional `WORDCLOUD_API_BASE` (default `https://api.openai.com/v1`).
- Or put them in a `.env.local` file at the project root — it is listed in
  `.gitignore`, loaded automatically, and real environment variables take precedence.

Only the Python standard library is used, so no extra dependency is added.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "wordcloud.sqlite"
DRAFTS = ROOT / "data" / "processed" / "ai-compare-drafts.json"
LOCAL_ENV = ROOT / ".env.local"

TOP_RANK = 2000
DEF_MAX_CHARS = 220
PROMPT_VERSION = 1

DIMENSIONS = {
    "intensity": "强度/程度差异",
    "register": "语域（口语 vs 书面/正式）",
    "subjectivity": "主观评价 vs 客观描述",
    "domain": "适用领域/专业场景",
    "object": "适用对象（人/物/抽象）",
    "scenario": "使用场景与搭配习惯",
}

SYSTEM_PROMPT = "你是法语词汇编辑，为中国学习者撰写高频近义词的辨析。只输出 JSON，不输出任何其他文字。"

USER_TEMPLATE = """为下列法语近义词对撰写 compare 辨析。

要求：
- dimension 只能从 {dimensions} 中选一个最主要差异维度；
- label：一句话中文结论，点明两词差异与不可互换的场景，40 字以内，将直接展示给学习者；
- examples：1-2 个简短法语例句，体现两词各自的典型用法；
- 每个输入 pair 必须恰好输出一个 item，key 原样返回。

输出 JSON：{{"items": [{{"key": "...", "dimension": "...", "label": "...", "examples": ["..."]}}]}}

输入：
{pairs_json}"""


def load_local_env() -> None:
    """Load KEY=VALUE lines from the git-ignored `.env.local`, without overriding real env."""
    if not LOCAL_ENV.exists():
        return
    for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_drafts() -> dict:
    if DRAFTS.exists():
        return json.loads(DRAFTS.read_text(encoding="utf-8"))
    return {"meta": {"kind": "ai_compare_drafts", "prompt_version": PROMPT_VERSION, "created_at": now_iso()}, "items": []}


def save_drafts(payload: dict) -> None:
    DRAFTS.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def pair_key(a_norm: str, a_pos: str, b_norm: str, b_pos: str) -> str:
    ends = sorted([(a_norm, a_pos), (b_norm, b_pos)])
    return f"{ends[0][0]}|{ends[0][1]}|{ends[1][0]}|{ends[1][1]}"


def candidate_pairs(conn: sqlite3.Connection, limit: int | None) -> list[dict]:
    rows = conn.execute(
        """
        WITH ranked AS (
          SELECT id, lemma, normalized, pos, gloss_zh,
                 COALESCE(flelex_frequency, lexique_frequency, 0) AS freq,
                 ROW_NUMBER() OVER (
                   ORDER BY COALESCE(flelex_frequency, lexique_frequency, 0) DESC
                 ) AS rnk
          FROM lexemes WHERE status='eligible'
        )
        SELECT a.id AS a_id, a.lemma AS a_lemma, a.normalized AS a_norm, a.pos AS a_pos,
               a.gloss_zh AS a_gloss, a.rnk AS a_rnk,
               b.id AS b_id, b.lemma AS b_lemma, b.normalized AS b_norm, b.pos AS b_pos,
               b.gloss_zh AS b_gloss, b.rnk AS b_rnk
        FROM official_edges e
        JOIN ranked a ON a.id = e.a_id
        JOIN ranked b ON b.id = e.b_id
        WHERE e.relation = 'syn'
          AND a.rnk <= ? AND b.rnk <= ?
          AND NOT EXISTS (
            SELECT 1 FROM official_edges c
            WHERE c.a_id = e.a_id AND c.b_id = e.b_id AND c.relation = 'compare'
          )
        ORDER BY a.rnk + b.rnk
        """,
        (TOP_RANK, TOP_RANK),
    ).fetchall()

    def first_def(lexeme_id: int) -> str:
        row = conn.execute(
            "SELECT definition_fr FROM lexeme_senses WHERE lexeme_id=? ORDER BY entry_id, sense_number LIMIT 1",
            (lexeme_id,),
        ).fetchone()
        return (row[0][:DEF_MAX_CHARS] if row and row[0] else "")

    pairs = []
    for row in rows:
        pairs.append({
            "key": pair_key(row["a_norm"], row["a_pos"], row["b_norm"], row["b_pos"]),
            "a": {"word": row["a_lemma"], "normalized": row["a_norm"], "pos": row["a_pos"],
                  "gloss": row["a_gloss"] or "", "def": first_def(row["a_id"])},
            "b": {"word": row["b_lemma"], "normalized": row["b_norm"], "pos": row["b_pos"],
                  "gloss": row["b_gloss"] or "", "def": first_def(row["b_id"])},
            "rank_sum": row["a_rnk"] + row["b_rnk"],
        })
        if limit and len(pairs) >= limit:
            break
    return pairs


def build_prompt(batch: list[dict]) -> str:
    compact = [
        {
            "key": p["key"],
            "a": {field: p["a"][field] for field in ("word", "pos", "gloss", "def")},
            "b": {field: p["b"][field] for field in ("word", "pos", "gloss", "def")},
        }
        for p in batch
    ]
    return USER_TEMPLATE.format(
        dimensions=sorted(DIMENSIONS),
        pairs_json=json.dumps(compact, ensure_ascii=False),
    )


def call_api(base: str, key: str, model: str, prompt: str, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=json.dumps({
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)


def validate_items(raw: dict, batch: list[dict]) -> tuple[list[dict], int]:
    expected = {p["key"] for p in batch}
    seen = set()
    accepted, rejected = [], 0
    for item in raw.get("items", []):
        key = item.get("key")
        if key not in expected or key in seen:
            rejected += 1
            continue
        seen.add(key)
        dimension, label = item.get("dimension"), item.get("label")
        examples = item.get("examples")
        if dimension not in DIMENSIONS or not isinstance(label, str) or not label.strip() \
                or not isinstance(examples, list) or not examples \
                or not all(isinstance(ex, str) and ex.strip() for ex in examples):
            rejected += 1
            continue
        accepted.append({
            "key": key,
            "dimension": dimension,
            "label": label.strip(),
            "examples": [ex.strip() for ex in examples[:2]],
        })
    rejected += len(expected - seen)
    return accepted, rejected


def cmd_pairs(args: argparse.Namespace) -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    pairs = candidate_pairs(conn, args.limit)
    drafts = load_drafts()
    known = {item["key"] for item in drafts["items"]}
    fresh = [p for p in pairs if p["key"] not in known]
    print(f"候选近义对（双 top-{TOP_RANK}、无 compare 边）：{len(pairs)}，未起草：{len(fresh)}")
    for pair in fresh[: args.show]:
        print(f"  {pair['a']['word']} ({pair['a']['pos']}) ↔ {pair['b']['word']} ({pair['b']['pos']})"
              f"  rank_sum={pair['rank_sum']}")


def cmd_draft(args: argparse.Namespace) -> None:
    api_key = os.environ.get("WORDCLOUD_API_KEY", "")
    model = os.environ.get("WORDCLOUD_MODEL", "")
    api_base = os.environ.get("WORDCLOUD_API_BASE", "https://api.openai.com/v1")
    if not args.dry_run and (not api_key or not model):
        raise SystemExit(
            "draft 需要 WORDCLOUD_API_KEY 与 WORDCLOUD_MODEL："
            "用环境变量传入，或写入项目根目录的 .env.local（已 gitignore）。"
        )

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    pairs = candidate_pairs(conn, args.limit)
    drafts = load_drafts()
    known = {item["key"] for item in drafts["items"]}
    todo = [p for p in pairs if p["key"] not in known]
    print(f"待起草 {len(todo)} / 候选 {len(pairs)}（已存在 {len(known)} 条，幂等跳过）")
    if not todo:
        return

    if args.dry_run:
        batch = todo[: args.batch_size]
        prompt = build_prompt(batch)
        print(f"--- dry-run：首批 {len(batch)} 对，prompt 约 {len(prompt)} 字符 ---")
        print(prompt)
        return

    by_key = {p["key"]: p for p in todo}
    total_ok = total_bad = 0
    for start in range(0, len(todo), args.batch_size):
        batch = todo[start : start + args.batch_size]
        prompt = build_prompt(batch)
        raw = None
        for attempt in (1, 2):
            try:
                raw = call_api(api_base, api_key, model, prompt, args.timeout)
                break
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                print(f"  批次 {start // args.batch_size + 1} 第 {attempt} 次失败：{exc}", file=sys.stderr)
                if attempt == 1:
                    time.sleep(2)
        if raw is None:
            total_bad += len(batch)
            continue
        accepted, rejected = validate_items(raw, batch)
        for item in accepted:
            pair = by_key[item.pop("key")]
            drafts["items"].append({
                "key": pair["key"],
                "a": {"lemma": pair["a"]["word"], "normalized": pair["a"]["normalized"], "pos": pair["a"]["pos"]},
                "b": {"lemma": pair["b"]["word"], "normalized": pair["b"]["normalized"], "pos": pair["b"]["pos"]},
                "draft": item,
                "model": model,
                "drafted_at": now_iso(),
                "review": {"status": "pending", "reviewer": None, "reviewed_at": None, "note": ""},
            })
        total_ok += len(accepted)
        total_bad += rejected
        save_drafts(drafts)
        print(f"  批次 {start // args.batch_size + 1}: +{len(accepted)} 条草稿（作废 {rejected}），累计 {total_ok}")
    print(f"完成：新草稿 {total_ok}，失败/作废 {total_bad}。写入 {DRAFTS.relative_to(ROOT)}")
    print("下一步：人工把 review.status 改为 accepted / rejected，然后运行 build_graph.py 重建。")


def cmd_stats(_args: argparse.Namespace) -> None:
    drafts = load_drafts()
    counts = {}
    for item in drafts["items"]:
        status = item.get("review", {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    print(f"{DRAFTS.relative_to(ROOT)}: {len(drafts['items'])} 条，{counts}")


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_pairs = sub.add_parser("pairs", help="列出候选词对（不调用 API）")
    p_pairs.add_argument("--limit", type=int, default=None)
    p_pairs.add_argument("--show", type=int, default=20, help="最多打印多少对")
    p_pairs.set_defaults(func=cmd_pairs)

    p_draft = sub.add_parser("draft", help="调用 completion API 起草 compare 辨析")
    p_draft.add_argument("--batch-size", type=int, default=15)
    p_draft.add_argument("--limit", type=int, default=None, help="只处理前 N 个候选（按频率排序）")
    p_draft.add_argument("--timeout", type=int, default=120)
    p_draft.add_argument("--dry-run", action="store_true", help="只打印首批 prompt，不调用 API")
    p_draft.set_defaults(func=cmd_draft)

    p_stats = sub.add_parser("stats", help="统计草稿与审校状态")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
