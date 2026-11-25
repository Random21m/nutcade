"""Nut Bowl (cabinet bowl): in the lobby, the computer's drives from the seed, the rules (downs, first downs, touchdowns, tackles, passes, kicks, turnovers, the clock and the end of the game),
real play with the keyboard and a tap on the play buttons, whole games played by a bot and replayed to the same score,
a high score at the end of a game, and every on-screen text in five languages fits the 224 px screen.
No mint is needed: only the page (NUTCADE_URL) is."""
import os, sys, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import outside_net, W, check, results, URL
from playwright.async_api import async_playwright

OUT = os.environ.get('QA_OUT', '/tmp/qa-out') + '/'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
os.makedirs(OUT, exist_ok=True)

async def wallet(b, vw=390, vh=844, lang='en', mobile=True):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    prefs = {'sound': True, 'music': True, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'bowl')
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and '127.0.0.1' not in m.text and 'Failed to load resource' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    await w.create()
    return w

HOOK = "(()=>{const g=Arcade.games.find(x=>x.id==='bowl');if(!g.__h){const od=g.draw;g.draw=function(s,G,c){window.__st=s;window.__G=G;return od.call(this,s,G,c)};g.__h=1}})()"
HASH = "(()=>{const d=document.querySelector('#gameCanvas').getContext('2d').getImageData(0,0,224,288).data;let h=0;for(let i=0;i<d.length;i+=61)h=(h*31+d[i]+(d[i+1]<<3))|0;return h})()"

async def lobby(w):
    await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(400)

async def open_bowl(w, start=True):
    await w.ev("document.querySelector('[data-game=bowl]').click()"); await w.wait(300)
    await w.ev(HOOK)
    if start:
        await w.pg.keyboard.press('Space'); await w.wait(250)

SIM = """(args)=>{
 const [seed, script] = args; const runs=[['0,0,0,0,0,,,',1]];
 const sim = Arcade.replay.ghost('bowl', seed, runs); const s = sim.state, g = Arcade.games.find(x=>x.id==='bowl'), G = sim.g, out = {};
 const fr = (held, hit, tx, ty) => { runs.push([held + ',' + hit + ',0,448,400,' + (tx === undefined ? '' : tx*4) + ',' + (ty === undefined ? '' : ty*4) + ',', 1]); return sim.step(); };
 const idle = n => { for (let i = 0; i < (n||1); i++) fr(0, 0); };
 const until = (f, max) => { let k = 0; while (!f() && k++ < (max||2000)) idle(); return k; };
 const snapUp = idx => { s.cur = idx; fr(16, 16); until(() => s.mode === 'play', 60); };       // choose a play, let it snap
 const yOf = yd => 330 - yd * 3;
 const body = () => ({ mode: s.mode, los: s.los, first: s.first, down: s.down, plays: s.plays, mine: s.mine, cpu: s.cpu, score: G.score, txt: s.bannerTxt, next: s.next, cpuYd: s.cpuYd, clock: Math.round(s.clock * 100) / 100 });
 out.mode0 = s.mode; out.los0 = s.los; out.down0 = s.down; out.n = s.cpuR.length;
 if (script==='dive') {
   snapUp(0); out.modeAfter = s.mode; out.type = s.playType; idle(14); out.hasCar = !!s.car && s.car.role === 'rb';
   let k = 0; while (s.mode === 'play' && k++ < 1500) { let held = 1; fr(held, 0); }
   Object.assign(out, body()); out.frames = sim.frames;
 }
 if (script==='tackle') {
   snapUp(0); idle(14); const c = s.car; const d = s.def[4]; d.x = c.x; d.y = c.y; d.blk = 0; d.stun = 0; idle(2);
   Object.assign(out, body());
 }
 if (script==='td') {
   snapUp(0); idle(14); const c = s.car; c.y = 31; c.vy = -1; const sc = G.score; idle(2);
   Object.assign(out, body()); out.gain = G.score - sc;
 }
 if (script==='first') { const sc = G.score; g.endPlay(s, G, 'tackle', yOf(40)); Object.assign(out, body()); out.gain = G.score - sc; }
 if (script==='short') { s.down = 2; g.endPlay(s, G, 'tackle', yOf(28)); Object.assign(out, body()); }
 if (script==='loss') { s.down = 1; g.endPlay(s, G, 'sack', yOf(19)); Object.assign(out, body()); }
 if (script==='inc') { s.down = 2; g.endPlay(s, G, 'inc', yOf(40)); Object.assign(out, body()); }
 if (script==='downs') { s.down = 4; s.los = 40; s.first = 50; g.endPlay(s, G, 'tackle', yOf(43)); Object.assign(out, body()); }
 if (script==='int') { s.los = 40; g.endPlay(s, G, 'int', yOf(55)); Object.assign(out, body()); }
 if (script==='cpu') {   // after the banner the computer plays its drive from the seeded list
   const e = s.cpuR[0]; g.turnover(s, G, 30, 'TURNOVER ON DOWNS'); s.banner = 1; idle(2);
   out.mode1 = s.mode; out.cpu1 = s.cpu; out.txt1 = s.cpuTxt; out.ourYd = s.ourYd; out.e = e; out.clock = s.clock; s.banner = 1; idle(2); out.mode2 = s.mode; out.los2 = s.los; out.down2 = s.down; out.first2 = s.first;
 }
 if (script==='kick') {
   s.los = 70; s.down = 4; g.newDown(s); fr(0, 0); s.cur = 1; fr(16, 16); idle(1); out.modeKick = s.mode; out.good = s.kick.good; out.kind = s.kick.kind; out.dd = s.kick.dd;
   until(() => s.mode === 'result', 200); Object.assign(out, body());
 }
 if (script==='punt') {
   s.los = 30; s.down = 4; g.newDown(s); fr(0, 0); s.cur = 0; fr(16, 16); idle(1); out.modeKick = s.mode; out.kind = s.kick.kind;
   until(() => s.mode === 'result', 200); Object.assign(out, body());
 }
 if (script==='pass') {
   snapUp(2); out.type = s.playType; idle(14); out.has = s.qbHas; out.ncar = s.car; s.tgt = 0; fr(16, 16); idle(1); out.flying = !!s.pass;
   until(() => !s.pass, 200); out.mode = s.mode; out.caught = !!s.car; out.i = s.car ? s.car.n : 0;
 }
 if (script==='catch') {   // with every defender far away, a thrown pass is caught and the receiver carries the ball
   snapUp(2); idle(14); for (const d of s.def) { d.x = 215; d.y = 300; d.blk = 99999; } g.throwTo(s, G, 1); out.flying = !!s.pass;
   until(() => !s.pass, 200); out.caught = !!s.car && s.car.ctl === true; out.n = s.car ? s.car.n : 0; out.mode = s.mode;
 }
 if (script==='tapthrow') {
   snapUp(3); idle(16); const w = s.wr[2], cam = Math.max(0, Math.min(360 - 206, Math.round(s.fy - 110)));
   fr(0, 0, w.x, w.y - cam + 22); idle(1); out.i = s.pass ? s.pass.i : -1; out.flying = !!s.pass;
 }
 if (script==='cycle') { snapUp(2); idle(14); const t0 = s.tgt; fr(8, 8); idle(1); out.t1 = s.tgt; fr(4, 4); idle(1); out.t2 = s.tgt; out.t0 = t0; }
 if (script==='sack') {   // nobody throws: the rush gets to the quarterback
   snapUp(2); until(() => s.mode !== 'play', 800); Object.assign(out, body());
 }
 if (script==='burst') { snapUp(0); idle(14); const b0 = s.burst; for (let i = 0; i < 10; i++) fr(1 | 16, 0); out.used = b0 - s.burst; out.b0 = b0; }
 if (script==='end') {   // the last play of the game: a win adds the bonus and the game ends
   s.mine = 14; s.cpu = 7; s.clock = 599; const sc = G.score; g.endPlay(s, G, 'tackle', yOf(30)); s.banner = 1; idle(3);
   out.mode = s.mode; out.end = s.end; out.gain = G.score - sc; out.txt = s.bannerTxt; out.clock = s.clock; idle(205); out.done = sim.done;
 }
 if (script==='lasttd') { s.mine = 7; s.cpu = 0; s.clock = 599.9; g.endPlay(s, G, 'td', 31); s.banner = 1; idle(3); out.mode = s.mode; out.cpu = s.cpu; out.txt = s.bannerTxt; }
 if (script==='lose') { s.mine = 0; s.cpu = 3; s.clock = 599; const sc = G.score; g.endPlay(s, G, 'inc', yOf(25)); s.banner = 1; idle(3); out.mode = s.mode; out.txt = s.bannerTxt; out.gain = G.score - sc; }
 if (script==='tie') { s.mine = 7; s.cpu = 7; s.clock = 599; const sc = G.score; g.endPlay(s, G, 'inc', yOf(25)); s.banner = 1; idle(3); out.mode = s.mode; out.txt = s.bannerTxt; out.gain = G.score - sc; }
 if (script==='clock') {   // the clock runs only while the ball is live, and a quarter is 2:30
   const c0 = s.clock; idle(30); out.huddle = s.clock - c0; snapUp(0); idle(60); out.live = s.clock - c0; out.q = g.q(s);
 }
 out.score = G.score; return out; }"""

BOT = """(args)=>{   // a whole game played by a simple bot, then the same inputs replayed
 const [seed] = args; const runs=[['0,0,0,0,0,,,',1]];
 const sim=Arcade.replay.ghost('bowl', seed, runs); const s=sim.state, G=sim.g;
 const fr=(held,hit)=>{runs.push([held+','+hit+',0,448,400,,,',1]); return sim.step();};
 let guard=0;
 while(!sim.done && guard++<300000){
   if(s.mode==='huddle'){ const idx = s.down===4 ? (s.los>=48 ? 1 : 0) : (s.plays*7+s.los)%4; let k=0; while(s.cur!==idx && k++<5){ fr(8,8); fr(0,0); } fr(16,16); }
   else if(s.mode==='play'){
     const c=s.car;
     if(c && c.ctl){ let held=1, near=null, nd=999; for(const d of s.def){ const dx=d.x-c.x, dy=d.y-c.y, dd=Math.sqrt(dx*dx+dy*dy); if(dy<6 && dd<nd){nd=dd;near=d;} }
       if(near && nd<42){ held |= (near.x<c.x ? 8 : 4); } if(c.x<40) held=(held&~4)|8; if(c.x>184) held=(held&~8)|4; if(near && nd<20) held|=16; fr(held,0); }
     else if(s.playType==='pass' && s.qbHas && s.pt>=22){ let best=0,bs=-1; for(let i=0;i<3;i++){ const w=s.wr[i]; let m=999; for(const d of s.def){const dd=Math.sqrt((d.x-w.x)**2+(d.y-w.y)**2); if(dd<m)m=dd;} if(m>bs){bs=m;best=i;} } let k=0; while(s.tgt!==best && k++<5){ fr(8,8); fr(0,0); } fr(16,16); }
     else fr(0,0);
   } else fr(0,0);
 }
 const first = { done: sim.done, score: G.score, mine: s.mine, cpu: s.cpu, plays: s.plays, clock: Math.round(s.clock), frames: sim.frames };
 const sim2 = Arcade.replay.ghost('bowl', seed, runs); while (sim2.step()) {}
 const second = { done: sim2.done, score: sim2.g.score, mine: sim2.state.mine, cpu: sim2.state.cpu, plays: sim2.state.plays, clock: Math.round(sim2.state.clock), frames: sim2.frames };
 return [first, second];
}"""

async def sim(w, seed, script):
    return await w.pg.evaluate(SIM, [seed, script])

STRINGS = ["NUT BOWL", "PICK A PLAY", "TAP A RECEIVER", "BURST", "CAUGHT", "BROKEN TACKLE", "TOUCHDOWN!", "INTERCEPTED!", "TURNOVER ON DOWNS", "FIRST DOWN!", "INCOMPLETE", "SACK", "GAIN", "LOSS", "NO GAIN",
           "KICK GOOD", "NO GOOD", "PUNT", "CPU BALL", "CPU TOUCHDOWN", "CPU FIELD GOAL", "CPU PUNTS", "YOU WIN", "TIE GAME", "YOU LOSE", "HI-SCORE", "GAME OVER", "PAUSED"]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await wallet(b)
        await lobby(w)
        n = await w.ev("document.querySelectorAll('[data-game]').length")
        check('lobby: Nut Bowl is a cabinet', await w.ev("!!document.querySelector('[data-game=bowl]')") and n == await w.ev("Arcade.games.length"), n)
        check('lobby: it has a name, a blurb and a score slot', await w.ev("(()=>{const e=document.querySelector('[data-game=bowl]');return e.querySelector('.nm').innerText==='NUT BOWL'&&e.querySelector('.ds').innerText.length>10&&!!e.querySelector('.hs')})()"))
        px = await w.ev("(()=>{const c=document.querySelector('[data-thumb=bowl]'),d=c.getContext('2d').getImageData(0,0,112,84).data;const s=new Set();for(let i=0;i<d.length;i+=4)s.add(d[i]+','+d[i+1]+','+d[i+2]);return s.size})()")
        check('lobby: the thumbnail is drawn (many colours)', px > 8, px)

        # ---- the game comes from the seed ----
        l1, l2, l3 = await w.ev("[Arcade.layout('bowl',7), Arcade.layout('bowl',7), Arcade.layout('bowl',99)]")
        check('seed: the same seed gives the same game (the computer\'s drives)', l1 == l2 and len(l1) > 1500)
        check('seed: another seed gives other drives', l1 != l3)
        s1, s2 = await sim(w, 5, 'dive'), await sim(w, 5, 'dive')
        check('replay: the same inputs on the same seed give the same play, frame for frame', s1 == s2, (s1, s2))
        c = await sim(w, 3, 'dive')
        check('start: the game opens in the huddle, 1st and 10 at our own 25, with 40 computer drives ready', c['mode0'] == 'huddle' and c['los0'] == 25 and c['down0'] == 1 and c['n'] == 40, c)

        # ---- the rules ----
        r = await sim(w, 3, 'dive')
        check('play: choosing a play snaps the ball, the run is a handoff, and you run until the tackle', r['modeAfter'] == 'play' and r['type'] == 'run' and r['hasCar'] and r['mode'] == 'result' and r['plays'] == 1, r)
        check('play: after a run the down, spot and score follow the yards', (r['down'] == 2 and r['los'] <= 35 and r['txt'] in ('GAIN', 'NO GAIN', 'LOSS')) or (r['down'] == 1 and r['txt'] in ('FIRST DOWN!', 'TOUCHDOWN!')) , r)
        t = await sim(w, 3, 'tackle')
        check('tackle: a defender on the runner ends the play and uses the down', t['mode'] == 'result' and t['down'] == 2 and t['plays'] == 1, t)
        td = await sim(w, 3, 'td')
        check('touchdown: crossing the goal line is 7 points and 800 score, then the computer has the ball', td['mine'] == 7 and td['gain'] == 800 and td['txt'] == 'TOUCHDOWN!' and td['next'] == 'cpu' and td['cpuYd'] == 25, td)
        f = await sim(w, 3, 'first')
        check('first down: 15 yards is 150 points plus 100, the next line is 10 yards on, and it is 1st down again', f['down'] == 1 and f['los'] == 40 and f['first'] == 50 and f['gain'] == 250 and f['txt'] == 'FIRST DOWN!', f)
        sh = await sim(w, 3, 'short')
        check('short gain: the next down, the line stays where it was', sh['down'] == 3 and sh['los'] == 28 and sh['first'] == 35 and sh['txt'] == 'GAIN', sh)
        ls = await sim(w, 3, 'loss')
        check('sack: a loss of yards, the next down, no points for it', ls['down'] == 2 and ls['los'] == 19 and ls['txt'] == 'SACK' and ls['score'] == 0, ls)
        ic = await sim(w, 3, 'inc')
        check('incomplete: no yards, the next down, the clock stops sooner', ic['down'] == 3 and ic['los'] == 25 and ic['txt'] == 'INCOMPLETE' and ic['clock'] == 3, ic)
        dn = await sim(w, 3, 'downs')
        check('4th down: not reaching the line gives the ball to the computer where we stopped', dn['next'] == 'cpu' and dn['txt'] == 'TURNOVER ON DOWNS' and dn['cpuYd'] == 57 and dn['mode'] == 'result', dn)
        it = await sim(w, 3, 'int')
        check('interception: the computer takes over at the spot', it['next'] == 'cpu' and it['txt'] == 'INTERCEPTED!' and it['cpuYd'] == 45, it)
        cp = await sim(w, 3, 'cpu')
        e = cp['e']; pTD = 0.05 + 30 * 0.002; pFG = 0.14
        want = 7 if e['r'] < pTD else 3 if e['r'] < pTD + pFG else 0
        check('computer drive: the result comes from the seeded list (touchdown, field goal or punt) and the clock moves by its time', cp['mode1'] == 'cpu' and cp['cpu1'] == want and cp['clock'] == e['t'] and (cp['ourYd'] == (25 if want else e['p'])), cp)
        check('computer drive: then we get the ball, 1st and 10 in the huddle', cp['mode2'] == 'huddle' and cp['los2'] == cp['ourYd'] and cp['down2'] == 1 and cp['first2'] == cp['ourYd'] + 10, cp)
        k = await sim(w, 3, 'kick')
        check('field goal: the kick flies, and a good one is 3 points and 300 score (a miss is nothing)', k['modeKick'] == 'kick' and k['kind'] == 'fg' and k['dd'] == 47 and k['mode'] == 'result' and ((k['good'] and k['mine'] == 3 and k['score'] == 300 and k['txt'] == 'KICK GOOD') or (not k['good'] and k['mine'] == 0 and k['score'] == 0 and k['txt'] == 'NO GOOD')) and k['next'] == 'cpu', k)
        ok = [await sim(w, sd, 'kick') for sd in range(1, 21)]
        check('field goal: a 47-yard kick is good some of the time (not always, not never)', 3 <= sum(1 for x in ok if x['good']) <= 18, [x['good'] for x in ok])
        pu = await sim(w, 3, 'punt')
        check('punt: the ball goes downfield and the computer starts from there', pu['modeKick'] == 'kick' and pu['kind'] == 'punt' and pu['txt'] == 'PUNT' and 1 <= pu['cpuYd'] <= 80 and pu['next'] == 'cpu', pu)
        ps = await sim(w, 3, 'pass')
        check('pass: a slant has the quarterback with the ball, and A throws to the chosen receiver', ps['type'] == 'pass' and ps['has'] is True and ps['ncar'] is None and ps['flying'] is True and ps['mode'] in ('play', 'result'), ps)
        ct = await sim(w, 3, 'catch')
        check('catch: an open receiver catches it and you run with him', ct['flying'] and ct['caught'] and ct['n'] == 2 and ct['mode'] == 'play', ct)
        tt = await sim(w, 3, 'tapthrow')
        check('touch: a tap on a receiver throws to him', tt['flying'] and tt['i'] == 2, tt)
        cy = await sim(w, 3, 'cycle')
        check('keys: right and left change the target receiver', cy['t1'] == (cy['t0'] + 1) % 3 and cy['t2'] == cy['t0'], cy)
        sk = await sim(w, 3, 'sack')
        check('pass rush: holding the ball too long ends in a sack', sk['mode'] == 'result' and sk['txt'] in ('SACK',) and sk['down'] == 2, sk)
        bu = await sim(w, 3, 'burst')
        check('burst: holding A while running uses up the burst meter', bu['used'] >= 8 and bu['b0'] == 50, bu)
        en = await sim(w, 3, 'end')
        check('end: the last play of a won game adds the 1000 win bonus and the game ends', en['mode'] == 'end' and en['end'] and en['txt'] == 'YOU WIN' and en['gain'] >= 1000 and en['done'] is True, en)
        lt = await sim(w, 3, 'lasttd')
        check('end: a touchdown as time runs out ends the game at once (the computer gets no last drive)', lt['mode'] == 'end' and lt['cpu'] == 0 and lt['txt'] == 'YOU WIN', lt)
        lo = await sim(w, 3, 'lose')
        check('end: a lost game gets no bonus', lo['mode'] == 'end' and lo['txt'] == 'YOU LOSE' and lo['gain'] < 1000, lo)
        ti = await sim(w, 3, 'tie')
        check('end: a tied game gets no bonus', ti['mode'] == 'end' and ti['txt'] == 'TIE GAME' and ti['gain'] < 1000, ti)
        cl = await sim(w, 3, 'clock')
        check('clock: it stands still in the huddle and runs (30 frames = 1 game second) while the ball is live', cl['huddle'] == 0 and 1.9 < cl['live'] < 2.3 and cl['q'] == 0, cl)
        for sd in (2, 9):
            g1, g2 = await w.pg.evaluate(BOT, [sd])
            check(f'whole game (seed {sd}) played by a bot: it ends, every drive is played, and replaying the inputs gives the same game', g1['done'] and g1['plays'] > 15 and g1['clock'] >= 600 and g1 == g2, (g1, g2))

        # ---- real play ----
        await open_bowl(w, start=False)
        check('title: shows the cabinet', await w.ev("!!document.querySelector('.game-view #gameCanvas')"))
        await w.pg.keyboard.press('Space'); await w.wait(300)
        check('play: starts in the huddle, 1st and 10', await w.ev("window.__st&&window.__st.mode==='huddle'&&window.__st.down===1&&window.__st.los===25"))
        await w.pg.keyboard.press('ArrowRight'); await w.wait(200)
        check('play: the right arrow moves along the play buttons', await w.ev("window.__st.cur") == 1)
        await w.pg.keyboard.press('ArrowLeft'); await w.wait(150)
        await w.pg.keyboard.press('Space'); await w.wait(300)
        check('play: A snaps the ball (the dive)', await w.ev("window.__st.mode==='snap'||window.__st.mode==='play'"))
        await w.until("window.__st.mode==='play'&&!!window.__st.car", 5000)
        y0 = await w.ev("window.__st.car.y"); await w.pg.keyboard.down('ArrowUp'); await w.wait(400); await w.pg.keyboard.up('ArrowUp')
        check('play: the up arrow runs the ball up the field', await w.ev("window.__st.car?window.__st.car.y:-1") < y0 or await w.ev("window.__st.mode") == 'result', y0)
        await w.until("window.__st.mode==='huddle'||window.__st.mode==='cpu'||window.__st.mode==='result'", 60000)
        await w.until("window.__st.mode==='huddle'", 20000)
        box = await w.pg.locator('#gameCanvas').bounding_box()
        d0 = await w.ev("window.__st.down+':'+window.__st.los")
        await w.pg.mouse.click(box['x'] + box['width'] * (3 + 2 * 55 + 26) / 224, box['y'] + box['height'] * (250 + 14) / 288); await w.wait(300)
        check('touch: a tap on a play button snaps that play (the slant)', await w.ev("window.__st.play") == 'SLANT' and await w.ev("window.__st.playType") == 'pass', await w.ev("window.__st.play"))
        t0 = await w.ev("window.__st.t"); await w.pg.keyboard.press('Enter'); await w.wait(250)
        a = await w.ev("window.__st.t"); await w.wait(400); b2 = await w.ev("window.__st.t")
        check('pause: Enter freezes the game', a == b2, (t0, a, b2))
        await w.pg.keyboard.press('Enter'); await w.wait(300)
        # the end of a game shows the high-score entry or the game-over screen
        await w.ev("(()=>{const s=window.__st,g=Arcade.games.find(x=>x.id==='bowl');s.mine=14;s.cpu=3;s.clock=599;s.mode='play';s.playType='run';s.car=null;g.endPlay(s,window.__G,'tackle',200);s.banner=1})()"); await w.wait(400)
        await w.ev("window.__st.banner=1"); await w.wait(500)
        await w.until("!!document.querySelector('.game-view input, .game-view [data-g=again], #entry input')", 20000)
        check('score: the finished game shows a high-score entry or the game-over screen', await w.ev("!!document.querySelector('.game-view input, .game-view [data-g=again], #entry input')"))
        check('no script errors', not w.errs, w.errs[:3])
        await w.pg.context.close()

        # ---- five languages: every text on the 224 px screen fits (the pixel font is 8 px a letter) ----
        for lang in LANGS:
            w = await wallet(b, 320, 640, lang); await lobby(w); await open_bowl(w)
            widths = await w.pg.evaluate("(S)=>S.map(s=>{const t=Nutcade.tr(s);return [s,t,t.length*8]})", STRINGS)
            bad = [x for x in widths if x[2] > 216]
            check(f'{lang}: every text fits the screen', not bad, bad)
            pan = await w.pg.evaluate("()=>{const T=Nutcade.tr;return [('Q4 2:30').length+(T('YOU')+' 14 CPU 10').length+3, (T('DOWN')+' 4 & '+T('GOAL')).length+(T('OPP')+' 45').length+3, (T('OWN')+' 45').length, T('BURST').length]}")
            check(f'{lang}: the panel rows fit on one line (28 letters), the burst label leaves room for its bar', pan[0] <= 28 and pan[1] <= 28 and pan[3] <= 9, pan)
            btn = await w.pg.evaluate("()=>['DIVE','SWEEP','SLANT','BOMB','PUNT','KICK'].map(k=>[k,Nutcade.tr(k)])")
            check(f'{lang}: the play button names fit the buttons (6 letters)', all(len(x[1]) <= 6 for x in btn), btn)
            if lang != 'en':
                same_ok = ('NUT BOWL', 'PUNT', 'SACK', 'TOUCHDOWN!', 'CPU TOUCHDOWN', 'CPU FIELD GOAL', 'GAIN', 'GAME OVER', 'HI-SCORE', 'PAUSED')
                miss = [x[0] for x in widths if x[1] == x[0] and x[0] not in same_ok]
                check(f'{lang}: the game texts are translated', not miss, miss)
            await w.wait(600)
            hint = await w.ev("(()=>{const h=document.querySelector('.game-view .hint'),c=document.querySelector('#gameCanvas').getBoundingClientRect(),r=h.getBoundingClientRect();return [r.top>=c.bottom-1, h.innerText]})()")
            check(f'{lang}: the controls hint sits under the screen', hint[0], hint)
            check(f'{lang}: no script errors', not w.errs, w.errs[:3])
            await w.pg.context.close()

        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
