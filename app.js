(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const canvas = $("#stage");
  const ctx = canvas.getContext("2d", { alpha: false });
  const viewport = $("#viewport");
  const panel = $("#panel");
  const panelContent = $("#panel-content");
  const tooltip = $("#tooltip");
  const search = $("#search");
  const searchResults = $("#search-results");
  const focusBar = $("#focus-bar");
  const trailEl = $("#trail");
  const focusLegend = $("#focus-legend");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const PERSONAL_KEY = "wordcloud.personal.v2";
  const LEARNING_KEY = "wordcloud.learning.v1";
  const MINUTE = 60 * 1000;
  const DAY = 24 * 60 * MINUTE;
  const PROGRESS_UPCOMING_DAYS = 7;
  const MOBILE_BREAKPOINT = 720;
  const CANVAS_FONT = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  const CANVAS_PIXEL_BUDGET = { mobile: 3600000, desktop: 9000000 };
  const VALID_REVIEW_RATINGS = new Set(["again", "hard", "good", "easy"]);
  const REVIEW_RATING_LABELS = { again: "再复习", hard: "模糊", good: "记住", easy: "很熟" };

  const SIGNALS = [[1, "释义接近"], [2, "来源确认的派生"], [4, "拼写相似"], [8, "读音相似"], [16, "审校关系"], [32, "连通骨架"], [64, "Lexique 词形候选"]];
  const RELATION_NAMES = { syn: "近义", compare: "对比", fam: "派生", drift: "语义漂移", trap: "易混", ant: "反义", cause: "因果" };
  const RELATION_ORDER = ["syn", "ant", "compare", "drift", "cause", "trap", "fam", "personal"];
  const FOCUS_LIMITS = { syn: 5, ant: 4, compare: 3, drift: 3, cause: 3, trap: 3, fam: 6, personal: 3 };
  const RELATION_STYLE = {
    syn: { color: "#7b8188", dash: [], arrow: false },
    compare: { color: "#c07a22", dash: [], arrow: true },
    fam: { color: "#3477b8", dash: [], arrow: false },
    drift: { color: "#7859a6", dash: [], arrow: false },
    trap: { color: "#c7465d", dash: [], arrow: false },
    ant: { color: "#278867", dash: [], arrow: false },
    cause: { color: "#6f647d", dash: [], arrow: true },
    personal: { color: "#b96d22", dash: [2, 5], arrow: false },
    satellite: { color: "#a8a69f", dash: [], arrow: false },
  };
  const NODE = { id: 0, word: 1, pos: 2, level: 3, gloss: 4, x: 5, y: 6, size: 7, community: 8, freq: 9, hasGloss: 10, status: 11, note: 12 };

  function runtimeNode(row) {
    const x = row[NODE.x], y = row[NODE.y];
    return {
      id: String(row[NODE.id]), word: row[NODE.word], pos: row[NODE.pos], level: row[NODE.level] || "—",
      gloss: row[NODE.gloss], x, y, homeX: x, homeY: y, drawX: x, drawY: y, targetX: x, targetY: y,
      size: row[NODE.size], community: row[NODE.community], freq: row[NODE.freq], status: row[NODE.status],
      note: row[NODE.note], personal: false, alpha: 1, targetAlpha: 1, focusRole: "global", focusColor: null,
    };
  }

  const officialNodes = GRAPH_NODES.map(runtimeNode);
  const searchOnlyNodes = (GRAPH_SEARCH_LEXEMES || []).map((row) => ({
    id: String(row[0]), word: row[1], pos: row[2], level: row[3] || "—", gloss: row[4], freq: row[5],
    status: row[6], note: row[7], searchOnly: true, personal: false,
  }));
  const foundationalCoreIds = new Set((GRAPH_META.foundational_core_ids || []).map(String));
  const teachingExamples = GRAPH_TEACHING_EXAMPLES || {};
  const contentStatus = GRAPH_CONTENT_STATUS || {};
  const aliasesById = GRAPH_ALIASES || {};
  let searchTools = null;
  let wordCardTools = null;
  let localDataTools = null;
  const nodeById = new Map(officialNodes.map((node) => [node.id, node]));
  for (const node of searchOnlyNodes) nodeById.set(node.id, node);
  const baseLinks = GRAPH_LINKS.map((row) => ({ a: String(row[0]), b: String(row[1]), mask: row[2], weight: row[3] }));
  const officialEdges = GRAPH_OFFICIAL_EDGES.map((row) => ({
    a: String(row[0]), b: String(row[1]), relation: row[2], dimension: row[3], subtype: row[4], direction: row[5],
    label: row[6], explanation: row[7], examples: row[8], confidence: row[9], review: row[10], kind: "official",
  }));
  const officialEdgeByReviewKey = new Map();
  const layoutAdj = new Map();
  const officialAdj = new Map();

  function addAdj(map, id, value) {
    if (!map.has(id)) map.set(id, []);
    map.get(id).push(value);
  }
  for (const edge of baseLinks) {
    addAdj(layoutAdj, edge.a, { ...edge, other: edge.b });
    addAdj(layoutAdj, edge.b, { ...edge, other: edge.a });
  }
  for (const edge of officialEdges) {
    addAdj(officialAdj, edge.a, { ...edge, other: edge.b });
    addAdj(officialAdj, edge.b, { ...edge, other: edge.a });
  }

  import("./src/search-tools.mjs").then((tools) => {
    searchTools = tools;
    if (search.value.trim()) doSearch();
  }).catch(() => {});
  import("./src/word-card-tools.mjs").then((tools) => {
    wordCardTools = tools;
    if (selected && !panel.classList.contains("hidden")) renderPanel(selected);
  }).catch(() => {});
  import("./src/local-data-tools.mjs").then((tools) => {
    localDataTools = tools;
    if (!$("#learning-progress-dialog").classList.contains("hidden")) renderLearningProgress();
  }).catch(() => {});

  let personal = { nodes: [], edges: [] };
  let learning = { saved: {} };
  let personalNodes = [];
  let personalEdges = [];
  let allNodes = [];
  let selected = null;
  let hovered = null;
  let focusConnections = [];
  let focusEdges = [];
  let focusStarted = 0;
  let focusCenter = null;
  let trail = [];
  let width = 0;
  let height = 0;
  let dpr = 1;
  let dragging = false;
  let dragStart = null;
  let moved = false;
  let framePending = false;
  let hitBoxes = new Map();
  let view = { x: 0, y: 0, scale: 1 };
  let homeView = { x: 0, y: 0, scale: 1 };
  let viewTween = null;
  const activePointers = new Map();
  let pinchStart = null;
  const localStorageWarnings = [];

  function rememberLocalWarning(message) {
    if (message && !localStorageWarnings.includes(message)) localStorageWarnings.push(message);
  }

  function localText(value, limit = 120) {
    return String(value ?? "").trim().slice(0, limit);
  }

  function loadPersonal() {
    let raw = null;
    try {
      raw = localStorage.getItem(PERSONAL_KEY);
    } catch (_) {
      rememberLocalWarning("我的词网：浏览器限制了本地存储读取。");
      return { nodes: [], edges: [] };
    }
    if (!raw) return { nodes: [], edges: [] };
    try {
      const value = JSON.parse(raw);
      const nodes = Array.isArray(value?.nodes) ? value.nodes.map((node) => ({
        ...node,
        id: localText(node?.id, 80),
        word: localText(node?.word, 80),
        pos: localText(node?.pos, 24) || "我的词",
        gloss: localText(node?.gloss, 180),
        note: localText(node?.note, 240),
        x: Number.isFinite(Number(node?.x)) ? Number(node.x) : 0,
        y: Number.isFinite(Number(node?.y)) ? Number(node.y) : 0,
        size: Math.max(1, Number(node?.size) || 3.4),
      })).filter((node) => node.id && node.word) : [];
      const edges = Array.isArray(value?.edges) ? value.edges.map((edge) => ({
        a: localText(edge?.a, 80),
        b: localText(edge?.b, 80),
        label: localText(edge?.label, 120) || "我的联想",
      })).filter((edge) => edge.a && edge.b) : [];
      if (!Array.isArray(value?.nodes) || !Array.isArray(value?.edges)) rememberLocalWarning("我的词网：部分本地数据格式不正确，已忽略缺失字段。");
      return { nodes, edges };
    } catch (_) {
      rememberLocalWarning("我的词网：本地数据无法解析，已暂时忽略。");
      return { nodes: [], edges: [] };
    }
  }

  function savePersonal() {
    try {
      localStorage.setItem(PERSONAL_KEY, JSON.stringify(personal));
    } catch (_) {
      rememberLocalWarning("我的词网：无法保存到当前浏览器。");
    }
  }

  function loadLearning() {
    let raw = null;
    try {
      raw = localStorage.getItem(LEARNING_KEY);
    } catch (_) {
      rememberLocalWarning("复习：浏览器限制了本地存储读取。");
      return { saved: {} };
    }
    if (!raw) return { saved: {} };
    try {
      const value = JSON.parse(raw);
      const saved = value?.saved && typeof value.saved === "object" && !Array.isArray(value.saved) ? value.saved : {};
      const savedRelations = value?.savedRelations
        && typeof value.savedRelations === "object"
        && !Array.isArray(value.savedRelations)
        ? value.savedRelations
        : {};
      if (!value?.saved || Array.isArray(value.saved) || typeof value.saved !== "object") rememberLocalWarning("复习：本地数据格式不正确，已忽略缺失字段。");
      if (value?.savedRelations !== undefined && (!value.savedRelations || Array.isArray(value.savedRelations) || typeof value.savedRelations !== "object")) {
        rememberLocalWarning("复习：关系复习数据格式不正确，已忽略缺失字段。");
      }
      const now = Date.now();
      const normalizedRelations = Object.fromEntries(Object.entries(savedRelations)
        .filter(([key]) => localText(key, 180))
        .map(([key, record]) => [String(key), normalizeLearningRelationRecord(record, now)])
        .filter(([, record]) => record.a && record.b && record.relation));
      return {
        saved: Object.fromEntries(Object.entries(saved)
          .filter(([id]) => localText(id, 80))
          .map(([id, record]) => [String(id), normalizeLearningRecord(record, now)])),
        savedRelations: normalizedRelations,
      };
    } catch (_) {
      rememberLocalWarning("复习：本地数据无法解析，已暂时忽略。");
      return { saved: {}, savedRelations: {} };
    }
  }

  function normalizeLearningRecord(record, now = Date.now()) {
    const raw = record && typeof record === "object" ? record : {};
    const addedAt = Number(raw.addedAt) || now;
    const lastReviewedAt = Number(raw.lastReviewedAt) || null;
    return {
      addedAt,
      reviews: Math.max(0, Number(raw.reviews) || 0),
      lastReviewedAt,
      dueAt: Number(raw.dueAt) || lastReviewedAt || now,
      intervalDays: Math.max(0, Number(raw.intervalDays) || 0),
      ease: Math.max(1.3, Number(raw.ease) || 2.3),
      lapses: Math.max(0, Number(raw.lapses) || 0),
      lastRating: VALID_REVIEW_RATINGS.has(raw.lastRating) ? raw.lastRating : null,
      trail: Array.isArray(raw.trail)
        ? raw.trail.map((id) => localText(id, 80)).filter(Boolean).slice(-8)
        : [],
    };
  }

  function normalizeLearningRelationRecord(record, now = Date.now()) {
    const raw = record && typeof record === "object" ? record : {};
    return {
      ...normalizeLearningRecord(raw, now),
      a: localText(raw.a, 80),
      b: localText(raw.b, 80),
      relation: localText(raw.relation, 24),
      dimension: localText(raw.dimension, 80),
    };
  }

  function saveLearning() {
    try {
      localStorage.setItem(LEARNING_KEY, JSON.stringify(learning));
    } catch (_) {
      rememberLocalWarning("复习：无法保存到当前浏览器。");
    }
  }

  personal = loadPersonal();
  learning = loadLearning();
  learning.savedRelations ||= {};

  function savedIds() {
    return Object.keys(learning.saved).filter((id) => nodeById.has(id));
  }

  function relationReviewEntries() {
    return Object.entries(learning.savedRelations || {})
      .map(([key, record]) => {
        const edge = officialEdgeByReviewKey.get(key);
        if (!edge) return null;
        const left = nodeById.get(edge.a);
        const right = nodeById.get(edge.b);
        if (!left || !right) return null;
        return { key, kind: "relation", edge, left, right, record };
      })
      .filter(Boolean);
  }

  function dueReviewEntries(now = Date.now()) {
    const words = savedIds().map((id) => ({
      key: id,
      kind: "word",
      node: nodeById.get(id),
      record: learning.saved[id],
    }));
    const relations = relationReviewEntries();
    const entries = [...words, ...relations]
      .filter((entry) => entry.record.dueAt <= now)
      .sort((a, b) => a.record.dueAt - b.record.dueAt
        || a.record.addedAt - b.record.addedAt
        || a.key.localeCompare(b.key));
    return entries;
  }

  function dueIds(now = Date.now()) {
    return dueReviewEntries(now).map((entry) => entry.key);
  }

  function isSaved(id) {
    return Boolean(learning.saved[String(id)]);
  }

  function isRelationSaved(edge) {
    return Boolean(learning.savedRelations?.[relationReviewKey(edge)]);
  }

  function updateReviewCount() {
    const due = dueReviewEntries().length;
    $("#review-count").textContent = due;
    $("#review-open").setAttribute("aria-label", due ? `开始 ${due} 个到期复习` : "查看复习队列");
  }

  function refreshLearningProgress() {
    const dialog = $("#learning-progress-dialog");
    if (dialog && !dialog.classList.contains("hidden")) renderLearningProgress();
  }

  function formatDue(dueAt, now = Date.now()) {
    const delta = dueAt - now;
    if (delta <= 0) return "现在可复习";
    if (delta < DAY) return `约 ${Math.ceil(delta / (60 * MINUTE))} 小时后`;
    if (delta < 2 * DAY) return "明天复习";
    return `${Math.ceil(delta / DAY)} 天后复习`;
  }

  function scheduleReview(record, rating, now = Date.now()) {
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
    next.lastRating = VALID_REVIEW_RATINGS.has(rating) ? rating : null;
    return next;
  }

  function toggleSaved(id) {
    const key = String(id);
    if (isSaved(key)) delete learning.saved[key];
    else learning.saved[key] = normalizeLearningRecord({ trail }, Date.now());
    saveLearning();
    updateReviewCount();
    refreshLearningProgress();
  }

  function toggleRelationSaved(edge) {
    const key = relationReviewKey(edge);
    if (isRelationSaved(edge)) {
      delete learning.savedRelations[key];
    } else {
      learning.savedRelations[key] = normalizeLearningRelationRecord({
        a: edge.a,
        b: edge.b,
        relation: edge.relation,
        dimension: edge.dimension,
        trail,
      }, Date.now());
    }
    saveLearning();
    updateReviewCount();
    refreshLearningProgress();
  }

  function rebuildPersonal() {
    for (const node of personalNodes) nodeById.delete(node.id);
    personalNodes = personal.nodes.map((raw) => {
      const x = raw.x, y = raw.y;
      return {
        ...raw, id: String(raw.id), x, y, homeX: x, homeY: y, drawX: x, drawY: y, targetX: x, targetY: y,
        personal: true, size: raw.size || 3.2, status: "personal", level: "我的", alpha: 1, targetAlpha: 1,
        focusRole: "global", focusColor: RELATION_STYLE.personal.color,
      };
    });
    personalEdges = personal.edges.map((edge) => ({ ...edge, a: String(edge.a), b: String(edge.b), kind: "personal", relation: "personal" }));
    for (const node of personalNodes) nodeById.set(node.id, node);
    allNodes = officialNodes.concat(personalNodes);
  }
  rebuildPersonal();

  const xs = officialNodes.map((node) => node.x);
  const ys = officialNodes.map((node) => node.y);
  const bounds = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };

  function isMobileLayout() {
    return width <= MOBILE_BREAKPOINT;
  }

  function canvasDpr(cssWidth, cssHeight) {
    const deviceDpr = Math.max(1, window.devicePixelRatio || 1);
    const mobile = cssWidth <= MOBILE_BREAKPOINT;
    const maxDpr = mobile ? 3 : 2.5;
    const pixelBudget = mobile ? CANVAS_PIXEL_BUDGET.mobile : CANVAS_PIXEL_BUDGET.desktop;
    const budgetDpr = Math.sqrt(pixelBudget / Math.max(1, cssWidth * cssHeight));
    return Math.max(1, Math.min(deviceDpr, maxDpr, budgetDpr));
  }

  function resize() {
    const rect = viewport.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = canvasDpr(width, height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    if (selected) enterFocus(selected, { addTrail: false, preserveCenter: true });
    else fitHome(false);
    requestDraw();
  }

  function computeHomeView() {
    const spanX = Math.max(1, bounds.maxX - bounds.minX);
    const spanY = Math.max(1, bounds.maxY - bounds.minY);
    return {
      x: (bounds.minX + bounds.maxX) / 2,
      y: (bounds.minY + bounds.maxY) / 2,
      scale: Math.min((width - 70) / spanX, (height - 70) / spanY),
    };
  }

  function fitHome(animate = true) {
    homeView = computeHomeView();
    selected = null;
    hovered = null;
    focusConnections = [];
    focusEdges = [];
    focusCenter = null;
    trail = [];
    for (const node of allNodes) {
      node.targetX = node.homeX; node.targetY = node.homeY;
      node.targetAlpha = node.status === "eligible" || node.personal ? 1 : .44;
      node.focusRole = "global"; node.focusColor = null;
    }
    panel.classList.add("hidden");
    viewport.classList.remove("is-focused", "panel-open");
    focusBar.classList.add("hidden");
    focusLegend.classList.add("hidden");
    $("#legend").classList.remove("focus-hidden");
    $("#map-copy").classList.remove("quiet");
    $("#reset").textContent = "全图";
    updateStats();
    if (animate) animateView(homeView, 520); else view = { ...homeView };
    requestDraw();
  }

  function animateView(target, duration = 420) {
    if (reducedMotion.matches) {
      view = { ...target };
      viewTween = null;
    } else {
      viewTween = { from: { ...view }, to: { ...target }, began: performance.now(), duration };
    }
    requestDraw();
  }

  function screen(node) {
    return { x: (node.drawX - view.x) * view.scale + width / 2, y: (node.drawY - view.y) * view.scale + height / 2 };
  }

  function worldAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    return { x: view.x + (clientX - rect.left - width / 2) / view.scale, y: view.y + (clientY - rect.top - height / 2) / view.scale };
  }

  function visible(point, margin = 10) {
    return point.x >= -margin && point.x <= width + margin && point.y >= -margin && point.y <= height + margin;
  }

  function nodeRadius(node) {
    const base = node.personal ? 3.6 : node.size;
    return Math.max(1.05, Math.min(7.5, base * Math.sqrt(Math.max(.32, view.scale))));
  }

  function pairKey(a, b) {
    return a < b ? `${a}|${b}` : `${b}|${a}`;
  }

  function relationReviewKey(edge) {
    const endpoints = [String(edge?.a || ""), String(edge?.b || "")].sort();
    return `relation:${endpoints[0]}|${endpoints[1]}|${String(edge?.relation || "")}|${String(edge?.dimension || "")}`;
  }

  for (const edge of officialEdges) {
    officialEdgeByReviewKey.set(relationReviewKey(edge), edge);
  }

  function personalFor(id) {
    return personalEdges.flatMap((edge) => {
      if (edge.a === id) return [{ ...edge, other: edge.b }];
      if (edge.b === id) return [{ ...edge, other: edge.a }];
      return [];
    });
  }

  function strongStructuralFor(id) {
    const officialPairs = new Set((officialAdj.get(id) || []).map((edge) => pairKey(id, edge.other)));
    return (layoutAdj.get(id) || [])
      .filter((edge) => (edge.mask & 2) && edge.weight >= .72 && !officialPairs.has(pairKey(id, edge.other)))
      .filter((edge) => nodeById.get(edge.other)?.word !== nodeById.get(id)?.word)
      .map((edge) => ({
        ...edge, a: id, b: edge.other, other: edge.other, relation: "fam", label: "构词线索", kind: "structural", review: "candidate",
      }));
  }

  function strongFormFor(id) {
    const officialPairs = new Set((officialAdj.get(id) || []).map((edge) => pairKey(id, edge.other)));
    return (layoutAdj.get(id) || [])
      .filter((edge) => (edge.mask & 4) && (edge.mask & 8) && edge.weight >= .76 && !officialPairs.has(pairKey(id, edge.other)))
      .filter((edge) => nodeById.get(edge.other)?.word !== nodeById.get(id)?.word)
      .map((edge) => ({
        ...edge, a: id, b: edge.other, other: edge.other, relation: "trap", label: "形音相近", kind: "form", review: "candidate",
      }));
  }

  function relationRank(edge) {
    const rank = RELATION_ORDER.indexOf(edge.relation);
    return rank < 0 ? RELATION_ORDER.length : rank;
  }

  function connectionsFor(id, limit = 16) {
    const byNeighbor = new Map();
    const officialByNeighbor = new Map();
    for (const edge of officialAdj.get(id) || []) {
      if (!officialByNeighbor.has(edge.other)) officialByNeighbor.set(edge.other, []);
      officialByNeighbor.get(edge.other).push({ ...edge, kind: "official" });
    }
    for (const [other, relations] of officialByNeighbor) {
      relations.sort((a, b) => relationRank(a) - relationRank(b) || Number(b.review === "reviewed") - Number(a.review === "reviewed"));
      byNeighbor.set(other, { ...relations[0], relations });
    }
    const candidates = [...personalFor(id), ...strongFormFor(id), ...strongStructuralFor(id)];
    const priority = { official: 4, personal: 3, form: 2, structural: 1 };
    for (const edge of candidates) {
      if (!nodeById.has(edge.other) || edge.other === id) continue;
      const existing = byNeighbor.get(edge.other);
      if (!existing || priority[edge.kind] > priority[existing.kind]) byNeighbor.set(edge.other, edge);
    }
    const ordered = [...byNeighbor.values()]
      .sort((a, b) => {
        const pa = priority[a.kind], pb = priority[b.kind];
        if (pa !== pb) return pb - pa;
        const ra = relationRank(a), rb = relationRank(b);
        if (ra !== rb) return ra - rb;
        return (nodeById.get(a.other)?.word || "").localeCompare(nodeById.get(b.other)?.word || "", "fr");
      });
    const counts = new Map();
    const selected = [];
    for (const edge of ordered) {
      const key = edge.kind === "official" ? edge.relation : edge.kind;
      const relationLimit = edge.kind === "official" ? (FOCUS_LIMITS[edge.relation] || 3) : edge.kind === "form" ? 2 : 3;
      if ((counts.get(key) || 0) >= relationLimit) continue;
      counts.set(key, (counts.get(key) || 0) + 1);
      selected.push(edge);
      if (selected.length >= limit) break;
    }
    return selected;
  }

  function focusScaleFor(count) {
    if (isMobileLayout()) return count > 6 ? .88 : .96;
    if (count > 12) return .86;
    return 1.02;
  }

  function focusViewTarget(center, scale, panelVisible = true) {
    const xShift = width > 900 ? 135 / scale : 0;
    const yShift = isMobileLayout() && panelVisible ? height * .22 / scale : 0;
    return { x: center.x + xShift, y: center.y + yShift, scale };
  }

  function positionRing(items, center, radius, startAngle = -Math.PI / 2) {
    items.forEach((connection, index) => {
      const angle = startAngle + index / Math.max(1, items.length) * Math.PI * 2;
      const node = nodeById.get(connection.other);
      node.targetX = center.x + Math.cos(angle) * radius;
      node.targetY = center.y + Math.sin(angle) * radius;
      node._focusAngle = angle;
      node.focusRole = "direct";
      node.focusColor = visualFor(connection).color;
      node.targetAlpha = 1;
      connection.angle = angle;
    });
  }

  function enterFocus(id, options = {}) {
    const node = nodeById.get(String(id));
    if (!node) return;
    if (options.resetTrail) trail = [];
    const previousSelected = selected;
    const center = options.preserveCenter && focusCenter
      ? focusCenter
      : previousSelected && node.focusRole === "direct"
        ? { x: node.drawX, y: node.drawY }
        : { x: node.drawX, y: node.drawY };

    selected = node.id;
    focusCenter = center;
    focusConnections = connectionsFor(node.id, isMobileLayout() ? 8 : 16);
    const focusScale = focusScaleFor(focusConnections.length);

    for (const item of allNodes) {
      item.targetX = item.homeX; item.targetY = item.homeY;
      item.targetAlpha = .075;
      item.focusRole = "background"; item.focusColor = null;
    }
    node.targetX = center.x; node.targetY = center.y;
    node.targetAlpha = 1; node.focusRole = "center"; node.focusColor = "#171816";

    if (focusConnections.length <= 10) {
      const screenRadius = isMobileLayout()
        ? Math.max(108, Math.min(width * .32, height * .16))
        : 215;
      positionRing(focusConnections, center, screenRadius / focusScale);
    } else {
      const split = Math.ceil(focusConnections.length / 2);
      positionRing(focusConnections.slice(0, split), center, 178 / focusScale);
      positionRing(focusConnections.slice(split), center, 300 / focusScale, -Math.PI / 2 + Math.PI / Math.max(1, focusConnections.length - split));
    }

    focusEdges = focusConnections.map((edge, index) => ({
      ...edge, from: node.id, to: edge.other, satellite: false, delay: 100 + index * 86,
    }));

    if (!isMobileLayout() && focusConnections.length && focusConnections.length <= 12) {
      const directIds = new Set([node.id, ...focusConnections.map((edge) => edge.other)]);
      const usedSatellites = new Set();
      let satelliteIndex = 0;
      for (const parentConnection of focusConnections) {
        if (satelliteIndex >= 16) break;
        const parent = nodeById.get(parentConnection.other);
        const satellites = connectionsFor(parent.id, 8)
          .filter((edge) => !directIds.has(String(edge.other))
            && nodeById.get(String(edge.other))?.focusRole === "background"
            && !usedSatellites.has(String(edge.other)))
          .slice(0, 2);
        satellites.forEach((edge, localIndex) => {
          if (satelliteIndex >= 16) return;
          usedSatellites.add(String(edge.other));
          const satellite = nodeById.get(String(edge.other));
          const branchSpread = satellites.length > 1 ? .68 : 0;
          const angle = parent._focusAngle + (localIndex - (satellites.length - 1) / 2) * branchSpread;
          satellite.targetX = parent.targetX + Math.cos(angle) * 84 / focusScale;
          satellite.targetY = parent.targetY + Math.sin(angle) * 84 / focusScale;
          satellite._focusAngle = angle;
          satellite.targetAlpha = .52;
          satellite.focusRole = "satellite";
          satellite.focusColor = visualFor(edge).color;
          focusEdges.push({ ...edge, from: parent.id, to: edge.other, satellite: true, delay: 540 + satelliteIndex * 34 });
          satelliteIndex += 1;
        });
      }
    }

    if (options.addTrail !== false) {
      if (trail[trail.length - 1] !== node.id) trail.push(node.id);
      if (trail.length > 8) trail = trail.slice(-8);
    }
    focusStarted = performance.now();
    renderTrail();
    renderPanel(node);
    viewport.classList.add("is-focused", "panel-open");
    $("#map-copy").classList.add("quiet");
    focusBar.classList.remove("hidden");
    focusLegend.classList.remove("hidden");
    $("#legend").classList.add("focus-hidden");
    $("#reset").textContent = "返回全图";
    searchResults.classList.add("hidden");
    search.blur();
    updateStats();
    animateView(focusViewTarget(center, focusScale, true), 560);
    requestDraw();
  }

  function visualFor(edge) {
    if (edge.satellite) return { ...RELATION_STYLE.satellite, alpha: .34, label: "" };
    if (edge.kind === "personal") return { ...RELATION_STYLE.personal, alpha: .88, label: edge.label || "我的联想" };
    if (edge.kind === "structural") return { ...RELATION_STYLE.fam, dash: [6, 5], alpha: .68, label: `${edge.label || "构词线索"} · 待核准` };
    if (edge.kind === "form") return { ...RELATION_STYLE.trap, dash: [3, 5], alpha: .58, label: `${edge.label || "形音相近"} · 候选` };
    const style = RELATION_STYLE[edge.relation] || RELATION_STYLE.syn;
    const mappedLabel = edge.label ? RELATION_NAMES[edge.label] : null;
    const relationName = RELATION_NAMES[edge.relation] || edge.relation || "已审校";
    // Canvas chips stay short (relation name only); custom teaching labels are
    // surfaced on the word card via `note`, never drawn across an edge.
    return { ...style, alpha: .95, label: mappedLabel || relationName, note: mappedLabel || !edge.label ? "" : edge.label };
  }

  function updateAnimations(now) {
    let active = false;
    if (viewTween) {
      const t = Math.min(1, (now - viewTween.began) / viewTween.duration);
      const eased = 1 - Math.pow(1 - t, 3);
      view.x = viewTween.from.x + (viewTween.to.x - viewTween.from.x) * eased;
      view.y = viewTween.from.y + (viewTween.to.y - viewTween.from.y) * eased;
      view.scale = viewTween.from.scale + (viewTween.to.scale - viewTween.from.scale) * eased;
      if (t >= 1) viewTween = null; else active = true;
    }
    const factor = reducedMotion.matches ? 1 : .13;
    for (const node of allNodes) {
      const dx = node.targetX - node.drawX, dy = node.targetY - node.drawY, da = node.targetAlpha - node.alpha;
      if (Math.abs(dx) > .05 || Math.abs(dy) > .05 || Math.abs(da) > .005) {
        node.drawX += dx * factor; node.drawY += dy * factor; node.alpha += da * factor;
        active = true;
      } else {
        node.drawX = node.targetX; node.drawY = node.targetY; node.alpha = node.targetAlpha;
      }
    }
    if (selected && now - focusStarted < 1100 + focusEdges.length * 45) active = true;
    return active;
  }

  function roundedRect(x, y, w, h, radius) {
    const r = Math.min(radius, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawArrow(from, to, color, alpha) {
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    const tip = { x: to.x - Math.cos(angle) * 18, y: to.y - Math.sin(angle) * 18 };
    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(tip.x, tip.y);
    ctx.lineTo(tip.x - Math.cos(angle - .52) * 7, tip.y - Math.sin(angle - .52) * 7);
    ctx.lineTo(tip.x - Math.cos(angle + .52) * 7, tip.y - Math.sin(angle + .52) * 7);
    ctx.closePath(); ctx.fill();
  }

  function directionTarget(edge) {
    if (!edge.direction || !edge.direction.includes("->")) return edge.to;
    return edge.direction.split("->")[1];
  }

  function drawEdgeChip(text, x, y, color, alpha) {
    if (!text) return;
    const mobile = isMobileLayout();
    const fontSize = mobile ? 10.5 : 10;
    const h = mobile ? 23 : 21;
    ctx.font = `600 ${fontSize}px ${CANVAS_FONT}`;
    const w = ctx.measureText(text).width + (mobile ? 20 : 17);
    ctx.globalAlpha = Math.min(1, alpha * .98);
    roundedRect(x - w / 2, y - h / 2, w, h, h / 2);
    ctx.fillStyle = "#fbfaf7"; ctx.fill();
    ctx.strokeStyle = color; ctx.lineWidth = mobile ? 1.25 : 1; ctx.stroke();
    ctx.fillStyle = color; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, x, y + .5);
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  }

  function drawFocusEdge(edge, now) {
    const a = nodeById.get(edge.from), b = nodeById.get(edge.to);
    if (!a || !b) return;
    const pa = screen(a), pb = screen(b);
    const raw = reducedMotion.matches ? 1 : Math.max(0, Math.min(1, (now - focusStarted - edge.delay) / 360));
    if (raw <= 0) return;
    const progress = 1 - Math.pow(1 - raw, 3);
    const end = { x: pa.x + (pb.x - pa.x) * progress, y: pa.y + (pb.y - pa.y) * progress };
    const visual = visualFor(edge);
    ctx.globalAlpha = visual.alpha * Math.min(a.alpha, b.alpha);
    ctx.strokeStyle = visual.color;
    ctx.lineWidth = edge.satellite ? .9 : edge.kind === "official" ? 2 : 1.5;
    ctx.setLineDash(visual.dash);
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(end.x, end.y); ctx.stroke();
    ctx.setLineDash([]);

    if (raw > .86 && visual.arrow && !edge.satellite) {
      const target = directionTarget(edge);
      if (target === edge.to) drawArrow(pa, pb, visual.color, visual.alpha);
      else drawArrow(pb, pa, visual.color, visual.alpha);
    }
    if (raw > .68 && !edge.satellite) {
      const t = .52;
      const mx = pa.x + (pb.x - pa.x) * t, my = pa.y + (pb.y - pa.y) * t;
      if (edge.relation === "trap" && edge.kind === "official") {
        ctx.globalAlpha = 1; ctx.strokeStyle = "#fbfaf7"; ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(mx - 4, my - 4); ctx.lineTo(mx + 4, my + 4); ctx.moveTo(mx - 4, my + 4); ctx.lineTo(mx + 4, my - 4); ctx.stroke();
        ctx.strokeStyle = visual.color; ctx.lineWidth = 1.8; ctx.stroke();
      } else {
        drawEdgeChip(visual.label, mx, my, visual.color, visual.alpha);
      }
    }
  }

  function drawFocusCard(node, point) {
    const mobile = isMobileLayout();
    const center = node.focusRole === "center";
    const wordFont = `650 ${center ? (mobile ? 16 : 15) : (mobile ? 13.5 : 12.5)}px ${CANVAS_FONT}`;
    const posFont = `550 ${mobile ? 9.5 : 9}px ${CANVAS_FONT}`;
    ctx.font = wordFont;
    const wordWidth = ctx.measureText(node.word).width;
    ctx.font = posFont;
    const posWidth = ctx.measureText(node.pos).width;
    const h = center ? (mobile ? 40 : 36) : (mobile ? 35 : 31);
    const leftPad = mobile ? 13 : 11;
    const gap = mobile ? 6 : 4;
    const rightPad = mobile ? 12 : 10;
    const w = Math.max(mobile ? 76 : 68, wordWidth + posWidth + leftPad + gap + rightPad);
    const x = point.x - w / 2, y = point.y - h / 2;
    ctx.globalAlpha = node.alpha;
    roundedRect(x, y, w, h, h / 2);
    if (center) {
      ctx.fillStyle = node.personal ? RELATION_STYLE.personal.color : "#171816";
      ctx.fill();
    } else {
      ctx.fillStyle = "rgba(251,250,247,.97)"; ctx.fill();
      ctx.strokeStyle = node.focusColor || "#777871"; ctx.lineWidth = mobile ? 1.5 : 1.25; ctx.stroke();
    }
    ctx.font = wordFont;
    ctx.fillStyle = center ? "#fbfaf7" : "#20211e";
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    ctx.fillText(node.word, x + leftPad, point.y + .3);
    ctx.font = posFont;
    ctx.fillStyle = center ? "rgba(251,250,247,.7)" : "#74756e";
    ctx.fillText(node.pos, x + leftPad + wordWidth + gap, point.y + .3);
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    const hitPadding = mobile ? 6 : 3;
    hitBoxes.set(node.id, { x: x - hitPadding, y: y - hitPadding, w: w + hitPadding * 2, h: h + hitPadding * 2 });
  }

  function drawFocusNode(node) {
    const p = screen(node);
    if (!visible(p, 50)) return;
    if (node.focusRole === "center" || node.focusRole === "direct") {
      drawFocusCard(node, p);
      return;
    }
    if (node.focusRole === "satellite") {
      ctx.globalAlpha = node.alpha;
      ctx.fillStyle = node.focusColor || "#8c8b84";
      ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2); ctx.fill();
      ctx.font = `500 9.5px ${CANVAS_FONT}`; ctx.fillStyle = "#686963";
      const labelWidth = ctx.measureText(node.word).width;
      const labelOnLeft = Math.cos(node._focusAngle || 0) < 0;
      ctx.textAlign = labelOnLeft ? "right" : "left";
      ctx.fillText(node.word, p.x + (labelOnLeft ? -6 : 6), p.y - 3);
      const labelX = labelOnLeft ? p.x - labelWidth - 10 : p.x - 7;
      hitBoxes.set(node.id, { x: labelX, y: p.y - 9, w: labelWidth + 17, h: 18 });
      ctx.textAlign = "left";
      return;
    }
    const isHovered = node.id === hovered;
    ctx.globalAlpha = isHovered ? .92 : node.alpha;
    ctx.fillStyle = isHovered ? "#343530" : "#85857e";
    ctx.beginPath(); ctx.arc(p.x, p.y, isHovered ? 4.2 : Math.max(.8, nodeRadius(node) * .68), 0, Math.PI * 2); ctx.fill();
    if (isHovered) {
      ctx.globalAlpha = .48; ctx.strokeStyle = "#343530"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(p.x, p.y, 7.2, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = .94; ctx.fillStyle = "#343530"; ctx.font = `600 ${isMobileLayout() ? 12 : 11}px ${CANVAS_FONT}`;
      ctx.fillText(node.word, p.x + 10, p.y - 5);
    }
  }

  function drawGlobal(now) {
    ctx.lineCap = "round";
    for (const edge of baseLinks) {
      const learningTopology = edge.mask & (1 | 2 | 16);
      if (!learningTopology || edge.weight < .26) continue;
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      if (!visible(pa, 30) && !visible(pb, 30)) continue;
      ctx.globalAlpha = (isMobileLayout() ? .032 : .045) + edge.weight * (isMobileLayout() ? .026 : .034);
      ctx.strokeStyle = "#8f9089"; ctx.lineWidth = isMobileLayout() ? .62 : .68;
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
    for (const edge of personalEdges) {
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      ctx.globalAlpha = .72; ctx.strokeStyle = RELATION_STYLE.personal.color; ctx.lineWidth = 1.1; ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke(); ctx.setLineDash([]);
    }

    const labels = [];
    for (const node of allNodes) {
      const p = screen(node);
      if (!visible(p, 16)) continue;
      const radius = nodeRadius(node);
      ctx.globalAlpha = node.alpha;
      ctx.fillStyle = node.personal ? RELATION_STYLE.personal.color : "#686963";
      ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill();
      const labelByZoom = (view.scale > 1.18 && node.size > 4.4) || (view.scale > 2.15 && node.size > 3.1) || view.scale > 4.5;
      if (node.id === hovered || labelByZoom) labels.push({ node, p, priority: node.id === hovered ? 90 : node.size });
    }
    labels.sort((a, b) => b.priority - a.priority);
    const occupied = [];
    for (const item of labels.slice(0, 150)) {
      ctx.font = item.priority >= 80 ? `650 ${isMobileLayout() ? 13 : 12.5}px ${CANVAS_FONT}` : `550 ${isMobileLayout() ? 11 : 10.5}px ${CANVAS_FONT}`;
      const textWidth = ctx.measureText(item.node.word).width;
      const x = item.p.x + nodeRadius(item.node) + 5, y = item.p.y - 3;
      const box = { x, y: y - 11, w: textWidth + 4, h: 15 };
      const collides = item.priority < 80 && occupied.some((other) => box.x < other.x + other.w && box.x + box.w > other.x && box.y < other.y + other.h && box.y + box.h > other.y);
      if (collides) continue;
      occupied.push(box); ctx.globalAlpha = .9; ctx.fillStyle = item.node.personal ? "#9a5619" : "#282925";
      ctx.fillText(item.node.word, x, y);
    }
  }

  function drawFocus(now) {
    for (const edge of focusEdges) drawFocusEdge(edge, now);
    for (const node of allNodes) {
      if (node.focusRole === "background") drawFocusNode(node);
    }
    for (const node of allNodes) {
      if (node.focusRole === "satellite") drawFocusNode(node);
    }
    for (const node of allNodes) {
      if (node.focusRole === "direct") drawFocusNode(node);
    }
    const center = nodeById.get(selected);
    if (center) drawFocusNode(center);

    if (!focusConnections.length && center) {
      const p = screen(center);
      ctx.globalAlpha = .76; ctx.fillStyle = "#686963"; ctx.font = `550 11.5px ${CANVAS_FONT}`; ctx.textAlign = "center";
      ctx.fillText("暂无可展示的可信关系", p.x, p.y + 44);
      ctx.font = `450 10px ${CANVAS_FONT}`; ctx.fillStyle = "#8d8e87";
      ctx.fillText("自动近邻仍在清理，不作为正式关系显示", p.x, p.y + 61);
      ctx.textAlign = "left";
    }

    const rippleAge = now - focusStarted;
    if (rippleAge >= 0 && rippleAge < 720 && center) {
      const p = screen(center), t = rippleAge / 720;
      ctx.globalAlpha = (1 - t) * .28; ctx.strokeStyle = center.personal ? RELATION_STYLE.personal.color : "#171816"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x, p.y, 15 + t * 44, 0, Math.PI * 2); ctx.stroke();
    }
  }

  function draw(now = performance.now()) {
    framePending = false;
    const active = updateAnimations(now);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#f7f6f2"; ctx.fillRect(0, 0, width, height);
    hitBoxes = new Map();
    if (selected) drawFocus(now); else drawGlobal(now);
    ctx.globalAlpha = 1; ctx.setLineDash([]);
    if (active) requestDraw();
  }

  function requestDraw() {
    if (framePending) return;
    framePending = true;
    requestAnimationFrame(draw);
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left, y = clientY - rect.top;
    if (selected) {
      for (const [id, box] of hitBoxes) {
        if (x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h) return nodeById.get(id);
      }
    }
    const mobile = isMobileLayout();
    let best = null, bestDistance = selected ? (mobile ? 9 : 5) : (mobile ? 18 : 12);
    const coarseLimit = mobile ? 24 : 13;
    for (const node of allNodes) {
      const p = screen(node);
      if (Math.abs(p.x - x) > coarseLimit || Math.abs(p.y - y) > coarseLimit) continue;
      const hitRadius = selected && node.focusRole === "background" ? Math.max(2, nodeRadius(node) * .68) : nodeRadius(node);
      const distance = Math.hypot(p.x - x, p.y - y) - hitRadius;
      if (distance < bestDistance) { bestDistance = distance; best = node; }
    }
    return best;
  }

  function signals(mask) {
    return SIGNALS.filter(([bit]) => mask & bit).map(([, label]) => label).join(" · ");
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function relationButton(node, edge) {
    const visual = visualFor(edge);
    const caption = visual.note ? `${visual.label} · ${visual.note}` : visual.label;
    return `<button class="relation-item ${edge.kind}" style="--relation-color:${visual.color}" data-node="${escapeHtml(node.id)}"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml(caption)}</small></button>`;
  }

  function renderSenseGroups(node) {
    const groups = GRAPH_SENSES[node.id] || [];
    const flattened = wordCardTools?.flattenSenseGroups(groups)
      || groups.flatMap((group, groupIndex) => group.senses.map((sense) => ({ ...sense, groupIndex, sourceUrl: group.sourceUrl })));
    if (!flattened.length) return "";
    const renderItems = (items, includeExamples = true) => items.map((sense) => `
      <li><span>${groups.length > 1 ? `${sense.groupIndex + 1}.${escapeHtml(sense.number)}` : escapeHtml(sense.number)}</span><div><p>${escapeHtml(sense.definition)}</p>${includeExamples && sense.examples?.length ? `<ul class="sense-examples">${sense.examples.map((example) => `<li>${escapeHtml(example)}</li>`).join("")}</ul>` : ""}</div></li>
    `).join("");
    const visible = flattened.slice(0, 5);
    const hidden = flattened.slice(5);
    const sourceUrl = groups[0]?.sourceUrl;
    return `<section class="panel-section sense-section">
      <h3>法语义项 · ${flattened.length}</h3>
      <ol class="sense-list">${renderItems(visible, !foundationalCoreIds.has(node.id) && !node.searchOnly)}</ol>
      ${hidden.length ? `<details class="sense-more"><summary>查看其余 ${hidden.length} 个义项</summary><ol class="sense-list continued">${renderItems(hidden, !foundationalCoreIds.has(node.id) && !node.searchOnly)}</ol></details>` : ""}
      ${(foundationalCoreIds.has(node.id) || node.searchOnly) && flattened.some((sense) => sense.examples?.length) ? `<details class="sense-more source-examples"><summary>查看来源原例句</summary><ol class="sense-list continued">${renderItems(flattened)}</ol></details>` : ""}
      ${sourceUrl ? `<a class="sense-source" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Wiktionnaire 来源 ↗</a>` : ""}
    </section>`;
  }

  function renderSenseSummary(summary) {
    if (!summary.senseTotal) return "";
    return `<section class="panel-priority sense-priority" aria-label="法语释义摘要">
      <h3>法语释义摘要 · ${summary.senseTotal}</h3>
      <ol>${summary.sensePreview.map((sense) => `<li>${escapeHtml(sense.definition)}</li>`).join("")}</ol>
    </section>`;
  }

  function renderUsageSummary(summary) {
    if (!summary.hasLearningCues) return "";
    const collocations = summary.collocationPreview.map((item) => `<li><strong>${escapeHtml(item.expression)}</strong><span>${escapeHtml(item.gloss || "")}</span></li>`).join("");
    const examples = summary.teachingExamplePreview.map((item) => `<li><strong>${escapeHtml(item.text)}</strong><span>${escapeHtml(item.gloss || "")}</span></li>`).join("");
    return `<section class="panel-priority usage-priority" aria-label="常用搭配和例句入口">
      <h3>常用搭配 / 例句</h3>
      <ul>${collocations}${examples}</ul>
    </section>`;
  }

  function renderRelationEntry(summary, relationCounts) {
    if (!summary.relationTotal) return "";
    const items = [
      relationCounts.reviewed ? `审校 ${relationCounts.reviewed}` : "",
      relationCounts.sourced ? `来源 ${relationCounts.sourced}` : "",
      relationCounts.mine ? `我的 ${relationCounts.mine}` : "",
      relationCounts.form + relationCounts.structural ? `线索 ${relationCounts.form + relationCounts.structural}` : "",
    ].filter(Boolean);
    return `<section class="panel-priority relation-priority" aria-label="关系入口">
      <h3>关系入口</h3>
      <p>${escapeHtml(items.join(" · ") || "暂无关系")}</p>
    </section>`;
  }

  function renderTeachingExamples(node) {
    const examples = teachingExamples[node.id] || [];
    if (!examples.length) return "";
    return `<section class="panel-section teaching-examples"><h3>学习例句 · 审校</h3><ul>${examples.map((example) => `<li><strong>${escapeHtml(example.text)}</strong><span>${escapeHtml(example.gloss)}</span></li>`).join("")}</ul></section>`;
  }

  function renderEditorialLearning(node) {
    const learning = GRAPH_LEARNING[node.id];
    if (!learning) return "";
    const collocations = learning.collocations || [];
    return `${collocations.length ? `<section class="panel-section collocation-section"><h3>常用搭配与固定表达</h3><ul class="collocation-list">${collocations.map((item) => `<li><strong>${escapeHtml(item.expression)}</strong><span>${escapeHtml(item.gloss)}</span></li>`).join("")}</ul></section>` : ""}
      ${learning.etymology ? `<section class="panel-section etymology-section"><h3>词源线索 · 审校</h3><p>${escapeHtml(learning.etymology.text)}</p><small>${escapeHtml(learning.etymology.source)} · ${escapeHtml(learning.etymology.reviewedAt)}</small></section>` : ""}`;
  }

  function relationNotesFor(items) {
    if (wordCardTools?.selectReviewedRelationNotes) return wordCardTools.selectReviewedRelationNotes(items);
    return items
      .filter(({ edge }) => edge.review === "reviewed" && edge.explanation && !edge.explanation.includes("requires production re-review"))
      .map(({ edge, node: other }) => ({
        a: edge.a,
        b: edge.b,
        word: other.word,
        pos: other.pos,
        relation: edge.relation,
        dimension: edge.dimension,
        label: edge.label,
        explanation: edge.explanation,
        examples: (() => {
          try {
            const parsed = JSON.parse(edge.examples || "[]");
            return Array.isArray(parsed) ? parsed : [];
          } catch {
            return [];
          }
        })(),
      }));
  }

  function renderReviewedRelationNotes(items) {
    const notes = relationNotesFor(items);
    if (!notes.length) return "";
    return `<section class="panel-section contrast-section"><h3>用法区分 · 审校</h3>${notes.map((note) => `
      <article class="contrast-note">
        <p><strong>${escapeHtml(note.word)}</strong> · ${escapeHtml(note.label)}</p>
        <p class="contrast-explanation">${escapeHtml(note.explanation)}</p>
        ${note.examples?.length ? `<ul class="contrast-examples">${note.examples.map((example) => `<li>${escapeHtml(example)}</li>`).join("")}</ul>` : ""}
        <div class="contrast-actions">
          <button class="${isRelationSaved(note) ? "quiet-button" : "primary-button"}" type="button" data-review-relation="${escapeHtml(relationReviewKey(note))}">${isRelationSaved(note) ? "移出复习" : "加入复习"}</button>
        </div>
      </article>
    `).join("")}</section>`;
  }

  function openDraftCardForNode(node) {
    const detail = {
      sourceLexemeId: node.personal ? "" : node.id,
      lemma: node.word,
      pos: node.pos,
      zhHint: node.gloss || "",
    };
    if (window.WordcloudDraftCards?.openFromWordCard) window.WordcloudDraftCards.openFromWordCard(detail);
    else window.dispatchEvent(new CustomEvent("wordcloud:open-draft-card", { detail }));
  }

  function renderPanel(node) {
    const official = (officialAdj.get(node.id) || [])
      .map((edge) => ({ edge: { ...edge, kind: "official" }, node: nodeById.get(edge.other) }))
      .filter((item) => item.node)
      .sort((a, b) => relationRank(a.edge) - relationRank(b.edge)
        || Number(b.edge.review === "reviewed") - Number(a.edge.review === "reviewed")
        || a.node.word.localeCompare(b.node.word, "fr"));
    const reviewed = official.filter((item) => item.edge.review === "reviewed");
    const sourced = official.filter((item) => item.edge.review !== "reviewed");
    const mine = personalFor(node.id).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const officialIds = new Set(official.map((item) => item.node.id));
    const form = strongFormFor(node.id).filter((edge) => !officialIds.has(edge.other)).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node).slice(0, 8);
    const formIds = new Set(form.map((item) => item.node.id));
    const structural = strongStructuralFor(node.id).filter((edge) => !officialIds.has(edge.other)).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node).slice(0, 16);
    const nearby = (layoutAdj.get(node.id) || []).filter((edge) => !officialIds.has(edge.other) && !formIds.has(edge.other) && !(edge.mask & 2))
      .sort((a, b) => b.weight - a.weight).slice(0, 5).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const badge = node.personal ? "我的词"
      : node.searchOnly ? `${node.level} 可检索学习词`
      : node.status === "eligible" ? `${node.level} 主词表` : "官方关系支撑词";
    const saved = isSaved(node.id);
    const relationCounts = {
      reviewed: reviewed.length,
      sourced: sourced.length,
      mine: mine.length,
      form: form.length,
      structural: structural.length,
    };
    const summary = wordCardTools?.summarizeWordCard({
      senseGroups: GRAPH_SENSES[node.id] || [],
      learning: GRAPH_LEARNING[node.id],
      teachingExamples: teachingExamples[node.id] || [],
      relationCounts,
    }) || {
      senseTotal: 0,
      sensePreview: [],
      collocationPreview: [],
      teachingExamplePreview: [],
      hasLearningCues: false,
      relationTotal: Object.values(relationCounts).reduce((sum, count) => sum + count, 0),
    };
    panelContent.innerHTML = `
      <header class="word-hero">
        <h1 class="word-title">${escapeHtml(node.word)}</h1>
        <div class="word-meta"><span>${escapeHtml(node.pos)}</span><span>${escapeHtml(badge)}</span></div>
        <p class="content-status ${contentStatus[node.id] || "pending_definition"}">${contentStatus[node.id] === "has_definition" ? "词典状态 · 有法语定义" : "词典状态 · 待补定义"}</p>
        <p class="word-gloss"><span>中文提示 · 可能不完整</span>${escapeHtml(node.gloss || "暂无")}</p>
      </header>
      <div class="panel-quick-actions" role="group" aria-label="常用操作">
        <button id="save-word-quick" class="${saved ? "quiet-button" : "primary-button"}" type="button">${saved ? "移出复习" : "加入复习"}</button>
        <button id="draft-word-quick" class="quiet-button" type="button">我的词卡</button>
      </div>
      ${node.note ? `<p class="word-note">${escapeHtml(node.note)}</p>` : ""}
      ${node.searchOnly ? `<section class="search-only-note"><strong>暂未建立学习关系</strong><span>这个词可搜索、查看义项并加入复习；它尚未进入关系图。</span></section>` : ""}
      ${renderSenseSummary(summary)}
      ${renderUsageSummary(summary)}
      ${renderRelationEntry(summary, relationCounts)}
      <div class="learning-actions">
        <section class="learning-action" aria-label="复习设置">
          <div><span class="eyebrow">主动回忆</span><p>${saved ? `已加入学习循环 · ${formatDue(learning.saved[node.id].dueAt)}` : "把这个词留到下一次主动回忆"}</p></div>
          <button id="save-word" class="${saved ? "quiet-button" : "primary-button"}" type="button">${saved ? "移出复习" : "加入复习"}</button>
        </section>
        <section class="learning-action" aria-label="我的词卡">
          <div><span class="eyebrow">我的词卡</span><p>保存自己的中文提示和用法备注</p></div>
          <button id="draft-word" class="quiet-button" type="button">加入 / 打开</button>
        </section>
      </div>
      ${renderSenseGroups(node)}
      ${renderTeachingExamples(node)}
      ${renderEditorialLearning(node)}
      ${reviewed.length ? `<section class="panel-section"><h3>人工审校关系 · ${reviewed.length}</h3><div class="relation-list">${reviewed.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${renderReviewedRelationNotes(reviewed)}
      ${sourced.length ? `<section class="panel-section"><h3>来源确认关系 · ${sourced.length}</h3><div class="relation-list">${sourced.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${mine.length ? `<section class="panel-section"><h3>我的关系 · ${mine.length}</h3><div class="relation-list">${mine.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${form.length ? `<section class="panel-section"><h3>形音线索 · 自动候选</h3><p class="candidate-note">只显示同时形似且音近的少量词，虚线不代表已确认的易混关系。</p><div class="relation-list">${form.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${structural.length ? `<section class="panel-section"><h3>构词线索 · 待核准</h3><p class="candidate-note">来自 Lexique 形态结构，只在图中以蓝色虚线显示，不等同于已审校教学关系。</p><div class="relation-list">${structural.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${nearby.length ? `<details class="panel-section candidate-details"><summary>查看自动候选</summary><p class="candidate-note">这些词只保留为自动候选，不进入中心发散图，也不影响大词网位置。</p><div class="relation-list">${nearby.map(({ edge, node: other }) => relationButton(other, { ...edge, kind: "structural", relation: "syn", label: signals(edge.mask) })).join("")}</div></details>` : ""}
    `;
    panel.classList.remove("hidden");
    panelContent.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => enterFocus(button.dataset.node)));
    panelContent.querySelectorAll("[data-review-relation]").forEach((button) => button.addEventListener("click", (event) => {
      event.stopPropagation();
      const edge = officialEdgeByReviewKey.get(button.dataset.reviewRelation);
      if (!edge) return;
      toggleRelationSaved(edge);
      renderPanel(node);
    }));
    $("#save-word").addEventListener("click", () => { toggleSaved(node.id); renderPanel(node); });
    $("#draft-word").addEventListener("click", () => openDraftCardForNode(node));
    $("#save-word-quick").addEventListener("click", () => { toggleSaved(node.id); renderPanel(node); });
    $("#draft-word-quick").addEventListener("click", () => openDraftCardForNode(node));
  }

  let reviewIndex = 0;
  let reviewRevealed = false;

  function relationExamples(value) {
    if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
    try {
      const parsed = JSON.parse(value || "[]");
      return Array.isArray(parsed) ? parsed.map((item) => String(item || "").trim()).filter(Boolean) : [];
    } catch (_) {
      return [];
    }
  }

  function reviewTrailMarkup(record) {
    const path = Array.isArray(record?.trail)
      ? record.trail.map((id) => nodeById.get(id)?.word || id).filter(Boolean)
      : [];
    return path.length > 1 ? `<small class="review-path">探索路径 · ${escapeHtml(path.join(" › "))}</small>` : "";
  }

  function closeReviewDialog() {
    $("#review-dialog").classList.add("hidden");
  }

  function renderReviewDialog() {
    const entries = dueReviewEntries();
    const content = $("#review-content");
    if (!entries.length) {
      const saved = savedIds().length;
      const relationSaved = relationReviewEntries().length;
      const hasSaved = saved || relationSaved;
      content.innerHTML = `<div class="review-empty"><p>${hasSaved ? "今天的复习已完成。" : "还没有学习词。"}</p><small>${hasSaved ? "到期的词条或关系会自动回到这里。" : "打开一个词条或审校关系后，选择“加入复习”。"}</small></div>`;
      return;
    }
    if (reviewIndex >= entries.length) reviewIndex = 0;
    const entry = entries[reviewIndex];
    const record = entry.record;
    const isRelation = entry.kind === "relation";
    const relationName = isRelation ? (RELATION_NAMES[entry.edge.relation] || entry.edge.relation) : "";
    const title = isRelation
      ? `${entry.left.word} ↔ ${entry.right.word}`
      : entry.node.word;
    const pos = isRelation
      ? `${relationName} · ${entry.left.pos} / ${entry.right.pos}`
      : entry.node.pos;
    const answer = isRelation
      ? `<div class="review-answer relation-review-answer">
          <span>${escapeHtml(relationName)} · 审校说明</span>
          <p><strong>${escapeHtml(entry.edge.label)}</strong></p>
          <p>${escapeHtml(entry.edge.explanation || "暂无说明")}</p>
          ${relationExamples(entry.edge.examples).length ? `<ul class="review-relation-examples">${relationExamples(entry.edge.examples).map((example) => `<li>${escapeHtml(example)}</li>`).join("")}</ul>` : ""}
        </div>`
      : `<div class="review-answer"><span>中文提示</span><p>${escapeHtml(entry.node.gloss || "暂无")}</p>${entry.node.note ? `<p class="review-note">${escapeHtml(entry.node.note)}</p>` : ""}</div>`;
    content.innerHTML = `
      <p class="review-progress">到期 ${entries.length} 个 · 第 ${reviewIndex + 1} 个 · 已复习 ${record.reviews || 0} 次</p>
      <p class="review-prompt">${isRelation ? "先回忆这两个词的区别和使用场景，再显示审校说明。" : "先主动回忆它的意思和用法，再显示提示。"}</p>
      <h3>${escapeHtml(title)}</h3>
      <p class="review-pos">${escapeHtml(pos)}</p>
      ${reviewRevealed ? answer : ""}
      ${reviewRevealed ? reviewTrailMarkup(record) : ""}
      <div class="review-actions">
        ${reviewRevealed ? `<button id="review-again" class="quiet-button" type="button">再复习<br><small>10 分钟</small></button><button id="review-hard" class="quiet-button" type="button">模糊<br><small>1 天</small></button><button id="review-good" class="primary-button" type="button">记住<br><small>递增间隔</small></button><button id="review-easy" class="quiet-button" type="button">很熟<br><small>更长间隔</small></button>` : `<button id="review-reveal" class="primary-button" type="button">显示提示</button>`}
      </div>
    `;
    if (!reviewRevealed) $("#review-reveal").addEventListener("click", () => { reviewRevealed = true; renderReviewDialog(); });
    else {
      ["again", "hard", "good", "easy"].forEach((rating) => $("#review-" + rating).addEventListener("click", () => {
        const scheduled = scheduleReview(record, rating);
        if (isRelation) learning.savedRelations[entry.key] = { ...record, ...scheduled };
        else learning.saved[entry.key] = { ...record, ...scheduled };
        saveLearning();
        updateReviewCount();
        refreshLearningProgress();
        reviewIndex = 0;
        reviewRevealed = false;
        renderReviewDialog();
      }));
    }
  }

  function openReviewDialog() {
    reviewIndex = 0;
    reviewRevealed = false;
    renderReviewDialog();
    $("#review-dialog").classList.remove("hidden");
    const firstAction = $("#review-content button");
    if (firstAction) firstAction.focus();
  }

  function closeLocalDataDialog() {
    $("#local-data-dialog").classList.add("hidden");
  }

  function renderLocalDataNotice(messages = []) {
    const notice = $("#local-data-notice");
    const allMessages = [...new Set(localStorageWarnings.concat(messages).filter(Boolean))];
    if (!allMessages.length) {
      notice.classList.add("hidden");
      notice.innerHTML = "";
      return;
    }
    notice.innerHTML = allMessages.map((message) => `<p>${escapeHtml(message)}</p>`).join("");
    notice.classList.remove("hidden");
  }

  function openLocalDataDialog() {
    $("#local-data-dialog").classList.remove("hidden");
    renderLocalDataNotice();
    $("#local-data-export").focus();
  }

  function exportLocalData() {
    const output = $("#local-data-output");
    if (!localDataTools) {
      output.value = "";
      renderLocalDataNotice(["本地数据导出正在准备，请再试一次。"]);
      return;
    }
    const exported = localDataTools.exportLocalLearningData(localStorage);
    renderLocalDataNotice(exported.errors);
    output.value = JSON.stringify(exported, null, 2);
  }

  function learningWordMeta() {
    return Object.fromEntries([...nodeById.values()].map((node) => [String(node.id), {
      label: node.word,
      word: node.word,
      pos: node.pos,
      level: node.level,
    }]));
  }

  function learningPathLabel(path) {
    return (Array.isArray(path) ? path : [])
      .map((id) => nodeById.get(String(id))?.word || String(id))
      .join(" › ");
  }

  function progressStatusLabel(status) {
    return { due: "已到期", upcoming: "即将到期", scheduled: "已安排" }[status] || "未安排";
  }

  function progressDate(value) {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp) || timestamp <= 0) return "时间未知";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp));
  }

  function renderProgressCategoryList(categories, kind) {
    const entries = Object.entries(categories || {}).sort(([a, left], [b, right]) => (
      right.items - left.items
      || right.completedReviews - left.completedReviews
      || a.localeCompare(b, "zh")
    ));
    if (!entries.length) return `<p class="learning-progress-empty">还没有${kind === "word" ? "词条" : "关系"}复习记录。</p>`;
    return `<ul>${entries.map(([key, value]) => `
      <li class="learning-progress-item">
        <strong>${escapeHtml(kind === "relation" ? (RELATION_NAMES[key] || key) : key)}</strong>
        <span>${value.items} 项 · 已完成 ${value.completedReviews} 次 · 到期 ${value.due} · 7 天内 ${value.upcoming}</span>
      </li>
    `).join("")}</ul>`;
  }

  function renderProgressSummary(progress) {
    const totals = progress.totals;
    return [
      ["累计完成", `${totals.completedReviews} 次`, "所有已保存复习记录的累计反馈"],
      ["已加入", `${totals.saved} 项`, `词条 ${totals.words} · 关系 ${totals.relations}`],
      ["到期", `${totals.due} 项`, "现在可以复习"],
      ["7 天内到期", `${totals.upcoming} 项`, "已安排但即将回到复习队列"],
    ].map(([label, value, note]) => `
      <article class="learning-progress-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        <small>${escapeHtml(note)}</small>
      </article>
    `).join("");
  }

  function renderRecentProgress(progress) {
    if (!progress.recent.length) return '<p class="learning-progress-empty">还没有完成过复习。</p>';
    return `<ul>${progress.recent.map((item) => `
      <li class="learning-progress-item">
        <strong>${escapeHtml(item.label)}</strong>
        <span>${item.kind === "relation" ? "关系" : "词条"} · ${escapeHtml(REVIEW_RATING_LABELS[item.rating] || "未记录反馈")} · ${escapeHtml(progressStatusLabel(item.status))}</span>
        <small>最近 ${escapeHtml(progressDate(item.reviewedAt))} · 累计 ${item.reviews} 次 · ${escapeHtml(formatDue(item.dueAt, progress.asOf))}</small>
      </li>
    `).join("")}</ul>`;
  }

  function renderPathProgress(progress) {
    if (!progress.paths.length) return '<p class="learning-progress-empty">完成一次探索并加入复习后，这里会显示路径进展。</p>';
    return `<ul>${progress.paths.map((path) => {
      const label = path.path.length ? learningPathLabel(path.path) : "未记录探索路径";
      const latest = path.lastReviewedAt ? ` · 最近 ${progressDate(path.lastReviewedAt)}` : "";
      return `<li class="learning-progress-item">
        <strong>${escapeHtml(label)}</strong>
        <span>${path.items} 项 · 已完成 ${path.completedReviews} 次 · 到期 ${path.due} · 7 天内 ${path.upcoming}</span>
        <small>${path.reviewedItems} 项有复习反馈${escapeHtml(latest)}</small>
      </li>`;
    }).join("")}</ul>`;
  }

  function renderLearningProgress() {
    const summary = $("#learning-progress-summary");
    const notice = $("#learning-progress-notice");
    if (!localDataTools?.summarizeLearningProgress) {
      summary.innerHTML = '<p class="learning-progress-empty">学习进度正在准备，请稍后再打开。</p>';
      notice.textContent = "本地统计工具尚未加载。";
      notice.classList.remove("hidden");
      return;
    }
    const progress = localDataTools.summarizeLearningProgress(learning, {
      now: Date.now(),
      upcomingDays: PROGRESS_UPCOMING_DAYS,
      wordMeta: learningWordMeta(),
      recentLimit: 12,
    });
    const messages = localStorageWarnings.filter(Boolean);
    notice.innerHTML = messages.map((message) => `<p>${escapeHtml(message)}</p>`).join("");
    notice.classList.toggle("hidden", messages.length === 0);
    summary.innerHTML = renderProgressSummary(progress);
    $("#learning-word-categories").innerHTML = renderProgressCategoryList(progress.categories.words, "word");
    $("#learning-relation-categories").innerHTML = renderProgressCategoryList(progress.categories.relations, "relation");
    $("#learning-recent").innerHTML = renderRecentProgress(progress);
    $("#learning-paths").innerHTML = renderPathProgress(progress);
  }

  function openLearningProgressDialog() {
    renderLearningProgress();
    $("#learning-progress-dialog").classList.remove("hidden");
    $("#learning-progress-close").focus();
  }

  function closeLearningProgressDialog() {
    $("#learning-progress-dialog").classList.add("hidden");
  }

  function renderTrail() {
    trailEl.innerHTML = trail.map((id, index) => {
      const node = nodeById.get(id);
      return `${index ? '<span class="trail-sep">›</span>' : ""}<button class="trail-chip${id === selected ? " current" : ""}" data-id="${escapeHtml(id)}">${escapeHtml(node?.word || id)}</button>`;
    }).join("");
    trailEl.querySelectorAll("[data-id]").forEach((button) => button.addEventListener("click", () => {
      const index = trail.indexOf(button.dataset.id);
      if (index >= 0) trail = trail.slice(0, index + 1);
      enterFocus(button.dataset.id, { addTrail: false });
    }));
  }

  function updateStats() {
    if (!selected) {
      const wordTotal = GRAPH_META.eligible_count + GRAPH_META.support_node_count;
      $("#stats").textContent = `收录 ${wordTotal.toLocaleString()} 个词 · ${GRAPH_META.edge_count.toLocaleString()} 条词汇关系`;
      return;
    }
    const officialCount = focusConnections
      .filter((edge) => edge.kind === "official")
      .reduce((total, edge) => total + (edge.relations?.length || 1), 0);
    const structuralCount = focusConnections.filter((edge) => edge.kind === "structural").length;
    const formCount = focusConnections.filter((edge) => edge.kind === "form").length;
    $("#stats").textContent = `${focusConnections.length} 个相关词 · ${officialCount} 条正式关系 · ${formCount + structuralCount} 自动线索`;
  }

  function showTooltip(node, event) {
    if (!node || selected && ["center", "direct"].includes(node.focusRole)) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = `<strong>${escapeHtml(node.word)}</strong><span>${escapeHtml(node.gloss || node.pos)}</span>`;
    tooltip.style.left = `${Math.min(window.innerWidth - 230, event.clientX + 13)}px`;
    tooltip.style.top = `${Math.min(window.innerHeight - 70, event.clientY + 13)}px`;
    tooltip.classList.remove("hidden");
  }

  function clampScale(scale) {
    return Math.max(homeView.scale * .62, Math.min(7, scale));
  }

  function beginPinch() {
    const points = [...activePointers.values()].slice(0, 2);
    if (points.length < 2) return;
    const centerX = (points[0].x + points[1].x) / 2;
    const centerY = (points[0].y + points[1].y) / 2;
    pinchStart = {
      distance: Math.max(1, Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)),
      scale: view.scale,
      world: worldAt(centerX, centerY),
    };
    dragging = false;
    moved = true;
    viewTween = null;
  }

  canvas.addEventListener("pointerdown", (event) => {
    activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
    if (activePointers.size >= 2) {
      beginPinch();
      return;
    }
    dragging = true;
    moved = false;
    dragStart = { clientX: event.clientX, clientY: event.clientY, x: view.x, y: view.y };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (activePointers.has(event.pointerId)) activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pinchStart && activePointers.size >= 2) {
      const points = [...activePointers.values()].slice(0, 2);
      const centerX = (points[0].x + points[1].x) / 2;
      const centerY = (points[0].y + points[1].y) / 2;
      const distance = Math.max(1, Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y));
      const rect = canvas.getBoundingClientRect();
      view.scale = clampScale(pinchStart.scale * distance / pinchStart.distance);
      view.x = pinchStart.world.x - (centerX - rect.left - width / 2) / view.scale;
      view.y = pinchStart.world.y - (centerY - rect.top - height / 2) / view.scale;
      requestDraw();
      return;
    }
    if (dragging) {
      const dx = event.clientX - dragStart.clientX, dy = event.clientY - dragStart.clientY;
      if (Math.hypot(dx, dy) > 3) moved = true;
      view.x = dragStart.x - dx / view.scale; view.y = dragStart.y - dy / view.scale; viewTween = null; requestDraw();
      return;
    }
    const hit = hitTest(event.clientX, event.clientY);
    const next = hit ? hit.id : null;
    if (next !== hovered) { hovered = next; requestDraw(); }
    canvas.style.cursor = hit ? "pointer" : "grab";
    showTooltip(hit, event);
  });
  canvas.addEventListener("pointerup", (event) => {
    const wasPinching = Boolean(pinchStart) || activePointers.size > 1;
    activePointers.delete(event.pointerId);
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (wasPinching) {
      pinchStart = null;
      dragging = false;
      moved = true;
      if (!activePointers.size) canvas.classList.remove("dragging");
      return;
    }
    if (!dragging) {
      if (!activePointers.size) canvas.classList.remove("dragging");
      return;
    }
    dragging = false; canvas.classList.remove("dragging");
    if (!moved) {
      const hit = hitTest(event.clientX, event.clientY);
      if (!hit && selected) fitHome();
      else if (hit?.focusRole === "background") enterFocus(hit.id, { resetTrail: true });
      else if (hit) enterFocus(hit.id);
    }
  });
  canvas.addEventListener("pointercancel", (event) => {
    activePointers.delete(event.pointerId);
    pinchStart = null;
    dragging = false;
    moved = true;
    canvas.classList.remove("dragging");
  });
  canvas.addEventListener("pointerleave", () => { if (!dragging) { hovered = null; tooltip.classList.add("hidden"); requestDraw(); } });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const before = worldAt(event.clientX, event.clientY);
    view.scale = clampScale(view.scale * Math.exp(-event.deltaY * .00125));
    const after = worldAt(event.clientX, event.clientY);
    view.x += before.x - after.x; view.y += before.y - after.y; viewTween = null;
    requestDraw();
  }, { passive: false });

  function doSearch() {
    const query = searchTools?.normalizeSearchText(search.value) || search.value.trim();
    $("#map-copy").classList.toggle("quiet", Boolean(query));
    if (!query) { searchResults.classList.add("hidden"); return; }
    if (!searchTools) {
      searchResults.innerHTML = `<div class="search-result"><small>搜索正在准备，请再试一次。</small></div>`;
      searchResults.classList.remove("hidden");
      return;
    }
    const entries = allNodes.concat(searchOnlyNodes).map((node) => ({
      id: node.id,
      word: node.word,
      pos: node.pos,
      gloss: node.gloss,
      level: node.level,
      freq: node.freq,
      personal: node.personal,
      searchOnly: node.searchOnly,
      isCore: foundationalCoreIds.has(node.id),
      aliases: aliasesById[node.id] || [],
    }));
    const searchState = searchTools.searchLexemes(entries, query, { limit: 12, suggestionLimit: 5 });
    const renderResult = (result, suggestion = false) => {
      const node = nodeById.get(result.entry.id);
      const alias = result.matchType.includes("Alias") ? `词形匹配：${result.matchedText} → ${node.word}` : "";
      const hint = suggestion ? `相近拼写：${result.matchedText}` : alias;
      return `<button class="search-result" data-node="${escapeHtml(node.id)}" role="option"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml([node.gloss || (node.personal ? "我的词" : node.level), hint, node.searchOnly ? "可检索词" : ""].filter(Boolean).join(" · "))}</small></button>`;
    };
    if (searchState.results.length) {
      searchResults.innerHTML = searchState.results.map((result) => renderResult(result)).join("");
    } else if (searchState.suggestions.length) {
      searchResults.innerHTML = `<div class="search-result search-empty"><small>没有精确匹配。你是不是想找：</small></div>${searchState.suggestions.map((result) => renderResult(result, true)).join("")}`;
    } else {
      searchResults.innerHTML = `<div class="search-result search-empty"><small>没有找到这个词。可以检查拼写，或用右下角的 + 加入自己的词网。</small></div>`;
    }
    searchResults.classList.remove("hidden");
    searchResults.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => openSearchResult(button.dataset.node)));
  }
  function openSearchResult(id) {
    const node = nodeById.get(String(id));
    if (node?.searchOnly) {
      searchResults.classList.add("hidden");
      search.blur();
      renderPanel(node);
      viewport.classList.add("panel-open");
      return;
    }
    enterFocus(id, { resetTrail: true });
  }
  search.addEventListener("input", doSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { const first = searchResults.querySelector("[data-node]"); if (first) openSearchResult(first.dataset.node); }
    if (event.key === "Escape") searchResults.classList.add("hidden");
  });

  document.querySelectorAll("[data-example-word]").forEach((button) => button.addEventListener("click", () => {
    const word = button.dataset.exampleWord;
    const match = allNodes.concat(searchOnlyNodes).find((node) => node.word === word && node.pos === "VER");
    if (!match) return;
    button.classList.add("example-chip-active");
    setTimeout(() => button.classList.remove("example-chip-active"), 480);
    search.value = match.word;
    openSearchResult(match.id);
  }));

  $("#panel-close").addEventListener("click", () => {
    panel.classList.add("hidden");
    viewport.classList.remove("panel-open");
    if (selected && focusCenter) animateView(focusViewTarget(focusCenter, focusScaleFor(focusConnections.length), false), 320);
  });
  $("#reset").addEventListener("click", () => fitHome());
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); fitHome(); });
  $("#focus-back").addEventListener("click", () => fitHome());
  $("#local-data-open").addEventListener("click", openLocalDataDialog);
  $("#local-data-close").addEventListener("click", closeLocalDataDialog);
  $("#local-data-mask").addEventListener("click", closeLocalDataDialog);
  $("#local-data-export").addEventListener("click", exportLocalData);
  $("#learning-progress-open").addEventListener("click", openLearningProgressDialog);
  $("#learning-progress-close").addEventListener("click", closeLearningProgressDialog);
  $("#learning-progress-mask").addEventListener("click", closeLearningProgressDialog);
  $("#review-open").addEventListener("click", openReviewDialog);
  $("#review-close").addEventListener("click", closeReviewDialog);
  $("#review-mask").addEventListener("click", closeReviewDialog);
  function toggleLegendBody() {
    const body = $("#legend-body");
    const expanded = body.classList.contains("hidden");
    body.classList.toggle("hidden");
    $("#legend").classList.toggle("mobile-legend-open", expanded);
    $("#legend-toggle").setAttribute("aria-expanded", String(expanded));
    $("#legend-open-mobile").setAttribute("aria-expanded", String(expanded));
  }
  $("#legend-toggle").addEventListener("click", toggleLegendBody);
  $("#legend-open-mobile").addEventListener("click", toggleLegendBody);
  $("#legend-relations").innerHTML = RELATION_ORDER
    .filter((key) => key !== "personal")
    .map((key) => `<span><i style="--c:${RELATION_STYLE[key].color}"></i>${escapeHtml(RELATION_NAMES[key] || key)}</span>`)
    .join("") + `<small>细虚线 = 自动候选 · 橙虚线 = 我的关系</small>`;

  function closeDialog() { $("#add-dialog").classList.add("hidden"); $("#add-error").textContent = ""; }
  $("#add-open").addEventListener("click", () => { $("#add-dialog").classList.remove("hidden"); $("#add-word").focus(); });
  $("#add-cancel").addEventListener("click", closeDialog);
  $("#add-mask").addEventListener("click", closeDialog);
  $("#add-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const word = $("#add-word").value.trim();
    const gloss = $("#add-gloss").value.trim();
    const targetWord = $("#add-target").value.trim().toLocaleLowerCase("fr");
    const relation = $("#add-relation").value.trim();
    const duplicate = allNodes.find((node) => node.word.toLocaleLowerCase("fr") === word.toLocaleLowerCase("fr"));
    if (duplicate) { $("#add-error").textContent = "这个词已经在图里了；你可以直接搜索并打开它。"; return; }
    const target = targetWord ? allNodes.find((node) => node.word.toLocaleLowerCase("fr") === targetWord) : null;
    if (targetWord && !target) { $("#add-error").textContent = "没有找到要连接的词，请输入完整词形。"; return; }
    const center = target || { x: view.x, y: view.y };
    const angle = (personal.nodes.length * 2.399963 + .6) % (Math.PI * 2);
    const id = `mine-${Date.now()}`;
    const newNode = { id, word, pos: "我的词", gloss, note: relation, x: center.x + Math.cos(angle) * 34, y: center.y + Math.sin(angle) * 34, size: 3.4 };
    personal.nodes.push(newNode);
    if (target) personal.edges.push({ a: id, b: target.id, label: relation || "我的联想" });
    savePersonal(); rebuildPersonal(); closeDialog(); event.currentTarget.reset(); enterFocus(id);
  });

  window.addEventListener("resize", resize);
  updateReviewCount();
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").catch(() => {}));
  }
  resize();
})();
