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
  const PERSONAL_KEY = "maillage.personal.v2";
  const LEARNING_KEY = "maillage.learning.v1";
  const MINUTE = 60 * 1000;
  const DAY = 24 * 60 * MINUTE;
  const MOBILE_BREAKPOINT = 720;
  const CANVAS_FONT = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  const CANVAS_PIXEL_BUDGET = { mobile: 3600000, desktop: 9000000 };

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
  const nodeById = new Map(officialNodes.map((node) => [node.id, node]));
  for (const node of searchOnlyNodes) nodeById.set(node.id, node);
  const baseLinks = GRAPH_LINKS.map((row) => ({ a: String(row[0]), b: String(row[1]), mask: row[2], weight: row[3] }));
  const officialEdges = GRAPH_OFFICIAL_EDGES.map((row) => ({
    a: String(row[0]), b: String(row[1]), relation: row[2], dimension: row[3], subtype: row[4], direction: row[5],
    label: row[6], explanation: row[7], examples: row[8], confidence: row[9], review: row[10], kind: "official",
  }));
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

  let personal = loadPersonal();
  let learning = loadLearning();
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

  function loadPersonal() {
    try {
      const value = JSON.parse(localStorage.getItem(PERSONAL_KEY) || "{}");
      return { nodes: Array.isArray(value.nodes) ? value.nodes : [], edges: Array.isArray(value.edges) ? value.edges : [] };
    } catch (_) {
      return { nodes: [], edges: [] };
    }
  }

  function savePersonal() {
    localStorage.setItem(PERSONAL_KEY, JSON.stringify(personal));
  }

  function loadLearning() {
    try {
      const value = JSON.parse(localStorage.getItem(LEARNING_KEY) || "{}");
      const saved = value.saved && typeof value.saved === "object" ? value.saved : {};
      const now = Date.now();
      return {
        saved: Object.fromEntries(Object.entries(saved).map(([id, record]) => [id, normalizeLearningRecord(record, now)])),
      };
    } catch (_) {
      return { saved: {} };
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
      lastRating: typeof raw.lastRating === "string" ? raw.lastRating : null,
    };
  }

  function saveLearning() {
    localStorage.setItem(LEARNING_KEY, JSON.stringify(learning));
  }

  function savedIds() {
    return Object.keys(learning.saved).filter((id) => nodeById.has(id));
  }

  function dueIds(now = Date.now()) {
    return savedIds().filter((id) => learning.saved[id].dueAt <= now)
      .sort((a, b) => learning.saved[a].dueAt - learning.saved[b].dueAt || learning.saved[a].addedAt - learning.saved[b].addedAt);
  }

  function isSaved(id) {
    return Boolean(learning.saved[String(id)]);
  }

  function updateReviewCount() {
    const due = dueIds().length;
    $("#review-count").textContent = due;
    $("#review-open").setAttribute("aria-label", due ? `开始 ${due} 个到期复习` : "查看复习队列");
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
    next.lastRating = rating;
    return next;
  }

  function toggleSaved(id) {
    const key = String(id);
    if (isSaved(key)) delete learning.saved[key];
    else learning.saved[key] = normalizeLearningRecord({}, Date.now());
    saveLearning();
    updateReviewCount();
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
    if (!groups.length) return "";
    const flattened = groups.flatMap((group, groupIndex) => group.senses.map((sense) => ({ ...sense, groupIndex, sourceUrl: group.sourceUrl })));
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

  function renderContrastNotes(items) {
    const contrasts = items.filter(({ edge }) => edge.relation === "compare" && edge.explanation);
    if (!contrasts.length) return "";
    return `<section class="panel-section contrast-section"><h3>用法区分</h3>${contrasts.map(({ edge, node: other }) => `
      <article class="contrast-note">
        <p><strong>${escapeHtml(other.word)}</strong> · ${escapeHtml(edge.label)}</p>
        <p class="contrast-explanation">${escapeHtml(edge.explanation)}</p>
        ${edge.examples ? `<ul class="contrast-examples">${JSON.parse(edge.examples || "[]").map((example) => `<li>${escapeHtml(example)}</li>`).join("")}</ul>` : ""}
      </article>
    `).join("")}</section>`;
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
    panelContent.innerHTML = `
      <h1 class="word-title">${escapeHtml(node.word)}</h1>
      <div class="word-meta"><span>${escapeHtml(node.pos)}</span><span>${escapeHtml(badge)}</span></div>
      <p class="content-status ${contentStatus[node.id] || "pending_definition"}">${contentStatus[node.id] === "has_definition" ? "词典状态 · 有法语定义" : "词典状态 · 待补定义"}</p>
      <p class="word-gloss"><span>中文提示 · 可能不完整</span>${escapeHtml(node.gloss || "暂无")}</p>
      ${node.note ? `<p class="word-note">${escapeHtml(node.note)}</p>` : ""}
      ${node.searchOnly ? `<section class="search-only-note"><strong>暂未建立学习关系</strong><span>这个词可搜索、查看义项并加入复习；它尚未进入关系图。</span></section>` : ""}
      <section class="learning-action" aria-label="复习设置">
        <div><span class="eyebrow">主动回忆</span><p>${saved ? `已加入学习循环 · ${formatDue(learning.saved[node.id].dueAt)}` : "把这个词留到下一次主动回忆"}</p></div>
        <button id="save-word" class="${saved ? "quiet-button" : "primary-button"}" type="button">${saved ? "移出复习" : "加入复习"}</button>
      </section>
      ${renderSenseGroups(node)}
      ${renderTeachingExamples(node)}
      ${renderEditorialLearning(node)}
      ${reviewed.length ? `<section class="panel-section"><h3>人工审校关系 · ${reviewed.length}</h3><div class="relation-list">${reviewed.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${renderContrastNotes(reviewed)}
      ${sourced.length ? `<section class="panel-section"><h3>来源确认关系 · ${sourced.length}</h3><div class="relation-list">${sourced.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${mine.length ? `<section class="panel-section"><h3>我的关系 · ${mine.length}</h3><div class="relation-list">${mine.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${form.length ? `<section class="panel-section"><h3>形音线索 · 自动候选</h3><p class="candidate-note">只显示同时形似且音近的少量词，虚线不代表已确认的易混关系。</p><div class="relation-list">${form.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${structural.length ? `<section class="panel-section"><h3>构词线索 · 待核准</h3><p class="candidate-note">来自 Lexique 形态结构，只在图中以蓝色虚线显示，不等同于已审校教学关系。</p><div class="relation-list">${structural.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${nearby.length ? `<details class="panel-section candidate-details"><summary>查看自动候选</summary><p class="candidate-note">这些词只保留为自动候选，不进入中心发散图，也不影响大词网位置。</p><div class="relation-list">${nearby.map(({ edge, node: other }) => relationButton(other, { ...edge, kind: "structural", relation: "syn", label: signals(edge.mask) })).join("")}</div></details>` : ""}
    `;
    panel.classList.remove("hidden");
    panelContent.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => enterFocus(button.dataset.node)));
    $("#save-word").addEventListener("click", () => { toggleSaved(node.id); renderPanel(node); });
  }

  let reviewIndex = 0;
  let reviewRevealed = false;

  function reviewNodes() {
    return dueIds()
      .map((id) => nodeById.get(id))
      .filter(Boolean);
  }

  function closeReviewDialog() {
    $("#review-dialog").classList.add("hidden");
  }

  function renderReviewDialog() {
    const nodes = reviewNodes();
    const content = $("#review-content");
    if (!nodes.length) {
      const saved = savedIds().length;
      content.innerHTML = `<div class="review-empty"><p>${saved ? "今天的复习已完成。" : "还没有学习词。"}</p><small>${saved ? "到期的词会自动回到这里。" : "打开一个词条后，选择“加入复习”。"}</small></div>`;
      return;
    }
    if (reviewIndex >= nodes.length) reviewIndex = 0;
    const node = nodes[reviewIndex];
    const record = learning.saved[node.id];
    content.innerHTML = `
      <p class="review-progress">今日到期 ${nodes.length} 个 · 第 ${reviewIndex + 1} 个 · 已复习 ${record.reviews || 0} 次</p>
      <p class="review-prompt">先主动回忆它的意思和用法，再显示提示。</p>
      <h3>${escapeHtml(node.word)}</h3>
      <p class="review-pos">${escapeHtml(node.pos)}</p>
      ${reviewRevealed ? `<div class="review-answer"><span>中文提示</span><p>${escapeHtml(node.gloss || "暂无")}</p></div>` : ""}
      <div class="review-actions">
        ${reviewRevealed ? `<button id="review-again" class="quiet-button" type="button">不记得<br><small>10 分钟</small></button><button id="review-hard" class="quiet-button" type="button">模糊<br><small>1 天</small></button><button id="review-good" class="primary-button" type="button">记得<br><small>递增间隔</small></button><button id="review-easy" class="quiet-button" type="button">很熟<br><small>更长间隔</small></button>` : `<button id="review-reveal" class="primary-button" type="button">显示提示</button>`}
      </div>
    `;
    if (!reviewRevealed) $("#review-reveal").addEventListener("click", () => { reviewRevealed = true; renderReviewDialog(); });
    else {
      ["again", "hard", "good", "easy"].forEach((rating) => $("#review-" + rating).addEventListener("click", () => {
        learning.saved[node.id] = scheduleReview(record, rating);
        saveLearning();
        updateReviewCount();
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
      $("#stats").textContent = `${GRAPH_META.eligible_count.toLocaleString()} 主词 · ${GRAPH_META.support_node_count} 支撑词 · ${GRAPH_META.edge_count.toLocaleString()} 词群线索`;
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
    const query = search.value.trim().toLocaleLowerCase("fr");
    if (!query) { searchResults.classList.add("hidden"); return; }
    const starts = [], contains = [];
    for (const node of allNodes.concat(searchOnlyNodes)) {
      const word = node.word.toLocaleLowerCase("fr");
      const aliases = (aliasesById[node.id] || []).map((alias) => alias.toLocaleLowerCase("fr"));
      const matchesStart = word.startsWith(query) || aliases.some((alias) => alias.startsWith(query));
      const matchesContains = word.includes(query) || aliases.some((alias) => alias.includes(query));
      if (matchesStart) starts.push(node); else if (matchesContains) contains.push(node);
      if (starts.length + contains.length > 40) break;
    }
    const results = starts.concat(contains).sort((a, b) => {
      const aExact = a.word.toLocaleLowerCase("fr") === query;
      const bExact = b.word.toLocaleLowerCase("fr") === query;
      if (aExact !== bExact) return Number(bExact) - Number(aExact);
      const aCore = aExact && foundationalCoreIds.has(a.id);
      const bCore = bExact && foundationalCoreIds.has(b.id);
      if (aCore !== bCore) return Number(bCore) - Number(aCore);
      return b.freq - a.freq || a.pos.localeCompare(b.pos, "fr");
    }).slice(0, 12);
    searchResults.innerHTML = results.length ? results.map((node) => `<button class="search-result" data-node="${escapeHtml(node.id)}" role="option"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml(node.gloss || (node.personal ? "我的词" : node.level))}${node.searchOnly ? " · 可检索词" : ""}</small></button>`).join("") : `<div class="search-result"><small>没有找到；你可以用右下角的 + 添加它。</small></div>`;
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

  $("#panel-close").addEventListener("click", () => {
    panel.classList.add("hidden");
    viewport.classList.remove("panel-open");
    if (selected && focusCenter) animateView(focusViewTarget(focusCenter, focusScaleFor(focusConnections.length), false), 320);
  });
  $("#reset").addEventListener("click", () => fitHome());
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); fitHome(); });
  $("#focus-back").addEventListener("click", () => fitHome());
  $("#review-open").addEventListener("click", openReviewDialog);
  $("#review-close").addEventListener("click", closeReviewDialog);
  $("#review-mask").addEventListener("click", closeReviewDialog);
  $("#legend-toggle").addEventListener("click", (event) => {
    const body = $("#legend-body"); body.classList.toggle("hidden"); event.currentTarget.setAttribute("aria-expanded", String(!body.classList.contains("hidden")));
  });

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
