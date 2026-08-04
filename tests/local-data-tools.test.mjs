import assert from "node:assert/strict";
import {
  exportLocalLearningData,
  loadLearningState,
  loadPersonalState,
  normalizeLearningRecord,
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

const record = normalizeLearningRecord({ reviews: "-1", ease: "1", lastRating: "unknown" }, 1000);
assert.equal(record.addedAt, 1000);
assert.equal(record.reviews, 0);
assert.equal(record.ease, 1.3);
assert.equal(record.lastRating, null);

const learning = loadLearningState(memoryStorage({
  "wordcloud.learning.v1": JSON.stringify({
    saved: { 42: { reviews: 2, dueAt: 5000, lastRating: "good" } },
    savedRelations: {
      "relation:11753|2928|compare|knowledge-scope": {
        a: "11753",
        b: "2928",
        relation: "compare",
        dimension: "knowledge-scope",
        dueAt: 6000,
      },
    },
  }),
}), "wordcloud.learning.v1", 2000);
assert.equal(learning.error, null);
assert.equal(learning.data.saved["42"].reviews, 2);
assert.equal(learning.data.saved["42"].lastRating, "good");
assert.equal(Object.keys(learning.data.savedRelations).length, 1);

const corruptLearning = loadLearningState(memoryStorage({ "wordcloud.learning.v1": "{bad" }), "wordcloud.learning.v1");
assert.equal(Object.keys(corruptLearning.data.saved).length, 0);
assert.match(corruptLearning.error, /无法解析/);

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
  "wordcloud.learning.v1": JSON.stringify({
    saved: { 42: { reviews: 1 } },
    savedRelations: {
      "relation:11753|2928|compare|knowledge-scope": {
        a: "11753",
        b: "2928",
        relation: "compare",
        dimension: "knowledge-scope",
        reviews: 1,
      },
    },
  }),
  "wordcloud.personal.v2": JSON.stringify({ nodes: [{ id: "mine-1", word: "flâner" }], edges: [] }),
  "wordcloud.draft_cards.v1": JSON.stringify({ drafts: [{ id: "draft-1", lemma: "se lever", pos: "ver", zhHint: "起床" }, { id: "bad" }] }),
}), { now: 3000 });
assert.equal(exported.schema, "wordcloud.local-learning-export.v1");
assert.equal(exported.exportedAt, new Date(3000).toISOString());
assert.equal(exported.storageKeys.learning, "wordcloud.learning.v1");
assert.equal(Object.keys(exported.learning.saved).length, 1);
assert.equal(Object.keys(exported.learning.savedRelations).length, 1);
assert.equal(exported.personal.nodes.length, 1);
assert.equal(exported.draftCards.length, 1);
assert.equal(exported.draftCards[0].pos, "VER");
assert.equal(exported.errors.length, 0);

const damagedExport = exportLocalLearningData(memoryStorage({
  "wordcloud.learning.v1": "{bad",
  "wordcloud.personal.v2": "{bad",
  "wordcloud.draft_cards.v1": JSON.stringify({ drafts: {} }),
}), { now: 3000 });
assert.equal(Object.keys(damagedExport.learning.saved).length, 0);
assert.equal(damagedExport.personal.nodes.length, 0);
assert.equal(damagedExport.draftCards.length, 0);
assert.equal(damagedExport.errors.length, 3);

const blockedExport = exportLocalLearningData(throwingStorage(), { now: 3000 });
assert.equal(blockedExport.errors.length, 3);
