/* NUTCADE chiptune transfer: send a code (ecash token, payment request, invoice...) as sound, like loading a game from tape.
   Each 20 ms symbol plays two tones at once, one from a low bank and one from a high bank, so it carries one byte.
   Data goes in frames of up to 48 bytes, each with a preamble and a CRC-16; the whole message ends with a CRC-32.
   The sender loops until stopped, and the receiver keeps every good frame it hears, so a frame missed on one pass
   is picked up on the next. The decoder runs Goertzel filters on the microphone signal. */
(() => {
'use strict';
const SYM = 0.02, WIN = 0.015, GAP_SYMS = 2, FRAME = 48;
const LOW = Array.from({ length: 16 }, (_, k) => 1500 + 200 * k);    // 1500..4500 Hz
const HIGH = Array.from({ length: 16 }, (_, k) => 5000 + 200 * k);   // 5000..8000 Hz
const PRE = [[0, 15], [15, 0], [0, 15], [15, 0], [0, 15], [15, 0], [5, 10], [10, 5]];
const MAGIC = 0x4e;   // 'N'

const crcTable = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = b => { let c = 0xFFFFFFFF; for (const x of b) c = crcTable[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
const crc16 = b => { let c = 0xFFFF; for (const x of b) { c ^= x << 8; for (let i = 0; i < 8; i++) c = c & 0x8000 ? ((c << 1) ^ 0x1021) & 0xFFFF : (c << 1) & 0xFFFF; } return c; };
const bytesOf = d => d instanceof Uint8Array ? d : new TextEncoder().encode(String(d));

function frames(data) {
  const body = bytesOf(data);
  const msg = new Uint8Array(body.length + 4); msg.set(body); new DataView(msg.buffer).setUint32(body.length, crc32(body));
  const total = Math.ceil(msg.length / FRAME); if (total > 250) throw new Error('That is too long to send as sound.');
  const out = [];
  for (let i = 0; i < total; i++) {
    const part = msg.subarray(i * FRAME, (i + 1) * FRAME);
    const f = new Uint8Array(4 + part.length + 2);
    f[0] = MAGIC; f[1] = i; f[2] = total; f[3] = part.length; f.set(part, 4);
    const c = crc16(f.subarray(0, 4 + part.length)); f[4 + part.length] = c >> 8; f[5 + part.length] = c & 255;
    out.push(f);
  }
  return out;
}
function symbolsFor(data) {
  const syms = [];
  for (const f of frames(data)) {
    PRE.forEach(s => syms.push(s));
    for (const b of f) syms.push([b >> 4, b & 15]);
    for (let g = 0; g < GAP_SYMS; g++) syms.push(null);
  }
  return syms;
}
/* One pass of the message as audio samples (with a short silence at each end). */
function encode(data, sr = 48000) {
  const syms = symbolsFor(data);
  const n = Math.round(SYM * sr), ramp = Math.round(0.002 * sr);
  const lead = Math.round(0.15 * sr);
  const out = new Float32Array(lead * 2 + syms.length * n);
  let pos = lead, phA = 0, phB = 0;
  const norm = Math.tanh(2.2);
  for (const s of syms) {
    if (s) {
      const fa = LOW[s[0]], fb = HIGH[s[1]];
      for (let i = 0; i < n; i++) {
        const env = Math.min(1, i / ramp, (n - 1 - i) / ramp);
        // soft-clipped sines: bright and buzzy like an 8-bit sound chip, with the harmonics kept low
        const a = Math.sin(phA), b = Math.sin(phB);
        out[pos + i] = env * 0.45 * (Math.tanh(2.2 * a) / norm * 0.5 + Math.tanh(2.2 * b) / norm * 0.5);
        phA += 2 * Math.PI * fa / sr; phB += 2 * Math.PI * fb / sr;
      }
    }
    pos += n;
  }
  return out;
}
const seconds = data => symbolsFor(data).length * SYM + 0.3;
const frameCount = data => frames(data).length;

/* ---------- decoder ---------- */
class Decoder {
  constructor(sr, onMessage, onProgress) {
    this.sr = sr; this.onMessage = onMessage; this.onProgress = onProgress || (() => {});
    this.n = Math.round(SYM * sr); this.hop = this.n / 4; this.w = Math.round(WIN * sr);
    this.buf = new Float32Array(Math.round(sr * 8)); this.len = 0; this.base = 0;   // buf[0] is absolute sample `base`
    this.hops = []; this.hop0 = 0; this.scanFrom = 0;
    this.parts = {}; this.total = 0; this.done = new Set(); this.level = 0; this.alpha = 0; this.good = 0;
    const mk = f => 2 * Math.cos(2 * Math.PI * f / sr);
    this.kl = LOW.map(mk); this.kh = HIGH.map(mk);
    this.win = Float32Array.from({ length: this.w }, (_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (this.w - 1)));
  }
  push(samples) {
    let pk = 0; for (let i = 0; i < samples.length; i += 8) { const v = Math.abs(samples[i]); if (v > pk) pk = v; }
    this.level = this.level * 0.7 + pk * 0.3;
    if (this.len + samples.length > this.buf.length) {
      const keep = Math.max(0, this.len - Math.round(this.sr * 4));   // keep the last 4 s
      this.buf.copyWithin(0, keep, this.len); this.len -= keep; this.base += keep;
    }
    this.buf.set(samples, this.len); this.len += samples.length;
    for (;;) {
      const start = Math.round(this.hop0 + this.hops.length * this.hop) - this.base;
      const s = start + Math.round((this.n - this.w) / 2);
      if (s < 0) { this.hops.push({}); continue; }
      if (s + this.w > this.len) break;
      this.hops.push(this.analyse(s));
    }
    this.scan();
  }
  analyse(s) {
    const b = this.buf, w = this.win, N = this.w;
    const bank = ks => { const out = new Float32Array(ks.length); for (let j = 0; j < ks.length; j++) { let s1 = 0, s2 = 0; const k = ks[j]; for (let i = 0; i < N; i++) { const s0 = b[s + i] * w[i] + k * s1 - s2; s2 = s1; s1 = s0; } out[j] = s1 * s1 + s2 * s2 - k * s1 * s2; } return out; };
    return { lo: bank(this.kl), hi: bank(this.kh), d: null };
  }
  /* Tone decision for one hop. In a room, echo keeps the previous symbol's tones ringing; with a > 0 their power one
     symbol earlier is partly subtracted, so a tone that just started wins over one that is fading. Noise favours a = 0,
     echo favours a > 0, so each frame is tried both ways and the CRC says which one was right. */
  sym(i, a) {
    const h = this.hops[i]; if (!h || !h.lo) return null;
    if (!h.d) h.d = {};
    let d = h.d[a];
    if (!d) {
      const p = a ? this.hops[i - 4] : null;
      const pick = (cur, prev) => { let best = -1, bi = 0, sum = 0; for (let j = 0; j < cur.length; j++) { const v = Math.max(0, cur[j] - (prev ? a * prev[j] : 0)); sum += v; if (v > best) { best = v; bi = j; } } return [bi, sum ? best / sum : 0]; };
      const lo = pick(h.lo, p && p.lo), hi = pick(h.hi, p && p.hi);
      d = h.d[a] = [lo[0], hi[0], Math.min(lo[1], hi[1])];
    }
    return d[2] > 0.22 ? d : null;
  }
  /* Try to read a frame whose preamble starts at hop i. Returns 'wait', null (no frame) or the frame's end hop. */
  frameAt(i, a) {
    const H = this.hops;
    let ok = 0;
    for (let p = 0; p < PRE.length; p++) { const h = this.sym(i + p * 4, a); if (h && h[0] === PRE[p][0] && h[1] === PRE[p][1]) ok++; }
    if (ok < PRE.length - 1) return null;
    let bestI = i, bestQ = -1;   // refine alignment: the hop offset (−1..+1) whose symbols are cleanest
    for (const d of [-1, 0, 1]) { let q = 0; for (let p = 0; p < PRE.length; p++) { const h = this.sym(i + d + p * 4, a); if (h) q += h[2]; } if (q > bestQ) { bestQ = q; bestI = i + d; } }
    const at = bestI + PRE.length * 4;
    const byteAt = j => { const h = this.sym(at + j * 4, a) || (H[at + j * 4] && H[at + j * 4].d && H[at + j * 4].d[a]); return h ? (h[0] << 4) | h[1] : 0; };
    if (at + 4 * 4 >= H.length) return 'wait';
    const hdr = [0, 1, 2, 3].map(byteAt);
    if (hdr[0] !== MAGIC || hdr[3] > FRAME || hdr[3] === 0 || hdr[2] === 0 || hdr[1] >= hdr[2]) return null;
    const L = 4 + hdr[3] + 2;
    if (at + L * 4 >= H.length) return 'wait';
    const f = new Uint8Array(L); for (let j = 0; j < L; j++) f[j] = byteAt(j);
    if (crc16(f.subarray(0, L - 2)) !== ((f[L - 2] << 8) | f[L - 1])) return null;
    if (this.total && this.total !== hdr[2]) this.parts = {};
    this.total = hdr[2]; this.parts[hdr[1]] = f.slice(4, 4 + hdr[3]); this.good++;
    return at + L * 4;
  }
  scan() {
    const need = PRE.length * 4 + 4;
    for (let i = this.scanFrom; i + need < this.hops.length; i++) {
      let r = null;
      for (const a of [0, 0.4, 0.8]) { r = this.frameAt(i, a); if (r !== null) break; }
      if (r === 'wait') return;
      if (r === null) { this.scanFrom = i + 1; continue; }
      this.scanFrom = r; i = r - 1;
      const have = Object.keys(this.parts).length; this.onProgress(have, this.total);
      if (have === this.total) this.finish();
    }
    // forget analysed hops we no longer need
    const drop = Math.max(0, this.scanFrom - 8);
    if (drop > 4000) { this.hops.splice(0, drop); this.hop0 += drop * this.hop; this.scanFrom -= drop; }
  }
  finish() {
    const chunks = []; for (let i = 0; i < this.total; i++) chunks.push(this.parts[i]);
    const len = chunks.reduce((t, c) => t + c.length, 0); const msg = new Uint8Array(len); let o = 0; for (const c of chunks) { msg.set(c, o); o += c.length; }
    this.parts = {}; this.total = 0;
    if (len < 5) return;
    const body = msg.slice(0, len - 4); const want = new DataView(msg.buffer, msg.byteOffset).getUint32(len - 4);
    if (crc32(body) !== want) return;
    const key = Array.from(body.subarray(0, 64)).join(',') + ':' + body.length;
    if (this.done.has(key)) return; this.done.add(key);
    this.onMessage(body);
  }
}

/* ---------- browser side ---------- */
let playing = null, listening = null;
const AC = () => typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext);
const canPlay = () => !!AC();
const canListen = () => !!(AC() && typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
/* Plays the message on a loop until stop(). onLoop(n) fires at the start of each pass. */
async function play(data, onLoop) {
  stop();
  const Ctx = AC(); const ctx = new Ctx();
  if (ctx.state === 'suspended') try { await ctx.resume(); } catch (e) {}
  const pcm = encode(data, ctx.sampleRate);
  const buf = ctx.createBuffer(1, pcm.length, ctx.sampleRate); buf.copyToChannel(pcm, 0);
  const src = ctx.createBufferSource(); src.buffer = buf; src.loop = true; src.connect(ctx.destination);
  src.start();
  const dur = pcm.length / ctx.sampleRate; let n = 0;
  const tick = () => { if (!playing || playing.src !== src) return; n++; onLoop && onLoop(n, dur); playing.t = setTimeout(tick, dur * 1000); };
  playing = { ctx, src, t: 0, started: performance.now(), dur };
  tick();
  return dur;
}
async function listen(onData, onProgress) {
  stop();
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  const Ctx = AC(); const ctx = new Ctx();
  if (ctx.state === 'suspended') try { await ctx.resume(); } catch (e) {}
  const srcNode = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const dec = new Decoder(ctx.sampleRate, b => onData(b), onProgress);
  proc.onaudioprocess = e => { try { dec.push(e.inputBuffer.getChannelData(0).slice()); } catch (x) {} };
  const mute = ctx.createGain(); mute.gain.value = 0;
  srcNode.connect(proc); proc.connect(mute); mute.connect(ctx.destination);
  listening = { ctx, stream, proc, dec };
  return dec;
}
function stop() {
  if (playing) { clearTimeout(playing.t); try { playing.src.stop(); } catch (e) {} try { playing.ctx.close(); } catch (e) {} playing = null; }
  if (listening) { try { listening.proc.disconnect(); } catch (e) {} listening.stream.getTracks().forEach(t => t.stop()); try { listening.ctx.close(); } catch (e) {} listening = null; }
}
const api = { canPlay, canListen, play, listen, stop, encode, seconds, frameCount, Decoder, isPlaying: () => !!playing, level: () => listening ? listening.dec.level : 0 };
if (typeof window !== 'undefined') window.Chiptune = api;
if (typeof module !== 'undefined') module.exports = api;
})();
