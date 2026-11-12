/* NUTCADE arcade: engine + seven original 80s-style games */
(function(){
'use strict';
const W = 224, H = 288;
const A = () => window.NutAudio || { sfx() {}, music() {}, stopMusic() {} };
const store = window.NutStore || { get: (k, d) => d, set() {} };
const C = { bg: '#05030c', ink: '#ece7ff', dim: '#8b82b8', pink: '#ff3d8b', cyan: '#2de2ff', gold: '#ffcf3a', lime: '#5dff7a', red: '#ff5444', violet: '#8d6bff', orange: '#ff9a1f', white: '#ffffff', blue: '#3d6bff', brown: '#b8651f', wood: '#8a4b1c' };
// Gameplay randomness comes from RNG, which is seeded for each game so a challenge replays the same layout.
// Visual effects (stars, sparks) use their own randomness so they never shift the gameplay sequence.
let RNG = Math.random;
function seeded(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const rnd = (a, b) => a + RNG() * (b - a);
const frnd = (a, b) => a + Math.random() * (b - a);
const ri = (a, b) => Math.floor(rnd(a, b + 1));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const hitBox = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

/* ---------- drawing helpers ---------- */
function spr(ctx, rows, x, y, pal, s = 1, flip = false) {
  for (let r = 0; r < rows.length; r++) { const row = rows[r]; for (let c = 0; c < row.length; c++) { const ch = row[flip ? row.length - 1 - c : c]; if (ch === '.' || !pal[ch]) continue; ctx.fillStyle = pal[ch]; ctx.fillRect(Math.round(x + c * s), Math.round(y + r * s), s, s); } }
}
function text(ctx, s, x, y, col = C.ink, size = 8, align = 'left') {
  ctx.font = `${size}px "Press Start 2P", monospace`; ctx.textAlign = align; ctx.textBaseline = 'top'; ctx.fillStyle = col; ctx.fillText(s, Math.round(x), Math.round(y));
}
const pad6 = n => String(Math.max(0, Math.floor(n))).padStart(6, '0');

/* ---------- scores ---------- */
const scoresOf = id => store.get('scores:' + id, []);
function qualifies(id, s) { const l = scoresOf(id); return s > 0 && (l.length < 5 || s > l[l.length - 1].s); }
function addScore(id, n, s) { const l = scoresOf(id); l.push({ n: (n || 'AAA').toUpperCase().slice(0, 3), s, t: Date.now() }); l.sort((a, b) => b.s - a.s); store.set('scores:' + id, l.slice(0, 5)); }
const hiOf = id => (scoresOf(id)[0] || { s: 0 }).s;

/* =====================================================================
   GAME 1: STAR SWARM (fixed shooter)
===================================================================== */
const SHIP = ['.....c.....', '....ccc....', '....cwc....', '.c.cwwwc.c.', '.ccccwcccc.', 'ccccccccccc', 'cc.ppppp.cc', 'c...p.p...c'];
const ALIENS = [
  [['..yyyy..', '.yyyyyy.', 'yy.yy.yy', 'yyyyyyyy', '.y.yy.y.', 'y......y'], ['..yyyy..', '.yyyyyy.', 'yy.yy.yy', 'yyyyyyyy', '.y.yy.y.', '.y....y.']],
  [['.p....p.', '..pppp..', '.pwppwp.', 'pppppppp', 'p.pppp.p', '..p..p..'], ['.p....p.', 'p.pppp.p', 'ppwppwpp', 'pppppppp', '..pppp..', '.p....p.']],
  [['c......c', 'cc.cc.cc', 'cccccccc', '.cwccwc.', '..cccc..', '.c....c.'], ['.c....c.', 'cc.cc.cc', 'cccccccc', '.cwccwc.', '..cccc..', 'c......c']]
];
const APAL = { y: C.gold, p: C.pink, c: C.cyan, w: C.white };
const SPAL = { c: C.lime, w: C.white, p: C.pink };
const starfield = n => Array.from({ length: n }, () => ({ x: frnd(0, W), y: frnd(0, H), v: frnd(0.2, 1.2), c: [C.ink, C.cyan, C.pink, C.gold][Math.floor(frnd(0, 4))] }));
function drawStars(ctx, stars, dy = 1) { for (const s of stars) { s.y += s.v * dy; if (s.y > H) { s.y = 0; s.x = frnd(0, W); } ctx.fillStyle = s.c; ctx.globalAlpha = s.v > 0.8 ? 1 : 0.5; ctx.fillRect(s.x | 0, s.y | 0, 1, 1); } ctx.globalAlpha = 1; }
const starSwarm = {
  id: 'swarm', name: 'STAR SWARM', year: '1981', blurb: 'Blast the diving formation before it lands.', track: 'action',
  help: '◀ ▶ move · A fire', keys: '← → move · Space fire',
  init(G) { const s = { stars: starfield(60), p: { x: 106, y: 256, w: 11, h: 8, inv: 120 }, shots: [], bombs: [], fx: [], wave: 0, lives: 3, t: 0 }; this.wave(s); return s; },
  wave(s) {
    s.wave++; s.al = []; s.ox = 20; s.dx = 0.25 + s.wave * 0.06; s.delay = 90;
    for (let r = 0; r < 5; r++) for (let c = 0; c < 8; c++) s.al.push({ r, c, type: r === 0 ? 2 : r < 3 ? 1 : 0, hx: c * 22, hy: 40 + r * 18, x: 0, y: -40, dive: null, alive: true, w: 8, h: 6 });
  },
  update(s, G) {
    s.t++; const p = s.p; if (p.inv > 0) p.inv--;
    if (p.dead) { if (--p.dead === 0) { if (s.lives <= 0) return G.over(); p.x = 106; p.inv = 120; } }
    else {
      if (G.held('left')) p.x -= 1.8; if (G.held('right')) p.x += 1.8;
      if (G.ptr.down) p.x += clamp(G.ptr.x - 5 - p.x, -2, 2);
      p.x = clamp(p.x, 2, W - 13);
      if ((G.hit('a') || (G.held('a') && s.t % 14 === 0) || (G.ptr.down && s.t % 16 === 0)) && s.shots.length < 3) { s.shots.push({ x: p.x + 5, y: p.y - 2, w: 1, h: 4 }); G.sfx('shoot'); }
    }
    s.shots.forEach(b => b.y -= 4.5); s.shots = s.shots.filter(b => b.y > 16);
    s.ox += s.dx; if (s.ox > 52 || s.ox < 8) s.dx *= -1;
    if (s.delay > 0) s.delay--;
    const alive = s.al.filter(a => a.alive);
    for (const a of alive) {
      const tx = s.ox + a.hx, ty = a.hy + Math.sin((s.t + a.c * 6) / 30) * 2;
      if (!a.dive) { a.x += (tx - a.x) * 0.08; a.y += (ty - a.y) * 0.08; }
      else {
        a.dive.t++; const d = a.dive;
        a.y += d.vy; a.x += Math.sin(d.t / 14) * 1.8 + (d.tx - a.x) * 0.01;
        if (d.t % 40 === 20 && s.bombs.length < 6) s.bombs.push({ x: a.x + 4, y: a.y + 6, w: 2, h: 4, v: 1.6 + s.wave * 0.1 });
        if (a.y > H + 8) { a.dive = null; a.y = -10; }
      }
      if (!a.dive && s.delay === 0 && RNG() < 0.0016 + s.wave * 0.0006) a.dive = { t: 0, vy: 1.2 + s.wave * 0.12, tx: p.x };
      if (!a.dive && s.delay === 0 && RNG() < 0.0008 * s.wave && s.bombs.length < 6) s.bombs.push({ x: a.x + 4, y: a.y + 6, w: 2, h: 4, v: 1.4 + s.wave * 0.1 });
      for (const b of s.shots) if (!b.gone && hitBox(b, a)) { b.gone = true; a.alive = false; G.addScore(a.dive ? (a.type + 1) * 40 : (a.type + 1) * 10); G.sfx('pop'); boom(s.fx, a.x + 4, a.y + 3, APAL[['y', 'p', 'c'][a.type]]); }
      if (!p.dead && !p.inv && hitBox(a, p)) { a.alive = false; kill(s, G); }
    }
    s.shots = s.shots.filter(b => !b.gone);
    s.bombs.forEach(b => b.y += b.v); s.bombs = s.bombs.filter(b => b.y < H);
    if (!p.dead && !p.inv) for (const b of s.bombs) if (hitBox(b, p)) { b.y = H + 9; kill(s, G); }
    tickFx(s.fx);
    if (!s.al.some(a => a.alive)) { G.sfx('levelup'); G.addScore(500 * s.wave); this.wave(s); }
    function kill(s, G) { s.lives--; s.p.dead = 90; boom(s.fx, s.p.x + 5, s.p.y + 4, C.lime, 30); G.sfx('die'); }
  },
  draw(s, G, ctx) {
    drawStars(ctx, s.stars, 0.6);
    for (const a of s.al) if (a.alive) spr(ctx, ALIENS[a.type][(s.t >> 4) & 1], a.x, a.y, APAL);
    if (!s.p.dead && !(s.p.inv && (s.t >> 2) & 1)) spr(ctx, SHIP, s.p.x, s.p.y, SPAL);
    ctx.fillStyle = C.white; s.shots.forEach(b => ctx.fillRect(b.x, b.y, 1, 4));
    ctx.fillStyle = C.red; s.bombs.forEach(b => { ctx.fillRect(b.x, b.y, 2, 4); });
    drawFx(ctx, s.fx);
    G.hud(s.lives, 'WAVE ' + s.wave);
    if (s.delay > 30) text(ctx, 'WAVE ' + s.wave, W / 2, 140, C.gold, 8, 'center');
  },
  thumb(ctx, t) { ctx.fillStyle = C.bg; ctx.fillRect(0, 0, 112, 84); for (let i = 0; i < 4; i++) for (let r = 0; r < 3; r++) spr(ctx, ALIENS[r][(t >> 4) & 1], 16 + i * 22 + Math.sin(t / 30) * 6, 10 + r * 12, APAL); spr(ctx, SHIP, 50 + Math.sin(t / 20) * 30, 70, SPAL); ctx.fillStyle = '#fff'; ctx.fillRect(56 + Math.sin(t / 20) * 30, 60 - (t * 3) % 40, 1, 4); }
};
function boom(fx, x, y, col, n = 14) { for (let i = 0; i < n; i++) { const a = frnd(0, 6.28), v = frnd(0.4, 2); fx.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 14 + Math.floor(frnd(0, 17)), col }); } }
function tickFx(fx) { for (const f of fx) { f.x += f.vx; f.y += f.vy; f.vx *= 0.96; f.vy *= 0.96; f.life--; } for (let i = fx.length - 1; i >= 0; i--) if (fx[i].life <= 0) fx.splice(i, 1); }
function drawFx(ctx, fx) { for (const f of fx) { ctx.fillStyle = f.life < 8 ? C.dim : f.col; ctx.fillRect(f.x | 0, f.y | 0, 1, 1); } }

/* =====================================================================
   GAME 2: NUT MAZE (maze chase, procedurally built each level)
===================================================================== */
const MW = 27, MH = 31, TS = 8, MOX = 4, MOY = 24;
function buildMaze() {
  const g = Array.from({ length: MH }, () => Array(MW).fill(1));
  const half = 13;
  const cells = []; for (let y = 1; y < MH - 1; y += 2) for (let x = 1; x <= half; x += 2) cells.push([x, y]);
  const seen = new Set(); const key = (x, y) => x + ',' + y;
  const stack = [[1 + 2 * ri(0, 6), 1 + 2 * ri(0, 14)]]; seen.add(key(...stack[0])); g[stack[0][1]][stack[0][0]] = 0;
  while (stack.length) {
    const [x, y] = stack[stack.length - 1];
    const n = [[2, 0], [-2, 0], [0, 2], [0, -2]].map(([dx, dy]) => [x + dx, y + dy, dx, dy]).filter(([nx, ny]) => nx >= 1 && nx <= half && ny >= 1 && ny < MH - 1 && !seen.has(key(nx, ny)));
    if (!n.length) { stack.pop(); continue; }
    const [nx, ny, dx, dy] = n[ri(0, n.length - 1)];
    g[y + dy / 2][x + dx / 2] = 0; g[ny][nx] = 0; seen.add(key(nx, ny)); stack.push([nx, ny]);
  }
  // braid: remove dead ends on the left half
  for (const [x, y] of cells) {
    const open = [[1, 0], [-1, 0], [0, 1], [0, -1]].filter(([dx, dy]) => g[y + dy][x + dx] === 0);
    if (open.length <= 1) {
      const opts = [[1, 0], [-1, 0], [0, 1], [0, -1]].filter(([dx, dy]) => g[y + dy][x + dx] === 1 && x + dx * 2 >= 1 && x + dx * 2 <= half && y + dy * 2 >= 1 && y + dy * 2 < MH - 1);
      if (opts.length) { const [dx, dy] = opts[ri(0, opts.length - 1)]; g[y + dy][x + dx] = 0; }
    }
  }
  // extra loops for flow
  for (let i = 0; i < 14; i++) { const x = 1 + 2 * ri(0, 6), y = 2 + 2 * ri(0, 13); if (x + 1 <= half && RNG() < 0.5) g[y - 1][x + 1] = 0; else g[y][x] = 0; }
  for (let y = 0; y < MH; y++) for (let x = 0; x < half; x++) g[y][MW - 1 - x] = g[y][x];
  for (let y = 0; y < MH; y++) { g[y][0] = 1; g[y][MW - 1] = 1; } for (let x = 0; x < MW; x++) { g[0][x] = 1; g[MH - 1][x] = 1; }
  return g;
}
const NUTBOT = ['..gggg..', '.gggggg.', 'ggwkgwkg', 'gggggggg', 'gg.gg.gg', 'gggggggg', '.gg..gg.', '.g....g.'];
const AUDITOR = [['...r....', '.rrrrrr.', 'rrwkrwkr', 'rrrrrrrr', 'rr.rr.rr', 'rrrrrrrr', 'r.r..r.r', 'r......r'], ['....r...', '.rrrrrr.', 'rrkwrkwr', 'rrrrrrrr', 'rr.rr.rr', 'rrrrrrrr', '.r.rr.r.', 'r......r']];
const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const OPP = { up: 'down', down: 'up', left: 'right', right: 'left' };
const nutMaze = {
  id: 'maze', name: 'NUT MAZE', year: '1980', blurb: 'Gobble every nut. Golden acorns turn the auditors.', track: 'bounce',
  help: '✚ or swipe to steer', keys: 'Arrow keys steer',
  init(G) { const s = { lives: 3, level: 0, t: 0 }; this.level(s); return s; },
  level(s) {
    s.level++; s.g = buildMaze(); s.nuts = new Set(); s.power = new Set();
    for (let y = 1; y < MH - 1; y++) for (let x = 1; x < MW - 1; x++) if (s.g[y][x] === 0) s.nuts.add(x + ',' + y);
    const corners = [[1, 1], [MW - 2, 1], [1, MH - 2], [MW - 2, MH - 2]];
    for (const [x, y] of corners) { const k = this.nearestOpen(s, x, y); s.power.add(k); s.nuts.delete(k); }
    this.reset(s); s.ready = 120;
  },
  nearestOpen(s, x, y) { for (let r = 0; r < 8; r++) for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) { const X = x + dx, Y = y + dy; if (s.g[Y] && s.g[Y][X] === 0) return X + ',' + Y; } return '1,1'; },
  reset(s) {
    const [px, py] = this.nearestOpen(s, 13, 23).split(',').map(Number);
    s.p = { tx: px, ty: py, x: px * TS, y: py * TS, dir: 'left', want: 'left', sp: 1.0 + s.level * 0.03, acc: 0 };
    s.nuts.delete(px + ',' + py);
    const [ex, ey] = this.nearestOpen(s, 13, 7).split(',').map(Number);
    const cols = [C.red, C.pink, C.cyan, C.orange];
    s.en = cols.map((c, i) => ({ tx: ex, ty: ey, x: ex * TS, y: ey * TS, dir: ['left', 'right', 'up', 'down'][i], col: c, mode: i, wait: i * 150, sp: 0.85 + s.level * 0.04, acc: 0, eaten: 0 }));
    s.fright = 0; s.combo = 0;
  },
  open(s, tx, ty) { return s.g[ty] && s.g[ty][tx] === 0; },
  step(s, e, choose) {
    e.acc += e.speed;
    while (e.acc >= 1) {
      e.acc -= 1;
      if (e.x === e.tx * TS && e.y === e.ty * TS) {
        choose(e);
        const [dx, dy] = DIRS[e.dir];
        if (!this.open(s, e.tx + dx, e.ty + dy)) return;
        e.tx += dx; e.ty += dy;
      }
      const gx = e.tx * TS, gy = e.ty * TS;
      e.x += Math.sign(gx - e.x); e.y += Math.sign(gy - e.y);
    }
  },
  update(s, G) {
    s.t++;
    if (s.ready > 0) { s.ready--; return; }
    if (s.dying) { if (--s.dying === 0) { if (s.lives <= 0) return G.over(); this.reset(s); s.ready = 60; } return; }
    const p = s.p;
    for (const d of ['up', 'down', 'left', 'right']) if (G.hit(d) || G.swipe === d) p.want = d;
    p.speed = p.sp;
    this.step(s, p, e => { const [dx, dy] = DIRS[e.want]; if (this.open(s, e.tx + dx, e.ty + dy)) e.dir = e.want; });
    const k = p.tx + ',' + p.ty;
    {
      const near = Math.abs(p.x - p.tx * TS) + Math.abs(p.y - p.ty * TS) < 4;
      if (near && s.nuts.delete(k)) { G.addScore(10); if (s.t % 2 === 0) G.sfx('eat'); }
      if (near && s.power.delete(k)) { G.addScore(50); s.fright = 420 - Math.min(300, s.level * 30); s.combo = 0; G.sfx('power'); s.en.forEach(e => { if (!e.eaten) e.dir = OPP[e.dir]; }); }
    }
    if (s.fright > 0) s.fright--;
    for (const e of s.en) {
      if (e.wait > 0) { e.wait--; continue; }
      const scared = s.fright > 0 && !e.eaten;
      e.speed = e.eaten ? 2 : scared ? e.sp * 0.6 : e.sp;
      this.step(s, e, en => {
        const opts = Object.keys(DIRS).filter(d => d !== OPP[en.dir] && this.open(s, en.tx + DIRS[d][0], en.ty + DIRS[d][1]));
        if (!opts.length) { en.dir = OPP[en.dir]; return; }
        let tx = p.tx, ty = p.ty;
        if (en.eaten) { tx = 13; ty = 7; if (Math.abs(en.tx - 13) + Math.abs(en.ty - 7) < 2) en.eaten = 0; }
        else if (en.mode === 1) { tx += DIRS[p.dir][0] * 4; ty += DIRS[p.dir][1] * 4; }
        else if (en.mode === 2 && (s.t >> 8) & 1) { tx = 1; ty = MH - 2; }
        else if (en.mode === 3 && Math.abs(en.tx - p.tx) + Math.abs(en.ty - p.ty) < 8) { tx = MW - 2; ty = 1; }
        if (scared || RNG() < 0.12) { en.dir = opts[ri(0, opts.length - 1)]; return; }
        opts.sort((a, b) => ((en.tx + DIRS[a][0] - tx) ** 2 + (en.ty + DIRS[a][1] - ty) ** 2) - ((en.tx + DIRS[b][0] - tx) ** 2 + (en.ty + DIRS[b][1] - ty) ** 2));
        en.dir = opts[0];
      });
      if (Math.abs(e.x - p.x) < 6 && Math.abs(e.y - p.y) < 6) {
        if (e.eaten) continue;
        if (scared) { e.eaten = 1; s.combo++; G.addScore(200 * 2 ** (s.combo - 1)); G.sfx('gulp'); }
        else { s.lives--; s.dying = 100; G.sfx('die'); return; }
      }
    }
    if (!s.nuts.size && !s.power.size) { G.sfx('levelup'); G.addScore(1000); this.level(s); }
  },
  draw(s, G, ctx) {
    const flash = !s.nuts.size;
    for (let y = 0; y < MH; y++) for (let x = 0; x < MW; x++) if (s.g[y][x]) {
      const X = MOX + x * TS, Y = MOY + y * TS;
      ctx.fillStyle = '#1a1250'; ctx.fillRect(X, Y, TS, TS);
      ctx.fillStyle = C.violet;
      if (!s.g[y - 1] || !s.g[y - 1][x]) ctx.fillRect(X, Y, TS, 1);
      if (!s.g[y + 1] || !s.g[y + 1][x]) ctx.fillRect(X, Y + TS - 1, TS, 1);
      if (!s.g[y][x - 1]) ctx.fillRect(X, Y, 1, TS);
      if (!s.g[y][x + 1]) ctx.fillRect(X + TS - 1, Y, 1, TS);
    }
    ctx.fillStyle = C.orange;
    for (const k of s.nuts) { const [x, y] = k.split(',').map(Number); ctx.fillRect(MOX + x * TS + 3, MOY + y * TS + 3, 2, 2); }
    for (const k of s.power) { if ((s.t >> 3) & 1) continue; const [x, y] = k.split(',').map(Number); spr(ctx, ['.33.', '2222', '1111', '.11.'], MOX + x * TS + 2, MOY + y * TS + 2, { 1: C.gold, 2: C.brown, 3: '#5a3110' }); }
    const p = s.p;
    if (!s.dying || (s.dying >> 2) & 1) spr(ctx, NUTBOT, MOX + p.x, MOY + p.y, { g: C.lime, w: C.white, k: '#000' }, 1, p.dir === 'left');
    for (const e of s.en) {
      const scared = s.fright > 0 && !e.eaten;
      const col = e.eaten ? 'rgba(0,0,0,0)' : scared ? (s.fright < 90 && (s.t >> 3) & 1 ? C.white : C.blue) : e.col;
      spr(ctx, AUDITOR[(s.t >> 3) & 1], MOX + e.x, MOY + e.y, { r: col, w: C.white, k: e.eaten ? C.white : C.blue });
    }
    G.hud(s.lives, 'LV ' + s.level);
    if (s.ready > 0) text(ctx, 'READY!', W / 2, MOY + 15 * TS, C.gold, 8, 'center');
  },
  thumb(ctx, t) {
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, 112, 84); ctx.strokeStyle = C.violet; ctx.lineWidth = 2;
    ctx.strokeRect(4, 4, 104, 76); ctx.strokeRect(22, 22, 68, 40); ctx.beginPath(); ctx.moveTo(56, 4); ctx.lineTo(56, 22); ctx.moveTo(56, 62); ctx.lineTo(56, 80); ctx.stroke();
    const x = (t * 0.8) % 112; ctx.fillStyle = C.orange; for (let i = 0; i < 12; i++) if (i * 9 > x) ctx.fillRect(i * 9 + 4, 12, 2, 2);
    spr(ctx, NUTBOT, x, 9, { g: C.lime, w: '#fff', k: '#000' }); spr(ctx, AUDITOR[(t >> 3) & 1], x - 22, 9, { r: C.red, w: '#fff', k: C.blue }); spr(ctx, AUDITOR[0], 90, 66, { r: C.cyan, w: '#fff', k: C.blue });
  }
};

/* =====================================================================
   GAME 3: BRICK BLITZ (paddle & ball)
===================================================================== */
const BRICK_COLS = [C.red, C.orange, C.gold, C.lime, C.cyan, C.blue, C.violet, C.pink];
const LAYOUTS = [
  r => true,
  (r, c) => (r + c) % 2 === 0 || r < 2,
  (r, c) => Math.abs(c - 5.5) < r + 1.5,
  (r, c) => c % 3 !== 1 || r % 2 === 0,
  (r, c) => !(r > 1 && r < 6 && c > 2 && c < 9) || r === 4
];
const brickBlitz = {
  id: 'brick', name: 'BRICK BLITZ', year: '1986', blurb: 'Smash the wall. Catch the ball. Keep the streak.', track: 'bounce',
  help: '◀ ▶ or drag · A launch', keys: '← → move · Space launch',
  init(G) { const s = { lives: 3, level: 0, t: 0, fx: [] }; this.level(s); return s; },
  level(s) {
    s.level++; s.bricks = []; const lay = LAYOUTS[(s.level - 1) % LAYOUTS.length];
    for (let r = 0; r < 8; r++) for (let c = 0; c < 12; c++) if (lay(r, c)) s.bricks.push({ x: 16 + c * 16, y: 52 + r * 9, w: 15, h: 8, col: BRICK_COLS[r], hp: r === 0 && s.level > 1 ? 2 : 1, pts: (8 - r) * 10 });
    s.pad = { x: 96, y: 262, w: 32, h: 5 }; this.serve(s);
  },
  serve(s) { s.ball = { x: s.pad.x + 15, y: s.pad.y - 4, vx: 0, vy: 0, r: 2, stuck: true }; s.speed = 2.1 + s.level * 0.15; },
  update(s, G) {
    s.t++; const p = s.pad, b = s.ball;
    if (G.held('left')) p.x -= 3.2; if (G.held('right')) p.x += 3.2;
    if (G.ptr.down) p.x = G.ptr.x - p.w / 2;
    p.x = clamp(p.x, 8, W - 8 - p.w);
    if (b.stuck) { b.x = p.x + p.w / 2; b.y = p.y - 3; if (G.hit('a') || G.tap) { b.stuck = false; const a = rnd(-0.6, 0.6); b.vx = Math.sin(a) * s.speed; b.vy = -Math.cos(a) * s.speed; G.sfx('hit'); } }
    else {
      const steps = 3;
      for (let i = 0; i < steps; i++) {
        b.x += b.vx / steps; b.y += b.vy / steps;
        if (b.x < 10) { b.x = 10; b.vx = Math.abs(b.vx); G.sfx('wall'); } if (b.x > W - 10) { b.x = W - 10; b.vx = -Math.abs(b.vx); G.sfx('wall'); }
        if (b.y < 30) { b.y = 30; b.vy = Math.abs(b.vy); G.sfx('wall'); }
        if (b.vy > 0 && b.y + 2 >= p.y && b.y < p.y + p.h && b.x > p.x - 2 && b.x < p.x + p.w + 2) {
          const rel = (b.x - (p.x + p.w / 2)) / (p.w / 2); const a = rel * 1.05;
          s.speed = Math.min(s.speed + 0.03, 4.5); b.vx = Math.sin(a) * s.speed; b.vy = -Math.cos(a) * s.speed; b.y = p.y - 3; G.sfx('hit');
        }
        for (const k of s.bricks) {
          if (k.dead) continue;
          if (b.x + 2 > k.x && b.x - 2 < k.x + k.w && b.y + 2 > k.y && b.y - 2 < k.y + k.h) {
            const ox = Math.min(b.x + 2 - k.x, k.x + k.w - (b.x - 2)), oy = Math.min(b.y + 2 - k.y, k.y + k.h - (b.y - 2));
            if (ox < oy) b.vx *= -1; else b.vy *= -1;
            if (--k.hp <= 0) { k.dead = true; G.addScore(k.pts); boom(s.fx, k.x + 8, k.y + 4, k.col, 8); }
            G.sfx('brick'); break;
          }
        }
      }
      if (b.y > H) { s.lives--; G.sfx('die'); if (s.lives <= 0) return G.over(); this.serve(s); }
    }
    s.bricks = s.bricks.filter(k => !k.dead);
    tickFx(s.fx);
    if (!s.bricks.length) { G.sfx('levelup'); G.addScore(1000); this.level(s); }
  },
  draw(s, G, ctx) {
    ctx.fillStyle = '#120c2e'; ctx.fillRect(0, 26, W, H); ctx.fillStyle = C.violet; ctx.fillRect(6, 26, 2, H); ctx.fillRect(W - 8, 26, 2, H); ctx.fillRect(6, 26, W - 12, 2);
    for (const k of s.bricks) { ctx.fillStyle = k.col; ctx.fillRect(k.x, k.y, k.w, k.h); ctx.fillStyle = 'rgba(255,255,255,.35)'; ctx.fillRect(k.x, k.y, k.w, 1); ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(k.x, k.y + k.h - 1, k.w, 1); if (k.hp > 1) { ctx.fillStyle = '#fff'; ctx.fillRect(k.x + 6, k.y + 3, 3, 2); } }
    const p = s.pad; ctx.fillStyle = C.cyan; ctx.fillRect(p.x, p.y, p.w, p.h); ctx.fillStyle = C.pink; ctx.fillRect(p.x, p.y, 4, p.h); ctx.fillRect(p.x + p.w - 4, p.y, 4, p.h); ctx.fillStyle = '#fff'; ctx.fillRect(p.x + 4, p.y, p.w - 8, 1);
    ctx.fillStyle = '#fff'; ctx.fillRect(s.ball.x - 2, s.ball.y - 2, 4, 4);
    drawFx(ctx, s.fx); G.hud(s.lives, 'LV ' + s.level);
    if (s.ball.stuck) text(ctx, 'A / TAP TO LAUNCH', W / 2, 200, C.gold, 8, 'center');
  },
  thumb(ctx, t) { ctx.fillStyle = '#120c2e'; ctx.fillRect(0, 0, 112, 84); for (let r = 0; r < 5; r++) for (let c = 0; c < 7; c++) if ((r * 7 + c + (t >> 5)) % 9) { ctx.fillStyle = BRICK_COLS[r]; ctx.fillRect(6 + c * 14.5, 8 + r * 7, 13, 5); } const bx = 56 + Math.sin(t / 17) * 44, by = 45 + Math.abs(Math.sin(t / 23)) * 28; ctx.fillStyle = '#fff'; ctx.fillRect(bx, by, 3, 3); ctx.fillStyle = C.cyan; ctx.fillRect(bx - 12, 76, 26, 3); }
};

/* =====================================================================
   GAME 4: VOID ROCKS (vector rock shooter)
===================================================================== */
function makeRock(x, y, size, lvl) {
  const r = [0, 6, 11, 18][size]; const n = 10; const pts = [];
  for (let i = 0; i < n; i++) { const a = i / n * Math.PI * 2; const rr = r * rnd(0.7, 1.15); pts.push([Math.cos(a) * rr, Math.sin(a) * rr]); }
  const a = rnd(0, 6.28), v = rnd(0.3, 0.8) + (3 - size) * 0.25 + lvl * 0.05;
  return { x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, r, size, pts, rot: 0, vr: rnd(-0.03, 0.03) };
}
const wrap = o => { if (o.x < 0) o.x += W; if (o.x > W) o.x -= W; if (o.y < 24) o.y += H - 24; if (o.y > H) o.y -= H - 24; };
const voidRocks = {
  id: 'rocks', name: 'VOID ROCKS', year: '1979', blurb: 'Drift, spin, and split the space rocks to dust.', track: 'action',
  help: '◀ ▶ turn · ▲ thrust · A fire', keys: '← → turn · ↑ thrust · Space fire',
  init(G) { const s = { lives: 3, wave: 0, t: 0, shots: [], fx: [], stars: starfield(30) }; this.ship(s); this.wave(s); return s; },
  ship(s) { s.p = { x: W / 2, y: 156, a: -Math.PI / 2, vx: 0, vy: 0, inv: 150 }; },
  wave(s) { s.wave++; s.rocks = []; for (let i = 0; i < 3 + s.wave; i++) { let x, y; do { x = rnd(0, W); y = rnd(24, H); } while (Math.hypot(x - s.p.x, y - s.p.y) < 60); s.rocks.push(makeRock(x, y, 3, s.wave)); } },
  update(s, G) {
    s.t++; const p = s.p;
    if (p.dead) { if (--p.dead === 0) { if (s.lives <= 0) return G.over(); this.ship(s); } }
    else {
      if (p.inv > 0) p.inv--;
      if (G.held('left')) p.a -= 0.075; if (G.held('right')) p.a += 0.075;
      p.thr = G.held('up');
      if (p.thr) { p.vx += Math.cos(p.a) * 0.07; p.vy += Math.sin(p.a) * 0.07; if (s.t % 6 === 0) G.sfx('thrust'); }
      p.vx *= 0.99; p.vy *= 0.99; const sp = Math.hypot(p.vx, p.vy); if (sp > 3.2) { p.vx *= 3.2 / sp; p.vy *= 3.2 / sp; }
      p.x += p.vx; p.y += p.vy; wrap(p);
      if ((G.hit('a') || (G.held('a') && s.t % 12 === 0)) && s.shots.length < 5) { s.shots.push({ x: p.x + Math.cos(p.a) * 7, y: p.y + Math.sin(p.a) * 7, vx: Math.cos(p.a) * 4.2 + p.vx, vy: Math.sin(p.a) * 4.2 + p.vy, life: 52 }); G.sfx('laser'); }
    }
    for (const b of s.shots) { b.x += b.vx; b.y += b.vy; wrap(b); b.life--; }
    const born = [];
    for (const r of s.rocks) {
      r.x += r.vx; r.y += r.vy; r.rot += r.vr; wrap(r);
      for (const b of s.shots) if (b.life > 0 && Math.hypot(b.x - r.x, b.y - r.y) < r.r) {
        b.life = 0; r.dead = true; G.addScore([0, 100, 50, 20][r.size]); G.sfx(r.size === 3 ? 'boom' : 'pop'); boom(s.fx, r.x, r.y, C.ink, 10);
        if (r.size > 1) for (let i = 0; i < 2; i++) born.push(makeRock(r.x, r.y, r.size - 1, s.wave));
        break;
      }
      if (!p.dead && !p.inv && Math.hypot(p.x - r.x, p.y - r.y) < r.r + 4) { s.lives--; p.dead = 100; boom(s.fx, p.x, p.y, C.cyan, 30); G.sfx('die'); }
    }
    s.shots = s.shots.filter(b => b.life > 0);
    s.rocks = s.rocks.filter(r => !r.dead).concat(born);
    tickFx(s.fx);
    if (!s.rocks.length) { G.sfx('levelup'); this.wave(s); }
  },
  draw(s, G, ctx) {
    drawStars(ctx, s.stars, 0);
    ctx.lineWidth = 1; ctx.strokeStyle = C.ink; ctx.shadowColor = C.cyan; ctx.shadowBlur = 4;
    for (const r of s.rocks) { ctx.beginPath(); r.pts.forEach(([x, y], i) => { const c = Math.cos(r.rot), sn = Math.sin(r.rot); const X = r.x + x * c - y * sn, Y = r.y + x * sn + y * c; i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); ctx.closePath(); ctx.stroke(); }
    const p = s.p;
    if (!p.dead && !(p.inv && (s.t >> 2) & 1)) {
      const pt = (d, a) => [p.x + Math.cos(p.a + a) * d, p.y + Math.sin(p.a + a) * d];
      ctx.strokeStyle = C.cyan; ctx.beginPath(); ctx.moveTo(...pt(8, 0)); ctx.lineTo(...pt(6, 2.5)); ctx.lineTo(...pt(3, Math.PI)); ctx.lineTo(...pt(6, -2.5)); ctx.closePath(); ctx.stroke();
      if (p.thr && (s.t >> 1) & 1) { ctx.strokeStyle = C.orange; ctx.beginPath(); ctx.moveTo(...pt(4, 2.8)); ctx.lineTo(...pt(10, Math.PI)); ctx.lineTo(...pt(4, -2.8)); ctx.stroke(); }
    }
    ctx.shadowBlur = 0; ctx.fillStyle = C.gold; s.shots.forEach(b => ctx.fillRect(b.x - 1, b.y - 1, 2, 2));
    drawFx(ctx, s.fx); G.hud(s.lives, 'WAVE ' + s.wave);
  },
  thumb(ctx, t) { ctx.fillStyle = C.bg; ctx.fillRect(0, 0, 112, 84); ctx.strokeStyle = C.ink; ctx.lineWidth = 1; [[20, 20, 12], [86, 30, 9], [60, 66, 6], [30, 64, 5]].forEach(([x, y, r], i) => { ctx.beginPath(); for (let k = 0; k < 9; k++) { const a = k / 9 * 6.28 + t / 60 * (i % 2 ? 1 : -1); const rr = r * (k % 2 ? .8 : 1.05); ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); } ctx.closePath(); ctx.stroke(); }); const a = t / 25; ctx.strokeStyle = C.cyan; ctx.beginPath(); ctx.moveTo(56 + Math.cos(a) * 7, 42 + Math.sin(a) * 7); ctx.lineTo(56 + Math.cos(a + 2.5) * 5, 42 + Math.sin(a + 2.5) * 5); ctx.lineTo(56 + Math.cos(a - 2.5) * 5, 42 + Math.sin(a - 2.5) * 5); ctx.closePath(); ctx.stroke(); ctx.fillStyle = C.gold; ctx.fillRect(56 + Math.cos(a) * (12 + (t * 2) % 30), 42 + Math.sin(a) * (12 + (t * 2) % 30), 2, 2); }
};

/* =====================================================================
   GAME 5: HOP LANES (road & river crossing)
===================================================================== */
const HT = 16, HOY = 32, HCOLS = 14;
const BUNNY = ['.w....w.', '.wp..pw.', '.wp..pw.', '..wwww..', '.wkwwkw.', '.wwppww.', 'wwwwwwww', '.w.ww.w.'];
const CAR = [['..rrrrrrrr....', '.rrccrrrccr...', 'rrrrrrrrrrrrr.', 'rrrrrrrrrrrrrr', '.kk.......kk..'], ['....yyyyyyyy..', '...yccyyyccyy.', '.yyyyyyyyyyyyy', 'yyyyyyyyyyyyyy', '..kk.......kk.']];
const hopLanes = {
  id: 'hop', name: 'HOP LANES', year: '1981', blurb: 'Dodge traffic, ride the logs, fill every burrow.', track: 'bounce',
  help: '✚ or swipe to hop', keys: 'Arrow keys hop',
  init(G) { const s = { lives: 3, level: 0, t: 0, fx: [] }; this.level(s); return s; },
  level(s) {
    s.level++; s.homes = [false, false, false, false, false]; const L = s.level;
    const lane = (row, kind, speed, len, gap, col) => { const items = []; let x = rnd(0, 40); while (x < W + 60) { items.push({ x, w: len * HT }); x += len * HT + gap * HT + rnd(0, 20); } return { row, kind, speed: speed * (1 + L * 0.12), items, col, span: x }; };
    s.lanes = [
      lane(1, 'log', -0.5, 3, 2, C.wood), lane(2, 'log', 0.8, 4, 3, C.wood), lane(3, 'log', -0.7, 2, 2, C.wood), lane(4, 'log', 0.45, 5, 3, C.wood), lane(5, 'log', -0.9, 3, 3, C.wood),
      lane(7, 'car', 0.9, 1, 4, 1), lane(8, 'car', -0.6, 2, 4, 0), lane(9, 'car', 1.2, 1, 5, 1), lane(10, 'car', -0.8, 1, 3, 0), lane(11, 'car', 0.55, 2, 4, 1)
    ];
    this.reset(s);
  },
  reset(s) { s.p = { x: 7 * HT - 8, row: 12, hop: 0 }; s.best = 12; s.time = 60 * 30; },
  die(s, G, how) { s.lives--; s.dead = 70; G.sfx(how === 'water' ? 'splash' : 'die'); boom(s.fx, s.p.x + 8, HOY + s.p.row * HT + 8, how === 'water' ? C.cyan : C.pink, 18); },
  update(s, G) {
    s.t++; tickFx(s.fx);
    for (const l of s.lanes) for (const it of l.items) { it.x += l.speed; if (l.speed > 0 && it.x > W + 10) it.x -= l.span; if (l.speed < 0 && it.x + it.w < -10) it.x += l.span; }
    if (s.dead) { if (--s.dead === 0) { if (s.lives <= 0) return G.over(); this.reset(s); } return; }
    const p = s.p; if (p.hop > 0) p.hop--;
    s.time--; if (s.time <= 0) return this.die(s, G, 'time');
    let moved = null; for (const d of ['up', 'down', 'left', 'right']) if (G.hit(d) || G.swipe === d) moved = d;
    if (G.tap && !moved) moved = 'up';
    if (moved && p.hop === 0) {
      if (moved === 'up') p.row--; if (moved === 'down') p.row = Math.min(12, p.row + 1); if (moved === 'left') p.x -= HT; if (moved === 'right') p.x += HT;
      p.x = clamp(p.x, 0, W - HT); p.hop = 6; G.sfx('hop');
      if (p.row < s.best) { s.best = p.row; G.addScore(10); }
    }
    const lane = s.lanes.find(l => l.row === p.row);
    if (p.row === 0) {
      const slots = [1, 4, 7, 10, 13].map(c => c * HT - HT / 2 + 8 - 8);
      const i = slots.findIndex(x => Math.abs(p.x - x) < 10);
      if (i >= 0 && !s.homes[i]) { s.homes[i] = true; G.addScore(50 + Math.floor(s.time / 30) * 2); G.sfx('coin'); if (s.homes.every(Boolean)) { G.sfx('levelup'); G.addScore(1000); this.level(s); } else this.reset(s); }
      else this.die(s, G, 'hedge');
    } else if (lane && lane.kind === 'log') {
      const on = lane.items.find(it => p.x + 8 > it.x + 2 && p.x + 8 < it.x + it.w - 2);
      if (!on) return this.die(s, G, 'water');
      p.x += lane.speed; if (p.x < -6 || p.x > W - HT + 6) return this.die(s, G, 'water');
    } else if (lane && lane.kind === 'car') {
      if (lane.items.some(it => p.x + 12 > it.x + 1 && p.x + 4 < it.x + it.w - 1)) return this.die(s, G, 'car');
    }
  },
  draw(s, G, ctx) {
    ctx.fillStyle = '#0b2a6b'; ctx.fillRect(0, HOY + HT, W, HT * 5);
    ctx.fillStyle = '#123d8f'; for (let i = 0; i < 30; i++) ctx.fillRect((i * 37 + s.t / 2) % W, HOY + HT + (i * 13) % (HT * 5), 6, 1);
    ctx.fillStyle = '#1d5c2a'; ctx.fillRect(0, HOY, W, HT);
    [1, 4, 7, 10, 13].forEach((c, i) => { const x = c * HT - HT / 2; ctx.fillStyle = '#05030c'; ctx.fillRect(x - 1, HOY + 2, HT + 2, HT - 2); if (s.homes[i]) spr(ctx, BUNNY, x + 4, HOY + 5, { w: C.ink, p: C.pink, k: '#000' }); });
    ctx.fillStyle = '#3b2a6b'; ctx.fillRect(0, HOY + HT * 6, W, HT); ctx.fillRect(0, HOY + HT * 12, W, HT);
    ctx.fillStyle = '#16122a'; ctx.fillRect(0, HOY + HT * 7, W, HT * 5);
    ctx.fillStyle = C.gold; for (let r = 8; r < 12; r++) for (let x = 0; x < W; x += 16) ctx.fillRect(x + 4, HOY + r * HT - 1, 7, 1);
    for (const l of s.lanes) for (const it of l.items) {
      const y = HOY + l.row * HT;
      if (l.kind === 'log') { ctx.fillStyle = C.wood; ctx.fillRect(it.x, y + 3, it.w, HT - 6); ctx.fillStyle = '#b06a2c'; ctx.fillRect(it.x, y + 3, it.w, 2); ctx.fillStyle = '#5a3110'; for (let k = 8; k < it.w; k += 14) ctx.fillRect(it.x + k, y + 7, 4, 1); }
      else { const spriteSet = CAR[l.col]; const pal = l.col ? { y: C.gold, c: C.cyan, k: '#000' } : { r: C.red, c: C.cyan, k: '#000' }; for (let k = 0; k < it.w; k += HT) spr(ctx, spriteSet, it.x + k + 1, y + 5, pal, 1, l.speed < 0); }
    }
    if (!s.dead) { const lift = s.p.hop > 0 ? -2 : 0; spr(ctx, BUNNY, s.p.x + 4, HOY + s.p.row * HT + 4 + lift, { w: C.ink, p: C.pink, k: '#000' }); }
    drawFx(ctx, s.fx);
    const tw = Math.max(0, s.time / (60 * 30)) * 120; ctx.fillStyle = tw < 30 ? C.red : C.lime; ctx.fillRect(W - 126, H - 14, tw, 6); text(ctx, 'TIME', W - 162, H - 15, C.gold);
    G.hud(s.lives, 'LV ' + s.level, true);
  },
  thumb(ctx, t) { ctx.fillStyle = '#16122a'; ctx.fillRect(0, 0, 112, 84); ctx.fillStyle = '#0b2a6b'; ctx.fillRect(0, 0, 112, 34); ctx.fillStyle = C.wood; ctx.fillRect((t * 0.6) % 150 - 40, 6, 40, 8); ctx.fillRect(112 - (t * 0.8) % 150, 20, 34, 8); ctx.fillStyle = '#3b2a6b'; ctx.fillRect(0, 34, 112, 10); spr(ctx, CAR[0], (t * 1.1) % 140 - 20, 50, { r: C.red, c: C.cyan, k: '#000' }); spr(ctx, CAR[1], 120 - (t * 0.9) % 140, 66, { y: C.gold, c: C.cyan, k: '#000' }, 1, true); spr(ctx, BUNNY, 52, 36 - ((t >> 5) & 1) * 2, { w: '#fff', p: C.pink, k: '#000' }); }
};

/* =====================================================================
   GAME 6: SKY SHIELD (missile defense)
===================================================================== */
const CITY = ['..c...cc..', '.ccc..cc.c', '.ccc.cccc.', 'cccccccccc', 'cwcwcwcwcc'];
const skyShield = {
  id: 'shield', name: 'SKY SHIELD', year: '1980', blurb: 'Tap the sky to stop warheads before they hit your cities.', track: 'action',
  help: 'Tap to fire · or ✚ aim + A', keys: 'Click to fire · arrows aim + Space',
  init(G) { const s = { t: 0, wave: 0, cross: { x: W / 2, y: 140 }, cities: [16, 46, 76, 138, 168, 198].map(x => ({ x, alive: true })), lastBonus: 0 }; this.wave(s); return s; },
  wave(s) { s.wave++; s.incoming = []; s.outs = []; s.booms = []; s.ammo = 24 + s.wave * 2; s.toSpawn = 8 + s.wave * 3; s.spawnT = 60; s.pause = 90; s.bonusShown = 0; },
  targets(s) { return s.cities.filter(c => c.alive).map(c => c.x + 5).concat([W / 2]); },
  update(s, G) {
    s.t++;
    if (s.bonusShown) { if (--s.bonusShown === 0) { if (!s.cities.some(c => c.alive)) return G.over(); this.wave(s); } return; }
    if (s.pause > 0) { s.pause--; return; }
    const c = s.cross;
    if (G.held('left')) c.x -= 2.5; if (G.held('right')) c.x += 2.5; if (G.held('up')) c.y -= 2.5; if (G.held('down')) c.y += 2.5;
    if (G.ptr.over) { c.x = G.ptr.x; c.y = G.ptr.y; }
    c.x = clamp(c.x, 4, W - 4); c.y = clamp(c.y, 30, 248);
    const fireAt = G.tap ? { x: clamp(G.tap.x, 4, W - 4), y: clamp(G.tap.y, 30, 248) } : G.hit('a') ? { x: c.x, y: c.y } : null;
    if (fireAt && s.ammo > 0) { s.ammo--; s.outs.push({ x: W / 2, y: 262, sx: W / 2, sy: 262, tx: fireAt.x, ty: fireAt.y }); G.sfx('launch'); }
    else if (fireAt) G.sfx('tick');
    if (s.toSpawn > 0 && --s.spawnT <= 0) {
      s.spawnT = Math.max(18, 70 - s.wave * 6) + ri(0, 30); const n = Math.min(s.toSpawn, ri(1, 2 + (s.wave > 2)));
      for (let i = 0; i < n; i++) { const tg = this.targets(s); const tx = tg[ri(0, tg.length - 1)]; const sx = rnd(0, W); s.incoming.push({ sx, sy: 24, x: sx, y: 24, tx, ty: 266, v: 0.28 + s.wave * 0.06, split: s.wave > 1 && RNG() < 0.15 + s.wave * 0.03 }); s.toSpawn--; }
    }
    for (const o of s.outs) { const dx = o.tx - o.x, dy = o.ty - o.y, d = Math.hypot(dx, dy); if (d < 4) { o.done = true; s.booms.push({ x: o.tx, y: o.ty, r: 1, grow: true }); G.sfx('boom'); } else { o.x += dx / d * 4; o.y += dy / d * 4; } }
    s.outs = s.outs.filter(o => !o.done);
    for (const b of s.booms) { if (b.grow) { b.r += 0.7; if (b.r >= (b.small ? 10 : 20)) b.grow = false; } else b.r -= 0.35; }
    s.booms = s.booms.filter(b => b.r > 0);
    const born = [];
    for (const m of s.incoming) {
      const dx = m.tx - m.sx, dy = m.ty - m.sy, d = Math.hypot(dx, dy); m.x += dx / d * m.v; m.y += dy / d * m.v;
      if (m.split && m.y > 110) { m.dead = true; for (let i = 0; i < 2; i++) { const tg = this.targets(s); born.push({ sx: m.x, sy: m.y, x: m.x, y: m.y, tx: tg[ri(0, tg.length - 1)], ty: 266, v: m.v }); } continue; }
      if (s.booms.some(b => Math.hypot(b.x - m.x, b.y - m.y) < b.r)) { m.dead = true; G.addScore(25 * Math.min(s.wave, 6)); s.booms.push({ x: m.x, y: m.y, r: 1, grow: true, small: true }); G.sfx('pop'); continue; }
      if (m.y >= 264) { m.dead = true; s.booms.push({ x: m.x, y: 262, r: 1, grow: true }); G.sfx('boom'); const city = s.cities.find(c => c.alive && Math.abs(c.x + 5 - m.x) < 9); if (city) city.alive = false; else if (Math.abs(m.x - W / 2) < 10) s.ammo = 0; }
    }
    s.incoming = s.incoming.filter(m => !m.dead).concat(born);
    if (G.score - s.lastBonus >= 10000) { const dead = s.cities.find(c => !c.alive); if (dead) { dead.alive = true; G.sfx('levelup'); } s.lastBonus += 10000; }
    if (!s.toSpawn && !s.incoming.length && !s.outs.length && !s.booms.length) {
      const alive = s.cities.filter(c => c.alive).length;
      s.bonus = alive * 100 + s.ammo * 5; G.addScore(alive ? s.bonus : 0); s.bonusShown = 150; G.sfx(alive ? 'levelup' : 'over');
    }
  },
  draw(s, G, ctx) {
    const g = ctx.createLinearGradient(0, 24, 0, 270); g.addColorStop(0, '#05030c'); g.addColorStop(1, '#2a0f3f'); ctx.fillStyle = g; ctx.fillRect(0, 24, W, H);
    ctx.fillStyle = '#5a2a14'; ctx.fillRect(0, 268, W, 20); ctx.fillStyle = C.gold; for (let x = 0; x < W; x += 6) ctx.fillRect(x, 268, 3, 1);
    ctx.fillStyle = '#7a3a1c'; ctx.beginPath(); ctx.moveTo(W / 2 - 16, 270); ctx.lineTo(W / 2, 256); ctx.lineTo(W / 2 + 16, 270); ctx.fill();
    for (const c of s.cities) if (c.alive) spr(ctx, CITY, c.x, 263, { c: C.cyan, w: C.gold }); else { ctx.fillStyle = '#3a2030'; ctx.fillRect(c.x, 266, 10, 2); }
    ctx.lineWidth = 1;
    for (const m of s.incoming) { ctx.strokeStyle = 'rgba(255,84,68,.7)'; ctx.beginPath(); ctx.moveTo(m.sx, m.sy); ctx.lineTo(m.x, m.y); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.fillRect(m.x - 1, m.y - 1, 2, 2); }
    for (const o of s.outs) { ctx.strokeStyle = 'rgba(45,226,255,.8)'; ctx.beginPath(); ctx.moveTo(o.sx, o.sy); ctx.lineTo(o.x, o.y); ctx.stroke(); ctx.fillStyle = C.cyan; ctx.fillRect(o.tx - 1, o.ty - 1, 3, 3); }
    for (const b of s.booms) { ctx.fillStyle = [C.white, C.gold, C.pink, C.cyan][(s.t >> 1) % 4]; ctx.beginPath(); ctx.arc(b.x, b.y, b.r, 0, 6.29); ctx.fill(); }
    const c = s.cross; ctx.strokeStyle = C.lime; ctx.beginPath(); ctx.moveTo(c.x - 5, c.y); ctx.lineTo(c.x + 5, c.y); ctx.moveTo(c.x, c.y - 5); ctx.lineTo(c.x, c.y + 5); ctx.stroke();
    text(ctx, 'AMMO ' + s.ammo, 8, 276, s.ammo < 5 ? C.red : C.ink);
    G.hud(null, 'WAVE ' + s.wave);
    if (s.pause > 0) text(ctx, 'DEFEND THE CITIES', W / 2, 130, C.gold, 8, 'center');
    if (s.bonusShown) { text(ctx, 'WAVE ' + s.wave + ' CLEAR', W / 2, 110, C.lime, 8, 'center'); text(ctx, 'BONUS ' + (s.bonus || 0), W / 2, 130, C.gold, 8, 'center'); }
  },
  thumb(ctx, t) { ctx.fillStyle = '#12061f'; ctx.fillRect(0, 0, 112, 84); ctx.fillStyle = '#5a2a14'; ctx.fillRect(0, 76, 112, 8); [8, 28, 70, 90].forEach(x => spr(ctx, CITY, x, 71, { c: C.cyan, w: C.gold })); ctx.strokeStyle = 'rgba(255,84,68,.8)'; ctx.beginPath(); const k = (t % 120) / 120; ctx.moveTo(10, 0); ctx.lineTo(10 + 25 * k, 70 * k); ctx.moveTo(100, 0); ctx.lineTo(100 - 30 * k, 70 * k); ctx.stroke(); const r = ((t + 60) % 120) / 120 * 12; ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(70, 34, r, 0, 6.29); ctx.fill(); }
};

/* =====================================================================
   GAME 7 (bonus): NIBBLE (snake)
===================================================================== */
const NT = 8, NW = 28, NH = 30, NOY = 28;
const nibble = {
  id: 'nibble', name: 'NIBBLE', year: '1982', blurb: 'Eat sats, grow longer, never bite your tail.', track: 'bounce',
  help: '✚ or swipe to turn', keys: 'Arrow keys turn',
  init(G) { const s = { t: 0, body: [[10, 15], [9, 15], [8, 15], [7, 15]], dir: 'right', q: [], grow: 0, every: 8, k: 0, eaten: 0 }; this.food(s); return s; },
  food(s) { let x, y; do { x = ri(1, NW - 2); y = ri(1, NH - 2); } while (s.body.some(([a, b]) => a === x && b === y)); s.f = [x, y]; if (RNG() < 0.2) s.bonus = { x: ri(1, NW - 2), y: ri(1, NH - 2), life: 300 }; },
  update(s, G) {
    s.t++;
    for (const d of ['up', 'down', 'left', 'right']) if (G.hit(d) || G.swipe === d) { const last = s.q.length ? s.q[s.q.length - 1] : s.dir; if (d !== last && d !== OPP[last] && s.q.length < 3) s.q.push(d); }
    if (s.bonus && --s.bonus.life <= 0) s.bonus = null;
    if (++s.k < s.every) return; s.k = 0;
    if (s.q.length) s.dir = s.q.shift();
    const [dx, dy] = DIRS[s.dir]; const h = [s.body[0][0] + dx, s.body[0][1] + dy];
    if (h[0] < 0 || h[1] < 0 || h[0] >= NW || h[1] >= NH || s.body.some(([a, b], i) => i < s.body.length - 1 && a === h[0] && b === h[1])) { G.sfx('die'); return G.over(); }
    s.body.unshift(h);
    if (h[0] === s.f[0] && h[1] === s.f[1]) { s.grow += 3; s.eaten++; G.addScore(10 * Math.ceil(s.eaten / 5)); G.sfx('eat'); G.sfx('hit'); this.food(s); if (s.eaten % 5 === 0) { s.every = Math.max(3, s.every - 1); G.sfx('levelup'); } }
    else if (s.bonus && h[0] === s.bonus.x && h[1] === s.bonus.y) { G.addScore(100); s.bonus = null; G.sfx('gulp'); }
    if (s.grow > 0) s.grow--; else s.body.pop();
  },
  draw(s, G, ctx) {
    ctx.fillStyle = '#0e0a24'; ctx.fillRect(0, NOY, W, NH * NT); ctx.fillStyle = '#18123a'; for (let x = 0; x < NW; x++) for (let y = 0; y < NH; y++) if ((x + y) % 2) ctx.fillRect(x * NT, NOY + y * NT, NT, NT);
    ctx.strokeStyle = C.violet; ctx.strokeRect(0.5, NOY + 0.5, W - 1, NH * NT - 1);
    spr(ctx, ['.oo.', 'oyyo', 'oyyo', '.oo.'], s.f[0] * NT + 2, NOY + s.f[1] * NT + 2, { o: C.orange, y: C.gold }, 1);
    if (s.bonus && (s.bonus.life > 60 || (s.t >> 2) & 1)) spr(ctx, ['.33.', '2222', '1111', '.11.'], s.bonus.x * NT + 2, NOY + s.bonus.y * NT + 2, { 1: C.gold, 2: C.brown, 3: '#5a3110' });
    s.body.forEach(([x, y], i) => { ctx.fillStyle = i === 0 ? C.lime : i % 2 ? '#3ad65c' : '#2fb84d'; ctx.fillRect(x * NT + 1, NOY + y * NT + 1, NT - 2, NT - 2); });
    const [hx, hy] = s.body[0]; ctx.fillStyle = '#000'; ctx.fillRect(hx * NT + 2, NOY + hy * NT + 2, 1, 1); ctx.fillRect(hx * NT + 5, NOY + hy * NT + 2, 1, 1);
    text(ctx, 'LENGTH ' + s.body.length, 8, H - 14, C.dim);
    G.hud(null, 'SPEED ' + (9 - s.every));
  },
  thumb(ctx, t) { ctx.fillStyle = '#0e0a24'; ctx.fillRect(0, 0, 112, 84); const n = 14; for (let i = 0; i < n; i++) { const k = (t / 4 - i) ; const x = 56 + Math.cos(k / 5) * 34, y = 42 + Math.sin(k / 3.3) * 26; ctx.fillStyle = i ? '#2fb84d' : C.lime; ctx.fillRect(x | 0, y | 0, 6, 6); } spr(ctx, ['.oo.', 'oyyo', 'oyyo', '.oo.'], 80, 20, { o: C.orange, y: C.gold }, 2); }
};

const GAMES = [starSwarm, nutMaze, brickBlitz, voidRocks, hopLanes, skyShield, nibble];

/* =====================================================================
   ENGINE
===================================================================== */
const keys = {}, pressed = new Set();
let G = null, cur = null, st = null, mode = 'title', raf = 0, view = null, ctx = null, frame = 0;
let chal = null, runSeed = 0;   // chal: a challenge being played { id, seed, target, by, name }
const KEYMAP = { ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down', ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right', Space: 'a', KeyZ: 'a', KeyX: 'a', KeyJ: 'a', Enter: 'b', KeyP: 'b', Escape: 'esc' };
function press(k) { if (!keys[k]) pressed.add(k); keys[k] = true; }
function release(k) { keys[k] = false; }
window.addEventListener('keydown', e => { if (!view || e.target.tagName === 'INPUT') return; const k = KEYMAP[e.code]; if (!k) return; e.preventDefault(); if (k === 'esc') { closeGame(); return; } press(k); });
window.addEventListener('keyup', e => { const k = KEYMAP[e.code]; if (k) release(k); });
window.addEventListener('blur', () => { for (const k in keys) keys[k] = false; if (mode === 'play') mode = 'pause'; });
document.addEventListener('visibilitychange', () => { if (document.hidden && mode === 'play') mode = 'pause'; });

const ptr = { x: W / 2, y: H / 2, down: false, over: false, sx: 0, sy: 0, st: 0 };
let tap = null, swipe = null;

function makeG() {
  const g = {
    W, H, score: 0,
    held: k => !!keys[k], hit: k => pressed.has(k), ptr,
    get tap() { return tap; }, get swipe() { return swipe; },
    sfx: n => A().sfx(n),
    addScore(n) { this.score += n; },
    over() { endGame(); },
    hud(lives, label, bottomless) {
      ctx.fillStyle = '#05030c'; ctx.fillRect(0, 0, W, 22);
      text(ctx, '1UP', 8, 3, C.red); text(ctx, pad6(this.score), 8, 12, C.ink);
      if (chal) { text(ctx, 'TARGET', W / 2, 3, C.pink, 8, 'center'); text(ctx, pad6(chal.target), W / 2, 12, this.score > chal.target ? C.lime : C.ink, 8, 'center'); }
      else { text(ctx, 'HI-SCORE', W / 2, 3, C.red, 8, 'center'); text(ctx, pad6(Math.max(hiOf(cur.id), this.score)), W / 2, 12, C.ink, 8, 'center'); }
      if (label) text(ctx, label, W - 8, 12, C.gold, 8, 'right');
      if (lives != null) for (let i = 0; i < lives - 1 && i < 5; i++) spr(ctx, ['.c.', 'ccc', 'c.c'], 8 + i * 6, bottomless ? H - 14 : H - 8, { c: C.lime }, 1);
    }
  };
  return g;
}
function fit() {
  if (!view) return; const frameEl = view.querySelector('.screen-frame'); const c = view.querySelector('#gameCanvas');
  const r = frameEl.getBoundingClientRect(); const k = Math.max(1, Math.min((r.width - 6) / W, (r.height - 6) / H));
  const kk = k >= 2 ? Math.floor(k * 2) / 2 : k;
  c.style.width = Math.floor(W * kk) + 'px'; c.style.height = Math.floor(H * kk) + 'px';
}
function toLogical(e) { const c = view.querySelector('#gameCanvas'); const r = c.getBoundingClientRect(); return { x: (e.clientX - r.left) / r.width * W, y: (e.clientY - r.top) / r.height * H }; }

function openGame(id, opts) {
  cur = GAMES.find(g => g.id === id); if (!cur) return;
  closeGame(true);
  chal = opts && opts.challenge ? opts.challenge : null;
  view = document.createElement('div'); view.className = 'game-view'; view.setAttribute('role', 'dialog'); view.setAttribute('aria-label', cur.name);
  view.innerHTML = `<div class="game-top"><button class="btn sm red" data-g="exit">Exit</button><div class="ttl">${cur.name}</div><button class="btn sm" data-g="mute" aria-label="Toggle sound">${(window.NutPrefs || {}).sound === false ? 'SND OFF' : 'SND ON'}</button></div>
    <div class="screen-frame"><canvas id="gameCanvas" width="${W}" height="${H}" aria-label="${cur.name} game screen"></canvas></div>
    <div class="pad touch-only"><div class="dpad">${['u', 'l', 'c', 'r', 'd'].map(k => `<button class="${k}" ${k === 'c' ? 'tabindex="-1" aria-hidden="true"' : `data-k="${{ u: 'up', l: 'left', r: 'right', d: 'down' }[k]}" aria-label="${{ u: 'Up', l: 'Left', r: 'Right', d: 'Down' }[k]}"`}>${{ u: '▲', l: '◀', r: '▶', d: '▼', c: '' }[k]}</button>`).join('')}</div>
    <div class="hint">${cur.help}</div><div class="abtns"><button class="abtn b" data-k="b" aria-label="Pause">II</button><button class="abtn a" data-k="a" aria-label="A button">A</button></div></div>
    <div class="pad-keys">${cur.keys} · Enter pause · Esc exit</div><div id="entry"></div>`;
  document.body.appendChild(view);
  document.body.style.overflow = 'hidden';
  ctx = view.querySelector('#gameCanvas').getContext('2d'); ctx.imageSmoothingEnabled = false;
  view.querySelectorAll('[data-k]').forEach(b => {
    const k = b.dataset.k;
    const down = e => { e.preventDefault(); b.setPointerCapture && b.setPointerCapture(e.pointerId); b.classList.add('on'); press(k); if (navigator.vibrate) try { navigator.vibrate(8); } catch (x) {} };
    const up = e => { b.classList.remove('on'); release(k); };
    b.addEventListener('pointerdown', down); b.addEventListener('pointerup', up); b.addEventListener('pointercancel', up); b.addEventListener('lostpointercapture', up);
    b.addEventListener('contextmenu', e => e.preventDefault());
  });
  view.querySelector('[data-g="exit"]').onclick = () => closeGame();
  view.querySelector('[data-g="mute"]').onclick = e => { const p = window.NutPrefs || {}; p.sound = p.sound === false; store.set('prefs', p); e.currentTarget.textContent = p.sound ? 'SND ON' : 'SND OFF'; if (p.sound) A().music(mode === 'play' ? cur.track : 'title'); else A().stopMusic(); };
  const cv = view.querySelector('#gameCanvas');
  cv.addEventListener('pointerdown', e => { e.preventDefault(); cv.setPointerCapture(e.pointerId); const p = toLogical(e); Object.assign(ptr, p, { down: true, over: e.pointerType === 'mouse', sx: e.clientX, sy: e.clientY, st: performance.now() }); });
  cv.addEventListener('pointermove', e => { const p = toLogical(e); ptr.x = p.x; ptr.y = p.y; if (e.pointerType === 'mouse') ptr.over = true; });
  cv.addEventListener('pointerleave', () => { ptr.over = false; });
  const upH = e => {
    if (!ptr.down) return; ptr.down = false; const dx = e.clientX - ptr.sx, dy = e.clientY - ptr.sy, d = Math.hypot(dx, dy);
    if (d > 22) swipe = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
    else if (performance.now() - ptr.st < 400) tap = toLogical(e);
  };
  cv.addEventListener('pointerup', upH); cv.addEventListener('pointercancel', () => { ptr.down = false; });
  window.addEventListener('resize', fit); fit(); setTimeout(fit, 50);
  G = makeG(); mode = 'title'; frame = 0; st = null;
  A().music('title');
  if (window.Nutcade) window.Nutcade.closeSheet();
  loop();
}
function closeGame(silent) {
  cancelAnimationFrame(raf); raf = 0; RNG = Math.random;
  if (view) { view.remove(); view = null; window.removeEventListener('resize', fit); document.body.style.overflow = ''; }
  for (const k in keys) keys[k] = false;
  if (!silent) { mode = 'title'; A().music('title'); if (window.Nutcade) window.Nutcade.refresh(); }
}
function startGame() { runSeed = chal ? chal.seed >>> 0 : (Math.random() * 4294967296) >>> 0; RNG = seeded(runSeed); G = makeG(); st = cur.init(G); mode = 'play'; A().sfx('start'); A().music(cur.track); if (window.Trophies) window.Trophies.played(cur.id); }
function endGame() {
  mode = 'over'; A().stopMusic(); A().sfx('over');
  const score = G.score;
  if (window.Trophies) try { window.Trophies.gameOver(cur.id, score, st, qualifies(cur.id, score)); } catch (e) {}
  const seed = runSeed;
  setTimeout(() => {
    if (!view) return;
    if (chal) showChallengeResult(score);
    else if (qualifies(cur.id, score)) showEntry(score, seed);
    else if (score > 0 && canChallenge()) showOver(score, seed);
    else { mode = 'title'; A().music('title'); }
  }, 1800);
}
const N = () => window.Nutcade;
const canChallenge = () => !!(N() && N().canChallenge && N().canChallenge());
const box6 = inner => `<div class="scrim" style="align-items:center"><div class="sheet initials" style="border-radius:8px;border-bottom:3px solid var(--cyan);max-width:340px">${inner}</div></div>`;
function challengeFromHere(g, seed, score, initials) { closeGame(); if (N()) N().startChallenge({ game: g.id, seed, score, by: initials || store.get('initials', 'AAA') }); }
function showOver(score, seed) {
  mode = 'entry';
  const box = view.querySelector('#entry'); const g = cur;
  box.innerHTML = box6(`<div style="font-family:var(--f-display);font-size:12px;color:var(--red)">GAME OVER</div>
    <div style="font-family:var(--f-display);font-size:18px">${pad6(score)}</div>
    <button class="btn solid gold block" data-g="chal">Challenge a friend</button><button class="btn block" data-g="again">Continue</button>`);
  box.querySelector('[data-g=again]').onclick = () => { box.innerHTML = ''; mode = 'title'; A().music('title'); };
  box.querySelector('[data-g=chal]').onclick = () => challengeFromHere(g, seed, score);
}
function showChallengeResult(score) {
  mode = 'entry';
  const box = view.querySelector('#entry'); const c = chal, g = cur;
  const initials = store.get('initials', 'AAA');
  if (qualifies(cur.id, score)) addScore(cur.id, initials, score);
  const res = N() ? N().challengeDone(c.id, score, initials) : null;
  const won = score > c.target;
  A().sfx(won ? 'levelup' : 'over');
  box.innerHTML = box6(`<div style="font-family:var(--f-display);font-size:14px;color:${won ? 'var(--lime)' : 'var(--pink)'}">${won ? 'YOU WIN!' : 'SO CLOSE!'}</div>
    <div class="scores" style="font-size:10px"><div><span>YOU</span><span data-noi18n>${esc6(initials)}</span><span>${pad6(score)}</span></div><div><span>THEM</span><span data-noi18n>${esc6(c.by)}</span><span>${pad6(c.target)}</span></div></div>
    ${res && res.canReply ? `<button class="btn solid gold block" data-g="reply">Send my score to ${esc6(res.name)}</button>` : ''}
    <button class="btn block ${res && res.canReply ? '' : 'solid gold'}" data-g="rematch">Rematch</button><button class="btn block" data-g="exit2">Exit</button>`);
  const rb = box.querySelector('[data-g=reply]');
  if (rb) rb.onclick = () => { rb.disabled = true; rb.textContent = 'SENDING…'; N().sendResult(c.id, score, initials).then(ok => { rb.textContent = ok ? 'SCORE SENT' : "COULDN'T SEND"; A().sfx(ok ? 'coin' : 'err'); }); };
  box.querySelector('[data-g=rematch]').onclick = () => { box.innerHTML = ''; mode = 'title'; A().music('title'); };
  box.querySelector('[data-g=exit2]').onclick = () => closeGame();
}
const esc6 = s => String(s || '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
function showEntry(score, seed) {
  mode = 'entry';
  const box = view.querySelector('#entry');
  const last = store.get('initials', 'AAA');
  box.innerHTML = `<div class="scrim" style="align-items:center"><form class="sheet initials" style="border-radius:8px;border-bottom:3px solid var(--cyan);max-width:340px">
    <div style="font-family:var(--f-display);font-size:12px;color:var(--gold)">NEW HIGH SCORE</div>
    <div style="font-family:var(--f-display);font-size:18px">${pad6(score)}</div>
    <label for="ini" class="label">Enter your initials</label>
    <input id="ini" class="inp" maxlength="3" value="${last}" autocomplete="off" autocapitalize="characters" spellcheck="false">
    <button class="btn solid gold block" type="submit">Save score</button></form></div>`;
  const inp = box.querySelector('#ini'); inp.focus(); inp.select();
  inp.addEventListener('input', () => { inp.value = inp.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); });
  box.querySelector('form').addEventListener('submit', e => { e.preventDefault(); const n = (inp.value || 'AAA').padEnd(3, 'A'); store.set('initials', n); addScore(cur.id, n, score); A().sfx('coin');
    box.innerHTML = `<div class="scrim" style="align-items:center"><div class="sheet initials" style="border-radius:8px;border-bottom:3px solid var(--cyan);max-width:340px">
      <div style="font-family:var(--f-display);font-size:12px;color:var(--lime)">SCORE SAVED</div>
      <div style="font-family:var(--f-display);font-size:18px">${pad6(score)} ${n}</div>
      <button class="btn solid gold block" data-g="card">Share score card</button>${canChallenge() ? '<button class="btn block violet" data-g="chal">Challenge a friend</button>' : ''}<button class="btn block" data-g="again">Continue</button></div></div>`;
    const g = cur;
    const cb = box.querySelector('[data-g=chal]'); if (cb) cb.onclick = () => challengeFromHere(g, seed, score, n);
    box.querySelector('[data-g=again]').onclick = () => { box.innerHTML = ''; mode = 'title'; A().music('title'); };
    box.querySelector('[data-g=card]').onclick = () => { closeGame(); if (window.Trophies) window.Trophies.openCard({ kind: 'score', game: g, score, initials: n, at: Date.now() }); };
  });
}
function drawTitle() {
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  if (!drawTitle.stars) drawTitle.stars = starfield(50); drawStars(ctx, drawTitle.stars, 0.4);
  if (!drawTitle.tc) { const c = document.createElement('canvas'); c.width = 112; c.height = 84; drawTitle.tc = c.getContext('2d'); }
  const tc = drawTitle.tc, thumb = tc.canvas; cur.thumb(tc, frame);
  ctx.drawImage(thumb, 56, 34); ctx.strokeStyle = C.violet; ctx.strokeRect(55.5, 33.5, 113, 85);
  text(ctx, cur.name, W / 2, 128, C.gold, 12, 'center');
  if (chal) { text(ctx, 'CHALLENGE FROM ' + String(chal.name || chal.by).toUpperCase().slice(0, 12), W / 2, 144, C.pink, 8, 'center'); text(ctx, 'BEAT ' + pad6(chal.target), W / 2, 154, C.ink, 8, 'center'); }
  else text(ctx, '© NUTCADE ' + cur.year, W / 2, 146, C.dim, 8, 'center');
  text(ctx, 'HIGH SCORES', W / 2, 166, C.cyan, 8, 'center');
  const sc = scoresOf(cur.id);
  for (let i = 0; i < 5; i++) { const r = sc[i]; const y = 182 + i * 12; text(ctx, `${i + 1}.`, 52, y, C.dim); text(ctx, r ? r.n : '---', 76, y, i === 0 ? C.gold : C.ink); text(ctx, r ? pad6(r.s) : '000000', 172, y, i === 0 ? C.gold : C.ink, 8, 'right'); }
  if ((frame >> 5) & 1) text(ctx, 'PRESS A OR TAP', W / 2, 252, C.pink, 8, 'center');
  text(ctx, 'CREDIT 99', W / 2, 270, C.dim, 8, 'center');
}
function loop() {
  raf = requestAnimationFrame(loop);
  if (!view) return;
  frame++;
  if (mode === 'title') {
    drawTitle();
    if (pressed.has('a') || pressed.has('b') || tap) startGame();
  } else if (mode === 'play') {
    if (pressed.has('b')) { mode = 'pause'; A().sfx('blip'); }
    else { cur.update(st, G); if (frame % 30 === 0 && window.Trophies && st) try { window.Trophies.progress(cur.id, st, G.score); } catch (e) {} if (mode !== 'over' || st) { ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H); cur.draw(st, G, ctx); } }
  } else if (mode === 'pause') {
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H); cur.draw(st, G, ctx);
    ctx.fillStyle = 'rgba(5,3,12,.7)'; ctx.fillRect(0, 22, W, H - 22);
    text(ctx, 'PAUSED', W / 2, 130, C.gold, 12, 'center'); text(ctx, 'A OR TAP TO RESUME', W / 2, 152, C.ink, 8, 'center');
    if (pressed.has('a') || pressed.has('b') || tap) { mode = 'play'; A().sfx('blip'); }
  } else if (mode === 'over' || mode === 'entry') {
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H); cur.draw(st, G, ctx);
    ctx.fillStyle = 'rgba(5,3,12,.6)'; ctx.fillRect(0, 22, W, H - 22);
    text(ctx, 'GAME OVER', W / 2, 130, C.red, 12, 'center');
  }
  pressed.clear(); tap = null; swipe = null;
}

/* ---------- arcade lobby ---------- */
let lobbyRaf = 0;
function mountList(el) {
  cancelAnimationFrame(lobbyRaf);
  el.innerHTML = `<div class="row between"><h2 class="h2">Arcade · ${GAMES.length} cabinets</h2><span class="tiny muted">Free play</span></div>
    <div class="cabinets">${GAMES.map(g => `<button class="cab" data-game="${g.id}" aria-label="Play ${g.name}"><canvas width="112" height="84" data-thumb="${g.id}"></canvas>
      <span class="nm">${g.name}</span><span class="ds">${g.blurb}</span><span class="hs">HI ${hiOf(g.id) ? pad6(hiOf(g.id)) + ' ' + scoresOf(g.id)[0].n : '------'}</span></button>`).join('')}</div>
    <div class="panel"><span class="h2">Hall of fame</span><div class="scores">${GAMES.map(g => { const s = scoresOf(g.id)[0]; return `<div><span style="color:var(--dim)">${g.name.split(' ')[0]}</span><span>${s ? s.n : '---'}</span><span>${s ? pad6(s.s) : '------'}</span>${s ? `<button class="sharebtn" data-card="${g.id}" aria-label="Share ${g.name} score card"><svg viewBox="0 0 8 8" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M5 0h3v3H7V2L4 5 3 4l3-3H5zM0 2h4v1H1v4h4V4h1v4H0z"/></svg></button>` : '<span></span>'}</div>`; }).join('')}</div></div>`;
  el.querySelectorAll('[data-game]').forEach(b => b.onclick = () => { A().sfx('select'); openGame(b.dataset.game); });
  el.querySelectorAll('[data-card]').forEach(b => b.onclick = () => { const g = GAMES.find(x => x.id === b.dataset.card); const s = scoresOf(g.id)[0]; A().sfx('select'); if (window.Trophies && s) window.Trophies.openCard({ kind: 'score', game: g, score: s.s, initials: s.n, at: s.t }); });
  const thumbs = [...el.querySelectorAll('[data-thumb]')].map(c => ({ c, x: c.getContext('2d'), g: GAMES.find(g => g.id === c.dataset.thumb) }));
  thumbs.forEach(t => t.x.imageSmoothingEnabled = false);
  let t = 0; const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const tick = () => { if (!el.isConnected) return; t++; if (!view) thumbs.forEach(o => o.g.thumb(o.x, t)); if (!reduce) lobbyRaf = requestAnimationFrame(tick); };
  tick();
}
function topLine() {
  const best = GAMES.map(g => ({ g, s: scoresOf(g.id)[0] })).filter(x => x.s).sort((a, b) => b.s.s - a.s.s)[0];
  return best ? `Top score: <span style="color:var(--gold)">${pad6(best.s.s)}</span> by ${best.s.n} on ${best.g.name}` : `${GAMES.length} cabinets of free play: shooters, mazes, bricks and more.`;
}
// layout(id, seed): the starting state a seed gives, so tests can check that a challenge replays the same layout
function layout(id, seed) { const g = GAMES.find(x => x.id === id); if (!g || view) return null; const keep = RNG; RNG = seeded(seed); const c0 = ctx; try { return JSON.stringify(g.init(makeG())); } finally { RNG = keep; ctx = c0; } }
window.Arcade = { mountList, open: openGame, topLine, playing: () => !!view, games: GAMES, layout, challenge: () => chal };
if (window.Nutcade) window.Nutcade.render();
})();
