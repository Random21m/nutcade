/* NUTCADE audio: chiptune sfx + tiny sequencer for original music loops */
(function(){
'use strict';
let ctx = null, master = null, sfxBus = null, musBus = null, noiseBuf = null;
const prefs = () => window.NutPrefs || { sound: true, music: true };
function ensure() {
  if (ctx) { if (ctx.state === 'suspended') ctx.resume().catch(() => {}); return ctx; }
  try {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain(); master.gain.value = 0.9; master.connect(ctx.destination);
    sfxBus = ctx.createGain(); sfxBus.gain.value = 0.5; sfxBus.connect(master);
    musBus = ctx.createGain(); musBus.gain.value = 0.22; musBus.connect(master);
    noiseBuf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  } catch (e) { ctx = null; }
  return ctx;
}
// unlock on first gesture
['pointerdown', 'keydown', 'touchstart'].forEach(ev => window.addEventListener(ev, () => { ensure(); if (pendingTrack) { const t = pendingTrack; pendingTrack = null; music(t); } }, { passive: true }));

function tone(type, f0, f1, dur, vol = 0.5, when = 0, bus = sfxBus) {
  const c = ctx; const t = c.currentTime + when;
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(f0, t);
  if (f1 && f1 !== f0) o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
  g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(bus); o.start(t); o.stop(t + dur + 0.02);
}
function noise(dur, vol = 0.5, when = 0, cutoff = 4000, bus = sfxBus, sweepTo) {
  const c = ctx; const t = c.currentTime + when;
  const s = c.createBufferSource(); s.buffer = noiseBuf;
  const f = c.createBiquadFilter(); f.type = 'lowpass'; f.frequency.setValueAtTime(cutoff, t);
  if (sweepTo) f.frequency.exponentialRampToValueAtTime(sweepTo, t + dur);
  const g = c.createGain(); g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  s.connect(f).connect(g).connect(bus); s.start(t, Math.random() * 0.5); s.stop(t + dur + 0.02);
}
const SFX = {
  blip: () => tone('square', 660, 660, 0.05, 0.3),
  select: () => { tone('square', 523, 523, 0.05, 0.3); tone('square', 784, 784, 0.07, 0.3, 0.05); },
  coin: () => { tone('square', 988, 988, 0.07, 0.35); tone('square', 1319, 1319, 0.25, 0.35, 0.07); },
  send: () => tone('square', 1200, 200, 0.25, 0.3),
  err: () => { tone('square', 220, 220, 0.1, 0.35); tone('square', 150, 150, 0.22, 0.35, 0.1); },
  start: () => [523, 659, 784, 1047].forEach((f, i) => tone('square', f, f, 0.09, 0.3, i * 0.07)),
  levelup: () => [523, 659, 784, 1047, 784, 1047, 1319].forEach((f, i) => tone('square', f, f, 0.08, 0.28, i * 0.06)),
  shoot: () => tone('square', 1400, 300, 0.09, 0.22),
  laser: () => tone('sawtooth', 900, 120, 0.12, 0.2),
  boom: () => { noise(0.45, 0.6, 0, 3000, sfxBus, 120); tone('square', 120, 40, 0.3, 0.25); },
  pop: () => { noise(0.12, 0.4, 0, 6000, sfxBus, 800); tone('square', 600, 200, 0.08, 0.18); },
  hit: () => tone('square', 440, 880, 0.04, 0.25),
  brick: () => tone('square', 880 + Math.random() * 300, 880, 0.05, 0.22),
  wall: () => tone('triangle', 300, 300, 0.04, 0.35),
  eat: () => tone('square', 700, 900, 0.035, 0.15),
  power: () => { for (let i = 0; i < 6; i++) tone('square', 300 + i * 120, 300 + i * 120, 0.05, 0.25, i * 0.04); },
  gulp: () => tone('square', 200, 1200, 0.18, 0.3),
  hop: () => tone('square', 400, 700, 0.06, 0.22),
  splash: () => noise(0.4, 0.45, 0, 2000, sfxBus, 300),
  thrust: () => noise(0.08, 0.18, 0, 900),
  launch: () => tone('triangle', 200, 900, 0.18, 0.35),
  die: () => { for (let i = 0; i < 8; i++) tone('square', 800 - i * 80, 760 - i * 80, 0.06, 0.25, i * 0.06); noise(0.5, 0.3, 0.45, 2000, sfxBus, 100); },
  over: () => [392, 349, 330, 262].forEach((f, i) => tone('square', f, f * 0.98, 0.22, 0.3, i * 0.22)),
  tick: () => tone('square', 1800, 1800, 0.02, 0.12)
};
function sfx(name) {
  if (!prefs().sound) return;
  if (!ensure()) return;
  try { (SFX[name] || SFX.blip)(); } catch (e) {}
}

/* ---- music ---- */
const NOTE = { C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11 };
const freq = n => { const m = n.match(/^([A-G]#?)(\d)$/); if (!m) return 0; return 440 * Math.pow(2, (NOTE[m[1]] + (m[2] - 4) * 12 - 9) / 12); };
const seq = s => s.replace(/\|/g, ' ').trim().split(/\s+/);
// Original loops written for NUTCADE.
const TRACKS = {
  title: { bpm: 132, lead: seq('C5 . E5 G5 . E5 C5 . | D5 . F5 A5 . F5 D5 . | E5 . G5 B5 . G5 E5 . | F5 E5 D5 C5 . G4 . . | C5 . E5 G5 . E5 C5 . | D5 . F5 A5 . C6 A5 . | G5 . E5 . F5 . D5 . | C5 . G4 . C5 . . .'),
    bass: seq('C3 . C3 . G2 . G2 . | D3 . D3 . A2 . A2 . | E3 . E3 . B2 . B2 . | F3 . G3 . C3 . G2 . | C3 . C3 . G2 . G2 . | D3 . D3 . F3 . F3 . | G2 . G2 . G2 . B2 . | C3 . G2 . C3 . . .'), hat: 2 },
  action: { bpm: 150, lead: seq('A4 C5 E5 A5 G5 E5 C5 E5 | F4 A4 C5 F5 E5 C5 A4 C5 | G4 B4 D5 G5 F5 D5 B4 D5 | E5 . E5 D5 C5 B4 A4 . | A4 C5 E5 A5 G5 E5 C5 E5 | F4 A4 C5 F5 A5 F5 C5 A4 | G4 B4 D5 G5 B5 G5 D5 B4 | E5 G#4 B4 E5 . . . .'),
    bass: seq('A2 A2 A3 A2 A2 A2 A3 A2 | F2 F2 F3 F2 F2 F2 F3 F2 | G2 G2 G3 G2 G2 G2 G3 G2 | E2 E2 E3 E2 E2 E2 E3 E2 | A2 A2 A3 A2 A2 A2 A3 A2 | F2 F2 F3 F2 F2 F2 F3 F2 | G2 G2 G3 G2 G2 G2 G3 G2 | E2 E2 E3 E2 E3 E2 E3 E2'), hat: 1 },
  bounce: { bpm: 140, lead: seq('G4 . B4 D5 . B4 G5 . | E5 . C5 . D5 . B4 . | A4 . C5 E5 . C5 A5 . | F#5 . D5 . E5 . C5 . | G4 . B4 D5 . G5 F#5 G5 | A5 . G5 . E5 . D5 . | C5 . E5 . D5 . F#4 . | G4 . . . G5 . . .'),
    bass: seq('G2 . D3 . G2 . D3 . | C3 . G2 . G2 . D3 . | A2 . E3 . A2 . E3 . | D3 . A2 . D3 . A2 . | G2 . D3 . G2 . D3 . | C3 . G3 . C3 . G3 . | A2 . D3 . D3 . F#2 . | G2 . D3 . G2 . . .'), hat: 2 }
};
let cur = null, timer = null, step = 0, nextT = 0, pendingTrack = null;
function music(name) {
  if (cur === name && timer) return;
  stopMusic();
  if (!name || !prefs().music || !prefs().sound) return;
  if (!ctx || ctx.state !== 'running') { pendingTrack = name; ensure(); if (!ctx || ctx.state !== 'running') return; pendingTrack = null; }
  const tr = TRACKS[name]; if (!tr) return;
  cur = name; step = 0; nextT = ctx.currentTime + 0.05;
  const stepDur = 60 / tr.bpm / 2;
  const sched = () => {
    while (nextT < ctx.currentTime + 0.25) {
      const when = nextT - ctx.currentTime;
      const l = tr.lead[step % tr.lead.length], b = tr.bass[step % tr.bass.length];
      if (l !== '.') tone('square', freq(l), freq(l), stepDur * 0.9, 0.35, when, musBus);
      if (b !== '.') tone('triangle', freq(b), freq(b), stepDur * 0.95, 0.9, when, musBus);
      if (step % tr.hat === 0) noise(0.03, step % 8 === 4 ? 0.35 : 0.15, when, 8000, musBus);
      if (step % 8 === 4 && tr.hat === 1) noise(0.08, 0.3, when, 1500, musBus);
      step++; nextT += stepDur;
    }
  };
  sched(); timer = setInterval(sched, 60);
}
function stopMusic() { if (timer) clearInterval(timer); timer = null; cur = null; pendingTrack = null; }
document.addEventListener('visibilitychange', () => { if (!ctx) return; if (document.hidden) ctx.suspend().catch(() => {}); else ctx.resume().catch(() => {}); });

window.NutAudio = { sfx, music, stopMusic, get track() { return cur; } };
})();
