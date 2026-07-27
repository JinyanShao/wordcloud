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

  const SIGNALS = [[1, "释义接近"], [2, "构词线索"], [4, "拼写相似"], [8, "读音相似"], [16, "审校关系"], [32, "连通骨架"]];
  const RELATION_NAMES = { syn: "近义", compare: "对比", fam: "派生", drift: "语义漂移", trap: "易混", ant: "反义", cause: "因果" };
  const RELATION_ORDER = ["fam", "syn", "compare", "drift", "ant", "cause", "trap", "personal"];
  const RELATION_STYLE = {
    syn: { color: "#7b8188", dash: [], arrow: false },
    compare: { color: "#c07a22", dash: [], arrow: true },
    fam: { color: "#3477b8", dash: [], arrow: false },
    drift: { color: "#7859a6", dash: [7, 5], arrow: false },
    trap: { color: "#c7465d", dash: [], arrow: false },
    ant: { color: "#278867", dash: [8, 5], arrow: false },
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
  const nodeById = new Map(officialNodes.map((node) => [node.id, node]));
  const baseLinks = GRAPH_LINKS.map((row) => ({ a: String(row[0]), b: String(row[1]), mask: row[2], weight: row[3] }));
  const officialEdges = GRAPH_OFFICIAL_EDGES.map((row) => ({
    a: String(row[0]), b: String(row[1]), relation: row[2], dimension: row[3], subtype: row[4], direction: row[5],
    label: row[6], explanation: row[7], confidence: row[8], review: row[9], kind: "official",
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

  function resize() {
    const rect = viewport.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    if (!homeView.scale || homeView.scale === 1) fitHome(false);
    else if (selected) enterFocus(selected, { addTrail: false, preserveCenter: true });
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

  function connectionsFor(id, limit = 16) {
    const byNeighbor = new Map();
    const candidates = [
      ...(officialAdj.get(id) || []).map((edge) => ({ ...edge, kind: "official" })),
      ...personalFor(id),
      ...strongStructuralFor(id),
    ];
    const priority = { official: 3, personal: 2, structural: 1 };
    for (const edge of candidates) {
      if (!nodeById.has(edge.other) || edge.other === id) continue;
      const existing = byNeighbor.get(edge.other);
      if (!existing || priority[edge.kind] > priority[existing.kind]) byNeighbor.set(edge.other, edge);
    }
    return [...byNeighbor.values()]
      .sort((a, b) => {
        const pa = priority[a.kind], pb = priority[b.kind];
        if (pa !== pb) return pb - pa;
        const ra = RELATION_ORDER.indexOf(a.relation), rb = RELATION_ORDER.indexOf(b.relation);
        if (ra !== rb) return ra - rb;
        return (nodeById.get(a.other)?.word || "").localeCompare(nodeById.get(b.other)?.word || "", "fr");
      })
      .slice(0, limit);
  }

  function focusScaleFor(count) {
    if (width < 720) return count > 8 ? .72 : .84;
    if (count > 12) return .86;
    return 1.02;
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
    focusConnections = connectionsFor(node.id);
    const focusScale = focusScaleFor(focusConnections.length);
    const centerShift = width > 900 ? 135 / focusScale : 0;

    for (const item of allNodes) {
      item.targetX = item.homeX; item.targetY = item.homeY;
      item.targetAlpha = .075;
      item.focusRole = "background"; item.focusColor = null;
    }
    node.targetX = center.x; node.targetY = center.y;
    node.targetAlpha = 1; node.focusRole = "center"; node.focusColor = "#171816";

    if (focusConnections.length <= 8) {
      positionRing(focusConnections, center, 215 / focusScale);
    } else {
      const split = Math.ceil(focusConnections.length / 2);
      positionRing(focusConnections.slice(0, split), center, 178 / focusScale);
      positionRing(focusConnections.slice(split), center, 300 / focusScale, -Math.PI / 2 + Math.PI / Math.max(1, focusConnections.length - split));
    }

    focusEdges = focusConnections.map((edge, index) => ({
      ...edge, from: node.id, to: edge.other, satellite: false, delay: 100 + index * 86,
    }));

    if (focusConnections.length && focusConnections.length <= 12) {
      const directIds = new Set([node.id, ...focusConnections.map((edge) => edge.other)]);
      const usedSatellites = new Set();
      let satelliteIndex = 0;
      for (const parentConnection of focusConnections) {
        if (satelliteIndex >= 16) break;
        const parent = nodeById.get(parentConnection.other);
        const satellites = connectionsFor(parent.id, 8)
          .filter((edge) => !directIds.has(edge.other) && !usedSatellites.has(edge.other))
          .slice(0, 2);
        satellites.forEach((edge, localIndex) => {
          if (satelliteIndex >= 16) return;
          usedSatellites.add(edge.other);
          const satellite = nodeById.get(edge.other);
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
    $("#map-copy").classList.add("quiet");
    focusBar.classList.remove("hidden");
    focusLegend.classList.remove("hidden");
    $("#legend").classList.add("focus-hidden");
    $("#reset").textContent = "返回全图";
    searchResults.classList.add("hidden");
    search.blur();
    updateStats();
    animateView({ x: center.x + centerShift, y: center.y, scale: focusScale }, 560);
    requestDraw();
  }

  function visualFor(edge) {
    if (edge.satellite) return { ...RELATION_STYLE.satellite, alpha: .34, label: "" };
    if (edge.kind === "personal") return { ...RELATION_STYLE.personal, alpha: .88, label: edge.label || "我的联想" };
    if (edge.kind === "structural") return { ...RELATION_STYLE.fam, dash: [6, 5], alpha: .68, label: "构词线索 · 待核准" };
    const style = RELATION_STYLE[edge.relation] || RELATION_STYLE.syn;
    const rawLabel = edge.label || edge.relation || "已审校";
    return { ...style, alpha: .95, label: RELATION_NAMES[rawLabel] || rawLabel };
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
    ctx.font = "600 9.5px Inter, sans-serif";
    const w = ctx.measureText(text).width + 16;
    ctx.globalAlpha = Math.min(1, alpha * .98);
    roundedRect(x - w / 2, y - 10, w, 20, 10);
    ctx.fillStyle = "#fbfaf7"; ctx.fill();
    ctx.strokeStyle = color; ctx.lineWidth = .8; ctx.stroke();
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
    ctx.lineWidth = edge.satellite ? .8 : edge.kind === "official" ? 1.75 : 1.35;
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
    ctx.font = node.focusRole === "center" ? "650 14px Inter, sans-serif" : "600 12px Inter, sans-serif";
    const wordWidth = ctx.measureText(node.word).width;
    ctx.font = "500 8.5px Inter, sans-serif";
    const posWidth = ctx.measureText(node.pos).width;
    const h = node.focusRole === "center" ? 34 : 29;
    const w = Math.max(64, wordWidth + posWidth + 28);
    const x = point.x - w / 2, y = point.y - h / 2;
    ctx.globalAlpha = node.alpha;
    roundedRect(x, y, w, h, h / 2);
    if (node.focusRole === "center") {
      ctx.fillStyle = node.personal ? RELATION_STYLE.personal.color : "#171816";
      ctx.fill();
    } else {
      ctx.fillStyle = "rgba(251,250,247,.97)"; ctx.fill();
      ctx.strokeStyle = node.focusColor || "#8f8e88"; ctx.lineWidth = 1.1; ctx.stroke();
    }
    ctx.font = node.focusRole === "center" ? "650 14px Inter, sans-serif" : "600 12px Inter, sans-serif";
    ctx.fillStyle = node.focusRole === "center" ? "#fbfaf7" : "#20211e";
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    ctx.fillText(node.word, x + 11, point.y + .3);
    ctx.font = "500 8.5px Inter, sans-serif";
    ctx.fillStyle = node.focusRole === "center" ? "rgba(251,250,247,.58)" : "#8a8982";
    ctx.fillText(node.pos, x + 15 + wordWidth, point.y + .3);
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    hitBoxes.set(node.id, { x, y, w, h });
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
      ctx.font = "500 9px Inter, sans-serif"; ctx.fillStyle = "#73736d";
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
      ctx.globalAlpha = .42; ctx.strokeStyle = "#343530"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x, p.y, 7.2, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = .9; ctx.fillStyle = "#343530"; ctx.font = "600 10px Inter, sans-serif";
      ctx.fillText(node.word, p.x + 10, p.y - 5);
    }
  }

  function drawGlobal(now) {
    ctx.lineCap = "round";
    for (const edge of baseLinks) {
      if (edge.weight < .26) continue;
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      if (!visible(pa, 30) && !visible(pb, 30)) continue;
      ctx.globalAlpha = .027 + edge.weight * .023;
      ctx.strokeStyle = "#9c9b95"; ctx.lineWidth = .5;
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
      ctx.fillStyle = node.personal ? RELATION_STYLE.personal.color : "#777770";
      ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill();
      const labelByZoom = (view.scale > 1.18 && node.size > 4.4) || (view.scale > 2.15 && node.size > 3.1) || view.scale > 4.5;
      if (node.id === hovered || labelByZoom) labels.push({ node, p, priority: node.id === hovered ? 90 : node.size });
    }
    labels.sort((a, b) => b.priority - a.priority);
    const occupied = [];
    for (const item of labels.slice(0, 150)) {
      ctx.font = item.priority >= 80 ? "600 12px Inter, sans-serif" : "500 10px Inter, sans-serif";
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
      ctx.globalAlpha = .7; ctx.fillStyle = "#777770"; ctx.font = "500 11px Inter, sans-serif"; ctx.textAlign = "center";
      ctx.fillText("暂无可展示的可信关系", p.x, p.y + 44);
      ctx.font = "400 9.5px Inter, sans-serif"; ctx.fillStyle = "#9b9a94";
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
    let best = null, bestDistance = selected ? 5 : 12;
    for (const node of allNodes) {
      const p = screen(node);
      if (Math.abs(p.x - x) > 13 || Math.abs(p.y - y) > 13) continue;
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
    return `<button class="relation-item ${edge.kind}" style="--relation-color:${visual.color}" data-node="${escapeHtml(node.id)}"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml(visual.label)}</small></button>`;
  }

  function renderPanel(node) {
    const official = (officialAdj.get(node.id) || []).map((edge) => ({ edge: { ...edge, kind: "official" }, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const mine = personalFor(node.id).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const officialIds = new Set(official.map((item) => item.node.id));
    const structural = strongStructuralFor(node.id).filter((edge) => !officialIds.has(edge.other)).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node).slice(0, 16);
    const nearby = (layoutAdj.get(node.id) || []).filter((edge) => !officialIds.has(edge.other) && !(edge.mask & 2))
      .sort((a, b) => b.weight - a.weight).slice(0, 5).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const badge = node.personal ? "我的词" : node.status === "eligible" ? `${node.level} 主词表` : "官方关系支撑词";
    panelContent.innerHTML = `
      <h1 class="word-title">${escapeHtml(node.word)}</h1>
      <div class="word-meta"><span>${escapeHtml(node.pos)}</span><span>${escapeHtml(badge)}</span></div>
      <p class="word-gloss">${escapeHtml(node.gloss || "暂无中文提示")}</p>
      ${node.note ? `<p class="word-note">${escapeHtml(node.note)}</p>` : ""}
      ${official.length ? `<section class="panel-section"><h3>已审校关系 · ${official.length}</h3><div class="relation-list">${official.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${mine.length ? `<section class="panel-section"><h3>我的关系 · ${mine.length}</h3><div class="relation-list">${mine.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${structural.length ? `<section class="panel-section"><h3>构词线索 · 待核准</h3><p class="candidate-note">来自 Lexique 形态结构，只在图中以蓝色虚线显示，不等同于已审校教学关系。</p><div class="relation-list">${structural.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${nearby.length ? `<details class="panel-section candidate-details"><summary>查看自动制图近邻</summary><p class="candidate-note">这些词只因自动信号靠近，不进入中心发散图。</p><div class="relation-list">${nearby.map(({ edge, node: other }) => relationButton(other, { ...edge, kind: "structural", relation: "syn", label: signals(edge.mask) })).join("")}</div></details>` : ""}
    `;
    panel.classList.remove("hidden");
    panelContent.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => enterFocus(button.dataset.node)));
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
      $("#stats").textContent = `${GRAPH_META.eligible_count.toLocaleString()} 主词 · ${GRAPH_META.support_node_count} 支撑词 · ${GRAPH_META.layout_link_count.toLocaleString()} 制图线索`;
      return;
    }
    const officialCount = focusConnections.filter((edge) => edge.kind === "official").length;
    const structuralCount = focusConnections.filter((edge) => edge.kind === "structural").length;
    $("#stats").textContent = `${focusConnections.length} 条可见关系 · ${officialCount} 已审校 · ${structuralCount} 构词线索`;
  }

  function showTooltip(node, event) {
    if (!node || selected && ["center", "direct"].includes(node.focusRole)) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = `<strong>${escapeHtml(node.word)}</strong><span>${escapeHtml(node.gloss || node.pos)}</span>`;
    tooltip.style.left = `${Math.min(window.innerWidth - 230, event.clientX + 13)}px`;
    tooltip.style.top = `${Math.min(window.innerHeight - 70, event.clientY + 13)}px`;
    tooltip.classList.remove("hidden");
  }

  canvas.addEventListener("pointerdown", (event) => {
    dragging = true; moved = false; canvas.setPointerCapture(event.pointerId); canvas.classList.add("dragging");
    dragStart = { clientX: event.clientX, clientY: event.clientY, x: view.x, y: view.y };
  });
  canvas.addEventListener("pointermove", (event) => {
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
    if (!dragging) return;
    dragging = false; canvas.releasePointerCapture(event.pointerId); canvas.classList.remove("dragging");
    if (!moved) {
      const hit = hitTest(event.clientX, event.clientY);
      if (!hit && selected) fitHome();
      else if (hit?.focusRole === "background") enterFocus(hit.id, { resetTrail: true });
      else if (hit) enterFocus(hit.id);
    }
  });
  canvas.addEventListener("pointerleave", () => { if (!dragging) { hovered = null; tooltip.classList.add("hidden"); requestDraw(); } });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const before = worldAt(event.clientX, event.clientY);
    view.scale = Math.max(homeView.scale * .62, Math.min(7, view.scale * Math.exp(-event.deltaY * .00125)));
    const after = worldAt(event.clientX, event.clientY);
    view.x += before.x - after.x; view.y += before.y - after.y; viewTween = null;
    requestDraw();
  }, { passive: false });

  function doSearch() {
    const query = search.value.trim().toLocaleLowerCase("fr");
    if (!query) { searchResults.classList.add("hidden"); return; }
    const starts = [], contains = [];
    for (const node of allNodes) {
      const word = node.word.toLocaleLowerCase("fr");
      if (word.startsWith(query)) starts.push(node); else if (word.includes(query)) contains.push(node);
      if (starts.length + contains.length > 40) break;
    }
    const results = starts.concat(contains).slice(0, 12);
    searchResults.innerHTML = results.length ? results.map((node) => `<button class="search-result" data-node="${escapeHtml(node.id)}" role="option"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml(node.gloss || (node.personal ? "我的词" : node.level))}</small></button>`).join("") : `<div class="search-result"><small>没有找到；你可以用右下角的 + 添加它。</small></div>`;
    searchResults.classList.remove("hidden");
    searchResults.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => enterFocus(button.dataset.node, { resetTrail: true })));
  }
  search.addEventListener("input", doSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { const first = searchResults.querySelector("[data-node]"); if (first) enterFocus(first.dataset.node, { resetTrail: true }); }
    if (event.key === "Escape") searchResults.classList.add("hidden");
  });

  $("#panel-close").addEventListener("click", () => panel.classList.add("hidden"));
  $("#reset").addEventListener("click", () => fitHome());
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); fitHome(); });
  $("#focus-back").addEventListener("click", () => fitHome());
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
  resize();
})();
