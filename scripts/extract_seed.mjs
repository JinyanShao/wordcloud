import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../data.js", import.meta.url), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(
  `${source}\nglobalThis.__seed = { nodes: NODES, edges: EDGES, edgeTypes: EDGE_TYPES };`,
  context,
);
fs.mkdirSync(new URL("../data/processed/", import.meta.url), { recursive: true });
fs.writeFileSync(
  new URL("../data/processed/editorial-seed.json", import.meta.url),
  `${JSON.stringify(context.__seed, null, 2)}\n`,
);
console.log(`extracted ${context.__seed.nodes.length} seed nodes and ${context.__seed.edges.length} seed edges`);
