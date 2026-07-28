#!/usr/bin/env python3
"""Draft first official relations for core gap words (P1) via a completion API.

Candidates are eligible lexemes with zero official edges, taken from the top of the
frequency ranking (the `in_core` set of `core-word-gap-list.csv`). The model may
propose up to two relations per word (syn / ant / fam) with a partner lemma that
must exist in the eligible lexicon — proposals failing script-side validation are
discarded, and the model is explicitly allowed to propose nothing.

Pipeline position (mirrors `ai_compare_draft.py`):

1. `words`  — inspect candidate words (no API call).
2. `draft`  — call an OpenAI-compatible chat completion endpoint in small batches,
              validate every proposal against the lexicon, and append per-word
              records to `data/processed/ai-first-edge-drafts.json` (idempotent:
              words already present are skipped, even when they yielded zero
              proposals).
3. Review   — a human flips each proposal's `review.status` to `accepted` /
              `rejected` in that file.
4. `build_graph.py` re-applies accepted proposals into `official_edges` on every
              rebuild, so the JSON file — not the SQLite rows — is the durable store.

Endpoint configuration: same as `ai_compare_draft.py` — environment variables
`MAILLAGE_API_KEY` / `MAILLAGE_MODEL` / optional `MAILLAGE_API_BASE`, or a
git-ignored `.env.local` at the project root. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "maillage.sqlite"
DRAFTS = ROOT / "data" / "processed" / "ai-first-edge-drafts.json"
LOCAL_ENV = ROOT / ".env.local"

CORE_TARGET = 1000
MAX_PROPOSALS_PER_WORD = 2
DEF_MAX_CHARS = 220
PROMPT_VERSION = 1

RELATIONS = {"syn": "近义", "ant": "反义", "fam": "同族派生"}
POS_SET = {"NOM", "VER", "ADJ", "ADV"}

SYSTEM_PROMPT = "你是法语词汇编辑，为中国学习者梳理高频法语词的可靠词际关系。只输出 JSON，不输出任何其他文字。"

USER_TEMPLATE = """下列每个法语词目前在词网中没有任何正式关系。请凭你的法语知识，为每个词提议最多 {max_props} 条可靠关系。

要求：
- relation 只能从 ["syn", "ant", "fam"] 中选：syn=近义，ant=反义，fam=同族直接派生（如 affirmer→affirmation）；
- partner 必须是真实存在的常用法语词的词典原形（动词用不定式，名词/形容词用阳性单数），partner_pos 只能从 ["NOM", "VER", "ADJ", "ADV"] 中选；
- label：一句话中文说明关系，40 字以内，将直接展示给学习者；
- 只提议你确定的关系。该词没有值得提议的关系时，relations 返回空数组，宁空勿猜；
- 每个输入 word 必须恰好输出一个 item，key 原样返回。

输出 JSON：{{"items": [{{"key": "...", "relations": [{{"relation": "...", "partner": "...", "partner_pos": "...", "label": "..."}}]}}]}}

输入：
{words_json}"""


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


def normalize(value: str) -> str:
    text = str(value or "").strip().replace("’", "'").lower()
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text))


def load_drafts() -> dict:
    if DRAFTS.exists():
        return json.loads(DRAFTS.read_text(encoding="utf-8"))
    return {"meta": {"kind": "ai_first_edge_drafts", "prompt_version": PROMPT_VERSION, "created_at": now_iso()}, "items": []}


def save_drafts(payload: dict) -> None:
    DRAFTS.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def candidate_words(conn: sqlite3.Connection, limit: int | None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT l.id, l.lemma, l.normalized, l.pos, l.gloss_zh,
               COALESCE(l.flelex_frequency, l.lexique_frequency, 0) AS freq
        FROM lexemes l
        WHERE l.status = 'eligible'
          AND NOT EXISTS (
            SELECT 1 FROM official_edges e WHERE e.a_id = l.id OR e.b_id = l.id
          )
        ORDER BY freq DESC, l.lemma
        """,
    ).fetchall()
    cap = limit if limit else CORE_TARGET
    words = []
    for row in rows[:cap]:
        sense = conn.execute(
            "SELECT definition_fr FROM lexeme_senses WHERE lexeme_id=? ORDER BY entry_id, sense_number LIMIT 1",
            (row["id"],),
        ).fetchone()
        words.append({
            "key": f"{row['normalized']}|{row['pos']}",
            "word": row["lemma"],
            "normalized": row["normalized"],
            "pos": row["pos"],
            "gloss": row["gloss_zh"] or "",
            "def": (sense[0][:DEF_MAX_CHARS] if sense and sense[0] else ""),
            "freq": row["freq"],
        })
    return words


def lexicon_lookup(conn: sqlite3.Connection) -> tuple[dict[tuple[str, str], str], dict[str, list[tuple[str, str]]]]:
    """(normalized, pos) -> status and normalized -> [(pos, status)] for linkable lexemes.

    Auxiliary lexemes are valid partners: they are deliberate vocabulary (genre,
    type, milieu…), just not main learning targets, and they enter the graph as
    support nodes when a reviewed edge needs them.
    """
    by_key: dict[tuple[str, str], str] = {}
    by_norm: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute(
        "SELECT normalized, pos, status FROM lexemes WHERE status IN ('eligible', 'auxiliary')"
    ):
        by_key[(row["normalized"], row["pos"])] = row["status"]
        by_norm.setdefault(row["normalized"], []).append((row["pos"], row["status"]))
    return by_key, by_norm


def build_prompt(batch: list[dict]) -> str:
    compact = [
        {"key": w["key"], "word": w["word"], "pos": w["pos"], "gloss": w["gloss"], "def": w["def"]}
        for w in batch
    ]
    return USER_TEMPLATE.format(
        max_props=MAX_PROPOSALS_PER_WORD,
        words_json=json.dumps(compact, ensure_ascii=False),
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


def validate_word(
    raw_relations: object,
    word: dict,
    by_key: dict[tuple[str, str], str],
    by_norm: dict[str, list[tuple[str, str]]],
) -> tuple[list[dict], list[dict]]:
    """Keep only proposals whose partner really exists in the linkable lexicon.

    Returns (accepted, rejected); rejected entries carry a machine-readable reason
    so yield problems are diagnosable from the drafts file itself.
    """
    if not isinstance(raw_relations, list):
        return [], []
    accepted, rejected = [], []
    seen_partners = set()
    for rel in raw_relations[:MAX_PROPOSALS_PER_WORD]:
        relation = rel.get("relation") if isinstance(rel, dict) else None
        partner_norm = normalize(rel.get("partner", "")) if isinstance(rel, dict) else ""
        partner_pos = str(rel.get("partner_pos", "")).strip().upper() if isinstance(rel, dict) else ""
        label = str(rel.get("label", "")).strip() if isinstance(rel, dict) else ""
        reason = None
        if relation not in RELATIONS:
            reason = "bad_relation"
        elif not label:
            reason = "empty_label"
        else:
            status = by_key.get((partner_norm, partner_pos))
            if status is None:
                # POS fallback: the model often guesses the wrong POS for a real
                # word; accept a unique lexicon entry for that lemma instead.
                candidates = by_norm.get(partner_norm, [])
                eligible = [c for c in candidates if c[1] == "eligible"]
                pick = eligible[0] if len(eligible) == 1 else (candidates[0] if len(candidates) == 1 else None)
                if pick:
                    partner_pos, status = pick
            if status is None:
                reason = "partner_not_in_lexicon"
            elif (partner_norm, partner_pos) == (word["normalized"], word["pos"]):
                reason = "self_loop"
            elif (partner_norm, partner_pos) in seen_partners:
                reason = "duplicate_partner"
        if reason:
            rejected.append({
                "relation": relation, "partner": partner_norm, "partner_pos": partner_pos,
                "label": label, "reason": reason,
            })
            continue
        seen_partners.add((partner_norm, partner_pos))
        accepted.append({
            "relation": relation,
            "partner": partner_norm,
            "partner_pos": partner_pos,
            "label": label,
            "review": {"status": "pending", "reviewer": None, "reviewed_at": None, "note": ""},
        })
    return accepted, rejected


def cmd_words(args: argparse.Namespace) -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    words = candidate_words(conn, args.limit)
    drafts = load_drafts()
    known = {item["key"] for item in drafts["items"]}
    fresh = [w for w in words if w["key"] not in known]
    print(f"零关系候选词（频率前 {len(words)}）：未起草 {len(fresh)}")
    for word in fresh[: args.show]:
        print(f"  {word['word']} ({word['pos']})  freq={word['freq']:.1f}  {word['gloss']}")


def cmd_draft(args: argparse.Namespace) -> None:
    api_key = os.environ.get("MAILLAGE_API_KEY", "")
    model = os.environ.get("MAILLAGE_MODEL", "")
    api_base = os.environ.get("MAILLAGE_API_BASE", "https://api.openai.com/v1")
    if not args.dry_run and (not api_key or not model):
        raise SystemExit(
            "draft 需要 MAILLAGE_API_KEY 与 MAILLAGE_MODEL："
            "用环境变量传入，或写入项目根目录的 .env.local（已 gitignore）。"
        )

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    words = candidate_words(conn, args.limit)
    by_key, by_norm = lexicon_lookup(conn)
    drafts = load_drafts()
    known = {item["key"] for item in drafts["items"]}
    todo = [w for w in words if w["key"] not in known]
    print(f"待起草 {len(todo)} / 候选 {len(words)}（已处理 {len(known)} 个词，幂等跳过）")
    if not todo:
        return

    if args.dry_run:
        batch = todo[: args.batch_size]
        prompt = build_prompt(batch)
        print(f"--- dry-run：首批 {len(batch)} 词，prompt 约 {len(prompt)} 字符 ---")
        print(prompt)
        return

    total_words = total_props = total_bad = 0
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
        returned = {item.get("key"): item for item in raw.get("items", []) if isinstance(item, dict)}
        for word in batch:
            item = returned.get(word["key"])
            proposals, rejected = validate_word(item.get("relations") if item else None, word, by_key, by_norm)
            drafts["items"].append({
                "key": word["key"],
                "word": {"lemma": word["word"], "normalized": word["normalized"], "pos": word["pos"]},
                "proposals": proposals,
                "rejected": rejected,
                "model": model,
                "drafted_at": now_iso(),
            })
            total_props += len(proposals)
            total_bad += len(rejected)
        total_words += len(batch)
        save_drafts(drafts)
        print(f"  批次 {start // args.batch_size + 1}: {len(batch)} 词，累计提议 {total_props} 条（作废 {total_bad}）")
    print(f"完成：处理 {total_words} 词，有效提议 {total_props} 条，作废 {total_bad}。写入 {DRAFTS.relative_to(ROOT)}")
    print("下一步：人工把每条提议的 review.status 改为 accepted / rejected，然后运行 build_graph.py 重建。")


def cmd_stats(_args: argparse.Namespace) -> None:
    drafts = load_drafts()
    counts: dict[str, int] = {}
    reasons: dict[str, int] = {}
    props = 0
    empty = 0
    for item in drafts["items"]:
        if not item.get("proposals"):
            empty += 1
        for prop in item.get("proposals", []):
            props += 1
            status = prop.get("review", {}).get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        for rej in item.get("rejected", []):
            reason = rej.get("reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
    print(f"{DRAFTS.relative_to(ROOT)}: {len(drafts['items'])} 词（{empty} 词无提议），{props} 条提议，{counts}")
    if reasons:
        print(f"作废 {sum(reasons.values())} 条，原因分布：{reasons}")


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_words = sub.add_parser("words", help="列出零关系候选词（不调用 API）")
    p_words.add_argument("--limit", type=int, default=None, help=f"只取频率前 N 个（默认 {CORE_TARGET}）")
    p_words.add_argument("--show", type=int, default=20)
    p_words.set_defaults(func=cmd_words)

    p_draft = sub.add_parser("draft", help="调用 completion API 提议首条关系")
    p_draft.add_argument("--batch-size", type=int, default=15)
    p_draft.add_argument("--limit", type=int, default=None, help=f"只处理频率前 N 个候选词（默认 {CORE_TARGET}）")
    p_draft.add_argument("--timeout", type=int, default=120)
    p_draft.add_argument("--dry-run", action="store_true", help="只打印首批 prompt，不调用 API")
    p_draft.set_defaults(func=cmd_draft)

    p_stats = sub.add_parser("stats", help="统计提议与审校状态")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
