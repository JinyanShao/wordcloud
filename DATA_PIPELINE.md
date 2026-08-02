# wordcloud data pipeline

The browser consumes generated static artifacts, but source alignment and review live in SQLite.

## Verified release build

Use the verified command for a reproducible release candidate. It validates every declared raw source against its reviewed SHA-256, runs the existing pipeline in its required order, writes `data/reports/build-manifest.json`, then verifies that manifest against the generated artifacts.

```bash
python3 -m pip install -r requirements-build.txt
pnpm install --frozen-lockfile
pnpm data:fetch       # downloads only missing or mismatched public sources; rejects a changed upstream snapshot
pnpm build:verified
```

`data/raw/` remains ignored because the source archives are large and license-bound. Do not replace a locked hash just to make a build pass: review the upstream release, its license and its lexical impact first. `pnpm data:verify-sources` performs the same lock check without network access. GitHub Actions runs this full sequence for pull requests and pushes to `main`; it validates only and never deploys.

The release baseline fixes Python 3.11.15, Node 26.5.0, pnpm 11.17.0 and the direct Python build dependencies in `requirements-build.txt`. Changing a lock, source hash or build script intentionally changes `build-manifest.json` and therefore requires review.

## Install build dependencies

```bash
python3 -m pip install -r requirements-build.txt
pnpm install
```

The browser artifact itself has no package runtime dependency.

## Individual pipeline steps

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

The build is destructive only to generated files under `data/processed` and `data/reports`. Raw downloads and the hand-authored `data.js` are never modified.

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
python3 scripts/validate_data.py
```

Outputs:

- `data/processed/graph-input.json`: combined layout graph
- `data/processed/layout-positions.json`: deterministic browser coordinates
- `graph-data.js`: compact static browser payload
- `data/reports/build-validation.md`: build evidence and invariant checks

The current verified counts are recorded in `data/reports/build-validation.md` and `data/reports/build-manifest.json`; do not duplicate volatile totals in this document.

## Build the core-word gap list

```bash
python3 scripts/build_gap_list.py
```

Read-only against `data/processed/wordcloud.sqlite`; run it after any graph rebuild to refresh priorities.

Outputs:

- `data/reports/core-word-gap-list.csv`: sortable per-word gap table (`in_core=1` marks the current ~1,000 core words)
- `data/reports/core-word-gap-list.md`: bucket counts, rules, and top examples

Buckets follow the priority order in `handover/7.27-handover.md`: P1 high-frequency words with no official edge, P2 single-edge words, P3 multi-sense bridge words, P4 confusable candidates without a reviewed trap/compare edge, P5 B2–C1 words with DBnary senses but no syn/ant edge.

## Audit DBnary definition gaps with Wiktextract

This is a reproducible **audit** path, not an alternative runtime importer. It uses the upstream MIT-licensed [Wiktextract](https://github.com/tatuylonen/wiktextract) CLI against an official French Wiktionary dump to classify only the runtime learning lexemes that have no DBnary sense. It never inserts extracted glosses into SQLite or `graph-data.js`.

```bash
python3 -m venv /tmp/wordcloud-wiktextract
/tmp/wordcloud-wiktextract/bin/pip install -r requirements-wiktextract-audit.txt
WIKTWORDS_BIN=/tmp/wordcloud-wiktextract/bin/wiktwords pnpm wiktextract:audit
```

Place the selected dump at `data/raw/wiktextract/frwiktionary-YYYYMMDD-pages-articles.xml.bz2` and set the `DUMP` constant in `scripts/audit_wiktextract.py` to that filename before the run. The generated report records the exact dump hash and extractor commit. A “Wiktionary usable differential” means the selected dump contains a same-POS gloss, but is not proof of a DBnary parser omission until DBnary is compared using a matching source snapshot. Raw dumps and JSONL output are intentionally ignored by Git; the Markdown report is the review artifact.

Build the review queue without publishing anything:

```bash
pnpm dbnary:alignment-queue
```

When DBnary publishes the historical extract for that exact dump date, analyze it with the existing importer and resolve the queue:

```bash
python3 scripts/import_dbnary.py analyze --raw data/raw/dbnary/fr_dbnary_ontolex_YYYYMMDD.ttl.bz2 \
  --analysis-output data/processed/dbnary-aligned-analysis.json \
  --report-output data/reports/dbnary-aligned-analysis.md \
  --expected-sha256 <reviewed-hash>
pnpm dbnary:alignment-queue -- --aligned-analysis data/processed/dbnary-aligned-analysis.json
```

The queue is a review artifact, not an approval artifact: it only distinguishes source coverage from a parser-capture signal. No Wiktextract text is copied into product data.

## Review P0 Wiktextract definitions

For the 59 A1–A2 lexemes confirmed absent from the aligned DBnary extract, reuse the pinned Wiktextract output to create a content-review queue:

```bash
pnpm wiktextract:p0:analyze
```

Review `data/processed/wiktextract-p0-review.json`, then record decisions in `data/reports/wiktextract-p0-review.csv`. Accepted rows require pipe-separated candidate sense IDs, a reviewer, and a review date. Merge and approve only after every row is decided:

```bash
pnpm wiktextract:p0:analyze
pnpm wiktextract:p0:approve
```

The approved artifact is optional input to `build_graph.py`; pending candidates are never read by the build. The adapter aligns records and enforces review metadata, while all Wiktionary parsing remains upstream Wiktextract functionality.

## Data boundaries

- `layout_links` influence cartography and do not count as official coverage.
- `official_edges` are sourced or reviewed claims shown to learners.
- `personal_links` remain browser-local under `wordcloud.personal.v2` and are not stored in this database.
- `CLUSTERS` in the original `data.js` are hand-authored prototype scaffolding, not Lexique data.
