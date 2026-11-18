"""Notices when money arrives (no server, no push service, nothing sent anywhere): an in-app notice for each arrival,
optional system notifications shown by the page or its service worker, the coin sound, and a "while you were away"
summary on opening or unlocking.

The grid: each kind of arrival (Lightning deposit, a token claimed, ecash over Nostr, a payment request paid, the
npub.cash Lightning address, a Wallet Connect make_invoice paid) x NUTCADE open / in a background tab / closed and
reopened / locked; plus two tabs (one notice), a reload mid-arrival, a restore from the 12 words (no flood for old
history), the duress PIN's wallet (only the open wallet's own arrivals, the other never shown), sound on and off,
system notifications off / on / permission denied, five languages and 320 / 1440 px wide screens.

Exact: a summary's count and total per kind equal the history lines that arrived in that window, and no arrival is
announced twice (across reloads, tabs and restores).

Uses two local test mints (ARR_FEE, default 3338, with input fees; ARR_FREE, default 3339, without) and mock_nostr.py
(ARR_NOSTR, default ws://127.0.0.1:3350/relay; it also stands in for npub.cash). ARR_ONLY=a,b runs some sections
(open, bg, closed, tabs, reload, notif, sound, locked, restore, duress, langs, widths, game, till). ARR_SHOTS: where screenshots go
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
  return {covered:out, card:[Math.round(q.top),Math.round(q.bottom)], inview:q.top>=0&&q.bottom<=innerHeight&&q.left>=0&&q.right<=innerWidth, buttons:btn.every(Boolean)&&btn.length>=2}})()"""
SIZES = [(320, 640), (375, 667), (430, 932), (1440, 900), (844, 390), (568, 320)]


async def looks(w, label, details=True):
    """the notice on screen at every size: covers nothing that matters, fully in view, its buttons reachable; at
    568x320 its Details sheet's buttons too"""
    bad = {}
    for vw, vh in SIZES:
        await w.pg.set_viewport_size({'width': vw, 'height': vh}); await w.wait(150)
        c = await w.ev(COVER_JS)
        if not c['card'] or c['covered'] or not c['inview'] or not c['buttons']: bad[f'{vw}x{vh}'] = c
    check(f'{label}: at 320/375/430/1440 px and 844x390/568x320 it covers no balance, lock, mint, Receive or Send, and its buttons are on screen', not bad, bad)
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
            check('duress PIN set up: the real wallet shows no system notification at all', ok and await d.ev("__sys.length") == 0 and not await d.ev(SYSN_JS), (await d.ev("__sys"), await d.ev(SYSN_JS)))
            real_ids = await d.ev("Nutcade.S.txs.map(t=>t.id)")
            await d.pg.reload(); await d.wait(1500)
            ns = await d.ev(SYSN_JS); body = await d.ev("document.body.innerText")
            check('duress set: locked, the real wallet\'s notifications are gone (no amount, and no "money arrived" that the duress wallet couldn\'t explain)', not ns and not re.search(r'Money arrived', body), (ns, body[:200]))
            await d.ev("__hide(false)")
            await unlock(d, DPIN); await settled(d)
            check('duress wallet: no summary of the real wallet\'s arrival', not await cards(d), await cards(d))
            check('duress wallet: its record of arrivals knows nothing of the real wallet', await has(d) and not await d.ev(f"(ids=>{{const j=JSON.stringify(NutArrivals.ledger()); return ids.some(i=>j.includes(i))}})({J(real_ids)})"))
            a = 888; tok = await token_from(p, a, FREE)
            async def slow(route): await asyncio.sleep(1.5); await route.continue_()
            await d.pg.route(re.compile(re.escape(FREE) + r'/v1/swap$'), slow); await d.ev("__sys.length=0")
            await claim(d, tok); await d.wait(200); await d.ev("__hide(true)")
            await d.until(f"Nutcade.S.txs.some(t=>t.amount===888&&t.status==='done')", 15000); await d.wait(1500); await d.pg.unroute_all()
            check('duress wallet: its arrival in a background tab shows no system notification either', await d.ev("__sys.length") == 0 and not await d.ev(SYSN_JS), await d.ev("__sys"))
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
                check(f'{lang}: the notifications setting says what a PIN and a duress PIN change, in the language', bool(helptxt) and (('With a PIN' in helptxt and 'duress' in helptxt) if lang == 'en' else ('With a PIN' not in helptxt and 'PIN' in helptxt)), helptxt)
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
