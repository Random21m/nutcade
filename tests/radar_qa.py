"""Mint reliability from MintRadar (1.24.0): optional (off by default), one request for the whole list, a Reliable / Shaky /
Mint down label on the Mints screen and Add mint, Suggested mints, a notice for a mint that holds your sats and is down.
MintRadar itself is a MOCK inside the page (window.fetch answers for mintradar.org; nothing reaches the real service and a
route aborts any request that slips through). Uses the local test mints 3338 and 3339.

Off: zero requests anywhere (every screen, the picker, a reload). On: one list request (the whole list, no mint named in it);
labels from score and status; ETag sent back and a 304 kept; cached (no second request within 5 minutes); 429 (Retry-After),
offline, a 500, garbage and a wrong shape are silent (no label, no error, nothing in the console); data too old shows nothing;
turning it off clears every label at once; Suggested mints (only online, score 80+, sats, NUT-04/05, https, not already added,
not blocked, never an invented address); a hostile name is shown as text; the warning for a mint that holds sats and is down
(and nothing moves); the setting is not in a backup file; the label shows in the three themes with a symbol and a word (never
colour alone) and in five languages with no missing translation; 320 and 1440 px wide with no sideways scroll.
RDR_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, A, B

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
LANGS = ['en', 'es', 'pt', 'de', 'fr']
J = json.dumps
# MintRadar's list as the tests see it; the first two are the wallet's own test mints
def entry(url, **kw):
    e = {'url': url, 'name': None, 'status': 'online', 'score': 95, 'scoreStale': False, 'uptime30dPct': 100, 'units': ['sat'], 'nuts': ['4', '5', '7'],
         'mintDisabled': False, 'meltDisabled': False, 'isTest': False, 'eligibleForRecommendation': True, 'someNewField': {'x': 1}}
    e.update(kw); return e
BASE = [entry(A, score=95), entry(B, score=60)]
SUGG = [entry('https://good1.example', name='Good One', score=99), entry('https://good2.example', name='Good Two', score=90),
        entry('https://low.example', name='Low', score=79), entry('https://offl.example', name='Off', status='offline', score=90, scoreStale=True),
        entry('https://nonut.example', name='NoNut', nuts=['4']), entry('https://usd.example', name='Usd', units=['usd']),
        entry('https://noteligible.example', name='NotEligible', eligibleForRecommendation=False), entry('http://insecure.example', name='Insecure'),
        entry('https://disabled.example', name='Disabled', mintDisabled=True)]
INIT = r"""
window.__i18nMiss = new Set(); window.__mr = []; window.__mock = { mode: 'ok', list: [], etag: '"v1"' }; window.__errs = [];
(() => { const F = window.fetch.bind(window);
  window.fetch = async (u, o) => { const url = String(u && u.url || u);
    if (!/mintradar\.org/.test(url)) return F(u, o);
    const hdr = {}; if (o && o.headers) for (const k of Object.keys(o.headers)) hdr[k.toLowerCase()] = o.headers[k];
    window.__mr.push({ url, h: hdr, opts: Object.keys(o || {}) }); const m = window.__mock;
    if (m.mode === 'offline') throw new TypeError('Failed to fetch');
    if (m.mode === 'hang') return new Promise(() => {});
    if (m.mode === '429') return new Response('{"error":"rate"}', { status: 429, headers: { 'Retry-After': String(m.retry || 30) } });
    if (m.mode === '500') return new Response('oops', { status: 500 });
    if (m.mode === 'garbage') return new Response('<html>not json {{{', { status: 200 });
    if (m.mode === 'shape') return new Response(JSON.stringify({ mints: 'no' }), { status: 200 });
    if (m.mode === 'array') return new Response(JSON.stringify([1, 2, 3]), { status: 200 });
    if (m.mode === 'junk') return new Response(JSON.stringify({ mints: [null, 5, 'x', { url: 5 }, { url: 'https://a.example', status: 'weird', score: 5 }, { url: 'ftp://a', status: 'online', score: 99 }, { url: 'https://s.example', status: 'online', score: 'high' }, { url: 'https://t.example', status: 'online', score: 250 }].concat(m.list) }), { status: 200 });
    if (m.etag && hdr['if-none-match'] === m.etag) return new Response(null, { status: 304 });
    return new Response(JSON.stringify({ methodology: 9, count: m.list.length, mints: m.list }), { status: 200, headers: { ETag: m.etag } });
  };
  window.addEventListener('error', e => window.__errs.push(String(e.message)));
})();
"""
async def wallet(b, lang='en', theme=None, vw=390, vh=844):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    if theme: prefs['theme'] = theme
    await ctx.add_init_script(INIT + "if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    real = []
    async def abort(route): real.append(route.request.url); await route.abort()
    await ctx.route(re.compile(r'https?://([^/]*\.)?mintradar\.org/.*'), abort)
    pg = await ctx.new_page(); w = W(pg, 'rdr'); w.real = real
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def funded(b, **kw):
    w = await wallet(b, **kw); await w.create(); await w.add_mint(A); await w.add_mint(B)
    return w
async def mock(w, **kw): await w.ev(f"Object.assign(window.__mock, {J(kw)})")
async def nreq(w): return await w.ev("window.__mr.length")
async def tab(w, name): await w.ev("Nutcade.closeSheet()"); await w.click(f'[data-act=tab][data-tab={name}]'); await w.wait(250)
async def chips(w): return await w.ev("[...document.querySelectorAll('#app [data-radar] .chip.rdr')].map(e=>e.className.replace('chip rdr ','')+'|'+e.innerText.trim())")
async def turn(w, on):
    await tab(w, 'settings'); cur = await w.ev("document.querySelector('#p_mintRadar').checked")
    if cur != on: await w.click("#p_mintRadar"); await w.wait(500)
async def fresh(w): await w.ev("(()=>{const r=Nutcade.mr.radar; r.next=0; r.at=r.at?r.at-1:0})()")   # (the 5 minutes are over)
async def age(w, ms): await w.ev(f"(()=>{{const r=Nutcade.mr.radar; r.at-= {ms}; r.next=0}})()")
async def section(name, fn):
    only = [x for x in os.environ.get('RDR_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
def clean(w): return not w.errs and not w.real

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        async def off():
            w = await funded(b); await mock(w, list=BASE + SUGG)
            await tab(w, 'settings')
            t = await w.ev("document.querySelector('#set-privacy').innerText"); on = await w.ev("document.querySelector('#p_mintRadar').checked")
            check('off: Settings > Privacy has "Show mint reliability", switched off', 'Show mint reliability' in t and on is False, t[:80])
            check('off: the note says MintRadar sees your phone\'s address, never learns your mints, and is not a safety statement',
                  "sees your phone's internet address" in t and 'does not learn which mints you use' in t and 'not a statement that a mint holds your sats or is safe to deposit into' in t)
            for t_ in ('wallet', 'mints', 'history', 'settings'): await tab(w, t_)
            await tab(w, 'mints'); await w.click('[data-act=pickMint]'); await w.wait(500); await w.ev("Nutcade.closeSheet()")
            await w.ev("location.reload()"); await w.wait(1200); await tab(w, 'mints'); await w.wait(1500)
            check('off: zero requests to MintRadar on every screen, the Add mint sheet and after a reload', await nreq(w) == 0 and not w.real, await nreq(w))
            check('off: no label, no note, no suggestions anywhere', not await chips(w) and 'MintRadar' not in await w.ev("document.querySelector('#app').innerText"))
            check('off: no page errors', not w.errs, w.errs[:2]); await w.pg.context.close()
        await section('off', off)

        async def on():
            w = await funded(b); await mock(w, list=BASE + SUGG)
            await turn(w, True)
            reqs = await w.ev("window.__mr")
            check('on: turning it on makes exactly one request, for the whole list', len(reqs) == 1 and reqs[0]['url'].startswith('https://mintradar.org/api/v1/wallets/mints'), len(reqs))
            check('on: the request names no mint and no wallet detail (only list flags)', all(re.fullmatch(r'(includeOffline|includeArchived|includeUnscored)=true', q) for q in reqs[0]['url'].split('?', 1)[1].split('&')) and '127.0.0.1' not in reqs[0]['url'], reqs[0]['url'])
            check('on: no cookies, no referrer, no stored cache (credentials omit, referrer none, no-store)', set(reqs[0]['opts']) >= {'credentials', 'referrerPolicy', 'cache'})
            await tab(w, 'mints')
            c = await chips(w)
            check('on: the Mints screen labels each mint (score 95 = Reliable, 60 = Shaky), with a symbol and a word', c == ['good|✓ RELIABLE', 'shaky|! SHAKY'], c)
            check('on: the note says this is a health signal and not a statement about your sats', await w.ev("/not a statement that a mint holds your sats or is safe to deposit into/.test(document.querySelector('#app').innerText)"))
            await w.click('[data-act=pickMint]'); await w.wait(400)
            sh = await w.ev("document.querySelector('#layer').innerText")
            names = await w.ev("[...document.querySelectorAll('#radarSugg .uname')].map(e=>e.innerText)")
            check('on: Add mint lists Suggested mints: only online, score 80+, sats, NUT-04/05, eligible, https, with the label', names == ['Good One', 'Good Two'] and 'Suggested mints' in sh, names)
            check('on: a suggested mint is added with the usual Add button, and not listed again after', await w.ev("document.querySelectorAll('#radarSugg [data-act=addMint]').length") == 2)
            check('on: still one request in total (the Add mint sheet reuses the list)', await nreq(w) == 1, await nreq(w)); await w.ev("Nutcade.closeSheet()")
            await tab(w, 'wallet'); await tab(w, 'mints'); await tab(w, 'wallet')
            check('on: still one request after changing screens (cached about 5 minutes)', await nreq(w) == 1, await nreq(w))
            await fresh(w); await tab(w, 'mints'); await w.wait(500); r = await w.ev("window.__mr")
            check('on: after 5 minutes, one more request that sends the ETag back (If-None-Match) and a 304 keeps the labels', len(r) == 2 and r[1]['h'].get('if-none-match') == '"v1"' and await chips(w) == ['good|✓ RELIABLE', 'shaky|! SHAKY'], [x['h'] for x in r])
            await mock(w, etag='"v2"', list=[entry(A, score=95), entry(B, status='degraded', score=60, scoreStale=True)]); await fresh(w); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(500)
            check('on: a changed list changes the labels (a mint that is not online is Mint down, even with a good old score)', await chips(w) == ['good|✓ RELIABLE', 'down|✕ MINT DOWN'], await chips(w))
            await mock(w, list=[entry(A, score=95, meltDisabled=True), entry(B, score=79)]); await fresh(w); await w.ev("Nutcade.mr.radar.etag=''"); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(500)
            check('on: a mint that has switched off minting or melting, or scores under 80, is Shaky', await chips(w) == ['shaky|! SHAKY', 'shaky|! SHAKY'], await chips(w))
            await mock(w, list=[entry(A, score=None), entry(B, score=95, isTest=True)]); await w.ev("Nutcade.mr.radar.etag=''"); await fresh(w); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(500)
            check('on: an online mint with no score yet shows no label', await chips(w) == ['good|✓ RELIABLE'], await chips(w))
            await turn(w, False)
            await tab(w, 'mints'); n0 = await nreq(w); await w.wait(800)
            check('on -> off: every label, note and suggestion is gone at once, and no further request', not await chips(w) and 'MintRadar' not in await w.ev("document.querySelector('#app').innerText") and await nreq(w) == n0)
            check('on: no page errors, nothing real reached the network', clean(w), (w.errs[:2], w.real)); await w.pg.context.close()
        await section('on', on)

        async def failures():
            for mode, kw in (('429', {'retry': 120}), ('500', {}), ('garbage', {}), ('shape', {}), ('array', {}), ('offline', {})):
                w = await funded(b); await mock(w, mode=mode, list=BASE, **kw); await turn(w, True); await tab(w, 'mints'); await w.wait(600)
                c = await chips(w); txt = await w.ev("document.querySelector('#app').innerText"); toast = await w.toast()
                check(f'failure {mode}: silent: no label, no note, no toast, no error text', not c and 'MintRadar' not in txt and not re.search(r'radar|reliab', toast, re.I) and not w.errs, (c, toast, w.errs[:2]))
                n = await nreq(w)
                for t_ in ('wallet', 'mints', 'wallet', 'mints'): await tab(w, t_)
                check(f'failure {mode}: it does not retry in a loop (no new request within 5 minutes)', await nreq(w) == n == 1, (n, await nreq(w)))
                if mode == '429':
                    left = await w.ev("Nutcade.mr.radar.next - Date.now()")
                    check('failure 429: not asked again before the time it told (at least 5 minutes, Retry-After 120 s)', left >= 290000, left)
                await mock(w, mode='ok'); await fresh(w); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(600)
                check(f'failure {mode}: once it works again the labels come', await chips(w) == ['good|✓ RELIABLE', 'shaky|! SHAKY'], await chips(w))
                await w.pg.context.close()
            w = await funded(b); await mock(w, mode='junk', list=BASE); await turn(w, True); await tab(w, 'mints'); await w.wait(500)
            check('junk entries (null, numbers, wrong status, ftp, score as text or 250) are skipped, the good ones still count', await chips(w) == ['good|✓ RELIABLE', 'shaky|! SHAKY'], await chips(w))
            check('junk: no errors', not w.errs, w.errs[:2]); await w.pg.context.close()
            w = await funded(b); await mock(w, list=BASE); await turn(w, True); await tab(w, 'mints')
            await age(w, 25 * 60e3); await mock(w, mode='offline'); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(400)
            check('old data (over 20 minutes) shows nothing: no label', not await chips(w) and 'MintRadar' not in await w.ev("document.querySelector('#app').innerText"))
            await w.pg.context.close()
        await section('failures', failures)

        async def hostile():
            w = await funded(b)
            evil = entry('https://evil.example', name='<img src=x onerror=window.__pwn=1>"\'Evil', score=99)
            ev2 = entry('https://' + 'a' * 400 + '.example', name='Long', score=99)
            await mock(w, list=BASE + [evil, ev2, entry('https://x"><b>.example', name='Quote', score=99)]); await turn(w, True)
            await tab(w, 'mints'); await w.click('[data-act=pickMint]'); await w.wait(500)
            ok = await w.ev("!window.__pwn && !document.querySelector('#radarSugg img') && !document.querySelector('#radarSugg b')")
            nm = await w.ev("[...document.querySelectorAll('#radarSugg .uname')].map(e=>e.innerText)")
            check('hostile: a name or address with markup is shown as plain text and runs nothing', ok and any('Evil' in x for x in nm), nm)
            check('hostile: an address over 300 characters is ignored; the Add button carries the address as plain text', all(len(u) < 100 for u in await w.ev("[...document.querySelectorAll('#radarSugg [data-act=addMint]')].map(e=>e.dataset.url)")))
            check('hostile: no errors', not w.errs, w.errs[:2]); await w.pg.context.close()
        await section('hostile', hostile)

        async def warn():
            w = await funded(b); await w.use(A); await w.receive_ln(500, 'hold'); await w.home()
            await mock(w, list=[entry(A, status='offline', score=90, scoreStale=True), entry(B, score=95)]); await turn(w, True); await tab(w, 'wallet'); await w.wait(400)
            bal0 = await w.ev("Nutcade.S.proofs[%s].reduce((a,p)=>a+p.amount,0)" % J(A)); act0 = await w.ev("Nutcade.S.active")
            t = await w.ev("document.querySelector('#app').innerText")
            check('warn: the wallet screen says a mint that holds your sats is reported down, with the amount', 'MintRadar reports this mint as down' in t and 'You hold 500 SAT there' in t, t[:200])
            await tab(w, 'mints'); check('warn: it also shows on the Mints screen', 'MintRadar reports this mint as down' in await w.ev("document.querySelector('#app').innerText"))
            check('warn: it says nothing moves, and nothing did (same balance, same active mint)', 'NUTCADE moves nothing by itself' in await w.ev("document.querySelector('#app').innerText") and bal0 == 500 and await w.ev("Nutcade.S.active") == act0)
            await mock(w, list=[entry(A, score=95), entry(B, status='offline', score=90)]); await fresh(w); await w.ev("Nutcade.mr.radar.etag='x'"); await tab(w, 'wallet'); await w.wait(600)
            check('warn: a down mint with no sats gives no notice, and the notice goes when the mint is back', 'MintRadar reports' not in await w.ev("document.querySelector('#app').innerText"))
            await w.pg.context.close()
        await section('warn', warn)

        async def backup():
            w = await funded(b); await mock(w, list=BASE); await turn(w, True)
            ok = await w.ev("JSON.stringify(Nutcade.S.prefs).includes('mintRadar')")
            check('backup: the setting is stored as a pref', ok)
            inb = await w.ev("Nutcade.mr.bkSent()")
            check('backup: a backup file never carries it (bkSettings lists other prefs, not mintRadar)', isinstance(inb, list) and 'mintRadar' not in inb, inb)
            ok = 'mintRadar' not in await w.ev("Nutcade.mr.bkAllowed()")
            check('backup: an imported file cannot switch it on (it is not an accepted setting)', ok)
            await w.pg.context.close()
        await section('backup', backup)

        async def look():
            for theme in ('neon', 'amber', 'phosphor'):
                w = await funded(b, theme=theme); await mock(w, list=BASE + [entry(B, status='offline')][:0]); await turn(w, True); await tab(w, 'mints'); await w.wait(300)
                await mock(w, etag='"z"', list=[entry(A, score=95), entry(B, status='offline', score=90)]); await fresh(w); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(500)
                col = await w.ev("[...document.querySelectorAll('#app [data-radar] .chip.rdr')].map(e=>({t:e.innerText.trim(),c:getComputedStyle(e).color,b:getComputedStyle(e).borderTopColor,bg:getComputedStyle(document.body).backgroundColor}))")
                sym = [x['t'] for x in col]
                check(f'look {theme}: each label is a symbol and a word (works without colour)', sym == ['✓ RELIABLE', '✕ MINT DOWN'], sym)
                check(f'look {theme}: the colours come from the theme (the two labels differ, none is the page background)', len(col) == 2 and col[0]['c'] != col[1]['c'] and all(x['c'] != x['bg'] for x in col), col)
                await w.ev("window.scrollTo(0,0)"); await w.pg.screenshot(path=os.path.join(OUT, f'radar-{theme}.png'))
                await w.pg.context.close()
            for vw in (320, 1440):
                w = await funded(b, vw=vw, vh=800); await mock(w, list=BASE + SUGG); await turn(w, True); await tab(w, 'mints'); await w.click('[data-act=pickMint]'); await w.wait(500)
                over = await w.ev("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                check(f'look: {vw}px wide, no sideways scroll on Add mint with suggestions', not over)
                await w.ev("Nutcade.closeSheet()"); await tab(w, 'mints'); over = await w.ev("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                check(f'look: {vw}px wide, no sideways scroll on the Mints screen', not over); await w.pg.context.close()
        await section('look', look)

        async def langs():
            for lang in LANGS:
                w = await funded(b, lang=lang); await mock(w, list=BASE + SUGG[:2] + [entry(A, status='offline')][:0]); await turn(w, True); await tab(w, 'mints'); await w.wait(400)
                await mock(w, etag='"q"', list=[entry(A, score=95, status='offline'), entry(B, score=60)] + SUGG[:2]); await fresh(w); await tab(w, 'wallet'); await tab(w, 'mints'); await w.wait(400)
                scr = await w.ev("document.querySelector('#app').innerText"); await w.click('[data-act=pickMint]'); await w.wait(500)
                sh = await w.ev("document.querySelector('#layer').innerText"); await w.ev("Nutcade.closeSheet()"); await tab(w, 'settings')
                st = await w.ev("document.querySelector('#set-privacy').innerText")
                miss = await w.ev("[...window.__i18nMiss]")
                if lang == 'en':
                    check('lang en: the English texts show', 'MINT DOWN' in scr and 'SHAKY' in scr and 'Suggested mints' in sh and 'Show mint reliability' in st)
                else:
                    eng = [x for x in ('SHAKY', 'MINT DOWN', 'RELIABLE', 'Suggested mints', 'MintRadar reports', 'Show mint reliability', 'health signal') if x in scr + sh + st]
                    check(f'lang {lang}: no English text left on the label, note, suggestions, warning or setting', not eng, eng)
                    check(f'lang {lang}: no missing translation', not [m for m in miss if re.search(r'MintRadar|mint reliab|Reliab|Shaky|SHAKY|Suggested|health signal', m, re.I)], [m for m in miss][:4])
                check(f'lang {lang}: no errors', not w.errs, w.errs[:2]); await w.pg.context.close()
        await section('langs', langs)

        bad = [r for r in results if not r[1]]
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
