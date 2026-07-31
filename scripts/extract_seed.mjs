import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../data.js", import.meta.url), "utf8");
const destination = new URL("../data/processed/editorial-seed.json", import.meta.url);
const existing = fs.existsSync(destination)
  ? JSON.parse(fs.readFileSync(destination, "utf8"))
  : {};
const context = {};
vm.createContext(context);
vm.runInContext(
  `${source}\nglobalThis.__seed = { nodes: NODES, edges: EDGES, edgeTypes: EDGE_TYPES };`,
  context,
);
if (Array.isArray(existing.foundationalCore)) {
  context.__seed.foundationalCore = existing.foundationalCore;
}
if (Array.isArray(existing.glossOverrides)) {
  context.__seed.glossOverrides = existing.glossOverrides;
}
if (Array.isArray(existing.editorialLearning)) {
  context.__seed.editorialLearning = existing.editorialLearning;
}
if (Array.isArray(existing.editorialRelations)) {
  context.__seed.editorialRelations = existing.editorialRelations;
}
if (Array.isArray(existing.editorialTeachingExamples)) {
  context.__seed.editorialTeachingExamples = existing.editorialTeachingExamples;
}
fs.mkdirSync(new URL("../data/processed/", import.meta.url), { recursive: true });
fs.writeFileSync(
  destination,
  `${JSON.stringify(context.__seed, null, 2)}\n`,
);
console.log(`extracted ${context.__seed.nodes.length} seed nodes and ${context.__seed.edges.length} seed edges; preserved ${context.__seed.foundationalCore?.length || 0} foundational core entries, ${context.__seed.glossOverrides?.length || 0} gloss overrides, ${context.__seed.editorialLearning?.length || 0} learning entries, ${context.__seed.editorialRelations?.length || 0} editorial relations, and ${context.__seed.editorialTeachingExamples?.length || 0} teaching-example entries`);
