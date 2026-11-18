"""Printable NUTCADE tokens and the logo in QR codes.

The grid: print 1 and many tokens x a fee and a no-fee mint x both styles (Arcade, Ink saver) x 5 languages; every
QR read back (by the app before printing, and here again from the printed images); claim with NUTCADE and with a
second Cashu wallet (Nutshell's); take back unclaimed; someone else claims first, then take back fails honestly; the
mint down (making, checking, taking back); the spending limit counts printed tokens; backup and restore keep the list
(imported twice, and the 12 words: exactly like normal sent tokens); a crash mid-print books once; the QR logo x
every QR size x the three themes (and None); the print pages rendered as print media and screenshotted; no screen
or page relies on color alone. Uses the local mints (3338 fee, 3339 no fee; other ports with TOK_FEE / TOK_NOFEE /
TOK_NOSTR) and mock_nostr.py. TOK_ONLY=name,name runs some sections."""
import asyncio, json, os, re, subprocess, sys, time
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net

FEE = os.environ.get('TOK_FEE', 'http://127.0.0.1:3338')       # input fees (100 ppk)
NOFEE = os.environ.get('TOK_NOFEE', 'http://127.0.0.1:3339')   # no fees
NOSTR = os.environ.get('TOK_NOSTR', 'http://127.0.0.1:3350')
OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ['en', 'es', 'pt', 'de', 'fr']
PIN = '135791'
# the English sentences that must never show on a non-English page or print (each is translated)
ENGLISH = ['HOW TO CLAIM', 'Whoever scans it first gets the sats', 'SCAN TO CLAIM', 'Print tokens', 'Open any Cashu wallet']
LEDGER = """(u=>{let s=0;for(const t of Nutcade.S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return [s,(Nutcade.S.proofs[u]||[]).reduce((a,p)=>a+p.amount,0)]})"""
PRINTED = "Nutcade.S.txs.filter(t=>t.print)"


async def wallet(b, lang='en', theme=None, vw=390, vh=844):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=True, has_touch=True, accept_downloads=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [NOSTR.replace('http', 'ws') + '/relay'], 'npcHost': NOSTR}
    if theme: prefs['theme'] = theme
    await ctx.add_init_script("window.__i18nMiss=new Set(); window.__printed=0; window.print=()=>{window.__printed++}; if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'tok')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def funded(b, mints, amount=6000, lang='en', theme=None):
    w = await wallet(b, lang, theme); await w.create()
    for m in mints:
        await w.add_mint(m); await w.use(m)
        ok = await w.receive_ln(amount)
        if not ok: raise RuntimeError('funding failed at ' + m)
    return w


async def books(w, mints=(FEE, NOFEE)):
    bad = []
    for m in mints:
        l, p = await w.ev(f"{LEDGER}({json.dumps(m)})")
        if l != p: bad.append((m, l, p))
    return bad


async def open_print(w, mint):
    await w.use(mint); await w.home(); await w.click('[data-act=send]'); await w.wait(150)
    await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('#ptAmt')", 5000)


async def make(w, mint, amount, count, style='arcade', expect_ok=True, ms=180000):
    """the Print tokens screen: amount, how many, style, Next (the cost), Make. Returns (summary, error, batch id)"""
    await open_print(w, mint)
    await w.fill('#ptAmt', str(amount)); await w.fill('#ptCount', str(count))
    await w.click(f'[data-act=ptStyle][data-s={style}]'); await w.wait(80)
    await w.click('[data-act=ptNext]')
    await w.until("!!document.querySelector('[data-act=ptMake]') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'') || !!document.querySelector('#limitLayer')", 20000)
    summary = await w.sheet_text()
    if not await w.ev("!!document.querySelector('[data-act=ptMake]')"):
        return summary, (await w.err()) or await w.ev("(document.querySelector('#limitLayer')||{}).innerText||''"), None
    await w.click('[data-act=ptMake]')
    await w.until("!!document.querySelector('.pt-ready') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'') || !!document.querySelector('#limitLayer')", ms)
    await w.wait(300)
    e = (await w.err()) or await w.ev("(document.querySelector('#limitLayer')||{}).innerText||''")
    bid = await w.ev("(document.querySelector('.pt-ready')||{dataset:{}}).dataset.b||null")
    return summary, e, bid


async def batch(w, bid):
    return await w.ev(f"Nutcade.S.txs.filter(t=>t.print&&t.print.b==={json.dumps(bid)}).sort((a,b)=>a.print.i-b.print.i)")


async def show_print(w, bid, shot=None, style=None):
    """the print pages as the printer gets them (print media), with a screenshot"""
    await w.ev(f"NutTokens.preparePrint({json.dumps(bid)}{', ' + json.dumps(style) if style else ''})"); await w.wait(300)
    vp = w.pg.viewport_size; await w.pg.set_viewport_size({'width': 794, 'height': 1123})   # (an A4 page at 96 dpi)
    await w.pg.emulate_media(media='print'); await w.wait(250)
    info = await w.ev("""(()=>{const P=document.querySelector('#tokPrint'); if(!P) return null;
      const vis=e=>{const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
      const app=document.querySelector('#app'), lay=document.querySelector('#layer');
      const fronts=[...P.querySelectorAll('.pt-front')], backs=[...P.querySelectorAll('.pt-back')], pages=[...P.querySelectorAll('.pt-page')];
      return {vis: vis(P), appHidden: !vis(app) && !(lay.firstChild && vis(lay.firstChild)), fronts: fronts.length, backs: backs.length, pages: pages.length,
        perPage: pages.map(p=>p.querySelectorAll('.pt-card').length), cuts: P.querySelectorAll('.pt-card').length && getComputedStyle(P.querySelector('.pt-card')).borderTopStyle,
        fold: P.querySelectorAll('.pt-fold').length, text: P.innerText, imgs: [...P.querySelectorAll('img.pt-qr')].map(i=>i.src),
        exact: getComputedStyle(P.querySelector('.pt-card')).printColorAdjust || getComputedStyle(P.querySelector('.pt-card')).webkitPrintColorAdjust,
        style: P.className}})()""")
    if shot:
        await w.pg.screenshot(path=os.path.join(OUT, shot), full_page=True)
    await w.pg.emulate_media(media='screen'); await w.pg.set_viewport_size(vp); await w.ev("NutTokens.endPrint()"); await w.wait(100)
    return info


async def read_img(w, src):
    """decode a printed QR image here, with the page's other reader (jsQR), independently of the app's own check"""
    return await w.ev(f"""(async()=>{{const i=new Image(); i.src={json.dumps(src)}; await i.decode(); const c=document.createElement('canvas'); c.width=i.naturalWidth; c.height=i.naturalHeight;
      const x=c.getContext('2d'); x.drawImage(i,0,0); const d=x.getImageData(0,0,c.width,c.height); const r=CashuLib.jsQR(d.data,c.width,c.height); return r?r.data:null}})()""")


async def plist(w):
    """the Printed tokens list: [{id, status text}]"""
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
    await w.click('[data-act=ptList]'); await w.until("!!document.querySelector('.pt-list')", 5000)
    return await w.ev("[...document.querySelectorAll('.pt-row')].map(r=>({id:r.dataset.id, text:r.innerText}))")


def second_wallet(token):
    py = os.environ.get('MINT_PY', sys.executable)
    r = subprocess.run([py, os.path.join(HERE, 'second_wallet.py'), 'receive', token], capture_output=True, text=True, timeout=120)
    try: return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception: return {'ok': False, 'error': (r.stdout + r.stderr)[-300:]}


async def section(name, fn):
    only = [x for x in os.environ.get('TOK_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    print(f'--- {name}', flush=True)
    try: await fn()
    except Exception as e:
        check(f'{name}: ran to the end', False, repr(e)[:300])


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ---------- the Print tokens button and screen ----------
        async def screen():
            w = await funded(b, [NOFEE], 3000)
            await w.home(); await w.click('[data-act=send]'); await w.wait(150)
            check('send: a Print tokens button on the Send screen (ecash)', await w.ev("!!document.querySelector('#layer [data-act=ptOpen]') && /print tokens/i.test(document.querySelector('#layer [data-act=ptOpen]').innerText)"))
            await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('#ptAmt')", 5000)
            t = await w.sheet_text()
            check('screen: amount per token, how many (1-20) and the two styles', await w.ev("!!document.querySelector('#ptAmt') && !!document.querySelector('#ptCount') && document.querySelectorAll('[data-act=ptStyle]').length===2") and 'ARCADE' in t.upper() and 'INK SAVER' in t.upper(), t[:300])
            # not by color alone: the chosen style says so in words / a mark, not just a color
            await w.click('[data-act=ptStyle][data-s=ink]'); await w.wait(80)
            on = await w.ev("[...document.querySelectorAll('[data-act=ptStyle]')].map(b=>[b.dataset.s,b.getAttribute('aria-pressed'),getComputedStyle(b,'::before').content])")
            check('screen: the chosen style is marked with a sign as well as color (aria-pressed + a ✓)', any(x[0] == 'ink' and x[1] == 'true' and '✓' in (x[2] or '') for x in on) and any(x[0] == 'arcade' and x[1] == 'false' and '✓' not in (x[2] or '') for x in on), on)
            for cnt, why in (('0', 'how many'), ('21', 'how many'), ('abc', 'how many')):
                await w.fill('#ptAmt', '100'); await w.fill('#ptCount', cnt); await w.click('[data-act=ptNext]'); await w.wait(250)
                e = await w.err(); check(f'screen: {cnt!r} tokens refused with a reason (1 to 20)', '20' in e and not await w.ev("!!document.querySelector('[data-act=ptMake]')"), e)
            await w.fill('#ptAmt', '0'); await w.fill('#ptCount', '2'); await w.click('[data-act=ptNext]'); await w.wait(250)
            check('screen: an amount of 0 refused', bool(await w.err()), await w.err())
            await w.fill('#ptAmt', '2000'); await w.fill('#ptCount', '2'); await w.click('[data-act=ptNext]'); await w.wait(400)
            e = await w.err(); check('screen: more than the balance refused before anything is made', 'Not enough' in e or 'more than' in e, e)
            check('screen: nothing made by the refusals', await w.ev(f"{PRINTED}.length") == 0 and await w.ev("Nutcade.S.ops.length") == 0)
            await w.pg.context.close()
        await section('screen', screen)

        # ---------- the grid: 1 and many x fee / no fee x both styles x 5 languages ----------
        async def grid():
            for li, lang in enumerate(LANGS):
                w = await funded(b, [FEE, NOFEE], 9000, lang)
                await w.ev("window.__i18nMiss=new Set()")
                for mi, mint in enumerate((FEE, NOFEE)):
                    for ci, count in enumerate((1, 4)):
                        style = ('arcade', 'ink')[(li + mi + ci) % 2]
                        amount = (21, 100, 250, 1000)[(li + 2 * mi + ci) % 4]
                        tag = f'{lang} {"fee" if mint == FEE else "no-fee"} x{count} {style} {amount}'
                        bal0 = await w.bal(mint); n0 = await w.ev("Nutcade.S.txs.length")
                        summary, e, bid = await make(w, mint, amount, count, style)
                        if not bid:
                            check(f'grid {tag}: made', False, e or summary[:200]); continue
                        txs = await batch(w, bid); bal1 = await w.bal(mint)
                        fees = sum(t.get('fee', 0) for t in txs)
                        num = await w.ev(f"Nutcade.fmt({amount})")
                        check(f'grid {tag}: {count} separate tokens, each its own pending ecash line', len(txs) == count and all(t['status'] == 'pending' and t['method'] == 'ecash' and t['amount'] == amount and t['token'].startswith('cashuB') for t in txs) and len({t['token'] for t in txs}) == count, [(t['amount'], t['status']) for t in txs])
                        check(f'grid {tag}: the balance dropped by exactly the tokens plus their fees', bal0 - bal1 == count * amount + fees, (bal0, bal1, fees))
                        check(f'grid {tag}: fee only on the fee mint', (fees > 0) if mint == FEE else (fees == 0), fees)
                        check(f'grid {tag}: the cost shown before making (amount x count, total) in the language', num in summary and (await w.ev(f"Nutcade.fmt({count * amount})")) in summary, summary[:300])
                        ready = await w.sheet_text()
                        check(f'grid {tag}: the fees actually paid shown after making ({fees})', (await w.ev(f"Nutcade.fmt({fees})")) in ready, ready[:300])
                        check(f'grid {tag}: journal closed, history = balance', await w.ev("Nutcade.S.ops.length") == 0 and not await books(w), await books(w))
                        chk = await w.ev("NutTokens.lastCheck")
                        check(f'grid {tag}: every QR read back by the app before printing', bool(chk) and len(chk) == count and all(c['ok'] for c in chk), chk)
                        shot = f'tok-{lang}-{"fee" if mint == FEE else "nofee"}-{count}-{style}.png' if (lang in ('en', 'de') and count == 4) else None
                        info = await show_print(w, bid, shot)
                        check(f'grid {tag}: print pages: {count} fronts and backs, only the tokens print', info and info['fronts'] == count and info['backs'] == count and info['vis'] and info['appHidden'], info and {k: info[k] for k in ('fronts', 'backs', 'vis', 'appHidden')})
                        check(f'grid {tag}: print style {style}', info and ('ink' in info['style']) == (style == 'ink'), info and info['style'])
                        txt = info['text'] if info else ''
                        host = mint.split('//')[1]
                        codes = [t['print']['code'] for t in txs]
                        check(f'grid {tag}: front has NUTCADE, TOKEN, the amount the local way, the mint, the date and each token number', 'NUTCADE' in txt and num in txt and host in txt and all(c in txt for c in codes) and (await w.ev("Nutcade.fmtDate(Date.now())")) in txt, txt[:300])
                        if lang == 'en':
                            check(f'grid {tag}: back: how to claim, the app link, and "This token IS the money..."', 'HOW TO CLAIM' in txt and 'random21m.github.io/nutcade' in txt and 'This token IS the money. Whoever scans it first gets the sats. Keep the code hidden until you hand it over.' in txt, txt[-500:])
                        else:
                            check(f'grid {tag}: front and back in the language (no English left)', not [s for s in ENGLISH if s in txt] and 'random21m.github.io/nutcade' in txt, [s for s in ENGLISH if s in txt])
                        decoded = [await read_img(w, s) for s in (info['imgs'] if info else [])]
                        ok_dec = len(decoded) == count and all(d and d.startswith('cashuB') for d in decoded)
                        same = ok_dec
                        for d, t in (zip(decoded, txs) if ok_dec else []):
                            same = same and await w.ev(f"(()=>{{const a=CashuLib.getDecodedToken({json.dumps(d)}, Object.keys(Nutcade.S.counters)).proofs.map(p=>p.secret).sort().join(), b=Nutcade.S.txs.find(t=>t.id==={json.dumps(t['id'])}).sent.map(p=>p.secret).sort().join(); return a===b}})()")
                        check(f'grid {tag}: every printed QR reads back (second reader) as its own token', ok_dec and same, [d and d[:20] for d in decoded])
                miss = await w.ev("[...(window.__i18nMiss||[])]")
                check(f'grid {lang}: no untranslated text on the new screens and pages', not miss, miss[:8])
                check(f'grid {lang}: no page errors', not w.errs, w.errs[:3])
                await w.pg.context.close()
            # the most at once: 20
            w = await funded(b, [NOFEE], 3000)
            s, e, bid = await make(w, NOFEE, 10, 20, 'ink')
            txs = await batch(w, bid) if bid else []
            check('grid: 20 tokens at once (the most)', len(txs) == 20 and not await books(w, (NOFEE,)), e)
            info = await show_print(w, bid, 'tok-20-ink.png') if bid else None
            check('grid: 20 tokens print on pages of several tokens each, with cut lines and a fold line', info and info['pages'] >= 2 and max(info['perPage']) >= 4 and sum(info['perPage']) == 20 and info['cuts'] in ('dashed', 'dotted') and info['fold'] == 20, info and (info['perPage'], info['cuts'], info['fold']))
            await w.pg.context.close()
        await section('grid', grid)

        # ---------- claim (NUTCADE and another wallet), take back, someone else first ----------
        async def claim():
            w = await funded(b, [FEE, NOFEE], 4000)
            for mint in (FEE, NOFEE):
                tag = 'fee' if mint == FEE else 'no-fee'
                s, e, bid = await make(w, mint, 200, 4, 'arcade')
                txs = await batch(w, bid)
                if len(txs) != 4: check(f'claim {tag}: made', False, e); continue
                info = await show_print(w, bid); toks = [await read_img(w, i) for i in info['imgs']]
                # 1: claimed with another NUTCADE wallet, from the printed QR
                r = await wallet(b); await r.create(); await r.receive_token(toks[0])
                got = await r.bal(mint)
                check(f'claim {tag}: a printed token claimed with another NUTCADE', got > 0 and got <= 200, got)
                # 2: claimed with a second Cashu wallet (Nutshell)
                sw = second_wallet(toks[1])
                check(f'claim {tag}: a printed token claimed with a second Cashu wallet (Nutshell)', sw.get('ok') and 0 < sw.get('amount', 0) <= 200, sw)
                # the list: checked at the mint (NUT-07)
                rows = await plist(w); await w.click('[data-act=ptCheck]'); await w.until("!document.querySelector('#layer .spinner')", 30000); await w.wait(500)
                st = {t['id']: await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(t['id'])}).status") for t in txs}
                check(f'claim {tag}: Check marks both claimed tokens claimed, the others still waiting', [st[t['id']] for t in txs] == ['claimed', 'claimed', 'pending', 'pending'], st)
                rows = await w.ev("[...document.querySelectorAll('.pt-row')].map(r=>({id:r.dataset.id, text:r.innerText}))")
                rt = {r_['id']: r_['text'] for r_ in rows}
                check(f'claim {tag}: the list says CLAIMED / WAITING in words (not color alone)', 'CLAIMED' in rt.get(txs[0]['id'], '') and 'WAITING' in rt.get(txs[2]['id'], ''), list(rt.values())[:4])
                check(f'claim {tag}: Take back only offered for unclaimed ones', await w.ev(f"!document.querySelector('.pt-row[data-id={json.dumps(txs[0]['id'])}] [data-act=ptTake]') && !!document.querySelector('.pt-row[data-id={json.dumps(txs[2]['id'])}] [data-act=ptTake]')"))
                # 3: take back an unclaimed one
                bal0 = await w.bal(mint)
                await w.click(f'.pt-row[data-id="{txs[2]["id"]}"] [data-act=ptTake]'); await w.until(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[2]['id'])}).status!=='pending' || /\\S/.test((document.querySelector('#sheetErr')||{{}}).innerText||'')", 30000); await w.wait(400)
                got = await w.bal(mint) - bal0
                check(f'claim {tag}: Take back an unclaimed token brings its sats back (less only the mint fee)', await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[2]['id'])}).status") == 'reclaimed' and (got == 200 if mint == NOFEE else 190 <= got <= 200), (got, await w.err()))
                rows = await w.ev("[...document.querySelectorAll('.pt-row')].map(r=>({id:r.dataset.id, text:r.innerText}))")
                check(f'claim {tag}: the list says TAKEN BACK', any(r_['id'] == txs[2]['id'] and 'TAKEN BACK' in r_['text'] for r_ in rows), [r_['text'] for r_ in rows][:4])
                # 4: someone else claims first; then take back fails honestly, nothing moves
                sw = second_wallet(toks[3])
                bal0 = await w.bal(mint); n0 = await w.ev("Nutcade.S.txs.length")
                await w.click(f'.pt-row[data-id="{txs[3]["id"]}"] [data-act=ptTake]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 30000); await w.wait(800)
                e = await w.err()
                check(f'claim {tag}: claimed by someone else first: Take back says so', sw.get('ok') and re.search(r'already claimed', e, re.I), (sw, e))
                check(f'claim {tag}: ... and marks it claimed, no sats or line added', await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[3]['id'])}).status") == 'claimed' and await w.bal(mint) == bal0 and await w.ev("Nutcade.S.txs.length") == n0, (await w.bal(mint) - bal0, await w.ev("Nutcade.S.txs.length") - n0))
                await w.until("Nutcade.S.ops.length===0", 20000)
                check(f'claim {tag}: history = balance', not await books(w), await books(w))
                await r.pg.context.close()
            # the token shows in the history with a PRINTED mark (in words)
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
            check('claim: printed tokens show in the history marked PRINTED', await w.ev("[...document.querySelectorAll('#txList .tx')].some(r=>/PRINTED/.test(r.innerText))"))
            pid = await w.ev(f"{PRINTED}[0].id"); await w.ev(f"document.querySelector('[data-act=tx][data-id=\"{pid}\"]').click()"); await w.wait(250)
            check('claim: a printed token\'s notes line says it was printed, with its number', await w.ev(f"/Printed token/.test(document.querySelector('.sheet-body').innerText) && document.querySelector('.sheet-body').innerText.includes({json.dumps('#')})"))
            # take back all unclaimed
            n_pend = await w.ev(f"{PRINTED}.filter(t=>t.status==='pending').length")
            await plist(w); await w.click('[data-act=ptTakeAll]'); await w.until(f"{PRINTED}.filter(t=>t.status==='pending').length===0 || /\\S/.test((document.querySelector('#sheetErr')||{{}}).innerText||'')", 60000); await w.wait(600)
            check(f'claim: Take back all unclaimed ({n_pend})', n_pend > 0 and await w.ev(f"{PRINTED}.filter(t=>t.status==='pending').length") == 0, await w.err())
            check('claim: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('claim', claim)

        # ---------- the mint down ----------
        async def down():
            w = await funded(b, [FEE], 3000)
            s, e, bid = await make(w, FEE, 100, 2)
            txs = await batch(w, bid)
            async def dead(route): await route.abort('connectionrefused')
            await w.pg.route(FEE + '/v1/**', dead)
            bal0 = await w.bal(FEE); n0 = await w.ev("Nutcade.S.txs.length")
            s, e, bid2 = await make(w, FEE, 100, 2, ms=60000)
            check('down: making tokens with the mint down: an honest error, nothing made', bool(e) and not bid2 and await w.bal(FEE) == bal0 and await w.ev("Nutcade.S.txs.length") == n0, (e, s[:120]))
            await w.until("Nutcade.S.ops.length===0", 20000)
            check('down: ... nothing left open in the journal', await w.ev("Nutcade.S.ops.length") == 0)
            await plist(w); await w.click('[data-act=ptCheck]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'') || !document.querySelector('#layer .spinner')", 40000); await w.wait(300)
            e = await w.err()
            check('down: Check with the mint down says it could not reach the mint; statuses unchanged', bool(e) and re.search(r"reach|answer|down|offline", e, re.I) and all((await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(t['id'])}).status")) == 'pending' for t in txs), e)
            await w.click(f'.pt-row[data-id="{txs[0]["id"]}"] [data-act=ptTake]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 40000); await w.wait(300)
            e = await w.err()
            check('down: Take back with the mint down fails with a reason, the token stays waiting', bool(e) and await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[0]['id'])}).status") == 'pending' and await w.bal(FEE) == bal0, e)
            await w.pg.unroute(FEE + '/v1/**', dead)
            await w.until("Nutcade.S.ops.length===0", 30000)
            await plist(w); await w.click(f'.pt-row[data-id="{txs[0]["id"]}"] [data-act=ptTake]'); await w.until(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[0]['id'])}).status==='reclaimed'", 30000)
            check('down: back up: Take back works', await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[0]['id'])}).status") == 'reclaimed')
            await w.until("Nutcade.S.ops.length===0", 30000)
            check('down: history = balance', not await books(w, (FEE,)), await books(w, (FEE,)))
            await w.pg.context.close()
        await section('down', down)

        # ---------- the spending limit ----------
        async def limit():
            w = await funded(b, [NOFEE], 5000)
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=limOpen]'); await w.until("!!document.querySelector('#limDay')", 5000)
            await w.fill('#limDay', '1000'); await w.click('[data-act=limSave]'); await w.wait(400); await w.ev("Nutcade.closeSheet()")
            s, e, bid = await make(w, NOFEE, 300, 4)
            check('limit: 4 x 300 over a 1,000 a day limit: held, with the whole batch\'s amount', not bid and '1,200' in e and await w.ev(f"{PRINTED}.length") == 0 and await w.bal(NOFEE) == 5000, e)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click()"); await w.ev("Nutcade.closeSheet()")
            s, e, bid = await make(w, NOFEE, 300, 3)
            used = await w.ev("Nutcade.r8.spentDay()")
            check('limit: 3 x 300 fits: made, and the day counts 900', bool(bid) and used == 900, (e, used))
            s, e, bid = await make(w, NOFEE, 100, 2)
            check('limit: 2 x 100 more is over what is left (100): held', not bid and 'limit' in e.lower(), e)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click()"); await w.ev("Nutcade.closeSheet()")
            # a token taken back gives the day back its amount (only a fee would count)
            pid = await w.ev(f"{PRINTED}[0].id"); await plist(w); await w.click(f'.pt-row[data-id="{pid}"] [data-act=ptTake]'); await w.until(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(pid)}).status==='reclaimed'", 30000)
            check('limit: a printed token taken back no longer counts', await w.ev("Nutcade.r8.spentDay()") == 600, await w.ev("Nutcade.r8.spentDay()"))
            check('limit: history = balance', not await books(w, (NOFEE,)), await books(w, (NOFEE,)))
            await w.pg.context.close()
        await section('limit', limit)

        # ---------- backup and restore keep the list; two devices, one seed ----------
        async def backup():
            w = await funded(b, [FEE, NOFEE], 3000)
            s, e, bid = await make(w, FEE, 150, 3); s, e, bid2 = await make(w, NOFEE, 150, 2, 'ink')
            tok, e = await w.send_ecash(150, 'normal token')   # (a normal sent token, the comparison)
            mine = await w.ev(f"{PRINTED}.map(t=>[t.id,t.print.code,t.status]).sort()")
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
            async with w.pg.expect_download() as d: await w.pg.evaluate("document.querySelector('[data-act=backupDownload]').click()")
            data = open(await (await d.value).path()).read()
            check('backup: the backup file holds every printed token (open sends) with its print record', all(c in data for _, c, _s in mine) and data.count('"print"') >= 5)
            async def imp(x):
                await x.ev("Nutcade.closeSheet()"); await x.click('[data-act=tab][data-tab=settings]'); await x.wait(150)
                await x.click('[data-act=restore]'); await x.wait(250); await x.pg.wait_for_selector('#restoreIn', timeout=60000)
                await x.pg.evaluate("v => { const t = document.querySelector('#restoreIn'); t.value = v; t.dispatchEvent(new Event('input', {bubbles: true})) }", data); await x.click('[data-act=doRestore]')
                await x.until("!document.querySelector('#restoreIn')", 90000); await x.wait(600); await x.until("Nutcade.S.ops.length===0", 60000); await x.wait(1500); await x.ev("Nutcade.closeSheet()")
            x = await wallet(b); await x.create(); await imp(x)
            got = await x.ev(f"{PRINTED}.map(t=>[t.id,t.print.code,t.status]).sort()")
            check('backup: restored from the file: the Printed tokens list is the same', got == mine, (got, mine))
            await imp(x)
            check('backup: imported twice: still once each', await x.ev(f"{PRINTED}.length") == 5 and await x.ev(f"{PRINTED}.map(t=>t.id)").__class__ is list and len(set(await x.ev(f"{PRINTED}.map(t=>t.id)"))) == 5)
            rows = await plist(x)
            check('backup: the restored list shows them', len(rows) == 5, len(rows))
            pid = mine[0][0]; pm = await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).mint"); b0 = await x.bal(pm)
            await x.click(f'.pt-row[data-id="{pid}"] [data-act=ptTake]'); await x.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status==='reclaimed'", 30000)
            check('backup: Take back works in the restored wallet', await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status") == 'reclaimed' and await x.bal(pm) > b0)
            # the first device then: its copy of that token was taken back elsewhere -> Check says claimed (like any sent token)
            await plist(w); await w.click('[data-act=ptCheck]'); await w.until("!document.querySelector('#layer .spinner')", 30000); await w.wait(400)
            check('backup: two devices: a token taken back on the other device shows as claimed here, no sats added', await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status") == 'claimed' and not await books(w), await books(w))
            await w.click(f'.pt-row[data-id="{mine[1][0]}"] [data-act=ptTake]'); await w.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(mine[1][0])}).status!=='pending'", 30000); await w.wait(300)
            await x.ev("Nutcade.closeSheet()"); await plist(x); await x.click(f'.pt-row[data-id="{mine[1][0]}"] [data-act=ptTake]'); await x.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 30000); await x.wait(500)
            check('backup: two devices: taken back here first, then Take back on the other says already claimed, nothing added', re.search('already claimed', await x.err(), re.I) and await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(mine[1][0])}).status") == 'claimed', await x.err())
            await x.until("Nutcade.S.ops.length===0", 30000)
            check('backup: history = balance on both', not await books(w) and not await books(x), (await books(w), await books(x)))
            # the 12 words: printed tokens come back exactly like a normal sent token does
            y = await wallet(b); await y.pg.check('#ack'); await y.click('[data-act=gateRestore]'); await y.until("!!document.querySelector('#phraseIn')", 5000)
            await y.fill('#phraseIn', await w.ev("Nutcade.S.seed.mnemonic")); await y.click('[data-act=doRestorePhrase]')
            await y.until("/SCAN COMPLETE|CONTINUE|READY/.test((document.querySelector('.sheet-body')||document.body).innerText||'') || Object.values(Nutcade.S.proofs).flat().length>0", 120000); await y.wait(4000)
            secs = set(await y.ev("Object.values(Nutcade.S.proofs).flat().map(p=>p.secret)"))
            normal = await w.ev(f"Nutcade.S.txs.find(t=>t.token==={json.dumps(tok)}).sent.map(p=>p.secret)")
            open_pr = await w.ev(f"{PRINTED}.filter(t=>t.status==='pending').map(t=>t.sent.map(p=>p.secret))")
            n_in = all(s_ in secs for s_ in normal); p_in = [all(s_ in secs for s_ in ps) for ps in open_pr]
            check('backup: restore from 12 words: unclaimed printed tokens come back exactly as a normal unclaimed sent token does', len(p_in) > 0 and all(x_ == n_in for x_ in p_in), (n_in, p_in))
            for z in (w, x, y): await z.pg.context.close()
        await section('backup', backup)

        # ---------- a crash mid-print books once ----------
        async def crash():
            w = await funded(b, [FEE], 4000)
            calls = {'n': 0}
            async def cut(route):
                calls['n'] += 1
                if calls['n'] == 3:   # the mint signs the 3rd token's swap, the answer never arrives: the page dies
                    try: await route.fetch()
                    except Exception: pass
                    await route.abort('failed')
                    asyncio.get_event_loop().call_later(0.2, lambda: asyncio.ensure_future(w.pg.close(run_before_unload=False)))
                else: await route.continue_()
            await w.pg.route(FEE + '/v1/swap', cut)
            ctx = w.pg.context; seed = await w.ev("Nutcade.S.seed.mnemonic"); bal0 = await w.bal(FEE)
            await open_print(w, FEE); await w.fill('#ptAmt', '200'); await w.fill('#ptCount', '5'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 10000)
            try:
                await w.click('[data-act=ptMake]')
                for _ in range(120):
                    if w.pg.is_closed(): break
                    await asyncio.sleep(0.25)
            except Exception: pass
            pg = await ctx.new_page(); w2 = W(pg, 'tok2'); pg.on('pageerror', lambda e: w2.errs.append('PAGEERROR ' + str(e)))
            await pg.goto(URL); await pg.wait_for_timeout(1500)
            await w2.until("Nutcade.S.ops.length===0", 60000); await w2.wait(1500)
            pr = await w2.ev(f"{PRINTED}.map(t=>({{i:t.print.i, a:t.amount, f:t.fee||0, s:t.status}}))")
            check('crash: the 2 tokens made before the crash are kept, once each', sorted(x['i'] for x in pr) == [1, 2], pr)
            check('crash: the interrupted 3rd token went back to the balance (it was never shown or printed), no 3rd to 5th token', len(pr) == 2 and await w2.ev("Nutcade.S.ops.length") == 0)
            bal1 = await w2.bal(FEE); out = sum(x['a'] + x['f'] for x in pr)
            feeLines = await w2.ev(f"Nutcade.S.txs.filter(t=>t.method==='fee'&&t.mint==={json.dumps(FEE)}).reduce((s,t)=>s+(t.fee||0),0)")
            check('crash: books once: balance = start - the two tokens - every fee the mint kept, history = balance', bal1 == bal0 - out - feeLines and not await books(w2, (FEE,)), (bal0, bal1, out, feeLines, await books(w2, (FEE,))))
            await w2.ev("location.reload()"); await pg.wait_for_timeout(1500); await w2.until("Nutcade.S.ops.length===0", 30000)
            check('crash: a second reload changes nothing', await w2.bal(FEE) == bal1 and len(await w2.ev(PRINTED)) == 2)
            rows = await plist(w2)
            check('crash: the list offers to print the batch again', len(rows) == 2 and await w2.ev("!!document.querySelector('[data-act=ptReprint]')"))
            await ctx.close()
        await section('crash', crash)

        # ---------- the QR logo: every QR size x the three themes, and None ----------
        async def logo():
            for theme in ('neon', 'amber', 'phosphor'):
                w = await funded(b, [NOFEE], 3000, 'en', theme)
                check(f'logo {theme}: the QR center setting (None / NUTCADE acorn), acorn by default', await w.ev("(()=>{Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); return [...document.querySelectorAll('[data-act=qrLogo]')].map(b=>b.dataset.v+':'+b.getAttribute('aria-pressed')).join()})()") == 'none:false,acorn:true')
                # sizes: a short code (Lightning address), a token (medium), a long token, an animated one
                small = 'lightning:' + 'a' * 30 + '@example.com'
                medium = await w.ev("NutTokens.sampleToken(1)"); long_ = await w.ev("NutTokens.sampleToken(3)"); huge = await w.ev("NutTokens.sampleToken(40)")
                for label, text in (('small', small), ('medium', medium), ('long', long_)):
                    r = await w.ev(f"NutTokens.showQR({json.dumps(text)})"); await w.until("!!document.querySelector('#layer .qr[data-check]') && document.querySelector('#layer .qr').dataset.check!=='pending'", 15000)
                    q = await w.ev("(()=>{const e=document.querySelector('#layer .qr'); const c=e.querySelector('canvas'); return {logo:e.dataset.logo, check:e.dataset.check, ecl:c&&c.dataset.ecl, len: c&&c.width}})()")
                    dec = await w.ev("(async()=>{const c=document.querySelector('#layer .qr canvas'); const d=c.getContext('2d').getImageData(0,0,c.width,c.height); const r=CashuLib.jsQR(d.data,c.width,c.height); return r?r.data:null})()")
                    want_logo = q['logo'] == '1'
                    check(f'logo {theme} {label} ({len(text)} chars): {"the acorn, at error correction H" if label != 'long' else "plain: with the acorn it would be too dense (over 117 modules)"}, read back by the app, scans', q['check'] == 'ok' and dec == (text if label != 'small' else text) and (q['ecl'] == 'H') == want_logo and want_logo == (label != 'long'), (q, dec and dec[:20]))
                    if label in ('small', 'medium'): check(f'logo {theme} {label}: the acorn is on by default', want_logo, q)
                    await w.pg.screenshot(path=os.path.join(OUT, f'logo-{theme}-{label}.png')) if label == 'medium' else None
                await w.ev(f"NutTokens.showQR({json.dumps(huge)})"); await w.until("!!document.querySelector('#layer .qr-anim canvas')", 15000); await w.wait(700)
                check(f'logo {theme}: a big animated QR (BC-UR) stays plain', await w.ev("(()=>{const e=document.querySelector('#layer .qr-anim'); const c=e.querySelector('canvas'); return e.dataset.logo!=='1' && c.dataset.logo!=='1'})()"))
                # a QR that would not scan with the logo falls back to plain
                await w.ev("NutTokens._logoScale=0.62"); await w.ev(f"NutTokens.showQR({json.dumps(medium)})"); await w.until("document.querySelector('#layer .qr') && ['ok','fail'].includes(document.querySelector('#layer .qr').dataset.check)", 15000)
                q = await w.ev("(()=>{const e=document.querySelector('#layer .qr'); return {logo:e.dataset.logo, check:e.dataset.check, fell:e.dataset.fallback}})()")
                check(f'logo {theme}: a logo QR that would not scan falls back to plain (read back)', q['logo'] == '0' and q['check'] == 'ok' and q['fell'] == '1', q)
                await w.ev("NutTokens._logoScale=0")
                # every QR the app shows goes the same way: the ecash address, a P2PK key, a sent token on its notes line
                await w.ev("Nutcade.closeSheet()"); await w.ev("document.querySelector('[data-act=tab][data-tab=wallet]').click()"); await w.wait(150)
                if not await w.ev("Nutcade.S.p2pk.length"): await w.ev("(()=>{const b=document.createElement('button'); b.dataset.act='p2pkNew'; document.body.appendChild(b); b.click(); b.remove()})()"); await w.until("Nutcade.S.p2pk.length>0", 5000); await w.ev("Nutcade.closeSheet()")
                for act in ('myAddrQR', 'p2pkShow'):
                    await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='{act}'; b.dataset.i='0'; document.body.appendChild(b); b.click(); b.remove()}})()")
                    await w.until("!!document.querySelector('#layer .qr') && ['ok','fail'].includes(document.querySelector('#layer .qr').dataset.check)", 15000)
                    q = await w.ev("(()=>{const e=document.querySelector('#layer .qr'); return {logo:e.dataset.logo, check:e.dataset.check, ecl:e.querySelector('canvas').dataset.ecl}})()")
                    check(f'logo {theme}: {act} QR: the acorn at H, read back', q == {'logo': '1', 'check': 'ok', 'ecl': 'H'}, q)
                    await w.ev("Nutcade.closeSheet()")
                tok, e = await w.send_ecash(100); await w.ev(f"document.querySelector('[data-act=tab][data-tab=history]').click()"); await w.wait(150)
                await w.ev("document.querySelector('#txList [data-act=tx]').click()"); await w.until("!!document.querySelector('#layer .qr') && ['ok','fail'].includes(document.querySelector('#layer .qr').dataset.check)", 15000)
                q = await w.ev("(()=>{const e=document.querySelector('#layer .qr'); return {logo:e.dataset.logo, check:e.dataset.check, ecl:e.querySelector('canvas').dataset.ecl, n:document.querySelector('#layer .code').innerText.length}})()")
                check(f'logo {theme}: a sent token on its notes line: read back, and the acorn only if it stays within 117 modules at H', q['check'] == 'ok' and (q['logo'] == '1') == (q['ecl'] == 'H'), q)
                # None: no logo anywhere, plain error correction
                await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150); await w.click('[data-act=qrLogo][data-v=none]'); await w.wait(150)
                check(f'logo {theme}: None saved', await w.ev("Nutcade.S.prefs.qrLogo") == 'none')
                await w.ev(f"NutTokens.showQR({json.dumps(medium)})"); await w.until("!!document.querySelector('#layer .qr canvas')", 15000); await w.wait(300)
                check(f'logo {theme}: with None, QRs are plain', await w.ev("(()=>{const e=document.querySelector('#layer .qr'); return e.dataset.logo==='0' && e.querySelector('canvas').dataset.ecl!=='H'})()"))
                s, e, bid = await make(w, NOFEE, 64, 1)
                info = await show_print(w, bid) if bid else None
                check(f'logo {theme}: with None, printed tokens are plain too', bool(bid) and await w.ev("NutTokens.lastCheck.every(c=>c.ok && !c.logo)"), await w.ev("NutTokens.lastCheck"))
                await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150); await w.click('[data-act=qrLogo][data-v=acorn]'); await w.wait(150)
                s, e, bid = await make(w, NOFEE, 64, 2)
                check(f'logo {theme}: with the acorn, a small printed token has it (and reads back)', bool(bid) and await w.ev("NutTokens.lastCheck.every(c=>c.ok && c.logo)"), await w.ev("NutTokens.lastCheck"))
                check(f'logo {theme}: no page errors', not w.errs, w.errs[:3])
                await w.pg.context.close()
            # the score card that pays out (trophies) and the treasure hunt cards use the same QR
            w = await wallet(b); await w.create()
            r = await w.ev("""(async()=>{let n=0; const v=NutQR.verified; NutQR.verified=(...a)=>{n++; return v(...a)}; const url='https://random21m.github.io/nutcade/#load=abc123def456';
              const o={kind:'trophy', d:Trophies.DEFS[0], loaded:{url, amount:21, until:Date.now()+864e5}, at:Date.now()};
              let r; try { r=await Trophies.renderCard(o); } finally { NutQR.verified=v; }
              const i=new Image(); i.src=r.url; await i.decode(); const c=document.createElement('canvas'); c.width=i.naturalWidth; c.height=i.naturalHeight; const x=c.getContext('2d'); x.drawImage(i,0,0);
              const d=x.getImageData(0,0,c.width,c.height); const q=CashuLib.jsQR(d.data,c.width,c.height); return [n, !!q && q.data===url]})()""")
            check('logo: the score card that pays out uses the same QR (acorn, read back) and scans', r == [1, True], r)
            await w.pg.context.close()
        await section('logo', logo)

        # ---------- print preview pages, both styles, screenshots ----------
        async def pages():
            w = await funded(b, [FEE], 9000)
            s, e, bid = await make(w, FEE, 1000, 6, 'arcade')
            for style in ('arcade', 'ink'):
                info = await show_print(w, bid, f'print-sheet-{style}.png', style)
                check(f'pages {style}: the print pages show only the tokens, 4 to a page, cut and fold lines', info and info['vis'] and info['appHidden'] and info['perPage'][0] == 4 and info['cuts'] in ('dashed', 'dotted') and info['fold'] == 6, info and {k: info[k] for k in ('perPage', 'cuts', 'fold', 'appHidden')})
                check(f'pages {style}: colors print as shown (print-color-adjust: exact)', info and info['exact'] == 'exact', info and info['exact'])
                # QR always dark on light: the QR image's light parts are light, dark parts dark (both styles)
                lum = await w.ev(f"""(async()=>{{const i=new Image(); i.src={json.dumps(info['imgs'][0])}; await i.decode(); const c=document.createElement('canvas'); c.width=i.naturalWidth; c.height=i.naturalHeight; const x=c.getContext('2d'); x.drawImage(i,0,0);
                  const d=x.getImageData(0,0,c.width,c.height).data; const L=(k)=>0.2126*d[k]+0.7152*d[k+1]+0.0722*d[k+2]; return [L(0), L((Math.floor(c.height*0.5)*c.width+Math.floor(c.width*0.06))*4)]}})()""")
                check(f'pages {style}: the QR is dark on light (quiet zone light)', lum[0] > 200, lum)
            # the Print button: prints (window.print) and marks the batch printed
            await w.ev("Nutcade.closeSheet()"); await plist(w); await w.click('[data-act=ptReprint]'); await w.until("!!document.querySelector('.pt-ready')", 60000)
            await w.click('[data-act=ptPrint]'); await w.wait(300)
            check('pages: Print opens the browser print for the tokens', await w.ev("window.__printed") >= 1)
            await w.pg.context.close()
        await section('pages', pages)

        bad = [r for r in results if not r[1]]
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
