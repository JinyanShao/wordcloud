import fs from "node:fs";
import Graph from "graphology";
import louvain from "graphology-communities-louvain";
import forceAtlas2 from "graphology-layout-forceatlas2";

const root = new URL("../", import.meta.url);
const input = JSON.parse(fs.readFileSync(new URL("data/processed/graph-input.json", root), "utf8"));
const graph = new Graph({ type: "undirected", multi: false, allowSelfLoops: false });

for (const node of input.nodes) graph.addNode(node.key, { x: node.x, y: node.y, size: node.size });
for (let index = 0; index < input.edges.length; index += 1) {
  const edge = input.edges[index];
  graph.addUndirectedEdgeWithKey(`e${index}`, edge.source, edge.target, { weight: edge.weight });
}

louvain.assign(graph, {
  resolution: 0.58,
  randomWalk: false,
  attributes: { community: "community", weight: "weight" },
});

const communities = new Map();
graph.forEachNode((key, attributes) => {
  const community = attributes.community ?? 0;
  if (!communities.has(community)) communities.set(community, []);
  communities.get(community).push(key);
});

const ranked = [...communities.entries()].sort((a, b) => b[1].length - a[1].length || a[0] - b[0]);
ranked.forEach(([community, members], communityIndex) => {
  members.sort((a, b) => Number(a) - Number(b));
  const golden = Math.PI * (3 - Math.sqrt(5));
  const anchorRadius = 16 * Math.sqrt(communityIndex);
  const anchorAngle = communityIndex * golden;
  const anchorX = Math.cos(anchorAngle) * anchorRadius;
  const anchorY = Math.sin(anchorAngle) * anchorRadius;
  members.forEach((key, memberIndex) => {
    const previous = graph.getNodeAttributes(key);
    const localRadius = 0.45 * Math.sqrt(memberIndex + 1);
    const localAngle = Math.atan2(previous.y, previous.x) + memberIndex * golden;
    graph.mergeNodeAttributes(key, {
      x: anchorX + Math.cos(localAngle) * localRadius,
      y: anchorY + Math.sin(localAngle) * localRadius,
      community,
    });
  });
});

const inferred = forceAtlas2.inferSettings(graph);
forceAtlas2.assign(graph, {
  iterations: 420,
  getEdgeWeight: "weight",
  settings: {
    ...inferred,
    barnesHutOptimize: true,
    barnesHutTheta: 0.55,
    edgeWeightInfluence: 1,
    gravity: 0.12,
    linLogMode: true,
    outboundAttractionDistribution: true,
    scalingRatio: 16,
    slowDown: 8,
    strongGravityMode: false,
  },
});

const raw = [];
graph.forEachNode((key, attributes) => {
  raw.push({
    id: Number(key),
    x: attributes.x,
    y: attributes.y,
    community: Number(attributes.community ?? 0),
    degree: graph.degree(key),
    weightedDegree: graph.reduceEdges(key, (sum, _edge, attrs) => sum + (attrs.weight ?? 1), 0),
  });
});

// Keep data-derived neighborhoods legible at overview scale. ForceAtlas2 finds
// the global topology; this deterministic affine pass opens space between its
// Louvain communities without inventing names or changing membership.
const communityStats = new Map();
for (const node of raw) {
  if (!communityStats.has(node.community)) communityStats.set(node.community, { x: 0, y: 0, n: 0 });
  const stat = communityStats.get(node.community);
  stat.x += node.x; stat.y += node.y; stat.n += 1;
}
for (const stat of communityStats.values()) { stat.x /= stat.n; stat.y /= stat.n; }
const globalCenter = raw.reduce((acc, node) => ({ x: acc.x + node.x / raw.length, y: acc.y + node.y / raw.length }), { x: 0, y: 0 });
for (const node of raw) {
  const center = communityStats.get(node.community);
  node.x = globalCenter.x + (center.x - globalCenter.x) + (node.x - center.x) * 0.62;
  node.y = globalCenter.y + (center.y - globalCenter.y) + (node.y - center.y) * 0.62;
}

const xs = raw.map((node) => node.x);
const ys = raw.map((node) => node.y);
const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1);
const scale = 2600 / span;
for (const node of raw) {
  node.x = Math.round((node.x - centerX) * scale * 1000) / 1000;
  node.y = Math.round((node.y - centerY) * scale * 1000) / 1000;
  node.weightedDegree = Math.round(node.weightedDegree * 100000) / 100000;
}
raw.sort((a, b) => a.id - b.id);

const output = {
  meta: {
    version: "layout-v1-forceatlas2-420",
    created_at: "2026-07-27T00:00:00Z",
    node_count: graph.order,
    edge_count: graph.size,
    community_count: communities.size,
    algorithm: "Louvain initialization + ForceAtlas2 Barnes-Hut",
  },
  positions: raw,
};
fs.writeFileSync(new URL("data/processed/layout-positions.json", root), `${JSON.stringify(output)}\n`);
console.log(JSON.stringify(output.meta));
