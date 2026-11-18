/* NUTCADE arcade: NEON ROAD, a pseudo-3D night-highway racer.
   The road is a ring of 200-unit segments projected to the screen every frame (nearest to farthest for what is visible,
   farthest to nearest for painting). The whole road is built from the seeded RNG in init(), so a seed gives the same road.
   update() uses only + - * / (no sin/cos) and RNG, so replays and challenges give the same run on every phone.
   Nothing is allocated while the game runs: the projection and the scratch rows are typed arrays made once. */
(window.NutCabinets = window.NutCabinets || []).push(function (K) {
'use strict';
const { W, H, C, Math, text, T, rnd, ri, clamp, boom, tickFx, drawFx } = K;

const SEG = 200, ROADW = 900, CAMH = 1000, CAMD = 0.84, DRAW = 100, CS = 0.6;   // segment length, road half width, camera
const HOR = 118, KY = 150, HW2 = W / 2;                                        // horizon row, vertical scale
const PLAYERZ = CAMH * CAMD, MAXSP = SEG;                                      // the car sits PLAYERZ ahead of the camera
const STAGE_LEN = 1500, NST = 8, TL = STAGE_LEN * NST;                          // a stage is 1500 segments; eight stages then it repeats
const POOL = 26, LANES = [-0.6, 0, 0.6], CARW = 0.62;
const START_TIME = 50, COUNT = 170, CARY = 268;

/* ---------- colours ---------- */
const hx = c => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
const mix = (a, b, t) => { const p = hx(a), q = hx(b); let o = '#'; for (let i = 0; i < 3; i++) o += ('0' + Math.round(p[i] + (q[i] - p[i]) * t).toString(16)).slice(-2); return o; };
const FOGT = [0, 0.12, 0.27, 0.45, 0.65, 0.85];
const FL = new Uint8Array(DRAW + 2); for (let n = 0; n < FL.length; n++) FL[n] = Math.min(5, Math.floor(Math.pow(n / DRAW, 1.35) * 6.4));
// one entry per look: sky stops (top, mid, low, horizon), sun, mountains, ground, grid, road, edge, lane, fog, poles
const DEFS = [
  { sky: ['#07031a', '#3b0f66', '#c2287a', '#ff8a3d'], sun: ['#ffd23a', '#ff3d8b'], m1: ['#2a0a4d', '#7a3dff'], m2: ['#160733', '#ff3d8b'], gA: '#12072b', gB: '#190a38', grid: '#ff3d8b', rA: '#1d1445', rB: '#180f3a', eA: '#2de2ff', eB: '#0b5f8c', ln: '#ffcf3a', fog: '#3a0a5a', pole: '#2a1a5a', lamp: '#2de2ff' },
  { sky: ['#020b24', '#06406b', '#1fb7c4', '#a8fff0'], sun: ['#ffffff', '#2de2ff'], m1: ['#06284a', '#2de2ff'], m2: ['#041a33', '#ff3d8b'], gA: '#04122a', gB: '#061a38', grid: '#2de2ff', rA: '#0f2a55', rB: '#0c2349', eA: '#ff3d8b', eB: '#7a1a52', ln: '#ffffff', fog: '#0a3a63', pole: '#0f3a66', lamp: '#ff3d8b' },
  { sky: ['#0b0221', '#2a0a66', '#7a2bff', '#ff7ad9'], sun: ['#fff06a', '#ff3dd4'], m1: ['#1b0a45', '#c13dff'], m2: ['#0f0530', '#5dff7a'], gA: '#0b0524', gB: '#13082f', grid: '#c13dff', rA: '#241552', rB: '#1d1045', eA: '#5dff7a', eB: '#1c7a3a', ln: '#5dff7a', fog: '#43107a', pole: '#35207a', lamp: '#5dff7a' },
  { sky: ['#14020a', '#5a0f1e', '#d4381e', '#ffb02a'], sun: ['#fff3a0', '#ff5444'], m1: ['#3a0a14', '#ff9a1f'], m2: ['#220610', '#ffcf3a'], gA: '#1a0510', gB: '#240818', grid: '#ff9a1f', rA: '#2a1230', rB: '#231029', eA: '#ffcf3a', eB: '#8a5a12', ln: '#ff9a1f', fog: '#5a1428', pole: '#4a1a30', lamp: '#ffcf3a' },
  { sky: ['#030a1c', '#173a7a', '#6a9bff', '#e6f0ff'], sun: ['#ffffff', '#8db4ff'], m1: ['#13306a', '#bfe0ff'], m2: ['#0a1c44', '#ffffff'], gA: '#050f26', gB: '#08163a', grid: '#6a9bff', rA: '#14275e', rB: '#10204f', eA: '#ffffff', eB: '#3d6bff', ln: '#ffffff', fog: '#2a4a9a', pole: '#1c3a80', lamp: '#ffffff' }
];
const NPAL = DEFS.length;
const PALS = DEFS.map(d => {
  const f = c => FOGT.map(t => mix(c, d.fog, t));
  return { d, gA: f(d.gA), gB: f(d.gB), rA: f(d.rA), rB: f(d.rB), eA: f(d.eA), eB: f(d.eB), ln: f(d.ln), grid: f(d.grid), pole: f(d.pole), lamp: f(d.lamp), base: mix(d.gA, d.fog, 0.92) };
});

/* ---------- cars: a wedge seen from behind, drawn from rows of letters at any width ---------- */
const CAR_BIG = ['.....hhhhhh.....', '....hggggggh....', '...hggggggggh...', 'ssssssssssssssss', '.bbbbbbbbbbbbbb.', '.btttbbbbbbtttb.', '.btttbbbbbbtttb.', 'bbbbbbbbbbbbbbbb', 'wwdbbbbbbbbbbdww', 'wwwddddddddddwww', '.ww..uuuuuu..ww.'];
const CAR_SMALL = ['..hhhh..', '.bggggb.', 'bbbbbbbb', 'btbbbbtb', 'wwbbbbww'];
const PLAYER_PAL = { b: '#2de2ff', h: '#c9f7ff', g: '#10274f', d: '#1593b8', t: '#ff3d8b', s: '#ff3d8b', w: '#0a0618', u: '#8d6bff' };
const GHOST_PAL = { b: '#fff', h: '#fff', g: '#fff', d: '#fff', t: '#fff', s: '#fff', w: '#fff' };
const TRAFFIC = [C.pink, C.gold, C.lime, C.orange, C.violet, '#ff5444'].map(b => ({ b, h: mix(b, '#ffffff', 0.45), g: '#1b1040', d: mix(b, '#000000', 0.45), t: '#ff2a2a', s: mix(b, '#000000', 0.3), w: '#0a0618' }));
function drawCar(ctx, rows, pal, cx, by, w, clip, lean) {
  const nR = rows.length, nC = rows[0].length, u = w / nC, left = cx - w / 2;
  for (let r = 0; r < nR; r++) {
    const ya = Math.round(by - (nR - r) * u); let yb = Math.round(by - (nR - r - 1) * u);
    if (yb <= ya) yb = ya + 1;
    if (ya >= clip) continue; if (yb > clip) yb = clip;
    const row = rows[r], sh = lean ? Math.round(lean * (nR - 1 - r) / (nR - 1)) : 0;
    let c = 0;
    while (c < nC) {
      const ch = row[c]; let e = c + 1; while (e < nC && row[e] === ch) e++;
      const col = pal[ch];
      if (col) { ctx.fillStyle = col; const xa = Math.round(left + c * u) + sh, xb = Math.round(left + e * u) + sh; ctx.fillRect(xa, ya, (xb - xa) || 1, yb - ya); }
      c = e;
    }
  }
}
function drawTraffic(ctx, pal, cx, by, w, clip) {
  if (w < 5) { const y = Math.min(by, clip); if (y > by - 3) { ctx.fillStyle = pal.b; ctx.fillRect(Math.round(cx - w / 2), Math.round(by - 3), Math.max(2, Math.round(w)), Math.min(3, Math.round(y - (by - 3)))); } return; }
  drawCar(ctx, w < 24 ? CAR_SMALL : CAR_BIG, pal, cx, by, w, clip, 0);
}

/* ---------- backdrops: sky with a striped sun and two mountain ranges, built once per look ---------- */
const BG = [];
const lcg = seed => { let a = seed >>> 0; return () => { a = (Math.imul(a, 1664525) + 1013904223) >>> 0; return a / 4294967296; }; };
const MTW = 448;
function mountains(def, which, seed, hmin, hmax, mh) {
  const cv = document.createElement('canvas'); cv.width = MTW; cv.height = mh; const g = cv.getContext('2d');
  const r = lcg(seed), px = [], py = []; let x = 0;
  while (x < MTW - 14) { px.push(x); py.push(hmin + r() * (hmax - hmin)); x += 18 + r() * 30; }
  px.push(MTW); py.push(py[0]);
  const col = def[which][0], edge = def[which][1]; let k = 0;
  for (let c = 0; c < MTW; c++) {
    while (px[k + 1] < c) k++;
    const t = (c - px[k]) / (px[k + 1] - px[k]), h = Math.round(py[k] + (py[k + 1] - py[k]) * t);
    g.fillStyle = col; g.fillRect(c, mh - h, 1, h); g.fillStyle = edge; g.fillRect(c, mh - h, 1, 1);
  }
  return cv;
}
function backdrop(pi) {
  if (BG[pi]) return BG[pi];
  const d = DEFS[pi], cv = document.createElement('canvas'); cv.width = W; cv.height = HOR + 1; const g = cv.getContext('2d');
  const st = d.sky;
  for (let y = 0; y <= HOR; y += 3) {
    const t = y / HOR; g.fillStyle = t < 0.5 ? mix(st[0], st[1], t / 0.5) : t < 0.85 ? mix(st[1], st[2], (t - 0.5) / 0.35) : mix(st[2], st[3], (t - 0.85) / 0.15);
    g.fillRect(0, y, W, 3);
  }
  const r = lcg(pi * 7919 + 5);
  for (let i = 0; i < 46; i++) { const y = Math.floor(r() * HOR * 0.6); g.globalAlpha = 0.35 + r() * 0.65; g.fillStyle = i % 5 === 0 ? C.cyan : i % 7 === 0 ? C.pink : '#ffffff'; g.fillRect(Math.floor(r() * W), y, 1, 1); }
  g.globalAlpha = 1;
  const cx = 112, cy = HOR - 16, R = 38;
  g.globalAlpha = 0.16; g.fillStyle = d.sun[1];
  for (let y = cy - R - 12; y <= HOR; y++) { const dy = y - cy, hw = Math.sqrt(Math.max(0, (R + 12) * (R + 12) - dy * dy)); if (hw > 0) g.fillRect(Math.round(cx - hw), y, Math.round(hw * 2), 1); }
  g.globalAlpha = 1;
  for (let y = cy - R; y <= HOR; y++) {
    const dy = y - cy; if (dy > 0 && (dy % 7) < dy / 6) continue;
    const hw = Math.sqrt(R * R - dy * dy); g.fillStyle = mix(d.sun[0], d.sun[1], (y - (cy - R)) / (R + 18)); g.fillRect(Math.round(cx - hw), y, Math.round(hw * 2), 1);
  }
  g.fillStyle = mix(st[3], '#ffffff', 0.35); g.fillRect(0, HOR, W, 1);
  return (BG[pi] = { sky: cv, m1: mountains(d, 'm1', pi * 31 + 3, 14, 40, 44), m2: mountains(d, 'm2', pi * 57 + 11, 6, 22, 26) });
}

/* ---------- road building (seeded) ---------- */
const ss = p => p * p * (3 - 2 * p);
function buildRoad(s) {
  const curve = s.curve = new Float32Array(TL + 1), ys = s.ys = new Float32Array(TL + 1);
  let n = 0, y = 0;
  const sec = (enter, hold, leave, c, dy) => {
    const total = enter + hold + leave, y0 = y, y1 = y + dy;
    for (let i = 0; i < total && n < TL; i++, n++) {
      curve[n] = i < enter ? c * ss(i / enter) : i < enter + hold ? c : c * (1 - ss((i - enter - hold) / leave));
      ys[n] = y0 + (y1 - y0) * ss(i / total);
    }
    y = y1;
  };
  for (let k = 0; k < NST; k++) {
    const end = (k + 1) * STAGE_LEN, d = k / (NST - 1), cmax = 1.7 + 2.5 * d, hmax = 500 + 1300 * d;
    if (k === 0) sec(10, 110, 10, 0, 0);
    while (n < end - 200) {
      const r = RNGf(), sg = RNGf() < 0.5 ? -1 : 1;
      let dy = (RNGf() * 2 - 1) * hmax; if (Math.abs(y + dy) > 1800) dy = -dy;
      if (r < 0.2) sec(20, ri(10, 40), 20, 0, 0);
      else if (r < 0.5) sec(ri(20, 34), ri(25, 70), ri(20, 34), sg * rnd(1.3, cmax), 0);
      else if (r < 0.66) { sec(18, ri(6, 20), 18, sg * rnd(1.3, cmax), 0); sec(18, ri(6, 20), 18, -sg * rnd(1.3, cmax), 0); }
      else if (r < 0.88) sec(40, ri(10, 40), 40, 0, dy);
      else sec(34, ri(20, 40), 34, sg * rnd(1.3, cmax), dy * 0.6);
    }
    const rem = end - n, a = Math.floor(rem * 0.4), b = Math.floor(rem * 0.2);
    sec(a, b, rem - a - b, 0, -y);   // the stage always ends flat and straight, where the checkpoint stands
  }
  curve[TL] = 0; ys[TL] = 0;
}
const RNGf = () => rnd(0, 1);

/* ---------- projection (a typed array per point, reused every frame) ---------- */
const PX = new Float32Array(DRAW + 2), PY = new Float32Array(DRAW + 2), PWD = new Float32Array(DRAW + 2), CLIPY = new Float32Array(DRAW + 2);
const VIS = new Uint8Array(DRAW + 2), PVAL = new Uint8Array(DRAW + 2);
const BH = new Int16Array(DRAW + 2), NEXT = new Int16Array(POOL);
const RC = new Float32Array(H + 8), RWD = new Float32Array(H + 8);
const GRID_M = [1.55, 2.2, 2.85, 3.5, 4.15, 4.8, 5.45, 6.1, 6.75, 7.4];
let LAST = null;
function project(s) {
  const pos = s.pos, abs0 = Math.floor(pos / SEG), pct = pos / SEG - abs0;
  const pz = pos + PLAYERZ, ip = Math.floor(pz / SEG), pp = pz / SEG - ip;
  const ya = s.ys[ip % TL], yb = s.ys[(ip + 1) % TL], camY = CAMH + ya + (yb - ya) * pp, camX = s.px * ROADW;
  let x = 0, dx = -s.curve[abs0 % TL] * CS * pct;
  for (let n = 0; n <= DRAW; n++) {
    const i = (abs0 + n) % TL, zr = (n - pct) * SEG;
    if (zr > 2) { const sc = CAMD / zr; PX[n] = HW2 + sc * (x - camX) * HW2; PY[n] = HOR - sc * (s.ys[i] - camY) * KY; PWD[n] = sc * ROADW * HW2; PVAL[n] = 1; } else PVAL[n] = 0;
    x += dx; dx += s.curve[i] * CS;
  }
  let maxy = H;
  for (let n = 0; n < DRAW; n++) {
    CLIPY[n] = maxy; VIS[n] = 0;
    if (!PVAL[n] || !PVAL[n + 1] || PY[n + 1] >= PY[n] || PY[n + 1] >= maxy) continue;
    VIS[n] = 1; if (PY[n] < maxy) maxy = PY[n];
  }
  BH.fill(-1);
  for (let i = 0; i < POOL; i++) {
    const c = s.cars[i]; if (!c.on) continue;
    const n = Math.floor(c.z / SEG) - abs0;
    if (n >= 1 && n < DRAW) { NEXT[i] = BH[n]; BH[n] = i; }
  }
}

/* ---------- drawing ---------- */
function backdropDraw(ctx, pi, sx) {
  const b = backdrop(pi);
  ctx.drawImage(b.sky, 0, 0);
  let o = -((sx * 0.45 % MTW) + MTW) % MTW; ctx.drawImage(b.m1, o, HOR - 44); ctx.drawImage(b.m1, o + MTW, HOR - 44);
  o = -((sx % MTW) + MTW) % MTW; ctx.drawImage(b.m2, o, HOR - 26); ctx.drawImage(b.m2, o + MTW, HOR - 26);
}
function renderWorld(ctx, s) {
  const abs0 = Math.floor(s.pos / SEG), pc = (Math.floor((s.pos + PLAYERZ) / SEG / STAGE_LEN)) % NPAL;
  if (s.fade > 0) { backdropDraw(ctx, s.oldPal, s.sky); ctx.globalAlpha = 1 - s.fade / 70; backdropDraw(ctx, pc, s.sky); ctx.globalAlpha = 1; } else backdropDraw(ctx, pc, s.sky);
  ctx.fillStyle = PALS[pc].base; ctx.fillRect(0, HOR + 1, W, H - HOR - 1);
  ctx.lineWidth = 1;
  let gk = -1;
  for (let n = DRAW - 1; n >= 1; n--) {
    if (!VIS[n]) continue;
    const a = abs0 + n, pi = ((a / STAGE_LEN) | 0) % NPAL, pal = PALS[pi], f = FL[n];
    const y1 = PY[n], y2 = PY[n + 1];
    let r0 = Math.round(y2), r1 = Math.round(y1); if (r0 < 0) r0 = 0; if (r1 > H) r1 = H;
    if (r1 <= r0) continue;
    const band = ((a / 3) | 0) & 1, X1 = PX[n], X2 = PX[n + 1], W1 = PWD[n], W2 = PWD[n + 1], dy = y1 - y2;
    ctx.fillStyle = band ? pal.gB[f] : pal.gA[f]; ctx.fillRect(0, r0, W, r1 - r0);
    if (a % 3 === 0) { ctx.fillStyle = pal.grid[f]; ctx.fillRect(0, r1 - 1, W, 1); }
    const key = pi * 8 + f;
    if (key !== gk) { if (gk >= 0) ctx.stroke(); gk = key; ctx.beginPath(); ctx.strokeStyle = pal.grid[f]; }
    for (let k = 0; k < GRID_M.length; k++) {
      const m = GRID_M[k], l1 = X1 - W1 * m, l2 = X2 - W2 * m, r1x = X1 + W1 * m, r2x = X2 + W2 * m;
      if (l1 > -4 || l2 > -4) { ctx.moveTo(l1, y1); ctx.lineTo(l2, y2); }
      if (r1x < W + 4 || r2x < W + 4) { ctx.moveTo(r1x, y1); ctx.lineTo(r2x, y2); }
    }
    for (let r = r0; r < r1; r++) { const t = (r + 0.5 - y2) / dy; RC[r] = X2 + (X1 - X2) * t; RWD[r] = W2 + (W1 - W2) * t; }
    ctx.fillStyle = band ? pal.eA[f] : pal.eB[f];
    for (let r = r0; r < r1; r++) {
      const cx = RC[r], w = RWD[r], ew = Math.max(1, w * 0.1), xl = Math.round(cx - w), xr = Math.round(cx + w);
      const xo = Math.round(cx - w - ew), xe = Math.round(cx + w + ew);
      ctx.fillRect(xo, r, Math.max(1, xl - xo), 1); ctx.fillRect(xr, r, Math.max(1, xe - xr), 1);
    }
    ctx.fillStyle = band ? pal.rA[f] : pal.rB[f];
    for (let r = r0; r < r1; r++) { const xl = Math.round(RC[r] - RWD[r]); ctx.fillRect(xl, r, Math.round(RC[r] + RWD[r]) - xl, 1); }
    if (!band) {
      ctx.fillStyle = pal.ln[f];
      for (let r = r0; r < r1; r++) { const w = RWD[r], lw = Math.max(1, Math.round(w * 0.03)); ctx.fillRect(Math.round(RC[r] - w * 0.333 - lw / 2), r, lw, 1); ctx.fillRect(Math.round(RC[r] + w * 0.333 - lw / 2), r, lw, 1); }
    }
  }
  if (gk >= 0) ctx.stroke();
}
function pole(ctx, pal, f, sx, by, wd, clip, side) {
  if (sx < -12 || sx > W + 12) return;
  const h = wd * 0.85, pw = Math.max(1, Math.round(wd * 0.035)), top = Math.round(by - h), bot = Math.min(Math.round(by), clip);
  if (bot <= top) return;
  ctx.fillStyle = pal.pole[f]; ctx.fillRect(Math.round(sx - pw / 2), top, pw, bot - top);
  if (top < clip) { const lw = Math.max(2, Math.round(wd * 0.08)), lh = Math.max(1, Math.round(wd * 0.04)); ctx.fillStyle = pal.lamp[f]; ctx.fillRect(Math.round(sx - lw / 2 + side * lw * 0.3), top - lh, lw, lh); }
}
function renderSprites(ctx, s) {
  const abs0 = Math.floor(s.pos / SEG);
  for (let n = DRAW - 1; n >= 1; n--) {
    if (!PVAL[n] || !PVAL[n + 1]) continue;
    const a = abs0 + n, pi = ((a / STAGE_LEN) | 0) % NPAL, pal = PALS[pi], f = FL[n], clip = CLIPY[n];
    const sx = PX[n], by = PY[n], wd = PWD[n];
    if (clip <= PY[n + 1] - 2 && clip < by - 160) continue;
    if (a % 4 === 0 && wd > 2.5) { pole(ctx, pal, f, sx - wd * 1.3, by, wd, clip, -1); pole(ctx, pal, f, sx + wd * 1.3, by, wd, clip, 1); }
    if (a % 30 === 15 && wd > 1.2) {
      const side = (a / 30 & 1) ? 1 : -1, px = sx + side * wd * 3.1, hw = wd * 0.75, h = wd * 0.9;
      if (px > -hw - 4 && px < W + hw + 4) { ctx.fillStyle = pal.pole[f]; ctx.beginPath(); ctx.moveTo(px - hw, by); ctx.lineTo(px, by - h); ctx.lineTo(px + hw, by); ctx.fill(); ctx.strokeStyle = pal.grid[f]; ctx.beginPath(); ctx.moveTo(px - hw, by); ctx.lineTo(px, by - h); ctx.lineTo(px + hw, by); ctx.stroke(); }
    }
    if (a % STAGE_LEN === 0 && wd > 1) {
      const h = wd * 1.25, bt = Math.round(by - h), th = Math.max(2, Math.round(wd * 0.2)), xa = Math.round(sx - wd * 1.12), xb = Math.round(sx + wd * 1.12), pw = Math.max(1, Math.round(wd * 0.06));
      const bot = Math.min(Math.round(by), clip);
      if (bot > bt) {
        ctx.fillStyle = pal.pole[f]; ctx.fillRect(xa, bt, pw, bot - bt); ctx.fillRect(xb - pw, bt, pw, bot - bt);
        const cells = 10, cw = (xb - xa) / cells;
        for (let i = 0; i < cells; i++) { ctx.fillStyle = (i & 1) ? C.pink : '#ffffff'; ctx.fillRect(Math.round(xa + i * cw), bt, Math.max(1, Math.round(cw)), Math.min(th, bot - bt)); }
      }
    }
    for (let ci = BH[n]; ci >= 0; ci = NEXT[ci]) {
      const c = s.cars[ci], p = c.z / SEG - Math.floor(c.z / SEG);
      const cx = PX[n] + (PX[n + 1] - PX[n]) * p, cwd = PWD[n] + (PWD[n + 1] - PWD[n]) * p, cby = PY[n] + (PY[n + 1] - PY[n]) * p;
      drawTraffic(ctx, TRAFFIC[c.col], cx + cwd * c.x, cby, cwd * CARW, clip);
    }
  }
}
let TOUCH = null;
function renderHUD(ctx, G, s) {
  const x = s.tx;
  // progress to the next checkpoint
  ctx.fillStyle = '#1a1250'; ctx.fillRect(0, 22, W, 3);
  const prog = ((s.pos / SEG) % STAGE_LEN) / STAGE_LEN; ctx.fillStyle = C.cyan; ctx.fillRect(0, 22, Math.round(W * prog), 3); ctx.fillStyle = C.pink; ctx.fillRect(W - 2, 22, 2, 3);
  const sec = Math.max(0, Math.ceil(s.tl / 60));
  if (sec !== s.secShown) { s.secShown = sec; s.timeTxt = x.time + ' ' + sec; }
  const low = sec <= 10 && s.go <= 0;
  text(ctx, s.timeTxt, 8, 28, low && ((s.t >> 3) & 1) ? C.red : C.gold);
  const kmh = Math.round(s.spd / MAXSP * 300);
  if (kmh !== s.kmhShown && (s.t & 3) === 0) { s.kmhShown = kmh; s.kmhTxt = kmh + ' KM/H'; }
  text(ctx, s.kmhTxt, W - 8, 28, C.cyan, 8, 'right');
  if (s.go > 0) {
    const nn = Math.ceil(s.go / 50);
    if (nn <= 3) text(ctx, String(nn), W / 2, 76, C.gold, 24, 'center');
    if (TOUCH === null) TOUCH = !matchMedia('(pointer:fine)').matches;
    const l1 = TOUCH ? x.touch1 : x.key1, l2 = TOUCH ? x.touch2 : x.key2;
    ctx.fillStyle = 'rgba(5,3,12,.62)'; ctx.fillRect(0, 120, W, 28);
    text(ctx, l1, W / 2, 124, C.ink, 8, 'center'); text(ctx, l2, W / 2, 136, C.ink, 8, 'center');
  } else if (s.t - s.goAt < 50) text(ctx, x.go, W / 2, 76, C.lime, 24, 'center');
  if (s.banner > 0 && ((s.banner >> 2) & 1 || s.banner < 90)) { ctx.fillStyle = 'rgba(5,3,12,.62)'; ctx.fillRect(0, 58, W, 36); text(ctx, x.cp, W / 2, 62, C.gold, 10, 'center'); text(ctx, s.bonusTxt, W / 2, 80, C.ink, 8, 'center'); }
  if (s.pop > 0) text(ctx, s.popTxt, W / 2, 100 - (40 - s.pop) / 4, s.popV > 50 ? C.lime : C.cyan, 8, 'center');
  if (s.up > 0) text(ctx, x.up, W / 2, 76, C.red, 10, 'center');
}
function renderPlayer(ctx, s) {
  const bob = s.off && (s.t & 2) ? 1 : 0, lean = -Math.round(s.steer * 2);
  const x = W / 2 + Math.round(s.steer * 3);
  if (!(s.bump > 0 && (s.t >> 2) & 1)) drawCar(ctx, CAR_BIG, PLAYER_PAL, x, CARY + bob, 62, H, lean);
  if (s.spd > MAXSP * 0.8 && (s.t & 2)) { ctx.fillStyle = C.orange; ctx.fillRect(x - 15, CARY - 3, 2, 3); ctx.fillRect(x + 13, CARY - 3, 2, 3); }
}

/* ---------- the cabinet ---------- */
const neonRoad = {
  id: 'neonRoad', daily: true, name: 'NEON ROAD', year: '1985', blurb: 'Race the clock down a neon highway. Pass traffic, hit every checkpoint.', track: 'drive',
  help: '◀ ▶ steer · ▲ boost · ▼ brake', keys: '← → steer · ↑ gas · ↓ brake',
  init(G) {
    const s = { t: 0, go: COUNT, goAt: -999, pos: 0, spd: 0, px: 0, steer: 0, tl: START_TIME * 60, stage: 1, lastSeg: 0, bump: 0, shake: 0, off: false, up: 0,
      banner: 0, bonusTxt: '', pop: 0, popTxt: '', popV: 0, fade: 0, oldPal: 0, sky: 0, fx: [], cars: [], secShown: -1, timeTxt: '', kmhShown: -1, kmhTxt: '0 KM/H', lastTick: -1, passes: 0, crashes: 0, gasOn: false, brakeOn: false,
      tx: { time: T('TIME'), go: T('GO!'), cp: T('CHECKPOINT !'), up: T('TIME UP!'), touch1: T('TOUCH A SIDE TO STEER'), touch2: T('TOUCH THE TOP TO BRAKE'), key1: T('ARROWS TO STEER'), key2: T('UP GAS / DOWN BRAKE') } };
    buildRoad(s);
    for (let i = 0; i < POOL; i++) s.cars.push({ on: false, z: 0, x: 0, tx: 0, sp: 0, cruise: 0, col: 0, ahead: true, hit: false, swt: 0 });
    this.fill(s, 8);
    return s;
  },
  place(s, c, zmin, zmax) {
    let z = 0, lane = 0;
    for (let k = 0; k < 6; k++) {
      z = zmin + rnd(0, zmax - zmin); lane = LANES[ri(0, 2)];
      let ok = true; for (let j = 0; j < POOL; j++) { const o = s.cars[j]; if (o !== c && o.on && Math.abs(o.z - z) < 1500 && Math.abs(o.x - lane) < 0.5) { ok = false; break; } }
      if (ok) break;
    }
    c.on = true; c.z = z; c.x = c.tx = lane; c.cruise = c.sp = MAXSP * rnd(0.2, 0.5); c.col = ri(0, TRAFFIC.length - 1); c.ahead = true; c.hit = false; c.swt = ri(60, 300);
  },
  fill(s, n) {   // switch cars on until n are running
    let on = 0; for (const c of s.cars) if (c.on) on++;
    for (const c of s.cars) if (on < n && !c.on) { this.place(s, c, s.pos + PLAYERZ + 2500, s.pos + DRAW * SEG + 1500); on++; }
  },
  update(s, G) {
    s.t++;
    if (s.fade > 0) s.fade--;
    if (s.shake > 0) s.shake--; if (s.bump > 0) s.bump--; if (s.pop > 0) s.pop--; if (s.banner > 0) s.banner--;
    tickFx(s.fx);
    const abs0 = Math.floor(s.pos / SEG), curve = s.curve[abs0 % TL];
    if (s.go > 0) {   // 3-2-1: the clock waits
      s.go--; if (s.go === 0) { s.goAt = s.t; G.sfx('start'); } else if (s.go % 50 === 0) G.sfx('blip');
      return;
    }
    // ----- input: keys, joystick or screen touch (sides steer and drive, the top of the screen brakes)
    let tgt = (G.held('right') ? 1 : 0) - (G.held('left') ? 1 : 0), gas = G.held('up') || G.held('a'), brake = G.held('down');
    if (G.ptr.down) { if (G.ptr.y < 112) brake = true; else { tgt += G.ptr.x < W / 2 ? -1 : 1; gas = true; } }
    tgt = clamp(tgt, -1, 1);
    if (s.up > 0) { tgt = 0; gas = false; brake = true; }
    s.gasOn = gas; s.brakeOn = brake;
    s.steer += (tgt - s.steer) * 0.28;
    const pct = s.spd / MAXSP, ps = Math.max(pct, 0.25);
    s.px += s.steer * 0.034 * ps - 0.034 * pct * pct * curve * 0.26;
    if (s.px > 2.6) { s.px = 2.6; s.spd *= 0.96; } else if (s.px < -2.6) { s.px = -2.6; s.spd *= 0.96; }
    s.off = Math.abs(s.px) > 1.02;
    // ----- speed: it cruises by itself, gas goes to full, brake stops, the grass drags
    const ACC = MAXSP / 260, CRUISE = MAXSP * 0.62;
    if (brake) s.spd -= ACC * 3.2; else if (gas) s.spd += ACC; else if (s.spd < CRUISE) s.spd += ACC * 0.8; else s.spd -= ACC * 0.5;
    if (s.up > 0) s.spd -= ACC * 1.2;
    if (s.off && s.spd > MAXSP * 0.3) { s.spd -= ACC * 3; if (s.t % 8 === 0) G.sfx('thrust'); if (s.t % 3 === 0) boom(s.fx, W / 2 + (s.px > 0 ? 22 : -22), CARY - 2, C.dim, 2); }
    s.spd = clamp(s.spd, 0, MAXSP);
    s.pos += s.spd; s.sky += curve * (s.spd / MAXSP) * 0.9;
    const seg = Math.floor(s.pos / SEG);
    if (seg > s.lastSeg) { G.addScore(seg - s.lastSeg); s.lastSeg = seg; }
    // ----- the clock
    if (s.up > 0) { if (--s.up === 0) return G.over(); }
    else {
      s.tl--;
      const sec = Math.ceil(s.tl / 60);
      if (sec <= 10 && sec !== s.lastTick && sec > 0) { s.lastTick = sec; G.sfx('tick'); }
      if (s.tl <= 0) { s.tl = 0; s.up = 100; s.banner = 0; G.sfx('over'); }
      if (seg >= s.stage * STAGE_LEN && s.up === 0) {   // checkpoint
        const bonus = Math.max(20, 34 - 2 * s.stage); s.oldPal = (s.stage - 1) % NPAL; s.fade = 70;
        s.tl += bonus * 60; G.addScore(500 * s.stage); s.stage++; s.banner = 170; s.bonusTxt = T('+' + bonus + ' SEC'); G.sfx('levelup');
        this.fill(s, Math.min(POOL, 8 + s.stage * 3));
      }
    }
    // ----- traffic
    const pz = s.pos + PLAYERZ;
    for (let i = 0; i < POOL; i++) {
      const c = s.cars[i]; if (!c.on) continue;
      let sp = c.cruise;
      for (let j = 0; j < POOL; j++) { const o = s.cars[j]; if (o !== c && o.on && o.z > c.z && o.z - c.z < 1300 && Math.abs(o.x - c.x) < 0.45 && o.sp < sp) sp = o.sp; }
      c.sp = sp; c.z += sp;
      if (--c.swt <= 0) { c.swt = ri(90, 320); if (s.stage >= 2 && rnd(0, 1) < 0.5) c.tx = LANES[ri(0, 2)]; }
      c.x += clamp(c.tx - c.x, -0.01, 0.01);
      if (c.z < s.pos - 1500 || c.z > s.pos + (DRAW + 60) * SEG) { this.place(s, c, s.pos + DRAW * SEG, s.pos + DRAW * SEG + 2000); continue; }
      const dz = c.z - pz;
      if (c.ahead && dz <= 0) {
        c.ahead = false;
        if (!c.hit) { const close = Math.abs(c.x - s.px) < 0.62; s.passes++; G.addScore(close ? 100 : 50); s.pop = 40; s.popV = close ? 100 : 50; s.popTxt = '+' + s.popV; G.sfx('eat'); }
      }
      if (s.bump <= 0 && !c.hit && dz > -SEG * 0.7 && dz < SEG * 0.7 && Math.abs(c.x - s.px) < 0.42) {
        c.hit = true; c.z += SEG * 1.4; s.crashes++; s.bump = 50; s.shake = 14;
        s.spd = Math.min(s.spd, Math.max(c.sp * 0.6, MAXSP * 0.12)); s.px += (s.px >= c.x ? 1 : -1) * 0.14;
        boom(s.fx, W / 2, CARY - 18, C.orange, 18); G.sfx('boom');
      }
    }
  },
  draw(s, G, ctx) {
    LAST = s;
    project(s);
    const sh = s.shake > 0;
    if (sh) { ctx.save(); ctx.translate((s.t & 1) ? 1 : -1, (s.t & 2) ? 1 : 0); }
    renderWorld(ctx, s);
    renderSprites(ctx, s);
    renderPlayer(ctx, s);
    drawFx(ctx, s.fx);
    if (sh) ctx.restore();
    G.hud(null, T('STAGE ' + s.stage));
    renderHUD(ctx, G, s);
  },
  ghost(gs, ctx) {   // the challenger's car, faint, when they are ahead of you on the road
    const me = LAST; if (!me || !gs) return;
    const gap = (gs.pos - me.pos) / SEG; if (gap < 2 || gap >= DRAW - 1) return;
    const n = Math.floor(gap), p = gap - n; if (!PVAL[n] || !PVAL[n + 1]) return;
    const wd = PWD[n] + (PWD[n + 1] - PWD[n]) * p;
    drawTraffic(ctx, GHOST_PAL, PX[n] + (PX[n + 1] - PX[n]) * p + wd * gs.px, PY[n] + (PY[n + 1] - PY[n]) * p, wd * CARW, CLIPY[n]);
  },
  thumb(ctx, t) {
    const w = 112, h = 84, hz = 42;
    ctx.fillStyle = '#07031a'; ctx.fillRect(0, 0, w, h);
    const bands = ['#07031a', '#1d0a45', '#4a0f6e', '#a0207a', '#e0407a', '#ff8a3d'];
    for (let i = 0; i < bands.length; i++) { ctx.fillStyle = bands[i]; ctx.fillRect(0, i * 7, w, 8); }
    for (let y = 8; y < hz; y++) { const dy = y - 26, hw = Math.sqrt(Math.max(0, 19 * 19 - dy * dy)); if (dy > 0 && (dy % 5) < dy / 6) continue; ctx.fillStyle = y < 26 ? '#ffd23a' : y < 34 ? '#ff7a5a' : '#ff3d8b'; ctx.fillRect(56 - hw, y, hw * 2, 1); }
    ctx.fillStyle = '#2a0a4d'; ctx.beginPath(); ctx.moveTo(0, hz); ctx.lineTo(14, 26); ctx.lineTo(30, hz - 8); ctx.lineTo(40, hz); ctx.moveTo(72, hz); ctx.lineTo(90, 24); ctx.lineTo(112, hz - 10); ctx.lineTo(112, hz); ctx.fill();
    ctx.fillStyle = '#12072b'; ctx.fillRect(0, hz, w, h - hz);
    const f = (t * 0.03) % 1; ctx.fillStyle = '#ff3d8b';
    for (let i = 0; i < 6; i++) { const p = (i + f) / 6; ctx.fillRect(0, hz + Math.round((h - hz) * p * p), w, 1); }
    ctx.strokeStyle = '#ff3d8b'; ctx.lineWidth = 1; ctx.beginPath();
    for (let k = -5; k <= 5; k++) { ctx.moveTo(56 + k * 3, hz); ctx.lineTo(56 + k * 30, h); }
    ctx.stroke();
    ctx.fillStyle = '#1d1445'; ctx.beginPath(); ctx.moveTo(53, hz); ctx.lineTo(59, hz); ctx.lineTo(98, h); ctx.lineTo(14, h); ctx.fill();
    ctx.strokeStyle = '#2de2ff'; ctx.beginPath(); ctx.moveTo(53, hz); ctx.lineTo(14, h); ctx.moveTo(59, hz); ctx.lineTo(98, h); ctx.stroke();
    ctx.fillStyle = '#ffcf3a';
    for (let i = 0; i < 6; i++) { const p0 = (i + f) / 6, p1 = (i + f + 0.45) / 6, y0 = hz + (h - hz) * p0 * p0, y1 = hz + (h - hz) * p1 * p1; ctx.fillRect(55.5 + 0.2 * 0, Math.round(y0), Math.max(1, Math.round(1 + p0 * 2)), Math.max(1, Math.round(y1 - y0))); }
    drawCar(ctx, CAR_BIG, PLAYER_PAL, 56 + Math.sin(t / 40) * 6, 79, 28, h, 0);
  }
};
return neonRoad;
});
