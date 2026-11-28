"""The README's pictures and tour video, made from the app itself (1.52.0).

Run from the repository root, with the test setup (Python Playwright, a Nutshell mint in MINT_PY's environment):
    MINT_PY=/path/to/mint/python python3 tools/readme_shots.py [scene ...]
It starts its own test mint "Pixel" (port 3361, fake Lightning, no fees), seen by the app as https://mint.pixel.cash, and
serves public/ on port 8099. The BTC price chart gets fixed candles around $97,000 (no network). Each scene drives real
wallets in headless phones (390 x 844), then lays the screenshots into the arcade frame at 1280 x 720 (docs/screens/*.jpg).
Scene "video" records the tour as docs/nutcade-tour.mp4 and docs/nutcade-tour.gif (ffmpeg). No real people's names.
"""
import asyncio, base64, json, math, os, re, shutil, signal, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from playwright.async_api import async_playwright
from wallet_qa import W, URL

OUT = os.path.join(ROOT, 'docs', 'screens')
PORT = 3361
MINT = 'https://mint.pixel.cash'
LOCAL = f'http://127.0.0.1:{PORT}'
J = json.dumps
FONTS = ''.join(re.findall(r'@font-face\{[^}]*\}', open(os.path.join(ROOT, 'public', 'index.html')).read())[:2])
PROCS = []


# ---------- the demo mint, the page and the price ----------
def start_servers():
    py = os.environ.get('MINT_PY', 'python3')
    d = tempfile.mkdtemp(prefix='nutcade-shots-'); stub = os.path.join(ROOT, 'tests', 'stub')
    env = dict(os.environ, MINT_BACKEND_BOLT11_SAT='FakeWallet', MINT_PRIVATE_KEY='nutcade-readme-shots', MINT_LISTEN_HOST='127.0.0.1',
               MINT_LISTEN_PORT=str(PORT), MINT_DATABASE='data/mint', FAKEWALLET_BRR='TRUE', FAKEWALLET_DELAY_INCOMING_PAYMENT='0.5',
               FAKEWALLET_DELAY_OUTGOING_PAYMENT='0.5', MINT_INFO_NAME='Pixel', MINT_INPUT_FEE_PPK='0', PYTHONPATH=stub,
               NUTCADE_PREIMAGE_DIR=os.path.join(d, 'preimages'))
    PROCS.append(subprocess.Popen([py, '-m', 'uvicorn', 'cashu.mint.app:app', '--host', '127.0.0.1', '--port', str(PORT)], cwd=d, env=env,
                                  stdout=open(os.path.join(d, 'log'), 'w'), stderr=subprocess.STDOUT))
    PROCS.append(subprocess.Popen([sys.executable, '-m', 'http.server', '8099', '-d', os.path.join(ROOT, 'public')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(120):
        try: urllib.request.urlopen(LOCAL + '/v1/info', timeout=1); urllib.request.urlopen('http://127.0.0.1:8099/index.html', timeout=1); return
        except Exception: time.sleep(0.5)
    raise RuntimeError('the demo mint or the page did not start')


def stop_servers():
    for p in PROCS:
        try: p.send_signal(signal.SIGTERM); p.wait(5)
        except Exception: pass


def candles(url):
    m = re.search(r'granularity=(\d+)&start=([^&]+)&end=([^&]+)', url); g = int(m.group(1)) if m else 3600
    end = int(time.time()) // g * g; out = []
    for i in range(300):
        t = end - i * g; x = (t / g) % 997
        c = 97121 - i * 9 + 900 * math.sin(x / 9) + 260 * math.sin(x * 1.7)
        out.append([t, round(c - 120), round(c + 140), round(c - 30), round(c), 12.5])
    return out


async def routes(ctx):
    async def mint(route):
        u = route.request.url.replace(MINT, LOCAL, 1)
        try:
            r = await route.fetch(url=u)
            await route.fulfill(response=r, headers=dict(r.headers, **{'access-control-allow-origin': '*'}))
        except Exception:
            try: await route.abort()
            except Exception: pass
    async def price(route):
        await route.fulfill(status=200, content_type='application/json', body=J(candles(route.request.url)), headers={'access-control-allow-origin': '*'})
    await ctx.route(MINT + '/**', mint)
    await ctx.route('https://api.exchange.coinbase.com/**', price)


async def phone(b, lang='en', prefs=None, video=None):
    o = dict(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    if video: o.update(record_video_dir=video, record_video_size={'width': 390, 'height': 844}, device_scale_factor=1)
    ctx = await b.new_context(**o)
    p = {'sound': False, 'music': False, 'lang': lang, 'fiat': True}
    p.update(prefs or {})
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(p)) + ")")
    await routes(ctx)
    pg = await ctx.new_page(); w = W(pg, 'shot')
    await pg.goto(URL); await pg.wait_for_timeout(800)
    return w


async def ready(w, sats=0):
    await w.create(); await w.add_mint(MINT); await w.use(MINT)
    if sats: await w.receive_ln(sats)
    await w.home(); await w.wait(600)


async def clean(w, toast=True):
    """closes the arrival banner (and, unless asked to keep it, the toast line) for a tidy picture"""
    await w.ev("document.querySelectorAll('[data-act=arrClose]').forEach(b=>b.click())")
    if toast: await w.ev("(t=>{if(t){t.hidden=true}})(document.querySelector('#toast'))")
    await w.wait(250)


async def snap(w, name):
    path = os.path.join(TMP, name + '.png')
    await w.pg.screenshot(path=path)
    return path


# ---------- the arcade frame ----------
COLORS = {'pink': '#ff3d9a', 'gold': '#ffc83d', 'cyan': '#3ee6ff', 'lime': '#7dff6a', 'violet': '#b48cff'}


def frame(name, title, phones, labels=None, top=False, extra=''):
    """title: [(text, color)], one line each; phones: png paths; labels: one line above (or under, top=True) each phone"""
    imgs = [base64.b64encode(open(p, 'rb').read()).decode() for p in phones]
    n = len(phones) + (1 if extra else 0); pw = 312 if n < 2 else 284 if n == 2 else 214 if n == 5 else 250
    tsize = 44 if n < 2 else 34
    ph = round(pw * 844 / 390)
    lines = ''.join(f'<div style="color:{COLORS[c]};text-shadow:0 0 18px {COLORS[c]}88,4px 4px 0 #000">{t}</div>' for t, c in title)
    cells = ''.join(f'''<div class="cell">{f'<div class="lab">{labels[i]}</div>' if labels and not top else ''}
      <div class="ph" style="width:{pw}px;height:{ph}px"><img src="data:image/png;base64,{im}"></div>
      {f'<div class="lab">{labels[i]}</div>' if labels and top else ''}</div>''' for i, im in enumerate(imgs))
    head = f'<div class="t top">{lines}</div>' if top else f'<div class="t">{lines}</div>'
    body = f'{head}<div class="row">{cells}</div>' if top else f'<div class="side">{head}<div class="row">{extra}{cells}</div></div>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
      html,body{{margin:0;width:1280px;height:720px;overflow:hidden;background:#0a0717}}
      body{{background:radial-gradient(ellipse 60% 70% at 72% 50%,#3a1660 0,transparent 70%),linear-gradient(#ffffff0d 1px,transparent 1px) 0 0/42px 42px,linear-gradient(90deg,#ffffff0d 1px,transparent 1px) 0 0/42px 42px,#0a0717;font-family:"Press Start 2P",monospace;color:#fff}}
      .side{{display:flex;align-items:center;justify-content:space-between;height:720px;padding:0 70px 0 80px;box-sizing:border-box}}
      .t{{font-size:{tsize}px;line-height:1.35;letter-spacing:2px;white-space:nowrap}} .t.top{{text-align:center;padding-top:44px;font-size:40px}}
      .row{{display:flex;gap:22px;align-items:center;justify-content:center}} .top + .row{{margin-top:26px}}
      .cell{{display:flex;flex-direction:column;align-items:center;gap:12px}}
      .lab{{font-family:"VT323",monospace;font-size:30px;letter-spacing:3px;color:#e8e3ff}}
      .ph{{border:3px solid #a26bff;border-radius:34px;padding:7px;background:#0a0717;box-shadow:0 0 34px #9b5cff88,inset 0 0 12px #9b5cff55}}
      .ph img{{width:100%;height:100%;border-radius:27px;display:block;object-fit:cover;object-position:top}}
      .card{{border-radius:10px;box-shadow:0 0 34px #ffc83d55}}</style></head><body>{body}</body></html>'''


async def render(b, name, html):
    ctx = await b.new_context(viewport={'width': 1280, 'height': 720}, device_scale_factor=1.5)
    pg = await ctx.new_page(); await pg.set_content(html); await pg.wait_for_timeout(400)
    png = os.path.join(TMP, name + '-frame.png'); await pg.screenshot(path=png); await ctx.close()
    subprocess.run(['convert', png, '-quality', '84', '-sampling-factor', '4:2:0', '-strip', os.path.join(OUT, name + '.jpg')], check=True)
    print('wrote', os.path.join(OUT, name + '.jpg'), os.path.getsize(os.path.join(OUT, name + '.jpg')) // 1024, 'KB', flush=True)


# ---------- the scenes ----------
async def wait_1up(w, before, amt):
    for _ in range(200):
        if await w.bal() >= before + amt: return True
        await w.wait(60)
    return False


async def s_lightning(b):
    w = await phone(b); await ready(w)
    await w.click('[data-act=receive]'); await w.wait(200)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
    await w.fill('#amtIn', '21000'); await w.click('[data-act=doLnInvoice]')
    await wait_1up(w, 0, 21000); await w.ev("document.querySelectorAll('[data-act=arrClose]').forEach(b=>b.click())"); await w.wait(500)
    p = await snap(w, '01')
    await render(b, '01-lightning', frame('01', [('LOAD SATS', 'gold'), ('OVER LIGHTNING', 'cyan')], [p]))
    await w.pg.context.close()


async def s_send(b):
    a = await phone(b); await ready(a, 21000); f = await phone(b); await ready(f)
    await a.home(); await a.click('[data-act=send]'); await a.wait(150); await a.fill('#amtIn', '2100'); await a.fill('#noteIn', 'Pizza night')
    await a.click('[data-act=doSendEcash]'); await a.until("!!Nutcade.S.txs[0] && !!Nutcade.S.txs[0].token", 20000)
    tok = await a.ev("Nutcade.S.txs[0].token")
    await f.home(); await f.click('[data-act=receive]'); await f.wait(150); await f.click('[data-act=recvMethod][data-m=ecash]'); await f.wait(100)
    await f.fill('#tokIn', tok); await f.click('[data-act=doReceiveToken]'); await f.wait(900)
    if await f.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await f.click('[data-act=doReceiveToken]')
    await wait_1up(f, 0, 2100); await clean(a); await f.ev("document.querySelectorAll('[data-act=arrClose]').forEach(b=>b.click())"); await f.wait(350)
    pa, pf = await snap(a, '04a'), await snap(f, '04b')
    await render(b, '04-send', frame('04', [('SEND SATS', 'pink'), ('TO FRIENDS', 'gold')], [pa, pf], ['YOU', 'FRIEND']))
    await a.pg.context.close(); await f.pg.context.close()


async def s_languages(b):
    shots = []
    for lang in ('en', 'es', 'pt', 'de', 'fr'):
        w = await phone(b, lang); await ready(w, 21000); await w.wait(1500); await clean(w)
        shots.append(await snap(w, '07' + lang)); await w.pg.context.close()
    await render(b, '07-languages', frame('07', [('5 LANGUAGES', 'cyan')], shots, ['ENGLISH', 'ESPAÑOL', 'PORTUGUÊS', 'DEUTSCH', 'FRANÇAIS'], top=True))


async def s_arcade(b):
    w = await phone(b); await ready(w, 1000); await clean(w)
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(400)
    n = await w.ev("Arcade.games.length")
    await w.ev("document.querySelector('[data-game=swarm]').click()"); await w.wait(800)
    for k in ('Enter', 'Enter'): await w.pg.keyboard.press(k); await w.wait(500)
    await w.pg.keyboard.down('Space')
    for i in range(14):
        await w.pg.keyboard.down('ArrowLeft' if i % 4 < 2 else 'ArrowRight'); await w.wait(180); await w.pg.keyboard.up('ArrowLeft' if i % 4 < 2 else 'ArrowRight')
    p = await snap(w, '02'); await w.pg.keyboard.up('Space')
    await render(b, '02-arcade', frame('02', [(f'{n} ARCADE', 'pink'), ('CABINETS', 'cyan'), ('BUILT IN', 'gold')], [p]))
    await w.pg.context.close()


async def s_trophies(b):
    w = await phone(b); await ready(w, 21000); await clean(w)
    ids = await w.ev("Trophies.DEFS.map(d=>d.id)")
    got = {i: 1700000000000 + k for k, i in enumerate(ids) if k % 3 != 2}
    await w.ev(f"window.NutStore.set('trophies', {J(got)}); Trophies.reload()"); await w.wait(200)
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
    await w.ev("document.querySelector('#trophyRoom').scrollIntoView({block:'start'})"); await w.wait(400); await clean(w)
    p = await snap(w, '03')
    await render(b, '03-trophies', frame('03', [('WIN', 'gold'), ('TROPHIES', 'pink')], [p]))
    await w.pg.context.close()


async def s_sound(b):
    a = await phone(b); await ready(a, 21000); f = await phone(b); await ready(f)
    await a.home(); await a.click('[data-act=send]'); await a.wait(150); await a.fill('#amtIn', '1024')
    await a.click('[data-act=doSendEcash]'); await a.until("!!Nutcade.S.txs[0] && !!Nutcade.S.txs[0].token", 20000); await a.wait(300)
    tok = await a.ev("Nutcade.S.txs[0].token")
    await a.ev("[...document.querySelectorAll('#layer button')].find(b=>/play as sound/i.test(b.innerText)).click()"); await a.wait(700)
    await f.home(); await f.click('[data-act=receive]'); await f.wait(150); await f.click('[data-act=recvMethod][data-m=ecash]'); await f.wait(100)
    await f.fill('#tokIn', tok); await f.click('[data-act=doReceiveToken]'); await f.wait(900)
    if await f.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await f.click('[data-act=doReceiveToken]')
    await wait_1up(f, 0, 1024); await clean(a); await f.ev("document.querySelectorAll('[data-act=arrClose]').forEach(b=>b.click())"); await f.wait(350)
    pa, pf = await snap(a, '05a'), await snap(f, '05b')
    await render(b, '05-sound', frame('05', [('SEND SATS', 'cyan'), ('BY SOUND', 'gold')], [pa, pf], ['YOU', 'FRIEND']))
    await a.pg.context.close(); await f.pg.context.close()


async def s_cashier(b):
    w = await phone(b); await ready(w); await clean(w)
    await w.click('[data-act=cashier]'); await w.wait(300)
    for k in '5000': await w.click(f'.cashier [data-ck="{k}"]')
    await w.click('.cashier [data-ck=charge]'); await w.until("/PAID!/.test(document.querySelector('.cashier').innerText)", 25000); await w.wait(600)
    p = await snap(w, '06')
    await render(b, '06-cashier', frame('06', [('CASHIER MODE', 'gold'), ('SELL FOR SATS', 'lime')], [p]))
    await w.pg.context.close()


async def s_pin(b):
    from r8_qa import set_pin
    w = await phone(b); await ready(w, 21000); await clean(w)
    await set_pin(w); await w.home(); await w.click('[data-act=lockNow]'); await w.wait(1500)
    await w.until("!!document.querySelector('[data-pinpad]')", 8000)
    for k in '13': await w.click(f'[data-pinpad] [data-k="{k}"]')
    await w.wait(300); p = await snap(w, '08')
    await render(b, '08-pin', frame('08', [('PIN LOCK', 'violet'), ('AND A DURESS', 'pink'), ('PIN', 'pink')], [p]))
    await w.pg.context.close()


async def s_pizza(b):
    w = await phone(b); await ready(w, 21000); await clean(w)
    await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=ptOpen]'); await w.wait(300)
    if await w.ev("!!document.querySelector('.pt-intro')"): await w.click('[data-act=ptIntroOk]'); await w.wait(300)
    await w.fill('#ptAmt', '1024'); await w.fill('#ptCount', '2'); await w.click('[data-act=ptStyle][data-s=pizza]'); await w.wait(100)
    await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000); await w.click('[data-act=ptMake]')
    await w.until("!!document.querySelector('.pt-ready')", 120000); await w.wait(500)
    bid = await w.ev("document.querySelector('.pt-ready').dataset.b")
    await w.ev("document.querySelector('.pt-ready .pt-preview').scrollIntoView({block:'center'})"); await w.wait(300)
    p = await snap(w, '09')
    await w.ev(f"NutTokens.preparePrint({J(bid)})"); await w.pg.set_viewport_size({'width': 794, 'height': 1123}); await w.pg.emulate_media(media='print'); await w.wait(400)
    cards = os.path.join(TMP, '09cards.png'); await w.pg.locator('#tokPrint .pt-page').first.screenshot(path=cards)
    c64 = base64.b64encode(open(cards, 'rb').read()).decode()
    extra = f'<img class="card" src="data:image/png;base64,{c64}" style="width:430px">'
    await render(b, '09-printed', frame('09', [('PRINT SATS', 'gold'), ('ON PAPER', 'pink')], [p], extra=extra))
    await w.pg.context.close()


async def s_readable(b):
    shots = []
    for on in (False, True):
        w = await phone(b, prefs={'readable': on}); await ready(w, 21000); await w.wait(1500); await clean(w)
        shots.append(await snap(w, '10' + ('b' if on else 'a'))); await w.pg.context.close()
    await render(b, '10-readable', frame('10', [('READABLE', 'lime'), ('TEXT', 'lime'), ('ONE SWITCH', 'cyan')], shots, ['ARCADE', 'READABLE']))


async def s_video(b):
    vdir = os.path.join(TMP, 'video'); os.makedirs(vdir, exist_ok=True)
    w = await phone(b, video=vdir); await ready(w); await clean(w)
    t0 = time.time(); await w.wait(1200)
    await w.click('[data-act=receive]'); await w.wait(700)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(300)
    await w.pg.type('#amtIn', '21000', delay=90); await w.pg.dispatch_event('#amtIn', 'input'); await w.wait(500)
    await w.click('[data-act=doLnInvoice]'); await wait_1up(w, 0, 21000); await w.wait(3200)
    await w.ev("Nutcade.closeSheet()"); await clean(w); await w.wait(900)
    await w.click('[data-act=send]'); await w.wait(700); await w.pg.type('#amtIn', '2100', delay=90); await w.pg.dispatch_event('#amtIn', 'input'); await w.wait(500)
    await w.click('[data-act=doSendEcash]'); await w.until("!!Nutcade.S.txs[0] && !!Nutcade.S.txs[0].token", 20000); await w.wait(2600)
    await w.ev("Nutcade.closeSheet()"); await clean(w); await w.wait(600)
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(1400)
    await w.ev("document.querySelector('[data-game=swarm]').click()"); await w.wait(900)
    for k in ('Enter', 'Enter'): await w.pg.keyboard.press(k); await w.wait(500)
    await w.pg.keyboard.down('Space')
    for i in range(22):
        k = 'ArrowLeft' if i % 6 < 3 else 'ArrowRight'; await w.pg.keyboard.down(k); await w.wait(200); await w.pg.keyboard.up(k)
    await w.pg.keyboard.up('Space'); await w.ev("(b=>b&&b.click())(document.querySelector('[data-g=exit]'))"); await w.wait(700)
    await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(700)
    await w.click('[data-act=send]'); await w.wait(500); await w.click('[data-act=ptOpen]'); await w.wait(600)
    if await w.ev("!!document.querySelector('.pt-intro')"): await w.wait(900); await w.click('[data-act=ptIntroOk]'); await w.wait(600)
    await w.fill('#ptAmt', '1024'); await w.fill('#ptCount', '2'); await w.wait(400); await w.click('[data-act=ptStyle][data-s=pizza]'); await w.wait(900)
    await w.click('[data-act=ptNext]'); await w.until("!!document.querySelector('[data-act=ptMake]')", 20000); await w.wait(1200); await w.click('[data-act=ptMake]')
    await w.until("!!document.querySelector('.pt-ready')", 120000); await w.wait(800)
    await w.ev("document.querySelector('.pt-ready .pt-preview').scrollIntoView({block:'center',behavior:'smooth'})"); await w.wait(3200)
    t1 = time.time(); vid = w.pg.video; await w.pg.context.close()
    src = await vid.path(); convert_tour(src, t1 - t0)
    print('length', round(t1 - t0, 1), 's', flush=True)


def convert_tour(src, length):
    """the recording (variable frame rate: seeking in it scrambles the order) made steady at 30 fps first, then its last
    `length` seconds kept, as docs/nutcade-tour.mp4 and a GIF for the README"""
    full = os.path.join(TMP, 'full.mp4'); mp4 = os.path.join(ROOT, 'docs', 'nutcade-tour.mp4'); gif = os.path.join(ROOT, 'docs', 'nutcade-tour.gif')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-vf', 'fps=30', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', full], check=True)
    total = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', full], capture_output=True, text=True).stdout.strip())
    start = max(0.0, total - length)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', full, '-ss', f'{start:.2f}', '-vf', 'scale=390:-2:flags=lanczos', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '24', '-movflags', '+faststart', '-an', mp4], check=True)
    pal = os.path.join(TMP, 'pal.png')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', mp4, '-vf', 'fps=12,scale=300:-1:flags=lanczos,palettegen=max_colors=96:stats_mode=diff', pal], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', mp4, '-i', pal, '-lavfi', 'fps=12,scale=300:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle', gif], check=True)
    for f in (mp4, gif): print('wrote', f, os.path.getsize(f) // 1024, 'KB', flush=True)


SCENES = {'lightning': s_lightning, 'arcade': s_arcade, 'trophies': s_trophies, 'send': s_send, 'sound': s_sound, 'cashier': s_cashier,
          'languages': s_languages, 'pin': s_pin, 'pizza': s_pizza, 'readable': s_readable, 'video': s_video}


async def main(names):
    global TMP
    TMP = tempfile.mkdtemp(prefix='nutcade-shots-png-'); os.makedirs(OUT, exist_ok=True)
    start_servers()
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            for n in names or list(SCENES):
                print('---', n, flush=True); await SCENES[n](b)
            await b.close()
    finally:
        stop_servers()
    print('pngs in', TMP)


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1:]))
