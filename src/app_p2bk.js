/* ===================== Pay to Blinded Key (1.29, NUT-28) ===================== */
/* "Hide who gets it (P2BK)" (Settings, Privacy), off by default and kept per wallet. When it is on, ecash NUTCADE locks to
   someone else (a gift, a bounty) carries blinded keys instead of the keys themselves: P' = P + r·G, with
   r = SHA256("Cashu_P2BK_v1" || x(e·P) || slot) from a fresh ephemeral key e per coin, whose public key E goes on the coin
   (p2pk_e; "pe" in a cashuB token). The mint, and anyone else who sees the coin, sees a key nobody used before; the
   receiver (and this wallet, for its refund key) finds the private key again from E.
   The bundled cashu-ts does the work on both sides: sending with blindKeys blinds every key of the lock (the receiver's key
   and our refund key alike), and claiming with our private keys derives the signing keys from p2pk_e. The lock is built in
   one place, sendEcashNow (app.js), with one flag (opts.blind, from sendGift and createBounty), so a lock is never
   half blinded; the line it makes says blinded: true. Extra Life (locked to our own key, the heir as refund), treasure
   hunts and the nutzaps we send are never blinded: a nutzap can't come back to us, and the receiver's kind 10019 doesn't say
   whether its wallet supports NUT-28, so a blinded one could be lost for good. Blinded nutzaps sent TO us are still taken.
   This file holds the setting and our own check of a blinded key, for the places that read a lock before claiming it: a
   nutzap (app_nutzap.js) and a bounty sent to us (app_r5.js readBounty). Slots (NUT-28): P2PK: 0 the data key, then the
   "pubkeys" keys, then the refund keys; HTLC (its data is a hash): the "pubkeys" keys from 1, then the refund keys.
   A wallet without NUT-28 can't spend such ecash (a lock to a key nobody holds): the Settings text says so.
   Cost: E is chosen by whoever sent the coins, so a lock is refused before any point math when it has more than
   P2BK_MAX_KEYS keys or more than P2BK_MAX_COINS coins, and x(k·E) is worked out once per coin (r per slot is a hash).
   k·E (our private key times their E) uses DQ.mulSecret, a fixed-sequence ladder; k·G and r·G use the bundled noble
   (L.getPubKeyFromPrivKey). The bundle exports no ECDH of its own: see src/README.md for what that means. */
const P2BK_TAG = new TextEncoder().encode('Cashu_P2BK_v1');
const P2BK_MAX_KEYS = 10, P2BK_MAX_COINS = 64;
const p2bkOn = () => S.prefs.p2bk === true;
// a compressed point as 66 hex characters (02/03), parsed once: p2bkE and p2bkX share it
const p2bkPts = new Map();
function p2bkPoint(v) {
  if (typeof v !== 'string' || !/^0[23][0-9a-f]{64}$/i.test(v)) return null;
  v = v.toLowerCase(); if (p2bkPts.has(v)) return p2bkPts.get(v);
  const p = DQ.point(v); if (p2bkPts.size >= 256) p2bkPts.clear(); p2bkPts.set(v, p); return p;
}
// a coin's p2pk_e as it may be used: 66 hex characters, 02 or 03, a point on the curve (lower case); null otherwise
const p2bkE = v => p2bkPoint(v) ? v.toLowerCase() : null;
const p2bkP = new Map();   // private key -> its public point (the same few keys every time)
const p2bkOkPriv = priv => /^[0-9a-f]{64}$/i.test(String(priv || '')) && BigInt('0x' + priv) > 0n && BigInt('0x' + priv) < DQ.N;
// x(k·E): the shared secret of our private key and a sender's E, once per coin; null when E isn't a point
function p2bkX(priv, E) {
  const Ep = p2bkPoint(E); if (!Ep || !p2bkOkPriv(priv)) return null;
  return DQ.xOf(DQ.mulSecret(Ep, BigInt('0x' + priv)));
}
// our key blinded for `slot` from that shared secret: P + r·G, r = SHA256(tag || x || slot) (NUT-28's second try: || 0xff)
function p2bkFrom(priv, zx, slot) {
  if (!zx || !p2bkOkPriv(priv) || !Number.isInteger(slot) || slot < 0 || slot > 255) return null;
  const h = (...x) => BigInt('0x' + hex(L.sha256(new Uint8Array([...P2BK_TAG, ...L.hexToBytes(zx), ...x]))));
  let r = h(slot); if (r === 0n || r >= DQ.N) { r = h(slot, 255); if (r === 0n || r >= DQ.N) return null; }
  const pt = k => DQ.point(hex(L.getPubKeyFromPrivKey(L.hexToBytes(k))));
  let P = p2bkP.get(priv); if (!P) { if (p2bkP.size > 8) p2bkP.clear(); P = pt(priv); p2bkP.set(priv, P); }
  return DQ.comp(DQ.add(P, pt(r.toString(16).padStart(64, '0'))));
}
// our key (its private key, 64 hex) blinded for `slot` with a sender's E: exactly what the sender's wallet wrote into the lock
function p2bkBlind(priv, E, slot) {
  if (!Number.isInteger(slot) || slot < 0 || slot > 255) return null;
  return p2bkFrom(priv, p2bkX(priv, E), slot);
}
// a key read from a lock is ours: the plain key with no E on the coin, our key blinded for that slot with its E.
// p2bkIs takes x(k·E) already worked out (zx; null: no E), for a lock with several slots
const p2bkIs = (lock, pub, priv, zx, slot) => typeof lock === 'string' && !!lock && (zx ? lock.toLowerCase() === p2bkFrom(priv, zx, slot) : lock.toLowerCase() === pub);
function p2bkMine(lock, pub, priv, E, slot) {
  if (typeof lock !== 'string' || !lock) return false;
  if (!E) return lock.toLowerCase() === pub;
  const zx = p2bkX(priv, E); return !!zx && p2bkIs(lock, pub, priv, zx, slot);
}
function p2bkSettingsHTML() {
  return toggle('p2bk', 'Hide who gets it (P2BK)', "Hides the receiver's key in the gifts and bounties you lock to someone. Only turn it on if their wallet supports it (NUTCADE 1.29 or newer does; some other wallets don't): a wallet that doesn't can't spend it, and it comes back to you after its time runs out. Nutzaps you send are never hidden: a nutzap can't come back. Off by default.");
}
window.NutP2BK = { on: () => p2bkOn(), blind: (priv, E, slot) => p2bkBlind(priv, E, slot), e: v => p2bkE(v), mine: (lock, pub, priv, E, slot) => p2bkMine(lock, pub, priv, E, slot), lockPub: () => myLockPub(), bounty: (bo, game) => readBounty(bo, { game: game || 'flipper' }), max: { keys: P2BK_MAX_KEYS, coins: P2BK_MAX_COINS } };
