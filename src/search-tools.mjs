const MATCH_RANK = {
  exactWord: 0,
  exactAlias: 1,
  startsWord: 2,
  startsAlias: 3,
  containsWord: 4,
  containsAlias: 5,
};

function text(value) {
  return String(value ?? "");
}

export function normalizeSearchText(value) {
  return text(value)
    .normalize("NFKC")
    .replace(/[’‘`´]/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("fr");
}

function foldSearchText(value) {
  return normalizeSearchText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^0-9a-zA-Z]+/g, "");
}

function normalizeEntry(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = text(raw.id).trim();
  const word = text(raw.word).trim();
  if (!id || !word) return null;
  const aliases = Array.isArray(raw.aliases) ? raw.aliases.map(normalizeSearchText).filter(Boolean) : [];
  return {
    ...raw,
    id,
    word,
    normalizedWord: normalizeSearchText(word),
    foldedWord: foldSearchText(word),
    normalizedAliases: [...new Set(aliases)],
    freq: Number(raw.freq) || 0,
    isCore: Boolean(raw.isCore),
  };
}

function bestMatch(entry, query) {
  if (entry.normalizedWord === query) return { type: "exactWord", matchedText: entry.word };
  const exactAlias = entry.normalizedAliases.find((alias) => alias === query);
  if (exactAlias) return { type: "exactAlias", matchedText: exactAlias };
  if (entry.normalizedWord.startsWith(query)) return { type: "startsWord", matchedText: entry.word };
  const startsAlias = entry.normalizedAliases.find((alias) => alias.startsWith(query));
  if (startsAlias) return { type: "startsAlias", matchedText: startsAlias };
  if (entry.normalizedWord.includes(query)) return { type: "containsWord", matchedText: entry.word };
  const containsAlias = entry.normalizedAliases.find((alias) => alias.includes(query));
  if (containsAlias) return { type: "containsAlias", matchedText: containsAlias };
  return null;
}

function maxSuggestionDistance(query) {
  if (query.length < 3) return 0;
  if (query.length <= 4) return 1;
  if (query.length <= 9) return 2;
  return 3;
}

function boundedEditDistance(left, right, limit) {
  if (Math.abs(left.length - right.length) > limit) return limit + 1;
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let i = 1; i <= left.length; i += 1) {
    const current = [i];
    let rowMin = current[0];
    for (let j = 1; j <= right.length; j += 1) {
      const cost = left[i - 1] === right[j - 1] ? 0 : 1;
      const value = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
      current[j] = value;
      rowMin = Math.min(rowMin, value);
    }
    if (rowMin > limit) return limit + 1;
    previous = current;
  }
  return previous[right.length];
}

function bestSuggestion(entry, foldedQuery, limit) {
  const candidates = [entry.word, ...entry.normalizedAliases].map((value) => ({
    text: value,
    folded: foldSearchText(value),
  })).filter((item) => item.folded && Math.abs(item.folded.length - foldedQuery.length) <= limit);
  let best = null;
  for (const candidate of candidates) {
    const distance = boundedEditDistance(foldedQuery, candidate.folded, limit);
    if (distance > limit) continue;
    if (!best || distance < best.distance || candidate.text.length < best.matchedText.length) {
      best = { distance, matchedText: candidate.text };
    }
  }
  return best;
}

export function searchLexemes(rawEntries, rawQuery, options = {}) {
  const query = normalizeSearchText(rawQuery);
  const limit = Math.max(1, Number(options.limit) || 12);
  const suggestionLimit = Math.max(0, Number(options.suggestionLimit) || 5);
  if (!query) return { query, results: [], suggestions: [] };

  const byId = new Map();
  for (const raw of Array.isArray(rawEntries) ? rawEntries : []) {
    const entry = normalizeEntry(raw);
    if (entry && !byId.has(entry.id)) byId.set(entry.id, entry);
  }

  const matches = [];
  for (const entry of byId.values()) {
    const match = bestMatch(entry, query);
    if (!match) continue;
    matches.push({
      entry,
      matchType: match.type,
      matchedText: match.matchedText,
      rank: MATCH_RANK[match.type],
    });
  }

  matches.sort((a, b) => a.rank - b.rank
    || Number(b.entry.isCore) - Number(a.entry.isCore)
    || b.entry.freq - a.entry.freq
    || a.entry.word.localeCompare(b.entry.word, "fr")
    || a.entry.id.localeCompare(b.entry.id, "fr"));

  if (matches.length) return { query, results: matches.slice(0, limit), suggestions: [] };

  const foldedQuery = foldSearchText(query);
  const maxDistance = maxSuggestionDistance(foldedQuery);
  if (!maxDistance || !suggestionLimit) return { query, results: [], suggestions: [] };

  const suggestions = [];
  for (const entry of byId.values()) {
    const suggestion = bestSuggestion(entry, foldedQuery, maxDistance);
    if (!suggestion) continue;
    suggestions.push({
      entry,
      matchType: "suggestion",
      matchedText: suggestion.matchedText,
      distance: suggestion.distance,
    });
  }

  suggestions.sort((a, b) => a.distance - b.distance
    || Number(b.entry.isCore) - Number(a.entry.isCore)
    || b.entry.freq - a.entry.freq
    || a.entry.word.localeCompare(b.entry.word, "fr")
    || a.entry.id.localeCompare(b.entry.id, "fr"));

  return { query, results: [], suggestions: suggestions.slice(0, suggestionLimit) };
}

export const SEARCH_MATCH_RANK = { ...MATCH_RANK };
