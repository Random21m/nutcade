/* =====================================================================
   GAME 9: CORNER POCKET (top-down 8-ball pool, 1 or 2 players)
   A cabinet file (see src/README.md): it registers a factory in window.NutCabinets and games.js calls it with the shared kit (C, T, text, rnd, clamp, boom...).
   The simulation (everything update() does) uses only + - * / and sqrt plus the deterministic Math above, and takes
   its randomness from RNG, so a replay plays out the same on every phone. Aim is a unit vector, never an angle
   (atan2 may round differently between browsers); draw-only code may use anything.
===================================================================== */
(window.NutCabinets = window.NutCabinets || []).push(function (K) {
'use strict';
const { W, H, C, Math, A, T, text, rnd, ri, clamp, boom, tickFx, drawFx, RNG, withSeed } = K;
const cornerPocket = (() => {
  const R = 4, DD = 8, DD2 = 64, NB = 16, ST = 5;                 // ball radius, diameter, balls (0 = cue), sub-steps a frame
  const CL = 30, CR = 194, CT = 52, CB = 254, CX = 112, CY = 153;   // the cloth
  const FOOTY = 109, HEADY = 203;                                  // rack apex line, head string
  const PX = [CL - 1, CR + 1, CL - 2, CR + 2, CL - 1, CR + 1], PY = [CT - 1, CT - 1, CY, CY, CB + 1, CB + 1], PR2 = 81;
  const FR_A = 0.028, FR_D = 0.0009, E_W = 0.74, E_B = 0.96, VMIN = 0.035;   // rolling friction, cushion and ball bounce
  const vOf = p => 0.8 + 11.2 * p * p;                             // power 0..1 to launch speed (px a frame)
  const ERR = [0.075, 0.035, 0.012], PERR = [0.24, 0.12, 0.05], RAND_PICK = [0.45, 0.2, 0];   // the machine's aim, power and shot-choice slips by level
  const LVK = ['easy', 'medium', 'hard'];
  const BCOL = [C.white, C.gold, C.blue, C.red, C.violet, C.orange, C.lime, C.brown, '#14101f'];
  const grpOf = n => n < 8 ? 0 : 1;                                // 1-7 solids (0), 9-15 stripes (1)
  // every string drawn on the canvas, with its pixel size, so the tests can check each language fits
  const TX = {
    title: ['CORNER POCKET', 12], vs: ['VS MACHINE', 8], two: ['2 PLAYERS', 8], how: ['HOW TO PLAY', 8], level: ['LEVEL', 8],
    easy: ['EASY', 8], medium: ['MEDIUM', 8], hard: ['HARD', 8], pick: ['UP/DOWN, THEN SPACE', 8], pickT: ['TAP AN OPTION', 8],
    pts: ['VS MACHINE SCORES POINTS', 8], p2: ['2P', 8], you: ['YOU', 8], cpu: ['CPU', 8], p1n: ['P1', 8], p2n: ['P2', 8], open: ['OPEN TABLE', 8],
    yourShot: ['YOUR SHOT', 8], machShot: ['MACHINE SHOT', 8], p1Shot: ['P1 SHOT', 8], p2Shot: ['P2 SHOT', 8], brk: ['BREAK SHOT', 8],
    scratch: ['SCRATCH!', 8], hand: ['BALL IN HAND', 8], placeLine: ['PLACE BEHIND THE LINE', 8], placeAny: ['PLACE THE CUE BALL', 8],
    groups: ['GROUPS ARE SET', 8], on8: ['SHOOT THE 8 BALL!', 8], power: ['POWER', 8],
    youWin: ['YOU WIN!', 12], youLose: ['YOU LOSE', 12], p1Wins: ['P1 WINS!', 12], p2Wins: ['P2 WINS!', 12],
    w8: ['8 BALL POTTED', 8], w8e: ['8 BALL POTTED TOO EARLY', 8], w8s: ['SCRATCH ON THE 8 BALL', 8],
    next: ['SPACE: NEXT', 8], nextT: ['TAP: NEXT', 8], back: ['SPACE: BACK', 8], backT: ['TAP: BACK', 8],
    r1: ['THE FIRST BALL POTTED AFTER THE BREAK PICKS YOUR GROUP: SOLIDS OR STRIPES.', 8],
    r2: ['POT ALL OF YOUR GROUP, THEN THE 8 BALL TO WIN.', 8],
    r3: ['POT ONE OF YOURS AND YOU SHOOT AGAIN.', 8],
    r4: ['SCRATCH (CUE BALL POTTED): YOUR OPPONENT GETS THE BALL IN HAND BEHIND THE HEAD LINE.', 8],
    r5: ['POT THE 8 TOO EARLY, OR SCRATCH ON THE 8, AND YOU LOSE.', 8],
    r6: ['DRAG BACK FROM THE CUE BALL TO AIM. THE FURTHER YOU DRAG, THE HARDER THE SHOT. LET GO TO SHOOT.', 8],
    r7: ['KEYS: ARROWS AIM. HOLD SPACE FOR POWER, RELEASE TO SHOOT.', 8],
    r8: ['VS MACHINE: POINTS FOR EVERY BALL YOU POT, A BONUS FOR WINNING, AND MORE FOR WINNING FAST.', 8]
  };
  const t = k => T(TX[k][0]);
  const wrapCache = new Map();
  function wrap(str, n) {            // greedy word wrap of an already translated string
    let l = wrapCache.get(str); if (l) return l;
    l = []; let line = '';
    for (const w of str.split(' ')) { if (line && (line + ' ' + w).length > n) { l.push(line); line = w; } else line = line ? line + ' ' + w : w; }
    if (line) l.push(line); wrapCache.set(str, l); return l;
  }

  /* ---------- table state ---------- */
  function newState() {
    const s = {
      ph: 'menu', t: 0, mode: 0, lvSel: 1, sel: 0, page: 0, ai: [false, true], lv: [1, 1],
      x: new Float64Array(NB), y: new Float64Array(NB), vx: new Float64Array(NB), vy: new Float64Array(NB),
      st: new Uint8Array(NB), dk: new Uint8Array(NB), dp: new Uint8Array(NB), pl: new Uint8Array(NB), np: 0,
      ax: 0, ay: -1, pw: 0, pdir: 1, hold: 0, arm: false, pd: false, parm: false, pm: false, chg: false, anx: 0, any: 0,
      turn: 0, grp: [-1, -1], brk: true, hand: 0, on8: false, shots: [0, 0], sk: 0, rollT: 0,
      aiT: 0, tdx: 0, tdy: -1, tpw: 0.5, hx: CX, hy: HEADY, msg: '', msgT: 0, msgC: C.gold, sfxT: 0,
      winner: -1, reason: '', endT: 0, done: false, fx: [], won: false, lastPot: 0
    };
    rack(s); return s;
  }
  function rack(s) {
    s.x[0] = CX; s.y[0] = HEADY;
    const shuf = a => { for (let i = a.length - 1; i > 0; i--) { const j = ri(0, i), q = a[i]; a[i] = a[j]; a[j] = q; } return a; };
    const so = shuf([1, 2, 3, 4, 5, 6, 7]), st = shuf([9, 10, 11, 12, 13, 14, 15]);
    const ca = ri(0, 1) ? so.pop() : st.pop(), cb = grpOf(ca) === 0 ? st.pop() : so.pop();   // the back corners: one solid, one stripe
    const rest = shuf(so.concat(st)), sp = DD + 0.15, rh = DD * 0.866 + 0.15; let oi = 0;
    for (let r = 0; r < 5; r++) for (let c = 0; c <= r; c++) {
      const n = r === 4 && c === 0 ? ca : r === 4 && c === 4 ? cb : r === 2 && c === 1 ? 8 : rest[oi++];
      s.x[n] = CX + (c - r / 2) * sp; s.y[n] = FOOTY - r * rh;
    }
    for (let n = 0; n < NB; n++) { s.vx[n] = s.vy[n] = 0; s.st[n] = 0; }
  }
  const left = (s, g) => { let n = 0; for (let i = 1; i < NB; i++) if (i !== 8 && grpOf(i) === g && s.st[i] !== 2) n++; return n; };
  const say = (s, k, frames, col) => { s.msg = k; s.msgT = frames; s.msgC = col || C.gold; };
  const turnMsg = s => s.brk && s.shots[0] + s.shots[1] === 0 ? 'brk' : s.mode === 1 ? (s.turn ? 'p2Shot' : 'p1Shot') : (s.ai[s.turn] ? 'machShot' : 'yourShot');
  function startMatch(s, mode, level) {
    s.mode = mode; s.ai = mode === 0 ? [false, true] : [false, false]; s.lv = [level, level]; s.lvSel = level;
    s.ph = 'aim'; s.turn = 0; s.brk = true; s.arm = false; s.parm = false; s.pd = false; s.ax = 0; s.ay = -1; s.pw = 0; s.pdir = 1; s.aiT = 0;
    say(s, 'brk', 120, C.cyan); if (s.ai[0]) aiThink(s);
  }

  /* ---------- the machine's brain ---------- */
  const segBlocked = (s, x0, y0, x1, y1, skip) => {
    const dx = x1 - x0, dy = y1 - y0, l2 = dx * dx + dy * dy; if (l2 < 1e-6) return false;
    for (let o = 1; o < NB; o++) {
      if (o === skip || s.st[o] !== 0) continue;
      let u = ((s.x[o] - x0) * dx + (s.y[o] - y0) * dy) / l2; u = u < 0 ? 0 : u > 1 ? 1 : u;
      const ex = x0 + dx * u - s.x[o], ey = y0 + dy * u - s.y[o];
      if (ex * ex + ey * ey < (DD - 0.8) * (DD - 0.8)) return true;
    }
    return false;
  };
  const PLAN = { dx: 0, dy: -1, pw: 0.5, q: -1 };
  // the best easy pot from (cx, cy): ghost ball behind the target, clear lines, gentle cut. Fills PLAN.
  function plan(s, cx, cy, lvl) {
    const g = s.grp[s.turn], on8 = g >= 0 && left(s, g) === 0;
    let bq = -1, bdx = 0, bdy = -1, bpw = 0.5, nfeas = 0, rdx = 0, rdy = -1, rpw = 0.5, rq = -1;
    for (let b = 1; b < NB; b++) {
      if (s.st[b] !== 0) continue;
      if (on8 ? b !== 8 : (b === 8 || (g >= 0 && grpOf(b) !== g))) continue;
      for (let p = 0; p < 6; p++) {
        const tx = s.x[b], ty = s.y[b]; let ux = PX[p] - tx, uy = PY[p] - ty; const d2 = Math.hypot(ux, uy); ux /= d2; uy /= d2;
        const gx = tx - ux * DD, gy = ty - uy * DD;
        if (gx < CL + R - 1 || gx > CR - R + 1 || gy < CT + R - 1 || gy > CB - R + 1) continue;
        const ex = gx - cx, ey = gy - cy, d1 = Math.hypot(ex, ey); if (d1 < 2) continue;
        const cs = (ex * ux + ey * uy) / d1; if (cs < 0.3) continue;
        if (segBlocked(s, cx, cy, gx, gy, b) || segBlocked(s, tx, ty, PX[p], PY[p], b)) continue;
        const q = cs / (1 + (d1 + d2) / 220);
        const vo = Math.sqrt(2 * FR_A * d2 * 1.25) + 0.8, vc = vo / (0.98 * cs), v0 = Math.sqrt(vc * vc + 2 * FR_A * d1 * 1.25);
        let pw = Math.sqrt(Math.max(0, (v0 - 0.8) / 11.2)); pw = pw < 0.14 ? 0.14 : pw > 1 ? 1 : pw;
        nfeas++;
        if (q > bq) { bq = q; bdx = ex / d1; bdy = ey / d1; bpw = pw; }
        if (RNG() < 1 / nfeas) { rq = q; rdx = ex / d1; rdy = ey / d1; rpw = pw; }   // a random feasible shot, for the easy levels
      }
    }
    if (bq >= 0 && lvl >= 0 && RNG() < RAND_PICK[lvl]) { PLAN.dx = rdx; PLAN.dy = rdy; PLAN.pw = rpw; PLAN.q = rq; return PLAN; }
    if (bq < 0) {   // nothing clean: tap the nearest ball of mine
      let bd = 1e9;
      for (let b = 1; b < NB; b++) {
        if (s.st[b] !== 0) continue;
        if (on8 ? b !== 8 : (b === 8 || (g >= 0 && grpOf(b) !== g))) continue;
        const ex = s.x[b] - cx, ey = s.y[b] - cy, d = Math.hypot(ex, ey);
        if (d > 1 && d < bd) { bd = d; bdx = ex / d; bdy = ey / d; }
      }
      bpw = 0.42; bq = bd < 1e9 ? 0.01 : -1;
    }
    PLAN.dx = bdx; PLAN.dy = bdy; PLAN.pw = bpw; PLAN.q = bq; return PLAN;
  }
  function aiThink(s) {   // choose the shot now; update() then turns the cue toward it and charges the power
    const lv = s.lv[s.turn]; let dx, dy, pw;
    if (s.brk && s.shots[0] + s.shots[1] === 0) { dx = 0; dy = -1; pw = 0.93; }
    else { const p = plan(s, s.x[0], s.y[0], lv); dx = p.dx; dy = p.dy; pw = p.pw; }
    const e = (RNG() + RNG() - 1) * ERR[lv], c = Math.cos(e), sn = Math.sin(e);
    s.tdx = dx * c - dy * sn; s.tdy = dx * sn + dy * c;
    s.tpw = clamp(pw * (1 + (RNG() - 0.5) * PERR[lv]), 0.1, 1);
    s.aiT = 0; s.pw = 0;
  }
  function aiPlace(s) {   // the best spot to put the cue ball: the candidate with the best shot
    let bq = -2, bx = CX, by = s.hand === 1 ? HEADY + 12 : CY;
    const y0 = s.hand === 1 ? HEADY + 2 : CT + 20, y1 = CB - R - 2;
    for (let iy = 0; iy < 4; iy++) for (let ix = 0; ix < 7; ix++) {
      const x = CL + 14 + ix * ((CR - CL - 28) / 6), y = y0 + iy * ((y1 - y0) / 3);
      if (!freeSpot(s, x, y)) continue;
      const p = plan(s, x, y, -1); if (p.q > bq) { bq = p.q; bx = x; by = y; }
    }
    s.x[0] = bx; s.y[0] = by;
  }
  function freeSpot(s, x, y) {
    if (x < CL + R || x > CR - R || y > CB - R || y < (s.hand === 1 ? HEADY : CT + R)) return false;
    for (let i = 1; i < NB; i++) if (s.st[i] === 0) { const dx = s.x[i] - x, dy = s.y[i] - y; if (dx * dx + dy * dy < (DD + 0.6) * (DD + 0.6)) return false; }
    for (let p = 0; p < 6; p++) { const dx = PX[p] - x, dy = PY[p] - y; if (dx * dx + dy * dy < 14 * 14) return false; }
    return true;
  }

  /* ---------- physics ---------- */
  function sink(s, i, p, G) {
    s.st[i] = 1; s.dk[i] = 0; s.dp[i] = p; s.vx[i] = s.vy[i] = 0; s.pl[s.np++] = i;
    boom(s.fx, PX[p], PY[p], i === 0 ? C.white : i === 8 ? C.dim : BCOL[i < 8 ? i : i - 8], 8);
    G.sfx(i === 0 ? 'splash' : 'pop');
  }
  function physics(s, G) {   // one frame: ST sub-steps of motion and collisions, then rolling friction. Returns whether anything still moves
    const x = s.x, y = s.y, vx = s.vx, vy = s.vy, st = s.st;
    for (let k = 0; k < ST; k++) {
      for (let i = 0; i < NB; i++) {
        if (st[i] !== 0) continue;
        x[i] += vx[i] / ST; y[i] += vy[i] / ST;
        for (let p = 0; p < 6; p++) { const dx = x[i] - PX[p], dy = y[i] - PY[p]; if (dx * dx + dy * dy < PR2) { sink(s, i, p, G); break; } }
        if (st[i] !== 0) continue;
        if (x[i] < CL + R) { x[i] = CL + R; if (vx[i] < 0) { if (vx[i] < -1.4) wallSnd(s, G); vx[i] = -vx[i] * E_W; vy[i] *= 0.985; } }
        else if (x[i] > CR - R) { x[i] = CR - R; if (vx[i] > 0) { if (vx[i] > 1.4) wallSnd(s, G); vx[i] = -vx[i] * E_W; vy[i] *= 0.985; } }
        if (y[i] < CT + R) { y[i] = CT + R; if (vy[i] < 0) { if (vy[i] < -1.4) wallSnd(s, G); vy[i] = -vy[i] * E_W; vx[i] *= 0.985; } }
        else if (y[i] > CB - R) { y[i] = CB - R; if (vy[i] > 0) { if (vy[i] > 1.4) wallSnd(s, G); vy[i] = -vy[i] * E_W; vx[i] *= 0.985; } }
      }
      for (let i = 0; i < NB - 1; i++) {
        if (st[i] !== 0) continue;
        for (let j = i + 1; j < NB; j++) {
          if (st[j] !== 0) continue;
          const dx = x[j] - x[i], dy = y[j] - y[i], d2 = dx * dx + dy * dy;
          if (d2 >= DD2 || d2 < 1e-9) continue;
          const d = Math.sqrt(d2), nx = dx / d, ny = dy / d, ov = (DD - d) * 0.5;
          x[i] -= nx * ov; y[i] -= ny * ov; x[j] += nx * ov; y[j] += ny * ov;
          const rvn = (vx[j] - vx[i]) * nx + (vy[j] - vy[i]) * ny;
          if (rvn < 0) {
            const J = -(1 + E_B) * rvn * 0.5;
            vx[i] -= J * nx; vy[i] -= J * ny; vx[j] += J * nx; vy[j] += J * ny;
            if (rvn < -0.7 && s.sfxT <= 0) { G.sfx('hit'); s.sfxT = 3; }
          }
        }
      }
    }
    let moving = false;
    for (let i = 0; i < NB; i++) {
      if (st[i] === 1) { moving = true; continue; }
      if (st[i] !== 0) continue;
      const sp = Math.hypot(vx[i], vy[i]); if (sp === 0) continue;
      const ns = sp * (1 - FR_D) - FR_A;
      if (ns < VMIN) { vx[i] = 0; vy[i] = 0; } else { const f = ns / sp; vx[i] *= f; vy[i] *= f; moving = true; }
    }
    return moving;
  }
  const wallSnd = (s, G) => { if (s.sfxT <= 0) { G.sfx('wall'); s.sfxT = 3; } };

  /* ---------- rules ---------- */
  function launch(s, G) {
    const v = vOf(s.pw);
    s.vx[0] = s.ax * v; s.vy[0] = s.ay * v; s.np = 0; s.rollT = 0; s.on8 = s.grp[s.turn] >= 0 && left(s, s.grp[s.turn]) === 0;
    s.shots[s.turn]++; s.ph = 'roll'; s.pw = 0; G.sfx('launch');
  }
  function finishShot(s, G) {
    const me = s.turn, opp = 1 - me; let scratch = false, p8 = false, first = -1;
    for (let i = 0; i < s.np; i++) { const n = s.pl[i]; if (n === 0) scratch = true; else if (n === 8) p8 = true; else if (first < 0) first = n; }
    const wasBreak = s.brk && s.shots[0] + s.shots[1] === 1; s.brk = false;
    // the 8 on the break goes back on its spot
    if (p8 && wasBreak) { s.st[8] = 0; s.x[8] = CX; s.y[8] = FOOTY - 2 * (DD * 0.866 + 0.15); s.vx[8] = s.vy[8] = 0; p8 = false; for (let n = 1; n < NB; n++) if (n !== 8 && s.st[n] === 0 && Math.hypot(s.x[n] - s.x[8], s.y[n] - s.y[8]) < DD) s.y[8] -= DD; }
    if (p8 || (s.on8 && scratch)) {   // the 8 decides the game
      const win = p8 && s.on8 && !scratch;
      s.winner = win ? me : opp; s.reason = win ? 'w8' : s.on8 ? 'w8s' : 'w8e';
      return endMatch(s, G);
    }
    // groups: the first ball potted after the break picks them (not on a scratch)
    let newGrp = false;
    if (s.grp[me] < 0 && !wasBreak && !scratch && first > 0) { s.grp[me] = grpOf(first); s.grp[opp] = 1 - grpOf(first); newGrp = true; }
    let mine = 0;
    for (let i = 0; i < s.np; i++) { const n = s.pl[i]; if (n === 0 || n === 8) continue; if (s.grp[me] < 0 || grpOf(n) === s.grp[me]) mine++; }
    if (s.mode === 0 && !s.ai[me] && mine) { G.addScore(100 * (s.lv[1] + 1) * mine); }
    s.lastPot = mine;
    if (scratch) { s.turn = opp; s.hand = 1; s.x[0] = CX; s.y[0] = HEADY; s.vx[0] = s.vy[0] = 0; s.st[0] = 0; say(s, 'scratch', 90, C.pink); G.sfx('err'); }
    else if (!mine) s.turn = opp;
    else if (newGrp) say(s, 'groups', 90, C.cyan);
    if (s.turn !== me || scratch) { s.pw = 0; s.arm = false; s.parm = false; }
    nextPhase(s, G, scratch);
  }
  function nextPhase(s, G, scratch) {
    s.pw = 0; s.pdir = 1; s.arm = false; s.parm = false; s.pd = false; s.pm = false; s.hold = 0; s.ax = 0; s.ay = -1;
    if (s.hand) { s.ph = 'place'; s.aiT = 0; s.hx = CX; s.hy = HEADY + 10; if (!s.ai[s.turn] && !freeSpot(s, s.hx, s.hy)) { s.hx = CX + 14; } return; }
    s.ph = 'aim'; s.aiT = 0;
    const g = s.grp[s.turn];
    if (g >= 0 && left(s, g) === 0) say(s, 'on8', 110, C.lime); else if (!scratch && s.msgT < 40) say(s, turnMsg(s), 100, C.gold);
    if (s.ai[s.turn]) aiThink(s);
  }
  function endMatch(s, G) {
    s.ph = 'end'; s.endT = 0; s.hand = 0;
    if (s.mode === 0 && !s.ai[0] && s.winner === 0) {
      s.won = true; const m = s.lv[1] + 1;
      G.addScore(1000 * m); G.addScore(Math.max(0, 28 - s.shots[0]) * 25 * m); G.sfx('levelup');
    } else G.sfx(s.mode === 0 ? 'die' : 'levelup');
  }

  /* ---------- per-phase updates ---------- */
  function rot(s, a) { const c = Math.cos(a), sn = Math.sin(a), nx = s.ax * c - s.ay * sn, ny = s.ax * sn + s.ay * c, k = 1 / Math.sqrt(nx * nx + ny * ny); s.ax = nx * k; s.ay = ny * k; }
  function humanAim(s, G) {
    const p = G.ptr, L = G.held('left'), Rr = G.held('right');
    if (L || Rr) { s.hold++; const a = 0.004 + Math.min(s.hold, 45) * 0.00016; rot(s, Rr ? a : -a); } else s.hold = 0;
    if (G.held('up')) rot(s, -0.0018); if (G.held('down')) rot(s, 0.0018);
    // keyboard / A button: hold to charge (the bar bounces), let go to shoot
    if (!G.held('a')) { s.arm = true; if (s.chg) { s.chg = false; if (!s.pm) { s.pw = Math.max(0.06, s.pw); return launchStrike(s); } } }
    else if (s.arm && !p.down) { s.chg = true; s.pw += s.pdir * 0.022; if (s.pw >= 1) { s.pw = 1; s.pdir = -1; } else if (s.pw <= 0.04) { s.pw = 0.04; s.pdir = 1; } }
    // touch / mouse: drag back from where you press; the pull sets the aim (opposite the drag) and the power
    if (!p.down) { s.parm = true; if (s.pd && s.pm) { s.pm = false; s.pd = false; if (s.pw > 0.05) return launchStrike(s); s.pw = 0; } s.pd = false; }
    else if (s.parm) {
      if (!s.pd) { s.pd = true; s.anx = p.x; s.any = p.y; s.pm = false; }
      const dx = s.anx - p.x, dy = s.any - p.y, d = Math.sqrt(dx * dx + dy * dy);
      if (d >= 6) { s.ax = dx / d; s.ay = dy / d; s.pw = clamp((d - 6) / 62, 0, 1); s.pm = true; s.chg = false; }
      else if (s.pm) s.pw = 0;
    }
  }
  function launchStrike(s) { s.ph = 'strike'; s.sk = 0; s.chg = false; s.pd = false; }
  function placeHuman(s, G) {
    const p = G.ptr, y0 = s.hand === 1 ? HEADY : CT + R;
    if (G.held('left')) s.hx -= 1.6; if (G.held('right')) s.hx += 1.6; if (G.held('up')) s.hy -= 1.6; if (G.held('down')) s.hy += 1.6;
    if (p.down) { s.pd = true; s.hx = p.x; s.hy = p.y - 10; }   // the ball rides above the finger
    s.hx = clamp(s.hx, CL + R, CR - R); s.hy = clamp(s.hy, y0, CB - R);
    const lift = !p.down && s.pd; if (lift) s.pd = false;
    if (G.hit('a') || lift) {
      if (freeSpot(s, s.hx, s.hy)) { s.hand = 0; s.x[0] = s.hx; s.y[0] = s.hy; s.vx[0] = s.vy[0] = 0; s.ph = 'aim'; s.arm = false; s.parm = false; s.pd = false; say(s, turnMsg(s), 100, C.gold); G.sfx('blip'); }
      else G.sfx('err');
    }
  }

  let last = null;
  const api = {
    id: 'cornerPocket', daily: true, name: 'CORNER POCKET', year: '1984', blurb: 'Eight-ball pool. Pot your group, then the 8. Play the machine or a friend.', track: 'title',
    help: 'drag back to aim · let go to shoot', keys: '← → aim · hold Space for power · release',
    // The Daily Challenge is the same match for everyone: against the machine on MEDIUM, straight to the break (no menu to pick an easier level).
    init(G) { last = newState(); const d = window.Arcade && window.Arcade.daily && window.Arcade.daily(); if (d && d.on) startMatch(last, 0, 1); return last; },
    update(s, G) {
      s.t++; if (s.msgT > 0) s.msgT--; if (s.sfxT > 0) s.sfxT--;
      tickFx(s.fx);
      for (let i = 0; i < NB; i++) if (s.st[i] === 1) { s.dk[i]++; s.x[i] += (PX[s.dp[i]] - s.x[i]) * 0.3; s.y[i] += (PY[s.dp[i]] - s.y[i]) * 0.3; if (s.dk[i] >= 10) s.st[i] = 2; }
      switch (s.ph) {
        case 'menu': return menu(s, G);
        case 'rules': if (G.hit('a') || G.tap) { if (++s.page > 1) { s.page = 0; s.ph = 'menu'; } G.sfx('blip'); } return;
        case 'aim':
          if (s.ai[s.turn]) {
            s.aiT++;
            if (s.aiT > 24) {   // turn the cue to the chosen line, charge, shoot
              s.ax += (s.tdx - s.ax) * 0.14; s.ay += (s.tdy - s.ay) * 0.14; const k = 1 / Math.sqrt(s.ax * s.ax + s.ay * s.ay); s.ax *= k; s.ay *= k;
              if (s.aiT > 60) { s.pw += s.tpw / 28; if (s.pw >= s.tpw) { s.pw = s.tpw; s.ax = s.tdx; s.ay = s.tdy; launchStrike(s); } }
            }
          } else humanAim(s, G);
          return;
        case 'strike': if (++s.sk >= 5) launch(s, G); return;
        case 'place':
          if (s.ai[s.turn]) { if (++s.aiT === 40) { aiPlace(s); s.hand = 0; s.ph = 'aim'; s.aiT = 0; say(s, turnMsg(s), 100, C.gold); aiThink(s); G.sfx('blip'); } }
          else placeHuman(s, G);
          return;
        case 'roll': {
          const moving = physics(s, G); s.rollT++;
          if (!moving || s.rollT > 60 * 25) { for (let i = 0; i < NB; i++) { s.vx[i] = s.vy[i] = 0; if (s.st[i] === 1) s.st[i] = 2; } finishShot(s, G); }
          return;
        }
        case 'end': if (++s.endT === 150 && !s.done) { s.done = true; G.over(); } return;
      }
    },
    draw(s, G, ctx) { drawAll(s, G, ctx); },
    thumb(ctx, tt) { drawThumb(ctx, tt); },
    ghost(s, ctx) { ctx.fillStyle = C.white; for (let i = 0; i < NB; i++) if (s.st[i] === 0) ctx.fillRect(Math.round(s.x[i]) - 3, Math.round(s.y[i]) - 3, 6, 6); }
  };
  function menu(s, G) {
    const act = i => {
      if (i === 0) startMatch(s, 0, s.lvSel); else if (i === 2) startMatch(s, 1, s.lvSel); else if (i === 3) { s.ph = 'rules'; s.page = 0; }
      else s.lvSel = (s.lvSel + 1) % 3;
      G.sfx(i === 3 || i === 1 ? 'blip' : 'select');
    };
    if (G.hit('up')) { s.sel = (s.sel + 3) % 4; G.sfx('tick'); } if (G.hit('down')) { s.sel = (s.sel + 1) % 4; G.sfx('tick'); }
    if (s.sel === 1) { if (G.hit('left')) { s.lvSel = (s.lvSel + 2) % 3; G.sfx('tick'); } if (G.hit('right')) { s.lvSel = (s.lvSel + 1) % 3; G.sfx('tick'); } }
    if (G.hit('a')) act(s.sel);
    if (G.tap) { for (let i = 0; i < 4; i++) { const y = 92 + i * 26; if (G.tap.x >= 28 && G.tap.x <= 196 && G.tap.y >= y - 3 && G.tap.y <= y + 22) { s.sel = i; act(i); break; } } }
  }

  /* ---------- drawing ---------- */
  let SPR = null, TBL = null, RING = null;
  function disc(c, cx, cy, r, col) { c.fillStyle = col; for (let dy = -r; dy <= r; dy++) { const w = Math.floor(Math.sqrt(r * r + r * 0.6 - dy * dy)); c.fillRect(cx - w, cy + dy, 2 * w + 1, 1); } }
  function makeArt() {
    const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d'); x.imageSmoothingEnabled = false; return x; };
    SPR = [];
    for (let n = 0; n < NB; n++) {
      const c = mk(9, 9), col = n === 0 ? '#ffffff' : n === 8 ? BCOL[8] : BCOL[n < 8 ? n : n - 8];
      disc(c, 4, 4, 4, n >= 9 ? '#f2eeff' : col);
      if (n >= 9) { c.save(); c.beginPath(); c.rect(0, 2, 9, 5); c.clip(); disc(c, 4, 4, 4, col); c.restore(); }
      c.fillStyle = 'rgba(0,0,0,.28)'; c.fillRect(2, 7, 5, 1); c.fillRect(7, 4, 1, 2);
      if (n === 8) { c.fillStyle = '#ffffff'; c.fillRect(3, 3, 3, 3); c.fillStyle = BCOL[8]; c.fillRect(4, 4, 1, 1); }
      else { c.fillStyle = 'rgba(255,255,255,.9)'; c.fillRect(2, 2, 2, 1); c.fillRect(2, 3, 1, 1); }
      SPR.push(c.canvas);
    }
    const rg = mk(9, 9); disc(rg, 4, 4, 4, '#ffffff'); rg.globalCompositeOperation = 'destination-out'; disc(rg, 4, 4, 3, '#000'); RING = rg.canvas;
    const t = mk(W, H);
    t.fillStyle = '#05030c'; t.fillRect(0, 0, W, H);
    t.fillStyle = C.pink; t.fillRect(CL - 10, CT - 10, CR - CL + 20, CB - CT + 20);
    t.fillStyle = '#2a1668'; t.fillRect(CL - 8, CT - 8, CR - CL + 16, CB - CT + 16);
    t.fillStyle = C.violet; t.fillRect(CL - 3, CT - 3, CR - CL + 6, CB - CT + 6);
    t.fillStyle = '#0b4f40'; t.fillRect(CL, CT, CR - CL, CB - CT);
    for (let y = CT; y < CB; y += 8) { t.fillStyle = (((y - CT) >> 3) & 1) ? '#0d5646' : '#0b4f40'; t.fillRect(CL, y, CR - CL, 8); }
    t.fillStyle = '#083a30'; t.fillRect(CL, CT, CR - CL, 2); t.fillRect(CL, CT, 2, CB - CT); t.fillRect(CR - 2, CT, 2, CB - CT); t.fillRect(CL, CB - 2, CR - CL, 2);
    t.fillStyle = '#1a7a60'; for (let x = CL + 4; x < CR - 4; x += 6) t.fillRect(x, HEADY, 3, 1);
    t.fillStyle = '#1a7a60'; t.fillRect(CX, FOOTY, 1, 1);
    t.fillStyle = C.gold;
    for (let i = 1; i < 4; i++) { const x = CL + i * (CR - CL) / 4; t.fillRect(Math.round(x) - 1, CT - 7, 2, 2); t.fillRect(Math.round(x) - 1, CB + 5, 2, 2); }
    for (const i of [1, 2, 3, 5, 6, 7]) { const y = CT + i * (CB - CT) / 8; t.fillRect(CL - 7, Math.round(y) - 1, 2, 2); t.fillRect(CR + 5, Math.round(y) - 1, 2, 2); }
    for (let p = 0; p < 6; p++) { disc(t, PX[p], PY[p], 9, C.gold); disc(t, PX[p], PY[p], 8, '#05030c'); }
    TBL = t.canvas;
  }
  const dots = (c, x0, y0, x1, y1, step, col) => {
    const dx = x1 - x0, dy = y1 - y0, l = Math.sqrt(dx * dx + dy * dy); if (l < 1) return;
    const n = Math.floor(l / step), sx = dx / l * step, sy = dy / l * step; c.fillStyle = col;
    for (let i = 0; i <= n; i++) c.fillRect(Math.round(x0 + sx * i), Math.round(y0 + sy * i), 1, 1);
  };
  const TR = { t: 0, i: -1, x: 0, y: 0 };
  function trace(s, ox, oy, dx, dy) {
    let bt = 1e9, bi = -1;
    if (dx < 0) bt = Math.min(bt, (CL + R - ox) / dx); else if (dx > 0) bt = Math.min(bt, (CR - R - ox) / dx);
    if (dy < 0) bt = Math.min(bt, (CT + R - oy) / dy); else if (dy > 0) bt = Math.min(bt, (CB - R - oy) / dy);
    for (let i = 1; i < NB; i++) {
      if (s.st[i] !== 0) continue;
      const ex = s.x[i] - ox, ey = s.y[i] - oy, b = ex * dx + ey * dy; if (b <= 0) continue;
      const c = ex * ex + ey * ey - b * b; if (c >= DD2) continue;
      const tt = b - Math.sqrt(DD2 - c); if (tt < bt) { bt = tt; bi = i; }
    }
    TR.t = bt; TR.i = bi; TR.x = ox + dx * bt; TR.y = oy + dy * bt;
  }
  function drawGuide(s, c) {
    const ox = s.x[0], oy = s.y[0]; trace(s, ox, oy, s.ax, s.ay);
    dots(c, ox + s.ax * 6, oy + s.ay * 6, TR.x, TR.y, 3, 'rgba(255,255,255,.85)');
    c.drawImage(RING, Math.round(TR.x) - 4, Math.round(TR.y) - 4);
    if (TR.i >= 0) {
      const nx = (s.x[TR.i] - TR.x) / DD, ny = (s.y[TR.i] - TR.y) / DD;
      dots(c, s.x[TR.i], s.y[TR.i], s.x[TR.i] + nx * 16, s.y[TR.i] + ny * 16, 2, C.gold);
      const k = s.ax * nx + s.ay * ny, cx = s.ax - k * nx, cy = s.ay - k * ny, l = Math.sqrt(cx * cx + cy * cy);
      if (l > 0.08) dots(c, TR.x, TR.y, TR.x + cx / l * 9 * l, TR.y + cy / l * 9 * l, 2, C.cyan);
    } else {
      const hx = Math.abs(TR.x - (CL + R)) < 0.01 || Math.abs(TR.x - (CR - R)) < 0.01;
      dots(c, TR.x, TR.y, TR.x + (hx ? -s.ax : s.ax) * 10, TR.y + (hx ? s.ay : -s.ay) * 10, 2, 'rgba(45,226,255,.7)');
    }
  }
  function drawCue(s, c, pull) {
    const ox = s.x[0], oy = s.y[0], gap = R + 2 + pull;
    for (let i = 0; i < 56; i++) {
      const px = ox - s.ax * (gap + i), py = oy - s.ay * (gap + i);
      if (px < CL - 8 || px > CR + 8 || py < CT - 8 || py > CB + 8) continue;   // the cue stops at the rails
      c.fillStyle = i < 2 ? C.cyan : i < 4 ? C.white : i < 44 ? '#e6b066' : '#7a431a';
      c.fillRect(Math.round(px) - 1, Math.round(py) - 1, 2, 2);
    }
  }
  function drawBall(c, s, i, tt) {
    if (s.st[i] === 2) return;
    let x = s.x[i], y = s.y[i];
    if (s.st[i] === 1) { const k = 1 - s.dk[i] / 10; if (k <= 0.1) return; const sz = Math.max(2, Math.round(9 * k)); c.drawImage(SPR[i], Math.round(x - sz / 2), Math.round(y - sz / 2), sz, sz); return; }
    const rx = Math.round(x), ry = Math.round(y);
    c.fillStyle = 'rgba(0,0,0,.35)'; c.fillRect(rx - 3, ry + 3, 7, 2);
    c.drawImage(SPR[i], rx - 4, ry - 4);
  }
  function dotsFor(s, c, g, x0, dir) {   // the balls a player still has to pot
    const m = g >= 0 && left(s, g) === 0;
    for (let k = 0; k < 8; k++) {
      const n = k < 7 ? (g === 0 ? k + 1 : k + 9) : 8, x = x0 + dir * k * 6;
      if (n === 8 && !m) continue;
      const gone = s.st[n] === 2;
      const col = n === 8 ? '#2a2540' : BCOL[n < 8 ? n : n - 8];
      if (gone) { c.fillStyle = '#2a2540'; c.fillRect(x, 26, 5, 5); c.fillStyle = C.bg; c.fillRect(x + 1, 27, 3, 3); }
      else { c.fillStyle = n === 8 ? '#6b6490' : col; c.fillRect(x, 26, 5, 5); if (n >= 9) { c.fillStyle = '#f2eeff'; c.fillRect(x, 26, 5, 1); c.fillRect(x, 30, 5, 1); } else if (n === 8) { c.fillStyle = C.ink; c.fillRect(x + 2, 28, 1, 1); } }
    }
  }
  function drawAll(s, G, c) {
    if (!TBL) makeArt();
    c.drawImage(TBL, 0, 0);
    if (s.ph === 'rules') return drawRules(s, c);
    if (s.ph === 'menu') { for (let i = 0; i < NB; i++) drawBall(c, s, i, 0); return drawMenu(s, G, c); }
    const pl = s.ph === 'place', human = !s.ai[s.turn];
    for (let i = 1; i < NB; i++) drawBall(c, s, i, s.t);
    if (pl) {   // ball in hand
      const ok = freeSpot(s, s.hx, s.hy), hx = s.ai[s.turn] ? s.x[0] : s.hx, hy = s.ai[s.turn] ? s.y[0] : s.hy;
      if (!s.ai[s.turn]) { c.globalAlpha = (s.t >> 3) & 1 ? 0.55 : 0.9; c.drawImage(SPR[0], Math.round(hx) - 4, Math.round(hy) - 4); c.globalAlpha = 1; c.drawImage(RING, Math.round(hx) - 4, Math.round(hy) - 4); if (!ok) { c.fillStyle = C.red; c.fillRect(Math.round(hx) - 1, Math.round(hy) - 1, 3, 3); } }
    } else if (s.st[0] === 0) drawBall(c, s, 0, s.t);
    if (s.ph === 'aim' || s.ph === 'strike') {
      if (s.ph === 'aim') drawGuide(s, c);
      const pull = s.ph === 'strike' ? (2 + s.pw * 20) * (1 - s.sk / 5) : 2 + s.pw * 20;
      drawCue(s, c, pull);
    }
    drawFx(c, s.fx);
    // top band: the two players and the balls each has left
    const names = s.mode === 1 ? ['p1n', 'p2n'] : ['you', 'cpu'];
    for (let p = 0; p < 2; p++) {
      const nm = t(names[p]), act = s.turn === p && s.ph !== 'end', col = act ? C.gold : C.dim;
      if (p === 0) { text(c, nm, 8, 25, col); if (s.grp[0] >= 0) dotsFor(s, c, s.grp[0], 12 + nm.length * 8, 1); }
      else { text(c, nm, W - 8, 25, col, 8, 'right'); if (s.grp[1] >= 0) dotsFor(s, c, s.grp[1], W - 12 - nm.length * 8 - 5, -1); }
    }
    if (s.grp[0] < 0) text(c, t('open'), W / 2, 25, C.dim, 8, 'center');
    const k = s.msgT > 0 ? s.msg : s.ph === 'place' ? (s.ai[s.turn] ? 'hand' : s.hand === 1 ? 'placeLine' : 'placeAny') : s.ph === 'end' ? '' : turnMsg(s);
    if (k) text(c, t(k), W / 2, 34, s.msgT > 0 ? s.msgC : s.ph === 'place' ? C.pink : C.ink, 8, 'center');
    // power bar
    c.fillStyle = C.violet; c.fillRect(CL - 8, 266, CR - CL + 16, 14); c.fillStyle = '#05030c'; c.fillRect(CL - 7, 267, CR - CL + 14, 12);
    const bw = CR - CL + 14, fill = Math.round(bw * s.pw);
    for (let x = 0; x < fill; x += 4) { const f = x / bw; c.fillStyle = f < 0.5 ? C.lime : f < 0.8 ? C.gold : C.red; c.fillRect(CL - 7 + x, 267, Math.min(3, fill - x), 12); }
    for (const [ox, oy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1]]) text(c, t('power'), W / 2 + ox, 270 + oy, '#05030c', 8, 'center');   // a dark outline keeps POWER readable over the green, gold and red fill
    text(c, t('power'), W / 2, 270, C.white, 8, 'center');
    G.hud(null, s.mode === 1 ? t('p2') : t(LVK[s.lv[1]]));
    if (s.ph === 'end') drawEnd(s, G, c);
  }
  function drawEnd(s, G, c) {
    const pop = Math.min(1, s.endT / 10); if (pop < 1) return;
    const win = s.mode === 0 ? s.winner === 0 : true;
    const k = s.mode === 1 ? (s.winner === 0 ? 'p1Wins' : 'p2Wins') : (s.winner === 0 ? 'youWin' : 'youLose');
    c.fillStyle = C.pink; c.fillRect(20, 160, 184, 66); c.fillStyle = '#05030c'; c.fillRect(22, 162, 180, 62);
    text(c, t(k), W / 2, 170, win ? C.lime : C.red, 12, 'center');
    text(c, t(s.reason), W / 2, 192, C.ink, 8, 'center');
  }
  function drawMenu(s, G, c) {
    c.fillStyle = 'rgba(5,3,12,.82)'; c.fillRect(0, 0, W, H);
    text(c, t('title'), W / 2, 66, C.gold, 12, 'center');
    const lv = t(LVK[s.lvSel]);
    for (let i = 0; i < 4; i++) {
      const y = 92 + i * 26, on = s.sel === i;
      c.fillStyle = on ? C.pink : C.violet; c.fillRect(32, y, 160, 20); c.fillStyle = '#12082e'; c.fillRect(34, y + 2, 156, 16);
      if (i === 1) { text(c, t('level'), 40, y + 6, on ? C.gold : C.ink); text(c, (on ? '< ' : '') + lv + (on ? ' >' : ''), 184, y + 6, on ? C.gold : C.cyan, 8, 'right'); }
      else text(c, t(['vs', '', 'two', 'how'][i]), W / 2, y + 6, on ? C.gold : C.ink, 8, 'center');
    }
    text(c, t(matchMedia('(pointer:fine)').matches ? 'pick' : 'pickT'), W / 2, 202, (s.t >> 5) & 1 ? C.pink : C.dim, 8, 'center');
    text(c, t('pts'), W / 2, 228, C.dim, 8, 'center');
  }
  function drawRules(s, c) {
    c.fillStyle = 'rgba(5,3,12,.9)'; c.fillRect(CL - 8, CT - 8, CR - CL + 16, CB - CT + 16); c.fillRect(0, 22, W, H - 22);
    text(c, t('how'), W / 2, 30, C.gold, 8, 'center');
    const pages = [['r1', 'r2', 'r3', 'r4', 'r5'], ['r6', 'r7', 'r8']]; let y = 48;
    for (const k of pages[s.page]) { for (const ln of wrap(t(k), 26)) { text(c, ln, 8, y, C.ink); y += 10; } y += 7; }
    text(c, (s.page + 1) + '/2', W - 8, 30, C.dim, 8, 'right');
    const fine = matchMedia('(pointer:fine)').matches;
    text(c, t(s.page === 0 ? (fine ? 'next' : 'nextT') : (fine ? 'back' : 'backT')), W / 2, 262, (s.t >> 5) & 1 ? C.pink : C.dim, 8, 'center');
  }
  function drawThumb(c, tt) {
    c.fillStyle = C.bg; c.fillRect(0, 0, 112, 84);
    c.fillStyle = C.pink; c.fillRect(6, 7, 100, 70); c.fillStyle = '#2a1668'; c.fillRect(7, 8, 98, 68); c.fillStyle = '#0b4f40'; c.fillRect(12, 13, 88, 58);
    for (const [x, y] of [[12, 13], [56, 12], [100, 13], [12, 71], [56, 72], [100, 71]]) disc(c, x, y, 4, '#05030c');
    const T0 = tt % 200, hit = T0 > 70;
    const cols = [C.gold, C.blue, C.red, C.violet, C.orange, C.lime, C.brown, '#14101f', C.gold, C.blue];
    let i = 0;
    for (let r = 0; r < 4; r++) for (let q = 0; q <= r; q++) {
      const bx = 30 - r * 5, by = 42 + (q - r / 2) * 6, k = hit ? Math.min(1, (T0 - 70) / 60) : 0;
      const sx = bx - k * (8 + q * 3 + r * 2) * (r + 1) / 3, sy = by + k * (q - r / 2 + 0.5) * 14;
      disc(c, Math.round(clamp(sx, 15, 97)), Math.round(clamp(sy, 16, 68)), 2, cols[i++ % cols.length]);
    }
    const cx = hit ? 36 + Math.max(0, 1 - (T0 - 70) / 20) * 40 : 94 - (T0 / 70) * 58;
    disc(c, Math.round(clamp(cx, 15, 97)), 42 + (hit ? Math.round((T0 - 70) / 14) : 0), 2, C.white);
    if (!hit) { c.fillStyle = '#e6b066'; c.fillRect(Math.round(98 - (T0 / 70) * 58) + 4, 42, 14, 1); }
  }

  // a self-contained match with no screen, for tests: the same code that runs on a phone, driven by two machine players
  function selfplay(seed, l0, l1, maxFrames) {
    return withSeed(seed >>> 0, () => {
      const Gs = { score: 0, over() { this.done = true; }, addScore(n) { this.score += n; }, sfx() {}, held: () => false, hit: () => false, ptr: { down: false, x: 0, y: 0 }, tap: null, done: false };
      const s = newState(); startMatch(s, 1, 1); s.ai = [true, true]; s.lv = [l0, l1]; aiThink(s);
      let frames = 0, bad = 0, lastPh = '', shots = 0, wins = -1, pots = 0;
      while (frames < maxFrames && !Gs.done) {
        api.update(s, Gs); frames++;
        let n = 0;
        for (let i = 0; i < NB; i++) { if (s.st[i] === 0) { n++; if (!(s.x[i] >= CL && s.x[i] <= CR && s.y[i] >= CT && s.y[i] <= CB) || !isFinite(s.x[i] + s.y[i])) bad++; } else if (s.st[i] === 2) n++; else n++; }
        if (n !== NB) bad++;
      }
      let potted = 0; for (let i = 1; i < NB; i++) if (s.st[i] === 2) potted++;
      return { done: Gs.done, frames, bad, winner: s.winner, reason: s.reason, shots: s.shots[0] + s.shots[1], potted, grp: s.grp.slice(), ph: s.ph };
    });
  }
  window.NutPool = { cur: () => last, selfplay, tx: TX, geom: { CL, CR, CT, CB, CX, CY, HEADY, FOOTY, R } };
  return api;
})();
return cornerPocket;
});
