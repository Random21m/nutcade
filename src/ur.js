/* NUTCADE animated QR codes: BC-UR multipart (ur:bytes), the same format cashu.me reads and writes.
   A long token is wrapped as a CBOR byte string, split into equal fragments, and sent as a loop of parts.
   The first parts are the fragments in order; later parts mix several fragments together (fountain coding),
   so a scanner that misses a few frames still finishes. Written from the Blockchain Commons specs
   (BCR-2020-005 UR, BCR-2020-006 multipart, BCR-2020-012 bytewords). */
(function(){
'use strict';
const WORDS = 'ableacidalsoapexaquaarchatomauntawayaxisbackbaldbarnbeltbetabiasbluebodybragbrewbulbbuzzcalmcashcatschefcityclawcodecolacookcostcruxcurlcuspcyandarkdatadaysdelidicedietdoordowndrawdropdrumdulldutyeacheasyechoedgeepicevenexamexiteyesfactfairfernfigsfilmfishfizzflapflewfluxfoxyfreefrogfuelfundgalagamegeargemsgiftgirlglowgoodgraygrimgurugushgyrohalfhanghardhawkheathelphighhillholyhopehornhutsicedideaidleinchinkyintoirisironitemjadejazzjoinjoltjowljudojugsjumpjunkjurykeepkenokeptkeyskickkilnkingkitekiwiknoblamblavalazyleaflegsliarlimplionlistlogoloudloveluaulucklungmainmanymathmazememomenumeowmildmintmissmonknailnavyneednewsnextnoonnotenumbobeyoboeomitonyxopenovalowlspaidpartpeckplaypluspoempoolposepuffpumapurrquadquizraceramprealredorichroadrockroofrubyruinrunsrustsafesagascarsetssilkskewslotsoapsolosongstubsurfswantacotasktaxitenttiedtimetinytoiltombtoystriptunatwinuglyundouniturgeuservastveryvetovialvibeviewvisavoidvowswallwandwarmwaspwavewaxywebswhatwhenwhizwolfworkyankyawnyellyogayurtzapszerozestzinczonezoom';
const W2I = {}; for (let i = 0; i < 256; i++) W2I[WORDS[i * 4] + WORDS[i * 4 + 3]] = i;
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(b) { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
const be32 = n => [n >>> 24 & 255, n >>> 16 & 255, n >>> 8 & 255, n & 255];
// bytewords, minimal style: two letters per byte, with a CRC32 of the bytes on the end
function bwEncode(b) { const all = [...b, ...be32(crc32(b))]; let s = ''; for (const x of all) s += WORDS[x * 4] + WORDS[x * 4 + 3]; return s; }
function bwDecode(s) {
  s = s.toLowerCase(); if (s.length % 2 || s.length < 10) throw new Error('bad bytewords');
  const out = new Uint8Array(s.length / 2); for (let i = 0; i < out.length; i++) { const v = W2I[s.substr(i * 2, 2)]; if (v === undefined) throw new Error('bad bytewords'); out[i] = v; }
  const body = out.slice(0, -4), c = out.slice(-4), want = be32(crc32(body));
  if (want.some((v, i) => v !== c[i])) throw new Error('bytewords checksum'); return body;
}
// CBOR: just what UR needs (unsigned ints, byte strings, arrays)
function cHead(major, n) { const m = major << 5; if (n < 24) return [m | n]; if (n < 256) return [m | 24, n]; if (n < 65536) return [m | 25, n >> 8, n & 255]; return [m | 26, ...be32(n)]; }
function cEnc(v) {
  if (typeof v === 'number') return cHead(0, v);
  if (v instanceof Uint8Array) return [...cHead(2, v.length), ...v];
  if (Array.isArray(v)) return [...cHead(4, v.length), ...v.flatMap(cEnc)];
  throw new Error('cbor type');
}
function cDec(b) {
  let i = 0;
  const num = ai => { if (ai < 24) return ai; if (ai === 24) return b[i++]; if (ai === 25) { const v = b[i] << 8 | b[i + 1]; i += 2; return v; } if (ai === 26) { const v = ((b[i] << 24) >>> 0) + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3]; i += 4; return v; } throw new Error('cbor size'); };
  const item = () => { const h = b[i++], major = h >> 5, n = num(h & 31);
    if (major === 0) return n; if (major === 2) { const v = b.slice(i, i + n); i += n; return v; } if (major === 4) { const a = []; for (let k = 0; k < n; k++) a.push(item()); return a; }
    throw new Error('cbor type'); };
  return item();
}
// Xoshiro256** seeded from SHA-256, and a double drawn the way the reference JS library rounds it (20 decimal places)
const M64 = (1n << 64n) - 1n, rotl = (x, k) => ((x << BigInt(k)) | (x >> BigInt(64 - k))) & M64;
async function sha256(bytes) { return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)); }
function Xoshiro(digest) {
  const s = [0n, 0n, 0n, 0n]; for (let i = 0; i < 4; i++) { let v = 0n; for (let n = 0; n < 8; n++) v = (v << 8n) | BigInt(digest[i * 8 + n]); s[i] = v; }
  const roll = () => { const r = (rotl((s[1] * 5n) & M64, 7) * 9n) & M64, t = (s[1] << 17n) & M64; s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = rotl(s[3], 45); return r; };
  const E20 = 10n ** 20n, D = 1n << 64n;
  const nextDouble = () => { const v = roll(); const q = (v * E20 * 2n + D) / (2n * D); return q >= E20 ? 1 : Number('0.' + q.toString().padStart(20, '0')); };
  return { nextDouble, nextInt: (lo, hi) => Math.floor(nextDouble() * (hi - lo + 1) + lo) };
}
// Walker/Vose alias sampler over the degree weights 1, 1/2, 1/3 …
function degree(n, rng) {
  const p = []; let sum = 0; for (let i = 0; i < n; i++) { p.push(1 / (i + 1)); sum += p[i]; }
  const P = p.map(x => x * n / sum), S = [], L = [], prob = [], alias = [];
  for (let i = n - 1; i >= 0; i--) (P[i] < 1 ? S : L).push(i);
  while (S.length && L.length) { const a = S.pop(), g = L.pop(); prob[a] = P[a]; alias[a] = g; P[g] = P[g] + P[a] - 1; (P[g] < 1 ? S : L).push(g); }
  while (L.length) prob[L.pop()] = 1; while (S.length) prob[S.pop()] = 1;
  const c = Math.floor(rng.nextDouble() * n); return (rng.nextDouble() < prob[c] ? c : alias[c]) + 1;
}
async function chooseFragments(seqNum, seqLen, checksum) {
  if (seqNum <= seqLen) return [seqNum - 1];
  const rng = Xoshiro(await sha256(new Uint8Array([...be32(seqNum), ...be32(checksum)])));
  const d = degree(seqLen, rng); const rest = [...Array(seqLen).keys()], out = [];
  while (rest.length) out.push(rest.splice(rng.nextInt(0, rest.length - 1), 1)[0]);
  return out.slice(0, d);
}
const xorInto = (a, b) => { for (let i = 0; i < a.length; i++) a[i] ^= b[i]; return a; };

/* encoder: next() resolves to the text of the next QR frame */
function encoder(text, maxLen = 150) {
  const msg = new Uint8Array(cEnc(new TextEncoder().encode(text))), len = msg.length, checksum = crc32(msg);
  let fl = 0; for (let n = 1; n <= Math.ceil(len / 10); n++) { fl = Math.ceil(len / n); if (fl <= maxLen) break; }
  const frags = []; for (let o = 0; o < len; o += fl) { const f = new Uint8Array(fl); f.set(msg.slice(o, o + fl)); frags.push(f); }
  let seq = 0;
  return {
    count: frags.length,
    async next() {
      if (frags.length <= 1) return 'ur:bytes/' + bwEncode(msg);
      seq = (seq + 1) >>> 0;
      const mix = new Uint8Array(fl); for (const i of await chooseFragments(seq, frags.length, checksum)) xorInto(mix, frags[i]);
      return 'ur:bytes/' + seq + '-' + frags.length + '/' + bwEncode(new Uint8Array(cEnc([seq, frags.length, len, checksum, mix])));
    }
  };
}

/* decoder: feed it every scanned string that starts with ur:; done() and text() once complete */
function decoder() {
  let want = null; const known = new Map(); let mixed = []; let result = null; const seen = new Set();
  const reduce = p => { for (const i of [...p.idx]) if (known.has(i)) { xorInto(p.data, known.get(i)); p.idx.delete(i); } return p; };
  function addSimple(i, data) {
    if (known.has(i)) return; known.set(i, data);
    const queue = [];
    mixed = mixed.filter(p => { if (!p.idx.has(i)) return true; xorInto(p.data, data); p.idx.delete(i); if (p.idx.size === 1) { queue.push(p); return false; } return p.idx.size > 0; });
    for (const p of queue) addSimple([...p.idx][0], p.data);
  }
  function finish() {
    if (known.size < want.n) return;
    const msg = new Uint8Array(want.n * want.fl); for (let i = 0; i < want.n; i++) msg.set(known.get(i), i * want.fl);
    const m = msg.slice(0, want.len); if (crc32(m) !== want.sum) { result = { error: 'checksum' }; return; }
    const bytes = cDec(m); result = { text: new TextDecoder().decode(bytes) };
  }
  return {
    async receive(str) {
      if (result) return true;
      const m = /^ur:bytes\/(?:(\d+)-(\d+)\/)?([a-z]+)$/i.exec(String(str).trim()); if (!m) return false;
      if (seen.has(str.toLowerCase())) return false; seen.add(str.toLowerCase());
      const body = bwDecode(m[3]);
      if (!m[1]) { result = { text: new TextDecoder().decode(cDec(body)) }; return true; }
      const [seq, n, len, sum, frag] = cDec(body);
      if (!want) want = { n, len, sum, fl: frag.length };
      else if (want.n !== n || want.len !== len || want.sum !== sum || want.fl !== frag.length) return false;
      const p = reduce({ idx: new Set(await chooseFragments(seq, n, sum)), data: new Uint8Array(frag) });
      if (p.idx.size === 1) addSimple([...p.idx][0], p.data);
      else if (p.idx.size > 1) mixed.push(p);
      finish(); return true;
    },
    progress() { return want ? Math.min(1, known.size / want.n) : 0; },
    done: () => !!result, text: () => result && result.text, error: () => result && result.error
  };
}
window.NutUR = { encoder, decoder };
})();
