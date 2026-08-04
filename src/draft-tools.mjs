const DEFAULT_STORAGE_KEY = "wordcloud.draft_cards.v1";
const VALID_POS = new Set(["NOM", "VER", "ADJ", "ADV", "PRON", "DET", "PREP", "CONJ", "INTJ", "PHRASE", "AUTRE"]);
const FIELD_LIMITS = {
  lemma: 80,
  pos: 16,
  zhHint: 180,
  note: 800,
  sourceLexemeId: 80,
};

function text(value, limit) {
  return String(value ?? "").trim().slice(0, limit);
}

function normalizePos(value) {
  const pos = text(value, FIELD_LIMITS.pos).toLocaleUpperCase("fr");
  return VALID_POS.has(pos) ? pos : "AUTRE";
}

function isDraftLike(value) {
  return value && typeof value === "object" && typeof value.id === "string" && typeof value.lemma === "string";
}

export function normalizeDraft(value, now = Date.now()) {
  if (!isDraftLike(value)) return null;
  const lemma = text(value.lemma, FIELD_LIMITS.lemma);
  if (!lemma) return null;
  const createdAt = Number(value.createdAt) || now;
  const sourceLexemeId = text(value.sourceLexemeId, FIELD_LIMITS.sourceLexemeId);
  return {
    id: text(value.id, 80) || `draft-${now}`,
    lemma,
    pos: normalizePos(value.pos),
    zhHint: text(value.zhHint, FIELD_LIMITS.zhHint),
    note: text(value.note, FIELD_LIMITS.note),
    sourceLexemeId,
    createdAt,
    updatedAt: Number(value.updatedAt) || createdAt,
  };
}

export function loadDraftState(storage, key = DEFAULT_STORAGE_KEY, now = Date.now()) {
  const empty = { drafts: [], error: null };
  let raw = null;
  try {
    raw = storage.getItem(key);
  } catch (_) {
    return { drafts: [], error: "无法读取本地词卡。浏览器可能限制了本地存储。" };
  }
  if (!raw) return empty;
  try {
    const parsed = JSON.parse(raw);
    const source = Array.isArray(parsed?.drafts) ? parsed.drafts : Array.isArray(parsed) ? parsed : null;
    if (!source) return { drafts: [], error: "本地词卡格式不正确，已忽略损坏内容。" };
    const drafts = source.map((item) => normalizeDraft(item, now)).filter(Boolean);
    return { drafts, error: drafts.length === source.length ? null : "部分本地词卡格式不正确，已忽略损坏条目。" };
  } catch (_) {
    return { drafts: [], error: "本地词卡数据无法解析，已暂时忽略。" };
  }
}

export function saveDraftState(storage, drafts, key = DEFAULT_STORAGE_KEY) {
  const normalized = Array.isArray(drafts) ? drafts.map((item) => normalizeDraft(item)).filter(Boolean) : [];
  try {
    storage.setItem(key, JSON.stringify({ drafts: normalized }));
    return { ok: true, drafts: normalized, error: null };
  } catch (_) {
    return { ok: false, drafts: normalized, error: "无法保存本地词卡。请检查浏览器存储权限或可用空间。" };
  }
}

export function createDraft(input, now = Date.now()) {
  const lemma = text(input?.lemma, FIELD_LIMITS.lemma);
  if (!lemma) return { ok: false, draft: null, error: "请先填写法语词。" };
  const draft = {
    id: `draft-${now}-${Math.random().toString(36).slice(2, 8)}`,
    lemma,
    pos: normalizePos(input?.pos),
    zhHint: text(input?.zhHint, FIELD_LIMITS.zhHint),
    note: text(input?.note, FIELD_LIMITS.note),
    sourceLexemeId: text(input?.sourceLexemeId, FIELD_LIMITS.sourceLexemeId),
    createdAt: now,
    updatedAt: now,
  };
  return { ok: true, draft, error: null };
}

export function updateDraft(draft, patch, now = Date.now()) {
  const current = normalizeDraft(draft, now);
  if (!current) return { ok: false, draft: null, error: "词卡不存在或格式不正确。" };
  const next = { ...current };
  if (Object.prototype.hasOwnProperty.call(patch || {}, "zhHint")) next.zhHint = text(patch.zhHint, FIELD_LIMITS.zhHint);
  if (Object.prototype.hasOwnProperty.call(patch || {}, "note")) next.note = text(patch.note, FIELD_LIMITS.note);
  next.updatedAt = now;
  return { ok: true, draft: next, error: null };
}

export function upsertDraft(drafts, draft) {
  const normalized = normalizeDraft(draft);
  if (!normalized) return Array.isArray(drafts) ? drafts.slice() : [];
  const source = Array.isArray(drafts) ? drafts : [];
  const index = source.findIndex((item) => item.id === normalized.id);
  if (index < 0) return [normalized, ...source];
  return source.map((item, itemIndex) => itemIndex === index ? normalized : item);
}

export function findDraftForWordCard(drafts, input) {
  const source = Array.isArray(drafts) ? drafts.map((item) => normalizeDraft(item)).filter(Boolean) : [];
  const sourceLexemeId = text(input?.sourceLexemeId, FIELD_LIMITS.sourceLexemeId);
  if (sourceLexemeId) {
    const bySource = source.find((item) => item.sourceLexemeId === sourceLexemeId);
    if (bySource) return bySource;
  }
  const lemma = text(input?.lemma, FIELD_LIMITS.lemma).toLocaleLowerCase("fr");
  const pos = normalizePos(input?.pos);
  if (!lemma) return null;
  return source.find((item) => item.lemma.toLocaleLowerCase("fr") === lemma && item.pos === pos) || null;
}

export const DRAFT_STORAGE_KEY = DEFAULT_STORAGE_KEY;
export const DRAFT_POS_OPTIONS = [...VALID_POS];
