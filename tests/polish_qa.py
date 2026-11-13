"""1.11 polish: layout on small and wide screens in every language (game controls, the PIN pad, sheets, toasts),
tap-target and text sizes, themes, units, dates, statuses, translated leftovers and the link-preview tags.
Uses the local mints and mock_nostr.py."""
import os, sys, asyncio, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, check, results, A, B, URL
from playwright.async_api import async_playwright

OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
SIZES = [(320, 640), (375, 667), (430, 932)]

async def wallet(b, vw=375, vh=667, lang='en', mobile=True, pin=False):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'polish')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w

# everything a finger can hit that is smaller than 40 px either way (a label wrapping a checkbox counts as the target)
SMALL_JS = """(()=>{const out=[];for(const e of document.querySelectorAll('#app *, #layer *, .cashier *, .game-view *')){
  if(!e.matches('button,a[href],select,input:not([type=hidden]),[data-act],summary,[role=button]'))continue;
  const s=getComputedStyle(e),r=e.getBoundingClientRect(); if(!r.width||!r.height||s.visibility==='hidden'||+s.opacity<0.05||e.closest('.sr,.tx,.dpad'))continue;
  const lab=e.closest('label'),rr=lab?lab.getBoundingClientRect():r; if(rr.width<40||rr.height<40)out.push((e.innerText||e.getAttribute('aria-label')||e.tagName).trim().slice(0,30)+' '+Math.round(rr.width)+'x'+Math.round(rr.height))}return out})()"""
# text in the pixel font under 9 px, or in the body font under 16 px (codes, addresses and tokens in a monospace box are exempt)
TINY_JS = """(()=>{const out=[];for(const e of document.querySelectorAll('#app *, #layer *, .cashier *, .game-view *')){
  if(![...e.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim()))continue; const s=getComputedStyle(e),r=e.getBoundingClientRect();
  if(!r.width||e.closest('.sr,.code,.mono,.qr,canvas,svg,.kv dd.tiny,.words'))continue; const f=parseFloat(s.fontSize);
  if(/Press Start/.test(s.fontFamily)?f<9:/VT323/.test(s.fontFamily)&&f<16)out.push(e.innerText.trim().slice(0,30)+' '+f)}return out})()"""
# anything poking out of the viewport sideways
OVER_JS = """(()=>{const W=document.documentElement.clientWidth,out=[];for(const e of document.querySelectorAll('#app *, #layer *, .cashier *, .game-view *')){
  if(!e.getClientRects().length||e.closest('.sr'))continue;const r=e.getBoundingClientRect();if(r.right>W+1||r.left<-1)out.push((e.className||e.tagName)+':'+Math.round(r.left)+'..'+Math.round(r.right))}return out.slice(0,4)})()"""
INVIEW = """(sel=>{const e=document.querySelector(sel); if(!e) return 'missing'; const r=e.getBoundingClientRect(); return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight ? 'ok' : [Math.round(r.left),Math.round(r.top),Math.round(r.right),Math.round(r.bottom)].join(',')})"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ---------- one funded wallet for the screens ----------
        w = await wallet(b)
        await w.create(); await w.add_mint(B); await w.add_mint(A); await w.use(B)
        await w.receive_ln(50000, 'Paycheck #work')
        tok, e = await w.send_ecash(700, 'Lunch #food')

        # the header: the full marquee only greets new players; after setup it's one row
        await w.home()
        h = await w.ev("document.querySelector('.marquee').getBoundingClientRect().height")
        check('header: a compact one-row marquee after setup', await w.ev("document.querySelector('.marquee').classList.contains('mini')") and h < 90, h)
        check('header: Receive, Send and Scan are above the fold at 375x667', all([await w.ev(f"({INVIEW})('{s}')") == 'ok' for s in ('[data-act=receive]', '[data-act=send]', '[data-act=scan]')]))

        # minus signs that read in the pixel font
        await w.click('[data-act=tab][data-tab=history]'); await w.wait(200)
        amts = await w.ev("[...document.querySelectorAll('.tx.out .amt')].map(e=>e.innerText)")
        check('history: sent amounts start with a mid-height dash, not a minus that falls to the baseline', amts and all(a.startswith('-') for a in amts), amts)
        check('history: the screen is called Notes, like its tab', await w.ev("document.querySelector('.screen .h2').innerText.trim()") == 'Notes')

        # search and filters don't stick around after leaving the tab
        await w.fill('#hq', 'lunch'); await w.wait(200); await w.click('[data-act=hf][data-f=out]'); await w.wait(150)
        await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(150); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        check('history: search and filter are cleared after leaving the tab', await w.ev("document.querySelector('#hq').value===''&&document.querySelector('[data-act=hf][data-f=all]').getAttribute('aria-pressed')==='true'"))

        # transaction status and dates
        await w.click('[data-act=tx]'); await w.wait(200)
        kv = await w.ev("document.querySelector('.sheet .kv').innerText")
        check('transaction: status reads as a proper word, not raw lowercase', re.search(r'\n(Pending|Complete)\b', kv) is not None, kv)
        check('transaction: the date reads like "Nov 13, 2026, 8:01 PM"', re.search(r'[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d\d', kv) is not None, kv)
        await w.ev("Nutcade.closeSheet()")

        # amount fields name the unit you're typing in
        await w.ev("""Nutcade.S.prefs.fiat=true""")
        await w.pg.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '100000'}}})))
        await w.home(); await w.wait(600); await w.click('[data-act=receive]'); await w.wait(200)
        lab0 = await w.ev("document.querySelector('label[for=amtIn]').innerText")
        await w.click('[data-act=amtUnit]'); await w.wait(150)
        lab1 = await w.ev("document.querySelector('label[for=amtIn]').innerText"); unit1 = await w.ev("document.querySelector('.unitbtn').innerText")
        check('amounts: the label follows the unit switch (SAT, then USD)', 'SAT' in lab0 and 'USD' in lab1 and unit1 == 'USD', (lab0, lab1, unit1))
        await w.click('[data-act=amtUnit]'); await w.wait(100); await w.ev("Nutcade.closeSheet(); Nutcade.S.prefs.amtFiat=false")

        # toasts: above the tab bar, never under the sheet title, taps go through
        await w.click('[data-act=receive]'); await w.wait(150); await w.ev("Nutcade.toast('Copied','cyan')"); await w.wait(150)
        t = await w.ev("""(()=>{const t=document.querySelector('#toast').getBoundingClientRect(),h=document.querySelector('.sheet-head').getBoundingClientRect();return {over:!(t.bottom<=h.top||t.top>=h.bottom), pe:getComputedStyle(document.querySelector('#toast')).pointerEvents}})()""")
        check('toasts: with a sheet open they sit above it, not on its title', not t['over'], t)
        check('toasts: taps go through them', t['pe'] == 'none', t)
        await w.ev("Nutcade.closeSheet()"); await w.wait(100)
        t = await w.ev("""(()=>{const t=document.querySelector('#toast').getBoundingClientRect(),b=document.querySelector('.tabbar').getBoundingClientRect(),m=document.querySelector('.marquee').getBoundingClientRect();return {bar:t.bottom<=b.top+1, top:t.top>m.bottom}})()""")
        check('toasts: on a tab they sit just above the tab bar', t['bar'] and t['top'], t)

        # cashier: no 1UP pile-up or wallet toasts on the PAID screen; the unit button shows the current unit
        await w.home(); await w.click('[data-act=cashier]'); await w.wait(300)
        check('cashier: the unit button shows the unit in use', await w.ev("document.querySelector('[data-ck=unit]').innerText.trim()") == 'SAT')
        await w.ev("Nutcade.toast('+5 SAT received','lime'); Nutcade.celebrate('in', 5)"); await w.wait(150)
        check('cashier: no wallet toasts or coin effects over the till', await w.ev("document.querySelector('#toast').hidden && !document.querySelector('#fxLayer')"))
        await w.ev("document.querySelector('.cashier').remove(); document.body.style.overflow=''; Nutcade.refresh()"); await w.wait(150)

        # tap targets and text sizes on the main screens and common sheets
        small, tiny = [], []
        for name, js in [('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"),
                         ('mints', "document.querySelector('[data-act=tab][data-tab=mints]').click()"),
                         ('history', "document.querySelector('[data-act=tab][data-tab=history]').click()"),
                         ('settings', "document.querySelector('[data-act=tab][data-tab=settings]').click()"),
                         ('arcade', "document.querySelector('[data-act=tab][data-tab=arcade]').click()"),
                         ('contacts', "document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=contactsOpen]').click()"),
                         ('send', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=send]').click()"),
                         ('scan', "Nutcade.closeSheet(); document.querySelector('[data-act=scan]').click()"),
                         ('restore', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=restore]').click()"),
                         ('report', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=mints]').click(); document.querySelector('[data-act=reportOpen]').click()")]:
            await w.ev(js); await w.wait(350)
            small += [name + ': ' + x for x in await w.ev(SMALL_JS)]; tiny += [name + ': ' + x for x in await w.ev(TINY_JS)]
        check('tap targets: every button, link and chip is at least 40 px', not small, small[:8])
        check('text: pixel font at least 9 px, body font at least 16 px', not tiny, tiny[:8])
        await w.ev("Nutcade.closeSheet()")

        # restore: the mint list uses the body font; the backup file picker is a styled, translated button
        await w.ev("document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=seedRestore]').click()"); await w.wait(300)
        check('restore: mints to scan are in the body font', 'VT323' in await w.ev("getComputedStyle(document.querySelector('#rmList .toggle')).fontFamily"))
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=restore]').click()"); await w.wait(200)
        check('import backup: a styled button, no raw file control', await w.ev("getComputedStyle(document.querySelector('#restoreFile')).opacity==='0' && /Choose a file/i.test(document.querySelector('.filepick').innerText)"))
        await w.ev("Nutcade.closeSheet()")

        # a mint met today is NEW, not F
        await w.ev("document.querySelector('[data-act=tab][data-tab=mints]').click()"); await w.wait(150)
        await w.ev("document.querySelector('[data-act=reportOpen]').click()"); await w.wait(400)
        age = await w.ev("[...document.querySelectorAll('.rrow')].find(r=>/Age/.test(r.innerText)).querySelector('.rg').innerText")
        check('report card: a mint met today shows NEW for its age, not a failing grade', age == 'NEW', age)
        await w.ev("Nutcade.closeSheet()")

        # themes: inputs, the marquee and the two big buttons follow the theme
        cols = {}
        for th in ['neon', 'amber', 'phosphor']:
            await w.ev(f"Nutcade.S.prefs.theme='{th}'; Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"); await w.wait(150)
            await w.ev("document.querySelector('[data-act=send]').click()"); await w.wait(150)
            cols[th] = await w.ev("""({inp:getComputedStyle(document.querySelector('#amtIn')).backgroundColor, mq:getComputedStyle(document.querySelector('.marquee')).backgroundImage,
                recv:getComputedStyle(document.querySelector('.push.recv .cap')).backgroundColor, send:getComputedStyle(document.querySelector('.push.send .cap')).backgroundColor})""")
        check('themes: input backgrounds follow Amber and Green', len({cols[t]['inp'] for t in cols}) == 3, {t: cols[t]['inp'] for t in cols})
        check('themes: the marquee follows Amber and Green', len({cols[t]['mq'] for t in cols}) == 3)
        check('themes: Send looks different from Receive in every theme', all(cols[t]['recv'] != cols[t]['send'] for t in cols), cols)
        await w.ev("Nutcade.S.prefs.theme='neon'; Nutcade.closeSheet(); Nutcade.render()")

        # English leftovers: lock screen, toasts, placeholders, game hints and notes NUTCADE writes, in every language
        miss = {}
        for lang in LANGS[1:]:
            await w.ev(f"Nutcade.closeSheet(); Nutcade.S.prefs.lang='{lang}'; document.querySelector('[data-act=tab][data-tab=settings]').click(); const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await w.wait(200)
            got = await w.ev("""['Your wallet is locked.','Wrong PIN. 4 tries before a wait.','CHECKING…','Found 321 SAT','lnbc… or name@domain.com','✚ or swipe to steer',
                'Arrow keys steer','PRESS A OR TAP','PRESS SPACE TO START','Recovered with recovery phrase','Extra Life for Bo','Choose a file','No file chosen','Pending','Complete',
                'Send or move the 49,700 SAT out of this mint before removing it.','Amount (SAT)','Amount (USD)','Not enough funds. This mint holds 49,700 SAT.','The mint turned this down.'].filter(s=>Nutcade.tr(s)===s)""")
            miss[lang] = got
        check('translations: the 1.11 leftovers are translated in es, pt, de and fr', not any(miss.values()), miss)
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); const s=document.querySelector('#p_lang'); s.value='de'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await w.wait(300)
        check('German: the tab and the screen both say Optionen', await w.ev("document.querySelector('[data-tab=settings]').innerText.trim()==='OPTIONEN' && /Optionen/.test(document.querySelector('.screen').innerText)"))
        await w.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await w.wait(200)

        # link previews: one description, the right number of games
        html = await w.ev("document.documentElement.outerHTML")
        descs = re.findall(r'<meta (?:name|property)="(?:description|og:description|twitter:description)" content="([^"]*)"', html)
        check('share text: one meta description and 8 games everywhere', html.count('name="description"') == 1 and all('8 retro games' in d for d in descs) and '7 retro' not in html, descs)
        check('no page errors', not w.errs, w.errs[:3])
        await w.pg.context.close()

        # ---------- nothing widens a 320 px page, in any language (a long German button once did) ----------
        for lang in LANGS:
            n = await wallet(b, 320, 640, lang)
            await n.create(); await n.add_mint(B); await n.receive_ln(3000, 'Coffee #food')
            wide = {}
            for name, js in [('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"),
                             ('arcade', "document.querySelector('[data-act=tab][data-tab=arcade]').click()"),
                             ('history', "document.querySelector('[data-act=tab][data-tab=history]').click()"),
                             ('mints', "document.querySelector('[data-act=tab][data-tab=mints]').click()"),
                             ('settings', "document.querySelector('[data-act=tab][data-tab=settings]').click()"),
                             ('contacts', "document.querySelector('[data-act=contactsOpen]').click()"),
                             ('restore', "Nutcade.closeSheet(); document.querySelector('[data-act=seedRestore]').click()"),
                             ('import', "Nutcade.closeSheet(); document.querySelector('[data-act=restore]').click()"),
                             ('lnaddr', "Nutcade.closeSheet(); document.querySelector('[data-act=lnAddr]').click()"),
                             ('support', "Nutcade.closeSheet(); document.querySelector('[data-act=support]').click()"),
                             ('pickmint', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=pickMint]').click()"),
                             ('receive', "Nutcade.closeSheet(); document.querySelector('[data-act=receive]').click()"),
                             ('request', "document.querySelector('[data-act=recvMethod][data-m=ecash]').click(); document.querySelector('[data-act=reqOpen]').click()"),
                             ('send-ln', "Nutcade.closeSheet(); document.querySelector('[data-act=send]').click(); document.querySelector('[data-act=sendMethod][data-m=ln]').click()"),
                             ('reqpay', "Nutcade.closeSheet(); document.querySelector('[data-act=send]').click(); document.querySelector('[data-act=reqPayOpen]').click()"),
                             ('scan', "Nutcade.closeSheet(); document.querySelector('[data-act=scan]').click()"),
                             ('cashier', "Nutcade.closeSheet(); document.querySelector('[data-act=cashier]').click()")]:
                try: await n.ev(js); await n.wait(300)
                except Exception as e: wide[name] = 'could not open: ' + str(e)[:80]; continue
                o = await n.ev(OVER_JS); iw = await n.ev("innerWidth")
                if o or iw != 320: wide[name] = (iw, o)
            await n.ev("document.querySelector('.cashier') && document.querySelector('.cashier').remove(); document.body.style.overflow=''")
            check(f'layout 320 px {lang}: no screen or sheet is wider than the phone', not wide, wide)
            await n.pg.context.close()

        # ---------- game controls, the PIN pad and the tab bar at every phone size and language ----------
        for vw, vh in SIZES:
            for lang in LANGS:
                g = await wallet(b, vw, vh, lang)
                await g.create()
                bad = {}
                for pad in ['stick', 'dpad']:
                    await g.ev(f"localStorage.setItem('nutcade:pad',JSON.stringify('{pad}')); document.querySelector('[data-act=tab][data-tab=arcade]').click()"); await g.wait(150)
                    for gid in ['swarm', 'flipper']:
                        await g.ev(f"document.querySelector('[data-game={gid}]').click()"); await g.wait(250)
                        for sel in ['.abtn.a', '.abtn.b', '.stick, .dpad', '[data-g=pad]', '[data-g=exit]']:
                            r = await g.ev(f"({INVIEW})('{sel}')")
                            if r != 'ok': bad[f'{pad}/{gid} {sel}'] = r
                        o = await g.ev(OVER_JS)
                        if o: bad[f'{pad}/{gid} overflow'] = o
                        await g.ev("document.querySelector('[data-g=exit]').click()"); await g.wait(150)
                check(f'arcade {vw}x{vh} {lang}: fire, pause and the stick or D-pad are all on screen', not bad, bad)
                tabs = await g.ev("[...document.querySelectorAll('.tab')].map(t=>{const s=t.querySelector('span');return s.scrollWidth<=t.clientWidth+1 && parseFloat(getComputedStyle(s).fontSize)>=9})")
                check(f'tab bar {vw}x{vh} {lang}: labels fit at 9 px or more', all(tabs), tabs)
                await g.pg.context.close()
        for vw, vh in [(320, 640), (375, 667)]:
            for lang in LANGS:
                k = await wallet(b, vw, vh, lang)
                await k.create()
                await k.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=pinSet]').click()"); await k.wait(200)
                for rnd in (1, 2):
                    for d in '135790': await k.click(f'[data-pinpad] [data-k="{d}"]')
                    await k.click('[data-pinpad] [data-k=ok]'); await k.wait(200)
                await k.until("document.body.innerText.includes('LOCKED DOWN')", 20000)
                await k.pg.reload(); await k.wait(700)
                where = {s: await k.ev(f"({INVIEW})('{s}')") for s in ['[data-k=del]', '[data-k="0"]', '[data-k=ok]', '[data-act=forgotPin]']}
                check(f'lock {vw}x{vh} {lang}: the whole keypad and Forgot PIN fit without scrolling', all(v == 'ok' for v in where.values()), where)
                sub = await k.ev("document.querySelector('.pinpad .th').innerText")
                check(f'lock {vw}x{vh} {lang}: the lock screen is translated', lang == 'en' or sub != 'Your wallet is locked.', sub)
                if vw == 320 and lang == 'en':
                    dots = await k.ev("document.querySelectorAll('.pin-dots i').length")
                    check('lock: no fixed row of six boxes before you type', dots == 1, dots)
                    await k.pg.screenshot(path=OUT + 'polish_lock_320.png')
                await k.pg.context.close()

        # ---------- desktop: sheets are centered dialogs, the tool row is an even grid, keyboard wording ----------
        d = await wallet(b, 1440, 900, 'en', mobile=False)
        await d.create(); await d.add_mint(B); await d.receive_ln(2000)
        await d.home(); await d.click('[data-act=receive]'); await d.wait(200)
        r = await d.ev("(()=>{const r=document.querySelector('.sheet').getBoundingClientRect();return {top:r.top,gap:innerHeight-r.bottom}})()")
        check('desktop: sheets open as centered dialogs', r['top'] > 20 and abs(r['top'] - r['gap']) < 40, r)
        await d.ev("Nutcade.closeSheet()")
        rows = await d.ev("[...new Set([...document.querySelectorAll('.toolrow .btn')].map(b=>Math.round(b.getBoundingClientRect().top)))].length")
        widths = await d.ev("[...new Set([...document.querySelectorAll('.toolrow .btn')].map(b=>Math.round(b.getBoundingClientRect().width)))]")
        check('desktop: the wallet tools are an even 2 x 2 grid', rows == 2 and len(widths) == 1, (rows, widths))
        await d.click('[data-act=tab][data-tab=arcade]'); await d.wait(200)
        await d.ev("document.querySelector('[data-game=swarm]').click()"); await d.wait(300)
        check('desktop: games explain the keys, not the touch buttons', await d.ev("getComputedStyle(document.querySelector('.pad-keys')).display!=='none' && getComputedStyle(document.querySelector('.pad')).display==='none'"))
        await d.pg.screenshot(path=OUT + 'polish_desktop_game.png')
        await d.pg.context.close()
        await b.close()
    n = len(results); ok = sum(1 for r in results if r[1])
    print(f'SUMMARY {ok}/{n} passed')

asyncio.run(main())
