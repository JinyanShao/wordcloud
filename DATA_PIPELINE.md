# maillage data pipeline

The browser consumes generated static artifacts, but source alignment and review live in SQLite.

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

- `data/processed/maillage.sqlite`
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

The current verified build contains 7,314 eligible nodes, 57 official support nodes, 20,270 combined browser layout edges, 98 reviewed prototype official edges, one connected component, and no layout islands.

## Data boundaries

- `layout_links` influence cartography and do not count as official coverage.
- `official_edges` are sourced or reviewed claims shown to learners.
- `personal_links` remain browser-local under `maillage.personal.v2` and are not stored in this database.
- `CLUSTERS` in the original `data.js` are hand-authored prototype scaffolding, not Lexique data.
