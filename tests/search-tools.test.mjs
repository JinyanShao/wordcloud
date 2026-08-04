import assert from "node:assert/strict";
import {
  normalizeSearchText,
  searchLexemes,
} from "../src/search-tools.mjs";

const entries = [
  { id: "1", word: "faire", pos: "VER", gloss: "做", freq: 100, isCore: true, aliases: ["fais", "fait", "font"] },
  { id: "2", word: "faible", pos: "ADJ", gloss: "弱的", freq: 20, aliases: ["faibles"] },
  { id: "3", word: "se lever", pos: "VER", gloss: "起床", freq: 30, aliases: ["se lève", "s'est levé"] },
  { id: "4", word: "être", pos: "VER", gloss: "是", freq: 120, aliases: ["suis", "est", "sont"] },
  { id: "5", word: "établir", pos: "VER", gloss: "建立", freq: 40, aliases: ["établit"] },
];

assert.equal(normalizeSearchText("  se   lever  "), "se lever");
assert.equal(normalizeSearchText("s’etablir"), "s'etablir");

const exact = searchLexemes(entries, "faire");
assert.equal(exact.results[0].entry.id, "1");
assert.equal(exact.results[0].matchType, "exactWord");

const alias = searchLexemes(entries, "suis");
assert.equal(alias.results[0].entry.id, "4");
assert.equal(alias.results[0].entry.word, "être");
assert.equal(alias.results[0].matchType, "exactAlias");

const reflexive = searchLexemes(entries, "  se   lever ");
assert.equal(reflexive.results[0].entry.id, "3");
assert.equal(reflexive.results[0].matchType, "exactWord");

const starts = searchLexemes(entries, "fai");
assert.equal(starts.results[0].entry.id, "1");
assert.equal(starts.results[0].matchType, "startsWord");

const typo = searchLexemes(entries, "fiare", { suggestionLimit: 3 });
assert.equal(typo.results.length, 0);
assert.equal(typo.suggestions[0].entry.id, "1");
assert.equal(typo.suggestions[0].matchedText, "faire");

const accentless = searchLexemes(entries, "etablir", { suggestionLimit: 3 });
assert.equal(accentless.results.length, 0);
assert.equal(accentless.suggestions[0].entry.id, "5");

const missing = searchLexemes(entries, "zzzz", { suggestionLimit: 3 });
assert.equal(missing.results.length, 0);
assert.equal(missing.suggestions.length, 0);
