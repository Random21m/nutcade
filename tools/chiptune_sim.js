// Channel simulation for the chiptune modem: resampling, clock drift, echo, noise, starting mid-pass.
const C = require('../src/chiptune.js');
function sim({ bytes = 600, snrDb = 12, drift = 80e-6, srOut = 44100, echo = true, startFrac = 0.37, seed = 1 }) {
  let s = seed; const rand = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const data = new Uint8Array(bytes).map(() => Math.floor(rand() * 256));
  const one = C.encode(data, 48000);
  const passes = 3, src = new Float32Array(one.length * passes); for (let p = 0; p < passes; p++) src.set(one, p * one.length);
  const start = Math.floor(one.length * startFrac);
  const ratio = 48000 / srOut * (1 + drift);
  const outLen = Math.floor((src.length - start) / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) { const x = start + i * ratio, k = Math.floor(x), f = x - k; out[i] = (src[k] || 0) * (1 - f) + (src[k + 1] || 0) * f; }
  if (echo) { const d1 = Math.round(0.012 * srOut), d2 = Math.round(0.031 * srOut); for (let i = out.length - 1; i >= d2; i--) out[i] += 0.45 * out[i - d1] + 0.25 * out[i - d2]; }
  let pw = 0; for (const v of out) pw += v * v; pw /= out.length;
  const nAmp = Math.sqrt(pw / Math.pow(10, snrDb / 10));
  for (let i = 0; i < out.length; i++) { const g = Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand()); out[i] = 0.2 * (out[i] + nAmp * g); }
  let got = null, at = 0; const t0 = Date.now();
  const dec = new C.Decoder(srOut, b => { if (!got) { got = b; at = i0; } });
  let i0 = 0;
  for (i0 = 0; i0 < out.length && !got; i0 += 4096) dec.push(out.subarray(i0, i0 + 4096));
  const ok = !!got && got.length === data.length && got.every((v, i) => v === data[i]);
  return { ok, secs: +(at / srOut).toFixed(1), pass: +(C.seconds(data)).toFixed(1), cpu: Date.now() - t0 };
}
for (const cfg of [{}, { snrDb: 6 }, { snrDb: 3 }, { snrDb: 0 }, { drift: 300e-6 }, { srOut: 48000 }, { bytes: 120 }, { bytes: 1200, snrDb: 8 }, { startFrac: 0.9, seed: 7 }])
  console.log(JSON.stringify(cfg), JSON.stringify(sim(cfg)));
console.log('-- harder');
for (const cfg of [{ snrDb: -3 }, { snrDb: -6 }, { snrDb: 3, drift: 1000e-6 }]) console.log(JSON.stringify(cfg), JSON.stringify(sim(cfg)));
// room reverb: exponentially decaying tail (RT60 ≈ 0.25 s) at a modest direct-to-reverb ratio
function reverbTest(ratio) {
  const data = new Uint8Array(400).map((_, i) => (i * 37 + 11) & 255);
  const sr = 44100, one = C.encode(data, sr), x = new Float32Array(one.length * 2); x.set(one); x.set(one, one.length);
  const L = Math.round(0.3 * sr), ir = new Float32Array(L); let s = 3; const r = () => (s = (s * 16807) % 2147483647) / 2147483647 - 0.5;
  for (let i = 0; i < L; i++) ir[i] = r() * Math.exp(-6.9 * i / (0.25 * sr)) * ratio * 0.08;
  const y = new Float32Array(x.length); for (let i = 0; i < x.length; i++) { y[i] += x[i]; }
  for (let i = 0; i < x.length; i += 1) { if (!x[i]) continue; const v = x[i]; for (let k = 1; k < L; k += 7) { if (i + k < y.length) y[i + k] += v * ir[k] * 7; } }
  let got = null; const dec = new C.Decoder(sr, b => { got = got || b; });
  for (let i = 0; i < y.length && !got; i += 4096) dec.push(y.subarray(i, i + 4096));
  return !!got && got.every((v, i) => v === data[i]);
}
console.log('-- reverb', [0.5, 1, 2, 3].map(k => k + ':' + reverbTest(k)).join(' '));
