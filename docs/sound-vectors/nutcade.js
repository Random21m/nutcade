// Loads NUTCADE's own sound code into Node, unchanged: the modem (src/chiptune.js), the payload layer
// (soundBytes/soundText/packToken/unpackToken from src/app_r4.js) and classify() from src/app.js.
// Nothing here re-implements the format; the functions are sliced out of the source files and run as-is.
const fs = require('fs'), vm = require('vm'), path = require('path');
const REPO = path.resolve(__dirname, '../..');
const src = f => fs.readFileSync(path.join(REPO, f), 'utf8');
const slice = (text, from, to) => { const a = text.indexOf(from), b = text.indexOf(to, a); if (a < 0 || b < 0) throw new Error('marker not found: ' + from); return text.slice(a, b); };
const ctx = { TextEncoder, TextDecoder, crypto: globalThis.crypto, atob, btoa, console, URL, URLSearchParams };
ctx.window = ctx; ctx.self = ctx; ctx.globalThis = ctx; vm.createContext(ctx);
vm.runInContext(src('src/lib.min.js') + ';globalThis.CashuLib = CashuLib;', ctx);
const app = src('src/app.js'), r4 = src('src/app_r4.js');
vm.runInContext([
  'const L = window.CashuLib; const S = { counters: {} };',
  // classify() only reaches these helpers for inputs that are not tokens or payment requests
  'const parseNostrAddr = () => null, btcAddr = () => false, normUrl = u => u, parseBtc = () => null;',
  slice(app, 'const num = a =>', '\n'),
  slice(app, 'const hex = b =>', '\n'),
  slice(app, 'function cleanToken(t)', '\n'),
  slice(app, 'function classify(raw) {', '\n}\n') + '\n}',
  slice(r4, 'const b64url = ', 'const ctBtn = '),
  'globalThis.App = { classify, soundBytes, soundText, packToken, unpackToken };'
].join('\n'), ctx);
// frames(), crc16() and crc32() are private to src/chiptune.js; run that same source text here to print frame bytes.
const ct = src('src/chiptune.js');
const Framing = new Function(slice(ct, 'const SYM = ', 'function symbolsFor') + 'return { frames, crc16, crc32, FRAME, MAGIC, PRE };')();
module.exports = { Framing, Chiptune: require(path.join(REPO, 'src/chiptune.js')), App: ctx.App, L: ctx.CashuLib, REPO };
