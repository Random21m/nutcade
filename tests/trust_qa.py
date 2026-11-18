"""Trust & help (unreleased): the check of your 12 words and the backup file's age, "Updated to vX" and "new version ready",
Help & FAQ (offline, five languages, every claim checked against the app), a mint's contact, terms and description (NUT-06,
untrusted text), the Privacy section and its list of hosts, the listing text and manifest, and Hide amounts. None of it moves money.
Uses the local mints (3338 fee, 3339 no fee, 3341 stuck payments) and mock_nostr.py.

The grid: every item x with and without a PIN x the duress PIN's wallet x five languages x 320 px wide, portrait and landscape,
in all three themes (and 375/390 px); a hostile mint's text; a new version served, the same one, an older one, nothing, garbage;
a payment held in flight while a new version is waiting. T_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, A, B, P, URL, invoice, outside_net
from r8_qa import set_pin, unlock, pad, PIN, DPIN

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
THEMES = ['neon', 'amber', 'phosphor']
SRC = {n: open(os.path.join(ROOT, 'src', n), encoding='utf-8').read() for n in os.listdir(os.path.join(ROOT, 'src')) if n.endswith(('.js', '.html', '.css'))}
APP_VERSION = re.search(r"const APP_VERSION = '([\d.]+)'", SRC['app.js']).group(1)
J = json.dumps

SMALL_JS = """(()=>{const out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(!e.matches('button,a[href],select,input:not([type=hidden]),[data-act],summary,[role=button]'))continue;
  const s=getComputedStyle(e),r=e.getBoundingClientRect(); if(!r.width||!r.height||s.visibility==='hidden'||+s.opacity<0.05||e.closest('.sr,.tx,.dpad'))continue;
  const lab=e.closest('label'),rr=lab?lab.getBoundingClientRect():r; if(rr.width<40||rr.height<40)out.push((e.innerText||e.getAttribute('aria-label')||e.tagName).trim().slice(0,30)+' '+Math.round(rr.width)+'x'+Math.round(rr.height))}return out})()"""
TINY_JS = """(()=>{const out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(![...e.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim()))continue; const s=getComputedStyle(e),r=e.getBoundingClientRect();
  if(!r.width||e.closest('.sr,.code,.mono,.qr,canvas,svg,.kv dd.tiny,.words'))continue; const f=parseFloat(s.fontSize);
  if(/Press Start/.test(s.fontFamily)?f<9:/VT323/.test(s.fontFamily)&&f<16)out.push(e.innerText.trim().slice(0,30)+' '+f)}return out})()"""
OVER_JS = """(()=>{const W=document.documentElement.clientWidth,out=[];for(const e of document.querySelectorAll('#app *, #layer *')){
  if(!e.getClientRects().length||e.closest('.sr'))continue;const r=e.getBoundingClientRect();if(r.right>W+1||r.left<-1)out.push((e.className||e.tagName)+':'+Math.round(r.left)+'..'+Math.round(r.right))}
  if(document.documentElement.scrollWidth>W+1)out.push('page scrolls sideways '+document.documentElement.scrollWidth+'>'+W);return out.slice(0,4)})()"""


async def wallet(b, vw=375, vh=667, lang='en', mobile=True, prefs=None, ctx=None, init=None):
    """A fresh browser context (service workers blocked, so routes see every request) with the stand-in relays and downloads allowed."""
    if ctx is None:
        ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile, accept_downloads=True, service_workers='block')
        p0 = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
        p0.update(prefs or {})
        if init: await ctx.add_init_script(init)
        await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(p0)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'trust'); w.reqs = []; w.frames = []
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) else None)
    pg.on('request', lambda r: w.reqs.append((r.method, r.url, r.post_data or '')))
    pg.on('websocket', lambda ws: (w.reqs.append(('WS', ws.url, '')), ws.on('framesent', lambda f: w.frames.append(str(f)))))
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def funded(b, **kw):
    """A wallet with a no-fee mint holding 50,000 SAT and a second mint holding 1,000 SAT, and one note and a pending token."""
    w = await wallet(b, **kw)
    await w.create(); await w.add_mint(A); await w.receive_ln(1000, 'Spare #misc'); await w.add_mint(B); await w.receive_ln(50000, 'Paycheck #work'); await w.use(B)
    tok, e = await w.send_ecash(700, 'Lunch #food')
    await w.home(); await w.wait(200)
    return w


async def tab(w, name):
    await w.ev("Nutcade.closeSheet()"); await w.click(f'[data-act=tab][data-tab={name}]'); await w.wait(250)


async def lay(w, tag, small=True):
    """Overflow, tap targets and tiny text on whatever is showing; returns the problems (empty is good)."""
    bad = {}
    o = await w.ev(OVER_JS)
    if o: bad['over'] = o
    if small:
        s = await w.ev(SMALL_JS)
        if s: bad['small'] = s[:4]
    t = await w.ev(TINY_JS)
    if t: bad['tiny'] = t[:3]
    return bad


async def shot(w, name):
    try: await w.pg.screenshot(path=OUT + 'trust_' + name + '.png')
    except Exception: pass


async def section(name, fn):
    only = [x for x in os.environ.get('T_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e:
        check(f'{name}: ran to the end', False, repr(e)[:300])


def hosts_in(text):
    return {m.group(2).lower() for m in re.finditer(r"(https?|wss?)://([a-z0-9][a-z0-9.\-]*[a-z0-9])", text, re.I)}


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        os.makedirs(OUT, exist_ok=True)

        # ======================= files: listing text, manifest, SECURITY.md, README =======================
        async def files():
            html = open(os.path.join(ROOT, 'public', 'index.html'), encoding='utf-8').read()
            descs = re.findall(r'<meta (?:name|property)="(?:description|og:description|twitter:description)" content="([^"]*)"', html)
            check('listing: three descriptions, all say 10 retro arcade cabinets and none says 8', len(descs) == 3 and all('10 retro arcade cabinets' in d for d in descs) and '8 retro' not in html and '7 retro' not in html, descs)
            check('listing: the welcome screen says ten cabinets, not eight', "Ten cabinets of free play" in SRC['app.js'] and 'Eight cabinets' not in SRC['app.js'])
            readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
            check('listing: the README no longer says 8 original or 8 retro games anywhere', 'one of the 8 original' not in readme and '8 retro' not in readme and 'one of the 10 arcade cabinets' in readme)
            man = json.load(open(os.path.join(ROOT, 'public', 'manifest.webmanifest'), encoding='utf-8'))
            check('manifest: an id on the same path as the start URL (so installed apps keep their identity), a longer description, categories', man.get('id') == '/nutcade/' and man.get('start_url') == './' and man.get('scope') == './' and len(man.get('description', '')) > 80 and man.get('categories'), {k: man.get(k) for k in ('id', 'start_url', 'categories')})
            check('manifest: name, colours, display and the three icons are as they were', man['name'] == 'NUTCADE' and man['display'] == 'standalone' and man['background_color'] == '#0a0717' and [i['src'] for i in man['icons']] == ['icon-192.png', 'icon-512.png', 'icon-maskable-512.png'] and 'orientation' not in man)
            shots = man.get('screenshots') or []
            check('manifest: screenshots are listed, and every one is a real file in public/ of the size it says', len(shots) >= 4 and all(os.path.exists(os.path.join(ROOT, 'public', s['src'])) for s in shots), [s['src'] for s in shots])
            try:
                from PIL import Image
                ok = all(Image.open(os.path.join(ROOT, 'public', s['src'])).size == tuple(int(x) for x in s['sizes'].split('x')) and s['type'] == 'image/jpeg' for s in shots)
            except ImportError: ok = True
            check('manifest: each screenshot has the size and type it declares, and a label', ok and all(s.get('label') and s.get('form_factor') == 'wide' for s in shots))
            same = all(open(os.path.join(ROOT, 'public', s['src']), 'rb').read() == open(os.path.join(ROOT, 'docs', 'screens', os.path.basename(s['src'])), 'rb').read() for s in shots)
            check('manifest: the screenshots are the real ones from docs/screens (none made up)', same)
            w = await wallet(b)
            for s in shots[:2]:
                r = await w.ev(f"fetch({J(s['src'])}).then(r=>[r.status,r.headers.get('content-type')])")
                check(f"manifest: {s['src']} is served", r[0] == 200 and 'image' in r[1], r)
            await w.pg.context.close()
            sec = open(os.path.join(ROOT, 'SECURITY.md'), encoding='utf-8').read()
            check('SECURITY.md: GitHub private vulnerability reporting, with the direct link and the steps', 'github.com/Random21m/nutcade/security/advisories/new' in sec and 'private vulnerability reporting' in sec.lower() and 'Report a vulnerability' in sec)
            check('SECURITY.md: no invented email address, Nostr key or account', not re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', sec) and 'npub1' not in sec and 'nostr:' not in sec.lower(), re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', sec))
            check('SECURITY.md: still says never to put details in a public issue, and still promises a reply', "don't open a public issue" in sec and 'reply within a few days' in sec)
            check("README: the changelog entry is 'Unreleased: Trust & help' and the version number is untouched", '**Unreleased: Trust & help.**' in readme and f"const APP_VERSION = '{APP_VERSION}'" in SRC['app.js'] and re.search(r"APP_VERSION = '1\.14\.0'", SRC['app.js']))
            for h in ('Help & FAQ', 'Checking your 12 words', 'Mint details', 'Hiding amounts'):
                check(f'README: a section for "{h}"', f'### {h}' in readme)
            check('README: the Features list mentions each item', all(x in readme for x in ('**Help & FAQ**', '**Check your 12 words**', '**Updated to vX**', '**Mint details**', '**Hide amounts**')))
        await section('files', files)

        # ======================= privacy: every host the app contacts, checked against the code =======================
        async def privacy():
            code = '\n'.join(v for k, v in SRC.items() if k.endswith('.js') and not k.startswith(('lib.min', 'i18n')))
            found = hosts_in(code)
            # not contacted by the app, only named: the XML namespace, the example in a placeholder, links the person taps, the share link's own site
            named_only = {'www.w3.org', 'mint.example.com', 'mint.example', 'cashu.space', 'github.com', 'random21m.github.io'}
            contacted = found - named_only - {'localhost', '127.0.0.1'}
            claimed = {'mint.minibits.cash', 'mint.cubabitcoin.org', '8333.space', 'testnut.cashu.space', 'nofees.testnut.cashu.space',
                       'relay.damus.io', 'nos.lol', 'relay.primal.net', 'relay.nostr.band', 'relay.cashumints.space',
                       'api.coinbase.com', 'api.exchange.coinbase.com', 'ws-feed.exchange.coinbase.com', 'npub.cash'}
            check('privacy: every host the code names is in the Privacy section (nothing is contacted that it does not list)', contacted <= claimed, sorted(contacted - claimed))
            check('privacy: every host the Privacy section lists is really in the code', claimed <= contacted, sorted(claimed - contacted))
            check('privacy: strike.me (the tip address) is in the code', 'strike.me' in SRC['app.js'])
            readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
            priv = readme[readme.index('## Privacy'):readme.index('## Sharing')]
            curated = {'mint.minibits.cash': 'Minibits', 'mint.cubabitcoin.org': 'Cuba Bitcoin', 'testnut.cashu.space': 'test mints', 'nofees.testnut.cashu.space': 'test mints', '8333.space': '8333.space'}
            names = [(curated[h] if h in curated else h) for h in claimed | {'strike.me'}]
            check('privacy: the README Privacy section names every one of those hosts (the five listed mints by name)', all(n in priv for n in names), [n for n in names if n not in priv])
            helptext = SRC['app_trust.js']
            hs = helptext[helptext.index("What does NUTCADE contact"):helptext.index("Reporting a problem")]
            check('privacy: so does the Help answer (the hosts, in the same words)', all(h in hs for h in claimed - {'api.exchange.coinbase.com', 'ws-feed.exchange.coinbase.com', 'api.coinbase.com', 'mint.minibits.cash', 'mint.cubabitcoin.org', 'testnut.cashu.space', 'nofees.testnut.cashu.space'}) and 'Coinbase' in hs and 'Minibits' in hs and 'Cuba Bitcoin' in hs and '8333.space' in hs, hs[:60])
            check('privacy: no analytics, tracking or advertising code (no gtag, pixel, sentry, matomo, plausible)', not re.search(r'gtag|google-analytics|matomo|plausible|sentry|mixpanel|segment\.|fbq\(|hotjar', code, re.I))
            # every network call in the new code goes to this site's own files (the update check) or to a mint the person already uses
            tr = SRC['app_trust.js']
            calls = re.findall(r"fetch\(([^,)]+)", tr)
            check('privacy: the new code makes exactly two kinds of request: this site\'s own page and a mint\'s /v1/info', sorted(set(c.strip() for c in calls)) == ["'index.html'", "url + '/v1/info'"], calls)
            check('privacy: the new code opens no WebSocket and reads no cookie, and sends no body', 'WebSocket' not in tr and 'document.cookie' not in tr and not re.search(r"method:\s*['\"](POST|PUT|PATCH|DELETE)", tr) and not re.search(r"\bbody:\s", tr) and 'sendBeacon' not in tr and 'XMLHttpRequest' not in tr)
        await section('privacy', privacy)

        # ======================= hide amounts =======================
        async def hide():
            w = await funded(b)
            bal = await w.ev("Object.values(Nutcade.S.proofs[" + J(B) + "]||[]).reduce((t,p)=>t+p.amount,0)")
            real = await w.ev("[50000,5000,700].map(n=>Nutcade.fmt(n))")
            check('hide: off by default; the balance and the eye button are there', await w.ev("!!document.querySelector('.credit-num[data-act=hideToggle]') && document.querySelector('.lockbtn[data-act=hideToggle]').getAttribute('aria-pressed')==='false'") and Nutcade_txt(await w.ev("document.querySelector('.credit-num').innerText"), bal))
            await w.click('.credit-num'); await w.wait(250)
            txt = await w.ev("document.querySelector('.credits').innerText")
            check('hide: tapping the balance shows ••• and no digits in the balance block', '•••' in txt and not re.search(r'\d', txt.replace('Credits', '')), txt)
            check('hide: the fiat line, the "All mints" total and the in-flight amounts are hidden too', await w.ev("!document.querySelector('.credits .fiat')") and 'All mints ••• SAT' in txt.replace('\n', ' '), txt)
            check('hide: the eye button now says Show amounts and is pressed', await w.ev("(b=>b.getAttribute('aria-pressed')==='true' && /Show amounts/.test(b.getAttribute('aria-label')))(document.querySelector('.lockbtn[data-act=hideToggle]'))"))
            check('hide: it is remembered on this device (the preference is stored)', await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')).hideAmounts===true"))
            await tab(w, 'history'); h = await w.ev("document.querySelector('#txList').innerText")
            check('hide: notes: no amount shows (the notes still do)', '•••' in h and not any(re.search(r'(^|[^\d,.])' + re.escape(x) + r'([^\d]|$)', h) for x in real) and 'Lunch' in h, h[:160])
            await tab(w, 'mints'); m = await w.ev("document.querySelector('.screen').innerText")
            check('hide: mints: balances are hidden', '•••' in m and not any(re.search(r'(^|[^\d,.])' + re.escape(x) + r'([^\d]|$)', m) for x in real), m[:200])
            await tab(w, 'settings'); s = await w.ev("document.querySelector('.screen').innerText")
            check('hide: settings: the Hide amounts switch is on', await w.ev("document.querySelector('#p_hideAmounts').checked"))
            # sheets are never hidden: the real amount shows where you pay, and in a note's details
            await tab(w, 'wallet'); await w.click('[data-act=send]'); await w.wait(250)
            await w.fill('#amtIn', '1234'); v = await w.ev("document.querySelector('#amtIn').value")
            check('hide: the Send sheet shows what you type, and no ••• (you always see what you send)', v in ('1234', '1,234') and '•••' not in await w.sheet_text(), v)
            await w.ev("Nutcade.closeSheet()")
            await tab(w, 'history'); await w.click('#txList .tx'); await w.wait(250)
            det = await w.sheet_text()
            check('hide: a note\'s details sheet shows the real amount (it is not a main screen)', re.search(r'700|5,000|1,000|50,000', det) is not None and '•••' not in det, det[:120])
            await w.ev("Nutcade.closeSheet()")
            check('hide: fmt() is back to normal outside the screens (nothing is left masked)', await w.ev("Nutcade.fmt(1234567)") == '1,234,567')
            await tab(w, 'wallet')
            await w.ev("Nutcade.S.prefs.btcSymbol=true; Nutcade.render()")
            check('hide: with amounts as ₿ it reads ₿•••', await w.ev("document.querySelector('.credit-num').innerText.startsWith('₿•••')"), await w.ev("document.querySelector('.credit-num').innerText"))
            await w.ev("Nutcade.S.prefs.btcSymbol=false; Nutcade.render()")
            await w.pg.reload(); await w.wait(900)
            check('hide: still hidden after a reload', '•••' in await w.ev("document.querySelector('.credit-num').innerText"))
            await w.pg.keyboard.press('Tab')
            await w.click('.lockbtn[data-act=hideToggle]'); await w.wait(200)
            check('hide: the eye button shows them again, with no ••• left on the wallet screen', not re.search(r'•', await w.ev("document.querySelector('.screen').innerText")) and await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')).hideAmounts===false"))
            await tab(w, 'settings'); await w.click('#p_hideAmounts'); await w.wait(250); await tab(w, 'wallet')
            check('hide: the Settings switch hides them too', '•••' in await w.ev("document.querySelector('.credit-num').innerText"))
            await w.click('.credit-num'); await w.wait(200)
            check('hide: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
            # a PIN: the choice belongs to the device (plain storage), and survives lock and unlock
            w = await funded(b)
            await w.click('.credit-num'); await w.wait(200); await set_pin(w)
            ls = await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')||'{}')")
            check('hide, PIN set: the choice is a device setting (plain storage), as the theme is', ls.get('hideAmounts') is True, ls)
            await tab(w, 'wallet'); await w.click('[data-act=lockNow]'); await w.wait(400); await unlock(w)
            check('hide, PIN set: still hidden after locking and unlocking', '•••' in await w.ev("document.querySelector('.credit-num').innerText"))
            await w.pg.context.close()
        await section('hide', hide)

        async def hide_lang_and_layout():
            for lang in LANGS:
                w = await funded(b, lang=lang)
                await w.click('.credit-num'); await w.wait(300)
                t = await w.ev("document.querySelector('.credits').innerText")
                check(f'hide, {lang}: the wallet reads ••• and the "All mints" line is translated with it', '•••' in t and (lang == 'en' or 'All mints' not in t), t.replace('\n', ' | '))
                await tab(w, 'settings'); await w.wait(250)
                check(f'hide, {lang}: Settings (switch text, nothing missed in translation)', not await w.ev("[...window.__i18nMiss]"), await w.ev("[...window.__i18nMiss]"))
                await w.pg.context.close()
            for (vw, vh) in ((320, 640), (640, 320), (375, 667)):
                w = await funded(b, vw=vw, vh=vh)
                await w.click('.credit-num'); await w.wait(250)
                for tb in ('wallet', 'history', 'mints', 'settings'):
                    await tab(w, tb); l = await lay(w, tb)
                    check(f'hide, {vw}x{vh}: the {tb} screen with amounts hidden: no overflow, tap targets and text sizes fine', not l, l)
                await w.pg.context.close()
        await section('hide_layout', hide_lang_and_layout)

        # ======================= the check of your 12 words =======================
        async def phrase():
            w = await funded(b)
            words = (await w.ev("Nutcade.S.seed.mnemonic")).split()
            check('words: nothing is offered right after setup (a week after the backup is the first time)', not await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText)"))
            DAY = 86400000
            await w.ev(f"Nutcade.S.seed.created=Date.now()-{6 * DAY}; Nutcade.render()")
            check('words: still nothing at 6 days', not await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText)"))
            await w.ev(f"Nutcade.S.seed.created=Date.now()-{8 * DAY}; Nutcade.render()")
            check('words: at 8 days the wallet offers it, in a notice with Check now and Later', await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText) && !!document.querySelector('.notice [data-act=pwOpen]') && !!document.querySelector('.notice [data-act=pwLater]')"))
            w.reqs.clear(); w.frames.clear()
            await w.click('.notice [data-act=pwOpen]'); await w.wait(300)
            pick = await w.ev("[...document.querySelectorAll('#layer [data-pw]')].map(i=>+i.dataset.pw)")
            labels = await w.ev("[...document.querySelectorAll('#layer label')].map(l=>l.innerText)")
            check('words: three different words, by position, in order, each field empty', len(pick) == 3 and len(set(pick)) == 3 and pick == sorted(pick) and await w.ev("[...document.querySelectorAll('#layer [data-pw]')].every(i=>i.value==='')") and labels == [f'Word #{i + 1}' for i in pick], (pick, labels))
            st = await w.sheet_text()
            check('words: the sheet never shows any of your words, and says the check stays on this phone', not any(re.search(r'\b' + x + r'\b', st) for x in words if len(x) > 3) and 'on this phone only' in st, st[:200])
            check('words: the fields are not remembered or spell-checked (autocomplete, autocapitalize, spellcheck off)', await w.ev("[...document.querySelectorAll('#layer [data-pw]')].every(i=>i.autocomplete==='off' && i.getAttribute('autocapitalize')==='off' && i.spellcheck===false)"))
            await w.fill(f'[data-pw="{pick[0]}"]', 'zebra'); await w.fill(f'[data-pw="{pick[1]}"]', words[pick[1]]); await w.fill(f'[data-pw="{pick[2]}"]', words[pick[2]])
            await w.click('[data-act=pwCheck]'); await w.wait(250)
            err = await w.err()
            check('words: a wrong word says which one ("Word #n doesn\'t match") and nothing is recorded', f"Word #{pick[0] + 1} doesn't match" in err and await w.ev("!(Nutcade.S.prefs.phraseCheck&&Nutcade.S.prefs.phraseCheck.done)"), err)
            await w.fill(f'[data-pw="{pick[0]}"]', '  ' + words[pick[0]].upper() + '  '); await w.fill(f'[data-pw="{pick[1]}"]', words[pick[1]]); await w.fill(f'[data-pw="{pick[2]}"]', words[pick[2]])
            await w.click('[data-act=pwCheck]'); await w.wait(400)
            check('words: the right words (any case, extra spaces) pass; the sheet closes; a toast says so', not await w.ev("!!document.querySelector('#layer .sheet')") and 'check out' in await w.toast(), await w.toast())
            pc = await w.ev("Nutcade.S.prefs.phraseCheck")
            check('words: only when it was passed and when to ask next are kept (about six months on)', set(pc) == {'done', 'next'} and abs(pc['next'] - pc['done'] - 182 * DAY) < 5000 and abs(time.time() * 1000 - pc['done']) < 60000, pc)
            nets = [r for r in w.reqs if any(x in (r[1] + r[2]) for x in words)] + [f for f in w.frames if sum(1 for x in set(words) if re.search(r'\b' + x + r'\b', f)) >= 2]
            check('words: nothing was sent anywhere that holds your words (requests and socket frames while checking)', not nets, nets[:2])
            check('words: the notice is gone, and Settings says when they were last checked', not await w.ev("/Time to check/.test(document.querySelector('.screen').innerText)"))
            await tab(w, 'settings'); st = await w.ev("document.querySelector('#set-backup').innerText")
            check('words: Settings, Backup: "12 words last checked JUST NOW" and the button to do it again', re.search(r'12 words last checked\s*JUST NOW', st) is not None and await w.ev("!!document.querySelector('#set-backup [data-act=pwOpen]')"), st[:160])
            await w.ev(f"Nutcade.S.seed.created=Date.now()-{400 * DAY}; Nutcade.render()")
            check('words: after a pass it does not ask again for a long while (even for an old wallet)', not await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText)"))
            await w.ev(f"Nutcade.S.prefs.phraseCheck.next=Date.now()-1000; Nutcade.render()"); await tab(w, 'wallet')
            check('words: and asks again once the six months are up', await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText)"))
            await w.click('.notice [data-act=pwLater]'); await w.wait(250)
            pc = await w.ev("Nutcade.S.prefs.phraseCheck")
            check('words: Later asks again in a week, not sooner', abs(pc['next'] - time.time() * 1000 - 7 * DAY) < 60000 and not await w.ev("/Time to check/.test(document.querySelector('.screen').innerText)"), pc)
            await w.ev(f"Nutcade.S.prefs.phraseCheck.next=Date.now()-1; Nutcade.render()")
            await w.click('.notice [data-act=pwOpen]'); await w.wait(250); await w.click('[data-act=pwOff]'); await w.wait(250)
            check('words: "Don\'t remind me again" turns the reminder off for good', await w.ev("Nutcade.S.prefs.phraseCheck.off===true") and not await w.ev("/Time to check/.test(document.querySelector('.screen').innerText)"))
            await w.ev(f"Nutcade.S.prefs.phraseCheck.next=1; Nutcade.S.seed.created=1; Nutcade.render()")
            check('words: ...also a year later', not await w.ev("/Time to check/.test(document.querySelector('.screen').innerText)"))
            await tab(w, 'settings'); await w.click('#set-backup [data-act=pwOpen]'); await w.wait(250)
            check('words: the check stays available in Settings, Backup', await w.ev("document.querySelectorAll('#layer [data-pw]').length")==3)
            await w.click('[data-act=pwLater]'); await w.wait(150)
            await w.click('#set-backup [data-act=pwOpen]'); await w.wait(250)
            ws = await w.ev("[...document.querySelectorAll('#layer [data-pw]')].map(i=>+i.dataset.pw)")
            for i in ws: await w.fill(f'[data-pw="{i}"]', words[i])
            await w.click('[data-act=pwCheck]'); await w.wait(300)
            check('words: a manual pass works with the reminder off (and records the date)', await w.ev("!!Nutcade.S.prefs.phraseCheck.done"))
            check('words: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('words', phrase)

        async def words_storage():
            # backup file age, and where the new settings live with and without a PIN
            w = await funded(b)
            await tab(w, 'settings'); t = await w.ev("document.querySelector('#set-backup').innerText")
            check('backup age: before any file: "Last backup file NEVER" and a line saying what a file holds', re.search(r'Last backup file\s*NEVER', t) and 'only holds what your wallet held on the day you made it' in t, t[:300])
            async with w.pg.expect_download() as dl:
                await w.click('[data-act=backupDownload]')
            await dl.value; await w.wait(400)
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check('backup age: after Download backup it says JUST NOW', re.search(r'Last backup file\s*JUST NOW', t) is not None, t[:300])
            at = await w.ev("Nutcade.S.prefs.backupFileAt")
            check('backup age: the date is stored (and survives a reload)', abs(at - time.time() * 1000) < 60000)
            await w.ev(f"Nutcade.S.prefs.backupFileAt=Date.now()-{3 * 86400000}; Nutcade.render()")
            check('backup age: three days later it reads 3D AGO', re.search(r'Last backup file\s*3D AGO', await w.ev("document.querySelector('#set-backup').innerText")) is not None)
            await w.ev(f"Nutcade.S.prefs.backupFileAt=Date.now()-{40 * 86400000}; Nutcade.render()")
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check('backup age: after a long time it shows the date, not a made-up age', not re.search(r'Last backup file\s*(NEVER|JUST NOW)', t) and re.search(r'Last backup file\s*\w{3} \d', t) is not None, t[:200])
            check('backup age: the file itself is as before (no new fields in the backup)', 'backupFileAt' not in SRC['app.js'][SRC['app.js'].index('const backupData'):SRC['app.js'].index('const backupData') + 1500])
            await w.pg.context.close()
            # a PIN: wallet settings go in the vault, device settings stay out
            w = await funded(b)
            await tab(w, 'settings')
            async with w.pg.expect_download() as dl:
                await w.click('[data-act=backupDownload]')
            await dl.value
            await w.ev("Nutcade.S.seed.created=Date.now()-8*86400000; Nutcade.render()"); await set_pin(w)
            await tab(w, 'wallet'); await w.ev("Nutcade.S.prefs.seenVersion='0.1.0'"); await w.click('.credit-num'); await w.wait(300)
            ls = await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')||'{}')")
            check('PIN set: backupFileAt and phraseCheck are inside the vault, not in plain storage (they belong to the wallet)', 'backupFileAt' not in ls and 'phraseCheck' not in ls, ls)
            check('PIN set: hideAmounts and seenVersion stay in plain storage (they belong to the device)', ls.get('hideAmounts') is True and ls.get('seenVersion') == '0.1.0', ls)
            await w.ev("Nutcade.render()"); await tab(w, 'wallet'); await w.click('[data-act=pwOpen]'); await w.wait(250)
            ws = await w.ev("[...document.querySelectorAll('#layer [data-pw]')].map(i=>+i.dataset.pw)"); words = (await w.ev("Nutcade.S.seed.mnemonic")).split()
            for i in ws: await w.fill(f'[data-pw="{i}"]', words[i])
            await w.click('[data-act=pwCheck]'); await w.wait(500)
            await w.click('[data-act=lockNow]'); await w.wait(500)
            ls = await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')||'{}')")
            check('PIN set, locked: still no phraseCheck or backupFileAt in plain storage after passing the check', 'backupFileAt' not in ls and 'phraseCheck' not in ls, ls)
            check('PIN set, locked: nothing about the wallet appears on the lock screen', not await w.ev("/12 words|backup file|Time to check/i.test(document.body.innerText)"))
            await unlock(w); await tab(w, 'settings')
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check('PIN set, unlocked: both are back (the check date and the backup file age)', re.search(r'12 words last checked\s*JUST NOW', t) and re.search(r'Last backup file\s*\w', t) and 'NEVER' not in t.split('Last backup file')[1][:20], t[:200])
            await w.pg.context.close()
        await section('words_storage', words_storage)

        async def words_duress():
            w = await funded(b)
            await set_pin(w)
            await w.ev("Nutcade.S.prefs.phraseCheck={done:Date.now()-5000,next:Date.now()+999999999}; Nutcade.S.prefs.backupFileAt=Date.now()-60000")
            await tab(w, 'settings'); await w.click('[data-act=duressOpen]'); await w.wait(250)
            await pad(w, PIN, '#layer [data-pinpad]'); await w.wait(400)
            await pad(w, DPIN); await w.wait(300); await pad(w, DPIN); await w.until("!!document.querySelector('#duressAmt')", 8000)
            await w.fill('#duressAmt', '300'); await w.click('[data-act=duressMake]'); await w.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await w.ev("Nutcade.closeSheet()")
            await tab(w, 'wallet'); await w.click('[data-act=lockNow]'); await w.wait(500)
            await unlock(w, DPIN); await tab(w, 'settings')
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check("duress wallet: it has its own history, not the real wallet's (12 words never checked, no backup file)", re.search(r'12 words last checked\s*NEVER', t) and re.search(r'Last backup file\s*NEVER', t), t[:200])
            await w.ev("Nutcade.S.seed.created=Date.now()-9*86400000; Nutcade.render()"); await tab(w, 'wallet')
            check('duress wallet: it gets the same reminder, for its own words', await w.ev("/Time to check your 12 words/.test(document.querySelector('.screen').innerText)"))
            await w.click('.notice [data-act=pwOpen]'); await w.wait(250)
            ws = await w.ev("[...document.querySelectorAll('#layer [data-pw]')].map(i=>+i.dataset.pw)"); dwords = (await w.ev("Nutcade.S.seed.mnemonic")).split()
            for i in ws: await w.fill(f'[data-pw="{i}"]', dwords[i])
            await w.click('[data-act=pwCheck]'); await w.wait(400)
            check("duress wallet: its own words pass", await w.ev("!!Nutcade.S.prefs.phraseCheck.done") and 'check out' in await w.toast())
            await w.click('[data-act=lockNow]'); await w.wait(500); await unlock(w, PIN); await tab(w, 'settings')
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check("real wallet again: its own dates are untouched by the duress wallet's check", re.search(r'12 words last checked\s*JUST NOW', t) and re.search(r'Last backup file\s*1M AGO|Last backup file\s*JUST NOW', t), t[:200])
            check('no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('words_duress', words_duress)

        async def words_lang_layout():
            for lang in LANGS:
                w = await funded(b, lang=lang)
                await w.ev("Nutcade.S.seed.created=Date.now()-9*86400000; Nutcade.render()"); await w.wait(200)
                await w.ev("window.__i18nMiss=new Set()"); await w.ev("Nutcade.render()"); await w.wait(300)
                n = await w.ev("document.querySelector('.notice [data-act=pwOpen]').closest('.notice').innerText")
                await w.click('.notice [data-act=pwOpen]'); await w.wait(300)
                await w.fill('#layer [data-pw]', 'zebra'); await w.click('[data-act=pwCheck]'); await w.wait(300)
                sheet = await w.sheet_text()
                await w.ev("Nutcade.closeSheet()"); await tab(w, 'settings'); await w.wait(250)
                miss = await w.ev("[...window.__i18nMiss]")
                check(f'words, {lang}: the notice, the sheet, the error and the Backup rows are fully translated', not miss and (lang == 'en' or 'Time to check' not in n and 'Type these words' not in sheet and "doesn't match" not in sheet), miss or n[:80])
                await w.pg.context.close()
            for th in THEMES:
                for (vw, vh) in ((320, 640), (640, 320)):
                    w = await funded(b, vw=vw, vh=vh)
                    await w.ev(f"Nutcade.S.prefs.theme={J(th)}; Nutcade.S.seed.created=Date.now()-9*86400000; Nutcade.S.prefs.seenVersion='0.1.0'; Nutcade.render()"); await w.wait(200)
                    l = await lay(w, 'wallet'); check(f'words, {th} {vw}x{vh}: the wallet with the reminder and the update note fits', not l, l)
                    await shot(w, f'words_wallet_{th}_{vw}x{vh}')
                    await w.click('.notice [data-act=pwOpen]'); await w.wait(250)
                    l = await lay(w, 'quiz'); check(f'words, {th} {vw}x{vh}: the check sheet fits (fields, buttons, links)', not l, l)
                    await w.fill('#layer [data-pw]', 'zebra'); await w.click('[data-act=pwCheck]'); await w.wait(250)
                    l = await lay(w, 'quiz err'); check(f'words, {th} {vw}x{vh}: and with the error showing', not l, l)
                    if th == 'neon': await shot(w, f'words_quiz_{vw}x{vh}')
                    await w.ev("Nutcade.closeSheet()"); await tab(w, 'settings'); await w.click('[data-act=jump][data-id=set-backup]'); await w.wait(250)
                    l = await lay(w, 'backup'); check(f'words, {th} {vw}x{vh}: Settings, Backup fits', not l, l)
                    if th == 'neon': await shot(w, f'words_backup_{vw}x{vh}')
                    await w.pg.context.close()
        await section('words_layout', words_lang_layout)

        # ======================= updated to vX / new version ready =======================
        async def updates():
            w = await wallet(b)
            check('updated: a brand-new install is not told about an update (the version is just noted)', await w.ev("Nutcade.S.prefs.seenVersion") == APP_VERSION)
            await w.create(); await w.wait(300)
            check('updated: ... and still none once the wallet exists', not await w.ev("/Updated to v/.test(document.body.innerText)") and await w.ev("Nutcade.S.prefs.seenVersion") == APP_VERSION)
            await w.pg.context.close()
            # an existing wallet meeting this feature for the first time (no seenVersion yet), then one that last saw an older version
            w = await funded(b)
            for label, setv in (('first time (nothing noted yet)', 'delete p.seenVersion'), ('an older version noted', "p.seenVersion='0.9.0'")):
                await w.ev(f"(()=>{{const p=JSON.parse(localStorage.getItem('nutcade:prefs')); {setv}; localStorage.setItem('nutcade:prefs',JSON.stringify(p))}})()")
                await w.pg.reload(); await w.wait(900)
                txt = await w.ev("document.querySelector('.screen').innerText")
                check(f'updated, {label}: one note "Updated to v{APP_VERSION}" with What\'s new', f'Updated to v{APP_VERSION}' in txt and await w.ev("!!document.querySelector('.notice [data-act=whatsNew]')"), txt[:120])
                w.reqs.clear()
                await w.click('.notice [data-act=whatsNew]'); await w.wait(300)
                st = await w.sheet_text()
                links = await w.ev("[...document.querySelectorAll('#layer a')].map(a=>({h:a.getAttribute('href'),t:a.target,r:a.rel}))")
                check(f'updated, {label}: the sheet lists what is new and links to the release page and the signed checksums', "What's new in v" + APP_VERSION in await w.ev("document.querySelector('#layer h3').innerText") and st.count('\n') >= 6 and any(l['h'] == f'https://github.com/Random21m/nutcade/releases/tag/v{APP_VERSION}' for l in links) and any(l['h'] == 'SHA256SUMS.txt' for l in links), (links, st[:100]))
                check(f'updated, {label}: external links open in a new tab with rel=noopener', all(l['t'] == '_blank' and 'noopener' in l['r'] for l in links), links)
                check(f'updated, {label}: opening it contacts nobody for it (no GitHub or other new host; the links wait for a tap)', not [r for r in w.reqs if 'github' in r[1] or 'SHA256' in r[1] or 'releases' in r[1]], [r[1] for r in w.reqs][:3])
                check(f'updated, {label}: it is marked as seen, and the note is gone', await w.ev(f"JSON.parse(localStorage.getItem('nutcade:prefs')).seenVersion==={J(APP_VERSION)}") and not await w.ev("/Updated to v/.test(document.querySelector('.screen').innerText)"))
                await w.ev("Nutcade.closeSheet()")
                await w.pg.reload(); await w.wait(900)
                check(f'updated, {label}: and does not come back after a reload', not await w.ev("/Updated to v/.test(document.body.innerText)"))
            await w.ev("(()=>{const p=JSON.parse(localStorage.getItem('nutcade:prefs')); p.seenVersion='0.9.0'; localStorage.setItem('nutcade:prefs',JSON.stringify(p))})()")
            await w.pg.reload(); await w.wait(900)
            await w.click('.notice [data-act=whatsNewDone]'); await w.wait(250)
            check('updated: OK on the note marks it seen without opening anything', not await w.ev("/Updated to v/.test(document.querySelector('.screen').innerText)") and await w.ev(f"JSON.parse(localStorage.getItem('nutcade:prefs')).seenVersion==={J(APP_VERSION)}"))
            await tab(w, 'settings'); await w.click('#set-about [data-act=whatsNew]'); await w.wait(250)
            check('updated: Settings, About can open What\'s new again any time', "What's new in v" in await w.ev("document.querySelector('#layer h3').innerText"))
            check('updated: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('updated', updates)

        async def newver():
            w = await funded(b)
            state = {'mode': 'newer'}
            async def handler(route):
                if route.request.resource_type not in ('fetch', 'xhr'): return await route.continue_()
                m = state['mode']
                if m == 'down': return await route.abort()
                r = await route.fetch(); body = await r.text()
                if m == 'newer': body = body.replace(f"const APP_VERSION = '{APP_VERSION}'", "const APP_VERSION = '9.9.9'")
                elif m == 'older': body = body.replace(f"const APP_VERSION = '{APP_VERSION}'", "const APP_VERSION = '0.0.1'")
                elif m == 'garbage': body = '<html>nothing here</html>'
                elif m == 'http500': return await route.fulfill(status=500, body='boom')
                await route.fulfill(response=r, body=body)
            await w.pg.context.route('**/index.html', handler)
            await tab(w, 'settings')
            async def check_btn():
                w.reqs.clear(); await w.click('[data-act=verCheck]'); await w.wait(1500)
                return await w.toast()
            for mode, want in (('same', 'newest'), ('older', 'newest'), ('down', "Couldn't check"), ('garbage', "Couldn't check"), ('http500', "Couldn't check")):
                state['mode'] = mode; t = await check_btn()
                check(f'new version, {mode}: the button says so ("{want}") and no chip appears', want in t and not await w.ev("/New version v/.test(document.body.innerText)"), t)
            check('new version: the only requests were this site\'s own page (no other host, no other path)', all(r[1].startswith(URL.rsplit('/', 1)[0]) and r[1].endswith('index.html') for r in w.reqs if r[0] == 'GET' and 'index' in r[1]) and not [r for r in w.reqs if not r[1].startswith(URL.rsplit('/', 1)[0])], [r[:2] for r in w.reqs][:4])
            check('new version: it sends nothing (a GET, no body, no cookies, no query)', all(r[0] == 'GET' and not r[2] and '?' not in r[1] for r in w.reqs if 'index.html' in r[1]), [r[:2] for r in w.reqs][:3])
            state['mode'] = 'newer'; t = await check_btn()
            check('new version, newer: the button says so and a notice names it', 'v9.9.9' in t and await w.ev("/New version v9.9.9 is ready/.test(document.querySelector('#set-about').innerText)"), t)
            await tab(w, 'wallet')
            check('new version, newer: the wallet screen shows "New version v9.9.9 is ready. Reload when you\'re done." with Reload now', await w.ev("/New version v9.9.9 is ready. Reload when you're done./.test(document.querySelector('.screen').innerText) && !!document.querySelector('.notice [data-act=reloadNow]')"))
            # a sheet open (a Send screen with something typed in): the offer goes away, and a tap does nothing
            await w.click('[data-act=send]'); await w.wait(250); await w.fill('#amtIn', '10')
            await w.ev("window.__mark=1; Nutcade.render()")
            check('new version: with a Send sheet open there is no reload offer on the wallet screen', not await w.ev("document.querySelector('.screen').innerText.includes('New version v')"))
            await w.ev("(()=>{const b=document.createElement('button');b.dataset.act='reloadNow';b.id='fakeReload';document.body.appendChild(b);b.click()})()"); await w.wait(600)
            check('new version: a reload requested while a sheet is open is refused with a message, and the page stays', await w.ev("window.__mark===1") and 'first' in await w.toast(), await w.toast())
            await w.ev("document.querySelector('#fakeReload').remove(); Nutcade.closeSheet()")
            # a real payment in flight: the stuck-payment mint keeps it pending
            await w.add_mint(P); await w.receive_ln(1000); pre = await w.bal(P)
            e, txt = await w.pay_ln(invoice(200), 'stuck')
            await w.home(); await w.ev("Nutcade.render()"); await w.wait(300)
            inflight = await w.ev("Nutcade.S.pending.length")
            check('new version: a payment that is pending at the mint is open work (setup of this check)', inflight >= 1, (inflight, e))
            check('new version: ...so no reload is offered while it is in flight', inflight >= 1 and not await w.ev("document.querySelector('.screen').innerText.includes('New version v')"))
            await w.ev("(()=>{const b=document.createElement('button');b.dataset.act='reloadNow';b.id='fakeReload';document.body.appendChild(b);b.click()})()"); await w.wait(600)
            check('new version: and a tap on Reload during it does nothing but explain', await w.ev("window.__mark===1") and 'first' in await w.toast())
            await w.ev("document.querySelector('#fakeReload').remove(); Nutcade.S.pending=[]; Nutcade.render()"); await w.wait(300)
            check('new version: once nothing is open the offer is there again', await w.ev("document.querySelector('.screen').innerText.includes('New version v9.9.9')"))
            await w.click('.notice [data-act=reloadNow]'); await w.wait(1500)
            check('new version: tapping Reload now reloads the page', await w.ev("window.__mark===undefined"))
            check('new version: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('newver', newver)

        async def newver_flight():
            # a payment held in flight at the mint's door (the request is on its way, no sheet is open): the page must not offer a reload
            w = await funded(b)
            state = {'mode': 'newer'}
            async def handler(route):
                if route.request.resource_type not in ('fetch', 'xhr'): return await route.continue_()
                r = await route.fetch(); body = (await r.text()).replace(f"const APP_VERSION = '{APP_VERSION}'", "const APP_VERSION = '9.9.9'")
                await route.fulfill(response=r, body=body)
            await w.pg.context.route('**/index.html', handler)
            gate = asyncio.Event(); hit = []
            async def melt(route):
                hit.append(1); await gate.wait(); await route.continue_()
            await w.pg.context.route('**/v1/melt/bolt11', melt)
            await w.pg.context.route('**/v1/swap', lambda r: r.continue_())
            await tab(w, 'settings'); await w.click('[data-act=verCheck]'); await w.wait(1200)
            await w.home(); await w.wait(200)
            check('in flight: before the payment, the offer is there', await w.ev("document.querySelector('.screen').innerText.includes('New version v9.9.9')"))
            inv = invoice(300, A)
            await w.click('[data-act=send]'); await w.wait(200); await w.click('[data-act=sendMethod][data-m=ln]'); await w.wait(100)
            await w.fill('#destIn', inv); await w.click('[data-act=doMeltQuote]'); await w.wait(1500)
            await w.ev("(()=>{const b=document.querySelector('#payBtn'); b.click()})()"); await w.wait(1200)
            await w.ev("window.__mark=1; Nutcade.closeSheet(); Nutcade.render()"); await w.wait(300)
            open_ = await w.ev("Nutcade.S.ops.length+Nutcade.S.pending.length")
            check('in flight: the melt request is held at the mint (setup of this check)', len(hit) >= 1, hit)
            check('in flight: with the payment on its way (no sheet open) the reload offer is hidden', not await w.ev("document.querySelector('.screen').innerText.includes('New version v')"), open_)
            await w.ev("(()=>{const b=document.createElement('button');b.dataset.act='reloadNow';b.id='fakeReload';document.body.appendChild(b);b.click()})()"); await w.wait(600)
            check('in flight: tapping Reload then does nothing but explain', await w.ev("window.__mark===1") and 'first' in await w.toast(), await w.toast())
            gate.set(); await w.until("Nutcade.S.ops.length===0 && Nutcade.S.pending.length===0", 40000); await w.wait(800)
            await w.ev("Nutcade.closeSheet(); Nutcade.render()"); await w.wait(300)
            check('in flight: once the payment has settled the offer returns', await w.ev("document.querySelector('.screen').innerText.includes('New version v9.9.9')"))
            check('in flight: no page errors', not [e for e in w.errs if 'PAGEERROR' in e], w.errs[:3])
            await w.pg.context.close()
        await section('newver_flight', newver_flight)

        async def updates_lang_layout():
            for lang in LANGS:
                w = await funded(b, lang=lang)
                async def handler(route):
                    if route.request.resource_type not in ('fetch', 'xhr'): return await route.continue_()
                    r = await route.fetch(); body = (await r.text()).replace(f"const APP_VERSION = '{APP_VERSION}'", "const APP_VERSION = '9.9.9'")
                    await route.fulfill(response=r, body=body)
                await w.pg.context.route('**/index.html', handler)
                await w.ev("Nutcade.S.prefs.seenVersion='0.1.0'; Nutcade.render()")
                await tab(w, 'settings'); await w.click('[data-act=verCheck]'); await w.wait(1500)
                await tab(w, 'wallet'); await w.ev("window.__i18nMiss=new Set(); Nutcade.render()"); await w.wait(300)
                t = await w.ev("document.querySelector('.screen').innerText")
                await w.click('.notice [data-act=whatsNew]'); await w.wait(300)
                st = await w.sheet_text()
                await w.ev("Nutcade.closeSheet()"); await tab(w, 'settings'); await w.wait(200)
                miss = await w.ev("[...window.__i18nMiss]")
                check(f'updates, {lang}: the notes, the What\'s new sheet and the About rows are fully translated', not miss and (lang == 'en' or ('Updated to' not in t and 'is ready' not in t and 'Release page' not in st)), miss or t[:100])
                await w.pg.context.close()
            for th in THEMES:
                for (vw, vh) in ((320, 640), (640, 320)):
                    w = await funded(b, vw=vw, vh=vh)
                    async def handler(route):
                        if route.request.resource_type not in ('fetch', 'xhr'): return await route.continue_()
                        r = await route.fetch(); body = (await r.text()).replace(f"const APP_VERSION = '{APP_VERSION}'", "const APP_VERSION = '9.9.9'")
                        await route.fulfill(response=r, body=body)
                    await w.pg.context.route('**/index.html', handler)
                    await w.ev(f"Nutcade.S.prefs.theme={J(th)}; Nutcade.S.prefs.seenVersion='0.1.0'; Nutcade.render()")
                    await tab(w, 'settings'); await w.click('[data-act=verCheck]'); await w.wait(1500); await w.click('[data-act=jump][data-id=set-about]'); await w.wait(250)
                    l = await lay(w, 'about'); check(f'updates, {th} {vw}x{vh}: Settings, About (with the new-version notice and buttons) fits', not l, l)
                    if th == 'amber': await shot(w, f'about_{vw}x{vh}')
                    await w.click('#set-about [data-act=whatsNew]'); await w.wait(250)
                    l = await lay(w, 'whatsnew'); check(f'updates, {th} {vw}x{vh}: the What\'s new sheet fits', not l, l)
                    if th == 'phosphor': await shot(w, f'whatsnew_{vw}x{vh}')
                    await w.ev("Nutcade.closeSheet()"); await tab(w, 'wallet'); await w.wait(150)
                    l = await lay(w, 'wallet'); check(f'updates, {th} {vw}x{vh}: the wallet with both notes fits', not l, l)
                    await w.pg.context.close()
        await section('updates_layout', updates_lang_layout)

        # ======================= Help & FAQ =======================
        async def helpsheet():
            w = await funded(b)
            await tab(w, 'settings')
            check('help: Settings has a Help chip in its index and a Help panel', await w.ev("!![...document.querySelectorAll('.set-index button')].find(b=>b.dataset.id==='set-help') && !!document.querySelector('#set-help [data-act=helpOpen]')"))
            await w.pg.context.set_offline(True)
            w.reqs.clear(); await w.click('#set-help [data-act=helpOpen]'); await w.wait(400)
            topics = await w.ev("[...document.querySelectorAll('#layer details summary')].map(s=>s.innerText)")
            check('help: it opens with no connection (offline) and lists the topics as folds', len(topics) >= 14, len(topics))
            check('help: opening it made no request at all', not [r for r in w.reqs if r[1].startswith('http')], w.reqs[:3])
            await w.ev("document.querySelectorAll('#layer details').forEach(d=>d.open=true)")
            txt = await w.sheet_text()
            for t in ('What is NUTCADE?', 'What are ecash and a mint?', 'What if a mint closes or stops working?', 'What are my 12 words?', 'I have a new phone, or I lost mine', 'A payment looks stuck', "Why isn't ecash mine until it is claimed?", 'What do fees cost?', 'What do the PIN and the duress PIN do?', 'Can I use it offline?', 'How do updates work?', 'What does NUTCADE contact? (Privacy)', 'Reporting a problem'):
                check(f'help: the topic "{t}" is there', t in topics, topics)
            check('help: "undefined", "[object" and raw markup never show', not re.search(r'undefined|\[object|&amp;|<\w', txt))
            links = await w.ev("[...document.querySelectorAll('#layer a')].map(a=>({h:a.href,t:a.target,r:a.rel}))")
            check('help: the two report links go to GitHub (the public form and the private security report) and open safely', {l['h'] for l in links} == {'https://github.com/Random21m/nutcade/issues/new?template=bug.yml', 'https://github.com/Random21m/nutcade/security/advisories/new'} and all(l['t'] == '_blank' and 'noopener' in l['r'] for l in links), links)
            check('help: in plain words: no sentence is longer than 60 words, and no jargon like NUT-xx, DLEQ, keyset, BOLT or P2PK', all(len(s.split()) <= 60 for s in re.split(r'(?<=[.!?]) ', txt.replace('\n', ' '))) and not re.search(r'NUT-\d|DLEQ|keyset|BOLT|P2PK|PBKDF', txt), [s for s in re.split(r'(?<=[.!?]) ', txt.replace('\n', ' ')) if len(s.split()) > 60][:1])
            check('help: the first-scan rule for printed tokens is not claimed (that feature is not in this build)', not re.search(r'\bprint(ed|s)?\b', txt, re.I) and not any(x in SRC['app.js'] for x in ('app_tokens', 'printTokens')))
            await w.pg.context.set_offline(False)
            # the hook: another feature can add a topic
            await w.ev("Nutcade.closeSheet(); (window.NutHelpTopics=window.NutHelpTopics||[]).push({q:'A later topic',a:['Added by a later feature.']})"); await tab(w, 'settings'); await w.click('#set-help [data-act=helpOpen]'); await w.wait(300)
            check('help: a topic pushed to window.NutHelpTopics shows up (the hook for the printed tokens\' first-scan rule)', 'A later topic' in await w.ev("[...document.querySelectorAll('#layer details summary')].map(s=>s.innerText)"))
            await w.ev("window.NutHelpTopics=[]; Nutcade.closeSheet()")
            check('help: no page errors', not w.errs, w.errs[:3])
            await w.pg.context.close()
        await section('help', helpsheet)

        async def help_claims():
            """Everything the help tells the person to tap or look for exists in the app, under that name."""
            w = await funded(b)
            ui = {}
            await tab(w, 'settings'); ui['settings'] = await w.ev("document.querySelector('.screen').innerText")
            await w.click('[data-act=sweepOpen]'); await w.wait(200); await w.ev("Nutcade.closeSheet()")
            await w.click('[data-act=seedRestore]'); await w.wait(300); ui['restore'] = await w.sheet_text(); await w.ev("Nutcade.closeSheet()")
            await tab(w, 'wallet'); await w.click('[data-act=pickMint]'); await w.wait(600); ui['picker'] = await w.sheet_text(); await w.ev("Nutcade.closeSheet()")
            await tab(w, 'mints'); ui['mints'] = await w.ev("document.querySelector('.screen').innerText"); ui['tabs'] = await w.ev("document.querySelector('.tabbar').innerText")
            await tab(w, 'history'); await w.click('#txList .tx:not(.done)') if await w.ev("!!document.querySelector('#txList .tx')") else None
            await w.ev("Nutcade.closeSheet()")
            pend = await w.ev("Nutcade.S.txs.findIndex(t=>t.status==='pending'&&t.method==='ecash'&&t.token)")
            await w.ev(f"document.querySelectorAll('#txList .tx')[{pend}].click()"); await w.wait(300); ui['pending tx'] = await w.sheet_text(); await w.ev("Nutcade.closeSheet()")
            await w.pg.context.close()
            g = await wallet(b); ui['welcome'] = await g.ev("document.body.innerText"); await g.pg.context.close()
            need = [('settings', 'Check stuck payments'), ('settings', 'Find lost ecash'), ('settings', 'Move sats between mints'), ('settings', 'Import backup'), ('settings', 'Check my 12 words'), ('settings', 'Show Bitcoin price'),
                    ('settings', 'Wallet tools'), ('settings', 'Backup'), ('settings', 'Hide amounts'), ('settings', 'Help & FAQ'), ('welcome', 'Restore from recovery phrase'), ('restore', 'Find my mints on Nostr'),
                    ('picker', 'Find mints people recommend'), ('picker', 'Minibits'), ('picker', 'Cuba Bitcoin'), ('picker', '8333.space'), ('picker', 'Testnut'), ('pending tx', 'Reclaim'), ('tabs', 'MINTS')]
            for where, label in need:
                check(f'help claims: "{label}" exists in the app ({where}), as the help says', label.lower() in ui[where].lower() or label.upper() in ui[where], ui[where][:60])
            check('help claims: the Mints tab has a report-card grade, as the help says', 'GRADE' in ui['mints'], ui['mints'][:100])
            check('help claims: two test mints and three others in the Add mint list, as the Privacy answer says', sum(1 for c in re.findall(r"\{ url: '([^']+)'[^}]*?(test: true)?\s*\}", SRC['app.js'][SRC['app.js'].index('const CURATED'):SRC['app.js'].index('const RELAYS')])) == 5 and SRC['app.js'][SRC['app.js'].index('const CURATED'):SRC['app.js'].index('const RELAYS')].count('test: true') == 2)
            check('help claims: relays the Help names are the ones in the code (3 default + 2 for finding mints)', all(x in SRC['app.js'] for x in ("'wss://relay.damus.io', 'wss://nos.lol', 'wss://relay.primal.net'", "'wss://relay.nostr.band', 'wss://relay.cashumints.space'")))
            check('help claims: the app really has a PIN-less restore, a duress PIN, Face ID, offline use and a spending limit (what the help mentions)', all(x in SRC['app.js'] + SRC['app_r8.js'] for x in ('gateRestore', 'duressOpen', 'bioStart', 'limOpen')) and 'serviceWorker' in SRC['app.js'])
        await section('help_claims', help_claims)

        async def help_lang_layout():
            for lang in LANGS:
                w = await funded(b, lang=lang)
                await tab(w, 'settings'); await w.ev("window.__i18nMiss=new Set()"); await w.click('#set-help [data-act=helpOpen]'); await w.wait(300)
                await w.ev("document.querySelectorAll('#layer details').forEach(d=>d.open=true)"); await w.wait(300)
                miss = await w.ev("[...window.__i18nMiss]"); st = await w.sheet_text()
                title = await w.ev("document.querySelector('#layer h3').innerText")
                check(f'help, {lang}: every question and answer (and the buttons) is translated: nothing missed', not miss, miss[:3])
                check(f'help, {lang}: the title and the text are in that language (not English left over)', (lang == 'en' and title == 'Help & FAQ') or (lang != 'en' and title != 'Help & FAQ' and 'What is NUTCADE?' not in st and 'recovery phrase' not in st.lower().replace('recuperación', '').replace('récupération', '').replace('recuperação', '') or lang != 'en' and title != 'Help & FAQ'), title)
                if lang != 'en':
                    en = await w.ev("[...document.querySelectorAll('#layer details')].length")
                    check(f'help, {lang}: still every topic', en >= 14, en)
                await w.pg.context.close()
            for th in THEMES:
                for (vw, vh) in ((320, 640), (640, 320), (390, 844)):
                    w = await funded(b, vw=vw, vh=vh)
                    await w.ev(f"Nutcade.S.prefs.theme={J(th)}; Nutcade.render()")
                    await tab(w, 'settings'); await w.click('[data-act=jump][data-id=set-help]'); await w.wait(250)
                    l = await lay(w, 'help panel'); check(f'help, {th} {vw}x{vh}: the Help panel in Settings fits', not l, l)
                    await w.click('#set-help [data-act=helpOpen]'); await w.wait(300)
                    l = await lay(w, 'help closed'); check(f'help, {th} {vw}x{vh}: the Help sheet (all folds closed) fits', not l, l)
                    await w.ev("document.querySelectorAll('#layer details').forEach(d=>d.open=true)"); await w.wait(250)
                    l = await lay(w, 'help open'); check(f'help, {th} {vw}x{vh}: and with every fold open (long words and web addresses wrap)', not l, l)
                    if th == 'neon' or (vw, vh) == (320, 640): await shot(w, f'help_{th}_{vw}x{vh}')
                    await w.ev("document.querySelector('#layer [data-act=close].block').scrollIntoView({block:'end'})"); await w.wait(150)
                    check(f'help, {th} {vw}x{vh}: the sheet scrolls to the end and the Done button can be reached', await w.ev("(()=>{const b=document.querySelector('#layer [data-act=close].block'); if(!b) return false; const r=b.getBoundingClientRect(); return r.bottom<=innerHeight+1 && r.top>=0})()"))
                    await w.pg.context.close()
        await section('help_layout', help_lang_layout)

        # ======================= a mint's contact, terms and description =======================
        async def mintinfo():
            w = await funded(b)
            bad = {'v': 0}
            hostile = {
                'name': 'Evil <b>Mint</b><img src=x onerror="window.__xss=1">', 'version': 'Nutshell/0.16.0<script>window.__xss=1</script>', 'pubkey': '02' + 'ab' * 32,
                'description': 'Short <img src=x onerror="window.__xss=2"> text',
                'description_long': ('Line one\n<script>window.__xss=3</script>\n‮gnp.exe‬ bidi \u0007 bell ‏ mark\n' + 'x' * 5000),
                'motd': '<svg onload="window.__xss=4">motd</svg>',
                'tos_url': 'http://mint.example.org/terms?a=1&b=2',
                'contact': [{'method': 'email', 'info': 'ops@mint.example.org'}, {'method': 'nostr', 'info': 'npub1' + 'q' * 58},
                            {'method': 'website', 'info': 'https://mint.example.org/contact'}, {'method': 'x', 'info': 'javascript:window.__xss=5'},
                            {'method': 'data', 'info': 'data:text/html,<script>window.__xss=6</script>'}, {'method': 'cred', 'info': 'https://user:pass@mint.example.org/'},
                            {'method': 'mailto', 'info': 'mailto:a@b.c'}, {'method': '<i>html</i>', 'info': '"><a href="javascript:window.__xss=7">x</a>'},
                            {'method': 'ninth', 'info': 'https://nine.example.org'}, {'method': 'tenth', 'info': 'http://plain.example.org/x'}],
                'nuts': {'4': {'methods': [{'method': 'bolt11', 'unit': 'sat'}]}, '5': {'methods': [{'method': 'bolt11', 'unit': 'sat'}]}}}
            state = {'mode': 'hostile'}
            async def info(route):
                if state['mode'] == 'down': return await route.abort()
                r = await route.fetch(); d = await r.json()
                if state['mode'] == 'hostile': d = dict(d, **hostile)
                elif state['mode'] == 'old': d = dict(d, contact=[['email', 'old@mint.example.org'], ['nostr', 'npub1old']], description=None, description_long=None, tos_url=None)
                elif state['mode'] == 'none': d = dict(d, contact=[], tos_url=None, description=None, description_long=None, motd=None)
                elif state['mode'] == 'weird': d = dict(d, contact='ops@mint', tos_url=['x'], description=42, description_long={'a': 1}, motd=7)
                await route.fulfill(response=r, body=json.dumps(d))
            await w.pg.context.route(f'{B}/v1/info', info)
            await tab(w, 'mints')
            check('mint details: every mint has a Details button', await w.ev("document.querySelectorAll('[data-act=mintInfo]').length")==2)
            await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1800)
            body = await w.ev("document.querySelector('#layer .sheet-body').innerHTML"); txt = await w.sheet_text()
            check('mint details: nothing from the mint ran (no script, no image, no handler, no injected element)', await w.ev("window.__xss===undefined") and not await w.ev("document.querySelector('#layer img,#layer script,#layer svg,#layer iframe,#layer [onerror],#layer [onload],#layer i,#layer b')"), await w.ev("window.__xss"))
            check('mint details: the markup the mint sent shows as plain text, escaped', '<img src=x' in txt and '<script>window.__xss=3' in txt and '&lt;' in body)
            links = await w.ev("[...document.querySelectorAll('#layer a')].filter(a=>!a.classList.contains('btn')).map(a=>({h:a.getAttribute('href'),t:a.target,r:a.rel}))")
            hrefs = [l['h'] for l in links]
            check('mint details: only http and https addresses became links (the terms, a website)', sorted(hrefs) == sorted(['http://mint.example.org/terms?a=1&b=2', 'https://mint.example.org/contact']), hrefs)
            check('mint details: every link opens in a new tab with rel=noopener (noreferrer too)', all(l['t'] == '_blank' and 'noopener' in l['r'] and 'noreferrer' in l['r'] for l in links), links)
            check('mint details: no javascript:, data: or mailto: link anywhere in the sheet', not await w.ev("[...document.querySelectorAll('#layer [href],#layer [src],#layer [action],#layer [formaction]')].some(e=>/^\\s*(javascript|data|mailto|vbscript):/i.test(e.getAttribute('href')||e.getAttribute('src')||''))"))
            check('mint details: a web address with a name and password in it is shown as text, not linked', 'user:pass@mint.example.org' in txt and 'user:pass' not in ' '.join(hrefs))
            check('mint details: javascript:, data: and mailto: contacts appear as plain text', all(x in txt for x in ('javascript:window.__xss=5', 'data:text/html', 'mailto:a@b.c')))
            check('mint details: contact, terms, description, long description and message are all shown, with markup in a contact\'s name shown as text', all(x in txt for x in ('Contact', 'Terms of service', 'About this mint', 'In more detail', 'Message from the mint', 'ops@mint.example.org', '<i>html</i>')), txt[:150])
            check('mint details: control and text-direction characters from the mint are stripped', not re.search('[‪-‮‎‏⁦-⁩\u0007]', txt) and 'gnp.exe' in txt)
            check('mint details: long text is cut (5,000 characters become at most 2,000) and at most 8 contacts show', len(txt) < 3200 and await w.ev("document.querySelectorAll('#layer .minfo-row').length") == 8 and 'nine.example.org' not in txt, (len(txt), await w.ev("document.querySelectorAll('#layer .minfo-row').length")))
            check('mint details: it says plainly that the text is the mint\'s, not ours', 'written by the mint, not by NUTCADE' in txt)
            check('mint details: the sheet text is in the mint\'s own words and is not translated (it is the mint\'s)', await w.ev("[...document.querySelectorAll('#layer [data-noi18n]')].length")>=6)
            await w.ev("Nutcade.closeSheet()")
            # an old mint's contact list ([[method, info]]), a mint with nothing, a mint with odd types, a mint that does not answer
            state['mode'] = 'old'; await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); txt = await w.sheet_text()
            check('mint details: the older contact format ([["email","…"]]) is read too', 'old@mint.example.org' in txt and 'npub1old' in txt, txt[:120]); await w.ev("Nutcade.closeSheet()")
            state['mode'] = 'none'; await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); txt = await w.sheet_text()
            check('mint details: a mint with nothing to say: "lists no contact" and "lists no terms"', 'The mint lists no contact.' in txt and 'The mint lists no terms.' in txt and 'undefined' not in txt and 'null' not in txt, txt[:200]); await w.ev("Nutcade.closeSheet()")
            state['mode'] = 'weird'; await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); txt = await w.sheet_text()
            check('mint details: odd types (a string for the contact list, numbers for the text) neither break nor show junk', 'The mint lists no terms.' in txt and 'undefined' not in txt and '[object' not in txt and not [e for e in w.errs if 'PAGEERROR' in e], (txt[:150], w.errs[:2])); await w.ev("Nutcade.closeSheet()")
            state['mode'] = 'down'; await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); txt = await w.sheet_text()
            check('mint details: a mint that does not answer: what was read earlier is still shown (it is kept on the phone)', 'The mint lists no terms.' in txt or 'The mint did not answer' in txt, txt[:100]); await w.ev("Nutcade.closeSheet()")
            state['mode'] = 'hostile'
            await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); await w.ev("Nutcade.closeSheet()")
            state['mode'] = 'down'; await w.pg.reload(); await w.wait(900); await tab(w, 'mints')
            await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1500); txt = await w.sheet_text()
            check('mint details: after a reload and with the mint unreachable, the kept details show (offline)', 'ops@mint.example.org' in txt, txt[:100]); await w.ev("Nutcade.closeSheet()")
            # a mint never reached at all
            await w.pg.context.route(f'{A}/v1/info', lambda r: r.abort())
            await w.click(f'[data-act=mintInfo][data-url="{A}"]'); await w.wait(1800); txt = await w.sheet_text()
            check('mint details: a mint that never answered and has nothing kept says so plainly', 'did not answer' in txt or 'The mint lists no contact' in txt, txt[:150])
            check('mint details: no page errors', not [e for e in w.errs if 'PAGEERROR' in e], w.errs[:3])
            await w.pg.context.close()
        await section('mintinfo', mintinfo)

        async def mintinfo_report():
            w = await funded(b)
            await w.pg.context.route(f'{B}/v1/info', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'name': 'Info Mint', 'pubkey': '02' + 'cd' * 32, 'version': 'Nutshell/0.16', 'motd': 'hello from the mint', 'contact': [{'method': 'email', 'info': 'a@b.example'}], 'tos_url': 'https://t.example/tos', 'nuts': {}})))
            await tab(w, 'mints'); await w.click(f'[data-act=reportOpen][data-url="{B}"]'); await w.wait(2500)
            t = await w.sheet_text()
            check('report card: still opens and shows the mint\'s message, as before', 'hello from the mint' in t, t[:200])
            await w.ev("Nutcade.closeSheet()")
            info = await w.ev("JSON.parse(localStorage.getItem('nutcade:mintlog')||'{}')[" + J(B) + "]")
            i = (info or {}).get('info') or {}
            check('report card: the numbers it used (contact count, terms yes/no, name, version) are still kept', i.get('contact') == 1 and i.get('tos') is True and i.get('name') == 'Info Mint' and i.get('version') == 'Nutshell/0.16' and i.get('motd') == 'hello from the mint', i)
            await w.pg.context.close()
        await section('mintinfo_report', mintinfo_report)

        async def mintinfo_lang_layout():
            hostile = {'name': 'Layout Mint', 'description': 'A fairly long description of the mint that should wrap onto several lines on a narrow phone without any sideways scrolling at all.', 'description_long': 'Longer text. ' * 80,
                       'motd': 'Be careful: ' + 'a' * 60, 'tos_url': 'https://averyveryverylongdomainname.example.org/path/to/a/very/long/terms-of-service-page-that-goes-on?and=on&on=and' + 'z' * 60,
                       'contact': [{'method': 'email', 'info': 'someone.with.a.very.long.address@a-very-long-domain-name.example.org'}, {'method': 'nostr', 'info': 'npub1' + 'q' * 58}, {'method': 'website', 'info': 'https://example.org/' + 'p' * 90}]}
            async def route_info(w):
                async def info(route):
                    r = await route.fetch(); d = await r.json(); await route.fulfill(response=r, body=json.dumps(dict(d, **hostile)))
                await w.pg.context.route(f'{B}/v1/info', info)
            for lang in LANGS:
                w = await funded(b, lang=lang); await route_info(w)
                await tab(w, 'mints'); await w.ev("window.__i18nMiss=new Set()")
                await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1800)
                miss = await w.ev("[...window.__i18nMiss]")
                check(f'mint details, {lang}: the labels, the notice and the button are translated (the mint\'s own text is left alone)', not miss and (lang == 'en' or 'Terms of service' not in await w.sheet_text()), miss)
                await w.pg.context.close()
            for th in THEMES:
                for (vw, vh) in ((320, 640), (640, 320)):
                    w = await funded(b, vw=vw, vh=vh); await route_info(w)
                    await w.ev(f"Nutcade.S.prefs.theme={J(th)}; Nutcade.render()"); await tab(w, 'mints')
                    l = await lay(w, 'mints'); check(f'mint details, {th} {vw}x{vh}: the Mints screen with the Details button fits', not l, l)
                    await w.click(f'[data-act=mintInfo][data-url="{B}"]'); await w.wait(1800)
                    l = await lay(w, 'sheet'); check(f'mint details, {th} {vw}x{vh}: the sheet with long addresses and text fits', not l, l)
                    if th != 'amber': await shot(w, f'mintinfo_{th}_{vw}x{vh}')
                    await w.pg.context.close()
        await section('mintinfo_layout', mintinfo_lang_layout)

        # ======================= nothing about money changed =======================
        async def money():
            code = {k: v for k, v in SRC.items()}
            check('money: the new files never touch proofs, counters, quotes, melts, swaps, the seed bytes or the limit gate', not re.search(r'S\.proofs|S\.counters|getWallet|swap\(|melt|mintQuote|limitGate|persistCounters|setSeed|seedFor|mnemonicToSeed', code['app_trust.js'] + code['app_trust_actions.js']), re.findall(r'S\.proofs|S\.counters|getWallet|swap\(|melt|mintQuote|limitGate', code['app_trust.js']))
            check('money: the new code only reads the money state (ops, pending, imports, quotes, flights) to know whether something is open', all(x in code['app_trust.js'] for x in ('S.ops', 'S.pending', 'S.imports', 'quoteBusy', 'flights')))
            w = await wallet(b)
            check('money: fmt() and money() still format amounts exactly as before', await w.ev("[Nutcade.fmt(0),Nutcade.fmt(1),Nutcade.fmt(1000),Nutcade.fmt(1234567.4)]") == ['0', '1', '1,000', '1,234,567'])
            await w.pg.context.close()
        await section('money', money)

        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', sum(1 for r in results if not r[1]), 'failed')
        await b.close()


def Nutcade_txt(t, bal):
    return re.sub(r'[^\d]', '', t) == str(bal)


if __name__ == '__main__':
    asyncio.run(main())
