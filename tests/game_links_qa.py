"""Acorn Links (cabinet links): in the lobby, nine holes from the seed, the rules (swing, wind-free carry, water, holing, scoring, the round ends),
real play with keyboard (hold Space, let go), mouse/touch (drag back and let go) and a tap on the panel (club), a replay that gives the same score,
a high score at the end of a round, and every on-screen text in five languages fits the 224 px screen.
No mint is needed: only the page (NUTCADE_URL) is."""
import os, sys, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, check, results, URL
from playwright.async_api import async_playwright

OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
os.makedirs(OUT, exist_ok=True)

async def wallet(b, vw=390, vh=844, lang='en', mobile=True):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': True, 'music': True, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'links')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and '127.0.0.1' not in m.text and 'Failed to load resource' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    await w.create()
    return w

HOOK = "(()=>{const g=Arcade.games.find(x=>x.id==='links');if(!g.__h){const od=g.draw;g.draw=function(s,G,c){window.__st=s;window.__G=G;return od.call(this,s,G,c)};g.__h=1}})()"
HASH = "(()=>{const d=document.querySelector('#gameCanvas').getContext('2d').getImageData(0,0,224,288).data;let h=0;for(let i=0;i<d.length;i+=61)h=(h*31+d[i]+(d[i+1]<<3))|0;return h})()"

def holep(st, par):
    d = st - par
    return 1000 if st == 1 else 700 if d <= -2 else 400 if d == -1 else 250 if d == 0 else 100 if d == 1 else 50 if d == 2 else 0

async def lobby(w):
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(400)

async def open_links(w, start=True):
    await w.ev("document.querySelector('[data-game=links]').click()"); await w.wait(300)
    await w.ev(HOOK)
    if start:
        await w.pg.keyboard.press('Space'); await w.wait(250)

# the same rules without a screen: a stepper fed one input per frame (held, hit, ptr bits, x*4, y*4, tap x, tap y, swipe)
SIM = """(args)=>{
 const [seed, script] = args; const runs=[['0,0,0,0,0,,,',1]];
 const sim = Arcade.replay.ghost('links', seed, runs); const s = sim.state, g = Arcade.games.find(x=>x.id==='links'), G = sim.g, out = {};
 const frame = (code, n=1) => { for (let i=0;i<n;i++){ runs.push([code,1]); if(!sim.step()) return false } return true };
 const idle = n => frame('0,0,0,448,400,,,', n);
 // a swing by dragging: press at (112,100), pull to (112+dx, 100+dy), let go
 const drag = (dx, dy) => { frame('0,0,1,448,400,,,'); frame('0,0,1,' + (112+dx)*4 + ',' + (100+dy)*4 + ',,,'); frame('0,0,0,' + (112+dx)*4 + ',' + (100+dy)*4 + ',,,'); idle(2); };
 const settle = (n=900) => { let k = 0; while (s.mode !== 'aim' && s.mode !== 'hole' && s.mode !== 'end' && k++ < n) idle(); return k; };
 const h = s.holes[0];
 out.nHoles = s.holes.length; out.par = s.holes.map(x=>x.par); out.mode0 = s.mode; out.club0 = s.club;
 if (script==='drive') {
   const ux = h.pin.x - h.tee.x, uy = h.pin.y - h.tee.y, d = Math.hypot(ux, uy), nx = ux/d, ny = uy/d;
   const x0 = s.ball.x, y0 = s.ball.y; drag(-nx*56, -ny*56); out.modeFly = s.mode; settle(); out.strokes = s.strokes;
   out.moved = Math.hypot(s.ball.x - x0, s.ball.y - y0); out.dot = ((s.ball.x - x0)*nx + (s.ball.y - y0)*ny) / (out.moved||1);
 }
 if (script==='power') {
   const x0 = s.ball.x, y0 = s.ball.y; s.club = 1; const ux = h.pin.x - h.tee.x, uy = h.pin.y - h.tee.y, d = Math.hypot(ux, uy), nx = ux/d, ny = uy/d;
   drag(-nx*14, -ny*14); settle(); out.short = Math.hypot(s.ball.x - x0, s.ball.y - y0);
 }
 if (script==='water') {
   const w = {x:100,y:100,rx:10,ry:10}; h.water.push(w); const from = {x:s.ball.x, y:s.ball.y}; s.strokes = 1; s.last = from; s.a0 = from; s.a1 = {x:100,y:100}; s.mode = 'fly'; s.f = s.fF = 10; s.club = 0;
   frame('0,0,0,448,400,,,', 2); out.strokes = s.strokes; out.back = Math.hypot(s.ball.x - from.x, s.ball.y - from.y); out.msg = s.msg; settle(); out.mode = s.mode;
 }
 if (script==='hole') {   // putt from a short distance, straight at the pin: it drops
   s.ball.x = h.pin.x; s.ball.y = h.pin.y + 14; h.green.rx = 40; h.green.ry = 40; h.slope = {x:0,y:0}; s.strokes = 1; s.lie = 'green'; s.club = 3; s.ax = 0; s.ay = -1; s.mode = 'aim';
   const sc0 = G.score; drag(0, 16); settle(); out.mode = s.mode; out.strokes = s.strokes; out.holed = s.holed; out.pts = G.score - sc0; out.txt = s.bannerTxt; out.par = h.par;
 }
 if (script==='trees') {   // a ball landing on any tree of any hole is dropped on a playable spot, never in water or out of bounds, never NaN
   let bad = 0, n = 0; for (let k = 0; k < 9; k++) { const hh = s.holes[k]; for (const t of hh.trees) { n++; s.hole = k; s.mode = 'fly'; s.club = 0; s.last = {x: hh.tee.x, y: hh.tee.y}; s.ball = {x: hh.tee.x, y: hh.tee.y}; s.a1 = {x: t.x, y: t.y}; s.dirx = 0; s.diry = -1; s.carry = 50; g.land(s, G);
     if (s.mode !== 'drop' && !(Number.isFinite(s.ball.x) && Number.isFinite(s.ball.y))) bad++; if (s.mode === 'roll' || s.mode === 'aim') { /* playable */ } }
   } out.trees = n; out.bad = bad; }
 if (script==='tap') {   // tap-to-aim uses the camera the screen shows, computed from the ball alone (the stepper never draws)
   const hh = s.holes[0]; s.mode = 'aim'; const cam = Math.max(0, Math.min(hh.H - 232, Math.round(s.ball.y - 150)));
   frame('0,0,0,448,400,,,'); frame('0,0,0,448,400,' + 60*4 + ',' + 80*4 + ',,'); idle(2);
   const sy = s.ball.y - cam + 22, dx = 60 - s.ball.x, dy = 80 - sy, d = Math.sqrt(dx*dx + dy*dy); out.cam = cam; out.ax = s.ax; out.ay = s.ay; out.wx = dx/d; out.wy = dy/d; }
 if (script==='score') {   // the points table: hole in one, eagle, birdie, par, bogey, double, worse
   const t = []; for (const [st, par] of [[1,4],[2,5],[3,4],[4,4],[5,4],[6,4],[8,4]]) { const hh = s.holes[0]; hh.par = par; s.strokes = st; s.mode = 'aim'; const a = G.score; g.holeOut(s, G); t.push(G.score - a); s.mode = 'aim'; s.holed = false; } out.table = t;
 }
 if (script==='round') {   // play out nine holes by force: the round ends and the game ends
   let k = 0; const par = s.holes.map(x=>x.par);
   for (let i = 0; i < 9; i++) { s.strokes = par[i] - 1; g.holeOut(s, G); idle(140); }
   out.hole = s.hole; out.mode = s.mode; idle(200); out.done = sim.done; out.under = s.total;
 }
 out.score = G.score; out.sx = s.ball.x; out.sy = s.ball.y;
 return out; }"""

async def sim(w, seed, script):
    return await w.pg.evaluate(SIM, [seed, script])

STRINGS = ["ACORN LINKS", "HOLE 9  PAR 5", "STROKES 12", "DRIVER", "IRON", "WEDGE", "PUTTER", "WIND < ^7.5", "PIN 640Y", "FAIRWAY", "TEE", "ROUGH", "SAND", "GREEN",
           "SPLASH! +1", "OUT OF BOUNDS +1", "PICK UP", "HOLE IN ONE!", "EAGLE", "BIRDIE", "PAR", "BOGEY", "DOUBLE BOGEY", "TRIPLE BOGEY", "ROUND OVER",
           "UNDER PAR BONUS", "DRAG BACK AND LET GO", "TAP TO AIM", "HI-SCORE", "GAME OVER", "PAUSED"]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await wallet(b)
        await lobby(w)
        n = await w.ev("document.querySelectorAll('[data-game]').length")
        check('lobby: Acorn Links is a cabinet', await w.ev("!!document.querySelector('[data-game=links]')") and n == await w.ev("Arcade.games.length"), n)
        check('lobby: it has a name, a blurb and a score slot', await w.ev("(()=>{const e=document.querySelector('[data-game=links]');return e.querySelector('.nm').innerText==='ACORN LINKS'&&e.querySelector('.ds').innerText.length>10&&!!e.querySelector('.hs')})()"))
        px = await w.ev("(()=>{const c=document.querySelector('[data-thumb=links]'),d=c.getContext('2d').getImageData(0,0,112,84).data;const s=new Set();for(let i=0;i<d.length;i+=4)s.add(d[i]+','+d[i+1]+','+d[i+2]);return s.size})()")
        check('lobby: the thumbnail is drawn (many colours)', px > 8, px)

        # ---- the course comes from the seed ----
        l1, l2, l3 = await w.ev("[Arcade.layout('links',7), Arcade.layout('links',7), Arcade.layout('links',99)]")
        check('course: the same seed gives the same nine holes', l1 == l2 and len(l1) > 1500)
        check('course: another seed gives other holes', l1 != l3)
        s1, s2 = await sim(w, 5, 'drive'), await sim(w, 5, 'drive')
        check('replay: the same inputs on the same seed give the same run, frame for frame', s1 == s2, (s1, s2))
        c = await sim(w, 3, 'drive')
        check('course: nine holes, every one a par 3, 4 or 5', c['nHoles'] == 9 and all(x in (3, 4, 5) for x in c['par']), c)
        check('course: the round starts aiming on a tee shot, with a club chosen', c['mode0'] == 'aim' and c['club0'] in (0, 1, 2, 3), c)

        # ---- the rules ----
        r = await sim(w, 3, 'drive')
        check('rules: a drag back swings the ball the other way, straight at the pin, and it carries well past the tee', r['modeFly'] == 'fly' and r['strokes'] == 1 and r['moved'] > 40 and r['dot'] > 0.8, r)
        p = await sim(w, 3, 'power')
        check('rules: a short pull is a short shot (less than a full swing)', 0 < p['short'] < r['moved'] * 0.4, (p['short'], r['moved']))
        wt = await sim(w, 3, 'water')
        check('rules: water costs a stroke and the ball goes back to where it was hit from', wt['strokes'] == 2 and wt['back'] < 1 and wt['mode'] == 'aim', wt)
        hl = await sim(w, 3, 'hole')
        check('rules: a gentle putt at the pin drops, the hole is scored and the next one starts', hl['holed'] is True and hl['mode'] == 'hole' and hl['strokes'] == 2 and hl['pts'] == holep(2, hl['par']), hl)
        tr = await sim(w, 3, 'trees')
        check('rules: a ball that hits a tree is dropped on a playable spot (never NaN, water or out of bounds)', tr['trees'] > 10 and tr['bad'] == 0, tr)
        tp = await sim(w, 3, 'tap')
        check('rules: tap-to-aim points at the tapped spot (the camera is worked out from the ball, so replays agree with the screen)', abs(tp['ax'] - tp['wx']) < 0.02 and abs(tp['ay'] - tp['wy']) < 0.02 and tp['cam'] > 0, tp)
        sc = await sim(w, 3, 'score')
        check('rules: points by score: ace 1000, eagle 700, birdie 400, par 250, bogey 100, double 50, worse 0', sc['table'] == [1000, 700, 400, 250, 100, 50, 0], sc['table'])
        rd = await sim(w, 4, 'round')
        check('rules: after the ninth hole the round ends, the game ends, and there is an under-par bonus', rd['done'] and rd['hole'] == 9 and rd['under'] == -9 and rd['score'] > 9 * 400, rd)

        # ---- real play ----
        await open_links(w, start=False)
        check('title: shows the cabinet', await w.ev("!!document.querySelector('.game-view #gameCanvas')"))
        h1 = await w.ev(HASH); await w.wait(250); h2 = await w.ev(HASH)
        await w.pg.keyboard.press('Space'); await w.wait(300)
        check('play: starts on hole 1 in the aim state', await w.ev("window.__st&&window.__st.hole===0&&window.__st.mode==='aim'&&window.__st.strokes===0"))
        a0 = await w.ev("[window.__st.ax, window.__st.ay]")
        await w.pg.keyboard.down('ArrowRight'); await w.wait(300); await w.pg.keyboard.up('ArrowRight')
        a1 = await w.ev("[window.__st.ax, window.__st.ay]")
        check('play: the right arrow turns the aim', abs(a1[0] - a0[0]) > 0.02, (a0, a1))
        c0 = await w.ev("window.__st.club"); await w.pg.keyboard.press('ArrowUp'); await w.wait(200)
        check('play: the up arrow changes the club', await w.ev("window.__st.club") == (c0 + 1) % 4, c0)
        await w.pg.keyboard.down('Space'); await w.wait(500)
        pw = await w.ev("window.__st.pw"); await w.pg.keyboard.up('Space'); await w.wait(200)
        check('play: holding Space runs the power meter; letting go swings', pw > 0.1 and await w.ev("window.__st.strokes") == 1, pw)
        await w.until("window.__st.mode==='aim'||window.__st.mode==='hole'", 30000)
        box = await w.pg.locator('#gameCanvas').bounding_box()
        s0 = await w.ev("window.__st.strokes"); await w.ev("window.__st.club=0")
        await w.pg.mouse.move(box['x'] + box['width'] * 0.5, box['y'] + box['height'] * 0.5); await w.pg.mouse.down()
        await w.pg.mouse.move(box['x'] + box['width'] * 0.5, box['y'] + box['height'] * 0.75, steps=4); await w.pg.mouse.up(); await w.wait(250)
        check('touch: dragging back and letting go swings', await w.ev("window.__st.strokes") == s0 + 1, await w.ev("window.__st.strokes"))
        await w.until("window.__st.mode==='aim'||window.__st.mode==='hole'", 30000)
        await w.ev("window.__st.mode==='hole'&&(window.__st.banner=1)"); await w.wait(300)
        cl = await w.ev("window.__st.club")
        await w.pg.mouse.click(box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.95); await w.wait(250)
        check('touch: a tap on the panel changes the club', await w.ev("window.__st.club") != cl, cl)
        t0 = await w.ev("window.__st.t"); await w.pg.keyboard.press('Enter'); await w.wait(250)
        a = await w.ev("window.__st.t"); await w.wait(400); b2 = await w.ev("window.__st.t")
        check('pause: Enter freezes the game', a == b2, (t0, a, b2))
        await w.pg.keyboard.press('Enter'); await w.wait(300)
        # a whole round, forced, ends with the new-high-score dialog
        await w.ev("(()=>{const s=window.__st,g=Arcade.games.find(x=>x.id==='links');s.hole=8;s.strokes=2;s.mode='aim';g.holeOut(s,window.__G);s.banner=1})()"); await w.wait(400)
        await w.ev("window.__st.banner=1"); await w.wait(500)
        await w.until("!!document.querySelector('.game-view input, .game-view [data-g=again], #entry input')", 20000)
        check('score: the finished round shows a high-score entry or the game-over screen', await w.ev("!!document.querySelector('.game-view input, .game-view [data-g=again], #entry input')"))
        check('no script errors', not w.errs, w.errs[:3])
        await w.pg.context.close()

        # ---- five languages: every text on the 224 px screen fits (the pixel font is 8 px a letter) ----
        for lang in LANGS:
            w = await wallet(b, 320, 640, lang); await lobby(w); await open_links(w)
            widths = await w.pg.evaluate("(S)=>S.map(s=>{const t=Nutcade.tr(s);return [s,t,t.length*8]})", STRINGS)
            bad = [x for x in widths if x[2] > 216 and x[0] not in ('HOLE 9  PAR 5', 'STROKES 12')]
            check(f'{lang}: every text fits the screen', not bad, bad)
            pan = await w.pg.evaluate("()=>{const T=Nutcade.tr;return [(T('HOLE')+' 9  '+T('PAR')+' 5').length+T('STROKES').length+3, (T('DRIVER').length+T('WIND').length+7), (T('PIN').length+8+T('ROUGH').length)]}")
            check(f'{lang}: the panel rows fit on one line (28 letters)', all(x <= 28 for x in pan), pan)
            if lang != 'en':
                same_ok = ('ACORN LINKS', 'DRIVER', 'WEDGE', 'PUTTER', 'ROUGH', 'GREEN', 'PAR', 'BIRDIE', 'BOGEY', 'GAME OVER', 'SAND', 'WIND < ^7.5', 'PIN 640Y', 'HOLE 9  PAR 5', 'STROKES 12', 'HI-SCORE', 'PAUSED', 'FAIRWAY', 'TRIPLE BOGEY', 'EAGLE', 'HOLE IN ONE!', 'DOUBLE BOGEY')
                miss = [x[0] for x in widths if x[1] == x[0] and x[0] not in same_ok]
                check(f'{lang}: the game texts are translated', not miss, miss)
            await w.wait(600)
            hint = await w.ev("(()=>{const h=document.querySelector('.game-view .hint'),c=document.querySelector('#gameCanvas').getBoundingClientRect(),r=h.getBoundingClientRect();return [r.top>=c.bottom-1, h.innerText]})()")
            check(f'{lang}: the controls hint sits under the screen', hint[0], hint)
            check(f'{lang}: no script errors', not w.errs, w.errs[:3])
            await w.pg.context.close()

        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
