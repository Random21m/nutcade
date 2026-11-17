// Decodes the WAV vectors with NUTCADE's own Decoder (src/chiptune.js) and soundText() (src/app_r4.js), and checks the text.
//   node docs/sound-vectors/decode_wav.js
// Three runs per vector: the clean WAV; two passes joined, heard from the middle of the first (so the frames arrive
// out of order and are stitched); and that same signal with white noise added at 6 dB SNR.
const fs = require('fs'), path = require('path');
const { Chiptune, App } = require('./nutcade.js');
const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, 'vectors.json'), 'utf8'));
function readWav(file) {
  const b = fs.readFileSync(file); if (b.toString('ascii', 0, 4) !== 'RIFF' || b.readUInt16LE(22) !== 1 || b.readUInt16LE(34) !== 16) throw new Error('want 16-bit mono WAV');
  const sr = b.readUInt32LE(24), n = b.readUInt32LE(40) / 2, x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = b.readInt16LE(44 + i * 2) / 32768;
  return { sr, x };
}
function decode(x, sr) {
  let got = null, progress = []; const dec = new Chiptune.Decoder(sr, b => { got = got || b; }, (have, total) => progress.push(have + '/' + total));
  for (let i = 0; i < x.length && !got; i += 4096) dec.push(x.subarray(i, i + 4096));
  return { got, progress };
}
let s = 7; const rand = () => (s = (s * 16807) % 2147483647) / 2147483647;
let fail = 0;
for (const v of vectors) {
  const { sr, x } = readWav(path.join(__dirname, v.wav));
  const two = new Float32Array(x.length * 2); two.set(x); two.set(x, x.length);
  const mid = two.subarray(Math.floor(x.length / 2));
  let pw = 0; for (const y of mid) pw += y * y; pw /= mid.length;
  const amp = Math.sqrt(pw / Math.pow(10, 6 / 10)), noisy = mid.map(y => y + amp * Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand()));
  for (const [label, sig] of [['clean', x], ['from mid-pass', mid], ['mid-pass + noise 6 dB', noisy]]) {
    const { got, progress } = decode(sig, sr);
    const text = got ? App.soundText(got) : '';
    const ok = text === v.input; if (!ok) fail++;
    console.log(`${v.name} [${label}] ${ok ? 'OK' : 'FAIL'}: ${got ? got.length : 0} payload bytes, frames heard ${progress.join(' ')}${ok ? ', text matches input' : ''}`);
  }
}
process.exit(fail ? 1 : 0);
