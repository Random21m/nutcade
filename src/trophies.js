/* NUTCADE trophies and shareable score cards */
(() => {
'use strict';
const N = () => window.Nutcade;
const store = window.NutStore;
const SITE = 'random21m.github.io/nutcade';

const ICON = {
  coin: ['..####..', '.##..##.', '##.##.##', '##.##.##', '##.##.##', '##.##.##', '.##..##.', '..####..'],
  up: ['...##...', '..####..', '.######.', '########', '...##...', '...##...', '...##...', '...##...'],
  bolt: ['....###.', '...###..', '..###...', '.######.', '...###..', '..###...', '.###....', '.##.....'],
  chain: ['.##.....', '#..#....', '#..#....', '.####...', '...####.', '....#..#', '....#..#', '.....##.'],
  note: ['######..', '#....##.', '#.##..#.', '#.....#.', '#.###.#.', '#.....#.', '#.##..#.', '#######.'],
  mint: ['...##...', '.######.', '########', '.#.##.#.', '.#.##.#.', '.#.##.#.', '########', '########'],
  floppy: ['#######.', '#.#..#.#', '#.#..#.#', '#.####.#', '#......#', '#.####.#', '#.#..#.#', '########'],
  lock: ['..####..', '.#....#.', '.#....#.', '########', '###..###', '###..###', '####.###', '########'],
  at: ['..####..', '.#....#.', '#..###.#', '#.#..#.#', '#.#..#.#', '#..####.', '.#......', '..#####.'],
  stack: ['.######.', '########', '.######.', '########', '.######.', '########', '.######.', '########'],
  ship: ['...##...', '...##...', '..####..', '.##..##.', '########', '##.##.##', '#..##..#', '........'],
  nut: ['..####..', '.######.', '########', '#.#.#.##', '.######.', '.######.', '..####..', '...##...'],
  brick: ['########', '#..#..##', '########', '##..#..#', '########', '#..#..##', '########', '........'],
  rock: ['..###...', '.#...##.', '#......#', '#..#...#', '.#.....#', '#......#', '.#..##..', '..##....'],
  frog: ['.##..##.', '#.#..#.#', '.######.', '########', '#.####.#', '.######.', '.#....#.', '##....##'],
  shield: ['########', '#......#', '#.####.#', '#.####.#', '.#.##.#.', '.#....#.', '..#..#..', '...##...'],
  ball: ['..####..', '.#..####', '#..#####', '#.######', '########', '########', '.######.', '..####..'],
  snake: ['......##', '.....#.#', '.....##.', '..####..', '.#......', '.#####..', '.....#..', '.####...'],
  stick: ['..###...', '..###...', '...#....', '...#....', '...#....', '.#####..', '#######.', '#######.'],
  star: ['...##...', '...##...', '########', '.######.', '..####..', '.##..##.', '##....##', '#......#'],
  five: ['#######.', '#.......', '######..', '......#.', '......#.', '#.....#.', '.#####..', '........'],
  cup: ['########', '#.####.#', '#.####.#', '.######.', '..####..', '...##...', '..####..', '.######.'],
  tape: ['########', '#......#', '#.#..#.#', '#......#', '########', '#.####.#', '#.#..#.#', '########'],
  boss: ['#......#', '##....##', '########', '#.####.#', '########', '##.##.##', '#.#..#.#', '#......#'],
  till: ['..####..', '..#..#..', '########', '#.#.#..#', '########', '#......#', '#.####.#', '########'],
  pig: ['.#....#.', '########', '#.######', '########', '##.#####', '.######.', '.#.##.#.', '.#.##.#.'],
  vs: ['#.....#.', '#.....#.', '.#...#..', '.#...#..', '..#.#.##', '..#.##..', '...#..##', '......##']
};

const done = t => ['done', 'claimed', 'reclaimed'].includes(t.status);
const DEFS = [
  { id: 'first-in', name: 'FIRST COIN', how: 'Receive your first sats.', icon: 'coin', col: '#ffcf3a', w: s => s.txs.some(t => t.type === 'in' && done(t) && t.amount > 0) },
  { id: 'first-out', name: 'PLAYER 2 JOINS', how: 'Send sats to someone.', icon: 'up', col: '#ff3d8b', w: s => s.txs.some(t => t.type === 'out' && done(t)) },
  { id: 'lightning', name: 'LIGHTNING ROD', how: 'Pay or get paid over Lightning.', icon: 'bolt', col: '#ffcf3a', w: s => s.txs.some(t => t.method === 'ln' && done(t)) },
  { id: 'onchain', name: 'CHAIN LINK', how: 'Move sats on-chain.', icon: 'chain', col: '#ff9a1f', w: s => s.txs.some(t => t.method === 'onchain' && done(t) && t.amount > 0) },
  { id: 'notes', name: 'NOTE TAKER', how: 'Write notes on 10 transactions.', icon: 'note', col: '#2de2ff', w: s => s.txs.filter(t => t.note).length >= 10 },
  { id: 'mints', name: 'MINT COLLECTOR', how: 'Add 3 mints.', icon: 'mint', col: '#9dff3a', w: s => s.mints.length >= 3 },
  { id: 'backup', name: 'SAVE GAME', how: 'Back up your 12 words.', icon: 'floppy', col: '#2de2ff', w: s => !!(s.seed && s.seed.backedUp) },
  { id: 'pin', name: 'VAULT DOOR', how: 'Lock your wallet with a PIN.', icon: 'lock', col: '#c13dff', w: () => !!(N().vault && N().vault.on) },
  { id: 'lnaddr', name: 'CALLING CARD', how: 'Turn on your own Lightning address.', icon: 'at', col: '#ff3d8b', w: s => !!s.prefs.npc },
  { id: 'regular', name: 'REGULAR', how: 'Make 21 transactions.', icon: 'stack', col: '#9dff3a', w: s => s.txs.filter(done).length >= 21 },
  { id: 'tape', name: 'TAPE LOADER', how: 'Send or receive a code as sound.', icon: 'tape', col: '#2de2ff', w: s => !!s.prefs.ctUsed },
  { id: 'boss', name: 'BOSS SLAYER', how: 'Collect every share of a split bill.', icon: 'boss', col: '#ff3d8b', w: s => (s.requests || []).some(r => r.split && r.paid.length >= r.split.people - 1) },
  { id: 'till', name: 'SHOPKEEPER', how: 'Make a sale in cashier mode.', icon: 'till', col: '#ffcf3a', w: s => s.txs.some(t => t.cashier && t.status === 'done') },
  { id: 'piggy', name: 'PIGGY SAVER', how: 'Save 1,000 sats in round-ups.', icon: 'pig', col: '#ff3d8b', w: s => !!(s.piggy && s.piggy.saved >= 1000) },
  { id: 'rival', name: 'RIVAL', how: 'Win a high-score challenge.', icon: 'vs', col: '#9dff3a', w: s => (s.challenges || []).some(c => c.dir === 'in' && c.best != null && c.best > c.score) },
  { id: 'g-swarm', game: 'swarm', name: 'ACE PILOT', how: 'Reach wave 3 in Star Swarm.', icon: 'ship', col: '#2de2ff', g: s => s.wave >= 3 },
  { id: 'g-maze', game: 'maze', name: 'NUT CRACKER', how: 'Reach level 2 in Nut Maze.', icon: 'nut', col: '#ffcf3a', g: s => s.level >= 2 },
  { id: 'g-brick', game: 'brick', name: 'WRECKING BALL', how: 'Reach level 2 in Brick Blitz.', icon: 'brick', col: '#ff3d8b', g: s => s.level >= 2 },
  { id: 'g-rocks', game: 'rocks', name: 'ROCK BREAKER', how: 'Reach wave 3 in Void Rocks.', icon: 'rock', col: '#c13dff', g: s => s.wave >= 3 },
  { id: 'g-hop', game: 'hop', name: 'SAFE CROSSING', how: 'Reach level 2 in Hop Lanes.', icon: 'frog', col: '#9dff3a', g: s => s.level >= 2 },
  { id: 'g-shield', game: 'shield', name: 'CITY SAVER', how: 'Reach wave 3 in Sky Shield.', icon: 'shield', col: '#2de2ff', g: s => s.wave >= 3 },
  { id: 'g-nibble', game: 'nibble', name: 'LONG BOI', how: 'Grow to length 30 in Nibble.', icon: 'snake', col: '#9dff3a', g: s => s.body && s.body.length >= 30 },
  { id: 'g-flipper', game: 'flipper', name: 'SILVER BALL', how: 'Light all three N-U-T lanes in Nut Flipper.', icon: 'ball', col: '#ffcf3a', g: s => s.mult >= 2 },
  { id: 'tour', name: 'GRAND TOUR', how: 'Play all 8 cabinets.', icon: 'stick', col: '#ff9a1f', p: p => Object.keys(p.by || {}).length >= 8 },
  { id: 'rat', name: 'ARCADE RAT', how: 'Play 50 games.', icon: 'stick', col: '#ff3d8b', p: p => (p.n || 0) >= 50 },
  { id: 'top5', name: 'TOP FIVE', how: 'Put your initials on a high-score table.', icon: 'star', col: '#ffcf3a', x: 'hiscore' },
  { id: 'big', name: 'FIVE DIGITS', how: 'Score 10,000 in any game.', icon: 'five', col: '#ff3d8b', x: 'big' }
];

let got = store.get('trophies', null);
const fresh = got === null;
if (!got) got = {};
const save = () => store.set('trophies', got);
const plays = () => store.get('plays', { n: 0, by: {} });

/* unlock queue: one toast at a time */
const queue = []; let showing = false;
function announce() {
  if (showing || !queue.length) return;
  showing = true;
  const d = queue.shift();
  const n = N();
  if (n) { n.sfx('levelup'); n.toast(`TROPHY! ${d.name}: ${d.how}`, 'gold'); }
  setTimeout(() => { showing = false; announce(); }, 2600);
}
function unlock(d, quiet) {
  if (got[d.id]) return false;
  got[d.id] = Date.now(); save();
  if (!quiet) { queue.push(d); announce(); }
  return true;
}

/* wallet trophies: checked whenever the main app renders */
let first = fresh;
function checkWallet() {
  const n = N(); if (!n || !n.S) return;
  const S = n.S; if (!S.seed || !S.seed.backedUp) return;
  const newly = [];
  for (const d of DEFS) if (d.w && !got[d.id]) { try { if (d.w(S)) newly.push(d); } catch (e) {} }
  if (!newly.length) { first = false; return; }
  if (first && newly.length > 1) {
    // Existing wallet seeing trophies for the first time: one summary, no toast flood.
    newly.forEach(d => unlock(d, true));
    n.toast(`You've earned ${newly.length} trophies. See them in the Arcade.`, 'gold');
  } else newly.forEach(d => unlock(d));
  first = false;
}

/* arcade hooks, called from games.js */
function played(id) {
  const p = plays(); p.n = (p.n || 0) + 1; p.by = p.by || {}; p.by[id] = (p.by[id] || 0) + 1; store.set('plays', p);
  for (const d of DEFS) if (d.p && !got[d.id] && d.p(p)) unlock(d);
}
function progress(id, st, score) {
  for (const d of DEFS) if (d.game === id && !got[d.id] && st && d.g(st)) unlock(d);
  if (score >= 10000) unlock(DEFS.find(d => d.x === 'big'));
}
function gameOver(id, score, st, high) {
  progress(id, st, score);
  if (high) unlock(DEFS.find(d => d.x === 'hiscore'));
}

/* ---------- pixel icons ---------- */
function iconSVG(d, on, size = 40) {
  const g = ICON[d.icon] || ICON.cup; const c = on ? d.col : '#3a3358';
  let r = '';
  g.forEach((row, y) => [...row].forEach((b, x) => { if (b === '#') r += `<rect x="${x}" y="${y}" width="1" height="1"/>`; }));
  return `<svg viewBox="-1 -1 10 10" width="${size}" height="${size}" shape-rendering="crispEdges" aria-hidden="true"><g fill="#000" transform="translate(.5 .5)">${r}</g><g fill="${c}">${r}</g></svg>`;
}
function drawIcon(ctx, d, x, y, px, on = true) {
  const g = ICON[d.icon] || ICON.cup;
  ctx.fillStyle = '#000'; g.forEach((row, yy) => [...row].forEach((b, xx) => { if (b === '#') ctx.fillRect(x + (xx + .5) * px, y + (yy + .5) * px, px, px); }));
  ctx.fillStyle = on ? d.col : '#3a3358'; g.forEach((row, yy) => [...row].forEach((b, xx) => { if (b === '#') ctx.fillRect(x + xx * px, y + yy * px, px, px); }));
}

/* ---------- trophy room (Arcade tab) ---------- */
function mount(el) {
  if (!el) return;
  const n = N(); const esc = n.esc;
  const have = DEFS.filter(d => got[d.id]).length;
  const p = plays();
  const box = document.createElement('div');
  box.className = 'panel'; box.id = 'trophyRoom';
  box.innerHTML = `<div class="row between"><span class="h2">Trophies</span><span class="tiny" style="color:var(--gold)">${have}/${DEFS.length}</span></div>
    <div class="meter" aria-hidden="true"><i style="width:${Math.round(have / DEFS.length * 100)}%"></i></div>
    <div class="trophies">${DEFS.map(d => `<button class="trophy ${got[d.id] ? 'on' : ''}" data-trophy="${d.id}" aria-label="${esc(d.name)}${got[d.id] ? ', earned' : ', locked'}">${iconSVG(d, !!got[d.id])}<span>${esc(d.name)}</span></button>`).join('')}</div>
    <div class="tiny muted"><span>${p.n ? `${n.fmt(p.n)} game${p.n === 1 ? '' : 's'} played on this device.` : 'Earn trophies by using your wallet and playing the cabinets.'}</span> <span>Trophies stay on this device and never leave it unless you share a card.</span></div>`;
  el.appendChild(box);
  box.querySelectorAll('[data-trophy]').forEach(b => b.onclick = () => openTrophy(b.dataset.trophy));
}
function openTrophy(id) {
  const n = N(); const d = DEFS.find(x => x.id === id); if (!d) return;
  const on = !!got[id];
  n.sfx('select');
  n.openSheet(on ? 'Trophy earned' : 'Locked trophy', `<div style="display:grid;justify-items:center;gap:10px;text-align:center">
    ${iconSVG(d, on, 96)}
    <div style="font-family:var(--f-display);font-size:14px;color:${on ? d.col : 'var(--dim)'}">${n.esc(d.name)}</div>
    <p style="margin:0">${n.esc(d.how)}</p>
    ${on ? `<div class="tiny muted">Earned ${new Date(got[id]).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</div>` : '<div class="tiny muted">Not earned yet.</div>'}</div>
    ${on ? `<button class="btn solid gold block" id="trophyShare">Share trophy card</button>` : ''}<button class="btn block" data-act="close">Close</button>`, body => {
    const b = body.querySelector('#trophyShare');
    if (b) b.onclick = () => openCard({ kind: 'trophy', d, at: got[id] });
    return null;
  });
}

/* ---------- share cards (1200 x 630, the size X and most sites preview) ---------- */
const CW = 1200, CH = 630;
let logoImg = null;
function loadLogo() {
  if (logoImg) return logoImg;
  logoImg = new Promise(res => {
    const img = new Image();
    img.onload = () => res(img); img.onerror = () => res(null);
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(N().logoSVG('NUTCADE', false));
  });
  return logoImg;
}
const pad6 = v => String(Math.max(0, Math.floor(v))).padStart(6, '0');
function txt(ctx, s, x, y, size, col, align = 'left', font = '"Press Start 2P"') {
  ctx.font = `${size}px ${font}, monospace`; ctx.textAlign = align; ctx.textBaseline = 'top';
  ctx.fillStyle = '#000'; ctx.fillText(s, x + Math.max(2, size / 10), y + Math.max(2, size / 10));
  ctx.fillStyle = col; ctx.fillText(s, x, y);
}
function fitText(ctx, s, maxW, size, font = '"Press Start 2P"') {
  let z = size; ctx.font = `${z}px ${font}, monospace`;
  while (z > 12 && ctx.measureText(s).width > maxW) { z -= 2; ctx.font = `${z}px ${font}, monospace`; }
  return z;
}
async function renderCard(o) {
  try { await Promise.all([document.fonts.load('40px "Press Start 2P"'), document.fonts.load('40px "VT323"')]); } catch (e) {}
  const logo = await loadLogo();
  const c = document.createElement('canvas'); c.width = CW; c.height = CH;
  const ctx = c.getContext('2d'); ctx.imageSmoothingEnabled = false;
  // backdrop: deep violet with a perspective grid and stars
  const bg = ctx.createLinearGradient(0, 0, 0, CH); bg.addColorStop(0, '#0a0717'); bg.addColorStop(.62, '#1a0b3a'); bg.addColorStop(1, '#2a0b3a');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, CW, CH);
  ctx.strokeStyle = 'rgba(193,61,255,.35)'; ctx.lineWidth = 2;
  const hz = 430;
  for (let i = -12; i <= 12; i++) { ctx.beginPath(); ctx.moveTo(CW / 2 + i * 30, hz); ctx.lineTo(CW / 2 + i * 190, CH); ctx.stroke(); }
  for (let k = 0; k < 7; k++) { const y = hz + (CH - hz) * Math.pow(k / 6, 1.8); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CW, y); ctx.stroke(); }
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 70; i++) { ctx.fillStyle = rnd() > .8 ? '#2de2ff' : 'rgba(255,255,255,.55)'; const s = rnd() > .9 ? 4 : 2; ctx.fillRect(Math.floor(rnd() * CW), Math.floor(rnd() * hz), s, s); }
  // frame
  ctx.fillStyle = '#ff3d8b'; ctx.fillRect(0, 0, CW, 8); ctx.fillRect(0, CH - 8, CW, 8); ctx.fillRect(0, 0, 8, CH); ctx.fillRect(CW - 8, 0, 8, CH);
  ctx.fillStyle = '#2de2ff'; ctx.fillRect(14, 14, CW - 28, 4); ctx.fillRect(14, CH - 18, CW - 28, 4); ctx.fillRect(14, 14, 4, CH - 28); ctx.fillRect(CW - 18, 14, 4, CH - 28);
  // left: game screen or big trophy
  const bx = 60, by = 70, bw = 480, bh = 360;
  ctx.fillStyle = '#05030c'; ctx.fillRect(bx - 10, by - 10, bw + 20, bh + 20);
  ctx.fillStyle = '#7a3dff'; ctx.fillRect(bx - 14, by - 14, bw + 28, 6); ctx.fillRect(bx - 14, by + bh + 8, bw + 28, 6); ctx.fillRect(bx - 14, by - 14, 6, bh + 28); ctx.fillRect(bx + bw + 8, by - 14, 6, bh + 28);
  if (o.kind === 'score' && o.game && o.game.thumb) {
    const t = document.createElement('canvas'); t.width = 112; t.height = 84; const tx = t.getContext('2d'); tx.imageSmoothingEnabled = false;
    try { o.game.thumb(tx, 40); } catch (e) {}
    ctx.drawImage(t, 0, 0, 112, 84, bx + 16, by + 18, 448, 324);
  } else {
    ctx.fillStyle = '#0a0717'; ctx.fillRect(bx, by, bw, bh);
    const rays = ctx.createRadialGradient(bx + bw / 2, by + bh / 2, 10, bx + bw / 2, by + bh / 2, 240); rays.addColorStop(0, 'rgba(255,207,58,.35)'); rays.addColorStop(1, 'rgba(255,207,58,0)');
    ctx.fillStyle = rays; ctx.fillRect(bx, by, bw, bh);
    drawIcon(ctx, o.d, bx + bw / 2 - 128, by + bh / 2 - 128, 32, true);
  }
  // scanlines over the screen
  ctx.fillStyle = 'rgba(0,0,0,.22)'; for (let y = by; y < by + bh; y += 4) ctx.fillRect(bx, y, bw, 2);
  // right column
  const rx = 600, rw = CW - rx - 60;
  if (logo) { const lw = rw, lh = lw * logo.height / logo.width; ctx.imageSmoothingEnabled = true; ctx.drawImage(logo, rx, 48, lw, Math.min(lh, 190)); ctx.imageSmoothingEnabled = false; }
  if (o.kind === 'score') {
    txt(ctx, 'NEW HIGH SCORE', rx, 262, 24, '#ffcf3a');
    const nm = o.game.name; txt(ctx, nm, rx, 304, fitText(ctx, nm, rw, 28), '#2de2ff');
    const sc = pad6(o.score); txt(ctx, sc, rx, 352, fitText(ctx, sc, rw, 64), '#ffffff');
    txt(ctx, `BY ${o.initials || 'AAA'}`, rx, 436, 22, '#ff3d8b');
  } else {
    txt(ctx, 'TROPHY UNLOCKED', rx, 262, 24, '#ffcf3a');
    const nm = o.d.name; txt(ctx, nm, rx, 306, fitText(ctx, nm, rw, 40), o.d.col);
    ctx.font = '34px "VT323", monospace'; ctx.textBaseline = 'top'; ctx.textAlign = 'left';
    const words = o.d.how.split(' '); let line = '', y = 368;
    for (const w of words) { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > rw && line) { txt(ctx, line, rx, y, 34, '#ffffff', 'left', '"VT323"'); line = w; y += 36; } else line = t; }
    if (line) txt(ctx, line, rx, y, 34, '#ffffff', 'left', '"VT323"');
  }
  const when = new Date(o.at || Date.now()).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase();
  txt(ctx, when, rx, 486, 16, '#9a8fc4');
  if (o.loaded && o.loaded.url) {
    // a loaded card: a QR over the game screen that pays out to whoever scans it first
    const L = window.CashuLib; let qr = null; try { qr = L.qrcode(0, 'M'); qr.addData(o.loaded.url); qr.make(); } catch (e) { qr = null; }
    if (qr) {
      const m = qr.getModuleCount(), cell = Math.floor(260 / (m + 4)), size = cell * (m + 4), qx = bx + bw - size - 14, qy = by + bh - size - 14;
      ctx.fillStyle = '#ffcf3a'; ctx.fillRect(qx - 8, qy - 8, size + 16, size + 16);
      ctx.fillStyle = '#ffffff'; ctx.fillRect(qx, qy, size, size); ctx.fillStyle = '#0a0717';
      for (let r = 0; r < m; r++) for (let k = 0; k < m; k++) if (qr.isDark(r, k)) ctx.fillRect(qx + (k + 2) * cell, qy + (r + 2) * cell, cell, cell);
      ctx.fillStyle = 'rgba(5,3,12,.88)'; ctx.fillRect(bx, by, bw, 66);
      txt(ctx, 'INSERT COIN: SCAN TO WIN', bx + bw / 2, by + 8, 18, '#ffcf3a', 'center');
      txt(ctx, `${N().fmt(o.loaded.amount)} SAT · FIRST SCAN TAKES IT`, bx + bw / 2, by + 38, 16, '#9dff3a', 'center');
    }
  }
  txt(ctx, 'A BITCOIN WALLET WITH AN ARCADE INSIDE', CW / 2, 548, 18, '#ffffff', 'center');
  txt(ctx, SITE, CW / 2, 580, 16, '#9dff3a', 'center');
  return new Promise(res => c.toBlob(b => res({ blob: b, url: b ? URL.createObjectURL(b) : c.toDataURL('image/png') }), 'image/png'));
}

function shareText(o) {
  if (o.loaded) return `${o.kind === 'score' ? `I scored ${N().fmt(o.score)} on ${o.game.name}` : `Trophy unlocked: ${o.d.name}`} in NUTCADE, and this card holds ${N().fmt(o.loaded.amount)} sats. First to scan it wins them.`;
  return o.kind === 'score'
    ? `I scored ${N().fmt(o.score)} on ${o.game.name} in NUTCADE, a Bitcoin wallet with an arcade inside.`
    : `Trophy unlocked in NUTCADE: ${o.d.name}.`;
}
async function openCard(o) {
  const n = N();
  n.openSheet(o.kind === 'score' ? 'Score card' : 'Trophy card', `<div id="cardBox">${'<div class="row" style="justify-content:center;padding:24px 0"><span class="spinner">PRINTING CARD</span></div>'}</div>`);
  const r = await renderCard(o);
  const box = document.getElementById('cardBox'); if (!box) return;
  const name = o.kind === 'score' ? `nutcade-${o.game.id}-${o.score}.png` : `nutcade-trophy-${o.d.id}.png`;
  const file = r.blob ? new File([r.blob], name, { type: 'image/png' }) : null;
  const canShare = !!(file && navigator.canShare && navigator.canShare({ files: [file] }));
  box.innerHTML = `<img src="${r.url}" alt="${n.esc(shareText(o))}" class="share-card">
    ${o.loaded ? `<div class="notice cyan">Loaded with ${n.esc(n.fmt(o.loaded.amount))} SAT. Whoever scans it first wins them. If nobody does by ${n.esc(new Date(o.loaded.until).toLocaleDateString())}, they come back to you.</div>`
      : `<div class="load-card"><label class="label" for="loadAmt">Put sats in it (optional)</label><div class="row" style="gap:8px"><input id="loadAmt" class="inp" inputmode="numeric" placeholder="210" style="flex:1"><button class="btn sm gold" id="cardLoad">Load card</button></div><div class="tiny muted">Adds a QR code to the card. The first person to scan it wins the sats; unclaimed after a week, they come back to you.</div><div id="sheetErr"></div></div>`}
    <div class="tiny muted">The card shows the game and score only, nothing about your wallet.</div>
    ${canShare ? '<button class="btn solid gold block" id="cardShare">Share</button>' : ''}
    <button class="btn block ${canShare ? '' : 'solid gold'}" id="cardSave">Save image</button>
    <button class="btn block" data-act="copy" data-text="${n.esc(shareText(o) + ' https://' + SITE)}">Copy text and link</button>`;
  const s = document.getElementById('cardShare');
  if (s) s.onclick = async () => { try { await navigator.share({ files: [file], text: shareText(o) + ' https://' + SITE }); } catch (e) { if (e.name !== 'AbortError') n.toast("Couldn't open sharing. Save the image instead.", 'gold'); } };
  const lb = document.getElementById('cardLoad');
  if (lb) lb.onclick = async () => {
    const amt = Math.floor(Number((document.getElementById('loadAmt').value || '').replace(/[^0-9]/g, '')));
    const err = document.getElementById('sheetErr');
    if (!(amt > 0)) { err.innerHTML = '<div class="notice red">Enter how many sats to put in the card.</div>'; return; }
    lb.disabled = true; lb.textContent = 'LOADING…';
    try { const ld = await n.loadCard(amt); n.sfx('coin'); openCard(Object.assign({}, o, { loaded: ld })); }
    catch (e) { lb.disabled = false; lb.textContent = 'Load card'; err.innerHTML = `<div class="notice red">${n.esc(e.message || String(e))}</div>`; }
  };
  document.getElementById('cardSave').onclick = () => {
    try { const a = document.createElement('a'); a.href = r.url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); n.toast('Card saved', 'lime'); }
    catch (e) { n.toast('Press and hold the image to save it.', 'gold'); }
  };
}

window.Trophies = { DEFS, checkWallet, played, progress, gameOver, mount, openTrophy, openCard, renderCard, got: () => Object.assign({}, got), iconSVG };
})();
