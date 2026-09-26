import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import LangToggle from '../components/LangToggle';
import { api } from '../lib/api';

// ── Node visual config ────────────────────────────────────────────────────────
// The API returns Persona / Identifier / Post / Listing / Case nodes, and an
// Identifier carries an identifier_type. Key on the real shapes so every node
// gets a deliberate style instead of falling through to the default grey.
// Every entity type gets its own hue. These previously collided (ONION_URL
// vs hidden_service, EMAIL vs certificate), which made two legend rows share a
// swatch. Hues are spread around the wheel and kept dark enough to hold up on
// the near-white canvas (#F8F7F5).
const IDENTIFIER_STYLE = {
  PGP_KEY:      { color: '#C2410C', key: 'gPgpKey',    r: 6 },
  BTC_ADDRESS:  { color: '#9F1239', key: 'gWallet',    r: 6 },
  ONION_URL:    { color: '#A16207', key: 'gOnionUrl',  r: 6 },
  EMAIL:        { color: '#BE123C', key: 'gEmail',     r: 6 },
};

const NODE_CFG = {
  persona:        { color: '#44403C', key: 'gPersona',      r: 9 },
  actor:          { color: '#44403C', key: 'gPersona',      r: 9 },
  identifier:     { color: '#78716C', key: 'gIdentifier',   r: 6 },
  post:           { color: '#A8A29E', key: 'gPost',         r: 5 },
  listing:        { color: '#B45309', key: 'gListing',      r: 5 },
  case:           { color: '#1C1917', key: 'gCase',         r: 11 },
  server:         { color: '#0F766E', key: 'gServer',       r: 6 },
  certificate:    { color: '#365314', key: 'gCertificate',  r: 5 },
  hidden_service: { color: '#7F1D1D', key: 'gHiddenService', r: 7 },
};

// Suspected-operator clusters. Personas that correlation believes are the same
// person share a colour, so "who is really who" is readable at a glance.
// Ordered so neighbouring entries differ in hue and in value.
const COMMUNITY_COLORS = [
  '#B91C1C', '#C2410C', '#A16207', '#4D7C0F', '#15803D',
  '#047857', '#7F1D1D', '#65A30D', '#166534', '#78716C',
];

const EDGE_STYLE = {
  CORRELATED_WITH:     { color: '#15803D', dash: null, key: 'gCorrelatedWith'  },
  COORDINATED_WITH:    { color: '#9F1239', dash: '5 3',  key: 'gCoordinatedWith' },
  AUTHORED:            { color: '#15803D', dash: null, key: 'gAuthored'        },
  PUBLISHED:           { color: '#B45309', dash: null, key: 'gPublished'       },
  USES_IDENTIFIER:     { color: '#A16207', dash: null, key: 'gUses'            },
  MENTIONS_IDENTIFIER: { color: '#78716C', dash: '2 3',  key: 'gMentions'        },
  PART_OF:             { color: '#D6D3D1', dash: '1 4',  key: 'gBelongsTo'       },
  HOSTED_ON:           { color: '#4D7C0F', dash: null, key: 'gHostedOn'        },
  SERVES_CERTIFICATE:  { color: '#365314', dash: null, key: 'gServesCert'      },
  CO_HOSTED_SERVER:    { color: '#BE123C', dash: '5 3',  key: 'gCoHosted'        },
};

const EDGE_COLOR = {
  high:    '#15803D',
  medium:  '#B45309',
  low:     '#78716C',
  default: '#D6D3D1',
};

// Labels resolve through i18n at render time, so the legend, the description
// panel and the edge labels all follow the active language. `key` is stable
// across languages, which is what the legend groups on.
function nodeStyle(node, t) {
  const type = String(node?.type || '').toLowerCase();
  const label = (cfg, fallback) => (cfg.key && t?.[cfg.key]) || fallback;
  if (type === 'identifier') {
    const sub = IDENTIFIER_STYLE[node.identifier_type];
    if (sub) return { ...sub, label: label(sub, node.identifier_type) };
    return { color: '#78716C', r: 6, label: node.identifier_type || t?.gIdentifier || 'Identifier' };
  }
  const cfg = NODE_CFG[type];
  if (cfg) return { ...cfg, label: label(cfg, node?.type) };
  return { color: '#A8A29E', r: 6, label: node?.type || t?.gEntity || 'Entity' };
}

function edgeStyle(edge, t) {
  const label = edge?.label || '';
  if (label === 'CORRELATED_WITH') {
    // `confidence` is the 0..1 link strength; `score` is a 0..100 stylometry
    // distance, so it must never be read as a 0..1 ratio.
    const confidence = Number(edge.confidence ?? 0);
    const pct = Math.round(confidence * 100);
    const color = confidence >= 0.8 ? EDGE_COLOR.high : confidence >= 0.5 ? EDGE_COLOR.medium : EDGE_COLOR.low;
    const tpl = t?.gCorrelatedWith || 'correlated {pct}%';
    return { color, dash: null, label: tpl.replace('{pct}', pct) };
  }
  const cfg = EDGE_STYLE[label];
  if (cfg) return { ...cfg, label: (cfg.key && t?.[cfg.key]) || cfg.key };
  return { color: EDGE_COLOR.default, dash: null, label: label.toLowerCase().replace(/_/g, ' ') };
}

// ── Suspected-operator communities ───────────────────────────────────────────
// Correlation already tells us which persona pairs look like the same person.
// Label propagation turns those pairwise opinions into groups, so the graph can
// answer "these four handles are probably one operator" at a glance instead of
// making the analyst trace edges by hand.

// Edges that express "these two are the same person". Weak stylometric and
// temporal signals are deliberately excluded: they are evidence, not identity.
const IDENTITY_EDGES = new Set(['COORDINATED_WITH', 'CORRELATED_WITH']);
// Relationships that mean "this persona is tied to that shared attribute".
const ATTRIBUTE_EDGES = new Set(['USES_IDENTIFIER', 'MENTIONS_IDENTIFIER']);

function detectCommunities(nodes, edges) {
  // The graph API returns capitalised types ("Persona"), so normalise the same
  // way nodeStyle does. Comparing raw values here silently matched nothing.
  const typeOf = n => String(n?.type || '').toLowerCase();
  const isPersona = new Set();
  for (const n of nodes) {
    const t = typeOf(n);
    if (t === 'persona' || t === 'actor') isPersona.add(n.id);
  }
  const adj = new Map();
  const bump = (a, b, w) => {
    let row = adj.get(a);
    if (!row) adj.set(a, (row = new Map()));
    row.set(b, (row.get(b) || 0) + w);
  };

  // 1. Direct correlation between two personas.
  for (const e of edges) {
    if (!IDENTITY_EDGES.has(e.label)) continue;
    if (!isPersona.has(e.source) || !isPersona.has(e.target)) continue;
    // Stronger links get more say in the vote.
    const w = Math.max(0.4, Number(e.score ?? e.confidence ?? 0) / 100);
    bump(e.source, e.target, w);
    bump(e.target, e.source, w);
  }

  // 2. Shared attributes. Two handles quoting the same PGP key or wallet are
  //    far more likely to be one operator than two stylometric lookalikes, and
  //    in practice there are many more of these than correlation edges. The
  //    weight decays with how many personas share the attribute so a busy
  //    shared node cannot collapse half the network into a single group.
  const sharers = new Map();
  for (const e of edges) {
    if (!ATTRIBUTE_EDGES.has(e.label)) continue;
    const [a, b] = [e.source, e.target];
    const attr = isPersona.has(a) ? b : isPersona.has(b) ? a : null;
    const who = isPersona.has(a) ? a : isPersona.has(b) ? b : null;
    if (!attr || !who) continue;
    let set = sharers.get(attr);
    if (!set) sharers.set(attr, (set = new Set()));
    set.add(who);
  }
  for (const set of sharers.values()) {
    const k = set.size;
    if (k < 2) continue;
    const w = Math.max(0.25, 1.6 / Math.sqrt(k));
    const members = [...set].sort();
    for (let i = 0; i < members.length; i++) {
      for (let j = i + 1; j < members.length; j++) {
        bump(members[i], members[j], w);
        bump(members[j], members[i], w);
      }
    }
  }

  const order = [...isPersona].sort();
  const label = new Map(order.map(id => [id, id]));
  for (let round = 0; round < 12; round++) {
    let changed = 0;
    for (const id of order) {
      const row = adj.get(id);
      if (!row || !row.size) continue;
      const tally = new Map();
      for (const [other, w] of row) {
        const l = label.get(other);
        tally.set(l, (tally.get(l) || 0) + w);
      }
      // Heaviest label wins; ties go to the lowest id so the result is stable.
      let best = null, bestW = -1;
      for (const l of [...tally.keys()].sort()) {
        const w = tally.get(l);
        if (w > bestW) { bestW = w; best = l; }
      }
      if (best && best !== label.get(id)) { label.set(id, best); changed++; }
    }
    if (!changed) break;
  }

  // Renumber by size so colour assignment does not shuffle between loads.
  const sizes = new Map();
  for (const l of label.values()) sizes.set(l, (sizes.get(l) || 0) + 1);
  const ranked = [...sizes.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
  const colourOf = new Map();
  ranked.forEach(([l], i) => colourOf.set(l, i));
  const community = new Map();
  for (const [id, l] of label) community.set(id, colourOf.get(l));

  const groups = ranked.map(([, size], i) => ({ id: i, size, members: [], multi: size > 1 }));
  for (const [id, ci] of community) groups[ci].members.push(id);
  return { community, groups, total: ranked.length };
}

/**
 * Seed the force simulation with one tight blob per community, arranged on a
 * golden-angle spiral. The simulation then only has to tidy up locally, which
 * is why the result stays legible instead of collapsing into one hairball.
 */
function seedPositions(nodes, edges, comm) {
  const GA = Math.PI * (3 - Math.sqrt(5));
  const index = new Map();
  nodes.forEach((n, i) => index.set(n.id, i));
  const out = new Map();

  const real = comm.groups.filter(g => g.multi);
  const biggest = Math.max(1, ...real.map(g => g.size));
  // Scale the ring to the clusters that actually exist, so a graph with one
  // tight cluster does not get flung to the edge of a huge empty circle.
  const spread = real.length > 1 ? 170 + Math.sqrt(biggest) * 30 : 0;

  real.forEach((g, gi) => {
    const r = real.length > 1 ? spread * Math.sqrt(gi + 0.6) : 0;
    const cx = Math.cos(gi * GA) * r;
    const cy = Math.sin(gi * GA) * r;
    const members = [...g.members].sort();
    const local = 38 + Math.sqrt(members.length) * 16;
    members.forEach((id, mi) => {
      const mr = members.length <= 1 ? 0 : local * Math.sqrt((mi + 0.5) / members.length);
      out.set(id, { x: cx + Math.cos(mi * GA) * mr, y: cy + Math.sin(mi * GA) * mr });
    });
  });

  // Everything that is not a persona gets parked next to the personas it
  // touches, so a post sits by its author instead of floating in the periphery.
  const anchor = new Map();
  for (const e of edges) {
    for (const [self, other] of [[e.source, e.target], [e.target, e.source]]) {
      if (out.has(self) || !out.has(other)) continue;
      let a = anchor.get(self);
      if (!a) anchor.set(self, (a = []));
      if (!a.includes(other)) a.push(other);
    }
  }
  const loose = [];
  nodes.forEach((n, i) => {
    if (out.has(n.id)) return;
    const hosts = anchor.get(n.id);
    if (hosts && hosts.length) {
      let sx = 0, sy = 0;
      for (const h of hosts) { const p = out.get(h); sx += p.x; sy += p.y; }
      // Deterministic fan-out so siblings do not stack on one pixel.
      const a = i * GA, rr = 30 + (i % 5) * 11;
      out.set(n.id, { x: sx / hosts.length + Math.cos(a) * rr, y: sy / hosts.length + Math.sin(a) * rr });
    } else {
      loose.push(n.id);
    }
  });

  // Genuinely unconnected nodes: a wide outer ring.
  loose.sort();
  loose.forEach((id, i) => {
    const r = spread * 2.1 + 40;
    const a = i * GA;
    out.set(id, { x: Math.cos(a) * r, y: Math.sin(a) * r });
  });

  const seeded = {};
  for (const n of nodes) {
    const p = out.get(n.id);
    if (p) seeded[n.id] = p;
  }
  return seeded;
}

// ── Force layout ──────────────────────────────────────────────────────────────
// Runs to completion in one pass (no rAF loop): the old version never converged,
// so it kept spreading the layout off-screen at 60fps. Repulsion is limited to
// nearby grid cells so cost stays near-linear instead of O(n^2) per frame.
const GRID_CELL = 140;
const ITERATIONS = 240;

function simulate(nodes, edges, seeds) {
  const n = nodes.length;
  const out = {};
  if (!n) return out;

  const index = new Map();
  nodes.forEach((d, i) => index.set(d.id, i));

  // Deterministic phyllotaxis start: no Math.random, so the same investigation
  // always lays out the same way. Communities, when known, override it.
  const P = new Float64Array(n * 2);
  const GA = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const seed = seeds && seeds[nodes[i].id];
    if (seed) {
      P[i * 2] = seed.x;
      P[i * 2 + 1] = seed.y;
    } else {
      const r = 26 * Math.sqrt(i + 0.5);
      P[i * 2]     = Math.cos(i * GA) * r;
      P[i * 2 + 1] = Math.sin(i * GA) * r;
    }
  }

  const links = [];
  for (const e of edges) {
    const a = index.get(e.source);
    const b = index.get(e.target);
    if (a !== undefined && b !== undefined && a !== b) links.push(a, b);
  }

  const F = new Float64Array(n * 2);
  const grid = new Map();

  for (let step = 0; step < ITERATIONS; step++) {
    const cool = 1 - step / ITERATIONS;
    F.fill(0);

    grid.clear();
    for (let i = 0; i < n; i++) {
      const k = `${Math.floor(P[i * 2] / GRID_CELL)},${Math.floor(P[i * 2 + 1] / GRID_CELL)}`;
      let cell = grid.get(k);
      if (!cell) grid.set(k, (cell = []));
      cell.push(i);
    }
    for (let i = 0; i < n; i++) {
      const x = P[i * 2], y = P[i * 2 + 1];
      const cx = Math.floor(x / GRID_CELL), cy = Math.floor(y / GRID_CELL);
      for (let ox = -1; ox <= 1; ox++) {
        for (let oy = -1; oy <= 1; oy++) {
          const cell = grid.get(`${cx + ox},${cy + oy}`);
          if (!cell) continue;
          for (const j of cell) {
            if (j === i) continue;
            let dx = x - P[j * 2], dy = y - P[j * 2 + 1];
            let d2 = dx * dx + dy * dy;
            if (d2 < 1) { dx = (i - j) || 1; dy = 0.5; d2 = dx * dx + dy * dy; }
            const d = Math.sqrt(d2);
            const f = 900 / d2;
            F[i * 2]     += (dx / d) * f;
            F[i * 2 + 1] += (dy / d) * f;
          }
        }
      }
    }

    for (let k = 0; k < links.length; k += 2) {
      const a = links[k], b = links[k + 1];
      const dx = P[b * 2] - P[a * 2], dy = P[b * 2 + 1] - P[a * 2 + 1];
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d - 70) * 0.05;
      F[a * 2]     += (dx / d) * f;
      F[a * 2 + 1] += (dy / d) * f;
      F[b * 2]     -= (dx / d) * f;
      F[b * 2 + 1] -= (dy / d) * f;
    }

    // Gentle pull to origin so disconnected fragments stay in frame.
    for (let i = 0; i < n; i++) {
      F[i * 2]     -= P[i * 2] * 0.006;
      F[i * 2 + 1] -= P[i * 2 + 1] * 0.006;
    }

    for (let i = 0; i < n; i++) {
      let vx = F[i * 2] * cool, vy = F[i * 2 + 1] * cool;
      const sp = Math.sqrt(vx * vx + vy * vy);
      if (sp > 18) { vx = (vx / sp) * 18; vy = (vy / sp) * 18; }
      P[i * 2] += vx;
      P[i * 2 + 1] += vy;
    }
  }

  for (let i = 0; i < n; i++) out[nodes[i].id] = { x: P[i * 2], y: P[i * 2 + 1] };
  return out;
}

/**
 * Scale + translate that frames the whole graph inside the viewport. This is
 * what makes the graph actually visible: without it a force layout happily
 * spreads to a few thousand units and 90% of it sits outside the element.
 */
function fitTransform(positions, nodes, w, h, t, pad = 44) {
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) {
    return { scale: 1, tx: 0, ty: 0 };
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    const p = positions[n.id];
    if (!p) continue;
    const r = nodeStyle(n, t).r + 6;
    if (p.x - r < minX) minX = p.x - r;
    if (p.x + r > maxX) maxX = p.x + r;
    if (p.y - r < minY) minY = p.y - r;
    if (p.y + r > maxY) maxY = p.y + r;
  }
  if (!isFinite(minX)) return { scale: 1, tx: w / 2, ty: h / 2 };

  const bw = Math.max(maxX - minX, 1);
  const bh = Math.max(maxY - minY, 1);
  const scale = Math.min((w - pad * 2) / bw, (h - pad * 2) / bh, 1.5);
  return {
    scale,
    tx: w / 2 - ((minX + maxX) / 2) * scale,
    ty: h / 2 - ((minY + maxY) / 2) * scale,
  };
}

// Clear space to leave between two node circles, in on-screen pixels. A force
// layout only balances globally, so a dense cluster can still end up with
// overlapping circles once the graph is squeezed into the side panel.
const MIN_GAP = 9;

/**
 * Nudge apart any pair that would render closer than MIN_GAP. Works in layout
 * units, converting the pixel budget through `scale`, and leaves the overall
 * structure alone because it only ever corrects overlaps.
 */
function enforceSpacing(positions, nodes, t, scale, passes = 24) {
  const n = nodes.length;
  if (n < 2 || !(scale > 0)) return positions;

  const P = new Float64Array(n * 2);
  for (let i = 0; i < n; i++) {
    const p = positions[nodes[i].id];
    P[i * 2]     = p ? p.x : 0;
    P[i * 2 + 1] = p ? p.y : 0;
  }
  const R = nodes.map(d => nodeStyle(d, t).r + 5);

  for (let pass = 0; pass < passes; pass++) {
    const cell = Math.max(20, 56 / scale);
    const grid = new Map();
    for (let i = 0; i < n; i++) {
      const k = `${Math.floor(P[i * 2] / cell)},${Math.floor(P[i * 2 + 1] / cell)}`;
      let c = grid.get(k);
      if (!c) grid.set(k, (c = []));
      c.push(i);
    }
    let corrections = 0;
    for (let i = 0; i < n; i++) {
      const cx = Math.floor(P[i * 2] / cell), cy = Math.floor(P[i * 2 + 1] / cell);
      for (let ox = -1; ox <= 1; ox++) {
        for (let oy = -1; oy <= 1; oy++) {
          const c = grid.get(`${cx + ox},${cy + oy}`);
          if (!c) continue;
          for (const j of c) {
            if (j === i) continue;
            let dx = P[i * 2] - P[j * 2], dy = P[i * 2 + 1] - P[j * 2 + 1];
            let d = Math.hypot(dx, dy);
            const minD = (R[i] + R[j] + MIN_GAP) / scale;
            if (d >= minD) continue;
            if (d < 1e-6) { dx = (i - j) || 1; dy = 0.5; d = Math.hypot(dx, dy); }
            const push = (minD - d) / 2 / d;
            P[i * 2]     += dx * push;
            P[i * 2 + 1] += dy * push;
            P[j * 2]     -= dx * push;
            P[j * 2 + 1] -= dy * push;
            corrections++;
          }
        }
      }
    }
    if (!corrections) break;
  }

  const out = {};
  for (let i = 0; i < n; i++) out[nodes[i].id] = { x: P[i * 2], y: P[i * 2 + 1] };
  return out;
}

function bboxOf(positions, nodes, t) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    const p = positions[n.id];
    if (!p) continue;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  if (!isFinite(minX)) return null;
  return { minX, minY, maxX, maxY, w: Math.max(maxX - minX, 1), h: Math.max(maxY - minY, 1) };
}

/**
 * Pushing overlapping nodes apart also inflates the whole cloud, and the wider
 * cloud is then scaled down to fit, which re-creates the overlaps. Restoring
 * the original extent keeps the rearrangement local, so the fit scale holds
 * steady. The correction is uniform on both axes, so nodes stay circular.
 */
function matchExtent(positions, reference, nodes, t) {
  const b = bboxOf(positions, nodes, t);
  const r = bboxOf(reference, nodes, t);
  if (!b || !r) return positions;
  const k = Math.min(Math.max(Math.min(r.w / b.w, r.h / b.h), 0.9), 1.1);
  if (Math.abs(k - 1) < 0.005) return positions;
  const cx = (r.minX + r.maxX) / 2, cy = (r.minY + r.maxY) / 2;
  const bcx = (b.minX + b.maxX) / 2, bcy = (b.minY + b.maxY) / 2;
  const out = {};
  for (const n of nodes) {
    const p = positions[n.id];
    if (!p) continue;
    out[n.id] = { x: cx + (p.x - bcx) * k, y: cy + (p.y - bcy) * k };
  }
  return out;
}

/**
 * Widen or heighten the cloud so it matches the viewport's shape. The shifted
 * graph lives in a tall narrow column; without this a roughly square layout is
 * scaled down to fit the column's width and leaves most of the height empty.
 * Scaling x only (never both axes) keeps the final transform uniform, so nodes
 * stay circular.
 */
function matchAspect(positions, nodes, w, h) {
  if (!(w > 0) || !(h > 0) || !nodes.length) return positions;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    const p = positions[n.id];
    if (!p) continue;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  if (!isFinite(minX)) return positions;

  const bw = Math.max(maxX - minX, 1);
  const bh = Math.max(maxY - minY, 1);
  const k = Math.min(Math.max((w / h) / (bw / bh), 0.45), 2.2);
  if (Math.abs(k - 1) < 0.04) return positions;

  const cx = (minX + maxX) / 2;
  const out = {};
  for (const n of nodes) {
    const p = positions[n.id];
    if (!p) continue;
    out[n.id] = { x: cx + (p.x - cx) * k, y: p.y };
  }
  return out;
}

// ── Description panel ─────────────────────────────────────────────────────────
function DescPanel({ node, t }) {
  if (!node) return (
    <div style={{ padding: '28px 24px', color: 'var(--text-tertiary)', fontSize: 14, textAlign: 'center' }}>
      {t.clickNode}
    </div>
  );

  const cfg = nodeStyle(node, t);

  const fields = [
    [t.gType,     cfg.label],
    [t.source,    node.source || node.provenance],
    [t.platform,  node.platform],
    [t.lastScan,  node.last_scan || node.last_seen],
    [t.gValue,    node.value],
    [t.gCategory, node.category || node.threat_type],
    [t.confidence, node.confidence],
  ].filter(([, v]) => v);

  return (
    <motion.div
      key={node.id}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      style={{ padding: '24px' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 20 }}>
        <div style={{
          width: 36, height: 36, borderRadius: '50%',
          background: cfg.color + '20',
          border: `2px solid ${cfg.color}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: cfg.color }} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)', lineHeight: 1.2, wordBreak: 'break-word' }}>
            {node.label || node.canonical_handle || node.id}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>{cfg.label}</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {fields.map(([label, val]) => (
          <div key={label}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              {label}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', wordBreak: 'break-all', fontFamily: typeof val === 'string' && val.length > 20 ? 'var(--font-mono)' : 'inherit' }}>
              {val}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────
function Legend({ nodes, edges, t, groups, communityOf, activeGroup, onPickGroup }) {
  // Grouped on the i18n key rather than the rendered label, so counts stay
  // correct and the legend re-renders when the language changes.
  const nodeKinds = useMemo(() => {
    const m = new Map();
    for (const n of nodes) {
      const s = nodeStyle(n, t);
      const k = s.key || s.label;
      const prev = m.get(k);
      if (prev) prev.count++;
      else m.set(k, { count: 1, label: s.label, color: s.color });
    }
    return [...m.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [nodes, t]);

  const edgeKinds = useMemo(() => {
    const m = new Map();
    for (const e of edges) {
      const s = edgeStyle(e, t);
      const k = s.key || s.label;
      const prev = m.get(k);
      if (prev) prev.count++;
      else m.set(k, { count: 1, label: s.label, color: s.color, dash: s.dash });
    }
    return [...m.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [edges, t]);

  // Communities are capped in the legend: past a handful the swatches stop
  // being comparable and the card eats the canvas.
  const MAX_GROUPS = 6;
  const shown = groups.filter(g => g.size > 1).slice(0, MAX_GROUPS);
  const hiddenGroups = groups.filter(g => g.size > 1).length - shown.length;

  return (
    <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 10, pointerEvents: 'none' }}>
      <div className="card" style={{ padding: '10px 12px', maxWidth: 190, pointerEvents: 'auto' }}>
        {shown.length > 0 && (
          <>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
              {t.gCommunities}
            </div>
            {shown.map(g => {
              const on = activeGroup === g.id;
              return (
                <button
                  key={g.id}
                  onClick={() => onPickGroup(on ? null : g.id)}
                  title={t.gCommunitiesHint}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    fontSize: 11, marginBottom: 3, padding: '1px 3px', cursor: 'pointer',
                    borderRadius: 4, border: '1px solid', textAlign: 'left',
                    borderColor: on ? COMMUNITY_COLORS[g.id % COMMUNITY_COLORS.length] : 'transparent',
                    background: on ? 'var(--accent-light)' : 'transparent',
                    color: on ? 'var(--text-primary)' : 'var(--text-secondary)',
                    opacity: activeGroup === null || on ? 1 : 0.45,
                  }}
                >
                  <span style={{
                    width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
                    background: COMMUNITY_COLORS[g.id % COMMUNITY_COLORS.length],
                  }} />
                  <span style={{ flex: 1 }}>{t.gGroup} {g.id + 1}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{g.size}</span>
                </button>
              );
            })}
            {hiddenGroups > 0 && (
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
                {t.gMoreGroups.replace('{n}', hiddenGroups)}
              </div>
            )}
            <div style={{ height: 1, background: 'var(--border)', margin: '8px 0 6px' }} />
          </>
        )}
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
          {t.entityTypes}
        </div>
        {nodeKinds.map(([key, { count, label, color }]) => {
          // Personas are coloured per community, so a single swatch would lie.
          const isPersona = key === 'gPersona';
          const stops = COMMUNITY_COLORS.slice(0, 4).map((c, i) =>
            `${c} ${i * 25}% ${(i + 1) * 25}%`).join(', ');
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
                background: isPersona ? `conic-gradient(${stops})` : color,
              }} />
              <span style={{ flex: 1 }}>{label}</span>
              <span style={{ color: 'var(--text-tertiary)' }}>{count}</span>
            </div>
          );
        })}
        {edgeKinds.length > 0 && (
          <>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', margin: '8px 0 6px' }}>
              {t.relationships}
            </div>
            {edgeKinds.map(([key, { count, label, color, dash }]) => {
              return (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
                  <span style={{ width: 12, height: 0, borderTop: `2px ${dash ? 'dashed' : 'solid'} ${color}`, flexShrink: 0 }} />
                  <span style={{ flex: 1 }}>{label}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{count}</span>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );

}

// ── Main graph screen ─────────────────────────────────────────────────────────
export default function GraphScreen({ caseData, onDone }) {
  const { t } = useLang();
  const [graphData, setGraphData]     = useState({ nodes: [], edges: [] });
  const [loadingGraph, setLoadingGraph] = useState(true);
  const [loadError, setLoadError]    = useState(false);
  const [shifted, setShifted]         = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [showAllLabels, setShowAllLabels] = useState(true);
  const [pinnedCommunity, setPinnedCommunity] = useState(null);
  const [zoom, setZoom]               = useState(1);
  const [pan, setPan]                 = useState({ x: 0, y: 0 });
  const [dragging, setDragging]       = useState(null);
  const [size, setSize] = useState({ w: 600, h: 500 });
  const wrapRef = useRef(null);

  // Fetch graph
  useEffect(() => {
    let cancelled = false;
    let shiftTimer = null;
    setLoadingGraph(true);
    setLoadError(false);
    api.getGraph(caseData.case_id)
      .then(data => {
        if (cancelled) return;
        let rawNodes = data?.nodes || data?.graph?.nodes || [];
        let rawEdges = data?.edges || data?.graph?.edges || data?.links || [];

        // Normalize Cytoscape-format: { data: { id, type, label, ... } } -> flat
        rawNodes = rawNodes.map(n => (n.data ? { ...n.data } : n));
        rawEdges = rawEdges.map(e => (e.data ? { ...e.data } : e));

        // Cap for rendering performance, preferring the most-connected nodes so
        // the visible graph is the informative part of the investigation.
        if (rawNodes.length > 300) {
          const degree = new Map();
          rawEdges.forEach(e => {
            degree.set(e.source, (degree.get(e.source) || 0) + 1);
            degree.set(e.target, (degree.get(e.target) || 0) + 1);
          });
          rawNodes = [...rawNodes]
            .sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0))
            .slice(0, 300);
          const nodeIds = new Set(rawNodes.map(n => n.id));
          rawEdges = rawEdges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target)).slice(0, 600);
        }

        setGraphData({ nodes: rawNodes, edges: rawEdges });
        setLoadingGraph(false);
        // Auto-shift to top-right after generation (flow.md step 4)
        shiftTimer = setTimeout(() => { if (!cancelled) setShifted(true); }, 1200);
      })
      .catch(() => {
        if (cancelled) return;
        setGraphData({ nodes: [], edges: [] });
        shiftTimer = setTimeout(() => { if (!cancelled) { setLoadError(true); setLoadingGraph(false); } }, 600);
      });
    return () => { cancelled = true; if (shiftTimer) clearTimeout(shiftTimer); };
  }, [caseData.case_id]);

  // One deterministic layout pass, recomputed only when the data changes.
  // Simulate once per dataset, then reshape for whatever space the graph
  // currently has. The viewport changes shape when the panel shifts, so the
  // spacing pass and the fit are redone whenever the size changes.
  // Who is probably the same person. Recomputed only when the graph changes.
  const comm = useMemo(
    () => detectCommunities(graphData.nodes, graphData.edges),
    [graphData.nodes, graphData.edges],
  );

  const communityOf = useCallback(
    id => comm.community.get(id) ?? null,
    [comm],
  );

  const layout = useMemo(() => {
    const raw = simulate(graphData.nodes, graphData.edges, seedPositions(graphData.nodes, graphData.edges, comm));
    if (!graphData.nodes.length) {
      return { positions: raw, fit: { scale: 1, tx: 0, ty: 0 } };
    }
    const shaped = matchAspect(raw, graphData.nodes, size.w, size.h);
    // Spreading the nodes enlarges the bounding box, which makes the fitting
    // scale shrink and quietly undo part of the separation. So alternate until
    // the scale settles; the gaps are then measured in the scale actually used
    // to render, and no pair can end up overlapping.
    let positions = shaped;
    let fit = fitTransform(positions, graphData.nodes, size.w, size.h, t);
    for (let pass = 0; pass < 3; pass++) {
      const spaced = enforceSpacing(positions, graphData.nodes, t, fit.scale);
      const next = matchExtent(spaced, positions, graphData.nodes, t);
      const nextFit = fitTransform(next, graphData.nodes, size.w, size.h, t);
      const settled = Math.abs(nextFit.scale - fit.scale) < fit.scale * 0.002;
      positions = next;
      fit = nextFit;
      if (settled) break;
    }
    return { positions, fit };
  }, [graphData.nodes, graphData.edges, size.w, size.h, t, comm]);

  const positions = layout.positions;
  const fit = layout.fit;

  // Responsive size. The auto-shift animates the viewport width, which makes
  // ResizeObserver report intermediate (and occasionally non-finite) rects, so
  // only accept sane measurements and keep the last good size otherwise.
  useEffect(() => {
    const ob = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      const width  = Number(rect.width);
      const height = Number(rect.height);
      if (!isFinite(width) || !isFinite(height) || width <= 0 || height <= 0) return;
      setSize(prev => (prev.w === width && prev.h === height ? prev : { w: width, h: height }));
    });
    if (wrapRef.current) ob.observe(wrapRef.current);
    return () => ob.disconnect();
  }, []);

  const onMouseDown = useCallback(e => {
    // The hit circle is a child of the [data-node] group, so testing
    // e.target.dataset.node missed it and a node click also started a pan.
    const hit = e.target.closest && e.target.closest('[data-node]');
    if (hit) return;
    setDragging({ sx: e.clientX - pan.x, sy: e.clientY - pan.y });
  }, [pan]);
  const onMouseMove = useCallback(e => {
    if (!dragging) return;
    setPan({ x: e.clientX - dragging.sx, y: e.clientY - dragging.sy });
  }, [dragging]);
  const onMouseUp = useCallback(() => setDragging(null), []);
  const onWheel   = useCallback(e => {
    e.preventDefault();
    setZoom(z => Math.min(4, Math.max(0.3, z * (e.deltaY < 0 ? 1.12 : 0.89))));
  }, []);

  const resetView = useCallback(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, []);

  // Selecting a cluster frames it. Colour alone tells you a group exists; being
  // flown to it is what makes it useful at 17 nodes across.
  const focusCluster = useCallback((groupId) => {
    const g = comm.groups[groupId];
    if (!g || !g.members.length) return;
    let sx = 0, sy = 0, n = 0;
    for (const id of g.members) {
      const p = positions[id];
      if (!p) continue;
      sx += p.x; sy += p.y; n++;
    }
    if (!n) return;
    const cx = sx / n, cy = sy / n;
    // Spread the members to size the frame, then pick a zoom that fits them.
    let rad = 0;
    for (const id of g.members) {
      const p = positions[id];
      if (p) rad = Math.max(rad, Math.hypot(p.x - cx, p.y - cy));
    }
    const fitRad = Math.max(60, rad * 1.6);
    const nextZoom = Math.min(4, Math.max(0.3,
      Math.min(size.w, size.h) / (2 * fitRad * fit.scale)));
    setZoom(nextZoom);
    setPan({
      x: size.w / 2 - (fit.tx + cx * fit.scale * nextZoom),
      y: size.h / 2 - (fit.ty + cy * fit.scale * nextZoom),
    });
  }, [comm, positions, fit, size.w, size.h]);

  // Hovering focuses a node just like selecting it does, so the graph can be
  // explored without committing to a selection.
  const focusedId = selectedNode?.id || hoveredId;
  const focusedNode = useMemo(
    () => (focusedId ? graphData.nodes.find(n => n.id === focusedId) || null : null),
    [focusedId, graphData.nodes],
  );

  // Edges touching the focused node, so the relationship types are readable.
  const incidentEdges = useMemo(() => {
    if (!focusedId) return null;
    return new Set(
      graphData.edges
        .filter(e => e.source === focusedId || e.target === focusedId)
        .map(e => `${e.source}|${e.target}|${e.label}`),
    );
  }, [focusedId, graphData.edges]);

  // Neighbours of the focused node keep their labels so a relationship can be
  // read without clicking through everything.
  const labelledIds = useMemo(() => {
    if (!focusedId) return null;
    const set = new Set([focusedId]);
    for (const e of graphData.edges) {
      if (e.source === focusedId) set.add(e.target);
      else if (e.target === focusedId) set.add(e.source);
    }
    // Selecting one persona should reveal the people it may be the same as,
    // not just the handles it happens to link to directly.
    const group = comm.community.get(focusedId);
    if (group !== undefined) {
      const bucket = comm.groups[group];
      if (bucket) for (const id of bucket.members) set.add(id);
    }
    return set;
  }, [focusedId, graphData.edges, comm]);

  const scale = fit.scale * zoom;
  // In the narrow side panel the fit scale is small, so blanket labels would
  // be unreadable clutter; they come back as soon as there is room (or when
  // the user asks for them).
  const showLabels = showAllLabels && scale > 0.34;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        display: 'flex', alignItems: 'center', padding: '0 24px',
        height: 56, background: 'var(--bg-card)', borderBottom: '1px solid var(--border)', gap: 12,
      }}>
        <div style={{ fontWeight: 600, fontSize: 15, flex: 1 }}>{caseData.name}</div>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t.graphTitle}</span>
        <LangToggle />
        <button className="btn btn-primary" onClick={onDone} id="open-workspace-btn">
          {t.gOpenWorkspace || 'Open Workspace'} →
        </button>
      </header>

      {/* Body — graph left/top-right + panel */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>

        {/* Graph viewport — animates to top-right */}
        <motion.div
          animate={shifted ? {
            position: 'absolute',
            top: 0, right: 0,
            // 70% of the row, mirroring the description panel's 30%.
            width: '70%',
            height: '100%',
          } : {
            position: 'relative',
            width: '100%',
            height: '100%',
          }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          style={{
            background: 'var(--bg)',
            borderLeft: shifted ? '1px solid var(--border)' : 'none',
          }}
        >
          <div id="graph-canvas-wrap" ref={wrapRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
            {/* Focus chip -- names the hovered/selected entity so the graph is
                readable without clicking through it. */}
            {focusedNode && (
              <div style={{
                position: 'absolute', top: 12, left: 12, zIndex: 3, pointerEvents: 'none',
                display: 'flex', alignItems: 'center', gap: 8, maxWidth: 'calc(100% - 24px)',
                padding: '7px 11px', borderRadius: 8,
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                boxShadow: '0 2px 10px rgba(28,25,23,0.10)',
              }}>
                <span style={{
                  width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
                  background: nodeStyle(focusedNode, t).color,
                }} />
                <span style={{
                  fontSize: 12, fontWeight: 600, color: 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {(focusedNode.label || focusedNode.canonical_handle || focusedNode.id || '').slice(0, 26)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)', flexShrink: 0 }}>
                  {nodeStyle(focusedNode, t).label}
                </span>
              </div>
            )}
            {/* Dot grid */}
            <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.4, pointerEvents: 'none' }}>
              <defs>
                <pattern id="dots-g" width="24" height="24" patternUnits="userSpaceOnUse">
                  <circle cx="12" cy="12" r="0.7" fill="#D6D3D1" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#dots-g)" />
            </svg>

            {/* Controls */}
            <div style={{ position: 'absolute', top: 12, left: 12, display: 'flex', flexDirection: 'column', gap: 4, zIndex: 10 }}>
              {[['+', () => setZoom(z => Math.min(4, z * 1.2))],
                ['-', () => setZoom(z => Math.max(0.3, z / 1.2))],
                ['R', resetView]].map(([lbl, fn]) => (
                <button key={lbl} onClick={fn} className="btn btn-secondary btn-sm btn-icon"
                  title={lbl === 'R' ? (t.gResetView || 'Reset view') : undefined}
                  style={{ width: 28, height: 28, justifyContent: 'center', fontSize: 13 }}>{lbl}</button>
              ))}
              <button
                onClick={() => setShowAllLabels(v => !v)}
                className="btn btn-secondary btn-sm btn-icon"
                title={showAllLabels ? (t.gHideLabels || 'Hide labels') : (t.gShowLabels || 'Show labels')}
                aria-pressed={showAllLabels}
                style={{
                  width: 28, height: 28, justifyContent: 'center', fontSize: 11,
                  color: showAllLabels ? 'var(--accent)' : 'var(--text-tertiary)',
                }}
              >
                Aa
              </button>
            </div>

            {/* Legend */}
            {!loadingGraph && graphData.nodes.length > 0 && (
              <Legend nodes={graphData.nodes} edges={graphData.edges} t={t}
                groups={comm.groups} communityOf={communityOf}
                activeGroup={pinnedCommunity} onPickGroup={ci => {
                  if (ci === null) { setPinnedCommunity(null); resetView(); }
                  else { setPinnedCommunity(ci); focusCluster(ci); }
                }} />
            )}

            {/* Stats */}
            {!loadingGraph && graphData.nodes.length > 0 && (
              <div style={{ position: 'absolute', bottom: 12, left: 12, fontSize: 11, color: 'var(--text-tertiary)' }}>
                {graphData.nodes.length} {t.nodes} | {graphData.edges.length} {t.edges}
              </div>
            )}

            {/* SVG canvas */}
            <svg
              style={{ width: '100%', height: '100%', cursor: dragging ? 'grabbing' : 'grab' }}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={onMouseUp}
              onWheel={onWheel}
            >
              <g transform={`translate(${fit.tx + pan.x},${fit.ty + pan.y}) scale(${fit.scale * zoom})`}>
                {/* Edges */}
                {graphData.edges.map((edge, i) => {
                  const fromId = edge.source || edge.from;
                  const toId   = edge.target || edge.to;
                  const f      = positions[fromId];
                  const to     = positions[toId];
                  if (!f || !to) return null;
                  const style  = edgeStyle(edge, t);
                  const key    = `${fromId}|${toId}|${edge.label}`;
                  const isIncident = incidentEdges?.has(key);
                  // A label sits on top of its own edge, so it gets a canvas
                  // coloured halo -- otherwise the stroke cuts the text in two
                  // and pale relationship colours vanish against the fill.
                  const midX = (f.x + to.x) / 2;
                  const midY = (f.y + to.y) / 2;
                  return (
                    <g key={edge.id || key}>
                      <line
                        x1={f.x} y1={f.y} x2={to.x} y2={to.y}
                        stroke={style.color}
                        strokeWidth={(isIncident ? 2.2 : 1.1) / Math.max(scale, 0.35)}
                        strokeOpacity={incidentEdges ? (isIncident ? 0.95 : 0.07) : 0.5}
                        strokeDasharray={style.dash || undefined}
                        strokeLinecap="round"
                      />
                      {isIncident && (
                        <text
                          x={midX} y={midY - 5 / Math.max(scale, 0.35)}
                          textAnchor="middle"
                          fontSize={11 / Math.max(scale, 0.35)}
                          fontWeight={600}
                          fill={style.color}
                          stroke="#F8F7F5" strokeWidth={3 / Math.max(scale, 0.35)}
                          paintOrder="stroke"
                          style={{ userSelect: 'none', pointerEvents: 'none' }}
                        >
                          {style.label}
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Nodes */}
                {graphData.nodes.map(node => {
                  const pos = positions[node.id];
                  if (!pos) return null;
                  const base  = nodeStyle(node, t);
                  // A persona wears its community colour; that is the whole
                  // point of the palette. Everything else keeps its type hue.
                  const commId = communityOf(node.id);
                  const cluster = commId === null ? null : comm.groups[commId];
                  const cfg = cluster && cluster.multi
                    ? { ...base, color: COMMUNITY_COLORS[commId % COMMUNITY_COLORS.length] }
                    : base;
                  const isSelected = selectedNode?.id === node.id;
                  const isHovered  = hoveredId === node.id;
                  const isFocused  = isSelected || isHovered;
                  const dimmed = pinnedCommunity !== null
                    ? communityOf(node.id) !== pinnedCommunity && base.key !== 'gCase'
                    : Boolean(labelledIds) && !labelledIds.has(node.id);
                  // Keep the pointer target at least ~11px on screen even when
                  // the fit scale is small, so nodes stay easy to hit in the
                  // narrow panel.
                  const hitR = Math.max(cfg.r, 11 / Math.max(scale, 0.2));
                  const inPinned = pinnedCommunity !== null
                    && communityOf(node.id) === pinnedCommunity;
                  const showNodeLabel = (showLabels || labelledIds?.has(node.id) || inPinned) && !dimmed;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${pos.x},${pos.y})`}
                      data-node="1"
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedNode(isSelected ? null : node)}
                      onMouseEnter={() => setHoveredId(node.id)}
                      onMouseLeave={() => setHoveredId(cur => (cur === node.id ? null : cur))}
                    >
                      <circle r={hitR} fill="transparent" />
                      {isFocused && (
                        <circle
                          r={cfg.r + 4} fill="none" stroke={cfg.color}
                          strokeWidth={1.5} strokeOpacity={0.45}
                        />
                      )}
                      <circle
                        r={cfg.r + (isSelected ? 3 : 0)}
                        fill={cfg.color}
                        fillOpacity={dimmed ? 0.2 : isSelected ? 1 : 0.88}
                        stroke={isSelected ? '#FFFFFF' : cfg.color}
                        strokeWidth={(isSelected ? 2 : 1) / Math.max(scale, 0.35)}
                        style={{ transition: 'r 150ms, fill-opacity 150ms' }}
                      />
                      {showNodeLabel && (
                        <text
                          y={cfg.r + 13 / Math.max(scale, 0.35)}
                          textAnchor="middle"
                          fontSize={(isFocused ? 11 : 9) / Math.max(scale, 0.45)}
                          fontWeight={isFocused ? 600 : 400}
                          fill={isFocused ? '#1C1917' : '#57534E'}
                          stroke="#F8F7F5" strokeWidth={2.5 / Math.max(scale, 0.45)}
                          paintOrder="stroke"
                          fontFamily="Inter, sans-serif"
                          style={{ userSelect: 'none', pointerEvents: 'none' }}
                        >
                          {(node.label || node.canonical_handle || node.id || '').slice(0, 18)}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            </svg>

            {/* Loading spinner */}
            {loadingGraph && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16,
              }}>
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                  style={{ width: 28, height: 28, border: '3px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%' }}
                />
                <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{t.generating}</span>
              </div>
            )}

            {/* Empty / error state — never leave a blank canvas */}
            {!loadingGraph && graphData.nodes.length === 0 && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 10, padding: 24, textAlign: 'center',
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                  {loadError ? (t.graphLoadFailed || 'Could not load the graph') : (t.graphEmpty || 'No graph data yet')}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-tertiary)', maxWidth: 320, lineHeight: 1.6 }}>
                  {loadError
                    ? (t.graphLoadFailedBody || 'The graph could not be fetched. Check that the backend is running, then try again.')
                    : (t.graphEmptyBody || 'Ingest data and run correlation to build the relationship graph for this investigation.')}
                </div>
                <button className="btn btn-secondary btn-sm" onClick={onDone} style={{ marginTop: 6 }}>
                  {t.backToWorkspace || 'Back to workspace'}
                </button>
              </div>
            )}
          </div>
        </motion.div>

        {/* Description panel — appears as graph shifts */}
        <AnimatePresence>
          {shifted && (
            <motion.div
              initial={{ opacity: 0, x: -24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.5, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
              style={{
                width: '30%',
                height: '100%',
                overflowY: 'auto',
                background: 'var(--bg-card)',
                borderRight: '1px solid var(--border)',
              }}
            >
              {/* Panel header */}
              <div style={{
                padding: '20px 24px', borderBottom: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 15 }}>
                    {selectedNode ? t.selected : t.graphTitle}
                  </div>
                  {!selectedNode && (
                    <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {t.graphReady} · {graphData.nodes.length} {t.nodes}, {graphData.edges.length} {t.edges}
                    </div>
                  )}
                </div>
              </div>

              <DescPanel
                node={selectedNode}
                t={t}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
