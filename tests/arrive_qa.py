"""Notices when money arrives (no server, no push service, nothing sent anywhere): an in-app notice for each arrival,
optional system notifications shown by the page or its service worker, the coin sound, and a "while you were away"
summary on opening or unlocking.

The grid: each kind of arrival (Lightning deposit, a token claimed, ecash over Nostr, a payment request paid, the
npub.cash Lightning address, a Wallet Connect make_invoice paid) x NUTCADE open / in a background tab / closed and
reopened / locked; plus two tabs (one notice), a reload mid-arrival, a restore from the 12 words (no flood for old
history), the duress PIN's wallet (only the open wallet's own arrivals, the other never shown; system notifications exactly as with
a PIN alone in both wallets), a sender's memo that reads like the app's own note, your own token in another encoding, a
deposit recovered after its answer was lost, claims cut off by 1.15.0 settled by this version (after a reload or from
a 1.15 backup), your own token handed back over Nostr, your own token saved to claim later (pasted or scanned while
offline or its mint is down, never announced), sound on and off,
system notifications off / on / permission denied, five languages and 320 / 1440 px wide screens.

Exact: a summary's count and total per kind equal the history lines that arrived in that window, and no arrival is
announced twice (across reloads, tabs and restores).

Uses two local test mints (ARR_FEE, default 3338, with input fees; ARR_FREE, default 3339, without) and mock_nostr.py
(ARR_NOSTR, default ws://127.0.0.1:3350/relay; it also stands in for npub.cash). ARR_ONLY=a,b runs some sections
(open, bg, closed, tabs, reload, notif, sound, locked, restore, duress, own, own2, toast, memo, own3, reenc, recover, sysduress,
legacy, held, langs, amounts, widths, game, till). ARR_SHOTS: where screenshots go
(default QA_OUT)."""
import asyncio, json, os, re, time, urllib.request
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net

FEE = os.environ.get('ARR_FEE', 'http://127.0.0.1:3338')
FREE = os.environ.get('ARR_FREE', 'http://127.0.0.1:3339')
NOSTR = os.environ.get('ARR_NOSTR', 'ws://127.0.0.1:3350/relay')
MOCK = re.sub(r'^ws', 'http', NOSTR).rsplit('/', 1)[0]
ORIGIN = re.match(r'https?://[^/]+', URL).group(0)
OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
SHOTS = os.environ.get('ARR_SHOTS', '') or os.path.join(OUT, 'arrive-shots')
ONLY = [x for x in os.environ.get('ARR_ONLY', '').split(',') if x]
PIN, DPIN = '135791', '246802'
J = json.dumps
LABEL = {'ln': 'Lightning deposit', 'token': 'Ecash claimed', 'nostr': 'Ecash over Nostr', 'request': 'Payment request paid',
         'npc': 'Lightning address', 'nwc': 'Wallet Connect invoice'}
KINDS = ['ln', 'token', 'nostr', 'request', 'npc', 'nwc']
NAME = {FEE: 'Mint A', FREE: 'Mint B'}

# Every page: the test's prefs, a switch that puts the page in a background tab (document.hidden), a count of the
# coin sound's tones, and a log of system notifications shown (they are still shown for real).
INIT = r"""
window.__i18nMiss = new Set();
if (!localStorage.getItem('nutcade:prefs')) localStorage.setItem('nutcade:prefs', %s);
(() => { let hid = false;
  Object.defineProperty(Document.prototype, 'hidden', { configurable: true, get() { return hid; } });
  Object.defineProperty(Document.prototype, 'visibilityState', { configurable: true, get() { return hid ? 'hidden' : 'visible'; } });
  window.__hide = h => { hid = !!h; document.dispatchEvent(new Event('visibilitychange')); }; })();
window.__tones = [];
(() => { const P = window.AudioContext || window.webkitAudioContext; if (!P) return; const oc = P.prototype.createOscillator;
  P.prototype.createOscillator = function () { const o = oc.call(this); const f = o.frequency, sv = f.setValueAtTime.bind(f); f.setValueAtTime = (v, t) => { window.__tones.push(v); return sv(v, t); }; return o; }; })();
window.__sys = [];
// A browser that can't grant notifications here (an older headless Chromium, as in CI): an in-page stand-in for the
// granted Notification API and the service worker's notifications, kept across reloads like the real ones.
(() => { if (!window.__wantNotif || !window.Notification || Notification.permission === 'granted' || !window.ServiceWorkerRegistration) return;
  const K = '__fakeNotes', load = () => JSON.parse(localStorage.getItem(K) || '[]'), keep = a => localStorage.setItem(K, JSON.stringify(a));
  Object.defineProperty(Notification, 'permission', { configurable: true, get: () => 'granted' }); Notification.requestPermission = async () => 'granted';
  ServiceWorkerRegistration.prototype.showNotification = async function (t, o) { o = o || {}; const a = load().filter(x => !o.tag || x.tag !== o.tag); a.push({ id: Math.random(), title: t, body: o.body || '', data: o.data || null, tag: o.tag || '' }); keep(a); };
  ServiceWorkerRegistration.prototype.getNotifications = async function (f) { return load().filter(x => !f || !f.tag || x.tag === f.tag).map(n => ({ title: n.title, body: n.body, data: n.data, tag: n.tag, close() { keep(load().filter(x => x.id !== n.id)); } })); };
  window.__fakeNotif = true; })();
(() => { if (window.ServiceWorkerRegistration) { const sn = ServiceWorkerRegistration.prototype.showNotification;
    ServiceWorkerRegistration.prototype.showNotification = function (t, o) { window.__sys.push({ title: t, body: (o || {}).body || '', at: Date.now() }); return sn.call(this, t, o); }; }
  if (window.Notification) { const N = window.Notification; const F = function (t, o) { window.__sys.push({ title: t, body: (o || {}).body || '', page: 1, at: Date.now() }); return new N(t, o); };
    F.prototype = N.prototype; Object.defineProperty(F, 'permission', { get() { return N.permission; } }); F.requestPermission = (...a) => N.requestPermission(...a); window.Notification = F; } })();
"""
CARDS_JS = "[...document.querySelectorAll('#arrStack .arr-card')].map(c=>({type:c.dataset.type, ids:(c.dataset.ids||'').split(' ').filter(Boolean), text:c.innerText}))"
LOG_JS = "(window.NutArrivals&&NutArrivals.log||[]).map(e=>({type:e.type, ids:e.ids}))"
SYSN_JS = "(async()=>{try{const r=await navigator.serviceWorker.ready; return (await r.getNotifications()).map(n=>({title:n.title, body:n.body}))}catch(e){return []}})()"
PEND_JS = "(window.NutArrivals?NutArrivals.ledger().pend.map(p=>p.id):null)"
ARRIVED_JS = "(t0=>Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done'&&t.amount>0&&!t.move&&t.ts>=t0).map(t=>({id:t.id, amount:t.amount, mint:t.mint, note:t.note, reqId:t.reqId||null, nwc:t.nwc||null})))"


# the app's own notes (and the start of some): a stranger's memo may say the same, and is still only their memo
OWN_NOTES = ['Reclaimed: lol', 'Restored from backup', 'Extra Life cashed out (was for Bob)', "Back from the duress PIN's wallet",
             'Recovered with recovery phrase', 'Restored from another phrase', 'Gift came back from Bob', "Payment request couldn't be delivered: the sats came back"]
WITH_MEMO_JS = "((t,m)=>{const d=CashuLib.getDecodedToken(t, Object.keys(Nutcade.S.counters||{})); return CashuLib.getEncodedToken({mint:d.mint, unit:'sat', memo:m, proofs:d.proofs})})(%s,%s)"
# your own token read back the way each path reads it: by sound (no DLEQ proofs), from an NFC card (binary), from a QR code (slim)
REENC_JS = """((tok,way)=>{const L=CashuLib, ids=Object.keys(Nutcade.S.counters||{}); try{
  if(way==='sound') return Nutcade.soundText(Nutcade.soundBytes(tok));
  if(way==='nfc') return L.getEncodedToken(L.getDecodedTokenBinary(L.getEncodedTokenBinary(L.getDecodedToken(tok, ids)), ids));
  const d=L.getDecodedToken(tok, ids); return L.getEncodedToken({mint:d.mint, unit:d.unit||'sat', proofs:d.proofs.map(p=>{const o=Object.assign({},p); delete o.dleq; return o})});
  }catch(e){return 'ERR '+e.message}})(%s,%s)"""
SEEN_JS = "(window.NutArrivals?NutArrivals.ledger().seen.map(x=>x[0]):null)"
TOASTS_JS = """(()=>{window.__toasts=[]; if(window.__toastObs) return; const seen=()=>{const e=document.getElementById('toast'); if(e&&!e.hidden&&e.textContent) window.__toasts.push(e.textContent)};
  window.__toastObs=new MutationObserver(seen); window.__toastObs.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden']})})()"""
num_ok = lambda line: line.get('status') == 'done' and (line.get('amount') or 0) > 0


def mock(path, data=None):
    req = urllib.request.Request(MOCK + path, data=(J(data).encode() if data is not None else None), method='POST' if data is not None else 'GET', headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def fmtn(n, lang='en'):
    s = f'{n:,}'
    return {'en': s, 'es': s.replace(',', '.'), 'pt': s.replace(',', '.'), 'de': s.replace(',', '.'), 'fr': s.replace(',', ' ')}[lang]


class Block:
    """stops a page from noticing deposits at a mint (no quote checks, no live updates) while on"""
    def __init__(s): s.on = False
    async def attach(s, pg, mint):
        hp = mint.split('//')[1]
        async def http(route):
            if s.on and route.request.method == 'GET': await route.abort()
            else: await route.continue_()
        async def ws(w):
            if not s.on: w.connect_to_server()
        await pg.route(re.compile(re.escape(mint) + r'/v1/mint/quote/bolt11/[^/?]+$'), http)
        await pg.route_web_socket(re.compile(re.escape(hp) + r'/v1/ws'), ws)


async def wallet(b, lang='en', vw=390, vh=844, notif=False, sound=False, ctx=None):
    if ctx is None:
        ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=vw < 800, has_touch=vw < 800)
        if notif:   # (ARR_FAKE_NOTIF=1: try the stand-in, as on a browser that can't grant notifications)
            if not os.environ.get('ARR_FAKE_NOTIF'): await ctx.grant_permissions(['notifications'], origin=ORIGIN)
            await ctx.add_init_script("window.__wantNotif = 1")
        prefs = {'sound': sound, 'music': False, 'crt': False, 'lang': lang, 'relays': [NOSTR], 'npcHost': MOCK}
        await ctx.add_init_script(INIT % J(J(prefs)))
        await ctx.route_web_socket(re.compile('coinbase'), lambda ws: None)
    pg = await ctx.new_page(); w = W(pg, 'arr')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'ERR_FAILED' not in m.text and 'net::' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def has(w): return await w.ev("!!window.NutArrivals")


async def settled(w, ms=45000):
    """the opening's checks are done and the summary (if any) is up"""
    if not await has(w): await w.wait(2500); return False
    return await w.until("NutArrivals.awayDone()", ms)


async def cards(w): return await w.ev(CARDS_JS)


async def pend(w, missing):
    """the ids waiting for a summary (without the feature: [missing], so a check on it fails)"""
    x = await w.ev(PEND_JS)
    return x if x is not None else [missing]


async def dismiss(w):
    await w.ev("document.querySelectorAll('#arrStack [data-act=arrClose]').forEach(b=>b.click())"); await w.wait(150)


async def pad(w, pin, root='[data-pinpad]'):
    for k in pin: await w.click(f'{root} [data-k="{k}"]')
    await w.click(f'{root} [data-k=ok]')


async def settings(w):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)


async def set_pin(w, pin=PIN):
    await settings(w); await w.click('[data-act=pinSet]'); await w.wait(200)
    await pad(w, pin); await w.wait(300); await pad(w, pin)
    await w.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await w.wait(500); await w.ev("Nutcade.closeSheet()")


async def unlock(w, pin=PIN):
    await w.until("!!document.querySelector('[data-pinpad]')", 8000)
    await pad(w, pin); await w.until("Nutcade.vault.open", 20000); await w.wait(300)


async def set_lang(w, lang):
    await settings(w)
    await w.ev(f"(()=>{{const s=document.querySelector('#p_lang'); s.value={J(lang)}; s.dispatchEvent(new Event('change',{{bubbles:true}}))}})()"); await w.wait(300)
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(150)


async def npub_hex(w): return await w.ev("CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")


# ---------- the ways money arrives (each returns once the payer's side is done) ----------
async def ln_invoice(r, amount, mint):
    """an invoice made in the receiver's Receive sheet; the test mints pay their own invoices after 0.5 s"""
    await r.use(mint); await r.home(); await r.click('[data-act=receive]'); await r.wait(150)
    if await r.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await r.click('[data-act=recvMethod][data-m=ln]'); await r.wait(100)
    n0 = await r.ev("Nutcade.S.txs.length")
    await r.fill('#amtIn', str(amount)); await r.click('[data-act=doLnInvoice]')
    await r.until(f"Nutcade.S.txs.length>{n0}", 10000)
    return await r.ev("Nutcade.S.txs[0].id")


async def token_from(p, amount, mint):
    await p.use(mint)
    return await p.ev(f"Nutcade.r8.sendEcash({amount}, '').then(t=>t.token)")


async def claim(r, tok):
    """pasted and claimed in the receiver's Receive sheet"""
    await r.home(); await r.click('[data-act=receive]'); await r.wait(150)
    await r.click('[data-act=recvMethod][data-m=ecash]'); await r.wait(100)
    await r.fill('#tokIn', tok); await r.click('[data-act=doReceiveToken]')


async def dm(p, to, amount, mint, memo=''):
    """ecash sent over Nostr (a NIP-17 gift wrap with the coins), the way a contact payment arrives"""
    await p.use(mint)
    return await p.ev(f"""(async()=>{{const tx=await Nutcade.r8.sendEcash({amount}, {J(memo)});
      const ev=CashuLib.nip17.wrapEvent(crypto.getRandomValues(new Uint8Array(32)), {{publicKey:{J(to)}}}, JSON.stringify({{mint:{J(mint)}, unit:'sat', proofs:tx.sent, memo:{J(memo) if memo else 'undefined'}}}));
      return await new Promise(res=>{{const ws=new WebSocket({J(NOSTR)}); ws.onopen=()=>ws.send(JSON.stringify(['EVENT',ev])); ws.onmessage=m=>{{const d=JSON.parse(m.data); if(d[0]==='OK'){{ws.close(); res(d[2])}}}}; setTimeout(()=>res('timeout'),8000)}})}})()""")


async def pay_request(p, enc, mint):
    await p.use(mint); await p.home(); await p.ev(f"Nutcade.handleScan({J(enc)})"); await p.wait(400)
    await p.ev(f"(()=>{{const s=document.querySelector('#reqMint'); if(s){{s.value={J(mint)}; s.dispatchEvent(new Event('change',{{bubbles:true}}))}}}})()")
    await p.click('[data-act=payReq]')
    ok = await p.until("!document.querySelector('#layer .spinner') && !!document.querySelector('#layer [data-act=close]')", 20000)
    await p.wait(300); await p.ev("Nutcade.closeSheet()"); return ok


async def npc_on(r, mint):
    await r.use(mint); await settings(r); await r.click('#set-lnaddr [data-act=lnAddr]'); await r.wait(250)
    await r.click('[data-act=lnAddrOn]'); await r.until("Nutcade.S.prefs.npc===true", 10000); await r.wait(600); await r.ev("Nutcade.closeSheet()")
    pk = await npub_hex(r)
    await r.until(f"fetch('{MOCK}/test/state').then(x=>x.json()).then(s=>(s.sockets['{pk}']||0)>0)", 8000)
    return pk


async def npc_pay(pk, amount): return await asyncio.to_thread(mock, f'/test/pay?pubkey={pk}&amount={amount}&lock=1', {})


async def nwc_make(r):
    await settings(r); await r.click('[data-act=nwcNew]'); await r.wait(200)
    await r.fill('#nwcName', 'Shop app'); await r.click('[data-act=nwcCreate]'); await r.until("!!document.querySelector('#layer .qr, #layer canvas')", 6000); await r.wait(300)
    uri = await r.ev("[...document.querySelectorAll('#layer .code')].map(e=>e.innerText).find(t=>t.startsWith('nostr+walletconnect://'))")
    for _ in range(40):
        if await r.ev("Nutcade.r7.nwcLive()"): break
        await r.wait(150)
    await r.wait(400); await r.ev("Nutcade.closeSheet()"); return uri


async def nwc_invoice(uri, amount):
    return await asyncio.to_thread(mock, '/test/nwc', {'uri': uri, 'method': 'make_invoice', 'params': {'amount': amount * 1000, 'description': 'order'}, 'wait': 15})


async def wait_line(r, pred_js, ms=25000):
    return await r.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.status==='done'&&({pred_js}))", ms)


def kind_of(line, reqs, nwc):
    if line.get('nwc'): return 'nwc'
    if line.get('reqId'): return 'request'
    if (line.get('note') or '') == 'Lightning address': return 'npc'
    return None


async def summary_rows(w, keep=False):
    """the summary: its card (one line), then its Details sheet's lines: kind -> (count, total). The sheet is closed
    again unless keep."""
    card = await w.ev("""(()=>{const c=document.querySelector('#arrStack .arr-card[data-type=away]'); if(!c) return null; return {ids:(c.dataset.ids||'').split(' ').filter(Boolean), text:c.innerText}})()""")
    if not card: return None
    await w.ev("document.querySelector('#arrStack .arr-card[data-type=away] [data-act=arrMore]')?.click()"); await w.wait(350)
    d = await w.ev("""(()=>{const d=document.querySelector('#layer .arr-details'); if(!d) return null; const o={}; for(const l of d.querySelectorAll('.arr-line')) o[l.dataset.k]=[+l.dataset.n, +l.dataset.a];
      return {rows:o, ids:(d.dataset.ids||'').split(' ').filter(Boolean), text:(document.querySelector('#layer .sheet')||d).innerText}})()""")
    if not keep: await w.ev("Nutcade.closeSheet()"); await w.wait(150)
    if not d: return dict(card, rows={}, text=card['text'])
    return {'rows': d['rows'], 'ids': card['ids'] if card['ids'] == d['ids'] else ['details differ'] + d['ids'], 'text': card['text'] + '\n' + d['text']}


# what a notice covers on the wallet screen (scrolled to the top): the balance, the lock, the mint, Receive and Send are
# sampled at their centre and corners; the card itself must be on screen with its buttons reachable
COVER_JS = """(()=>{scrollTo(0,0); const out=[]; const sel={balance:'.credit-num', lock:'[data-act=lockNow]', mint:'#app .mint-pill', receive:'#app [data-act=receive]', send:'#app [data-act=send]'};
  for(const [k,s] of Object.entries(sel)){const e=document.querySelector(s); if(!e) continue; const r=e.getBoundingClientRect(); if(!r.width) continue;
    for(const [x,y] of [[.5,.5],[.1,.15],[.9,.15],[.1,.85],[.9,.85]]){const px=r.left+r.width*x, py=r.top+r.height*y; if(py<0||py>innerHeight) continue; const h=document.elementFromPoint(px,py); if(h&&h.closest('.arr-card')){out.push(k);break}}}
  const c=document.querySelector('#arrStack .arr-card'); if(!c) return {covered:out, card:null};
  const q=c.getBoundingClientRect(); const btn=[...c.querySelectorAll('button')].map(b=>{const r=b.getBoundingClientRect(); const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); return h&&(h===b||b.contains(h))});
  const big=c.querySelector('.arr-big'), br=big&&big.getBoundingClientRect();
  const amount=!!big&&big.scrollWidth<=big.clientWidth+1&&br.left>=q.left-1&&br.right<=q.right+1&&br.right<=innerWidth;   // (shown in full: not cut, not outside the card)
  const out2=[...c.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect(); return r.width&&(r.left<q.left-1||r.right>q.right+1)}).map(e=>(e.className||e.tagName)+' '+Math.round(e.getBoundingClientRect().right)+'>'+Math.round(q.right));
  return {covered:out, outside:out2, card:[Math.round(q.top),Math.round(q.bottom)], inview:q.top>=0&&q.bottom<=innerHeight&&q.left>=0&&q.right<=innerWidth, buttons:btn.every(Boolean)&&btn.length>=2, amount, text:big&&big.innerText}})()"""
SIZES = [(320, 640), (375, 667), (430, 932), (1440, 900), (844, 390), (568, 320)]


async def looks(w, label, details=True):
    """the notice on screen at every size: covers nothing that matters, fully in view, its buttons reachable; at
    568x320 its Details sheet's buttons too"""
    bad = {}
    for vw, vh in SIZES:
        await w.pg.set_viewport_size({'width': vw, 'height': vh}); await w.wait(150)
        c = await w.ev(COVER_JS)
        if not c['card'] or c['covered'] or not c['inview'] or not c['buttons'] or not c['amount'] or c['outside']: bad[f'{vw}x{vh}'] = c
    check(f'{label}: at 320/375/430/1440 px and 844x390/568x320 its amount shows in full, nothing sticks out of the card, it covers no balance, lock, mint, Receive or Send, and its buttons are on screen', not bad, bad)
    if details:
        await w.ev("document.querySelector('#arrStack .arr-card [data-act=arrMore]')?.click()"); await w.wait(350)
        reach = await w.ev("""(()=>{const out={}; for(const s of ['#layer [data-act=arrNotes]','#layer [data-act=close]']){const e=[...document.querySelectorAll(s)].pop(); if(!e){out[s]='missing';continue} e.scrollIntoView({block:'center'}); const q=e.getBoundingClientRect();
          const h=document.elementFromPoint(q.left+q.width/2,q.top+q.height/2); out[s]=q.top>=0&&q.bottom<=innerHeight&&h&&(h===e||e.contains(h))?'ok':'not reachable'} return out})()""")
        check(f'{label}: at 568x320 its Details sheet has Open notes and OK on screen', all(v == 'ok' for v in reach.values()), reach)
    await w.pg.set_viewport_size({'width': 390, 'height': 844}); await w.wait(150)


async def shot(w, name):
    os.makedirs(SHOTS, exist_ok=True)
    try: await w.pg.screenshot(path=os.path.join(SHOTS, name + '.png'))
    except Exception as e: print('screenshot failed', name, e)


async def no_overflow(w):
    return await w.ev("""(()=>{const W=document.documentElement.clientWidth; if(document.documentElement.scrollWidth>W) return 'page scrolls sideways';
      for(const e of document.querySelectorAll('#arrStack, #arrStack *')){const r=e.getBoundingClientRect(); if(r.width&&(r.left<-1||r.right>W+1)) return (e.className||e.tagName)+' '+Math.round(r.left)+'..'+Math.round(r.right)+' of '+W}
      return ''})()""")


async def main():
    os.makedirs(SHOTS, exist_ok=True)
    want = lambda s: not ONLY or s in ONLY
    async with async_playwright() as pw:
        b = await pw.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        # ---------- the payer (two mints, sats on both) and the receiver ----------
        p = await wallet(b); await p.create(); await p.add_mint(FEE); await p.add_mint(FREE)
        await p.use(FEE); await p.receive_ln(30000); await p.use(FREE); await p.receive_ln(60000); await p.receive_ln(60000)
        r = await wallet(b, notif=True); words = await r.create(); await r.add_mint(FEE); await r.add_mint(FREE); await r.use(FREE)
        await r.receive_ln(1000); await r.wait(1500); await dismiss(r)
        rpk = await npub_hex(r)
        feature = await has(r)
        check('the arrival notices are part of the app (window.NutArrivals)', feature)
        check('opening a fresh wallet shows no summary (nothing arrived while away)', not [c for c in await cards(r) if c['type'] == 'away'])
        npk = await npc_on(r, FREE)
        nwc_uri = await nwc_make(r)
        await r.use(FREE)
        amt = iter(range(1201, 9999, 7))

        async def arrive(kind, mint, a, hidden=False):
            """one arrival of a kind on a page that is open (or in a background tab); returns the new line's id"""
            n0 = await r.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done').length")
            if kind == 'ln':
                await ln_invoice(r, a, mint)
                if hidden: await r.ev("__hide(true)")
            elif kind == 'token':
                tok = await token_from(p, a, mint)
                if hidden:   # claimed, then the tab goes to the background while the mint answers
                    async def slow(route): await asyncio.sleep(1.5); await route.continue_()
                    await r.pg.route(re.compile(re.escape(mint) + r'/v1/swap$'), slow)
                await claim(r, tok)
                if hidden: await r.wait(200); await r.ev("__hide(true)")
            else:
                if hidden: await r.ev("__hide(true)")
                if kind == 'nostr': await dm(p, rpk, a, mint)
                elif kind == 'request':
                    enc = await r.ev(f"Nutcade.r8.newRequest({a}, 'Pizza').encoded"); await r.wait(600)
                    await pay_request(p, enc, mint)
                elif kind == 'npc': await npc_pay(npk, a)
                elif kind == 'nwc': await nwc_invoice(nwc_uri, a)
            ok = await r.until(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done').length>{n0}", 30000)
            if kind == 'token' and hidden: await r.pg.unroute_all()
            await r.wait(1500)
            line = await r.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done').sort((x,y)=>y.ts-x.ts)[0]")
            return line if ok else None

        # ---------- open: a notice per arrival, with amount, kind and mint ----------
        if want('open'):
            for kind, mint in [('ln', FREE), ('token', FEE), ('nostr', FREE), ('request', FREE), ('npc', FREE), ('nwc', FREE)]:
                await dismiss(r); a = next(amt); log0 = len(await r.ev(LOG_JS)); sys0 = len(await r.ev("__sys"))
                line = await arrive(kind, mint, a)
                await r.wait(800)
                cs = [c for c in await cards(r) if c['type'] == 'live']
                got = cs[0]['text'] if cs else ''
                log = (await r.ev(LOG_JS))[log0:]
                ann = [i for e in log for i in e['ids']]
                check(f'open, {kind}: a notice shows the amount, where it came from and the mint',
                      bool(line) and len(cs) == 1 and LABEL[kind] in got and ('+' + fmtn(line['amount']) + ' SAT') in got and NAME[mint] in got, (line and line['amount'], got))
                check(f'open, {kind}: announced once, for that history line', bool(line) and ann == [line['id']], (ann, line and line['id']))
                check(f'open, {kind}: no system notification while the page is in front', len(await r.ev("__sys")) == sys0)
                check(f'open, {kind}: nothing left for the summary', bool(line) and line['id'] not in await pend(r, line['id']))
                if kind == 'nostr': await shot(r, 'notice-open-390')
            await dismiss(r)

        # ---------- system notifications: off, on, permission denied ----------
        if want('notif') or want('bg') or want('locked'):
            await settings(r)
            check('notifications: a setting in Settings, off at first', await r.ev("!!document.querySelector('#p_arrNotify') && !document.querySelector('#p_arrNotify').checked"))
            await r.home(); await r.ev("__sys.length=0")
            line = await arrive('nostr', FREE, next(amt), hidden=True); await r.wait(1200)
            check('notifications off: an arrival in a background tab shows no system notification', bool(line) and await r.ev("__sys.length") == 0, await r.ev("__sys"))
            check('notifications off: the notice is still on the page for when you come back', bool(line) and any(line['id'] in c['ids'] for c in await cards(r)))
            await r.ev("__hide(false)"); await r.wait(400); await dismiss(r)
            await settings(r); await r.ev("document.querySelector('#p_arrNotify')?.click()"); await r.wait(800)
            check('notifications on: turning it on asks for permission then (granted here) and stays on', await r.ev("Notification.permission==='granted' && !!Nutcade.S.prefs.arrNotify && document.querySelector('#p_arrNotify').checked"))
            dn = await wallet(b)
            await dn.create(); await settings(dn); await dn.ev("document.querySelector('#p_arrNotify')?.click()")
            await dn.until("Notification.permission!=='default' || !document.querySelector('#p_arrNotify') || !document.querySelector('#p_arrNotify').checked", 20000); await dn.wait(300)   # (the browser answers the prompt)
            txt = await dn.ev("(document.querySelector('#arrNotifyHelp')||{}).textContent||''")
            check('notifications denied: the setting goes back off and says how to allow them', await dn.ev("!Nutcade.S.prefs.arrNotify && !!document.querySelector('#p_arrNotify') && !document.querySelector('#p_arrNotify').checked") and bool(re.search(r'blocked|allow', txt, re.I)), txt[-300:])
            await dn.ev("__hide(true)"); await dn.ev("__sys.length=0")
            await dn.add_mint(FREE); await dn.use(FREE); await dn.receive_ln(500); await dn.wait(1500)
            check('notifications denied: an arrival shows none (and nothing breaks)', await dn.ev("__sys.length") == 0 and not [e for e in dn.errs if 'PAGEERROR' in e], dn.errs[:3])
            await dn.pg.context.close()
            await r.home()

        # ---------- a background tab: the notice waits on the page, a system notification says what came ----------
        if want('bg'):
            for kind, mint in [('ln', FREE), ('token', FEE), ('nostr', FREE), ('request', FREE), ('npc', FREE), ('nwc', FREE)]:
                await dismiss(r); a = next(amt); log0 = len(await r.ev(LOG_JS)); await r.ev("__sys.length=0")
                line = await arrive(kind, mint, a, hidden=True)
                await r.wait(1000)
                sysn = await r.ev("__sys")
                cs = [c for c in await cards(r) if c['type'] == 'live']
                check(f'background, {kind}: the notice is on the page', bool(line) and len(cs) == 1 and line['id'] in cs[0]['ids'], cs)
                check(f'background, {kind}: one system notification with the amount, the kind and the mint',
                      bool(line) and len(sysn) == 1 and fmtn(line['amount']) in sysn[0]['body'] and LABEL[kind] in sysn[0]['body'] + sysn[0]['title'] and NAME[mint] in sysn[0]['body'], sysn)
                check(f'background, {kind}: not counted as seen until you come back', bool(line) and line['id'] in await pend(r, None))
                await r.ev("__hide(false)"); await r.wait(500)
                check(f'background, {kind}: seen once you come back (no summary later)', bool(line) and line['id'] not in await pend(r, line['id']))
                ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]
                check(f'background, {kind}: announced once', bool(line) and ann.count(line['id']) == 1 and len(ann) == 1, ann)
            await dismiss(r)

        # ---------- closed, then reopened: the summary (count and total per kind) equals the history lines ----------
        async def away_batch(label, close, reopen, after_close=None, t0=None, extra=None, shotname=None):
            """every kind arrives while the receiver is away; returns the history lines that arrived"""
            nonlocal r
            blk = Block(); await blk.attach(r.pg, FREE); await blk.attach(r.pg, FEE); blk.on = True
            enc = await r.ev(f"Nutcade.r8.newRequest(1111, 'Away').encoded"); await r.wait(500)
            await ln_invoice(r, 1301, FREE); await r.ev("Nutcade.closeSheet()")
            await nwc_invoice(nwc_uri, 1302)
            tok = await token_from(p, 1303, FEE)
            await r_ctx.set_offline(True)   # offline: the token is saved, and claimed once NUTCADE is back
            await claim(r, tok); await r.until("Nutcade.S.txs.some(t=>t.status==='pending'&&t.incoming&&t.offline)", 15000); await r.ev("Nutcade.closeSheet()")
            await r.wait(1200)   # (the invoices are paid at the mint by now; this page can't see it)
            t0 = t0 or int(time.time() * 1000)
            await close()
            await r_ctx.set_offline(False)
            blk.on = False
            try: await r.pg.unroute_all(behavior='ignoreErrors')
            except Exception: pass
            await dm(p, rpk, 1304, FREE)
            await pay_request(p, enc, FREE)
            await npc_pay(npk, 1305)
            if after_close: await after_close()
            r = await reopen()
            done = await settled(r, 60000); await r.wait(500)
            lines = await r.ev(ARRIVED_JS + f"({t0})")
            want_k = {1301: 'ln', 1302: 'nwc', 1304: 'nostr', 1111: 'request', 1305: 'npc', **(extra or {})}
            kinds = {}
            for l in lines:
                k = want_k.get(l['amount']) or ('token' if l['mint'] == FEE else '?')
                kinds.setdefault(k, []).append(l)
            if shotname: await shot(r, shotname)
            if label.startswith('closed'): await looks(r, f'{label}: the one-line summary', details=False)
            sm = await summary_rows(r, keep=True)
            if shotname: await shot(r, shotname + '-details')
            check(f'{label}: every kind arrived and is in the history', set(kinds) == set(KINDS), {k: [x['amount'] for x in v] for k, v in kinds.items()})
            check(f'{label}: a summary of what arrived while away', done and bool(sm), sm)
            exp = {k: [len(v), sum(x['amount'] for x in v)] for k, v in kinds.items()}
            check(f'{label}: count and total per kind equal the history lines that arrived (exact)', bool(sm) and sm['rows'] == exp, (sm and sm['rows'], exp))
            check(f'{label}: the summary is exactly those lines', bool(sm) and sorted(sm['ids']) == sorted(l['id'] for l in lines), (sm and sm['ids'], [l['id'] for l in lines]))
            check(f'{label}: the summary names each kind and the total', bool(sm) and all(LABEL[k] in sm['text'] for k in KINDS) and fmtn(sum(x['amount'] for x in lines)) in sm['text'], sm and sm['text'])
            check(f'{label}: no separate notice for them as well', not [c for c in await cards(r) if c['type'] == 'live'])
            await r.ev("document.querySelector('#layer [data-act=arrNotes]')?.click()"); await r.wait(300)
            check(f'{label}: the summary links to the notes (history)', await r.ev("!!document.querySelector('[data-act=tab][data-tab=history][aria-current]')") and not await r.ev("!!document.querySelector('#arrStack .arr-card[data-type=away]')"))
            await r.home(); await r.wait(300)
            return lines

        async def reopen_closed():
            w = await wallet(b, ctx=r_ctx); return w

        r_ctx = r.pg.context
        if want('closed'):
            async def close_r(): await r.pg.close()
            lines = await away_batch('closed, reopened', close_r, reopen_closed, shotname='summary-closed-390')
            ids = [l['id'] for l in lines]
            r2 = r; await r2.pg.reload(); await r2.wait(700); await settled(r2)
            check('closed: a reload after the summary shows it again? no', not [c for c in await cards(r2) if c['type'] == 'away'] and not [i for e in await r2.ev(LOG_JS) for i in e['ids'] if i in ids])

        # ---------- two tabs: one notice ----------
        if want('tabs'):
            t2 = await wallet(b, ctx=r_ctx); await t2.wait(800)
            busy = await t2.ev("/another tab/i.test(document.body.innerText)")
            check('two tabs: the second tab says NUTCADE is open in another tab', busy)
            log0 = len(await r.ev(LOG_JS)); a = next(amt)
            line = await arrive('ln', FREE, a); await r.wait(1500)
            ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']] + [i for e in await t2.ev(LOG_JS) for i in e['ids']]
            check('two tabs: one arrival, one notice (in the tab in charge)', bool(line) and ann == [line['id']] and not await cards(t2), ann)
            # the second tab takes over: what the first already showed isn't shown again
            await t2.click('[data-act=takeover]'); await t2.wait(1200); await settled(t2)
            check('two tabs: taking over shows no summary of what the first tab showed', not [c for c in await cards(t2) if c['type'] == 'away'], await cards(t2))
            # an arrival the tab in charge only got in the background is summed up once, by the tab that takes over
            await r.pg.close(); r = t2
            a = next(amt); line = await arrive('nostr', FREE, a, hidden=True)
            check('two tabs: (an arrival while the tab in charge is in the background)', bool(line))
            t3 = await wallet(b, ctx=r_ctx); await t3.wait(800); await t3.click('[data-act=takeover]'); await t3.wait(1200); await settled(t3)
            sm = await summary_rows(t3)
            check('two tabs: the tab that takes over sums it up once', bool(sm) and bool(line) and sm['ids'] == [line['id']], sm)
            nlog = len(await r.ev(LOG_JS)); await r.ev("__hide(false)"); await r.wait(800)
            check('two tabs: the paused tab announces nothing more when you look at it', len(await r.ev(LOG_JS)) == nlog)
            check('two tabs: the paused tab writes nothing (its record of arrivals unchanged)', await r.ev("!!document.querySelector('[data-act=takeover]') || /another tab/i.test(document.body.innerText)"))
            await r.pg.close()
            r = t3; await dismiss(r)

        # ---------- a reload mid-arrival ----------
        if want('reload'):
            lost = {'on': True, 'hit': False}; blk = Block(); await blk.attach(r.pg, FREE)
            async def lose(route):
                if lost['on'] and route.request.method == 'POST':
                    await route.fetch(); blk.on = True; lost['hit'] = True; await route.abort()   # the mint signs, the answer never comes (and no retry before the reload)
                else: await route.continue_()
            await r.pg.route(re.compile(re.escape(FREE) + r'/v1/mint/bolt11$'), lose)
            a = next(amt); qid = await ln_invoice(r, a, FREE)
            await r.until(f"(Nutcade.S.quotes.find(q=>q.txId==={J(qid)})||{{}}).ctr", 15000); await r.wait(1500)
            check('reload mid-arrival: (the deposit\'s answer was lost; its line still waits)', await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(qid)}).status") == 'pending')
            log0 = await r.ev(LOG_JS); lost['on'] = False; blk.on = False
            await r.pg.reload(); await r.wait(700); await settled(r)
            st = await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(qid)})")
            sm = await summary_rows(r)
            check('reload mid-arrival: the deposit is credited once after the reload', st and st['status'] == 'done' and st['amount'] == a, st)
            check('reload mid-arrival: announced once (in the summary)', bool(sm) and sm['ids'] == [qid] and qid not in [i for e in log0 for i in e['ids']], (sm, log0))
            await r.pg.reload(); await r.wait(700); await settled(r)
            check('reload mid-arrival: a second reload shows nothing again', not await cards(r))
            # recorded in a background tab, never seen, then the page reloads: summed up once
            await r.ev("__hide(true)"); a = next(amt); line = await arrive('nostr', FREE, a, hidden=True)
            await r.pg.reload(); await r.wait(700); await settled(r)
            sm = await summary_rows(r)
            check('reload: an arrival not yet seen (background tab) is summed up after a reload, once', bool(line) and bool(sm) and sm['ids'] == [line['id']], sm)
            await shot(r, 'summary-reload-390')
            await r.pg.reload(); await r.wait(700); await settled(r)
            check('reload: and not again after the next reload', not await cards(r))
            await r.pg.unroute_all()

        # ---------- sound: the coin, once, only with sound on ----------
        if want('sound'):
            await dismiss(r)
            for on in (True, False):
                await r.ev(f"Nutcade.S.prefs.sound={J(on)}; window.NutPrefs.sound={J(on)}"); await r.ev("__tones.length=0")
                line = await arrive('npc', FREE, next(amt)); await r.wait(1500)
                coins = await r.ev("__tones.filter(f=>f===988).length")
                check(f'sound {"on" if on else "off"}: the coin sound plays {"once" if on else "not at all"} for an arrival', bool(line) and coins == (1 if on else 0), coins)
                await r.ev("__tones.length=0"); await dismiss(r)
                tok = await token_from(p, next(amt), FREE); await claim(r, tok); await r.until("!document.querySelector('#layer .spinner')", 15000); await r.wait(1500)
                coins = await r.ev("__tones.filter(f=>f===988).length")
                check(f'sound {"on" if on else "off"}: a claimed token: the app\'s own coin, no second one from the notice' if on else 'sound off: a claimed token: silent', coins == (1 if on else 0), coins)
                await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            await r.ev("Nutcade.S.prefs.sound=false; window.NutPrefs.sound=false")

        # ---------- locked: no amounts on the lock screen or in system notifications; the summary after unlocking ----------
        if want('locked'):
            await dismiss(r); await set_pin(r)
            if not await r.ev("!!Nutcade.S.prefs.arrNotify"):
                await settings(r); await r.ev("document.querySelector('#p_arrNotify')&&document.querySelector('#p_arrNotify')?.click()"); await r.wait(600)
            await r.home()
            # a detailed notification while unlocked (background tab), then the app locks
            t_seen = int(time.time() * 1000); await r.ev("__sys.length=0")
            await r.ev("__hide(true)"); a = next(amt); line = await arrive('npc', FREE, a, hidden=True)
            before = await r.ev(SYSN_JS)
            sysn = await r.ev("__sys")
            check('with a PIN: a system notification never shows the amount or the mint, only "Money arrived. Open NUTCADE to see."',
                  bool(sysn) and bool(before) and all(not re.search(r'\d|Mint|SAT', n['body'] + n['title']) and 'Open NUTCADE to see' in n['body'] for n in sysn + before), (sysn, before))
            async def lock(): await r.pg.reload(); await r.wait(1500)
            async def look_locked():
                await r.wait(1500)
                body = await r.ev("document.body.innerText")
                ns = await r.ev(SYSN_JS)
                amts = [fmtn(x) for x in (1301, 1302, 1303, 1304, 1111, 1305, a)] + [str(x) for x in (1301, 1302, 1303, 1304, 1111, 1305, a)]
                check('locked: the lock screen shows no amount', not any(x in body for x in amts) and 'SAT' not in body, body[:300])
                check('locked: system notifications show no amount', bool(ns) and not any(re.search(r'\d', n['body'] + n['title']) for n in ns), ns)
                check('locked: they say only "Money arrived, unlock to see"', bool(ns) and all(re.search(r'unlock', n['body'], re.I) for n in ns), ns)
                check('locked: the lock screen says the same, without amounts', bool(re.search(r'Money arrived', body)) and bool(re.search(r'unlock to see', body, re.I)), body[:300])
                await shot(r, 'locked-390')
            async def unlock_r():
                await unlock(r); return r
            lines = await away_batch('locked, unlocked', lock, unlock_r, after_close=look_locked, t0=t_seen, extra={a: 'npc'}, shotname='summary-unlocked-390')
            check('locked: the arrival shown only as a notification while unlocked is in the summary (it was never seen in the app)', bool(line) and line['id'] in [l['id'] for l in lines])
            ns = await r.ev(SYSN_JS)
            check('unlocked: the "unlock to see" notifications are cleared', not ns, ns)
            await r.pg.reload(); await r.wait(900); await unlock(r); await settled(r)
            check('locked: unlocking again repeats nothing', not await cards(r))

        # ---------- restore from the 12 words: no flood of notices for old history ----------
        if want('restore'):
            x = await wallet(b)
            await x.pg.check('#ack'); await x.click('[data-act=gateRestore]'); await x.wait(300)
            await x.fill('#phraseIn', words)
            await x.ev(f"(()=>{{const t=document.querySelector('#rmExtra'); t.value={J(FREE + chr(10) + FEE)}; t.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")
            await x.click('[data-act=doRestorePhrase]')
            await x.until("/CONTINUE|SCAN COMPLETE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 90000)
            await x.ev("document.querySelector('#layer [data-act=close]')&&document.querySelector('#layer [data-act=close]').click()"); await x.wait(300)
            if await x.ev("!!document.querySelector('[data-act=gateStart]')"): await x.click('[data-act=gateStart]'); await x.wait(400)
            await x.ev("Nutcade.closeSheet()"); await x.wait(6000)
            rec = await x.ev("Nutcade.S.txs.filter(t=>t.type==='in').length")
            check('restore: (the 12 words brought the sats back)', rec > 0 and await x.bal() > 0, (rec, await x.bal()))
            check('restore: no notices and no summary for old history', not await cards(x) and not await x.ev(LOG_JS), (await cards(x), await x.ev(LOG_JS)))
            await x.pg.reload(); await x.wait(700); await settled(x)
            check('restore: none after a reload either', not await cards(x))
            await x.add_mint(FREE); await x.use(FREE); a = next(amt); tok = await token_from(p, a, FREE); await claim(x, tok)
            await x.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.amount==={a}&&t.status==='done')", 15000); await x.wait(1500)
            log = await x.ev(LOG_JS)
            check('restore: a new arrival afterwards gets its one notice', len(log) == 1 and len(log[0]['ids']) == 1, log)
            await x.pg.context.close()

        # ---------- the duress PIN's wallet: only the open wallet's own arrivals ----------
        if want('duress'):
            d = await wallet(b, notif=True); await d.create(); await d.add_mint(FREE); await d.use(FREE); await d.receive_ln(3000); await d.wait(1500)
            dpk = await npub_hex(d)
            await set_pin(d)
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250)
            await pad(d, PIN); await d.wait(800); await pad(d, DPIN); await d.wait(300); await pad(d, DPIN)
            await d.until("!!document.querySelector('#duressAmt')", 8000); await d.fill('#duressAmt', '300'); await d.click('[data-act=duressMake]')
            await d.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await d.ev("Nutcade.closeSheet()")
            await settings(d); await d.ev("document.querySelector('#p_arrNotify')?.click()"); await d.wait(600); await d.home(); await dismiss(d)
            # the real wallet gets ecash in a background tab (a detailed notification), then the app locks
            await d.ev("__hide(true)"); await d.ev("__sys.length=0"); await dm(p, dpk, 777, FREE)
            ok = await d.until("Nutcade.S.txs.some(t=>t.amount===777&&t.status==='done')", 20000); await d.wait(1500)
            check('duress: (the real wallet got 777 SAT in a background tab)', ok)
            sysn = await d.ev("__sys")
            check('duress PIN set up: the real wallet\'s system notification is the one a PIN alone gives (no amount, only "Money arrived. Open NUTCADE to see.")', ok and len(sysn) == 1 and sysn[0]['title'] == 'NUTCADE' and sysn[0]['body'] == 'Money arrived. Open NUTCADE to see.', sysn)
            real_ids = await d.ev("Nutcade.S.txs.map(t=>t.id)")
            await d.pg.reload(); await d.wait(1500)
            ns = await d.ev(SYSN_JS); body = await d.ev("document.body.innerText")
            check('duress set: locked, as with a PIN alone: only "Money arrived, unlock to see", no amount (the duress wallet has the same, so it gives nothing away)', [(n['title'], n['body']) for n in ns] == [('NUTCADE', 'Money arrived, unlock to see.')] and bool(re.search(r'Money arrived, unlock to see', body)) and '777' not in body, (ns, body[:200]))
            await d.ev("__hide(false)")
            await unlock(d, DPIN); await settled(d)
            check('duress wallet: no summary of the real wallet\'s arrival', not await cards(d), await cards(d))
            check('duress wallet: its record of arrivals knows nothing of the real wallet', await has(d) and not await d.ev(f"(ids=>{{const j=JSON.stringify(NutArrivals.ledger()); return ids.some(i=>j.includes(i))}})({J(real_ids)})"))
            a = 888; tok = await token_from(p, a, FREE)
            async def slow(route): await asyncio.sleep(1.5); await route.continue_()
            await d.pg.route(re.compile(re.escape(FREE) + r'/v1/swap$'), slow); await d.ev("__sys.length=0")
            await claim(d, tok); await d.wait(200); await d.ev("__hide(true)")
            await d.until(f"Nutcade.S.txs.some(t=>t.amount===888&&t.status==='done')", 15000); await d.wait(1500); await d.pg.unroute_all()
            sysn = await d.ev("__sys")
            check('duress wallet: its arrival in a background tab gives the same notification a PIN alone gives', len(sysn) == 1 and sysn[0]['title'] == 'NUTCADE' and sysn[0]['body'] == 'Money arrived. Open NUTCADE to see.', sysn)
            await d.ev("__hide(false)"); await d.wait(300)
            cs = await cards(d)
            check('duress wallet: its own arrival gets a notice', len(cs) == 1 and '+888 SAT' in cs[0]['text'], cs)
            await shot(d, 'notice-duress-390')
            await d.ev("__hide(true)"); await dm(p, dpk, 999, FREE); await d.wait(4000)
            check('duress wallet: ecash sent to the real wallet isn\'t seen here', not await d.ev("Nutcade.S.txs.some(t=>t.amount===999)"))
            await d.ev("__hide(false)")
            await d.pg.reload(); await d.wait(900); await unlock(d, PIN); await settled(d)
            sm = await summary_rows(d)
            amts = await d.ev(f"(ids=>Nutcade.S.txs.filter(t=>ids.includes(t.id)).map(t=>t.amount))({J(sm['ids'] if sm else [])})")
            check('real wallet: its summary has its own arrivals (777 SAT seen only as a notification, 999 SAT) and nothing of the duress wallet (888 SAT)', bool(sm) and sorted(amts) == [777, 999] and '888' not in sm['text'], (amts, sm and sm['text']))
            await d.pg.context.close()

        # ---------- five languages: the notice and the summary, numbers written the language's way ----------
        if want('langs'):
            await r.ev("Nutcade.closeSheet()")
            for lang in ['en', 'es', 'pt', 'de', 'fr']:
                await set_lang(r, lang); await dismiss(r); await r.ev("__i18nMiss=new Set()")
                tok = await token_from(p, 2500, FREE); await claim(r, tok)
                await r.until("!document.querySelector('#layer .spinner')", 15000); await r.wait(1500); await r.ev("Nutcade.closeSheet()"); await r.wait(300)
                cs = [c for c in await cards(r) if c['type'] == 'live']
                txt = cs[0]['text'] if cs else ''
                miss = [m for m in await r.ev("[...(window.__i18nMiss||[])]") if any(m in c['text'] for c in cs)]
                check(f'{lang}: the notice is in the language, with 2,500 written its way', bool(cs) and ('+' + fmtn(2500, lang) + ' SAT') in txt and (lang == 'en' or LABEL['token'] not in txt) and not miss, (txt, miss))
                await shot(r, f'notice-{lang}-390')
                await looks(r, f'{lang}: the notice', details=False)
                await dismiss(r)
                pg0 = r.pg; await pg0.close()
                await dm(p, rpk, 2500, FREE)
                r = await wallet(b, ctx=r_ctx)
                if await r.ev("!!document.querySelector('[data-pinpad]')"): await unlock(r)
                await settled(r); await r.wait(400)
                await looks(r, f'{lang}: the summary')
                await r.ev("Nutcade.closeSheet()")
                if not await r.ev("!!document.querySelector('#arrStack .arr-card[data-type=away]')"):   # (Details took the card: open the page again for the rest)
                    pg0 = r.pg; await pg0.close(); await dm(p, rpk, 2500, FREE); r = await wallet(b, ctx=r_ctx)
                    if await r.ev("!!document.querySelector('[data-pinpad]')"): await unlock(r)
                    await settled(r); await r.wait(400)
                await shot(r, f'summary-{lang}-390')
                await r.pg.set_viewport_size({'width': 568, 'height': 320}); await r.wait(200); await shot(r, f'summary-{lang}-568x320'); await r.pg.set_viewport_size({'width': 390, 'height': 844})
                sm = await summary_rows(r)
                miss = [m for m in await r.ev("[...(window.__i18nMiss||[])]") if sm and m in sm['text']]
                check(f'{lang}: the summary is in the language, numbers written its way', bool(sm) and fmtn(2500, lang) in sm['text'] and (lang == 'en' or 'while you were away' not in sm['text'].lower()) and not miss, (sm and sm['text'], miss))
                check(f'{lang}: the summary doesn\'t rely on color alone (a sign and words)', bool(sm) and '+' in sm['text'])
                await r.ev("Nutcade.closeSheet()"); await dismiss(r)
                await settings(r); helptxt = await r.ev("(document.querySelector('#arrNotifyHelp')||{}).textContent||''"); await r.home()
                check(f'{lang}: the notifications setting says what a PIN changes, in the language, and nothing of a duress PIN', bool(helptxt) and (('With a PIN' in helptxt) if lang == 'en' else ('With a PIN' not in helptxt and 'PIN' in helptxt)) and not re.search(r'duress|coacci|coação|Notfall|contrainte', helptxt, re.I), helptxt)
            await set_lang(r, 'en')

        # ---------- your own coins coming back are not money arriving (1.14 keyset check-up, 1.15 printed tokens) ----------
        if want('own'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            log0 = len(await r.ev(LOG_JS)); n_in = lambda: r.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done').length")
            # coins the check-up set aside (the mint refused them then), offered again and accepted: a line "Coins the mint accepts again"
            got = await r.ev(f"""(async()=>{{const u={J(FREE)}; const m=Nutcade.S.mints.find(m=>m.url===u); if(m&&!m.ks) m.ks={{}}; const ks=Nutcade.r9.status(u); const ps=Nutcade.S.proofs[u]; const k=ps.filter(p=>p.amount>=64).slice(0,2); if(!ks||k.length<2) return 'setup';
              const ids=new Set(k.map(p=>p.secret)); Nutcade.S.proofs[u]=ps.filter(p=>!ids.has(p.secret)); ks.aside=(ks.aside||[]).concat(k); ks.asideAt=Date.now();
              await Nutcade.r9.check(u, {{manual:true}}); return Nutcade.S.txs.find(t=>t.note==='Coins the mint accepts again'&&t.type==='in')||'none'}})()""")
            await r.wait(1500)
            check('keyset check-up: (coins set aside came back, with their own line)', isinstance(got, dict) and got.get('upkeep') and got.get('status') == 'done', got)
            check('keyset check-up: coins set aside coming back are not announced as money arriving (they are your own)', isinstance(got, dict) and not [e for e in (await r.ev(LOG_JS))[log0:] if got['id'] in e['ids']] and got['id'] not in await pend(r, got['id']) and not await cards(r))
            # printed tokens: one taken back, one claimed by someone else
            await r.home(); await r.click('[data-act=send]'); await r.wait(150)
            await r.click('[data-act=ptOpen]'); await r.until("!!document.querySelector('#ptAmt') || !!document.querySelector('.pt-intro')", 5000)
            if await r.ev("!!document.querySelector('.pt-intro')"): await r.click('[data-act=ptIntroOk]'); await r.until("!!document.querySelector('#ptAmt')", 5000)
            await r.fill('#ptAmt', '100'); await r.fill('#ptCount', '2'); await r.click('[data-act=ptNext]')
            await r.until("!!document.querySelector('[data-act=ptMake]') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 20000)
            await r.click('[data-act=ptMake]'); await r.until("!!document.querySelector('.pt-ready') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 120000); await r.wait(300)
            bid = await r.ev("(document.querySelector('.pt-ready')||{dataset:{}}).dataset.b||null")
            toks = await r.ev(f"Nutcade.S.txs.filter(t=>t.print&&t.print.b==={J(bid)})") if bid else []
            check('printed tokens: (two made)', len(toks) == 2, (bid, len(toks)))
            if len(toks) == 2:
                log0 = len(await r.ev(LOG_JS)); await r.ev("Nutcade.closeSheet()"); await r.click('[data-act=tab][data-tab=history]'); await r.wait(150)
                await r.click('[data-act=ptList]'); await r.until("!!document.querySelector('.pt-list')", 5000)
                await r.click(f'[data-act=ptTake][data-id="{toks[0]["id"]}"]'); await r.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.status==='done'&&/^Reclaimed: /.test(t.note||'')&&t.ts>Date.now()-60000)", 20000); await r.wait(1500)
                back = await r.ev("Nutcade.S.txs.find(t=>t.type==='in'&&/^Reclaimed: /.test(t.note||''))")
                check('printed token taken back: (its line)', bool(back) and back['status'] == 'done', back)
                check('printed token taken back: not announced as money arriving', bool(back) and not [e for e in (await r.ev(LOG_JS))[log0:] if back['id'] in e['ids']] and back['id'] not in await pend(r, back['id']))
                n0 = await n_in(); log1 = len(await r.ev(LOG_JS))
                await claim(p, toks[1]['token']); await p.until("!document.querySelector('#layer .spinner')", 20000); await p.ev("Nutcade.closeSheet()")
                await r.ev("Nutcade.closeSheet()"); await r.click('[data-act=tab][data-tab=history]'); await r.wait(150)
                await r.click('[data-act=ptList]'); await r.until("!!document.querySelector('.pt-list')", 5000); await r.ev("document.querySelector('[data-act=ptCheck]')?.click()")
                await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(toks[1]['id'])})||{{}}).status==='claimed'", 20000); await r.wait(1500)
                check('printed token claimed by someone else: (marked claimed here)', await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(toks[1]['id'])}).status") == 'claimed')
                check('printed token claimed by someone else: nothing announced here (no new line coming in, no notice)', await n_in() == n0 and len(await r.ev(LOG_JS)) == log1)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r); await r.home()

        # ---------- your own token coming back, every way (1.16.0 recheck): by your own hand it is never an arrival
        # (a printed or plain token pasted back into Receive, the same with the mint's answer lost and settled after a
        # reload, a gift taken back by hand); a gift nobody opened, coming back by itself, is ("Came back to you") ----------
        if want('own2'):
            async def relock(w):   # (a PIN set by an earlier section: unlock after a reload)
                if await w.ev("!!document.querySelector('[data-pinpad]')"): await unlock(w)
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            n_in = lambda: r.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done').length")
            def newest_in(t0): return r.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0})||null")
            async def not_announced(label, line, log0):
                check(f'{label}: (its line, the sats back)', bool(line) and line.get('status') == 'done', line)
                ev = [e for e in (await r.ev(LOG_JS))[log0:] if line and line['id'] in e['ids']]
                seen = await r.ev("window.NutArrivals?NutArrivals.ledger().seen.map(x=>x[0]):null")
                check(f'{label}: not announced as money arriving (no notice, not waiting for a summary, not on the arrivals record)', bool(line) and not ev and line['id'] not in await pend(r, line['id']) and seen is not None and line['id'] not in seen and not await cards(r), (ev, await cards(r)))
            # printed token, scanned back into your own Receive
            await r.home(); await r.click('[data-act=send]'); await r.wait(150)
            await r.click('[data-act=ptOpen]'); await r.until("!!document.querySelector('#ptAmt') || !!document.querySelector('.pt-intro')", 5000)
            if await r.ev("!!document.querySelector('.pt-intro')"): await r.click('[data-act=ptIntroOk]'); await r.until("!!document.querySelector('#ptAmt')", 5000)
            await r.fill('#ptAmt', '120'); await r.fill('#ptCount', '1'); await r.click('[data-act=ptNext]')
            await r.until("!!document.querySelector('[data-act=ptMake]') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 20000)
            await r.click('[data-act=ptMake]'); await r.until("!!document.querySelector('.pt-ready') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 120000); await r.wait(300)
            bid = await r.ev("(document.querySelector('.pt-ready')||{dataset:{}}).dataset.b||null")
            pt = await r.ev(f"Nutcade.S.txs.find(t=>t.print&&t.print.b==={J(bid)})||null") if bid else None
            check('own2 printed token: (made)', bool(pt), bid)
            if pt:
                await r.ev("Nutcade.closeSheet()"); await dismiss(r); log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
                await claim(r, pt['token']); await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(pt['id'])})||{{}}).status==='reclaimed'", 20000); await r.wait(1500)
                await not_announced('own2 printed token scanned back into your own Receive', await newest_in(t0), log0)
                await r.ev("Nutcade.closeSheet()")
            # a plain token you made, pasted back
            await dismiss(r); tok = await token_from(r, 130, FREE); await r.wait(300); log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await claim(r, tok); await wait_line(r, f"t.ts>={t0}"); await r.wait(1500)
            await not_announced('own2 a token you made, pasted back into Receive', await newest_in(t0), log0)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            # the same with the mint's answer lost (the mint swapped it, the page never heard): settled after a reload
            tok = await token_from(r, 140, FREE); await r.wait(300); t0 = await r.ev("Date.now()")
            async def lose(route):
                try: await route.fetch()
                except Exception: pass
                await route.abort()
            await r.pg.route(re.compile(re.escape(FREE) + r'/v1/swap$'), lose)
            await claim(r, tok); await r.wait(2500); await r.pg.unroute(re.compile(re.escape(FREE) + r'/v1/swap$')); await r.ev("Nutcade.closeSheet()")
            await r.pg.reload(); await r.wait(700); await relock(r); await settled(r); await r.wait(1500)
            await wait_line(r, f"t.ts>={t0}", 30000); await r.wait(1000)
            await not_announced('own2 a token you made, pasted back, the mint\'s answer lost and settled after a reload', await newest_in(t0), 0)
            await dismiss(r)
            # the same at a mint that takes only 3 coins per request (its info says so here): claimed in parts, none announced
            tok = await token_from(r, 255, FREE); await r.wait(300); t0 = await r.ev("Date.now()")
            ncoins = None
            INFO = re.compile(re.escape(FREE) + r'/v1/info$')
            async def small(route):
                resp = await route.fetch(); d = await resp.json(); d['max_array_length'] = 3; await route.fulfill(response=resp, json=d)
            await r.pg.route(INFO, small); await r.pg.reload(); await r.wait(700); await relock(r); await settled(r); await r.wait(500); await dismiss(r)
            await r.ev(f"Nutcade.r8.mintMax({J(FREE)})")
            await claim(r, tok); await r.until(f"Nutcade.S.txs.some(t=>t.token==={J(tok)}&&t.status==='reclaimed')", 40000); await r.wait(2000)
            lines = await r.ev(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.ts>={t0}).map(t=>({{id:t.id, status:t.status, amount:t.amount, back:t.back||null, note:t.note}}))")
            seen = await r.ev("NutArrivals.ledger().seen.map(x=>x[0])"); mx = await r.ev(f"Nutcade.r8.mintMax({J(FREE)})")
            check('own2 a token you made, pasted back at a mint taking 3 coins per request: claimed in parts', mx == 3 and len([l for l in lines if l['status'] == 'done']) >= 2 and sum(l['amount'] for l in lines if l['status'] == 'done') == 255, (mx, ncoins, lines))
            check('own2 ... in parts: no part announced as money arriving (no notice, nothing on the arrivals record)', bool(lines) and not [l for l in lines if l['id'] in seen] and not await cards(r), (lines, await cards(r)))
            await r.pg.unroute(INFO); await r.pg.reload(); await r.wait(700); await relock(r); await settled(r); await dismiss(r)
            # gifts: one taken back by hand, one coming back by itself
            gifts = {}
            for k in ('hand', 'auto'):
                pub = await r.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return Array.from(CashuLib.getPubKeyFromPrivKey(k),x=>x.toString(16).padStart(2,'0')).join('')})()")
                o = {'locktime': int(time.time()) + 2, 'txx': {'lockUntil': int(time.time() * 1000) + 3600e3, 'giftTo': 'Friend ' + k}}
                gifts[k] = await r.ev(f"Nutcade.r8.sendEcash(150, 'gift', {J(pub)}, {J(FREE)}, {J(o)}).then(t=>t.id, e=>'ERR '+e.message)")
            check('own2 gifts: (two made)', all(not str(v).startswith('ERR') for v in gifts.values()), gifts)
            await r.wait(3500); await r.ev("Nutcade.S.txs.filter(t=>t.lockUntil&&t.status==='pending'&&t.giftTo==='Friend hand').forEach(t=>t.lockUntil=Date.now()-60000)")
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await r.ev("Nutcade.closeSheet()"); await r.click('[data-act=tab][data-tab=history]'); await r.wait(200)
            await r.ev(f"document.querySelector('#txList [data-id=\"{gifts['hand']}\"]').click()"); await r.wait(300); await r.click('#layer [data-act=giftTake]')
            await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(gifts['hand'])})||{{}}).status==='reclaimed'", 20000); await r.wait(1500)
            await not_announced('own2 a gift taken back by hand', await newest_in(t0), log0)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r); await r.home()
            await r.ev("Nutcade.S.txs.filter(t=>t.lockUntil&&t.status==='pending').forEach(t=>t.lockUntil=Date.now()-60000)")
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await r.ev("Nutcade.r8.refundExpired()"); await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(gifts['auto'])})||{{}}).status==='reclaimed'", 20000); await r.wait(1500)
            line = await newest_in(t0); cs = await cards(r)
            check('own2 a gift nobody opened, coming back by itself: announced once, "Came back to you"', bool(line) and len([e for e in (await r.ev(LOG_JS))[log0:] if line['id'] in e['ids']]) == 1 and any('Came back to you' in c['text'] for c in cs), (line, cs))
            await dismiss(r)

        # ---------- one message per arrival (1.16.0 recheck): no "+X received" toast beside the notice ----------
        if want('toast'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            await r.ev("""(()=>{window.__toasts=[]; if(window.__toastObs) return; const seen=()=>{const e=document.getElementById('toast'); if(e&&!e.hidden&&e.textContent) window.__toasts.push(e.textContent)};
              window.__toastObs=new MutationObserver(seen); window.__toastObs.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden']})})()""")
            for kind, sheet in (('ln', True), ('ln', False), ('nostr', False), ('request', False)):
                await r.ev("window.__toasts=[]"); await dismiss(r); t0 = await r.ev("Date.now()"); a = next(amt)
                if kind == 'ln':
                    await ln_invoice(r, a, FREE)
                    if not sheet: await r.ev("Nutcade.closeSheet()")
                elif kind == 'nostr': await dm(p, rpk, a, FREE)
                else:
                    enc = await r.ev(f"Nutcade.r8.newRequest({a}, 'Pizza').encoded"); await r.wait(600); await pay_request(p, enc, FREE)
                await wait_line(r, f"t.ts>={t0}&&t.amount==={a}", 25000)
                await r.until("!!document.querySelector('#arrStack .arr-card')", 8000); await r.wait(1500)
                ts = await r.ev("window.__toasts"); cs = await cards(r)
                label = f'{kind}{" (Receive sheet open)" if sheet else ""}'
                check(f'toast: {label}: the notice says it once (no "+{a} received" toast beside it)', bool(cs) and not [t for t in ts if re.search(r'received|deposited', t)], (ts, [c['text'] for c in cs]))
                await r.ev("Nutcade.closeSheet()")
            await dismiss(r); await r.home()

        # ---------- a sender's memo is only the sender's words (1.16.0 fix round, finding 1): a stranger's ecash whose
        # memo reads like one of the app's own notes is still money arriving, over Nostr, pasted or scanned ----------
        if want('memo'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            for memo in OWN_NOTES:
                for way in ('nostr', 'paste', 'scan'):
                    await r.ev("Nutcade.closeSheet()"); await dismiss(r); a = next(amt); log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
                    if way == 'nostr': await dm(p, rpk, a, FREE, memo)
                    else:
                        tok = await p.ev(WITH_MEMO_JS % (J(await token_from(p, a, FREE)), J(memo)))
                        if way == 'paste': await claim(r, tok)
                        else:   # (what the scanner does with a token it read: Receive, filled in)
                            await r.home(); await r.ev(f"Nutcade.handleScan({J(tok)})")
                            await r.until(f"(document.querySelector('#tokIn')||{{}}).value==={J(tok)}", 5000); await r.click('[data-act=doReceiveToken]')
                    ok = await wait_line(r, f"t.ts>={t0}&&t.amount==={a}", 25000); await r.wait(1500)
                    line = await r.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}&&t.amount==={a})||null")
                    ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]
                    cs = [c for c in await cards(r) if c['type'] == 'live']
                    lab = LABEL['nostr'] if way == 'nostr' else LABEL['token']
                    check(f'memo {memo!r}, {way}: a stranger\'s ecash is announced once, as "{lab}" (the memo is the sender\'s, never read as the app\'s own note)',
                          ok and bool(line) and (line.get('note') or '').startswith(memo) and ann == [line['id']] and len(cs) == 1 and lab in cs[0]['text'] and 'Came back to you' not in cs[0]['text'] and not line.get('back') and not line.get('self'),
                          (line and line.get('note'), ann, [c['text'] for c in cs]))
            await r.ev("Nutcade.closeSheet()"); await dismiss(r)

        # ---------- the app's own lines are marked by the code that writes them (finding 1, the other side): never
        # announced, whatever their note says ----------
        if want('own3'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            async def own_line(label, t0, pred, log0):
                line = await r.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}&&({pred}))||null")
                ev = [e for e in (await r.ev(LOG_JS))[log0:] if line and line['id'] in e['ids']]
                seen = await r.ev(SEEN_JS)
                check(f'{label}: (its line, the sats back)', bool(line) and num_ok(line), line)
                check(f'{label}: not announced as money arriving (no notice, not waiting for a summary, not on the arrivals record)',
                      bool(line) and not ev and seen is not None and line['id'] not in seen and not [c for c in await cards(r) if line['id'] in c['ids']],
                      (line and {k: line.get(k) for k in ('note', 'back', 'self')}, ev))
            # a token you sent, taken back from its line in your notes (Take back)
            tx = await r.ev("Nutcade.r8.sendEcash(160, 'lunch').then(t=>t.id)"); await r.wait(300)
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await r.ev("Nutcade.closeSheet()"); await r.click('[data-act=tab][data-tab=history]'); await r.wait(200)
            await r.ev(f"document.querySelector('#txList [data-id=\"{tx}\"]').click()"); await r.wait(300); await r.click('#layer [data-act=reclaim]')
            await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(tx)})||{{}}).status==='reclaimed'", 20000); await r.wait(1500)
            await own_line('own3 a token you sent, taken back from your notes', t0, "/^Reclaimed: /.test(t.note||'')", log0)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r); await r.home()
            # an Extra Life set up, then cashed out
            heir = await p.ev(f"CashuLib.nprofileEncode({{pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:[{J(NOSTR)}]}})")
            await r.click('[data-act=extraOpen]'); await r.until("!!document.querySelector('#xlTo')", 5000); await r.wait(150)
            await r.ev("(()=>{const s=document.querySelector('#xlTo'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true}))})()")
            await r.fill('#xlKey', heir); await r.fill('#amtIn', '300'); await r.click('[data-act=extraStart]')
            xl = await r.until("!!Nutcade.S.extra", 30000); await r.wait(1000); await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await r.home(); await r.click('[data-act=extraOpen]'); await r.wait(300); await r.click('[data-act=extraCash]'); await r.wait(200); await r.click('[data-act=extraCashGo]')
            xo = await r.until("!Nutcade.S.extra", 30000); await r.wait(1500)
            check('own3 Extra Life: (set up, then cashed out)', xl and xo, (xl, xo, await r.err()))
            await own_line('own3 an Extra Life you cashed out', t0, "/^Extra Life cashed out/.test(t.note||'')", log0)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            # coins found again: Find lost ecash (a coin this wallet lost track of), a backup that has a coin this wallet doesn't
            for how in ('find', 'backup'):
                bk = await r.ev("Promise.resolve(Nutcade.r8.backupData()).then(d=>typeof d==='string'?d:JSON.stringify(d))") if how == 'backup' else None
                lost = await r.ev(f"(()=>{{const u={J(FREE)}, ps=Nutcade.S.proofs[u]||[], x=ps.find(p=>p.amount>=8&&p.amount<=512); if(!x) return 0; Nutcade.S.proofs[u]=ps.filter(p=>p!==x); return x.amount}})()")
                log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
                if how == 'find':
                    await settings(r); await r.click('[data-act=findLost]')
                    await r.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.ts>={t0}&&/^Recovered with recovery phrase/.test(t.note||''))", 180000); await r.wait(1500)
                    await own_line(f'own3 Find lost ecash ({lost} SAT found again)', t0, "/^Recovered with recovery phrase/.test(t.note||'')", log0)
                else:
                    res = await r.ev(f"Nutcade.r8.importBackup(JSON.parse({J(bk)})).then(()=>'ok', e=>'ERR '+e.message)"); await r.wait(2000)
                    await own_line(f'own3 a backup imported, with a coin this wallet lost track of ({lost} SAT, {res})', t0, "/^Restored from backup/.test(t.note||'')", log0)
                await r.ev("Nutcade.closeSheet()"); await dismiss(r); await r.home()
            # ecash under another phrase, swept into this wallet
            q = await wallet(b); qwords = await q.create(); await q.add_mint(FREE); await q.use(FREE); await q.receive_ln(400); await q.wait(1000); await q.pg.context.close()
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await settings(r); await r.click('[data-act=sweepOpen]'); await r.until("!!document.querySelector('#phraseIn')", 5000)
            await r.ev(f"(()=>{{const t=document.querySelector('#phraseIn'); t.value={J(qwords)}; t.dispatchEvent(new Event('input',{{bubbles:true}})); document.querySelectorAll('[data-rmint]').forEach(i=>i.checked=false); document.querySelector('#rmExtra').value={J(FREE)}}})()")
            await r.click('[data-act=doSweep]'); await r.until("/SCAN COMPLETE|BONUS ROUND/.test((document.querySelector('.sheet-body')||{}).innerText||'') || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 120000); await r.wait(1500)
            await own_line('own3 ecash under another phrase, swept into this wallet', t0, "/^Restored from another phrase/.test(t.note||'')", log0)
            await r.ev("Nutcade.closeSheet()"); await dismiss(r); await r.home()

        # ---------- your own token, brought back in another encoding (finding 2): found by its coins, not its text ----------
        if want('reenc'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r)
            for way in ('sound', 'nfc', 'qr'):
                own = await r.ev("Nutcade.r8.sendEcash(180, '').then(t=>({id:t.id, token:t.token}))"); await r.wait(300)
                text = await r.ev(REENC_JS % (J(own['token']), J(way)))
                log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
                await r.ev("Nutcade.closeSheet()"); await r.home(); await r.ev(f"Nutcade.handleScan({J(text)})")
                await r.until(f"(document.querySelector('#tokIn')||{{}}).value==={J(text)}", 5000); await r.click('[data-act=doReceiveToken]')
                await wait_line(r, f"t.ts>={t0}"); await r.wait(1500)
                line = await r.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0})||null")
                st = await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(own['id'])}).status")
                ev = [e for e in (await r.ev(LOG_JS))[log0:] if line and line['id'] in e['ids']]
                check(f'reenc {way}: (your own token, read back {"as other text" if text != own["token"] else "as the same text"}, claimed back)', bool(line) and line['amount'] == 180 and not text.startswith('ERR'), (text[:30], line))
                check(f'reenc {way}: not announced as money arriving (brought back by your hand)', bool(line) and line.get('back') == 'hand' and not ev and line['id'] not in await r.ev(SEEN_JS) and not await cards(r), (line and line.get('back'), ev, await cards(r)))
                check(f'reenc {way}: its sent line says reclaimed (not "claimed" by someone)', st == 'reclaimed', st)
                await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            # someone else's token for the same amount while one of yours is out: theirs is money arriving, yours stays out
            mine = await r.ev("Nutcade.r8.sendEcash(170, '').then(t=>t.id)")
            log0 = len(await r.ev(LOG_JS)); t0 = await r.ev("Date.now()")
            await claim(r, await token_from(p, 170, FREE)); await wait_line(r, f"t.ts>={t0}"); await r.wait(1500); await r.ev("Nutcade.closeSheet()")
            line = await r.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0})||null")
            st = await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(mine)}).status")
            ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]
            check('reenc someone else\'s token, the same amount as one of yours still out: announced once; yours stays out', bool(line) and ann == [line['id']] and not line.get('back') and st == 'pending', (line, ann, st))
            await dismiss(r)

        # ---------- a deposit recovered after the mint's answer was lost (finding 4): announced exactly once, the
        # notice or the toast, never neither ----------
        if want('recover'):
            await r.ev("Nutcade.closeSheet()"); await r.use(FREE); await dismiss(r); await r.ev(TOASTS_JS)
            MINTRQ = re.compile(re.escape(FREE) + r'/v1/mint/bolt11$')
            blk = Block(); await blk.attach(r.pg, FREE)
            async def lose(route):   # (the mint signs; its answer never reaches the page, and the page hears nothing more of it for now)
                try: await route.fetch()
                except Exception: pass
                blk.on = True; await route.abort()
            async def lost_deposit(a):
                """a deposit the mint issued while this page never heard its answer: the line waits, the record keeps its counters"""
                await r.pg.route(MINTRQ, lose)
                txid = await ln_invoice(r, a, FREE)
                ok = await r.until(f"Nutcade.S.quotes.some(q=>q.txId==={J(txid)}&&q.ctr)", 15000); await r.wait(2500); await r.ev("Nutcade.closeSheet()")
                return txid, ok and await r.ev(f"(Nutcade.S.txs.find(t=>t.id==={J(txid)})||{{}}).status==='pending'")
            async def answer_again():   # (the mint can be heard again: the next round of checks finds the deposit issued)
                blk.on = False; await r.pg.unroute(MINTRQ); await r.ev("window.dispatchEvent(new Event('online'))")
            # the line still waiting: the recovery is its arrival (one notice, no toast beside it)
            a = next(amt); await r.ev("window.__toasts=[]"); log0 = len(await r.ev(LOG_JS))
            txid, ok = await lost_deposit(a)
            await answer_again()
            done = await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(txid)})||{{}}).status==='done'", 40000); await r.wait(2500)
            ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]; ts = await r.ev("window.__toasts")
            check('recover, its line still waiting: (the answer was lost, then the deposit was recovered from its record)', ok and done and await r.ev(f"Nutcade.S.txs.find(t=>t.id==={J(txid)}).amount") == a, (ok, done))
            check('recover, its line still waiting: announced exactly once (its notice, no toast beside it)', ann.count(txid) == 1 and not [t for t in ts if re.search(r'Recovered|received', t)], (ann, ts))
            await dismiss(r)
            # the recovered coins credited to a line that is done already and was announced (a later "Recovered X from an
            # interrupted deposit"): no notice again for the old line, so the toast says it
            a1 = next(amt); line1 = await ln_invoice(r, a1, FREE); await wait_line(r, f"t.id==={J(line1)}"); await r.wait(1500); await r.ev("Nutcade.closeSheet()"); await dismiss(r)
            a2 = next(amt); txid, ok = await lost_deposit(a2)
            await r.ev(f"(()=>{{const S=Nutcade.S, q=S.quotes.find(q=>q.txId==={J(txid)}); q.txId={J(line1)}; S.txs=S.txs.filter(t=>t.id!=={J(txid)})}})()")
            await r.ev("window.__toasts=[]"); log0 = len(await r.ev(LOG_JS))
            await answer_again()
            done = await r.until(f"(Nutcade.S.txs.find(t=>t.id==={J(line1)})||{{}}).amount==={a1 + a2}", 40000); await r.wait(2500)
            ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]; ts = await r.ev("window.__toasts")
            said = sorted(set(t for t in ts if 'Recovered' in t and fmtn(a2) in t))
            check('recover onto a line already done: (the new coins credited to it)', ok and done, (ok, done))
            check('recover onto a line already done: the new sats are said exactly once (the toast "Recovered X"), never lost', done and len(said) == 1 and line1 not in ann, (ts, ann))
            await dismiss(r); await r.home()

        # ---------- system notifications with a duress PIN (finding 3): exactly as with a PIN alone, in both wallets,
        # so neither a notification nor its absence tells anyone a duress PIN exists ----------
        if want('sysduress'):
            async def bg_claim(w, a):
                tok = await token_from(p, a, FREE)
                async def slow(route): await asyncio.sleep(1.5); await route.continue_()
                await w.pg.route(re.compile(re.escape(FREE) + r'/v1/swap$'), slow); await w.ev("__sys.length=0")
                await claim(w, tok); await w.wait(200); await w.ev("__hide(true)")
                ok = await w.until(f"Nutcade.S.txs.some(t=>t.amount==={a}&&t.status==='done')", 20000); await w.wait(1500); await w.pg.unroute_all()
                return ok
            async def notify(w, on):
                if await w.ev("!!Nutcade.S.prefs.arrNotify") != on: await settings(w); await w.ev("document.querySelector('#p_arrNotify')?.click()"); await w.wait(700)
                await w.ev("Nutcade.closeSheet()"); await w.home()
            async def observe(w, label, pin, a):
                """what someone holding this wallet sees: an arrival in a background tab with notifications off, then on, then locked"""
                o = {}
                await dismiss(w); await notify(w, False)
                ok1 = await bg_claim(w, a); o['off'] = [(n['title'], n['body']) for n in await w.ev("__sys")] + [(n['title'], n['body']) for n in await w.ev(SYSN_JS)]
                await w.ev("__hide(false)"); await w.wait(500); await w.ev("Nutcade.closeSheet()"); await dismiss(w)
                await notify(w, True)
                ok2 = await bg_claim(w, a + 1); o['on'] = [(n['title'], n['body']) for n in await w.ev("__sys")]
                o['shown'] = sorted((n['title'], n['body']) for n in await w.ev(SYSN_JS))
                await w.pg.reload(); await w.wait(2000)   # (locked, as after the auto-lock)
                o['locked'] = sorted((n['title'], n['body']) for n in await w.ev(SYSN_JS))
                o['lock screen'] = bool(re.search(r'Money arrived, unlock to see', await w.ev("document.body.innerText")))
                await unlock(w, pin); await settled(w); await w.wait(600)
                o['after unlock'] = await w.ev(SYSN_JS)
                o['summary'] = [c['type'] for c in await cards(w)]
                await w.ev("Nutcade.closeSheet()"); await dismiss(w)
                await settings(w); o['help'] = await w.ev("(document.querySelector('#arrNotifyHelp')||{}).textContent||''"); await w.ev("Nutcade.closeSheet()"); await w.home()
                check(f'sysduress {label}: (both arrivals came in)', ok1 and ok2, (ok1, ok2))
                return o
            GEN, LOCKED = ('NUTCADE', 'Money arrived. Open NUTCADE to see.'), ('NUTCADE', 'Money arrived, unlock to see.')
            seen = {}
            w1 = await wallet(b, notif=True); await w1.create(); await w1.add_mint(FREE); await w1.use(FREE); await w1.receive_ln(3000); await w1.wait(1500); await set_pin(w1)
            seen['a PIN only'] = await observe(w1, 'a PIN only', PIN, 531); await w1.pg.context.close()
            w2 = await wallet(b, notif=True); await w2.create(); await w2.add_mint(FREE); await w2.use(FREE); await w2.receive_ln(3000); await w2.wait(1500); await set_pin(w2)
            await settings(w2); await w2.click('[data-act=duressOpen]'); await w2.wait(250)
            await pad(w2, PIN); await w2.wait(800); await pad(w2, DPIN); await w2.wait(300); await pad(w2, DPIN)
            await w2.until("!!document.querySelector('#duressAmt')", 8000); await w2.fill('#duressAmt', '300'); await w2.click('[data-act=duressMake]')
            await w2.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await w2.ev("Nutcade.closeSheet()"); await w2.home()
            seen['a PIN and a duress PIN, the real wallet'] = await observe(w2, 'a PIN and a duress PIN, the real wallet', PIN, 541)
            await w2.pg.reload(); await w2.wait(900); await unlock(w2, DPIN); await settled(w2); await w2.wait(400); await dismiss(w2)
            check('sysduress (the duress PIN\'s wallet is open)', await w2.ev("!!Nutcade.vault.decoy"))
            seen['a PIN and a duress PIN, the duress PIN\'s wallet'] = await observe(w2, 'a PIN and a duress PIN, the duress PIN\'s wallet', DPIN, 551)
            ref = seen['a PIN only']
            check('sysduress a PIN only: notifications off, none; on, one that says only "Money arrived. Open NUTCADE to see."; locked, only "unlock to see", also on the lock screen; cleared on unlocking; the arrival in the summary',
                  ref['off'] == [] and ref['on'] == [GEN] and ref['shown'] == [GEN] and ref['locked'] == [LOCKED] and ref['lock screen'] and ref['after unlock'] == [] and ref['summary'] == ['away'], ref)
            for k, o in seen.items():
                if k == 'a PIN only': continue
                check(f'sysduress {k}: exactly what a PIN-only wallet shows (the same words in the same cases: nothing gives the duress PIN away, by text or by silence)', o == ref, {x: (o[x], ref[x]) for x in o if o[x] != ref[x]})
            check('sysduress the notifications help says nothing of a duress PIN', all('duress' not in o['help'].lower() and 'With a PIN' in o['help'] for o in seen.values()), [o['help'] for o in seen.values()])
            # the duress PIN turned off: its wallet's sats come back to the real one, and that is not money arriving
            await w2.pg.reload(); await w2.wait(900); await unlock(w2, PIN); await settled(w2); await dismiss(w2)
            log0 = len(await w2.ev(LOG_JS)); t0 = await w2.ev("Date.now()")
            await settings(w2); await w2.click('[data-act=duressOpen]'); await w2.wait(250); await pad(w2, PIN); await w2.until("!!document.querySelector('[data-act=duressOff]')", 8000)
            await w2.click('[data-act=duressOff]'); await w2.wait(300); await w2.click('[data-act=duressOffGo]'); await w2.until("!document.querySelector('[data-act=duressOffGo]')", 30000); await w2.wait(2000)
            back = await w2.ev(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}).map(t=>({{id:t.id, amount:t.amount, note:t.note, back:t.back||null}}))")
            sn = await w2.ev(SEEN_JS); ev = [e for e in (await w2.ev(LOG_JS))[log0:] if any(x['id'] in e['ids'] for x in back)]
            check('sysduress duress PIN turned off: (its wallet\'s sats came back: 300 + 551 + 552 SAT)', bool(back) and sum(x['amount'] for x in back) == 300 + 551 + 552 and all(x['note'] == "Back from the duress PIN's wallet" for x in back), back)
            check('sysduress duress PIN turned off: the sats coming back are not announced as money arriving', bool(back) and not ev and not [x for x in back if x['id'] in sn] and not await cards(w2), (back, ev))
            await w2.pg.context.close()

        # ---------- claims cut off by 1.15.0 (the upgrade side of finding 1) and your own token handed back over Nostr
        # (finding 2). The grid: every kind of claim record x saved by 1.16 (control) / saved by 1.15.0 (no marks) and
        # settled after a reload / saved by 1.15.0 inside a backup imported into another device. Each claim's mint answer
        # is lost (the mint signs, the page never hears it), so the claim is finished from its record. Our own coins are
        # never announced; what came back by itself is "Came back to you"; a stranger's ecash is announced whatever its
        # memo; the books are exact (balance up by the line, our sent token reclaimed). ----------
        if want('legacy'):
            # (a receiver of its own: the main one may have a PIN by now, and these cells reload it)
            rl = await wallet(b, notif=True); await rl.create(); await rl.add_mint(FREE); await rl.use(FREE)
            await rl.receive_ln(1000); await rl.wait(1500); await dismiss(rl); rlpk = await npub_hex(rl)
            ppk = await npub_hex(p)
            SWAP = re.compile(re.escape(FREE) + r'/v1/swap$'); HOLD = re.compile(re.escape(FREE) + r'/v1/(restore|checkstate)$')
            async def lose(route):
                try: await route.fetch()
                except Exception: pass
                await route.abort()
            async def drop(route): await route.abort()
            async def cut(): await rl.pg.route(SWAP, lose); await rl.pg.route(HOLD, drop)   # (from here the mint's answers are lost)
            # what 1.15.0 wrote: no back / self on a claim's record and no mk on it or on a part saved to claim later
            STRIP = "(o=>{delete o.back; delete o.self; delete o.mk})"
            STRIP_JS = f"""(()=>{{const s={STRIP}, ops=JSON.parse(localStorage.getItem('nutcade:ops')||'[]'), txs=JSON.parse(localStorage.getItem('nutcade:txs')||'[]');
              ops.forEach(s); txs.filter(t=>t.incoming).forEach(s); localStorage.setItem('nutcade:ops', JSON.stringify(ops)); localStorage.setItem('nutcade:txs', JSON.stringify(txs));
              Nutcade.S.ops.forEach(s); Nutcade.S.txs.filter(t=>t.incoming).forEach(s); return ops.length}})()"""
            SELF_JS = """(()=>{const ops=JSON.parse(localStorage.getItem('nutcade:ops')||'[]'); ops.forEach(o=>o.self=1); localStorage.setItem('nutcade:ops', JSON.stringify(ops)); Nutcade.S.ops.forEach(o=>o.self=1)})()"""
            BAL_JS = "(Nutcade.S.proofs[%s]||[]).reduce((t,p)=>t+p.amount,0)" % J(FREE)
            HEIR = {'name': 'Bob', 'pubkey': ppk}
            lx = iter(range(21, 999, 3))
            async def own_tok(a): return await rl.ev(f"Nutcade.r8.sendEcash({a}, 'for lunch').then(t=>({{id:t.id, token:t.token, sent:t.sent}}))")
            async def go(w, js): await w.ev(f"(()=>{{{js}.catch(()=>{{}}); return 1}})()")
            async def nostr_back(proofs, memo=None):   # (our own coins handed back by their receiver over Nostr, re-encoded)
                return await p.ev(f"""(async()=>{{const ev=CashuLib.nip17.wrapEvent(crypto.getRandomValues(new Uint8Array(32)), {{publicKey:{J(rlpk)}}}, JSON.stringify({{mint:{J(FREE)}, unit:'sat', proofs:{J(proofs)}, memo:{J(memo) if memo else 'undefined'}}}));
                  return await new Promise(res=>{{const ws=new WebSocket({J(NOSTR)}); ws.onopen=()=>ws.send(JSON.stringify(['EVENT',ev])); ws.onmessage=m=>{{const d=JSON.parse(m.data); if(d[0]==='OK'){{ws.close(); res(d[2])}}}}; setTimeout(()=>res('timeout'),8000)}})}})()""")
            # each kind: (name, starts the claim on rl and returns (note pattern, our sent line id or None), what its line is marked, announced as)
            async def k_takeback(a):
                o = await own_tok(a); await cut()
                await rl.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='reclaim'; b.dataset.id={J(o['id'])}; document.body.appendChild(b); b.click(); b.remove()}})()")
                return '^Reclaimed: ', o['id']
            async def k_paste(a):
                o = await own_tok(a); await cut(); await rl.home(); await rl.click('[data-act=receive]'); await rl.wait(150); await rl.click('[data-act=recvMethod][data-m=ecash]'); await rl.wait(100)
                await rl.fill('#tokIn', o['token']); await rl.fill('#noteIn', 'pasted back'); await rl.click('[data-act=doReceiveToken]'); return '^pasted back$', o['id']
            async def k_gift(a):
                o = await own_tok(a); await cut(); await go(rl, f"Nutcade.r8.recv({J(o['token'])}, 'Gift came back from Bob', {{own:true}})"); return '^Gift came back from Bob$', o['id']
            async def k_request(a):
                o = await own_tok(a); await cut(); await go(rl, f"Nutcade.r8.recv({J(o['token'])}, \"Payment request couldn't be delivered: the sats came back\", {{own:true}})"); return "^Payment request couldn't", o['id']
            async def k_extra(a):
                tok = await token_from(p, a, FREE); await cut()
                await go(rl, f"Nutcade.r8.recv({J(tok)}, 'Extra Life cashed out (was for Bob)', {{own:true, hand:true, follow:{{k:'extra-end', heir:{J(HEIR)}, secrets:[]}}}})"); return '^Extra Life cashed out', None
            async def k_duress(a):   # (the duress PIN turned off: its wallet's sats saved as "mine", then claimed)
                tok = await token_from(p, a, FREE)
                h = await rl.ev(f"Nutcade.r8.hold({J(tok)}, \"Back from the duress PIN's wallet\", {{mine:true, back:'hand'}}).id"); await cut()
                await go(rl, f"Nutcade.r8.recv({J(tok)}, \"Back from the duress PIN's wallet\", {{follow:{{k:'incoming', txId:{J(h)}, reqId:null}}}})"); return "^Back from the duress", None
            async def k_sweep(a):   # (a sweep of another phrase: its record is marked self when 1.16 writes it)
                tok = await token_from(p, a, FREE); await cut()
                await go(rl, f"Nutcade.r8.recv({J(tok)}, 'Restored from another phrase', {{}})"); return '^Restored from another phrase$', None
            async def k_heir(a):   # (an Extra Life left to you, claimed in parts: its parts are saved "mine", and it is money arriving)
                tok = await token_from(p, a, FREE)
                h = await rl.ev(f"Nutcade.r8.hold({J(tok)}, 'Extra Life from Bob (part 1 of 2)', {{mine:true, mk:1}}).id"); await cut()
                await go(rl, f"Nutcade.r8.recv({J(tok)}, 'Extra Life from Bob (part 1 of 2)', {{follow:{{k:'incoming', txId:{J(h)}, reqId:null}}}})"); return '^Extra Life from Bob', None
            async def k_memo(memo):
                async def f(a):
                    tok = await p.ev(WITH_MEMO_JS % (J(await token_from(p, a, FREE)), J(memo))); await cut(); await claim(rl, tok); return '^' + re.escape(memo) + '$', None
                return f
            async def k_memo_nostr(a):
                await cut(); await dm(p, rlpk, a, FREE, 'Gift came back from Bob'); return '^Gift came back from Bob$', None
            async def k_nostr_own(a):
                o = await own_tok(a); await cut(); await nostr_back([{k: v for k, v in x.items() if k != 'dleq'} for x in o['sent']], 'here you go'); return '^here you go$', o['id']
            KINDS_L = [   # name, start, mark, announced as (None: not announced), modes
                ('a token taken back (Take back)', k_takeback, ('back', 'hand'), None, 'all'),
                ('your own token pasted back', k_paste, ('back', 'hand'), None, 'all'),
                ('a gift nobody opened, back by itself', k_gift, ('back', 'auto'), 'Came back to you', 'all'),
                ("a payment request that couldn't be delivered", k_request, ('back', 'auto'), 'Came back to you', 'all'),
                ('an Extra Life cashed out', k_extra, ('back', 'hand'), None, 'all'),
                ("the duress PIN's wallet's sats coming back", k_duress, ('back', 'hand'), None, 'all'),
                ('a sweep of another phrase', k_sweep, ('self', True), None, 'all'),
                ('an Extra Life left to you, a part saved to claim', k_heir, ('back', None), 'Ecash claimed', 'all'),
                ("a stranger's token, memo 'Reclaimed: lol'", await k_memo('Reclaimed: lol'), ('back', None), 'Ecash claimed', 'all'),
                ("a stranger's token, memo 'Gift came back from Bob'", await k_memo('Gift came back from Bob'), ('back', None), 'Ecash claimed', 'all'),
                ("a stranger's token, memo 'Extra Life cashed out (was for Bob)'", await k_memo('Extra Life cashed out (was for Bob)'), ('back', None), 'Ecash claimed', 'all'),
                # (a 1.15 record of this one reads exactly like a 1.15 sweep: only the 1.16 record tells them apart)
                ("a stranger's token, memo 'Restored from another phrase'", await k_memo('Restored from another phrase'), ('back', None), 'Ecash claimed', '1.16'),
                # (ecash over Nostr whose claim is finished from its record is "Ecash claimed", as before)
                ("a stranger's ecash over Nostr, memo 'Gift came back from Bob'", k_memo_nostr, ('back', None), 'Ecash claimed', 'all'),
                # (a 1.15 record of your own token handed back over Nostr has op.own like a pasted one: taken back by hand)
                ('your own token handed back over Nostr (re-encoded)', k_nostr_own, ('back', 'auto'), 'Came back to you', '1.16'),
            ]
            imp = None
            async def importer():
                nonlocal imp
                if imp is None: imp = await wallet(b, notif=True); await imp.create(); await imp.wait(500)
                return imp
            for name, start, (mk, mv), label, modes in KINDS_L:
                for mode in ('1.16, reload', '1.15, reload', '1.15, backup imported'):
                    if modes == '1.16' and not mode.startswith('1.16'): continue
                    tag = f'legacy {name} [{mode}]'
                    await rl.ev("Nutcade.closeSheet()"); await rl.home(); await dismiss(rl); a = next(lx)
                    t0 = await rl.ev("Date.now()"); pat, own = await start(a)
                    has_op = await rl.until("JSON.parse(localStorage.getItem('nutcade:ops')||'[]').some(o=>o.kind==='receive')", 15000); await rl.wait(2500); await rl.ev("Nutcade.closeSheet()")
                    if name.startswith('a sweep') and mode.startswith('1.16'): await rl.ev(SELF_JS)
                    if mode.startswith('1.15'): await rl.ev(STRIP_JS)
                    rec = await rl.ev("JSON.parse(localStorage.getItem('nutcade:ops')||'[]').filter(o=>o.kind==='receive').map(o=>({back:o.back||null, self:o.self||null, mk:o.mk||null, own:!!o.own, k:(o.follow||{}).k||null, note:o.note}))")
                    check(f'{tag}: (the claim\'s answer was lost: its record waits, as {"1.15.0" if mode.startswith("1.15") else "1.16"} saved it)', has_op and len(rec) == 1 and (not mode.startswith('1.15') or not any(x['back'] or x['self'] or x['mk'] for x in rec)), rec)
                    w = rl
                    if mode.endswith('imported'):
                        bk = await rl.ev("Promise.resolve(Nutcade.r8.backupData()).then(d=>typeof d==='string'?d:JSON.stringify(d))")
                        bk = J({**json.loads(bk), 'ops': [{k: v for k, v in o.items() if k not in ('back', 'self', 'mk')} for o in json.loads(bk).get('ops', [])],
                                'txs': [{k: v for k, v in t.items() if not (t.get('incoming') and k in ('back', 'mk'))} for t in json.loads(bk).get('txs', [])]})
                        w = await importer(); await w.ev("Nutcade.closeSheet()"); await dismiss(w)
                        b0 = await w.ev(BAL_JS); t0 = await w.ev("Date.now()")
                        res = await w.ev(f"Nutcade.r8.importBackup(JSON.parse({J(bk)})).then(()=>'ok', e=>'ERR '+e.message)")
                        await rl.pg.unroute(SWAP); await rl.pg.unroute(HOLD); await rl.pg.reload(); await rl.wait(800); await settled(rl)   # (the record settled on its own device too)
                    else:
                        b0 = await rl.ev(BAL_JS)
                        await rl.pg.unroute(SWAP); await rl.pg.unroute(HOLD); await rl.pg.reload(); await rl.wait(800); await settled(rl)
                    ok = await wait_line(w, f"t.ts>={t0}&&t.amount==={a}&&new RegExp({J(pat)}).test(t.note||'')", 40000); await w.wait(2500); await settled(w)
                    line = await w.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}&&t.amount==={a}&&new RegExp({J(pat)}).test(t.note||''))||null")
                    seen = await w.ev(SEEN_JS) or []; cs = [c for c in await cards(w) if line and line['id'] in c['ids']]
                    got = line and (line.get(mk) if mk == 'back' else bool(line.get(mk)))
                    check(f'{tag}: settled from its record, its line marked {mk}={mv}', ok and bool(line) and got == mv, (line and {k: line.get(k) for k in ('note', 'amount', 'back', 'self')}))
                    if label is None:
                        check(f'{tag}: not announced as money arriving', bool(line) and line['id'] not in seen and not cs, (line and line.get('note'), [c['text'] for c in cs]))
                    else:
                        # (a live notice names its kind; in a "while you were away" summary it is the kind waiting on the arrivals record)
                        pk = None
                        if cs and cs[0]['type'] == 'away': sr = await summary_rows(w); pk = sr and sorted(sr['rows']); said = (sr or {}).get('text', '')
                        else: said = cs[0]['text'] if cs else ''
                        check(f'{tag}: announced once, as "{label}"', bool(line) and seen.count(line['id']) == 1 and len(cs) == 1 and label in said and (label == 'Came back to you' or 'Came back to you' not in said), (line and line.get('note'), [c['text'] for c in cs], pk))
                    if not mode.endswith('imported'):
                        b1 = await rl.ev(BAL_JS); st = own and await rl.ev(f"(Nutcade.S.txs.find(t=>t.id==={J(own)})||{{}}).status")
                        check(f'{tag}: books exact (balance up by its line{", our sent token reclaimed" if own else ""})', bool(line) and b1 - b0 == line['amount'] and (not own or st == 'reclaimed'), (b0, b1, line and line['amount'], st))
                    await dismiss(w); await dismiss(rl)
            if imp: await imp.pg.context.close()
            # your own token handed back over Nostr by the one you sent it to, the answer heard (finding 2): "Came back to you"
            for strip in (False, True):
                await rl.ev("Nutcade.closeSheet()"); await rl.home(); await dismiss(rl); a = 45 + strip   # (several coins)
                o = await own_tok(a); b0 = await rl.ev(BAL_JS); log0 = len(await rl.ev(LOG_JS)); t0 = await rl.ev("Date.now()"); await rl.ev(TOASTS_JS)
                await nostr_back([{k: v for k, v in x.items() if k != 'dleq'} for x in o['sent']] if strip else o['sent'][::-1])   # (without the DLEQ proofs, or in another order: never the very text we sent)
                ok = await wait_line(rl, f"t.ts>={t0}&&t.amount>0", 25000); await rl.wait(2000)
                line = await rl.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}&&t.amount>0)||null")
                ann = [i for e in (await rl.ev(LOG_JS))[log0:] for i in e['ids']]; cs = [c for c in await cards(rl) if line and line['id'] in c['ids']]
                st = await rl.ev(f"(Nutcade.S.txs.find(t=>t.id==={J(o['id'])})||{{}}).status"); b1 = await rl.ev(BAL_JS); ts = await rl.ev("window.__toasts")
                tag = f'legacy your own token handed back over Nostr ({"without its DLEQ proofs" if strip else "its coins in another order"})'
                check(f'{tag}: claimed, marked came back by itself (back auto)', ok and bool(line) and line.get('back') == 'auto', line)
                check(f'{tag}: announced once, as "Came back to you" (no toast beside it)', bool(line) and ann == [line['id']] and len(cs) == 1 and 'Came back to you' in cs[0]['text'] and not [t for t in ts if 'received' in t], (ann, [c['text'] for c in cs], ts))
                check(f'{tag}: books exact (our sent line reclaimed, balance up by its line)', st == 'reclaimed' and bool(line) and b1 - b0 == line['amount'] and line['amount'] == a, (st, b0, b1, line and line['amount']))
                await dismiss(rl)
            check('legacy: no page errors', not [e for e in rl.errs + (imp.errs if imp else []) if 'PAGEERROR' in e], [e for e in rl.errs if 'PAGEERROR' in e][:5])
            await rl.pg.context.close()
            if await r.ev("Nutcade.vault.on && !Nutcade.vault.open"): await unlock(r); await settled(r); await dismiss(r)   # (the main receiver locked itself meanwhile)

        # ---------- your own token brought back by hand and saved to claim later (rk-160c): pasted while offline, a printed
        # token scanned while its mint can't be reached, pasted at a mint you removed ("Trust mint & claim") while offline
        # x the saved line as 1.16 saves it / as 1.15.0 saved it x claimed automatically when back online / with "Claim now"
        # from its line / its claim's answer lost and settled after a reload. Your own coins brought back by hand are never
        # announced (back 'hand'), as when claimed at once; a stranger's token saved the same way is announced as before;
        # your own token handed back over Nostr (by a contact, from a mint you removed: saved, then "Trust mint & claim")
        # came back by itself ("Came back to you"). Books exact: our sent line reclaimed, balance up by the line, one line. ----------
        if want('held'):
            hw = await wallet(b, notif=True); await hw.create(); await hw.add_mint(FREE); await hw.use(FREE)
            await hw.receive_ln(3000); await hw.wait(1500); await dismiss(hw)
            hv = await wallet(b, notif=True); await hv.create(); await hv.add_mint(FEE); await hv.add_mint(FREE); await hv.use(FREE)   # (sends all it holds at a mint, then removes it; it keeps another mint)
            await hv.receive_ln(400); await hv.wait(1500); await dismiss(hv); hvpk = await npub_hex(hv)
            HB = "(Nutcade.S.proofs[%s]||[]).reduce((t,p)=>t+p.amount,0)" % J(FREE)
            H_SWAP = re.compile(re.escape(FREE) + r'/v1/swap$'); H_HOLD = re.compile(re.escape(FREE) + r'/v1/(restore|checkstate)$'); H_ALL = re.compile(re.escape(FREE) + r'/v1/.*')
            async def h_lose(route):
                try: await route.fetch()
                except Exception: pass
                await route.abort()
            async def h_drop(route): await route.abort()
            async def h_down(route): await route.abort('connectionrefused')
            H_STRIP = """(()=>{const s=o=>{delete o.back; delete o.self; delete o.mk; delete o.came}, ops=JSON.parse(localStorage.getItem('nutcade:ops')||'[]'), txs=JSON.parse(localStorage.getItem('nutcade:txs')||'[]');
              ops.forEach(s); txs.filter(t=>t.incoming).forEach(s); localStorage.setItem('nutcade:ops', JSON.stringify(ops)); localStorage.setItem('nutcade:txs', JSON.stringify(txs));
              Nutcade.S.ops.forEach(s); Nutcade.S.txs.filter(t=>t.incoming).forEach(s); return 1})()"""
            FAKE_OFF = "Object.defineProperty(navigator, 'onLine', {configurable:true, get:()=>false})"   # (the page reads itself offline: no automatic claim)
            REAL_ON = "delete navigator.onLine"
            HELD_JS = "Nutcade.S.txs.filter(t=>t.incoming&&t.status==='pending').map(t=>({id:t.id, offline:!!t.offline, back:t.back||null, mk:t.mk||null, mine:!!t.mine}))"
            async def h_receive(w, tok, note, scan=False, trust=False):
                await w.ev("Nutcade.closeSheet()"); await w.home()
                if scan: await w.ev(f"Nutcade.handleScan({J(tok)})"); await w.wait(400)
                else:
                    await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100)
                    await w.fill('#tokIn', tok)
                if note: await w.fill('#noteIn', note)
                await w.click('[data-act=doReceiveToken]'); await w.wait(700)
                if trust:
                    t = await w.ev("(document.querySelector('[data-act=doReceiveToken]')||{dataset:{}}).dataset.trust||''")
                    check('held: (an unknown mint: asked to trust it first)', t == '1', t)
                    await w.click('[data-act=doReceiveToken]'); await w.wait(700)
                await w.until(f"Nutcade.S.txs.some(t=>t.incoming&&t.status==='pending'&&t.amount>0)", 15000); await w.wait(300); await w.ev("Nutcade.closeSheet()")
            async def h_claim_now(w, hid):
                await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='claimIncoming'; b.dataset.id={J(hid)}; document.body.appendChild(b); b.click(); b.remove()}})()")
            hl = iter(range(61, 999, 2))
            # way: (name, wallet, own?) ; save(w, tok) saves it and leaves the page online-able; claim kinds per way
            async def save_offline(w, tok, own):   # (the context is offline afterwards)
                await w.pg.context.set_offline(True); await w.wait(300); await h_receive(w, tok, 'pasted back' if own else 'from a friend')
            async def save_down(w, tok, own):   # (the mint can't be reached from the start: the page opened while it was down; still down afterwards)
                await w.pg.route(H_ALL, h_down); await w.pg.reload(); await w.wait(800); await settled(w); await dismiss(w)
                await h_receive(w, tok, '', scan=True)
            async def save_trust(w, tok, own):   # (at a mint you removed, while offline)
                await w.pg.context.set_offline(True); await w.wait(300); await h_receive(w, tok, 'pasted back' if own else 'from a friend', trust=True)
            async def back_on(w, way):   # (the network is back; the mint can be reached)
                if way == 'down': await w.pg.unroute(H_ALL)
                else: await w.pg.context.set_offline(False)
                await w.wait(300)
            WAYS = {'offline': ('pasted while offline', save_offline), 'down': ('a printed token scanned while its mint is down', save_down),
                    'trust': ('pasted at a mint you removed, "Trust mint & claim" while offline', save_trust)}
            H_CELLS = [   # (way, claim, own, label: None = not announced)
                *[(wy, cl, 'own', None) for wy in ('offline', 'down') for cl in ('auto', 'now', 'lost')],
                *[('trust', cl, 'own', None) for cl in ('now', 'lost')],
                *[('offline', cl, 'stranger', 'Ecash claimed') for cl in ('auto', 'lost')],
                ('down', 'auto', 'stranger', 'Ecash claimed'),
                *[('nostr', cl, 'nostr', 'Came back to you') for cl in ('now', 'lost')],
            ]
            # (a 1.15 record of a claim of your own token, its answer lost, has op.own as one pasted by hand has: taken
            # back by hand, not announced; the accepted limit of the legacy cells)
            for way, how, who, label in H_CELLS:
                for saved_by in ('1.16', '1.15'):
                    if way == 'nostr' and how == 'lost' and saved_by == '1.15': continue
                    w = hv if way in ('trust', 'nostr') else hw
                    await w.ev("Nutcade.closeSheet()"); await w.home(); await dismiss(w)
                    a = next(hl); own = None
                    if way in ('trust', 'nostr'):
                        await w.until(f"{HB}>0", 30000); a = await w.ev(HB)   # (all it holds there)
                    if who == 'stranger': tok = await token_from(p, a, FREE)
                    else: o = await w.ev(f"Nutcade.r8.sendEcash({a}, 'lunch', null, {J(FREE)}).then(t=>({{id:t.id, token:t.token, sent:t.sent}}))"); tok = o['token']; own = o['id']
                    if way in ('trust', 'nostr'):   # (then the mint is removed: nothing left there)
                        await w.home(); await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='confirmRemove'; b.dataset.url={J(FREE)}; document.body.appendChild(b); b.click(); b.remove()}})()"); await w.wait(300)
                    b0 = await w.ev(HB); t0 = await w.ev("Date.now()")
                    wname = 'over Nostr from a contact, saved (a mint you removed)' if way == 'nostr' else WAYS[way][0]
                    tag = f"held {'your own token' if who != 'stranger' else 'a stranger' + chr(39) + 's token'} {wname} [{saved_by}, {dict(auto='claimed automatically back online', now='Claim now from its line', lost='its answer lost, settled after a reload')[how]}]"
                    if way == 'nostr':   # (handed back by Bob, a contact, re-encoded; the mint is unknown now, so it is saved)
                        bob = await p.ev("(()=>{if(!window.__bobSk) window.__bobSk=crypto.getRandomValues(new Uint8Array(32)); return CashuLib.nostrPub(window.__bobSk)})()")
                        await w.ev(f"(()=>{{if(!Nutcade.S.contacts.some(c=>c.pubkey==={J(bob)})) Nutcade.S.contacts.push({{id:'bob1', name:'Bob', pubkey:{J(bob)}}})}})()")
                        res = await p.ev(f"""(async()=>{{const ev=CashuLib.nip17.wrapEvent(window.__bobSk, {{publicKey:{J(hvpk)}}}, JSON.stringify({{mint:{J(FREE)}, unit:'sat', proofs:{J([{k: v for k, v in x.items() if k != 'dleq'} for x in o['sent']])}, memo:'here you go'}}));
                          return await new Promise(res=>{{const ws=new WebSocket({J(NOSTR)}); ws.onopen=()=>ws.send(JSON.stringify(['EVENT',ev])); ws.onmessage=m=>{{const d=JSON.parse(m.data); if(d[0]==='OK'){{ws.close(); res(d[2])}}}}; setTimeout(()=>res('timeout'),8000)}})}})()""")
                        await w.until("Nutcade.S.txs.some(t=>t.incoming&&t.status==='pending'&&t.amount>0)", 25000); await w.wait(500)
                    else:
                        await WAYS[way][1](w, tok, who != 'stranger')
                    held = await w.ev(HELD_JS)
                    check(f'{tag}: (saved to claim later: one line)', len(held) == 1, held)
                    hid = held[0]['id'] if held else None
                    if saved_by == '1.15': await w.ev(H_STRIP)
                    if how == 'lost': await w.pg.route(H_SWAP, h_lose); await w.pg.route(H_HOLD, h_drop)
                    if how == 'now':   # (before the automatic claim: the page still reads itself offline)
                        await w.ev(FAKE_OFF); await back_on(w, way); await h_claim_now(w, hid)
                    elif way == 'trust' or way == 'nostr':
                        await back_on(w, way); await h_claim_now(w, hid)
                    else:
                        await back_on(w, way); await w.ev("window.dispatchEvent(new Event('online'))")
                    if how == 'lost':
                        has_op = await w.until("JSON.parse(localStorage.getItem('nutcade:ops')||'[]').some(o=>o.kind==='receive')", 20000); await w.wait(2500); await w.ev("Nutcade.closeSheet()")
                        if saved_by == '1.15': await w.ev(H_STRIP)
                        rec = await w.ev("JSON.parse(localStorage.getItem('nutcade:ops')||'[]').filter(o=>o.kind==='receive').map(o=>({back:o.back||null, mk:o.mk||null, own:!!o.own, k:(o.follow||{}).k||null}))")
                        check(f'{tag}: (the claim\'s answer was lost: its record waits)', has_op and len(rec) == 1, rec)
                        await w.pg.unroute(H_SWAP); await w.pg.unroute(H_HOLD); await w.pg.reload(); await w.wait(800); await settled(w)
                    ok = await wait_line(w, f"t.ts>={t0}&&t.amount==={a}", 40000); await w.wait(2500); await w.ev("Nutcade.closeSheet()"); await w.wait(300)
                    if how == 'now': await w.ev(REAL_ON)
                    line = await w.ev(f"Nutcade.S.txs.find(t=>t.type==='in'&&t.status==='done'&&t.ts>={t0}&&t.amount==={a})||null")
                    seen = await w.ev(SEEN_JS) or []; cs = [c for c in await cards(w) if line and line['id'] in c['ids']]
                    mv = 'hand' if who == 'own' else 'auto' if who == 'nostr' else None
                    check(f'{tag}: claimed, its line marked back={mv}', ok and bool(line) and line.get('back') == mv, line and {k: line.get(k) for k in ('note', 'amount', 'back', 'self')})
                    if label is None:
                        check(f'{tag}: not announced as money arriving', bool(line) and line['id'] not in seen and not cs, (line and line.get('note'), [c['text'] for c in cs]))
                    else:
                        pk = None
                        if cs and cs[0]['type'] == 'away': sr = await summary_rows(w); pk = sr and sorted(sr['rows']); said = (sr or {}).get('text', '')
                        else: said = cs[0]['text'] if cs else ''
                        check(f'{tag}: announced once, as "{label}"', bool(line) and seen.count(line['id']) == 1 and len(cs) == 1 and label in said and (label == 'Came back to you' or 'Came back to you' not in said), (line and line.get('note'), [c['text'] for c in cs], pk))
                    b1 = await w.ev(HB); st = own and await w.ev(f"(Nutcade.S.txs.find(t=>t.id==={J(own)})||{{}}).status")
                    n_in = await w.ev(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.ts>={t0}&&t.amount==={a}&&t.status!=='failed').length")
                    left = await w.ev(f"Nutcade.S.txs.filter(t=>t.incoming&&t.status==='pending').length")
                    check(f'{tag}: books exact (balance up by its line{", our sent token reclaimed" if own else ""}, one line, nothing left saved)', bool(line) and b1 - b0 == line['amount'] == a and (not own or st == 'reclaimed') and n_in == 1 and left == 0, (b0, b1, line and line['amount'], st, n_in, left))
                    await dismiss(w)
            check('held: no page errors', not [e for e in hw.errs + hv.errs if 'PAGEERROR' in e], [e for e in hw.errs + hv.errs if 'PAGEERROR' in e][:5])
            await hw.pg.context.close(); await hv.pg.context.close()

        # ---------- big amounts (up to 9,999,999 SAT) and long labels: the amount is never cut, in every language ----------
        if want('amounts'):
            await r.use(FREE); await dismiss(r)
            # (a long mint name, for the label line: only how it is shown here)
            await r.ev(f"(()=>{{const m=Nutcade.S.mints.find(m=>m.url==={J(FREE)}); m.name='Mint B of the Very Long Name Cooperative'}})()")
            for lang in ['en', 'es', 'pt', 'de', 'fr']:
                await set_lang(r, lang); await dismiss(r)
                await ln_invoice(r, 9999999, FREE)
                await r.until("!!document.querySelector('#arrStack .arr-card')", 20000); await r.ev("Nutcade.closeSheet()"); await r.wait(300)
                txt = (await cards(r) or [{'text': ''}])[0]['text']
                check(f'{lang}, 9,999,999 SAT: (a notice)', ('+' + fmtn(9999999, lang) + ' SAT') in txt, txt)
                await looks(r, f'{lang}, a 9,999,999 SAT notice with a long label', details=False)
                if lang in ('en', 'fr'): await r.pg.set_viewport_size({'width': 320, 'height': 640}); await shot(r, f'notice-9999999-{lang}-320'); await r.pg.set_viewport_size({'width': 390, 'height': 844})
                await dismiss(r)
                # the longest kind, "Wallet Connect invoice", with the long mint name
                await nwc_invoice(nwc_uri, 9999997)
                await r.until("!!document.querySelector('#arrStack .arr-card')", 20000); await r.wait(300)
                txt = (await cards(r) or [{'text': ''}])[0]['text']
                check(f'{lang}, 9,999,997 SAT Wallet Connect invoice: (a notice)', fmtn(9999997, lang) in txt, txt)
                await looks(r, f'{lang}, a 9,999,997 SAT Wallet Connect notice with a long mint name', details=False)
                if lang in ('de', 'pt'): await r.pg.set_viewport_size({'width': 320, 'height': 640}); await shot(r, f'notice-nwc-{lang}-320'); await r.pg.set_viewport_size({'width': 390, 'height': 844})
                await dismiss(r)
                # a summary of the same size: paid while the page is away, then opened again
                blk = Block(); await blk.attach(r.pg, FREE); blk.on = True
                await ln_invoice(r, 9999998, FREE); await r.ev("Nutcade.closeSheet()"); await r.wait(1500)
                pg0 = r.pg; await pg0.close(); r = await wallet(b, ctx=r_ctx)
                if await r.ev("!!document.querySelector('[data-pinpad]')"): await unlock(r)
                await r.ev(f"(()=>{{const m=Nutcade.S.mints.find(m=>m.url==={J(FREE)}); m.name='Mint B of the Very Long Name Cooperative'}})()")
                await settled(r); await r.wait(400)
                txt = ([c for c in await cards(r) if c['type'] == 'away'] or [{'text': ''}])[0]['text']
                check(f'{lang}, 9,999,998 SAT: (a summary)', fmtn(9999998, lang) in txt, txt)
                if lang in ('en', 'pt'): await r.pg.set_viewport_size({'width': 320, 'height': 640}); await shot(r, f'summary-9999998-{lang}-320'); await r.pg.set_viewport_size({'width': 390, 'height': 844})
                await looks(r, f'{lang}, a 9,999,998 SAT summary', details=False)
                await dismiss(r)
            await set_lang(r, 'en')

        # ---------- 320 and 1440 px ----------
        if want('widths'):
            for vw, vh in [(320, 640), (1440, 900)]:
                await r.pg.set_viewport_size({'width': vw, 'height': vh}); await r.wait(300); await dismiss(r)
                tok = await token_from(p, 2500, FREE); await claim(r, tok)
                await r.until("!document.querySelector('#layer .spinner')", 15000); await r.wait(1500); await r.ev("Nutcade.closeSheet()"); await r.wait(300)
                ov = await no_overflow(r)
                check(f'{vw} px: the notice fits the screen', bool(await cards(r)) and not ov, ov)
                await shot(r, f'notice-{vw}')
                await dismiss(r); pg0 = r.pg; await pg0.close(); await dm(p, rpk, 2500, FREE)
                r = await wallet(b, ctx=r_ctx, vw=vw, vh=vh); await r.pg.set_viewport_size({'width': vw, 'height': vh})
                if await r.ev("!!document.querySelector('[data-pinpad]')"): await unlock(r)
                await settled(r); await r.wait(400)
                ov = await no_overflow(r); await shot(r, f'summary-{vw}')
                check(f'{vw} px: the summary fits the screen', bool(await summary_rows(r)) and not ov, ov)
                await dismiss(r)

        # ---------- a phone held sideways; another tab; a game (or the till) filling the screen ----------
        if want('widths') or want('game'):
            REACH = """(sel=>{const e=document.querySelector(sel); if(!e) return 'missing'; e.scrollIntoView({block:'center'}); const q=e.getBoundingClientRect();
              if(q.top<0||q.bottom>innerHeight) return 'off screen'; const h=document.elementFromPoint(q.left+q.width/2,q.top+q.height/2); return h&&(h===e||e.contains(h))?'ok':'covered'})"""
            await r.pg.set_viewport_size({'width': 844, 'height': 390}); await dismiss(r)
            tok = await token_from(p, 1500, FREE); await claim(r, tok)
            await r.until("!document.querySelector('#layer .spinner')", 15000); await r.wait(1500); await r.ev("Nutcade.closeSheet()")
            for vw, vh in ((844, 390), (568, 320)):
                await r.pg.set_viewport_size({'width': vw, 'height': vh}); await r.wait(200)
                g = await r.ev(REACH + "('[data-act=send]')"); h = await r.ev("(document.querySelector('#arrStack .arr-card')||{getBoundingClientRect:()=>({height:-1})}).getBoundingClientRect().height")
                check(f'sideways {vw}x{vh}: a notice is compact and leaves the screen usable', 0 < h < vh / 3 and g == 'ok', (g, h))
                if vw == 568: await shot(r, 'notice-568x320')
            await r.wait(1200); await settings(r)
            check('another tab: going there closes a notice you have seen', not await cards(r), await cards(r))
            await r.pg.set_viewport_size({'width': 844, 'height': 390})
            await r.click('[data-act=tab][data-tab=arcade]'); await r.wait(300)
            await dm(p, rpk, 1600, FREE); await r.until("!!document.querySelector('#arrStack .arr-card')", 20000); await r.wait(300)
            shown = bool(await cards(r))
            await r.ev("document.querySelector('[data-game=swarm]').click()"); await r.wait(800)
            g = await r.ev(REACH.replace("e.scrollIntoView({block:'center'}); ", '') + "('[data-g=exit]')")
            check('a game: a notice on screen waits under it (the exit stays reachable)', shown and g == 'ok', (shown, g))
            await r.ev("document.querySelector('[data-g=exit]')?.click()"); await r.wait(500)
            check('a game: back from it, the notice is there again', await r.ev("!!document.querySelector('#arrStack .arr-card') && getComputedStyle(document.querySelector('#arrStack')).display!=='none'"))
            await dismiss(r); await r.home(); await r.pg.set_viewport_size({'width': 390, 'height': 844})

        # ---------- the till (cashier mode): its own sale is on its PAID! screen; any other arrival waits for after ----------
        if want('widths') or want('game') or want('till'):
            await dismiss(r); await r.home(); await r.use(FREE); await r.click('[data-act=cashier]'); await r.wait(300)
            log0 = len(await r.ev(LOG_JS))
            await dm(p, rpk, 1717, FREE)
            await r.until("Nutcade.S.txs.some(t=>t.amount===1717&&t.status==='done')", 20000); await r.wait(2500)
            other = await r.ev("Nutcade.S.txs.find(t=>t.amount===1717&&t.status==='done').id")
            check('till open: a payment that is not the sale is not marked seen and not shown over the till', other in await pend(r, None) and not [e for e in (await r.ev(LOG_JS))[log0:] if other in e['ids']])
            for k in '123': await r.click(f'.cashier [data-ck="{k}"]')
            await r.click('.cashier [data-ck=charge]')
            paid = await r.until("/PAID!/.test((document.querySelector('.cashier')||{}).innerText||'')", 25000); await r.wait(1500)
            sale = await r.ev("(Nutcade.S.txs.find(t=>t.cashier&&t.amount===123)||{}).id")
            check('till: (the sale went through)', paid and bool(sale))
            await r.ev("document.querySelector('#cashExit').dispatchEvent(new PointerEvent('pointerdown'))"); await r.wait(1300)
            check('till: (closed)', await r.ev("!document.querySelector('.cashier')"))
            await r.until("!!document.querySelector('#arrStack .arr-card')", 8000); await r.wait(500)
            ann = [i for e in (await r.ev(LOG_JS))[log0:] for i in e['ids']]
            check('till closed: the other payment gets its notice now, the sale none (the till showed it)', ann == [other] and sale not in await pend(r, None), (ann, other, sale))
            await dismiss(r)

        # ---------- a fresh wallet on a phone held sideways: its first deposit covers no screen's buttons (as r8 checks) ----------
        if want('widths') or want('game'):
            IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
            SEE = """(sel=>{const e=document.querySelector(sel); if(!e) return 'missing'; e.scrollIntoView({block:'center'}); const q=e.getBoundingClientRect();
              if(q.width<1||q.top<0||q.bottom>innerHeight||q.left<0||q.right>innerWidth) return 'off screen'; const h=document.elementFromPoint(q.left+q.width/2,q.top+q.height/2);
              if(h&&(h===e||e.contains(h))) return 'ok'; const c=h&&h.closest('.arr-card'); return 'covered by '+(c?'a notice ('+c.dataset.type+', '+Math.round(c.getBoundingClientRect().height)+' px)':(h?(h.id||h.className||h.tagName):'nothing'))+' at y '+Math.round(q.top)})"""
            for vw, vh in ((844, 390), (568, 320)):
                ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=True, has_touch=True, user_agent=IPHONE)
                await ctx.add_init_script(INIT % J(J({'sound': False, 'music': False, 'crt': False, 'lang': 'en', 'relays': [NOSTR], 'npcHost': MOCK})))
                u = await wallet(b, ctx=ctx); await u.create()
                check(f'sideways {vw}x{vh}: a wallet just made has no "while you were away" to wait for', await u.ev("!!window.NutArrivals && NutArrivals.awayDone()"))
                await u.add_mint(FREE); await u.use(FREE); await u.receive_ln(2000)
                await u.until("!!document.querySelector('#arrStack .arr-card')", 5000)
                ts = [c['type'] for c in await cards(u)]
                check(f'sideways {vw}x{vh}: a deposit right after making a wallet gets its notice, not a "while you were away"', ts == ['live'], ts)
                res = {}
                for tabn, sel in (('wallet', '[data-act=send]'), ('history', '#app .tx'), ('mints', '#app [data-act=pickMint]'), ('settings', '[data-act=limOpen]')):
                    await u.ev("Nutcade.closeSheet()"); await u.click(f'[data-act=tab][data-tab={tabn}]'); await u.wait(250)
                    res[tabn] = await u.ev(SEE + f"({J(sel)})"); res[tabn + ' tabs'] = await u.ev(SEE + "('[data-act=tab][data-tab=wallet]')")
                check(f'sideways {vw}x{vh}, a fresh wallet\'s first deposit: every screen\'s buttons stay usable', all(v == 'ok' for v in res.values()), res)
                await ctx.close()

        errs = [e for e in (r.errs + p.errs) if 'PAGEERROR' in e]
        for e in r.errs + p.errs: print('  page said:', e[:300])
        check('no page errors', not errs, errs[:5])
        await b.close()
    fails = [n for n, ok, _ in results if not ok]
    print(f'SUMMARY {len(results) - len(fails)}/{len(results)} passed')


if __name__ == '__main__':
    asyncio.run(main())
