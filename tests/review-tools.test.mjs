import assert from "node:assert/strict";
import {
  normalizeLearningState,
  normalizeRelationReviewRecord,
  relationReviewKey,
  scheduleReview,
  sortDueReviewEntries,
  summarizeLearningProgress,
} from "../src/review-tools.mjs";

const edge = {
  a: "11753",
  b: "2928",
  relation: "compare",
  dimension: "knowledge-scope",
};

assert.equal(relationReviewKey(edge), "relation:11753|2928|compare|knowledge-scope");

const normalized = normalizeRelationReviewRecord({
  a: 11753,
  b: 2928,
  relation: "compare",
  dimension: "knowledge-scope",
  trail: ["406", "13435", "2928"],
  reviews: "bad",
  ease: "1",
}, 1000);
assert.equal(normalized.a, "11753");
assert.equal(normalized.b, "2928");
assert.equal(normalized.ease, 1.3);
assert.deepEqual(normalized.trail, ["406", "13435", "2928"]);

const state = normalizeLearningState({
  saved: {
    "2928": { reviews: 1, dueAt: 3000, lastRating: "good" },
  },
  savedRelations: {
    [relationReviewKey(edge)]: {
      ...edge,
      dueAt: 2000,
      lastRating: "again",
    },
    broken: { relation: "compare" },
  },
}, 1000);
assert.equal(Object.keys(state.saved).length, 1);
assert.equal(Object.keys(state.savedRelations).length, 1);

const again = scheduleReview(state.savedRelations[relationReviewKey(edge)], "again", 5000);
assert.equal(again.dueAt, 5000 + 10 * 60 * 1000);
assert.equal(again.reviews, 1);
assert.equal(again.lastRating, "again");

const due = sortDueReviewEntries([
  { key: "late", dueAt: 900, addedAt: 100 },
  { key: "first", dueAt: 100, addedAt: 300 },
  { key: "second", dueAt: 100, addedAt: 200 },
  { key: "future", dueAt: 9000, addedAt: 1 },
], 1000);
assert.deepEqual(due.map((item) => item.key), ["second", "first", "late"]);

const progress = summarizeLearningProgress({
  saved: {
    "2928": { reviews: 2, lastReviewedAt: 7000, dueAt: 9000, lastRating: "good", trail: ["406", "2928"] },
    "11753": { reviews: 0, dueAt: 1000, trail: ["406", "11753"] },
  },
  savedRelations: {
    [relationReviewKey(edge)]: { ...edge, reviews: 1, lastReviewedAt: 6000, dueAt: 12000, lastRating: "hard", trail: ["406", "2928"] },
  },
}, {
  now: 5000,
  upcomingWindowMs: 10_000,
  wordMeta: { "2928": { word: "connaître", pos: "VER" }, "11753": { word: "savoir", pos: "VER" } },
});
assert.deepEqual(progress.totals, {
  saved: 3, words: 2, relations: 1, reviewedEntries: 2, completedReviews: 3, due: 1, upcoming: 2,
});
assert.deepEqual(progress.categories.words.VER, {
  items: 2, reviewedItems: 1, completedReviews: 2, due: 1, upcoming: 1,
});
assert.deepEqual(progress.categories.relations.compare, {
  items: 1, reviewedItems: 1, completedReviews: 1, due: 0, upcoming: 1,
});
assert.equal(progress.recent[0].label, "connaître");
assert.equal(progress.recent[0].status, "upcoming");
assert.equal(progress.paths[0].items, 2);
assert.equal(progress.paths[0].completedReviews, 3);
assert.deepEqual(progress.paths[0].path, ["406", "2928"]);

const damagedRecord = normalizeLearningState({
  saved: { broken: { reviews: "2.9", dueAt: "Infinity", lastReviewedAt: "NaN" } },
  savedRelations: {},
}, 1000);
assert.equal(damagedRecord.saved.broken.reviews, 2);
assert.equal(damagedRecord.saved.broken.dueAt, 1000);
assert.equal(damagedRecord.saved.broken.lastReviewedAt, null);

const damagedProgress = summarizeLearningProgress({ saved: null, savedRelations: [] }, { now: 1000 });
assert.equal(damagedProgress.totals.saved, 0);
assert.deepEqual(damagedProgress.paths, []);
