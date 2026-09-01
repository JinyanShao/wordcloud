# wordcloud data pipeline

The browser consumes `graph-data.js`. Raw downloads, SQLite databases, intermediate JSON, and generated reports are intentionally not committed to keep the repository small.

## Install build dependencies

```bash
python3 -m pip install -r requirements-build.txt
pnpm install
```

The browser artifact itself has no package runtime dependency.

## Rebuild the lexicon

```bash
node scripts/extract_seed.mjs
python3 scripts/build_data.py build
```

Use a Python environment containing the packages in `requirements-build.txt`.

Inputs:

- `data/raw/FleLex_TT_Beacco.tsv`
- `data/raw/Lexique400.tsv`
- `dict.js`
- `data/sources.json`
- `sql/schema.sql`
- `data/processed/editorial-seed.json` (generated from the historical `data.js`)

Outputs:

- `data/processed/wordcloud.sqlite`
- `data/processed/eligible-lexicon.csv`
- `data/reports/lexicon-audit-v1.md`
- `data/reports/lexicon-audit-sample-500.csv`

The build is destructive only to generated files under `data/processed` and `data/reports`. Raw downloads and the hand-authored `data.js` are never modified. These generated outputs are ignored by Git.

## Complete the stratified review

The completed v1 decisions are stored in `data/audit-review-v1.json`. Apply them to a clean rebuild and sync them into SQLite:

```bash
python3 scripts/apply_audit_review.py
python3 scripts/build_data.py sync-review
```

Accepted decisions are `agree`, `override_eligible`, `override_auxiliary`, `override_excluded`, and `defer`.

## Rebuild the global graph

```bash
python3 scripts/build_graph.py
node scripts/layout.mjs
python3 scripts/export_runtime.py
python3 scripts/build_summary.py
python3 scripts/validate_data.py
```

Outputs:

- `data/processed/graph-input.json`: combined layout graph
- `data/processed/layout-positions.json`: deterministic browser coordinates
- `graph-data.js`: compact static browser payload
- `data/build-summary.json`: checked public build manifest used by README and validation
- `data/reports/build-validation.md`: build evidence and invariant checks

The current checked build is recorded in `data/build-summary.json`: 7,985 rendered nodes, including 7,314 eligible lexemes and 671 support lexemes; 6,495 formal relations; 16,058 browser layout links; 31,328 French definitions; 79.3% formal-relation coverage for eligible rendered words; one connected component.

## Build the core-word gap list

```bash
python3 scripts/build_gap_list.py
```

Read-only against `data/processed/wordcloud.sqlite`; run it after any graph rebuild to refresh priorities.

Outputs:

- `data/reports/core-word-gap-list.csv`: sortable per-word gap table (`in_core=1` marks the current ~1,000 core words)
- `data/reports/core-word-gap-list.md`: bucket counts, rules, and top examples

Buckets follow the priority order in `handover/7.27-handover.md`: P1 high-frequency words with no official edge, P2 single-edge words, P3 multi-sense bridge words, P4 confusable candidates without an evidence-checked trap/compare edge, P5 B2–C1 words with DBnary senses but no syn/ant edge.

## Draft `compare` relations with a completion API

```bash
python3 scripts/ai_compare_draft.py pairs            # inspect candidates, no API call
python3 scripts/ai_compare_draft.py draft --dry-run  # inspect the first prompt
WORDCLOUD_API_KEY=... WORDCLOUD_MODEL=... python3 scripts/ai_compare_draft.py draft --limit 30
python3 scripts/ai_compare_draft.py stats
```

`WORDCLOUD_API_BASE` defaults to `https://api.openai.com/v1`; any OpenAI-compatible chat completion endpoint works. Standard library only, no new dependency. Credentials can also go in a `.env.local` file at the project root (`WORDCLOUD_API_KEY=...` / `WORDCLOUD_MODEL=...` lines) — it is git-ignored and loaded automatically; never hardcode keys in tracked scripts.

Candidates are official syn edges where both endpoints rank in the top 2,000 eligible lexemes by frequency and no compare edge exists yet (currently 412 pairs). Drafts are appended to `data/processed/ai-compare-drafts.json` — this JSON file is the durable store, because `build_graph.py` wipes and rebuilds `official_edges` on every run. The script is idempotent: keys already in the file are skipped, so interrupted runs and gap-filling re-runs cost nothing extra.

Evidence-check and publish:

1. Open `data/processed/ai-compare-drafts.json`, edit the draft text if needed, then set `review.status` to `accepted` or `rejected` with evidence-check metadata.
2. Re-run the graph build (`build_graph.py` → `layout.mjs` → `export_runtime.py` → `validate_data.py`). Accepted drafts are re-applied into `official_edges` as `relation='compare'`, `review_status='evidence_checked'`, sourced to `wordcloud_evidence_checks` with the draft provenance (`origin`, `key`, `model`) in `source_record`.

AI drafts never enter `official_edges` without passing source grounding and automated evidence checks. This gate does not mean a separate human reviewer verified every published relation.

## Draft first edges for zero-relation core words (P1)

```bash
python3 scripts/ai_first_edge_draft.py words            # inspect candidates, no API call
python3 scripts/ai_first_edge_draft.py draft --dry-run  # inspect the first prompt
python3 scripts/ai_first_edge_draft.py draft --limit 30 # pilot batch
python3 scripts/ai_first_edge_draft.py stats
```

Same credentials as the compare drafter (`.env.local` or env vars). Candidates are the top 1,000 eligible words by frequency with zero official edges — the `in_core` P1 set of the gap list. The model proposes up to 2 relations per word (`syn` / `ant` / `fam`) and is explicitly allowed to propose none. Every proposed partner is validated before it reaches the review file: the normalized lemma must exist as an `eligible` or `auxiliary` lexeme (auxiliary words like genre/type/milieu enter the graph as support nodes once an evidence-checked edge needs them), a wrong-POS guess falls back to a unique lexicon entry for that lemma, and anything else is discarded with a machine-readable reason recorded under `rejected` in the drafts file (`stats` shows the reason breakdown).

Drafts live in `data/processed/ai-first-edge-drafts.json` (durable store, idempotent — words with zero proposals are also recorded so re-runs never re-bill them). Evidence-check each proposal (`review.status` → `accepted` / `rejected`), then rebuild the graph. Accepted proposals become evidence-checked official edges with confidence 0.7 and `origin: ai_first_edge_draft` provenance, and the pair is added to the seed layout signal so confirmed relations pull together in the global view.

## Data boundaries

- `layout_links` influence cartography and do not count as official coverage.
- `official_edges` are source-grounded or evidence-checked claims shown to learners.
- `personal_links` remain browser-local under `wordcloud.personal.v2` and are not stored in this database.
- `CLUSTERS` in the original `data.js` are hand-authored prototype scaffolding, not Lexique data.
