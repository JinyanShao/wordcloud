# Phase 4C-v2 — Adversarial Semantic Challenge Review

Adversarial re-review of a targeted subset of the Phase 4C adjudication (`50a396a`), specifically hunting for cases where v1 got the call wrong — not re-confirming v1's reasoning.

## Reviewed subset

Union of four sets, deduplicated:

- **A** — all v1 `confidence == medium` (36)
- **B** — all v1 `decision == drop` (6)
- **C** — all v1 `decision == keep` + `confidence == high` where the input record has `source_sense_count >= 10`, `same_lemma_multiple_pos`, or `marked_or_specialized_sense_present` (75)
- **D** — the 18 keys the external reviewer named explicitly

**Union: 113 of 160 records reviewed.** (Above the "few dozen" estimate in the brief because set C alone — high-confidence keeps carrying a review flag — is large; the union was computed and applied exactly as specified rather than trimmed to hit a smaller number.)

## Corrections: 11

| Key | Change |
|---|---|
| `galerie\|NOM` | **DROP → KEEP**, sense `__ws_3_galerie__nom__1` |
| `suite\|NOM` | **DROP → KEEP**, sense `__ws_4_suite__nom__1` |
| `habitude\|NOM` | sense changed `__ws_1` → `__ws_2` (same entry) |
| `gagner\|VER` | confidence high → medium |
| `création\|NOM` | confidence high → medium |
| `consommation\|NOM` | confidence high → medium |
| `mobile\|ADJ` | confidence high → medium |
| `partie\|NOM` | confidence high → medium |
| `réduction\|NOM` | confidence high → medium |
| `relever\|VER` | confidence unchanged (medium); external check added, unverified frequency claim removed from reasoning |
| `menacer\|VER` | confidence medium → high (external check validated the sense choice) |

**DROP → KEEP: 2** (`galerie|NOM`, `suite|NOM`)
**KEEP → DROP: 0**
**Selected-sense changes: 1** (`habitude|NOM`, same entry, sense 1 → sense 2)
**Confidence changes: 8** (6 downgraded high→medium: `gagner`, `création`, `consommation`, `mobile`, `partie`, `réduction`; 1 upgraded medium→high: `menacer`; 1 unchanged but evidentially strengthened: `relever`)
**External checks performed: 2** (`relever|VER`, `menacer|VER`, both via Larousse.fr — see `external_evidence` in the corrections file)

The other 102 reviewed records were re-examined against the 7-point adversarial checklist (sense-1 default, missed more-modern sense, fixed-expression misreading, common-sense-misjudged-as-specialized, specialized-sense-misjudged-as-primary, false-single-sense confidence, unverified frequency framing) and held: their v1 decision, sense, and confidence stand.

## The two reversals in detail

**`galerie|NOM`**: v1 dropped it, reasoning that the entry's ~26 senses were "architectural/artistic/regional/technical... without one obviously dominant everyday use." That reasoning conflated "many senses are specialized" with "no sense is ordinary." Sense 3 — *"Salle de palais, de musée, plus longue que large où se trouvent exposées des collections de tableaux et d'œuvres d'art"* — is a completely ordinary art-gallery sense that needs no external corroboration. Corrected to KEEP.

**`suite|NOM`**: v1 dropped it on the theory that its A1 frequency was purely an artifact of the locution `tout de suite`. On reflection, "la suite" (what comes next — *la suite de l'histoire*, *la suite du film*) is itself a normal, productive, standalone modern noun usage that a learner would want taught independently of that locution. Corrected to KEEP on sense 4 (*"Continuation, ce qui est ajouté à un ouvrage pour le continuer"*), medium confidence given senses 1/3/6 are also plausible readings of the same general idea.

**`habitude|NOM`** was not reversed on decision, but the sense pick was wrong: v1 chose sense 1 (*"Disposition acquise par des actes réitérés"* — an abstract, philosophical framing) purely because it was listed first. Sense 2 (*"Façon régulière de se comporter, d'agir, d'être"*) states the everyday meaning of "a habit" far more directly, with no dictionary-order justification for preferring sense 1.

## Confidence recalibration

Six items were downgraded from high to medium because re-examination found a second, equally-core modern sense that v1's reasoning had waved away as a non-issue rather than flagged as real competition (`gagner`: earn vs. win; `création`: act of creating vs. a creation/work; `consommation`: general consumption vs. a café order; `mobile`: movable vs. mobile-tech; `partie`: portion vs. game/match; `réduction`: decrease vs. discount). In each case the same sense was kept as primary — the correction is entirely to the confidence label, acknowledging the competition rather than asserting there was none.

Two items (`relever`, `menacer`) were hard enough — extreme polysemy (44 and 22 fragmented senses respectively) — to warrant a limited Larousse.fr check rather than resting on unverified "this is the most frequent sense" language. The check confirmed both picks were legitimate dictionary-recognized senses (not idiosyncratic), which raised `menacer` to high confidence (Larousse lists the interpersonal-threat reading first and as most basic) and left `relever` at medium (confirmed as a real sense, but the verb still has no single dominant meaning across its 44 senses).

## Final-v2 KEEP / DROP

- v1: 154 KEEP / 6 DROP
- v2 corrections: +2 KEEP (galerie, suite), 0 new DROPs
- **final-v2: 156 KEEP / 4 DROP**

Remaining DROPs: `rien|NOM` (POS mismatch), `grâce|NOM` (fixed-expression dominance), `téléviser|VER` (low standalone pedagogical value), `événement|NOM` (sense is a spelling-variant cross-reference, not a definition). These four were inside the reviewed union (B) and were re-challenged adversarially; none were overturned — the reasoning held on a second, skeptical read.

## Validation performed

- Every correction's `key` belongs to the original 160.
- Every correction's `old_decision` / `old_sense_id` / `old_confidence` matches `learner-candidate-160-adjudicated.jsonl` (v1) exactly.
- Every `new_sense_id` (where decision is keep) exists in that key's `source_senses` in the original 160-input packet.
- Every DROP has `selected_entry_id` / `selected_sense_id` / `selected_sense_number` all null.
- `learner-candidate-final-v2.json` = v1 KEEP set with corrections applied, verified by independent reconstruction (not just copied).
- No Chinese prose, no examples, anywhere in the v2 artifacts.
- Re-running the materialization script produces byte-identical output (deterministic).

As before: the validator confirms structural integrity, not semantic correctness. The reasoning for each correction is recorded for a human reviewer to check independently.
