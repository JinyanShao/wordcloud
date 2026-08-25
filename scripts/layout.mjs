import fs from "node:fs";
import Graph from "graphology";
import louvain from "graphology-communities-louvain";
import forceAtlas2 from "graphology-layout-forceatlas2";

const root = new URL("../", import.meta.url);
const input = JSON.parse(fs.readFileSync(new URL("data/processed/graph-input.json", root), "utf8"));
const graph = new Graph({ type: "undirected", multi: false, allowSelfLoops: false });

// Radius has one product meaning: learning progression. The bands deliberately
// overlap slightly so the result reads as a continuous cloud rather than rings.
const LEVEL_BANDS = {
  A1: [36, 145],
  A2: [105, 245],
  B1: [82, 525],
  B2: [500, 910],
  C1: [885, 1245],
  C2: [1215, 1325],
};
const TOPOLOGY_FACTORS = {
  semantic: 0.58,
  derivation: 1.0,
  editorial_seed: 1.12,
};

function stableUnit(value, salt = "") {
  let hash = 2166136261;
  const text = `${salt}:${value}`;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967296;
}

// graphology-communities-louvain defaults its internal tie-breaking `rng` to
// the global Math.random, which makes repeated builds on identical input
// pick different (equally valid) local optima. mulberry32 is a small,
// well-known deterministic PRNG: seeding it with a fixed constant gives
// Louvain a reproducible rng without touching Math.random itself, so nothing
// outside this layout pass is affected.
function mulberry32(seed) {
  let state = seed >>> 0;
  return function random() {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const LOUVAIN_SEED = 0x5747_4c56; // "WGLV" — arbitrary, fixed for reproducibility
const louvainRng = mulberry32(LOUVAIN_SEED);

function topologyWeight(edge) {
  let remaining = 1;
  for (const signal of edge.signals || []) {
    const factor = TOPOLOGY_FACTORS[signal];
    if (!factor) continue;
    const rawWeight = edge.signal_weights?.[signal] ?? edge.weight;
    remaining *= 1 - Math.min(0.96, rawWeight * factor);
  }
  return 1 - remaining;
}

for (const node of input.nodes) {
  graph.addNode(node.key, {
    x: node.x,
    y: node.y,
    size: node.size,
    level: node.level || "",
    frequency: Number(node.frequency || 0),
    diversity: Number(node.diversity || 0),
    status: node.status || "eligible",
  });
}
for (let index = 0; index < input.edges.length; index += 1) {
  const edge = input.edges[index];
  const weight = topologyWeight(edge);
  if (weight < 0.05) continue;
  graph.addUndirectedEdgeWithKey(`e${index}`, edge.source, edge.target, { weight });
}

louvain.assign(graph, {
  resolution: 0.58,
  randomWalk: false,
  rng: louvainRng,
  attributes: { community: "community", weight: "weight" },
});

const communities = new Map();
graph.forEachNode((key, attributes) => {
  const community = attributes.community ?? 0;
  if (!communities.has(community)) communities.set(community, []);
  communities.get(community).push(key);
});

// Deterministic community seeds make repeated builds with unchanged data stable.
const ranked = [...communities.entries()].sort((a, b) => b[1].length - a[1].length || a[0] - b[0]);
const golden = Math.PI * (3 - Math.sqrt(5));
ranked.forEach(([community, members], communityIndex) => {
  members.sort((a, b) => Number(a) - Number(b));
  const anchorRadius = 18 * Math.sqrt(communityIndex);
  const anchorAngle = communityIndex * golden;
  const anchorX = Math.cos(anchorAngle) * anchorRadius;
  const anchorY = Math.sin(anchorAngle) * anchorRadius;
  members.forEach((key, memberIndex) => {
    const localRadius = 0.5 * Math.sqrt(memberIndex + 1);
    const localAngle = stableUnit(key, "local-angle") * Math.PI * 2;
    graph.mergeNodeAttributes(key, {
      x: anchorX + Math.cos(localAngle) * localRadius,
      y: anchorY + Math.sin(localAngle) * localRadius,
      community,
    });
  });
});

const inferred = forceAtlas2.inferSettings(graph);
forceAtlas2.assign(graph, {
  iterations: 380,
  getEdgeWeight: "weight",
  settings: {
    ...inferred,
    barnesHutOptimize: true,
    barnesHutTheta: 0.55,
    edgeWeightInfluence: 1,
    gravity: 0.08,
    linLogMode: true,
    outboundAttractionDistribution: true,
    scalingRatio: 17,
    slowDown: 8,
    strongGravityMode: false,
  },
});

const forceCenter = graph.reduceNodes(
  (center, _key, attributes) => ({ x: center.x + attributes.x / graph.order, y: center.y + attributes.y / graph.order }),
  { x: 0, y: 0 },
);
const communityStats = new Map();
graph.forEachNode((key, attributes) => {
  const community = attributes.community ?? 0;
  if (!communityStats.has(community)) communityStats.set(community, { x: 0, y: 0, n: 0 });
  const stat = communityStats.get(community);
  stat.x += attributes.x;
  stat.y += attributes.y;
  stat.n += 1;
});
for (const stat of communityStats.values()) {
  stat.x /= stat.n;
  stat.y /= stat.n;
}

// Within each level, frequency determines the continuous inward-to-outward
// order. Area interpolation prevents thousands of nodes from piling up on the
// same narrow inner circumference.
const levelMembers = new Map();
graph.forEachNode((key, attributes) => {
  if (!LEVEL_BANDS[attributes.level]) return;
  if (!levelMembers.has(attributes.level)) levelMembers.set(attributes.level, []);
  levelMembers.get(attributes.level).push({ key, frequency: attributes.frequency, diversity: attributes.diversity });
});
const radiusByNode = new Map();
for (const [level, members] of levelMembers) {
  members.sort((a, b) => b.frequency - a.frequency || b.diversity - a.diversity || Number(a.key) - Number(b.key));
  const [inner, outer] = LEVEL_BANDS[level];
  members.forEach((member, index) => {
    const rank = members.length <= 1 ? 0 : index / (members.length - 1);
    const radius = Math.sqrt(inner * inner + rank * (outer * outer - inner * inner));
    radiusByNode.set(member.key, radius);
  });
}

// A handful of editorial support nodes have no CEFR value. Keep them near the
// known-level words they connect to instead of inventing a difficulty level.
graph.forEachNode((key, attributes) => {
  if (radiusByNode.has(key)) return;
  let weightedRadius = 0;
  let totalWeight = 0;
  graph.forEachEdge(key, (_edge, edgeAttributes, source, target) => {
    const neighbor = source === key ? target : source;
    const neighborRadius = radiusByNode.get(neighbor);
    if (neighborRadius == null) return;
    const weight = edgeAttributes.weight || 0;
    weightedRadius += neighborRadius * weight;
    totalWeight += weight;
  });
  const fallback = attributes.status === "eligible" ? 1060 : 700;
  const radius = totalWeight ? weightedRadius / totalWeight : fallback;
  radiusByNode.set(key, Math.max(42, Math.min(1315, radius + (stableUnit(key, "radius") - 0.5) * 24)));
});

function wrapAngle(angle) {
  while (angle <= -Math.PI) angle += Math.PI * 2;
  while (angle > Math.PI) angle -= Math.PI * 2;
  return angle;
}

// Radius (CEFR/frequency) and angle (ForceAtlas2 community pull) are chosen
// independently, so two nodes can legitimately land almost on top of each
// other -- most visibly for strongly-pulled pairs like editorial relations,
// but measurably for ~1% of all edges. This pass only ever adjusts angle: it
// never touches radius, so "radius = learning progression" stays exactly
// true. It repeatedly finds node pairs closer than MIN_DIST world units
// (via a spatial hash grid, so it stays fast at 7k+ nodes) and nudges each
// one along its own tangential direction, away from the other -- the polar
// equivalent of a repulsion force that can't leak into the radial axis.
// Fully deterministic: fixed iteration order, no Math.random (only the
// existing stableUnit hash, for the zero-distance fallback direction).
function declumpAngles(items, { minDist = 48, iterations = 220, damping = 0.6 } = {}) {
  const cellSize = minDist;
  for (let iter = 0; iter < iterations; iter += 1) {
    const cart = items.map((item) => ({
      x: Math.cos(item.angle) * item.radius,
      y: Math.sin(item.angle) * item.radius,
    }));
    const grid = new Map();
    cart.forEach((point, index) => {
      const cellKey = `${Math.floor(point.x / cellSize)}:${Math.floor(point.y / cellSize)}`;
      if (!grid.has(cellKey)) grid.set(cellKey, []);
      grid.get(cellKey).push(index);
    });
    const pushX = new Array(items.length).fill(0);
    const pushY = new Array(items.length).fill(0);
    let violations = 0;
    for (let index = 0; index < items.length; index += 1) {
      const point = cart[index];
      const cx = Math.floor(point.x / cellSize);
      const cy = Math.floor(point.y / cellSize);
      for (let dx = -1; dx <= 1; dx += 1) {
        for (let dy = -1; dy <= 1; dy += 1) {
          const bucket = grid.get(`${cx + dx}:${cy + dy}`);
          if (!bucket) continue;
          for (const j of bucket) {
            if (j <= index) continue;
            const other = cart[j];
            let ddx = other.x - point.x;
            let ddy = other.y - point.y;
            let dist = Math.hypot(ddx, ddy);
            if (dist >= minDist) continue;
            violations += 1;
            if (dist < 1e-6) {
              const fallback = stableUnit(`${items[index].key}:${items[j].key}`, "declump-fallback") * Math.PI * 2;
              ddx = Math.cos(fallback);
              ddy = Math.sin(fallback);
              dist = 1;
            }
            const nx = ddx / dist, ny = ddy / dist;
            const overlap = (minDist - dist) * 0.5;
            pushX[index] -= nx * overlap; pushY[index] -= ny * overlap;
            pushX[j] += nx * overlap; pushY[j] += ny * overlap;
          }
        }
      }
    }
    if (!violations) break;
    for (let index = 0; index < items.length; index += 1) {
      if (!pushX[index] && !pushY[index]) continue;
      const item = items[index];
      const tangentX = -Math.sin(item.angle), tangentY = Math.cos(item.angle);
      const tangential = pushX[index] * tangentX + pushY[index] * tangentY;
      const arcShift = (tangential / Math.max(item.radius, 1)) * damping;
      item.angle = wrapAngle(item.angle + arcShift);
    }
  }
}

const angleItems = [];
graph.forEachNode((key, attributes) => {
  const community = attributes.community ?? 0;
  const stat = communityStats.get(community);
  const nodeAngle = Math.atan2(attributes.y - forceCenter.y, attributes.x - forceCenter.x);
  let angle;
  if (graph.degree(key) === 0 || !stat || stat.n === 1) {
    angle = stableUnit(key, "isolated-angle") * Math.PI * 2 - Math.PI;
  } else {
    const communityAngle = Math.atan2(stat.y - forceCenter.y, stat.x - forceCenter.x);
    angle = communityAngle + wrapAngle(nodeAngle - communityAngle) * 0.72;
  }
  angleItems.push({ key, angle, radius: radiusByNode.get(key) });
});

declumpAngles(angleItems);

const positions = [];
angleItems.forEach(({ key, angle, radius }) => {
  positions.push({
    id: Number(key),
    x: Math.round(Math.cos(angle) * radius * 1000) / 1000,
    y: Math.round(Math.sin(angle) * radius * 1000) / 1000,
    community: Number(graph.getNodeAttribute(key, "community") ?? 0),
    degree: graph.degree(key),
    weightedDegree: Math.round(graph.reduceEdges(key, (sum, _edge, attrs) => sum + (attrs.weight ?? 1), 0) * 100000) / 100000,
    radius: Math.round(radius * 1000) / 1000,
  });
});
positions.sort((a, b) => a.id - b.id);

const levelCounts = {};
graph.forEachNode((_key, attributes) => {
  const label = attributes.level || "unrated";
  levelCounts[label] = (levelCounts[label] || 0) + 1;
});
const output = {
  meta: {
    version: "layout-v2-radial-learning-space",
    created_at: "2026-07-27T00:00:00Z",
    node_count: graph.order,
    edge_count: graph.size,
    community_count: communities.size,
    isolated_count: graph.nodes().filter((key) => graph.degree(key) === 0).length,
    algorithm: "CEFR-frequency radial bands + Louvain + ForceAtlas2 angular topology",
    radial_meaning: "inward=easier and more frequent; outward=more advanced and less frequent",
    angular_signals: Object.keys(TOPOLOGY_FACTORS),
    excluded_angular_signals: ["morphology", "spelling", "phonetic", "skeleton"],
    level_counts: levelCounts,
  },
  positions,
};
fs.writeFileSync(new URL("data/processed/layout-positions.json", root), `${JSON.stringify(output)}\n`);
console.log(JSON.stringify(output.meta));
