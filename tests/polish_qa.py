"""1.11 polish: layout on small and wide screens in every language (game controls, the PIN pad, sheets, toasts),
tap-target and text sizes, themes, units, dates, statuses, translated leftovers and the link-preview tags.
Uses the local mints and mock_nostr.py."""
import os, sys, asyncio, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, check, results, A, B, URL
from playwright.async_api import async_playwright
from r7_qa import forward, mock as r7mock, nwc as r7nwc, make_nwc as r7make_nwc

OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
SIZES = [(320, 640), (375, 667), (430, 932)]

async def wallet(b, vw=375, vh=667, lang='en', mobile=True, pin=False):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    await ctx.route('https://lnurl.test/**', forward)   # LNURL vouchers and zap endpoints (mock_nostr.py)
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
                'Send or move the 49,700 SAT out of this mint before removing it.','Amount (SAT)','Amount (USD)','Not enough funds. This mint holds 49,700 SAT.','The mint turned this down.',
                'Type the same PIN again.','WALLET LOCKED DOWN!','Enter it again.','PAUSED','A OR TAP TO RESUME','ENTER TO RESUME','Your hunt','Treasure hunt','the treasure hunters',
                'Ecash token QR','Lightning invoice QR, animated','6 digits entered','Joystick','Pause','Clue card 2','STAR SWARM game screen','Fee reserve 7 SAT','Holds 49,700 SAT',
                '₿67 in your piggy bank · ₿49,288 to spend','Rounds up to the nearest ₿100. Next goal: ₿1,000'].filter(s=>Nutcade.tr(s)===s && !(s==='Joystick'||(s==='Pause'&&/de|fr/.test(document.documentElement.lang))))""")
            if lang == 'de': miss['de-numbers'] = [] if await w.ev("Nutcade.fmt(30000)==='30.000' && Nutcade.fmt(1500)==='1.500'") else [await w.ev("Nutcade.fmt(30000)")]
            if lang == 'fr': miss['fr-numbers'] = [] if await w.ev("Nutcade.fmt(30000)==='30\u202f000'") else [await w.ev("Nutcade.fmt(30000)")]
            miss[lang] = got
        check('translations: the 1.11 leftovers are translated in es, pt, de and fr', not any(miss.values()), miss)
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); const s=document.querySelector('#p_lang'); s.value='de'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await w.wait(300)
        await w.ev("document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=send]').click(); document.querySelector('[data-act=sendMethod][data-m=ln]').click()"); await w.wait(250)
        ph = await w.ev("document.querySelector('#destIn').placeholder")
        check('German: textarea placeholders are translated too', ph != 'lnbc… or name@domain.com', ph)
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
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
                top0 = await k.ev("Math.round(document.querySelector('.pin-keys').getBoundingClientRect().top)")
                for d in '111111': await k.click(f'[data-pinpad] [data-k="{d}"]')
                await k.click('[data-pinpad] [data-k=ok]'); await k.until("document.querySelector('#pinErr').innerText.length>0 && !document.querySelector('#pinErr').classList.contains('busy')", 20000); await k.wait(300)
                top1 = await k.ev("Math.round(document.querySelector('.pin-keys').getBoundingClientRect().top)")
                check(f'lock {vw}x{vh} {lang}: a wrong-PIN message does not move the keypad', top0 == top1, (top0, top1, await k.ev("document.querySelector('#pinErr').innerText")))
                if vw == 320 and lang == 'en':
                    d0 = await k.ev("[...document.querySelectorAll('.pin-dots i')].map(i=>i.className)")
                    check('lock: six faint boxes before you type, the first one the cursor', len(d0) == 6 and d0[0] == 'cur', d0)
                    ops = []
                    for _ in range(6): ops.append(float(await k.ev("getComputedStyle(document.querySelector('.pin-dots i.cur')).opacity"))); await k.wait(180)
                    check('lock: the cursor box never goes below 40% opacity', min(ops) >= 0.39, ops)
                    for d in '123456789012': await k.click(f'[data-pinpad] [data-k="{d}"]')
                    fit = await k.ev("(()=>{const b=[...document.querySelectorAll('.pin-dots i')];const p=document.querySelector('.panel').getBoundingClientRect();return {n:b.length,on:b.filter(i=>i.classList.contains('on')).length,inside:b.every(i=>{const r=i.getBoundingClientRect();return r.left>=p.left&&r.right<=p.right})}})()")
                    check('lock: twelve digits show twelve boxes and fit a 320 px phone', fit['n'] == 12 and fit['on'] == 12 and fit['inside'], fit)
                    await k.pg.emulate_media(reduced_motion='reduce'); await k.click('[data-pinpad] [data-k=del]'); await k.wait(100)
                    check('lock: no blinking with reduced motion', await k.ev("getComputedStyle(document.querySelector('.pin-dots i.cur')).animationName") == 'none')
                    await k.pg.screenshot(path=OUT + 'polish_lock_320.png')
                # Face ID on (the flag is faked: headless Chrome has no passkeys): button and Forgot PIN still fit
                await k.ev("(()=>{const v=JSON.parse(localStorage.getItem('nutcade:vault'));v.bio={id:'x'};localStorage.setItem('nutcade:vault',JSON.stringify(v))})()")
                await k.pg.reload(); await k.wait(700)
                where = {s: await k.ev(f"({INVIEW})('{s}')") for s in ['[data-k=ok]', '[data-act=bioUnlock]', '[data-act=forgotPin]']}
                check(f'lock {vw}x{vh} {lang}: with Face ID on, the button and Forgot PIN fit', all(v == 'ok' for v in where.values()), where)
                await k.pg.context.close()

        # ---------- round 2: the cashier with big amounts, long unbroken text, the token sheet, toasts ----------
        for vw, vh in [(320, 640), (375, 667)]:
            c = await wallet(b, vw, vh, 'en')
            await c.pg.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '100000'}}})))
            await c.create(); await c.add_mint(B); await c.receive_ln(3000); await c.home(); await c.wait(800)
            await c.click('[data-act=cashier]'); await c.wait(300)
            CASH = "(()=>{const W=innerWidth,H=innerHeight,bad=[];for(const e of document.querySelectorAll('.cashier *')){const r=e.getBoundingClientRect();if(r.width&&(r.right>W+1||r.left<-1))bad.push(e.className+':'+Math.round(r.right))}const ch=document.querySelector('.cash-charge');if(ch&&ch.scrollWidth>ch.clientWidth+1)bad.push('CHARGE label cut off');for(const s of ['[data-ck=\"3\"]','[data-ck=del]','[data-ck=clear]','[data-ck=m-ecash]','[data-ck=unit]','.cash-charge','[data-ck=close]']){const e=document.querySelector(s);const r=e&&e.getBoundingClientRect();if(!r||r.right>W||r.bottom>H)bad.push('hidden '+s)}return bad.slice(0,5)})()"
            b0 = await c.ev(CASH)
            for k in '12345678': await c.click(f'[data-ck="{k}"]')
            b8 = await c.ev(CASH); await c.click('[data-ck="9"]'); b9 = await c.ev(CASH)
            check(f'cashier {vw}x{vh}: empty, 8 and 9 digits all fit, every key, CHARGE and Close the till visible', not b0 and not b8 and not b9, (b0, b8, b9))
            await c.click('[data-ck=clear]'); await c.click('[data-ck=unit]'); await c.wait(150)
            for k in '9999999.99': await c.click(f'[data-ck="{k}"]')
            bf = await c.ev(CASH)
            check(f'cashier {vw}x{vh}: a big amount in your currency fits too', not bf and await c.ev("document.querySelector('[data-ck=unit]').innerText.trim()") == 'USD', bf)
            await c.pg.screenshot(path=OUT + f'polish_cashier_{vw}.png')
            await c.ev("document.querySelector('.cashier').remove(); document.body.style.overflow=''; Nutcade.refresh()"); await c.wait(150)
            # the token sheet's main button is visible without scrolling
            await c.click('[data-act=send]'); await c.wait(150); await c.fill('#amtIn', '300'); await c.click('[data-act=doSendEcash]'); await c.until("!!document.querySelector('#layer .qr')", 8000); await c.wait(400)
            r = await c.ev(f"({INVIEW})('#layer .sheet-body [data-act=copy]')")
            check(f'token sheet {vw}x{vh}: COPY TOKEN visible without scrolling', r == 'ok', r)
            # a three-line toast stays in the strip above the sheet
            await c.ev("Nutcade.toast('Send or move the 1,234,567 SAT out of this mint before removing it, or you will lose them for good.','red')"); await c.wait(150)
            t = await c.ev("(()=>{const t=document.querySelector('#toast').getBoundingClientRect(),s=document.querySelector('#layer .sheet').getBoundingClientRect();return {t:Math.round(t.bottom),s:Math.round(s.top)}})()")
            check(f'toasts {vw}x{vh}: a three-line toast stays above the sheet and its X', t['t'] <= t['s'], t)
            await c.ev("Nutcade.closeSheet()")
            # in a game every toast waits
            await c.click('[data-act=tab][data-tab=arcade]'); await c.wait(150); await c.ev("document.querySelector('[data-game=swarm]').click()"); await c.wait(300)
            await c.ev("Nutcade.toast('Something failed','red')"); await c.wait(200)
            held = await c.ev("!document.querySelector('#toast') || document.querySelector('#toast').hidden")
            await c.ev("document.querySelector('[data-g=exit]').click()"); await c.wait(1500)
            check(f'toasts {vw}x{vh}: nothing covers the game controls; the toast shows after leaving', held and await c.ev("!document.querySelector('#toast').hidden"))
            await c.pg.context.close()
        L60 = 'W' * 20 + 'Supercalifragilistic' + 'X' * 20
        for lang in LANGS:
            n = await wallet(b, 320, 640, lang)
            await n.create(); await n.add_mint(B); await n.receive_ln(3000)
            await n.ev(f"""(()=>{{const S=Nutcade.S;S.mints[0].name={json.dumps(L60)};
              S.mints.push({{url:'https://'+{json.dumps(L60.lower())}+'.example.com/'+{json.dumps(L60)},name:{json.dumps(L60)},methods:{{}},keysets:[]}});
              S.contacts.push({{id:'cL',name:{json.dumps(L60)},ln:{json.dumps(L60.lower()+'@'+L60.lower()+'.com')},nostr:''}});
              S.requests.unshift({{id:'rL',encoded:'creqA',amount:100,memo:{json.dumps(L60)},created:Date.now(),paid:[]}});
              S.txs.forEach(t=>{{t.note={json.dumps(L60 + ' #' + L60[:20])};t.contactName={json.dumps(L60)}}}); Nutcade.render()}})()"""); await n.wait(200)
            wide = {}
            for name, js in [('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"), ('history', "document.querySelector('[data-act=tab][data-tab=history]').click()"),
                             ('tx', "document.querySelector('[data-act=tx]').click()"), ('mints', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=mints]').click()"),
                             ('report', "document.querySelector('[data-act=reportOpen]').click()"), ('contacts', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=contactsOpen]').click()"),
                             ('pay-contact', "document.querySelector('[data-act=payContact]').click()"), ('pickmint', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=pickMint]').click()"),
                             ('send', "Nutcade.closeSheet(); document.querySelector('[data-act=send]').click()"), ('receive', "Nutcade.closeSheet(); document.querySelector('[data-act=receive]').click()"),
                             ('requests', "document.querySelector('[data-act=recvMethod][data-m=ecash]').click(); document.querySelector('[data-act=reqOpen]').click()"),
                             ('lnaddr', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=lnAddr]').click()"),
                             ('cashier', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=cashier]').click()")]:
                try: await n.ev(js); await n.wait(300)
                except Exception as e: wide[name] = 'could not open: ' + str(e)[:60]; continue
                o = await n.ev(OVER_JS); iw = await n.ev("innerWidth")
                if o or iw != 320: wide[name] = (iw, o)
            check(f'long text 320 px {lang}: a 60-character unbroken name, address, note or memo never widens a screen', not wide, wide)
            await n.pg.context.close()

        # small leftovers in German at 320: a huge amount, the mint status line, the offline banner
        g = await wallet(b, 320, 640, 'de')
        await g.create(); await g.add_mint(B); await g.receive_ln(3000)
        await g.ev("(()=>{const S=Nutcade.S;const t=JSON.parse(JSON.stringify(S.txs[0]));t.id='big';t.amount=100000000000;S.txs.unshift(t);Nutcade.render()})()")
        await g.click('[data-act=tab][data-tab=history]'); await g.wait(200)
        ov = await g.ev("(()=>{const r=document.querySelector('.tx');const a=r.querySelector('.amt').getBoundingClientRect(),m=r.querySelector('.meta').getBoundingClientRect();return !(a.left<m.right&&m.left<a.right&&a.top<m.bottom&&m.top<a.bottom)})()")
        check('history: a 1,000 BTC amount does not cover the row\'s chips', ov)
        await g.click('[data-act=tab][data-tab=mints]'); await g.wait(2500)
        h = await g.ev("(()=>{const e=document.querySelector('.health span.nowrap');return e?Math.round(e.getBoundingClientRect().height):0})()")
        check('mints: the status (ONLINE · 9 MS) stays on one line in German', 0 < h < 20, h)
        await g.pg.context.set_offline(True); await g.click('[data-act=tab][data-tab=wallet]'); await g.wait(600)
        nb = await g.ev("(()=>{const b=document.querySelector('#netBanner').getBoundingClientRect(),m=document.querySelector('.marquee').getBoundingClientRect();return {b:Math.round(b.bottom),m:Math.round(m.top)}})()")
        check('offline: the banner sits above the header, not on it', nb['b'] <= nb['m'], nb)
        await g.pg.context.set_offline(False); await g.pg.context.close()

        # ---------- round 3 ----------
        # no pixel-font label, button, tab or short status splits inside a word, in any language
        SPLIT = """(()=>{const out=[];for(const e of document.querySelectorAll('#app *,#layer *,.cashier *')){const r=e.getBoundingClientRect();if(!r.width||e.closest('.code,.mono,.qr,canvas,svg,textarea,[data-noi18n],.uname,.note,.tag,.meta,.kv dd,.notice'))continue;
          const s=getComputedStyle(e);const ps=/Press/.test(s.fontFamily);if(!ps&&!e.closest('button,.btn,label,.label,.tab,.health'))continue;
          for(const n of e.childNodes){if(n.nodeType!==3||!n.nodeValue.trim())continue;const re=/[^\\s\\-\\/@.·:]+/g;let m;while((m=re.exec(n.nodeValue))){if(m[0].length<3)continue;const rg=document.createRange();rg.setStart(n,m.index);rg.setEnd(n,m.index+m[0].length);
            if(new Set([...rg.getClientRects()].filter(q=>q.width>0).map(q=>Math.round(q.top))).size>1)out.push(m[0])}}}return [...new Set(out)].slice(0,8)})()"""
        for vw, vh in [(320, 640), (375, 667)]:
            for lang in LANGS:
                z = await wallet(b, vw, vh, lang)
                await z.create(); await z.add_mint(B); await z.receive_ln(2000)
                found = {}
                for name, js in [('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"), ('arcade', "document.querySelector('[data-act=tab][data-tab=arcade]').click()"),
                                 ('history', "document.querySelector('[data-act=tab][data-tab=history]').click()"), ('mints', "document.querySelector('[data-act=tab][data-tab=mints]').click()"),
                                 ('settings', "document.querySelector('[data-act=tab][data-tab=settings]').click()"), ('receive', "document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=receive]').click()"),
                                 ('send', "Nutcade.closeSheet(); document.querySelector('[data-act=send]').click()"), ('cashier', "Nutcade.closeSheet(); document.querySelector('[data-act=cashier]').click()")]:
                    await z.ev(js); await z.wait(1500 if name == 'mints' else 300)
                    sp = await z.ev(SPLIT)
                    if sp: found[name] = sp
                check(f'words {vw}x{vh} {lang}: no label, button or status splits inside a word', not found, found)
                await z.pg.context.close()

        # typed amounts in your currency are read the way your language writes them (never 1000x off)
        CASES = {'en': [('1,234.56', 1234.56), ('1234.56', 1234.56), ('1.000', 1.0), ('0,5', 0.5), ('1,000', 1000)],
                 'xx': [('1.234,56', 1234.56), ('1 234,56', 1234.56), ('1234,56', 1234.56), ('1234.56', 1234.56), ('1.000', 1000), ('0,5', 0.5), ('1,234.56', 1234.56), ('1\u202f234,56', 1234.56)]}
        for lang in LANGS:
            f = await wallet(b, 375, 667, lang)
            await f.pg.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '100000'}}})))
            await f.create(); await f.add_mint(B); await f.receive_ln(25000, 'Rent #home'); await f.home(); await f.wait(900)
            await f.click('[data-act=receive]'); await f.wait(150)
            await f.fill('#amtIn', '2500'); await f.click('[data-act=amtUnit]'); await f.wait(100); await f.click('[data-act=amtUnit]'); await f.wait(100)
            rt = await f.ev("document.querySelector('#amtIn').value")
            await f.click('[data-act=amtUnit]'); await f.wait(100)
            bad = [] if rt == '2500' else [('SAT -> USD -> SAT', rt)]
            for typed, exp in CASES['en' if lang == 'en' else 'xx']:
                await f.fill('#amtIn', typed); await f.wait(60)
                hint = await f.ev("document.querySelector('.amtconv').innerText")
                if int(re.sub(r'[^0-9]', '', hint) or 0) != round(exp / 100000 * 1e8): bad.append((typed, hint))
            check(f'fiat {lang}: typed amounts are read in the language\'s format, and the ≈ SAT hint matches', not bad, bad)
            await f.ev("Nutcade.closeSheet(); Nutcade.S.prefs.amtFiat=false")
            # the till: whole part grouped, the language's decimal mark, and the SAT value right
            await f.click('[data-act=cashier]'); await f.wait(200); await f.click('[data-ck=unit]'); await f.wait(100)
            for k in '123456.78': await f.click(f'[data-ck="{k}"]')
            disp = await f.ev("[document.querySelector('.cash-amt').innerText, document.querySelector('[data-ck=\".\"]').innerText, document.querySelector('.cash-conv').innerText]")
            want = {'en': '123,456.78', 'de': '123.456,78', 'es': '123.456,78', 'pt': '123.456,78', 'fr': '123\u202f456,78'}[lang]
            check(f'cashier {lang}: the amount in your currency is grouped with the language\'s decimal mark', disp[0].startswith(want) and disp[1] == want[-3] and re.sub(r'[^0-9]', '', disp[2]) == '123456780', disp)
            await f.ev("document.querySelector('.cashier').remove(); document.body.style.overflow=''; Nutcade.refresh()"); await f.wait(150)
            # history search: 25.000, 25 000 and 25000 all find the 25,000 SAT payment
            await f.click('[data-act=tab][data-tab=history]'); await f.wait(150)
            hits = []
            for q in ['25.000', '25 000', '25,000', '25000']:
                await f.fill('#hq', q); await f.wait(200); hits.append(await f.ev("document.querySelectorAll('#txList .tx').length"))
            check(f'history {lang}: searching an amount works however it is grouped', all(h >= 1 for h in hits), hits)
            if lang == 'de':
                await f.click('[data-act=tab][data-tab=wallet]'); await f.click('[data-act=splitOpen]'); await f.wait(150)
                await f.fill('#amtIn', '900'); await f.fill('#splitN', '3'); await f.click('[data-act=splitCreate]'); await f.wait(600)
                check('split (de): the default memo is translated', await f.ev("Nutcade.S.requests[0].memo") == 'Rechnung teilen', await f.ev("Nutcade.S.requests[0].memo"))
                await f.ev("Nutcade.closeSheet()")
            await f.pg.context.close()

        # error toasts are never dropped while a game holds the queue; the screen-reader digit count is singular for one
        t = await wallet(b, 375, 667, 'en'); await t.create()
        await t.click('[data-act=tab][data-tab=arcade]'); await t.wait(150); await t.ev("document.querySelector('[data-game=swarm]').click()"); await t.wait(300)
        await t.ev("Nutcade.toast('A received');Nutcade.toast('B failed','red');Nutcade.toast('C three');Nutcade.toast('D four');Nutcade.toast('E five')"); await t.wait(200)
        await t.ev("document.querySelector('[data-g=exit]').click()"); seen = []
        for _ in range(60):
            x = await t.toast()
            if x and (not seen or seen[-1] != x): seen.append(x)
            await t.wait(250)
        check('toasts: an error raised during a game is shown after it, first', seen[:1] == ['B failed'], seen)
        await t.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=pinSet]').click()"); await t.wait(200)
        await t.click('[data-pinpad] [data-k="1"]'); one = await t.ev("document.querySelector('.pin-dots').getAttribute('aria-label')")
        check('PIN pad: "1 digit entered", singular', one == '1 digit entered', one)
        css = await t.ev("[...document.querySelectorAll('style')].map(s=>s.textContent).join('\\n')")
        missing = []
        for m in re.finditer(r'([{;]\s*)([a-z-]+)\s*:([^;{}]*color-mix\()', css):
            prop = m.group(2); start = m.start(2); before = css[max(css.rfind('{', 0, start), css.rfind(';', 0, start - 1)) + 1:start]
            prev = re.split(r';', css[css.rfind('{', 0, start) + 1:start])
            prev = [d.strip() for d in prev if d.strip()]
            if not prev or not prev[-1].startswith(prop + ':') or 'color-mix' in prev[-1]: missing.append(prop + ' @' + str(start))
        check('older Safari: every color-mix() declaration has a plain fallback right before it', not missing and css.count('color-mix(') > 0, missing[:6])
        hy = await t.ev("[getComputedStyle(document.body).hyphens, (()=>{const n=document.createElement('div');n.className='notice';document.body.appendChild(n);const h=getComputedStyle(n).hyphens;n.remove();return h})()]")
        check('body text is not hyphenated', all(h == 'manual' for h in hy), hy)
        await t.pg.context.close()

        # desktop: the till's keypad works from the keyboard; offline, CHARGE fits a 320x640 phone in German
        k = await wallet(b, 1440, 900, 'en', mobile=False)
        await k.create(); await k.add_mint(B); await k.home(); await k.wait(300); await k.click('[data-act=cashier]'); await k.wait(200)
        await k.pg.keyboard.type('1250'); await k.pg.keyboard.press('Backspace'); await k.wait(100)
        typed = await k.ev("document.querySelector('.cash-amt').innerText")
        await k.click('[data-ck=clear]'); await k.pg.keyboard.press('Enter'); await k.wait(300); empty_ok = await k.ev("!document.querySelector('.cash-pay,.cash-paid')")
        await k.pg.keyboard.type('21'); await k.pg.keyboard.press('Enter'); ok = await k.until("!!document.querySelector('.cash-pay,.cash-paid')", 10000)
        check('desktop cashier: digits, Backspace and Enter work; Enter does nothing on an empty amount', typed.startswith('125') and empty_ok and ok, (typed, empty_ok, ok))
        await k.pg.context.close()
        o = await wallet(b, 320, 640, 'de'); await o.create(); await o.add_mint(B); await o.home()
        await o.pg.context.set_offline(True); await o.wait(500); await o.click('[data-act=cashier]'); await o.wait(400)
        r = await o.ev(f"[({INVIEW})('.cash-charge'), ({INVIEW})('[data-ck=close]')]")
        check('offline (de 320x640): CHARGE and Close the till fit under the banner', r == ['ok', 'ok'], r)
        await o.pg.context.set_offline(False); await o.pg.context.close()

        # ---------- round 4: typed amounts never silently become different amounts ----------
        # The tester's whole sweep table, typed into a fiat amount field in every language at a rate of $100,000:
        # each row is read exactly (the ≈ SAT hint, which is what the invoice uses) or refused (no hint, red field,
        # and Create invoice makes nothing). None = refuse; a pair = either of those readings is fine.
        SWEEP = [('12,50', 12.5, 12.5), ('12.50', 12.5, 12.5), ('1.234,56', 1234.56, 1234.56), ('1 234,56', 1234.56, 1234.56), ('1,234.56', 1234.56, 1234.56), ('1234,5', 1234.5, 1234.5), ('0,5', 0.5, 0.5),
                 ('1.000', 1.0, 1000), ('1,000', 1000, 1.0), ('1,234', 1234, 1.234), ('1.234', 1.234, 1234), ('1.234.567,89', 1234567.89, 1234567.89), ('1,234,567.89', 1234567.89, 1234567.89),
                 ('1,5', 1.5, 1.5), ('1.5', 1.5, 1.5), ('12.34', 12.34, 12.34), ('1 000', 1000, 1000), ('1 000', 1000, 1000), ('1 000,50', 1000.5, 1000.5), ("1'234.50", 1234.5, 1234.5),
                 (',5', 0.5, 0.5), ('.5', 0.5, 0.5), ('5,', 5, 5), ('5.', 5, 5), ('-5', None, None), ('+5', None, None), ('abc', None, None), ('12abc', None, None), ('1e3', None, None),
                 ('$12.50', None, None), ('12,50 €', None, None), ('0,001', 0.001, 0.001), ('0.001', 0.001, (0.001, None)), ('0.500', 0.5, (0.5, None)), ('0,500', (0.5, None), 0.5),
                 ('12..50', None, None), ('12,,50', None, None), ('1.2.3', None, None), ('1,23,4', None, None), ('1.23.456', None, None), ('1.234.56', None, None), ('1,234,56', None, None),
                 ('1.234,56,7', None, None), ('999999999999', 999999999999, 999999999999), ('99.999.999.999,99', 99999999999.99, 99999999999.99), ('１２', None, None), ('١٢', None, None),
                 ('1_000', None, None), ('', 0, 0), ('   ', 0, 0), ('.', 0, 0), (',', 0, 0), ('0', 0, 0), ('00012,50', 12.5, 12.5)]
        from fractions import Fraction
        def want_sats(x): v = Fraction(str(x)) / 100000 * 10**8; return int(v + Fraction(1, 2)) if v else 0
        SATS = [('1000', 1000), ('1,000', {'en': 1000}), ('1.000', {'de': 1000, 'es': 1000, 'pt': 1000}), ('1 000', 1000), ('1 000', 1000), (' 2 100 ', 2100), ('007', 7),
                ('1.5', None), ('1,5', None), ('-500', None), ('+500', None), ('1e3', None), ('12abc', None), ('0x10', None), ('٣٠٠', None), ('１２３', None), ('1_000', None),
                ('0,5', None), ('12 34', None), ('99999999999999999999', None), ('9007199254740993', None), ('2100000000000001', None)]
        def sat_want(exp, lang):
            if isinstance(exp, dict): return exp.get(lang)
            return exp
        for lang in LANGS:
            m = await wallet(b, 375, 667, lang)
            await m.pg.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '100000'}}})))
            await m.create(); await m.add_mint(B); await m.receive_ln(2000); await m.home(); await m.wait(900)
            await m.click('[data-act=receive]'); await m.wait(150)
            if await m.ev("document.querySelector('#amtIn').dataset.cur") != 'fiat': await m.click('[data-act=amtUnit]'); await m.wait(100)
            bad = []
            for typed, een, edc in SWEEP:
                exp = een if lang == 'en' else edc
                okset = set(exp) if isinstance(exp, tuple) else {exp}
                await m.fill('#amtIn', typed); await m.wait(40)
                got = await m.ev("[document.querySelector('.amtconv').innerText, document.querySelector('#amtIn').getAttribute('aria-invalid')]")
                n = int(re.sub(r'[^0-9]', '', got[0]) or 0)
                reading = None if got[1] == 'true' else n
                fine = any((reading is None and e is None) or (e is not None and reading == want_sats(e)) for e in okset)
                if fine and reading is None:   # refused: submitting makes nothing
                    n0 = await m.ev("Nutcade.S.txs.length"); await m.click('[data-act=doLnInvoice]'); await m.wait(250)
                    fine = await m.ev("Nutcade.S.txs.length") == n0 and bool(await m.err())
                if not fine: bad.append((typed, got, [want_sats(e) if e is not None else 'refuse' for e in okset]))
            check(f'round 4 sweep {lang}: all {len(SWEEP)} typed amounts in your currency are read exactly or refused', not bad, bad[:6])
            # SAT fields: whole SAT, grouped with spaces or the language's own mark; anything else refused, nothing dropped
            await m.click('[data-act=amtUnit]'); await m.wait(100); bad = []
            for typed, exp in SATS:
                e = sat_want(exp, lang)
                r = await m.ev(f"(t=>{{try{{return Nutcade.parseSat(t)}}catch(e){{return 'ERR '+e.message}}}})({json.dumps(typed)})")
                if e is None and not str(r).startswith('ERR'): bad.append((typed, r))
                if e is not None and r != e: bad.append((typed, r))
            msgs = await m.ev("['1.5','-500','99999999999999999999'].map(t=>{try{Nutcade.parseSat(t)}catch(e){return Nutcade.tr(e.message)}})")
            check(f'round 4 SAT {lang}: whole SAT only, decimals and junk refused with a translated reason, never stripped', not bad and all(msgs) and not any('bigint' in x or 'Unsafe' in x for x in msgs) and (lang == 'en' or msgs[0] != 'SAT are whole numbers, with no decimals. Type it like this: 1,500'), (bad, msgs))
            # SAT -> currency -> SAT keeps exactly what was typed
            rt = []
            for v in ['1', '7', '49', '515', '1271123']:
                await m.fill('#amtIn', v); await m.click('[data-act=amtUnit]'); await m.wait(60); f = await m.ev("document.querySelector('#amtIn').value"); await m.click('[data-act=amtUnit]'); await m.wait(60)
                rt.append((v, f, await m.ev("document.querySelector('#amtIn').value")))
            check(f'round 4 toggle {lang}: switching to USD and back restores the exact SAT typed', all(a == c and b not in ('', '0.00', '0,00') for a, b, c in rt), rt)
            await m.pg.context.close()

        # bitcoin: links and addresses
        z = await wallet(b, 375, 667, 'en'); await z.create(); await z.add_mint(B)
        ADDR = 'bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq'
        bip = [('0.001', 100000), ('1.5', 150000000), ('0.00000001', 1), ('.5', 50000000), ('21000000', 2100000000000000), ('1,5', None), ('1.5.5', None), ('0.1abc', None), ('1e-3', None),
               ('-1', None), ('abc', None), ('0.000000015', None), ('21000001', None), ('0', None), ('%200.5', None)]
        bad = []
        for a, exp in bip:
            r = await z.ev(f"(r=>[r.kind,r.amount,r.badAmount!=null])(Nutcade.classify({json.dumps('bitcoin:' + ADDR + '?amount=' + a)}))")
            if r[0] != 'btc' or r[1] != exp or r[2] != (exp is None): bad.append((a, r))
        r2 = await z.ev(f"[Nutcade.classify({json.dumps('BITCOIN:' + ADDR.upper() + '?AMOUNT=0.5')}).amount, Nutcade.classify({json.dumps('bitcoin:' + ADDR + '?amount=0.001&amount=5')}).amount]")
        check('round 4 BIP21: amounts are read exactly in BTC or left out (commas, exponents, junk, two amounts, over 21M)', not bad and r2 == [50000000, None], (bad, r2))
        good = ['bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq', 'bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0', '1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2', '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy', 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx']
        badA = [ADDR + 'x', ADDR[:-1] + 'p', '1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3', '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLz', 'bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5md']
        ga = await z.ev(f"{json.dumps(good)}.map(a=>Nutcade.classify(a).kind)"); ba = await z.ev(f"{json.dumps(badA)}.map(a=>Nutcade.classify(a).kind)")
        check('round 4 addresses: bech32/bech32m and base58check checksums are checked (one extra or wrong letter is refused)', all(k == 'btc' for k in ga) and not any(k == 'btc' for k in ba), (ga, ba))
        await z.ev(f"Nutcade.handleScan({json.dumps('bitcoin:' + ADDR + '?amount=1,5')})"); await z.wait(300)
        check('round 4 BIP21: an amount that can\'t be read is left out and the send screen says so', await z.ev("!document.querySelector('#amtIn') || document.querySelector('#amtIn').value===''") and 'left out' in await z.err(), await z.err())
        await z.ev("Nutcade.closeSheet()")
        # mint URLs: one spelling; old twins are merged with their ecash
        n0 = await z.ev("Nutcade.S.mints.length")
        await z.ev("document.querySelector('[data-act=pickMint]').click()"); await z.wait(200); await z.fill('#mintUrl', 'HTTP://127.0.0.1:3339/'); await z.click('[data-act=addMintUrl]'); await z.wait(1500)
        check('round 4 mints: HTTP://127.0.0.1:3339/ is the same mint, not a second copy', await z.ev("Nutcade.S.mints.length") == n0, await z.ev("Nutcade.S.mints.map(m=>m.url)"))
        await z.ev("Nutcade.closeSheet()"); await z.receive_ln(300)
        total0 = await z.bal()
        await z.ev("""(()=>{const g=k=>JSON.parse(localStorage.getItem('nutcade:'+k));const ms=g('mints'),ps=g('proofs');const u='http://127.0.0.1:3339';
          ms.push(Object.assign({},ms.find(m=>m.url===u),{url:'HTTP://127.0.0.1:3339/'}));const p=ps[u];ps['HTTP://127.0.0.1:3339/']=[p[0]].concat(p.slice(1,2).map(x=>Object.assign({},x)));ps[u]=p.slice(1);
          localStorage.setItem('nutcade:mints',JSON.stringify(ms));localStorage.setItem('nutcade:proofs',JSON.stringify(ps))})()""")
        await z.pg.reload(); await z.wait(900)
        mg = await z.ev("[Nutcade.S.mints.map(m=>m.url), Object.keys(Nutcade.S.proofs), Object.values(Nutcade.S.proofs).flat().length, new Set(Object.values(Nutcade.S.proofs).flat().map(p=>p.secret)).size]")
        check('round 4 mints: a wallet that already holds a twin spelling is merged on load, each coin once, nothing lost', mg[0] == ['http://127.0.0.1:3339'] and mg[1] == ['http://127.0.0.1:3339'] and mg[2] == mg[3] and await z.bal() == total0, (mg, total0, await z.bal()))
        # counts, split, request for 0, duplicate contacts
        await z.home(); res = []
        for tot, n in [('1000', '2.5'), ('1000', '1e1'), ('3', '30')]:
            await z.click('[data-act=splitOpen]'); await z.wait(150); n0 = await z.ev("Nutcade.S.requests.length")
            await z.fill('#amtIn', tot); await z.ev(f"document.querySelector('#splitN').value={json.dumps(n)}"); await z.click('[data-act=splitCreate]'); await z.wait(300)
            res.append((tot, n, await z.ev("Nutcade.S.requests.length") - n0, (await z.err())[:40])); await z.ev("Nutcade.closeSheet()")
        await z.click('[data-act=huntNew]'); await z.wait(150); await z.fill('#amtIn', '100'); await z.fill('#huntN', '2.5'); await z.click('[data-act=huntCreate]'); await z.wait(300)
        res.append(('hunt', '2.5', 0 if await z.err() else 1, (await z.err())[:40])); await z.ev("Nutcade.closeSheet()")
        check('round 4 counts: 2.5 people, 1e1 people and 2.5 clue cards are refused, and 3 SAT among 30 people', all(r[2] == 0 and r[3] for r in res), res)
        await z.click('[data-act=receive]'); await z.wait(150); await z.click('[data-act=recvMethod][data-m=ecash]'); await z.wait(100); await z.click('[data-act=reqOpen]'); await z.wait(200)
        n0 = await z.ev("Nutcade.S.requests.length"); await z.fill('#amtIn', '0'); await z.click('[data-act=reqCreate]'); await z.wait(300)
        check('round 4 request: 0 is refused (empty means any amount)', await z.ev("Nutcade.S.requests.length") == n0 and 'empty' in await z.err(), await z.err())
        await z.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await z.wait(150)
        made = []
        for ln in ['bob@pay.test', ' BOB@Pay.Test ']:
            await z.click('[data-act=contactsOpen]'); await z.wait(150); await z.ev("document.querySelector('[data-act=contactEdit]:not([data-id])').click()"); await z.wait(150)
            await z.fill('#cName', 'Bob'); await z.fill('#cLn', ln); await z.click('[data-act=contactSave]'); await z.wait(300); made.append(await z.ev("Nutcade.S.contacts.length"))
            e = await z.ev("[(document.querySelector('#sheetErr')||{}).innerText||'', !!document.querySelector('#sheetErr [data-act=contactEdit][data-id]')]"); await z.ev("Nutcade.closeSheet()")
        check('round 4 contacts: the same Lightning address can\'t be saved twice; the message offers the existing contact', made == [1, 1] and 'already has' in e[0] and e[1], (made, e))
        await z.pg.context.close()

        # fees on the fee mint: amount + fee is exactly what the balance dropped by
        fz = await wallet(b, 375, 667, 'en'); await fz.create(); await fz.add_mint(A); await fz.use(A); await fz.receive_ln(4000)
        b0 = await fz.bal(A); tok, e = await fz.send_ecash(1000); t = await fz.ev("Nutcade.S.txs[0]"); b1 = await fz.bal(A)
        b2 = None; t2 = None
        e2, q = await fz.pay_ln(__import__('wallet_qa').invoice(700, B)); t2 = await fz.ev("Nutcade.S.txs[0]"); b2 = await fz.bal(A)
        check('round 4 fees: ecash send and Lightning payment on a fee mint record fee = balance drop - amount', not e and not e2 and b0 - b1 == t['amount'] + t['fee'] and t['fee'] >= 2 and b1 - b2 == t2['amount'] + t2['fee'] and t2['status'] == 'done',
              (b0, b1, b2, t['amount'], t['fee'], t2['amount'], t2['fee'], e, e2))
        await fz.home(); await fz.click('[data-act=send]'); await fz.wait(150); await fz.fill('#amtIn', str(b2)); await fz.click('[data-act=doSendEcash]'); await fz.wait(1500)
        msg = await fz.err(); has_btn = await fz.has('#sheetErr [data-act=sendMax]') if hasattr(fz, 'has') else await fz.ev("!!document.querySelector('#sheetErr [data-act=sendMax]')")
        await fz.click('#sheetErr [data-act=sendMax]'); await fz.until("!!document.querySelector('#layer .qr')", 8000); t3 = await fz.ev("Nutcade.S.txs[0]"); b3 = await fz.bal(A)
        check('round 4 fees: sending the whole balance explains the fee and offers the most that can be sent, which works', 'most you can send' in msg and 'Not enough funds available' not in msg and has_btn and b2 - b3 == t3['amount'] + t3['fee'] and b3 < 5,
              (msg, b2, b3, t3['amount'], t3['fee']))
        await fz.pg.context.close()

        # the till: opened with the mouse, Enter charges (once), and doesn't reset the amount
        k = await wallet(b, 1440, 900, 'en', mobile=False); await k.create(); await k.add_mint(B); await k.home(); await k.wait(300)
        await k.pg.locator('#app [data-act=cashier]').click(); await k.wait(300)
        inside = await k.ev("!!document.activeElement.closest('.cashier')")
        await k.pg.keyboard.type('250'); n0 = await k.ev("Nutcade.S.quotes.length+'/'+Nutcade.S.txs.length")
        await k.pg.keyboard.down('Enter')
        for _ in range(5): await k.pg.keyboard.down('Enter')
        await k.pg.keyboard.up('Enter'); await k.until("!!document.querySelector('.cash-pay,.cash-paid')", 10000); await k.wait(500)
        txs = await k.ev("Nutcade.S.txs.filter(t=>/#cashier/.test(t.note||'')).map(t=>t.amount)")
        check('round 4 till: opened by mouse, focus is in the till and Enter (even held) charges exactly once, the typed amount', inside and txs == [250], (inside, n0, txs))
        await k.pg.context.close()

        # D-pad: switching re-fits the screen, so the hint never sits on the canvas
        dp = []
        for lang, vw, g in [('en', 320, 'flipper'), ('fr', 320, 'swarm'), ('es', 375, 'shield')]:
            q = await wallet(b, vw, 640 if vw == 320 else 667, lang); await q.create()
            await q.ev("localStorage.removeItem('nutcade:pad')"); await q.click('[data-act=tab][data-tab=arcade]'); await q.wait(150); await q.ev(f"document.querySelector('[data-game={g}]').click()"); await q.wait(400)
            await q.ev("document.querySelector('[data-g=pad]').click()"); await q.wait(200)
            r = await q.ev("(()=>{const c=document.querySelector('#gameCanvas').getBoundingClientRect(),h=document.querySelector('.game-view .hint').getBoundingClientRect();return [Math.round(c.bottom),Math.round(h.top)]})()")
            dp.append((lang, vw, g, r)); await q.pg.context.close()
        check('round 4 D-pad: the hint sits under the game screen after switching to the D-pad', all(r[0] <= r[1] for *_, r in dp), dp)

        # German sheet title at 320 and 375: it only breaks at a soft hyphen
        for vw in (320, 375):
            q = await wallet(b, vw, 667, 'de'); await q.create()
            await q.ev("document.querySelector('[data-act=tab][data-tab=settings]').click()"); await q.wait(150); await q.click('[data-act=seedShow]'); await q.wait(300)
            br = await q.ev("""(()=>{const out=[];for(const h of document.querySelectorAll('#layer .sheet-head h3')){const n=h.firstChild;if(!n||n.nodeType!==3)continue;const t=n.nodeValue;let top=null;
              for(let i=0;i<t.length;i++){const r=document.createRange();r.setStart(n,i);r.setEnd(n,i+1);const q=[...r.getClientRects()].filter(x=>x.width>0).pop();if(!q)continue;const y=Math.round(q.top);
                if(top!==null&&y>top+2){out.push({at:i,ok:/[\\u00ad\\s-]$/.test(t.slice(0,i))||t[i-1]===' '})}top=y}}return [document.querySelector('#layer .sheet-head h3').innerText,out]})()""")
            check(f'round 4 German title at {vw}: breaks only at a soft hyphen or a space', all(x['ok'] for x in br[1]), br)
            await q.pg.context.close()

        # keyboard focus survives a redraw right after a sheet closes (why the tester's Restore wallet check failed)
        rf = await wallet(b, 1440, 900, 'en', mobile=False); await rf.create(); await rf.add_mint(B)
        await rf.click('[data-act=tab][data-tab=settings]'); await rf.wait(150); await rf.pg.locator('#app [data-act=seedRestore]').focus(); await rf.pg.keyboard.press('Enter'); await rf.wait(400)
        for _ in range(22): await rf.pg.keyboard.press('Tab')
        await rf.pg.keyboard.press('Escape'); await rf.wait(100); a1 = await rf.ev("document.activeElement.dataset.act||document.activeElement.tagName")
        await rf.ev("Nutcade.refresh()"); await rf.wait(100); a2 = await rf.ev("document.activeElement.dataset.act||document.activeElement.tagName")
        check('round 4 focus: after Esc on Restore wallet, focus is on its button, and stays there through a screen refresh', a1 == a2 == 'seedRestore', (a1, a2))
        await rf.pg.context.close()

        # ---------- round 5 ----------
        # The history always adds up to the balance, on both kinds of mint, after every money path, failures included.
        # ledger(mint) = sum of received (done/claimed) - sum of sent (amount + fee), skipping payments that failed or
        # expired (they moved nothing; a cost that didn't come back is its own "Mint fee" line).
        LEDGER = """(u=>{let s=0;for(const t of Nutcade.S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return [s,(Nutcade.S.proofs[u]||[]).reduce((a,p)=>a+p.amount,0)]})"""
        FM = 'http://127.0.0.1:3340'
        from wallet_qa import invoice as qinv
        mw = await wallet(b, 375, 667, 'en')
        await mw.create(); await mw.add_mint(B); await mw.add_mint(A); await mw.add_mint(FM)
        broken = []
        # 1.12: LNURL vouchers, zaps and Wallet Connect are money paths too
        zp = {}   # a zap from each mint pays an invoice at the other one (a test mint counts its own invoices as paid already)
        for M, O, nm in ((A, B, 'zeda'), (B, A, 'zedb')): r7mock('/test/lnurlp', {'name': nm, 'zap': True, 'mint': O}); zp[M] = r7mock('/test/profile', {'name': nm, 'lud16': nm + '@lnurl.test'})
        nwc_uri = await r7make_nwc(mw, 'Ledger app'); await mw.ev("Nutcade.closeSheet()")
        async def books(step):
            for u in (A, B, FM):
                l, p = await mw.ev(LEDGER + f"({json.dumps(u)})")
                if l != p: broken.append((step, u[-4:], l, p))
        for M, O in ((A, B), (B, A)):
            await mw.use(M); await mw.receive_ln(6000); await books('receive ' + M[-4:])
            tok, e = await mw.send_ecash(1000); await books('send ecash ' + M[-4:])
            await mw.receive_token(tok); await books('reclaim own token ' + M[-4:])
            e, q = await mw.pay_ln(qinv(700, O)); await books('pay invoice ' + M[-4:])
            e, q = await mw.pay_ln(qinv(300, M)); await books('failed self-payment ' + M[-4:])   # the test mint already counts its own invoices as paid
            await mw.home(); await mw.click('[data-act=huntNew]'); await mw.wait(150); await mw.fill('#amtIn', '200'); await mw.click('[data-act=huntCreate]'); await mw.wait(2500); await mw.ev("Nutcade.closeSheet()"); await books('treasure hunt ' + M[-4:])
            await mw.home(); await mw.click('[data-act=cashier]'); await mw.wait(300)
            for k in '150': await mw.click(f'[data-ck="{k}"]')
            await mw.click('[data-ck=charge]'); await mw.until("!!document.querySelector('.cash-paid')", 15000); await mw.ev("document.querySelector('#cashExit').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}))"); await mw.wait(300); await books('till sale ' + M[-4:])
            vid = 'ledger' + M[-4:]; r7mock('/test/lnurlw', {'id': vid, 'min': 1, 'max': 900, 'desc': 'Ledger voucher'}); have = await mw.bal(M)
            await mw.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}')"); await mw.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000)
            await mw.ev(f"document.querySelector('#wdMint').value={json.dumps(M)}"); await mw.click('[data-act=lnurlwGo]'); await mw.until(f"(Nutcade.S.proofs[{json.dumps(M)}]||[]).reduce((t,p)=>t+p.amount,0) >= {have + 900}", 20000); await mw.wait(300); await mw.ev("Nutcade.closeSheet()"); await books('LNURL voucher ' + M[-4:])
            await mw.home(); await mw.click('[data-act=send]'); await mw.wait(150); await mw.click('[data-act=sendMethod][data-m=ln]'); await mw.wait(100); await mw.fill('#destIn', zp[M]['npub']); await mw.click('[data-act=doMeltQuote]')
            await mw.until("!!document.querySelector('[data-act=zapQuote]')", 10000); await mw.fill('#amtIn', '210'); await mw.click('[data-act=zapQuote]'); await mw.until("!!document.querySelector('#payBtn')", 10000); await mw.click('#payBtn'); await mw.until("!document.querySelector('#payBtn')", 15000); await mw.wait(300); await mw.ev("Nutcade.closeSheet()"); await books('zap ' + M[-4:])
            await r7nwc(mw, nwc_uri, 'pay_invoice', {'invoice': qinv(333, O)}); await books('Wallet Connect payment ' + M[-4:])
            r = await r7nwc(mw, nwc_uri, 'make_invoice', {'amount': 444000}); inv = ((r.get('answer') or {}).get('result') or {}).get('invoice')
            await mw.until(f"(Nutcade.S.txs.find(t=>t.request==={json.dumps(inv)})||{{}}).status==='done'", 20000); await books('Wallet Connect invoice ' + M[-4:])
            await mw.ev("window.__nutcadeTest={lnurlMs:800}"); r7mock('/test/lnurlw', {'id': vid + 'x', 'min': 1, 'max': 90, 'mode': 'error'}); await mw.ev(f"Nutcade.handleScan('lnurlw://lnurl.test/lnurlw/{vid}x')"); await mw.until("!!document.querySelector('[data-act=lnurlwGo]')", 8000)
            await mw.click('[data-act=lnurlwGo]'); await mw.wait(1500); await mw.ev("window.__nutcadeTest={}; Nutcade.closeSheet()"); await books('refused voucher ' + M[-4:])
        fee_rows = await mw.ev(f"Nutcade.S.txs.filter(t=>t.method==='fee').map(t=>[t.mint.slice(-4),t.fee,t.status,!!(Nutcade.S.txs.find(x=>x.id===t.feeFor)||{{}}).cost])")
        failed = await mw.ev("Nutcade.S.txs.filter(t=>t.status==='failed'&&t.type==='out').map(t=>[t.mint.slice(-4),t.amount,t.fee||0,t.cost||0])")
        # the always-fail mint (no input fees): a failed payment costs nothing and records no fee
        await mw.use(FM); await mw.receive_ln(3000); e, q = await mw.pay_ln(qinv(400, B)); await books('failed payment, no-fee mint')
        f0 = await mw.ev(f"(t=>[t.status,t.fee||0,t.cost||0])(Nutcade.S.txs.find(t=>t.mint==={json.dumps(FM)}&&t.type==='out'))")
        await mw.use(FM); r = await r7nwc(mw, nwc_uri, 'pay_invoice', {'invoice': qinv(150, B)}, wait=25); await books('failed Wallet Connect payment, no-fee mint')
        check('round 5 money: after every path on the fee mint and the no-fee mint (receive, send, reclaim, pay, failed payment, hunt, till, LNURL voucher, refused voucher, zap, Wallet Connect payment and invoice, failed Wallet Connect payment) the history adds up to the balance', not broken, broken)
        check('round 5 money: a failed payment that cost a swap fee records no fee itself and one linked "Mint fee" line with the real cost', all(f[2] == 0 for f in failed) and any(r[0] == A[-4:] and r[1] >= 1 and r[3] for r in fee_rows) and not any(r[0] == B[-4:] for r in fee_rows), (failed, fee_rows))
        check('round 5 money: a failed payment that cost nothing records no fee and no fee line', f0[0] == 'failed' and f0[1] == 0 and f0[2] == 0, f0)
        # the failed payment says what it cost, and its detail and history row show nothing moved
        await mw.use(A); n0 = await mw.ev("Nutcade.S.txs.length"); e, q = await mw.pay_ln(qinv(250, A))
        await mw.click('[data-act=tab][data-tab=history]'); await mw.wait(200)
        rows = await mw.ev("[...document.querySelectorAll('#txList .tx')].slice(0,2).map(r=>r.innerText.replace(/\\s+/g,' ')+'|'+r.querySelector('.amt').className)")
        await mw.ev("[...document.querySelectorAll('#txList .tx')].find(r=>/FAILED/.test(r.innerText)).click()"); await mw.wait(250); det = await mw.sheet_text(); await mw.ev("Nutcade.closeSheet()")
        check('round 5 money: the failed payment is struck through, says the mint kept 1 SAT, and the fee line shows -1', 'except 1 SAT the mint kept' in det and any('void' in r for r in rows) and any('FEE' in r and '-1' in r for r in rows), (rows, det[:200]))
        await mw.pg.context.close()

        # SAT typed, only the view switched to USD: the hint and the invoice are exactly the SAT typed
        tg = await wallet(b, 375, 667, 'en')
        await tg.pg.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '97123.55'}}})))
        await tg.create(); await tg.add_mint(B); await tg.receive_ln(5000); await tg.home(); await tg.wait(900)
        await tg.click('[data-act=receive]'); await tg.wait(150); await tg.fill('#amtIn', '49'); await tg.click('[data-act=amtUnit]'); await tg.wait(100)
        view = await tg.ev("[document.querySelector('#amtIn').value, document.querySelector('.amtconv').innerText]")
        await tg.click('[data-act=doLnInvoice]'); await tg.wait(1500); a49 = await tg.ev("Nutcade.S.txs[0].amount")
        check('round 5 switch: 49 SAT shown in USD still says ≈ 49 SAT and invoices 49', '49 SAT' in view[1] and a49 == 49, (view, a49))
        await tg.ev("Nutcade.closeSheet()"); await tg.click('[data-act=cashier]'); await tg.wait(200)
        if await tg.ev("document.querySelector('[data-ck=unit]').innerText.trim()") != 'SAT': await tg.click('[data-ck=unit]'); await tg.wait(100)   # start from SAT
        for k in '49': await tg.click(f'[data-ck="{k}"]')
        await tg.click('[data-ck=unit]'); await tg.wait(100); till = await tg.ev("document.querySelector('.cash-charge').innerText")
        check('round 5 switch: on the till too, 49 SAT viewed in USD charges 49', '49 SAT' in till, till)
        await tg.pg.context.close()
        # "01.000" and friends are refused in every language; plain decimals still read
        for lang in LANGS:
            z = await wallet(b, 375, 667, lang)
            r = await z.ev("['01.000','01,000','00.500','0.5','0,5','00012,50'].map(t=>{try{return Nutcade.parseFiat(t)}catch(e){return 'refused'}})")
            check(f'round 5 leading zero {lang}: 01.000, 01,000 and 00.500 are refused; 0.5, 0,5 and 00012,50 read', r == ['refused', 'refused', 'refused', 0.5, 0.5, 12.5], r)
            await z.pg.context.close()
        # merging twin mint spellings also remaps Extra Life, heirlooms, challenges, hunts and the mint log
        mg = await wallet(b, 375, 667, 'en'); await mg.create(); await mg.add_mint(B); await mg.receive_ln(500)
        await mg.ev("""(()=>{const g=k=>JSON.parse(localStorage.getItem('nutcade:'+k)||'null');const T='HTTP://127.0.0.1:3339/';
          localStorage.setItem('nutcade:extra',JSON.stringify({mint:T,amount:1,proofs:[],heir:{pubkey:'02',name:'Al'},until:Date.now()+9e9,days:30}));
          localStorage.setItem('nutcade:heirlooms',JSON.stringify([{from:'x',name:'Al',token:'',amount:1,mint:T,until:0,state:'waiting'}]));
          localStorage.setItem('nutcade:challenges',JSON.stringify([{id:'c1',dir:'out',game:'swarm',score:1,bounties:[{mint:T,amount:1}]}]));
          localStorage.setItem('nutcade:hunts',JSON.stringify([{pub:'p',mint:T,amount:1}]));
          const ml=g('mintlog')||{};ml[T]={first:1,ms:[5],ops:[1,0],keysets:{},changes:[]};localStorage.setItem('nutcade:mintlog',JSON.stringify(ml))})()""")
        await mg.pg.reload(); await mg.wait(900)
        st = await mg.ev("JSON.stringify([Nutcade.S.extra&&Nutcade.S.extra.mint,(Nutcade.S.heirlooms||[]).map(h=>h.mint),(Nutcade.S.challenges||[]).map(c=>c.bounties.map(b=>b.mint)),(Nutcade.S.hunts||[]).map(h=>h.mint),Object.keys(Nutcade.S.mintlog||{})])")
        check('round 5 merge: Extra Life, heirlooms, challenge bounties, hunts and the mint log all point at the merged mint', 'HTTP' not in st and st.count('http://127.0.0.1:3339') >= 5, st)
        await mg.pg.context.close()

        # No English left on screen in the other languages: main screens, sheets, toasts, game screens and aria labels.
        # Every string the page translates and doesn't find is recorded; only brand names, units and currency codes may stay.
        ALLOW = re.compile(r'^(NUTCADE|SAT|BTC|LN|NOSTR|[A-Z]{3}|(STAR SWARM|NUT MAZE|BRICK BLITZ|VOID ROCKS|HOP LANES|SKY SHIELD|NIBBLE|NUT FLIPPER))$')
        SHEETS = [('wallet', 'receive'), ('wallet', 'send'), ('wallet', 'scan'), ('wallet', 'splitOpen'), ('wallet', 'huntNew'), ('wallet', 'extraOpen'), ('wallet', 'pickMint'), ('wallet', 'ctListen'),
                  ('settings', 'seedShow'), ('settings', 'seedRestore'), ('settings', 'restore'), ('settings', 'resetAsk'), ('settings', 'lnAddr'), ('settings', 'support'), ('settings', 'contactsOpen'),
                  ('settings', 'moveOpen'), ('settings', 'tillOpen'), ('settings', 'pinSet'), ('settings', 'findLost'), ('mints', 'reportOpen'), ('settings', 'nwcNew'), ('mints', 'blockMint')]
        for lang in ('de', 'fr', 'es', 'pt'):
            h = await wallet(b, 375, 667, lang)
            await h.pg.add_init_script("(()=>{const s=window.__i18nMiss;const a=s.add.bind(s);s.add=v=>{try{const k='qa:miss5';const c=JSON.parse(localStorage.getItem(k)||'[]');if(!c.includes(v)){c.push(v);localStorage.setItem(k,JSON.stringify(c))}}catch(e){}return a(v)}})()")
            await h.pg.reload(); await h.wait(700)
            await h.create(); await h.add_mint(B); await h.add_mint(A); await h.use(B); await h.receive_ln(4000, 'Lunch #food'); await h.send_ecash(300, 'Pizza')
            for t in ('wallet', 'arcade', 'history', 'mints', 'settings'):
                await h.ev(f"Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab={t}]').click()"); await h.wait(400)
            for t, a in SHEETS:
                await h.ev(f"Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab={t}]').click()"); await h.wait(150)
                await h.ev(f"(e=>e&&e.click())(document.querySelector('#app [data-act={a}]'))"); await h.wait(500)
            await h.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=history]').click()"); await h.wait(150); await h.ev("document.querySelector('[data-act=tx]').click()"); await h.wait(300)
            await h.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()"); await h.wait(150); await h.click('[data-act=send]'); await h.wait(150)
            for v in ('1.5', '-5', '99999999999999999999'):
                await h.fill('#amtIn', v); await h.click('[data-act=doSendEcash]'); await h.wait(300)
            await h.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=arcade]').click()"); await h.wait(200)
            for g in ('swarm', 'flipper'):
                await h.ev(f"document.querySelector('[data-game={g}]').click()"); await h.wait(500); await h.ev("document.querySelector('[data-g=pad]').click()"); await h.wait(200); await h.ev("document.querySelector('[data-g=exit]').click()"); await h.wait(200)
            await h.ev("document.querySelector('[data-act=tab][data-tab=wallet]').click()"); await h.wait(200); await h.click('[data-act=cashier]'); await h.wait(300)
            for k in '25': await h.click(f'[data-ck="{k}"]')
            await h.ev("Nutcade.toast('Contact deleted','gold')"); await h.wait(200)
            miss = [m for m in await h.ev("JSON.parse(localStorage.getItem('qa:miss5')||'[]')") if not ALLOW.match(m.strip())]
            check(f'round 5 i18n {lang}: no English left on the main screens, sheets, toasts, game screens and aria labels', not miss, miss[:12])
            await h.pg.context.close()

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
        await d.ev("document.querySelector('[data-g=exit]').click()"); await d.wait(200)
        await d.click('[data-act=tab][data-tab=wallet]'); await d.wait(200)
        await d.pg.locator('[data-act=send]').focus(); await d.pg.keyboard.press('Enter'); await d.wait(300)
        inside = []
        for _ in range(16): await d.pg.keyboard.press('Tab'); inside.append(await d.ev("!!document.activeElement.closest('#layer .sheet')"))
        check('desktop: Tab stays inside an open sheet', all(inside), inside)
        await d.pg.fill('#amtIn', '21'); await d.pg.focus('#amtIn'); await d.pg.keyboard.press('Enter'); await d.until("!!document.querySelector('#layer .qr')", 8000)
        check('desktop: Enter in the amount field presses the main button', await d.ev("Nutcade.S.txs[0].amount") == 21)
        await d.pg.keyboard.press('Escape'); await d.wait(200)
        check('desktop: closing a sheet puts focus back on the button that opened it', await d.ev("document.activeElement && document.activeElement.dataset.act") == 'send')
        await d.click('[data-act=tab][data-tab=settings]'); await d.wait(150); await d.pg.locator('#app [data-act=seedRestore]').focus(); await d.pg.keyboard.press('Enter'); await d.wait(300); await d.pg.keyboard.press('Escape'); await d.wait(200)
        check('desktop: closing Restore wallet puts focus back on its button', await d.ev("document.activeElement && document.activeElement.dataset.act") == 'seedRestore')
        await d.click('[data-act=tab][data-tab=wallet]'); await d.wait(150)
        foc = {}
        for th in ['neon', 'amber', 'phosphor']:
            await d.ev(f"Nutcade.S.prefs.theme='{th}'; Nutcade.render()"); await d.click('[data-act=receive]'); await d.wait(200); await d.pg.focus('#amtIn')
            foc[th] = await d.ev("[getComputedStyle(document.querySelector('#amtIn')).boxShadow, getComputedStyle(document.querySelector('.sheet')).boxShadow]"); await d.ev("Nutcade.closeSheet()")
        check('themes: the focus ring and the sheet glow follow the theme', len({foc[t][0] for t in foc}) == 3 and len({foc[t][1] for t in foc}) == 3, foc)
        await d.ev("Nutcade.S.prefs.theme='neon'; Nutcade.render()")
        await d.pg.set_viewport_size({'width': 667, 'height': 375}); await d.click('[data-act=tab][data-tab=arcade]'); await d.wait(200)
        await d.ev("document.querySelector('[data-game=swarm]').click()"); await d.wait(400)
        g = await d.ev("(()=>{const c=document.querySelector('#gameCanvas').getBoundingClientRect(),k=document.querySelector('.pad-keys').getBoundingClientRect();return {c:Math.round(c.bottom),k:Math.round(k.top),kb:Math.round(k.bottom),H:innerHeight}})()")
        check('desktop: in a 667x375 window the key hints sit under the game, not on it', g['c'] <= g['k'] and g['kb'] <= g['H'], g)
        await d.pg.context.close()
        await b.close()
    n = len(results); ok = sum(1 for r in results if r[1])
    print(f'SUMMARY {ok}/{n} passed')

asyncio.run(main())
