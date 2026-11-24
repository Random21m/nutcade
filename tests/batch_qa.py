"""Batched deposits (1.34.0, NUT-29): several paid Lightning deposits waiting at one mint are claimed with one batch request.

Uses the local test mints: 3339 (Mint B, no fees: Nutshell 0.21 advertises nuts[29] for bolt11), 3351 (the same, at most 2
quotes a batch, refused above that), 3352 (no NUT-29 in its info, its batch endpoint refusing) and 3347 (a login, NUT-21/22,
whose batch endpoint asks for a blind auth token like its other money endpoints; login server mock_oidc.py on 3348).
Deposits are made through Receive while the mint's answer about them is held at "UNPAID" (FakeWallet pays every invoice by
itself), so several are paid and waiting at once; then the hold is lifted and the app is reopened (its start-up check), as
after paying several invoices while NUTCADE was closed. Every request to the mint is logged and counted.

The grid: 3 paid -> one batch request, one history line each, the exact balance; more than the mint's max_batch_size -> in
chunks (a lone one left over claimed on its own); paid and unpaid mixed (only the paid ones batched, the other claimed on its
own later); a batch refused (not paid, not supported, unit mismatch: each deposit then claimed on its own, once, and no
second batch while the refusal holds); the batch's answer lost (recovered from its counters after a reload, and in the same
round without one; never twice); two devices with one seed (the same counters, and different ones): nothing counted twice
on either device, nothing lost between them; a mint without NUT-29 (single requests exactly as 1.33.0); a mint with a login,
logged in (one BAT for the batch), logged out (no request, nothing lost, all in once after logging in) and refusing the
batch behind "Blind authentication failed" (asked again with a fresh BAT, then each on its own); NUT-20 locked deposits
(npub.cash) batched with their signatures; 999 / 1,000 / 1,234,567 and the amounts shown in all five languages.
NOT proven here: a mint other than Nutshell 0.21 (CDK's NUT-29), bolt12 batches (NUTCADE has no bolt12 deposits), and the
browser's Web Locks across real tabs (two contexts here are two devices). BT_ONLY=a,b runs some sections."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL
from auto_move_qa import wallet, fresh
from auth_qa import Spy, login, oidc, mints_tab
from arrive_qa import npc_on, npc_pay

J = json.dumps
B, TWO, NO, AU = 'http://127.0.0.1:3339', 'http://127.0.0.1:3351', 'http://127.0.0.1:3352', 'http://127.0.0.1:3347'
MOCK = 'http://127.0.0.1:3350'
LEDGER = """(u=>{let s=0;for(const t of Nutcade.S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return [s,(Nutcade.S.proofs[u]||[]).reduce((a,p)=>a+p.amount,0)]})"""
BATCH, SINGLE = '/v1/mint/bolt11/batch', '/v1/mint/bolt11'


class Log:
    """every request this page sends to the test mints (kept across reloads): method, mint, path, body"""
    def __init__(s, pg):
        s.reqs = []; pg.on('request', s.on)

    def on(s, r):
        try:
            u = urllib.parse.urlparse(r.url)
            if u.port not in (3339, 3347, 3351, 3352): return
            body = None
            if r.method == 'POST':
                try: body = r.post_data_json
                except Exception: body = None
            s.reqs.append({'m': r.method, 'base': f'{u.scheme}://{u.netloc}', 'p': u.path, 'body': body, 'blind': r.headers.get('blind-auth'), 'r': r})
        except Exception:
            pass

    def mark(s): return len(s.reqs)

    def posts(s, path, base=None, since=0):
        return [x for x in s.reqs[since:] if x['m'] == 'POST' and x['p'] == path and (base is None or x['base'] == base)]

    async def status(s, x):
        try:
            resp = await asyncio.wait_for(x['r'].response(), 15); return resp.status if resp else 0
        except Exception: return 0


async def unpaid(route):
    """the mint's real answer about a quote, but still UNPAID"""
    try:
        r = await route.fetch(); j = await r.json(); j['state'] = 'UNPAID'
        await route.fulfill(response=r, body=J(j))
    except Exception:   # unrouted while in flight: nothing left to hold
        pass


class Hold:
    """holds the mint's answer about its deposits at UNPAID (all of them, or only the quote ids in .only)"""
    def __init__(s, w, url, only=None):
        s.w, s.url, s.only = w, url, only
        s.pat = re.compile(re.escape(url) + r'/v1/mint/quote/bolt11/[A-Za-z0-9_-]+$')

    async def h(s, route):
        qid = route.request.url.rsplit('/', 1)[1]
        if route.request.method == 'GET' and (s.only is None or qid in s.only): await unpaid(route)
        else:
            try: await route.continue_()
            except Exception: pass

    async def on(s): await s.w.pg.route(s.pat, s.h); return s
    async def off(s): await s.w.pg.unroute(s.pat, s.h)


async def deposit(w, n, url):
    """Receive -> Lightning -> n -> Create invoice (the invoice is paid by the fake Lightning); the sheet closed again"""
    await w.use(url); await w.home()
    await w.click('[data-act=receive]'); await w.wait(150)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
    n0 = await w.ev("Nutcade.S.txs.length")
    await w.fill('#amtIn', str(n)); await w.click('[data-act=doLnInvoice]')
    await w.until(f"(Nutcade.S.txs.length > {n0} && !!Nutcade.S.txs[0].quote) || !!((document.querySelector('#sheetErr')||{{}}).innerText||'').trim()", 15000)
    e = await w.err(); await w.ev("Nutcade.closeSheet()"); await w.wait(150)
    return None if e else await w.ev(f"Nutcade.S.txs.length > {n0} ? Nutcade.S.txs[0].quote : null")


async def paid_at_mint(url, qid, ms=10000):
    """until the mint itself says the quote is paid"""
    for _ in range(ms // 250):
        try:
            st = json.loads(urllib.request.urlopen(f'{url}/v1/mint/quote/bolt11/{qid}', timeout=5).read())['state']
            if st in ('PAID', 'ISSUED'): return st
        except Exception: pass
        await asyncio.sleep(0.25)
    return None


async def held_deposits(w, url, amounts, hold=None):
    """deposits paid at the mint and waiting in the app (held UNPAID); returns their quote ids"""
    hold = hold or await Hold(w, url).on()
    ids = []
    for n in amounts: ids.append(await deposit(w, n, url))
    for q in ids:
        if q: await paid_at_mint(url, q)
    return ids, hold


async def lines(w, url): return await w.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(url)}&&t.type==='in').map(t=>[t.quote||'',t.status,t.amount,t.note||''])")
async def bal(w, url): return await w.ev(f"(Nutcade.S.proofs[{J(url)}]||[]).reduce((t,p)=>t+p.amount,0)")
async def ledger(w, url): return await w.ev(LEDGER + f"({J(url)})")
async def open_q(w, url): return await w.ev(f"Nutcade.S.quotes.filter(q=>q.mint==={J(url)}).map(q=>q.quote)")


async def reopen(w, ms=2500):
    """the app closed and opened again (its start-up check runs)"""
    await w.pg.reload(); await w.wait(ms)


async def settled(w, url, ids, ms=30000):
    return await w.until(f"{J(ids)}.every(id=>!Nutcade.S.quotes.some(q=>q.quote===id) && Nutcade.S.txs.some(t=>t.quote===id&&t.status==='done'))", ms)


def per_quote(log, ids, base, since=0):
    """how many times each quote was asked for: in a batch request, and on its own"""
    out = {q: [0, 0] for q in ids}
    for x in log.posts(BATCH, base, since):
        for q in (x['body'] or {}).get('quotes') or []:
            if q in out: out[q][0] += 1
    for x in log.posts(SINGLE, base, since):
        q = (x['body'] or {}).get('quote')
        if q in out: out[q][1] += 1
    return out


async def shown(w, amounts, lang):
    """the history tab shows each amount in the language's number format"""
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(300)
    txt = await w.ev("document.body.innerText")
    want = await w.ev(f"{J(amounts)}.map(n=>new Intl.NumberFormat(Nutcade.locale(),{{useGrouping:'always'}}).format(n))")
    miss = [x for x in want if x not in txt]
    await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(150)
    return not miss, (lang, want, miss)


async def section(name, fn):
    only = [x for x in os.environ.get('BT_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


def mint_info(url): return json.loads(urllib.request.urlopen(url + '/v1/info', timeout=10).read())


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        errs = []

        async def mints():
            nb, n2, nn = (mint_info(u).get('nuts', {}) for u in (B, TWO, NO))
            check('setup: Mint B advertises NUT-29 for bolt11, the two-quote mint max_batch_size 2, the third mint no NUT-29',
                  'bolt11' in (nb.get('29') or {}).get('methods', []) and (n2.get('29') or {}).get('max_batch_size') == 2 and '29' not in nn, (nb.get('29'), n2.get('29'), nn.get('29')))
        await section('mints', mints)

        # ======================= 3 paid -> one batch request =======================
        async def three():
            w = await fresh(b, 'bt-three', mints=(B,)); log = Log(w.pg)
            amts = [999, 1000, 1234567]
            ids, hold = await held_deposits(w, B, amts)
            check('three: setup: 3 deposits paid at the mint, waiting in the app', all(ids) and len(await open_q(w, B)) == 3 and await bal(w, B) == 0, ids)
            m0 = log.mark(); await hold.off(); await reopen(w)
            ok = await settled(w, B, ids)
            pq, bat = per_quote(log, ids, B, m0), log.posts(BATCH, B, m0)
            check('three: one batch request for the three (no single mint request), answered by the mint',
                  ok and len(bat) == 1 and sorted(bat[0]['body']['quotes']) == sorted(ids) and all(v == [1, 0] for v in pq.values()) and await log.status(bat[0]) == 200, (ok, pq, [x['body'] and x['body'].get('quotes') for x in bat]))
            ls = await lines(w, B)
            check('three: one history line per deposit, each with its own amount, done', sorted([l[2] for l in ls if l[1] == 'done']) == sorted(amts) and len(ls) == 3 and set(l[0] for l in ls) == set(ids), ls)
            check('three: the balance is exactly 999 + 1,000 + 1,234,567 (and the history adds up to it)', await bal(w, B) == sum(amts) and (await ledger(w, B)) == [sum(amts)] * 2, (await bal(w, B), await ledger(w, B)))
            await reopen(w); await w.wait(2000)
            check('three: reopened: nothing claimed again, the balance the same, no request for them', await bal(w, B) == sum(amts) and len(log.posts(BATCH, B, m0)) == 1 and not log.posts(SINGLE, B, m0) and len(await lines(w, B)) == 3)
            ok, d = await shown(w, amts, 'en'); check('three: en: the amounts shown as 999 / 1,000 / 1,234,567', ok, d)
            errs.extend(w.errs); await w.pg.context.close()
        await section('three', three)

        # ======================= more than max_batch_size -> chunks =======================
        async def chunks():
            w = await fresh(b, 'bt-chunks', mints=(TWO,), lang='es'); log = Log(w.pg)
            amts = [999, 1000, 1234567, 21, 5]
            ids, hold = await held_deposits(w, TWO, amts)
            m0 = log.mark(); await hold.off(); await reopen(w)
            ok = await settled(w, TWO, ids)
            bat = log.posts(BATCH, TWO, m0); pq = per_quote(log, ids, TWO, m0)
            sizes = sorted(len(x['body']['quotes']) for x in bat)
            st = [await log.status(x) for x in bat]
            check('chunks: 5 deposits at a mint taking 2 a batch: two batches of 2 (every one answered), the fifth on its own, each deposit asked for once',
                  ok and sizes == [2, 2] and st == [200, 200] and sorted(map(tuple, pq.values())) == [(0, 1), (1, 0), (1, 0), (1, 0), (1, 0)], (ok, sizes, st, pq))
            check('chunks: five lines, exact balance', sorted(l[2] for l in await lines(w, TWO)) == sorted(amts) and await bal(w, TWO) == sum(amts) and (await ledger(w, TWO)) == [sum(amts)] * 2, await lines(w, TWO))
            ok, d = await shown(w, amts, 'es'); check('chunks: es: the amounts in Spanish number format', ok, d)
            errs.extend(w.errs); await w.pg.context.close()
        await section('chunks', chunks)

        # ======================= paid and unpaid mixed =======================
        async def mixed():
            w = await fresh(b, 'bt-mixed', mints=(B,), lang='pt'); log = Log(w.pg)
            amts = [300, 400, 500, 600]
            ids, hold = await held_deposits(w, B, amts)
            late = await Hold(w, B, only={ids[1]}).on()   # (one still unpaid as far as the app can tell)
            m0 = log.mark(); await hold.off(); await reopen(w)
            ok = await settled(w, B, [ids[0], ids[2], ids[3]])
            bat = log.posts(BATCH, B, m0)
            check('mixed: 3 paid and 1 unpaid: one batch of the 3 paid, the unpaid one left waiting (not asked for)',
                  ok and len(bat) == 1 and sorted(bat[0]['body']['quotes']) == sorted([ids[0], ids[2], ids[3]]) and per_quote(log, [ids[1]], B, m0)[ids[1]] == [0, 0] and ids[1] in await open_q(w, B), (ok, [x['body']['quotes'] for x in bat]))
            check('mixed: the balance is the three paid ones', await bal(w, B) == 1400, await bal(w, B))
            m1 = log.mark(); await late.off()
            ok = await settled(w, B, [ids[1]], 30000)
            check('mixed: once paid, the fourth is claimed on its own (no batch of one), exact balance, four lines',
                  ok and not log.posts(BATCH, B, m1) and per_quote(log, [ids[1]], B, m1)[ids[1]] == [0, 1] and await bal(w, B) == 1800 and (await ledger(w, B)) == [1800, 1800], (ok, await bal(w, B)))
            ok, d = await shown(w, amts, 'pt'); check('mixed: pt: the amounts in Portuguese number format', ok, d)
            errs.extend(w.errs); await w.pg.context.close()
        await section('mixed', mixed)

        # ======================= a batch refused -> each on its own, once =======================
        async def refused():
            for name, status, body, lang in (('not paid', 400, {'detail': 'quote not paid', 'code': 20001}, 'de'),
                                              ('not supported', 404, {'detail': 'Not Found'}, 'fr'),
                                              ('unit mismatch', 400, {'detail': 'quote unit does not match output unit', 'code': 11005}, 'en')):
                w = await fresh(b, 'bt-ref', mints=(B,), lang=lang); log = Log(w.pg)
                amts = [999, 1000, 1234567]
                ids, hold = await held_deposits(w, B, amts)
                pat = re.compile(re.escape(B) + '/v1/mint/bolt11/batch$')
                async def no(route, status=status, body=body):
                    try:
                        if route.request.method != 'POST': await route.continue_(); return
                        await route.fulfill(status=status, headers={'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}, body=J(body))
                    except Exception: pass
                await w.pg.route(pat, no)
                m0 = log.mark(); await hold.off(); await reopen(w)
                ok = await settled(w, B, ids)
                pq = per_quote(log, ids, B, m0)
                check(f'refused ({name}): the batch tried once, then each deposit claimed on its own, once', ok and len(log.posts(BATCH, B, m0)) == 1 and all(v == [1, 1] for v in pq.values()), (ok, pq))
                check(f'refused ({name}): three lines, exact balance, nothing stranded', sorted(l[2] for l in await lines(w, B)) == sorted(amts) and await bal(w, B) == sum(amts) and (await ledger(w, B)) == [sum(amts)] * 2 and not await open_q(w, B), (await lines(w, B), await bal(w, B)))
                # more deposits paid while the refusal still holds: no second batch, each on its own
                ids2, hold2 = await held_deposits(w, B, [10, 20])
                m1 = log.mark(); await hold2.off()   # (the app stays open: its 8-second check finds them)
                ok = await settled(w, B, ids2)
                check(f'refused ({name}): two more right after (the app still open): no second batch while the refusal holds, each on its own, exact balance',
                      ok and not log.posts(BATCH, B, m1) and all(v == [0, 1] for v in per_quote(log, ids2, B, m1).values()) and await bal(w, B) == sum(amts) + 30, (ok, per_quote(log, ids2, B, m1)))
                ok, d = await shown(w, amts, lang); check(f'refused ({name}): {lang}: the amounts in its number format', ok, d)
                errs.extend(w.errs); await w.pg.context.close()
        await section('refused', refused)

        # ======================= the batch's answer lost =======================
        async def lost():
            for mode in ('reload', 'same round'):
                w = await fresh(b, 'bt-lost', mints=(B,)); log = Log(w.pg)
                amts = [999, 1000, 1234567]
                ids, hold = await held_deposits(w, B, amts)
                st = {'lost': 0}
                pat = re.compile(re.escape(B) + '/v1/mint/bolt11/batch$')
                async def lose(route):
                    try:
                        if route.request.method != 'POST': await route.continue_(); return
                        await route.fetch()   # the mint signs ...
                        st['lost'] += 1; await route.abort('connectionreset')   # ... and the answer never arrives
                    except Exception: pass
                await w.pg.route(pat, lose)
                if mode == 'reload':
                    # after the lost answer, the app sees the deposits as unpaid until it is reopened
                    gate = {'on': False}
                    gpat = re.compile(re.escape(B) + r'/v1/mint/quote/bolt11/[A-Za-z0-9_-]+$')
                    async def after(route):
                        if gate['on'] or st['lost']:
                            gate['on'] = True; await unpaid(route)
                        else:
                            try: await route.continue_()
                            except Exception: pass
                    await w.pg.route(gpat, after)
                m0 = log.mark(); await hold.off(); await reopen(w)
                if mode == 'reload':
                    await w.wait(6000)
                    check('lost (reload): setup: the batch reached the mint, its answer lost, the deposits still waiting in the app', st['lost'] == 1 and len(await open_q(w, B)) == 3 and await bal(w, B) == 0, (st, await open_q(w, B), await bal(w, B)))
                    await w.pg.unroute(gpat, after); await w.pg.unroute(pat, lose)
                    await reopen(w)
                ok = await settled(w, B, ids)
                pq = per_quote(log, ids, B, m0)
                check(f'lost ({mode}): recovered from the batch\'s counters: three lines with their amounts, exact balance, no mint request sent again',
                      ok and st['lost'] == 1 and all(v == [1, 0] for v in pq.values()) and sorted(l[2] for l in await lines(w, B)) == sorted(amts) and await bal(w, B) == sum(amts) and (await ledger(w, B)) == [sum(amts)] * 2,
                      (mode, ok, st, pq, await lines(w, B), await bal(w, B)))
                await reopen(w); await w.wait(2500)
                check(f'lost ({mode}): reopened again: nothing counted twice', await bal(w, B) == sum(amts) and len(await lines(w, B)) == 3 and (await ledger(w, B)) == [sum(amts)] * 2)
                errs.extend(w.errs); await w.pg.context.close()
        await section('lost', lost)

        # ======================= two devices, one seed =======================
        async def two():
            for bump in (0, 40):
                w = await fresh(b, 'bt-two', mints=(B,))
                await deposit(w, 100, B); await w.until(f"(Nutcade.S.proofs[{J(B)}]||[]).reduce((t,p)=>t+p.amount,0) >= 100", 20000)   # (coins first: the counters are in use)
                amts = [999, 1000, 1234567]
                ids, hold = await held_deposits(w, B, amts)
                ls = json.loads(await w.ev("JSON.stringify(Object.fromEntries(Object.keys(localStorage).filter(k=>k.startsWith('nutcade:')).map(k=>[k,localStorage.getItem(k)])))"))
                if bump:
                    c = json.loads(ls['nutcade:counters']); ls['nutcade:counters'] = J({k: v + bump for k, v in c.items()})
                ctx = await b.new_context(viewport={'width': 390, 'height': 844})
                await ctx.add_init_script(f"if(!sessionStorage.getItem('x')){{sessionStorage.setItem('x',1); const d={J(ls)}; for(const k in d) localStorage.setItem(k,d[k]);}}")
                pg = await ctx.new_page(); d = W(pg, 'bt-two-b'); pg.on('pageerror', lambda e, d=d: d.errs.append('PAGEERROR ' + str(e)))
                h2 = await Hold(d, B).on()
                await pg.goto(URL); await d.wait(1500)
                l1, l2 = Log(w.pg), Log(d.pg)
                await hold.off(); await h2.off()
                await asyncio.gather(w.pg.reload(), d.pg.reload())
                await asyncio.gather(settled(w, B, ids, 40000), settled(d, B, ids, 40000))
                await w.wait(3000)
                st = [json.loads(urllib.request.urlopen(f'{B}/v1/mint/quote/bolt11/{q}', timeout=5).read())['state'] for q in ids]
                b1, b2 = await bal(w, B), await bal(d, B)
                allp = {p['secret']: p for p in (await w.ev(f"Nutcade.S.proofs[{J(B)}]")) + (await d.ev(f"Nutcade.S.proofs[{J(B)}]"))}
                union = sum(p['amount'] for p in allp.values())
                g1, g2 = await ledger(w, B), await ledger(d, B)
                tag = 'same counters' if not bump else 'counters apart'
                check(f'two ({tag}): the mint issued every deposit once', st == ['ISSUED'] * 3, st)
                check(f'two ({tag}): on each device the history adds up to its balance, and no device holds more than was paid',
                      g1[0] == g1[1] and g2[0] == g2[1] and b1 <= sum(amts) + 100 and b2 <= sum(amts) + 100, (g1, g2))
                check(f'two ({tag}): nothing lost between them: the two devices\' coins together are exactly what was paid', union == sum(amts) + 100, (union, b1, b2))
                check(f'two ({tag}): each deposit has one line on each device (never two)', all(sum(1 for l in ls_ if l[0] == q) == 1 for ls_ in (await lines(w, B), await lines(d, B)) for q in ids))
                for x in (w, d): errs.extend(x.errs); await x.pg.context.close()
        await section('two', two)

        # ======================= a mint without NUT-29: as 1.33.0 =======================
        async def nonut():
            w = await fresh(b, 'bt-no', mints=(NO,)); log = Log(w.pg)
            amts = [999, 1000, 1234567]
            ids, hold = await held_deposits(w, NO, amts)
            m0 = log.mark(); await hold.off(); await reopen(w)
            ok = await settled(w, NO, ids)
            rq = log.reqs[m0:]
            paths = sorted(set((x['m'], re.sub(r'/[A-Za-z0-9_-]{20,}$', '/<id>', x['p'])) for x in rq))
            pq = per_quote(log, ids, NO, m0)
            check('no NUT-29: each deposit claimed on its own (one mint request each, as 1.33.0), never a batch or a batch check',
                  ok and all(v == [0, 1] for v in pq.values()) and not any('batch' in x['p'] or x['p'].endswith('/check') for x in rq), (ok, pq, paths))
            seq = [(x['m'], 'GET' if x['m'] == 'GET' else x['body'].get('quote')) for x in rq if x['p'].startswith('/v1/mint/') and x['p'] != '/v1/mint/quote/bolt11']
            each = all(any(s == ('POST', q) for s in seq) and seq.index(('POST', q)) > 0 for q in ids)
            check('no NUT-29: the requests are only 1.33.0\'s kinds (info, keys, quote state, mint, websocket), each mint request after a state check',
                  each and set(p_ for m_, p_ in paths) <= {'/v1/info', '/v1/keysets', '/v1/keys', '/v1/keys/<id>', '/v1/mint/quote/bolt11/<id>', '/v1/mint/bolt11', '/v1/ws', '/v1/checkstate', '/v1/restore'}, paths)
            check('no NUT-29: three lines, exact balance', await bal(w, NO) == sum(amts) and (await ledger(w, NO)) == [sum(amts)] * 2)
            errs.extend(w.errs); await w.pg.context.close()
        await section('nonut', nonut)

        # ======================= a mint with a login =======================
        async def auth():
            oidc('/test/reset')
            w = await fresh(b, 'bt-auth', mints=(AU,)); await login(w); await w.ev("Nutcade.closeSheet()")
            log = Log(w.pg); spy = Spy(w.pg)
            amts = [999, 1000, 1234567]
            ids, hold = await held_deposits(w, AU, amts)
            m0, s0 = log.mark(), spy.mark(); await hold.off(); await reopen(w)
            ok = await settled(w, AU, ids)
            bat = log.posts(BATCH, AU, m0); rep = await spy.report(s0)
            check('auth (logged in): one batch request carrying one blind auth token, answered; nothing on its own',
                  ok and len(bat) == 1 and bat[0]['blind'] and await log.status(bat[0]) == 200 and all(v == [1, 0] for v in per_quote(log, ids, AU, m0).values()), (ok, len(bat), per_quote(log, ids, AU, m0)))
            check('auth (logged in): every protected request with exactly one BAT, none used twice, none sent where not asked', not rep['no_bat'] and not rep['twice'] and not rep['unprot_bat'], rep)
            check('auth (logged in): exact balance, three lines', await bal(w, AU) == sum(amts) and (await ledger(w, AU)) == [sum(amts)] * 2)
            # logged out (no BATs left): nothing is sent, nothing lost; after logging in, all of it once
            ids2, hold2 = await held_deposits(w, AU, [10, 20, 30])
            await mints_tab(w); await w.click(f'[data-act=authLogout][data-url="{AU}"]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
            m1, s1 = log.mark(), spy.mark(); await hold2.off(); await reopen(w); await w.wait(5000)
            rep = await spy.report(s1)
            check('auth (logged out): no batch and no mint request sent without a BAT; the deposits still waiting, nothing booked',
                  not log.posts(BATCH, AU, m1) and not rep['no_bat'] and sorted(await open_q(w, AU)) == sorted(ids2) and await bal(w, AU) == sum(amts), (len(log.posts(BATCH, AU, m1)), rep['no_bat'], await open_q(w, AU)))
            await login(w); await w.ev("Nutcade.closeSheet()")
            ok = await settled(w, AU, ids2)
            pq = per_quote(log, ids2, AU, m1)
            check('auth (logged in again): the three come in once (one batch), exact balance', ok and all(v == [1, 0] for v in pq.values()) and await bal(w, AU) == sum(amts) + 60 and (await ledger(w, AU))[0] == sum(amts) + 60, (ok, pq, await bal(w, AU)))
            # refused behind "Blind authentication failed": asked once more with a fresh BAT, then each on its own
            ids3, hold3 = await held_deposits(w, AU, [7, 8, 9])
            pat = re.compile(re.escape(AU) + '/v1/mint/bolt11/batch$')
            bent = []
            async def bend(route):
                j = None
                try:
                    if route.request.method == 'POST':
                        j = json.loads(route.request.post_data or 'null'); j['quote_amounts'][0] = int(j['quote_amounts'][0]) + 1   # (the mint refuses it)
                except Exception as e_: bent.append(repr(e_)[:100]); j = None
                try:
                    if j is None: await route.continue_()
                    else: bent.append('bent'); await route.continue_(post_data=J(j))
                except Exception as e_: bent.append(repr(e_)[:100])
            await w.pg.route(pat, bend)
            m2, s2 = log.mark(), spy.mark(); await hold3.off(); await reopen(w)
            ok = await settled(w, AU, ids3)
            bat = log.posts(BATCH, AU, m2); stb = [await log.status(x) for x in bat]; rep = await spy.report(s2)
            check('auth (masked refusal): the batch refused (with a fresh BAT once more), then each deposit on its own, once, exact balance',
                  ok and 1 <= len(bat) <= 2 and all(s_ >= 400 for s_ in stb) and all(v[1] == 1 for v in per_quote(log, ids3, AU, m2).values()) and await bal(w, AU) == sum(amts) + 60 + 24, (ok, stb, bent, per_quote(log, ids3, AU, m2), await bal(w, AU)))
            check('auth (masked refusal): every protected request with one BAT, none used twice', not rep['no_bat'] and not rep['twice'], rep)
            errs.extend(w.errs); await w.pg.context.close()
        await section('auth', auth)

        # ======================= NUT-20 locked deposits (npub.cash) =======================
        async def locked():
            w = await fresh(b, 'bt-npc', mints=(B,)); log = Log(w.pg)
            pk = await npc_on(w, B)
            pat = re.compile(re.escape(MOCK) + r'/api/v2/wallet/quotes.*')
            async def empty(route):
                try: await route.fulfill(status=200, headers={'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}, body=J({'error': False, 'data': {'quotes': []}, 'metadata': {'total': 0}}))
                except Exception: pass
            await w.pg.route(pat, empty)
            amts = [999, 1000, 1234567]
            res = [await npc_pay(pk, n) for n in amts]
            ids = [r_['quote'] for r_ in res]
            await w.wait(1500)
            check('locked: setup: three locked (NUT-20) payments paid at the mint, none in the app yet', all(ids) and not await open_q(w, B) and await bal(w, B) == 0)
            m0 = log.mark(); await w.pg.unroute(pat, empty); await reopen(w)
            ok = await settled(w, B, ids, 40000)
            bat = log.posts(BATCH, B, m0)
            sig = bat and (bat[0]['body'] or {}).get('signatures')
            check('locked: one batch request with a signature for each locked quote (NUT-20), answered', ok and len(bat) == 1 and sig and len(sig) == 3 and all(sig) and await log.status(bat[0]) == 200, (ok, len(bat), sig))
            check('locked: three "Lightning address" lines, exact balance', sorted(l[2] for l in await lines(w, B) if l[3] == 'Lightning address') == sorted(amts) and await bal(w, B) == sum(amts) and (await ledger(w, B)) == [sum(amts)] * 2, await lines(w, B))
            errs.extend(w.errs); await w.pg.context.close()
        await section('locked', locked)

        check('end: no page errors', not errs, errs[:5])
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
