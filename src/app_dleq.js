/* =====================================================================
   Offline token check (1.26): the mint's signature on ecash, checked with no connection (NUT-12 DLEQ proofs)
   A token taken while offline (pasted, scanned, heard or tapped) can't be swapped yet. What can be checked is that
   its mint really signed every coin in it: each coin may carry a DLEQ proof that its signature was made with the
   mint's key for that amount. With the mint's public keys saved from the last time it was reached, that proof is
   checked right here, so a made-up token is refused at once. It never shows that the coins are unspent: only the
   mint can say that, so the sender can still spend them first, and the screens say so.
   Self-contained secp256k1 (BigInt, Jacobian coordinates); the bundled library checks the same proofs online, but
   doesn't export its checker. Nothing here moves money or talks to the network.
===================================================================== */

const DQ = (() => {
  const P = 2n ** 256n - 2n ** 32n - 977n, N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;
  const G = [0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798n, 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8n, 1n];
  const md = (a, m = P) => { const r = a % m; return r < 0n ? r + m : r; };
  const pw = (b, e) => { let r = 1n; b = md(b); while (e > 0n) { if (e & 1n) r = r * b % P; b = b * b % P; e >>= 1n; } return r; };
  const inv = a => { let [x, y, u, v] = [md(a), P, 1n, 0n]; while (x) { const q = y / x; [x, y] = [y - q * x, x]; [u, v] = [v - q * u, u]; } return md(v); };
  const ZERO = [0n, 1n, 0n];
  const dbl = ([x, y, z]) => {
    if (!z || !y) return ZERO;
    const y2 = y * y % P, s = 4n * x * y2 % P, m = 3n * x * x % P;
    const nx = md(m * m - 2n * s), ny = md(m * (s - nx) - 8n * y2 * y2), nz = 2n * y * z % P;
    return [nx, ny, nz];
  };
  const add = (p, q) => {
    if (!p[2]) return q; if (!q[2]) return p;
    const z1 = p[2] * p[2] % P, z2 = q[2] * q[2] % P;
    const u1 = p[0] * z2 % P, u2 = q[0] * z1 % P, s1 = p[1] * z2 % P * q[2] % P, s2 = q[1] * z1 % P * p[2] % P;
    if (u1 === u2) return s1 === s2 ? dbl(p) : ZERO;
    const h = md(u2 - u1), r = md(s2 - s1), h2 = h * h % P, h3 = h2 * h % P, v = u1 * h2 % P;
    const nx = md(r * r - h3 - 2n * v), ny = md(r * (v - nx) - s1 * h3), nz = h * p[2] % P * q[2] % P;
    return [nx, ny, nz];
  };
  const mul = (p, k) => { k = md(k, N); let r = ZERO; for (let i = 255; i >= 0; i--) { r = dbl(r); if ((k >> BigInt(i)) & 1n) r = add(r, p); } return r; };
  const neg = ([x, y, z]) => [x, md(-y), z];
  // k·p for a SECRET k (our private key times a point someone else chose: Pay to Blinded Key, app_p2bk.js). A Montgomery
  // ladder: the same add and double for every bit, the points swapped with a mask instead of a branch, over a fixed 257 bits
  // (k + N, the same point). BigInt arithmetic itself is not constant time, so this narrows the timing signal but can't
  // promise none (src/README.md); mul above is for public scalars only.
  const cswap = (a, b, m) => { for (let i = 0; i < 3; i++) { const d = (a[i] ^ b[i]) & m; a[i] ^= d; b[i] ^= d; } };
  const mulSecret = (p, k) => {
    k = md(k, N) + N; const r0 = [...ZERO], r1 = [...p];
    for (let i = 256; i >= 0; i--) {
      const m = -((k >> BigInt(i)) & 1n);
      cswap(r0, r1, m);
      const s = add(r0, r1), d = dbl(r0);
      r1[0] = s[0]; r1[1] = s[1]; r1[2] = s[2]; r0[0] = d[0]; r0[1] = d[1]; r0[2] = d[2];
      cswap(r0, r1, m);
    }
    return r0;
  };
  const aff = p => { if (!p[2]) return null; const zi = inv(p[2]), z2 = zi * zi % P; return [p[0] * z2 % P, p[1] * z2 % P * zi % P]; };
  const h64 = n => n.toString(16).padStart(64, '0');
  const big = h => BigInt('0x' + h);
  const isHex = (h, n) => typeof h === 'string' && h.length === n && /^[0-9a-f]+$/i.test(h);
  // a proof's e, s and r as 64 hex digits: written without leading zeros by some wallets (cashu-ts reads them that way too)
  const pad = h => typeof h === 'string' && h.length >= 1 && h.length <= 64 && /^[0-9a-f]+$/i.test(h) ? h.padStart(64, '0').toLowerCase() : null;
  const wellFormed = d => !!(d && pad(d.e) && pad(d.s) && pad(d.r));
  // a compressed point (02/03 + x), or null when it isn't one on the curve
  function lift(xn, odd) {
    if (xn >= P) return null;
    const rhs = md(xn * xn % P * xn + 7n), y = pw(rhs, (P + 1n) / 4n);
    if (y * y % P !== rhs) return null;
    return [xn, (y & 1n) === (odd ? 1n : 0n) ? y : md(-y), 1n];
  }
  function point(h) { if (!isHex(h, 66) || !/^0[23]/.test(h)) return null; return lift(big(h.slice(2)), h[1] === '3'); }
  const hexOf = u8 => Array.from(u8, b => b.toString(16).padStart(2, '0')).join('');
  const cat = (...a) => { const o = new Uint8Array(a.reduce((n, x) => n + x.length, 0)); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };
  const DOMAIN = new TextEncoder().encode('Secp256k1_HashToCurve_Cashu_');
  // NUT-00 hash_to_curve: Y for a coin's secret
  function hashToCurve(msg) {
    const h = L.sha256(cat(DOMAIN, msg));
    for (let c = 0; c < 65536; c++) {
      const ctr = new Uint8Array([c & 255, (c >> 8) & 255, 0, 0]);
      const p = lift(big(hexOf(L.sha256(cat(h, ctr)))), false);
      if (p) return p;
    }
    throw new Error('hash_to_curve');
  }
  const unc = p => { const a = aff(p); return '04' + h64(a[0]) + h64(a[1]); };
  // NUT-12, checked by the receiver: C' = C + r·A, B' = Y + r·G, R1 = s·G − e·A, R2 = s·B' − e·C', and e = hash(R1, R2, A, C')
  function proofOk(p, Ahex) {
    const d0 = p && p.dleq; if (!wellFormed(d0)) return false;
    const d = { e: pad(d0.e), s: pad(d0.s), r: pad(d0.r) };
    const A = point(Ahex), C = point(String(p.C || '')); if (!A || !C) return false;
    const e = big(d.e), s = big(d.s), r = big(d.r);
    if (e >= N || s >= N || r >= N) return false;
    const Y = hashToCurve(new TextEncoder().encode(String(p.secret)));
    const C_ = add(C, mul(A, r)), B_ = add(Y, mul(G, r));
    const R1 = add(mul(G, s), neg(mul(A, e))), R2 = add(mul(B_, s), neg(mul(C_, e)));
    if (!R1[2] || !R2[2] || !C_[2]) return false;
    const hash = hexOf(L.sha256(new TextEncoder().encode(unc(R1) + unc(R2) + unc(A) + unc(C_))));
    return hash === d.e;
  }
  // a point as 02/03 + x (33 bytes as hex), or null at infinity
  const comp = p => { const a = aff(p); return a ? ((a[1] & 1n) ? '03' : '02') + h64(a[0]) : null; };
  return { proofOk, wellFormed, hashToCurve, point, unc, mul, mulSecret, add, comp, xOf: p => { const a = aff(p); return a ? h64(a[0]) : null; }, G, N };
})();

/* ---------- the mints' public keys, saved for offline use ---------- */
// url -> { keysetId: { amount: compressed public key } }, the sat keysets the mint served the last time it was loaded.
// Kept with the wallet (inside the PIN vault when one is set, like the mint list); never in backup files (the mint serves them again).
S.mintkeys = store.get('mintkeys', {});
// Not saved in the duress PIN's wallet: its part of the vault must stay the size of the filler an unused one has (app_r8.js).
function saveMintKeys(url, w) {
  if (vault.decoy) return;
  try {
    const got = {};
    for (const k of w.keyChain.getKeysets()) {   // (the account's own unit: the wallet is built for it)
      const kk = k.keys instanceof Map ? Object.fromEntries(k.keys) : (k.keys || {});
      const keys = {}; for (const [a, pub] of Object.entries(kk)) if (/^0[23][0-9a-f]{64}$/i.test(String(pub))) keys[a] = String(pub).toLowerCase();
      if (Object.keys(keys).length) got[k.id] = keys;
    }
    if (!Object.keys(got).length) return;
    const was = S.mintkeys[url] || {};   // (the mint's whole list, its retired keysets too; one it no longer lists is dropped: its coins aren't accepted any more)
    if (JSON.stringify(got) === JSON.stringify(was)) return;
    S.mintkeys[url] = got; store.set('mintkeys', S.mintkeys);
  } catch (e) {}
}
// The check of a token's coins against the saved keys of its mint:
//   ok      every coin carries a proof and every proof is good (n coins)
//   bad     a coin's well-formed proof is wrong, or the same coin is in the token twice: not signed by this mint (refused)
//   noproof some coin carries no proof, or one that can't be read (made by a wallet that leaves them out): can't be checked here
//   big     more coins than are checked here without freezing the screen: not checked (no line is shown)
//   nokeys  NUTCADE hasn't saved the keys of this mint, or of the keyset a coin is on (new since it was last reached): can't be checked here
function offlineCheck(token) {
  const meta = peekToken(token), ks = S.mintkeys[meta.mint];
  let proofs;
  try { proofs = L.getDecodedToken(cleanToken(token), Object.keys(ks || {}).concat(Object.keys(S.counters))).proofs || []; }
  catch (e) { return { state: 'nokeys', n: 0 }; }   // (a short keyset id none of the saved keys match: a keyset new since)
  if (!proofs.length) return { state: 'bad', n: 0 };
  // one real coin written into a token many times would add up to many times its value: a token never holds a coin twice
  const secs = new Set(proofs.map(p => String(p.secret))), sigs = new Set(proofs.map(p => String(p.C).toLowerCase()));
  if (secs.size !== proofs.length || sigs.size !== proofs.length) return { state: 'bad', n: proofs.length };
  if (proofs.length > DQ_MAX) return { state: 'big', n: proofs.length };
  if (!ks) return { state: 'nokeys', n: proofs.length };
  let missing = false, unknown = false;
  for (const p of proofs) {
    const keys = ks[p.id];
    if (!keys) { unknown = true; continue; }   // (a keyset the mint made after its keys were saved here: never called fake)
    const A = keys[String(p.amount)];
    if (!A) { unknown = true; continue; }   // (no saved key for this amount: not checked, never called fake; the mint refuses it when claimed)
    if (!DQ.wellFormed(p.dleq)) { missing = true; continue; }
    if (!DQ.proofOk(p, A)) return { state: 'bad', n: proofs.length };
  }
  return { state: unknown ? 'nokeys' : missing ? 'noproof' : 'ok', n: proofs.length };
}
// the secrets of a token's coins, read with every keyset id this wallet knows (its own and every saved mint's: a token's
// short keyset ids can only be read with them); null when it can't be read
function heldSecrets(token) {
  try {
    const ids = new Set(Object.keys(S.counters)); for (const ks of Object.values(S.mintkeys || {})) for (const id of Object.keys(ks)) ids.add(id);
    const ps = L.getDecodedToken(cleanToken(token), [...ids]).proofs || []; return ps.length ? ps.map(p => String(p.secret)) : null;
  } catch (e) { return null; }
}
const DQ_MAX = 300;   // (about 2 s at most on a slow phone)
const forgedErr = () => Object.assign(new Error("This token's coins weren't signed by its mint. It may be fake, so NUTCADE didn't save it."), { forged: true });
// the line shown on a saved token's screen about its check
function checkLine(t) {
  if (t.dleq === 'ok') return `<div class="notice cyan">✓ Signature checked offline: the mint really signed these coins. It can't show they're unspent: only the mint can say that when you claim.</div>`;
  if (t.dleq === 'noproof') return `<div class="notice">Not checked: the wallet that made this token left out the mint's signature proofs.</div>`;
  if (t.dleq === 'nokeys') return `<div class="notice">Not checked: NUTCADE doesn't have the keys the mint signed these coins with yet. It gets them the next time it reaches the mint.</div>`;
  return '';
}
