function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function trimText(value) {
  return String(value ?? "").trim();
}

export function flattenSenseGroups(groups) {
  return asArray(groups).flatMap((group, groupIndex) => asArray(group?.senses).map((sense) => ({
    ...sense,
    groupIndex,
    sourceUrl: group?.sourceUrl || "",
  }))).filter((sense) => trimText(sense.definition));
}

// Each example is either a bare French string (no reviewed gloss yet) or
// an { fr, zh } pair (see build_graph.py's official_edges insertion). This
// always normalizes to { fr, zh } so callers don't need to branch on shape.
function normalizeExample(entry) {
  if (entry && typeof entry === "object") {
    return { fr: trimText(entry.fr), zh: trimText(entry.zh) };
  }
  return { fr: trimText(entry), zh: "" };
}

export function parseRelationExamples(value) {
  const list = Array.isArray(value) ? value : (() => {
    const text = trimText(value);
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  })();
  return list.map(normalizeExample).filter((example) => example.fr);
}

export function selectReviewedRelationNotes(items, options = {}) {
  const limit = Number.isFinite(options.limit) ? Math.max(0, options.limit) : 8;
  return asArray(items)
    .filter((item) => item?.edge?.review === "reviewed" && trimText(item.edge.explanation))
    .filter((item) => !trimText(item.edge.explanation).includes("requires production re-review"))
    .map((item) => ({
      a: trimText(item.edge?.a),
      b: trimText(item.edge?.b),
      word: trimText(item.node?.word),
      pos: trimText(item.node?.pos),
      relation: trimText(item.edge?.relation),
      dimension: trimText(item.edge?.dimension),
      label: trimText(item.edge?.label),
      explanation: trimText(item.edge?.explanation),
      examples: parseRelationExamples(item.edge?.examples),
    }))
    .filter((item) => item.word && item.explanation)
    .slice(0, limit);
}
