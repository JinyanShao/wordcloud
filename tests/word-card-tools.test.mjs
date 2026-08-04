import assert from "node:assert/strict";
import {
  flattenSenseGroups,
  parseRelationExamples,
  selectReviewedRelationNotes,
  summarizeWordCard,
  wordCardSectionOrder,
} from "../src/word-card-tools.mjs";

const senseGroups = [
  {
    sourceUrl: "https://example.test",
    senses: [
      { number: "1", definition: "réaliser une action" },
      { number: "2", definition: "fabriquer quelque chose" },
    ],
  },
  {
    senses: [
      { number: "1", definition: "   " },
      { number: "2", definition: "causer un état" },
    ],
  },
];

const flattened = flattenSenseGroups(senseGroups);
assert.equal(flattened.length, 3);
assert.equal(flattened[0].groupIndex, 0);
assert.equal(flattened[2].definition, "causer un état");

const summary = summarizeWordCard({
  senseGroups,
  learning: {
    collocations: [
      { expression: "faire attention", gloss: "注意" },
      { expression: "faire partie de", gloss: "属于" },
      { expression: "", gloss: "ignored" },
    ],
  },
  teachingExamples: [
    { text: "Je fais attention.", gloss: "我注意。" },
  ],
  relationCounts: {
    reviewed: 1,
    sourced: 2,
    form: 3,
  },
});

assert.equal(summary.senseTotal, 3);
assert.equal(summary.sensePreview.length, 2);
assert.equal(summary.collocationTotal, 2);
assert.equal(summary.teachingExampleTotal, 1);
assert.equal(summary.relationTotal, 6);
assert.equal(summary.hasReliableRelations, true);
assert.equal(summary.hasLearningCues, true);

const order = wordCardSectionOrder({
  senseGroups,
  relationCounts: { sourced: 1 },
});
assert.deepEqual(order.slice(0, 4), ["hero", "actions", "sense-summary", "relation-entry"]);
assert.ok(order.indexOf("full-senses") < order.indexOf("reviewed-relations"));

const emptyOrder = wordCardSectionOrder({});
assert.deepEqual(emptyOrder.slice(0, 3), ["hero", "actions", "full-senses"]);

assert.deepEqual(parseRelationExamples('["Je sais nager.","Je connais Marie."]'), ["Je sais nager.", "Je connais Marie."]);
assert.deepEqual(parseRelationExamples("{bad json"), []);

const relationNotes = selectReviewedRelationNotes([
  {
    edge: {
      review: "reviewed",
      relation: "compare",
      label: "savoir 表事实或技能；connaître 表熟悉的人、地点或作品。",
      explanation: "Savoir porte sur une information ou un savoir-faire. Connaître porte sur une personne, un lieu ou une œuvre.",
      examples: '["Je sais la réponse.","Je connais cette ville."]',
    },
    node: { word: "connaître", pos: "VER" },
  },
  {
    edge: {
      review: "reviewed",
      relation: "compare",
      label: "旧关系",
      explanation: "Prototype editorial seed; requires production re-review.",
      examples: "[]",
    },
    node: { word: "ancien", pos: "ADJ" },
  },
  {
    edge: {
      review: "sourced",
      relation: "syn",
      label: "近义",
      explanation: "Source relation.",
      examples: "[]",
    },
    node: { word: "source", pos: "NOM" },
  },
]);

assert.equal(relationNotes.length, 1);
assert.equal(relationNotes[0].word, "connaître");
assert.equal(relationNotes[0].examples.length, 2);
