"""Mint reviews (1.36.0, NIP-87 kind 38000): writing, publishing, editing and deleting your own review of a mint.
Uses the local test mint 3339 and the stand-in Nostr relay (mock_nostr.py, port 3350), which checks every signature,
keeps one kind 38000 per author and d tag (the newer one wins) and honours kind 5 deletions with an "a" tag.

Covered: the button on the report card and on Mints -> Details; the exact event that goes out (kind 38000, the tags
k=38172, d=<the mint's pubkey from /v1/info>, u=<mint url>,"cashu" and, when the mint's kind 38172 announcement is known,
a=38172:<announcer>:<d>,<relay>,"cashu"; content "[N/5] text" as cashu.me writes it; a valid signature by the wallet's
own Nostr key, the one the 12 words give); stars required; the length cap; plain text (control and direction characters
dropped, one line); hostile review text from relays and from your own input shown as text (report card, Mints ->
discovery, your own review); re-publishing replaces (same d); delete sends kind 5 and the report card stops counting
it, even if a relay keeps a copy; your own review counted once; one rating per person; [0/5] and [9/5] ignored;
0 relays accepting is a failure (refused, unreachable), never a success; offline says it needs a connection and sends
nothing; a locked wallet publishes nothing; the duress PIN's wallet never publishes (it answers as relays that don't
answer); the sheet in five languages at 320 px with every text translated.
RV_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from r8_qa import set_pin, unlock, pad, PIN, DPIN

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
LANGS = ['en', 'es', 'pt', 'de', 'fr']

def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def post(path, body): return json.loads(urllib.request.urlopen(urllib.request.Request(MOCK + path, data=J(body).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
def evs(kind, author=None):
    return [e for e in state()['events'] if e['kind'] == kind and (not author or e['pubkey'] == author)]
def pubs(author, kind): return state()['pub_count'].get(f'{author}:{kind}', 0)
def mint_pub(): return json.loads(urllib.request.urlopen(M + '/v1/info', timeout=10).read())['pubkey']

HELPERS = """
window.__rvSign = (sk, kind, tags, content, dt) => CashuLib.finalizeEvent({ kind, created_at: Math.floor(Date.now() / 1000) + (dt || 0), tags, content }, sk);
window.__rvKey = () => crypto.getRandomValues(new Uint8Array(32));
window.__rvWordsKey = w => CashuLib.mnemonicToSeedSync(w).slice(0, 32);
window.__rvPublish = ev => new Promise(r => { const ws = new WebSocket(%s); ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d[0] === 'OK') { try { ws.close(); } catch (e) {} r(d[2]); } }; setTimeout(() => r(false), 5000); });
""" % J(RELAY)
# the five discovery relays (wss://relay.damus.io and the rest) all reach the stand-in relay, for the Mints -> discovery list
REDIRECT = "{ const _W = window.WebSocket; window.WebSocket = class extends _W { constructor(u, p) { super(/^wss:\\/\\//.test(String(u)) ? %s : u, p); } }; }" % J(RELAY)

async def wallet(b, name, lang='en', width=390, redirect=False):
    ctx = await b.new_context(viewport={'width': width, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    await ctx.add_init_script(HELPERS)
    if redirect: await ctx.add_init_script(REDIRECT)
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def section(name, fn):
    only = [x for x in os.environ.get('RV_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def mints_tab(w):
    await w.ev("Nutcade.closeSheet()")
    if await w.ev("!!document.querySelector('[data-act=tab][data-tab=mints]')"): await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200)
async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
async def me(w): return await w.ev("CashuLib.nostrPub(window.__rvWordsKey(Nutcade.S.seed.mnemonic))")
async def report(w, fresh=False):
    """the report card, after its checks (fresh: Check again, which reads Nostr again)"""
    await mints_tab(w)
    await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='reportOpen'; b.dataset.url={J(M)}; {'b.dataset.fresh=1;' if fresh else ''} document.body.appendChild(b); b.click(); b.remove();}})()")
    await w.until("!!document.querySelector('#layer [data-act=reportOpen][data-fresh]')", 20000); await w.wait(200)
    return await w.sheet_text()
async def open_review(w):
    await w.ev("Nutcade.closeSheet()")
    await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='rvOpen'; b.dataset.url={J(M)}; document.body.appendChild(b); b.click(); b.remove();}})()")
    await w.until("!!document.querySelector('#layer #rvForm, #layer #rvMine')", 8000); await w.wait(250)
async def stars(w, n): await w.click(f'#layer [data-act=rvStar][data-n="{n}"]'); await w.wait(80)
async def write(w, text):
    await w.ev(f"(()=>{{const t=document.querySelector('#rvText'); t.value={J(text)}; t.dispatchEvent(new Event('input',{{bubbles:true}}));}})()"); await w.wait(80)
async def publish(w, ms=12000):
    await w.click('#layer [data-act=rvPublish]')
    await w.until("!document.querySelector('#layer [data-act=rvPublish] .spinner') && !document.querySelector('#layer #rvBusy')", ms); await w.wait(300)
    return await w.sheet_text()
def tg(e, k): return [t for t in e['tags'] if t and t[0] == k]

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al = await wallet(b, 'rv-alice'); words = await al.create(); await al.add_mint(M); await al.use(M)
        PK = await me(al); MP = mint_pub(); ctx = {}
        check('setup: the wallet, its mint and the mint\'s pubkey', PK and re.fullmatch(r'0[23][0-9a-f]{64}', MP or ''), (PK, MP))

        async def buttons():
            t = await report(al)
            check('buttons: the report card has "Review this mint"', await al.ev(f"!!document.querySelector('#layer [data-act=rvOpen][data-url=\"{M}\"]')"), t[-300:])
            await mints_tab(al); await al.click(f'[data-act=mintInfo][data-url="{M}"]'); await al.wait(600)
            check('buttons: Mints -> Details has "Review this mint"', await al.ev(f"!!document.querySelector('#layer [data-act=rvOpen][data-url=\"{M}\"]')"))
            await al.click('#layer [data-act=rvOpen]'); await al.until("!!document.querySelector('#layer #rvForm')", 5000)
            txt = await al.sheet_text()
            check('buttons: the sheet has 5 stars, a text box, a preview, one warning line and Publish',
                  await al.ev("document.querySelectorAll('#layer [data-act=rvStar]').length") == 5 and await al.ev("!!document.querySelector('#rvText') && !!document.querySelector('#rvPrev') && document.querySelectorAll('#layer [data-rvwarn]').length===1 && !!document.querySelector('#layer [data-act=rvPublish]')"), txt[:300])
            warn = await al.ev("document.querySelector('#layer [data-rvwarn]').innerText")
            check('buttons: the warning says public, stays on relays, linked to this wallet\'s Nostr identity', all(x in warn.lower() for x in ('public', 'relays', "wallet's nostr identity")), warn)
            check('buttons: nothing is published by opening it', not evs(38000, PK) and pubs(PK, 38000) == 0)
        await section('buttons', buttons)

        async def required():
            await open_review(al); await write(al, 'no stars here'); n0 = pubs(PK, 38000)
            await publish(al)
            e = await al.err()
            check('stars: Publish without stars is refused with a plain line, nothing sent', 'star' in e.lower() and pubs(PK, 38000) == n0 and not evs(38000, PK), e)
            check('stars: the preview waits for the stars', 'pick' in (await al.ev("document.querySelector('#rvPrev').innerText")).lower() or await al.ev("document.querySelector('#rvPrev').innerText.trim()") == '', await al.ev("document.querySelector('#rvPrev').innerText"))
        await section('required', required)

        async def cap():
            await open_review(al); await stars(al, 3)
            mx = await al.ev("+document.querySelector('#rvText').maxLength")
            check('cap: the text box takes at most 250 characters', mx == 250, mx)
            await write(al, 'x' * 251); n0 = pubs(PK, 38000)
            await publish(al); e = await al.err()
            check('cap: 251 characters (set past the box) is refused, nothing sent', '250' in e and pubs(PK, 38000) == n0, e)
            await write(al, 'y' * 250)
            cnt = await al.ev("document.querySelector('#rvCount').innerText")
            check('cap: the counter shows 250/250', '250/250' in cnt, cnt)
        await section('cap', cap)

        async def publish1():
            hostile = 'Fast <img src=x onerror="window.__pwned=1"> & "friendly"‮\u0007\n  second line'
            await open_review(al); await stars(al, 4); await write(al, hostile)
            prev = await al.ev("document.querySelector('#rvPrev').innerText")
            want = '[4/5] Fast <img src=x onerror="window.__pwned=1"> & "friendly" second line'
            check('publish: the preview is exactly what goes out, as text (control and direction characters dropped, one line)', prev.strip() == want and not await al.ev("!!document.querySelector('#rvPrev img')"), prev)
            t0 = int(time.time())
            txt = await publish(al)
            e = (evs(38000, PK) or [None])[-1]
            ctx['e1'] = e
            check('publish: one kind 38000 event on the relay, from the wallet\'s key', e is not None and len(evs(38000, PK)) == 1, len(evs(38000, PK)))
            check('publish: the tags are exactly k=38172, d=<mint pubkey>, u=<mint url>,"cashu" (no announcement known: no a tag)',
                  e and e['tags'] == [['k', '38172'], ['d', MP], ['u', M, 'cashu']], e and e['tags'])
            check('publish: content "[4/5] text", as cashu.me writes it', e and e['content'] == want, e and e['content'])
            ok = await al.ev(f"CashuLib.verifyEvent({J(e)})") if e else False
            check('publish: the signature is valid, the pubkey is the Nostr key the 12 words give', ok and e['pubkey'] == PK and e['pubkey'] == await al.ev(f"CashuLib.nostrPub(window.__rvWordsKey({J(words)}))"), (ok, e and e['pubkey']))
            check('publish: created_at is now', e and abs(e['created_at'] - t0) < 30, e and e['created_at'])
            check('publish: the sheet says how many relays accepted it (1 of 1)', '1 of 1' in txt, txt[-300:])
            check('publish: no markup ran or was made from the text', not await al.ev("window.__pwned") and not await al.ev("!!document.querySelector('#layer img')"))
            mine = await al.ev("document.querySelector('#rvMine') && document.querySelector('#rvMine').innerText")
            check('publish: your review is shown on the sheet as text, with Edit and Delete', mine and '<img' in mine and await al.ev("!!document.querySelector('#layer [data-act=rvEdit]') && !!document.querySelector('#layer [data-act=rvDelAsk]')"), mine)
            st = await al.ev(f"JSON.stringify(Nutcade.rv.mine({J(M)}))")
            check('publish: remembered per mint, without secrets (stars, text, d, time)', st and '"stars":4' in st and words.split()[0] not in st and 'sig' not in st, st)
            await al.pg.reload(); await al.wait(900); await open_review(al)
            mine = await al.ev("(document.querySelector('#rvMine')||{}).innerText||''")
            check('publish: still there after a reload, still as text', '<img' in mine and not await al.ev("!!document.querySelector('#layer img')"), mine)
            t = await report(al)
            check('publish: the report card counts it: 1 Nostr user, 4.0/5 from 1 rating', 'Recommended by 1 Nostr user' in t and '4.0/5 from 1 rating' in t, t)
            t = await report(al, fresh=True)
            check('own: read back from the relay, still counted once (1 user, 1 rating)', 'Recommended by 1 Nostr user' in t and '4.0/5 from 1 rating' in t, t)
        await section('publish', publish1)

        async def replace():
            # the mint's announcement (kind 38172) appears on the relay: one with d = the mint's pubkey, and a bogus one
            ann = await al.ev("Array.from(window.__rvKey())"); bog = await al.ev("Array.from(window.__rvKey())")
            a1 = await al.ev(f"window.__rvSign(new Uint8Array({J(ann)}), 38172, [['d', {J(MP)}], ['u', {J(M)}], ['nuts', '1,2,3,4,5'], ['n', 'regtest']], '')")
            a2 = await al.ev(f"window.__rvSign(new Uint8Array({J(bog)}), 38172, [['d', 'ff'.repeat(33)], ['u', {J(M)}]], '')")
            check('replace: two announcements on the relay', await al.ev(f"window.__rvPublish({J(a1)})") and await al.ev(f"window.__rvPublish({J(a2)})"))
            await report(al, fresh=True)
            e1 = ctx.get('e1')
            await open_review(al); await al.click('#layer [data-act=rvEdit]'); await al.wait(200)
            check('replace: Edit fills in the stars and text you gave', await al.ev("document.querySelector('#layer [data-act=rvStar][data-n=\"4\"]').getAttribute('aria-pressed')") == 'true' and 'second line' in await al.ev("document.querySelector('#rvText').value"))
            await stars(al, 5); await write(al, 'Even better now')
            await al.wait(1100)
            txt = await publish(al)
            es = evs(38000, PK)
            e = es[-1] if es else None
            check('replace: the relay keeps one review (the new one replaced the old: same d)', len(es) == 1 and e['id'] != (e1 or {}).get('id') and tg(e, 'd') == [['d', MP]], [x['id'][:8] for x in es])
            check('replace: content "[5/5] Even better now", newer created_at', e and e['content'] == '[5/5] Even better now' and e1 and e['created_at'] > e1['created_at'], e and (e['content'], e['created_at']))
            check('replace: the a tag names the mint\'s announcement whose d is the mint\'s pubkey, with its relay and "cashu"',
                  e and tg(e, 'a') == [['a', f"38172:{a1['pubkey']}:{MP}", RELAY, 'cashu']], e and e['tags'])
            check('replace: tags in order k, d, u, a', e and [t[0] for t in e['tags']] == ['k', 'd', 'u', 'a'], e and e['tags'])
            t = await report(al, fresh=True)
            check('replace: still counted once, with the new stars (1 user, 5.0/5 from 1 rating)', 'Recommended by 1 Nostr user' in t and '5.0/5 from 1 rating' in t, t)
        await section('replace', replace)

        async def others():
            ks = [await al.ev("Array.from(window.__rvKey())") for _ in range(4)]
            def sign(k, content, d=MP, dt=0, kind=38000):
                return al.ev(f"window.__rvSign(new Uint8Array({J(k)}), {kind}, [['k','38172'],['d',{J(d)}],['u',{J(M)},'cashu']], {J(content)}, {dt})")
            pub = lambda e: al.ev(f"window.__rvPublish({J(e)})")
            await pub(await sign(ks[0], '[3/5] ok'))
            await pub(await sign(ks[1], '[2/5] first', d='aa' * 33, dt=-50)); await pub(await sign(ks[1], '[4/5] second', d='bb' * 33))   # (one person, two events)
            await pub(await sign(ks[2], '[9/5] lies')); await pub(await sign(ks[3], '[0/5] zero <script>window.__pwned=1</script>'))
            t = await report(al, fresh=True)
            # people: you, ks0, ks1 (twice), ks2, ks3 = 5; ratings: you 5, ks0 3, ks1 4 (its newest) = 4.0 from 3
            check('others: one rating per person (their newest), [9/5] and [0/5] ignored, your own once: 5 users, 4.0/5 from 3 ratings',
                  'Recommended by 5 Nostr users' in t and '4.0/5 from 3 ratings' in t, t)
            check('others: no hostile text ran', not await al.ev("window.__pwned"))
        await section('others', others)

        async def discovery():
            d = await wallet(b, 'rv-disc', redirect=True); await d.create()
            k = await d.ev("Array.from(window.__rvKey())")
            ev = await d.ev(f"window.__rvSign(new Uint8Array({J(k)}), 38000, [['k','38172'],['d','cc'.repeat(33)],['u','http://127.0.0.1:3341','cashu']], '[5/5] <img src=x onerror=\"window.__pwned=1\"> ‮great', 0)")
            await d.ev(f"window.__rvPublish({J(ev)})")
            await d.ev("Nutcade.closeSheet()"); await d.click('[data-act=tab][data-tab=wallet]'); await d.wait(100)
            await d.ev("document.querySelector('[data-act=pickMint]').click()"); await d.wait(300)
            await d.click('#layer [data-act=discover]')
            ok = await d.until("/127\\.0\\.0\\.1:3341/.test((document.querySelector('#nostrList')||{}).innerText||'')", 15000); await d.wait(500)
            t = await d.ev("document.querySelector('#nostrList').innerText")
            check('discovery: a hostile review from a relay is shown as text, never as markup', ok and '<img src=x' in t and not await d.ev("!!document.querySelector('#nostrList img')") and not await d.ev("window.__pwned"), t[:300])
            check('discovery: direction-changing characters are dropped from it, and it is never translated', '‮' not in t and await d.ev("!!document.querySelector('#nostrList [data-noi18n][data-rvquote]')"), t[:300])
            await d.pg.context.close()
        await section('discovery', discovery)

        async def delete():
            e = evs(38000, PK)[-1]
            await open_review(al); await al.click('#layer [data-act=rvDelAsk]'); await al.wait(200)
            txt = await al.sheet_text()
            check('delete: it asks first, and says relays that ignore deletions may keep a copy', 'copy' in txt.lower() and await al.ev("!!document.querySelector('#layer [data-act=rvDel]')"), txt[:300])
            await al.click('#layer [data-act=rvDel]')
            await al.until("!document.querySelector('#layer [data-act=rvDel]')", 12000); await al.wait(400)
            dl = [x for x in evs(5, PK) if any(t[0] == 'a' and t[1].startswith('38000:') for t in x['tags'])]
            dx = dl[-1] if dl else None
            check('delete: one kind 5 with a=38000:<pubkey>:<d> and k=38000, signed by the wallet key',
                  dx and dx['tags'] == [['a', f'38000:{PK}:{MP}'], ['k', '38000']] and dx['content'] == '' and dx['created_at'] >= e['created_at'] and await al.ev(f"CashuLib.verifyEvent({J(dx)})"), dx)
            check('delete: the relay no longer has the review', not evs(38000, PK))
            check('delete: removed here too (no own review on the sheet)', await al.ev(f"Nutcade.rv.mine({J(M)})") is None and await al.ev("!!document.querySelector('#layer #rvForm') && !document.querySelector('#layer #rvMine')"))
            t = await report(al, fresh=True)
            check('delete: the report card no longer counts it (4 users, 3.5/5 from 2 ratings)', 'Recommended by 4 Nostr users' in t and '3.5/5 from 2 ratings' in t, t)
            post('/test/inject', {'event': e})   # (a relay that ignored the deletion and kept the old copy)
            t = await report(al, fresh=True)
            check('delete: a copy a relay kept is still not counted', 'Recommended by 4 Nostr users' in t and '3.5/5 from 2 ratings' in t, t)
            await open_review(al)
            check('delete: ... and not shown as your review', not await al.ev("!!document.querySelector('#layer #rvMine')"))
            post('/test/forget', {'ids': [e['id']]})
        await section('delete', delete)

        async def ownrelay():
            # your review published from another device or app with the same 12 words: shown as yours, counted once
            ev = await al.ev(f"window.__rvSign(window.__rvWordsKey({J(words)}), 38000, [['k','38172'],['d',{J(MP)}],['u',{J(M)},'cashu']], '[2/5] from my <b>laptop</b>', 5)")
            await al.ev(f"window.__rvPublish({J(ev)})")
            t = await report(al, fresh=True)
            check('own: a review with your key from another device is counted once (5 users, 3.0/5 from 3)', 'Recommended by 5 Nostr users' in t and '3.0/5 from 3 ratings' in t, t)
            await open_review(al)
            mine = await al.ev("(document.querySelector('#rvMine')||{}).innerText||''")
            check('own: ... shown as your review, as text', 'from my <b>laptop</b>' in mine, mine)
            await al.click('#layer [data-act=rvDelAsk]'); await al.wait(150); await al.click('#layer [data-act=rvDel]')
            await al.until("!document.querySelector('#layer [data-act=rvDel]')", 12000); await al.wait(300)
            check('own: ... and it can be deleted from here', not evs(38000, PK))
        await section('ownrelay', ownrelay)

        async def zero():
            n0 = len(evs(38000, PK))
            post('/test/relay_mode', {'refuse': True, 'kinds': [38000]})
            await open_review(al); await stars(al, 2); await write(al, 'refused'); txt = await publish(al)
            e = await al.err()
            check('zero: a relay that refuses: a failure with the count (0 of 1), never a success', '0 of 1' in e and not await al.ev("!!document.querySelector('#layer #rvResult')") and pubs(PK, 38000) > 0 and len(evs(38000, PK)) == n0, (e, txt[-200:]))
            check('zero: nothing remembered as published', await al.ev(f"Nutcade.rv.mine({J(M)})") is None and not await al.ev("!!document.querySelector('#layer #rvMine')"))
            post('/test/relay_mode', {})
            await al.ev("Nutcade.S.prefs.relays=['ws://127.0.0.1:9/relay']")
            await open_review(al); await stars(al, 2); await write(al, 'unreachable'); await publish(al, 15000)
            e = await al.err()
            check('zero: relays that can\'t be reached: the same failure (0 of 1)', '0 of 1' in e and await al.ev(f"Nutcade.rv.mine({J(M)})") is None, e)
            await al.ev(f"Nutcade.S.prefs.relays=[{J(RELAY)}]")
            # a review on one relay, then deleting it while no relay answers: kept, with the failure
            await open_review(al); await stars(al, 3); await write(al, 'keep me'); await publish(al)
            await al.ev("Nutcade.S.prefs.relays=['ws://127.0.0.1:9/relay']")
            await al.click('#layer [data-act=rvDelAsk]'); await al.wait(150); await al.click('#layer [data-act=rvDel]'); await al.wait(500)
            await al.until("!document.querySelector('#layer [data-act=rvDel] .spinner')", 15000); await al.wait(300)
            e = await al.err()
            check('zero: a delete no relay accepted is a failure, and your review stays', '0 of 1' in e and (await al.ev(f"Nutcade.rv.mine({J(M)})") or {}).get('stars') == 3 and evs(38000, PK), e)
            await al.ev(f"Nutcade.S.prefs.relays=[{J(RELAY)}]")
        await section('zero', zero)

        async def offline():
            n0 = pubs(PK, 38000)
            await al.pg.context.set_offline(True); await al.wait(300)
            await open_review(al)
            if await al.ev("!!document.querySelector('#layer [data-act=rvEdit]')"): await al.click('#layer [data-act=rvEdit]'); await al.wait(150)
            note = await al.ev("(document.querySelector('#rvOff')||{}).innerText||''")
            check('offline: the sheet says publishing needs a connection', 'connection' in note.lower(), note)
            await stars(al, 1); await write(al, 'offline'); await publish(al)
            e = await al.err()
            check('offline: Publish says it needs a connection, nothing sent, nothing queued', 'connection' in e.lower() and pubs(PK, 38000) == n0 and (await al.ev(f"Nutcade.rv.mine({J(M)})") or {}).get('stars') == 3, e)
            await al.pg.context.set_offline(False); await al.wait(1500)
            check('offline: nothing goes out later on its own', pubs(PK, 38000) == n0)
        await section('offline', offline)

        async def words():
            # other 12 words (a restore, a new phrase): a review signed by the old key is no longer yours
            x = await wallet(b, 'rv-words'); await x.create(); await x.add_mint(M); await x.use(M)
            async def users():
                t = await report(x, fresh=True); m = re.search(r'Recommended by (\d+) Nostr users?', t); r_ = re.search(r'from (\d+) ratings?', t)
                return (int(m.group(1)) if m else -1, int(r_.group(1)) if r_ else 0), t
            async def after(label, old_pk):
                new_pk = await me(x)
                check(f'{label}: the wallet now has another Nostr key', new_pk and new_pk != old_pk, (old_pk[:12], (new_pk or '')[:12]))
                check(f'{label}: the old key\'s review is no longer "yours" (nothing remembered, no Your review)', await x.ev(f"Nutcade.rv.mine({J(M)})") is None)
                await open_review(x)
                check(f'{label}: the sheet shows the form, no Your review, no Edit or Delete', await x.ev("!!document.querySelector('#layer #rvForm') && !document.querySelector('#layer #rvMine') && !document.querySelector('#layer [data-act=rvDelAsk]')"))
                n5 = pubs(new_pk, 5)
                r = await x.ev(f"Nutcade.rv.del({J(M)}).then(v => v === null ? 'none' : 'sent', e => e.message)")
                check(f'{label}: nothing can be deleted under the new key: no kind 5 is sent, the old review stays on the relay', r == 'none' and pubs(new_pk, 5) == n5 == 0 and len(evs(38000, old_pk)) == 1, (r, pubs(new_pk, 5)))
                return new_pk
            await open_review(x); await stars(x, 2); await write(x, 'under my first words'); await publish(x)
            pk1 = await me(x)
            check('words: setup: a review under the first words', len(evs(38000, pk1)) == 1)
            u1, _ = await users()
            # restore to other words (Settings -> Restore wallet), scanning only the test mint
            phrase = await x.ev("CashuLib.generateMnemonic(CashuLib.wordlist, 128)")
            await settings(x); await x.click('[data-act=seedRestore]'); await x.until("!!document.querySelector('#phraseIn')", 8000)
            await x.ev("document.querySelectorAll('[data-rmint]').forEach(i => { i.checked = false; })")
            await x.fill('#phraseIn', phrase); await x.fill('#rmExtra', M)
            await x.click('#layer [data-act=doRestorePhrase]')
            await x.until("/SCAN COMPLETE|CONTINUE!/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 60000); await x.ev("Nutcade.closeSheet()")
            pk2 = await after('restore', pk1)
            u2, t2 = await users()
            check('restore: the old review counts once, as someone else\'s (same people and ratings as before)', u2 == u1, (u1, u2, t2[-200:]))
            # a review under the restored words, then Settings -> New recovery phrase
            await open_review(x); await stars(x, 4); await write(x, 'under the restored words'); await publish(x)
            check('words: setup: a review under the restored words', len(evs(38000, pk2)) == 1)
            u3, _ = await users()
            # (New recovery phrase has no button today: its action is pressed as pinguard_qa and backup_qa press it)
            await settings(x); await x.ev("(()=>{const b=document.createElement('button'); b.dataset.act='newSeedAsk'; document.querySelector('#app').appendChild(b); b.click(); b.remove();})()")
            await x.until("!!document.querySelector('#confirmWord')", 8000)
            await x.fill('#confirmWord', 'NEW'); await x.click('#layer [data-act=doNewSeed]'); await x.wait(800)
            await after('new phrase', pk2)
            u4, t4 = await users()
            check('new phrase: the old review counts once, as someone else\'s (same people and ratings as before)', u4 == u3, (u3, u4, t4[-200:]))
            await x.pg.context.close()
        await section('words', words)

        async def locked():
            e = await wallet(b, 'rv-lock'); ew = await e.create(); await e.add_mint(M); await e.use(M)
            EPK = await me(e)
            await set_pin(e)
            await open_review(e); await stars(e, 5); await write(e, 'real wallet'); await publish(e)
            check('locked: setup: the real wallet published its review', len(evs(38000, EPK)) == 1)
            await e.pg.reload(); await e.wait(800)
            n0 = pubs(EPK, 38000)
            r = await e.ev(f"Nutcade.rv.publish({J(M)}, 4, 'while locked').then(()=>'sent', x=>x.message)")
            check('locked: a locked wallet publishes nothing', r != 'sent' and pubs(EPK, 38000) == n0, r)
            await unlock(e, PIN)
            ctx['ed'] = (e, EPK)
        await section('locked', locked)

        async def duress():
            e, EPK = ctx['ed']
            await e.receive_ln(500)
            await settings(e); await e.click('[data-act=duressOpen]'); await e.wait(250)
            await pad(e, PIN); await e.wait(800); await pad(e, DPIN); await e.wait(300); await pad(e, DPIN); await e.until("!!document.querySelector('#duressAmt')", 8000)
            await e.fill('#duressAmt', '100'); await e.click('[data-act=duressMake]'); await e.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await e.ev("Nutcade.closeSheet()")
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            DPK = await e.ev("CashuLib.nostrPub(window.__rvWordsKey(Nutcade.S.seed.mnemonic))")
            n38, nr, nd = len(evs(38000)), pubs(EPK, 38000), pubs(DPK, 38000)
            await open_review(e)
            check('duress: the duress wallet does not show the real wallet\'s review', not await e.ev("!!document.querySelector('#layer #rvMine')"))
            await stars(e, 1); await write(e, 'duress'); t0 = time.time()
            await publish(e, 15000); dt = time.time() - t0
            err = await e.err()
            check('duress: Publish answers as relays that don\'t answer (0 of 1), after as long as they would take', '0 of 1' in err and dt > 5, (err, round(dt, 1)))
            check('duress: nothing published under either identity, nothing remembered', len(evs(38000)) == n38 and pubs(EPK, 38000) == nr and pubs(DPK, 38000) == nd and await e.ev(f"Nutcade.rv.mine({J(M)})") is None)
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            await open_review(e)
            check('duress: back in the real wallet, its review is still there', 'real wallet' in await e.ev("(document.querySelector('#rvMine')||{}).innerText||''"))
            await e.pg.context.close()
        await section('duress', duress)

        async def langs():
            for lang in LANGS:
                x = await wallet(b, 'rv-' + lang, lang, width=320); await x.create(); await x.add_mint(M); await x.use(M)
                await open_review(x)
                lay = "document.documentElement.scrollWidth > window.innerWidth + 1 || [...document.querySelectorAll('#layer .sheet *')].some(e=>e.getBoundingClientRect().right > window.innerWidth + 1 || (e.scrollWidth>e.clientWidth+1 && /auto|scroll|hidden/.test(getComputedStyle(e).overflowX) && e.tagName!=='TEXTAREA'))"
                check(f'{lang} 320px: the review sheet fits', not await x.ev(lay))
                await stars(x, 5); await write(x, 'Lorem ipsum ' * 20); await publish(x)
                check(f'{lang} 320px: with your review on it, it still fits', await x.ev("!!document.querySelector('#layer #rvMine')") and not await x.ev(lay))
                await x.click('#layer [data-act=rvDelAsk]'); await x.wait(200)
                check(f'{lang} 320px: the delete question fits', not await x.ev(lay))
                await x.ev("Nutcade.closeSheet()"); await report(x)
                check(f'{lang} 320px: the report card with its button fits', not await x.ev(lay))
                if lang != 'en':
                    eng = await x.ev("Nutcade.rv.texts()")
                    trd = await x.ev(f"{J(eng)}.map(s=>Nutcade.tr(s))")
                    same = [s for s, t in zip(eng, trd) if s == t]
                    miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/review|relay|star|Nostr|publish|connection/i.test(s))")
                    check(f'{lang}: every review text is translated, nothing missing on screen', eng and not same and not miss, (same[:3], miss[:3]))
                    if lang == 'fr':
                        frt = ' '.join(trd)
                        check('fr: French uses "vous"', (' vous' in frt.lower() or 'votre' in frt.lower()) and ' tu ' not in frt.lower() and ' ton ' not in frt.lower(), frt[:200])
                await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not al.errs, al.errs[:5])
        await al.pg.screenshot(path=os.path.join(OUT, 'review.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
