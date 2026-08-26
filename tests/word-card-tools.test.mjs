import assert from "node:assert/strict";
import {
  flattenSenseGroups,
  parseRelationExamples,
  selectPreviewSenses,
  selectReviewedRelationNotes,
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

assert.deepEqual(
  parseRelationExamples('["Je sais nager.","Je connais Marie."]'),
  [{ fr: "Je sais nager.", zh: "" }, { fr: "Je connais Marie.", zh: "" }],
);
assert.deepEqual(
  parseRelationExamples('[{"fr":"Je sais nager.","zh":"我会游泳。"}]'),
  [{ fr: "Je sais nager.", zh: "我会游泳。" }],
);
assert.deepEqual(parseRelationExamples("{bad json"), []);

const relationNotes = selectReviewedRelationNotes([
  {
    edge: {
      review: "reviewed",
      relation: "compare",
      label: "savoir 表事实或技能；connaître 表熟悉的人、地点或作品。",
      explanation: "Savoir porte sur une information ou un savoir-faire. Connaître porte sur une personne, un lieu ou une œuvre.",
      examples: '[{"fr":"Je sais la réponse.","zh":"我知道答案。"},{"fr":"Je connais cette ville.","zh":"我熟悉这座城市。"}]',
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
assert.equal(relationNotes[0].examples[0].zh, "我知道答案。");

// selectPreviewSenses: a relation-bound sense (e.g. enfiler's "put on
// clothing" is sense #11 of 11) must reach the 3-item preview even when it
// sits far outside the raw dictionary order, without losing the rest of the
// dictionary's own ordering for the un-bound case.
const enfilerSenses = [
  { number: "1", definition: "Traverser d'un fil par une ouverture." },
  { number: "2", definition: "Enfiler un anneau, au jeu de bague." },
  { number: "3", definition: "Munir de ses cordes un instrument." },
  { number: "10", definition: "Passer un membre dans un vêtement." },
  { number: "11", definition: "Mettre un manteau rapidement." },
];

assert.deepEqual(
  selectPreviewSenses(enfilerSenses, ["11"], 3).map((sense) => sense.number),
  ["11", "1", "2"],
  "the bound sense must lead the preview, not fall off the end of dictionary order",
);
assert.deepEqual(
  selectPreviewSenses(enfilerSenses, [], 3).map((sense) => sense.number),
  ["1", "2", "3"],
  "with no bound sense, preview stays plain first-N-by-dictionary-order (unchanged behavior)",
);
assert.deepEqual(
  selectPreviewSenses(enfilerSenses, ["7"], 3).map((sense) => sense.number),
  ["1", "2", "3"],
  "a sense number with no match in this word's list is a no-op, not an error",
);
assert.deepEqual(
  selectPreviewSenses(enfilerSenses, ["3", "11"], 3).map((sense) => sense.number),
  ["3", "11", "1"],
  "multiple bound senses (e.g. both sides of a relation happen to name senses for the same word) all lead, in their original relative order",
);
assert.deepEqual(selectPreviewSenses([], ["11"], 3), []);
