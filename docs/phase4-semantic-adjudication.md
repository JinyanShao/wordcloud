# Phase 4C — Full Semantic Adjudication

Input: `data/phase4/learner-candidate-160-review.jsonl` (160 deterministically curated candidates from Phase 4B).
Output: `data/phase4/learner-candidate-160-adjudicated.jsonl` (160 rows), `data/phase4/learner-candidate-final.json` (frozen KEEP set).

This phase performed genuine French learner-primary semantic judgment on each of the 160 candidates: for every entry, is there a source sense that accurately represents the sense a modern learner should master first for this lemma+POS, and is that lexeme/POS combination itself learner-appropriate? No automatic rules (sense-1 default, frequency, family status) were used to pick senses; every choice was a semantic call, revisited in a second self-review pass before freezing.

## Summary counts

| | Count |
|---|---|
| KEEP | 154 |
| DROP | 6 |
| Total adjudicated | 160 |

**KEEP by CEFR** (kept / input):
- A1: 47 / 50
- A2: 33 / 35
- B1: 49 / 50
- B2: 25 / 25

**KEEP by POS**:
- NOM: 91
- VER: 49
- ADJ: 13
- ADV: 1

**Confidence distribution (KEEP only)**: high 122, medium 32, low 0.
No `low`-confidence KEEPs were forced through — where the semantic fit was genuinely weak, the item was dropped instead of hedged with a low-confidence keep.

**External dictionary checks**: 0. All 160 adjudications were resolved from the packet's source senses and general French-language knowledge; no case required outside lookup to determine modern learner-primary usage.

## Why the result (154/6) differs from the ~100–120 estimate

The 160-item pool had already been through deterministic frequency-based curation and had `travers|NOM` / `cesse|NOM` excluded in Phase 4B, plus a requirement that every candidate carry at least one sourced French sense. In practice the large majority of the remaining candidates are ordinary, unambiguous core vocabulary (concrete nouns like *fenêtre*, *table*, *cheval*; common verbs like *dormir*, *acheter*, *envoyer*) where a clear learner-primary sense exists and no defect criterion applies. The estimate in the brief was a prior, not a target — quality findings were left to stand rather than padding the DROP count to hit a number.

## DROP reason categories (6 total)

1. **POS/learner-use mismatch** (1): `rien|NOM` — the learner-primary "rien" is the indefinite pronoun in `ne...rien`; the packet's noun senses (`un rien` = a trifle, `le néant`, plus an unrelated Lao-language sense on a second entry) do not represent that usage.
2. **Fixed-expression-dominant** (2): `suite|NOM` (driven by `tout de suite`), `grâce|NOM` (driven by `grâce à`) — the CEFR-A1 frequency of these lemmas is attributable to a lexicalized preposition/adverb phrase, not to the standalone noun senses on offer, which are either too abstract (continuation/series) or too literary-register (elegance, pardon, religious grace) to be A1 learner-primary.
3. **No dominant ordinary sense among a highly specialized/regional sense list** (1): `galerie|NOM` — all 22+ senses are architectural, art-historical, mining/speleological, or regional-technical (Québec balcony, French car roof rack); no single sense stands out as *the* modern everyday meaning at A2.
4. **Low standalone pedagogical value despite a legitimate single sense** (1): `téléviser|VER` — real usage is almost exclusively the passive/participial "être télévisé"; the active infinitive is rarely produced by learners.
5. **Sense is a data artifact, not a definition** (1): `événement|NOM` — the only source sense is "spelling variant of évènement," a cross-reference with no semantic content; binding to it would not actually tell a learner what an "événement" is.

## Notable difficult cases (hardest 10 to adjudicate)

1. **société|NOM** (A1) — abstract "human society" vs. concrete "company/business." Chose the business-association sense (4) as more A1-appropriate register; medium confidence.
2. **part|NOM** (A1) — the partitive "a share/portion" sense is real and taught, but much of the word's real-world frequency is driven by `quelque part` / `d'autre part`, which are more idiomatic. Kept, but flagged as borderline.
3. **échelle|NOM** (B2) — genuine toss-up between the literal "ladder" (chosen, base/etymological sense) and the very common figurative "scale" (à l'échelle mondiale), which is arguably more salient in B2-level argumentative texts.
4. **relever|VER** (B1) — 44 senses with no single dominant modern meaning; chose "faire remarquer, souligner" (to note/point out) over the literal "lift again" because it best matches frequent modern written usage ("on relève que...").
5. **menacer|VER** (B1) — the sense list is unusually fragmented (22 micro-senses describing grammatical complementation patterns rather than clean meanings); chose "tenir des propos menaçants" as the closest fit to interpersonal threat.
6. **opposer|VER** (B1) — chose the pronominal "s'opposer à" (to object to) over the transitive "put in contrast," since the reflexive construction is the more frequent modern usage pattern.
7. **introduire|VER** (B2) — chose the figurative "établir, faire adopter" (introduce a reform/policy) over the literal "insert into," reflecting common B2-level civic/political register.
8. **poche|NOM** (B1) — chose the specific "garment pocket" sense over a broader, vaguer "soft container" sense that arguably functions as the entry's true headword sense.
9. **milieu|NOM** (A1) — resolved cleanly because the source data itself flags one sense "(Plus courant)"; included here as a reminder that such explicit markers are a legitimate (not decisive on their own, but strong) signal.
10. **grâce|NOM** (A1, dropped) — hardest DROP call: "grâce" has real standalone senses (elegance, favor, pardon), but none is plausibly what drives its A1 frequency ranking, which is almost certainly `grâce à`.

## Validation performed

- Adjudication file has exactly 160 lines; every input `key` appears exactly once; no unknown keys.
- Every KEEP's `selected_sense_id` / `selected_entry_id` / `selected_sense_number` is copied verbatim from that record's `source_senses` (no fabricated senses).
- Every DROP has all three selection fields `null`.
- The `learner-candidate-final.json` key set is identical to the adjudication file's KEEP key set.
- No learner-facing prose fields (`gloss_zh_short`, `example_fr`, `example_zh`, usage notes, family explanations) were generated anywhere in this phase's outputs.
- `travers|NOM` and `cesse|NOM` confirmed absent from input and outputs.
- Packaging is deterministic (single script, no randomness, re-run reproduces identical output).

Semantic correctness of individual sense choices is a judgment call, not something the validator can prove — it is documented above for the hardest cases and open to a maintainer's second read.
