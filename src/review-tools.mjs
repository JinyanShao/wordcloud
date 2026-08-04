const MINUTE = 60 * 1000;
const DAY = 24 * 60 * MINUTE;
const VALID_RATINGS = new Set(["again", "hard", "good", "easy"]);

function text(value, limit = 120) {
  return String(value ?? "").trim().slice(0, limit);
}

function normalizeTrail(value) {
  return Array.isArray(value)
    ? value.map((item) => text(item, 80)).filter(Boolean).slice(-8)
    : [];
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function timestamp(value) {
  const number = finiteNumber(value);
  return number !== null && number > 0 ? number : null;
}

function safeNow(value) {
  const number = finiteNumber(value);
  return number !== null && number >= 0 ? number : Date.now();
}

export function normalizeLearningRecord(record, now = Date.now()) {
  const raw = record && typeof record === "object" ? record : {};
  const safeTimestamp = safeNow(now);
  const addedAt = timestamp(raw.addedAt) ?? safeTimestamp;
  const lastReviewedAt = timestamp(raw.lastReviewedAt);
  const dueAt = timestamp(raw.dueAt) ?? lastReviewedAt ?? safeTimestamp;
  const lastRating = VALID_RATINGS.has(raw.lastRating) ? raw.lastRating : null;
  return {
    addedAt,
    reviews: Math.max(0, Math.floor(finiteNumber(raw.reviews) ?? 0)),
    lastReviewedAt,
    dueAt,
    intervalDays: Math.max(0, finiteNumber(raw.intervalDays) ?? 0),
    ease: Math.max(1.3, finiteNumber(raw.ease) ?? 2.3),
    lapses: Math.max(0, Math.floor(finiteNumber(raw.lapses) ?? 0)),
    lastRating,
    trail: normalizeTrail(raw.trail),
  };
}

export function normalizeRelationReviewRecord(record, now = Date.now()) {
  const raw = record && typeof record === "object" ? record : {};
  return {
    ...normalizeLearningRecord(raw, now),
    a: text(raw.a, 80),
    b: text(raw.b, 80),
    relation: text(raw.relation, 24),
    dimension: text(raw.dimension, 80),
  };
}

export function normalizeLearningState(value, now = Date.now()) {
  const raw = value && typeof value === "object" ? value : {};
  const saved = raw.saved && typeof raw.saved === "object" && !Array.isArray(raw.saved) ? raw.saved : {};
  const savedRelations = raw.savedRelations
    && typeof raw.savedRelations === "object"
    && !Array.isArray(raw.savedRelations)
    ? raw.savedRelations
    : {};
  const normalizedRelations = {};
  for (const [key, record] of Object.entries(savedRelations)) {
    const normalized = normalizeRelationReviewRecord(record, now);
    if (text(key, 180) && normalized.a && normalized.b && normalized.relation) {
      normalizedRelations[String(key)] = normalized;
    }
  }
  return {
    saved: Object.fromEntries(Object.entries(saved)
      .filter(([id]) => text(id, 80))
      .map(([id, record]) => [String(id), normalizeLearningRecord(record, now)])),
    savedRelations: normalizedRelations,
  };
}

export function relationReviewKey(edge) {
  const endpoints = [text(edge?.a, 80), text(edge?.b, 80)].sort();
  return `relation:${endpoints[0]}|${endpoints[1]}|${text(edge?.relation, 24)}|${text(edge?.dimension, 80)}`;
}

export function scheduleReview(record, rating, now = Date.now()) {
  const next = normalizeLearningRecord(record, now);
  const firstReview = next.reviews === 0;
  if (rating === "again") {
    next.intervalDays = 0;
    next.ease = Math.max(1.3, next.ease - 0.2);
    next.lapses += 1;
    next.dueAt = now + 10 * MINUTE;
  } else if (rating === "hard") {
    next.intervalDays = Math.max(1, Math.round(Math.max(1, next.intervalDays) * 1.2));
    next.ease = Math.max(1.3, next.ease - 0.15);
    next.dueAt = now + next.intervalDays * DAY;
  } else if (rating === "easy") {
    next.intervalDays = firstReview ? 4 : Math.max(4, Math.round(Math.max(1, next.intervalDays) * next.ease * 1.3));
    next.ease = Math.min(3.0, next.ease + 0.05);
    next.dueAt = now + next.intervalDays * DAY;
  } else {
    next.intervalDays = firstReview ? 1 : Math.max(2, Math.round(Math.max(1, next.intervalDays) * next.ease));
    next.dueAt = now + next.intervalDays * DAY;
  }
  next.reviews += 1;
  next.lastReviewedAt = now;
  next.lastRating = VALID_RATINGS.has(rating) ? rating : null;
  return next;
}

export function sortDueReviewEntries(entries, now = Date.now()) {
  return (Array.isArray(entries) ? entries : [])
    .filter((entry) => Number(entry?.dueAt) <= now)
    .sort((a, b) => Number(a.dueAt) - Number(b.dueAt)
      || Number(a.addedAt) - Number(b.addedAt)
      || String(a.key || "").localeCompare(String(b.key || "")));
}

function positiveNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : fallback;
}

function categoryFor(meta, fallback = "未分类") {
  if (!meta || typeof meta !== "object") return fallback;
  return text(meta.category || meta.pos || meta.level, 80) || fallback;
}

function labelFor(meta, fallback) {
  if (!meta || typeof meta !== "object") return fallback;
  return text(meta.label || meta.word || meta.title, 120) || fallback;
}

function emptyCategory() {
  return { items: 0, reviewedItems: 0, completedReviews: 0, due: 0, upcoming: 0 };
}

function categoryBucket(map, key) {
  if (!map[key]) map[key] = emptyCategory();
  return map[key];
}

function dueStatus(dueAt, now, upcomingWindowMs) {
  if (dueAt <= now) return "due";
  if (dueAt <= now + upcomingWindowMs) return "upcoming";
  return "scheduled";
}

export function summarizeLearningProgress(value, options = {}) {
  const now = positiveNumber(options.now, Date.now());
  const requestedWindow = options.upcomingWindowMs ?? (
    finiteNumber(options.upcomingDays) === null ? null : Number(options.upcomingDays) * DAY
  );
  const upcomingWindowMs = positiveNumber(requestedWindow, 7 * DAY);
  const recentLimit = Math.max(1, Math.min(50, Number(options.recentLimit) || 12));
  const state = normalizeLearningState(value, now);
  const wordMeta = options.wordMeta && typeof options.wordMeta === "object" ? options.wordMeta : {};
  const entries = [];

  for (const [key, record] of Object.entries(state.saved)) {
    const category = categoryFor(wordMeta[key]);
    entries.push({ key: String(key), kind: "word", category, label: labelFor(wordMeta[key], String(key)), record, trail: record.trail });
  }
  for (const [key, record] of Object.entries(state.savedRelations)) {
    const category = text(record.relation, 24) || "未分类";
    const left = labelFor(wordMeta[record.a], record.a);
    const right = labelFor(wordMeta[record.b], record.b);
    entries.push({ key: String(key), kind: "relation", category, label: `${left} ↔ ${right}`, record, trail: record.trail });
  }

  const wordsByCategory = {};
  const relationsByCategory = {};
  const trailMap = {};
  let completedReviews = 0;
  let reviewedEntries = 0;
  let due = 0;
  let upcoming = 0;

  for (const entry of entries) {
    const reviews = Math.max(0, Math.floor(finiteNumber(entry.record.reviews) ?? 0));
    const dueAt = timestamp(entry.record.dueAt) ?? now;
    const status = dueStatus(dueAt, now, upcomingWindowMs);
    const category = categoryBucket(entry.kind === "word" ? wordsByCategory : relationsByCategory, entry.category);
    completedReviews += reviews;
    if (reviews > 0) reviewedEntries += 1;
    category.items += 1;
    category.reviewedItems += Number(reviews > 0);
    category.completedReviews += reviews;
    category.due += Number(status === "due");
    category.upcoming += Number(status === "upcoming");
    due += Number(status === "due");
    upcoming += Number(status === "upcoming");

    const path = normalizeTrail(entry.trail);
    const pathKey = JSON.stringify(path);
    if (!trailMap[pathKey]) {
      trailMap[pathKey] = {
        path,
        items: 0,
        reviewedItems: 0,
        completedReviews: 0,
        due: 0,
        upcoming: 0,
        lastReviewedAt: null,
        lastRating: null,
      };
    }
    const pathSummary = trailMap[pathKey];
    pathSummary.items += 1;
    pathSummary.reviewedItems += Number(reviews > 0);
    pathSummary.completedReviews += reviews;
    pathSummary.due += Number(status === "due");
    pathSummary.upcoming += Number(status === "upcoming");
    const lastReviewedAt = timestamp(entry.record.lastReviewedAt);
    if (lastReviewedAt && (!pathSummary.lastReviewedAt || lastReviewedAt > pathSummary.lastReviewedAt)) {
      pathSummary.lastReviewedAt = lastReviewedAt;
      pathSummary.lastRating = entry.record.lastRating || null;
    }
  }

  const recent = entries
    .map((entry) => ({ entry, reviewedAt: timestamp(entry.record.lastReviewedAt) }))
    .filter(({ reviewedAt }) => reviewedAt)
    .sort((a, b) => b.reviewedAt - a.reviewedAt || a.entry.key.localeCompare(b.entry.key))
    .slice(0, recentLimit)
    .map(({ entry, reviewedAt }) => ({
      key: entry.key,
      kind: entry.kind,
      category: entry.category,
      label: entry.label,
      reviewedAt,
      rating: entry.record.lastRating || null,
      reviews: Math.max(0, Math.floor(finiteNumber(entry.record.reviews) ?? 0)),
      dueAt: timestamp(entry.record.dueAt) ?? now,
      status: dueStatus(timestamp(entry.record.dueAt) ?? now, now, upcomingWindowMs),
      trail: normalizeTrail(entry.trail),
    }));

  const paths = Object.values(trailMap)
    .sort((a, b) => b.items - a.items
      || b.completedReviews - a.completedReviews
      || JSON.stringify(a.path).localeCompare(JSON.stringify(b.path)))
    .slice(0, 20);

  return {
    asOf: now,
    upcomingWindowMs,
    upcomingDays: upcomingWindowMs / DAY,
    totals: {
      saved: entries.length, words: Object.keys(state.saved).length, relations: Object.keys(state.savedRelations).length,
      reviewedEntries,
      completedReviews,
      due,
      upcoming,
    },
    categories: { words: wordsByCategory, relations: relationsByCategory }, recent, paths,
  };
}
