/* ===================== Trust & help: checking your 12 words, update notices, Help & FAQ, mint details, hiding amounts =====================
   None of this moves money. It reads and writes display settings only (hideAmounts, seenVersion on the device; backupFileAt and
   phraseCheck inside the wallet), and it never asks a server anything: the one request it makes is for this site's own page. */
const TRUST_DAY = 86400e3;

/* ---------- hide amounts ----------
   Tapping the balance (or the eye beside it) flips S.prefs.hideAmounts, which belongs to this device. render() sets maskAmounts
   only while it writes the wallet, notes, mints and settings screens, so fmt() reads ••• there. A sheet (a payment, a token, a
   confirmation) is drawn outside that window and always shows the real amount. */
const EYE_ON = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M1 8c2-3.5 4.5-5 7-5s5 1.5 7 5c-2 3.5-4.5 5-7 5S3 11.5 1 8zm7-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm0 1.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z"/></svg>';
const EYE_OFF = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M1 8c2-3.5 4.5-5 7-5s5 1.5 7 5c-2 3.5-4.5 5-7 5S3 11.5 1 8zm7-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/><path d="M2 13.5L13.5 2l1 1L3 14.5z"/></svg>';
const hideBtn = () => `<button class="lockbtn" data-act="hideToggle" aria-pressed="${S.prefs.hideAmounts ? 'true' : 'false'}" aria-label="${S.prefs.hideAmounts ? 'Show amounts' : 'Hide amounts'}" title="${S.prefs.hideAmounts ? 'Show amounts' : 'Hide amounts'}">${S.prefs.hideAmounts ? EYE_OFF : EYE_ON}</button>`;

/* ---------- is a money step open? ----------
   The reload offer never appears (and a tap on it does nothing) while anything is in flight: a payment, a journaled step, a
   deposit being collected, a backup's waiting part, a restore scan, the till, a game, or any open sheet (a Send screen with
   an amount typed in, a confirmation). Nothing here reloads by itself: only a tap does, and only when this says no. */
function moneyBusy() {
  return !!($('#layer .sheet') || (cash && cash.el) || (window.Arcade && window.Arcade.playing())
    || (S.ops || []).length || (S.pending || []).length || (S.imports || []).length || (S.oplate || []).length
    || (S.quotes || []).some(q => quoteBusy(q)) || flights.size || busyQuotes.size);
}

/* ---------- checking your 12 words ----------
   Offered a week after the backup, then about twice a year. You type three words from your paper; they are compared here, on
   this phone, with the phrase already in the wallet. They are never shown, saved or sent. */
const PHRASE_FIRST = 7 * TRUST_DAY, PHRASE_AGAIN = 182 * TRUST_DAY, PHRASE_LATER = 7 * TRUST_DAY;
const phraseCheckOf = () => S.prefs.phraseCheck || {};
function phraseDue() {
  const pc = phraseCheckOf();
  if (pc.off || !S.seed || !S.seed.backedUp) return false;
  const base = num(S.seed.created); if (!base && !pc.next) return false;
  return Date.now() >= (pc.next || base + PHRASE_FIRST);
}
function setPhraseCheck(patch) { S.prefs.phraseCheck = Object.assign({}, phraseCheckOf(), patch); save(); }
function openPhraseCheck() {
  if (!S.seed) return;
  const pick = pickWords();
  openSheet('Check your 12 words', `
    <p style="margin:0">Type these words from your paper copy, not from memory.</p>
    <div class="tiny muted">This check happens on this phone only. Your words are not shown, saved or sent anywhere.</div>
    ${pick.map(i => `<div class="field"><label for="pw${i}">Word #${i + 1}</label><input id="pw${i}" class="inp" data-pw="${i}" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" data-noi18n></div>`).join('')}
    <div id="sheetErr"></div>
    <button class="btn solid gold block" data-act="pwCheck">Check</button>
    <div class="row wrap" style="justify-content:center"><button class="linkbtn" data-act="seedShow">Show the words again</button><button class="linkbtn" data-act="pwLater">Not now</button></div>
    <button class="linkbtn" data-act="pwOff" style="justify-self:center">Don't remind me again</button>`);
}
function backupHealth() {
  const pc = phraseCheckOf();
  return `<div class="row between tiny"><span>12 words last checked</span><span style="color:${pc.done ? 'var(--lime)' : 'var(--gold)'}">${pc.done ? esc(timeAgo(pc.done).toUpperCase()) : 'NEVER'}</span></div>
      <button class="btn sm" data-act="pwOpen">Check my 12 words</button>`;
}
function backupFileRow() {
  const at = S.prefs.backupFileAt;
  return `<div class="row between tiny"><span>Last backup file</span><span style="color:${at ? 'var(--lime)' : 'var(--gold)'}">${at ? esc(timeAgo(at).toUpperCase()) : 'NEVER'}</span></div>
      <p class="th" style="margin:0">A backup file only holds what your wallet held on the day you made it.</p>`;
}

/* ---------- "Updated to vX" and "new version ready" ----------
   seenVersion is the last version this device told you about. After an update NUTCADE says so once, with what's new and a link
   to the release page and its signed checksums. A tab that stays open for days looks, now and then, at this site's own page
   (the same file the app was loaded from: no server, nothing sent) and, when it names a newer version, offers a reload that
   waits until no money step is open. */
const WHATS_NEW = [   // (v1.30.0, with the v1.29.0 items; rewrite this list at every release)
  'New, optional and off by default: Sync this wallet across devices (Settings, Privacy) keeps your coins the same on every device with your 12 words and the switch on, through your Nostr relays, encrypted. Each mint checks every coin before it counts.',
  'Relays can see how many sync events you publish, how big they are and when: use your own relays if you can. It doesn\'t work with other wallets\' sync.',
  'Restoring from your 12 words tells you when wallet sync was on for them, and asks before turning it on here.',
  'New, optional and off by default: Hide who gets it (P2BK, Settings, Privacy) hides the receiver\'s key in the gifts and bounties you send. Turn it on only if their wallet supports it (NUTCADE 1.29 or newer does). Nutzaps are never hidden.',
];
let newVer = null, verCheckedAt = 0, verBusy = false;
const verParts = v => String(v || '').split(/[.-]/).slice(0, 3).map(x => parseInt(x, 10) || 0);
function verNewer(a, b) { const x = verParts(a), y = verParts(b); for (let i = 0; i < 3; i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); } return false; }
function whatsNewDue() { return !!(S.seed && S.seed.backedUp && S.prefs.seenVersion !== APP_VERSION); }
function seenNow() { if (S.prefs.seenVersion !== APP_VERSION) { S.prefs.seenVersion = APP_VERSION; save(); } }
// a brand-new install has nothing to be told about; an existing wallet meeting this feature for the first time does
function trustBoot() { if (S.prefs.seenVersion === undefined && !S.seed && !vault.on) { S.prefs.seenVersion = APP_VERSION; save(); } }
async function checkNewVersion(manual) {
  if (verBusy || tabLocked || (!manual && (document.hidden || !navigator.onLine))) return null;
  if (!/^https?:$/.test(location.protocol)) return null;
  verBusy = true; verCheckedAt = Date.now();
  const ac = new AbortController(), tm = setTimeout(() => ac.abort(), 15000);
  try {
    const r = await fetch('index.html', { cache: 'no-store', credentials: 'omit', signal: ac.signal });
    if (!r.ok) return null;
    const m = /const APP_VERSION = '(\d+\.\d+\.\d+)'/.exec(await r.text());
    if (!m) return null;
    newVer = verNewer(m[1], APP_VERSION) ? m[1] : null;
    if (newVer && !$('#layer .sheet') && tab === 'wallet' && !moneyBusy()) refresh();
    return newVer || false;
  } catch (e) { return null; }
  finally { clearTimeout(tm); verBusy = false; }
}
setInterval(() => { if (!document.hidden && !tabLocked && S.seed && Date.now() - verCheckedAt > 6 * 3600e3) checkNewVersion(); }, 10 * 60e3);
document.addEventListener('visibilitychange', () => { if (!document.hidden && !tabLocked && S.seed && Date.now() - verCheckedAt > 6 * 3600e3) setTimeout(() => checkNewVersion(), 2000); });
function trustNotices() {
  if (!S.seed || !S.seed.backedUp) return '';
  const out = [];
  if (whatsNewDue()) out.push(`<div class="notice cyan row between" style="flex-wrap:wrap" role="status"><span>Updated to v${esc(APP_VERSION)}</span><span class="row" style="gap:8px"><button class="btn sm" data-act="whatsNew">What's new</button><button class="btn sm" data-act="whatsNewDone">OK</button></span></div>`);
  if (newVer && !moneyBusy()) out.push(`<div class="notice cyan row between" style="flex-wrap:wrap" role="status"><span>New version v${esc(newVer)} is ready. Reload when you're done.</span><button class="btn sm" data-act="reloadNow">Reload now</button></div>`);
  if (phraseDue() && !moneyBusy()) out.push(`<div class="notice row between" style="flex-wrap:wrap" role="status"><span>Time to check your 12 words. It takes a minute and nothing leaves this phone.</span><span class="row" style="gap:8px"><button class="btn sm gold" data-act="pwOpen">Check now</button><button class="btn sm" data-act="pwLater">Later</button></span></div>`);
  return out.join('');
}
function openWhatsNew() {
  seenNow();
  const rel = `https://github.com/Random21m/nutcade/releases/tag/v${APP_VERSION}`;
  openSheet(`What's new in v${APP_VERSION}`, `
    <ul class="gate-list">${WHATS_NEW.map(x => `<li>${x}</li>`).join('')}</ul>
    <div class="tiny muted">Every release has signed checksums, so you can check that the files are the real ones.</div>
    <div class="row wrap"><a class="btn sm" href="${esc(rel)}" target="_blank" rel="noopener noreferrer">Release page on GitHub</a><a class="btn sm" href="SHA256SUMS.txt" target="_blank" rel="noopener">Checksums</a></div>
    <button class="btn block" data-act="close">Done</button>`);
  render();
}
function updatePanel() {
  return `${newVer ? `<div class="notice cyan row between" style="flex-wrap:wrap"><span>New version v${esc(newVer)} is ready. Reload when you're done.</span><button class="btn sm" data-act="reloadNow">Reload now</button></div>` : ''}
      <div class="row wrap"><button class="btn sm" data-act="whatsNew">What's new</button><button class="btn sm" data-act="verCheck">Check for a new version</button></div>`;
}

/* ---------- storage safety: a wallet that can't be saved, storage filling up, and iPhone's Home Screen ----------
   saveHealth (app.js) notes every write of wallet data that failed. While anything is noted, the wallet screen says so in red
   with a way out (Try again, Download backup, and Find lost ecash as the recovery path), once per episode also as a toast; it
   goes away by itself when the writes work again. It looks the same with or without a PIN, in either wallet of the vault.
   Storage use is NUTCADE's own share of localStorage (every record's key and value, 2 bytes a character, kept up to date by
   each write: nothing is read back to measure it) against an assumed 5 MB, or the browser's own estimate when that is fuller.
   It is checked at start and a few seconds after writes, never on each one. 70% gives a soft warning, 90% a red one.
   On an iPhone or iPad where NUTCADE runs as a website (not from the Home Screen) and the wallet holds sats, a banner says
   Safari may delete it, with the steps; "Not today" hides it until tomorrow (a setting of this device). */
const STORE_CAP = 5 * 1024 * 1024;
let useLevel = 0, useEst = null, useEstAt = 0;
const useBytes = () => { let n = 0; for (const v of useSizes.values()) n += v; return n * 2; };
function usePct() {
  let r = useBytes() / STORE_CAP;
  if (useEst && useEst.quota > 0) r = Math.max(r, useEst.usage / useEst.quota);
  return Math.max(0, Math.min(100, Math.round(r * 100)));
}
async function useEstimate() {
  useEstAt = Date.now();
  try { if (navigator.storage && navigator.storage.estimate) { const e = await navigator.storage.estimate(); useEst = e && +e.quota > 0 ? { usage: +e.usage || 0, quota: +e.quota } : null; } } catch (e) { useEst = null; }
}
function useCheck() {
  const p = usePct(), lvl = p >= 90 ? 2 : p >= 70 ? 1 : 0;
  if (Date.now() - useEstAt > 10 * 60e3) useEstimate().then(() => { if ((usePct() >= 90 ? 2 : usePct() >= 70 ? 1 : 0) !== useLevel) useCheck(); }, () => {});
  if (lvl === useLevel) return lvl;
  useLevel = lvl;
  if (tab === 'wallet' && !(window.Arcade && window.Arcade.playing())) refresh();
  return lvl;
}
setTimeout(useCheck, 1500);
function saveHealthChanged() {
  if (saveBad() && !saveHealth.told) { saveHealth.told = true; toast("NUTCADE couldn't save your wallet: storage is full. Keep it open and read the notice on the wallet screen.", 'red'); sfx('err'); }
  if (!(window.Arcade && window.Arcade.playing())) refresh();
}
const useLine = () => `${(useBytes() / 1048576).toFixed(1)} MB / ${STORE_CAP / 1048576} MB (${usePct()}%)`;
function storageRow() {
  const p = usePct();
  return `<div class="row between tiny"><span>Storage used by NUTCADE</span><span style="color:${saveBad() || p >= 90 ? 'var(--red)' : p >= 70 ? 'var(--gold)' : 'var(--lime)'}">${useLine()}</span></div>`;
}
function storageNotice() {
  if (saveBad()) return `<div class="notice red" role="alert" data-storage="full" style="display:grid;gap:8px">
      <b>NUTCADE can't save your wallet.</b>
      <span>This browser's storage is full, so your newest coins and changes exist only on this screen. Don't close or reload NUTCADE.</span>
      <span class="tiny">Download a backup file now to keep a copy. Then free up space on this phone and tap Try again.</span>
      <span class="tiny">If NUTCADE closes before it can save, use Find lost ecash in Settings, Backup: your 12 words bring those coins back.</span>
      <div class="row wrap"><button class="btn sm red" data-act="saveRetry">Try again</button><button class="btn sm gold" data-act="backupDownload">Download backup</button></div></div>`;
  const p = usePct();
  if (p >= 90) return `<div class="notice red" role="status" data-storage="90" style="display:grid;gap:8px"><span>Storage for NUTCADE is ${p}% full.</span><span>Soon it may not be able to save your wallet. Download a backup file now, and free up space on this phone.</span><div class="row wrap"><button class="btn sm gold" data-act="backupDownload">Download backup</button></div></div>`;
  if (p >= 70) return `<div class="notice" role="status" data-storage="70" style="display:grid;gap:8px"><span>Storage for NUTCADE is ${p}% full.</span><span>Download a backup file now and then to keep a copy.</span><div class="row wrap"><button class="btn sm gold" data-act="backupDownload">Download backup</button></div></div>`;
  return '';
}
const isIOS = () => { try { return /iPhone|iPad|iPod/.test(navigator.userAgent || '') || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); } catch (e) { return false; } };
const isInstalled = () => { try { return navigator.standalone === true || matchMedia('(display-mode: standalone)').matches; } catch (e) { return false; } };
const homeHintDue = () => isIOS() && !isInstalled();
const homeHintHTML = () => `<div class="notice row between" role="status" data-home-hint style="flex-wrap:wrap"><span>Add NUTCADE to your Home Screen, or Safari may delete this wallet.</span><span class="row" style="gap:8px"><button class="btn sm gold" data-act="homeSteps">Show me how</button>${S.seed ? '<button class="btn sm" data-act="homeLater">Not today</button>' : ''}</span></div>`;
function homeBanner() {
  if (!homeHintDue() || !(totalBalance() > 0) || S.prefs.homeLater === new Date().toDateString()) return '';
  return homeHintHTML();
}
function openHomeSteps() {
  openSheet('Add to Home Screen', `
    <ol class="gate-list"><li>Open NUTCADE in Safari.</li>${S.seed ? '<li>In Settings, Backup, tap Download backup and keep the file.</li>' : ''}<li>Tap Share (the square with an arrow; on newer iOS, tap ••• first).</li><li>Tap Add to Home Screen, then Add.</li><li>From now on, open NUTCADE from the new icon.</li></ol>
    ${S.seed ? `<div class="notice">The new icon keeps a wallet of its own and starts empty. Open it, tick the box, tap Create a new wallet and finish its setup steps (its words are replaced when you import), then tap Import backup in Settings, Backup and choose the file. Your wallet comes back as it was in the file. Then use only the icon.</div>
    <div class="tiny muted">No backup file? Tap Restore from recovery phrase instead and enter your 12 words. That brings back the ecash made from your words at your mints, but not tokens still waiting to be claimed, locked ecash, ecash that didn't come from your words, or payments still in progress: settle those in Safari first.</div>` : '<div class="notice">Then set up your wallet from the new icon.</div>'}
    <div class="tiny muted">Safari can clear the storage of websites you have not opened in a while, but a Home Screen app keeps it.</div>
    <div class="row wrap"><a class="btn sm" href="https://github.com/Random21m/nutcade#get-nutcade-add-it-to-your-home-screen" target="_blank" rel="noopener noreferrer">Steps for every device</a></div>
    <button class="btn block" data-act="close">Done</button>`);
}

/* ---------- Help & FAQ ----------
   Plain words, offline, in the app's five languages (tools/i18n_trust.py). Every sentence is its own text, so it translates on
   its own. Other features can add topics with window.NutHelpTopics.push({ q, a: [paragraphs] }) before the Help sheet opens
   (the printed tokens' first-scan rule is meant to arrive this way); their text needs a row in the translation tool too. */
const HELP = [
  { q: 'What is NUTCADE?', a: [
    'NUTCADE is a wallet for Bitcoin, held as Cashu ecash, with an arcade built in. It runs in your browser.',
    'There is no account to make, and nobody at NUTCADE can see or touch your sats.'] },
  { q: 'What are ecash and a mint?', a: [
    'Ecash is money in the form of coins that sit on your device. A mint is a service that makes those coins and holds the Bitcoin behind them. You choose which mints to use.',
    'Anyone can run a mint, so only use mints you trust. A mint sees the coins you exchange with it.'] },
  { q: 'What if a mint closes or stops working?', a: [
    'Your sats are a promise from the mint. If it closes or stops working, the ecash you hold there may not be spendable any more, and NUTCADE cannot bring it back.',
    'So keep only what you can afford to lose at any one mint, and spread your sats over more than one. The Mints tab shows how each mint is doing, and its report card gives it a grade.',
    'While a mint works, you can move sats to another one: Settings, Wallet tools, Move sats between mints.'] },
  { q: 'What are my 12 words?', a: [
    'They are your recovery phrase, and the only way to get your sats back if this phone is lost or its browser data is cleared. NUTCADE does not keep a copy.',
    'Write them on paper, in order, and keep them offline. Never type them into a website, take a screenshot or send them to anyone, including anyone who says they are NUTCADE support.',
    'Also write down the mints you use. Restoring scans the mints you list.',
    'To practise, tap Check my 12 words in Settings, Backup. The check happens on this phone only.'] },
  { q: 'I have a new phone, or I lost mine', a: [
    'Open NUTCADE on the new device, tick the box and tap Restore from recovery phrase. Type your 12 words and tick the mints you used (Find my mints on Nostr can find them for you). NUTCADE scans those mints and rebuilds your balance.',
    'Your notes and history are not in your 12 words. They come back only from a backup file (Settings, Backup, Import backup).',
    'A backup file holds your phrase and all your coins, so anyone who has it can spend your sats. Keep it private.'] },
  { q: 'A payment looks stuck', a: [
    'Open Settings, Wallet tools and tap Check stuck payments. A Lightning payment that fails returns your sats. One that is still waiting is tracked until the mint settles it.',
    'If NUTCADE closes halfway through a step, it finishes or puts it right the next time you open it.',
    'If your balance looks too low, tap Find lost ecash in Settings, Backup. NUTCADE asks your mints for coins that belong to your 12 words and were never saved.'] },
  { q: "Why isn't ecash mine until it is claimed?", a: [
    'A token is like cash in an envelope: whoever claims it first gets it. It is yours only once your wallet has claimed it.',
    'When you send a token, it shows as pending until the other person claims it. While it is unclaimed you can take it back with Reclaim.',
    'Offline, ecash that people give you is saved and claimed when you are back online. Until then it is not yours yet.'] },
  { q: 'What do fees cost?', a: [
    'A mint may charge a small fee to spend coins, and Lightning payments have a network fee. NUTCADE shows the fee before you confirm.'] },
  { q: 'What do the PIN and the duress PIN do?', a: [
    'A PIN locks NUTCADE and keeps your phrase, ecash and notes encrypted on this device. It stops someone who picks up your phone. It cannot stop malware on a device that is already compromised. If you forget it, reset the wallet and restore with your 12 words.',
    'The duress PIN is a second PIN that opens a small, separate wallet instead of yours, for when someone makes you unlock NUTCADE. It helps against a person standing in front of you. It does not help against someone who studies your phone with the app\'s open code.',
    'Face ID or fingerprint opens your real wallet only, so turn it off if you rely on the duress PIN.'] },
  { q: 'Can I use it offline?', a: [
    'Open NUTCADE once while online and it keeps a copy, so it opens without a connection after that. Offline, you can send ecash for amounts made of the exact coins you hold.'] },
  { q: 'Hide my amounts', a: [
    'Tap your balance, or the eye button beside it, to show ••• instead of amounts on the wallet, notes and mints screens. It is remembered on this device.',
    'Payment screens always show the real amount, so you know what you are about to send.'] },
  { q: 'How do updates work?', a: [
    'NUTCADE updates itself: the next time you open it, it loads the new version, and a note tells you what changed.',
    'If you keep it open for days, a message says when a new version is ready. Reload when you are done: NUTCADE never reloads by itself, and never offers it in the middle of a payment.'] },
  { q: 'Keeping your wallet safe', a: [
    'The only real address is https://random21m.github.io/nutcade/. Anything else that calls itself NUTCADE is not us.',
    'On iPhone, add NUTCADE to your Home Screen. Safari can clear the storage of websites you have not opened in a while, but a Home Screen app keeps it.',
    'Set a PIN, keep your 12 words offline, and start with small amounts: NUTCADE is young software that has not been independently audited.'] },
  { q: 'What does NUTCADE contact? (Privacy)', a: [
    'NUTCADE has no account, no tracking, no analytics and no ads. It contacts these services, and only for the reason given:'], ul: [
    'Your mints: for every payment, to check that they answer, and to read their name and contact details. A mint sees the coins you exchange with it.',
    'The mints in the Add mint list (Minibits, Cuba Bitcoin, 8333.space and two test mints), only while that list is open, to show whether they answer.',
    'Nostr relays (relay.damus.io, nos.lol and relay.primal.net): for game challenges and payments between contacts, apps you connect with Wallet Connect, your encrypted mint list, requests you made and ecash sent to your ecash address. A contact or a payment request can name relays of its own, which are used when you send to them.',
    'Two more relays (relay.nostr.band and relay.cashumints.space) are asked only when you tap Find mints people recommend.',
    'Coinbase, for the price and the price chart, only while Show Bitcoin price is on.',
    'MintRadar (mintradar.org), only while Show mint reliability is on: it sees the internet address of your phone when NUTCADE downloads its public list of mint health. NUTCADE asks for the whole list, so MintRadar never learns which mints you use.',
    'npub.cash, while your Lightning address is on, and npubx.cash, when you tip from inside the app (the tip address is an npubx.cash address).',
    'The web address of any Lightning address, LNURL, voucher or payment request you pay or scan, and of a Nostr profile when you zap it. It sees that one request.',
    'This website, to load NUTCADE, its QR scanner and the update check. GitHub, which hosts it, sees these requests like any website visit.',
    'GitHub pages (the source, release notes and the problem report form), only when you tap a link to them.'], after: [
    'The camera is used only while a scanner is open and the microphone only while a Listen screen is open. Nothing is recorded or sent.'] },
  { q: 'Reporting a problem', a: [
    'Reports on GitHub are public. Never paste your 12 words, your PIN, a backup file or a token into one.',
    'For a security problem, use the private report link below, so that only the maintainer sees it.'] }
];
function helpTopics() { return HELP.concat(Array.isArray(window.NutHelpTopics) ? window.NutHelpTopics : []); }
function helpPanel() {
  return `<div class="panel" id="set-help"><span class="h2">Help</span>
      <p class="th" style="margin:0">Short answers: what ecash is, a new phone, a stuck payment and what NUTCADE contacts. It works offline.</p>
      <button class="btn sm gold" data-act="helpOpen">Help &amp; FAQ</button>
    </div>`;
}
function openHelp() {
  openSheet('Help & FAQ', `
    <div class="help">${helpTopics().map(t => `<details><summary>${esc(t.q)}</summary><div class="help-a">${(t.a || []).map(p => `<p>${esc(p)}</p>`).join('')}${t.ul ? `<ul>${t.ul.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}${(t.after || []).map(p => `<p>${esc(p)}</p>`).join('')}</div></details>`).join('')}</div>
    <div class="row wrap"><a class="btn sm" href="https://github.com/Random21m/nutcade/issues/new?template=bug.yml" target="_blank" rel="noopener noreferrer">Report a problem</a><a class="btn sm red" href="https://github.com/Random21m/nutcade/security/advisories/new" target="_blank" rel="noopener noreferrer">Report a security problem privately</a></div>
    <button class="btn block" data-act="close">Done</button>`);
}

/* ---------- a mint's contact, terms and description (NUT-06) ----------
   The text comes from the mint, so it is never trusted: it is shortened, stripped of control and direction-changing characters, and
   escaped wherever it is shown. A link is made only from an http(s) address without a name or password in it, and opens in a
   new tab with rel=noopener. Nothing else (mailto:, javascript:, data:) ever becomes a link. */
const clipText = (v, n) => (typeof v === 'string' ? v : '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u0080-\u009f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\u061c\ufeff]/g, '').slice(0, n);
function webUrl(u) {
  try { const x = new URL(String(u == null ? '' : u).trim()); return (x.protocol === 'https:' || x.protocol === 'http:') && !x.username && !x.password && x.hostname ? x.href : null; } catch (e) { return null; }
}
const safeLink = (u, label) => { const h = webUrl(u); return h ? `<a href="${esc(h)}" target="_blank" rel="noopener noreferrer" data-noi18n style="overflow-wrap:anywhere">${esc(label == null ? h : label)}</a>` : `<span data-noi18n style="overflow-wrap:anywhere">${esc(label == null ? u : label)}</span>`; };
// NUT-06: contact is [{ method, info }]; older mints send [[method, info]]
function mintInfoOf(info) {
  const raw_ = Array.isArray(info.contact) ? info.contact : [];
  const contacts = raw_.slice(0, 8).map(c => Array.isArray(c) ? { method: clipText(String(c[0] == null ? '' : c[0]), 30), info: clipText(String(c[1] == null ? '' : c[1]), 200) } : c && typeof c === 'object' ? { method: clipText(String(c.method == null ? '' : c.method), 30), info: clipText(String(c.info == null ? '' : c.info), 200) } : null).filter(c => c && c.method && c.info);
  return { name: info.name || '', version: info.version || '', contact: (info.contact || []).length, motd: info.motd || '', tos: !!info.tos_url, nuts: Object.keys(info.nuts || {}).length,
    contacts, tosUrl: clipText(info.tos_url, 500), desc: clipText(info.description, 300), descLong: clipText(info.description_long, 2000) };
}
function mintInfoHTML(url, state) {
  const l = mlog(url), i = l.info, m = S.mints.find(x => x.url === url) || { name: host(url), url };
  const head = `<div><div class="h2 uname" data-noi18n>${esc(m.name)}</div><div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(url))}</div></div>`;
  if (!i) return head + (state === 'busy' ? busyHTML('ASKING THE MINT') : '<div class="notice">The mint did not answer, so there is nothing to show yet.</div>');
  const sec = (label, body) => `<div class="field"><label>${label}</label>${body}</div>`;
  const contacts = (i.contacts || []).length ? `<div class="minfo-list">${i.contacts.map(c => `<div class="minfo-row"><span class="tiny muted" data-noi18n>${esc(c.method)}</span>${safeLink(c.info)}</div>`).join('')}</div>` : '<div class="tiny muted">The mint lists no contact.</div>';
  return head + `
    ${i.desc ? sec('About this mint', `<div data-noi18n style="overflow-wrap:anywhere">${esc(i.desc)}</div>`) : ''}
    ${i.descLong ? sec('In more detail', `<div data-noi18n style="overflow-wrap:anywhere;white-space:pre-line">${esc(i.descLong)}</div>`) : ''}
    ${i.motd ? sec('Message from the mint', `<div data-noi18n style="overflow-wrap:anywhere">${esc(clipText(String(i.motd), 500))}</div>`) : ''}
    ${sec('Contact', contacts)}
    ${sec('Terms of service', i.tosUrl && webUrl(i.tosUrl) ? safeLink(i.tosUrl) : '<div class="tiny muted">The mint lists no terms.</div>')}
    ${i.version ? sec('Software', `<div class="tiny" data-noi18n>${esc(clipText(String(i.version), 60))}</div>`) : ''}
    <div class="tiny muted">This text was written by the mint, not by NUTCADE. Read it with care: a mint that says it is safe has not been checked by us.</div>`;
}
function openMintInfo(url) {
  openSheet('Mint details', mintInfoHTML(url, mlog(url).info ? 'done' : 'busy') + '<button class="btn block" data-act="close">Done</button>', body => {
    let live = true;
    (async () => {
      try {
        const ac = new AbortController(), tm = setTimeout(() => ac.abort(), 7000);
        const r = await fetch(url + '/v1/info', { cache: 'no-store', signal: ac.signal }).finally(() => clearTimeout(tm));
        const info = r.ok ? await r.json() : null;
        if (info && typeof info === 'object') { const l = mlog(url); l.info = mintInfoOf(info); saveMlog(); }
      } catch (e) {}
      if (live && body.isConnected) body.innerHTML = mintInfoHTML(url, 'done') + '<button class="btn block" data-act="close">Done</button>';
    })();
    return () => { live = false; };
  });
}
