import assert from "node:assert/strict";
import {
  exportLocalLearningData,
  loadPersonalState,
} from "../src/local-data-tools.mjs";

function memoryStorage(seed = {}) {
  const values = new Map(Object.entries(seed));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
  };
}

function throwingStorage() {
  return {
    getItem() {
      throw new Error("blocked");
    },
  };
}

const personal = loadPersonalState(memoryStorage({
  "wordcloud.personal.v2": JSON.stringify({
    nodes: [{ id: "mine-1", word: "flâner", x: "12", y: "bad" }, { id: "", word: "ignored" }],
    edges: [{ a: "mine-1", b: "official-1", label: "" }, { a: "missing", b: "official-2" }],
  }),
}), "wordcloud.personal.v2");
assert.equal(personal.error, null);
assert.equal(personal.data.nodes.length, 1);
assert.equal(personal.data.nodes[0].pos, "我的词");
assert.equal(personal.data.nodes[0].y, 0);
assert.equal(personal.data.edges.length, 1);
assert.equal(personal.data.edges[0].label, "我的联想");

const exported = exportLocalLearningData(memoryStorage({
  "wordcloud.personal.v2": JSON.stringify({ nodes: [{ id: "mine-1", word: "flâner" }], edges: [] }),
  "wordcloud.draft_cards.v1": JSON.stringify({ drafts: [{ id: "draft-1", lemma: "se lever", pos: "ver", zhHint: "起床" }, { id: "bad" }] }),
}), { now: 3000 });
assert.equal(exported.schema, "wordcloud.local-learning-export.v2");
assert.equal(exported.exportedAt, new Date(3000).toISOString());
assert.equal(exported.storageKeys.personal, "wordcloud.personal.v2");
assert.equal(exported.learning, undefined);
assert.equal(exported.personal.nodes.length, 1);
assert.equal(exported.draftCards.length, 1);
assert.equal(exported.draftCards[0].pos, "VER");
assert.equal(exported.errors.length, 0);

const damagedExport = exportLocalLearningData(memoryStorage({
  "wordcloud.personal.v2": "{bad",
  "wordcloud.draft_cards.v1": JSON.stringify({ drafts: {} }),
}), { now: 3000 });
assert.equal(damagedExport.personal.nodes.length, 0);
assert.equal(damagedExport.draftCards.length, 0);
assert.equal(damagedExport.errors.length, 2);

const blockedExport = exportLocalLearningData(throwingStorage(), { now: 3000 });
assert.equal(blockedExport.errors.length, 2);
