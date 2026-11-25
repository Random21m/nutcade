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
// (cashu-ts 5 refuses to encode a coin whose DLEQ lacks its r, NUT-12: such a DLEQ, which no receiver can check, is left off the
// coin, as the library itself drops it when it decodes one; everything else on the coin goes as it is)
const tokDleq = t => t && Array.isArray(t.proofs) && t.proofs.some(p => p && p.dleq && !p.dleq.r) ? Object.assign({}, t, { proofs: t.proofs.map(p => p && p.dleq && !p.dleq.r ? Object.assign({}, p, { dleq: undefined }) : p) }) : t;
const tokEnc = (t, ...r) => L.getEncodedToken(tokDleq(t && typeof t.mint === 'string' && UNIT_RE.test(t.mint) ? Object.assign({}, t, { mint: acctUrl(t.mint), unit: acctUnit(t.mint) }) : t), ...r);

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
// any ecash at all, in any unit (what decides whether a new phrase, a restore, an import or a reset has money to look after;
// totalBalance() is SAT only)
const anyBalance = () => Object.keys(S.proofs || {}).some(k => sum(S.proofs[k]) > 0);
const otherHeld = () => Object.keys(S.proofs || {}).some(k => !isSatAcct(k) && sum(S.proofs[k]) > 0);
// totals of a list, one per unit ({ sat: 1200, usd: 150 }): never one number across units
function perUnit(list, amt = x => x.amount, unit = x => txUnit(x)) { const t = {}; for (const x of list || []) { const u = unit(x), n = num(amt(x)); if (n) t[u] = (t[u] || 0) + n; } return t; }
const addUnit = (t, u, n) => { if (num(n)) t[u] = (t[u] || 0) + num(n); return t; };
// "1,200 SAT · 1.50 USD" (SAT alone reads exactly as money() always has); nothing at all reads as 0 SAT
function moneyList(t, sep = ' · ') { const ps = UNIT_LIST.filter(u => num(t && t[u])).map(u => moneyU(t[u], u)); return ps.length ? ps.join(sep) : money(0); }
const listEmpty = t => !UNIT_LIST.some(u => num(t && t[u]));
// what this wallet holds, unit by unit
const heldMoney = () => moneyList(Object.fromEntries(unitTotals()));
// every mint address once (a mint's USD account is the same mint as its SAT account): what is written down or published
const mintAddrs = () => [...new Set(S.mints.map(m => acctUrl(m.url)))];
// a mint address that came from outside (a token, a payment, a request, another service): an address only, never an
// account key. An address with '|' in it is refused, so "https://m|usd" can never name an account here.
function extUrl(u) { const s = normUrl1(u); if (s.includes('|')) throw Object.assign(new Error("This mint address isn't valid."), { keep: true }); return s; }
const extUrlOr = u => { try { return extUrl(u); } catch (e) { return null; } };
// a token in a unit NUTCADE doesn't hold is refused before anything is saved or claimed
const unitErr = u => Object.assign(new Error(`This token is in ${unitCode(u)}. NUTCADE holds SAT, USD, EUR and CHF.`), { keep: true });
// the keysets of the USD, EUR and CHF accounts (wallet sync never publishes their counters or their coins)
function unitKsIds() {
  const ids = new Set(), add = ps => { for (const p of ps || []) if (p && p.id) ids.add(p.id); };
  for (const k of Object.keys(S.proofs || {})) if (!isSatAcct(k)) add(S.proofs[k]);
  for (const k of Object.keys(S.mintkeys || {})) if (!isSatAcct(k)) for (const id of Object.keys(S.mintkeys[k] || {})) ids.add(id);
  for (const k of Object.keys(wallets)) if (!isSatAcct(k)) { try { for (const ks of wallets[k].ready.keyChain.getKeysets()) ids.add(ks.id); } catch (e) {} }
  for (const t of S.txs) if (!isSatAcct(t.mint)) add(t.sent);
  for (const p of S.pending) if (!isSatAcct(p.mint)) add(p.proofs);
  return ids;
}
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
// a list of mints to scan (restore, sweep): each address also stands for every other unit account it offers, added to the
// list in place; its SAT account is left out when the mint issues no SAT and none is held here (a scan of it can't load)
// A mint that can't say which units it issues (asked twice) is named in `miss`: its accounts already held here are still
// scanned, its other units are not, and the screen says so.
async function unitAccounts(list, miss) {
  for (const u of [...list]) if (isSatAcct(u)) {
    let us = null;
    for (let i = 0; i < 2 && !us; i++) { try { us = await mintUnits(u); } catch (e) { if (!i) await sleep(800); } }
    if (!us) { for (const m of S.mints) if (acctUrl(m.url) === u && !isSatAcct(m.url) && !list.includes(m.url)) list.push(m.url); if (miss) miss.push(host(u)); continue; }
    for (const x of us) { const k = acctKey(u, x); if (x !== 'sat' && !list.includes(k)) list.push(k); }
    if (us.length && !us.includes('sat') && !S.mints.find(m => m.url === u)) list.splice(list.indexOf(u), 1);
  }
  return list;
}
// the screen's line for mints that couldn't say which units they issue (restore, sweep)
const unitMissHTML = miss => miss.length ? miss.map(h => `<div class="notice red">Couldn't ask ${esc(h)} which units it issues, so only its SAT ecash and the accounts you already hold there were scanned. Try again later.</div>`).join('') : '';
// an account's name in a list: the mint's address, and its unit when it isn't SAT
const acctHost = k => host(k) + (isSatAcct(k) ? '' : ' · ' + unitCode(acctUnit(k)));
// an account a scan added only to look in it (USD, EUR or CHF), with nothing of it held, recorded or in flight: it goes
// again, whether the scan found nothing or failed. (A SAT account a restore adds stays, as before 1.31: Find lost ecash
// scans it again later.)
function dropScanned(url) {
  if (isSatAcct(url) || !S.mints.find(m => m.url === url) || balanceOf(url) || S.txs.some(t => t.mint === url) || S.pending.some(p => p.mint === url) || S.ops.some(o => o.mint === url) || S.quotes.some(q => q.mint === url)) return false;
  S.mints = S.mints.filter(m => m.url !== url); delete S.proofs[url]; if (S.active === url) S.active = S.mints[0] ? S.mints[0].url : null; save();
  return true;
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
   Everything beyond Lightning and ecash counts in SAT, so these start nothing from another unit's account: they say so and
   spend nothing. The click dispatcher in app.js checks this list before any of them runs, against the account the action
   acts on (its button's own mint, data-from or data-url, else the account in use), so a step on a SAT record (taking back
   a printed token, cashing out an Extra Life, claiming a nutzap) or a SAT-only setting (the spending limit, wallet sync,
   the Lightning address) works whichever account is in use. Their buttons are also left out of the screens, so the message
   is a backstop, not the normal way to meet them. */
const SAT_ACTS = new Set([
  'allEcash', 'allOnchain', 'doOnchainAddr',                                     // Send all, on-chain
  'cashier', 'splitOpen', 'splitCreate',                                          // cashier mode, bill split
  'extraOpen', 'extraStart',                                                      // a new Extra Life
  'huntNew', 'huntCreate',                                                        // a new treasure hunt
  'ptOpen', 'ptMake',                                                             // new printed tokens
  'chalSend', 'chalSendOpen',                                                     // challenges with sats on them
  'nzSend',                                                                       // sending a nutzap
  'zapOpen', 'zapQuote', 'zapContact', 'lnurlQuote', 'lnurlAll', 'lnurlwGo',       // zaps, LNURL
  'moveOpen', 'swapToken',                                                       // moving sats between mints (moveQuote picks SAT mints only)
  'ctPlay',                                                                       // send by sound
  'contactEcash', 'contactLn', 'payContact',                                      // paying a contact (sats over Nostr)
  'tipQuote',                                                                     // the tip jar
  'duressMake'                                                                    // the duress PIN's wallet is funded in SAT
]);
// the account an action acts on: its button's own mint when it names one held here, else the account in use
function actAcct(b) {
  const d = (b && b.dataset) || {};
  for (const v of [d.from, d.url]) { if (!v) continue; const k = normUrl(v); if (S.mints.some(m => m.url === k)) return k; }
  return S.active;
}

// (tests: the units table and the pieces around it, so a check can read exactly what the app uses)
window.NutUnits = {
  table: () => JSON.parse(JSON.stringify(UNITS)), list: () => UNIT_LIST.slice(),
  fmt: (n, u) => fmtU(n, u), money: (n, u) => moneyU(n, u), code: u => unitCode(u),
  parse: (v, u) => { try { return parseUnitAmt(v, u); } catch (e) { return { error: e.message, why: e.amount || null }; } },
  key: (url, u) => acctKey(normUrl(url), u), url: k => acctUrl(k), unit: k => acctUnit(k),
  totals: () => unitTotals(), accounts: () => S.mints.map(m => ({ url: m.url, unit: acctUnit(m.url), unitField: m.unit || null, units: m.units || [], bal: balanceOf(m.url), name: m.name })),
  satOnly: a => SAT_ACTS.has(a), mintUnits: u => mintUnits(u), invoiceSats: i => invoiceSats(i),
  satTotal: () => totalBalance(), any: () => anyBalance(), held: () => heldMoney(), addrs: () => mintAddrs(),
  payload: (p, from) => receivePayload(p, from),   // (a NUT-18 payment as it arrives over Nostr)
  nwc: async () => { const c = { id: 'units-test', seeAll: true }; return { list: (await NWC.list_transactions(c, { unpaid: true })).transactions, balance: (await NWC.get_balance(c)).balance }; },
  nwcPay: async inv => { const c = { id: 'units-test', seeAll: true }; try { return { ok: await NWC.pay_invoice(c, { invoice: inv }) }; } catch (e) { return { code: e.nwc || null, msg: e.message }; } },
  nwcLookup: async inv => { const c = { id: 'units-test', seeAll: true }; try { return { ok: await NWC.lookup_invoice(c, { invoice: inv }) }; } catch (e) { return { code: e.nwc || null, msg: e.message }; } },
  lockPub: () => myLockPub(),
  bounty: async (tok, amount) => { const r = await readBounty({ token: tok, amount }, { game: 'units-test' }); return r ? { amount: r.amount, mint: r.mint } : null; },
  heir: async tok => { const was = S.heirlooms.slice(), f = 'f'.repeat(64); await onExtraLife({ t: 'nutcade-extralife', token: tok }, f); const h = S.heirlooms.find(x => x.from === f); S.heirlooms = was; saveHeir(); return h ? { amount: h.amount, mint: h.mint } : null; },
  inspect: async u => { const l = await inspectMint(u); return { ksTotal: l.ksTotal, noted: Object.keys(l.keysets).length, news: (l.changes || []).filter(c => c.kind === 'new').length, keys: (reportCard(u).rows.find(r => r.k === 'Keys') || {}).g }; },
  syncWant: () => { const w = syWalletWant(null); return { counters: w.cs.map(([id]) => id), gone: w.gone.length, mints: w.mints, unitKs: [...unitKsIds()] }; }
};
