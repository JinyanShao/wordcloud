import { normalizeDraft } from "./draft-tools.mjs";

export const LOCAL_DATA_KEYS = {
  personal: "wordcloud.personal.v2",
  draftCards: "wordcloud.draft_cards.v1",
};

function readRaw(storage, key) {
  try {
    return { raw: storage.getItem(key), error: null };
  } catch (_) {
    return { raw: null, error: "浏览器限制了本地存储读取。" };
  }
}

function parseStoredJson(storage, key, label) {
  const read = readRaw(storage, key);
  if (read.error) return { value: null, error: `${label}：${read.error}` };
  if (!read.raw) return { value: null, error: null };
  try {
    return { value: JSON.parse(read.raw), error: null };
  } catch (_) {
    return { value: null, error: `${label}：本地数据无法解析，已在导出中忽略。` };
  }
}

function recordError(errors, error) {
  if (error) errors.push(error);
}

function text(value, limit) {
  return String(value ?? "").trim().slice(0, limit);
}

function number(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function normalizePersonalState(value) {
  const raw = value && typeof value === "object" ? value : {};
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.map((node) => ({
    id: text(node?.id, 80),
    word: text(node?.word, 80),
    pos: text(node?.pos, 24) || "我的词",
    gloss: text(node?.gloss, 180),
    note: text(node?.note, 240),
    x: number(node?.x, 0),
    y: number(node?.y, 0),
    size: Math.max(1, number(node?.size, 3.4)),
  })).filter((node) => node.id && node.word) : [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = Array.isArray(raw.edges) ? raw.edges.map((edge) => ({
    a: text(edge?.a, 80),
    b: text(edge?.b, 80),
    label: text(edge?.label, 120) || "我的联想",
  })).filter((edge) => nodeIds.has(edge.a) || nodeIds.has(edge.b)) : [];
  return { nodes, edges };
}

export function loadPersonalState(storage, key = LOCAL_DATA_KEYS.personal) {
  const parsed = parseStoredJson(storage, key, "我的词网");
  return { data: normalizePersonalState(parsed.value), error: parsed.error };
}

export function exportLocalLearningData(storage, options = {}) {
  const now = Number(options.now) || Date.now();
  const errors = [];
  const personal = loadPersonalState(storage, LOCAL_DATA_KEYS.personal);
  const draftRead = parseStoredJson(storage, LOCAL_DATA_KEYS.draftCards, "我的词卡");
  recordError(errors, personal.error);
  recordError(errors, draftRead.error);

  const draftSource = Array.isArray(draftRead.value?.drafts)
    ? draftRead.value.drafts
    : Array.isArray(draftRead.value)
      ? draftRead.value
      : [];
  if (draftRead.value && !Array.isArray(draftRead.value?.drafts) && !Array.isArray(draftRead.value)) {
    errors.push("我的词卡：本地数据格式不正确，已在导出中忽略。");
  }
  const draftCards = draftSource.map((item) => normalizeDraft(item, now)).filter(Boolean);

  return {
    exportedAt: new Date(now).toISOString(),
    schema: "wordcloud.local-learning-export.v2",
    boundaries: {
      personal: "我的词网节点和个人联想边，只显示在当前浏览器。",
      draftCards: "我的词卡，只保存用户自己的中文提示和备注。",
    },
    storageKeys: { ...LOCAL_DATA_KEYS },
    personal: personal.data,
    draftCards,
    errors,
  };
}
