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
        await h.create(); await h.add_mint(B); await h.add_mint(A); await h.use(A); await h.receive_ln(5000)
        shot_dir = SHOTS if SHOTS and lang in ('en', 'de') else ''
        over, n, notgold = [], [0], []
        async def snap(name):
            await h.ev("(e=>e&&e.remove())(document.getElementById('fxLayer'))")   # no coin shower over the screenshot
            o = await h.ev(OVER_JS)
            if o: over.append((name, o))
            ng = await h.ev("[...document.querySelectorAll('#layer .btn.solid')].filter(b=>!b.classList.contains('gold')&&!b.classList.contains('red')&&b.id!=='payBtn').map(b=>b.innerText)")
            if ng and name not in ('block_ln_refused',): notgold.append((name, ng))   # (that one is the existing Receive sheet)
            if shot_dir:
                n[0] += 1; await h.pg.screenshot(path=os.path.join(shot_dir, f'{lang}_{n[0]:02d}_{name}.png'))
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
        mc = await w.ev(f"Nutcade.r7.meltCost({json.dumps(A)}, 600, 0).mintFee")
        check('(fix 2) nwc: the payment is tagged with its app before it goes out, and still after a reload mid-payment', pre_tag and pre_tag[0] and t6.get('nwc') == pre_tag[0], (pre_tag, t6.get('nwc')))
        check('(fix 2) after a reload mid-payment, the change comes back: the fee recorded is the real one, not the whole reserve', t6['status'] == 'done' and t6['fee'] <= 1 + mc, (t6['fee'], mc))
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
        check('(fix 2) a payment whose answer was lost still records the real fee (its change restored), not the whole reserve', t7['amount'] == 700 and t7['status'] == 'done' and t7['fee'] <= 1 + mc and not e, (t7['status'], t7['fee'], e))
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
            await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(f'{A}{path}', failing(1, status))
            e, q = await w.pay_ln(invoice(800, B))
            await w.pg.unroute(f'{A}/v1/melt/bolt11')
            st = await w.ev(PEND)
            check(f'(round 2, 1) {what} during change recovery: the payment is done, its change still pending, the record kept for a retry', st[0] == 'done' and st[2] and st[3] and st[1] >= 8, st)
            await w.pg.unroute(f'{A}{path}')
            ok, txt = await try_now(); st2 = await w.ev(PEND)
            check(f'(round 2, 1) {what}: the payment says its change is still coming, and Try now recovers it: fee is the real one, record closed', ok and 'hasn\'t come back from the mint yet' in txt and not st2[2] and not st2[3] and st2[1] <= 1 + mc, (st2, txt[:160]))
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
        await w.pg.unroute(f'{A}/v1/restore'); await w.pg.reload(); await w.wait(800)
        await w.until("!Nutcade.S.txs[0].changePending", 30000); st = await w.ev(PEND)
        check('(round 2, 1) after the reloads, the next start recovers the change: the real fee, record closed', not st[2] and not st[3] and st[1] <= 1 + mc, st)
        await books(w, 'change recovery through reloads', broken)
        # Find lost ecash credits found change to its payment instead of adding a "Recovered" line
        await w.pg.route(f'{A}/v1/melt/bolt11', drop_answer); await w.pg.route(f'{A}/v1/restore', failing(1000, 500))
        e, q = await w.pay_ln(invoice(600, B)); await w.pg.unroute(f'{A}/v1/melt/bolt11'); await w.pg.unroute(f'{A}/v1/restore')
        RECA = "Nutcade.S.txs.filter(t=>t.note==='Recovered with recovery phrase'&&t.mint===" + json.dumps(A) + ").length"
        nrec = await w.ev(RECA); tid = await w.ev("Nutcade.S.txs[0].id")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=findLost]'); await w.until(f"!(Nutcade.S.txs.find(t=>t.id==={json.dumps(tid)})||{{}}).changePending", 60000); await w.wait(500)
        t9 = await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(tid)})")
        check('(round 2, 1) Find lost ecash credits the change to its payment (real fee), with no separate Recovered line', not t9.get('changePending') and t9['fee'] <= 1 + mc and await w.ev(RECA) == nrec, (t9['fee'], t9.get('changePending')))
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
        # (round 2, item 2) a scoped app asking to pay an invoice the user already paid learns nothing and pays nothing
        mine_inv = invoice(321, B); e, q = await w.pay_ln(mine_inv); n0 = await w.ev("Nutcade.S.txs.length")
        r = await nwc(w, uri, 'pay_invoice', {'invoice': mine_inv})
        check('(round 2, 2) nwc: a scoped app asking about an invoice it didn\'t pay gets a refusal (RESTRICTED), no preimage or fee, nothing paid', r['answer'] and r['answer']['result'] is None and r['answer']['error']['code'] == 'RESTRICTED' and 'preimage' not in json.dumps(r['answer']) and await w.ev("Nutcade.S.txs.length") == n0, r.get('answer'))
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
