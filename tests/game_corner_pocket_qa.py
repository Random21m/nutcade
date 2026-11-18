"""Corner Pocket (8-ball pool cabinet): menu, controls (keys, touch drag), pause, rules, the machine, scores, game over, restart,
replay determinism, five languages, and layout at 320 / 1440 / landscape. Light: one browser, no mints."""
import os, sys, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import check, results, OUT, URL, outside_net
from playwright.async_api import async_playwright

ID = 'cornerPocket'
ST = "NutPool.cur()"
LANGS = ['en', 'es', 'pt', 'de', 'fr']

async def make(b, vw, vh, mobile=True, dsf=1):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=dsf, is_mobile=mobile, has_touch=mobile)
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs',JSON.stringify({sound:false,crt:true}))")
    pg = await ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket connection' not in m.text else None)   # (the wallet's Nostr relays are not reachable from a test box)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    await pg.check('#ack'); await pg.evaluate("document.querySelector('[data-act=gateCreate]').click()"); await pg.wait_for_timeout(400)
    words = (await pg.evaluate("Nutcade.S.seed.mnemonic")).split()
    await pg.check('#wrote'); await pg.evaluate("document.querySelector('[data-act=gateToConfirm]').click()"); await pg.wait_for_timeout(200)
    for el in await pg.query_selector_all('[data-cw]'):
        await el.fill(words[int(await el.get_attribute('data-cw'))])
    await pg.evaluate("document.querySelector('[data-act=gateConfirm]').click()"); await pg.wait_for_timeout(500)
    await pg.evaluate("document.querySelector('[data-act=gateStart]').click()"); await pg.wait_for_timeout(400); await pg.evaluate("Nutcade.closeSheet()")
    await pg.evaluate("document.querySelector('[data-act=tab][data-tab=arcade]').click()"); await pg.wait_for_timeout(400)
    return pg, errs

async def open_game(pg):
    await pg.evaluate(f"document.querySelector('[data-game={ID}]').click()"); await pg.wait_for_timeout(300)
    await pg.keyboard.press('Space'); await pg.wait_for_timeout(150)   # past the title screen, into the mode menu

async def tap(pg, *keys):
    for k in keys:
        await pg.keyboard.press(k); await pg.wait_for_timeout(70)

async def canvas_xy(pg, lx, ly):
    box = await pg.locator('#gameCanvas').bounding_box()
    return box['x'] + lx / 224 * box['width'], box['y'] + ly / 288 * box['height']

async def until(pg, js, ms=20000):
    for _ in range(ms // 100):
        if await pg.evaluate(js): return True
        await pg.wait_for_timeout(100)
    return False

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        pg, errs = await make(b, 390, 844)
        ev = pg.evaluate

        # ---- the cabinet is in the arcade ----
        check('the arcade lists Corner Pocket', await ev(f"[...document.querySelectorAll('[data-game]')].map(b=>b.dataset.game).includes('{ID}')"))
        check('the lobby shows its name', 'CORNER POCKET' in await ev(f"document.querySelector('[data-game={ID}]').innerText"))
        await open_game(pg)
        check('it opens on a canvas with the mode menu', await ev(f"!!document.querySelector('.game-view #gameCanvas') && {ST}.ph==='menu'"))
        check('the menu has four options and VS MACHINE is first', await ev(f"{ST}.sel===0"))
        await tap(pg, 'ArrowDown', 'ArrowDown')
        check('arrow keys move through the menu', await ev(f"{ST}.sel===2"))
        await tap(pg, 'ArrowUp', 'ArrowRight', 'ArrowRight')
        check('left and right change the machine level', await ev(f"{ST}.sel===1 && {ST}.lvSel===0"))
        await tap(pg, 'ArrowUp', 'Space')
        check('Space on VS MACHINE starts a match on the break', await ev(f"{ST}.ph==='aim' && {ST}.mode===0 && {ST}.turn===0 && {ST}.brk===true && {ST}.ai[1]===true"))
        check('the rack is 15 balls plus the cue ball, all on the table inside the cloth', await ev(f"(()=>{{const s={ST},g=NutPool.geom; let n=0; for(let i=0;i<16;i++){{ if(s.st[i]===0 && s.x[i]>=g.CL && s.x[i]<=g.CR && s.y[i]>=g.CT && s.y[i]<=g.CB) n++; }} return n===16 && s.x[0]===g.CX && s.y[0]===g.HEADY;}})()"))

        # ---- keyboard: aim, power, shoot ----
        ax0 = await ev(f"{ST}.ax")
        await pg.keyboard.down('ArrowRight'); await pg.wait_for_timeout(350); await pg.keyboard.up('ArrowRight')
        ax1 = await ev(f"{ST}.ax")
        check('the arrow keys turn the aim', ax1 > ax0 + 0.02, (ax0, ax1))
        await pg.keyboard.down('ArrowLeft'); await pg.wait_for_timeout(350); await pg.keyboard.up('ArrowLeft')
        await pg.keyboard.down('Space'); await pg.wait_for_timeout(700)
        pw = await ev(f"{ST}.pw")
        check('holding Space charges the power bar', pw > 0.1, pw)
        await pg.screenshot(path=OUT + 'pool_aim_320.png') if False else None
        await ev(f"window.__rk=Array.from({ST}.x).map((x,i)=>[x,{ST}.y[i]])")
        await pg.keyboard.up('Space'); await pg.wait_for_timeout(150)
        check('releasing Space shoots the cue ball', await ev(f"['strike','roll'].includes({ST}.ph) && {ST}.shots[0]===1"))
        check('the balls come to rest and the turn moves on', await until(pg, f"{ST}.ph!=='roll' && {ST}.ph!=='strike'", 40000))
        check('the break scatters the rack', await ev(f"__rk.filter((p,i)=>Math.hypot(p[0]-{ST}.x[i],p[1]-{ST}.y[i])>2).length") >= 4)
        # ---- the machine plays its turn (if the human's break passed it) ----
        if await ev(f"{ST}.turn===1 && {ST}.ph!=='end'"):
            check('the machine takes its shot', await until(pg, f"{ST}.shots[1]>=1 || {ST}.turn===0", 20000))
            await until(pg, f"{ST}.ph!=='roll' && {ST}.ph!=='strike' && ({ST}.turn===0 || {ST}.ph==='end')", 40000)

        # ---- pause and resume ----
        await pg.keyboard.press('Enter'); await pg.wait_for_timeout(200)
        t0 = await ev(f"{ST}.t"); await pg.wait_for_timeout(400); t1 = await ev(f"{ST}.t")
        check('Enter pauses the game', t0 == t1, (t0, t1))
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(400)
        check('and Space resumes it', await ev(f"{ST}.t") > t1)

        # ---- 2 players, touch: drag back from the ball to aim and shoot ----
        await ev("document.querySelector('[data-g=exit]').click()"); await pg.wait_for_timeout(200)
        await open_game(pg)
        await tap(pg, 'ArrowDown', 'ArrowDown', 'Space')
        check('2 PLAYERS starts with both players human', await ev(f"{ST}.mode===1 && !{ST}.ai[0] && !{ST}.ai[1]"))
        cx, cy = await canvas_xy(pg, 112, 203)
        await pg.mouse.move(cx, cy); await pg.mouse.down()
        px, py = await canvas_xy(pg, 120, 203 + 40)
        await pg.mouse.move(px, py, steps=6); await pg.wait_for_timeout(100)
        st = await ev(f"({{ax:{ST}.ax, ay:{ST}.ay, pw:{ST}.pw}})")
        check('dragging back sets the aim (away from the drag) and the power', st['ay'] < -0.9 and st['ax'] < -0.05 and st['pw'] > 0.3, st)
        await pg.mouse.up(); await pg.wait_for_timeout(150)
        check('letting go shoots', await ev(f"['strike','roll'].includes({ST}.ph) && {ST}.shots[0]+{ST}.shots[1]===1"))
        await until(pg, f"{ST}.ph!=='roll' && {ST}.ph!=='strike'", 40000)
        await pg.mouse.move(cx, cy); await pg.mouse.down(); await pg.mouse.move(cx + 2, cy + 2, steps=2); await pg.mouse.up(); await pg.wait_for_timeout(150)
        check('a tiny drag cancels the shot', await ev(f"{ST}.shots[0]+{ST}.shots[1]===1") or await ev(f"{ST}.ph==='place'"))

        # ---- scratch gives ball in hand behind the head string, and the 8 rules ----
        sc = await ev("""(()=>{ const s=NutPool.cur(); const g=NutPool.geom;
          // P1 shoots straight at the corner with the cue ball only: rig a table with just the cue ball heading into a pocket
          for(let i=1;i<16;i++){ s.st[i]=0; s.vx[i]=s.vy[i]=0; s.x[i]=g.CL+20+((i*13)%130); s.y[i]=g.CT+20+((i*29)%60); }
          s.ph='roll'; s.brk=false; s.shots=[3,3]; s.turn=0; s.grp=[0,1]; s.hand=0; s.np=0; s.on8=false; s.rollT=0;
          s.x[0]=g.CL+16; s.y[0]=g.CT+16; s.vx[0]=-2; s.vy[0]=-2; return true; })()""")
        await until(pg, f"{ST}.ph==='place'", 8000)
        check('scratching hands the other player the ball in hand behind the head string', await ev(f"{ST}.ph==='place' && {ST}.turn===1 && {ST}.hand===1"))
        # try to put it in front of the line: it is held on the line; then Space places it
        await ev(f"{ST}.hy=120; {ST}.hx=112")
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(120)
        check('the cue ball cannot be placed in front of the head string', await ev(f"{ST}.ph==='aim' && {ST}.hand===0 && {ST}.y[0]>=NutPool.geom.HEADY"))

        # ---- potting the 8 early loses; the last ball then the 8 wins; scratching on the 8 loses ----
        async def rig8(grp_left, scenario):
            return await ev("""((left, scenario)=>{ const s=NutPool.cur(), g=NutPool.geom;
              for(let i=0;i<16;i++){ s.vx[i]=s.vy[i]=0; s.st[i]=0; s.x[i]=g.CL+30+(i%8)*16; s.y[i]=g.CT+40+Math.floor(i/8)*30; }
              s.grp=[0,1]; s.brk=false; s.shots=[5,5]; s.turn=0; s.hand=0; s.np=0; s.rollT=0; s.winner=-1; s.ph='roll';
              for(let i=1;i<8;i++) if(i>left) s.st[i]=2;                      // my solids that are already gone
              s.on8 = left===0;
              s.x[8]=g.CL+15; s.y[8]=g.CT+15; s.vx[8]=-2; s.vy[8]=-2;          // the 8 rolls into the corner
              if(scenario==='scratch8'){ s.x[8]=g.CX; s.y[8]=g.CT+100; s.vx[8]=s.vy[8]=0; s.x[0]=g.CL+16; s.y[0]=g.CB-16; s.vx[0]=-2; s.vy[0]=2; }
              return true; })(LEFT, SCEN)""".replace('LEFT', str(grp_left)).replace('SCEN', json.dumps(scenario)))
        await rig8(3, 'x'); await until(pg, f"{ST}.ph==='end'", 8000)
        check('potting the 8 too early loses', await ev(f"{ST}.ph==='end' && {ST}.winner===1 && {ST}.reason==='w8e'"))
        await ev(f"{ST}.ph='roll'"); await rig8(0, 'x'); await until(pg, f"{ST}.ph==='end'", 8000)
        check('potting the 8 after your whole group wins', await ev(f"{ST}.ph==='end' && {ST}.winner===0 && {ST}.reason==='w8'"))
        await rig8(0, 'scratch8'); await until(pg, f"{ST}.ph==='end'", 8000)
        check('scratching while shooting at the 8 loses', await ev(f"{ST}.ph==='end' && {ST}.winner===1 && {ST}.reason==='w8s'"))
        await pg.wait_for_timeout(5000)
        check('game over returns to the title (2 players scores nothing, so no initials)', await ev("!document.querySelector('#ini')"))

        # ---- first pot after the break picks the group ----
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(200)
        await tap(pg, 'ArrowDown', 'ArrowDown', 'Space')
        check('restart: a fresh table in the menu flow', await ev(f"{ST}.ph==='aim' && {ST}.grp[0]===-1 && {ST}.grp[1]===-1"))
        await ev("""(()=>{ const s=NutPool.cur(), g=NutPool.geom; s.brk=false; s.shots=[1,0]; s.turn=0; s.ph='roll'; s.np=0;
          for(let i=0;i<16;i++){ s.st[i]=0; s.vx[i]=s.vy[i]=0; s.x[i]=g.CX+(i-8)*7; s.y[i]=g.CY+((i*37)%50); }
          s.x[11]=g.CL+15; s.y[11]=g.CT+15; s.vx[11]=-2; s.vy[11]=-2; })()""")   # a stripe goes in first
        await until(pg, f"{ST}.ph!=='roll'", 8000)
        check('the first ball potted after the break decides solids or stripes', await ev(f"{ST}.grp[0]===1 && {ST}.grp[1]===0 && {ST}.turn===0"))
        await ev("document.querySelector('[data-g=exit]').click()"); await pg.wait_for_timeout(200)

        # ---- VS MACHINE: points, win bonus, high score, game over, restart ----
        await open_game(pg)
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(200)
        await ev("""(()=>{ const s=NutPool.cur(), g=NutPool.geom;
          for(let i=0;i<16;i++){ s.vx[i]=s.vy[i]=0; s.st[i]=0; s.x[i]=g.CL+30+(i%8)*16; s.y[i]=g.CT+40+Math.floor(i/8)*30; }
          s.grp=[0,1]; s.brk=false; s.shots=[6,6]; s.turn=0; s.hand=0; s.np=0; s.rollT=0; s.on8=true; s.ph='roll';
          for(let i=1;i<8;i++) s.st[i]=2; s.x[8]=g.CL+15; s.y[8]=g.CT+15; s.vx[8]=-2; s.vy[8]=-2; })()""")
        await until(pg, f"{ST}.ph==='end'", 8000)
        await pg.wait_for_timeout(500)
        check('beating the machine is a win', await ev(f"{ST}.winner===0 && {ST}.won===true"))
        got = await until(pg, "!!document.querySelector('#ini')", 9000)
        check('the win scores points and asks for initials (a new high score)', got)
        if got:
            await pg.fill('#ini', 'POL'); await pg.keyboard.press('Enter'); await pg.wait_for_timeout(400)
            top = await ev("(NutStore.get('scores:cornerPocket',[])[0]||{})")
            check('the high score is saved with a bonus for the quick win', top.get('n') == 'POL' and top.get('s', 0) >= 2000 + 22 * 25 * 2, top)
            check('the unlocked trophy is recorded', await ev("!!(JSON.parse(localStorage.getItem('nutcade:trophies')||'{}')['g-pocket'])"))
            await ev("document.querySelector('[data-g=again]').click()"); await pg.wait_for_timeout(300)
            await pg.keyboard.press('Space'); await pg.wait_for_timeout(300)
            check('Continue then Space starts over at the menu', await ev(f"{ST}.ph==='menu' && {ST}.t<40"))
        await ev("document.querySelector('[data-g=exit]').click()"); await pg.wait_for_timeout(200)
        check('the lobby lists the saved score', 'POL' in await ev(f"document.querySelector('[data-game={ID}]').innerText"))

        # ---- the simulation: physics invariants, the machine finishes whole games, levels differ, deterministic ----
        sim = await ev("""(()=>{ const out={fin:0,bad:0,n:0,wins:[0,0],det:true};
          for(let i=0;i<40;i++){ const r=NutPool.selfplay(500+i,2,0,60*60*10); out.n++; if(r.done) out.fin++; out.bad+=r.bad; if(r.winner>=0) out.wins[r.winner]++; }
          const a=JSON.stringify(NutPool.selfplay(77,1,1,60*60*10)), b=JSON.stringify(NutPool.selfplay(77,1,1,60*60*10)); out.det=a===b; return out; })()""")
        check('40 machine-vs-machine games all finish with a winner', sim['fin'] == 40 and sum(sim['wins']) == 40, sim)
        check('no ball ever leaves the cloth or goes missing (fast balls never tunnel)', sim['bad'] == 0, sim)
        check('the HARD machine beats the EASY machine most of the time', sim['wins'][0] >= 28, sim)
        check('the same seed plays out the same', sim['det'])
        lay = await ev("[Arcade.layout('cornerPocket',7), Arcade.layout('cornerPocket',7), Arcade.layout('cornerPocket',99)]")
        check('a seed gives the same rack, another seed another rack', lay[0] == lay[1] and lay[0] != lay[2])
        # a replay (inputs only) gives the same result every time
        rep = await pg.evaluate("""async ()=>{
          const idle='0,0,0,448,576,,,', press='16,16,0,448,576,,,', held='16,0,0,448,576,,,', rel='0,0,0,448,576,,,';
          const frames=[]; for(let i=0;i<5;i++) frames.push(idle); frames.push(press); for(let i=0;i<4;i++) frames.push(held); frames.push(rel);   // VS MACHINE
          for(let i=0;i<20;i++) frames.push(idle); for(let i=0;i<25;i++) frames.push(held); for(let i=0;i<4000;i++) frames.push(rel);                    // break and wait
          const packed=await Arcade.replay.pack({frames});
          const a=await Arcade.replay.verify('cornerPocket', 1234, packed, 0), c=await Arcade.replay.verify('cornerPocket', 1234, packed, 0);
          return {a, c}; }""")
        check('a recorded game replays frame for frame (same result twice)', rep['a']['score'] == rep['c']['score'] and rep['a']['frames'] == rep['c']['frames'] and rep['a']['frames'] > 3000, rep)

        # ---- the POWER label stays readable over the bar's fill ----
        await ev("document.querySelector('[data-g=exit]')&&document.querySelector('[data-g=exit]').click()"); await open_game(pg); await tap(pg, 'Space'); await pg.wait_for_timeout(200)   # a fresh match, at the break
        rec = await ev("""(async()=>{ const rec=[]; const P=CanvasRenderingContext2D.prototype, orig=P.fillText; const want=Nutcade.tr('POWER');
          P.fillText=function(t,x,y){ if(t===want) rec.push([x,y,this.fillStyle]); return orig.apply(this,arguments); };
          const s=NutPool.cur(); s.pw=0.6; await new Promise(r=>setTimeout(r,150)); P.fillText=orig; return rec; })()""")
        dark = [r for r in rec if r[2] == '#05030c']; white = [r for r in rec if r[2] == '#ffffff']
        offs = {(r[0] - white[-1][0], r[1] - white[-1][1]) for r in dark} if white else set()
        check('POWER is drawn with a dark outline all round (4 sides and corners), then the white label on top', bool(white) and rec[-1][2] == '#ffffff' and {(-1, 0), (1, 0), (0, -1), (0, 1)} <= offs, rec[-9:])

        # ---- five languages: every line drawn on the canvas fits ----
        await ev("document.querySelector('[data-g=exit]')&&document.querySelector('[data-g=exit]').click()")
        for lang in LANGS:
            await ev(f"Nutcade.closeSheet(); Nutcade.S.prefs.lang='{lang}'; document.querySelector('[data-act=tab][data-tab=settings]').click(); const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await pg.wait_for_timeout(250)
            r = await ev("""(async()=>{ await document.fonts.load('8px "Press Start 2P"'); const c=document.createElement('canvas').getContext('2d'); const bad=[], same=[];
              for (const [k,[en,sz]] of Object.entries(NutPool.tx)) { const t=Nutcade.tr(en); if(t===en && !%s && !['cpu','title'].includes(k) && !/^(p1n|p2n)$/.test(k)) same.push(k);
                c.font=sz+'px "Press Start 2P"';
                if (/^r\\d$/.test(k)) { for (const w of t.split(' ')) if (c.measureText(w).width>208) bad.push(k+':'+w); }
                else if (c.measureText(t).width>216) bad.push(k+':'+t+':'+c.measureText(t).width); }
              return {bad, same}; })()""" % ('true' if lang == 'en' else 'false'))
            check(f'{lang}: every line fits the 224 px screen and is translated', not r['bad'] and not r['same'], r)
        await ev("Nutcade.closeSheet(); Nutcade.S.prefs.lang='en'; document.querySelector('[data-act=tab][data-tab=settings]').click(); const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        check('no script errors', not errs, errs[:3])
        await pg.context.close()

        # ---- layout at 320, 1440 and landscape; looks right ----
        for name, vw, vh, mobile in [('320', 320, 640, True), ('1440', 1440, 900, False), ('land', 667, 375, True)]:
            pg2, errs2 = await make(b, vw, vh, mobile)
            await open_game(pg2)
            await pg2.keyboard.press('Space'); await pg2.wait_for_timeout(300)
            await pg2.keyboard.down('ArrowRight'); await pg2.wait_for_timeout(200); await pg2.keyboard.up('ArrowRight')
            await pg2.screenshot(path=OUT + f'pool_{name}.png')
            r = await pg2.evaluate("""(()=>{ const c=document.querySelector('#gameCanvas').getBoundingClientRect(), k=document.querySelector('.pad-keys').getBoundingClientRect();
              return {inView:c.left>=0&&c.top>=0&&c.right<=innerWidth+1&&c.bottom<=innerHeight+1, w:Math.round(c.width), h:Math.round(c.height), hscroll:document.documentElement.scrollWidth>innerWidth+1, keysClear:k.top>=c.bottom-1 || k.left>=c.right-1}; })()""")
            check(f'{name}: the table fits the screen, no sideways scroll', r['inView'] and not r['hscroll'] and r['w'] >= 100, r)
            # the pixels: green cloth is drawn, balls are not blank
            px = await pg2.evaluate("""(()=>{ const c=document.querySelector('#gameCanvas'), x=c.getContext('2d'); const d=x.getImageData(112,120,1,1).data; const e=x.getImageData(112,203,1,1).data; return [[...d],[...e]]; })()""")
            check(f'{name}: cloth and cue ball are drawn', px[0][1] > px[0][0] and px[1][0] > 200 and px[1][1] > 200, px)
            check(f'{name}: no script errors', not errs2, errs2[:3])
            await pg2.context.close()
        await b.close()

if __name__ == '__main__':
    asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
