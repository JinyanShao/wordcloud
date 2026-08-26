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
  const MOBILE_BREAKPOINT = 720;
  const CANVAS_FONT = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  const CANVAS_PIXEL_BUDGET = { mobile: 3600000, desktop: 9000000 };

  const SIGNALS = [[1, "释义接近"], [2, "来源确认的派生"], [4, "拼写相似"], [8, "读音相似"], [16, "编辑关系"], [32, "连通骨架"], [64, "Lexique 词形候选"]];
  // Public relations use the formal word-family model; old build artifacts
  // are normalized through LEGACY_RELATION during load.
  const RELATION_NAMES = {
    synonym: "近义", antonym: "反义", compare: "对比", trap: "易混",
    derivation: "构词", conversion_or_lexicalization: "转类", etymological_family: "词源",
  };
  const RELATION_ORDER = ["synonym", "antonym", "compare", "trap", "derivation", "conversion_or_lexicalization", "etymological_family", "personal"];
  const FOCUS_LIMITS = { synonym: 5, antonym: 4, compare: 3, trap: 3, derivation: 6, conversion_or_lexicalization: 4, etymological_family: 4, personal: 3 };
  const RELATION_STYLE = {
    synonym: { color: "#7b8188", dash: [], arrow: false },
    compare: { color: "#c07a22", dash: [], arrow: true },
    derivation: { color: "#3477b8", dash: [], arrow: false },
    conversion_or_lexicalization: { color: "#3477b8", dash: [4, 4], arrow: false },
    etymological_family: { color: "#3477b8", dash: [2, 5], arrow: false },
    trap: { color: "#c7465d", dash: [], arrow: false },
    antonym: { color: "#278867", dash: [], arrow: false },
    personal: { color: "#b96d22", dash: [2, 5], arrow: false },
  };
  const LEGACY_RELATION = { syn: "synonym", ant: "antonym", fam: "derivation", drift: "derivation" };
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
  const aliasesById = GRAPH_ALIASES || {};
  let searchTools = null;
  let wordCardTools = null;
  let localDataTools = null;
  const nodeById = new Map(officialNodes.map((node) => [node.id, node]));
  for (const node of searchOnlyNodes) nodeById.set(node.id, node);
  const baseLinks = GRAPH_LINKS.map((row) => ({ a: String(row[0]), b: String(row[1]), mask: row[2], weight: row[3] }));
  const officialEdges = GRAPH_OFFICIAL_EDGES.map((row) => ({
    a: String(row[0]), b: String(row[1]), relation: LEGACY_RELATION[row[2]] || row[2], dimension: row[3], subtype: row[4], direction: row[5],
    label: row[6], explanation: row[7], examples: row[8], confidence: row[9], review: row[10], kind: "official",
    keySenseA: row[11] || "", keySenseB: row[12] || "",
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
  }).catch(() => {});

  let personal = { nodes: [], edges: [] };
  let personalNodes = [];
  let personalEdges = [];
  let allNodes = [];
  let searchEntriesCache = null;
  let selected = null;
  let hovered = null;
  let focusConnections = [];
  let focusEdges = [];
  let focusStarted = 0;
  let trail = [];
  let onboardingTimer = null;
  let onboardingHighlight = null;
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
    searchEntriesCache = null;
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
    if (selected) enterFocus(selected, { addTrail: false });
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
    trail = [];
    search.value = "";
    searchResults.innerHTML = "";
    searchResults.classList.add("hidden");
    panelContent.innerHTML = "";
    tooltip.classList.add("hidden");
    search.blur();
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
    $("#reset").textContent = "重置视图";
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
        ...edge, a: id, b: edge.other, other: edge.other, relation: "derivation", label: "构词线索", kind: "structural", review: "candidate",
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
    const familyRelations = new Set(["derivation", "conversion_or_lexicalization", "etymological_family"]);
    const familyQueue = [id];
    const familySeen = new Set([id]);
    for (let index = 0; index < familyQueue.length && familySeen.size < 80; index += 1) {
      for (const edge of officialAdj.get(familyQueue[index]) || []) {
        if (!familyRelations.has(edge.relation) || familySeen.has(edge.other)) continue;
        familySeen.add(edge.other);
        familyQueue.push(edge.other);
      }
    }
    for (const edge of officialAdj.get(id) || []) {
      if (!officialByNeighbor.has(edge.other)) officialByNeighbor.set(edge.other, []);
      officialByNeighbor.get(edge.other).push({ ...edge, kind: "official" });
    }
    for (const member of familySeen) {
      if (member === id) continue;
      const edge = (officialAdj.get(id) || []).find((item) => item.other === member)
        || { a: id, b: member, other: member, relation: "etymological_family", label: "同一词族", explanation: "", examples: "[]", review: "reviewed" };
      if (!officialByNeighbor.has(member)) officialByNeighbor.set(member, []);
      officialByNeighbor.get(member).push({ ...edge, kind: "official" });
    }
    for (const [other, relations] of officialByNeighbor) {
      relations.sort((a, b) => relationRank(a) - relationRank(b) || Number(b.review === "reviewed") - Number(a.review === "reviewed"));
      byNeighbor.set(other, { ...relations[0], relations });
    }
    // Only reviewed relations and the learner's own personal links are shown
    // in the focus graph. Auto-generated form/structural candidates are
    // layout-only signal, never confirmed language fact, so they stay out of
    // the graph entirely and surface (collapsed) in the word panel instead.
    const candidates = personalFor(id);
    const priority = { official: 4, personal: 3 };
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
      const relationLimit = edge.kind === "official" ? (FOCUS_LIMITS[edge.relation] || 3) : 3;
      if ((counts.get(key) || 0) >= relationLimit) continue;
      counts.set(key, (counts.get(key) || 0) + 1);
      selected.push(edge);
      if (selected.length >= limit) break;
    }
    return selected;
  }

  // The circular map stays the single source of truth for node position --
  // a focused word and its reviewed relations are highlighted in place
  // rather than re-laid-out into an isolated ring, so this only has to pick
  // a view (pan/zoom) that frames the highlighted set on the real map.
  function focusViewForIds(ids, panelVisible = true) {
    const points = ids.map((value) => nodeById.get(value)).filter(Boolean);
    if (!points.length) return { ...homeView };
    const xs = points.map((node) => node.homeX), ys = points.map((node) => node.homeY);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const spanX = Math.max(24, maxX - minX), spanY = Math.max(24, maxY - minY);
    const padding = isMobileLayout() ? 120 : 200;
    const fitScale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
    const scale = Math.max(homeView.scale * .55, Math.min(fitScale, homeView.scale * 6, 3.4));
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    const xShift = width > 900 ? 135 / scale : 0;
    const yShift = isMobileLayout() && panelVisible ? height * .2 / scale : 0;
    return { x: cx + xShift, y: cy + yShift, scale };
  }

  function enterFocus(id, options = {}) {
    const node = nodeById.get(String(id));
    if (!node) return;
    stopOnboarding();
    if (options.resetTrail) trail = [];
    selected = node.id;
    focusConnections = connectionsFor(node.id, isMobileLayout() ? 8 : 16);

    // Highlight in place on the real map rather than re-laying-out into an
    // isolated ring: every node keeps its true circular-map position, the
    // whole map stays visible (dimmed) as context, and only the searched
    // word plus its reviewed/personal relations light up at full opacity.
    for (const item of allNodes) {
      item.targetX = item.homeX; item.targetY = item.homeY;
      item.targetAlpha = item.status === "eligible" || item.personal ? .16 : .05;
      item.focusRole = "background"; item.focusColor = null;
    }
    node.targetAlpha = 1;
    node.focusRole = "center";
    node.focusColor = node.personal ? RELATION_STYLE.personal.color : "#171816";
    for (const edge of focusConnections) {
      const neighbor = nodeById.get(edge.other);
      if (!neighbor) continue;
      neighbor.targetAlpha = 1;
      neighbor.focusRole = "direct";
      neighbor.focusColor = visualFor(edge).color;
    }

    focusEdges = focusConnections.map((edge, index) => ({
      ...edge, from: node.id, to: edge.other, delay: 100 + index * 86,
    }));

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
    $("#reset").textContent = "返回词网";
    searchResults.classList.add("hidden");
    search.blur();
    updateStats();
    animateView(focusViewForIds([node.id, ...focusConnections.map((edge) => edge.other)], true), 560);
    requestDraw();
  }

  function visualFor(edge) {
    if (edge.kind === "personal") return { ...RELATION_STYLE.personal, alpha: .88, label: edge.label || "我的联想" };
    if (edge.kind === "structural") return { ...RELATION_STYLE.derivation, dash: [6, 5], alpha: .68, label: `${edge.label || "构词线索"} · 待核准` };
    if (edge.kind === "form") return { ...RELATION_STYLE.trap, dash: [3, 5], alpha: .58, label: `${edge.label || "形音相近"} · 候选` };
    const style = RELATION_STYLE[edge.relation] || RELATION_STYLE.synonym;
    const mappedLabel = edge.label ? RELATION_NAMES[edge.label] : null;
    // Historical/Latin-root word-family links are real, but they are not
    // the same claim as a transparent modern prefix (faire -> refaire):
    // label them "词源" (etymology) instead of "构词" (word-formation) so
    // the two are never conflated.
    const isEtymological = edge.relation === "etymological_family" || edge.kind === "official" && String(edge.dimension || "").includes("etymological");
    const relationName = isEtymological ? "词源" : (RELATION_NAMES[edge.relation] || edge.relation || "已整理");
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
    ctx.lineWidth = edge.kind === "official" ? 2 : 1.5;
    ctx.setLineDash(visual.dash);
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(end.x, end.y); ctx.stroke();
    ctx.setLineDash([]);

    if (raw > .86 && visual.arrow) {
      const target = directionTarget(edge);
      if (target === edge.to) drawArrow(pa, pb, visual.color, visual.alpha);
      else drawArrow(pb, pa, visual.color, visual.alpha);
    }
    if (raw > .68) {
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

  // Layout links only organize the map into a legible shape -- they are
  // never a language relation -- so they always render as extremely faint
  // gray, well below the visual weight of any reviewed relation.
  function drawLayoutLines(opacityScale) {
    for (const edge of baseLinks) {
      const learningTopology = edge.mask & (1 | 2 | 16);
      if (!learningTopology || edge.weight < .26) continue;
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      if (!visible(pa, 30) && !visible(pb, 30)) continue;
      ctx.globalAlpha = ((isMobileLayout() ? .02 : .028) + edge.weight * (isMobileLayout() ? .016 : .02)) * opacityScale;
      ctx.strokeStyle = "#8f9089"; ctx.lineWidth = isMobileLayout() ? .62 : .68;
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
  }

  // A brief, gentle first-look cue: cycle through the map's 3 best-known
  // reviewed relations so a new visitor sees what a confirmed relation
  // looks like (a solid colored line) before touching anything. Runs once,
  // stops as soon as the learner interacts, and is skipped entirely under
  // prefers-reduced-motion.
  const ONBOARDING_PAIRS = [["faire", "refaire"], ["dire", "parler"], ["voir", "regarder"]];

  function findOfficialEdgeBetween(wordA, wordB) {
    // A lemma can have multiple POS entries (e.g. "dire" NOM and VER); try
    // every candidate pairing rather than assuming the first array match is
    // the one that actually carries the reviewed relation.
    for (const nodeA of officialNodes.filter((item) => item.word === wordA)) {
      for (const nodeB of officialNodes.filter((item) => item.word === wordB)) {
        const edge = (officialAdj.get(nodeA.id) || []).find((item) => item.other === nodeB.id);
        if (edge) return { edge, a: nodeA, b: nodeB };
      }
    }
    return null;
  }

  function stopOnboarding() {
    if (onboardingTimer) { clearTimeout(onboardingTimer); onboardingTimer = null; }
    if (onboardingHighlight) { onboardingHighlight = null; requestDraw(); }
  }

  function runOnboarding() {
    if (reducedMotion.matches) return;
    const pairs = ONBOARDING_PAIRS.map(([a, b]) => findOfficialEdgeBetween(a, b)).filter(Boolean);
    if (!pairs.length) return;
    const STEP_MS = 2400;
    let index = 0;
    const step = () => {
      if (selected) { stopOnboarding(); return; }
      onboardingHighlight = pairs[index];
      requestDraw();
      index += 1;
      onboardingTimer = setTimeout(index < pairs.length ? step : stopOnboarding, STEP_MS);
    };
    onboardingTimer = setTimeout(step, 1100);
  }

  function drawOnboardingHighlight() {
    if (!onboardingHighlight || selected) return;
    const { edge, a, b } = onboardingHighlight;
    const pa = screen(a), pb = screen(b);
    const visual = visualFor(edge);
    ctx.globalAlpha = .92; ctx.strokeStyle = visual.color; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    for (const [node, p] of [[a, pa], [b, pb]]) {
      ctx.globalAlpha = 1; ctx.fillStyle = "#171816";
      ctx.beginPath(); ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2); ctx.fill();
      ctx.font = `650 12px ${CANVAS_FONT}`; ctx.fillStyle = "#171816";
      ctx.fillText(node.word, p.x + 8, p.y - 7);
    }
    drawEdgeChip(visual.label, (pa.x + pb.x) / 2, (pa.y + pb.y) / 2, visual.color, 1);
  }

  function drawGlobal(now) {
    ctx.lineCap = "round";
    drawLayoutLines(1);
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
    drawOnboardingHighlight();
  }

  function drawFocus(now) {
    ctx.lineCap = "round";
    drawLayoutLines(.35);
    for (const node of allNodes) {
      if (node.focusRole === "background") drawFocusNode(node);
    }
    for (const edge of focusEdges) drawFocusEdge(edge, now);
    for (const node of allNodes) {
      if (node.focusRole === "direct") drawFocusNode(node);
    }
    const center = nodeById.get(selected);
    if (center) drawFocusNode(center);

    if (!focusConnections.length && center) {
      const p = screen(center);
      ctx.globalAlpha = .76; ctx.fillStyle = "#686963"; ctx.font = `550 11.5px ${CANVAS_FONT}`; ctx.textAlign = "center";
      ctx.fillText("这个词目前还没有经过编辑整理的词汇关系", p.x, p.y + 44);
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

  // Chinese-first: node.gloss (the one editorially reviewed Chinese meaning)
  // is the panel's primary content, shown in the header. Everything below
  // is raw Wiktionnaire/DBnary dictionary material -- useful, but never
  // reviewed -- so it stays clearly labeled "词典原文" and collapsed by
  // default rather than presented as if it were curated.
  // A reviewed relation can bind to one specific dictionary sense (e.g. the
  // RL-fr node for "enfiler II" resolves to DBnary sense #11, "put on a
  // coat") -- but dictionary sense order has nothing to do with that, so the
  // plain first-N-by-source-order preview can show three senses totally
  // unrelated to the relation the learner just clicked into. Collect every
  // sense number a reviewed relation names for this node, from either side.
  function keySenseNumbersFor(nodeId) {
    const edges = officialAdj.get(nodeId) || [];
    const hints = edges.map((edge) => (edge.a === nodeId ? edge.keySenseA : edge.keySenseB)).filter(Boolean);
    return [...new Set(hints)];
  }

  function renderSenseGroups(node) {
    const groups = GRAPH_SENSES[node.id] || [];
    const flattened = wordCardTools?.flattenSenseGroups(groups)
      || groups.flatMap((group, groupIndex) => group.senses.map((sense) => ({ ...sense, groupIndex, sourceUrl: group.sourceUrl })));
    if (!flattened.length) return "";
    const includeExamples = !foundationalCoreIds.has(node.id) && !node.searchOnly;
    const keySenses = keySenseNumbersFor(node.id);
    const preview = wordCardTools?.selectPreviewSenses
      ? wordCardTools.selectPreviewSenses(flattened, keySenses, 3)
      : flattened.slice(0, 3);
    const sourceUrl = groups[0]?.sourceUrl;
    const renderFull = (items) => items.map((sense) => `
      <li><span>${groups.length > 1 ? `${sense.groupIndex + 1}.${escapeHtml(sense.number)}` : escapeHtml(sense.number)}</span><div><p>${escapeHtml(sense.definition)}</p>${includeExamples && sense.examples?.length ? `<ul class="sense-examples">${sense.examples.map((example) => `<li>${escapeHtml(example)}</li>`).join("")}</ul>` : ""}</div></li>
    `).join("");
    return `<section class="panel-section sense-section">
      <h3>词典释义</h3>
      <ol class="sense-preview-list">${preview.map((sense) => `<li>${escapeHtml(sense.definition)}</li>`).join("")}</ol>
      <details class="sense-more"><summary>词典原文${flattened.length > 1 ? `（共 ${flattened.length} 条）` : ""}</summary><ol class="sense-list continued">${renderFull(flattened)}</ol></details>
      ${sourceUrl ? `<a class="sense-source" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Wiktionnaire 来源 ↗</a>` : ""}
    </section>`;
  }

  function renderTeachingExamples(node) {
    const examples = teachingExamples[node.id] || [];
    if (!examples.length) return "";
    return `<section class="panel-section teaching-examples"><h3>学习例句 · 编辑例句</h3><ul>${examples.map((example) => `<li><strong>${escapeHtml(example.text)}</strong><span>${escapeHtml(example.gloss)}</span></li>`).join("")}</ul></section>`;
  }

  function renderEditorialLearning(node) {
    const learning = GRAPH_LEARNING[node.id];
    if (!learning) return "";
    const collocations = learning.collocations || [];
    return collocations.length ? `<section class="panel-section collocation-section"><h3>常用搭配与固定表达</h3><ul class="collocation-list">${collocations.map((item) => `<li><strong>${escapeHtml(item.expression)}</strong><span>${escapeHtml(item.gloss)}</span></li>`).join("")}</ul></section>` : "";
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
            return Array.isArray(parsed)
              ? parsed.map((entry) => (entry && typeof entry === "object" ? { fr: entry.fr || "", zh: entry.zh || "" } : { fr: String(entry || ""), zh: "" }))
              : [];
          } catch {
            return [];
          }
        })(),
      }));
  }

  function contrastNoteArticle(note) {
    return `<article class="contrast-note">
        <p class="contrast-explanation"><strong>${escapeHtml(note.word)}</strong> · ${escapeHtml(note.label)}</p>
        <p class="contrast-explanation-fr">${escapeHtml(note.explanation)}</p>
        ${note.examples?.length ? `<p class="example-tag">编辑例句</p><ul class="contrast-examples">${note.examples.map((example) => `<li>${escapeHtml(example.fr)}${example.zh ? `<span class="contrast-example-zh">${escapeHtml(example.zh)}</span>` : ""}</li>`).join("")}</ul>` : ""}
      </article>`;
  }

  function renderReviewedRelationNotes(items) {
    const notes = relationNotesFor(items);
    if (!notes.length) return "";
    // Historical/Latin-root word-family links are real, but they are not
    // the same claim as a live usage contrast, so they get their own
    // clearly-labeled area with an explicit caveat rather than sitting
    // alongside "用法区分" as if they described modern usage.
    const etymological = notes.filter((note) => String(note.dimension || "").includes("etymological"));
    const usage = notes.filter((note) => !etymological.includes(note));
    // The Chinese label is the primary explanation (it already states why
    // the two words relate/differ); the French sentence is supplementary
    // detail for learners who want it, not the only account.
    return `
      ${usage.length ? `<section class="panel-section contrast-section"><h3>用法区分 · 编辑整理</h3>${usage.map(contrastNoteArticle).join("")}</section>` : ""}
      ${etymological.length ? `<section class="panel-section contrast-section etymology-relation-section"><h3>词源联系 · 编辑整理</h3><p class="candidate-note">历史同源关系，说明两个词共享词根，不代表现代法语中意思相近或可以互换。</p>${etymological.map(contrastNoteArticle).join("")}</section>` : ""}
    `;
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
    // GRAPH_OFFICIAL_EDGES only ever contains relations with real human
    // review evidence (see has_real_review_evidence in build_graph.py), so
    // everything reaching officialAdj here is already reviewed -- there is
    // no separate "sourced but unreviewed" bucket to show learners.
    const reviewed = (officialAdj.get(node.id) || [])
      .map((edge) => ({ edge: { ...edge, kind: "official" }, node: nodeById.get(edge.other) }))
      .filter((item) => item.node)
      .sort((a, b) => relationRank(a.edge) - relationRank(b.edge)
        || a.node.word.localeCompare(b.node.word, "fr"));
    const mine = personalFor(node.id).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const officialIds = new Set(reviewed.map((item) => item.node.id));
    const form = strongFormFor(node.id).filter((edge) => !officialIds.has(edge.other)).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node).slice(0, 8);
    const formIds = new Set(form.map((item) => item.node.id));
    const structural = strongStructuralFor(node.id).filter((edge) => !officialIds.has(edge.other)).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node).slice(0, 16);
    const nearby = (layoutAdj.get(node.id) || []).filter((edge) => !officialIds.has(edge.other) && !formIds.has(edge.other) && !(edge.mask & 2))
      .sort((a, b) => b.weight - a.weight).slice(0, 5).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const badge = node.personal ? "我的词"
      : node.searchOnly ? `${node.level} 可检索学习词`
      : node.status === "eligible" ? `${node.level} 主词表` : "因编辑整理关系收录";
    panelContent.innerHTML = `
      <h1 class="word-title">${escapeHtml(node.word)}</h1>
      <div class="word-meta"><span>${escapeHtml(node.pos)}</span><span>${escapeHtml(badge)}</span></div>
      <p class="word-gloss"><span>中文提示 · 可能不完整</span>${escapeHtml(node.gloss || "暂无")}</p>
      ${node.note ? `<p class="word-note">${escapeHtml(node.note)}</p>` : ""}
      ${node.searchOnly ? `<section class="search-only-note"><strong>暂未建立学习关系</strong><span>这个词可搜索、查看义项；它尚未进入关系图。</span></section>` : ""}
      <div class="learning-actions">
        <section class="learning-action" aria-label="我的词卡">
          <button id="draft-word" class="quiet-button" type="button">我的词卡 · 加入 / 打开</button>
        </section>
      </div>
      ${renderSenseGroups(node)}
      ${renderTeachingExamples(node)}
      ${renderEditorialLearning(node)}
      ${reviewed.length ? `<section class="panel-section"><h3>经过编辑整理的词汇关系</h3><div class="relation-list">${reviewed.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : `<p class="empty-relations-note">这个词目前还没有经过编辑整理的词汇关系。</p>`}
      ${renderReviewedRelationNotes(reviewed)}
      ${mine.length ? `<section class="panel-section"><h3>我的关系</h3><div class="relation-list">${mine.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${form.length ? `<details class="panel-section candidate-details"><summary>形音相近的自动候选（未经编辑整理）</summary><p class="candidate-note">只是形近且音近，虚线不代表已确认的易混关系。</p><div class="relation-list">${form.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></details>` : ""}
      ${structural.length ? `<details class="panel-section candidate-details"><summary>构词相近的自动候选（未经编辑整理）</summary><p class="candidate-note">来自词形结构的自动匹配，不等同于已编辑整理的教学关系。</p><div class="relation-list">${structural.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></details>` : ""}
      ${nearby.length ? `<details class="panel-section candidate-details"><summary>查看更多自动候选</summary><p class="candidate-note">这些词只保留为自动候选，不进入中心发散图，也不影响大词网位置。</p><div class="relation-list">${nearby.map(({ edge, node: other }) => relationButton(other, { ...edge, kind: "structural", relation: "derivation", label: signals(edge.mask) })).join("")}</div></details>` : ""}
    `;
    panel.classList.remove("hidden");
    panelContent.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => enterFocus(button.dataset.node)));
    $("#draft-word").addEventListener("click", () => openDraftCardForNode(node));
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
      // The layout-skeleton edge count isn't a count of reviewed relations,
      // so showing it here would read as a quality signal it isn't.
      const wordTotal = GRAPH_META.eligible_count + GRAPH_META.support_node_count;
      $("#stats").textContent = `收录 ${wordTotal.toLocaleString()} 个词`;
      return;
    }
    const officialCount = focusConnections
      .filter((edge) => edge.kind === "official")
      .reduce((total, edge) => total + (edge.relations?.length || 1), 0);
    $("#stats").textContent = officialCount ? `${focusConnections.length} 个相关词 · ${officialCount} 条编辑整理关系` : "";
  }

  function showTooltip(node, event) {
    if (!node || selected && ["center", "direct"].includes(node.focusRole)) { tooltip.classList.add("hidden"); return; }
    const meta = node.personal ? "我的词" : [node.pos, node.level].filter(Boolean).join(" · ");
    tooltip.innerHTML = `<strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(meta)}</em><span>${escapeHtml(node.gloss || "中文提示待补")}</span>`;
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
    stopOnboarding();
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

  function getSearchEntries() {
    if (!searchEntriesCache) {
      searchEntriesCache = allNodes.concat(searchOnlyNodes).map((node) => ({
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
    }
    return searchEntriesCache;
  }

  function doSearch() {
    stopOnboarding();
    const query = searchTools?.normalizeSearchText(search.value) || search.value.trim();
    $("#map-copy").classList.toggle("quiet", Boolean(query));
    if (!query) { searchResults.classList.add("hidden"); return; }
    if (!searchTools) {
      searchResults.innerHTML = `<div class="search-result"><small>搜索正在准备，请再试一次。</small></div>`;
      searchResults.classList.remove("hidden");
      return;
    }
    const searchState = searchTools.searchLexemes(getSearchEntries(), query, { limit: 12, suggestionLimit: 5 });
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
  // Debounced so a burst of fast keystrokes coalesces into one search pass
  // instead of one full re-render per key; skipped mid-composition so an IME
  // (e.g. typing accented letters or Chinese) doesn't get its in-progress,
  // not-yet-committed text treated as a real query.
  let searchDebounce = null;
  let composing = false;
  function scheduleSearch() {
    if (composing) return;
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(doSearch, 60);
  }
  search.addEventListener("compositionstart", () => { composing = true; });
  search.addEventListener("compositionend", () => { composing = false; scheduleSearch(); });
  search.addEventListener("input", scheduleSearch);
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
    if (selected) animateView(focusViewForIds([selected, ...focusConnections.map((edge) => edge.other)], false), 320);
  });
  $("#reset").addEventListener("click", () => fitHome());
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); fitHome(); });
  $("#focus-back").addEventListener("click", () => fitHome());
  $("#local-data-open").addEventListener("click", openLocalDataDialog);
  $("#local-data-close").addEventListener("click", closeLocalDataDialog);
  $("#local-data-mask").addEventListener("click", closeLocalDataDialog);
  $("#local-data-export").addEventListener("click", exportLocalData);
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
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").catch(() => {}));
  }
  resize();
  runOnboarding();
})();
