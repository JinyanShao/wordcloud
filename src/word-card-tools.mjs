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

export function summarizeWordCard(input) {
  const senses = flattenSenseGroups(input?.senseGroups);
  const learning = input?.learning && typeof input.learning === "object" ? input.learning : {};
  const collocations = asArray(learning.collocations).filter((item) => trimText(item?.expression));
  const teachingExamples = asArray(input?.teachingExamples).filter((item) => trimText(item?.text));
  const relationCounts = input?.relationCounts && typeof input.relationCounts === "object" ? input.relationCounts : {};
  const relationTotal = Number(relationCounts.reviewed || 0)
    + Number(relationCounts.sourced || 0)
    + Number(relationCounts.mine || 0)
    + Number(relationCounts.form || 0)
    + Number(relationCounts.structural || 0);

  return {
    senseTotal: senses.length,
    sensePreview: senses.slice(0, 2),
    collocationTotal: collocations.length,
    collocationPreview: collocations.slice(0, 2),
    teachingExampleTotal: teachingExamples.length,
    teachingExamplePreview: teachingExamples.slice(0, 1),
    relationTotal,
    hasReliableRelations: Number(relationCounts.reviewed || 0) + Number(relationCounts.sourced || 0) > 0,
    hasLearningCues: collocations.length > 0 || teachingExamples.length > 0,
  };
}

export function parseRelationExamples(value) {
  if (Array.isArray(value)) return value.map(trimText).filter(Boolean);
  const text = trimText(value);
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed.map(trimText).filter(Boolean) : [];
  } catch {
    return [];
  }
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

export function wordCardSectionOrder(input) {
  const summary = summarizeWordCard(input);
  const order = ["hero", "actions"];
  if (summary.senseTotal) order.push("sense-summary");
  if (summary.hasLearningCues) order.push("usage-summary");
  if (summary.relationTotal) order.push("relation-entry");
  order.push("full-senses", "examples", "learning", "reviewed-relations", "contrast", "sourced-relations", "personal-relations", "form-candidates", "structural-candidates", "nearby-candidates");
  return order;
}
