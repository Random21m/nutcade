"""Auto-move into your mint (1.32.0): "Move what I receive into my mint" (Settings, Auto-move).

Uses the local test mints: 3338 (Mint A, input fees), 3339 (Mint B, no fees), 3340 (every payment fails) and 3345 (sat, usd
and eur, for two units in one wallet). Their Lightning is fake (FakeWallet): every deposit invoice is paid by itself, so a
check of "nothing moved" reads the sending mint's coins and the history lines, never only the total.

The grid: auto-move x fee / no-fee mint (each side) x my mint down (and slow: the screen keeps working) x login asked
(a mint answering NUT-21/22's auth errors, for my mint and for the sending mint) x amount below / exactly at / above the
"don't move below" setting x a sending mint without Lightning x a payment that fails x a crash mid-move (the page reloaded
while the melt's answer is held: recovered by the journal, moved once, no coin lost) x two units in one wallet (USD skipped,
never added to SAT) x the duress PIN's wallet (nothing, ever) x the spending limit and the PIN (over the one-payment limit,
over the day, under both: counted like any payment). Plus: off by default, my mint unset, a blocked mint (not offered, and
refused when it was picked before), fees over 2%, two arrivals at once (one move), the catch-up at app start, no retry
after a failure until the next arrival, the setting kept per wallet (PIN vault, duress wallet's own, not in backup files,
not taken from one, off after a restore from other words and after Reset), hostile input (a mint name with markup, typed
and stored thresholds that aren't whole numbers), and the new texts in five languages.
NOT proven here: a real mint's login flow (only its error answers are stood in for), two devices moving the same coins at
once (the mint refuses the second spend; see sync_qa for that machinery), and real Lightning fees. AM_ONLY=a,b runs some
sections (their names start with those letters)."""
import asyncio, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net
from r8_qa import set_pin, unlock, pad, PIN, DPIN, set_limits

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
A, B, F, P, MULTI = 'http://127.0.0.1:3338', 'http://127.0.0.1:3339', 'http://127.0.0.1:3340', 'http://127.0.0.1:3341', 'http://127.0.0.1:3345'
USD = MULTI + '|usd'
RELAY = 'ws://127.0.0.1:3350/relay'
MOCK = 'http://127.0.0.1:3350'
SAT_TOTAL = "Nutcade.S.mints.filter(m=>!m.url.includes('|')).reduce((t,m)=>t+(Nutcade.S.proofs[m.url]||[]).reduce((a,p)=>a+p.amount,0),0)"
WHATS = ["New, optional and off by default: Auto-move (Settings) moves the sats you receive at your other mints into the mint you pick, over Lightning, while NUTCADE is open, and catches up when you open it.",
         "It moves SAT only, only when a mint holds at least the amount you set (1,000 SAT to start) and only when the fees are 2% or less. Moves count toward your spending limit; one that needs your PIN waits for you."]
CORS = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*', 'Content-Type': 'application/json'}
# every toast shown, kept for the checks
TOASTS = "window.__toasts=[]; new MutationObserver(()=>{const t=document.querySelector('#toast'); if(t&&!t.hidden&&t.textContent&&window.__toasts[window.__toasts.length-1]!==t.textContent) window.__toasts.push(t.textContent)}).observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true});"


async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    await ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{" + TOASTS + "})")
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text and 'Failed to load' not in m.text and 'Failed to fetch' not in m.text and 'net::' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def fresh(b, name, mints=(A, B), lang='en'):
    w = await wallet(b, name, lang); await w.create()
    for m in mints: await w.add_mint(m)
    return w


async def section(name, fn):
    only = [x for x in os.environ.get('AM_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
async def bal(w, url): return await w.ev(f"(Nutcade.S.proofs[{J(url)}]||[]).reduce((t,p)=>t+p.amount,0)")
async def total(w): return await w.ev(SAT_TOTAL)
async def autos(w): return await w.ev("Nutcade.S.txs.filter(t=>t.autoMove).map(t=>({type:t.type,status:t.status,amount:t.amount,fee:t.fee||0,mint:t.mint}))")
async def lines(w): return await w.ev("NutAutoMove.last()")
def ks(ls): return [l['k'] for l in (ls or [])]
async def recv(w, url, n):
    await w.use(url); return await w.receive_ln(n)


async def am_set(w, on=True, my=None, mn=None):
    """Settings -> Auto-move: the switch, my mint, don't move below (as a person does it)"""
    await settings(w)
    if bool(await w.ev("document.querySelector('#p_amOn').checked")) != on: await w.click('#p_amOn'); await w.wait(200)
    if on and my is not None:
        await w.pg.select_option('#p_amMint', my); await w.wait(200)
    if on and mn is not None:
        await w.pg.fill('#p_amMin', str(mn)); await w.pg.dispatch_event('#p_amMin', 'change'); await w.wait(200)
    await w.ev("Nutcade.closeSheet()")


async def run(w): return await w.ev("NutAutoMove.run('test')")


async def wait_run(w, t0, ms=90000):
    """until a run that started after t0 has ended"""
    return await w.until(f"NutAutoMove.at() > {t0} && !NutAutoMove.busy()", ms)


async def settled(w, ms=60000):
    """every automatic move's lines done (or failed)"""
    return await w.until("Nutcade.S.txs.filter(t=>t.autoMove).every(t=>t.status!=='pending') && !Nutcade.S.pending.length", ms)


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        errs = []

        # ======================= the setting: off by default, my mint, the threshold, blocked mints, hostile input =======================
        async def pref():
            w = await fresh(b, 'am-pref')
            check('pref: off by default (a new wallet): off, no mint picked, 1,000 SAT',
                  await w.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint, Nutcade.S.prefs.amMin]") == [False, '', 1000])
            await settings(w)
            txt = await w.ev("(document.querySelector('#set-automove')||{}).innerText||''")
            check('pref: Settings has an Auto-move panel with the switch off and nothing else to fill in while off',
                  'Auto-move' in txt and 'Move what I receive into my mint' in txt and not await w.ev("document.querySelector('#p_amOn').checked") and not await w.ev("!!document.querySelector('#p_amMint')"), txt[:200])
            await recv(w, A, 1500)
            t0 = await w.ev("NutAutoMove.at()"); await w.wait(4000)
            check('pref: while off, money arriving moves nothing and no run happens', not await autos(w) and await bal(w, A) == 1500 and await w.ev("NutAutoMove.at()") == t0 and await run(w) is None)
            await am_set(w, True)
            await settings(w)
            opts = await w.ev("[...document.querySelectorAll('#p_amMint option')].map(o=>o.value)")
            check('pref: on, "My mint" lists only your own mints that take and pay Lightning, with "Pick a mint" first and selected', opts == ['', A, B] and await w.ev("document.querySelector('#p_amMint').value") == '', opts)
            check('pref: my mint unset: the panel says to pick one', 'Pick your mint below' in await w.ev("document.querySelector('#set-automove').innerText"))
            ls = await run(w)
            check('pref: my mint unset: a run moves nothing and says so', ks(ls) == ['unset'] and not await autos(w) and await bal(w, A) == 1500, ls)
            # the threshold: only whole numbers of SAT, 1 or more
            for v in ('abc', '0', '-5', '1.5', '99999999999999999999', '1e3', '', '<b>1</b>'):
                await settings(w); await w.ev("window.__toasts=[]")
                await w.pg.fill('#p_amMin', v); await w.pg.dispatch_event('#p_amMin', 'change'); await w.wait(150)
                got = await w.ev("Nutcade.S.prefs.amMin")
                check(f'pref: "don\'t move below" refuses {v!r} and keeps 1,000', got == 1000 and any('whole number' in t for t in await w.ev("window.__toasts")), (got, await w.ev("window.__toasts")))
            await settings(w); await w.pg.fill('#p_amMin', '1500'); await w.pg.dispatch_event('#p_amMin', 'change'); await w.wait(150)
            check('pref: "don\'t move below" takes 1500 as the whole number 1500', await w.ev("Nutcade.S.prefs.amMin") == 1500)
            for bad in ('-5', "'x'", '1.5', 'NaN', '1e300', "'1000'"):
                await w.ev(f"Nutcade.S.prefs.amMin = {bad}")
                check(f'pref: a stored threshold of {bad} is read as the default 1,000', await w.ev("NutAutoMove.min()") == 1000)
            await w.ev("Nutcade.S.prefs.amMin = 1000")
            # a blocked mint: never offered, and refused when it was picked before it was blocked
            await am_set(w, True, my=B)
            await w.ev(f"Nutcade.S.blocked.push({{url:{J(B)}, name:'Mint B', at:Date.now()}}); Nutcade.render()")
            await settings(w)
            check('pref: a blocked mint is not offered as my mint', B not in await w.ev("NutAutoMove.fit()") and B not in await w.ev("[...document.querySelectorAll('#p_amMint option')].map(o=>o.value)"))
            ls = await run(w)
            check('pref: my mint blocked after it was picked: nothing moves, one line says so', ks(ls) == ['mybad'] and not await autos(w) and await bal(w, A) == 1500, ls)
            await w.ev("Nutcade.S.blocked.length = 0; Nutcade.render()")
            # hostile mint name
            await w.ev(f"Nutcade.S.mints.find(m=>m.url==={J(A)}).name = '<img src=x onerror=\"window.__pwn=1\">Evil'; Nutcade.S.mints.find(m=>m.url==={J(A)}).methods.melt = []")
            await w.ev("NutAutoMove.run('test')"); await settings(w)
            inj = await w.ev("[!!document.querySelector('#set-automove img'), window.__pwn===1, (document.querySelector('#set-automove').innerText.match(/<img[^\\n]*Evil/)||[])[0]||'']")
            check('hostile: a mint name with markup is shown as text in the list and the lines, never run', not inj[0] and not inj[1] and inj[2], inj)
            check('pref: a sending mint without Lightning: nothing moves, its line says why', ks(await lines(w)) == ['noln'] and await bal(w, A) == 1500 and not await autos(w), await lines(w))
            errs.extend(w.errs); await w.pg.context.close()
        await section('pref', pref)

        # ======================= moves: no-fee into a fee mint, and a fee mint into a no-fee one =======================
        async def move():
            for name, my, src, n in (('no-fee mint into a fee mint', A, B, 2000), ('fee mint into a no-fee mint', B, A, 3000)):
                w = await fresh(b, 'am-move')
                await am_set(w, True, my=my)
                t0 = await w.ev("NutAutoMove.at()")
                await recv(w, src, n)
                ok = await wait_run(w, t0) and await settled(w)
                await w.wait(3000)   # (and nothing more: the moved deposit is not an arrival)
                au = await autos(w); ls = await lines(w); out = [t for t in au if t['type'] == 'out']; inn = [t for t in au if t['type'] == 'in']
                check(f'move, {name}: an arrival moves it to my mint by itself, one payment and one deposit, both done',
                      ok and len(out) == 1 and len(inn) == 1 and out[0]['status'] == 'done' and inn[0]['status'] == 'done' and out[0]['mint'] == src and inn[0]['mint'] == my and ks(ls) == ['moved'], (au, ls))
                if out and inn:
                    bm, bs, tot = await bal(w, my), await bal(w, src), await total(w)
                    check(f'move, {name}: my mint holds exactly the amount moved, and only the fee left the wallet', bm == inn[0]['amount'] and tot == n - out[0]['fee'] and bs == n - inn[0]['amount'] - out[0]['fee'], (bm, bs, tot, au))
                    check(f'move, {name}: the fee is 2% of the amount or less and the line says how much moved', out[0]['fee'] * 100 <= inn[0]['amount'] * 2 and ls[0]['a'] == [inn[0]['amount']], (au, ls))
                    check(f'move, {name}: a toast said it moved', any(re.search(r'Moved [\d,]+ SAT to your mint', t) for t in await w.ev("window.__toasts")), await w.ev("window.__toasts"))
                    check(f'move, {name}: the lines are marked as moves (not arrivals, outside the piggy bank)', await w.ev("Nutcade.S.txs.filter(t=>t.autoMove).every(t=>t.move===true && !t.roundup)"))
                errs.extend(w.errs); await w.pg.context.close()
        await section('move', move)

        # ======================= the threshold: below, exactly at; fees over 2% =======================
        async def threshold():
            w = await fresh(b, 'am-thr')
            await am_set(w, True, my=B, mn=1000)
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, A, 999); await wait_run(w, t0); await w.wait(500)
            ls = await lines(w)
            check('threshold: 999 SAT at the other mint (one below 1,000): nothing moves, the line says so', ks(ls) == ['none'] and ls[0]['a'] == [1000] and not await autos(w) and await bal(w, A) == 999, ls)
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, A, 1); await wait_run(w, t0); await settled(w)
            au = await autos(w)
            check('threshold: exactly 1,000 SAT there moves (less the fees)', ks(await lines(w)) == ['moved'] and len([t for t in au if t['type'] == 'in' and t['status'] == 'done']) == 1 and await bal(w, A) < 1000 - 950, (au, await lines(w)))
            await am_set(w, True, mn=50)
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, A, 60 - await bal(w, A)); await wait_run(w, t0); await w.wait(300)
            ls = await lines(w)
            fee_ok = ks(ls) == ['fee'] and ls[0]['a'][0] * 100 > ls[0]['a'][1] * 2
            check('fee cap: 60 SAT with a threshold of 50: the fees are more than 2% of it, so nothing moves and the line says so', fee_ok and len(await autos(w)) == 2 and await bal(w, A) == 60, ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('threshold', threshold)

        # ======================= my mint down or slow, a login asked for, a failed payment =======================
        async def down():
            w = await fresh(b, 'am-down')
            await recv(w, B, 1500)
            await am_set(w, True, my=A)
            hits = []
            async def abort(route):
                if route.request.method == 'POST' and '/v1/mint/quote/bolt11' in route.request.url: hits.append(time.time())
                await route.abort()
            await w.pg.route(A + '/**', abort)
            ls = await run(w)
            check('my mint down: nothing moves, one line says my mint isn\'t answering', ks(ls) == ['mydown'] and not await autos(w) and await bal(w, B) == 1500, ls)
            n = len(hits); await w.wait(8000)
            check('my mint down: nothing is tried again by itself (no timer, no loop)', len(hits) == n and n >= 1, (n, len(hits)))
            await am_set(w, True, my=A)   # (picking the mint again starts the reasons afresh)
            await w.ev("window.__toasts=[]")
            await w.ev("NutAutoMove.run('again')"); await w.ev("NutAutoMove.run('again')"); await w.wait(500)
            nt = [t for t in await w.ev("window.__toasts") if 'nothing moved' in t]
            check('my mint down: the same reason again shows its toast once, not at every run', len(nt) == 1, await w.ev("window.__toasts"))
            await w.pg.unroute(A + '/**')
            held = []
            async def hang(route):
                if route.request.method == 'POST' and '/v1/mint/quote/bolt11' in route.request.url: held.append(route); return
                await route.continue_()
            await w.pg.route(A + '/**', hang)
            await w.ev("NutAutoMove.run('test'); 1")
            await w.until("NutAutoMove.busy()", 3000)
            t = time.time(); await settings(w); await w.click('[data-act=tab][data-tab=wallet]'); dt = time.time() - t
            check('slow mint: while my mint doesn\'t answer, the screens keep working', dt < 3 and await w.ev("NutAutoMove.busy()") and held, (dt, len(held)))
            ok = await w.until("!NutAutoMove.busy()", 45000)
            check('slow mint: the request\'s time limit ends the run with the same one line, nothing moved', ok and ks(await lines(w)) == ['mydown'] and await bal(w, B) == 1500 and not await autos(w), await lines(w))
            await w.pg.unroute(A + '/**')
            async def abort_melt(route): await route.abort()
            await w.pg.route(B + '/v1/melt/quote/bolt11', abort_melt)
            await w.ev("window.__toasts=[]")
            ls = await w.ev("NutAutoMove.run('again')")
            check('sending mint down: nothing moves, its line says it isn\'t answering', ks(ls) == ['down'] and ls[0]['n'] == 'Mint B' and await bal(w, B) == 1500 and not await autos(w), ls)
            check('sending mint down: a new reason gets its own toast', any('nothing moved' in t for t in await w.ev("window.__toasts")), await w.ev("window.__toasts"))
            await w.pg.unroute(B + '/v1/melt/quote/bolt11')
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, B, 100); await wait_run(w, t0); await settled(w)
            check('my mint back: the next arrival moves it all', ks(await lines(w)) == ['moved'] and await bal(w, B) < 100 and len(await autos(w)) == 2, (await lines(w), await autos(w)))
            errs.extend(w.errs); await w.pg.context.close()
        await section('down', down)

        async def login():
            w = await fresh(b, 'am-login')
            await recv(w, B, 1500)
            await am_set(w, True, my=A)
            async def auth(code, detail):
                async def h(route):
                    if route.request.method == 'OPTIONS': await route.fulfill(status=204, headers=CORS); return
                    if route.request.method == 'POST': await route.fulfill(status=400, headers=CORS, body=J({'detail': detail, 'code': code})); return
                    await route.continue_()
                return h
            await w.pg.route(A + '/v1/mint/quote/bolt11', await auth(30001, 'Endpoint requires clear auth'))
            ls = await run(w)
            check('login asked (NUT-21 30001) by my mint: nothing moves, one line says my mint asks for a login', ks(ls) == ['mylogin'] and not await autos(w) and await bal(w, B) == 1500, ls)
            await w.pg.unroute(A + '/v1/mint/quote/bolt11')
            await w.pg.route(B + '/v1/melt/quote/bolt11', await auth(31001, 'Endpoint requires blind auth'))
            ls = await run(w)
            check('login asked (NUT-22 31001) by the sending mint: nothing moves, its line names it', ks(ls) == ['login'] and ls[0]['n'] == 'Mint B' and not await autos(w) and await bal(w, B) == 1500, ls)
            await w.pg.unroute(B + '/v1/melt/quote/bolt11')
            await w.pg.route(A + '/v1/mint/quote/bolt11', await auth(20000, 'Lightning backend error'))
            ls = await run(w)
            check('my mint answers with an error (not a login): "turned the request down", not "isn\'t answering"', ks(ls) == ['myrefused'] and not await autos(w), ls)
            await w.pg.unroute(A + '/v1/mint/quote/bolt11')
            await w.pg.route(B + '/v1/melt/quote/bolt11', await auth(20000, 'Lightning backend error'))
            ls = await run(w)
            check('the sending mint answers with an error: its line says it turned the request down', ks(ls) == ['refused'] and ls[0]['n'] == 'Mint B' and not await autos(w), ls)
            await w.pg.unroute(B + '/v1/melt/quote/bolt11')
            ls = await run(w); await settled(w)
            check('login answered again: the next run moves it', ks(ls) == ['moved'] and await bal(w, B) < 100, ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('login', login)

        async def fail():
            w = await fresh(b, 'am-fail', mints=(F, B))
            await recv(w, F, 1500)
            await am_set(w, True, my=B)
            ls = await run(w); await w.until("!Nutcade.S.pending.length", 30000); await w.wait(500)
            check('failed payment: the move didn\'t go through, the line says so and the sats are back at the sending mint', ks(ls) == ['fail'] and await bal(w, F) == 1500 and [t['status'] for t in await autos(w) if t['type'] == 'out'] == ['failed'], (ls, await bal(w, F), await autos(w)))
            errs.extend(w.errs); await w.pg.context.close()
        await section('fail', fail)

        # ======================= two arrivals at once; the catch-up at app start =======================
        async def twice():
            w = await fresh(b, 'am-twice')
            await recv(w, A, 1500)
            await am_set(w, True, my=B)
            same = await w.ev(f"(()=>{{NutAutoMove.arrived({{mint:{J(A)},type:'in'}}); NutAutoMove.arrived({{mint:{J(A)},type:'in'}}); const a=NutAutoMove.run('test'), b=NutAutoMove.run('test'); return Promise.all([a,b]).then(r=>a===b)}})()")
            await w.wait(6000); await w.until("!NutAutoMove.busy()", 60000); await settled(w)
            au = await autos(w)
            check('twice: two arrivals and two runs at once make one run and one move (single flight)', same and len([t for t in au if t['type'] == 'out']) == 1 and len([t for t in au if t['type'] == 'in']) == 1, au)
            out = [t for t in au if t['type'] == 'out']
            check('twice: nothing moved twice, only the fee left the wallet', out and await total(w) == 1500 - out[0]['fee'], (await total(w), au))
            errs.extend(w.errs); await w.pg.context.close()
        await section('twice', twice)

        async def start():
            w = await fresh(b, 'am-start')
            await recv(w, A, 1500)
            await am_set(w, True, my=B)
            await w.wait(4000)
            check('start: turning it on or picking my mint moves nothing by itself (only arrivals and app start do)', not await autos(w) and await bal(w, A) == 1500)
            await w.pg.reload(); await w.wait(800)
            ok = await w.until("NutAutoMove.at() > 0 && !NutAutoMove.busy()", 90000); await settled(w)
            check('start: opening NUTCADE catches up: the 1,500 SAT left waiting are moved once', ok and ks(await lines(w)) == ['moved'] and len(await autos(w)) == 2 and await bal(w, A) < 100, (await lines(w), await autos(w)))
            await recv(w, A, 1200); await w.until("!NutAutoMove.busy()", 60000); await w.wait(2500); await w.until("!NutAutoMove.busy()", 60000); await settled(w)
            t0 = await w.ev("NutAutoMove.at()"); fid = await w.ev("Nutcade.S.txs.find(t=>t.type==='in'&&!t.move&&t.amount===1200).id")
            await w.ev(f"NutAutoMove.arrived(Nutcade.S.txs.find(t=>t.id==={J(fid)}))")
            await w.click('[data-act=tab][data-tab=history]'); await w.wait(300)
            await w.ev(f"document.querySelector('[data-act=tx][data-id={fid}]').click()"); await w.until("!!document.querySelector('#noteEdit')", 5000)
            await w.fill('#noteEdit', 'fresh edit'); await w.click('[data-act=saveNote]'); await w.wait(4000)
            check('start: a fresh arrival already seen starts no second run (its note edited, or announced again)', await w.ev("NutAutoMove.at()") == t0 and not await w.ev("NutAutoMove.busy()"), (t0, await w.ev("NutAutoMove.at()")))
            await w.ev("const t=Nutcade.S.txs.find(t=>t.type==='in'&&!t.move&&t.amount===1200); t.ts=Date.now()-3600e3"); await am_set(w, True, mn=5000)   # (saved with the setting)
            await w.pg.reload(); await w.wait(800); await w.until("NutAutoMove.at() > 0 && !NutAutoMove.busy()", 90000)
            t0 = await w.ev("NutAutoMove.at()"); tid = await w.ev("Nutcade.S.txs.find(t=>t.type==='in'&&!t.move&&t.amount===1200).id")
            await w.click('[data-act=tab][data-tab=history]'); await w.wait(300)
            await w.ev(f"document.querySelector('[data-act=tx][data-id={tid}]').click()"); await w.until("!!document.querySelector('#noteEdit')", 5000)
            await w.fill('#noteEdit', 'edited later'); await w.click('[data-act=saveNote]'); await w.wait(4000)
            check('start: editing the note of an old received line starts no run (only new arrivals do)', await w.ev(f"Nutcade.S.txs.find(t=>t.id==={J(tid)}).note") == 'edited later' and await w.ev("NutAutoMove.at()") == t0, (t0, await w.ev("NutAutoMove.at()")))
            errs.extend(w.errs); await w.pg.context.close()
        await section('start', start)

        # ======================= fee cap exactly at 2%; sync and the 12 words; several sources =======================
        async def cap():
            w = await fresh(b, 'am-cap')
            await am_set(w, True, my=A, mn=50)
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, B, 102); await wait_run(w, t0); await settled(w)
            au = await autos(w); ls = await lines(w)
            check('fee cap: a fee of exactly 2% (2 SAT on 100) is allowed: it moves', ks(ls) == ['moved'] and ls[0]['a'] == [100] and len(au) == 2, (ls, au))
            left = await bal(w, B)
            t0 = await w.ev("NutAutoMove.at()"); await recv(w, B, 101 - left); await wait_run(w, t0); await w.wait(300)
            ls = await lines(w)
            check('fee cap: 2 SAT on 99 (just over 2%) is refused, nothing moves', ks(ls) == ['fee'] and ls[0]['a'] == [2, 99] and len(await autos(w)) == 2 and await bal(w, B) == 101, ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('cap', cap)

        async def waits():
            w = await fresh(b, 'am-wait')
            await am_set(w, True, my=A)
            await w.ev("Nutcade.S.prefs.sync = true"); await am_set(w, True, my=B); await am_set(w, True, my=A)   # (saved with the setting)
            await settings(w)
            check('sync: while wallet sync is on the panel says auto-move waits', 'waits while wallet sync is on' in await w.ev("document.querySelector('#set-automove').innerText"))
            await recv(w, B, 1500); await w.wait(4000)
            check('sync: while it is on an arrival moves nothing and starts no run', not await autos(w) and await bal(w, B) == 1500 and await w.ev("NutAutoMove.at()") == 0)
            await w.pg.reload(); await w.wait(6000)
            check('sync: opening NUTCADE with sync on moves nothing either', not await autos(w) and await bal(w, B) == 1500 and await w.ev("NutAutoMove.at()") == 0)
            ls = await run(w)
            check('sync: a run asked for says the same one line', ks(ls) == ['sync'] and not await autos(w), ls)
            await w.ev("Nutcade.S.prefs.sync = false; Nutcade.S.seed.backedUp = false")
            ls = await run(w)
            check('12 words: not written down yet (the app is on its set-up screens): a run says auto-move waits for them and moves nothing', ks(ls) == ['backup'] and not await autos(w), ls)
            await w.ev("Nutcade.S.seed.backedUp = true")
            ls = await run(w); await settled(w)
            check('sync off and words written down: it moves', ks(ls) == ['moved'] and await bal(w, B) < 100, ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('waits', waits)

        async def multi():
            w = await fresh(b, 'am-multi', mints=(A, F, MULTI, B))
            for m in (A, F, MULTI): await recv(w, m, 1500)
            await w.ev(f"Nutcade.S.blocked.push({{url:{J(MULTI)}, name:'Multi Mint', at:Date.now()}})")
            await am_set(w, True, my=B)
            ls = await run(w); await settled(w)
            got = {l['n']: l['k'] for l in ls}
            check('several sources: one moves, one fails, each with its own line; a blocked mint is skipped and left alone',
                  got.get('Mint A') == 'moved' and got.get('Fail Mint') == 'fail' and 'Multi Mint' not in got and await bal(w, MULTI) == 1500 and await bal(w, F) == 1500 and await bal(w, A) < 100, (ls, await bal(w, F), await bal(w, MULTI)))
            errs.extend(w.errs); await w.pg.context.close()
        await section('multi', multi)

        # ======================= a payment in flight; what happens meanwhile =======================
        async def flight():
            w = await fresh(b, 'am-flight', mints=(P, B))
            await recv(w, P, 1500)
            await am_set(w, True, my=B)
            async def no_check(route):
                if route.request.method == 'GET': await route.abort(); return
                await route.continue_()
            await w.pg.route(B + '/v1/mint/quote/bolt11/*', no_check)   # (the deposit's state can't be read: the move stays open)
            async def lost(route):
                if route.request.method == 'POST': await route.fetch(); await route.abort(); return   # (the mint has it and says pending; the answer is lost)
                await route.continue_()
            await w.pg.route(P + '/v1/melt/bolt11', lost)
            ls = await w.ev("window.__toasts=[]; NutAutoMove.run('again')")
            out = [t for t in await autos(w) if t['type'] == 'out']
            tl = await w.ev("window.__toasts")
            check('in flight: the toast says it is on its way with the amount, never "nothing moved"', any(re.search(r'[\d,]+ SAT on its way to your mint', t) for t in tl) and not any('nothing moved' in t for t in tl) and ls and ls[0]['a'] and ls[0]['a'][0] > 0, (tl, ls))
            check('in flight: a payment whose answer was lost and that the mint holds as pending is "still in flight", never "didn\'t go through"',
                  ks(ls) and ks(ls)[0] in ('inflight', 'waiting') and out and out[0]['status'] == 'pending', (ls, out))
            errs.extend(w.errs); await w.pg.context.close()
        await section('flight', flight)

        async def during():
            w = await fresh(b, 'am-during')
            s = await fresh(b, 'am-sender', mints=(B,))
            await recv(w, A, 2000); await recv(s, B, 500)
            tok, e = await s.send_ecash(50); check('during: setup: a token from another wallet', tok and not e, e)
            await am_set(w, True, my=B)
            held = []
            async def hold(route):
                if route.request.method == 'POST': held.append((route, await route.fetch())); return
                await route.continue_()
            await w.pg.route(A + '/v1/melt/bolt11', hold)
            await w.ev("window.__toasts=[]; Nutcade.S.prefs.hideAmounts = true; NutAutoMove.run('again'); 1")
            for _ in range(120):
                if held: break
                await w.wait(250)
            await w.ev(f"Nutcade.r8.recv({J(tok)}, 'from a friend')"); await w.wait(800)
            t = await w.ev("Nutcade.S.txs.find(t=>t.type==='in'&&t.amount===50)")
            led = await w.ev("JSON.parse(localStorage.getItem('nutcade:arrivals')||'{}')")
            check('during: a token received while an auto-move is in flight is a normal arrival (announced, not marked a move)',
                  held and t and not t.get('move') and any(x[0] == t['id'] for x in led.get('seen', [])), (t, led.get('seen', [])[-3:]))
            await w.ev(f"Nutcade.S.prefs.piggy = true; Nutcade.S.piggy.saved = {SAT_TOTAL}")
            r = await w.ev(f"Nutcade.r8.sendEcash(10, 'x', null, {J(B)}).then(()=>'sent', e=>e.piggy ? 'piggy' : String(e.message))")
            check('during: a payment meanwhile still stops at the piggy bank', r == 'piggy', r)
            await w.ev("Nutcade.S.prefs.piggy = false; Nutcade.S.piggy.saved = 0")
            route, resp = held[0]; await route.fulfill(response=resp); await w.pg.unroute(A + '/v1/melt/bolt11')
            await w.until("!NutAutoMove.busy()", 90000); await settled(w)
            ts = [x for x in await w.ev("window.__toasts") if 'to your mint' in x]
            check('Hide amounts: the "Moved ... to your mint" toast hides the amount', ts and '•••' in ts[0] and not re.search(r'\d', ts[0]), await w.ev("window.__toasts"))
            errs.extend(w.errs + s.errs); await w.pg.context.close(); await s.pg.context.close()
        await section('during', during)

        # ======================= a crash mid-move =======================
        async def crash():
            w = await fresh(b, 'am-crash')
            await recv(w, A, 2000)
            await am_set(w, True, my=B)
            held = []
            async def hold(route):
                if route.request.method == 'POST':
                    held.append(await route.fetch()); return   # (the mint has the payment and pays it; its answer never reaches the page)
                await route.continue_()
            await w.pg.route(A + '/v1/melt/bolt11', hold)
            await w.ev("NutAutoMove.run('test'); 1")
            for _ in range(120):
                if held: break
                await w.wait(250)
            await w.wait(1500)
            mid = await w.ev("[Nutcade.S.pending.length, Nutcade.S.txs.filter(t=>t.autoMove).length]")
            check('crash: the payment reached the mint, its answer is held, both lines are on record (setup)', held and mid[0] >= 1 and mid[1] == 2, mid)
            await w.pg.unroute(A + '/v1/melt/bolt11')
            await w.pg.reload(); await w.wait(800)
            ok = await settled(w, 90000) and await w.until("NutAutoMove.at() > 0 && !NutAutoMove.busy()", 90000)
            await w.wait(2000)
            au = await autos(w); out = [t for t in au if t['type'] == 'out']; inn = [t for t in au if t['type'] == 'in']
            check('crash: after the reload the journal settles it: one payment done, one deposit claimed at my mint', ok and len(out) == 1 and len(inn) == 1 and out[0]['status'] == 'done' and inn[0]['status'] == 'done' and await bal(w, B) == inn[0]['amount'], (au, await bal(w, B)))
            check('crash: no coin lost or moved twice: only the fee left, nothing in flight, and the start-up run found nothing left to move',
                  out and await total(w) == 2000 - out[0]['fee'] and await w.ev("!Nutcade.S.pending.length && !Nutcade.S.ops.length") and ks(await lines(w)) == ['none'], (await total(w), au, await lines(w)))
            ls = await run(w)
            check('crash: another run moves nothing more', ks(ls) == ['none'] and len(await autos(w)) == 2, ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('crash', crash)

        # ======================= two units in one wallet =======================
        async def units():
            from units_qa import add_account, deposit
            w = await fresh(b, 'am-units', mints=(B,))
            await add_account(w, MULTI); await add_account(w, MULTI, 'usd')
            await deposit(w, MULTI, '1500'); await deposit(w, USD, '20.00')
            check('units: setup: 1,500 SAT and 20.00 USD (2000 cents) at the multi-unit mint', await bal(w, MULTI) == 1500 and await bal(w, USD) == 2000, (await bal(w, MULTI), await bal(w, USD)))
            await am_set(w, True, my=B, mn=2500)
            check('units: the USD account is never offered as my mint', USD not in await w.ev("NutAutoMove.fit()"))
            ls = await run(w)
            check('units: SAT and USD are never added together: 1,500 SAT + 2000 cents is not 2,500 SAT, nothing moves', ks(ls) == ['unit', 'none'] and 'USD' in ls[0]['n'] and not await autos(w), ls)
            await am_set(w, True, mn=1000)
            ls = await run(w); await settled(w)
            check('units: the SAT account moves and the USD account is skipped with a line, its 2000 cents untouched', ks(ls) == ['unit', 'moved'] and await bal(w, USD) == 2000 and await bal(w, MULTI) < 100 and all(t['mint'] != USD for t in await autos(w)), (ls, await bal(w, USD)))
            t0 = await w.ev("NutAutoMove.at()"); await deposit(w, USD, '1.00'); await w.wait(4000)
            check('units: USD arriving starts no run', await w.ev("NutAutoMove.at()") == t0)
            await settings(w)
            check('units: the panel shows the skipped line with the account', 'auto-move moves SAT only' in await w.ev("document.querySelector('#set-automove').innerText"))
            errs.extend(w.errs); await w.pg.context.close()
        await section('units', units)

        # ======================= the spending limit and the PIN =======================
        async def limits():
            w = await fresh(b, 'am-lim')
            await recv(w, A, 1500)
            await set_pin(w)
            await am_set(w, True, my=B)
            e, _ = await set_limits(w, '500', '')
            ls = await run(w)
            check('limit: over the one-payment limit (it would need the PIN): nothing moves, the line says so', not e and ks(ls) == ['per'] and ls[0]['a'][0] > 500 and not await autos(w) and await bal(w, A) == 1500, (e, ls))
            e, _ = await set_limits(w, '', '800')
            ls = await run(w)
            check('limit: over what is left of the day: nothing moves, the line says so', not e and ks(ls) == ['day'] and not await autos(w), (e, ls))
            used0 = await w.ev("Nutcade.r8.spentDay()")
            e, _ = await set_limits(w, '5000', '5000')
            ls = await run(w); await settled(w)
            au = await autos(w); out = [t for t in au if t['type'] == 'out']
            used1 = await w.ev("Nutcade.r8.spentDay()")
            check('limit: under both limits it moves, and the move counts toward the day like any payment', ks(ls) == ['moved'] and out and used1 - used0 == out[0]['amount'] + out[0]['fee'], (ls, used0, used1, au))
            await w.pg.reload(); await w.wait(800); await unlock(w); await w.wait(800)
            check('limit: with a PIN the setting lives in the vault: after a reload and unlock it is still on with my mint', await w.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint]") == [True, B])
            check('limit: the setting is not in plain storage next to the vault', 'amMint' not in (await w.ev("localStorage.getItem('nutcade:prefs')") or ''))
            errs.extend(w.errs); await w.pg.context.close()
        await section('limits', limits)

        # ======================= the duress PIN's wallet =======================
        async def duress():
            e = await fresh(b, 'am-duress')
            await recv(e, A, 1000); await am_set(e, True, my=B); await set_pin(e)
            check('duress: setup: the real wallet has auto-move on with my mint', await e.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint]") == [True, B])
            await settings(e); await e.click('[data-act=duressOpen]'); await e.wait(250)
            await pad(e, PIN); await e.wait(800); await pad(e, DPIN); await e.wait(300); await pad(e, DPIN); await e.until("!!document.querySelector('#duressAmt')", 8000)
            await e.fill('#duressAmt', '100'); await e.click('[data-act=duressMake]'); await e.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await e.ev("Nutcade.closeSheet()")
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            await e.wait(3000)
            check('duress: the duress wallet starts with its own setting off (the real wallet\'s is on) and nothing ran on unlock', await e.ev("Nutcade.S.prefs.amOn") is not True and await e.ev("NutAutoMove.at()") == 0 and not await autos(e))
            for m in (A, B):
                if not await e.ev(f"Nutcade.S.mints.some(m=>m.url==={J(m)})"): await e.add_mint(m)
            await am_set(e, True, my=B)
            before = await bal(e, A)
            await recv(e, A, 1500); await e.wait(5000)
            check('duress: there money arriving moves nothing (the same screens, no run)', not await autos(e) and await bal(e, A) == before + 1500 and await e.ev("NutAutoMove.at()") == 0)
            check('duress: a run asked for directly does nothing', await run(e) is None and not await autos(e))
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(6000)
            check('duress: opening the duress wallet moves nothing either', not await autos(e) and await bal(e, A) == before + 1500)
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            check('duress: the real wallet\'s setting is its own (still on, my mint kept)', await e.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint]") == [True, B])
            errs.extend(e.errs); await e.pg.context.close()
        await section('duress', duress)

        # ======================= backups, restore, reset =======================
        async def restore():
            w = await fresh(b, 'am-restore')
            await am_set(w, True, my=B, mn=1234)
            d = await w.ev("JSON.parse(Nutcade.r8.backupData())")
            check('backup: the backup file carries none of the auto-move settings', not any(k.startswith('am') for k in (d.get('settings') or {})) and 'amMint' not in J(d), list((d.get('settings') or {}).keys()))
            await am_set(w, False)
            d.setdefault('settings', {}).update({'amOn': True, 'amMint': A, 'amMin': 1})
            await w.ev(f"Nutcade.r8.importBackup({J(d)})"); await w.wait(500)
            check('backup: importing a file that carries them changes nothing (not taken from a backup)', await w.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint, Nutcade.S.prefs.amMin]") == [False, B, 1234])
            await am_set(w, True)
            await settings(w); await w.click('[data-act=seedRestore]'); await w.until("!!document.querySelector('#phraseIn')", 8000)
            await w.fill('#phraseIn', ' '.join(['abandon'] * 11 + ['about']))
            await w.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await w.fill('#rmExtra', B)
            await w.click('[data-act=doRestorePhrase]'); await w.until("!document.querySelector('[data-act=doRestorePhrase]')", 90000); await w.wait(800); await w.ev("Nutcade.closeSheet()")
            check('restore: other 12 words turn it off and forget my mint (another wallet)', await w.ev("Nutcade.S.seed.mnemonic.startsWith('abandon')") and await w.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint]") == [False, ''], (await w.ev("[Nutcade.S.seed.mnemonic.slice(0,20), Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint]"), await w.sheet_text(), await w.err()))
            errs.extend(w.errs); await w.pg.context.close()
            r = await fresh(b, 'am-reset')
            await am_set(r, True, my=B, mn=2000)
            await settings(r); await r.click('[data-act=resetAsk]'); await r.until("!!document.querySelector('#confirmWord')", 8000)
            await r.fill('#confirmWord', 'RESET'); await r.click('[data-act=doReset]'); await r.wait(2500)
            left = await r.ev("JSON.parse(localStorage.getItem('nutcade:prefs')||'{}')")
            check('reset: the wallet\'s auto-move settings are gone with it', not any(k in left for k in ('amOn', 'amMint', 'amMin')), {k: left.get(k) for k in ('amOn', 'amMint', 'amMin')})
            await r.create()
            check('reset: a new wallet after it starts with auto-move off', await r.ev("[Nutcade.S.prefs.amOn, Nutcade.S.prefs.amMint, Nutcade.S.prefs.amMin]") == [False, '', 1000])
            errs.extend(r.errs); await r.pg.context.close()
        await section('restore', restore)

        # ======================= five languages =======================
        async def langs():
            page = urllib.request.urlopen(URL, timeout=10).read().decode('utf-8')
            check('langs: the What\'s new list has the auto-move lines and still the P2BK line', all(x.replace("'", "\\'") in page for x in WHATS) and 'Hide who gets it (P2BK, Settings, Privacy)' in page)
            keys = ['unset', 'mybad', 'mydown', 'mylogin', 'none', 'moved', 'waiting', 'noln', 'down', 'login', 'fee', 'per', 'day', 'fail', 'unit', 'inflight', 'myrefused', 'refused', 'dust', 'quote', 'sync', 'backup', 'error']
            extra = ['Moved 1,000 SAT to your mint', 'Moved ••• SAT to your mint', 'Pick a mint', 'Auto-move: nothing moved. See Settings, Auto-move.', 'Type a whole number of SAT, 1 or more.'] + WHATS
            for lang in ('es', 'pt', 'de', 'fr'):
                x = await fresh(b, 'am-' + lang, lang=lang)
                await am_set(x, True, my=B); await x.ev("NutAutoMove.run('test')"); await settings(x)
                st = await x.ev("document.querySelector('#set-automove').innerText")
                eng = await x.ev(f"{J(keys)}.map(k=>NutAutoMove.txt(k,[1000,20]))")
                trd = await x.ev(f"{J(eng + extra)}.map(s=>Nutcade.tr(s))")
                same = [s for s, t in zip(eng + extra, trd) if s == t]
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/Auto-move|auto-move|My mint|my mint|move below|Pick your mint|asks for a login|Lightning deposits now|nothing moved|stay there|on its way to your mint|whole number of SAT|Pick a mint|turned the request|still in flight|waits while|waits until/.test(s))")
                check(f'{lang}: the auto-move panel, every line, the toasts and What\'s new show translated, nothing missing',
                      'Move what I receive' not in st and 'Pick a mint' not in st and "Don't move below" not in st and 'Nothing to move' not in st and not same and not miss, (st[:200], same[:3], miss[:5]))
                errs.extend(x.errs); await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not errs, errs[:5])
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
