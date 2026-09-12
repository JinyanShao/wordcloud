# Phase 4D — Full Learner Content Authoring

Full-scale authoring of `gloss_zh_short` / `usage_note_zh` / `example_fr` / `example_zh` for all 156 KEEP records frozen in `data/phase4/learner-candidate-final-v2.json` (commit `e91bb65`). No sense was reselected in this phase.

## Scope and counts

- **Source KEEP count:** 156
- **Authored count:** 156 (0 semantic blockers)
- **CEFR distribution:** A1 48 · A2 34 · B1 49 · B2 25
- **POS distribution:** NOM 93 · VER 49 · ADJ 13 · ADV 1
- **Usage notes written:** 15 of 156 (the rest are `null` by default, per instructions)

The 4 frozen DROPs (`rien|NOM`, `grâce|NOM`, `téléviser|VER`, `événement|NOM`) received no content and are absent from every Phase 4D artifact.

## Authoring approach

Each record was hand-authored from its frozen `selected_definition_fr` — read, understood, and turned into a Chinese gloss and a French example built to activate that exact sense and no sibling sense. Concretely this meant:

- Choosing example contexts that foreclose the competing sense a `confidence: medium` record carries (e.g. `gagner` → "*Il gagne deux mille euros par mois*" reads only as "earn," never "win"; `suite` → "*J'ai hâte de lire la suite de cette histoire*" reads only as "what happens next," never `tout de suite`; `société` → business-partner context, never "society at large").
- Respecting real morphology: pronominal-only verbs (`se fier à`, `s'opposer à`, `s'enfuir`) are written and conjugated in their pronominal form in the example, with a usage note stating that modern French uses only the pronominal form.
- Respecting plural-dominant usage: `vacance` is taught as `les vacances` with an explicit note that the plural is standard.
- Writing usage notes only where a construction/valency point has real teaching value (`plaire à`, `préférer... à`, `intéresser` vs. `s'intéresser à`, `servir à`, `condamner... à`, `soumettre... à`, `avoir tendance à`, `avoir l'habitude de`, plus the three pronominal notes and the vacances-plural note) — 15 total, the rest left `null`.

## Adversarial second-pass review

Re-reviewed 85 of the 156 records (the union of: 38 `confidence: medium`, 45 with `source_sense_count >= 10`, 15 `same_lemma_multiple_pos`, and the 24 explicitly named high-risk words, after dedup) against the 7-point checklist: gloss drift to a sibling sense, example ambiguity, French naturalness, Chinese fidelity, construction correctness, usage-note necessity, and sibling-sense bleed.

**Content corrections made in this pass: 0.** Every record held up under adversarial re-reading, including hard stress-tests on the genuinely risky ones (`menacer`'s threat-of-punishment example forces the interpersonal reading; `poche`'s "*de son manteau*" qualifier forces the garment-pocket reading over the generic-bag sense; `durable`'s shoe context forces "long-lasting" over "ecologically sustainable"; `bureau`'s "*posé sur le bureau, à côté de la lampe*" forces furniture over workplace). No sense was reselected — this pass could only fix prose, and found none that needed fixing.

**External checks in this pass: 0.** None of the 85 records required an authoritative dictionary lookup to confirm natural usage; all were resolvable from the frozen definition plus standard French usage knowledge.

## Anti-template QA

Automated structural checks (not a claim of semantic correctness):

- No duplicate `example_fr` or `example_zh` across the 156 records.
- No duplicate `gloss_zh_short` except one legitimate pair (`utiliser`/`employer`, true near-synonyms, each with its own distinct example).
- No `的的` or `地地` anywhere in the Chinese content.
- No empty `gloss_zh_short` / `example_fr` / `example_zh` (usage_note is allowed to be empty/null).
- Opening-skeleton scan for `C'est...`, `Il est...`, `Elle est...`, `Nous avons...`, `Cette chose...`, `Voici un/une...`: no pattern exceeds 5% of examples. `Nous avons` appears in 7/156 (4.5%), each continuing with a distinct verb and object (*fait un long voyage*, *un nouveau projet*, *pris le train*, *visité une galerie*, *eu une longue conversation*, *déplacé le canapé*, *déménagé récemment*) — natural variation from the passé composé auxiliary, not a stamped-out template.
- `content_status` is `external_semantic_authored` on every record, never `reviewed`.

## Structural validator

`data/phase4/learner-content-156-authored.json` and `data/phase4/learner-content-156-review.jsonl` were checked for:

- final-v2 KEEP count = 156.
- Authored records (156) + semantic_blockers (0) = 156.
- The 4 DROP keys are absent from both artifacts.
- The canonical key set exactly equals the final-v2 KEEP key set.
- `entry_id` / `sense_id` / `sense_number` / `runtime_lexeme_id` / `lemma` / `pos` / `cefr` match `learner-candidate-final-v2.json` 100% (no silent reselection).
- No duplicate stable keys.
- All semantic fields (`gloss_zh_short`, `example_fr`, `example_zh`) non-empty; `usage_note_zh` may be null.
- Review JSONL is a deterministic, byte-exact re-derivation of canonical + final-v2 (re-running the derivation script reproduces it exactly).

As instructed: this validator proves structural integrity (right keys, right frozen IDs, no templating fingerprints, no leaked drops), not semantic correctness. Semantic quality rests on the authoring + adversarial-review reasoning documented above, for a human to spot-check.

## What this phase did not touch

No changes to `learner-sense-content.js`, Phase 2C/3 content, `app.js`, the graph, family relations, the runtime builder, or the Pages workflow. No family-context prose. No merge to `main`, no deploy. `definition_fr` is retained only in the review JSONL as an audit aid, not duplicated into any runtime-facing artifact.
