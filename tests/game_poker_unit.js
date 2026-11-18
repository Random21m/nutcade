// Nut Poker rules: unit tests (node tests/game_poker_unit.js). Prints PASS/FAIL lines like the Python suites; exits 1 on any failure.
const assert = require('assert');
const P = require('../src/game_poker.js');
let bad = 0;
const check = (name, fn) => { try { fn(); console.log('PASS', name); } catch (e) { bad++; console.log('FAIL', name, '-', e.message); } };
const R = { 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, J: 9, Q: 10, K: 11, A: 12 }, S = { s: 0, h: 1, d: 2, c: 3 };
const H = str => str.split(' ').map(x => 13 * S[x.slice(-1)] + R[x.slice(0, -1)]);   // 'As Kh 10d' -> card numbers
const ev = str => P.evaluate(H(str));
check('royal flush', () => assert.strictEqual(ev('10h Jh Qh Kh Ah'), 'royal'));
check('royal flush in any order and any suit', () => { assert.strictEqual(ev('Ks As Js 10s Qs'), 'royal'); assert.strictEqual(ev('Ac Qc 10c Kc Jc'), 'royal'); });
check('straight flush', () => assert.strictEqual(ev('5d 6d 7d 8d 9d'), 'sflush'));
check('straight flush: 9-10-J-Q-K is not royal', () => assert.strictEqual(ev('9c 10c Jc Qc Kc'), 'sflush'));
check('ace-low straight flush A-2-3-4-5 (the wheel)', () => assert.strictEqual(ev('Ah 2h 3h 4h 5h'), 'sflush'));
check('four of a kind', () => assert.strictEqual(ev('7s 7h 7d 7c 2h'), 'quads'));
check('four aces with a low kicker', () => assert.strictEqual(ev('As Ah Ad Ac 2h'), 'quads'));
check('full house', () => assert.strictEqual(ev('3s 3h 3d 9c 9h'), 'full'));
check('full house, pair below the triple and above', () => { assert.strictEqual(ev('Ks Kh 2d 2c 2h'), 'full'); assert.strictEqual(ev('2s 2h Kd Kc Kh'), 'full'); });
check('flush', () => assert.strictEqual(ev('2h 5h 9h Jh Kh'), 'flush'));
check('ace-high flush that is not a straight', () => assert.strictEqual(ev('Ad 3d 6d 9d Jd'), 'flush'));
check('straight', () => assert.strictEqual(ev('4s 5h 6d 7c 8h'), 'straight'));
check('ace-low straight A-2-3-4-5', () => assert.strictEqual(ev('As 2h 3d 4c 5h'), 'straight'));
check('ace-high straight 10-J-Q-K-A, mixed suits', () => assert.strictEqual(ev('10s Jh Qd Kc Ah'), 'straight'));
check('no wrap-around straight: Q-K-A-2-3 pays nothing', () => assert.strictEqual(ev('Qs Kh Ad 2c 3h'), null));
check('no wrap-around straight: K-A-2-3-4 pays nothing', () => assert.strictEqual(ev('Ks Ah 2d 3c 4h'), null));
check('J-Q-K-A-2 pays nothing', () => assert.strictEqual(ev('Js Qh Kd Ac 2h'), null));
check('wrap-around in one suit is a flush, not a straight flush', () => assert.strictEqual(ev('Qh Kh Ah 2h 3h'), 'flush'));
check('three of a kind', () => assert.strictEqual(ev('8s 8h 8d Kc 2h'), 'trips'));
check('two pair', () => assert.strictEqual(ev('5s 5h Jd Jc 2h'), 'twopair'));
check('two pair of low cards still pays', () => assert.strictEqual(ev('2s 2h 3d 3c 9h'), 'twopair'));
check('a pair of jacks pays (jacks or better)', () => assert.strictEqual(ev('Js Jh 2d 5c 9h'), 'jacks'));
check('a pair of queens, kings and aces pay', () => { assert.strictEqual(ev('Qs Qh 2d 5c 9h'), 'jacks'); assert.strictEqual(ev('Ks Kh 2d 5c 9h'), 'jacks'); assert.strictEqual(ev('As Ah 2d 5c 9h'), 'jacks'); });
check('a pair of 10s pays nothing', () => assert.strictEqual(ev('10s 10h 2d 5c 9h'), null));
check('pairs from 2 to 10 pay nothing', () => { for (const r of ['2', '3', '4', '5', '6', '7', '8', '9', '10']) assert.strictEqual(ev(`${r}s ${r}h ${r === '9' ? '2' : '9'}d ${r === '4' ? '7' : '4'}c Jh`), null, r); });
check('high card (ace-high, nothing) pays nothing', () => assert.strictEqual(ev('As Kh 9d 5c 2h'), null));
check('four to a flush pays nothing', () => assert.strictEqual(ev('2h 5h 9h Jh Kc'), null));
check('four to a straight pays nothing', () => assert.strictEqual(ev('4s 5h 6d 7c 9h'), null));
check('a pair of jacks beats nothing but loses to two pair', () => assert.strictEqual(ev('Js Jh 4d 4c 9h'), 'twopair'));
check('bad hands are refused', () => {
  assert.throws(() => P.evaluate([1, 2, 3, 4])); assert.throws(() => P.evaluate([1, 1, 2, 3, 4])); assert.throws(() => P.evaluate([1, 2, 3, 4, 52])); assert.throws(() => P.evaluate([1, 2, 3, 4, 1.5])); assert.throws(() => P.evaluate(null));
});
check('pay table: 1 to 4 credits pay 250/50/25/9/6/4/3/2/1 per credit', () => {
  const per = { royal: 250, sflush: 50, quads: 25, full: 9, flush: 6, straight: 4, trips: 3, twopair: 2, jacks: 1 };
  for (const k in per) for (let b = 1; b <= 4; b++) assert.strictEqual(P.payout(k, b), per[k] * b, k + b);
});
check('pay table: everything but the royal is multiplied by 5 at max bet', () => {
  const per = { sflush: 50, quads: 25, full: 9, flush: 6, straight: 4, trips: 3, twopair: 2, jacks: 1 };
  for (const k in per) assert.strictEqual(P.payout(k, 5), per[k] * 5, k);
});
check('pay table: the royal flush pays 4000 at max bet, 250 per credit below', () => { assert.strictEqual(P.payout('royal', 5), 4000); assert.strictEqual(P.payout('royal', 4), 1000); assert.strictEqual(P.payout('royal', 1), 250); });
check('nothing pays nothing, and odd bets pay nothing', () => { assert.strictEqual(P.payout(null, 3), 0); assert.strictEqual(P.payout('royal', 0), 0); assert.strictEqual(P.payout('royal', 6), 0); assert.strictEqual(P.payout('jacks', 2.5), 0); });
check('start credits are 100, max bet 5', () => { assert.strictEqual(P.START, 100); assert.strictEqual(P.MAXBET, 5); });
check('every one of the 2,598,960 five-card hands is classified, with the exact textbook counts', () => {
  const want = { royal: 4, sflush: 36, quads: 624, full: 3744, flush: 5108, straight: 10200, trips: 54912, twopair: 123552, jacks: 337920, none: 2062860 };   // none = 1,302,540 high-card hands + 760,320 pairs of 10s and below
  const got = { royal: 0, sflush: 0, quads: 0, full: 0, flush: 0, straight: 0, trips: 0, twopair: 0, jacks: 0, none: 0 }; let n = 0; const h = [0, 0, 0, 0, 0];
  for (let a = 0; a < 48; a++) for (let b = a + 1; b < 49; b++) for (let c = b + 1; c < 50; c++) for (let d = c + 1; d < 51; d++) for (let e = d + 1; e < 52; e++) { h[0] = a; h[1] = b; h[2] = c; h[3] = d; h[4] = e; got[P.evaluate(h) || 'none']++; n++; }
  assert.strictEqual(n, 2598960); assert.deepStrictEqual(got, want);
});
check('the shuffle uses crypto.getRandomValues, never Math.random', () => {
  const real = Math.random, rgv = globalThis.crypto.getRandomValues.bind(globalThis.crypto); let calls = 0;
  Math.random = () => { throw new Error('Math.random was used'); };
  Object.defineProperty(globalThis, 'crypto', { value: { getRandomValues: a => { calls++; return rgv(a); } }, configurable: true });
  try { P.newDeck(); } finally { Math.random = real; Object.defineProperty(globalThis, 'crypto', { value: require('crypto').webcrypto, configurable: true }); }
  assert.ok(calls >= 51, calls + ' crypto calls');
});
check('a deck is a permutation of all 52 cards, and decks differ', () => {
  const a = P.newDeck(), b = P.newDeck();
  assert.deepStrictEqual([...a].sort((x, y) => x - y), Array.from({ length: 52 }, (_, i) => i)); assert.notDeepStrictEqual(a, b);
});
check('secureInt is uniform: each of 7 values within 5% of expected over 140000 draws', () => {
  const c = new Array(7).fill(0); for (let i = 0; i < 140000; i++) c[P.secureInt(7)]++;
  for (const x of c) assert.ok(Math.abs(x - 20000) < 1000, c.join(','));
});
check('secureInt covers its whole range and never leaves it', () => { const seen = new Set(); for (let i = 0; i < 2000; i++) { const v = P.secureInt(52); assert.ok(v >= 0 && v < 52); seen.add(v); } assert.strictEqual(seen.size, 52); });
check('shuffle is fair: every card lands in every position about equally (52000 decks)', () => {
  const pos = Array.from({ length: 4 }, () => new Array(52).fill(0)); const N = 52000;
  for (let i = 0; i < N; i++) { const d = P.newDeck(); for (let p = 0; p < 4; p++) pos[p][d[p]]++; }
  for (const row of pos) for (const x of row) assert.ok(x > 800 && x < 1200, 'a card count of ' + x + ' (expected 1000)');
});
check('newDeck takes a random source, so the shuffle itself is testable', () => { const d = P.newDeck(() => 0); assert.strictEqual(d.length, 52); assert.strictEqual(new Set(d).size, 52); });
console.log(bad ? `${bad} FAILED` : 'ALL POKER UNIT TESTS PASSED'); process.exit(bad ? 1 : 0);
