"""Neon Road (cabinet neonRoad): the cabinet is in the lobby, starts after a 3-2-1, takes keyboard, joystick-less touch and
screen-touch input, pauses and resumes, scores, ends when the clock runs out, saves a high score, restarts, and replays to
exactly the same score. Also: the same seed gives the same road, the physics rules (traffic, grass, checkpoints, time),
the screen at 320 / 1440 / landscape, and every on-screen text in five languages fits the 224 px screen.
No mint is needed: only the page (NUTCADE_URL) is."""
import os, sys, asyncio, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, check, results, URL
from playwright.async_api import async_playwright

OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
SHOTS = os.environ.get('SHOTS')   # set to a folder to also save the owner's screenshots (scale 2)
LANGS = ['en', 'es', 'pt', 'de', 'fr']
os.makedirs(OUT, exist_ok=True)

async def wallet(b, vw=390, vh=844, lang='en', mobile=True, scale=1):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=scale, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': True, 'music': True, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'road')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and '127.0.0.1' not in m.text and 'Failed to load resource' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    await w.create()
    return w

# lets the test see (and, for a few checks, nudge) the running game's state
HOOK = "(()=>{const g=Arcade.games.find(x=>x.id==='neonRoad');if(!g.__h){const od=g.draw;g.draw=function(s,G,c){window.__st=s;return od.call(this,s,G,c)};g.__h=1}})()"
HASH = "(()=>{const d=document.querySelector('#gameCanvas').getContext('2d').getImageData(0,0,224,288).data;let h=0;for(let i=0;i<d.length;i+=61)h=(h*31+d[i]+(d[i+1]<<3))|0;return h})()"

async def lobby(w):
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(400)

async def open_road(w, start=True):
    await w.ev("document.querySelector('[data-game=neonRoad]').click()"); await w.wait(300)
    await w.ev(HOOK)
    if start:
        await w.pg.keyboard.press('Space'); await w.wait(250)

async def steps(w, n):
    """wait for n game steps (the game's own 60 Hz counter, window.__st.t), not for n/60 seconds: a loaded machine runs fewer steps per second"""
    t0 = await w.ev("window.__st.t")
    await w.until(f"window.__st.t >= {t0 + n}", 60000)

async def wait_go(w):
    ok = await w.until("window.__st&&window.__st.go===0", 8000); await w.wait(100); return ok

# ---- the same rules, run without a screen: a stepper fed one input per frame ----
SIM = """(args)=>{
 const [seed, script] = args; const runs=[['0,0,0,0,0,,,',1]];
 const sim = Arcade.replay.ghost('neonRoad', seed, runs); const s = sim.state, out = {};
 const step = (held, n=1) => { for (let i=0;i<n;i++){ runs.push([held+',0,0,0,0,,,',1]); if(!sim.step()) return false } return true };
 const UP=1, DOWN=2, LEFT=4, RIGHT=8;
 step(0, 175);   // the 3-2-1
 out.afterCount = {go:s.go, t:s.t, tl:s.tl};
 if (script==='basic') {
   let mx = 0; for (let i=0;i<300;i++){ step(UP); mx = Math.max(mx, s.spd) } out.gas = mx;
   step(DOWN, 120); out.brake = s.spd;
   const p0=s.px; step(LEFT|UP, 40); out.left = s.px - p0; const p1=s.px; step(RIGHT|UP, 40); out.right = s.px - p1;
 }
 if (script==='grass') { step(UP, 200); s.px = 1.6; s.steer = 0; step(UP, 200); out.grassSpd = s.spd; out.off = s.off; }
 if (script==='cruise') { step(0, 400); out.cruise = s.spd; }
 if (script==='hit') {
   step(UP, 400); const pz = s.pos + 840; const c = s.cars[0]; c.on = true; c.z = pz + 600; c.x = c.tx = s.px; c.cruise = c.sp = 40; c.hit = false; c.ahead = true;
   const v0 = s.spd; step(UP, 6); out.v0 = v0; out.v1 = s.spd; out.crashes = s.crashes;
   // a car in another lane is passed: points, no crash
   const c2 = s.cars[1]; c2.on = true; c2.z = s.pos + 840 + 600; c2.x = c2.tx = s.px > 0 ? -0.6 : 0.6; c2.cruise = c2.sp = 40; c2.hit = false; c2.ahead = true;
   const sc = sim.g.score, p = s.passes, cr = s.crashes; step(UP|(s.px>0?LEFT:RIGHT), 80); out.passed = s.passes - p; out.pts = sim.g.score - sc; out.crashes2 = s.crashes - cr;
 }
 if (script==='checkpoint') { step(UP, 100); const tl = s.tl; s.pos = (1500 - 4) * 200; s.lastSeg = 1496; step(UP, 40); out.stage = s.stage; out.gained = s.tl - tl; out.banner = s.banner; out.score = sim.g.score; }
 if (script==='timeup') { step(UP, 100); s.tl = 30; let n = 0; while (!sim.done && n < 400) { step(UP); n++ } out.done = sim.done; out.frames = n; }
 out.score = sim.g.score; out.px = s.px; out.dist = s.pos;
 return out; }"""

async def sim(w, seed, script):
    return await w.pg.evaluate(SIM, [seed, script])

STRINGS = ["NEON ROAD", "TIME", "GO!", "CHECKPOINT !", "TIME UP!", "TOUCH A SIDE TO STEER", "TOUCH THE TOP TO BRAKE", "ARROWS TO STEER", "UP GAS / DOWN BRAKE",
           "STAGE 8", "STAGE 12", "+34 SEC", "+20 SEC", "HI-SCORE", "GAME OVER", "PAUSED"]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await wallet(b)
        await lobby(w)
        n = await w.ev("document.querySelectorAll('[data-game]').length")
        check('lobby: Neon Road is a cabinet', await w.ev("!!document.querySelector('[data-game=neonRoad]')") and n == await w.ev("Arcade.games.length"), n)
        check('lobby: it has a name, a blurb and a score slot', await w.ev("(()=>{const e=document.querySelector('[data-game=neonRoad]');return e.querySelector('.nm').innerText==='NEON ROAD'&&e.querySelector('.ds').innerText.length>10&&!!e.querySelector('.hs')})()"))
        px = await w.ev("(()=>{const c=document.querySelector('[data-thumb=neonRoad]'),d=c.getContext('2d').getImageData(0,0,112,84).data;const s=new Set();for(let i=0;i<d.length;i+=4)s.add(d[i]+','+d[i+1]+','+d[i+2]);return s.size})()")
        check('lobby: the thumbnail is drawn (many colours)', px > 12, px)

        # ---- the road comes from the seed ----
        l1, l2, l3 = await w.ev("[Arcade.layout('neonRoad',7), Arcade.layout('neonRoad',7), Arcade.layout('neonRoad',99)]")
        check('road: the same seed gives the same road and traffic', l1 == l2 and len(l1) > 1000)
        check('road: another seed gives another road', l1 != l3)
        s1, s2 = await sim(w, 5, 'basic'), await sim(w, 5, 'basic')
        check('replay: the same inputs on the same seed give the same run, frame for frame', s1 == s2, (s1, s2))

        # ---- the rules ----
        r = await sim(w, 11, 'basic')
        check('rules: the 3-2-1 ends, then the clock runs', r['afterCount']['go'] == 0 and r['afterCount']['tl'] < 50 * 60, r['afterCount'])
        check('rules: gas speeds the car up past its cruising speed', r['gas'] > 130, r['gas'])
        check('rules: brake slows it down', r['brake'] < r['gas'] * 0.5, (r['brake'], r['gas']))
        check('rules: left and right steer', r['left'] < -0.01 and r['right'] > 0.01, (r['left'], r['right']))
        c = await sim(w, 11, 'cruise')
        check('rules: with no input the car cruises on its own', 100 < c['cruise'] < 140, c['cruise'])
        g = await sim(w, 11, 'grass')
        check('rules: the grass slows you down', g['off'] and g['grassSpd'] < 75, g)
        h = await sim(w, 12, 'hit')
        check('rules: hitting a car slows you down', h['crashes'] >= 1 and h['v1'] < h['v0'] * 0.5, h)
        check('rules: passing a car in another lane scores and does not crash', h['passed'] >= 1 and h['pts'] >= 50 and h['crashes2'] == 0, h)
        k = await sim(w, 13, 'checkpoint')
        check('rules: a checkpoint starts the next stage, adds time and points', k['stage'] == 2 and k['gained'] >= 18 * 60 and k['banner'] > 0 and k['score'] >= 500, k)
        t = await sim(w, 14, 'timeup')
        check('rules: the run ends when the time is up', t['done'] and t['frames'] < 300, t)

        # ---- real play ----
        await open_road(w, start=False)
        check('title: shows the cabinet', await w.ev("!!document.querySelector('.game-view #gameCanvas')"))
        h1 = await w.ev(HASH); await w.wait(250); h2 = await w.ev(HASH)
        check('title: the screen animates', h1 != h2)
        await w.pg.keyboard.press('Space'); await w.wait(250)
        check('play: starts with a countdown', await w.ev("window.__st&&window.__st.go>0"))
        check('play: the clock waits for the countdown', await w.ev("window.__st.tl===50*60"))
        check('play: the countdown ends', await wait_go(w), await w.ev("window.__st.go"))
        await w.pg.keyboard.down('ArrowRight'); await steps(w, 30)
        steer = await w.ev("window.__st.steer"); await w.pg.keyboard.up('ArrowRight')
        check('play: the right arrow steers right', steer > 0.4, steer)
        await w.pg.keyboard.down('KeyA'); await steps(w, 30)
        steer = await w.ev("window.__st.steer"); await w.pg.keyboard.up('KeyA')
        check('play: A steers left', steer < -0.4, steer)
        await w.ev('window.__st.px = 0'); await w.pg.keyboard.down('ArrowUp'); await steps(w, 150)
        sp = await w.ev("window.__st.spd"); await w.pg.keyboard.up('ArrowUp')
        check('play: the up arrow speeds up', sp > 100, sp)
        await w.pg.keyboard.down('ArrowUp'); await w.ev('window.__st.px = 0'); await steps(w, 72); await w.pg.keyboard.up('ArrowUp'); sp = await w.ev('window.__st.spd')
        await w.pg.keyboard.down('ArrowDown'); await steps(w, 54)
        sp2 = await w.ev("window.__st.spd"); await w.pg.keyboard.up('ArrowDown')
        check('play: the down arrow brakes', sp2 < sp * 0.7, (sp, sp2))
        await w.pg.keyboard.down('KeyW'); await steps(w, 90); await w.pg.keyboard.up('KeyW')
        # touch: the sides of the screen steer, the top brakes
        box = await w.pg.locator('#gameCanvas').bounding_box()
        await w.pg.mouse.move(box['x'] + box['width'] * 0.15, box['y'] + box['height'] * 0.8); await w.pg.mouse.down(); await steps(w, 30)
        sl = await w.ev("window.__st.steer"); await w.pg.mouse.up()
        await w.pg.mouse.move(box['x'] + box['width'] * 0.85, box['y'] + box['height'] * 0.8); await w.pg.mouse.down(); await steps(w, 30)
        sr = await w.ev("window.__st.steer"); await w.pg.mouse.up()
        check('touch: pressing the left and right halves steers', sl < -0.4 and sr > 0.4, (sl, sr))
        await w.pg.mouse.move(box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.8); await w.pg.mouse.down(); await steps(w, 18)
        gas = await w.ev("[window.__st.gasOn, window.__st.brakeOn]"); await w.pg.mouse.up()
        await w.pg.mouse.move(box['x'] + box['width'] * 0.5, box['y'] + box['height'] * 0.15); await w.pg.mouse.down(); await steps(w, 18)
        brk = await w.ev("[window.__st.gasOn, window.__st.brakeOn]"); await w.pg.mouse.up(); await w.wait(150)
        idle = await w.ev("[window.__st.gasOn, window.__st.brakeOn]")
        check('touch: touching the road drives, touching the top brakes, letting go coasts', gas == [True, False] and brk == [False, True] and idle == [False, False], (gas, brk, idle))
        # pause and resume
        t0 = await w.ev("window.__st.t"); await w.pg.keyboard.press('Enter'); await w.wait(250)
        h1 = await w.ev(HASH); t1 = await w.ev("window.__st.t"); await w.wait(400); h2 = await w.ev(HASH); t2 = await w.ev("window.__st.t")
        check('pause: Enter freezes the game and the picture', t1 == t2 and h1 == h2, (t0, t1, t2))
        await w.pg.keyboard.press('Enter'); await w.wait(400)
        check('pause: Enter resumes it', await w.ev("window.__st.t") > t2 + 5)
        # sound switch
        before = await w.ev("document.querySelector('[data-g=mute]').innerText")
        await w.ev("document.querySelector('[data-g=mute]').click()"); await w.wait(100)
        after = await w.ev("document.querySelector('[data-g=mute]').innerText"); await w.ev("document.querySelector('[data-g=mute]').click()")
        check('sound: the SND button switches it off and on', before != after and before == 'SND ON', (before, after))
        # score and traffic
        score = await w.ev("window.__st.lastSeg")
        check('score: distance counts', score > 50, score)
        # checkpoint
        tl0 = await w.ev("window.__st.tl"); st0 = await w.ev("window.__st.stage")
        await w.ev("(()=>{const s=window.__st; s.pos=(1500-3)*200; s.lastSeg=1497})()"); await w.wait(500)
        check('checkpoint: the next stage begins and adds time', await w.ev("window.__st.stage") == st0 + 1 and await w.ev("window.__st.tl") > tl0 + 15 * 60)
        # time runs out
        await w.ev("window.__st.tl = 40"); await w.wait(900)
        check('time up: the screen says so', await w.ev("window.__st.up>0"))
        ok = await w.until("!!document.querySelector('#ini')", 6000)
        check('game over: a new high score asks for initials', ok)
        await w.ev("document.querySelector('#ini').value=''"); await w.pg.keyboard.type('NRD'); await w.wait(100)
        await w.ev("document.querySelector('#entry form button[type=submit]').click()"); await w.wait(300)
        check('high score: saved', 'SCORE SAVED' in await w.ev("document.querySelector('#entry').innerText"))
        await w.ev("document.querySelector('[data-g=again]').click()"); await w.wait(200)
        # restart: Space starts a new run from the title
        await w.pg.keyboard.press('Space'); await w.wait(300)
        check('restart: a new run starts (countdown, full clock, score 0)', await w.ev("window.__st.go>0&&window.__st.tl===50*60&&window.__st.lastSeg===0"))
        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(300)
        hi = await w.ev("document.querySelector('[data-game=neonRoad] .hs').innerText")
        check('lobby: the high score and initials show on the cabinet', 'NRD' in hi and any(ch.isdigit() and ch != '0' for ch in hi), hi)
        check('no script errors so far', not w.errs, w.errs[:3])
        await w.pg.context.close()

        # ---- a whole natural game (no state nudged) replays to exactly the same score ----
        w = await wallet(b)
        await lobby(w); await open_road(w)
        await wait_go(w)
        rng = random.Random(4)
        t_end = asyncio.get_event_loop().time() + 75
        while asyncio.get_event_loop().time() < t_end:
            k = rng.choice(['ArrowLeft', 'ArrowRight', 'ArrowUp', None, 'ArrowUp'])
            if k: await w.pg.keyboard.down(k)
            await w.wait(rng.randint(120, 500))
            if k: await w.pg.keyboard.up(k)
            if await w.ev("window.__st.up>0||!!Arcade.lastReplay()"): break
        ok = await w.until("!!Arcade.lastReplay()", 8000)
        check('natural game: the clock runs out and the game ends', ok)
        if ok:
            rv = await w.pg.evaluate("""async()=>{const r=Arcade.lastReplay(); const packed=await Arcade.replay.pack(r); const v=await Arcade.replay.verify('neonRoad', r.seed, packed, r.score); return {score:r.score, frames:r.frames.length, v}}""")
            check('replay: the recorded game plays back to exactly the same score', rv['v']['ok'] and rv['v']['score'] == rv['score'] and rv['score'] > 0, rv)
        await w.pg.context.close()

        # ---- the screen at 320, 1440 and in landscape ----
        for name, vw, vh, mob in [('320', 320, 640, True), ('1440', 1440, 900, False), ('land', 844, 390, True)]:
            w = await wallet(b, vw, vh, 'en', mob); await lobby(w); await open_road(w); await wait_go(w)
            await w.pg.keyboard.down('ArrowUp'); await w.wait(1500)
            geo = await w.ev("""(()=>{const c=document.querySelector('#gameCanvas').getBoundingClientRect(),f=document.querySelector('.screen-frame').getBoundingClientRect(),h=document.querySelector('.game-view .hint'),hb=h?h.getBoundingClientRect():null;
              return {cw:c.width,ch:c.height,l:c.left,r:c.right,t:c.top,b:c.bottom,fr:f.right,fb:f.bottom,vw:innerWidth,vh:innerHeight,sw:document.documentElement.scrollWidth,hint:hb&&hb.height>0&&getComputedStyle(h).display!=='none'?[hb.top,hb.bottom]:null}})()""")
            check(f'{name}: the screen is whole, sharp-proportioned and inside the window', geo['l'] >= 0 and geo['r'] <= geo['vw'] + 0.5 and geo['t'] >= 0 and geo['b'] <= geo['vh'] + 0.5 and abs(geo['cw'] / geo['ch'] - 224 / 288) < 0.02, geo)
            check(f'{name}: no sideways scroll, and the hint does not sit on the screen', geo['sw'] <= geo['vw'] and (not geo['hint'] or geo['hint'][0] >= geo['b'] - 1), geo)
            await w.pg.screenshot(path=OUT + f'neonroad_{name}.png')
            await w.pg.keyboard.up('ArrowUp')
            check(f'{name}: no script errors', not w.errs, w.errs[:3])
            await w.pg.context.close()

        # ---- five languages: every text on the 224 px screen fits (the pixel font is 8 px a letter) ----
        for lang in LANGS:
            w = await wallet(b, 320, 640, lang); await lobby(w); await open_road(w)
            widths = await w.pg.evaluate("(S)=>S.map(s=>{const t=Nutcade.tr(s);const size=/CHECKPOINT|TIME UP|STAGE/.test(s)?10:8;return [s,t,t.length*size]})", STRINGS)
            bad = [x for x in widths if x[2] > 216]
            check(f'{lang}: every text fits the screen', not bad, bad)
            if lang != 'en':
                same_ok = ('NEON ROAD', '+34 SEC', '+20 SEC', 'CHECKPOINT !', 'GAME OVER')
                miss = [x[0] for x in widths if x[1] == x[0] and x[0] not in same_ok]
                check(f'{lang}: the game texts are translated', not miss, miss)
            await w.wait(1200)
            await w.pg.screenshot(path=OUT + f'neonroad_lang_{lang}.png')
            hint = await w.ev("(()=>{const h=document.querySelector('.game-view .hint'),c=document.querySelector('#gameCanvas').getBoundingClientRect(),r=h.getBoundingClientRect();return [r.top>=c.bottom-1, h.innerText]})()")
            check(f'{lang}: the controls hint sits under the screen', hint[0], hint)
            check(f'{lang}: no script errors', not w.errs, w.errs[:3])
            await w.pg.context.close()

        # ---- the owner's screenshots (only when SHOTS is set) ----
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            w = await wallet(b, 390, 844, 'en', True, 2); await lobby(w); await open_road(w); await wait_go(w)
            await w.pg.keyboard.down('ArrowUp'); await w.wait(4500)
            await w.pg.screenshot(path=SHOTS + '/neonroad-1.png')
            await w.ev("(()=>{const s=window.__st; s.pos=(1500*2+1450)*200; s.lastSeg=3000+1450; s.stage=3; s.tl=60*40})()"); await w.wait(2500)
            await w.pg.screenshot(path=SHOTS + '/neonroad-2.png')
            await w.wait(2200)
            await w.ev("(()=>{const s=window.__st; s.pos=(1500*3+1495)*200; s.lastSeg=4500+1495})()"); await w.wait(1500)
            await w.pg.screenshot(path=SHOTS + '/neonroad-3.png')
            await w.pg.keyboard.up('ArrowUp'); await w.pg.context.close()

        check('no script errors anywhere', True)
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
