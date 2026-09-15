# Phase 5B — Family Learning Prototype

Prototype to test whether an explicit path — *current exact sense → most valuable family relation → form change → semantic continuity between the two exact senses → one active guess → optional full family* — teaches better than just listing family members, which is all the current UI did before this change. 20 families, hand-authored pedagogy, one lightweight retrieval interaction per family. Not an SRS, not a coverage expansion, no account/score/queue.

## Why these 20 families

Selection was constrained to the same 1,644 `fam + sourced + derivational_morphology` partial families the production family UI already uses (0 new/invented relations). Within that set, 87 families have ≥2 members with an existing production learner aid, and 78 of those have at least one edge directly connecting two aided members (the only kind that can carry an honest exact-sense bridge). The 20 were picked from that 78 to hit every required category at once, not by ease:

- All four construction subtypes are represented: suffixation (13 relations), prefixation (8), semantic_derivation (4), conversion (3).
- Family size spans 2 (`loin/lointain`) to 17 (`porter`), with a genuine mix on both sides of the small/large line (small ≤4: 11 families; large 5+: 9 families).
- CEFR: A1 9 · A2 7 · B1 3 · B2 1 (anchor level). POS: ADJ 7 · VER 6 · NOM 6 · ADV 1 (`loin`, the only ADV in the qualifying pool with a real edge).
- Semantic alignment is not padded toward "easy": transparent 15, shifted 9, opaque 4 — see below for why several look transparent-on-paper but were deliberately marked otherwise.

**Named candidates from the brief, checked and resolved against real production data:**
`prendre/reprendre`, `tenir/retenir`, `étrange/étranger`, `possible`, `porter` all confirmed with real edges and included. `faire/fait`, `emploi/employer`, `public/publicité` also confirmed and included. All eight ended up in the final 20 — none needed substitution, but two (`emploi/employer`, `faire/fait`) turned out to be the two most important negative cases in the set (see below), not the easy wins their family relation would suggest.

## Distributions

| Family size | Count |
|---|---|
| 2 | 5 |
| 3 | 2 |
| 4 | 4 |
| 5 | 2 |
| 6 | 1 |
| 8 | 2 |
| 10 | 2 |
| 11 | 1 |
| 17 | 1 |

Construction: suffixation 13 · prefixation 8 · semantic_derivation 4 · conversion 3 (28 teaching relations total).
Semantic alignment: transparent 15 · shifted 9 · opaque 4.
Confidence (authoring confidence in the alignment call, not Phase 4's sense-selection confidence): high 20 · medium 8, 0 low.

## The point of the exact-sense layer: two cases that would have been wrong without it

This is the part of Phase 5B that isn't optional polish — it's the reason the prototype exists.

- **`emploi → employer`**: the family relation is completely real (conversion, both ends have production learner aids). But Phase 4's frozen exact sense for `employer|VER` is *"to use, to employ (a method)"* — general usage, not "to hire someone for a job." A learner who knows `emploi` = "job/employment" and sees `employer` in the family list would reasonably assume the verb means "to employ (for work)." It doesn't, under the sense actually bound here. This is marked **opaque**, and the interaction is built specifically to surface the mismatch rather than paper over it.
- **`faire → fait`**: `faire` = "to do," `fait` = "a fact." The conversion is real, but the current noun sense has solidified into something a literal "to do" → "a done thing" reading won't produce reliably. Marked **shifted**.

Two more worth naming: `actif` family's `action → actif` and `agir → action` relations look transparent from the construction alone, but the frozen `action|NOM` sense is specifically *"effect/influence"* (as in a drug's effect), not generic "an action" — so both were marked shifted rather than transparent, and the explanation says so explicitly. `porter → emporter` uses `en-`, which a learner has almost certainly seen mean "into" (`entrer`); here it means "away." That's marked shifted specifically to flag the false-friend prefix, in contrast to `porter → apporter`'s `a-`, which is marked transparent.

None of this would be visible from the family graph alone — it only shows up when the two ends' *actual bound senses* are read side by side. That comparison is the deliverable.

## Core-member selection

Families ≤4 members: all shown, no selection logic (11 of 20 families). Families 5+: 2–4 core members chosen for `porter` (17→4: `apporter`, `emporter`, `transport`, `rapport` — the four aided siblings, prioritizing rule 1 even though only two have a direct edge to the anchor), `faire` (10→2: `fait`, `façon`), `connaître` (8→3), `sécurité` (8→3), `sentiment` (11→3), `actif` (10→3). Core selection never determines semantic alignment — it only decides which members get a card at all; the alignment judgment is independent and was made per relation, not per family.

## Expand/collapse behavior

The new "词族学习" section shows only the 2–4 core teaching relations regardless of family size — `porter` at 17 members shows exactly 2 cards, not 17. The pre-existing "一起认识" section (untouched, still Phase 1 deterministic content) continues to list every member of the sourced family without pagination; for `porter` that's all 17 in one list. This was already true before Phase 5B and was out of scope to fix here (it doesn't break the panel — `.panel` already has `overflow:auto` — it just makes it a longer scroll). Documented as a known limitation, not silently patched.

## What the prototype cannot tell you yet

- No usage data: this validates that the exact-sense bridge is *renderable and honest*, not that it improves retention. That needs actual learners.
- 20 families is far short of the 1,644 available; the manual semantic-authoring step (reading both exact senses, judging alignment, writing the Chinese bridge) does not scale by simple repetition — it is exactly the kind of judgment call that broke on `emploi/employer` and `actif/action` above, and those breaks are only caught by a human reading both sides, not by any automatable rule.
- If this expands past a hand-authored prototype, the two costs that matter are: (1) semantic authoring time scales linearly with relation count, not family count — a size-17 family with 2 honest relations costs about the same authoring effort as two size-2 families; (2) every relation needs the same "does the frozen sense actually support this" check that caught `emploi/employer`, which cannot be skipped or approximated without risking exactly the kind of mechanical over-generalization this design is built to avoid.

## Validation performed

`scripts/validate_phase5_family_prototype.py` (also run as `tests/test_phase5_family_prototype.py`, 16 cases): exactly 20 families; every anchor and every teaching-relation endpoint resolves to a real sourced `fam + derivational_morphology` edge (no invented edge, no non-family-dimension edge accepted); every exact sense referenced matches `learner-sense-content.js` byte-for-byte; no duplicate family or relation; `semantic_alignment` restricted to the three-value enum; all learner-facing authored fields non-empty; `selected_core_members` is a subset of the real family; the 6 blocked/dropped keys (`rien|NOM`, `grâce|NOM`, `téléviser|VER`, `événement|NOM`, `travers|NOM`, `cesse|NOM`) never appear as a learner aid anywhere in the prototype; the existing 754-record learner runtime is asserted unchanged (99 phase2c + 499 phase3 + 156 phase4). As with prior phases, this proves structural/sourcing integrity, not that the Chinese pedagogy is correct — that rests on the authoring and the adversarial re-read documented above.
