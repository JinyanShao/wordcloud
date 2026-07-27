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
  const PERSONAL_KEY = "maillage.personal.v2";
  const SIGNALS = [[1, "释义接近"], [2, "构词线索"], [4, "拼写相似"], [8, "读音相似"], [16, "审校关系"], [32, "连通骨架"]];
  const RELATION_NAMES = { syn: "近义", compare: "对比", fam: "词族", drift: "语义漂移", trap: "易混", ant: "反义", cause: "因果" };
  const NODE = { id: 0, word: 1, pos: 2, level: 3, gloss: 4, x: 5, y: 6, size: 7, community: 8, freq: 9, hasGloss: 10, status: 11, note: 12 };

  const officialNodes = GRAPH_NODES.map((row) => ({
    id: String(row[NODE.id]), word: row[NODE.word], pos: row[NODE.pos], level: row[NODE.level] || "—",
    gloss: row[NODE.gloss], x: row[NODE.x], y: row[NODE.y], size: row[NODE.size], community: row[NODE.community],
    freq: row[NODE.freq], status: row[NODE.status], note: row[NODE.note], personal: false,
  }));
  const nodeById = new Map(officialNodes.map((node) => [node.id, node]));
  const baseLinks = GRAPH_LINKS.map((row) => ({ a: String(row[0]), b: String(row[1]), mask: row[2], weight: row[3] }));
  const officialEdges = GRAPH_OFFICIAL_EDGES.map((row) => ({
    a: String(row[0]), b: String(row[1]), relation: row[2], dimension: row[3], subtype: row[4], direction: row[5],
    label: row[6], explanation: row[7], confidence: row[8], review: row[9],
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
  let width = 0;
  let height = 0;
  let dpr = 1;
  let dragging = false;
  let dragStart = null;
  let moved = false;
  let framePending = false;
  let view = { x: 0, y: 0, scale: 1 };
  let homeView = { x: 0, y: 0, scale: 1 };

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
    personalNodes = personal.nodes.map((node) => ({ ...node, id: String(node.id), personal: true, size: node.size || 3.2, status: "personal", level: "我的" }));
    personalEdges = personal.edges.map((edge) => ({ ...edge, a: String(edge.a), b: String(edge.b) }));
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
    requestDraw();
  }

  function fitHome(animate = true) {
    const spanX = Math.max(1, bounds.maxX - bounds.minX);
    const spanY = Math.max(1, bounds.maxY - bounds.minY);
    homeView = {
      x: (bounds.minX + bounds.maxX) / 2,
      y: (bounds.minY + bounds.maxY) / 2,
      scale: Math.min((width - 70) / spanX, (height - 70) / spanY),
    };
    selected = null;
    hovered = null;
    panel.classList.add("hidden");
    $("#map-copy").classList.remove("quiet");
    if (animate) animateView(homeView); else view = { ...homeView };
    requestDraw();
  }

  function animateView(target) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      view = { ...target };
      requestDraw();
      return;
    }
    const start = { ...view };
    const began = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - began) / 360);
      const ease = 1 - Math.pow(1 - t, 3);
      view.x = start.x + (target.x - start.x) * ease;
      view.y = start.y + (target.y - start.y) * ease;
      view.scale = start.scale + (target.scale - start.scale) * ease;
      draw();
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function screen(node) {
    return { x: (node.x - view.x) * view.scale + width / 2, y: (node.y - view.y) * view.scale + height / 2 };
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

  function selectedSets() {
    const official = new Set();
    const layout = new Set();
    const personalSet = new Set();
    if (!selected) return { official, layout, personalSet };
    for (const edge of officialAdj.get(selected) || []) official.add(edge.other);
    for (const edge of (layoutAdj.get(selected) || []).slice().sort((a, b) => b.weight - a.weight).slice(0, 24)) layout.add(edge.other);
    for (const edge of personalEdges) {
      if (edge.a === selected) personalSet.add(edge.b);
      if (edge.b === selected) personalSet.add(edge.a);
    }
    return { official, layout, personalSet };
  }

  function draw() {
    framePending = false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#f7f6f2";
    ctx.fillRect(0, 0, width, height);
    const related = selectedSets();

    ctx.lineCap = "round";
    for (const edge of baseLinks) {
      const a = nodeById.get(edge.a);
      const b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      if (!visible(pa, 30) && !visible(pb, 30)) continue;
      const incident = selected && (edge.a === selected || edge.b === selected);
      ctx.globalAlpha = selected ? (incident ? .24 : .018) : (.045 + edge.weight * .035);
      ctx.strokeStyle = incident ? "#8c8b84" : "#9c9b95";
      ctx.lineWidth = incident ? 1 : .55;
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }

    ctx.setLineDash([]);
    for (const edge of officialEdges) {
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const incident = selected && (edge.a === selected || edge.b === selected);
      if (!incident && view.scale < 1.05) continue;
      const pa = screen(a), pb = screen(b);
      ctx.globalAlpha = selected ? (incident ? .82 : .06) : .32;
      ctx.strokeStyle = "#171816";
      ctx.lineWidth = incident ? 1.7 : 1;
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }

    ctx.setLineDash([5, 4]);
    for (const edge of personalEdges) {
      const a = nodeById.get(edge.a), b = nodeById.get(edge.b);
      if (!a || !b) continue;
      const pa = screen(a), pb = screen(b);
      ctx.globalAlpha = selected && edge.a !== selected && edge.b !== selected ? .12 : .82;
      ctx.strokeStyle = "#b96d22"; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
    ctx.setLineDash([]);

    const labels = [];
    for (const node of allNodes) {
      const p = screen(node);
      if (!visible(p, 16)) continue;
      const radius = nodeRadius(node);
      const isSelected = node.id === selected;
      const isHovered = node.id === hovered;
      const isOfficial = related.official.has(node.id);
      const isPersonalRelated = related.personalSet.has(node.id);
      const isLayout = related.layout.has(node.id);
      let alpha = 1;
      if (selected && !isSelected && !isOfficial && !isPersonalRelated && !isLayout) alpha = .15;
      else if (selected && isLayout && !isOfficial) alpha = .48;
      else if (!selected && node.status !== "eligible" && !node.personal) alpha = .44;
      ctx.globalAlpha = alpha;
      ctx.beginPath(); ctx.arc(p.x, p.y, isSelected ? Math.max(6, radius + 2) : radius, 0, Math.PI * 2);
      if (node.personal) {
        ctx.fillStyle = "#b96d22";
      } else if (isSelected || isOfficial) {
        ctx.fillStyle = "#171816";
      } else {
        ctx.fillStyle = "#777770";
      }
      ctx.fill();
      if (isSelected) {
        ctx.globalAlpha = .22; ctx.strokeStyle = node.personal ? "#b96d22" : "#171816"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(p.x, p.y, radius + 7, 0, Math.PI * 2); ctx.stroke();
      }
      const labelByZoom = (view.scale > 1.18 && node.size > 4.4) || (view.scale > 2.15 && node.size > 3.1) || view.scale > 4.5;
      if (isSelected || isHovered || isOfficial || isPersonalRelated || labelByZoom) {
        labels.push({ node, p, priority: isSelected ? 100 : isHovered ? 90 : isOfficial || isPersonalRelated ? 80 : node.size });
      }
    }

    labels.sort((a, b) => b.priority - a.priority);
    const occupied = [];
    let labelCount = 0;
    for (const item of labels) {
      if (labelCount > 150 && item.priority < 80) break;
      ctx.font = item.priority >= 80 ? "600 12px Inter, sans-serif" : "500 10px Inter, sans-serif";
      const textWidth = ctx.measureText(item.node.word).width;
      const x = item.p.x + nodeRadius(item.node) + 5;
      const y = item.p.y - 3;
      const box = { x, y: y - 11, w: textWidth + 4, h: 15 };
      const collides = item.priority < 80 && occupied.some((other) => box.x < other.x + other.w && box.x + box.w > other.x && box.y < other.y + other.h && box.y + box.h > other.y);
      if (collides) continue;
      occupied.push(box);
      ctx.globalAlpha = selected && item.priority < 80 ? .24 : .9;
      ctx.fillStyle = item.node.personal ? "#9a5619" : "#282925";
      ctx.fillText(item.node.word, x, y);
      labelCount += 1;
    }
    ctx.globalAlpha = 1;
  }

  function requestDraw() {
    if (framePending) return;
    framePending = true;
    requestAnimationFrame(draw);
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left, y = clientY - rect.top;
    let best = null, bestDistance = 12;
    for (const node of allNodes) {
      const p = screen(node);
      if (Math.abs(p.x - x) > 13 || Math.abs(p.y - y) > 13) continue;
      const distance = Math.hypot(p.x - x, p.y - y) - nodeRadius(node);
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

  function relationButton(node, meta, kind = "official") {
    const rawLabel = meta.label || meta.relation || "已审校";
    const sub = kind === "personal" ? (meta.label || "我的连接") : (RELATION_NAMES[rawLabel] || rawLabel);
    return `<button class="relation-item ${kind}" data-node="${escapeHtml(node.id)}"><strong>${escapeHtml(node.word)}</strong><em>${escapeHtml(node.pos)}</em><small>${escapeHtml(sub)}</small></button>`;
  }

  function renderPanel(node) {
    const official = (officialAdj.get(node.id) || []).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const mine = personalEdges.flatMap((edge) => {
      if (edge.a === node.id) return [{ edge, node: nodeById.get(edge.b) }];
      if (edge.b === node.id) return [{ edge, node: nodeById.get(edge.a) }];
      return [];
    }).filter((item) => item.node);
    const officialNeighborIds = new Set(official.map((item) => item.node.id));
    const nearby = (layoutAdj.get(node.id) || []).filter((edge) => !officialNeighborIds.has(edge.other) && edge.other !== node.id)
      .sort((a, b) => b.weight - a.weight).slice(0, 8).map((edge) => ({ edge, node: nodeById.get(edge.other) })).filter((item) => item.node);
    const badge = node.personal ? "我的词" : node.status === "eligible" ? `${node.level} 主词表` : "官方关系支撑词";
    panelContent.innerHTML = `
      <h1 class="word-title">${escapeHtml(node.word)}</h1>
      <div class="word-meta"><span>${escapeHtml(node.pos)}</span><span>${escapeHtml(badge)}</span></div>
      <p class="word-gloss">${escapeHtml(node.gloss || "暂无中文提示")}</p>
      ${node.note ? `<p class="word-note">${escapeHtml(node.note)}</p>` : ""}
      ${official.length ? `<section class="panel-section"><h3>maillage 审校关系 · ${official.length}</h3><div class="relation-list">${official.map(({ edge, node: other }) => relationButton(other, edge)).join("")}</div></section>` : ""}
      ${mine.length ? `<section class="panel-section"><h3>我的关系 · ${mine.length}</h3><div class="relation-list">${mine.map(({ edge, node: other }) => relationButton(other, edge, "personal")).join("")}</div></section>` : ""}
      ${nearby.length ? `<section class="panel-section"><h3>制图邻近 · 尚未审校</h3><p class="candidate-note">这些词因释义、构词、拼写或读音线索靠近，只用于发现候选，不当作已确认关系。</p><div class="relation-list">${nearby.map(({ edge, node: other }) => relationButton(other, { label: signals(edge.mask) }, "candidate")).join("")}</div></section>` : ""}
    `;
    panel.classList.remove("hidden");
    panelContent.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => selectNode(button.dataset.node)));
  }

  function selectNode(id, move = true) {
    const node = nodeById.get(String(id));
    if (!node) return;
    selected = node.id;
    $("#map-copy").classList.add("quiet");
    renderPanel(node);
    searchResults.classList.add("hidden");
    search.blur();
    if (move) animateView({ x: node.x, y: node.y, scale: Math.max(view.scale, 1.38) });
    requestDraw();
  }

  function showTooltip(node, event) {
    if (!node) { tooltip.classList.add("hidden"); return; }
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
      view.x = dragStart.x - dx / view.scale; view.y = dragStart.y - dy / view.scale; requestDraw();
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
    if (!moved) { const hit = hitTest(event.clientX, event.clientY); if (hit) selectNode(hit.id, false); }
  });
  canvas.addEventListener("pointerleave", () => { if (!dragging) { hovered = null; tooltip.classList.add("hidden"); requestDraw(); } });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const before = worldAt(event.clientX, event.clientY);
    view.scale = Math.max(homeView.scale * .62, Math.min(7, view.scale * Math.exp(-event.deltaY * .00125)));
    const after = worldAt(event.clientX, event.clientY);
    view.x += before.x - after.x; view.y += before.y - after.y;
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
    searchResults.querySelectorAll("[data-node]").forEach((button) => button.addEventListener("click", () => selectNode(button.dataset.node)));
  }
  search.addEventListener("input", doSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { const first = searchResults.querySelector("[data-node]"); if (first) selectNode(first.dataset.node); }
    if (event.key === "Escape") searchResults.classList.add("hidden");
  });

  $("#panel-close").addEventListener("click", () => fitHome());
  $("#reset").addEventListener("click", () => fitHome());
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); fitHome(); });
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
    const node = { id, word, pos: "我的词", gloss, note: relation, x: center.x + Math.cos(angle) * 34, y: center.y + Math.sin(angle) * 34, size: 3.4 };
    personal.nodes.push(node);
    if (target) personal.edges.push({ a: id, b: target.id, label: relation || "我的联想" });
    savePersonal(); rebuildPersonal(); closeDialog(); event.currentTarget.reset(); selectNode(id);
  });

  $("#stats").textContent = `${GRAPH_META.eligible_count.toLocaleString()} 主词 · ${GRAPH_META.support_node_count} 支撑词 · ${GRAPH_META.layout_link_count.toLocaleString()} 制图线索`;
  window.addEventListener("resize", resize);
  resize();
})();
