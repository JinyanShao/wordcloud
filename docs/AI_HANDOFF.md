# AI handoff

## Durable product state — 2026-09-07

- The static runtime was rebuilt from the registered sources.  It now contains 9,067 rendered nodes, 9,187 sourced formal relations, 45,095 French definitions, and one connected component.  The exact public figures are in `data/build-summary.json`.
- A1/A2 aligned content words (`NOM`, `VER`, `ADJ`, non-functional `ADV`) are eligible main-map entries.  Closed-class words and functional adverbs remain auxiliary.  This brings common lookup words such as `école`, `maison`, `chat`, `avoir`, and `bonjour` into the runtime.
- The family UI uses only `fam + sourced + derivational_morphology` relations.  The generated audit records 3,077 such edges, 4,652 connected word entries, and 1,644 partial families.  A partial family is not an exhaustive linguistic family.  `semantic_derivation` is shown as an irregular family link, not as a productive suffix rule.
- The old 500-row audit sample changed with the eligibility policy.  `scripts/apply_audit_review.py` carries a decision forward only when its lemma still occurs in the new sample; 153 reviews carry forward and 347 rows remain unreviewed.  Do not describe the new 500-row sample as fully human-reviewed.
- DBnary now uses the registered `official-snapshot-2026-09-01` source snapshot because the old source URL returned 404.  The source hash is pinned in `data/sources.json`.

## Verification completed

- `pnpm check:full` — 18/18 build checks passed.
- `pnpm check:runtime`, `pnpm families:check`, six unit tests, `node --check app.js`, and `git diff --check` passed.
- Local browser check confirmed common lookup words, accent-insensitive `ecole`, sourced word-family rendering across prefix/suffix/conversion/irregular-family types, and no mobile horizontal overflow.

## Release status and next work

- Changes are ready for the intended-file commit; GitHub Pages has not yet been published from this worktree.  The current browser console has only a non-functional missing `favicon.ico` 404.
- The next content-quality priority is editorial review of the 347 new audit-sample rows and learner-facing Chinese explanations/examples.  Do not turn spelling similarity or AI drafts into sourced word-family claims.
