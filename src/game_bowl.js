/* NUTCADE arcade: NUT BOWL, a top-down arcade football game.
   You always have the ball: pick a play (dive, sweep, slant, bomb, or punt / kick on 4th down), then run it with the stick or throw to a receiver.
   The computer plays defence on the field, and between your drives its offence is worked out from the seeded list in init(), so a seed gives the same game.
   Four quarters of 2:30. Yards, first downs, touchdowns, field goals and a win bonus score points.
   update() uses only + - * / and sqrt (no sin, cos or atan2 of the browser) and the seeded RNG, so a replay gives the same score on every phone. */
(window.NutCabinets = window.NutCabinets || []).push(function (K) {
'use strict';
const { W, H, C, Math, text, T, rnd, ri, clamp, boom, tickFx, drawFx } = K;

const FH = 360, GL = 30, OWN = 330, YD = 3, XL = 14, XR = 210;                     // the field: 3 px a yard, goal lines at y 30 (theirs) and y 330 (ours), sidelines at x 14 and 210
const VIEW_TOP = 22, VIEW_H = 206, PANEL = VIEW_TOP + VIEW_H;
const QLEN = 150, GAME = QLEN * 4;                                                   // game seconds
const DEFSP = [0.95, 1.0, 1.05, 1.1];                                                // the defence gets quicker each quarter
const RUN = 1.0, BURST = 1.55, BURST_MAX = 50, TACKLE = 5;
const yOf = yd => OWN - yd * YD;
const ydOf = y => Math.round((OWN - y) / YD);
const camOf = s => clamp(Math.round(s.fy - 110), 0, FH - VIEW_H);                    // a pure function of the state, so update() and replays see what the screen shows
const MENU = [['DIVE', 'SWEEP', 'SLANT', 'BOMB'], ['PUNT', 'KICK', 'DIVE', 'SLANT']];
const ROUTES = {                                                                     // per receiver: [until frame, vx, vy] pieces; then he settles
  SLANT: [[[14, 0, -1.3], [70, 0.95, -0.75]], [[14, 0, -1.3], [70, -0.95, -0.75]], [[26, 0, -1.2], [80, 0.55, -0.3]]],
  BOMB: [[[120, 0, -1.4]], [[36, 0, -1.3], [120, -0.55, -1.15]], [[20, 0, -1.2], [100, 1.0, -0.25]]]
};
const PAL = { grass: '#14652c', grass2: '#188036', line: '#e9f5ea', ezone: '#3a2a78', ezone2: '#2f2166', mine: '#ff9a1f', myhelm: '#ffcf3a', theirs: '#8d6bff', thelm: '#ff3d8b', ball: '#b8651f' };

const mk = (x, y, role, extra) => Object.assign({ x, y, vx: 0, vy: 0, role, blk: 0, stun: 0, eng: null }, extra || {});
const dist = (a, b) => Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y));
const mmss = n => { const r = Math.max(0, Math.floor(n)); return Math.floor(r / 60) + ':' + (r % 60 < 10 ? '0' : '') + (r % 60); };

const bowl = {
  id: 'bowl', daily: true, name: 'NUT BOWL', year: '1984', blurb: 'Top-down football. Pick a play, run it, beat the clock.', track: 'action',
  help: 'pick a play · stick to run · A for a burst · tap a receiver to throw', keys: '← → pick a play, A to snap · arrows run, A burst · ← → pick target, A throw',
  init(G) {
    const cpu = []; for (let i = 0; i < 40; i++) cpu.push({ r: Math.round(rnd(0, 1) * 1000) / 1000, t: ri(25, 55), p: ri(15, 40) });
    const s = { t: 0, mode: 'huddle', los: 25, first: 35, down: 1, clock: 0, mine: 0, cpu: 0, cpuR: cpu, ci: 0, cur: 0, menu: MENU[0], play: '', playType: '', off: null, def: [], wr: [], ol: [], qb: null, rb: null,
      car: null, ball: { x: 112, y: yOf(25) }, z: 0, pass: null, kick: null, tgt: 0, pt: 0, carT: 0, burst: BURST_MAX, bursting: false, qbHas: false, blitz: false, fy: yOf(25) - 10, snapT: 0,
      gain: null, bonusTxt: '', fx: [], msg: '', msgT: 0, banner: 0, bannerTxt: '', bannerSub: '', next: '', cpuYd: 25, cpuTxt: '', cpuSub: '', ourYd: 25, end: false, intro: 200, q: 0, plays: 0 };
    this.newDown(s); return s;
  },
  q(s) { return Math.min(3, Math.floor(s.clock / QLEN)); },
  newDown(s) { s.menu = MENU[s.down === 4 ? 1 : 0]; s.cur = 0; s.mode = 'huddle'; s.play = ''; s.car = null; s.pass = null; s.kick = null; s.z = 0; s.ball = { x: 112, y: yOf(s.los) }; s.fy = yOf(s.los) - 10; s.q = this.q(s); this.formation(s, false); },
  formation(s, live) {                                                              // line both teams up on the ball
    const ly = yOf(s.los), x0 = 112;
    s.qb = mk(x0, ly + 9, 'qb'); s.rb = mk(x0, ly + 20, 'rb');
    s.ol = [mk(x0 - 16, ly + 3, 'ol'), mk(x0, ly + 3, 'ol'), mk(x0 + 16, ly + 3, 'ol')];
    s.wr = [mk(x0 - 62, ly + 4, 'wr', { n: 1 }), mk(x0 + 62, ly + 4, 'wr', { n: 2 }), mk(x0 + 34, ly + 7, 'wr', { n: 3 })];
    const top = Math.max(10, ly - 12), d = [];
    d.push(mk(96, Math.max(6, ly - 5), 'dl', { base: 0.92, delay: 0 }), mk(112, Math.max(6, ly - 5), 'dl', { base: 0.92, delay: 0 }), mk(128, Math.max(6, ly - 5), 'dl', { base: 0.92, delay: 0 }));
    d.push(mk(80, Math.max(8, ly - 20), 'lb', { base: 1.02, delay: 8, hx: 80 }), mk(144, Math.max(8, ly - 20), 'lb', { base: 1.02, delay: 8, hx: 144 }));
    d.push(mk(52, Math.max(10, ly - 36), 'db', { base: 1.1, delay: 14, cov: 0 }), mk(172, Math.max(10, ly - 36), 'db', { base: 1.1, delay: 14, cov: 1 }));
    s.def = d;
  },
  say(s, m, n = 100) { s.msg = m; s.msgT = n; },
  choose(s, G, i) {
    const name = s.menu[i]; if (!name) return; s.play = name; G.sfx('select');
    if (name === 'PUNT' || name === 'KICK') return this.kickOff(s, G, name);
    s.playType = name === 'SLANT' || name === 'BOMB' ? 'pass' : 'run';
    s.mode = 'snap'; s.snapT = 36; s.pt = 0; s.car = null; s.pass = null; s.tgt = 0; s.burst = BURST_MAX; s.bursting = false; s.qbHas = s.playType === 'pass'; s.carT = 0;
    s.blitz = rnd(0, 1) < 0.3;
    const run = s.playType === 'run';                                               // the line fight: each lineman holds one rusher for a while (longer on a pass)
    for (let k = 0; k < 3; k++) { const b = s.ol[k], d = s.def[k]; b.eng = d; d.blk = run ? ri(20, 45) : ri(48, 100); }
    s.intro = 0;
  },
  kickOff(s, G, name) {                                                             // punt or field goal
    s.mode = 'kick'; s.pt = 0; const lx = 112, ly = yOf(s.los);
    if (name === 'KICK') {
      const dd = 100 - s.los + 17, p = clamp(1.45 - dd * 0.016, 0.05, 0.97), good = rnd(0, 1) < p;
      s.kick = { f: 0, F: 56, x0: lx, y0: ly + 9, x1: lx + (good ? 0 : (rnd(0, 1) < 0.5 ? -14 : 14)), y1: 8, good, kind: 'fg', hi: 38, dd };
    } else {
      const len = ri(28, 46), end = s.los + len, tb = end >= 100;
      s.kick = { f: 0, F: 56, x0: lx, y0: ly + 9, x1: lx + ri(-30, 30), y1: tb ? yOf(98) : yOf(end), good: false, kind: 'punt', hi: 46, spot: end, tb };
    }
    G.sfx('hit');
  },
  turnover(s, G, cpuYd, txt) { s.cpuYd = clamp(cpuYd, 1, 99); s.next = 'cpu'; s.mode = 'result'; s.banner = 80; s.bannerTxt = txt; s.bannerSub = ''; s.gain = null; s.car = null; },
  cpuDrive(s, G) {                                                                  // the computer's turn with the ball, worked out from the seeded list
    const e = s.cpuR[s.ci % s.cpuR.length]; s.ci++;
    const pTD = 0.05 + s.cpuYd * 0.002 + this.q(s) * 0.015, pFG = 0.14 + this.q(s) * 0.01;
    s.clock += e.t; s.ourYd = e.p;
    if (e.r < pTD) { s.cpu += 7; s.cpuTxt = 'CPU TOUCHDOWN'; s.ourYd = 25; G.sfx('die'); }
    else if (e.r < pTD + pFG) { s.cpu += 3; s.cpuTxt = 'CPU FIELD GOAL'; s.ourYd = 25; G.sfx('die'); }
    else { s.cpuTxt = 'CPU PUNTS'; G.sfx('tick'); }
    s.cpuSub = T('YOU') + ' ' + s.mine + '  CPU ' + s.cpu;
    s.mode = 'cpu'; s.banner = 110; s.q = this.q(s);
  },
  // the play ends: work out downs, distance, score and the clock
  endPlay(s, G, kind, y) {
    s.car = null; s.pass = null; s.qbHas = false;
    const yd = clamp(ydOf(y), 1, 99);
    s.plays++;
    if (kind === 'td') {
      s.mine += 7; G.addScore(800); s.clock += 5; boom(s.fx, s.ball.x, s.ball.y, C.gold, 30); G.sfx('levelup');
      s.cpuYd = 25; s.next = 'cpu'; s.mode = 'result'; s.banner = 100; s.gain = null; s.bannerTxt = 'TOUCHDOWN!'; s.bannerSub = T('YOU') + ' ' + s.mine + '  CPU ' + s.cpu; return;
    }
    if (kind === 'int') { G.sfx('err'); return this.turnover(s, G, 100 - yd, 'INTERCEPTED!'); }
    const prev = s.los; let txt;
    if (kind !== 'inc') s.los = yd;
    const gain = s.los - prev;
    if (gain > 0) G.addScore(gain * 10);
    s.clock += kind === 'inc' || kind === 'oob' ? 3 : 7;
    if (kind !== 'inc' && s.los >= s.first) { G.addScore(100); s.first = Math.min(100, s.los + 10); s.down = 1; txt = 'FIRST DOWN!'; G.sfx('coin'); }
    else { s.down++; if (s.down > 4) { G.sfx('err'); return this.turnover(s, G, 100 - s.los, 'TURNOVER ON DOWNS'); } G.sfx(gain > 0 ? 'tick' : 'wall'); }
    if (!txt) txt = kind === 'inc' ? 'INCOMPLETE' : kind === 'sack' ? 'SACK' : gain > 0 ? 'GAIN' : gain < 0 ? 'LOSS' : 'NO GAIN';
    s.next = 'huddle'; s.mode = 'result'; s.banner = 64; s.bannerTxt = txt; s.bannerSub = ''; s.gain = kind === 'inc' || txt === 'NO GAIN' ? null : gain;
  },
  throwTo(s, G, i) {
    const w = s.wr[i], q = s.qb, d = dist(w, q), F = Math.max(14, Math.floor(d / 4.2));
    const x1 = clamp(w.x + w.vx * F, XL - 4, XR + 4), y1 = clamp(w.y + w.vy * F, 8, FH - 8);
    s.pass = { x0: q.x, y0: q.y, x1, y1, f: 0, F, i, long: d > 110 }; s.qbHas = false; s.tgt = i; G.sfx('shoot');
  },
  land(s, G) {                                                                      // the pass arrives
    const p = s.pass, w = s.wr[p.i]; let nd = null, ndd = 999;
    for (const d of s.def) { const dd = Math.sqrt((d.x - p.x1) * (d.x - p.x1) + (d.y - p.y1) * (d.y - p.y1)); if (dd < ndd) { ndd = dd; nd = d; } }
    const dr = Math.sqrt((w.x - p.x1) * (w.x - p.x1) + (w.y - p.y1) * (w.y - p.y1)), r = rnd(0, 1), r2 = rnd(0, 1);
    s.ball = { x: p.x1, y: p.y1 }; s.z = 0;
    if (dr < 9 && (ndd >= 8 || r < 0.62) && !(p.long && r2 < 0.12)) {                // caught
      s.car = w; w.ctl = true; s.pass = null; s.carT = s.pt; for (const d of s.def) d.delay = 0; G.sfx('coin'); this.say(s, 'CAUGHT', 40); return;
    }
    if (ndd < 8 && r < 0.3) return this.endPlay(s, G, 'int', p.y1);
    s.pass = null; this.endPlay(s, G, 'inc', p.y1);
  },
  update(s, G) {
    s.t++; if (s.msgT) s.msgT--; if (s.intro) s.intro--; tickFx(s.fx);
    const m = s.mode;
    if (m === 'huddle') {
      s.fy += (yOf(s.los) - 10 - s.fy) * 0.2;
      if (G.hit('left')) { s.cur = (s.cur + 3) % 4; G.sfx('blip'); } else if (G.hit('right')) { s.cur = (s.cur + 1) % 4; G.sfx('blip'); }
      if (G.hit('a')) return this.choose(s, G, s.cur);
      if (G.tap && G.tap.y >= PANEL + 22) { const i = clamp(Math.floor((G.tap.x - 2) / 55), 0, 3); s.cur = i; return this.choose(s, G, i); }
      return;
    }
    if (m === 'snap') { s.fy += (yOf(s.los) - 10 - s.fy) * 0.2; if (--s.snapT <= 0) { s.mode = 'play'; G.sfx('hit'); } return; }
    if (m === 'play') return this.live(s, G);
    if (m === 'kick') {
      const k = s.kick; k.f++; const u = k.f / k.F;
      s.ball = { x: k.x0 + (k.x1 - k.x0) * u, y: k.y0 + (k.y1 - k.y0) * u }; s.z = 4 * u * (1 - u) * k.hi; s.fy += (s.ball.y - 20 - s.fy) * 0.1;
      if (k.f >= k.F) {
        s.z = 0; s.plays++; s.clock += 8;
        if (k.kind === 'fg') {
          if (k.good) { s.mine += 3; G.addScore(300); boom(s.fx, k.x1, 12, C.gold, 20); G.sfx('levelup'); s.cpuYd = 25; s.bannerTxt = 'KICK GOOD'; }
          else { G.sfx('err'); s.cpuYd = Math.max(20, 100 - s.los); s.bannerTxt = 'NO GOOD'; }
          s.bannerSub = T('YOU') + ' ' + s.mine + '  CPU ' + s.cpu;
        } else { s.cpuYd = k.tb ? 20 : 100 - k.spot; s.bannerTxt = 'PUNT'; s.bannerSub = ''; G.sfx('tick'); }
        s.next = 'cpu'; s.mode = 'result'; s.banner = 80; s.kick = null; s.gain = null;
      }
      return;
    }
    if (m === 'result') {
      if (--s.banner > 0) return;
      if (s.clock >= GAME) return this.finish(s, G);                              // time is up: no more drives
      if (s.next === 'cpu') { this.cpuDrive(s, G); return; }
      this.newDown(s); return;
    }
    if (m === 'cpu') {
      if (--s.banner > 0) return;
      if (s.clock >= GAME) return this.finish(s, G);
      s.los = s.ourYd; s.first = s.los + 10; s.down = 1; this.newDown(s); return;
    }
    if (m === 'end') { if (--s.banner <= 0) G.over(); }
  },
  finish(s, G) {
    s.mode = 'end'; s.banner = 200; s.end = true; s.clock = GAME;
    s.bonusTxt = ''; if (s.mine > s.cpu) { G.addScore(1000); s.bonusTxt = '+1000'; s.bannerTxt = 'YOU WIN'; G.sfx('levelup'); } else if (s.mine === s.cpu) { s.bannerTxt = 'TIE GAME'; G.sfx('coin'); } else { s.bannerTxt = 'YOU LOSE'; G.sfx('die'); }
    s.bannerSub = T('YOU') + ' ' + s.mine + '  CPU ' + s.cpu;
  },
  live(s, G) {
    s.pt++; s.clock += 1 / 30; const run = s.playType === 'run', q = s.qb, ly = yOf(s.los);
    // the receivers run their routes
    if (!run) {
      const R = ROUTES[s.play];
      for (let i = 0; i < 3; i++) {
        const w = s.wr[i]; if (w === s.car) continue; const segs = R[i]; let vx = 0, vy = 0;
        for (const g of segs) if (s.pt < g[0]) { vx = g[1]; vy = g[2]; break; }
        w.vx = vx; w.vy = vy; w.x = clamp(w.x + vx, XL + 4, XR - 4); w.y = Math.max(8, w.y + vy);
      }
      if (s.pt < 30) q.y += 0.33;                                                       // the quarterback drops back
    } else { if (s.pt < 10) { s.rb.y -= 1.0; s.rb.x += (q.x - s.rb.x) * 0.1; } else if (s.pt === 10) { s.car = s.rb; s.rb.ctl = true; s.carT = 10; G.sfx('tick'); } }
    // you control the runner (or the receiver who caught it)
    const c = s.car;
    if (c && c.ctl) {
      let dx = (G.held('right') ? 1 : 0) - (G.held('left') ? 1 : 0), dy = (G.held('down') ? 1 : 0) - (G.held('up') ? 1 : 0);
      if (dx && dy) { dx *= 0.7071; dy *= 0.7071; }
      s.bursting = G.held('a') && s.burst > 0 && (dx || dy); let sp = RUN; if (s.bursting) { sp = BURST; s.burst--; }
      c.vx += (dx * sp - c.vx) * 0.3; c.vy += (dy * sp - c.vy) * 0.3;
      c.x += c.vx; c.y = Math.min(FH - 4, c.y + c.vy);
      s.ball = { x: c.x + 2, y: c.y }; s.fy += (c.y - s.fy) * 0.15;
    } else if (!s.pass) { s.ball = { x: q.x + 2, y: q.y }; s.fy += (q.y - 20 - s.fy) * 0.1; }
    // the throw
    if (!run && s.qbHas && s.pt >= 12) {
      if (G.hit('left')) { s.tgt = (s.tgt + 2) % 3; G.sfx('blip'); } else if (G.hit('right')) { s.tgt = (s.tgt + 1) % 3; G.sfx('blip'); }
      if (G.hit('a')) this.throwTo(s, G, s.tgt);
      else if (G.tap && G.tap.y >= VIEW_TOP && G.tap.y < PANEL) {
        const wy = G.tap.y - VIEW_TOP + camOf(s); let best = -1, bd = 26;
        for (let i = 0; i < 3; i++) { const dd = Math.sqrt((s.wr[i].x - G.tap.x) * (s.wr[i].x - G.tap.x) + (s.wr[i].y - wy) * (s.wr[i].y - wy)); if (dd < bd) { bd = dd; best = i; } }
        if (best >= 0) this.throwTo(s, G, best);
      }
    }
    if (s.pass) {                                                                       // the ball in the air
      const p = s.pass; p.f++; const u = p.f / p.F;
      s.ball = { x: p.x0 + (p.x1 - p.x0) * u, y: p.y0 + (p.y1 - p.y0) * u }; s.z = 4 * u * (1 - u) * (8 + p.F * 0.5); s.fy += (s.ball.y - s.fy) * 0.12;
      if (p.f >= p.F) { this.land(s, G); if (s.mode !== 'play') return; }
    }
    this.blockers(s); this.defence(s, G);
    // what happens to the ball carrier
    const car = s.car;
    if (car) {
      if (car.y <= GL) { s.ball = { x: car.x, y: GL }; return this.endPlay(s, G, 'td', GL); }
      if (car.x < XL || car.x > XR) { car.x = clamp(car.x, XL, XR); return this.endPlay(s, G, 'oob', car.y); }
      if (car !== q) for (const d of s.def) {
        if (d.stun > 0 || Math.sqrt((d.x - car.x) * (d.x - car.x) + (d.y - car.y) * (d.y - car.y)) > TACKLE) continue;
        if (s.bursting && rnd(0, 1) < 0.3) { d.stun = 30; d.blk = 25; boom(s.fx, car.x, car.y, C.white, 6); G.sfx('pop'); this.say(s, 'BROKEN TACKLE', 40); continue; }
        boom(s.fx, car.x, car.y, C.red, 8); G.sfx('hit'); return this.endPlay(s, G, 'tackle', car.y);
      }
      if (s.pt > 900) return this.endPlay(s, G, 'tackle', car.y);
    } else if (s.qbHas) {                                                                // the quarterback can be sacked
      for (const d of s.def) if (d.blk <= 0 && Math.sqrt((d.x - q.x) * (d.x - q.x) + (d.y - q.y) * (d.y - q.y)) < 6) { boom(s.fx, q.x, q.y, C.red, 10); G.sfx('hit'); return this.endPlay(s, G, 'sack', q.y); }
      if (s.pt > 420) return this.endPlay(s, G, 'sack', q.y);
    }
  },
  blockers(s) {
    for (const b of s.ol) {
      if (b.eng && b.eng.blk > 0) { b.x += (b.eng.x - b.x) * 0.3; b.y += (b.eng.y + 5 - b.y) * 0.3; continue; }
      b.eng = null; let bd = 70, tg = null;
      for (const d of s.def) if (d.blk <= 0 && d.stun <= 0) { const dd = dist(b, d); if (dd < bd) { bd = dd; tg = d; } }
      if (!tg) continue;
      const L = bd || 1; b.x += (tg.x - b.x) / L * 1.0; b.y += (tg.y - b.y) / L * 1.0;
      if (bd < 7) { b.eng = tg; tg.blk = ri(36, 70); }
    }
  },
  defence(s, G) {
    const car = s.car, q = s.qb, fac = DEFSP[this.q(s)], pass = s.playType === 'pass', ly = yOf(s.los), land = s.pass;
    for (let i = 0; i < s.def.length; i++) {
      const d = s.def[i]; if (d.stun > 0) d.stun--;
      let sp = d.base * fac, tx = d.x, ty = d.y, go = true;
      if (d.blk > 0) { d.blk--; sp *= 0.25; }
      if (car && car !== q) {
        if (s.pt - s.carT >= d.delay) { tx = car.x + car.vx * 9; ty = car.y + car.vy * 9; } else go = false;
      } else if (pass) {
        if (land && Math.sqrt((d.x - land.x1) * (d.x - land.x1) + (d.y - land.y1) * (d.y - land.y1)) < 46) { tx = land.x1; ty = land.y1; sp *= 1.1; }
        else if (d.role === 'dl' || (d.role === 'lb' && s.blitz && i === 3)) { tx = q.x; ty = q.y; }
        else if (d.role === 'lb') { let t = null, bd = 34; for (const w of s.wr) { const dd = dist(d, w); if (dd < bd) { bd = dd; t = w; } } if (t) { tx = t.x; ty = t.y; } else { tx = d.hx; ty = ly - 22; sp *= 0.7; } }
        else { const w = s.wr[d.cov]; tx = w.x + w.vx * 6; ty = w.y + w.vy * 6 + 3; sp *= 0.97; }
      } else if (s.pt < 10 || s.pt - s.carT < d.delay) go = false;
      if (go) { const dx = tx - d.x, dy = ty - d.y, L = Math.sqrt(dx * dx + dy * dy) || 1; if (L > sp) { d.x += dx / L * sp; d.y += dy / L * sp; } else { d.x = tx; d.y = ty; } }
      d.x = clamp(d.x, XL - 6, XR + 6); d.y = clamp(d.y, 6, FH - 6);
    }
    for (let i = 0; i < s.def.length; i++) for (let j = i + 1; j < s.def.length; j++) {            // defenders do not stack on each other
      const a = s.def[i], b = s.def[j], dx = b.x - a.x, dy = b.y - a.y, L = Math.sqrt(dx * dx + dy * dy);
      if (L < 5) { const k = L ? 0.5 / L : 0; a.x -= dx * k; a.y -= dy * k; b.x += dx * k; b.y += dy * k; }
    }
  },
  draw(s, G, ctx) {
    const cam = camOf(s), ly = yOf(s.los);
    ctx.save(); ctx.beginPath(); ctx.rect(0, VIEW_TOP, W, VIEW_H); ctx.clip(); ctx.translate(0, VIEW_TOP - cam);
    ctx.fillStyle = PAL.grass; ctx.fillRect(0, 0, W, FH);
    for (let yd = 0; yd < 100; yd += 10) { ctx.fillStyle = (yd / 10) % 2 ? PAL.grass2 : PAL.grass; ctx.fillRect(XL, yOf(yd + 10), XR - XL, 10 * YD); }
    ctx.fillStyle = '#0e4a20'; ctx.fillRect(0, 0, XL, FH); ctx.fillRect(XR, 0, W - XR, FH);
    ctx.fillStyle = PAL.ezone; ctx.fillRect(XL, 0, XR - XL, GL); ctx.fillStyle = PAL.ezone2; ctx.fillRect(XL, OWN, XR - XL, FH - OWN);
    text(ctx, 'CPU', W / 2, 11, C.dim, 8, 'center'); text(ctx, 'NUTS', W / 2, OWN + 11, C.dim, 8, 'center');
    ctx.fillStyle = PAL.line;
    for (let yd = 0; yd <= 100; yd += 5) { const y = yOf(yd); ctx.fillRect(XL, y, XR - XL, yd % 10 === 0 ? 2 : 1); }
    for (let yd = 10; yd < 100; yd += 10) { const n = String(yd > 50 ? 100 - yd : yd), y = yOf(yd); text(ctx, n, 30, y + 4, '#8fd09b', 8, 'center'); text(ctx, n, W - 30, y + 4, '#8fd09b', 8, 'center'); }
    ctx.fillStyle = PAL.line; for (let yd = 1; yd < 100; yd++) if (yd % 5) { const y = yOf(yd); ctx.fillRect(XL + 1, y, 2, 1); ctx.fillRect(XR - 3, y, 2, 1); }
    // the goalposts
    ctx.fillStyle = C.gold; ctx.fillRect(W / 2 - 12, 4, 24, 2); ctx.fillRect(W / 2 - 12, 4, 1, 8); ctx.fillRect(W / 2 + 11, 4, 1, 8); ctx.fillRect(W / 2, 6, 1, 14);
    // line of scrimmage and the first-down line
    ctx.fillStyle = C.blue; ctx.fillRect(XL, ly - 1, XR - XL, 2);
    if (s.first < 100) { ctx.fillStyle = C.gold; const fy = yOf(s.first); for (let x = XL; x < XR; x += 6) ctx.fillRect(x, fy - 1, 3, 2); }
    const shown = s.mode === 'huddle' || s.mode === 'snap' || s.mode === 'play' || s.mode === 'result' || s.mode === 'kick';
    if (shown) {
      const ents = [].concat(s.def.map(d => [d, 0]), s.ol.map(o => [o, 1]), s.wr.map(w => [w, 1]), [[s.qb, 1], [s.rb, 1]]);
      ents.sort((a, b) => a[0].y - b[0].y);
      for (const [e, off] of ents) {
        const x = Math.round(e.x), y = Math.round(e.y);
        ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(x - 3, y + 3, 7, 2);
        ctx.fillStyle = off ? PAL.mine : PAL.theirs; ctx.fillRect(x - 3, y - 2, 6, 6); ctx.fillStyle = off ? PAL.myhelm : PAL.thelm; ctx.fillRect(x - 2, y - 4, 4, 3);
        if (e === s.car) { ctx.strokeStyle = C.white; ctx.strokeRect(x - 5.5, y - 6.5, 11, 12); }
      }
      if (s.playType === 'pass' && (s.mode === 'play' || s.mode === 'snap')) for (let i = 0; i < 3; i++) { const w = s.wr[i]; if (w === s.car || !s.qbHas && !s.pass) continue; text(ctx, String(i + 1), w.x, w.y - 14, i === s.tgt ? C.gold : C.dim, 8, 'center'); }
      if (s.mode === 'play' && s.playType === 'pass' && s.qbHas) { const w = s.wr[s.tgt]; ctx.strokeStyle = C.gold; ctx.strokeRect(Math.round(w.x) - 6.5, Math.round(w.y) - 7.5, 13, 14); }
      // the ball
      const b = s.ball; if (s.z > 1) { ctx.fillStyle = 'rgba(0,0,0,.4)'; ctx.fillRect(Math.round(b.x) - 2, Math.round(b.y), 4, 2); }
      ctx.fillStyle = PAL.ball; ctx.fillRect(Math.round(b.x) - 2, Math.round(b.y - s.z) - 1, 5, 3); ctx.fillStyle = C.white; ctx.fillRect(Math.round(b.x), Math.round(b.y - s.z) - 1, 1, 1);
    }
    drawFx(ctx, s.fx);
    ctx.restore();
    // the panel
    ctx.fillStyle = '#05030c'; ctx.fillRect(0, PANEL, W, H - PANEL); ctx.fillStyle = '#1a1038'; ctx.fillRect(0, PANEL, W, 1);
    const q = this.q(s), rem = QLEN - (s.clock - q * QLEN), togo = s.first >= 100 ? T('GOAL') : String(s.first - s.los);
    text(ctx, 'Q' + (q + 1) + ' ' + mmss(rem), 6, PANEL + 5, C.gold); text(ctx, T('YOU') + ' ' + s.mine + ' CPU ' + s.cpu, W - 6, PANEL + 5, C.ink, 8, 'right');
    text(ctx, T('DOWN') + ' ' + s.down + ' & ' + togo, 6, PANEL + 15, C.cyan); text(ctx, (s.los <= 50 ? T('OWN') + ' ' + s.los : T('OPP') + ' ' + (100 - s.los)), W - 6, PANEL + 15, C.lime, 8, 'right');
    if (s.mode === 'huddle') {
      for (let i = 0; i < 4; i++) {
        const x = 3 + i * 55, on = i === s.cur;
        ctx.fillStyle = on ? '#3a2a78' : '#120a26'; ctx.fillRect(x, PANEL + 26, 52, 28); ctx.strokeStyle = on ? C.gold : '#2a1a4a'; ctx.strokeRect(x + 0.5, PANEL + 26.5, 51, 27);
        text(ctx, T(s.menu[i]), x + 26, PANEL + 36, on ? C.gold : C.ink, 8, 'center');
      }
    } else if (s.mode === 'play' || s.mode === 'snap') {
      if (s.playType === 'run' || s.car) { text(ctx, T('BURST'), 6, PANEL + 28, C.dim); ctx.fillStyle = '#2a1a4a'; ctx.fillRect(84, PANEL + 28, 60, 6); ctx.fillStyle = s.burst > 12 ? C.lime : C.red; ctx.fillRect(84, PANEL + 28, Math.round(60 * s.burst / BURST_MAX), 6); }
      else text(ctx, T('TAP A RECEIVER'), W / 2, PANEL + 28, C.dim, 8, 'center');
    }
    G.hud(null, 'Q' + (q + 1));
    if (s.msgT && s.mode === 'play') text(ctx, T(s.msg), W / 2, 50, C.gold, 8, 'center');
    if (s.mode === 'huddle' && s.intro) text(ctx, T('PICK A PLAY'), W / 2, 40, C.ink, 8, 'center');
    if (s.mode === 'result' || s.mode === 'end') {
      ctx.fillStyle = 'rgba(5,3,12,.75)'; ctx.fillRect(0, 84, W, 50);
      text(ctx, T(s.bannerTxt), W / 2, 94, /TOUCH|^KICK GOOD|WIN|FIRST/.test(s.bannerTxt) ? C.gold : C.lime, 8, 'center');
      if (s.bannerSub || s.gain !== null) text(ctx, s.bannerSub || ((s.gain > 0 ? '+' : '') + s.gain + ' ' + T('YD')), W / 2, 110, C.ink, 8, 'center');
      if (s.mode === 'end') text(ctx, s.bonusTxt || '', W / 2, 122, C.lime, 8, 'center');
    }
    if (s.mode === 'cpu') { ctx.fillStyle = 'rgba(5,3,12,.8)'; ctx.fillRect(0, 84, W, 50); text(ctx, T('CPU BALL'), W / 2, 92, C.dim, 8, 'center'); text(ctx, T(s.cpuTxt), W / 2, 106, s.cpuTxt === 'CPU PUNTS' ? C.lime : C.pink, 8, 'center'); text(ctx, s.cpuSub, W / 2, 120, C.ink, 8, 'center'); }
  },
  thumb(ctx, t) {
    ctx.fillStyle = PAL.grass; ctx.fillRect(0, 0, 112, 84);
    for (let i = 0; i < 6; i++) { ctx.fillStyle = i % 2 ? PAL.grass2 : PAL.grass; ctx.fillRect(10, 10 + i * 12, 92, 12); }
    ctx.fillStyle = '#0e4a20'; ctx.fillRect(0, 0, 10, 84); ctx.fillRect(102, 0, 10, 84); ctx.fillStyle = PAL.ezone; ctx.fillRect(10, 0, 92, 10); ctx.fillStyle = PAL.line; for (let i = 0; i < 7; i++) ctx.fillRect(10, 10 + i * 12, 92, 1);
    ctx.fillStyle = PAL.theirs; for (let i = 0; i < 5; i++) ctx.fillRect(34 + i * 10, 30, 5, 5);
    ctx.fillStyle = PAL.mine; for (let i = 0; i < 5; i++) ctx.fillRect(34 + i * 10, 46, 5, 5);
    const k = (t % 80) / 80, x = 56 + (k < 0.5 ? k * 24 : (1 - k) * 24), y = 66 - k * 46; ctx.fillStyle = C.white; ctx.fillRect(Math.round(x) - 3, Math.round(y) - 3, 7, 7); ctx.fillStyle = PAL.mine; ctx.fillRect(Math.round(x) - 2, Math.round(y) - 2, 5, 5);
    ctx.fillStyle = C.gold; ctx.fillRect(Math.round(x) - 1, Math.round(y) - 4, 3, 2);
  }
};
return bowl;
});
