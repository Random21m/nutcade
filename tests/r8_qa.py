"""Round 8 (1.13): the wallet-wide spending limit, the duress PIN, NUT-06 request-size limits (a mint that takes at
most 3 items per request), phones held sideways, the problem-report form, pinned GitHub Actions, and the 1.12.1 recheck's
polish. Uses the local mints (3338 fee, 3339 no fee, 3342 no fee with max_array_length 3) and mock_nostr.py.

The spending-limit grid: every way sats leave (Lightning, ecash, payment request, gift, bounty, Extra Life, move
between mints, Wallet Connect, zap, Lightning address, contact over Nostr, multi-mint, offline, a Numo-style checkout)
x under / exactly at / over / over-then-PIN, on a fee and a no-fee mint, with and without a PIN, two taps and two
tabs at once, after a reload and across the 24-hour window (clock moved forward)."""
import asyncio, json, os, re, time, urllib.request
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, A, B, URL, invoice, outside_net
from r7_qa import mock, forward, LEDGER, OVER_JS, nwc, make_nwc, zap_to, books

C = 'http://127.0.0.1:3342'   # max_array_length 3, no fee
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PIN, DPIN = '135791', '246802'
LANGS = ['en', 'es', 'pt', 'de', 'fr']


async def wallet(b, vw=375, vh=667, lang='en', mobile=True, init=None, ctx=None, ua=None):
    if ctx is None:
        kw = dict(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile, accept_downloads=True)
        if ua: kw['user_agent'] = ua
        ctx = await b.new_context(**kw)
        prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
        if init: await ctx.add_init_script(init)
        await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
        await ctx.route('https://lnurl.test/**', forward)
    pg = await ctx.new_page(); w = W(pg, 'r8')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'lnurl.test' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def pad(w, pin, root='[data-pinpad]'):
    for k in pin: await w.click(f'{root} [data-k="{k}"]')
    await w.click(f'{root} [data-k=ok]')


async def set_pin(w, pin=PIN):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=pinSet]'); await w.wait(200)
    await pad(w, pin); await w.wait(300); await pad(w, pin)
    await w.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await w.wait(500); await w.ev("Nutcade.closeSheet()")


async def unlock(w, pin=PIN, wait=True):
    await w.until("!!document.querySelector('[data-pinpad]')", 8000)
    t0 = time.time(); await pad(w, pin)
    if wait: await w.until("Nutcade.vault.open", 20000)
    else: await w.until("/Wrong PIN|Wait/.test((document.querySelector('#pinErr')||{}).innerText||'')", 20000)
    dt = time.time() - t0; await w.wait(800); return dt


async def set_lang(w, lang):
    await settings(w)
    await w.ev(f"(()=>{{const s=document.querySelector('#p_lang'); s.value={json.dumps(lang)}; s.dispatchEvent(new Event('change',{{bubbles:true}}))}})()"); await w.wait(300)


async def settings(w):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)


async def set_limits(w, per, day, pin=PIN):
    """Settings -> Security -> Spending limit; returns (error text, toast)"""
    await settings(w); await w.click('[data-act=limOpen]'); await w.until("!!document.querySelector('#limDay')", 5000)
    await w.ev(f"(()=>{{for(const [id,v] of [['limPer',{json.dumps(per)}],['limDay',{json.dumps(day)}]]){{const e=document.querySelector('#'+id);e.value=v;e.dispatchEvent(new Event('input',{{bubbles:true}}))}}}})()")
    await w.click('[data-act=limSave]'); await w.wait(400)
    if pin and await w.ev("!!document.querySelector('#layer [data-pinpad]')"):
        await pad(w, pin, '#layer [data-pinpad]'); await w.until("!document.querySelector('#layer [data-pinpad]') || /wrong/i.test((document.querySelector('#pinErr')||{}).innerText||'')", 20000); await w.wait(300)
    e = await w.err(); t = await w.toast(); pinerr = await w.ev("(document.querySelector('#pinErr')||{}).innerText||''")
    await w.ev("Nutcade.closeSheet()")
    return e or pinerr, t


async def outcome(w, n0, ms=30000):
    """after a spend was started: ('limit', text) when the over-the-limit screen shows, ('err', text) for an error,
    ('ok', tx) when a new outgoing line is in the history"""
    js = f"""(()=>{{const L=document.querySelector('#limitLayer'); if(L) return ['limit', L.innerText];
      const e=(document.querySelector('#sheetErr')||{{}}).innerText||''; if(e.trim()) return ['err', e];
      const n=Nutcade.S.txs.length-{n0}; if(n>0){{const t=Nutcade.S.txs.slice(0,n).find(t=>t.type==='out'&&t.status!=='failed'&&t.method!=='fee'); if(t) return ['ok', t];}}
      return null}})()"""
    for _ in range(ms // 250):
        r = await w.ev(js)
        if r: return r
        await w.wait(250)
    return ['timeout', await w.sheet_text()]


async def settled(w):
    """a payment that went through has finished on screen (its done screen shown) before the next step starts"""
    await w.until("Nutcade.S.pending.length===0 && !document.querySelector('#layer .spinner')", 30000); await w.wait(600); await w.ev("Nutcade.closeSheet()"); await w.wait(200)


# everything in plain storage except the vault record itself (with a PIN: only the device's own settings)
PLAIN_JS = "Object.keys(localStorage).filter(k=>k!=='nutcade:vault').map(k=>k+'='+localStorage.getItem(k)).join('\\n')"
OKKEY_JS = "(()=>{const k=[...document.querySelectorAll('[data-pinpad] [data-k=ok]')].pop(); if(!k) return false; const r=k.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight})()"
NOALLOW = "localStorage.setItem('nutcade:pinchg','[]')"   # (a test resets the device's PIN-change allowance between steps)


async def layer_pin(w, pin=PIN):
    await pad(w, pin, '#limitLayer [data-pinpad]')
    await w.until("!document.querySelector('#limitLayer')", 20000)


async def spend_estimate(w, start):
    """the app's own number for a spend (amount + fees, at most), read from the over-the-limit screen with a 1 SAT
    per-payment limit; the screen is then dismissed"""
    n0 = await w.ev("Nutcade.S.txs.length"); await start(); r = await outcome(w, n0)
    txt = r[1] if r[0] in ('limit', 'err') else ''
    m = re.search(r'This payment is ([\d,]+) SAT', txt or '')
    await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); document.querySelector('#limitLayer')?.remove(); Nutcade.closeSheet()"); await w.wait(200)
    return int(m.group(1).replace(',', '')) if m else None, r


# ---------- the ways sats leave (each starts the spend in the UI and returns; outcome() reads what happened) ----------
def ways(w, mint, fr=None, ctx=None):
    async def ln(a):
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        # (another mint's invoice: the test mints mark their own invoices paid after 0.5 s)
        await w.fill('#destIn', invoice(a, A if mint == B else B)); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
        if await w.ev("!!document.querySelector('#payBtn')"): await w.wait(300); await w.click('#payBtn')
    async def ecash(a):
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', str(a)); await w.click('[data-act=doSendEcash]')
    async def gift(a):
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
        await w.ev("const s=document.querySelector('#giftTo'); if (s) { s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})) }")
        k = await w.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return Array.from(CashuLib.getPubKeyFromPrivKey(k),x=>x.toString(16).padStart(2,'0')).join('')})()")
        await w.fill('#giftKey', k); await w.fill('#amtIn', str(a)); await w.click('[data-act=doSendEcash]')
    async def reqpay(a):
        enc = await fr.ev(f"Nutcade.r8.newRequest({a}, 'Numo checkout').encoded")
        await w.home(); await w.ev(f"Nutcade.handleScan({json.dumps(enc)})"); await w.wait(300); await w.click('[data-act=payReq]')
    async def bounty(a):
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev(f"Nutcade.startChallenge({{game:'flipper', seed:{int(time.time()*1000) % 100000}, score:1200, by:'R8B'}})"); await w.wait(300)
        await w.fill('#bountyAmt', str(a)); await w.click('[data-act=chalSend]')
    async def extra(a):
        if await w.ev("!!Nutcade.S.extra"):
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=extraOpen]'); await w.wait(200)
            await w.click('[data-act=extraCash]'); await w.wait(150); await w.click('[data-act=extraCashGo]'); await w.until("!Nutcade.S.extra", 20000); await w.wait(300)
        await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=extraOpen]'); await w.until("!!document.querySelector('#xlTo')", 5000); await w.wait(150)
        await w.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Heir R8').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
        await w.fill('#amtIn', str(a)); await w.click('[data-act=extraStart]')
    async def move(a):
        await w.use(mint); await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200); await w.click('#app [data-act=moveOpen]'); await w.wait(250)
        other = A if mint == B else B
        await w.ev(f"(()=>{{const f=document.querySelector('#mvFrom'), t=document.querySelector('#mvTo'); if(f){{f.value={json.dumps(mint)}; f.dispatchEvent(new Event('change',{{bubbles:true}}))}} if(t){{t.value={json.dumps(other)}; t.dispatchEvent(new Event('change',{{bubbles:true}}))}}}})()")
        await w.fill('#amtIn', str(a)); await w.click('[data-act=moveQuote]'); await w.until("!!document.querySelector('#mvGo') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
        if await w.ev("!!document.querySelector('#mvGo')"): await w.wait(300); await w.click('#mvGo')
    async def zap(a):
        mock('/test/lnurlp', {'name': 'zed', 'zap': True}); p = mock('/test/profile', {'name': 'zed', 'lud16': 'zed@lnurl.test'})
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#destIn', p['npub']); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('[data-act=zapQuote]')", 12000)
        await w.fill('#amtIn', str(a)); await w.click('[data-act=zapQuote]'); await w.until("!!document.querySelector('#payBtn')", 12000); await w.wait(300); await w.click('#payBtn')
    async def lnaddr(a):
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
        mock('/test/lnurlp', {'name': 'payee8', 'zap': False})
        await w.fill('#destIn', 'payee8@lnurl.test'); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#amtIn') && !!document.querySelector('[data-act=lnurlQuote], [data-act=zapQuote]')", 12000)
        await w.fill('#amtIn', str(a)); await w.ev("document.querySelector('[data-act=lnurlQuote], [data-act=zapQuote]').click()")
        await w.until("!!document.querySelector('#payBtn') || !!(document.querySelector('#sheetErr')||{}).innerText", 12000)
        if await w.ev("!!document.querySelector('#payBtn')"): await w.wait(300); await w.click('#payBtn')
    async def contact(a):
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=contactsOpen]'); await w.wait(150)
        await w.ev("document.querySelector('[data-act=payContact]').click()"); await w.until("!!document.querySelector('[data-act=contactEcash]')", 5000)
        await w.fill('#amtIn', str(a)); await w.click('[data-act=contactEcash]')
    async def hunt(a):
        await w.home(); await w.ev("document.querySelector('[data-act=huntNew]').click()"); await w.until("!!document.querySelector('[data-act=huntCreate]')", 5000)
        await w.fill('#amtIn', str(a)); await w.click('[data-act=huntCreate]')
    async def split(a):   # a friend's bill split (a payment request for each share), paid here
        await fr.home(); await fr.click('[data-act=splitOpen]'); await fr.wait(150)
        await fr.fill('#amtIn', str(a * 2)); await fr.fill('#splitN', '2'); await fr.fill('#memoIn', 'Pizza night'); await fr.click('[data-act=splitCreate]'); await fr.wait(400)
        enc = await fr.ev("Nutcade.S.requests[0].encoded"); await fr.ev("Nutcade.closeSheet()")
        await w.home(); await w.ev(f"Nutcade.handleScan({json.dumps(enc)})"); await w.wait(300); await w.click('[data-act=payReq]')
    return {'ln': ln, 'ecash': ecash, 'gift': gift, 'reqpay': reqpay, 'bounty': bounty, 'extra': extra, 'move': move, 'zap': zap, 'lnaddr': lnaddr, 'contact': contact, 'hunt': hunt, 'split': split}


async def section(name, fn):
    only = [x for x in os.environ.get('R8_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e:
        check(f'{name}: ran to the end', False, repr(e)[:300])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        broken = []

        # ======================= files: the manifest, the issue form, pinned actions =======================
        async def files():
            man = json.load(open(os.path.join(ROOT, 'public', 'manifest.webmanifest')))
            check('landscape: the manifest does not lock the orientation (you choose)', 'orientation' not in man, man.get('orientation'))
            bug = os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', 'bug.yml'); cfg = os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', 'config.yml')
            t = open(bug).read() if os.path.exists(bug) else ''
            check('report a problem: .github/ISSUE_TEMPLATE/bug.yml and config.yml exist', bool(t) and os.path.exists(cfg))
            for k in ('What happened', 'Steps', 'Device', 'NUTCADE version'):
                check(f'report a problem: the form asks for "{k}"', k.lower() in t.lower())
            check('report a problem: the form warns never to paste the 12 words, the PIN or tokens', all(x in t.lower() for x in ('12 words', 'pin', 'token')) and 'never' in t.lower())
            check('report a problem: no tracking (no links to analytics, no images)', not re.search(r'analytics|track|pixel|\.png|\.gif|utm_', t, re.I))
            rd = open(os.path.join(ROOT, 'README.md')).read()
            check('report a problem: README links the form', 'issues/new?template=bug.yml' in rd or 'issues/new/choose' in rd)
            wf = open(os.path.join(ROOT, '.github', 'workflows', 'test-and-deploy.yml')).read()
            uses = re.findall(r'uses:\s*(\S+)(.*)', wf)
            want = {'actions/checkout': 'v4', 'actions/upload-artifact': 'v4', 'actions/configure-pages': 'v5', 'actions/upload-pages-artifact': 'v3', 'actions/deploy-pages': 'v4'}
            for name, ver in want.items():
                u = [x for x in uses if x[0].startswith(name + '@')]
                check(f'pinned actions: {name} is pinned to a full commit SHA with {ver} in a comment', bool(u) and all(re.fullmatch(name + r'@[0-9a-f]{40}', x[0]) and re.search(r'#\s*' + ver + r'\b', x[1]) for x in u), u)
            check('pinned actions: every action in the workflow is pinned to a SHA', uses and all(re.search(r'@[0-9a-f]{40}$', x[0]) for x in uses), uses)
        await section('files', files)

        # ======================= spending limit: settings, inputs, vault =======================
        w = await wallet(b); await w.create(); await w.add_mint(A); await w.add_mint(B)
        fr = await wallet(b); await fr.create(); await fr.add_mint(A); await fr.add_mint(B)
        await w.use(A); await w.receive_ln(30000); await w.use(B); await w.receive_ln(30000); await w.use(A)
        fr_addr = await fr.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")
        await settings(w); await w.click('[data-act=contactsOpen]'); await w.wait(150)
        await w.click('[data-act=contactEdit]'); await w.wait(150); await w.fill('#cName', 'Heir R8'); await w.fill('#cNostr', fr_addr); await w.click('[data-act=contactSave]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")

        async def inputs():
            # no PIN: limits are kept in plain storage, and survive a reload
            for v, why in [('-5', 'negative'), ('0', 'zero'), ('1.5', 'decimal'), ('1e3', 'exponent'), ('99999999999999999999', 'huge'), ('abc', 'junk'), ('12abc', 'junk after a number'), ('2,5', 'a comma not grouping thousands')]:
                e, _ = await set_limits(w, '', v)
                check(f'limit input: {why} ({v!r}) is refused with a message and nothing is saved', bool(e) and 'undefined' not in e and not await w.ev("!!(Nutcade.S.limits&&Nutcade.S.limits.day)"), e)
            await settings(w); await w.click('[data-act=limOpen]'); await w.wait(200)
            hint = await w.sheet_text()
            await w.ev("const e=document.querySelector('#limPer'); e.value='500'; e.dispatchEvent(new Event('input',{bubbles:true}))"); await w.click('[data-act=limSave]'); await w.wait(300)
            e6 = await w.err(); await w.ev("Nutcade.closeSheet()")
            check('limit input: without a PIN, a per-payment amount is refused with a message (never dropped with "off")', 'PIN first' in e6 and 'Set a PIN first to use this one' in hint and not await w.ev("!!(Nutcade.S.limits&&Nutcade.S.limits.per)"), (e6, hint[-120:]))
            check('limit input: without a PIN the per-payment box is off (it needs a PIN to ask for)', await w.ev("(()=>{Nutcade.closeSheet(); document.querySelector('[data-act=limOpen]').click(); const d=document.querySelector('#limPer').disabled; Nutcade.closeSheet(); return d})()"))
            e, t = await set_limits(w, '', '2,500')
            check("limit input: '2,500' in English is 2,500 SAT", not e and await w.ev("Nutcade.S.limits.day===2500 && !Nutcade.S.limits.per"), (e, await w.ev("Nutcade.S.limits")))
            e, t = await set_limits(w, '', '  ')
            check('limit input: spaces only = off', not e and await w.ev("!Nutcade.S.limits || !Nutcade.S.limits.day"), (e, await w.ev("Nutcade.S.limits")))
            e, t = await set_limits(w, '', '')
            check('limit input: empty = off', not e and await w.ev("!Nutcade.S.limits || (!Nutcade.S.limits.per && !Nutcade.S.limits.day)"), (e, t))
            for lang, txt in [('de', '2.500'), ('fr', '2 500'), ('es', '2.500'), ('pt', '2.500')]:
                await set_lang(w, lang)
                e, t = await set_limits(w, '', txt)
                check(f"limit input: {txt!r} in {lang} is 2,500 SAT", not e and await w.ev("Nutcade.S.limits.day===2500"), (e, await w.ev("Nutcade.S.limits")))
                await settings(w); st = await w.ev("(document.querySelector('#set-security')||{}).innerText||''")
                check(f'limit settings in {lang}: the limit is shown the {lang} way', ('2.500' if lang != 'fr' else '2 500') in st or ('2 500' in st and lang == 'fr'), st[-200:])
            await set_lang(w, 'en')
            await w.pg.reload(); await w.wait(900)
            check('limit: survives a reload', await w.ev("Nutcade.S.limits && Nutcade.S.limits.day===2500"), await w.ev("Nutcade.S.limits"))
            e, t = await set_limits(w, '', ''); check('limit: turned off again', not e)
        await section('limit inputs', inputs)

        async def grid_core():
            for mint, tag in [(A, 'fee mint'), (B, 'no-fee mint')]:
                await w.use(mint); wy = ways(w, mint, fr)
                for way, amt in [('ecash', 300), ('ln', 300)]:
                    start = lambda: wy[way](amt)
                    await set_limits(w, '1', '')
                    est, r = await spend_estimate(w, start)
                    check(f'{way} {tag}: over the per-payment limit shows the over-the-limit screen with the amount and fees', est and est >= amt and r[0] == 'limit' and 'SAT' in r[1], r)
                    if not est: continue
                    # exactly at: passes with no PIN asked
                    await set_limits(w, str(est), '')
                    n0 = await w.ev("Nutcade.S.txs.length"); bal0 = await w.bal(mint); await start(); r = await outcome(w, n0); await w.wait(800)
                    await settled(w); cost = bal0 - await w.bal(mint)
                    check(f'{way} {tag}: exactly at the per-payment limit ({est} SAT with fees) goes through without asking', r[0] == 'ok' and cost <= est, (r[0], cost, est))
                    await w.ev("Nutcade.closeSheet()")
                    # one SAT over: asks, PIN once lets it through
                    await set_limits(w, str(est - 1), '')
                    n0 = await w.ev("Nutcade.S.txs.length"); bal0 = await w.bal(mint); await start(); r = await outcome(w, n0)
                    nothing = await w.bal(mint) == bal0 and not await w.ev(f"Nutcade.S.ops.length || Nutcade.S.pending.some(p=>p.mint==={json.dumps(mint)})")
                    check(f'{way} {tag}: one SAT over the per-payment limit is held: nothing leaves, the screen says the amount', r[0] == 'limit' and f'{est:,}' in r[1] and nothing, (r, nothing))
                    if r[0] == 'limit':
                        await layer_pin(w); r2 = await outcome(w, n0); await settled(w)
                        check(f'{way} {tag}: the PIN lets it through once', r2[0] == 'ok', r2)
                        await w.ev("Nutcade.closeSheet()"); n1 = await w.ev("Nutcade.S.txs.length"); await start(); r3 = await outcome(w, n1)
                        check(f'{way} {tag}: the next one over asks again (the PIN was for one payment)', r3[0] == 'limit', r3)
                        b1 = await w.bal(mint); await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click()"); await w.wait(400)
                        check(f'{way} {tag}: Cancel on the over-the-limit screen leaves everything as it was', not await w.ev("!!document.querySelector('#limitLayer')") and await w.ev("Nutcade.S.txs.length") == n1 and await w.bal(mint) == b1)
                    await w.ev("Nutcade.closeSheet()")
                await books(w, f'core grid {tag}', broken, (A, B))
            await set_limits(w, '', '')
        await set_pin(w)
        await section('core grid (PIN on)', grid_core)

        async def daily():
            # the daily limit: rolling 24 hours, fees count, reload, the window moving on, two taps, two tabs
            await w.use(B)
            used0 = await w.ev("Nutcade.r8.spentDay()")
            e, _ = await set_limits(w, '', str(used0 + 1000), PIN)
            check('daily: with a PIN, changing the limit asks for the PIN', not e and await w.ev(f"Nutcade.S.limits.day==={used0 + 1000}"), e)
            check('daily: with a PIN, the limit is inside the vault, not in plain storage', await w.ev("localStorage.getItem('nutcade:limits')===null && !Object.keys(localStorage).some(k=>/limit/i.test(k))"))
            wy = ways(w, B, fr)
            n0 = await w.ev("Nutcade.S.txs.length"); await wy['ecash'](600); r = await outcome(w, n0); await w.ev("Nutcade.closeSheet()")
            check('daily: 600 of 1,000 goes through', r[0] == 'ok', r)
            n0 = await w.ev("Nutcade.S.txs.length"); await wy['ecash'](500); r = await outcome(w, n0)
            check('daily: the next 500 is held, the screen says how much is left and when it frees up', r[0] == 'limit' and '400' in r[1] and re.search(r'\d{1,2}:\d{2}|tomorrow|in \d+ h', r[1], re.I), r)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            n0 = await w.ev("Nutcade.S.txs.length"); await wy['ecash'](400); r = await outcome(w, n0); await w.ev("Nutcade.closeSheet()")
            check('daily: exactly the 400 left goes through', r[0] == 'ok', r)
            await w.pg.reload(); await w.wait(700); await unlock(w)
            n0 = await w.ev("Nutcade.S.txs.length"); await wy['ecash'](1); r = await outcome(w, n0)
            check('daily: after a reload the day is still used up (1 SAT more is held)', r[0] == 'limit', r)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            # fees count: on the fee mint a payment that fits only without its fee is held
            await w.use(A); e, _ = await set_limits(w, '', str(await w.ev("Nutcade.r8.spentDay()") + 300), PIN)
            n0 = await w.ev("Nutcade.S.txs.length"); await ways(w, A)['ecash'](300); r = await outcome(w, n0)
            check('daily: fees count (300 SAT with a 300 SAT day left on a fee mint is held)', r[0] == 'limit', r)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            # the window moves on: 24 hours later the same payment goes through
            await w.ev("(()=>{const real=Date.now.bind(Date); Date.now=()=>real()+86400e3+60e3})()")
            n0 = await w.ev("Nutcade.S.txs.length"); await ways(w, A)['ecash'](300); r = await outcome(w, n0); await w.ev("Nutcade.closeSheet()")
            check('daily: 24 hours later (clock moved on) the day is free again', r[0] == 'ok', r)
            await w.pg.reload(); await w.wait(700); await unlock(w)
            # two taps at once (two payments started together, on two mints): only what fits goes through
            await w.ev("Nutcade.closeSheet()")
            e, _ = await set_limits(w, '', str(await w.ev("Nutcade.r8.spentDay()") + 1000), PIN)
            res = await w.ev("""(async()=>{const r=await Promise.allSettled([Nutcade.r8.sendEcash(600,'tap 1',null,'http://127.0.0.1:3339'), Nutcade.r8.sendEcash(600,'tap 2',null,'http://127.0.0.1:3338'), Nutcade.r8.sendEcash(600,'tap 3',null,'http://127.0.0.1:3339')]);
              return r.map(x=>x.status==='fulfilled'?'ok':(x.reason&&x.reason.limit?'limit':String(x.reason&&x.reason.message)))})()""")
            check('two taps: three 600 SAT payments started at once under a 1,000 SAT day: exactly one goes through', sorted(res) == ['limit', 'limit', 'ok'], res)
            # two tabs: a payment in flight in one tab counts in the other
            await w.use(B); left = await w.ev("Nutcade.r8.limitLeft()")
            held = {'n': 0}
            async def hold_melt(route):
                held['n'] += 1; await asyncio.sleep(6)
                try: await route.continue_()
                except Exception: pass
            e, _ = await set_limits(w, '', str(await w.ev("Nutcade.r8.spentDay()") + 1000), PIN)
            await w.pg.route(f'{B}/v1/melt/bolt11', hold_melt)
            n0 = await w.ev("Nutcade.S.txs.length"); await ways(w, B)['ln'](700); await w.until("Nutcade.S.pending.length>0", 10000)
            w2 = await wallet(b, ctx=w.pg.context); await w2.wait(500)
            if await w2.ev("!!document.querySelector('[data-act=takeover]')"): await w2.click('[data-act=takeover]'); await w2.wait(800)
            if await w2.ev("!!document.querySelector('[data-pinpad]')"): await unlock(w2)
            n2 = await w2.ev("Nutcade.S.txs.length"); await w2.use(B); await ways(w2, B)['ecash'](400); r = await outcome(w2, n2)
            check('two tabs: a payment still in flight in one tab counts in the other (700 in flight + 400 > 1,000 is held)', r[0] == 'limit', r)
            await w2.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            await w.pg.unroute(f'{B}/v1/melt/bolt11'); await w2.until("Nutcade.S.pending.length===0", 40000)
            await books(w2, 'daily two tabs', broken, (A, B))
            e, _ = await set_limits(w2, '', '', PIN)
            check('daily: removing the limit needs the PIN too, and works', not e and await w2.ev("!Nutcade.S.limits || !Nutcade.S.limits.day"), e)
            await w.pg.close()
            return w2
        w2 = None
        async def daily_run():
            nonlocal w2
            w2 = await daily()
        await section('daily limit', daily_run)
        if w2: w = w2

        async def wrong_pin():
            e, _ = await set_limits(w, '100', '', '000000')
            check('limit: a wrong PIN changes nothing', await w.ev("!Nutcade.S.limits || !Nutcade.S.limits.per"), e)
            await w.ev("Nutcade.closeSheet()")
        await section('limit wrong PIN', wrong_pin)

        async def every_way():
            # every way sats leave: over the per-payment limit -> held with the amount, nothing leaves; PIN -> goes through;
            # under -> goes through without asking
            await w.use(A)
            wy = ways(w, A, fr)
            for way, amt in [('gift', 200), ('reqpay', 200), ('bounty', 200), ('extra', 200), ('move', 300), ('zap', 210), ('lnaddr', 220), ('contact', 150), ('hunt', 210), ('split', 130)]:
              start = lambda: wy[way](amt)
              try:
                await set_limits(w, '100', '', PIN)
                n0 = await w.ev("Nutcade.S.txs.length"); bal0 = await w.bal(); await start(); r = await outcome(w, n0)
                check(f'{way}: over the per-payment limit is held with the amount on screen, nothing leaves', r[0] == 'limit' and re.search(r'\d', r[1] or '') and await w.bal() == bal0, (r[0], (r[1] or '')[:160], await w.bal() - bal0))
                if r[0] == 'limit':
                    await layer_pin(w); r2 = await outcome(w, n0, 40000)
                    check(f'{way}: the PIN lets it through', r2[0] == 'ok', r2[:1] + [str(r2[1])[:160]])
                await settled(w)
                await set_limits(w, '100000', '', PIN)
                n0 = await w.ev("Nutcade.S.txs.length"); await start(); r = await outcome(w, n0, 40000)
                check(f'{way}: under the limit goes through without asking', r[0] == 'ok', r[:1] + [str(r[1])[:160]])
                await settled(w)
                await books(w, f'way {way}', broken, (A, B))
              except Exception as ex:
                check(f'{way}: ran to the end', False, repr(ex)[:200]); await w.ev("document.querySelector('#limitLayer')?.remove(); Nutcade.closeSheet()")
            await set_limits(w, '', '', PIN)
        await section('every way', every_way)

        async def nwc_way():
            uri = await make_nwc(w, 'Limit app', 'day', 5000)
            await w.ev("Nutcade.closeSheet()")
            await set_limits(w, '100', '', PIN)
            ans = lambda r: (r or {}).get('answer') or r or {}
            bal_app = ((ans(await nwc(w, uri, 'get_balance')).get('result')) or {}).get('balance')
            r = ans(await nwc(w, uri, 'pay_invoice', {'invoice': invoice(300, B)}))
            bal_app2 = ((ans(await nwc(w, uri, 'get_balance')).get('result')) or {}).get('balance')
            check("Wallet Connect: a payment refused for the wallet's limit pays nothing and takes nothing from the app's budget", bal_app is not None and bal_app == bal_app2 and not await w.ev("Nutcade.S.txs.some(t=>t.nwc&&t.type==='out')"), (bal_app, bal_app2))
            check('Wallet Connect: over the wallet limit (inside the app budget) is refused with QUOTA_EXCEEDED and says why', (r.get('error') or {}).get('code') in ('QUOTA_EXCEEDED', 'RESTRICTED') and 'limit' in ((r.get('error') or {}).get('message') or '').lower(), r)
            await set_limits(w, '', str(await w.ev("Nutcade.r8.spentDay()") + 250), PIN)
            r = ans(await nwc(w, uri, 'pay_invoice', {'invoice': invoice(300, B)}))
            check('Wallet Connect: over the daily limit is refused too', (r.get('error') or {}).get('code') in ('QUOTA_EXCEEDED', 'RESTRICTED'), r)
            await set_limits(w, '', '', PIN)
            r = ans(await nwc(w, uri, 'pay_invoice', {'invoice': invoice(300, B)}))
            check('Wallet Connect: with no wallet limit, the app budget alone decides (paid)', bool(r.get('result')) and not r.get('error'), r)
        await section('nwc', nwc_way)

        async def multi_offline():
            # multi-mint: the per-payment limit counts the whole payment, not each part
            await set_limits(w, '5000', '', PIN)
            amt = max(await w.bal(A), await w.bal(B)) + 1000
            await w.use(A); await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
            await w.fill('#destIn', invoice(amt, 'http://127.0.0.1:3340')); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#mppBtn')", 20000)
            await w.click('#mppBtn'); await w.until("!!document.querySelector('#mppPay') || !!document.querySelector('#limitLayer')", 40000)
            if await w.ev("!!document.querySelector('#mppPay')"): await w.click('#mppPay')
            n0 = await w.ev("Nutcade.S.txs.length"); r = await outcome(w, n0)
            check('multi-mint: a payment split over two mints is held when the whole is over the per-payment limit (each part alone is under)', r[0] == 'limit', r[:1] + [str(r[1])[:160]])
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            await set_limits(w, '', '', PIN)
            # offline: the ecash you hand over offline counts too
            await set_limits(w, '50', '', PIN)
            await w.use(B); await w.pg.context.set_offline(True); await w.wait(300)
            n0 = await w.ev("Nutcade.S.txs.length"); await ways(w, B)['ecash'](64); r = await outcome(w, n0)
            check('offline: sending ecash offline over the limit is held too', r[0] == 'limit', r[:1] + [str(r[1])[:160]])
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            await w.pg.context.set_offline(False); await w.wait(300)
            await set_limits(w, '', '', PIN)
        await section('multi-mint and offline', multi_offline)

        async def frees():
            # the day frees what came back: a token taken back (only its fee stays), a failed payment (only what the mint kept)
            await w.use(B); u0 = await w.ev("Nutcade.r8.spentDay()")
            tok, e = await w.send_ecash(300); u1 = await w.ev("Nutcade.r8.spentDay()")
            t0 = await w.ev("Nutcade.S.txs.find(t=>t.token&&t.amount===300&&t.status==='pending').id")
            await w.click('[data-act=tab][data-tab=history]'); await w.wait(150); await w.ev(f"Nutcade.closeSheet(); document.querySelector('[data-act=tx][data-id=\"{t0}\"]')?.click()"); await w.wait(300)
            await w.ev("document.querySelector('[data-act=reclaim]')?.click()"); await w.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(t0)}).status==='reclaimed'", 20000); await w.ev("Nutcade.closeSheet()")
            u2 = await w.ev("Nutcade.r8.spentDay()")
            check('frees: a token sent counts, and taken back frees its amount (no-fee mint: back to where it was)', u1 - u0 == 300 and u2 == u0, (u0, u1, u2))
            fm = 'http://127.0.0.1:3340'; await w.add_mint(fm); await w.use(fm); await w.receive_ln(500)
            u3 = await w.ev("Nutcade.r8.spentDay()"); await w.pay_ln(invoice(200, B)); await w.wait(1500)
            u4 = await w.ev("Nutcade.r8.spentDay()")
            check('frees: a payment that fails and comes back counts nothing (no fee on this mint)', u4 == u3 and await w.ev("Nutcade.S.txs.some(t=>t.mint==='http://127.0.0.1:3340'&&t.type==='out'&&t.status==='failed')"), (u3, u4))
            await w.use(B)
        await section('frees', frees)

        async def incoming_free():
            # what comes in is never limited: claiming a token, and swapping a token from another mint into yours
            await set_limits(w, '1', '1', PIN)
            await fr.use(A); tok, e = await fr.send_ecash(200)
            await w.use(B); await w.home(); _, e, txt = await w.receive_token(tok)
            check('incoming: a 1 SAT limit never blocks receiving', not e and not await w.ev("!!document.querySelector('#limitLayer')"), e)
            await set_limits(w, '', '', PIN)
        await section('incoming', incoming_free)

        async def numo():
            # a Numo-style checkout: a Lightning invoice and a Cashu payment request for the same sale
            await set_limits(w, '400', '', PIN)
            wy = ways(w, A, fr); await w.use(A)
            for way in ('ln', 'reqpay'):
                n0 = await w.ev("Nutcade.S.txs.length"); await wy[way](300); r = await outcome(w, n0)
                check(f'Numo checkout ({way}): 300 SAT under a 400 SAT limit is paid', r[0] == 'ok', r[:1] + [str(r[1])[:120]])
                await settled(w)
                n0 = await w.ev("Nutcade.S.txs.length"); await wy[way](500); r = await outcome(w, n0)
                check(f'Numo checkout ({way}): 500 SAT over a 400 SAT limit is held', r[0] == 'limit', r[:1] + [str(r[1])[:120]])
                await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            await set_limits(w, '', '', PIN)
            await books(w, 'numo', broken, (A, B))
        await section('numo', numo)

        async def no_pin():
            # without a PIN: the limit holds the payment and says to change it in Settings (no PIN to go over)
            n = await wallet(b); await n.create(); await n.add_mint(B); await n.use(B); await n.receive_ln(3000)
            e, t = await set_limits(n, '', '500')
            check('no PIN: a daily limit can be set (kept in plain storage)', not e and await n.ev("Nutcade.S.limits.day===500"), e)
            n0 = await n.ev("Nutcade.S.txs.length"); await ways(n, B)['ecash'](600); r = await outcome(n, n0)
            check('no PIN: over the limit is refused with the amount and where to change it, no PIN pad', r[0] in ('err', 'limit') and 'Settings' in r[1] and '600' in r[1] and not await n.ev("!!document.querySelector('#limitLayer [data-pinpad]')"), r)
            await n.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            n0 = await n.ev("Nutcade.S.txs.length"); await ways(n, B)['ln'](300); r = await outcome(n, n0)
            check('no PIN: under the limit goes through', r[0] == 'ok', r)
            await settled(n); await set_pin(n)
            check('no PIN -> PIN: setting a PIN moves the limit into the vault', await n.ev("localStorage.getItem('nutcade:limits')===null && Nutcade.S.limits.day===500"))
            await n.pg.context.close()
        await section('no PIN', no_pin)
        await w.pg.context.close(); await fr.pg.context.close()

        # ======================= duress PIN =======================
        async def duress():
            d = await wallet(b); real_words = await d.create(); await d.add_mint(A); await d.add_mint(B)
            await d.use(A); await d.receive_ln(5000); await d.use(B); await d.receive_ln(7000)
            await set_pin(d)
            ref = await wallet(b); await ref.create(); await ref.add_mint(B); await set_pin(ref)
            check('duress: a wallet with only a PIN already has the same vault fields (the second part is always there)', await ref.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault'))).sort()") == await d.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault'))).sort()"))
            ref_names = await ref.ev("Object.keys(localStorage).sort()")
            await settings(ref); ref_acts = await ref.ev("[...document.querySelectorAll('#app [data-act]')].map(e=>e.dataset.act).filter(a=>!/^(tab|jump|copy)$/.test(a)).sort()")
            await ref.pg.context.close()
            check('PIN set: storage names are only the device\'s own (the same in any wallet with a PIN)', await d.ev("Object.keys(localStorage).sort()") == ref_names, (await d.ev("Object.keys(localStorage).sort()"), ref_names))
            plain = await d.ev(PLAIN_JS)
            kids = await d.ev("Object.keys(Nutcade.S.counters)")
            check('PIN set: plain storage has none of the wallet (no mint, keyset, counter, log or trophy)', not any(x in plain for x in [A, B, '3338', '3339'] + kids) and not re.search(r'counters|mintlog|opsdone|trophies|"mints"', plain), plain[:300])
            ref_keys = await d.ev("Object.keys(localStorage).sort()"); ref_vault = await d.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault'))).sort()")
            ref_slot = await d.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault')).slot||{}).sort()")
            real_hist = await d.ev("Nutcade.S.txs.map(t=>t.id)"); real_bal = await d.bal()
            spent0 = await d.ev("Nutcade.r8.spentDay()"); await set_limits(d, '', str(spent0 + 100))
            # set: needs the real PIN, must differ from it
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250)
            await pad(d, '000000'); await d.wait(800)
            check('duress: setting it up starts with the real PIN (a wrong one is refused)', await d.ev("/wrong/i.test((document.querySelector('#pinErr')||{}).innerText||'')"))
            await pad(d, PIN); await d.wait(800); await pad(d, PIN); await d.wait(600)
            check('duress: the duress PIN must differ from the real PIN', await d.ev("/differ|same as/i.test((document.querySelector('#pinErr')||document.querySelector('#layer')||{}).innerText||'')"))
            await pad(d, DPIN); await d.wait(300); await pad(d, DPIN); await d.until("!!document.querySelector('#duressAmt')", 8000)
            await d.fill('#duressAmt', '300'); await d.click('[data-act=duressMake]'); await d.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000)
            check('duress: set up, with 300 SAT for the decoy', await d.ev("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')"), await d.sheet_text())
            await d.ev("Nutcade.closeSheet()")
            real_after = await d.bal(); real_vault_ct = await d.ev("(async()=>{await Nutcade.vault.chain; return JSON.parse(localStorage.getItem('nutcade:vault')).data.ct})()")
            check('duress: setting it adds no storage names', await d.ev("Object.keys(localStorage).sort()") == ref_keys, (await d.ev("Object.keys(localStorage).sort()"), ref_keys))
            check('duress: the 300 SAT for it count toward the spending limit (the PIN just entered lets them through)', await d.ev("Nutcade.r8.spentDay()") >= 300 + spent0, (spent0, await d.ev("Nutcade.r8.spentDay()")))
            check("duress: the vault record keeps the same fields, and its second part the same shape", await d.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault'))).sort()") == ref_vault and ref_slot == await d.ev("Object.keys(JSON.parse(localStorage.getItem('nutcade:vault')).slot||{}).sort()") and ref_slot)
            # open with the duress PIN (and watch every request: nothing may go to the real wallet's own mint, Mint A)
            await d.pg.reload(); await d.wait(700)
            plain = await d.ev(PLAIN_JS); check('locked: plain storage has none of the wallet', not any(x in plain for x in [A, B] + kids))
            to_a = []
            d.pg.on('request', lambda r: to_a.append(r.url) if r.url.startswith(A) and getattr(d, 'decoy_on', False) else None)
            d.decoy_on = True
            t_dur = await unlock(d, DPIN)
            await d.until("Object.values(Nutcade.S.proofs).flat().length>0", 30000); await d.wait(800)
            dw = await d.ev("Nutcade.S.seed && Nutcade.S.seed.mnemonic")
            tro = await d.ev("Object.keys(Nutcade.S && window.Trophies ? window.Trophies.got() : {})")
            check("duress PIN: its trophies are its own (none of the real wallet's, like LIGHTNING ROD)", 'lightning' not in tro, tro)
            await settings(d); dec_acts = await d.ev("[...document.querySelectorAll('#app [data-act]')].map(e=>e.dataset.act).filter(a=>!/^(tab|jump|copy)$/.test(a)).sort()")
            check('duress PIN: its Settings has the same buttons as a wallet with only a PIN (mint list backup included)', dec_acts == ref_acts, (sorted(set(ref_acts) ^ set(dec_acts))))
            check('duress PIN: opens a different wallet (its own 12 words)', dw and dw != real_words)
            check('duress PIN: its balance is the decoy\'s (about 300 SAT), not the real one', 280 <= await d.bal() <= 300, await d.bal())
            check('duress PIN: none of the real history is there', not await d.ev(f"Nutcade.S.txs.some(t=>{json.dumps(real_hist)}.includes(t.id))"))
            check('duress PIN: it has a history of its own (the sats it received)', await d.ev("Nutcade.S.txs.length>=1"))
            for tabn in ('wallet', 'history', 'mints', 'settings'):
                await d.ev("Nutcade.closeSheet()"); await d.click(f'[data-act=tab][data-tab={tabn}]'); await d.wait(300)
                txt = await d.ev("document.body.innerText")
                bad = r'decoy|real wallet|second wallet' + ('' if tabn == 'settings' else '|duress|another wallet')   # (Settings has the duress PIN row every wallet has, and "Moving from another wallet?")   # (Settings has the duress PIN row every wallet has)
                check(f'duress PIN: the {tabn} screen says nothing about a decoy or another wallet, and shows no real amount', not re.search(bad, txt, re.I) and f'{real_bal:,}' not in txt and '12,000' not in txt, re.findall(r'.{0,30}(?:' + bad + r').{0,30}', txt, re.I)[:3])
            await settings(d)
            st = await d.ev("(document.querySelector('#set-security')||{}).innerText||''")
            check('duress PIN: Settings shows a PIN wallet with no duress PIN set', 'ON' in st and re.search(r'Duress PIN\s*OFF', st), st)
            # the decoy is a working wallet: it can spend its sats
            tok, e = await d.send_ecash(100); check('duress PIN: the decoy can spend its own sats', tok and not e, e)
            dec_keys = await d.ev("Object.keys(localStorage).sort()")
            check('duress PIN: storage names are exactly those of a wallet with only a PIN while the decoy is open', dec_keys == ref_names, (dec_keys, ref_names))
            plain = await d.ev(PLAIN_JS); check('duress PIN: plain storage shows nothing of the real wallet while the decoy is open', not any(x in plain for x in [A] + kids))
            check("duress PIN: no request goes to the real wallet's own mint while the decoy is open", not to_a, to_a[:3])
            d.decoy_on = False
            check('duress PIN: the real wallet\'s encrypted data is untouched', await d.ev("(async()=>{await Nutcade.vault.chain; return JSON.parse(localStorage.getItem('nutcade:vault')).data.ct})()") == real_vault_ct)
            check('duress PIN: the decoy never reads or writes the plain mint list of the real wallet', await d.ev("JSON.stringify(Nutcade.S.mints.map(m=>m.url))") != json.dumps([A, B]).replace(' ', ''))
            # a backup made in the decoy is the decoy's only
            bk = await d.ev("Nutcade.r8.backupData()")
            check('duress PIN: a backup made in the decoy has only the decoy (its words, none of the real wallet)', dw in bk and real_words not in bk and A not in bk)
            # wrong PIN tries count for both
            await d.pg.reload(); await d.wait(700)
            t_wrong = await unlock(d, '999999', wait=False)
            # timing: the real and duress PIN take as long as each other (both keys are always tried)
            await d.pg.reload(); await d.wait(700); t_real = await unlock(d, PIN)
            check('timing: the duress and real PIN take about as long to open (within 50%)', max(t_dur, t_real) / max(0.01, min(t_dur, t_real)) < 1.5, (round(t_dur, 2), round(t_real, 2), round(t_wrong, 2)))
            check('real PIN: the real wallet is all there, as it was', abs(await d.bal() - real_after) <= 0 and await d.ev(f"{json.dumps(real_hist)}.every(id=>Nutcade.S.txs.some(t=>t.id===id))") and await d.ev("Nutcade.S.seed.mnemonic") == real_words, (await d.bal(), real_after))
            bk = await d.ev("Nutcade.r8.backupData()")
            check('real PIN: a backup of the real wallet has no trace of the decoy', dw not in bk)
            # change the real PIN: the duress PIN still opens the decoy
            await d.ev(NOALLOW); await set_limits(d, '', '', PIN); await d.ev(NOALLOW)
            await settings(d); await d.click('[data-act=pinChange]'); await d.wait(200); await pad(d, PIN); await d.wait(800); await pad(d, '111333'); await d.wait(300); await pad(d, '111333'); await d.wait(2500)
            await d.pg.reload(); await d.wait(700); await unlock(d, DPIN)
            check('change real PIN: the duress PIN still opens the decoy', await d.ev("Nutcade.S.seed.mnemonic") == dw)
            await d.pg.reload(); await d.wait(700); await unlock(d, '111333')
            check('change real PIN: the new real PIN opens the real wallet', await d.ev("Nutcade.S.seed.mnemonic") == real_words)
            # change the duress PIN (needs the real PIN)
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, '111333'); await d.until("!!document.querySelector('[data-act=duressChange]')", 8000)
            await d.click('[data-act=duressChange]'); await d.wait(200); await pad(d, '222444'); await d.wait(300); await pad(d, '222444'); await d.wait(2500); await d.ev("Nutcade.closeSheet()")
            await d.pg.reload(); await d.wait(700); await unlock(d, DPIN, wait=False)
            check('change duress PIN: the old duress PIN no longer opens anything', not await d.ev("Nutcade.vault.open"))
            await d.pg.reload(); await d.wait(700); await unlock(d, '222444')
            check('change duress PIN: the new one opens the decoy', await d.ev("Nutcade.S.seed.mnemonic") == dw)
            # lockout: wrong tries count across both PINs
            await d.pg.reload(); await d.wait(700)
            for _ in range(5): await unlock(d, '909090', wait=False)
            await pad(d, '222444'); await d.wait(1200)
            check('lockout: after 5 wrong tries the duress PIN waits too (same lockout)', not await d.ev("Nutcade.vault.open") and await d.ev("/Wait/.test(document.body.innerText)"))
            await d.ev("localStorage.removeItem('nutcade:pinfails')")
            # turn it off (needs the real PIN): the duress PIN is just a wrong PIN, storage names the same
            await d.ev(NOALLOW); await d.pg.reload(); await d.wait(700); await unlock(d, '111333')
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, '111333'); await d.until("!!document.querySelector('[data-act=duressOff]')", 8000)
            bal_on = await d.bal(); await d.click('[data-act=duressOff]'); await d.wait(300)
            if await d.ev("!!document.querySelector('[data-act=duressOffGo]')"): await d.click('[data-act=duressOffGo]'); await d.until("!document.querySelector('[data-act=duressOffGo]')", 30000); await d.wait(1500)
            check("duress off: the duress wallet's sats (its coins and its unclaimed token) come back to the real wallet", await d.bal() - bal_on == 300, (bal_on, await d.bal()))
            check('duress off: storage names unchanged', set(await d.ev("Object.keys(localStorage).sort()")) <= set(ref_keys))
            await d.pg.reload(); await d.wait(700); await unlock(d, '222444', wait=False)
            check('duress off: the old duress PIN is now just a wrong PIN', not await d.ev("Nutcade.vault.open"))
            await d.ev("localStorage.removeItem('nutcade:pinfails')")
            await d.pg.reload(); await d.wait(700); await unlock(d, '111333')
            check('duress off: the real wallet is unchanged', await d.ev("Nutcade.S.seed.mnemonic") == real_words)
            check("duress off: the sats that came back have a history note saying where from", await d.ev("Nutcade.S.txs.some(t=>t.type==='in'&&/duress PIN's wallet/.test(t.note||''))"))
            await books(d, 'duress real', broken, (A, B))
            # PIN changes share one allowance: 3 in 24 hours, then the same answer everywhere (also after a reload)
            await d.ev(NOALLOW)
            async def change_pin(old, new):
                await settings(d); await d.click('[data-act=pinChange]'); await d.wait(200); await pad(d, old); await d.wait(900)
                e1 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''")
                if 'available' in e1: await d.ev("Nutcade.closeSheet()"); return e1
                await pad(d, new); await d.wait(300); await pad(d, new); await d.wait(2500)
                e2 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''"); t = await d.toast(); await d.ev("Nutcade.closeSheet()"); return e2 or t
            r = [await change_pin('111333', '333555'), await change_pin('333555', '444666'), await change_pin('444666', '555777'), await change_pin('555777', '666888')]
            check('PIN changes: 3 in 24 hours go through, the 4th gets "not available right now"', all('available' not in x and 'wrong' not in x.lower() for x in r[:3]) and "aren't available" in r[3], r)
            await d.pg.reload(); await d.wait(700); await unlock(d, '555777')
            check('PIN changes: the allowance is not reset by unlocking again', "aren't available" in await change_pin('555777', '666888'))
            await d.ev(NOALLOW)
            # inside the duress wallet: a new PIN that is the real PIN is refused (never an oracle), no duress PIN of its own, no Remove PIN, no Face ID
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, '555777'); await d.wait(900); await pad(d, DPIN); await d.wait(300); await pad(d, DPIN)
            await d.until("!!document.querySelector('#duressAmt')", 8000); await d.click('[data-act=duressMake]'); await d.until("/READY/.test(document.body.innerText)", 30000); await d.ev("Nutcade.closeSheet()")
            await d.ev(NOALLOW); await d.pg.reload(); await d.wait(700); await unlock(d, DPIN)
            r1 = await change_pin(DPIN, '555777')
            check('in the duress wallet: changing its PIN to the real PIN is refused with the neutral answer', "aren't available" in r1, r1)
            check('in the duress wallet: and that uses up the allowance, so it reads as an allowance run out', await d.ev("JSON.parse(localStorage.getItem('nutcade:pinchg')).length") >= 3)
            await d.ev(NOALLOW)
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, DPIN); await d.wait(900)
            r2 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''"); await d.ev("Nutcade.closeSheet()")
            check('in the duress wallet: setting a duress PIN of its own gets the same neutral answer (no pretend success)', "aren't available" in r2, r2)
            await d.ev(NOALLOW)
            await settings(d); await d.click('[data-act=pinRemove]'); await d.wait(200); await pad(d, DPIN); await d.wait(1500)
            r3 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''"); await d.ev("Nutcade.closeSheet()")
            check('in the duress wallet: Remove PIN gets the same neutral answer and changes nothing', "aren't available" in r3 and await d.ev("!!localStorage.getItem('nutcade:vault')"), r3)
            await d.ev(NOALLOW); await d.pg.reload(); await d.wait(700); await unlock(d, '555777')
            check('after all that: the real PIN still opens the real wallet, untouched', await d.ev("Nutcade.S.seed.mnemonic") == real_words)
            # Reset wallet inside the duress wallet: only that wallet starts over; the real one survives
            rb = await d.bal(); await d.pg.reload(); await d.wait(700); await unlock(d, DPIN)
            await settings(d); await d.click('[data-act=resetAsk]'); await d.wait(200); await d.fill('#confirmWord', 'RESET'); await d.click('[data-act=doReset]'); await d.wait(2500)
            check('reset inside the duress wallet: the vault is still there (no plain wallet next to it)', await d.ev("!!localStorage.getItem('nutcade:vault') && !localStorage.getItem('nutcade:seed') && !localStorage.getItem('nutcade:proofs')"))
            await unlock(d, '555777')
            check('reset inside the duress wallet: the real wallet is all there', await d.ev("Nutcade.S.seed.mnemonic") == real_words and await d.bal() == rb, (await d.bal(), rb))
            await d.pg.context.close()
        await section('duress', duress)

        # ======================= NUT-06: a mint that takes at most 3 items per request =======================
        CF, CM = 'http://127.0.0.1:3343', 'http://127.0.0.1:3344'   # 3 items per request with input fees; exactly 128 (NUTCADE's minimum)
        def size_watch(seen):
            async def watch(route):
                try:
                    body = json.loads(route.request.post_data or '{}')
                    for k in ('inputs', 'outputs', 'Ys'):
                        if isinstance(body.get(k), list): p = route.request.url.split('/v1/')[-1]; seen[p] = max(seen.get(p, 0), len(body[k]))
                except Exception: pass
                await route.fallback()
            return watch
        async def hide(route):   # (the mint's info without its limit: as a mint that starts enforcing one later)
            try:
                r = await route.fetch(); j = await r.json(); j.pop('max_array_length', None); await route.fulfill(response=r, body=json.dumps(j))
            except Exception: pass
        async def nut06():
            info = json.loads(urllib.request.urlopen(C + '/v1/info', timeout=5).read())
            check('NUT-06: the test mints advertise 3 (and 128, NUTCADE\'s minimum)', info.get('max_array_length') == 3 and json.loads(urllib.request.urlopen(CM + '/v1/info', timeout=5).read()).get('max_array_length') == 128)
            # a mint below the minimum can't be added, in every language
            for lang in LANGS:
                n = await wallet(b, 375, 667, lang); await n.create(); await n.add_mint(C); t = await n.toast()
                check(f'NUT-06 {lang}: a mint that accepts only 3 coins per request can\'t be added, and says why (3, and the minimum 128)', not await n.ev(f"Nutcade.S.mints.some(m=>m.url==={json.dumps(C)})") and '3' in t and '128' in t and (lang == 'en' or 'only accepts' not in t), t)
                await n.pg.context.close()
            n = await wallet(b); await n.create(); await n.add_mint(CF)
            check('NUT-06: the fee mint with 3 per request can\'t be added either', not await n.ev(f"Nutcade.S.mints.some(m=>m.url==={json.dumps(CF)})"), await n.toast())
            await n.pg.context.close()
            # a mint at exactly the minimum: works normally, never a request over 128, coins picked within the limit
            seen = {}; g = await wallet(b); gw = await g.create(); await g.add_mint(CM); await g.use(CM); await g.pg.route(f'{CM}/v1/**', size_watch(seen))
            for _ in range(16): await g.receive_ln(1023)
            n0 = await g.ev(f"Nutcade.S.proofs[{json.dumps(CM)}].length")
            b1 = await g.bal(CM); tok2, e2 = await g.send_ecash(b1 - 8)
            check('NUT-06 at 128: a payment that would need more coins than the mint takes is refused with a clear message, nothing sent', not tok2 and '128 coins' in e2 and await g.bal(CM) == b1, (e2, await g.bal(CM) - b1))
            sw0 = await g.ev("performance.getEntriesByType('resource').filter(e=>/3344\\/v1\\/swap/.test(e.name)).length")
            tok, e = await g.send_ecash(16000)
            sw1 = await g.ev("performance.getEntriesByType('resource').filter(e=>/3344\\/v1\\/swap/.test(e.name)).length")
            check('NUT-06 at 128: a send that the usual pick would make of over 128 coins takes the biggest coins instead: one swap, at most 128 coins in', n0 >= 160 and tok and not e and sw1 - sw0 == 1 and max(seen.values() or [0]) <= 128, (n0, e, sw1 - sw0, seen))
            l, pp = await g.ev(LEDGER + f"({json.dumps(CM)})"); check('NUT-06 at 128: history = balance', l == pp, (l, pp))
            m = await wallet(b); await m.pg.route(f'{CM}/v1/**', size_watch(seen)); await m.pg.check('#ack'); await m.click('[data-act=gateRestore]'); await m.until("!!document.querySelector('#phraseIn')", 5000)
            await m.ev(f"(()=>{{const t=document.querySelector('#phraseIn'); t.value={json.dumps(gw)}; t.dispatchEvent(new Event('input',{{bubbles:true}})); document.querySelectorAll('[data-rmint]').forEach(i=>i.checked=false); document.querySelector('#rmExtra').value={json.dumps(CM)}}})()")
            await m.click('[data-act=doRestorePhrase]'); await m.until(f"(Nutcade.S.proofs[{json.dumps(CM)}]||[]).length>0", 120000); await m.wait(1500)
            check('NUT-06 at 128: restoring from the 12 words finds the coins, at most 128 outputs per request', await m.bal(CM) > 0 and 0 < seen.get('restore', 0) <= 128, (await m.bal(CM), seen.get('restore')))
            await m.pg.context.close(); await g.pg.context.close()
            # a mint already here that starts saying less than the minimum: no new deposits, a notice, sats can still move out
            seen = {}; h = await wallet(b); await h.pg.route(f'{C}/v1/info', hide); await h.create(); await h.add_mint(B); await h.add_mint(C); await h.use(C); await h.pg.route(f'{C}/v1/**', size_watch(seen))
            for a in (7, 7, 7, 56, 448, 3584, 14, 112, 896): await h.receive_ln(a)
            check('NUT-06 later: while its info says nothing, the mint is used as usual', await h.bal(C) == 5131, await h.bal(C))
            await h.pg.unroute(f'{C}/v1/info')
            tok, e = await h.send_ecash(30)
            l, pp = await h.ev(LEDGER + f"({json.dumps(C)})")
            check('NUT-06 later: when it starts enforcing 3, the refused request is followed by its info read again, and the sats still leave (in steps), nothing lost', tok and not e and l == pp and await h.ev("Nutcade.S.ops.length===0"), (e, l, pp))
            await h.pg.reload(); await h.wait(1500); await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=mints]'); await h.wait(1500)
            txt = await h.ev("document.body.innerText")
            check('NUT-06 later: the mints screen says it now accepts only 3 coins and to move the sats out', 'accepts only 3 coins' in txt and 'Move your sats out' in txt, txt[:300])
            await h.use(C); await h.home(); await h.click('[data-act=receive]'); await h.wait(150)
            if await h.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await h.click('[data-act=recvMethod][data-m=ln]'); await h.wait(100)
            q0 = await h.ev("Nutcade.S.quotes.length"); await h.fill('#amtIn', '7'); await h.click('[data-act=doLnInvoice]'); await h.wait(1500); e = await h.err(); await h.close()
            check('NUT-06 later: Receive there is refused before any invoice', 'no new deposits' in e and await h.ev("Nutcade.S.quotes.length") == q0, e)
            b0 = await h.bal(B); await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=mints]'); await h.wait(200); await h.click('#app [data-act=moveOpen]'); await h.wait(250)
            await h.ev(f"(()=>{{const f=document.querySelector('#mvFrom'), t=document.querySelector('#mvTo'); f.value={json.dumps(B)}; f.dispatchEvent(new Event('change',{{bubbles:true}})); t.value={json.dumps(C)}; t.dispatchEvent(new Event('change',{{bubbles:true}}))}})()")
            offered = await h.ev(f"[...document.querySelectorAll('#mvTo option')].some(o=>o.value==={json.dumps(C)})")
            await h.fill('#amtIn', '7'); await h.click('[data-act=moveQuote]'); await h.wait(2500); e = await h.err(); await h.ev("Nutcade.closeSheet()")
            check('NUT-06 later: a move INTO it is not offered (or refused) before anything is paid', (not offered or 'no new deposits' in e) and await h.bal(B) == b0 and not await h.ev(f"Nutcade.S.quotes.some(q=>q.mint==={json.dumps(C)})"), (offered, e, b0 - await h.bal(B)))
            m2 = await h.ev(f"Nutcade.r8.moveQuote ? Nutcade.r8.moveQuote({json.dumps(B)}, {json.dumps(C)}, 7).then(()=>'ok',e=>e.message) : 'n/a'")
            check('NUT-06 later: and the move itself refuses it before any quote is paid (the check every quote site uses)', 'no new deposits' in m2, m2)
            fz = await wallet(b); await fz.create(); await fz.add_mint(A); await fz.use(A); await fz.receive_ln(500); tk, _ = await fz.send_ecash(300); await fz.add_mint(B); await fz.use(B); await fz.receive_ln(500); tk2, _ = await fz.send_ecash(200); await fz.pg.context.close()
            await h.use(C); await h.home(); await h.click('[data-act=receive]'); await h.wait(150); await h.click('[data-act=recvMethod][data-m=ecash]'); await h.wait(100)
            await h.ev(f"(()=>{{const t=document.querySelector('#tokIn'); t.value={json.dumps(tk)}; t.dispatchEvent(new Event('input',{{bubbles:true}}))}})()"); await h.wait(300)
            await h.click('[data-act=doReceiveToken]'); await h.until("!!document.querySelector('[data-act=swapToken]')", 8000)
            await h.ev("document.querySelector('[data-act=swapToken]')?.click()"); await h.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 30000)
            e = await h.err(); await h.close()
            check('NUT-06 later: a token from another mint swapped into it is refused before anything is paid', 'no new deposits' in e and not await h.ev(f"Nutcade.S.quotes.some(q=>q.mint==={json.dumps(C)})"), e)
            _, e, _ = await h.receive_token(tk2)
            n_c = await h.ev(f"(Nutcade.S.proofs[{json.dumps(C)}]||[]).length")
            check('NUT-06 later: a token of the other mint is still claimed there (not into this one)', not e or 'no new deposits' not in e, e)
            await h.ev("Nutcade.closeSheet()"); await h.click('[data-act=tab][data-tab=mints]'); await h.wait(200); await h.click('#app [data-act=moveOpen]'); await h.wait(250)
            await h.ev(f"(()=>{{const f=document.querySelector('#mvFrom'), t=document.querySelector('#mvTo'); f.value={json.dumps(C)}; f.dispatchEvent(new Event('change',{{bubbles:true}})); t.value={json.dumps(B)}; t.dispatchEvent(new Event('change',{{bubbles:true}}))}})()")
            seen.clear(); bc = await h.bal(C); await h.fill('#amtIn', '2048'); await h.click('[data-act=moveQuote]'); await h.until("!!document.querySelector('#mvGo') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
            sheet = await h.sheet_text(); tot = re.search(r'Total, at most\s*([\d,]+)', sheet)
            if await h.ev("!!document.querySelector('#mvGo')"): await h.wait(300); await h.click('#mvGo')
            await h.until("/MOVED!|ON ITS WAY/.test((document.querySelector('.sheet-body')||{}).innerText||'') || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 60000); await h.wait(2000)
            e = await h.err(); await h.ev("Nutcade.closeSheet()")
            l, pp = await h.ev(LEDGER + f"({json.dumps(C)})")
            check('NUT-06 later: moving sats OUT still works (in steps, never a request over 3), the sheet says part of the change may be kept and its total holds', not e and 'may be kept' in sheet and 'comes back as change' not in sheet and max(seen.values() or [0]) <= 3 and l == pp and tot and bc - pp <= int(tot.group(1).replace(',', '')), (e, seen, l, pp, tot and tot.group(1), bc - pp))
            await books(h, 'nut06 later', broken, (B, C)); await h.pg.context.close()
        await section('nut06', nut06)

        # ======================= phones held sideways: no card, everything usable, nothing lost =======================
        IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        REACH = """(sel=>{const e=document.querySelector(sel); if(!e) return 'missing'; e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect();
          if(r.width<1||r.top<0||r.bottom>innerHeight||r.left<0||r.right>innerWidth) return 'off screen'; const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); return h&&(h===e||e.contains(h))?'ok':'covered'})"""
        async def landscape():
            for vw, vh in ((844, 390), (568, 320)):
                u = await wallet(b, vw, vh, 'en', ua=IPHONE); await u.create(); await u.add_mint(B); await u.use(B); await u.receive_ln(2000)
                res = {}
                check(f'landscape {vw}x{vh}: no "turn your phone" card or anything covering the app', not await u.ev("!!document.querySelector('#upright')"))
                for tabn, sel in (('wallet', '[data-act=send]'), ('history', '#app .tx'), ('mints', '#app [data-act=pickMint]'), ('settings', '[data-act=limOpen]')):
                    await u.ev("Nutcade.closeSheet()"); await u.click(f'[data-act=tab][data-tab={tabn}]'); await u.wait(250)
                    res[tabn] = await u.ev(REACH + f"({json.dumps(sel)})"); res[tabn + ' tabs'] = await u.ev(REACH + "('[data-act=tab][data-tab=wallet]')")
                await u.home(); await u.click('[data-act=send]'); await u.wait(250); res['send sheet'] = await u.ev(REACH + "('[data-act=doSendEcash]')"); await u.ev("Nutcade.closeSheet()")
                o = await u.ev(OVER_JS); check(f'landscape {vw}x{vh}: the main screens and the send sheet are usable (their buttons on screen and not covered), nothing wider than the screen', all(v == 'ok' for v in res.values()) and not o, (res, o))
                await u.click('[data-act=tab][data-tab=arcade]'); await u.wait(200); await u.ev("document.querySelector('[data-game=swarm]').click()"); await u.wait(800)
                g = await u.ev(REACH + "('[data-g=exit]')")
                check(f'landscape {vw}x{vh}: a game opens and its exit is reachable', await u.ev("!!(window.Arcade && window.Arcade.playing())") and g == 'ok', g)
                await u.pg.set_viewport_size({'width': vh, 'height': vw}); await u.wait(600); await u.pg.set_viewport_size({'width': vw, 'height': vh}); await u.wait(600)
                check(f'landscape {vw}x{vh}: turning the phone in the middle of a game loses nothing (still playing)', await u.ev("!!(window.Arcade && window.Arcade.playing())"))
                await u.ev("document.querySelector('[data-g=exit]')?.click()"); await u.wait(1200)
                async def slow(route):
                    await asyncio.sleep(3)
                    try: await route.continue_()
                    except Exception: pass
                await u.pg.route(f'{B}/v1/melt/bolt11', slow)
                n0 = await u.ev("Nutcade.S.txs.length"); bal0 = await u.bal(B); await ways(u, B)['ln'](300); await u.wait(500)
                await u.pg.set_viewport_size({'width': vh, 'height': vw}); await u.wait(1500); await u.pg.set_viewport_size({'width': vw, 'height': vh})
                r = await outcome(u, n0); await settled(u)
                l, pp = await u.ev(LEDGER + f"({json.dumps(B)})")
                check(f'landscape {vw}x{vh}: turning the phone in the middle of a payment loses nothing (paid once, history = balance)', r[0] == 'ok' and await u.ev("Nutcade.S.pending.length===0") and l == pp and bal0 - pp >= 300, (r[0], l, pp, bal0))
                await u.pg.context.close()
        await section('landscape', landscape)

        # ======================= About: report a problem; polish from the 1.12.1 recheck =======================
        async def polish():
            for lang in LANGS:
                q = await wallet(b, 375, 667, lang); await q.create(); await settings(q)
                a = await q.ev("(()=>{const e=[...document.querySelectorAll('#set-about a')].find(a=>/issues\\/new/.test(a.href)); return e ? [e.href, e.innerText] : null})()")
                check(f'About {lang}: a "Report a problem" link to the issue form', a and 'template=bug.yml' in a[0], a)
                await q.pg.context.close()
            q = await wallet(b, 375, 667); await q.create(); await q.add_mint(A); await q.use(A); await q.receive_ln(1000)
            # "Need X SAT including fees" includes the mint's fee to spend ecash
            inv = invoice(990, B)
            e, txt = await q.pay_ln(inv, confirm=True)
            m = re.search(r'([\d,]+) SAT (?:including fees|plus)', e or '')
            mq = await q.ev(f"(async()=>{{const w=new CashuLib.Wallet({json.dumps(A)},{{unit:'sat'}}); await w.loadMint(); const mq=await w.createMeltQuoteBolt11({json.dumps(inv)}); return [Number(mq.amount), Number(mq.fee_reserve)]}})()")
            need = int(m.group(1).replace(',', '')) if m else 0
            check('fee mint: "Need X SAT including fees" counts the mint\'s fee to spend ecash too', need > mq[0] + mq[1], (e, mq))
            # a reclaim on a fee mint: one honest fee line
            tok, e = await q.send_ecash(150)
            t0 = await q.ev("Nutcade.S.txs[0].id")
            await q.click('[data-act=tab][data-tab=history]'); await q.wait(150); await q.ev(f"Nutcade.closeSheet(); document.querySelector('[data-act=tx][data-id=\"{t0}\"]')?.click()"); await q.wait(300)
            await q.ev("document.querySelector('[data-act=reclaim], [data-act=takeBack], [data-act=reclaimGo]')?.click()"); await q.wait(500)
            await q.ev("document.querySelector('[data-act=reclaimGo]')?.click()"); await q.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(t0)}).status==='reclaimed'", 20000)
            back = await q.ev("Nutcade.S.txs[0]"); sent = await q.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(t0)})")
            await q.ev("Nutcade.closeSheet()"); await q.click('[data-act=tab][data-tab=history]'); await q.wait(200)
            rows = await q.ev("[...document.querySelectorAll('.tx')].slice(0,3).map(r=>r.innerText)")
            fees = sum(len(re.findall(r'[Ff]ee \d', r)) for r in rows[:2])
            check('reclaim on a fee mint: one fee line for what it cost, not "Sent fee 2" plus "Received fee 1"', fees <= 1 and (back.get('fee') or 0) == 0, (rows[:2], sent.get('fee'), back.get('fee')))
            # never "removed 0 SAT of spent ecash"
            async def spent_twice(route):
                await route.fulfill(status=400, content_type='application/json', body=json.dumps({'detail': 'Token already spent.', 'code': 11001}))
            await q.pg.route(f'{A}/v1/swap', spent_twice)
            _, e = await q.send_ecash(50)
            await q.pg.unroute(f'{A}/v1/swap')
            check('"already spent" with nothing to remove never says "removed 0 SAT"', e and not re.search(r'removed 0 SAT', e), e)
            # a failed treasure-hunt post redraws at once
            await q.ev("Nutcade.S.prefs.relays=['ws://127.0.0.1:9/none']")
            await q.ev("Nutcade.closeSheet()"); await q.home(); bal_shown0 = await q.ev("(document.querySelector('.credit-num')||{}).innerText||''")
            await q.ev("Nutcade.closeSheet(); document.querySelector('[data-act=huntNew]')?.click()"); await q.wait(300)
            opened = await q.ev("!!document.querySelector('[data-act=huntCreate]')")
            if opened:
                await q.fill('#amtIn', '100'); await q.click('[data-act=huntCreate]')
                await q.until("!!(document.querySelector('#sheetErr')||{}).innerText || /RELAY/.test(document.body.innerText)", 30000); await q.wait(500)
                await q.ev("Nutcade.closeSheet()"); await q.wait(300)
                txt = await q.ev("document.body.innerText"); bal_shown = await q.ev("(document.querySelector('.credit-num')||{}).innerText||''")
                check('treasure hunt: a post no relay took redraws at once (new balance, WAITING FOR A RELAY chip)', 'WAITING FOR A RELAY' in txt and bal_shown != bal_shown0, (bal_shown0, bal_shown, 'WAITING FOR A RELAY' in txt))
            else: check('treasure hunt: a post no relay took redraws at once (new balance, WAITING FOR A RELAY chip)', False, 'hunt screen not found')
            await q.pg.context.close()
            # long names at 320 px in English: wrap or fit, nothing cut off
            LN = 'Bartholomew Fitzgerald-Montgomery Lightning Emporium'
            n = await wallet(b, 320, 640, 'en'); await n.create(); await n.add_mint(B); await n.receive_ln(3000)
            await n.ev(f"""(()=>{{const S=Nutcade.S; S.mints[0].name={json.dumps(LN)}; S.contacts.push({{id:'cL',name:{json.dumps(LN)},ln:'bart@example.com',nostr:''}});
              S.txs.forEach(t=>{{t.note='Zap to '+{json.dumps(LN)}+' for the great pizza'}}); Nutcade.render()}})()""")
            cut = {}
            for name, js in [('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"), ('history', "document.querySelector('[data-act=tab][data-tab=history]').click()"),
                             ('mints', "document.querySelector('[data-act=tab][data-tab=mints]').click()"), ('contacts', "document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=contactsOpen]').click()")]:
                await n.ev(js); await n.wait(300)
                c = await n.ev("""[...document.querySelectorAll('#app *, #layer *')].filter(e=>e.getClientRects().length && e.children.length===0 && /Bartholomew|Emporium/.test(e.textContent) && (e.scrollWidth>e.clientWidth+1) && getComputedStyle(e).overflow!=='visible').map(e=>e.className+':'+e.textContent.slice(0,30))""")
                o = await n.ev(OVER_JS)
                if c or o: cut[name] = (c, o)
            check('long names at 320 px (English): wrap or fit, nothing cut off or wider than the screen', not cut, cut)
            await n.pg.context.close()
        await section('polish', polish)

        # ======================= every new screen in each language, at 320 px: nothing left in English, nothing too wide =======================
        async def looks():
            for lang in LANGS:
                k = await wallet(b, 320, 640, lang); await k.create(); await k.add_mint(B); await k.use(B); await k.receive_ln(3000); await set_pin(k)
                miss, wide = set(), {}
                async def shot(name):
                    o = await k.ev(OVER_JS); iw = await k.ev("innerWidth")
                    if o or iw != 320: wide[name] = (iw, o)
                    for x in await k.ev("[...window.__i18nMiss]"): miss.add(x)
                await k.ev("window.__i18nMiss=new Set()")
                await settings(k); await k.ev("document.querySelector('#set-security').scrollIntoView()"); await shot('settings')
                await k.click('[data-act=limOpen]'); await k.wait(250); await shot('limit sheet')
                await k.ev("const e=document.querySelector('#limDay'); e.value='-1'; e.dispatchEvent(new Event('input',{bubbles:true}))"); await k.click('[data-act=limSave]'); await k.wait(300); await shot('limit error')
                await k.ev("Nutcade.closeSheet()")
                await set_limits(k, '1000', '2500')
                await settings(k); await shot('settings with limits')
                st = await k.ev("(document.querySelector('#set-security')||{}).innerText||''")
                want = {'en': '2,500', 'es': '2.500', 'pt': '2.500', 'de': '2.500', 'fr': '2\u202f500'}[lang]
                check(f'looks {lang}: the daily limit is written the {lang} way in Settings', want in st or (lang == 'fr' and '2 500' in st), st[-160:])
                n0 = await k.ev("Nutcade.S.txs.length"); await ways(k, B)['ecash'](1500); r = await outcome(k, n0); await shot('over the limit')
                want2 = {'en': '1,500', 'es': '1.500', 'pt': '1.500', 'de': '1.500', 'fr': '1\u202f500'}[lang]
                check(f'looks {lang}: the over-the-limit screen is translated and writes amounts the {lang} way', r[0] == 'limit' and (want2 in r[1] or (lang == 'fr' and '1 500' in r[1])) and (lang == 'en' or 'This payment' not in r[1]), r[1][:200])
                await k.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
                await settings(k); await k.click('[data-act=duressOpen]'); await k.wait(250); await shot('duress pin')
                await pad(k, PIN); await k.wait(900); await shot('duress new'); await pad(k, PIN); await k.wait(300); await shot('duress same')
                await pad(k, DPIN); await k.wait(300); await pad(k, DPIN); await k.until("!!document.querySelector('#duressAmt')", 8000); await shot('duress fund')
                await k.click('[data-act=duressMake]'); await k.until("!!document.querySelector('[data-act=close]')", 20000); await k.wait(300); await shot('duress ready')
                await settings(k); await k.click('[data-act=duressOpen]'); await k.wait(250); await pad(k, PIN); await k.until("!!document.querySelector('[data-act=duressOff]')", 8000); await shot('duress menu')
                await k.click('[data-act=duressOff]'); await k.wait(250); await shot('duress off')
                await k.ev("Nutcade.closeSheet()"); await settings(k); await k.ev("document.querySelector('#set-about').scrollIntoView()"); await shot('about')
                check(f'looks {lang}: the spending limit, over-the-limit, duress PIN and About screens have nothing left in English', lang == 'en' or not miss, sorted(miss)[:8])
                check(f'looks {lang}: none of them is wider than 320 px', not wide, wide)
                await k.pg.context.close()
        await section('looks', looks)

        async def okkey():
            k = await wallet(b, 320, 568); await k.create(); await k.add_mint(B); await k.use(B); await k.receive_ln(2000); await set_pin(k)
            res = {}
            await settings(k); await k.click('[data-act=limOpen]'); await k.wait(200)
            await k.ev("const e=document.querySelector('#limPer'); e.value='100'; e.dispatchEvent(new Event('input',{bubbles:true}))"); await k.click('[data-act=limSave]'); await k.wait(300)
            res['limit save'] = await k.ev(OKKEY_JS); await pad(k, PIN, '#layer [data-pinpad]'); await k.wait(1500)
            n0 = await k.ev("Nutcade.S.txs.length"); await ways(k, B)['ecash'](300); await outcome(k, n0); res['over the limit'] = await k.ev(OKKEY_JS)
            await k.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.closeSheet()")
            await settings(k); await k.click('[data-act=duressOpen]'); await k.wait(200); res['duress PIN'] = await k.ev(OKKEY_JS); await pad(k, PIN); await k.wait(900); res['duress choose'] = await k.ev(OKKEY_JS)
            check('looks 320x568: the PIN pad\'s OK key is on screen without scrolling (limit save, over the limit, duress)', all(res.values()), res)
            await k.pg.context.close()
        await section('okkey', okkey)

        # ======================= fix round 2 (the 1.13.0 recheck) =======================
        async def r2_reset():
            # Reset wallet with a PIN (and with a duress PIN) leaves no vault: the start screen, as in 1.12.1
            for duress in (False, True):
                z = await wallet(b); await z.create(); await z.add_mint(B); await z.use(B); await z.receive_ln(500); await set_pin(z)
                if duress:
                    await settings(z); await z.click('[data-act=duressOpen]'); await z.wait(250); await pad(z, PIN); await z.wait(900); await pad(z, DPIN); await z.wait(300); await pad(z, DPIN)
                    await z.until("!!document.querySelector('#duressAmt')", 8000); await z.click('[data-act=duressMake]'); await z.until("/READY/.test(document.body.innerText)", 30000); await z.ev("Nutcade.closeSheet()")
                await settings(z); await z.click('[data-act=resetAsk]'); await z.wait(200); await z.fill('#confirmWord', 'RESET'); await z.click('[data-act=doReset]'); await z.wait(2500)
                tag = 'PIN and duress PIN' if duress else 'PIN'
                check(f'reset with a {tag}: no vault left, the start screen (not a dead lock screen)', await z.ev("!localStorage.getItem('nutcade:vault') && !!document.querySelector('[data-act=gateCreate]') && !document.querySelector('[data-pinpad]')"), await z.ev("[Object.keys(localStorage), document.body.innerText.slice(0,80)]"))
                await z.pg.context.close()
            # Remove PIN: no vault comes back afterwards
            z = await wallet(b); await z.create(); await z.add_mint(B); await set_pin(z)
            await settings(z); await z.click('[data-act=pinRemove]'); await z.wait(200); await pad(z, PIN); await z.wait(2500); await z.ev("Nutcade.S.prefs.theme='amber'; Nutcade.render()"); await z.ev("document.querySelector('[data-act=setTheme][data-t=neon]')?.click()"); await z.wait(1500)
            check('remove PIN: the vault is gone and stays gone after a settings change', await z.ev("!localStorage.getItem('nutcade:vault') && !Nutcade.vault.on"))
            await z.pg.context.close()
        await section('r2reset', r2_reset)

        async def r2_mints():
            # the mint at the minimum: every way money goes in still works there (a move into it, a token swapped into it)
            z = await wallet(b); await z.create(); await z.add_mint(B); await z.add_mint(CM); await z.use(B); await z.receive_ln(2000)
            b0 = await z.bal(B)
            await z.ev("Nutcade.closeSheet()"); await z.click('[data-act=tab][data-tab=mints]'); await z.wait(200); await z.click('#app [data-act=moveOpen]'); await z.wait(250)
            await z.ev(f"(()=>{{const f=document.querySelector('#mvFrom'), t=document.querySelector('#mvTo'); f.value={json.dumps(B)}; f.dispatchEvent(new Event('change',{{bubbles:true}})); t.value={json.dumps(CM)}; t.dispatchEvent(new Event('change',{{bubbles:true}}))}})()")
            await z.fill('#amtIn', '300'); await z.click('[data-act=moveQuote]'); await z.until("!!document.querySelector('#mvGo')", 15000); await z.wait(300); await z.click('#mvGo')
            ok = await z.until(f"(Nutcade.S.proofs[{json.dumps(CM)}]||[]).reduce((t,p)=>t+p.amount,0)===300", 40000)
            check('a move into a mint at the minimum (128) works as usual', ok, await z.bal(CM))
            await z.pg.context.close()
        await section('r2mints', r2_mints)

        async def r2_multi():
            seen = {}
            z = await wallet(b); await z.create(); await z.add_mint(B); await z.add_mint(CM); await z.pg.route(f'{CM}/v1/**', size_watch(seen))
            await z.use(CM)
            for a in (7, 7, 7, 56, 448, 3584, 14, 112, 896): await z.receive_ln(a)
            await z.use(B); await z.receive_ln(1500)
            amt = await z.bal(CM) + 800
            await z.home(); await z.click('[data-act=send]'); await z.wait(150); await z.click('[data-act=sendMethod][data-m=ln]'); await z.wait(100)
            await z.fill('#destIn', invoice(amt, 'http://127.0.0.1:3340')); await z.click('[data-act=doMeltQuote]'); await z.until("!!document.querySelector('#mppBtn')", 20000); await z.wait(300)
            await z.click('#mppBtn'); await z.until("!!document.querySelector('#mppPay') || !!document.querySelector('#layer .notice.red')", 40000); await z.wait(300)
            if await z.ev("!!document.querySelector('#mppPay')"): await z.click('#mppPay')
            await z.until("!document.querySelector('#mppPay')", 60000); await z.wait(4000)
            txt = await z.sheet_text(); st = await z.ev("Nutcade.S.txs.filter(t=>/part \\d of/.test(t.note||'')).map(t=>t.status)")
            words_ok = not ('came back' in txt and 'done' in st and 'went through' not in txt)
            check('multi-mint with a 128-item mint as one part: never a request over 128, and the sheet says what was booked', max(seen.values() or [0]) <= 128 and words_ok, (seen, st, txt[:200]))
            await books(z, 'r2 multi', broken, (B, CM)); await z.pg.context.close()
        await section('r2multi', r2_multi)

        async def r2_decoy():
            # the sats put in the duress wallet are its own coins at once: the real words never find them
            d = await wallet(b); words = await d.create(); await d.add_mint(B); await d.use(B); await d.receive_ln(3000); await set_pin(d)
            await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, PIN); await d.wait(900); await pad(d, DPIN); await d.wait(300); await pad(d, DPIN)
            await d.until("!!document.querySelector('#duressAmt')", 8000); await d.fill('#duressAmt', '300'); await d.click('[data-act=duressMake]'); await d.until("/READY/.test(document.body.innerText)", 30000); await d.ev("Nutcade.closeSheet()")
            real = await d.bal()
            r = await wallet(b); await r.ev("Nutcade.closeSheet()"); await r.pg.check('#ack'); await r.click('[data-act=gateRestore]'); await r.until("!!document.querySelector('#phraseIn')", 5000)
            await r.ev(f"(()=>{{const t=document.querySelector('#phraseIn'); t.value={json.dumps(words)}; t.dispatchEvent(new Event('input',{{bubbles:true}})); document.querySelectorAll('[data-rmint]').forEach(i=>i.checked=false); const x=document.querySelector('#rmExtra'); x.value={json.dumps(B)}}})()")
            await r.click('[data-act=doRestorePhrase]'); await r.until("/SCAN COMPLETE/.test(document.body.innerText) || Object.values(Nutcade.S.proofs).flat().length>0", 120000); await r.wait(3000)
            found = await r.bal(); await r.pg.context.close()
            check('duress set-up: the real words find exactly the real balance (the duress wallet\'s sats are its own coins at once)', found == real, (found, real))
            await d.pg.reload(); await d.wait(700); await unlock(d, DPIN)
            check('duress set-up: the duress wallet holds its sats as its own coins from the start (nothing left to claim)', await d.bal() == 300 and not await d.ev("Nutcade.S.txs.some(t=>t.incoming&&t.status==='pending')"), (await d.bal(), await d.ev("Nutcade.S.txs.map(t=>[t.status,t.amount])")))
            # Change PIN to the real PIN inside the duress wallet: refused at the same step, with the same words, as when the allowance is used up
            async def refusal_step(new):
                await settings(d); await d.click('[data-act=pinChange]'); await d.wait(200); await pad(d, DPIN); await d.wait(900)
                e1 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''")
                if e1: await d.ev("Nutcade.closeSheet()"); return ('after current PIN', e1)
                await pad(d, new); await d.wait(300); await pad(d, new); await d.wait(2500)
                e2 = await d.ev("(document.querySelector('#pinErr')||{}).innerText||''"); await d.ev("Nutcade.closeSheet()"); return ('after new PIN', e2)
            await d.ev(NOALLOW); a1 = await refusal_step(PIN)
            await d.ev("localStorage.setItem('nutcade:pinchg', JSON.stringify([Date.now(),Date.now(),Date.now()]))"); a2 = await refusal_step('777999')
            check('duress wallet: "change PIN to the real PIN" is refused at the same step and with the same words as a used-up allowance', a1 == a2 and "aren't available" in a1[1], (a1, a2))
            await d.ev(NOALLOW); await d.pg.context.close()
        await section('r2decoy', r2_decoy)

        check('round 8: the books add up everywhere (history = balance)', not broken, broken)
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', sum(1 for r in results if not r[1]), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
