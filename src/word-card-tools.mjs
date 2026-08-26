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

// A reviewed relation can be bound to one specific dictionary sense (its
// source names the exact RL-fr/DBnary sense id), which has no relationship
// to that sense's position in the raw dictionary ordering. Without this, the
// word-card preview shows senses purely by source order, which can be a
// completely different meaning from the one the relation is actually about.
// Moves any sense whose number is in keySenseNumbers to the front (stable
// order within each group), then truncates to `limit`.
export function selectPreviewSenses(senses, keySenseNumbers = [], limit = 3) {
  const list = asArray(senses);
  const keys = new Set(asArray(keySenseNumbers).map(trimText).filter(Boolean));
  if (!keys.size) return list.slice(0, limit);
  const priority = list.filter((sense) => keys.has(trimText(sense.number)));
  const rest = list.filter((sense) => !keys.has(trimText(sense.number)));
  return [...priority, ...rest].slice(0, limit);
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
