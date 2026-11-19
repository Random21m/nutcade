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
OVER_JS = """(()=>{const W=document.documentElement.clientWidth,out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(!e.getClientRects().length||e.closest('.sr')||e.closest('.pt-preview'))continue;const r=e.getBoundingClientRect();if(r.right>W+1||r.left<-1)out.push((e.className||e.tagName)+':'+Math.round(r.left)+'..'+Math.round(r.right))}
  for(const p of document.querySelectorAll('.pt-preview')){const r=p.getBoundingClientRect(); if(r.right>W+1||r.left<-1) out.push('pt-preview:'+Math.round(r.left)+'..'+Math.round(r.right))}
  return out.slice(0,4)})()"""


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
    await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('#ptAmt') || !!document.querySelector('.pt-intro')", 5000)
    if await w.ev("!!document.querySelector('.pt-intro')"):   # (the first time: the first-scan rule, then the screen)
        await w.click('[data-act=ptIntroOk]'); await w.until("!!document.querySelector('#ptAmt')", 5000)


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
            await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('.pt-intro')", 5000); await w.click('[data-act=ptIntroOk]')   # (the first time: the first-scan rule)
            await w.until("!!document.querySelector('#ptAmt')", 5000)
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
            await w.fill('#ptAmt', '1048575'); await w.fill('#ptCount', '1'); await w.click('[data-act=ptNext]'); await w.wait(400)
            e = await w.err(); check('screen: an amount of 20 coins (1,048,575) refused before anything is made: its code would be too dense on paper', 'too dense' in e and '20 coins' in e, e)
            check('screen: nothing made by the refusals', await w.ev(f"{PRINTED}.length") == 0 and await w.ev("Nutcade.S.ops.length") == 0)
            # a code that wouldn't scan: nothing prints, the screen says which and why, the tokens are kept
            await w.ev("window.__gid=CanvasRenderingContext2D.prototype.getImageData; CanvasRenderingContext2D.prototype.getImageData=function(x,y,w,h){return new ImageData(Math.max(1,w|0),Math.max(1,h|0))}; 0")   # (every image reads as blank)
            s, e, bid = await make(w, NOFEE, 100, 2)
            pr = await w.ev(f"{PRINTED}.map(t=>[t.status,t.print.code])")
            check('screen: a code that would not read back: nothing prints, and the screen says which token and why', not bid and "didn't read back" in e and any(c in e for _s, c in pr) and not await w.ev("!!document.querySelector('#tokPrint')"), e)
            check('screen: ... the tokens made are kept (waiting in Printed tokens), history = balance', len(pr) == 2 and all(x[0] == 'pending' for x in pr) and not await books(w, (NOFEE,)), pr)
            await w.ev("CanvasRenderingContext2D.prototype.getImageData=window.__gid; 0"); await plist(w); await w.click('[data-act=ptReprint]'); await w.until("!!document.querySelector('.pt-ready')", 60000)
            check('screen: ... and Print again prints them once they read back', await w.ev("!!document.querySelector('.pt-ready') && NutTokens.lastCheck.length===2 && NutTokens.lastCheck.every(c=>c.ok)"))
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
                        est = await w.ev("NutTokens.lastEstimate")
                        check(f'grid {tag}: the fees paid are within the "up to" shown before making', est and fees <= est['fee'] and est['spend'] == count * amount + est['fee'], (fees, est))
                        check(f'grid {tag}: the cost shown before making (amount x count, total) in the language', num in summary and (await w.ev(f"Nutcade.fmt({count * amount})")) in summary, summary[:300])
                        ready = await w.sheet_text()
                        check(f'grid {tag}: the fees actually paid shown after making ({fees})', (await w.ev(f"Nutcade.fmt({fees})")) in ready, ready[:300])
                        check(f'grid {tag}: journal closed, history = balance', await w.ev("Nutcade.S.ops.length") == 0 and not await books(w), await books(w))
                        chk = await w.ev("NutTokens.lastCheck")
                        check(f'grid {tag}: every QR read back by the app (its bundled zxing reader) before printing', bool(chk) and len(chk) == count and all(c['ok'] and c['by'] == 'zxing' for c in chk), chk)
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
                check(f'claim {tag}: the list says CLAIMED / UNCLAIMED in words (not color alone)', 'CLAIMED' in rt.get(txs[0]['id'], '') and 'UNCLAIMED' in rt.get(txs[2]['id'], ''), list(rt.values())[:4])
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
            s, e, bid = await make(w, NOFEE, 50, 2)
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
            await plist(w); await w.click('[data-act=ptCheck]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'') || !document.querySelector('#layer .spinner')", 40000); await w.wait(300)
            e = await w.err()
            sts = [await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(t['id'])}).status") for t in txs]
            check('down: Check with the mint down says it could not reach the mint; statuses unchanged', bool(e) and re.search(r"reach|answer|down|offline", e, re.I) and sts == ['pending', 'pending'], (e, sts))
            await w.click(f'.pt-row[data-id="{txs[0]["id"]}"] [data-act=ptTake]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 40000); await w.wait(300)
            e = await w.err()
            check('down: Take back with the mint down fails with a reason, the token stays waiting', bool(e) and await w.ev(f"Nutcade.S.txs.find(x=>x.id==={json.dumps(txs[0]['id'])}).status") == 'pending' and await w.bal(FEE) == bal0, e)
            await w.pg.unroute(FEE + '/v1/**', dead)
            await w.ev("Nutcade.closeSheet()"); await w.until("Nutcade.S.ops.length===0", 70000)
            check('down: back up: the step the mint never got settles with nothing booked (balance and lines as before)', await w.ev("Nutcade.S.ops.length") == 0 and await w.bal(FEE) == bal0 and await w.ev("Nutcade.S.txs.length") == n0, (await w.ev("Nutcade.S.ops.length"), await w.bal(FEE) - bal0, await w.ev("Nutcade.S.txs.length") - n0))
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
            ids = await x.ev(f"{PRINTED}.map(t=>t.id)")
            check('backup: imported twice: still once each', len(ids) == 5 and len(set(ids)) == 5, ids)
            rows = await plist(x)
            check('backup: the restored list shows them', len(rows) == 5, len(rows))
            pid = mine[0][0]; pm = await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).mint"); b0 = await x.bal(pm)
            await x.click(f'.pt-row[data-id="{pid}"] [data-act=ptTake]'); await x.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status==='reclaimed'", 30000)
            check('backup: Take back works in the restored wallet', await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status") == 'reclaimed' and await x.bal(pm) > b0)
            # the first device then: its copy of that token was taken back elsewhere -> Check says claimed (like any sent token)
            await plist(w); await w.click('[data-act=ptCheck]'); await w.until("!document.querySelector('#layer .spinner')", 30000); await w.wait(400)
            check('backup: two devices: a token taken back on the other device shows as claimed here, no sats added', await w.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(pid)}).status") == 'claimed' and not await books(w), await books(w))
            await w.click(f'.pt-row[data-id="{mine[1][0]}"] [data-act=ptTake]'); await w.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(mine[1][0])}).status!=='pending'", 30000); await w.wait(300)
            await x.ev("Nutcade.closeSheet()"); await plist(x); xb = await x.bal(); xn = await x.ev("Nutcade.S.txs.length")
            sel = f'.pt-row[data-id="{mine[1][0]}"] [data-act=ptTake]'; said = ''
            if await x.ev(f"!!document.querySelector({json.dumps(sel)})"):   # (not seen as claimed yet: Take back finds out)
                await x.click(sel); await x.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 30000); await x.wait(500); said = await x.err()
            row = await x.ev(f"(document.querySelector('.pt-row[data-id=\"{mine[1][0]}\"]')||{{}}).innerText||''")
            check('backup: two devices: taken back here first, the other device says it was claimed (already claimed, or CLAIMED with no Take back), nothing added', (not said or re.search('already claimed', said, re.I)) and 'CLAIMED' in row and await x.ev(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(mine[1][0])}).status") == 'claimed' and await x.bal() == xb and await x.ev("Nutcade.S.txs.length") == xn, (said, row))
            await x.until("Nutcade.S.ops.length===0", 30000)
            check('backup: history = balance on both', not await books(w) and not await books(x), (await books(w), await books(x)))
            # the 12 words: printed tokens come back exactly like a normal sent token does
            y = await wallet(b); await y.pg.check('#ack'); await y.click('[data-act=gateRestore]'); await y.until("!!document.querySelector('#phraseIn')", 5000)
            await y.fill('#phraseIn', await w.ev("Nutcade.S.seed.mnemonic"))
            await y.ev("document.querySelectorAll('[data-rmint]').forEach(i=>{i.checked=false})"); await y.fill('#rmExtra', FEE + '\n' + NOFEE)
            await y.click('[data-act=doRestorePhrase]')
            await y.until("/SCAN COMPLETE|CONTINUE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 180000); await y.wait(1000)
            secs = set(await y.ev("Object.values(Nutcade.S.proofs).flat().map(p=>p.secret)"))
            normal = await w.ev(f"Nutcade.S.txs.find(t=>t.token==={json.dumps(tok)}).sent.map(p=>p.secret)")
            open_pr = await w.ev(f"{PRINTED}.filter(t=>t.status==='pending').map(t=>t.sent.map(p=>p.secret))")
            n_in = all(s_ in secs for s_ in normal); p_in = [all(s_ in secs for s_ in ps) for ps in open_pr]
            wsec = await w.ev("Object.values(Nutcade.S.proofs).flat().map(p=>p.secret)"); bal_in = sum(1 for s_ in wsec if s_ in secs)
            check('backup: restore from 12 words: unclaimed printed tokens come back exactly as a normal unclaimed sent token does', len(p_in) > 0 and all(x_ == n_in for x_ in p_in) and bal_in == len(wsec) > 0, (n_in, p_in, bal_in, len(wsec), len(secs)))
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

        # ---------- recheck findings: the fee shown is a true "up to", a stop mid-batch never remakes, coins incl. fee coins ----------
        async def money2():
            async def slow(w, sec):
                async def h(route):
                    await asyncio.sleep(sec); await route.continue_()
                await w.pg.route('**/v1/swap', h); return h
            # F1: on the fee mint the fee paid is never more than the "up to" shown; the same coins always give the same number
            w = await funded(b, [FEE], 30000); await w.receive_ln(9000); await w.receive_ln(777)
            for amount, count in ((63, 20), (255, 12), (127, 15), (524, 8), (21, 20), (63, 20), (1000, 5), (33, 17)):
                if await w.bal(FEE) < amount * count * 1.1 + 100: break
                ests = []
                for _ in range(4):
                    await open_print(w, FEE); await w.fill('#ptAmt', str(amount)); await w.fill('#ptCount', str(count)); await w.click('[data-act=ptNext]')
                    await w.until("!!document.querySelector('[data-act=ptMake]') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 20000)
                    ests.append((await w.ev("NutTokens.lastEstimate") or {}).get('fee'))
                b0 = await w.bal(FEE); await w.click('[data-act=ptMake]')
                await w.until("!!document.querySelector('.pt-ready') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 240000); await w.wait(300)
                bid = await w.ev("(document.querySelector('.pt-ready')||{dataset:{}}).dataset.b||null"); txs = await batch(w, bid) if bid else []
                paid = b0 - await w.bal(FEE) - amount * len(txs); lines = sum(t.get('fee', 0) for t in txs)
                check(f'money2 fee {count}x{amount}: paid {paid} <= shown "up to {ests[-1]}", and the same coins give the same number every time {sorted(set(ests))}', bid and len(txs) == count and paid == lines and ests[-1] is not None and paid <= ests[-1] and len(set(ests)) == 1, (await w.err(), len(txs), paid, lines, ests))
                await w.ev("Nutcade.closeSheet()")
            check('money2 fee: history = balance', not await books(w, (FEE,)), await books(w, (FEE,)))
            # the coins give another cost at Make than the one shown (here the shown number is made 1 SAT lower, as when
            # coins changed since; at 100 ppk real coin changes rarely move the cost): nothing is made, the cost is shown again
            await open_print(w, FEE); await w.fill('#ptAmt', '63'); await w.fill('#ptCount', '5'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000)
            n0 = await w.ev(f"{PRINTED}.length"); real = (await w.ev("NutTokens.lastEstimate"))['spend']
            await w.ev("NutTokens.lastEstimate.spend -= 1; 0")
            await w.click('[data-act=ptMake]'); await w.until("/\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'') || !!document.querySelector('.pt-ready')", 60000); await w.wait(300)
            e = await w.err()
            check('money2: the coins give another cost at Make than shown: nothing is made, the cost is worked out again and shown', 'changed since' in e and await w.ev(f"{PRINTED}.length") == n0 and await w.ev("!!document.querySelector('[data-act=ptMake]')") and (await w.ev("NutTokens.lastEstimate"))['spend'] == real, (e, real))
            await w.ev("Nutcade.closeSheet()")
            # F1: the spending limit uses the number shown: a day limit of exactly what is shown lets the batch through
            for trial in range(3):
                await open_print(w, FEE); await w.fill('#ptAmt', '63'); await w.fill('#ptCount', '20'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000)
                est = await w.ev("NutTokens.lastEstimate")
                await w.ev(f"Nutcade.S.limits={{per:0, day: Nutcade.r8.spentDay() + {est['spend']}}}")
                await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('.pt-ready') || !!document.querySelector('#limitLayer') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 240000); await w.wait(300)
                ok = await w.ev("!!document.querySelector('.pt-ready')"); lay = await w.ev("(document.querySelector('#limitLayer')||{}).innerText||''")
                check(f'money2 limit {trial}: a day limit of exactly the cost shown ({est["spend"]}) lets the batch through, and it stays within it', ok and await w.ev("Nutcade.r8.spentDay() <= Nutcade.S.limits.day"), (lay[:160], await w.err()))
                await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); Nutcade.S.limits=null; Nutcade.closeSheet()")
            await w.pg.context.close()
            # F2: the limit runs out in the middle of a batch (another payment used the day): what was made is never made again
            for withpin in (False, True):
                w = await funded(b, [NOFEE], 6000)
                if withpin:
                    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=pinSet]'); await w.wait(200)
                    for _ in range(2):
                        for k in PIN: await w.click(f'[data-pinpad] [data-k="{k}"]')
                        await w.click('[data-pinpad] [data-k=ok]'); await w.wait(300)
                    await w.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await w.ev("Nutcade.closeSheet()")
                await w.ev("Nutcade.S.limits={per:0, day:5000}")
                h = await slow(w, 0.8)
                await open_print(w, NOFEE); await w.fill('#ptAmt', '100'); await w.fill('#ptCount', '5'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000)
                await w.click('[data-act=ptMake]'); await w.until(f"{PRINTED}.length>=2", 30000)
                await w.ev("Nutcade.S.limits.day = Nutcade.r8.spentDay() + 50")   # (as if another payment used up the day meanwhile)
                await w.until("!!document.querySelector('.pt-stopped') || !!document.querySelector('#limitLayer') || !!document.querySelector('.pt-ready')", 60000); await w.wait(600)
                if withpin and await w.ev("!!document.querySelector('#limitLayer [data-pinpad]')"):
                    for k in PIN: await w.click(f'#limitLayer [data-pinpad] [data-k="{k}"]')
                    await w.click('#limitLayer [data-pinpad] [data-k=ok]'); await w.wait(4000)
                await w.pg.unroute('**/v1/swap', h)
                n = await w.ev(f"{PRINTED}.length"); txt = (await w.sheet_text()) + await w.ev("(document.querySelector('#limitLayer')||{}).innerText||''")
                check(f'money2 mid-batch limit (PIN {withpin}): no token made twice, never more than the 5 asked for', 2 <= n < 5 and len(set(await w.ev(f"{PRINTED}.map(t=>t.print.i)"))) == n, n)
                check(f'money2 mid-batch limit (PIN {withpin}): the screen says exactly how many were made ({n} of 5), not "nothing was sent"', f'{n} of 5' in txt and 'Nothing was sent' not in txt, txt[:300])
                await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); document.querySelector('.pt-stopped [data-act=ptReprint]')?.click()"); await w.until("!!document.querySelector('.pt-ready')", 30000)
                check(f'money2 mid-batch limit (PIN {withpin}): the {n} made can be printed from the stop screen', await w.ev("!!document.querySelector('.pt-ready') && NutTokens.lastCheck.length") == n)
                await w.until("Nutcade.S.ops.length===0", 20000)
                check(f'money2 mid-batch limit (PIN {withpin}): history = balance, nothing left open', not await books(w, (NOFEE,)) and await w.ev("Nutcade.S.ops.length") == 0)
                await w.pg.context.close()
            # F3: the coins actually in the token (the receiver's fee coin too) decide whether its code fits on paper
            w = await funded(b, [FEE, NOFEE], 6000)
            for mint, ok_ in ((FEE, False), (NOFEE, True)):
                n0 = await w.ev(f"{PRINTED}.length"); b0 = await w.bal(mint)
                await open_print(w, mint); await w.fill('#ptAmt', '1023'); await w.fill('#ptCount', '2'); await w.click('[data-act=ptNext]'); await w.wait(1500)
                e = await w.err(); can = await w.ev("!!document.querySelector('[data-act=ptMake]')")
                if ok_: check('money2 density: 1,023 SAT on the no-fee mint (10 coins) fits and is offered', can, e)
                else: check('money2 density: 1,023 SAT on the fee mint (10 coins + the fee coin = 11) is refused before anything is made, counting 11', not can and 'too dense' in e and '11 coins' in e and await w.ev(f"{PRINTED}.length") == n0 and await w.bal(mint) == b0, e)
                await w.ev("Nutcade.closeSheet()")
            await w.pg.context.close()
            # O1: a click on a disabled button does nothing (here Make while a batch is being made, and Create token)
            w = await funded(b, [NOFEE], 3000); h = await slow(w, 0.6)
            await open_print(w, NOFEE); await w.fill('#ptAmt', '50'); await w.fill('#ptCount', '3'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000)
            await w.ev("(()=>{const b=document.querySelector('[data-act=ptMake]'); b.click(); setTimeout(()=>b.dispatchEvent(new MouseEvent('click',{bubbles:true})),200)})()")
            await w.until("!!document.querySelector('.pt-ready')", 60000); await w.wait(2500)
            check('money2 disabled: a click on Make while it is making does nothing (one batch of 3)', await w.ev(f"{PRINTED}.length") == 3, await w.ev(f"{PRINTED}.length"))
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '40')
            n0 = await w.ev("Nutcade.S.txs.length")
            await w.ev("(()=>{const b=document.querySelector('[data-act=doSendEcash]'); b.click(); setTimeout(()=>b.dispatchEvent(new MouseEvent('click',{bubbles:true})),150)})()"); await w.wait(4000)
            check('money2 disabled: a click on Create token while it is making the token does nothing (one token)', await w.ev(f"Nutcade.S.txs.length - {n0}") == 1, await w.ev(f"Nutcade.S.txs.slice(0,3).map(t=>[t.amount,t.note])"))
            await w.pg.unroute('**/v1/swap', h)
            check('money2 disabled: history = balance', not await books(w, (NOFEE,)))
            await w.pg.context.close()
        await section('money2', money2)

        # ---------- owner additions: the first-scan rule first, amount presets with their value, take back after printing ----------
        async def owner():
            RULE = 'A printed token is cash. Whoever scans it first gets the sats. Keep it folded or hidden until you hand it over.'
            w = await funded(b, [FEE, NOFEE], 6000); await w.use(NOFEE)
            async def tap(x):
                await x.home(); await x.click('[data-act=send]'); await x.wait(150); await x.click('[data-act=ptOpen]'); await x.until("!!document.querySelector('#ptAmt') || !!document.querySelector('.pt-intro')", 5000)
                return await x.ev("!!document.querySelector('.pt-intro')"), await x.sheet_text()
            intro, t = await tap(w)
            check('owner intro: the first tap on Print tokens shows the first-scan rule before anything else, with I understand', intro and RULE in t and 'I UNDERSTAND' in t.upper() and not await w.ev("!!document.querySelector('#ptAmt')"), t[:300])
            await w.click('[data-act=ptIntroOk]'); await w.until("!!document.querySelector('#ptAmt')", 5000)
            check('owner intro: I understand goes on to the Print tokens screen', await w.ev("!!document.querySelector('#ptAmt')"))
            intro, t = await tap(w)
            check('owner intro: shown once (the second time straight to the screen)', not intro)
            await w.pg.reload(); await w.wait(1200); intro, t = await tap(w)
            check('owner intro: still once after a reload', not intro)
            # the same wallet restored on a new phone: shown there again
            y = await wallet(b); await y.pg.check('#ack'); await y.click('[data-act=gateRestore]'); await y.until("!!document.querySelector('#phraseIn')", 5000)
            await y.fill('#phraseIn', await w.ev("Nutcade.S.seed.mnemonic")); await y.ev("document.querySelectorAll('[data-rmint]').forEach(i=>{i.checked=false})"); await y.fill('#rmExtra', NOFEE)
            await y.click('[data-act=doRestorePhrase]'); await y.until("/SCAN COMPLETE|CONTINUE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 180000); await y.ev("Nutcade.closeSheet()")
            await y.use(NOFEE); intro, t = await tap(y)
            check('owner intro: the same wallet restored on a new phone shows it again', intro and RULE in t, t[:200])
            await y.pg.context.close()
            # in every language
            for lang in LANGS[1:]:
                z = await wallet(b, lang); await z.create(); await z.add_mint(NOFEE); await z.ev("window.__i18nMiss=new Set()")
                intro, t = await tap(z); miss = await z.ev("[...(window.__i18nMiss||[])]")
                check(f'owner intro {lang}: the rule in the language', intro and 'Whoever scans' not in t and len(t) > 60 and not miss, (t[:160], miss[:4]))
                await z.pg.context.close()
            # presets: 1,000 / 2,100 / 5,000 / 21,000 and Other, each with its value in the chosen currency from the price the app has
            await w.ev("Nutcade.S.prefs.fiat=false; Nutcade.closeSheet()")
            await open_print(w, NOFEE)
            pre = await w.ev("[...document.querySelectorAll('[data-act=ptPreset]')].map(b=>[b.dataset.a, b.innerText.replace(/\\s+/g,' ').trim()])")
            check('owner presets: 1,000 / 2,100 / 5,000 / 21,000 and Other', [x[0] for x in pre] == ['1000', '2100', '5000', '21000', 'other'] and '2,100' in pre[1][1], pre)
            check('owner presets: no price available (Show Bitcoin price off): no money value shown', await w.ev("[...document.querySelectorAll('.pt-fiat')].every(e=>!e.innerText.trim())"))
            reqs = []
            w.pg.on('request', lambda r: reqs.append(r.url) if not re.match(r'https?://(127\.0\.0\.1|localhost)', r.url) and not r.url.startswith('data:') else None)
            await w.ev("Nutcade.S.prefs.fiat=true; Nutcade.S.prefs.currency='USD'; Nutcade.livePrice(50000,'USD'); Nutcade.closeSheet()")
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('#ptAmt')", 5000); await w.wait(400)
            fx = await w.ev("[...document.querySelectorAll('[data-act=ptPreset]')].map(b=>(b.parentElement.querySelector('.pt-fiat[data-a=\"'+b.dataset.a+'\"]')||{}).innerText||'')")
            check('owner presets: each preset shows about what it is worth from the price the app already has ($0.50 / $1.05 / $2.50 / $10.50 at $50,000)', fx[:4] == ['≈ $0.50', '≈ $1.05', '≈ $2.50', '≈ $10.50'], fx)
            check('owner presets: no network request for it', not reqs, reqs[:3])
            await w.click('[data-act=ptPreset][data-a="2100"]'); await w.wait(100)
            check('owner presets: a preset fills the amount and is marked (✓, not color alone)', await w.ev("Nutcade.parseSat(document.querySelector('#ptAmt').value)") == 2100 and await w.ev("document.querySelector('[data-act=ptPreset][data-a=\"2100\"]').getAttribute('aria-pressed')") == 'true' and '✓' in await w.ev("getComputedStyle(document.querySelector('[data-act=ptPreset][data-a=\"2100\"]'),'::before').content"))
            await w.click('[data-act=ptPreset][data-a=other]'); await w.wait(100)
            check('owner presets: Other clears the amount for any amount', await w.ev("document.querySelector('#ptAmt').value===''") and await w.ev("document.querySelector('[data-act=ptPreset][data-a=other]').getAttribute('aria-pressed')") == 'true')
            # a preset whose code would be too dense on this mint (fee coin counted) is disabled, with the reason
            for mint in (FEE, NOFEE):
                info = await w.ev(f"NutTokens.presetInfo({json.dumps(mint)})")
                check(f'owner presets {mint[-4:]}: every preset fits the 133-module rule here (fee coins counted)', all(x['fits'] == (x['modules'] <= 133) for x in info) and all(x['fits'] for x in info), info)
                lim = max(x['modules'] for x in info) - 1
                await w.ev(f"NutTokens.maxModules={lim}; Nutcade.closeSheet()"); await open_print(w, mint); await w.wait(200)
                st = await w.ev("[...document.querySelectorAll('[data-act=ptPreset]')].filter(b=>b.dataset.a!=='other').map(b=>[b.dataset.a, b.disabled])")
                info = {str(x['a']): x for x in await w.ev(f"NutTokens.presetInfo({json.dumps(mint)})")}
                why = await w.ev("(document.querySelector('.pt-pre-why')||{}).innerText||''")
                check(f'owner presets {mint[-4:]}: a preset that would be too dense here is disabled, the reason shown, the others not', all(d == (not info[a]['fits']) for a, d in st) and any(d for a, d in st) and not all(d for a, d in st) and 'too dense' in why and 'coins' in why, (st, why))
                await w.ev("NutTokens.maxModules=133")
            # after printing: take it back any time, with a link to the list
            await w.ev("Nutcade.closeSheet()")
            s_, e, bid = await make(w, NOFEE, 2100, 1)
            await w.click('[data-act=ptPrint]'); await w.until("!!document.querySelector('.pt-after')", 5000)
            t = await w.ev("(document.querySelector('.pt-after')||{}).innerText||''")
            check('owner after print: "Nobody claimed it? Take it back any time in Notes → Printed tokens", with a link', 'Nobody claimed it? Take it back any time in Notes → Printed tokens' in t and await w.ev("!!document.querySelector('.pt-after [data-act=ptList]')"), t)
            await w.click('.pt-after [data-act=ptList]'); await w.until("!!document.querySelector('.pt-list')", 5000)
            check('owner after print: the link opens Printed tokens', await w.ev("!!document.querySelector('.pt-list')"))
            await w.ev("NutTokens.endPrint()")
            check('owner: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('owner', owner)

        # ---------- every new screen in five languages at 320 px: nothing off screen, nothing left in English ----------
        async def narrow():
            for lang in LANGS:
                w = await wallet(b, lang, vw=320, vh=640); await w.create(); await w.add_mint(NOFEE); await w.use(NOFEE); await w.receive_ln(3000)
                await w.ev("window.__i18nMiss=new Set()"); over = {}
                await open_print(w, NOFEE); over['print'] = await w.ev(OVER_JS)
                await w.fill('#ptAmt', '128'); await w.fill('#ptCount', '2'); await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 10000); over['cost'] = await w.ev(OVER_JS)
                await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('.pt-ready')", 60000); await w.wait(400); over['ready'] = await w.ev(OVER_JS)
                if lang == 'en': await w.pg.screenshot(path=os.path.join(OUT, 'tok-ready-320.png'), full_page=True)
                await plist(w); over['list'] = await w.ev(OVER_JS)
                await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(200); over['notes'] = await w.ev(OVER_JS)
                await w.ev("document.querySelector('#txList [data-act=tx]').click()"); await w.wait(300); over['line'] = await w.ev(OVER_JS)
                await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(200); over['settings'] = await w.ev(OVER_JS)
                miss = await w.ev("[...(window.__i18nMiss||[])]")
                check(f'narrow {lang}: Print tokens, its cost, the ready screen, the list, the notes and Settings fit 320 px', not any(over.values()), {k: v for k, v in over.items() if v})
                check(f'narrow {lang}: nothing new left untranslated', not miss, miss[:6])
                await w.pg.context.close()
        await section('narrow', narrow)

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

        # ---------- 1.14.2 interplay (rebase onto the PIN guard): PIN on x per-payment limit x wrong / cancel / right PIN;
        # the PIN lets this one batch through and nothing after it; the PIN guard on the backup keeps the print records;
        # PIN removed keeps the list; the duress wallet's printed tokens stay its own; a mint that starts taking fewer
        # coins per request before or during a batch: never made another (dearer) way, never over the cost shown ----------
        async def pinlim():
            async def pad(x, pin, root='[data-pinpad]'):
                for k in pin: await x.click(f'{root} [data-k="{k}"]')
                await x.click(f'{root} [data-k=ok]')
            async def set_pin(x):
                await x.ev("Nutcade.closeSheet()"); await x.click('[data-act=tab][data-tab=settings]'); await x.wait(150); await x.click('[data-act=pinSet]'); await x.wait(200)
                await pad(x, PIN); await x.wait(300); await pad(x, PIN); await x.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await x.wait(500); await x.ev("Nutcade.closeSheet()")
            async def set_limits(x, per, day):
                await x.ev("Nutcade.closeSheet()"); await x.click('[data-act=tab][data-tab=settings]'); await x.wait(150); await x.click('[data-act=limOpen]'); await x.until("!!document.querySelector('#limDay')", 5000)
                await x.ev(f"(()=>{{for(const [id,v] of [['limPer',{json.dumps(per)}],['limDay',{json.dumps(day)}]]){{const e=document.querySelector('#'+id);e.value=v;e.dispatchEvent(new Event('input',{{bubbles:true}}))}}}})()")
                await x.click('[data-act=limSave]'); await x.wait(400)
                if await x.ev("!!document.querySelector('#layer [data-pinpad]')"): await pad(x, PIN, '#layer [data-pinpad]'); await x.until("!document.querySelector('#layer [data-pinpad]')", 20000)
                await x.ev("Nutcade.closeSheet()")
            async def to_make(x, mint, amount, count):
                await open_print(x, mint); await x.fill('#ptAmt', str(amount)); await x.fill('#ptCount', str(count)); await x.click('[data-act=ptNext]')
                await x.until("!!document.querySelector('[data-act=ptMake]') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 20000)
                return await x.ev("NutTokens.lastEstimate")
            LAY = "(document.querySelector('#limitLayer')||{}).innerText||''"
            # A: PIN on, per-payment limit 1,000, a batch of 3 x 500 (1,500): asks the PIN for the whole batch
            w = await funded(b, [NOFEE], 6000); await set_pin(w); await set_limits(w, '1000', '')
            n0 = await w.ev(f"{PRINTED}.length"); b0 = await w.bal(NOFEE); d0 = await w.ev("Nutcade.r8.spentDay()")
            await to_make(w, NOFEE, 500, 3); await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('#limitLayer [data-pinpad]')", 20000)
            check('pinlim: PIN on, 3 x 500 over a 1,000 per-payment limit: the PIN pad asks for the whole batch (1,500), nothing made yet', '1,500' in await w.ev(LAY) and await w.ev(f"{PRINTED}.length") == n0 and await w.bal(NOFEE) == b0, await w.ev(LAY))
            await pad(w, '000000', '#limitLayer [data-pinpad]'); await w.until("/wrong/i.test((document.querySelector('#limitLayer')||{}).innerText||'')", 20000); await w.wait(500)
            check('pinlim: a wrong PIN makes nothing and keeps asking', await w.ev(f"{PRINTED}.length") == n0 and await w.bal(NOFEE) == b0 and await w.ev("!!document.querySelector('#limitLayer [data-pinpad]')"))
            await w.click('#limitLayer [data-act=limitNo]'); await w.wait(800)
            check('pinlim: Cancel makes nothing', await w.ev(f"{PRINTED}.length") == n0 and await w.bal(NOFEE) == b0 and not await w.ev("!!document.querySelector('#limitLayer')"))
            await w.ev("Nutcade.closeSheet()"); await to_make(w, NOFEE, 500, 3); await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('#limitLayer [data-pinpad]')", 20000)
            await pad(w, PIN, '#limitLayer [data-pinpad]'); await w.until("!!document.querySelector('.pt-ready') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 90000); await w.wait(500)
            made = await w.ev(f"{PRINTED}.length") - n0
            check('pinlim: the right PIN: the whole batch of 3 is made, once, and the day counts all 1,500', made == 3 and await w.ev("Nutcade.r8.spentDay()") - d0 == 1500 and await w.bal(NOFEE) == b0 - 1500, (made, await w.err(), await w.ev("Nutcade.r8.spentDay()") - d0))
            await w.ev("Nutcade.closeSheet()")
            # the PIN was for that batch only: the next batch over the limit, and a plain token over it, ask again
            await to_make(w, NOFEE, 600, 2); await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('#limitLayer') || !!document.querySelector('.pt-ready')", 20000)
            check('pinlim: the PIN does not carry over: the next batch over the limit asks again, nothing made', await w.ev("!!document.querySelector('#limitLayer [data-pinpad]')") and await w.ev(f"{PRINTED}.length") - n0 == 3)
            await w.click('#limitLayer [data-act=limitNo]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '1200'); await w.click('[data-act=doSendEcash]'); await w.until("!!document.querySelector('#limitLayer') || !!document.querySelector('.tokbox, [data-act=copyTok]')", 20000)
            check('pinlim: nor to a plain token over the limit', await w.ev("!!document.querySelector('#limitLayer [data-pinpad]')"))
            await w.click('#limitLayer [data-act=limitNo]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
            # the PIN guard: Download backup asks for the PIN first; the file then has every printed token with its record
            mine = await w.ev(f"{PRINTED}.map(t=>t.print.code)")
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
            await w.ev("window.__dlx=0; document.addEventListener('click', e=>{ if(e.target.closest && e.target.closest('a[download]')) window.__dlx++ }, true)")
            await w.click('#app [data-act=backupDownload]'); await w.wait(400)
            asked = await w.ev("!!document.querySelector('#layer [data-pinpad=guard]')")
            async with w.pg.expect_download() as d:
                await pad(w, PIN, '#layer [data-pinpad=guard]')
            data = open(await (await d.value).path()).read()
            check('pinlim: PIN guard: Download backup asks for the PIN, then the file holds every printed token with its record', asked and all(c in data for c in mine) and data.count('"print"') >= len(mine), (asked, len(mine)))
            await w.ev("Nutcade.closeSheet()")
            # PIN removed: the list and the first-scan rule seen stay
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=pinRemove]'); await w.wait(200); await pad(w, PIN); await w.until("!Nutcade.vault.on", 20000); await w.wait(1500)
            await w.ev("Nutcade.closeSheet()"); await w.pg.reload(); await w.wait(1500)
            after = await w.ev(f"{PRINTED}.map(t=>t.print.code)")
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=ptOpen]'); await w.until("!!document.querySelector('#ptAmt') || !!document.querySelector('.pt-intro')", 5000)
            check('pinlim: PIN removed (and a reload): the printed tokens are all still there, the first-scan rule not shown again', sorted(after) == sorted(mine) and not await w.ev("!!document.querySelector('.pt-intro')"), (len(after), len(mine)))
            check('pinlim: history = balance', not await books(w, (NOFEE,)), await books(w, (NOFEE,)))
            check('pinlim A: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
            # D: the duress wallet: its printed tokens are its own; nothing about them in plain storage; the real wallet doesn't see them
            DPIN = '246802'
            w = await funded(b, [NOFEE], 4000); await set_pin(w)
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=duressOpen]'); await w.wait(250)
            await pad(w, PIN); await w.wait(800); await pad(w, DPIN); await w.wait(300); await pad(w, DPIN); await w.until("!!document.querySelector('#duressAmt')", 8000)
            await w.fill('#duressAmt', '800'); await w.click('[data-act=duressMake]'); await w.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000)
            await w.ev("Nutcade.closeSheet()"); real_n = await w.ev(f"{PRINTED}.length")
            await w.pg.reload(); await w.wait(700); await w.until("!!document.querySelector('[data-pinpad]')", 8000); await pad(w, DPIN); await w.until("Nutcade.vault.open", 20000); await w.wait(800)
            await w.until("Object.values(Nutcade.S.proofs).flat().length>0", 30000); await w.wait(800)
            dm = await w.ev("Nutcade.S.active")
            s_, e, bid = await make(w, dm, 100, 2)
            dn = await w.ev(f"{PRINTED}.length")
            check('pinlim duress: the duress wallet prints its own tokens (2 x 100)', bool(bid) and dn == 2, (e, dn))
            plain = await w.ev("JSON.stringify(Object.fromEntries(Object.keys(localStorage).filter(k=>k!=='nutcade:vault').map(k=>[k,localStorage.getItem(k)])))")
            codes = await w.ev(f"{PRINTED}.map(t=>t.print.code)")
            check('pinlim duress: nothing about them in plain storage (no ptintro, no code, no print record)', 'ptintro' not in plain and '"print"' not in plain and not any(c in plain for c in codes), plain[:200])
            await w.ev("Nutcade.closeSheet()"); await w.pg.reload(); await w.wait(700); await w.until("!!document.querySelector('[data-pinpad]')", 8000); await pad(w, PIN); await w.until("Nutcade.vault.open", 20000); await w.wait(1500)
            check("pinlim duress: the real wallet doesn't see them (its own printed tokens unchanged)", await w.ev(f"{PRINTED}.length") == real_n and not await w.ev(f"{PRINTED}.some(t=>{json.dumps(codes)}.includes(t.print.code))"))
            check('pinlim duress: real wallet history = balance', not await books(w, (NOFEE,)), await books(w, (NOFEE,)))
            await w.pg.context.close()
            # E: the fee mint starts taking only 3 coins per request (and enforcing it), before Make and during a batch
            # (1,024: one coin, so in steps the library could still make it, at a higher fee than shown)
            def dropper(after_swaps):
                st = {'swaps': 0, 'on': False, 'big': 0}
                async def h(route):
                    rq = route.request; ep = rq.url.split('/v1/')[-1]
                    try:
                        if ep == 'swap' and rq.method == 'POST' and not st['on']:
                            st['swaps'] += 1
                            if st['swaps'] > after_swaps: st['on'] = True
                        if not st['on']: return await route.fallback()
                        if ep == 'info' and rq.method == 'GET':
                            r = await route.fetch(); j = await r.json(); j['max_array_length'] = 3; return await route.fulfill(response=r, body=json.dumps(j))
                        if rq.method == 'POST':
                            j = json.loads(rq.post_data or '{}'); n = max([len(j[k]) for k in ('inputs', 'outputs', 'Ys') if isinstance(j.get(k), list)] or [0])
                            if n > 3:
                                st['big'] += 1
                                return await route.fulfill(status=422, body=json.dumps({'detail': [{'type': 'too_long', 'msg': f'List should have at most 3 items after validation, not {n}'}]}), headers={'content-type': 'application/json'})
                        await route.fallback()
                    except Exception:
                        try: await route.fallback()
                        except Exception: pass
                return st, h
            for after_swaps, tag in ((0, 'before Make'), (1, 'after the first token')):
                w = await funded(b, [FEE], 9000)
                est = await to_make(w, FEE, 1024, 4); b0 = await w.bal(FEE); n0 = await w.ev(f"{PRINTED}.length")
                st, h = dropper(after_swaps); await w.pg.route(FEE + '/v1/**', h)
                await w.click('[data-act=ptMake]'); await w.until("!!document.querySelector('.pt-ready') || !!document.querySelector('.pt-stopped') || /\\S/.test((document.querySelector('#sheetErr')||{}).innerText||'')", 180000); await w.wait(1500)
                txt = await w.sheet_text(); made = await w.ev(f"{PRINTED}.filter(t=>t.status!=='failed').length") - n0; spent = b0 - await w.bal(FEE)
                odd = await w.ev("Nutcade.S.txs.filter(t=>/part \\d+ of|smaller requests/.test(t.note||'')).length")
                want = 0 if after_swaps == 0 else 1
                check(f'pinlim request limit {tag}: never made another way: {want} token(s) of 4, the rest refused, never over the cost shown ({est["spend"]})', made == want and spent <= est['spend'] and spent == made * 1024 + sum(t.get('fee', 0) for t in await w.ev(f"{PRINTED}")) and not odd and not await w.ev("!!document.querySelector('.pt-ready')"), (made, spent, odd, txt[:240]))
                check(f'pinlim request limit {tag}: the screen says why (coins per request){", and exactly how many were made" if want else ""}', re.search(r'coins per request', txt) and (not want or '1 of 4' in txt), txt[:300])
                await w.pg.unroute(FEE + '/v1/**', h); await w.until("Nutcade.S.ops.length===0", 30000)
                check(f'pinlim request limit {tag}: history = balance, nothing left open', not await books(w, (FEE,)) and await w.ev("Nutcade.S.ops.length") == 0, await books(w, (FEE,)))
                await w.pg.context.close()
        await section('pinlim', pinlim)

        bad = [r for r in results if not r[1]]
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
