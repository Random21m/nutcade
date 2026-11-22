/* ===================== Pay to Blinded Key (1.29, NUT-28) ===================== */
/* "Hide who gets it (P2BK)" (Settings, Privacy), off by default and kept per wallet. When it is on, ecash NUTCADE locks to
   someone else (a gift, a bounty, a nutzap) carries blinded keys instead of the keys themselves: P' = P + r·G, with
   r = SHA256("Cashu_P2BK_v1" || x(e·P) || slot) from a fresh ephemeral key e per coin, whose public key E goes on the coin
   (p2pk_e; "pe" in a cashuB token). The mint, and anyone else who sees the coin, sees a key nobody used before; the
   receiver (and this wallet, for its refund key) finds the private key again from E.
   The bundled cashu-ts does the work on both sides: sending with blindKeys blinds every key of the lock (the receiver's key
   and our refund key alike), and claiming with our private keys derives the signing keys from p2pk_e. The lock is built in
   one place, sendEcashNow (app.js), with one flag (opts.blind, from sendGift, createBounty and nzSendTo), so a lock is never
   half blinded; the line it makes says blinded: true. Extra Life (locked to our own key, the heir as refund) and treasure
   hunts are never blinded.
   This file holds the setting and our own check of a blinded key, for the places that read a lock before claiming it: a
   nutzap (app_nutzap.js) and a bounty sent to us (app_r5.js readBounty). Slots (NUT-28): P2PK: 0 the data key, then the
   "pubkeys" keys, then the refund keys; HTLC (its data is a hash): the "pubkeys" keys from 1, then the refund keys.
   A wallet without NUT-28 can't spend such ecash (a lock to a key nobody holds): the Settings text says so. */
const P2BK_TAG = new TextEncoder().encode('Cashu_P2BK_v1');
const p2bkOn = () => S.prefs.p2bk === true;
// a coin's p2pk_e as it may be used: 66 hex characters, 02 or 03, a point on the curve (lower case); null otherwise
const p2bkE = v => typeof v === 'string' && /^0[23][0-9a-f]{64}$/i.test(v) && DQ.point(v.toLowerCase()) ? v.toLowerCase() : null;
const p2bkP = new Map();   // private key -> its public point (the same few keys every time)
// our key (its private key, 64 hex) blinded for `slot` with a sender's E: exactly what the sender's wallet wrote into the lock
function p2bkBlind(priv, E, slot) {
  const Ep = DQ.point(p2bkE(E) || '');
  if (!Ep || !/^[0-9a-f]{64}$/i.test(String(priv || '')) || !Number.isInteger(slot) || slot < 0 || slot > 255) return null;
  const k = BigInt('0x' + priv); if (k <= 0n || k >= DQ.N) return null;
  const zx = DQ.xOf(DQ.mul(Ep, k)); if (!zx) return null;
  const h = (...x) => BigInt('0x' + hex(L.sha256(new Uint8Array([...P2BK_TAG, ...L.hexToBytes(zx), ...x]))));
  let r = h(slot); if (r === 0n || r >= DQ.N) { r = h(slot, 255); if (r === 0n || r >= DQ.N) return null; }   // (NUT-28's second try)
  let P = p2bkP.get(priv); if (!P) { if (p2bkP.size > 8) p2bkP.clear(); P = DQ.mul(DQ.G, k); p2bkP.set(priv, P); }
  return DQ.comp(DQ.add(P, DQ.mul(DQ.G, r)));
}
// a key read from a lock is ours: the plain key with no E on the coin, our key blinded for that slot with its E
const p2bkMine = (lock, pub, priv, E, slot) => typeof lock === 'string' && !!lock && (E ? lock.toLowerCase() === p2bkBlind(priv, E, slot) : lock.toLowerCase() === pub);
function p2bkSettingsHTML() {
  return toggle('p2bk', 'Hide who gets it (P2BK)', "Hides the receiver's key in the ecash you lock to someone (gifts, bounties and nutzaps). Only turn it on if their wallet supports it (NUTCADE 1.29 or newer does; some other wallets don't): a wallet that doesn't can't spend it. Gifts and bounties can be taken back after their time runs out; a nutzap can't. Off by default.");
}
window.NutP2BK = { on: () => p2bkOn(), blind: (priv, E, slot) => p2bkBlind(priv, E, slot), e: v => p2bkE(v), mine: (lock, pub, priv, E, slot) => p2bkMine(lock, pub, priv, E, slot), lockPub: () => myLockPub() };
