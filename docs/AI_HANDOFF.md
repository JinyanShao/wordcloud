# AI handoff

## Durable product state — 2026-09-07

- `data/build-summary.json` is the canonical source for build-scale figures.  Its current terms are: 9,067 rendered lexical entries (all runtime nodes and all searchable entries), made of 9,046 eligible main-map entries and 21 rendered support entries; 9,187 formal relations; 45,095 French definitions; and one connected component.  A lemma with different POS values is more than one lexical entry.
- A1/A2 aligned content words (`NOM`, `VER`, `ADJ`, non-functional `ADV`) are eligible main-map entries.  Closed-class words and functional adverbs remain auxiliary.  This brings common lookup words such as `école`, `maison`, `chat`, `avoir`, and `bonjour` into the runtime.
- The family UI uses only `fam + sourced + derivational_morphology` relations.  The generated audit records 3,077 such edges, 4,652 connected word entries, and 1,644 partial families.  A partial family is not an exhaustive linguistic family.  `semantic_derivation` is shown as an irregular family link, not as a productive suffix rule.
- The old 500-row audit sample changed with the eligibility policy.  `scripts/apply_audit_review.py` carries a decision forward only when its lemma still occurs in the new sample; 153 reviews carry forward and 347 rows remain unreviewed.  Do not describe the new 500-row sample as fully human-reviewed.
- DBnary now uses the registered `official-snapshot-2026-09-01` source snapshot because the old source URL returned 404.  The source hash is pinned in `data/sources.json`.
- Phase 1 learner content is deterministic and contains no AI text: `learner-content.js` projects 4,652 participating lexical entries, 3,077 direct sourced family relations, and 142 observed structure groups.  It is generated from SQLite facts, does not duplicate definitions/examples, and labels observed structure without claiming a productive rule.  `data/learner-content-overrides.json` is intentionally empty and may only add future teaching classifications or notes.

## Verification completed

- `pnpm check:full` — 18/18 build checks passed.
- `pnpm check:runtime`, `pnpm families:check`, six unit tests, `node --check app.js`, and `git diff --check` passed.
- Local browser check confirmed common lookup words, accent-insensitive `ecole`, sourced word-family rendering across prefix/suffix/conversion/irregular-family types, and no mobile horizontal overflow.
- Learner projection build/SQLite validation, static-runtime validation, nine unit tests, and a local side-panel check passed.

## Release status and next work

- GitHub Pages was published from `main` at `15ced88` on 2026-09-07.  Runtime CI and deployment succeeded; the production site was checked with accent-insensitive `ecole` search and the `école` family.  The browser console has only a non-functional missing `favicon.ico` 404.
- The next content-quality priority is editorial review of the 347 new audit-sample rows and learner-facing Chinese explanations/examples.  Do not turn spelling similarity or AI drafts into sourced word-family claims.
