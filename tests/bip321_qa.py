"""An amount in the on-chain deposit QR code (1.38.0, BIP321 / BIP21 bitcoin:ADDRESS?amount=BTC).

The address screen of an on-chain deposit (NUT-30) has an optional amount field. Empty: the plain bitcoin:ADDRESS QR as
before. A valid whole-SAT amount: bitcoin:ADDRESS?amount=X, X the BTC decimal written with string math (1 SAT =
0.00000001, 100000000 = 1, no trailing zeros, no exponent, no grouping, always '.'). Anything else (0, negative, a
fraction of a SAT, more than 21 million BTC, outside the mint's on-chain limits) keeps the plain QR and says why.
The amount is only a request (the mint credits whatever arrives): nothing is stored, and the screen says so.

Covered: the formatter against Python's Decimal over edge and random values (and refusing what isn't a whole SAT);
every written link read back by NUTCADE's own scanner (classify/parseBtc) to the same SAT; the screen in English with
the QR decoded from its canvas; 2,500 / 2.500 / 2 500 per language; fiat entry; every invalid case; nothing stored;
reopening from history (field empty); the real flow with the mint's on-chain answers played by the test (Mint B,
3339); the Lightning and on-chain receive screens' units unchanged; the screen at 320/375/430 px in 5 languages.
B3_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, random, re, sys, time
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from sendall_qa import bech32_addr

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
LANGS = ['en', 'es', 'pt', 'de', 'fr']
MAX_SAT = 2100000000000000
ADDR = bech32_addr('bc')
LIMITS = {'min': 1000, 'max': 1000000}

def btc(n):   # the expected text: Decimal, never a float
    s = format(Decimal(n) / Decimal(100000000), 'f')
    return s.rstrip('0').rstrip('.') if '.' in s else s

async def wallet(b, name, lang='en', width=390, fiat=False):
    ctx = await b.new_context(viewport={'width': width, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang}
    if fiat: prefs.update({'fiat': True, 'currency': 'USD'})
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, name)
    # the price service: a fixed $50,000 (CI has the network; a live price would override Nutcade.livePrice)
    try: await ctx.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '50000'}}})))
    except Exception: pass
    await ctx.route_web_socket(re.compile('coinbase'), lambda ws: None)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def section(name, fn):
    only = [x for x in os.environ.get('B3_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])

async def limits(w, lim=LIMITS):
    """the mint's on-chain deposit method, as its info would give it (None: no limits stated)"""
    await w.ev(f"(()=>{{const m=Nutcade.S.mints.find(x=>x.url==={J(M)}); m.methods.mint=m.methods.mint.filter(x=>x.method!=='onchain'); m.methods.mint.push(Object.assign({{method:'onchain',min:null,max:null}},{J(lim or {})}));}})()")
async def address_screen(w, addr=ADDR):
    """a waiting on-chain deposit in the history (no quote kept, so nothing is polled), opened with Show address"""
    await w.ev("Nutcade.closeSheet()")
    tid = await w.ev(f"""(()=>{{const id='b3'+Date.now()+Math.random().toString(36).slice(2,6); Nutcade.S.txs.unshift({{id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'onchain',amount:0,mint:{J(M)},quote:'q-'+id,request:{J(addr)}}});
      const b=document.createElement('button'); b.dataset.act='tx'; b.dataset.id=id; document.body.appendChild(b); b.click(); b.remove(); return id;}})()""")
    await w.until("!!document.querySelector('#layer [data-act=resumeAddr]')", 5000)
    await w.click('#layer [data-act=resumeAddr]'); await w.wait(300)
    return tid
async def amount(w, text):
    """sets the field's text directly (never typed) and lets the QR redraw"""
    await w.ev(f"(()=>{{const e=document.querySelector('#layer #btcAmt'); e.value={J(text)}; e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")
    await w.wait(250)
async def screen(w):
    """what the screen shows: the QR's link (as drawn, decoded from the canvas), the copy buttons, the note, the message"""
    return await w.ev("""(()=>{ const q=document.querySelector('#layer #btcQR'), c=q&&q.querySelector('canvas'); let read=null;
      if (c) { const x=c.getContext('2d'), d=x.getImageData(0,0,c.width,c.height), r=CashuLib.jsQR(d.data,c.width,c.height); read=r?r.data:null; }
      const link=document.querySelector('#layer [data-act=copy][data-link]'), note=document.querySelector('#layer #btcNote'), err=document.querySelector('#layer #btcErr');
      return { field: !!document.querySelector('#layer #btcAmt'), uri: q?q.dataset.uri:null, read,
        addr: (document.querySelector('#layer [data-act=copy]:not([data-link])')||{}).dataset?.text||null,
        link: link&&!link.hidden?link.dataset.text:null, note: note&&!note.hidden?note.innerText:'', err: err?err.innerText:'' }; })()""")
async def uri_is(w, want, tag):
    s = await screen(w)
    check(f'{tag}: the QR is {want}', s['uri'] == want and s['read'] == want, s)
    return s

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al = await wallet(b, 'b3-alice'); await al.create(); await al.add_mint(M); await al.use(M)

        async def fmt():
            edge = [1, 9, 10, 99, 100, 999, 1000, 2100, 2500, 9999, 12345, 99999, 100000, 1234567, 10000000, 99999999, 100000000, 100000001,
                    123456789, 210000000, 1000000000, 2099999999999999, MAX_SAT]
            rnd = random.Random(321); vals = edge + [rnd.randint(1, MAX_SAT) for _ in range(1500)] + [rnd.randint(1, 10 ** rnd.randint(1, 15)) for _ in range(1500)]
            got = await al.ev(f"(v=>v.map(n=>Nutcade.btc.fmt(n)))({J(vals)})")
            bad = [(n, g, btc(n)) for n, g in zip(vals, got) if g != btc(n)]
            check(f'format: {len(vals)} amounts written exactly as Decimal does (1 = 0.00000001, 100000000 = 1, no trailing zeros)', not bad, bad[:5])
            check('format: the table by hand', [got[vals.index(n)] for n in (1, 10, 2100, 100000000, 100000001, MAX_SAT)] == ['0.00000001', '0.0000001', '0.000021', '1', '1.00000001', '21000000'], got[:8])
            check('format: only digits and at most one ".", never an exponent or grouping', all(re.fullmatch(r'\d+(\.\d{0,7}[1-9])?', g or '') for g in got), [g for g in got if not re.fullmatch(r'\d+(\.\d{0,7}[1-9])?', g or '')][:5])
            nope = await al.ev(f"[0,-1,1.5,{MAX_SAT + 1},NaN,Infinity,'5',null,undefined,9007199254740993].map(n=>Nutcade.btc.fmt(n))")
            check('format: 0, negative, a fraction, above 21 million BTC, not a number: no amount at all', all(x is None for x in nope), nope)
            # the whole link, read back by NUTCADE's own scanner
            back = await al.ev(f"((v,a)=>v.map(n=>{{const u=Nutcade.btc.uri(a,n), c=Nutcade.classify(u); return [u, c.kind, c.value, c.amount];}}))({J(vals)},{J(ADDR)})")
            badb = [(n, r) for n, r in zip(vals, back) if r != [f'bitcoin:{ADDR}?amount={btc(n)}', 'btc', ADDR, n]]
            check(f'round trip: all {len(vals)} links read back by NUTCADE\'s scanner (parseBtc) to the same SAT', not badb, badb[:4])
            check('round trip: no amount when there is none (bitcoin:ADDRESS)', await al.ev(f"Nutcade.btc.uri({J(ADDR)},0)") == f'bitcoin:{ADDR}' and await al.ev(f"Nutcade.btc.uri({J(ADDR)},null)") == f'bitcoin:{ADDR}')
        await section('fmt', fmt)

        async def screen_en():
            await limits(al, None); await address_screen(al)
            s = await uri_is(al, f'bitcoin:{ADDR}', 'empty')
            check('empty: the amount field is there, no payment link, no note, no message', s['field'] and s['link'] is None and not s['note'] and not s['err'] and s['addr'] == ADDR, s)
            lab = await al.ev("document.querySelector('label[for=btcAmt]').innerText")
            check('empty: the field is in SAT and optional', 'SAT' in lab and 'optional' in lab.lower(), lab)
            for text, n in [('2500', 2500), ('2,500', 2500), (' 2 500 ', 2500), ('1', 1), ('100000000', 100000000), ('1,234,567', 1234567), (str(MAX_SAT), MAX_SAT)]:
                await amount(al, text)
                s = await uri_is(al, f'bitcoin:{ADDR}?amount={btc(n)}', f'en "{text}"')
                check(f'en "{text}": "Copy payment link" copies that link; the address button still copies the address; the note says it is only a request',
                      s['link'] == f'bitcoin:{ADDR}?amount={btc(n)}' and s['addr'] == ADDR and 'only a request' in s['note'] and 'whatever' in s['note'] and 'ignore' in s['note'] and not s['err'], s)
            for text, why in [('0', 'zero'), ('-5', 'negative'), ('2.5', 'a fraction of a SAT'), ('2,50', 'a bad group'), (str(MAX_SAT + 1), 'above 21 million BTC'),
                              ('99999999999999999999', 'far too large'), ('abc', 'not a number'), ('1e5', 'an exponent')]:
                await amount(al, text)
                s = await uri_is(al, f'bitcoin:{ADDR}', f'invalid "{text}" ({why})')
                check(f'invalid "{text}" ({why}): a plain message, no payment link, no note', s['err'].strip() and s['link'] is None and not s['note'], s)
            # clipboard blocked: the text selected for copying by hand is the payment link, not the address box
            await amount(al, '12,345')
            await al.ev("(()=>{const c=navigator.clipboard;window.__wt=c.writeText;c.writeText=()=>Promise.reject(new Error('blocked'));return 1})()")
            await al.click('#btcLink [data-act=copy]'); await al.wait(250)
            sel = await al.ev("String(getSelection())")
            check('clipboard blocked: "Copy payment link" selects the payment link', sel.strip() == f'bitcoin:{ADDR}?amount=0.00012345', sel)
            await al.click('#layer [data-act=copy]:not([data-link])'); await al.wait(250)
            sel = await al.ev("String(getSelection())")
            check('clipboard blocked: "Copy address" still selects the address', sel.strip() == ADDR, sel)
            await al.ev("(()=>{navigator.clipboard.writeText=window.__wt;getSelection().removeAllRanges();return 1})()")
            await amount(al, '')
            s = await uri_is(al, f'bitcoin:{ADDR}', 'cleared')
            check('cleared: no message left', not s['err'] and s['link'] is None, s)
            # the mint's on-chain limits
            await limits(al); await address_screen(al)
            for text, ok in [('999', False), ('1000', True), ('1,000,000', True), ('1000001', False)]:
                await amount(al, text); n = int(text.replace(',', ''))
                s = await uri_is(al, f'bitcoin:{ADDR}?amount={btc(n)}' if ok else f'bitcoin:{ADDR}', f'limits 1,000-1,000,000 "{text}"')
                if not ok: check(f'limits "{text}": the message names the limit', ('1,000' in s['err'] if n < 1000 else '1,000,000' in s['err']) and 'SAT' in s['err'], s['err'])
            check('screen: no script errors', not al.errs, al.errs[:4])
        await section('screen', screen_en)

        async def stored():
            await limits(al); tid = await address_screen(al)
            before = await al.ev("JSON.stringify([Nutcade.S.txs, Nutcade.S.quotes])")
            ls0 = await al.ev("JSON.stringify(Object.keys(localStorage).sort().map(k=>[k,localStorage.getItem(k)]))")
            await amount(al, '123,457'); await al.wait(1500)
            s = await screen(al)
            after = await al.ev("JSON.stringify([Nutcade.S.txs, Nutcade.S.quotes])")
            ls1 = await al.ev("JSON.stringify(Object.keys(localStorage).sort().map(k=>[k,localStorage.getItem(k)]))")
            check('stored: an amount in the QR changes nothing in the history, the deposits or storage', s['uri'].endswith('amount=0.00123457') and before == after and ls0 == ls1 and '123457' not in ls1 and '0.00123457' not in ls1)
            await al.ev("Nutcade.closeSheet()"); await al.wait(200)
            await al.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='tx'; b.dataset.id={J(tid)}; document.body.appendChild(b); b.click(); b.remove();}})()")
            await al.until("!!document.querySelector('#layer [data-act=resumeAddr]')", 5000); await al.click('#layer [data-act=resumeAddr]'); await al.wait(300)
            s = await uri_is(al, f'bitcoin:{ADDR}', 'reopened from history')
            check('reopened from history: the field is empty again', await al.ev("document.querySelector('#btcAmt').value") == '' and s['link'] is None, s)
        await section('stored', stored)

        async def fiat():
            w = await wallet(b, 'b3-fiat', fiat=True); await w.create(); await w.add_mint(M); await w.use(M)
            await w.ev("Nutcade.livePrice(50000,'USD')"); await limits(w, None); await address_screen(w)
            has = await w.ev("!!document.querySelector('#layer #btcAmt') && !!document.querySelector('#layer #btcAmt').closest('.amtwrap')")
            check('fiat: the field has the switch to your currency', has)
            if has:
                if await w.ev("document.querySelector('#btcAmt').dataset.cur!=='fiat'"): await w.click('#layer .unitbtn'); await w.wait(250)
                await amount(w, '1.00')   # $1 at $50,000 a bitcoin: 2,000 SAT
                await uri_is(w, f'bitcoin:{ADDR}?amount=0.00002', 'fiat $1.00 at $50,000')
                await w.click('#layer .unitbtn'); await w.wait(300)
                s = await uri_is(w, f'bitcoin:{ADDR}?amount=0.00002', 'fiat switched back to SAT')
                check('fiat: switched back the field shows 2000 SAT', await w.ev("document.querySelector('#btcAmt').value") == '2000', s)
            check('fiat: no script errors', not w.errs, w.errs[:4]); await w.pg.context.close()
        await section('fiat', fiat)

        async def flow():
            """Receive -> On-chain -> Get Bitcoin address, with the mint's on-chain answers played by the test"""
            w = await wallet(b, 'b3-flow'); st = {'n': 0}
            async def info(route):
                try:
                    r = await route.fetch(); d = await r.json()
                    n4 = d.setdefault('nuts', {}).setdefault('4', {'methods': [], 'disabled': False})
                    n4.setdefault('methods', []).append({'method': 'onchain', 'unit': 'sat', 'min_amount': 1000, 'max_amount': 1000000, 'options': {'confirmations': 1}})
                    await route.fulfill(response=r, body=J(d))
                except Exception as e:
                    if 'already handled' not in str(e): raise
            async def quote(route):
                try:
                    rq = route.request
                    if rq.method == 'POST':
                        body = json.loads(rq.post_data or '{}'); st['n'] += 1
                        st['q'] = {'quote': f"b3q{st['n']}x{int(time.time() * 1000)}", 'request': ADDR, 'unit': 'sat', 'expiry': int(time.time()) + 3600,
                                   'pubkey': body.get('pubkey'), 'amount_paid': 0, 'amount_issued': 0}
                    await route.fulfill(status=200, body=J(st.get('q') or {}), headers={'content-type': 'application/json', 'access-control-allow-origin': '*'})
                except Exception as e:
                    if 'already handled' not in str(e): raise
            await w.pg.context.route(M + '/v1/info', info)
            await w.pg.context.route(M + '/v1/mint/quote/onchain**', quote)
            await w.create(); await w.add_mint(M); await w.use(M); await w.home()
            await w.click('[data-act=receive]'); await w.wait(250); await w.click('[data-act=recvMethod][data-m=onchain]'); await w.wait(250)
            t = await w.sheet_text()
            check('flow: the on-chain receive screen is unchanged (limits in SAT, no amount field before the address)', 'Limits: min 1,000, max 1,000,000 SAT.' in t and not await w.ev("!!document.querySelector('#layer #btcAmt')"), t[:300])
            await w.click('#layer [data-act=doOnchainAddr]')
            await w.until("!!document.querySelector('#layer #btcQR canvas')", 15000); await w.wait(200)
            await uri_is(w, f'bitcoin:{ADDR}', 'flow: new address')
            n0 = await w.ev("JSON.stringify([Nutcade.S.txs,Nutcade.S.quotes])")
            await amount(w, '21,000')
            s = await uri_is(w, f'bitcoin:{ADDR}?amount=0.00021', 'flow: 21,000 SAT')
            check('flow: the mint was asked once; the deposit is kept with amount 0, as before', st['n'] == 1 and await w.ev("Nutcade.S.txs[0].amount===0 && Nutcade.S.txs[0].method==='onchain'") and n0 == await w.ev("JSON.stringify([Nutcade.S.txs,Nutcade.S.quotes])"), s)
            await amount(w, '1000001')
            await uri_is(w, f'bitcoin:{ADDR}', 'flow: above the mint\'s on-chain max (from its info)')
            # the Lightning receive screen is unchanged
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=receive]'); await w.wait(250); await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(250)
            lab = await w.ev("(document.querySelector('label[for=amtIn]')||{}).innerText||''")
            check('flow: the Lightning receive screen is unchanged (Amount (SAT), no on-chain amount field)', lab == 'Amount (SAT)' and not await w.ev("!!document.querySelector('#layer #btcAmt')"), lab)
            check('flow: no script errors', not w.errs, w.errs[:4]); await w.pg.context.close()
        await section('flow', flow)

        async def langs():
            nums = {'en': '2,500', 'es': '2.500', 'pt': '2.500', 'de': '2.500', 'fr': '2 500'}
            frac = {'en': '2.5', 'es': '2,5', 'pt': '2,5', 'de': '2,5', 'fr': '2,5'}
            lay = "document.documentElement.scrollWidth > window.innerWidth + 1 || [...document.querySelectorAll('#layer .sheet *')].some(e=>e.getBoundingClientRect().right > window.innerWidth + 1 || (e.scrollWidth>e.clientWidth+1 && /auto|scroll|hidden/.test(getComputedStyle(e).overflowX) && !e.classList.contains('code')))"
            for lang in LANGS:
                x = await wallet(b, 'b3-' + lang, lang, width=320); await x.create(); await x.add_mint(M); await x.use(M)
                await limits(x); await address_screen(x)
                await amount(x, nums[lang])
                s = await uri_is(x, f'bitcoin:{ADDR}?amount=0.000025', f'{lang}: "{nums[lang]}"')
                await amount(x, frac[lang])
                e1 = (await uri_is(x, f'bitcoin:{ADDR}', f'{lang}: "{frac[lang]}" (a fraction of a SAT)'))['err']
                await amount(x, '999'); e2 = (await screen(x))['err']
                await amount(x, nums[lang])
                for width in (320, 375, 430):
                    await x.pg.set_viewport_size({'width': width, 'height': 844}); await x.wait(250)
                    check(f'{lang} {width}px: the address screen with an amount fits', not await x.ev(lay))
                    await amount(x, '999'); check(f'{lang} {width}px: with the limit message it fits', not await x.ev(lay)); await amount(x, nums[lang])
                if lang != 'en':
                    txt = (await x.sheet_text()) + '\n' + e1 + '\n' + e2
                    eng = [p for p in ('only a request', 'whatever actually', 'some wallets ignore', 'Copy payment link', 'Amount (SAT, optional)', 'Send Bitcoin to', 'deposits of at least', 'Type at least', 'with no amount', 'whole numbers') if p.lower() in txt.lower()]
                    miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/amount|request|arrive|payment link|wallet|SAT|QR/i.test(s))")
                    check(f'{lang}: every text on the address screen is translated', not eng and not miss, (eng, miss[:4], txt[:300]))
                    if lang == 'fr': check('fr: French uses "vous"', ' tu ' not in txt.lower() and ' ton ' not in txt.lower() and ' ta ' not in txt.lower(), txt[:300])
                await x.pg.screenshot(path=os.path.join(OUT, f'bip321-{lang}.png'))
                check(f'{lang}: no script errors', not x.errs, x.errs[:4]); await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not al.errs, al.errs[:5])
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
