/* maillage — 词网引擎 v2
 * 双层模型：
 *   星云层（默认）— 全部词以散点按词族聚成 4 个星座，建立"场"的组织感
 *   聚焦层（点击）— 一词居中，仅其直接关系以辐射辐条展开，
 *                   每条线中点带关系标签牌，点击邻居即"走"过去
 * 无依赖，手写物理 + 缓动，离线可用 */

"use strict";

/* 测试辅助：URL 带 ?snap 时跳过所有过渡动画，直接呈现终态（供无头截图验证布局） */
const SNAP = location.search.includes("snap");

/* ---------------- 用户自定义词：localStorage 持久化 ---------------- */
const CUSTOM_KEY = "maillage.custom.v1";

/* 必须在数据索引建立之前把自定义词/边并入 */
(function loadCustom() {
  try {
    const raw = localStorage.getItem(CUSTOM_KEY);
    if (!raw) return;
    const { nodes: cn = [], edges: ce = [] } = JSON.parse(raw);
    cn.forEach((n) => {
      NODES.push(n);
      if (n.cluster && CLUSTERS[n.cluster]) CLUSTERS[n.cluster].members.push(n.id);
    });
    ce.forEach((e) => EDGES.push(e));
  } catch (err) { /* 损坏的本地数据不影响启动 */ }
})();

function saveCustom() {
  const cn = NODES.filter((n) => n.isCustom)
    .map(({ id, gloss, note, isCustom, cluster }) => ({ id, pos: "", gloss, note, isCustom, cluster }));
  const ce = EDGES.filter((e) => e.isCustom && !e.removed)
    .map(({ a, b, type, label, isCustom }) => ({ a, b, type, label, isCustom }));
  localStorage.setItem(CUSTOM_KEY, JSON.stringify({ nodes: cn, edges: ce }));
}

/* ---------------- 数据索引 ---------------- */
const nodeData = new Map(NODES.map((n) => [n.id, n]));
const clusterOf = {};
Object.entries(CLUSTERS).forEach(([key, c]) => c.members.forEach((id) => (clusterOf[id] = key)));
const clusterKeys = Object.keys(CLUSTERS);

const adjacency = new Map(NODES.map((n) => [n.id, []]));
EDGES.forEach((e, i) => {
  e.key = e.a + "|" + e.b;
  e.el = null; e.chipEl = null;
  e.p = 0; e.targetP = 0; e.delay = 0;
  adjacency.get(e.a).push(i);
  adjacency.get(e.b).push(i);
});

/* 辐条排序：先词族，再语义，最后警示类 */
const TYPE_ORDER = ["fam", "syn", "axis", "drift", "ant", "cause", "trap"];

/* ---------------- DOM ---------------- */
const svg = document.getElementById("stage");
const defs = svg.querySelector("defs");
const world = document.getElementById("world");
const gEdges = document.getElementById("edges");
const gParticles = document.getElementById("particles");
const gNodes = document.getElementById("nodes");
const gClusters = document.getElementById("clusters");
const tooltip = document.getElementById("tooltip");
const hint = document.getElementById("hint");
const panel = document.getElementById("panel");
const panelContent = document.getElementById("panel-content");
const trailEl = document.getElementById("trail");

const SVGNS = "http://www.w3.org/2000/svg";
function mk(tag, attrs, parent) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(el);
  return el;
}

Object.entries(EDGE_TYPES).forEach(([type, t]) => {
  if (!t.arrow) return;
  const m = mk("marker", {
    id: "arr-" + type, viewBox: "0 0 10 10", refX: 9, refY: 5,
    markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse"
  }, defs);
  mk("path", { d: "M 0 1 L 9 5 L 0 9 z", fill: t.color }, m);
});

/* ---------------- 文字测量 ---------------- */
const measurer = document.createElement("canvas").getContext("2d");
function measurePill(id, pos) {
  measurer.font = "500 14.5px Geist, system-ui, sans-serif";
  const lw = measurer.measureText(id).width;
  measurer.font = "400 10px 'Geist Mono', ui-monospace, monospace";
  const pw = measurer.measureText(pos).width;
  return { lw, w: Math.ceil(lw + pw + 34), h: 30 };
}
function measureChip(text) {
  measurer.font = "500 10.5px Geist, system-ui, sans-serif";
  return Math.ceil(measurer.measureText(text).width) + 16;
}

/* ---------------- 视图 ---------------- */
const view = { tx: 0, ty: 0, k: 1 };
let viewAnim = null;
function applyView() {
  world.setAttribute("transform", `translate(${view.tx},${view.ty}) scale(${view.k})`);
}
function toWorld(sx, sy) {
  const r = svg.getBoundingClientRect();
  return { x: (sx - r.left - view.tx) / view.k, y: (sy - r.top - view.ty) / view.k };
}
function toScreen(wx, wy) {
  const r = svg.getBoundingClientRect();
  return { x: wx * view.k + view.tx + r.left, y: wy * view.k + view.ty + r.top };
}
function centerOn(wx, wy, k) {
  const r = svg.getBoundingClientRect();
  const tk = k || view.k;
  viewAnim = {
    from: { ...view },
    to: { tx: r.width / 2 - wx * tk, ty: r.height / 2 - wy * tk, k: tk },
    t0: performance.now(), dur: 600
  };
}

/* ---------------- 运行态 ---------------- */
const nodes = new Map();       // id -> 运行时节点（全部常驻）
const clusterAnchor = {};      // 词族锚点
let mode = "nebula";           // nebula | focus
let focusId = null;
let trail = [];
const visited = new Set();
const visitedOrder = [];       // 首次探访顺序，驱动历史边栏
let soloType = null;
const satelliteParent = new Map();  // 二度灰点 -> 它所属的一度词
const particles = [];
const ripples = [];
const clusterLabelEls = {};

/* ---------------- 节点 ---------------- */
function spawnNode(id, x, y) {
  const d = nodeData.get(id);
  const { lw, w, h } = measurePill(d.id, d.pos);
  const n = {
    id, x, y, vx: 0, vy: 0, tx: x, ty: y,
    home: { x, y }, w, h, lw,
    pillT: 0,            // 0 = 散点, 1 = 完整词卡
    dim: 1,              // 聚焦时非相关词变暗
    pinned: false
  };

  const g = mk("g", { class: "node" }, gNodes);
  // 散点形态
  n.dot = mk("circle", { class: "dot", r: 4.5 }, g);
  mk("circle", { class: "hit", r: 13, fill: "transparent" }, g);
  // 词卡形态
  const pill = mk("g", { class: "pill" }, g);
  n.rect = mk("rect", { x: -w / 2, y: -h / 2, width: w, height: h, rx: h / 2 }, pill);
  const label = mk("text", { class: "label", x: -w / 2 + 13, y: 3.5 }, pill);
  label.textContent = d.id;
  const pos = mk("text", { class: "pos", x: -w / 2 + 13 + lw + 8, y: 3 }, pill);
  pos.textContent = d.pos;
  n.pill = pill; n.el = g;

  g.addEventListener("pointerdown", (ev) => startNodeDrag(ev, n));
  g.addEventListener("click", (ev) => { ev.stopPropagation(); if (!dragMoved) onNodeClick(n); });
  g.addEventListener("pointerenter", (ev) => showTooltip(n, ev));
  g.addEventListener("pointermove", (ev) => moveTooltip(n, ev));
  g.addEventListener("pointerleave", hideTooltip);

  nodes.set(id, n);
  return n;
}

/* ---------------- 星云层物理 ---------------- */
let simTime = 0;
function nebulaPhysics() {
  simTime += 16;
  const arr = [...nodes.values()];
  arr.forEach((n, i) => {
    const a = clusterAnchor[clusterOf[n.id]];
    // 锚点引力：词族聚拢
    n.vx += (a.x - n.x) * 0.004;
    n.vy += (a.y - n.y) * 0.004;
    // 缓慢漂移：星云呼吸感
    n.vx += Math.sin(simTime * 0.0004 + i * 2.3) * 0.008;
    n.vy += Math.cos(simTime * 0.0005 + i * 1.7) * 0.008;
  });
  // 散点间斥力
  for (let i = 0; i < arr.length; i++) {
    for (let j = i + 1; j < arr.length; j++) {
      const a = arr[i], b = arr[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 0.01;
      const minD = 30;
      if (d < minD) {
        const f = ((minD - d) / minD) * 0.5;
        dx /= d; dy /= d;
        a.vx -= dx * f; a.vy -= dy * f;
        b.vx += dx * f; b.vy += dy * f;
      }
    }
  }
  arr.forEach((n) => {
    if (n.pinned) { n.vx = 0; n.vy = 0; return; }
    n.vx *= 0.88; n.vy *= 0.88;
    n.x += n.vx; n.y += n.vy;
    n.home.x = n.x; n.home.y = n.y;
  });
}

/* 聚焦层：参与者缓动到辐条位置，旁观者退回原处变暗 */
function focusEase() {
  nodes.forEach((n) => {
    if (n.pinned) return;
    if (SNAP) { n.x = n.tx; n.y = n.ty; return; }
    n.x += (n.tx - n.x) * 0.09;
    n.y += (n.ty - n.y) * 0.09;
  });
}

/* ---------------- 聚焦层 ---------------- */
function neighborsOf(id) {
  return adjacency.get(id)
    .map((ei) => {
      const e = EDGES[ei];
      return { id: e.a === id ? e.b : e.a, edge: e };
    })
    .filter((x) => !x.edge.removed);
}

function enterFocus(id, fromTrail) {
  const n = nodes.get(id);
  if (!n) return;

  if (!fromTrail) {
    if (trail[trail.length - 1] !== id) trail.push(id);
    if (trail.length > 8) trail = trail.slice(trail.length - 8);
  }
  visited.add(id);
  if (!visitedOrder.includes(id)) visitedOrder.push(id);
  renderHistory();

  const fromNebula = mode === "nebula";
  mode = "focus";
  focusId = id;
  hint.classList.add("gone");

  // 只有从星云进入时才更新"归处"；聚焦间游走时保留原星云位置，否则旁观者会滞留在旧中心周围
  if (fromNebula) nodes.forEach((m) => { m.home.x = m.x; m.home.y = m.y; });

  // 中心词定在原位，邻居按关系类型排序后均匀辐散
  const cx = n.x, cy = n.y;
  n.tx = cx; n.ty = cy;
  const nbrs = neighborsOf(id).sort(
    (a, b) => TYPE_ORDER.indexOf(a.edge.type) - TYPE_ORDER.indexOf(b.edge.type)
  );
  const count = nbrs.length;
  const R = count <= 4 ? 215 : 215 + (count - 4) * 26;
  const inEgo = new Set([id, ...nbrs.map((x) => x.id)]);
  nbrs.forEach(({ id: nid }, i) => {
    const a = -Math.PI / 2 + (i / count) * Math.PI * 2;
    const m = nodes.get(nid);
    m.tx = cx + Math.cos(a) * R;
    m.ty = cy + Math.sin(a) * R;
    m._spokeAngle = a;
  });

  // 二度关系：挂在一度词外侧的卫星灰点（不展开，仅预显）
  satelliteParent.clear();
  nbrs.forEach(({ id: nid }) => {
    neighborsOf(nid).forEach(({ id: sid }) => {
      if (inEgo.has(sid) || satelliteParent.has(sid)) return;
      satelliteParent.set(sid, nid);
    });
  });
  const byParent = new Map();
  satelliteParent.forEach((pid, sid) => {
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid).push(sid);
  });
  byParent.forEach((sats, pid) => {
    const p = nodes.get(pid);
    const base = p._spokeAngle;
    sats.forEach((sid, i) => {
      const spread = (i - (sats.length - 1) / 2) * 0.38;
      const a = base + spread;
      const m = nodes.get(sid);
      m.tx = p.tx + Math.cos(a) * 62;
      m.ty = p.ty + Math.sin(a) * 62;
    });
  });

  // 状态：pillT / dim 目标；非参与者退回星云原位
  nodes.forEach((m) => {
    const participant = inEgo.has(m.id) || satelliteParent.has(m.id);
    m.pillTarget = inEgo.has(m.id) ? 1 : 0;
    m.dimTarget = inEgo.has(m.id) ? 1 : satelliteParent.has(m.id) ? 0.6 : 0.14;
    if (!participant) { m.tx = m.home.x; m.ty = m.home.y; }
  });

  syncEdges();
  setActiveNode(id);
  ripple(cx, cy);
  centerOn(cx, cy, 1);
  renderTrail();
  updateStats();
  resetBtn.classList.remove("hidden");
  history.replaceState(null, "", "#focus=" + encodeURIComponent(id));
}

function exitFocus() {
  mode = "nebula";
  focusId = null;
  trail = [];
  satelliteParent.clear();
  nodes.forEach((m) => {
    m.pillTarget = 0;
    m.dimTarget = 1;
    m.tx = m.home.x; m.ty = m.home.y;
  });
  syncEdges();
  setActiveNode(null);
  renderTrail();
  renderHistory();
  updateStats();
  resetBtn.classList.add("hidden");
  history.replaceState(null, "", location.pathname);
  centerOn(0, 0, Math.min(view.k, 0.95));
}

function onNodeClick(n) {
  if (mode === "focus" && n.id === focusId) { exitFocus(); return; }
  enterFocus(n.id);
}

function setActiveNode(id) {
  nodes.forEach((m) => m.el.classList.toggle("active", m.id === id));
  if (id) showPanel(id); else panel.classList.add("hidden");
}

/* ---------------- 边（辐条 + 卫星发线） ---------------- */
function edgeWanted(e) {
  if (e.removed) return false;
  if (mode !== "focus") return false;
  if (e.a === focusId || e.b === focusId) return true;                    // 辐条
  return satelliteParent.get(e.a) === e.b || satelliteParent.get(e.b) === e.a; // 发线
}

function syncEdges() {
  const now = performance.now();
  // 全量重建：边的角色（辐条/发线）在焦点切换时会变，重建保证样式与角色一致
  EDGES.forEach((e) => {
    if (e.el) { e.el.remove(); e.el = null; }
    if (e.chipEl) { e.chipEl.remove(); e.chipEl = null; }
    if (e.markEl) { e.markEl.remove(); e.markEl = null; }
    e.p = 0; e.targetP = 0; e.delay = 0;
  });
  let i = 0;
  EDGES.forEach((e) => {
    if (edgeWanted(e) && !e.el) {
      const isSpoke = e.a === focusId || e.b === focusId;
      e.el = mk("line", { class: isSpoke ? "edge" : "edge faint" }, gEdges);
      if (isSpoke) {
        e.el.setAttribute("stroke", EDGE_TYPES[e.type].color);
        e.el.setAttribute("stroke-width", 1.6);
        if (EDGE_TYPES[e.type].dash) e.el.setAttribute("stroke-dasharray", EDGE_TYPES[e.type].dash);
        if (EDGE_TYPES[e.type].arrow) e.el.setAttribute("marker-end", `url(#arr-${e.type})`);
        if (soloType && e.type !== soloType) e.el.classList.add("dimmed");
      }
      e.p = 0; e.targetP = 1;
      e.delay = isSpoke ? now + 120 + i * 110 : now + 500 + i * 30;  // 发线随辐条之后淡入
      i++;
      if (isSpoke && e.type === "trap") {
        // 形近陷阱：红线 + 正中央一个 ×（带白底光晕，压在红线上）
        e.markEl = mk("g", { class: "trap-mark" }, gEdges);
        const d = "M -4.5 -4.5 L 4.5 4.5 M -4.5 4.5 L 4.5 -4.5";
        mk("path", { d, stroke: "#ffffff", "stroke-width": 6, fill: "none", "stroke-linecap": "round" }, e.markEl);
        mk("path", { d, stroke: EDGE_TYPES.trap.color, "stroke-width": 2, fill: "none", "stroke-linecap": "round" }, e.markEl);
      } else if (isSpoke) {
        // 关系标签牌（仅辐条，陷阱除外）
        const t = EDGE_TYPES[e.type];
        const text = t.name + (e.label ? " · " + e.label : "");
        const cw = measureChip(text);
        const chip = mk("g", { class: "chip" }, gEdges);
        mk("rect", { x: -cw / 2, y: -10, width: cw, height: 20, rx: 10, stroke: t.color }, chip);
        const ct = mk("text", { "text-anchor": "middle", y: 3.5, fill: t.color }, chip);
        ct.textContent = text;
        e.chipEl = chip;
      }
    } else if (!edgeWanted(e) && e.el) {
      e.targetP = 0; e.delay = 0;
    }
  });
}

function pruneEdges() {
  EDGES.forEach((e) => {
    if (e.el && e.targetP === 0 && e.p <= 0.01) {
      e.el.remove(); e.el = null;
      if (e.chipEl) { e.chipEl.remove(); e.chipEl = null; }
      if (e.markEl) { e.markEl.remove(); e.markEl = null; }
    }
  });
}

/* ---------------- 粒子（涟漪） ---------------- */
function ripple(x, y) {
  const el = mk("circle", { class: "particle", fill: "none", stroke: "#171717", "stroke-width": 1 }, gParticles);
  ripples.push({ x, y, r: 8, el });
}

/* ---------------- 渲染循环 ---------------- */
function frame(now) {
  if (viewAnim) {
    if (SNAP) {
      Object.assign(view, viewAnim.to);
      viewAnim = null;
    } else {
      const t = Math.min(1, (now - viewAnim.t0) / viewAnim.dur);
      const e = 1 - Math.pow(1 - t, 3);
      view.tx = viewAnim.from.tx + (viewAnim.to.tx - viewAnim.from.tx) * e;
      view.ty = viewAnim.from.ty + (viewAnim.to.ty - viewAnim.from.ty) * e;
      view.k = viewAnim.from.k + (viewAnim.to.k - viewAnim.from.k) * e;
      if (t === 1) viewAnim = null;
    }
  }

  if (mode === "nebula") nebulaPhysics(); else focusEase();

  // 节点形态插值
  nodes.forEach((n) => {
    const pt = n.pillTarget == null ? (mode === "nebula" ? 0 : n.pillT) : n.pillTarget;
    n.pillT += (pt - n.pillT) * 0.14;
    if (SNAP || Math.abs(n.pillT - pt) < 0.005) n.pillT = pt;
    const dim = n.dimTarget == null ? 1 : n.dimTarget;
    n.dim += (dim - n.dim) * 0.12;
    if (SNAP) n.dim = dim;

    n.el.setAttribute("transform", `translate(${n.x},${n.y})`);
    n.el.style.opacity = n.dim;
    const pillS = Math.max(0.001, n.pillT);
    n.pill.setAttribute("transform", `scale(${pillS})`);
    n.pill.style.opacity = n.pillT;
    n.dot.setAttribute("r", 4.5 * (1 - n.pillT * 0.7));
    n.dot.style.opacity = 1 - n.pillT;
  });

  // 辐条生长 + 标签牌跟随
  EDGES.forEach((e) => {
    if (!e.el) return;
    if (SNAP) e.p = e.targetP;
    else if (now >= e.delay) {
      const dir = e.targetP > e.p ? 1 : -1;
      e.p += dir * 0.06;
      if ((dir > 0 && e.p >= e.targetP) || (dir < 0 && e.p <= e.targetP)) e.p = e.targetP;
    }
    const a = nodes.get(e.a), b = nodes.get(e.b);
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.hypot(dx, dy) || 0.01;
    const ux = dx / d, uy = dy / d;
    const trimOf = (nd) => (nd.pillT > 0.5 ? nd.w / 2 * 0.72 + 4 : 7);
    const trimA = trimOf(a);
    const trimB = trimOf(b) + (EDGE_TYPES[e.type].arrow ? 6 : 0);
    const x1 = a.x + ux * trimA, y1 = a.y + uy * trimA;
    const x2 = a.x + ux * Math.max(trimA + 8, d - trimB), y2 = a.y + uy * Math.max(trimA + 8, d - trimB);
    const ex = x1 + (x2 - x1) * e.p, ey = y1 + (y2 - y1) * e.p;
    e.el.setAttribute("x1", x1); e.el.setAttribute("y1", y1);
    e.el.setAttribute("x2", ex); e.el.setAttribute("y2", ey);
    if (e.markEl) {
      // × 固定在线段中点，每帧跟随
      const mx = (x1 + ex) / 2, my = (y1 + ey) / 2;
      e.markEl.setAttribute("transform", `translate(${mx},${my})`);
      e.markEl.style.opacity = Math.max(0, (e.p - 0.5) / 0.5);
    }
    if (e.chipEl) {
      // 标签牌放在已生长部分的 60% 处，随线生长滑出
      const mx = x1 + (ex - x1) * 0.6, my = y1 + (ey - y1) * 0.6;
      e.chipEl.setAttribute("transform", `translate(${mx},${my})`);
      e.chipEl.style.opacity = Math.max(0, (e.p - 0.35) / 0.65);
    }
  });
  pruneEdges();

  // 词族标签：星云层清晰，聚焦层隐去
  const labelTarget = mode === "nebula" ? 0.85 : 0;
  Object.values(clusterLabelEls).forEach((el) => {
    const cur = parseFloat(el.style.opacity || 0);
    el.style.opacity = cur + (labelTarget - cur) * 0.1;
  });

  // 粒子
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.life++;
    p.x += p.vx; p.y += p.vy;
    p.vx *= 0.94; p.vy *= 0.94;
    const t = p.life / p.max;
    if (t >= 1) { p.el.remove(); particles.splice(i, 1); continue; }
    p.el.setAttribute("cx", p.x); p.el.setAttribute("cy", p.y);
    p.el.setAttribute("r", p.r * (1 - t * 0.6));
    p.el.setAttribute("fill", p.color);
    p.el.setAttribute("opacity", 0.85 * (1 - t));
  }
  for (let i = ripples.length - 1; i >= 0; i--) {
    const r = ripples[i];
    r.r += 1.7;
    const o = 1 - r.r / 54;
    if (o <= 0) { r.el.remove(); ripples.splice(i, 1); continue; }
    r.el.setAttribute("cx", r.x); r.el.setAttribute("cy", r.y);
    r.el.setAttribute("r", r.r);
    r.el.setAttribute("opacity", o * 0.4);
  }

  applyView();
  requestAnimationFrame(frame);
}

/* ---------------- 悬浮卡 ---------------- */
function showTooltip(n, ev) {
  if (mode === "focus" && n.id === focusId) return;  // 中心词信息已在面板
  const d = nodeData.get(n.id);
  tooltip.innerHTML = `<span class="tw">${d.id}</span><span class="tp">${d.pos}</span><div class="tg">${d.gloss}</div>`;
  tooltip.classList.remove("hidden");
  moveTooltip(n, ev);
}
function moveTooltip(n) {
  const s = toScreen(n.x, n.y);
  const vp = document.getElementById("viewport").getBoundingClientRect();
  let x = s.x - vp.left + 18, y = s.y - vp.top - 24;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > vp.width - 12) x = s.x - vp.left - r.width - 18;
  if (y + r.height > vp.height - 12) y = vp.height - r.height - 12;
  tooltip.style.left = x + "px";
  tooltip.style.top = y + "px";
}
function hideTooltip() { tooltip.classList.add("hidden"); }

/* ---------------- 详情面板 ---------------- */
function lineSample(type) {
  const t = EDGE_TYPES[type];
  const dash = t.dash ? ` stroke-dasharray="${t.dash}"` : "";
  const x = type === "trap" ? `<path d="M 10 1 L 16 7 M 10 7 L 16 1" stroke="${t.color}" stroke-width="1.5" stroke-linecap="round"/>` : "";
  return `<svg width="26" height="8"><line x1="1" y1="4" x2="25" y2="4" stroke="${t.color}" stroke-width="1.5"${dash}/>${x}</svg>`;
}

function showPanel(id) {
  const d = nodeData.get(id);
  const rows = neighborsOf(id).map(({ id: other, edge: e }) => {
    const od = nodeData.get(other);
    const t = EDGE_TYPES[e.type];
    return `<button class="rel-row" data-target="${other}">
      ${lineSample(e.type)}
      <span class="rw">${other}</span>
      <span class="rl">${t.name}${e.label ? " · " + e.label : ""}<br>${od.gloss}</span>
    </button>`;
  }).join("");

  panelContent.innerHTML = `
    <div class="pw">${d.id}</div>
    <div class="pp">${[d.pos, CLUSTERS[clusterOf[id]].name].filter(Boolean).join(" · ")}</div>
    <div class="pg">${d.gloss}</div>
    <div class="pn">${d.note}</div>
    <div class="rel-title">关系 · ${adjacency.get(id).filter((ei) => !EDGES[ei].removed).length}</div>
    ${rows}
    ${d.isCustom ? '<div class="rel-title">管理</div><button id="del-word" class="btn ghost">从词网移除</button>' : ""}`;
  panel.classList.remove("hidden");
  panelContent.querySelectorAll(".rel-row").forEach((b) =>
    b.addEventListener("click", () => enterFocus(b.dataset.target)));
  const delBtn = document.getElementById("del-word");
  if (delBtn) delBtn.addEventListener("click", () => removeCustomWord(id));
}

document.getElementById("panel-close").addEventListener("click", () => panel.classList.add("hidden"));

/* ---------------- 历史边栏 ---------------- */
const historyEl = document.getElementById("history");
const historyItems = document.getElementById("history-items");

function renderHistory() {
  if (!visitedOrder.length) { historyEl.classList.add("hidden"); return; }
  historyItems.innerHTML = visitedOrder.map((id) =>
    `<button class="hist-chip${id === focusId ? " current" : ""}" data-id="${id}">${id}</button>`
  ).join("");
  historyEl.classList.remove("hidden");
  historyItems.querySelectorAll(".hist-chip").forEach((b) =>
    b.addEventListener("click", () => enterFocus(b.dataset.id)));
}

/* ---------------- 足迹链 ---------------- */
function renderTrail() {
  if (!trail.length) { trailEl.classList.add("hidden"); trailEl.innerHTML = ""; return; }
  trailEl.innerHTML = trail.map((id, i) =>
    `<button class="trail-chip${i === trail.length - 1 ? " current" : ""}" data-i="${i}">${id}</button>`
  ).join('<span class="trail-sep">→</span>');
  trailEl.classList.remove("hidden");
  trailEl.querySelectorAll(".trail-chip").forEach((b) =>
    b.addEventListener("click", () => {
      const i = +b.dataset.i;
      const id = trail[i];
      trail = trail.slice(0, i + 1);
      enterFocus(id, true);
    }));
}

/* ---------------- 图例 ---------------- */
const legendItems = document.getElementById("legend-items");
Object.entries(EDGE_TYPES).forEach(([type, t]) => {
  const item = document.createElement("div");
  item.className = "legend-item";
  const x = type === "trap" ? `<path d="M 14 1 L 20 9 M 14 9 L 20 1" stroke="${t.color}" stroke-width="1.5" stroke-linecap="round" fill="none"/>` : "";
  item.innerHTML = `<svg width="34" height="10"><line x1="2" y1="5" x2="32" y2="5" stroke="${t.color}" stroke-width="1.5"${t.dash ? ` stroke-dasharray="${t.dash}"` : ""}/>${x}</svg><span>${t.name}</span>`;
  item.addEventListener("click", () => {
    soloType = soloType === type ? null : type;
    legendItems.querySelectorAll(".legend-item").forEach((el) => el.classList.remove("solo"));
    if (soloType) item.classList.add("solo");
    EDGES.forEach((e) => {
      if (e.el) e.el.classList.toggle("dimmed", !!soloType && e.type !== soloType);
      if (e.chipEl) e.chipEl.classList.toggle("dimmed", !!soloType && e.type !== soloType);
    });
  });
  legendItems.appendChild(item);
});

/* ---------------- 搜索 ---------------- */
const searchInput = document.getElementById("search");
const searchResults = document.getElementById("search-results");
const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

searchInput.addEventListener("input", () => {
  const q = norm(searchInput.value.trim());
  if (!q) { searchResults.classList.add("hidden"); return; }
  const hits = NODES.filter((n) => norm(n.id).includes(q)).slice(0, 6);
  if (!hits.length) { searchResults.classList.add("hidden"); return; }
  searchResults.innerHTML = hits.map((n) =>
    `<button class="search-item" data-id="${n.id}">
       <span>${n.id}</span><span class="pos">${n.pos}</span>
       <span class="g">${n.gloss.split("；")[0]}</span>
     </button>`).join("");
  searchResults.classList.remove("hidden");
  searchResults.querySelectorAll(".search-item").forEach((b) =>
    b.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      enterFocus(b.dataset.id);
      searchResults.classList.add("hidden");
      searchInput.blur();
    }));
});
searchInput.addEventListener("blur", () => setTimeout(() => searchResults.classList.add("hidden"), 150));
searchInput.addEventListener("keydown", (ev) => { if (ev.key === "Escape") searchInput.blur(); });

/* ---------------- 平移 / 缩放 / 拖拽 ---------------- */
let panning = false, panStart = null;
let dragNode = null, dragMoved = false;

svg.addEventListener("pointerdown", (ev) => {
  panning = true; panStart = { x: ev.clientX, y: ev.clientY, tx: view.tx, ty: view.ty, moved: false };
  svg.classList.add("panning");
});
window.addEventListener("pointermove", (ev) => {
  if (dragNode) {
    const w = toWorld(ev.clientX, ev.clientY);
    if (Math.hypot(w.x - dragNode.x, w.y - dragNode.y) > 3) dragMoved = true;
    dragNode.x = w.x; dragNode.y = w.y;
    if (mode === "nebula") { dragNode.home.x = w.x; dragNode.home.y = w.y; }
    return;
  }
  if (panning && panStart) {
    const dx = ev.clientX - panStart.x, dy = ev.clientY - panStart.y;
    if (Math.hypot(dx, dy) > 4) panStart.moved = true;
    view.tx = panStart.tx + dx;
    view.ty = panStart.ty + dy;
  }
});
window.addEventListener("pointerup", () => {
  panning = false;
  svg.classList.remove("panning");
  if (dragNode) { dragNode.pinned = false; dragNode = null; setTimeout(() => (dragMoved = false), 0); }
});
svg.addEventListener("click", (ev) => {
  // 点击空白处：回到星云
  if (mode === "focus" && panStart && !panStart.moved && ev.target === svg) exitFocus();
});

function startNodeDrag(ev, n) {
  ev.stopPropagation();
  dragNode = n; n.pinned = true; dragMoved = false;
}

svg.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const r = svg.getBoundingClientRect();
  const mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const k2 = Math.min(2.6, Math.max(0.35, view.k * Math.exp(-ev.deltaY * 0.0012)));
  view.tx = mx - ((mx - view.tx) * k2) / view.k;
  view.ty = my - ((my - view.ty) * k2) / view.k;
  view.k = k2;
}, { passive: false });

/* ---------------- 添加单词（P2 入口） ---------------- */
const fab = document.getElementById("fab");
const addDialog = document.getElementById("add-dialog");
const addWordEl = document.getElementById("add-word");
const addGlossEl = document.getElementById("add-gloss");
const addNoteEl = document.getElementById("add-note");
const addSuggEl = document.getElementById("add-sugg");
const addRelsEl = document.getElementById("add-rels");
let dictLoading = false;

function lazyLoadDict() {
  if (typeof DICT !== "undefined" || dictLoading) return;
  dictLoading = true;
  const s = document.createElement("script");
  s.src = "dict.js";
  document.body.appendChild(s);
}

/* 一行关系：挂载词（输入自匹配）+ 关系类型 + 删除 */
function makeRelRow(anchorId) {
  const row = document.createElement("div");
  row.className = "rel-edit";
  row.innerHTML = `
    <input class="rel-anchor" type="text" placeholder="挂到哪个词…" autocomplete="off" spellcheck="false"
           value="${anchorId || ""}">
    <select class="rel-type">${Object.entries(EDGE_TYPES)
      .map(([type, t]) => `<option value="${type}">${t.name}</option>`).join("")}</select>
    <button class="rel-x" type="button" aria-label="移除">×</button>
    <div class="sugg hidden"></div>`;
  const input = row.querySelector(".rel-anchor");
  const sugg = row.querySelector(".sugg");
  input.addEventListener("input", () => {
    const q = norm(input.value.trim());
    if (!q) { sugg.classList.add("hidden"); return; }
    const hits = NODES.filter((n) => norm(n.id).includes(q) && n.id !== addWordEl.value.trim()).slice(0, 5);
    if (!hits.length) { sugg.classList.add("hidden"); return; }
    sugg.innerHTML = hits.map((n) =>
      `<button class="sugg-item" data-w="${n.id}">
         <span>${n.id}</span><span class="sg">${n.gloss.split("；")[0]}</span>
       </button>`).join("");
    sugg.classList.remove("hidden");
    sugg.querySelectorAll(".sugg-item").forEach((b) =>
      b.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        input.value = b.dataset.w;
        sugg.classList.add("hidden");
      }));
  });
  input.addEventListener("blur", () => setTimeout(() => sugg.classList.add("hidden"), 150));
  row.querySelector(".rel-x").addEventListener("click", () => {
    if (addRelsEl.children.length > 1) row.remove();
    else input.value = "";
  });
  addRelsEl.appendChild(row);
  return row;
}

function openAddDialog() {
  addRelsEl.innerHTML = "";
  makeRelRow(focusId || trail[trail.length - 1] || "");
  addWordEl.value = ""; addGlossEl.value = ""; addNoteEl.value = "";
  addSuggEl.classList.add("hidden");
  addDialog.classList.remove("hidden");
  lazyLoadDict();
  addWordEl.focus();
}

function closeAddDialog() { addDialog.classList.add("hidden"); }

addWordEl.addEventListener("input", () => {
  if (typeof DICT === "undefined") return;
  const q = norm(addWordEl.value.trim());
  if (q.length < 2) { addSuggEl.classList.add("hidden"); return; }
  const keys = Object.keys(DICT);
  const starts = keys.filter((k) => norm(k).startsWith(q)).slice(0, 4);
  const inside = keys.filter((k) => !norm(k).startsWith(q) && norm(k).includes(q)).slice(0, 3);
  const hits = [...starts, ...inside];
  if (!hits.length) { addSuggEl.classList.add("hidden"); return; }
  addSuggEl.innerHTML = hits.map((k) =>
    `<button class="sugg-item" data-w="${k}" data-g="${DICT[k].join("；")}">
       <span>${k}</span><span class="sg">${DICT[k].join(" / ")}</span>
     </button>`).join("");
  addSuggEl.classList.remove("hidden");
  addSuggEl.querySelectorAll(".sugg-item").forEach((b) =>
    b.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      addWordEl.value = b.dataset.w;
      addGlossEl.value = b.dataset.g;
      addSuggEl.classList.add("hidden");
    }));
});
addWordEl.addEventListener("blur", () => setTimeout(() => addSuggEl.classList.add("hidden"), 150));

document.getElementById("add-rel-more").addEventListener("click", () => makeRelRow(""));

/* rels: [{ anchor, type }] —— 一个词可以同时挂多个锚点 */
function addCustomWord(word, gloss, rels, note) {
  const cluster = clusterOf[rels[0].anchor];
  const nd = { id: word, pos: "", gloss: gloss || "（未填释义）",
               note: note || "你手动添加的词。", isCustom: true, cluster };
  NODES.push(nd);
  nodeData.set(word, nd);
  CLUSTERS[cluster].members.push(word);
  clusterOf[word] = cluster;
  adjacency.set(word, []);
  rels.forEach(({ anchor, type }) => {
    const e = { a: word, b: anchor, type, label: note || undefined, isCustom: true,
                key: word + "|" + anchor, el: null, chipEl: null, p: 0, targetP: 0, delay: 0 };
    EDGES.push(e);
    adjacency.get(word).push(EDGES.length - 1);
    adjacency.get(anchor).push(EDGES.length - 1);
  });

  const a = clusterAnchor[cluster];
  const ang = Math.random() * Math.PI * 2, rr = 24 + Math.random() * 50;
  const n = spawnNode(word, a.x + Math.cos(ang) * rr, a.y + Math.sin(ang) * rr);
  n.home.x = n.x; n.home.y = n.y;
  if (mode === "focus") { n.pillTarget = 0; n.dimTarget = 0.14; }

  saveCustom();
  // 正聚焦在某个挂载点上：重排辐条，新边立刻生长出来
  if (mode === "focus" && rels.some((r) => r.anchor === focusId)) enterFocus(focusId, true);
  else ripple(n.x, n.y);
}

function removeCustomWord(id) {
  const nd = nodeData.get(id);
  if (!nd || !nd.isCustom) return;
  adjacency.get(id).forEach((ei) => { EDGES[ei].removed = true; EDGES[ei].targetP = 0; });
  NODES.splice(NODES.indexOf(nd), 1);
  nodeData.delete(id);
  const cm = CLUSTERS[nd.cluster].members;
  cm.splice(cm.indexOf(id), 1);
  delete clusterOf[id];
  const rn = nodes.get(id);
  if (rn) { rn.el.remove(); nodes.delete(id); }
  adjacency.delete(id);
  saveCustom();
  if (focusId === id) exitFocus();
  else if (mode === "focus") enterFocus(focusId, true);
}

fab.addEventListener("click", openAddDialog);
document.getElementById("add-cancel").addEventListener("click", closeAddDialog);
addDialog.querySelector(".dlg-mask").addEventListener("click", closeAddDialog);
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !addDialog.classList.contains("hidden")) closeAddDialog();
});
document.getElementById("add-ok").addEventListener("click", () => {
  const word = addWordEl.value.trim();
  if (!word) { addWordEl.focus(); return; }
  if (nodeData.has(word)) { addWordEl.focus(); addWordEl.style.boxShadow = "rgba(225,29,72,0.5) 0 0 0 2px"; setTimeout(() => (addWordEl.style.boxShadow = ""), 900); return; }
  // 收集有效关系行：挂载词必须已存在；同一锚点去重
  const seen = new Set();
  const rels = [];
  addRelsEl.querySelectorAll(".rel-edit").forEach((row) => {
    const anchor = row.querySelector(".rel-anchor").value.trim();
    const type = row.querySelector(".rel-type").value;
    if (anchor && nodeData.has(anchor) && anchor !== word && !seen.has(anchor)) {
      seen.add(anchor);
      rels.push({ anchor, type });
    }
  });
  if (!rels.length) {
    const first = addRelsEl.querySelector(".rel-anchor");
    first.focus();
    first.style.boxShadow = "rgba(225,29,72,0.5) 0 0 0 2px";
    setTimeout(() => (first.style.boxShadow = ""), 900);
    return;
  }
  addCustomWord(word, addGlossEl.value.trim(), rels, addNoteEl.value.trim());
  closeAddDialog();
});

/* ---------------- 顶栏 ---------------- */
const resetBtn = document.getElementById("reset");
resetBtn.addEventListener("click", () => exitFocus());

function updateStats() {
  const liveEdges = EDGES.filter((e) => !e.removed).length;
  document.getElementById("stats").textContent =
    `${NODES.length} 词 · ${liveEdges} 关系 · ${Object.keys(CLUSTERS).length} 词族 · 已探访 ${visited.size}`;
}

/* ---------------- 初始化 ---------------- */
function init() {
  const r = svg.getBoundingClientRect();
  const radius = Math.min(r.width, r.height) * 0.36;
  clusterKeys.forEach((key, i) => {
    const a = -Math.PI / 4 - (i / clusterKeys.length) * Math.PI * 2;
    clusterAnchor[key] = { x: Math.cos(a) * radius, y: Math.sin(a) * radius * 0.8 };
    const label = mk("text", {
      class: "cluster-label", "text-anchor": "middle",
      x: clusterAnchor[key].x, y: clusterAnchor[key].y - 92
    }, gClusters);
    label.textContent = CLUSTERS[key].name;
    label.style.opacity = 0.85;
    clusterLabelEls[key] = label;
  });

  NODES.forEach((nd) => {
    const a = clusterAnchor[clusterOf[nd.id]];
    const ang = Math.random() * Math.PI * 2, rr = 20 + Math.random() * 55;
    spawnNode(nd.id, a.x + Math.cos(ang) * rr, a.y + Math.sin(ang) * rr);
  });

  view.tx = r.width / 2; view.ty = r.height / 2; view.k = 0.95;
  updateStats();

  // 深链：#focus=xxx 直接聚焦
  const m = location.hash.match(/focus=([^\s&]+)/);
  if (m && nodeData.has(decodeURIComponent(m[1]))) {
    setTimeout(() => enterFocus(decodeURIComponent(m[1])), 400);
  }

  requestAnimationFrame(frame);
}

if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => {
    nodes.forEach((n) => {
      const d = nodeData.get(n.id);
      const mm = measurePill(d.id, d.pos);
      n.w = mm.w; n.lw = mm.lw;
      n.rect.setAttribute("x", -mm.w / 2);
      n.rect.setAttribute("width", mm.w);
    });
  });
}

init();
