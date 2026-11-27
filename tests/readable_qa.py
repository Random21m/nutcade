"""1.39-era "Readable text" setting (Settings -> Look & sound, off by default).

On: the wallet screens use the plain system font stack at a larger size, in rem so they follow the browser's text size;
the logo, headings and everything in the games keep the pixel fonts. A font change only: every theme works. Off: the app
renders exactly as before. The class `readable` on <html> is set by the page's first script from the stored setting, so
there is no flash of pixel text.

Covered: off by default with today's computed fonts and sizes; turning it on (the real switch) changes wallet text to the
system font with larger sizes; headings and game screens keep the pixel fonts; the setting persists across a reload, the
class is on <html> before the body exists (no flash), and it is applied on the PIN lock screen; the root font size scales
wallet text when on and does not when off; no network request for a font; every theme; the label and hint translated in
every language; no horizontal overflow, no clipped buttons, the tab bar and the PIN pad fit at 320, 375 and 430 px in
every language with it on. Needs no mint: relays and the price service are stubs or off, anything else outside is blocked.
R_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as MINT

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
LANGS = ['en', 'es', 'pt', 'de', 'fr']
SIZES = [(320, 640), (375, 667), (430, 932)]
LABEL = {'en': 'Readable text', 'es': 'Texto legible', 'pt': 'Texto legível', 'de': 'Gut lesbarer Text', 'fr': 'Texte lisible'}
HINT = {'en': 'Plain, larger text', 'es': 'Texto sencillo y más grande', 'pt': 'Texto simples e maior', 'de': 'Schlichter, größerer Text', 'fr': 'Texte simple et plus grand'}
THEMES = ['neon', 'amber', 'phosphor']
TABS = ['wallet', 'arcade', 'history', 'mints', 'settings']

async def wallet(b, name='readable', vw=375, vh=667, lang='en', on=False, blocked=None, mobile=True):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'fiat': False, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    if on: prefs['readable'] = True
    # a seed only on the very first load of this context: reloads keep whatever the app has stored since
    await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ");"
        # what the page looked like when its body was first created (before the first paint), and at DOMContentLoaded
        "window.__rd={};new MutationObserver((m,o)=>{if(document.body){window.__rd.atBody=document.documentElement.classList.contains('readable');o.disconnect()}}).observe(document,{childList:true,subtree:true});"
        "document.addEventListener('DOMContentLoaded',()=>{window.__rd.atDCL=document.documentElement.classList.contains('readable')});")
    async def gate(route):   # the services are stubs: nothing outside this machine is reached, and a font request would be seen
        u = route.request.url
        if re.match(r'https?://(127\.0\.0\.1|localhost)[:/]', u) or u.startswith('data:') or u.startswith('blob:'): return await route.continue_()
        if blocked is not None: blocked.append(u)
        await route.abort()
    await ctx.route('**/*', gate)
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w

async def section(name, fn):
    only = [x for x in os.environ.get('R_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])

async def frames(w):   # two animation frames: what was just changed has been laid out
    await w.ev("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
async def ready(w):    # a reload has finished and the app has drawn something
    await w.until("document.readyState==='complete' && !!document.querySelector('#app *')", 15000); await frames(w)
async def tab(w, t):
    await w.ev(f"Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab={t}]').click()")
    await w.until(f"document.querySelector('[data-act=tab][data-tab={t}]').getAttribute('aria-current')==='page'", 5000); await frames(w)

# a few elements on the wallet screens, by CSS selector, and what each one looked like before this setting existed
BEFORE = {'body': ('VT323', 22), '.btn.sm': ('Press Start', 9), '.tab': ('Press Start', 9), '.field label': ('Press Start', 9), '.th': ('VT323', 17), 'select.inp': ('VT323', 20)}
def probe_js(sels):
    return "(()=>{const o={};for(const s of %s){const e=document.querySelector(s);if(!e){o[s]=null;continue}const c=getComputedStyle(e);o[s]={f:c.fontFamily,s:parseFloat(c.fontSize)}}return o})()" % J(sels)
SYS = re.compile(r'system-ui|-apple-system|Segoe UI|Roboto', re.I)
PIX = re.compile(r'Press Start|VT323', re.I)

# anything poking out sideways, and any button or tab whose text does not fit inside it (clipped, not merely wrapped)
OVER_JS = """(()=>{const W=document.documentElement.clientWidth,out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(!e.getClientRects().length||e.closest('.sr,.cab'))continue;const r=e.getBoundingClientRect();if(r.right>W+1||r.left<-1)out.push((e.className&&e.className.baseVal===undefined?e.className:e.tagName)+':'+Math.round(r.left)+'..'+Math.round(r.right))}
  if(document.documentElement.scrollWidth>W+1)out.push('page scrolls sideways '+document.documentElement.scrollWidth);return out.slice(0,5)})()"""
CLIP_JS = """(()=>{const out=[];for(const e of document.querySelectorAll('#app button, #layer button, #app .btn, #layer .btn, .tab span, .seg button, .chip')){
  const r=e.getBoundingClientRect();if(!r.width||!r.height||e.closest('.sr,.pin-keys,.cab'))continue;
  if(e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1)out.push((e.innerText||e.className).trim().slice(0,24)+' '+e.scrollWidth+'x'+e.scrollHeight+' in '+e.clientWidth+'x'+e.clientHeight)}return out.slice(0,5)})()"""
INVIEW = """(sel=>{const e=document.querySelector(sel); if(!e) return 'missing'; const r=e.getBoundingClientRect(); return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight ? 'ok' : [Math.round(r.left),Math.round(r.top),Math.round(r.right),Math.round(r.bottom)].join(',')})"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ---------- off by default: the app looks as before ----------
        async def off():
            w = await wallet(b, 'off'); await w.create()
            check('off: no readable class on the page by default', not await w.ev("document.documentElement.classList.contains('readable')"))
            check('off: the prefs hold no readable switch turned on', not await w.ev("!!Nutcade.S.prefs.readable"))
            await tab(w, 'settings')
            check('off: the Settings switch is there and unchecked', await w.ev("(()=>{const i=document.querySelector('#p_readable');return !!i && i.type==='checkbox' && !i.checked})()"))
            check('off: the switch sits in Look & sound', await w.ev("!!document.querySelector('#set-look #p_readable')"))
            got = await w.ev(probe_js(list(BEFORE)))
            bad = {s: got[s] for s, (f, z) in BEFORE.items() if got.get(s) is None or f not in got[s]['f'] or got[s]['s'] != z}
            check('off: computed fonts and sizes are today\'s (pixel fonts, 22/9/9/9/17/20 px)', not bad, {s: got[s] for s in bad})
            await tab(w, 'wallet')
            check('off: the balance stays in the pixel font', 'Press Start' in await w.ev("getComputedStyle(document.querySelector('.credit-num')).fontFamily"))
            check('off: no script errors', not w.errs, w.errs[:3]); await w.pg.context.close()
        await section('off', off)

        # ---------- on: the switch, system font, larger sizes, pixel fonts kept where they belong ----------
        async def on():
            w = await wallet(b, 'on'); await w.create()
            before = {}
            await tab(w, 'wallet'); before['balance'] = await w.ev(probe_js(['.credit-num', '.push .cap', '.push .t']))
            await tab(w, 'settings')
            before['set'] = await w.ev(probe_js(['body', '.btn', '.field label', '.th', '.inp', '.toggle', '.tl', '.label', '.sub']))
            await w.pg.click('#p_readable'); await frames(w)
            check('on: the switch turns the class on at once', await w.ev("document.documentElement.classList.contains('readable') && Nutcade.S.prefs.readable===true && document.querySelector('#p_readable').checked"))
            after = await w.ev(probe_js(list(before['set'].keys())))
            wrong = {s: after[s] for s in after if after[s] and before['set'][s] and not SYS.search(after[s]['f'])}
            check('on: settings text (body, buttons, labels, hints, inputs, toggles) is in the system font', not wrong and after['body'] and SYS.search(after['body']['f']), wrong or after['body'])
            check('on: the system font has no downloaded face in the stack (no network font)', all('Press Start' not in after[s]['f'] and 'VT323' not in after[s]['f'] for s in after if after[s]), {s: after[s]['f'] for s in after if after[s]})
            small = {s: (before['set'][s]['s'], after[s]['s']) for s in ('.btn', '.field label', '.label', '.sub') if after.get(s) and before['set'].get(s) and after[s]['s'] <= before['set'][s]['s']}
            check('on: pixel-font text (buttons, field labels, labels) is larger than before', not small and after['.btn']['s'] > before['set']['.btn']['s'], small or (before['set']['.btn'], after['.btn']))
            check('on: input and body text are at least 20 px, hints and toggles at least 17 px', after['.inp']['s'] >= 20 and after['body']['s'] >= 20 and after['.th']['s'] >= 17 and after['.toggle']['s'] >= 18, {s: after[s]['s'] for s in after if after[s]})
            check('on: sizes are in rem (they are whole multiples of the 16 px root)', all(round(after[s]['s'] / 16 * 10000) % 625 == 0 for s in ('.btn', '.inp', '.th', '.toggle', 'body')), {s: after[s]['s'] for s in after if after[s]})
            await tab(w, 'wallet')
            a2 = await w.ev(probe_js(['.credit-num', '.push .cap', '.push .t']))
            check('on: the balance and the big buttons are in the system font, the balance still big', all(SYS.search(a2[s]['f']) for s in a2 if a2[s]) and a2['.credit-num']['s'] >= 28, a2)
            # no wallet text in the system font under 13 px (codes and addresses in a monospace box are exempt)
            tiny = []
            for t in TABS[:1] + TABS[2:]:
                await tab(w, t)
                tiny += [t + ': ' + x for x in await w.ev("""(()=>{const out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
                  if(![...e.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim()))continue;const s=getComputedStyle(e),r=e.getBoundingClientRect();
                  if(!r.width||e.closest('.sr,.code,.mono,.qr,canvas,svg,.words,.marquee,.h2,.sheet-head,.tab'))continue;
                  if(!/Press Start|VT323/.test(s.fontFamily)&&parseFloat(s.fontSize)<13)out.push(e.innerText.trim().slice(0,24)+' '+s.fontSize)}return out.slice(0,6)})()""")]
            check('on: no system-font text under 13 px on the wallet, notes, mints and settings screens', not tiny, tiny[:6])
            # headings and the logo keep the pixel font
            await tab(w, 'settings')
            hs = await w.ev("""(()=>{const f=s=>{const e=document.querySelector(s);return e?getComputedStyle(e).fontFamily:null};return {h1:f('.marquee h1'),h2:f('.h2'),logo:!!document.querySelector('.marquee .logo svg, .marquee h1')}})()""")
            check('on: headings (.h2) keep the pixel font', hs['h2'] and 'Press Start' in hs['h2'], hs)
            check('on: the marquee (logo or title) is still there', hs['logo'] and (hs['h1'] is None or 'Press Start' in hs['h1']), hs)
            await w.ev("document.querySelector('[data-act=reportOpen]') || 0"); await tab(w, 'mints'); await w.ev("document.querySelector('[data-act=addMint]')&&document.querySelector('[data-act=addMint]').click()"); await frames(w)
            sh = await w.ev("(()=>{const e=document.querySelector('.sheet-head h3');return e?getComputedStyle(e).fontFamily:null})()")
            if sh: check('on: a sheet title keeps the pixel font', 'Press Start' in sh, sh)
            await w.ev("Nutcade.closeSheet()")
            # the arcade: open a cabinet, its screen is untouched
            await tab(w, 'arcade')
            await w.ev("document.querySelector('[data-game]').click()"); await w.until("!!document.querySelector('.game-view canvas')", 8000); await frames(w)
            g = await w.ev("""(()=>{const f=s=>{const e=document.querySelector('.game-view '+s);return e?getComputedStyle(e).fontFamily+'|'+getComputedStyle(e).fontSize:null};
              return {view:!!document.querySelector('.game-view'),canvas:!!document.querySelector('.game-view canvas'),ttl:f('.game-top .ttl'),abtn:f('.abtn'),root:getComputedStyle(document.querySelector('.game-view')).fontFamily}})()""")
            check('on: a game screen opens with its canvas', g['view'] and g['canvas'], g)
            check('on: the game screen keeps the pixel fonts (title, buttons, the screen itself)', g['ttl'] and 'Press Start' in g['ttl'] and (g['abtn'] is None or 'Press Start' in g['abtn']) and PIX.search(g['root']), g)
            await w.ev("document.querySelector('[data-g=exit]').click()"); await frames(w)
            lob = await w.ev("(()=>{const e=document.querySelector('.cab .nm');return e?getComputedStyle(e).fontFamily:null})()")
            check('on: the cabinet names in the arcade list keep the pixel font', lob and 'Press Start' in lob, lob)
            # off again
            await tab(w, 'settings'); await w.pg.click('#p_readable'); await frames(w)
            got = await w.ev(probe_js(['body', '.btn', '.field label']))
            check('on: turning it off again gives back the pixel fonts and sizes', not await w.ev("document.documentElement.classList.contains('readable')") and 'VT323' in got['body']['f'] and got['.btn']['s'] == before['set']['.btn']['s'] and got['body']['s'] == 22, got)
            check('on: no script errors', not w.errs, w.errs[:3]); await w.pg.context.close()
        await section('on', on)

        # ---------- persistence and no flash ----------
        async def persist():
            w = await wallet(b, 'persist'); await w.create()
            await tab(w, 'settings')
            await frames(w); was = await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs'))")
            await w.pg.click('#p_readable'); await w.until("JSON.parse(localStorage.getItem('nutcade:prefs')).readable===true", 5000)
            now = await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs'))")
            chg = {k for k in was if was.get(k) != now.get(k)}   # (a first save also writes the app's other defaults that were never stored; nothing already stored may change)
            check('persist: the stored prefs are exactly the earlier ones with readable:true (no other stored value changed)', chg == {'readable'} and now['readable'] is True, (chg, {k: (was.get(k), now.get(k)) for k in chg}))
            await w.pg.reload(); await ready(w)
            rd = await w.ev("window.__rd")
            check('persist: after a reload the class is on <html> when the body is first created (before the first paint)', rd.get('atBody') is True, rd)
            check('persist: and at DOMContentLoaded', rd.get('atDCL') is True, rd)
            check('persist: the first screen already uses the system font (no pixel text flash)', bool(SYS.search(await w.ev("getComputedStyle(document.body).fontFamily"))))
            await tab(w, 'settings')
            check('persist: the switch is still on after the reload', await w.ev("document.querySelector('#p_readable').checked"))
            await w.pg.click('#p_readable'); await frames(w); await w.pg.reload(); await ready(w)
            rd = await w.ev("window.__rd")
            check('persist: turned off and reloaded: no class, at the body or later', rd.get('atBody') is False and rd.get('atDCL') is False and not await w.ev("document.documentElement.classList.contains('readable')"), rd)
            # a damaged stored value must not break the page
            await w.ev("localStorage.setItem('nutcade:prefs','{not json')"); await w.pg.reload(); await ready(w)
            check('persist: a damaged stored setting does not break the page (the class stays off)', not await w.ev("document.documentElement.classList.contains('readable')") and await w.ev("!!document.querySelector('#app')"))
            check('persist: no script errors', not [e for e in w.errs if 'JSON' not in e and 'not json' not in e], w.errs[:3]); await w.pg.context.close()
        await section('persist', persist)

        # ---------- text size follows the browser's setting ----------
        async def zoom():
            for on_ in (True, False):
                w = await wallet(b, 'zoom', on=on_); await w.create(); await tab(w, 'settings')
                s0 = await w.ev(probe_js(['body', '.btn', '.th', '.inp', '.toggle']))
                await w.ev("document.documentElement.style.fontSize='24px'"); await frames(w)   # (the browser's text size set to 150 %)
                s1 = await w.ev(probe_js(['body', '.btn', '.th', '.inp', '.toggle']))
                if on_: check('zoom: text size 150 % scales the wallet text by 1.5 (body, buttons, hints, inputs, toggles)', all(abs(s1[s]['s'] / s0[s]['s'] - 1.5) < 0.02 for s in s0), {s: (s0[s]['s'], s1[s]['s']) for s in s0})
                else: check('zoom: with it off nothing changes (pixel sizes as before, as the page always did)', all(s1[s]['s'] == s0[s]['s'] for s in s0), {s: (s0[s]['s'], s1[s]['s']) for s in s0})
                if on_:
                    await w.ev("document.documentElement.style.fontSize='24px'"); await tab(w, 'wallet')
                    check('zoom: at 150 % the wallet screen does not scroll sideways', not await w.ev(OVER_JS), await w.ev(OVER_JS))
                    v = await w.ev("document.querySelector('meta[name=viewport]').content")
                    check('zoom: the page allows pinch zoom (no user-scalable=no, no maximum-scale)', 'user-scalable' not in v and 'maximum-scale' not in v, v)
                await w.pg.context.close()
        await section('zoom', zoom)

        # ---------- no font is downloaded, nothing else is reached ----------
        async def network():
            blocked = []
            w = await wallet(b, 'net', on=True, blocked=blocked); await w.create()
            fonts = []
            w.pg.on('request', lambda r: fonts.append(r.url) if r.resource_type == 'font' and not r.url.startswith('data:') else None)
            for t in TABS: await tab(w, t)
            await frames(w)
            check('network: no font file was requested from anywhere (the pixel fonts are inlined, the system fonts are local)', not fonts, fonts[:3])
            check('network: nothing outside this machine was reached but the Add-mint list probing its curated mints (/v1/info), as without this setting', all(u.endswith('/v1/info') for u in blocked), blocked[:3])
            check('network: the page itself carries no font file but its own inlined ones', await w.ev("[...document.styleSheets].every(s=>{try{return [...s.cssRules].every(r=>!(r.type===5)||/data:/.test(r.cssText))}catch(e){return true}})"))
            await w.pg.context.close()
        await section('network', network)

        # ---------- every theme ----------
        async def themes():
            w = await wallet(b, 'themes', on=True); await w.create()
            seen = {}
            for th in THEMES:
                await w.ev(f"Nutcade.S.prefs.theme='{th}'; Nutcade.closeSheet(); Nutcade.render()"); await frames(w)
                await tab(w, 'settings')
                st = await w.ev("""(()=>{const c=getComputedStyle(document.body);const b=getComputedStyle(document.querySelector('.btn'));return {cls:document.body.className,html:document.documentElement.classList.contains('readable'),font:c.fontFamily,bf:b.fontFamily,col:b.borderTopColor,ink:c.color,over:document.documentElement.scrollWidth>innerWidth+1}})()""")
                seen[th] = st
                check(f'themes: {th}: the class stays on and the wallet text is in the system font', st['html'] and f'theme-{th}' in st['cls'] and SYS.search(st['font']) and SYS.search(st['bf']), st)
                check(f'themes: {th}: no sideways scroll', not st['over'])
            check('themes: it is a font change only: the theme colours still differ between themes', len({seen[t]['col'] for t in THEMES}) >= 2, {t: seen[t]['col'] for t in THEMES})
            # picking a theme with it on keeps it on
            await w.ev("document.querySelector('[data-act=setTheme][data-t=amber]').click()"); await frames(w)
            check('themes: choosing a theme in Settings keeps Readable text on', await w.ev("document.documentElement.classList.contains('readable') && document.body.classList.contains('theme-amber')"))
            check('themes: no script errors', not w.errs, w.errs[:3]); await w.pg.context.close()
        await section('themes', themes)

        # ---------- the label and hint in every language ----------
        async def labels():
            for lang in LANGS:
                w = await wallet(b, 'lab-' + lang, lang=lang); await w.create(); await tab(w, 'settings')
                t = await w.ev("document.querySelector('#p_readable').closest('label').innerText")
                miss = await w.ev("[...(window.__i18nMiss||[])].filter(s=>/Readable|Plain, larger/.test(s))")
                check(f'{lang}: the switch has its translated label and hint', LABEL[lang] in t and HINT[lang] in t and not miss, (t[:160], miss))
                if lang != 'en': check(f'{lang}: the label is not the English one', 'Readable text' not in t and 'Plain, larger' not in t, t[:160])
                if lang == 'fr': check('fr: French uses "vous"/"votre", not "tu"', not re.search(r'\b(tu|ton|ta|tes)\b', t.lower()), t)
                await w.pg.context.close()
        await section('labels', labels)

        # ---------- layout with it on: every phone width, every language ----------
        async def layout():
            for vw, vh in SIZES:
                for lang in LANGS:
                    w = await wallet(b, f'lay-{vw}-{lang}', vw, vh, lang, on=True); await w.create(); await w.add_mint(MINT); await w.use(MINT)
                    check(f'layout {vw} {lang}: the class is on', await w.ev("document.documentElement.classList.contains('readable')"))
                    bad = {}; opened = {}
                    for t in TABS:
                        await tab(w, t)
                        o, c = await w.ev(OVER_JS), await w.ev(CLIP_JS)
                        if o: bad[t + ' overflow'] = o
                        if c: bad[t + ' clipped'] = c
                    # sheets: send, receive, settings pieces that hold the most text
                    for name, js in [('send', "document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=send]').click()"),
                                     ('receive', "Nutcade.closeSheet(); document.querySelector('[data-act=receive]').click()"),
                                     ('scan', "Nutcade.closeSheet(); document.querySelector('[data-act=scan]').click()"),
                                     ('help', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); const h=document.querySelector('[data-act=helpOpen]'); if(h) h.click()"),
                                     ('contacts', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=contactsOpen]').click()"),
                                     ('restore', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=restore]').click()"),
                                     ('limit', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); const l=document.querySelector('[data-act=limitOpen]'); if(l) l.click()")]:
                        await w.ev("try{" + js + "}catch(e){}"); await frames(w)
                        opened[name] = await w.ev("!!document.querySelector('#layer .sheet')")
                        o, c = await w.ev(OVER_JS), await w.ev(CLIP_JS)
                        if o: bad[name + ' overflow'] = o
                        if c: bad[name + ' clipped'] = c
                    await w.ev("Nutcade.closeSheet()")
                    if vw == 375 and lang == 'en': check('layout: the sheets the layout check opens really opened (send, receive, scan, contacts, restore)', all(opened.get(n) for n in ('send', 'receive', 'scan', 'contacts', 'restore')), opened)
                    check(f'layout {vw}px {lang}: no sideways overflow and no clipped buttons on any tab or sheet', not bad, bad)
                    await tab(w, 'wallet')
                    tabs = await w.ev("""(()=>{const bar=document.querySelector('.tabbar').getBoundingClientRect();return {inside:bar.left>=0&&bar.right<=innerWidth+1&&bar.bottom<=innerHeight+1,
                      each:[...document.querySelectorAll('.tab')].map(t=>{const s=t.querySelector('span'),r=t.getBoundingClientRect();return s.scrollWidth<=t.clientWidth+1&&r.left>=-1&&r.right<=innerWidth+1&&parseFloat(getComputedStyle(s).fontSize)>=10})}})()""")
                    check(f'layout {vw}px {lang}: the tab bar fits, its five labels fit at 10 px or more', tabs['inside'] and len(tabs['each']) == 5 and all(tabs['each']), tabs)
                    if vw == 375: await w.pg.screenshot(path=os.path.join(OUT, f'readable-on-{lang}-{vw}.png'))
                    check(f'layout {vw}px {lang}: no script errors', not w.errs, w.errs[:3]); await w.pg.context.close()
        await section('layout', layout)

        # ---------- the PIN lock screen and pad with it on ----------
        async def pin():
            for vw, vh in [(320, 640), (375, 667)]:
                for lang in LANGS:
                    k = await wallet(b, f'pin-{vw}-{lang}', vw, vh, lang, on=True); await k.create()
                    await k.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=pinSet]').click()"); await frames(k)
                    for rnd in (1, 2):
                        for d in '135790': await k.click(f'[data-pinpad] [data-k="{d}"]')
                        await k.click('[data-pinpad] [data-k=ok]'); await frames(k)
                    await k.until("document.body.innerText.includes('LOCKED DOWN')", 20000)
                    await k.pg.reload(); await ready(k); await k.until("!!document.querySelector('[data-k=ok]')", 15000)
                    rd = await k.ev("window.__rd")
                    check(f'lock {vw} {lang}: the lock screen has the class from the first paint (it is a device setting, not in the vault)', rd.get('atBody') is True and await k.ev("document.documentElement.classList.contains('readable')"), rd)
                    where = {s: await k.ev(f"({INVIEW})('{s}')") for s in ['[data-k=del]', '[data-k="0"]', '[data-k=ok]', '[data-act=forgotPin]']}
                    check(f'lock {vw} {lang}: the whole keypad and Forgot PIN fit without scrolling', all(v == 'ok' for v in where.values()), where)
                    o, c = await k.ev(OVER_JS), await k.ev(CLIP_JS)
                    check(f'lock {vw} {lang}: no sideways overflow or clipped text on the lock screen', not o and not c, (o, c))
                    f = await k.ev("({k:getComputedStyle(document.querySelector('.pin-k')).fontFamily,t:getComputedStyle(document.querySelector('.pinpad .th')||document.body).fontFamily})")
                    check(f'lock {vw} {lang}: the pad text is in the system font', SYS.search(f['k']) and SYS.search(f['t']), f)
                    if vw == 375 and lang == 'en': await k.pg.screenshot(path=os.path.join(OUT, 'readable-on-lock-375.png'))
                    await k.pg.context.close()
        await section('pin', pin)


        # ---------- amounts are never cut inside themselves, at every text size ----------
        # (the Pay sheet's own markup is built from the app's own formatter and styles; a real payment this large needs funds no test mint has)
        AMT_JS = """(()=>{const out=[],re=/\\d[\\d.,\\u00a0\\u202f\\u2009 ]*\\d(?:\\s?(?:SAT|USD|EUR|CHF))?/g;
          const root=document.querySelector('#layer .sheet-body')||document.querySelector('#app .screen')||document.querySelector('#app');
          const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
          while(n=w.nextNode()){const e=n.parentElement;if(!e||e.closest('.sr,script,style,.marquee'))continue;const s=n.nodeValue;let m;
            while(m=re.exec(s)){if(!/\\d{3}/.test(m[0]))continue;const r=document.createRange();r.setStart(n,m.index);r.setEnd(n,m.index+m[0].length);
              const tops=new Set([...r.getClientRects()].map(x=>Math.round(x.top)));
              const alone=e.closest('dd,.amt,.credit-num,.chip,button.btn,.pc-price,.cash-amt');
              const num=m[0].replace(/\s?(SAT|USD|EUR|CHF)$/,'');const rn=document.createRange();rn.setStart(n,m.index);rn.setEnd(n,m.index+num.length);
              const nt=new Set([...rn.getClientRects()].map(x=>Math.round(x.top)));
              if(nt.size>1||(alone&&tops.size>1))out.push('AMOUNT SPLIT: '+m[0]+' in <'+e.tagName+'.'+e.className+'>')}
            // a word cut in the middle although it would have fitted a line of its own
            const wr=/[^\\s\\u00a0-]{4,}/g;while(m=wr.exec(s)){const r=document.createRange();r.setStart(n,m.index);r.setEnd(n,m.index+m[0].length);
              const rs=[...r.getClientRects()];if(new Set(rs.map(x=>Math.round(x.top))).size>1){const tot=rs.reduce((a,x)=>a+x.width,0),box=(e.closest('dd,dt,button,.tx,.notice,p,div')||e).clientWidth;if(tot<=box-8)out.push('WORD CUT: '+m[0]+' in <'+e.tagName+'.'+e.className+'>')}}}
          return out.slice(0,6)})()"""
        BIG = [21000000, 12345678]
        async def amounts():
            for vw in (320, 375, 414):
                for lang in LANGS:
                    w = await wallet(b, f'amt-{vw}-{lang}', vw, 760, lang, on=True); await w.create()
                    bad = {}
                    await w.ev(f"""(()=>{{const S=Nutcade.S; S.mints=S.mints.length?S.mints:[]; const now=Date.now(); S.txs.unshift(
                      {{id:'bigA',ts:now,note:'Lunch #food',status:'done',fee:123457,type:'out',method:'ln',amount:{BIG[1]},mint:'https://mint.test'}},
                      {{id:'bigB',ts:now-1000,note:'',status:'done',fee:0,type:'in',method:'ln',amount:{BIG[0]},mint:'https://mint.test'}}); Nutcade.render()}})()""")
                    for root in (16, 20, 24):
                        await w.ev(f"document.documentElement.style.fontSize='{root}px'")
                        await tab(w, 'history'); r = await w.ev(AMT_JS)
                        if r: bad[f'root{root} notes'] = r
                        await tab(w, 'wallet'); r = await w.ev(AMT_JS)
                        if r: bad[f'root{root} wallet'] = r
                        await w.ev(f"""(()=>{{const f=Nutcade.fmt;Nutcade.openSheet('Pay','<dl class="kv"><dt>Pay</dt><dd>'+f({BIG[1]})+' SAT</dd><dt>Fee reserve</dt><dd>'+f(123457)+' SAT</dd><dt>Mint fee, at most</dt><dd>'+f(1234)+' SAT</dd><dt>Total, at most</dt><dd>'+f({BIG[0]})+' SAT</dd><dt>Note</dt><dd>Lunch</dd></dl><div class="notice">This mint holds '+f({BIG[0]})+' SAT, not enough on its own.</div><button class="btn solid pink block">Pay '+f({BIG[1]})+' SAT</button><button class="btn block">Cancel</button>')}})()""")
                        await w.until("!!document.querySelector('#layer .kv')", 3000); await frames(w)
                        r = await w.ev(AMT_JS)
                        if r: bad[f'root{root} pay sheet'] = r
                        o = await w.ev(OVER_JS)
                        if o: bad[f'root{root} overflow'] = o
                        c = await w.ev(CLIP_JS)   # (no button label clipped at an edge)
                        if c: bad[f'root{root} clipped'] = c
                        if vw == 320 and lang == 'de' and root == 24: await w.pg.screenshot(path=os.path.join(OUT, 'readable-pay-320-de-24-after.png'))
                        await w.ev("Nutcade.closeSheet()")
                    check(f'amounts {vw}px {lang}: at text size 16, 20 and 24 every amount (21,000,000 / 12,345,678 SAT, a fee) stays on one line in the notes list, the wallet and the Pay sheet, and no word is cut', not bad, bad)
                    await w.pg.context.close()
        await section('amounts', amounts)

        # ---------- the arcade is exactly as without the setting ----------
        STYLE_JS = """(sel=>{const P=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','whiteSpace','hyphens','overflowWrap','wordBreak','textTransform','width','height','paddingTop','paddingLeft','marginTop','display'];
          return [...document.querySelectorAll(sel)].map(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return (e.className&&e.className.baseVal===undefined?e.className:e.tagName)+'|'+P.map(p=>s[p]).join('|')+'|'+Math.round(r.width)+'x'+Math.round(r.height)})})"""
        async def arcade():
            for vw in (320, 375):
                got = {}
                for on_ in (False, True):
                    w = await wallet(b, f'arc-{on_}', vw, 700, 'en', on=on_); await w.create()
                    await tab(w, 'arcade'); await w.until("!!document.querySelector('.cab')", 5000); await frames(w)
                    snap = {'list': await w.ev(f"({STYLE_JS})('.cab, .cab *')")}
                    ids = await w.ev("Arcade.games.map(c=>c.id)")
                    for gid in ids[:6]:
                        await w.ev(f"document.querySelector('[data-game={gid}]').click()"); await w.until("!!document.querySelector('.game-view canvas')", 8000); await frames(w)
                        snap[gid] = await w.ev(f"({STYLE_JS})('.game-view, .game-view *')")
                        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.until("!document.querySelector('.game-view')", 5000)
                    got[on_] = snap; await w.pg.context.close()
                diff = {k: [(a, c) for a, c in zip(got[False][k], got[True][k]) if a != c][:2] for k in got[False] if got[False][k] != got[True][k]}
                check(f'arcade {vw}px: the cabinet list and 6 game screens have identical computed styles and sizes with Readable text on and off', not diff and len(got[True]) >= 7 and all(got[True][k] for k in got[True]), diff)
        await section('arcade', arcade)

        # ---------- no hyphenation, no breaking inside words anywhere in the wallet ----------
        async def nohyphen():
            w = await wallet(b, 'hy', 320, 700, 'de', on=True); await w.create()
            await w.ev("document.documentElement.style.fontSize='24px'")
            bad = {}
            for tname in TABS:
                if tname == 'arcade': continue
                await tab(w, tname)
                r = await w.ev("""[...document.querySelectorAll('#app *')].filter(e=>!e.closest('.game-view,.cab')&&getComputedStyle(e).hyphens!=='manual').slice(0,3).map(e=>e.tagName+'.'+e.className)""")
                a = await w.ev("""[...document.querySelectorAll('#app .btn,#app .chip,#app .seg button,#app .unitbtn,#app .linkbtn')].filter(e=>getComputedStyle(e).overflowWrap==='anywhere').slice(0,3).map(e=>e.className)""")
                if r: bad[tname + ' hyphens'] = r
                if a: bad[tname + ' anywhere'] = a
            check('hyphens: under Readable text no wallet element hyphenates and no button, chip or tab breaks anywhere', not bad, bad)
            await w.pg.context.close()
        await section('nohyphen', nohyphen)

        # ---------- before/after screenshots (one language, 375 px) ----------
        async def shots():
            w = await wallet(b, 'shots'); await w.create()
            for t in ('wallet', 'settings'):
                await tab(w, t); await w.pg.screenshot(path=os.path.join(OUT, f'readable-off-{t}-375.png'))
            await w.ev("Nutcade.S.prefs.readable=true; Nutcade.save&&Nutcade.save(); Nutcade.render()"); await frames(w)
            for t in ('wallet', 'settings'):
                await tab(w, t); await w.pg.screenshot(path=os.path.join(OUT, f'readable-on-{t}-375.png'))
            check('shots: before and after screenshots taken', True); await w.pg.context.close()
        await section('shots', shots)

        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
