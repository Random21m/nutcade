/* ---------- units (1.31): sat, and USD, EUR and CHF ecash ----------
   The units table is here and nowhere else. Every amount is an integer in its unit's smallest step (SAT; cents for USD, EUR
   and CHF), never a float: "12.50" typed for USD is read as the integer 1250, and amounts in different units are never
   added together or compared.
   An account is one unit at one mint. A SAT account is keyed by the mint's address exactly as before 1.31 (so old wallets
   and backups load unchanged); any other unit is keyed "<mint address>|usd" (S.mints entry with that url and unit: 'usd',
   S.proofs under that key, every record that names it: history, payments in flight, deposits, journal steps). The key is
   never sent anywhere: getWallet talks to the real address with the unit's own keysets (cashu-ts Wallet { unit }), tokens
   carry the real address and the unit (tokEnc), and a request built from a key by mistake fails loudly (the '|' makes it
   an address that doesn't resolve) instead of reaching the mint as SAT.
   Only SAT has the extras: wallet sync, nutzaps, gifts, bounties, printed tokens, Extra Life, treasure hunts, zaps, LNURL,
   Wallet Connect, on-chain, Send all, cashier mode, bill split, send by sound, challenges, the piggy bank, the spending
   limit, the mint report card and the price in your currency. With another unit active they say so and spend nothing. */
const UNITS = { sat: { dp: 0, code: 'SAT' }, usd: { dp: 2, code: 'USD' }, eur: { dp: 2, code: 'EUR' }, chf: { dp: 2, code: 'CHF' } };
const UNIT_LIST = ['sat', 'usd', 'eur', 'chf'];
const UNIT_RE = /\|(usd|eur|chf)$/;
const unitOk = u => Object.prototype.hasOwnProperty.call(UNITS, u);
const acctUnit = k => { const m = UNIT_RE.exec(String(k || '')); return m ? m[1] : 'sat'; };
const acctUrl = k => String(k || '').replace(UNIT_RE, '');
const acctKey = (url, unit) => !unit || unit === 'sat' ? url : url + '|' + unit;
const isSatAcct = k => acctUnit(k) === 'sat';
const unitDp = u => (UNITS[u] || UNITS.sat).dp;
const unitCode = u => unitOk(u) ? UNITS[u].code : String(u || '').toUpperCase().slice(0, 8);
const txUnit = t => (t && unitOk(t.unit) && t.unit) || acctUnit(t && t.mint);
// one spelling per account: the address as normUrl1 spells it, then the unit (lowercase) for a non-SAT account
const normUrl = u => { const s = String(u ?? '').trim(); const m = /\|(usd|eur|chf)$/i.exec(s); return m ? normUrl1(s.slice(0, m.index)) + '|' + m[1].toLowerCase() : normUrl1(s); };
// a token for an account: the real address and the account's unit (any record's key works: SAT keys pass unchanged)
const tokEnc = (t, ...r) => L.getEncodedToken(t && typeof t.mint === 'string' && UNIT_RE.test(t.mint) ? Object.assign({}, t, { mint: acctUrl(t.mint), unit: acctUnit(t.mint) }) : t, ...r);

/* ---------- showing amounts: one formatter that knows the unit ---------- */
// "12.50" (12,50 in German): the whole part grouped as the language does, then exactly the unit's decimals; SAT as fmt()
function fmtU(n, unit) {
  const dp = unitDp(unit); if (!dp) return fmt(n);
  if (maskAmounts) return '•••';
  const v = Math.round(num(n)), a = Math.abs(v), d = 10 ** dp;
  return (v < 0 ? '-' : '') + Math.floor(a / d).toLocaleString(numLocale(), { useGrouping: 'always' }) + decMark() + String(a % d).padStart(dp, '0');
}
const fmtUEn = (n, unit) => { const dp = unitDp(unit); if (!dp) return String(Math.round(num(n))); const v = Math.round(num(n)), a = Math.abs(v), d = 10 ** dp; return (v < 0 ? '-' : '') + Math.floor(a / d) + '.' + String(a % d).padStart(dp, '0'); };
// the small label after a big number: SAT (or nothing with the ₿ symbol), USD, EUR, CHF
const unitTagU = unit => !unit || unit === 'sat' ? unitTag() : unitCode(unit);
// "1,000 SAT" (₿1,000), "12.50 USD": the amount first, like SAT, so every sentence written for "{#} SAT" reads the same
const moneyU = (n, unit) => !unit || unit === 'sat' ? money(n) : fmtU(n, unit) + ' ' + unitCode(unit);
const moneyAt = (url, n) => moneyU(n, acctUnit(url));
const arrMoneyU = (n, unit) => { const was = maskAmounts; maskAmounts = !!S.prefs.hideAmounts; try { return moneyU(n, unit); } finally { maskAmounts = was; } };
const unitChip = unit => unit && unit !== 'sat' ? `<span class="chip unit" data-noi18n>${esc(unitCode(unit))}</span>` : '';
// a mint and its unit, as a name: "Multi Mint" for SAT, "Multi Mint · USD"
const acctName = m => !m ? '' : m.name + (isSatAcct(m.url) ? '' : ' · ' + unitCode(acctUnit(m.url)));

/* ---------- typed amounts in a unit with decimals ---------- */
// The amount as an integer in cents: "12.50" -> 1250, "0.01" -> 1, "12" -> 1200; "12.505" is refused (more than 2 decimals),
// never rounded. Read with the same rules as amounts in your currency (parseFiatText: your language's decimal mark).
function parseUnitAmt(v, unit) {
  const dp = unitDp(unit); if (!dp) return parseSat(v);
  const s = String(v ?? '').trim(); if (!s) return 0;
  let t; try { t = parseFiatText(s); } catch (e) { throw amtErr(`That amount can't be read. Type it like this: ${fmtU(1250, unit)}`, 'unreadable'); }
  const [w, f0 = ''] = t.split('.'), f = f0.replace(/0+$/, '');
  if (f.length > dp) throw amtErr(`${unitCode(unit)} amounts have at most 2 decimals (cents). Type it like this: ${fmtU(1250, unit)}`, 'decimal');
  const n = Number(w) * 10 ** dp + Number(f.padEnd(dp, '0') || 0);
  if (!Number.isSafeInteger(n) || n > 1e15) throw amtErr('That amount is too large. Type a smaller amount.', 'large');
  return n;
}
// an amount field for the active account: SAT as always (with the switch to your currency), any other unit typed as it is
function amtField(id, label, ph, unit = acctUnit(S.active), extra = '') {
  if (unit === 'sat') return `<label for="${id}">${label.replace('{U}', 'SAT')}</label>${extra}<input id="${id}" class="inp amount" inputmode="numeric" placeholder="${ph}" autocomplete="off">`;
  return `<label for="${id}">${label.replace('{U}', unitCode(unit))}</label>${extra}<input id="${id}" class="inp amount" data-unit="${unit}" inputmode="decimal" placeholder="${fmtUEn(1250, unit)}" autocomplete="off">`;
}

/* ---------- accounts ---------- */
const satMints = () => S.mints.filter(m => isSatAcct(m.url));
// every unit's total, never added across units: [[unit, total]] in table order, units held only
function unitTotals() {
  const t = {}; for (const m of S.mints) { const u = acctUnit(m.url); t[u] = (t[u] || 0) + balanceOf(m.url); }
  return UNIT_LIST.filter(u => u in t).map(u => [u, t[u]]);
}
const heldAny = () => S.mints.some(m => balanceOf(m.url) > 0);
// the units a mint's wallet offers (its keysets, active or not), those NUTCADE holds, in table order
function unitsOfWallet(w) {
  try { const ks = Object.values((w.keyChain && w.keyChain.keysets) || {}); const us = new Set(ks.map(k => k && k.unit)); return UNIT_LIST.filter(u => us.has(u)); } catch (e) { return []; }
}
// the units a mint offers, asked from it directly (when it has no SAT keyset, a SAT wallet can't load it)
async function mintUnits(url) {
  const r = await fetch(acctUrl(normUrl(url)) + '/v1/keysets'); if (!r.ok) throw new Error(`The mint answered ${r.status}.`);
  const j = await r.json(); const us = new Set(((j && j.keysets) || []).map(k => k && k.unit));
  return UNIT_LIST.filter(u => us.has(u));
}
// the accounts at one mint, SAT first
const acctsAt = url => { const u = acctUrl(url); return S.mints.filter(m => acctUrl(m.url) === u).sort((a, b) => UNIT_LIST.indexOf(acctUnit(a.url)) - UNIT_LIST.indexOf(acctUnit(b.url))); };

/* ---------- SAT only ---------- */
const SAT_ONLY_MSG = 'This works with SAT only. Pick a SAT mint first (MINTS tab). Nothing was spent.';
const satOnlyErr = () => Object.assign(new Error(SAT_ONLY_MSG), { keep: true, satOnly: true });
// true (and says so) when the account in use isn't SAT
function notSat(url = S.active) { if (!url || isSatAcct(url)) return false; sfx('err'); toast(SAT_ONLY_MSG, 'gold'); return true; }

/* ---------- Lightning invoices: the amount the invoice itself states (never a conversion of ours) ---------- */
// SAT, rounded up to the whole SAT (an invoice can ask for millisats); null when the invoice states no amount
function invoiceSats(inv) {
  const m = /^ln(?:bcrt|bc|tbs|tb)(\d+)([munp]?)1/i.exec(String(inv || '').trim()); if (!m) return null;
  const msat = BigInt(m[1]) * ({ '': 100000000000n, m: 100000000n, u: 100000n, n: 100n, p: 1n }[m[2].toLowerCase()]) / (m[2].toLowerCase() === 'p' ? 10n : 1n);
  return Number((msat + 999n) / 1000n);
}

/* ---------- the mint list: a mint's accounts together, each its own line ---------- */
// every account, grouped by mint address (the order the mints were added), SAT first inside a mint
function mintOrder() {
  const out = [], seen = new Set();
  for (const m of S.mints) { const u = acctUrl(m.url); if (seen.has(u)) continue; seen.add(u); out.push(...acctsAt(m.url)); }
  return out;
}
// under a mint's last account line: the units it offers that NUTCADE doesn't hold yet, each added on its own
function unitAddRow(m) {
  const at = acctsAt(m.url); if (at[at.length - 1] !== m) return '';   // (once per mint, under its last line)
  const have = new Set(at.map(x => acctUnit(x.url)));
  const more = (m.units || []).filter(u => unitOk(u) && !have.has(u));
  if (!more.length) return '';
  return `<div class="row" style="flex-wrap:wrap;gap:6px" data-unitadd><span class="tiny muted">Also at this mint:</span>${more.map(u => `<button class="btn sm lime" data-act="addUnit" data-url="${esc(acctUrl(m.url))}" data-u="${esc(u)}">Add ${esc(unitCode(u))}</button>`).join('')}</div>`;
}

/* ---------- the SAT-only entry points ----------
   Everything beyond Lightning and ecash counts in SAT, so with another unit's account in use these do nothing and say so
   (the click dispatcher in app.js checks this list before any of them runs, so nothing is ever half-done in the wrong unit).
   Their buttons are also left out of the screens, so the message is a backstop, not the normal way to meet them. */
const SAT_ACTS = new Set([
  'allEcash', 'allOnchain', 'doOnchainAddr',                                     // Send all, on-chain
  'cashier', 'tillOpen', 'tillCsv', 'splitOpen', 'splitCreate', 'splitShow',      // cashier mode, bill split
  'extraOpen', 'extraStart', 'extraContinue', 'extraCash', 'extraCashGo', 'extraCopy',   // Extra Life
  'huntNew', 'huntCreate', 'huntCards', 'huntPrint', 'huntShow', 'huntOpen',      // treasure hunts
  'ptOpen', 'ptMake', 'ptPrint', 'ptReprint', 'ptTake', 'ptTakeAll', 'ptNext', 'ptCheck',   // printed tokens
  'chalSend', 'chalSendOpen', 'chalQR',                                           // challenges with sats on them
  'nzSend', 'nzClaim', 'nzRetry',                                                 // nutzaps
  'zapOpen', 'zapQuote', 'zapContact', 'lnurlQuote', 'lnurlAll', 'lnurlwGo',       // zaps, LNURL
  'nwcNew', 'nwcCreate',                                                          // Wallet Connect
  'moveOpen', 'moveQuote', 'swapToken',                                           // moving sats between mints
  'piggyEmpty', 'piggyEmptyGo', 'limOpen', 'limSave',                             // piggy bank, spending limit
  'ctListen', 'ctPlay',                                                           // send by sound
  'syncNow', 'syncAddMint', 'syncRestoreOn',                                      // wallet sync
  'myAddrQR', 'contactEcash', 'contactLn', 'payContact', 'sendFrom',              // contacts (sats over Nostr)
  'lnAddrOn', 'lnAddrMint', 'lnAddrSync', 'tipQuote',                             // Lightning address, the tip jar
  'duressMake'                                                                    // the duress PIN's wallet is funded in SAT
]);

// (tests: the units table and the pieces around it, so a check can read exactly what the app uses)
window.NutUnits = {
  table: () => JSON.parse(JSON.stringify(UNITS)), list: () => UNIT_LIST.slice(),
  fmt: (n, u) => fmtU(n, u), money: (n, u) => moneyU(n, u), code: u => unitCode(u),
  parse: (v, u) => { try { return parseUnitAmt(v, u); } catch (e) { return { error: e.message, why: e.amount || null }; } },
  key: (url, u) => acctKey(normUrl(url), u), url: k => acctUrl(k), unit: k => acctUnit(k),
  totals: () => unitTotals(), accounts: () => S.mints.map(m => ({ url: m.url, unit: acctUnit(m.url), unitField: m.unit || null, units: m.units || [], bal: balanceOf(m.url), name: m.name })),
  satOnly: a => SAT_ACTS.has(a), mintUnits: u => mintUnits(u), invoiceSats: i => invoiceSats(i)
};
