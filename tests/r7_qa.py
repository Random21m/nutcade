"""Round 7 (1.12): LNURL-withdraw vouchers (LUD-03), blocked mints, Nostr Wallet Connect (NIP-47, wallet side) and
zaps (NIP-57). Uses the local mints and mock_nostr.py, which also plays the LNURL services (reached as
https://lnurl.test, forwarded here), Nostr profiles and an NWC app. With SHOTS=dir it saves screenshots of every
new screen at 375 px in English and German."""
import asyncio, json, os, re, urllib.request, urllib.error
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, A, B, URL, invoice, outside_net

MOCK = 'http://127.0.0.1:3350'
FM = 'http://127.0.0.1:3340'
SHOTS = os.environ.get('SHOTS', '')
LEDGER = """(u=>{let s=0;for(const t of Nutcade.S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return [s,(Nutcade.S.proofs[u]||[]).reduce((a,p)=>a+p.amount,0)]})"""
ALLOW = re.compile(r'^(NUTCADE|SAT|BTC|LN|NOSTR|[A-Z]{3}|Wallet Connect|Zap)$')
OVER_JS = """(()=>{const W=document.documentElement.clientWidth,out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(!e.getClientRects().length||e.closest('.sr'))continue;const r=e.getBoundingClientRect();if(r.right>W+1||r.left<-1)out.push((e.className||e.tagName)+':'+Math.round(r.left)+'..'+Math.round(r.right))}return out.slice(0,4)})()"""


def change_ok(amount, tx):
    """A settled Lightning payment on the test mints got back its whole fee reserve, max(2, 1%), minus their 1 SAT
    Lightning fee. A lost change shows 0; a change credited twice breaks history == balance (checked after each)."""
    reserve = max(2, -(-amount // 100))
    return bool(tx) and tx.get('status') == 'done' and tx.get('change', 0) >= reserve - 1 and tx.get('fee', 0) >= 1


def mock(path, data=None):
    req = urllib.request.Request(MOCK + path, data=(json.dumps(data).encode() if data is not None else None), method='POST' if data is not None else 'GET', headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


async def forward(route):
    """https://lnurl.test/... is served by mock_nostr.py"""
    u = route.request.url.replace('https://lnurl.test', MOCK, 1)
    def get():
        try:
            r = urllib.request.urlopen(u, timeout=30); return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    st, body = await asyncio.to_thread(get)
    try: await route.fulfill(status=st, body=body, headers={'content-type': 'application/json', 'access-control-allow-origin': '*'})
    except Exception: pass


async def wallet(b, vw=375, vh=667, lang='en', mobile=True):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile, accept_downloads=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    await ctx.route('https://lnurl.test/**', forward)
    await ctx.route('https://down.test/**', lambda r: r.abort())
    pg = await ctx.new_page(); w = W(pg, 'r7')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'lnurl.test' not in m.text and 'down.test' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


def error_strings():
    """Every error message the app can show, from its source: literal ones, and templated ones whose only value is an
    amount (a sample amount in its place); plus the round-3 notes and screens."""
    import glob
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
    out = set()
    for f in sorted(glob.glob(os.path.join(src, 'app*.js'))):
        s = open(f, encoding='utf-8').read()
        for m in re.finditer(r"""(?:new Error|\w+Err)\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`((?:[^`\\]|\\.)*)`)""", s):
            t = m.group(1) or m.group(2) or m.group(3)
            if t is None: continue
            if m.group(3) is not None:
                t = re.sub(r'\$\{money\([^}]*\)\}', '1,234 SAT', t)
                if '${' in t: continue
            t = t.replace("\\'", "'").replace('\\"', '"')
            if re.match(r'^[A-Z][a-z]', t) and not t.endswith(': ') and not re.search(r"""nwcErr\(\s*'[A-Z_]+',\s*$""", s[max(0, m.start() - 40):m.start() + 7]):
                out.add(t)
    out |= {"Mint B didn't answer in time. Try again in a moment.", "The mint didn't answer in time. Try again in a moment.", 'Restore ecash from another phrase', 'NUTCADE is open in another tab.', "The mint didn't answer in time.", "The mint didn't answer. Try again in a moment.", 'This invoice has expired. Nothing was received.',
            'This invoice is already paid. NUTCADE is collecting the ecash from the mint, and it shows here as soon as it is in.', 'COLLECTING',
            'Mint fee for moving ecash under your phrase', 'Mint fee for an interrupted step', 'Mint fee for keeping Extra Life going', 'Ecash already spent elsewhere',
            'Some of this ecash was already spent. NUTCADE removed 1,234 SAT of spent ecash from your balance (see your notes). Try again with what is left.'}
    return sorted(out)


EXTRA_AT_MINT = """(async()=>{const x=Nutcade.S.extra; if(!x) return null; const w=new CashuLib.Wallet(x.mint,{unit:'sat'}); await w.loadMint();
  const st=await w.checkProofsStates(x.proofs); const s=JSON.parse(x.proofs[0].secret); const lt=+((s[1].tags||[]).find(t=>t[0]==='locktime')||[])[1];
  return {amount:x.amount, sum:x.proofs.reduce((a,p)=>a+p.amount,0), unspent:st.every(t=>t.state==='UNSPENT'), kind:s[0], pub:s[1].data, lt, until:x.until, unlocked:!!x.unlocked, mint:x.mint}})()"""
SECRETS_JS = """(()=>{const S=Nutcade.S; return [...Object.values(S.proofs).flat().map(p=>p.secret), ...((S.extra&&S.extra.proofs)||[]).map(p=>p.secret),
  ...S.pending.flatMap(p=>p.proofs.map(x=>x.secret)), ...S.ops.flatMap(o=>(o.outs||[]).map(x=>x.s))].filter(Boolean)})()"""
LEAK_JS = "(l)=>Object.keys(localStorage).filter(k=>{const v=localStorage.getItem(k)||''; return l.some(s=>v.includes(s))})"


def quote_inv(n, mint):
    """an invoice from a test mint, with its quote id (to ask the mint later whether it was paid)"""
    q = json.loads(urllib.request.urlopen(urllib.request.Request(mint + '/v1/mint/quote/bolt11', data=json.dumps({'amount': n, 'unit': 'sat'}).encode(), headers={'Content-Type': 'application/json'})).read())
    return q['request'], q['quote']


def quote_state(mint, quote):
    return json.loads(urllib.request.urlopen(mint + '/v1/mint/quote/bolt11/' + quote, timeout=10).read()).get('state')


async def words_ok(w, mints):
    """a restore from the wallet's own 12 words finds nothing the wallet doesn't already show"""
    bal0, n0 = await w.bal(), await w.ev("Nutcade.S.txs.length")
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=seedRestore]'); await w.wait(250)
    await w.fill('#phraseIn', await w.ev("Nutcade.S.seed.mnemonic"))
    await w.ev(f"document.querySelectorAll('[data-rmint]').forEach(i=>{{i.checked={json.dumps(list(mints))}.includes(i.dataset.rmint)}})")
    await w.click('[data-act=doRestorePhrase]'); await w.until("/SCAN COMPLETE|CONTINUE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 120000); t = await w.sheet_text()
    await w.ev("Nutcade.closeSheet()")
    return 'SCAN COMPLETE' in t and await w.bal() == bal0 and await w.ev("Nutcade.S.txs.length") == n0, (t[:100], await w.bal() - bal0, await w.ev("Nutcade.S.txs.length") - n0)


async def unpaid(route):
    """the mint's real answer about a quote, but still UNPAID: holds a deposit unpaid however the test mint behaves"""
    r = await route.fetch(); j = await r.json(); j['state'] = 'UNPAID'
    await route.fulfill(response=r, body=json.dumps(j))


async def nwc(w, uri, method, params=None, **kw):
    body = dict({'uri': uri, 'method': method, 'params': params or {}}, **kw)
    return await asyncio.to_thread(mock, '/test/nwc', body)


async def books(w, step, broken, mints=(A, B)):
    for u in mints:
        l, p = await w.ev(LEDGER + f"({json.dumps(u)})")
        if l != p: broken.append((step, u[-4:], l, p))


async def withdraw(w, lnurl, amount=None, mint=None):
    """scan a voucher, optionally pick the amount and mint, tap Withdraw; returns the sheet text right after"""
    await w.ev(f"Nutcade.handleScan({json.dumps(lnurl)})")
    await w.until("!!document.querySelector('[data-act=lnurlwGo]') || !!document.querySelector('#layer .notice.red')", 8000)
    if mint: await w.ev(f"document.querySelector('#wdMint').value={json.dumps(mint)}")
    if amount is not None: await w.fill('#amtIn', str(amount))
    if await w.ev("!!document.querySelector('[data-act=lnurlwGo]')"):
        await w.click('[data-act=lnurlwGo]')
        await w.until("!document.querySelector('[data-act=lnurlwGo]') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
    await w.wait(300)
    return await w.sheet_text()


async def zap_to(w, npub, amount, comment='', pay=True):
    await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
    await w.fill('#destIn', npub); await w.click('[data-act=doMeltQuote]')
    await w.until("!!document.querySelector('[data-act=zapQuote]') || !!document.querySelector('#layer .notice.red')", 12000)
    pre = await w.sheet_text()
    if not await w.ev("!!document.querySelector('[data-act=zapQuote]')"): return pre, None
    await w.fill('#amtIn', str(amount))
    if comment: await w.fill('#zapComment', comment)
    await w.click('[data-act=zapQuote]')
    await w.until("!!document.querySelector('#payBtn') || !!(document.querySelector('#sheetErr')||{}).innerText", 12000)
    q = await w.sheet_text()
    w.zap_pre = pre
    if not pay or not await w.ev("!!document.querySelector('#payBtn')"): return q, None
    await w.click('#payBtn'); await w.until("!document.querySelector('#payBtn')", 15000); await w.wait(400)
    return q, await w.sheet_text()


async def make_nwc(w, name, per='none', sats=None):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
    await w.click('[data-act=nwcNew]'); await w.wait(200)
    await w.fill('#nwcName', name)
    if per != 'none':
        await w.pg.select_option('#nwcPer', per); await w.wait(100); await w.fill('#amtIn', str(sats))
    await w.click('[data-act=nwcCreate]'); await w.until("!!document.querySelector('#layer .qr, #layer canvas')", 6000); await w.wait(300)
    uri = await w.ev("[...document.querySelectorAll('#layer .code')].map(e=>e.innerText).find(t=>t.startsWith('nostr+walletconnect://'))")
    for _ in range(40):   # the wallet's listener is up
        if await w.ev("Nutcade.r7.nwcLive()"): break
        await w.wait(150)
    await w.wait(400)
    return uri


async def set_pin(w, pin='135791'):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=pinSet]'); await w.wait(200)
    for _ in range(2):
        for k in pin: await w.click(f'[data-pinpad] [data-k="{k}"]')
        await w.click('[data-pinpad] [data-k=ok]'); await w.wait(600)
    await w.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await w.wait(500); await w.ev("Nutcade.closeSheet()")


async def unlock(w, pin='135791'):
    for k in pin: await w.click(f'[data-pinpad] [data-k="{k}"]')
    await w.click('[data-pinpad] [data-k=ok]'); await w.until("Nutcade.vault.open", 20000); await w.wait(800)


async def tour(b, pa, pb, pc, pd):
    # =================== screens, layouts, focus and translations ===================
    miss_all = {}
    for lang, vw, vh, mobile in (('en', 375, 667, True), ('de', 375, 667, True), ('fr', 320, 640, True), ('es', 430, 932, True), ('pt', 1440, 900, False)):
        h = await wallet(b, vw, vh, lang, mobile)
        await h.pg.add_init_script("(()=>{const s=window.__i18nMiss;const a=s.add.bind(s);s.add=v=>{try{const k='qa:miss7';const c=JSON.parse(localStorage.getItem(k)||'[]');if(!c.includes(v)){c.push(v);localStorage.setItem(k,JSON.stringify(c))}}catch(e){}return a(v)}})()")
        await h.pg.reload(); await h.wait(700)
        await h.create(); await h.add_mint(B); await h.add_mint(A); await h.use(B); await h.receive_ln(3000); await h.use(A); await h.receive_ln(5000)
        shot_dir = SHOTS if SHOTS and lang in ('en', 'de') else ''
        over, n, notgold = [], [0], []
        async def snap(name):
            await h.ev("(e=>e&&e.remove())(document.getElementById('fxLayer'))")   # no coin shower over the screenshot
            o = await h.ev(OVER_JS)
            if o: over.append((name, o))
            ng = await h.ev("[...document.querySelectorAll('#layer .btn.solid')].filter(b=>!b.classList.contains('gold')&&!b.classList.contains('red')&&b.id!=='payBtn'&&b.id!=='mppPay').map(b=>b.innerText)")
            if ng and name not in ('block_ln_refused',): notgold.append((name, ng))   # (that one is the existing Receive sheet)
            if shot_dir:
                n[0] += 1; await h.pg.screenshot(path=os.path.join(shot_dir, f'{lang}_{n[0]:02d}_{name}.png'))
        # (round 2, B) the pay, multinut and move sheets, in every language: their text is checked for English below
        await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#destIn', invoice(6500, FM)); await h.click('[data-act=doMeltQuote]'); await h.until("!!document.querySelector('#mppBtn')", 15000); await snap('pay_not_enough')
        await h.click('#mppBtn'); await h.until("!!document.querySelector('#mppPay') || !!(document.querySelector('#layer .notice.red'))", 20000); await snap('multinut_confirm')
        await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=mints]'); await h.wait(200); await h.click('#app [data-act=moveOpen]'); await h.wait(250); await snap('move_sheet')
        await h.ev(f"document.querySelector('#mvFrom').value={json.dumps(A)}; document.querySelector('#mvTo').value={json.dumps(B)}"); await h.fill('#amtIn', '500')
        await h.click('[data-act=moveQuote]'); await h.until("!!document.querySelector('#mvGo')", 15000); await snap('move_confirm')
        await h.click('#mvGo'); await h.until("/MOVED|ON ITS WAY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await snap('move_done')
        await h.ev("Nutcade.closeSheet()")
        # texts on those sheets that a normal tour doesn't reach (failures, the no-move variant): asked of the translator directly
        TRS = ["The payment didn't go through, so the parts that were sent came back to your wallet.", 'The payment is in flight. NUTCADE will settle each part when the mints confirm. Check the parts in your notes.',
               'Your 3,000 SAT at Mint B stays usable: you can still send it.', 'Mint B holds 300 SAT, not enough on its own.', 'Payment is in flight. NUTCADE will settle it when the mint confirms. Check the transaction in your notes.',
               "The move didn't go through, so the sats stayed where they were.", "Paid. Its change hasn't come back yet; NUTCADE keeps trying."]
        await h.ev(f"{json.dumps(TRS)}.forEach(t=>Nutcade.tr(t))")
        vid = f'tour-{lang}'
        mock('/test/lnurlw', {'id': vid, 'min': 100, 'max': 2500, 'desc': 'Meetup voucher'})
        await h.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}')"); await h.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000); await snap('voucher')
        await h.fill('#amtIn', '9999'); await h.click('[data-act=lnurlwGo]'); await h.wait(300); await snap('voucher_range_error')
        await h.fill('#amtIn', '1000'); await h.click('[data-act=lnurlwGo]'); await h.until("/1UP/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 15000); await snap('voucher_done')
        await h.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}')"); await h.wait(1200); await snap('voucher_used')
        mock('/test/lnurlw', {'id': vid + 'e', 'min': 1, 'max': 50, 'mode': 'error'})
        await h.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)
        await h.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}e')"); await h.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000); await h.click('[data-act=lnurlwGo]'); await h.wait(1500); await snap('voucher_service_error')
        await h.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))
        await h.ev("window.__nutcadeTest={lnurlMs:800}"); mock('/test/lnurlw', {'id': vid + 's', 'min': 1, 'max': 50, 'mode': 'slow'})
        await h.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)
        await h.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}s')"); await h.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000); await h.click('[data-act=lnurlwGo]'); await h.wait(1600); await snap('voucher_waiting')
        await h.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))
        await h.ev("window.__nutcadeTest={}; Nutcade.closeSheet()")
        # blocked mint
        await h.click('[data-act=tab][data-tab=mints]'); await h.wait(200)
        await h.ev(f"document.querySelector('[data-act=blockMint][data-url=\"{B}\"]').click()"); await h.wait(250); await snap('block_sheet')
        await h.click('[data-act=blockMintGo]'); await h.wait(250); await snap('block_done')
        await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=mints]'); await h.wait(200); await snap('mints_blocked')
        req = await h.ev(f"new CashuLib.PaymentRequest([{{type:'post',target:'{MOCK}/test/post'}}],'r1',50,'sat',[{json.dumps(B)}],'Lunch').toEncodedRequest()")
        await h.ev(f"Nutcade.handleScan({json.dumps(req)})"); await h.wait(400); await snap('block_request_refused')
        await h.ev("Nutcade.closeSheet()"); await h.use(B); await h.home(); await h.click('[data-act=receive]'); await h.wait(150)
        if await h.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await h.click('[data-act=recvMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#amtIn', '100'); await h.click('[data-act=doLnInvoice]'); await h.wait(500); await snap('block_ln_refused')
        await h.ev("Nutcade.closeSheet()"); await h.use(A)
        await h.ev(f"Nutcade.toast('Refused 120 SAT from Mint B: you blocked that mint. It waits in your notes if you unblock it.','gold')"); await h.wait(300)
        await h.ev(f"Nutcade.toast('Mint B unblocked','lime')"); await h.wait(200)
        # zaps
        await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#destIn', pa['npub']); await h.click('[data-act=doMeltQuote]'); await h.until("!!document.querySelector('[data-act=zapQuote]')", 10000); await snap('zap_sheet')
        await h.fill('#amtIn', '21'); await h.fill('#zapComment', 'gm'); await h.click('[data-act=zapQuote]'); await h.until("!!document.querySelector('#payBtn')", 10000); await snap('zap_quote')
        await h.click('#payBtn'); await h.until("!document.querySelector('#payBtn')", 15000); await h.wait(400); await snap('zap_done')
        await h.ev(f"Nutcade.closeSheet()"); await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#destIn', pb['npub']); await h.click('[data-act=doMeltQuote]'); await h.until("!!document.querySelector('[data-act=zapQuote]')", 10000); await snap('zap_unsupported')
        await h.ev(f"Nutcade.closeSheet()"); await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#destIn', pc['npub']); await h.click('[data-act=doMeltQuote]'); await h.wait(2500); await snap('zap_no_address')
        await h.ev(f"Nutcade.closeSheet()"); await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
        await h.fill('#destIn', pd['npub']); await h.click('[data-act=doMeltQuote]'); await h.until("!!document.querySelector('[data-act=zapQuote]')", 10000); await h.fill('#amtIn', '30'); await h.click('[data-act=zapQuote]'); await h.wait(1500); await snap('zap_wrong_amount')
        # Wallet Connect
        await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=settings]'); await h.wait(150)
        if not mobile:   # (fix 10) a sheet that fills in after a lookup puts the focus in its amount field
            mock('/test/lnurlw', {'id': vid + 'f', 'min': 1, 'max': 50})
            await h.ev("Nutcade.closeSheet()"); await h.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}f')"); await h.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000); await h.wait(200)
            f_v = await h.ev("document.activeElement.id")
            await h.ev("Nutcade.closeSheet()"); await h.home(); await h.click('[data-act=send]'); await h.wait(150); await h.click('[data-act=sendMethod][data-m=ln]'); await h.wait(100)
            await h.fill('#destIn', pa['npub']); await h.click('[data-act=doMeltQuote]'); await h.until("!!document.querySelector('[data-act=zapQuote]')", 10000); await h.wait(200)
            f_z = await h.ev("document.activeElement.id"); await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=settings]'); await h.wait(150)
            check(f'(fix 10) focus {lang} {vw}: the voucher and zap sheets open with focus in the amount field', f_v == 'amtIn' and f_z == 'amtIn', (f_v, f_z))
        if not mobile:   # keyboard: focus lands in the new sheet and comes back to the button that opened it
            await h.pg.locator('#app [data-act=nwcNew]').focus(); await h.pg.keyboard.press('Enter'); await h.wait(300)
            f1 = await h.ev("document.activeElement.id")
            inside = []
            for _ in range(10): await h.pg.keyboard.press('Tab'); inside.append(await h.ev("!!document.activeElement.closest('#layer .sheet')"))
            await h.pg.keyboard.press('Escape'); await h.wait(200)
            check(f'round 7 focus {lang} {vw}: Connect an app opens with focus in the name field, Tab stays inside, Esc returns focus', f1 == 'nwcName' and all(inside) and await h.ev("document.activeElement.dataset.act") == 'nwcNew', (f1, inside))
        await h.click('[data-act=nwcNew]'); await h.wait(200); await snap('nwc_new')
        await h.pg.select_option('#nwcPer', 'week'); await h.wait(100); await snap('nwc_new_budget')
        await h.fill('#nwcName', 'Amethyst'); await h.fill('#amtIn', '5000'); await h.click('[data-act=nwcCreate]'); await h.wait(800); await snap('nwc_uri_once')
        u = await h.ev("[...document.querySelectorAll('#layer .code')].map(e=>e.innerText).find(t=>t.startsWith('nostr+walletconnect://'))")
        await h.ev("Nutcade.closeSheet()"); await h.wait(1500)
        await nwc(h, u, 'pay_invoice', {'invoice': invoice(120, B)}); await h.wait(500)
        await nwc(h, u, 'pay_invoice', {'invoice': invoice(99999, B)})
        await h.click('[data-act=tab][data-tab=settings]'); await h.wait(150); await h.ev("document.querySelector('#set-nwc').scrollIntoView()"); await snap('nwc_list')
        await h.click('[data-act=nwcEdit]'); await h.wait(200); await snap('nwc_edit')
        await h.click('#layer [data-act=nwcRevokeAsk]'); await h.wait(200); await snap('nwc_revoke')
        await h.click('[data-act=nwcRevoke]'); await h.wait(300)
        await h.click('[data-act=tab][data-tab=history]'); await h.wait(250); await snap('history_new_rows')
        await h.ev("[...document.querySelectorAll('#txList .tx')].find(r=>/NWC/.test(r.innerText)).click()"); await h.wait(250); await snap('history_nwc_detail')
        await h.ev("Nutcade.closeSheet()")
        if lang != 'en':   # (C) screen-reader labels: none left in English where the language has another word (history with tags, settings, a game with joystick and D-pad)
            ARIA = """(()=>{const D=window.NUTCADE_I18N[document.documentElement.lang.slice(0,2)].t;return [...document.querySelectorAll('[aria-label]')].map(e=>e.getAttribute('aria-label')).filter(l=>D[l]!==undefined&&D[l]!==l)})()"""
            left = []
            await h.ev("Nutcade.S.txs[0].note='Lunch #food'; Nutcade.render()"); await h.click('[data-act=tab][data-tab=history]'); await h.wait(250); left += await h.ev(ARIA)
            await h.click('[data-act=tab][data-tab=settings]'); await h.wait(250); left += await h.ev(ARIA)
            await h.click('[data-act=tab][data-tab=arcade]'); await h.wait(250); await h.ev("document.querySelector('[data-game=swarm]').click()"); await h.wait(500); left += await h.ev(ARIA)
            await h.ev("document.querySelector('[data-g=pad]').click()"); await h.wait(250); left += await h.ev(ARIA)
            await h.ev("document.querySelector('[data-g=pad]').click()"); await h.wait(150); await h.ev("document.querySelector('[data-g=exit]').click()"); await h.wait(200)
            labels = await h.ev("['Filter','Tags','Sections','Joystick','Pause'].map(k=>[k, window.NUTCADE_I18N[document.documentElement.lang.slice(0,2)].t[k]])")
            check(f'(C) aria {lang}: no screen-reader label left in English where {lang} has its own word (Filter, Tags, Sections, Joystick, Pause and the rest)', not left and all(v for k, v in labels), (left, labels))
        # solid (main) buttons in the new sheets are gold; Revoke stays red
        miss = [m for m in await h.ev("JSON.parse(localStorage.getItem('qa:miss7')||'[]')") if not ALLOW.match(m.strip())]
        if lang != 'en': miss_all[lang] = miss
        check(f'round 7 layout {lang} {vw}: nothing on the new screens pokes out sideways', not over, over[:3])
        check(f'round 7 buttons {lang}: the main button on every new sheet is gold (Revoke stays red)', not notgold, notgold[:3])
        check(f'round 7 no page errors {lang}', not h.errs, h.errs[:4])
        await h.pg.context.close()
    for lang, miss in miss_all.items():
        check(f'round 7 i18n {lang}: no English left on the voucher, blocked-mint, zap and Wallet Connect screens, errors and toasts', not miss, miss[:12])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        tour_only = os.environ.get('R7_ONLY') == 'tour'
        w = await wallet(b)
        if tour_only:   # (for retaking the screenshots only)
            pa, pb, pc = [mock('/test/profile', {'name': n, 'lud16': n + '@lnurl.test'} if n != 'carol' else {'name': n}) for n in ('alice', 'bob', 'carol')]
            for n, z, x in (('alice', True, 0), ('bob', False, 0)): mock('/test/lnurlp', {'name': n, 'zap': z, 'extra': x})
            pd = mock('/test/profile', {'name': 'dave', 'lud06': mock('/test/lnurlp', {'name': 'dave', 'zap': True, 'extra': 1})['lnurl']})
        await w.create(); await w.add_mint(B); await w.add_mint(A); await w.add_mint(FM); await w.use(A)
        await w.receive_ln(20000); await w.use(B); await w.receive_ln(3000); await w.use(A)
        broken = []
        await books(w, 'start', broken)
        if tour_only: return await tour(b, pa, pb, pc, pd)

        # =================== LNURL-withdraw (LUD-03) ===================
        v = mock('/test/lnurlw', {'id': 'v1', 'min': 100, 'max': 5000, 'desc': 'Conference voucher'})
        await w.ev(f"Nutcade.handleScan({json.dumps(v['lnurl'])})"); await w.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000)
        t = await w.sheet_text()
        check('voucher: a scanned LNURL that resolves to a withdrawRequest offers to load it, with its description and limits', 'Conference voucher' in t and '100 SAT to 5,000 SAT' in t, t[:300])
        check('voucher: the amount defaults to the maximum, into the active mint', await w.ev("[document.querySelector('#amtIn').value, document.querySelector('#wdMint').value]") == ['5000', A])
        q0, n0, b0 = await w.ev("Nutcade.S.quotes.length"), await w.ev("Nutcade.S.txs.length"), await w.bal(A)
        bad = {}
        for amt in ('50', '6000', '1.5', '-5', '1e3'):
            await w.fill('#amtIn', amt); await w.click('[data-act=lnurlwGo]'); await w.wait(300); bad[amt] = await w.err()
        check('voucher: amounts outside the limits are refused with the range', 'gives 100 SAT to 5,000 SAT' in bad['50'] and 'gives 100 SAT to 5,000 SAT' in bad['6000'], bad)
        check('voucher: typed amounts go through the strict parser (no decimals, signs or exponents)', 'whole numbers' in bad['1.5'] and "can't be read" in bad['-5'] and "can't be read" in bad['1e3'], bad)
        check('voucher: a refused amount creates no invoice and no history line', await w.ev("Nutcade.S.quotes.length") == q0 and await w.ev("Nutcade.S.txs.length") == n0)
        await w.fill('#amtIn', '1200'); await w.ev("(b=>{b.click();b.click();b.click()})(document.querySelector('[data-act=lnurlwGo]'))")
        ok = await w.until(f"(Nutcade.S.proofs[{json.dumps(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= {b0 + 1200}", 20000); await w.wait(1500)
        st = mock('/test/state')['vouchers']['v1']
        tx = await w.ev("Nutcade.S.txs.find(t=>t.lnurlw)")
        check('voucher: withdrawing 1,200 SAT loads exactly 1,200 SAT, and a triple tap asks the voucher once', ok and await w.bal(A) == b0 + 1200 and st['calls'] == 1 and [x['msat'] for x in st['prs']] == [1200000], (await w.bal(A) - b0, st['calls'], st['prs']))
        check('voucher: history shows Lightning in with the voucher description', tx and tx['type'] == 'in' and tx['method'] == 'ln' and tx['note'] == 'Conference voucher' and tx['status'] == 'done' and tx['amount'] == 1200, tx)
        done = await w.sheet_text()
        check('voucher: the done screen says 1UP', '1UP' in done, done[:120])
        await books(w, 'voucher', broken)
        # the same voucher again: refused here, without asking the service
        t = await withdraw(w, v['lnurl'])
        check('voucher: a voucher already used in this wallet is refused before anything is made', 'already used in this wallet' in t and mock('/test/state')['vouchers']['v1']['calls'] == 1, t[:200])
        # LUD-17 lnurlw:// form, fixed amount, into another mint
        v2 = mock('/test/lnurlw', {'id': 'v2', 'min': 777, 'max': 777, 'desc': ''})
        bB = await w.bal(B)
        t = await withdraw(w, v2['lud17'], mint=B)
        await w.until(f"(Nutcade.S.proofs[{json.dumps(B)}]||[]).reduce((t,p)=>t+p.amount,0) >= {bB + 777}", 20000); await w.wait(500)
        check('voucher: the lnurlw:// form (LUD-17) works, into a chosen mint, for a fixed amount', await w.bal(B) == bB + 777, await w.bal(B) - bB)
        await books(w, 'voucher B', broken)
        # the service says no
        # (fix 3) a refusal never drops the invoice: it stays watched, and if the service pays it after all, it is minted
        for vid, mode, want in (('v3', 'error', 'The voucher service turned this down.'), ('v4', 'spent', 'The voucher service says this voucher was already used.')):
            vv = mock('/test/lnurlw', {'id': vid, 'min': 10, 'max': 300, 'desc': 'Gift card', 'mode': mode}); ba = await w.bal(A)
            await w.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)   # unpaid while the screen is read
            t = await withdraw(w, vv['lnurl'], 300)
            ft = await w.ev("Nutcade.S.txs[0]"); kept = await w.ev("Nutcade.S.quotes.some(q=>q.txId===Nutcade.S.txs[0].id)")
            check(f'voucher: a service ERROR ({mode}) is reported with its reason as not confirmed yet, the invoice is kept and watched, nothing spent', want in t and 'Not confirmed yet' in t and 'Nothing was spent.' in t and ft['status'] == 'pending' and kept and await w.bal(A) == ba, (t[:300], ft['status'], kept))
            await w.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))   # the (test) mint now reports the invoice paid: as if the service paid after all
            ok = await w.until(f"(Nutcade.S.proofs[{json.dumps(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= {ba + 300}", 30000); await w.wait(500)
            check(f'voucher: after a refusal ({mode}), the service paying later is still minted, exactly once', ok and await w.bal(A) == ba + 300 and (await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(ft['id'])})") or {}).get('status') == 'done', await w.bal(A) - ba)
            await w.ev("Nutcade.closeSheet()"); await books(w, 'voucher ' + mode, broken)
        # refused, then never paid: it expires at the mint, and only then is it reported as over
        mock('/test/lnurlw', {'id': 'v3x', 'min': 1, 'max': 120, 'desc': 'Refused', 'mode': 'error'}); ba = await w.bal(A)
        await w.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)
        await withdraw(w, 'lnurlw://lnurl.test/lnurlw/v3x', 120)
        await w.ev("(q=>{q.expiry=Math.floor(Date.now()/1000)+2})(Nutcade.S.quotes.find(q=>q.amount===120))")
        await w.until("/expired/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 15000); t = await w.sheet_text()
        await w.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))
        et = await w.ev("Nutcade.S.txs.find(t=>t.note==='Refused')")
        check('voucher: a refused voucher that never pays expires at the mint and says so, with nothing spent', 'never paid, and the invoice has expired' in t and et['status'] == 'expired' and await w.bal(A) == ba, (t[:200], et['status']))
        await w.ev("Nutcade.closeSheet()"); await books(w, 'voucher refused, expired', broken)
        # nothing left on the voucher; a dead link; an unreachable service
        mock('/test/lnurlw', {'id': 'v5', 'min': 1, 'max': 100, 'mode': 'empty'})
        t = await withdraw(w, 'lnurlw://lnurl.test/lnurlw/v5')
        check('voucher: an emptied voucher says it has nothing left', 'nothing left to withdraw' in t, t[:200])
        mock('/test/lnurlw', {'id': 'v6', 'min': 1, 'max': 100, 'mode': 'gone'})
        t = await withdraw(w, 'lnurlw://lnurl.test/lnurlw/v6')
        check('voucher: a link the service no longer knows is refused with its reason', 'turned this link down' in t and 'not found' in t, t[:200])
        t = await withdraw(w, 'lnurlw://down.test/lnurlw/x')
        check("voucher: a service that can't be reached says so", "Couldn't reach down.test" in t, t[:200])
        # a slow service: the wallet stops waiting, keeps watching the invoice, and the sats still arrive
        await w.ev("window.__nutcadeTest={lnurlMs:1500}")
        mock('/test/lnurlw', {'id': 'v7', 'min': 1, 'max': 400, 'desc': 'Slow one', 'mode': 'slow'}); ba = await w.bal(A)
        await w.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)   # held unpaid until the notice is read
        t = await withdraw(w, 'lnurlw://lnurl.test/lnurlw/v7', 400)
        await w.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))
        check("voucher: a service that doesn't answer in time is reported, and the invoice stays watched", "didn't answer in time" in t and 'If it pays' in t and await w.ev("Nutcade.S.quotes.some(q=>q.amount===400)"), t[:250])
        ok = await w.until(f"(Nutcade.S.proofs[{json.dumps(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= {ba + 400}", 30000)
        check('voucher: when the slow service does pay, exactly the invoice amount arrives', ok and await w.bal(A) == ba + 400, await w.bal(A) - ba)
        await w.ev("window.__nutcadeTest={}"); await w.ev("Nutcade.closeSheet()")
        await books(w, 'voucher slow', broken)
        # the invoice expires before the service pays
        await w.pg.route(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'), unpaid)
        mock('/test/lnurlw', {'id': 'v8', 'min': 1, 'max': 250, 'desc': 'Expiring'}); ba = await w.bal(A)
        await withdraw(w, 'lnurlw://lnurl.test/lnurlw/v8', 250)
        await w.ev("(q=>{q.expiry=Math.floor(Date.now()/1000)+2})(Nutcade.S.quotes.find(q=>q.amount===250))")   # the mint's invoice runs out in 2 s
        await w.until("/expired/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 15000); t = await w.sheet_text()
        await w.pg.unroute(re.compile(r'http://127\.0\.0\.1:3338/v1/mint/quote/bolt11/.+'))
        et = await w.ev("Nutcade.S.txs.find(t=>t.note==='Expiring')")
        check("voucher: an invoice that expires unpaid says so, costs nothing and is marked expired", "didn't pay before the invoice expired" in t and 'Nothing was received' in t and et and et['status'] == 'expired' and await w.bal(A) == ba, (t[:200], et and et['status']))
        await w.ev("Nutcade.closeSheet()"); await books(w, 'voucher expired', broken)

        # =================== blocked mints ===================
        await w.use(B); tokB, e = await w.send_ecash(150); await w.use(A)
        await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200)
        await w.ev(f"document.querySelector('[data-act=blockMint][data-url=\"{B}\"]').click()"); await w.wait(250)
        t = await w.sheet_text()
        check('block: the mint screen offers Block this mint, warns that its sats stay usable and offers to move them', 'BLOCK THIS MINT' in t.upper() and 'stays usable' in t and await w.ev("!!document.querySelector('#layer [data-act=moveOpen]')"), t[:300])
        await w.click('[data-act=blockMintGo]'); await w.wait(300)
        check('block: after blocking, the sheet says so and offers Move sats out', 'is blocked' in await w.sheet_text() and await w.ev("!!document.querySelector('#layer [data-act=moveOpen][data-from]')"))
        await w.click('#layer [data-act=moveOpen]'); await w.wait(300)
        mv = await w.ev("[document.querySelector('#mvFrom').value, [...document.querySelector('#mvTo').options].map(o=>o.value)]")
        check('block: the move-sats flow opens from the blocked mint, and never into it', mv[0] == B and B not in mv[1] and A in mv[1], mv)
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200)
        card = await w.ev(f"[...document.querySelectorAll('.panel')].find(p=>p.innerText.includes('127.0.0.1:3339')).innerText")
        check('block: the mint card shows BLOCKED, the reason and an Unblock button', 'BLOCKED' in card and 'is blocked' in card and 'UNBLOCK' in card.upper(), card[:300])
        await w.pg.reload(); await w.wait(1200)
        check('block: the blocked list survives a reload', await w.ev(f"Nutcade.r7.isBlocked({json.dumps(B)})"))
        # a token from the blocked mint
        ba = await w.bal(B)
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100)
        await w.fill('#tokIn', tokB); await w.wait(200)
        peek = await w.ev("document.querySelector('#tokPeek').innerText")
        await w.click('[data-act=doReceiveToken]'); await w.wait(800); er = await w.err()
        check('block: a token from a blocked mint is refused with a message naming it and an Unblock button', 'Mint B is blocked, so NUTCADE refused this ecash.' in er and await w.ev("!!document.querySelector('#sheetErr [data-act=unblockMint]')") and await w.bal(B) == ba, er)
        check('block: the token preview already says the mint is blocked', 'is blocked' in peek, peek[:150])
        # Lightning into a blocked mint
        await w.ev("Nutcade.closeSheet()"); await w.use(B); await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
        if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
        nq = await w.ev("Nutcade.S.quotes.length"); await w.fill('#amtIn', '100'); await w.click('[data-act=doLnInvoice]'); await w.wait(600); er = await w.err()
        check("block: a Lightning deposit into a blocked mint is refused and says why", "won't receive into it" in er and await w.ev("Nutcade.S.quotes.length") == nq, er)
        # its existing coins still spend
        tok2, e2 = await w.send_ecash(100)
        check('block: ecash already at the blocked mint can still be sent', tok2 and not e2, e2)
        await books(w, 'blocked send', broken); await w.use(A)
        # a payment request that only takes the blocked mint
        req = await w.ev(f"new CashuLib.PaymentRequest([{{type:'post',target:'{MOCK}/test/post'}}],'r1',50,'sat',[{json.dumps(B)}],'Lunch').toEncodedRequest()")
        await w.ev(f"Nutcade.handleScan({json.dumps(req)})"); await w.wait(400); t = await w.sheet_text()
        check('block: a payment request that only takes a blocked mint is refused, naming it, with Unblock', 'only takes ecash from Mint B, which you blocked' in t and await w.ev("!!document.querySelector('#layer [data-act=unblockMint]')"), t[:200])
        # ecash over Nostr from the blocked mint: refused, said so, kept aside
        fr = await wallet(b); await fr.create(); await fr.add_mint(B); await fr.receive_ln(500)
        addr = await w.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")
        await fr.ev("Nutcade.closeSheet()"); await fr.click('[data-act=tab][data-tab=settings]'); await fr.wait(100); await fr.click('[data-act=contactsOpen]'); await fr.wait(150)
        await fr.click('[data-act=contactEdit]'); await fr.wait(150); await fr.fill('#cName', 'Main'); await fr.fill('#cNostr', addr); await fr.click('[data-act=contactSave]'); await fr.wait(300)
        await fr.ev("document.querySelector('[data-act=payContact]').click()"); await fr.wait(200); await fr.fill('#amtIn', '120'); await fr.click('[data-act=contactEcash]'); await fr.wait(2500)
        await w.ev("Nutcade.closeSheet()"); await w.home()
        ok = await w.until("Nutcade.S.txs.some(t=>t.refused)", 15000); toast = await w.toast()
        rt = await w.ev("Nutcade.S.txs.find(t=>t.refused)")
        check('block: ecash over Nostr from a blocked mint is refused with a toast naming the mint, kept aside unclaimed', ok and 'Refused 120 SAT from Mint B' in toast and rt['status'] == 'pending' and await w.bal(B) == ba - 100, (toast, rt and rt['status']))
        await books(w, 'blocked nostr', broken)
        # the backup file carries the list, and an import restores it
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        async with w.pg.expect_download() as dl: await w.click('[data-act=backupDownload]')
        bk = json.loads(open(await (await dl.value).path()).read())
        check('block: the backup file includes the blocked list', any(x['url'] == B for x in bk.get('blocked', [])), bk.get('blocked'))
        nw = await wallet(b); await nw.create(); await nw.click('[data-act=tab][data-tab=settings]'); await nw.wait(100); await nw.click('[data-act=restore]'); await nw.wait(150)
        await nw.pg.fill('#restoreIn', json.dumps({'app': 'nutcade', 'v': 2, 'blocked': bk['blocked'], 'mints': [], 'proofs': {}, 'txs': []})); await nw.click('[data-act=doRestore]'); await nw.wait(300)
        await nw.pg.reload(); await nw.wait(900)
        check('block: importing the backup restores the blocked list (and it survives a reload)', await nw.ev(f"Nutcade.r7.isBlocked({json.dumps(B)})"))
        await nw.pg.context.close()
        # (fix 7) two mints, the one with sats blocked: Move sats out opens the move sheet (it used to only toast)
        t2 = await wallet(b); await t2.create(); await t2.add_mint(A); await t2.add_mint(B); await t2.use(B); await t2.receive_ln(600)
        await t2.click('[data-act=tab][data-tab=mints]'); await t2.wait(200); await t2.ev(f"document.querySelector('[data-act=blockMint][data-url=\"{B}\"]').click()"); await t2.wait(250)
        await t2.click('[data-act=blockMintGo]'); await t2.wait(250); await t2.click('#layer [data-act=moveOpen]'); await t2.wait(300)
        mv2 = await t2.ev("document.querySelector('#mvFrom') ? [document.querySelector('#mvFrom').value, [...document.querySelector('#mvTo').options].map(o=>o.value)] : null")
        check('block: with two mints and the one holding sats blocked, Move sats out opens the move sheet, from it to the other', mv2 == [B, [A]], mv2)
        await t2.pg.context.close()
        # unblock from the refused note; then the ecash is claimed
        await w.click('[data-act=tab][data-tab=history]'); await w.wait(200)
        await w.ev("[...document.querySelectorAll('#txList .tx')].find(r=>/BLOCKED/.test(r.innerText)).click()"); await w.wait(300)
        t = await w.sheet_text()
        check('block: the refused ecash in the notes explains why and offers Unblock', 'is blocked' in t and await w.ev("!!document.querySelector('#layer [data-act=unblockMint]')"), t[:200])
        await w.click('#layer [data-act=unblockMint]'); await w.wait(300)
        check('block: Unblock takes the mint off the list', not await w.ev(f"Nutcade.r7.isBlocked({json.dumps(B)})"))
        await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        await w.ev("[...document.querySelectorAll('#txList .tx')].find(r=>/PENDING/.test(r.innerText)&&/120/.test(r.innerText)).click()"); await w.wait(300)
        await w.click('#layer [data-act=claimIncoming]'); await w.wait(2000)
        check('block: after unblocking, the waiting ecash is claimed', await w.bal(B) == ba - 100 + 120, await w.bal(B) - ba)
        await w.ev("Nutcade.closeSheet()"); await books(w, 'unblocked claim', broken)
        await w.home(); await w.receive_token(tokB); check('block: after unblocking, tokens from the mint are accepted again', await w.bal(B) >= ba - 100 + 120 + 150 - 2)
        await books(w, 'unblocked token', broken)
        tokH, _ = await fr.send_ecash(50, 'For the heirloom test')   # (round 2, item 3) a plain token, held as an Extra Life copy below
        # (fix 7) a single mint with sats, blocked: no Move button; it says why and offers Add a mint / Send from it
        await fr.ev("Nutcade.closeSheet()"); await fr.click('[data-act=tab][data-tab=mints]'); await fr.wait(200)
        await fr.ev(f"document.querySelector('[data-act=blockMint][data-url=\"{B}\"]').click()"); await fr.wait(250); t1 = await fr.sheet_text()
        m1 = await fr.ev("!!document.querySelector('#layer [data-act=moveOpen]')")
        await fr.click('[data-act=blockMintGo]'); await fr.wait(250); t1b = await fr.sheet_text(); m1b = await fr.ev("!!document.querySelector('#layer [data-act=moveOpen]')")
        check("block: with no other mint to move to, no Move button is offered; it says so and offers Add a mint and Send", not m1 and not m1b and "can't be moved yet" in t1 and "can't be moved yet" in t1b and await fr.ev("!!document.querySelector('#layer [data-act=pickMint]') && !!document.querySelector('#layer [data-act=sendFrom]')"), (t1[:300], m1, m1b))
        await fr.click('#layer [data-act=sendFrom]'); await fr.wait(300)
        check('block: Send from the blocked mint opens Send with it as the source', await fr.ev("!!document.querySelector('[data-act=doSendEcash]') && Nutcade.S.active===" + json.dumps(B)))
        await fr.pg.context.close()

        # =================== zaps (NIP-57) ===================
        alice = mock('/test/lnurlp', {'name': 'alice', 'zap': True}); mock('/test/lnurlp', {'name': 'bob', 'zap': False}); mock('/test/lnurlp', {'name': 'dave', 'zap': True, 'extra': 1}); mock('/test/lnurlp', {'name': 'erin', 'zap': True, 'min': 1000, 'max': 2000})
        pa = mock('/test/profile', {'name': 'alice', 'display_name': 'Alice', 'lud16': 'alice@lnurl.test'})
        pb = mock('/test/profile', {'name': 'bob', 'lud16': 'bob@lnurl.test'})
        pc = mock('/test/profile', {'name': 'carol'})
        pd = mock('/test/profile', {'name': 'dave', 'lud06': mock('/test/lnurlp', {'name': 'dave', 'zap': True, 'extra': 1})['lnurl']})
        pe = mock('/test/profile', {'name': 'erin', 'lud16': 'erin@lnurl.test'})
        mynpub = await w.ev("CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        ba = await w.bal(A); nz = len(mock('/test/state')['zaps'])
        q, done = await zap_to(w, pa['npub'], 210, 'gm from the arcade')
        z = mock('/test/state')['zaps'][nz:]
        ev = z[0]['event'] if z else {}
        tags = {t[0]: t[1:] for t in (ev or {}).get('tags', [])}
        check('zap: the profile is fetched, the endpoint allows Nostr, and the quote shows the fee before paying', 'Fee reserve' in q and 'alice@lnurl.test' in q, q[:200])
        tot = re.search(r'Total, at most\n([\d,]+) SAT', q); mf = re.search(r'Mint fee, at most\n([\d,]+) SAT', q)
        check('(fix 4) pay screen on the fee mint: it shows the mint fee and the total at most, and the payment cost no more than that total', bool(tot and mf) and int(mf.group(1)) >= 1 and ba - await w.bal(A) <= int(tot.group(1).replace(',', '')), (q[:300], ba - await w.bal(A)))
        check('(fix 9) zap: the sheet said the zap is signed with this wallet\'s Nostr key and can be linked to you', 'signed with this wallet' in w.zap_pre and 'link it to you' in w.zap_pre, w.zap_pre[:400])
        zp = await w.ev("Nutcade.S.txs[0].preimage"); zh = await w.ev("Nutcade.r7.decodeBolt11(Nutcade.S.txs[0].invoice).paymentHash")
        check('(fix 5) zap: the payment preimage is stored, and it matches the invoice', bool(zp) and __import__('hashlib').sha256(bytes.fromhex(zp)).hexdigest() == zh, (zp, zh))
        # anonymous zap: a fresh one-time key signs it, tagged anon, and the receiver's endpoint still accepts it
        nz = len(mock('/test/state')['zaps'])
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#destIn', pa['npub']); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('[data-act=zapQuote]')", 12000)
        await w.fill('#amtIn', '33'); await w.pg.check('#zapAnon'); await w.click('[data-act=zapQuote]'); await w.until("!!document.querySelector('#payBtn')", 12000)
        await w.click('#payBtn'); await w.until("!document.querySelector('#payBtn')", 15000); await w.wait(400)
        za = mock('/test/state')['zaps'][nz:]; ze = za[0]['event'] if za else {}
        check('(fix 9) anonymous zap: signed by a one-time key (not the wallet\'s), tagged anon, accepted by the endpoint and paid', len(za) == 1 and za[0]['valid'] and ze['pubkey'] != mynpub and ['anon'] in ze['tags'] and await w.ev("Nutcade.S.txs[0].status") == 'done' and await w.ev("Nutcade.S.txs[0].zap.anon"), za)
        await w.ev("Nutcade.closeSheet()"); await books(w, 'anonymous zap', broken)
        check("zap: the kind-9734 zap request is signed with the wallet's Nostr key and carries amount, p, lnurl, relays and the comment",
              len(z) == 1 and z[0]['valid'] and ev['pubkey'] == mynpub and tags.get('amount') == ['210000'] and tags.get('p') == [pa['pubkey']] and tags.get('lnurl', [''])[0].startswith('lnurl1') and tags.get('relays') and ev['content'] == 'gm from the arcade', z)
        zt = await w.ev("Nutcade.S.txs[0]")
        check('zap: paid, and history shows "Zap to Alice"', 'SENT' in (done or '') and zt['note'] == 'Zap to Alice' and zt['zap'] and zt['status'] == 'done' and await w.bal(A) < ba - 209, (done and done[:80], zt['note']))
        await books(w, 'zap', broken)
        # no zap support: offered a plain payment and told so
        q, done = await zap_to(w, pb['npub'], 99, 'thanks')
        check("zap: an endpoint without zap support offers a plain Lightning payment and says so", "doesn't support zaps" in w.zap_pre and 'PAY AS A PLAIN LIGHTNING PAYMENT' in w.zap_pre.upper(), w.zap_pre[:200])
        bt = await w.ev("Nutcade.S.txs[0]")
        check('zap: the plain payment goes through, recorded as To Bob without zap', bt['note'] == 'To bob' and not bt.get('zap') and bt['status'] == 'done' and mock('/test/state')['zaps'][-1]['event'] is None, bt['note'])
        await books(w, 'plain pay', broken)
        q, done = await zap_to(w, pc['npub'], 50)
        check('zap: a profile without a Lightning address says it can\'t be zapped', 'no Lightning address' in q, q[:200])
        ba = await w.bal(A); n0 = await w.ev("Nutcade.S.txs.length")
        q, done = await zap_to(w, pd['npub'], 300)
        check('zap: an invoice for the wrong amount (lud06 endpoint, +1 SAT) is refused before paying, and nothing is spent', 'asked for 301 SAT instead of 300 SAT' in q and await w.bal(A) == ba and await w.ev("Nutcade.S.txs.length") == n0, q[:200])
        q, done = await zap_to(w, pe['npub'], 50)
        check("zap: an amount outside the endpoint's limits is refused with the limits", 'takes 1,000 SAT to 2,000 SAT' in q, q[:200])
        await w.ev("Nutcade.closeSheet()")
        # zap a contact; double tap on Pay pays once
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=contactsOpen]'); await w.wait(150)
        await w.click('[data-act=contactEdit]'); await w.wait(150); await w.fill('#cName', 'Ally'); await w.fill('#cNostr', pa['npub']); await w.click('[data-act=contactSave]'); await w.wait(300)
        await w.ev("document.querySelector('[data-act=payContact]').click()"); await w.wait(200)
        await w.click('[data-act=zapContact]'); await w.until("!!document.querySelector('[data-act=zapQuote]')", 10000)
        await w.fill('#amtIn', '21'); await w.click('[data-act=zapQuote]'); await w.until("!!document.querySelector('#payBtn')", 10000)
        ba = await w.bal(A); n0 = await w.ev("Nutcade.S.txs.length")
        await w.ev("(b=>{b.click();b.click();b.click()})(document.querySelector('#payBtn'))"); await w.wait(3500)
        check('zap: a contact is zapped by name, and a triple tap on Pay pays once', await w.ev("Nutcade.S.txs.length") == n0 + 1 and await w.ev("Nutcade.S.txs[0].note") == 'Zap to Ally' and ba - await w.bal(A) < 42, (await w.ev("Nutcade.S.txs.length") - n0, ba - await w.bal(A)))
        await w.ev("Nutcade.closeSheet()"); await books(w, 'zap contact', broken)
        # scanning an unknown npub offers a zap without saving
        await w.ev(f"Nutcade.handleScan({json.dumps(pe['npub'])})"); await w.wait(300)
        check('zap: scanning an unknown npub offers to zap without saving', await w.ev("!!document.querySelector('#layer [data-act=zapOpen]')"))
        await w.ev("Nutcade.closeSheet()")

        # =================== Nostr Wallet Connect (NIP-47) ===================
        uri = await make_nwc(w, 'Damus')
        check('nwc: creating a connection shows its nostr+walletconnect:// link and QR', bool(uri) and uri.startswith('nostr+walletconnect://') and 'relay=' in uri and 'secret=' in uri, uri)
        secret = re.search(r'secret=([0-9a-f]{64})', uri).group(1)
        await w.ev("Nutcade.closeSheet()"); await w.wait(200)
        stored = await w.ev("JSON.stringify(Object.assign({}, localStorage))")
        check("nwc: the app's secret is shown once and never stored", secret not in stored and secret not in await w.ev("document.body.innerHTML"))
        panel = await w.ev("document.querySelector('#set-nwc').innerText")
        check('nwc: the list says plainly it only answers while NUTCADE is open, and the budget warning (no budget: whole balance)', 'only answers while NUTCADE is open' in panel and 'Damus' in panel and 'whole balance' in panel, panel[:400])
        r = await nwc(w, uri, 'get_info'); r4 = await nwc(w, uri, 'get_info', enc='nip04')
        check('nwc: get_info answers over NIP-44 (tagged) and over NIP-04 for older apps', r['answer'] and r['answer']['result']['methods'] and r['enc_tag'] and r4['answer'] and r4['answer']['result']['alias'] == 'NUTCADE' and not r4['enc_tag'] and r['valid'], (r.get('answer'), r4.get('answer')))
        notes = await asyncio.to_thread(mock, '/test/nwc/notes', {'uri': uri})
        check('nwc: the info event (kind 13194) lists the methods and encryptions', notes['info'] and 'pay_invoice' in notes['info']['content'] and ['encryption', 'nip44_v2 nip04'] in notes['info']['tags'], notes['info'])
        tot = await w.bal()
        r = await nwc(w, uri, 'get_balance')
        check('nwc: get_balance is the wallet balance in msat', r['answer']['result']['balance'] == tot * 1000, (r['answer'], tot))
        inv = invoice(500, B); ba = await w.bal(A)
        r = await nwc(w, uri, 'pay_invoice', {'invoice': inv})
        pt = await w.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(inv)})")
        ph = await w.ev(f"Nutcade.r7.decodeBolt11({json.dumps(inv)}).paymentHash"); pre = ((r.get('answer') or {}).get('result') or {}).get('preimage') or ''
        check('(fix 5) nwc: pay_invoice pays and returns the real preimage (it hashes to the invoice\'s payment hash) and the fee', r['answer'] and r['answer']['error'] is None and len(pre) == 64 and __import__('hashlib').sha256(bytes.fromhex(pre)).hexdigest() == ph and r['answer']['result']['fees_paid'] == pt['fee'] * 1000 and pt and pt['status'] == 'done' and pt.get('preimage') == pre, r.get('answer'))
        rl = await nwc(w, uri, 'lookup_invoice', {'invoice': inv})
        check('(fix 5) nwc: lookup_invoice of a paid invoice returns the same preimage', rl['answer']['result'] and rl['answer']['result']['preimage'] == pre, rl.get('answer'))
        check('nwc: the payment shows in history marked with the connection name', pt and pt['note'] == 'Wallet Connect: Damus' and pt['nwc'] and pt['nwcName'] == 'Damus', pt and pt['note'])
        await books(w, 'nwc pay', broken)
        r2 = await nwc(w, uri, 'pay_invoice', {'invoice': inv})
        check('nwc: the same invoice asked again is not paid twice (answers with the first proof)', r2['answer']['result'] and r2['answer']['result']['preimage'] == r['answer']['result']['preimage'] and await w.ev(f"Nutcade.S.txs.filter(t=>t.request==={json.dumps(inv)}).length") == 1, r2.get('answer'))
        inv2 = invoice(300, B)
        r = await nwc(w, uri, 'pay_invoice', {'invoice': inv2}, repeat=3)
        check('nwc: the same request event delivered three times pays once', await w.ev(f"Nutcade.S.txs.filter(t=>t.request==={json.dumps(inv2)}).length") == 1 and r['answer']['error'] is None)
        await books(w, 'nwc repeat', broken)
        inv3 = invoice(200, B); n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uri, 'pay_invoice', {'invoice': inv3, 'amount': 201000})
        check('nwc: an amount that disagrees with the invoice is refused, nothing paid', r['answer']['error'] and r['answer']['error']['code'] == 'OTHER' and await w.ev("Nutcade.S.txs.length") == n0, r['answer'])
        r = await nwc(w, uri, 'pay_invoice', {'invoice': invoice(900000, B)})
        check('nwc: more than the wallet holds answers INSUFFICIENT_BALANCE, nothing paid', r['answer']['error'] and r['answer']['error']['code'] == 'INSUFFICIENT_BALANCE' and await w.ev("Nutcade.S.txs.length") == n0, r['answer'])
        r = await nwc(w, uri, 'make_invoice', {'amount': 2100000, 'description': 'coffee'})
        mk = r['answer']['result']
        ok = await w.until(f"(Nutcade.S.txs.find(t=>t.request==={json.dumps(mk['invoice'])})||{{}}).status==='done'", 20000)
        r = await nwc(w, uri, 'lookup_invoice', {'payment_hash': mk['payment_hash']})
        check('nwc: make_invoice makes a 2,100 SAT invoice; once paid it is minted and lookup_invoice says settled', mk['amount'] == 2100000 and ok and r['answer']['result']['state'] == 'settled' and r['answer']['result']['type'] == 'incoming', (mk.get('amount'), ok, r['answer']))
        r = await nwc(w, uri, 'make_invoice', {'amount': 1500})
        check('nwc: make_invoice refuses amounts that are not whole sats', r['answer']['error'] and r['answer']['error']['code'] == 'OTHER', r['answer'])
        r = await nwc(w, uri, 'lookup_invoice', {'payment_hash': '00' * 32})
        check('nwc: lookup_invoice of an unknown hash answers NOT_FOUND', r['answer']['error']['code'] == 'NOT_FOUND', r['answer'])
        own = await w.ev("Nutcade.S.txs.find(t=>t.method==='ln'&&t.type==='in'&&!t.nwc&&t.request).request")   # a deposit made in the app, not by this connection
        r = await nwc(w, uri, 'lookup_invoice', {'invoice': own}); rall = await nwc(w, uri, 'list_transactions', {'limit': 200, 'unpaid': True})
        mine = await w.ev("Nutcade.S.nwc[0].id"); ids = await w.ev("Nutcade.S.txs.filter(t=>t.nwc===Nutcade.S.nwc[0].id&&t.method==='ln').map(t=>t.request)")
        check('(fix 8) nwc: by default an app sees only its own payments and invoices (another invoice is NOT_FOUND to it)', r['answer']['error'] and r['answer']['error']['code'] == 'NOT_FOUND' and all(x['invoice'] in ids for x in rall['answer']['result']['transactions']) and len(rall['answer']['result']['transactions']) == len(ids), (r['answer'], len(rall['answer']['result']['transactions']), len(ids)))
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=nwcEdit]'); await w.wait(200)
        warn = await w.sheet_text(); await w.pg.check('#nwcAll'); await w.click('[data-act=nwcSave]'); await w.wait(300)
        r = await nwc(w, uri, 'lookup_invoice', {'invoice': own})
        check('(fix 8) nwc: with "see my whole wallet history" on (off by default, with a plain warning), it sees the other invoice too', 'whole wallet history' in warn and 'every Lightning payment' in warn and r['answer']['result'] and r['answer']['result']['invoice'] == own, r['answer'])
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=nwcEdit]'); await w.wait(200); await w.pg.uncheck('#nwcAll'); await w.click('[data-act=nwcSave]'); await w.wait(300)
        r = await nwc(w, uri, 'list_transactions', {'limit': 10})
        lt = r['answer']['result']['transactions']
        check('nwc: list_transactions lists the Lightning payments, newest first', any(x['invoice'] == inv and x['type'] == 'outgoing' and x['state'] == 'settled' for x in lt) and any(x['invoice'] == mk['invoice'] for x in lt), [(x['type'], x['amount'], x['state']) for x in lt][:6])
        await w.wait(800)
        notes = await asyncio.to_thread(mock, '/test/nwc/notes', {'uri': uri})
        kinds = {(n['kind'], (n.get('note') or {}).get('notification_type')) for n in notes['notes']}
        check('nwc: notifications payment_sent and payment_received are sent to the app', (23197, 'payment_sent') in kinds and (23197, 'payment_received') in kinds, kinds)
        r = await nwc(w, uri, 'make_invoice_x')
        check('nwc: an unknown method answers NOT_IMPLEMENTED', r['answer']['error']['code'] == 'NOT_IMPLEMENTED', r['answer'])
        await w.until("Date.now()/1000 - Nutcade.r7.nwcSince() > 40", 60000)   # backdated requests below must not predate this tab's answering
        n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uri, 'pay_invoice', {'invoice': invoice(77, B)}, age=90, wait=6)
        check('(fix 6) nwc: a request more than a minute old is refused with an error, not paid', r['answer'] and r['answer']['error'] and r['answer']['error']['code'] == 'OTHER' and 'minute old' in r['answer']['error']['message'] and await w.ev("Nutcade.S.txs.length") == n0, r.get('answer'))
        r65 = await nwc(w, uri, 'pay_invoice', {'invoice': invoice(66, B)}, age=65, wait=6); r30 = await nwc(w, uri, 'get_info', age=30)
        check('(fix 6) nwc: the 60 s rule: a payment 65 s old is refused (not paid), a request 30 s old is answered', r65['answer'] and r65['answer']['error'] and 'minute old' in r65['answer']['error']['message'] and not await w.ev("Nutcade.S.txs.some(t=>t.amount===66&&t.type==='out')") and r30['answer'] and r30['answer']['result'] and r30['answer']['result']['alias'] == 'NUTCADE', (r65.get('answer'), r30.get('answer')))
        r = await nwc(w, uri, 'get_info', age=900, wait=3)
        check('nwc: a request from long ago is ignored', r['answer'] is None)
        r = await nwc(w, uri, 'get_info', expired=True, wait=3)
        check('nwc: an expired request is ignored', r['answer'] is None)
        await books(w, 'nwc make', broken)
        # budgets: per day
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=nwcEdit]'); await w.wait(200)
        await w.fill('#nwcName', 'Damus Pro'); await w.pg.select_option('#nwcPer', 'day'); await w.wait(100)
        await w.fill('#amtIn', '1.5'); await w.click('[data-act=nwcSave]'); await w.wait(200); er = await w.err()
        check('nwc: the budget amount goes through the strict parser', 'whole numbers' in er, er)
        spent = await w.ev("Nutcade.S.txs.filter(t=>t.nwc&&t.type==='out'&&t.status==='done'&&t.ts>=new Date().setHours(0,0,0,0)).reduce((s,t)=>s+t.amount+(t.fee||0),0)")
        await w.fill('#amtIn', str(spent + 700)); await w.click('[data-act=nwcSave]'); await w.wait(300)
        panel = await w.ev("document.querySelector('#set-nwc').innerText")
        check('nwc: renamed, with a daily budget shown as left today', 'Damus Pro' in panel and '700 SAT of' in panel and 'left today' in panel, panel[:400])
        r = await nwc(w, uri, 'get_balance')
        check('nwc: get_balance is capped by what the budget has left', r['answer']['result']['balance'] == 700000, r['answer'])
        r = await nwc(w, uri, 'pay_invoice', {'invoice': invoice(600, B)})
        t0 = await w.ev("Nutcade.S.txs[0]")
        check('nwc: a payment inside the budget goes through, under the new name', r['answer']['error'] is None and t0['note'] == 'Wallet Connect: Damus Pro', (r['answer'], t0['note']))
        n0 = await w.ev("Nutcade.S.txs.length"); ba = await w.bal()
        r = await nwc(w, uri, 'pay_invoice', {'invoice': invoice(400, B)})
        check('nwc: a payment past the budget answers QUOTA_EXCEEDED and pays nothing', r['answer']['error'] and r['answer']['error']['code'] == 'QUOTA_EXCEEDED' and await w.ev("Nutcade.S.txs.length") == n0 and await w.bal() == ba, r['answer'])
        await books(w, 'nwc budget', broken)
        # (fix 1) fee mint, budget = amount + Lightning reserve only: refused, since the mint's fees could push it over
        uriT = await make_nwc(w, 'Tight', 'total', 12); await w.ev("Nutcade.closeSheet()"); await w.use(A); n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uriT, 'pay_invoice', {'invoice': invoice(10, B)})
        check('(fix 1) nwc: on the fee mint, a 10 SAT invoice against a 12 SAT budget (amount + reserve) is refused: the worst case includes the mint fee', r['answer']['error'] and r['answer']['error']['code'] == 'QUOTA_EXCEEDED' and await w.ev("Nutcade.S.txs.length") == n0, r['answer'])
        cost = await w.ev(f"(async()=>{{const q=await (await fetch('{A}/v1/melt/quote/bolt11',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{request:{json.dumps(invoice(10, B))},unit:'sat'}})}})).json(); return Nutcade.r7.meltCost({json.dumps(A)}, q.amount, q.fee_reserve)}})()")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.ev("[...document.querySelectorAll('#set-nwc [data-act=nwcEdit]')].pop().click()"); await w.wait(200)
        await w.fill('#amtIn', str(cost['total'])); await w.click('[data-act=nwcSave]'); await w.wait(300)
        r = await nwc(w, uriT, 'pay_invoice', {'invoice': invoice(10, B)})
        sp = await w.ev("(c=>Nutcade.S.txs.filter(t=>t.nwc===c.id&&t.type==='out'&&t.status!=='failed').reduce((s,t)=>s+t.amount+(t.fee||0),0))(Nutcade.S.nwc.find(c=>c.name==='Tight'))")
        check('(fix 1) nwc: with the budget at the worst case it pays, and what it really cost stays within the budget', r['answer']['error'] is None and 10 < sp <= cost['total'], (r['answer'], sp, cost))
        await books(w, 'nwc tight budget', broken)
        # (fix 2) reload while a Wallet Connect payment is in flight: it stays tagged, counts against the budget, and its change comes back
        uriR = await make_nwc(w, 'Reloader', 'day', 1000); await w.ev("Nutcade.closeSheet()")
        held = asyncio.Event()
        async def hold_melt(route):   # the mint pays, but the answer (with the change) never reaches the page, which reloads
            try: await route.fetch()
            except Exception: pass
            held.set()
        await w.pg.route('http://127.0.0.1:3338/v1/melt/bolt11', hold_melt)
        inv600 = invoice(600, B)
        await asyncio.to_thread(mock, '/test/nwc', {'uri': uriR, 'method': 'pay_invoice', 'params': {'invoice': inv600}, 'nowait': True})
        await asyncio.wait_for(held.wait(), 30); await w.wait(300)
        pre_tag = await w.ev(f"(t=>t&&[t.nwc,t.status])(Nutcade.S.txs.find(t=>t.request==={json.dumps(inv600)}))")
        await w.pg.unroute('http://127.0.0.1:3338/v1/melt/bolt11'); await w.pg.reload(); await w.wait(1500)
        await w.until(f"(Nutcade.S.txs.find(t=>t.request==={json.dumps(inv600)})||{{}}).status==='done'", 40000)
        t6 = await w.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(inv600)})")
        mc = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(A)}, 600, 0)"))['mintFee']
        check('(fix 2) nwc: the payment is tagged with its app before it goes out, and still after a reload mid-payment', pre_tag and pre_tag[0] and t6.get('nwc') == pre_tag[0], (pre_tag, t6.get('nwc')))
        check('(fix 2) after a reload mid-payment, the change comes back: the fee recorded is the real one, not the whole reserve', change_ok(600, t6), (t6['fee'], mc))
        r = await nwc(w, uriR, 'pay_invoice', {'invoice': invoice(600, B)})
        check('(fix 2) a second 600 SAT payment on the 1,000 SAT daily budget is refused after the reload', r['answer']['error'] and r['answer']['error']['code'] == 'QUOTA_EXCEEDED', r['answer'])
        await books(w, 'nwc reload mid-payment', broken)
        # the same lost answer on a plain payment (no reload): the change is recovered too
        held2 = asyncio.Event()
        async def drop_melt(route):
            try: await route.fetch()
            except Exception: pass
            held2.set(); await route.abort()
        await w.pg.route('http://127.0.0.1:3338/v1/melt/bolt11', drop_melt)
        e, q = await w.pay_ln(invoice(700, B))
        await w.pg.unroute('http://127.0.0.1:3338/v1/melt/bolt11')
        await w.until("Nutcade.S.txs[0].status==='done'", 30000); t7 = await w.ev("Nutcade.S.txs[0]")
        check('(fix 2) a payment whose answer was lost still records the real fee (its change restored), not the whole reserve', t7['amount'] == 700 and change_ok(700, t7) and not e, (t7['status'], t7['fee'], e))
        await books(w, 'lost melt answer', broken)
        CORS = {'access-control-allow-origin': '*', 'content-type': 'application/json'}
        async def drop_answer(route):   # the mint pays, the answer never arrives
            try: await route.fetch()
            except Exception: pass
            await route.abort()
        def failing(n, status):   # the first n calls fail with this status, the rest go through
            left = {'n': n}
            async def h(route):
                if left['n'] > 0: left['n'] -= 1; await route.fulfill(status=status, headers=CORS, body='{"detail":"test failure"}')
                else: await route.continue_()
            return h
        PEND = "(t=>[t.status,t.fee,!!t.changePending,!!Nutcade.S.pending.find(p=>p.txId===t.id)])(Nutcade.S.txs[0])"
        async def try_now():   # the payment's detail: Try now
            await w.click('[data-act=tab][data-tab=history]'); await w.wait(200); await w.ev("document.querySelector('#txList .tx').click()"); await w.wait(250)
            ok = await w.ev("!!document.querySelector('#layer [data-act=reconcileTx]')"); txt = await w.sheet_text()
            if ok: await w.click('#layer [data-act=reconcileTx]')
            await w.until("!Nutcade.S.txs[0].changePending", 20000); await w.ev("Nutcade.closeSheet()")
            return ok, txt
        # (round 2, item 1) the change recovery fails once (500 on restore, then 429 on the state check): the payment
        # stays open with its counter range, says so, and the fee is only lowered by what really came back
        for what, path, status in (('restore 500', '/v1/restore', 500), ('checkstate 429', '/v1/checkstate', 429)):
            mc = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(A)}, 800, 0)"))['mintFee']
            await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(f'{A}{path}', failing(1, status))
            e, q = await w.pay_ln(invoice(800, B))
            await w.pg.unroute(f'{A}/v1/melt/bolt11')
            st = await w.ev(PEND)
            check(f'(round 2, 1) {what} during change recovery: the payment is done, its change still pending, the record kept for a retry', st[0] == 'done' and st[2] and st[3] and st[1] >= 8, st)
            await w.pg.unroute(f'{A}{path}')
            ok, txt = await try_now(); st2 = await w.ev(PEND)
            check(f'(round 2, 1) {what}: the payment says its change is still coming, and Try now recovers it: fee is the real one, record closed', ok and 'hasn\'t come back from the mint yet' in txt and not st2[2] and not st2[3] and change_ok(800, await w.ev('Nutcade.S.txs[0]')), (st2, txt[:160]))
            await books(w, 'change recovery after ' + what, broken)
        # three reloads in a row while the change is being recovered, then it comes back
        hits = {'n': 0}
        async def hold(route): hits['n'] += 1   # never answered: the tab is reloaded in the middle
        await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(f'{A}/v1/restore', hold)
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#destIn', invoice(900, B)); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn')", 10000); await w.click('#payBtn')
        for i in range(3):
            n0 = hits['n']
            for _ in range(80):
                if hits['n'] > n0: break
                await w.wait(250)
            if i == 0: await w.pg.unroute(f'{A}/v1/melt/bolt11')
            await w.pg.reload(); await w.wait(600)
        st = await w.ev(PEND)
        check('(round 2, 1) three reloads in a row during change recovery: the payment stays open with its change pending', st[0] == 'done' and st[2] and st[3], st)
        await w.pg.unroute(f'{A}/v1/restore'); await w.pg.reload(); await w.wait(800); mc = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(A)}, 800, 0)"))['mintFee']
        await w.until("!Nutcade.S.txs[0].changePending", 30000); st = await w.ev(PEND)
        check('(round 2, 1) after the reloads, the next start recovers the change: the real fee, record closed', not st[2] and not st[3] and change_ok(900, await w.ev('Nutcade.S.txs[0]')), st)
        await books(w, 'change recovery through reloads', broken)
        # Find lost ecash credits found change to its payment instead of adding a "Recovered" line
        mc = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(A)}, 800, 0)"))['mintFee']
        await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(f'{A}/v1/restore', failing(1000, 500))
        e, q = await w.pay_ln(invoice(600, B)); await w.pg.unroute(f'{A}/v1/melt/bolt11'); await w.pg.unroute(f'{A}/v1/restore')
        RECA = "Nutcade.S.txs.filter(t=>t.note==='Recovered with recovery phrase'&&t.mint===" + json.dumps(A) + ").length"
        nrec = await w.ev(RECA); tid = await w.ev("Nutcade.S.txs[0].id")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=findLost]'); await w.until(f"!(Nutcade.S.txs.find(t=>t.id==={json.dumps(tid)})||{{}}).changePending", 60000); await w.wait(500)
        t9 = await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(tid)})")
        check('(round 2, 1) Find lost ecash credits the change to its payment (real fee), with no separate Recovered line', not t9.get('changePending') and change_ok(600, t9) and await w.ev(RECA) == nrec, (t9['fee'], t9.get('changePending')))
        await books(w, 'find lost credits change', broken)
        # an interrupted deposit whose restore fails once: the quote is kept, then the ecash is credited to that deposit (no double line)
        await w.pg.route(f'{B}/v1/restore', failing(1, 500))
        await w.ev(f"""(async()=>{{ const S=Nutcade.S; const ws=new CashuLib.Wallet('{B}',{{unit:'sat',bip39seed:CashuLib.mnemonicToSeedSync(S.seed.mnemonic),counterInit:{{...S.counters}}}}); await ws.loadMint();
            const q=await ws.createMintQuoteBolt11(640); const id='crash'+Date.now();
            S.txs.unshift({{id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'ln',amount:640,mint:'{B}',quote:q.quote,request:q.request}});
            S.quotes.push({{kind:'bolt11',quote:q.quote,request:q.request,amount:640,mint:'{B}',txId:id}});
            await new Promise(r=>setTimeout(r,1200)); await ws.mintProofsBolt11(640,q.quote); window.__crashTx=id; }})()""")
        ok = await w.until("(Nutcade.S.txs.find(t=>t.id===window.__crashTx)||{}).status==='done'", 40000); await w.pg.unroute(f'{B}/v1/restore')
        ct = await w.ev("Nutcade.S.txs.find(t=>t.id===window.__crashTx)")
        check('(round 2, 1) an interrupted deposit whose recovery fails once is retried, then credited to the deposit itself', ok and ct['amount'] == 640 and not await w.ev("Nutcade.S.txs.some(t=>t.note==='Recovered with recovery phrase'&&t.mint===" + json.dumps(B) + "&&t.ts>Date.now()-60000)"), ct)
        await books(w, 'interrupted deposit retried', broken)
        # (round 2, item 4) a slow mint (800 ms on every call) and a reload mid-payment: the startup check and the live
        # watch both reconcile the payment at once; its change is credited once, the fee is the real one (not 0)
        async def slow(route):
            await asyncio.sleep(0.8)
            try: await route.continue_()
            except Exception: pass
        async def slow_drop(route):
            await asyncio.sleep(0.8)
            try: await route.fetch()
            except Exception: pass
            try: await route.abort()
            except Exception: pass
        for M, O in ((A, B), (B, A)):
            await w.use(M); mcm = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(M)}, 700, 0)"))['mintFee']
            await w.pg.context.route(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*'), slow); await w.pg.context.route(f'{M}/v1/melt/bolt11', slow_drop)
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
            inv7 = invoice(700, O); await w.fill('#destIn', inv7); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn')", 15000)
            await w.click('#payBtn'); await w.until(f"Nutcade.S.txs.some(t=>t.request==={json.dumps(inv7)})", 15000); await w.wait(2500)
            await w.pg.reload(); await w.wait(500)   # mid-payment: startup check and live watch both pick it up, on a slow mint
            await w.until(f"(t=>t&&t.status==='done'&&!t.changePending)(Nutcade.S.txs.find(t=>t.request==={json.dumps(inv7)}))", 60000)
            await w.pg.context.unroute(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*')); await w.pg.context.unroute(f'{M}/v1/melt/bolt11')
            t7 = await w.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(inv7)})")
            check(f'(round 2, 4) slow mint {M[-4:]} and a reload mid-payment, both checks racing: the change is credited once, the fee is the real one', change_ok(700, t7), (t7['fee'], mcm))
            await books(w, 'slow mint, reload, racing ' + M[-4:], broken, (A, B, FM))
        await w.use(A)
        # two tabs: the first is mid-payment on a slow mint when the second takes over; both try to settle it
        await w.pg.context.route(re.compile(re.escape(A) + r'/v1/(?!melt/bolt11$).*'), slow); await w.pg.context.route(f'{A}/v1/melt/bolt11', slow_drop)
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        mcT = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(A)}, 650, 0)"))['mintFee']
        invT = invoice(650, B); await w.fill('#destIn', invT); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn')", 15000)
        await w.click('#payBtn'); await w.until(f"Nutcade.S.txs.some(t=>t.request==={json.dumps(invT)})", 15000); await w.wait(2000)
        pg2 = await w.pg.context.new_page(); t2 = W(pg2, 'tab2'); pg2.on('pageerror', lambda e: t2.errs.append(str(e)))
        await pg2.goto(URL); await t2.until("!!document.querySelector('[data-act=takeover]')", 10000); await t2.click('[data-act=takeover]'); await pg2.wait_for_timeout(1500)
        paused = await w.ev("!!document.querySelector('[data-act=takeover]')")
        await t2.until(f"(t=>t&&t.status==='done'&&!t.changePending)(Nutcade.S.txs.find(t=>t.request==={json.dumps(invT)}))", 60000); await t2.wait(4000)
        await w.pg.context.unroute(re.compile(re.escape(A) + r'/v1/(?!melt/bolt11$).*')); await w.pg.context.unroute(f'{A}/v1/melt/bolt11')
        await pg2.reload(); await t2.wait(1500)   # what the storage holds now, after both tabs worked on it
        tT = await t2.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(invT)})"); b2 = []
        await books(t2, 'two tabs racing', b2, (A, B, FM))
        check('(round 2, 4) two tabs racing on the same payment: the first pauses and writes nothing more, the change is credited once, the history equals the balance', paused and tT and change_ok(650, tT) and not b2, (paused, tT and tT['fee'], mcT, b2))
        await pg2.close(); await w.pg.reload(); await w.wait(1200)
        await books(w, 'after two tabs', broken, (A, B, FM))
        # (round 2, C) reload mid-move, both ways, on a slow mint whose answer is lost: real fee, the deposit claimed, books add up
        for M, O in ((A, B), (B, A)):
            mcm = (await w.ev(f"Nutcade.r7.meltCostNow({json.dumps(M)}, 400, 0)"))['mintFee']
            await w.pg.context.route(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*'), slow); await w.pg.context.route(f'{M}/v1/melt/bolt11', slow_drop)
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200); await w.click('#app [data-act=moveOpen]'); await w.wait(250)
            await w.ev(f"document.querySelector('#mvFrom').value={json.dumps(M)}; document.querySelector('#mvTo').value={json.dumps(O)}"); await w.fill('#amtIn', '400')
            await w.click('[data-act=moveQuote]'); await w.until("!!document.querySelector('#mvGo')", 20000); n0 = await w.ev("Nutcade.S.txs.length")
            await w.click('#mvGo'); await w.until(f"Nutcade.S.txs.length >= {n0 + 2}", 20000); await w.wait(2500)
            await w.pg.reload(); await w.wait(500)
            ok = await w.until("(o=>o&&o.status==='done'&&!o.changePending)(Nutcade.S.txs.find(t=>t.move&&t.type==='out')) && (i=>i&&i.status==='done')(Nutcade.S.txs.find(t=>t.move&&t.type==='in'))", 60000)
            await w.pg.context.unroute(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*')); await w.pg.context.unroute(f'{M}/v1/melt/bolt11')
            mo = await w.ev("[Nutcade.S.txs.find(t=>t.move&&t.type==='out'), Nutcade.S.txs.find(t=>t.move&&t.type==='in')]")
            check(f'(round 2, C) reload mid-move {M[-4:]} to {O[-4:]} on a slow mint: the move settles with the real fee and the deposit is claimed', ok and mo[0]['mint'] == M and change_ok(400, mo[0]) and mo[1]['mint'] == O and mo[1]['amount'] == 400, [(x['mint'][-4:], x['amount'], x['fee'], x['status']) for x in mo])
            await books(w, 'reload mid-move ' + M[-4:], broken, (A, B, FM))
        # reload mid-payment for a payment split across both mints (multinut)
        ba_, bb_ = await w.bal(A), await w.bal(B); amtM = max(ba_, bb_) + min(ba_, bb_) // 3
        for M in (A, B): await w.pg.context.route(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*'), slow); await w.pg.context.route(f'{M}/v1/melt/bolt11', slow_drop)
        await w.use(A); await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#destIn', invoice(amtM, FM)); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#mppBtn')", 20000)
        await w.click('#mppBtn'); await w.until("!!document.querySelector('#mppPay')", 40000); await w.click('#mppPay')
        await w.until("Nutcade.S.txs.filter(t=>/\\(part \\d of \\d\\)$/.test(t.note||'')&&t.status==='pending').length>=2", 30000); await w.wait(2500)
        parts_note = await w.ev("Nutcade.S.txs.filter(t=>/\\(part \\d of \\d\\)$/.test(t.note||'')).slice(0,2).map(t=>t.id)")
        await w.pg.reload(); await w.wait(500)
        ok = await w.until(f"{json.dumps(parts_note)}.every(id=>(t=>t&&t.status==='done'&&!t.changePending)(Nutcade.S.txs.find(t=>t.id===id)))", 60000)
        for M in (A, B): await w.pg.context.unroute(re.compile(re.escape(M) + r'/v1/(?!melt/bolt11$).*')); await w.pg.context.unroute(f'{M}/v1/melt/bolt11')
        pm = await w.ev(f"{json.dumps(parts_note)}.map(id=>Nutcade.S.txs.find(t=>t.id===id)).map(t=>[t.mint,t.amount,t.fee,t.status])")
        pts = await w.ev(f"{json.dumps(parts_note)}.map(id=>Nutcade.S.txs.find(t=>t.id===id))")
        check('(round 2, C) reload mid-payment split across two mints (multinut) on slow mints: both parts settle with real fees', ok and len(pm) == 2 and {p[0] for p in pm} == {A, B} and sum(p[1] for p in pm) == amtM and all(change_ok(t['amount'], t) for t in pts), pm)
        await books(w, 'reload mid-multinut', broken, (A, B, FM))
        await w.use(B); await w.receive_ln(4000); await w.use(A); await w.receive_ln(15000)   # (the split payment spent most of both mints)
        # restoring from the 12 words after all of the above finds nothing extra: every SAT is already accounted for
        bal0, n0 = await w.bal(), await w.ev("Nutcade.S.txs.length")
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=seedRestore]'); await w.wait(250)
        await w.fill('#phraseIn', await w.ev("Nutcade.S.seed.mnemonic"))
        await w.ev(f"document.querySelectorAll('[data-rmint]').forEach(i=>{{i.checked=[{json.dumps(A)},{json.dumps(B)},{json.dumps(FM)}].includes(i.dataset.rmint)}})")
        await w.click('[data-act=doRestorePhrase]'); await w.until("/SCAN COMPLETE|CONTINUE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 120000); rtxt = await w.sheet_text()
        check('(round 2, C) a restore from the 12 words after the recovery-failure and race cases finds nothing extra', 'SCAN COMPLETE' in rtxt and await w.bal() == bal0 and await w.ev("Nutcade.S.txs.length") == n0, (rtxt[:120], await w.bal() - bal0))
        await w.ev("Nutcade.closeSheet()"); await books(w, 'restore from 12 words', broken, (A, B, FM))
        # ================= round 3 =================
        def held(delay):   # the mint does it at once; its answer reaches the page `delay` s later
            async def h(route):
                try: r = await route.fetch()
                except Exception: return
                await asyncio.sleep(delay)
                try: await route.fulfill(response=r)
                except Exception: pass
            return h
        async def find_lost():
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
            await w.click('[data-act=findLost]'); await w.wait(500); await w.until("!document.querySelector('[data-act=findLost] .spinner')", 120000); await w.wait(500)
        RECB = lambda m: f"Nutcade.S.txs.filter(t=>t.note==='Recovered with recovery phrase'&&t.mint==={json.dumps(m)}).length"
        async def ln_pay_start(M, inv):
            await w.use(M); await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
            await w.fill('#destIn', inv); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn')", 20000); await w.click('#payBtn')
        await w.pg.route_web_socket(re.compile(r'127\.0\.0\.1:33(38|39|40)'), lambda ws: None)   # no live updates from the mints: polling only
        await w.pg.reload(); await w.wait(1500)
        # (round 3, item 1a) Find lost ecash while a payment's answer is on its way: its change is the payment's, never "Recovered"
        for M, O in ((B, A), (A, B)):
            nrec = await w.ev(RECB(M)); inv = invoice(900, O)
            await w.pg.route(f'{M}/v1/melt/bolt11', held(7)); await ln_pay_start(M, inv)
            await w.wait(2500); await find_lost()
            await w.until(f"(t=>t&&t.status==='done'&&!t.changePending)(Nutcade.S.txs.find(t=>t.request==={json.dumps(inv)}))", 60000); await w.pg.unroute(f'{M}/v1/melt/bolt11')
            t1 = await w.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(inv)})")
            check(f'(round 3, 1a) {M[-4:]}: Find lost ecash during a slow payment answer: the change goes to the payment once, no Recovered line', change_ok(900, t1) and await w.ev(RECB(M)) == nrec, (t1 and (t1['fee'], t1.get('change')), await w.ev(RECB(M)) - nrec))
            await books(w, 'find lost during slow payment ' + M[-4:], broken, (A, B, FM))
        # (round 3, item 1b) Find lost ecash while a token claim, then a token make, is waiting for the mint's answer
        await w.use(B); tokC, _ = await w.send_ecash(700, 'r3 claim'); nrec = await w.ev(RECB(B))
        await w.pg.route(f'{B}/v1/swap', held(6))
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100); await w.fill('#tokIn', tokC); await w.click('[data-act=doReceiveToken]')
        await w.wait(1500); await w.ev("Nutcade.closeSheet()"); await find_lost()
        await w.until(f"Nutcade.S.txs.some(t=>t.token==={json.dumps(tokC)}&&t.status==='reclaimed')", 30000); await w.wait(1000)
        check('(round 3, 1b) Find lost ecash during a token claim: the claim records the ecash once, no Recovered line', await w.ev(RECB(B)) == nrec and await w.ev("Nutcade.S.ops.length") == 0, await w.ev(RECB(B)) - nrec)
        await books(w, 'find lost during a claim', broken, (A, B, FM))
        n0 = await w.ev("Nutcade.S.txs.length")
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '900'); await w.click('[data-act=doSendEcash]')
        await w.wait(1500); await w.ev("Nutcade.closeSheet()"); await find_lost()
        await w.until("Nutcade.S.txs.some(t=>t.type==='out'&&t.method==='ecash'&&t.amount===900&&t.token)", 30000); await w.pg.unroute(f'{B}/v1/swap'); await w.wait(1000)
        tm = await w.ev("Nutcade.S.txs.find(t=>t.type==='out'&&t.method==='ecash'&&t.amount===900&&t.token)")
        check('(round 3, 1b) Find lost ecash during a token make: the token is 900 SAT with no fee (no-fee mint), no Recovered line', tm and tm['fee'] == 0 and await w.ev(RECB(B)) == nrec, tm and tm['fee'])
        await books(w, 'find lost during a make', broken, (A, B, FM))
        # (round 3, item 2) interrupted deposits (two at once, and one while Find lost runs) settle as themselves; never offered for paying
        async def drop_mint(route):
            try: await route.fetch()
            except Exception: pass
            try: await route.abort()
            except Exception: pass
        await w.use(B); nrec = await w.ev(RECB(B)); await w.pg.route(f'{B}/v1/mint/bolt11', drop_mint); await w.pg.route(f'{B}/v1/restore', failing(1000, 500))   # (held unsettled while we look)
        for amt in (410, 333):
            await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
            if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
            await w.fill('#amtIn', str(amt)); await w.click('[data-act=doLnInvoice]'); await w.wait(2500); await w.ev("Nutcade.closeSheet()")
        await w.until("Nutcade.S.quotes.filter(q=>q.state==='PAID'||q.state==='ISSUED').length>=2", 30000)
        await w.click('[data-act=tab][data-tab=history]'); await w.wait(200); await w.ev("document.querySelector('#txList [data-id=\"'+Nutcade.S.quotes.find(q=>q.amount==410).txId+'\"]').click()"); await w.wait(300)
        dtx = await w.sheet_text(); offer = await w.ev("!!document.querySelector('#layer [data-act=resumeInvoice]')")
        check('(round 3, 2) a deposit the mint says is paid is never offered for paying again: no Show invoice, it says it is being collected', not offer and 'already paid' in dtx, (offer, dtx[:200]))
        await w.pg.unroute(f'{B}/v1/restore'); await find_lost(); await w.pg.unroute(f'{B}/v1/mint/bolt11')
        ok = await w.until("[410,333].every(a=>Nutcade.S.txs.some(t=>t.type==='in'&&t.method==='ln'&&t.amount===a&&t.status==='done'&&t.mint===" + json.dumps(B) + "))", 90000)
        check('(round 3, 2) two interrupted deposits (one while Find lost ran) each settle as themselves, with no Recovered line and no quote left', ok and await w.ev(RECB(B)) == nrec and await w.ev(f"Nutcade.S.quotes.filter(q=>q.mint==={json.dumps(B)}).length") == 0, (ok, await w.ev(RECB(B)) - nrec))
        await books(w, 'interrupted deposits', broken, (A, B, FM))
        # (round 3, 2, go) the exact case: the deposit's own restore fails once, and Find lost is tapped at once and again
        # 3 s later (so one scan joins another): the deposit is still credited to itself, never 0, never "Recovered"
        nrec = await w.ev(RECB(B)); await w.pg.route(f'{B}/v1/mint/bolt11', drop_mint); await w.pg.route(f'{B}/v1/restore', failing(1, 500))
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
        if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#amtIn', '444'); await w.click('[data-act=doLnInvoice]'); await w.until("Nutcade.S.quotes.some(q=>q.amount==444&&q.ctr)", 30000); await w.ev("Nutcade.closeSheet()")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.ev("document.querySelector('[data-act=findLost]').click()"); await w.wait(3000)
        await w.ev("const b=document.querySelector('[data-act=findLost]'); if (b && !b.disabled) b.click()"); await w.pg.unroute(f'{B}/v1/mint/bolt11')
        ok = await w.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.method==='ln'&&t.amount===444&&t.status==='done'&&t.mint==={json.dumps(B)}) && !Nutcade.S.quotes.some(q=>q.amount==444)", 90000)
        await w.until("!document.querySelector('[data-act=findLost] .spinner')", 60000); await w.pg.unroute(f'{B}/v1/restore')
        check('(round 3, 2) Find lost tapped at once and 3 s later while the deposit\'s restore failed once: the deposit gets its 444 SAT, no Recovered line, nothing credited 0',
              ok and await w.ev(RECB(B)) == nrec and not await w.ev("Nutcade.S.txs.some(t=>t.type==='in'&&t.method==='ln'&&t.status==='done'&&t.amount===0)"), (ok, await w.ev(RECB(B)) - nrec))
        await books(w, 'deposit with a failed restore and two scans', broken, (A, B, FM))
        # (round 3, item 3) a reload while a token is being made on a slow mint: the step settles on the next start
        await w.use(B); bB0 = await w.bal(B); n3 = await w.ev("Nutcade.S.txs.length"); await w.pg.route(f'{B}/v1/swap', held(4))
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '500'); await w.click('[data-act=doSendEcash]'); await w.wait(1500)
        await w.pg.reload(); await w.wait(800); await w.pg.unroute(f'{B}/v1/swap')
        ok = await w.until("Nutcade.S.ops.length===0", 40000); bB1 = await w.bal(B)
        new3 = await w.ev(f"Nutcade.S.txs.slice(0, Nutcade.S.txs.length-{n3}).map(t=>[t.type,t.method,t.amount,t.fee,t.status,t.note,t.mint&&t.mint.slice(-4)])")
        e, q = await w.pay_ln(invoice(300, A))
        check('(round 3, 3) a reload during "make a token": the open step settles by itself, nothing is lost, the next payment works', ok and bB1 == bB0 and not e, (ok, bB1 - bB0, e, new3))
        await books(w, 'reload during make a token', broken, (A, B, FM))
        # coins spent elsewhere (a stale copy): the payment drops them with a line, and explains instead of failing twice
        fx = await wallet(b); await fx.create(); await fx.add_mint(B)
        tokS, _ = await w.send_ecash(200, 'r3 stale'); sp0 = await w.ev("Nutcade.S.txs.filter(t=>t.note==='Ecash already spent elsewhere').reduce((a,t)=>a+t.amount,0)")
        await fx.receive_token(tokS)
        # as if the wallet never noticed: a stored copy of coins it once received (its history has them), spent elsewhere since
        await w.ev(f"(d=>{{const P=JSON.parse(localStorage.getItem('nutcade:proofs')); P[{json.dumps(B)}].push(...d.proofs.map(p=>Object.assign({{}},p,{{amount:Number(p.amount)}}))); localStorage.setItem('nutcade:proofs', JSON.stringify(P));"
                   f" const T=JSON.parse(localStorage.getItem('nutcade:txs')); T.unshift({{id:'stale1', type:'in', method:'ecash', amount:200, mint:{json.dumps(B)}, status:'done', ts:Date.now(), note:'stale copy'}}); localStorage.setItem('nutcade:txs', JSON.stringify(T));"
                   f" localStorage.setItem('nutcade:gen', String(+(localStorage.getItem('nutcade:gen')||0)+1))}})(CashuLib.getDecodedToken({json.dumps(tokS)}, Object.keys(Nutcade.S.counters)))")
        await w.pg.reload(); await w.wait(1500)
        real = await w.bal(B) - 200
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', str(real + 100)); await w.click('[data-act=doSendEcash]'); await w.wait(4000)
        er = await w.err(); await w.ev("Nutcade.closeSheet()")
        check('(round 3, 3) "already spent": the spent coins are dropped with a line ("already spent elsewhere") and the error explains, it does not just repeat "already spent"', await w.ev("Nutcade.S.txs.filter(t=>t.note==='Ecash already spent elsewhere').reduce((a,t)=>a+t.amount,0)") - sp0 == 200 and 'already spent. proofs' not in er.lower(), er)
        tok2b, e2b = await w.send_ecash(100)
        check('(round 3, 3) after that, a payment from the same mint works', tok2b and not e2b, e2b)
        await books(w, 'stale coins dropped', broken, (A, B, FM))
        # the paused-tab rule: a token claim in flight in tab A when tab B takes over: tab B settles it and gets the sats
        tokP, _ = await fx.send_ecash(111, 'for tab B')
        await w.pg.route(f'{B}/v1/swap', held(6))
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100); await w.fill('#tokIn', tokP); await w.click('[data-act=doReceiveToken]'); await w.wait(1200)
        hb = await w.bal(B)
        pg3 = await w.pg.context.new_page(); t3 = W(pg3, 'tab3')
        await pg3.goto(URL); await t3.until("!!document.querySelector('[data-act=takeover]')", 10000); await t3.click('[data-act=takeover]'); await pg3.wait_for_timeout(1500)
        ok = await t3.until(f"Nutcade.S.ops.length===0 && Nutcade.S.txs.some(t=>t.type==='in'&&t.amount===111)", 60000); await w.pg.unroute(f'{B}/v1/swap')
        await pg3.reload(); await t3.wait(1500); b3 = []
        await books(t3, 'paused-tab claim', b3, (A, B, FM))
        check('(round 3, 3) a claim in flight in a tab paused by a takeover: the new tab settles it, gets the 111 SAT once, books add up', ok and await t3.bal(B) == hb + 111 and not b3, (ok, await t3.bal(B) - hb, b3))
        await pg3.close(); await w.pg.reload(); await w.wait(1500); await fx.pg.context.close()
        # (round 3, locked outputs) an interrupted gift (P2PK), bounty (HTLC) and Extra Life (locked to your own key) come
        # back in full after a reload: the swap's outputs (and the step's follow-up data) were on record
        await w.use(B); await w.receive_ln(3000)
        async def interrupted(start, wait_s=1500):
            n0 = await w.ev("Nutcade.S.txs.length"); bal0 = await w.bal(B)
            await w.pg.route(f'{B}/v1/swap', held(8)); await start(); await w.wait(wait_s)
            outs = await w.ev("Nutcade.S.ops.map(o=>o.outs.length)")
            await w.pg.reload(); await w.wait(800); await w.pg.unroute(f'{B}/v1/swap')
            ok = await w.until("Nutcade.S.ops.length===0", 60000); await w.wait(500)
            return ok, outs, bal0, await w.ev(f"Nutcade.S.txs.slice(0, Nutcade.S.txs.length-{n0})")
        async def gift_start():
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
            await w.ev("const s=document.querySelector('#giftTo'); if (s) { s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})) }")
            await w.fill('#giftKey', okey); await w.fill('#amtIn', '300'); await w.click('[data-act=doSendEcash]')
        okey = await w.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return Array.from(CashuLib.getPubKeyFromPrivKey(k),x=>x.toString(16).padStart(2,'0')).join('')})()")
        ok, outs, bal0, new = await interrupted(gift_start)
        g = [t for t in new if t.get('type') == 'out' and t.get('method') == 'ecash' and t.get('token')]
        sec = json.loads(g[0]['sent'][0]['secret']) if g and g[0].get('sent') else None
        check('(round 3, locked) an interrupted gift (P2PK lock) is back after a reload as the same locked token: 300 SAT, locked to their key, back date kept, no loss line',
              ok and outs and outs[0] > 0 and len(g) == 1 and g[0]['amount'] == 300 and g[0]['status'] == 'pending' and g[0].get('lockUntil') and sec and sec[0] == 'P2PK' and sec[1]['data'] == okey
              and not any('no wallet can restore' in (t.get('note') or '') for t in new), (ok, outs, [(t.get('note'), t.get('amount'), t.get('status')) for t in new], sec and sec[0]))
        if g:
            fz = await wallet(b); await fz.create(); await fz.add_mint(B); _, ez, _ = await fz.receive_token(g[0]['token'])
            check('(round 3, locked) the recovered gift token is live ecash (someone else is told it is locked, not spent)', 'locked' in (ez or '').lower() and 'spent' not in (ez or '').lower(), ez)
            await fz.pg.context.close()
        await books(w, 'interrupted gift', broken, (A, B, FM))
        async def bounty_start():
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
            await w.ev("Nutcade.startChallenge({game:'flipper', seed:4242, score:1200, by:'R3B'})"); await w.wait(300)
            await w.fill('#bountyAmt', '250'); await w.click('[data-act=chalSend]')
        ok, outs, bal0, new = await interrupted(bounty_start)
        g = [t for t in new if t.get('type') == 'out' and t.get('method') == 'ecash' and t.get('token')]
        sec = json.loads(g[0]['sent'][0]['secret']) if g and g[0].get('sent') else None
        cb = await w.ev("(c=>c&&{b:(c.bounties||[]).map(b=>({tx:b.txId,state:b.state,pre:!!b.pre,H:b.H,unsent:!!b.unsent})),sent:(c.sentTo||[]).length})(Nutcade.S.challenges.find(c=>c.dir==='out'&&c.seed===4242))")
        okb = await w.until("(c=>c&&(c.bounties||[]).length===1&&!c.bounties[0].unsent&&(c.sentTo||[]).length>0)(Nutcade.S.challenges.find(c=>c.dir==='out'&&c.seed===4242))", 40000)
        cb2 = await w.ev("(c=>c&&{b:(c.bounties||[]).map(b=>({tx:b.txId,state:b.state,pre:b.pre,H:b.H,unsent:!!b.unsent})),sent:(c.sentTo||[]).length})(Nutcade.S.challenges.find(c=>c.dir==='out'&&c.seed===4242))")
        hok = bool(cb2 and cb2['b'] and cb2['b'][0]['pre'] and sec and __import__('hashlib').sha256(bytes.fromhex(cb2['b'][0]['pre'])).hexdigest() == cb2['b'][0]['H'] == sec[1]['data'])
        check('(round 3, locked) an interrupted bounty (HTLC lock) settles after a reload into a working bounty: 250 SAT locked to the hash of its saved secret, linked to its challenge',
              ok and outs and len(g) == 1 and g[0]['amount'] == 250 and g[0].get('lockUntil') and g[0].get('bounty') and sec and sec[0] == 'HTLC' and cb2 and len(cb2['b']) == 1 and cb2['b'][0]['tx'] == g[0]['id'] and cb2['b'][0]['state'] == 'open' and hok,
              (ok, outs, [(t.get('note'), t.get('amount'), t.get('bounty')) for t in new], sec and sec[0], cb2, hok))
        check('(round 3, locked) and its challenge still goes out to the friend (a relay took it)', okb, (cb, cb2))
        await books(w, 'interrupted bounty', broken, (A, B, FM))
        # an heir with a real NUTCADE, to see their side of each step
        hr = await wallet(b); await hr.create(); await hr.add_mint(B)
        hr_addr = await hr.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")
        hr_pub = await hr.ev("CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=contactsOpen]'); await w.wait(150)
        await w.click('[data-act=contactEdit]'); await w.wait(150); await w.fill('#cName', 'Heir R3'); await w.fill('#cNostr', hr_addr); await w.click('[data-act=contactSave]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
        async def extra_start(amount='400', days=None):
            await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=extraOpen]'); await w.until("!!document.querySelector('#xlTo')", 5000); await w.wait(150)
            await w.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Heir R3').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
            if days: await w.ev(f"const b=document.querySelector('[data-act=giftDays][data-days=\"90\"]'); b.dataset.days={days}/86400; b.click()")
            await w.fill('#amtIn', amount); await w.click('[data-act=extraStart]')
        mine = await w.ev("'02'+CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        ok, outs, bal0, new = await interrupted(extra_start)
        x = await w.ev("Nutcade.S.extra && {amount:Nutcade.S.extra.amount, n:Nutcade.S.extra.proofs.length, until:Nutcade.S.extra.until, heir:Nutcade.S.extra.heir.name, unlocked:!!Nutcade.S.extra.unlocked, sec:JSON.parse(Nutcade.S.extra.proofs[0].secret)}")
        toks = [t for t in new if t.get('token')]
        check('(round 3, locked) an interrupted Extra Life lock finishes its setup after a reload: 400 SAT locked to your key for your heir, its history line, no stray token',
              ok and outs and x and x['amount'] == 400 and not x['unlocked'] and x['sec'][0] == 'P2PK' and x['sec'][1]['data'] == mine and x['until'] > 0 and not toks
              and any((t.get('note') or '').startswith('Extra Life for') and t.get('amount') == 400 for t in new), (ok, outs, x and {k: x[k] for k in ('amount', 'heir', 'unlocked')}, [(t.get('note'), t.get('amount')) for t in new]))
        await books(w, 'interrupted Extra Life', broken, (A, B, FM))
        okh = await hr.until("Nutcade.S.heirlooms.some(h=>h.state==='waiting'&&h.amount===400)", 30000)
        check("(round 3, locked) and the heir's NUTCADE gets its copy", okh, await hr.ev("Nutcade.S.heirlooms.map(h=>[h.state,h.amount])"))
        # (round 4, 1-3) CONTINUE is one swap: the Extra Life's own locked coins in, new locked coins out. Interrupted at
        # every point (a reload while its answer is on the way, a lost answer, a request that never reaches the mint, a
        # reload with the first restore failing) it ends as a valid Extra Life (new date if the mint did it, old date if
        # not), with no coin of the balance touched, no fee line, and nothing for Find lost or the 12 words to find
        mine_lock = await w.ev("'02'+CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        async def never_sent(route):
            try: await route.abort()
            except Exception: pass
        async def cont_cases(M, tag):
            for how in ('reload', 'lost', 'never', 'failrestore'):
                await w.ev("Nutcade.closeSheet()"); x0 = await w.ev(EXTRA_AT_MINT); b0, n0 = await w.bal(M), await w.ev("Nutcade.S.txs.length")
                await w.pg.route(f'{M}/v1/swap', {'reload': held(8), 'lost': drop_answer, 'never': never_sent, 'failrestore': held(8)}[how])
                if how == 'failrestore': await w.pg.route(f'{M}/v1/restore', failing(1, 500))
                await w.home(); await w.click('[data-act=extraOpen]'); await w.wait(300); await w.click('[data-act=extraContinue]'); await w.wait(1500)
                if how in ('reload', 'failrestore'): await w.pg.reload(); await w.wait(800)
                await w.pg.unroute(f'{M}/v1/swap')
                ok = await w.until("Nutcade.S.ops.length===0", 120000); await w.wait(800)
                if how == 'failrestore': await w.pg.unroute(f'{M}/v1/restore')
                x = await w.ev(EXTRA_AT_MINT); nl = await w.ev(f"Nutcade.S.txs.slice(0, Nutcade.S.txs.length-{n0}).map(t=>[t.note,t.amount,t.fee])")
                moved = how != 'never'
                good = (ok and x and x0 and x['unspent'] and x['kind'] == 'P2PK' and x['pub'] == mine_lock and not x['unlocked'] and x['mint'] == M
                        and (x['until'] > x0['until'] if moved else x['until'] == x0['until']) and x['lt'] == x['until'] // 1000
                        and x0['amount'] - 1 <= x['amount'] <= x0['amount'] and x['sum'] >= x['amount'] and await w.bal(M) == b0 and not nl)
                check(f'(round 4, 1-3) {tag}: CONTINUE {how}: the Extra Life is valid ({"new" if moved else "old"} date, locked to your key, unspent), the balance and history untouched, no fee line',
                      good, (how, ok, x0 and {k: x0[k] for k in ('amount', 'sum', 'until')}, x and {k: x[k] for k in ('amount', 'sum', 'until', 'lt', 'unspent', 'unlocked')}, await w.bal(M) - b0, nl))
                await books(w, f'CONTINUE {how} {tag}', broken, (A, B, FM))
            rec0 = await w.ev(RECB(M)); await find_lost()
            ok_w, why = await words_ok(w, (A, B, FM))
            check(f'(round 4, 1-3) {tag}: after all of them, Find lost ecash finds nothing and a restore from the 12 words equals the balance', await w.ev(RECB(M)) == rec0 and ok_w, (await w.ev(RECB(M)) - rec0, why))
        await cont_cases(B, 'no-fee mint')
        # (round 4, 4) a takeover while CONTINUE's swap is on its way: the paused tab asks the mint nothing more, the tab in
        # charge finishes the Extra Life from the record
        rec = {'on': False, 'reqs': []}
        dup = {'on': True, 'n': 0}   # "outputs already signed" answers from now on (none expected: a paused tab uses no counters at the mint)
        async def dup_chk(r):
            try:
                if dup['on'] and r.status == 400 and '/v1/' in r.url and ('11003' in await r.text() or 'already signed' in (await r.text()).lower()): dup['n'] += 1
            except Exception: pass
        w.pg.on('response', lambda r: asyncio.ensure_future(dup_chk(r)))
        w.pg.on('request', lambda r: rec['reqs'].append((__import__('time').time(), r.method, r.url)) if rec['on'] and '/v1/' in r.url and r.url.startswith(('http://127.0.0.1:33', 'http://localhost:33')) else None)
        async def take_over():
            pg3 = await w.pg.context.new_page(); t3 = W(pg3, 'tab3')
            await pg3.goto(URL); await t3.until("!!document.querySelector('[data-act=takeover]')", 10000)
            await t3.click('[data-act=takeover]'); tp = __import__('time').time(); await pg3.wait_for_timeout(1500)
            return pg3, t3, tp
        async def back_to_a(pg3):
            await pg3.close(); await w.pg.reload(); await w.wait(1500)
        x0 = await w.ev(EXTRA_AT_MINT); b0 = await w.bal(B)
        await w.pg.route(f'{B}/v1/swap', held(6)); rec['on'] = True; rec['reqs'] = []
        await w.home(); await w.click('[data-act=extraOpen]'); await w.wait(300); await w.click('[data-act=extraContinue]'); await w.wait(1500)
        pg3, t3, tp = await take_over()
        await w.wait(9000); await w.pg.unroute(f'{B}/v1/swap')
        ok = await t3.until(f"Nutcade.S.ops.length===0 && Nutcade.S.extra && Nutcade.S.extra.until > {x0['until']}", 60000)
        late = [r for r in rec['reqs'] if r[0] > tp + 0.5]; rec['on'] = False
        x = await t3.ev(EXTRA_AT_MINT); b3 = []
        await books(t3, 'takeover during CONTINUE', b3, (A, B, FM))
        check('(round 4, 4) a takeover during CONTINUE: the paused tab sends no request to any mint after it is paused',
              not late, late[:4])
        check('(round 4, 4) and the tab in charge finishes the Extra Life from the record: new date, locked to your key, unspent, balance untouched, books add up',
              ok and x and x['unspent'] and x['pub'] == mine_lock and x['until'] > x0['until'] and await t3.bal(B) == b0 and not b3, (ok, x, await t3.bal(B) - b0, b3))
        await back_to_a(pg3)
        # (round 4, 4) a takeover while a Lightning payment is getting its ecash ready: nothing is paid from the paused tab
        for M, O in ((B, A), (A, B)):
            inv, qid = quote_inv(321, O); b0, n0 = await w.bal(M), await w.ev("Nutcade.S.txs.length")
            await w.pg.route(f'{M}/v1/swap', held(6)); rec['on'] = True; rec['reqs'] = []
            await ln_pay_start(M, inv); await w.wait(1500)
            pg3, t3, tp = await take_over()
            await w.wait(9000); await w.pg.unroute(f'{M}/v1/swap')
            ok = await t3.until("Nutcade.S.ops.length===0", 60000); await t3.wait(1000)
            late = [r for r in rec['reqs'] if r[0] > tp + 0.5]; rec['on'] = False
            st = quote_state(O, qid); b3 = []
            await books(t3, f'takeover during a payment {M[-4:]}', b3, (A, B, FM))
            lines = await t3.ev(f"Nutcade.S.txs.slice(0, Nutcade.S.txs.length-{n0}).map(t=>[t.note||t.method,t.amount,t.fee])")
            check(f'(round 4, 4) {M[-4:]}: a takeover while a payment gets its ecash ready: the paused tab sends no request after it is paused, the invoice is not paid',
                  not late and st == 'UNPAID', (late[:4], st))
            check(f'(round 4, 4) {M[-4:]}: and the tab in charge settles the prepared ecash: balance whole (less only the mint\'s swap fee), books add up, no payment line',
                  ok and b0 - (2 if M == A else 0) <= await t3.bal(M) <= b0 and not b3 and not any(l[0] == 'ln' for l in lines), (ok, await t3.bal(M) - b0, b3, lines))
            await back_to_a(pg3)
        await w.use(B)
        # (round 4, 3) with a PIN set, no plain spendable coins in any localStorage key, at any step of an interrupted CONTINUE
        pw = await wallet(b); await pw.create(); await pw.add_mint(B); await pw.use(B); await pw.receive_ln(3000)
        await pw.ev("Nutcade.closeSheet()"); await pw.click('[data-act=tab][data-tab=settings]'); await pw.wait(100); await pw.click('[data-act=contactsOpen]'); await pw.wait(150)
        await pw.click('[data-act=contactEdit]'); await pw.wait(150); await pw.fill('#cName', 'Heir R3'); await pw.fill('#cNostr', hr_addr); await pw.click('[data-act=contactSave]'); await pw.wait(300)
        await set_pin(pw)
        await pw.home(); await pw.click('[data-act=extraOpen]'); await pw.until("!!document.querySelector('#xlTo')", 5000); await pw.wait(150)
        await pw.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Heir R3').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
        await pw.fill('#amtIn', '600'); await pw.click('[data-act=extraStart]'); await pw.until("!!Nutcade.S.extra", 20000); await pw.ev("Nutcade.closeSheet()")
        leaks = {}
        sec = await pw.ev(SECRETS_JS); leaks['set up'] = await pw.pg.evaluate(LEAK_JS, sec)
        u0 = await pw.ev("Nutcade.S.extra.until"); await pw.pg.route(f'{B}/v1/swap', held(8))
        await pw.home(); await pw.click('[data-act=extraOpen]'); await pw.wait(300); await pw.click('[data-act=extraContinue]'); await pw.wait(1500)
        sec = sorted(set(sec + await pw.ev(SECRETS_JS))); leaks['swap on its way'] = await pw.pg.evaluate(LEAK_JS, sec)
        await pw.pg.reload(); await pw.wait(800); await pw.pg.unroute(f'{B}/v1/swap')
        leaks['after reload, locked'] = await pw.pg.evaluate(LEAK_JS, sec)
        await unlock(pw); ok = await pw.until(f"Nutcade.S.ops.length===0 && Nutcade.S.extra && Nutcade.S.extra.until > {u0}", 60000); await pw.wait(800)
        sec = sorted(set(sec + await pw.ev(SECRETS_JS))); leaks['settled'] = await pw.pg.evaluate(LEAK_JS, sec)
        x = await pw.ev(EXTRA_AT_MINT); pb = []
        await books(pw, 'PIN CONTINUE', pb, (B,))
        check('(round 4, 3) with a PIN, no plain spendable coins (or journal secrets) in any localStorage key: set up, swap on its way, reloaded and locked, settled',
              len(sec) > 5 and not any(leaks.values()), leaks)
        check('(round 4, 3) and the interrupted CONTINUE finishes under the PIN: new date, valid at the mint, books add up', ok and x and x['unspent'] and not pb, (ok, x, pb))
        await pw.pg.context.close()
        # (round 4, 5) a mint past its time limit is named in the message, in your language, with no raw address
        async def hang_swap(route):
            await asyncio.sleep(60)
        await w.use(B); await w.pg.route(f'{B}/v1/swap', hang_swap)
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '100'); await w.click('[data-act=doSendEcash]')
        await w.until("!!(document.querySelector('#sheetErr')||{}).innerText", 40000); er = await w.err()
        await w.pg.unroute(f'{B}/v1/swap'); await w.ev("Nutcade.closeSheet()"); await w.until("Nutcade.S.ops.length===0", 60000)
        bname = await w.ev(f"Nutcade.S.mints.find(m=>m.url==={json.dumps(B)}).name")
        check('(round 4, 5) a mint request past its time limit says "<mint name> didn\'t answer in time. Try again in a moment.", with no raw address', er.startswith(f"{bname} didn't answer in time. Try again in a moment.") and 'http' not in er, er)
        await books(w, 'mint timed out', broken, (A, B, FM))
        # (round 4, 6) Settings has Restore ecash from another phrase, and it opens
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
        vis = await w.ev("(b=>!!b&&b.getClientRects().length>0)(document.querySelector('[data-act=sweepOpen]'))")
        await w.click('[data-act=sweepOpen]'); await w.wait(300); st6 = await w.sheet_text(); await w.ev("Nutcade.closeSheet()")
        check('(round 4, 6) Settings shows "Restore ecash from another phrase", and it opens the restore screen', vis and 'Other 12 words' in st6, (vis, st6[:80]))
        # an interrupted cash-out: the Extra Life is closed when it settles, and the heir's copy is marked ended
        async def cash_start():
            await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=extraOpen]'); await w.wait(300); await w.click('[data-act=extraCash]'); await w.wait(200); await w.click('[data-act=extraCashGo]')
        ok, outs, bal0, new = await interrupted(cash_start)
        await w.wait(1500); x = await w.ev("Nutcade.S.extra")
        check('(round 3, two-step) an interrupted Extra Life cash-out settles after a reload: the sats are in your balance (one line), the Extra Life is closed',
              ok and x is None and await w.bal(B) >= bal0 + 396 and sum(1 for t in new if (t.get('note') or '').startswith('Extra Life cashed out')) == 1, (ok, x and x.get('amount'), await w.bal(B) - bal0, [(t.get('note'), t.get('amount')) for t in new]))
        okh = await hr.until("Nutcade.S.heirlooms.length>0 && Nutcade.S.heirlooms.every(h=>h.state!=='waiting')", 30000)
        check("(round 3, two-step) and the heir's copy is marked ended", okh, await hr.ev("Nutcade.S.heirlooms.map(h=>h.state)"))
        await w.wait(31000); await w.ev("window.dispatchEvent(new Event('online'))"); await w.wait(3000)
        check('(round 3, two-step) nothing later tries to continue it or shows its spent coins (after a background check)',
              await w.ev("!Nutcade.S.extra && Nutcade.S.ops.length===0 && !document.querySelector('[data-act=extraContinue]')"), await w.ev("Nutcade.S.extra"))
        await books(w, 'interrupted cash-out', broken, (A, B, FM))
        # an interrupted heir claim: the heir's NUTCADE gets the sats once, and its heirloom says claimed
        await extra_start('300', 20); await w.until("!!Nutcade.S.extra", 20000)
        await w.ev("Nutcade.S.extra.auto=false; localStorage.setItem('nutcade:extra', JSON.stringify(Nutcade.S.extra))"); await w.ev("Nutcade.closeSheet()")
        await hr.until("Nutcade.S.heirlooms.some(h=>h.state==='waiting'&&h.amount===300)", 30000)
        hb0 = await hr.bal(B); await hr.pg.route(f'{B}/v1/swap', held(8))
        okc = await hr.until("Nutcade.S.ops.some(o=>o.follow&&o.follow.k==='heir')", 120000)
        await hr.wait(1200); await hr.pg.reload(); await hr.wait(800); await hr.pg.unroute(f'{B}/v1/swap')
        ok = await hr.until("Nutcade.S.ops.length===0 && Nutcade.S.heirlooms.some(h=>h.amount===300&&h.state==='claimed')", 60000)
        hb = []
        await books(hr, 'interrupted heir claim', hb, (B,))
        check("(round 3, two-step) an interrupted heir claim settles after a reload: the heir gets the 300 SAT once and the heirloom says claimed",
              okc and ok and 296 <= await hr.bal(B) - hb0 <= 300 and not hb, (okc, ok, await hr.bal(B) - hb0, await hr.ev("Nutcade.S.heirlooms.map(h=>[h.state,h.amount])"), hb))
        await w.until("!Nutcade.S.extra", 60000); await books(w, 'Extra Life passed on', broken, (A, B, FM))
        # an interrupted take-back of a gift whose date passed, and of a bounty nobody won: each is marked back, once
        async def take_back(tx_id):
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(200)
            await w.ev(f"document.querySelector('#txList [data-id=\"{tx_id}\"]').click()"); await w.wait(300); await w.click('#layer [data-act=giftTake]')
        for kind in ('gift', 'bounty'):
            if kind == 'gift':
                okey2 = await w.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return Array.from(CashuLib.getPubKeyFromPrivKey(k),x=>x.toString(16).padStart(2,'0')).join('')})()")
                await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
                await w.ev("const s=document.querySelector('#giftTo'); if (s) { s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})) }")
                await w.fill('#giftKey', okey2); await w.ev("const b=document.querySelector('[data-act=giftDays][data-days=\"1\"]'); b.dataset.days=3/86400; b.click()")
                await w.fill('#amtIn', '222'); await w.click('[data-act=doSendEcash]'); await w.until("Nutcade.S.txs[0].amount===222&&!!Nutcade.S.txs[0].lockUntil", 20000)
            else:
                await w.ev("window.__nutcadeTest={bountySecs:3}"); await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
                await w.ev("Nutcade.startChallenge({game:'flipper', seed:5151, score:900, by:'R3R'})"); await w.wait(300)
                await w.fill('#bountyAmt', '222'); await w.click('[data-act=chalSend]'); await w.until("Nutcade.S.txs[0].amount===222&&!!Nutcade.S.txs[0].bounty", 20000); await w.ev("window.__nutcadeTest=null")
            gid = await w.ev("Nutcade.S.txs[0].id"); await w.ev("Nutcade.closeSheet()"); await w.wait(4500)
            ok, outs, bal0, new = await interrupted(lambda: take_back(gid))
            st = await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(gid)}).status")
            check(f'(round 3, two-step) an interrupted take-back of a {kind} settles after a reload: marked back (not "claimed by them"), 222 SAT in your balance once',
                  ok and st == 'reclaimed' and 218 <= await w.bal(B) - bal0 <= 222 and sum(1 for t in new if t.get('type') == 'in') == 1, (ok, st, await w.bal(B) - bal0, [(t.get('note'), t.get('amount')) for t in new]))
            await books(w, f'interrupted {kind} take-back', broken, (A, B, FM))
        # an interrupted bounty win: the friend's NUTCADE gets the sats once and the bounty says won
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev("Nutcade.startChallenge({game:'flipper', seed:6161, score:800, by:'R3W'})"); await w.wait(300)
        await w.fill('#bountyAmt', '180'); await w.ev("[...document.querySelectorAll('#layer [data-act=chalSend]')].find(b=>b.textContent==='Heir R3').click()")
        await w.until("Nutcade.S.challenges.some(c=>c.seed===6161&&(c.bounties||[]).length===1)", 20000); await w.ev("Nutcade.closeSheet()")
        cw = await w.ev("(c=>({id:c.id, pre:c.bounties[0].pre}))(Nutcade.S.challenges.find(c=>c.seed===6161))")
        okr = await hr.until(f"Nutcade.S.challenges.some(c=>c.dir==='in'&&c.id==={json.dumps(cw['id'][:24])}&&c.bounty)", 30000)
        hb0 = await hr.bal(B); await hr.pg.route(f'{B}/v1/swap', held(8))
        await w.pg.evaluate("""async ([pk, re, pre]) => { const sk = CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32);
            const ev = CashuLib.nip17.wrapEvent(sk, { publicKey: pk }, JSON.stringify({ t: 'nutcade-bounty', re, pre }));
            const ws = new WebSocket('ws://127.0.0.1:3350/relay'); await new Promise(r => { ws.onopen = r; }); ws.send(JSON.stringify(['EVENT', ev])); await new Promise(r => setTimeout(r, 800)); ws.close(); }""", [hr_pub, cw['id'][:24], cw['pre']])
        okc = await hr.until("Nutcade.S.ops.some(o=>o.follow&&o.follow.k==='bounty-won')", 30000)
        await hr.wait(1200); await hr.pg.reload(); await hr.wait(800); await hr.pg.unroute(f'{B}/v1/swap')
        ok = await hr.until(f"Nutcade.S.ops.length===0 && Nutcade.S.challenges.some(c=>c.id==={json.dumps(cw['id'][:24])}&&c.bounty&&c.bounty.state==='won')", 60000)
        hb = []; await books(hr, 'interrupted bounty win', hb, (B,))
        check("(round 3, two-step) an interrupted bounty win settles after a reload: the friend gets the 180 SAT once and the bounty says won",
              okr and okc and ok and 176 <= await hr.bal(B) - hb0 <= 180 and not hb, (okr, okc, ok, await hr.bal(B) - hb0, hb))
        # (round 4, 1-3) the same on the mint that charges a fee to spend ecash
        await w.use(A); await extra_start('500'); await w.until("!!Nutcade.S.extra", 20000); await w.ev("Nutcade.S.extra.auto=false; localStorage.getItem('nutcade:extra') && localStorage.setItem('nutcade:extra', JSON.stringify(Nutcade.S.extra))"); await w.ev("Nutcade.closeSheet()")
        await cont_cases(A, 'fee mint')
        bb = await w.bal(A)
        await w.home(); await w.click('[data-act=extraOpen]'); await w.wait(300); await w.click('[data-act=extraCash]'); await w.wait(200); await w.click('[data-act=extraCashGo]')
        ok2 = await w.until("!Nutcade.S.extra", 30000); await w.ev("Nutcade.closeSheet()")
        check('(round 4, 1-3) fee mint: after its CONTINUEs the Extra Life cashes out into the balance', ok2 and await w.bal(A) >= bb + 495, (ok2, await w.bal(A) - bb))
        await books(w, 'fee-mint Extra Life cashed out', broken, (A, B, FM)); await w.use(B)
        # a plain token reclaimed, interrupted: marked back once, never "claimed" later
        tokR, _ = await w.send_ecash(160, 'r3 reclaim'); rid = await w.ev(f"Nutcade.S.txs.find(t=>t.token==={json.dumps(tokR)}).id")
        async def reclaim_start():
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(200)
            await w.ev(f"document.querySelector('#txList [data-id=\"{rid}\"]').click()"); await w.wait(300); await w.click('#layer [data-act=reclaim]')
        ok, outs, bal0, new = await interrupted(reclaim_start)
        await w.ev("Nutcade.S.prefs.checkSent=true"); await w.wait(1000)
        st = await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(rid)}).status")
        check('(round 3, two-step) an interrupted reclaim settles after a reload: the token is marked reclaimed, its 160 SAT back once', ok and st == 'reclaimed' and await w.bal(B) - bal0 == 160, (ok, st, await w.bal(B) - bal0))
        await books(w, 'interrupted reclaim', broken, (A, B, FM))
        dup['on'] = False
        check('(round 4, 4) after the takeovers, no mint answers "outputs already signed" to this wallet', dup['n'] == 0, dup['n'])
        await hr.pg.context.close()
        # (round 3, item 4) one mint that never answers doesn't stop the background check for the others
        async def hang(route):
            await asyncio.sleep(400)
        await w.use(FM); await w.receive_ln(800); await w.use(A)
        await w.pg.route(f'{FM}/v1/melt/bolt11', hang); await ln_pay_start(FM, invoice(200, B)); await w.wait(1500); await w.ev("Nutcade.closeSheet()")
        await w.pg.route(re.compile(re.escape(FM) + '/v1/.*'), hang)   # from now on FM accepts every request and never answers
        fy = await wallet(b); await fy.create(); await fy.add_mint(B)
        await w.use(B); tokH2, _ = await w.send_ecash(150, 'r3 claimed?'); await fy.receive_token(tokH2); await w.ev("Nutcade.closeSheet()")
        t0 = __import__('time').time()
        ok = await w.until(f"Nutcade.S.txs.some(t=>t.token==={json.dumps(tokH2)}&&t.status==='claimed')", 90000)
        check('(round 3, 4) with one mint hung, the background check still runs for the others ("was my token claimed" answered)', ok, round(__import__('time').time() - t0))
        await w.pg.unroute(re.compile(re.escape(FM) + '/v1/.*')); await w.pg.unroute(f'{FM}/v1/melt/bolt11'); await fy.pg.context.close()
        await w.pg.reload(); await w.wait(1500); await w.until(f"!Nutcade.S.pending.some(p=>p.mint==={json.dumps(FM)})", 150000)
        await books(w, 'hung mint', broken, (A, B, FM))
        # (round 3, item 5) a payment settled from its coins' state (quote check failing then) gets its preimage later
        await w.use(A); invP = invoice(400, B)
        await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(re.compile(re.escape(A) + r'/v1/melt/quote/bolt11/.+'), failing(1, 500))
        e, q = await w.pay_ln(invP); await w.pg.unroute(f'{A}/v1/melt/bolt11'); await w.pg.unroute(re.compile(re.escape(A) + r'/v1/melt/quote/bolt11/.+'))
        p0 = await w.ev(f"(t=>t&&[t.status,!!t.preimage])(Nutcade.S.txs.find(t=>t.request==={json.dumps(invP)}))")
        ok = await w.until(f"!!(Nutcade.S.txs.find(t=>t.request==={json.dumps(invP)})||{{}}).preimage", 90000)
        pv = await w.ev(f"Nutcade.S.txs.find(t=>t.request==={json.dumps(invP)}).preimage"); ph = await w.ev(f"Nutcade.r7.decodeBolt11({json.dumps(invP)}).paymentHash")
        check('(round 3, 5) a payment closed from its coins\' state gets its preimage from the mint later, and it matches the invoice', p0 and p0[0] == 'done' and ok and pv and __import__('hashlib').sha256(bytes.fromhex(pv)).hexdigest() == ph, (p0, pv))
        await books(w, 'preimage later', broken, (A, B, FM))
        # (round 3, go 3) every error message the app can show is translated, in every language
        errs = error_strings(); untr = {}
        for lang in ('de', 'es', 'pt', 'fr'):
            lw = await wallet(b, lang=lang)
            got = await lw.ev(f"{json.dumps(errs)}.map(s=>Nutcade.tr(s))")
            untr[lang] = [e for e, g in zip(errs, got) if g == e]
            await lw.pg.context.close()
        check(f'(round 3, go 3) all {len(errs)} error messages (and the round-3 notes) are translated into de, es, pt and fr', not any(untr.values()), {k: v[:6] for k, v in untr.items() if v})
        # (round 2, item 2) a scoped app asking to pay an invoice the user already paid learns nothing and pays nothing
        mine_inv = invoice(321, B); e, q = await w.pay_ln(mine_inv); n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uri, 'pay_invoice', {'invoice': mine_inv})
        check('(round 2, 2 + go 4) nwc: a scoped app asking to pay an invoice it didn\'t pay gets the answer a payment that fails gets (PAYMENT_FAILED, "Nothing left the wallet"), no sign this wallet paid it, nothing paid again',
              r['answer'] and r['answer']['result'] is None and r['answer']['error']['code'] == 'PAYMENT_FAILED' and r['answer']['error']['message'] == 'The payment failed. Nothing left the wallet.' and 'preimage' not in json.dumps(r['answer']) and await w.ev("Nutcade.S.txs.length") == n0, r.get('answer'))
        # (round 2, item 3) an Extra Life copy claimed by several background checks at once: claimed once, never "ended"
        hb = await w.bal(B)
        await w.ev(f"Nutcade.S.heirlooms.unshift({{from:'ff',name:'Kim',token:{json.dumps(tokH)},amount:50,mint:{json.dumps(B)},until:Date.now()-60000,state:'waiting',at:Date.now()}}); for(let i=0;i<3;i++) window.dispatchEvent(new Event('online'))")
        await w.until("Nutcade.S.heirlooms[0].state!=='waiting'", 75000); await w.wait(3000)
        check('(round 2, 3) an heirloom claimed by overlapping background checks ends up claimed (not "ended"), its sats arrive once', await w.ev("Nutcade.S.heirlooms[0].state") == 'claimed' and await w.bal(B) == hb + 50, (await w.ev("Nutcade.S.heirlooms[0].state"), await w.bal(B) - hb))
        await books(w, 'heirloom claimed once', broken)
        # a total budget, two payments racing for it: one goes through
        uri2 = await make_nwc(w, 'Racer', 'total', 500); await w.ev("Nutcade.closeSheet()")
        i1, i2 = invoice(300, B), invoice(300, B)
        a1 = await asyncio.to_thread(mock, '/test/nwc', {'uri': uri2, 'method': 'pay_invoice', 'params': {'invoice': i1}, 'nowait': True})
        a2 = await asyncio.to_thread(mock, '/test/nwc', {'uri': uri2, 'method': 'pay_invoice', 'params': {'invoice': i2}, 'nowait': True})
        x1 = (await asyncio.to_thread(mock, '/test/nwc/answer', {'uri': uri2, 'id': a1['id'], 'wait': 20}))['answer']
        x2 = (await asyncio.to_thread(mock, '/test/nwc/answer', {'uri': uri2, 'id': a2['id'], 'wait': 20}))['answer']
        codes = sorted([(x or {}).get('error') and x['error']['code'] or 'OK' for x in (x1, x2)])
        check('nwc: two payments sent at once against a 500 SAT total budget: one pays, one is QUOTA_EXCEEDED', codes == ['OK', 'QUOTA_EXCEEDED'], (x1, x2))
        await books(w, 'nwc race', broken)
        # a payment that fails at the mint: said so, marked, and the books still add up
        await w.use(FM); await w.receive_ln(1500); n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uri2, 'pay_invoice', {'invoice': invoice(100, B)}, wait=25)
        ft = await w.ev("Nutcade.S.txs.find(t=>t.nwc&&t.mint===%s)" % json.dumps(FM))
        check('nwc: a payment that fails answers PAYMENT_FAILED, says what it cost, and the failed line is marked with the app', r['answer'] and r['answer']['error'] and r['answer']['error']['code'] == 'PAYMENT_FAILED' and 'Nothing left' in r['answer']['error']['message'] and ft and ft['status'] == 'failed' and ft['nwcName'] == 'Racer', (r.get('answer'), ft and ft['status']))
        await books(w, 'nwc failed', broken, (A, B, FM)); await w.use(A)
        # revoke: no more answers, right away
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        await w.ev("[...document.querySelectorAll('#set-nwc [data-act=nwcRevokeAsk]')].pop().click()"); await w.wait(200)
        rv = await w.sheet_text(); await w.click('[data-act=nwcRevoke]'); await w.wait(100)
        r = await nwc(w, uri2, 'get_info', wait=4)
        check('nwc: revoking asks first, then the app gets no answer at all', 'stops working with this wallet right away' in rv and r['answer'] is None and 'Racer' not in await w.ev("document.querySelector('#set-nwc').innerText"), rv[:120])
        # PIN: the connection's keys live in the encrypted vault and keep working after unlocking
        await set_pin(w)
        st = await w.ev("JSON.stringify(Object.assign({}, localStorage))")
        sk = await w.ev("Nutcade.S.nwc[0].sk")
        check('nwc: with a PIN, connection keys are only inside the encrypted vault', 'nutcade:nwc' not in await w.ev("Object.keys(localStorage)") and sk not in st, [k for k in await w.ev("Object.keys(localStorage)") if 'nwc' in k])
        await w.pg.reload(); await w.wait(800)
        r = await nwc(w, uri, 'get_info', wait=3)
        check('nwc: while the wallet is locked, nothing is answered', r['answer'] is None)
        lk = await asyncio.to_thread(mock, '/test/nwc', {'uri': uri, 'method': 'pay_invoice', 'params': {'invoice': invoice(55, B)}, 'nowait': True})
        await unlock(w); await w.wait(1500)
        x = (await asyncio.to_thread(mock, '/test/nwc/answer', {'uri': uri, 'id': lk['id'], 'wait': 15}))['answer']
        check('(fix 6) nwc: a payment sent while the wallet was locked is refused with an error on unlock, never paid', x and x['error'] and x['error']['code'] == 'OTHER' and 'locked' in x['error']['message'] and not await w.ev("Nutcade.S.txs.some(t=>t.amount===55&&t.type==='out')"), x)
        r = await nwc(w, uri, 'get_info', wait=8)
        check('nwc: after unlocking, the connection answers again', r['answer'] and r['answer']['result']['alias'] == 'NUTCADE', r.get('answer'))
        check('round 7 money: after every new path (vouchers, blocked mints, zaps, NWC payments, budgets, failures) the history adds up to the balance', not broken, broken)
        check('round 7: no page errors', not w.errs, w.errs[:5])
        await w.pg.context.close()

        await tour(b, pa, pb, pc, pd)
        await b.close()
    n = len(results); ok = sum(1 for r in results if r[1])
    print(f'SUMMARY {ok}/{n} passed')

if __name__ == '__main__':
    asyncio.run(main())
