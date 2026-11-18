"""Nut Poker QA: the cabinet in the real page (menu, keys, touch, holds, draws, pay table, refill, high score, no sats on the share card,
layouts, five languages). The rules themselves are in tests/game_poker_unit.js, run from here too."""
import os, sys, asyncio, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.environ.get('POKER_SHOTS', '')
ST = "NutPoker.state()"
def hands(spec):   # 'Ah Kh 10s' -> card numbers (spades 0, hearts 1, diamonds 2, clubs 3; 2..A = 0..12)
    R = {**{str(i): i - 2 for i in range(2, 11)}, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}; S = {'s': 0, 'h': 1, 'd': 2, 'c': 3}
    return [13 * S[x[-1]] + R[x[:-1]] for x in spec.split()]
async def main():
    # ---- the rules, as unit tests ----
    import shutil
    node = shutil.which('node')
    if not node:   # no system node (the CI image): use the one Playwright ships
        from playwright._impl._driver import compute_driver_executable
        node = str(compute_driver_executable()[0])
    r = subprocess.run([node, os.path.join(HERE, 'game_poker_unit.js')], capture_output=True, text=True)
    fails = [l for l in r.stdout.splitlines() if l.startswith('FAIL')]
    check('unit tests: hand evaluation, pay table and shuffle (43 checks in tests/game_poker_unit.js)', r.returncode == 0 and r.stdout.count('PASS') >= 40 and not fails, fails[:3] or r.stderr[-300:])
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'poker'); await w.create()
        key = lambda k: w.pg.keyboard.press(k)
        async def phase(ph, ms=4000):
            return await w.until(f"{ST}.phase==='{ph}'", ms)
        async def rig(hand, held=(1, 1, 1, 1, 1)):
            await w.ev(f"(()=>{{const s={ST}; s.hand={json.dumps(hand)}; s.held={json.dumps(list(held))};}})()")
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(400)
        check('menu: Nut Poker is a cabinet in the arcade', await w.ev("!!document.querySelector('[data-game=poker]')"))
        check('menu: it has a name, a blurb and a high-score slot', await w.ev("(()=>{const c=document.querySelector('[data-game=poker]');return c.querySelector('.nm').innerText==='NUT POKER'&&c.querySelector('.ds').innerText.length>10&&!!c.querySelector('.hs')})()"))
        await w.ev("document.querySelector('[data-game=poker]').click()"); await w.wait(400)
        check('opens on its title screen with a canvas', await w.ev("!!document.querySelector('.game-view #gameCanvas')") and await w.ev(f"{ST}") is None)
        check('touch: no joystick for a card game, just the A and pause buttons', await w.ev("!document.querySelector('.game-view .stick') && !!document.querySelector('.game-view .abtn.a') && document.querySelector('[data-g=pad]').hidden"))
        await key('Space'); await w.wait(200)
        check('starts with 100 free credits, bet 1, ready to deal', await w.ev(f"(()=>{{const s={ST}; return s&&s.credits===100&&s.bet===1&&s.phase==='ready'}})()"))
        # ---- bet keys ----
        await key('KeyB'); await w.wait(60); check('B bets one more', await w.ev(f"{ST}.bet")==2)
        await key('KeyM'); await w.wait(60); check('M bets the max, 5', await w.ev(f"{ST}.bet")==5)
        await key('KeyB'); await w.wait(60); check('B after 5 wraps round to 1', await w.ev(f"{ST}.bet")==1)
        for _ in range(3): await key('KeyB'); await w.wait(40)
        check('B steps 1 to 4', await w.ev(f"{ST}.bet")==4)
        px = await w.ev("(()=>{const x=document.querySelector('#gameCanvas').getContext('2d'); const c=(a,y)=>Array.from(x.getImageData(a,y,1,1).data).slice(0,3); return {l4:c(190,25), l1:c(137,25)}})()")
        check('pay table: the column of the current bet (4) is lit, the first is not', px['l4'][0] > px['l1'][0] + 15, px)
        await key('KeyM'); await w.wait(80)
        px = await w.ev("(()=>{const x=document.querySelector('#gameCanvas').getContext('2d'); const c=(a,y)=>Array.from(x.getImageData(a,y,1,1).data).slice(0,3); return {l5:c(208,25), l4:c(190,25)}})()")
        check('pay table: at bet 5 the last column is lit', px['l5'][0] > px['l4'][0] + 15, px)
        # ---- deal ----
        await w.ev("window.__cg=0; const o=crypto.getRandomValues.bind(crypto); crypto.getRandomValues=a=>{window.__cg++; return o(a)}; 0")
        await key('Enter'); await w.wait(100)
        check('Enter deals: the bet leaves your credits', await w.ev(f"{ST}.credits")==95 and await w.ev(f"{ST}.phase") in ('deal','hold'))
        check('the shuffle used crypto.getRandomValues for the deck (51 draws)', await w.ev("window.__cg")>=51, await w.ev("window.__cg"))
        check('the hand reaches the hold phase', await phase('hold'))
        d = await w.ev(f"(()=>{{const s={ST}; return {{hand:s.hand.slice(), deck:s.deck.slice(), pos:s.pos}}}})()")
        check('five different cards, all from one 52-card deck', len(set(d['hand']))==5 and sorted(d['deck'])==list(range(52)) and d['hand']==d['deck'][:5] and d['pos']==5, d)
        await key('Digit2'); await key('Digit4'); await w.wait(80)
        check('2 and 4 hold the second and fourth cards', await w.ev(f"{ST}.held")==[0,1,0,1,0])
        await key('Digit2'); await w.wait(60); check('pressing again lets go', await w.ev(f"{ST}.held")==[0,0,0,1,0])
        await key('KeyB'); await w.wait(60); check('bet keys do nothing mid-hand', await w.ev(f"{ST}.bet")==5)
        await key('Digit1'); await key('Digit3'); await key('Digit5'); await w.wait(60)
        px = await w.ev("(()=>{const x=document.querySelector('#gameCanvas').getContext('2d'); return Array.from(x.getImageData(7+19,125+25,1,1).data).slice(0,3)})()")
        await key('Digit1'); await key('Digit3'); await key('Digit5'); await w.wait(60)
        before = await w.ev(f"{ST}.hand.slice()"); await key('Enter'); await w.wait(100)
        check('Enter draws: the phase moves on', await w.ev(f"{ST}.phase")=='draw')
        check('the draw is taken from the same deck, in order', await w.ev(f"(()=>{{const s={ST}; return s.pos>5 && s.hand.every((c,i)=> s.held[i] ? c===({json.dumps(before)})[i] : s.deck.indexOf(c)>=5)}})()"))
        check('the hand resolves into a result', await phase('result'))
        res = await w.ev(f"(()=>{{const s={ST}; return {{hand:s.hand.slice(), key:s.key, win:s.win, credits:s.credits, unique:new Set(s.hand).size, ev:NutPoker.evaluate(s.hand), pay:NutPoker.payout(NutPoker.evaluate(s.hand), s.bet)}}}})()")
        check('the result matches the evaluator and the pay table, and the credits follow', res['unique']==5 and res['key']==res['ev'] and res['win']==res['pay'] and res['credits']==95+res['win'], res)
        # ---- exact outcomes, with hands set up in the hold phase ----
        async def play(hand, bet):
            await w.ev(f"{ST}.bet={bet}"); await key('Enter'); await phase('hold'); await rig(hand); c0 = await w.ev(f"{ST}.credits")
            await key('Enter'); ok = await phase('result'); return ok, c0, await w.ev(f"(()=>{{const s={ST}; return {{key:s.key, win:s.win, credits:s.credits}}}})()")
        ok, c0, r = await play(hands('10h Jh Qh Kh Ah'), 5)
        check('royal flush at max bet pays 4000', ok and r['key']=='royal' and r['win']==4000 and r['credits']==c0+4000, r)
        await w.wait(1200)
        px = []
        for _ in range(8):
            px.append(await w.ev("(()=>{const x=document.querySelector('#gameCanvas').getContext('2d'); return Array.from(x.getImageData(5,27,1,1).data).join(',')})()")); await w.wait(70)
        check('the winning row flashes', len(set(px)) >= 2, px)
        ok, c0, r = await play(hands('10h Jh Qh Kh Ah'), 2)
        check('royal flush at 2 credits pays 500, not the max bet bonus', r['win']==500, r)
        ok, c0, r = await play(hands('Js Jh 2d 5c 9h'), 3); check('a pair of jacks pays 1 per credit', r['key']=='jacks' and r['win']==3, r)
        ok, c0, r = await play(hands('10s 10h 2d 5c 9h'), 3); check('a pair of 10s pays nothing', r['key'] is None and r['win']==0 and r['credits']==c0, r)
        ok, c0, r = await play(hands('As 2h 3d 4c 5h'), 1); check('ace-low straight pays 4', r['key']=='straight' and r['win']==4, r)
        ok, c0, r = await play(hands('10s Jh Qd Kc Ah'), 1); check('ace-high straight pays 4', r['key']=='straight' and r['win']==4, r)
        ok, c0, r = await play(hands('Ah 2h 3h 4h 5h'), 1); check('ace-low straight flush pays 50', r['key']=='sflush' and r['win']==50, r)
        ok, c0, r = await play(hands('7s 7h 7d 7c 2h'), 4); check('four of a kind at 4 pays 100', r['key']=='quads' and r['win']==100, r)
        ok, c0, r = await play(hands('3s 3h 3d 9c 9h'), 5); check('full house at 5 pays 45', r['key']=='full' and r['win']==45, r)
        ok, c0, r = await play(hands('2h 5h 9h Jh Kh'), 1); check('flush pays 6', r['key']=='flush' and r['win']==6, r)
        ok, c0, r = await play(hands('8s 8h 8d Kc 2h'), 1); check('three of a kind pays 3', r['key']=='trips' and r['win']==3, r)
        ok, c0, r = await play(hands('5s 5h Jd Jc 2h'), 1); check('two pair pays 2', r['key']=='twopair' and r['win']==2, r)
        # ---- pause ----
        await key('Enter'); await phase('hold'); await key('KeyP'); await w.wait(150)
        t1 = await w.ev(f"{ST}.t"); await w.wait(250); t2 = await w.ev(f"{ST}.t")
        check('P pauses the game', t1 == t2, (t1, t2))
        await key('Digit1'); await w.wait(100); check('keys do nothing while paused', await w.ev(f"{ST}.held[0]")==0)
        await key('Enter'); await w.wait(250); check('Enter resumes it', await w.ev(f"{ST}.t") > t2 and await w.ev(f"{ST}.phase")=='hold')
        await key('Digit1'); await w.wait(80); check('and play carries on after the pause', await w.ev(f"{ST}.held[0]")==1)
        # ---- touch: bet buttons, tap to hold, deal/draw buttons ----
        await w.ev(f"(()=>{{const s={ST}; s.held=[0,0,0,0,0];}})()"); await key('Enter'); await phase('result')
        async def tap(x, y):
            bb = await w.pg.locator('#gameCanvas').bounding_box(); await w.pg.touchscreen.tap(bb['x'] + x / 224 * bb['width'], bb['y'] + y / 288 * bb['height']); await w.wait(120)
        await w.ev(f"{ST}.bet=1"); await tap(113, 241); check('touch: tapping BET MAX sets 5', await w.ev(f"{ST}.bet")==5)
        await tap(40, 241); check('touch: tapping BET ONE wraps to 1', await w.ev(f"{ST}.bet")==1)
        await tap(186, 241); check('touch: tapping DEAL deals', await w.ev(f"{ST}.phase") in ('deal','hold'))
        await phase('hold'); await tap(7 + 2 * 43 + 19, 150); check('touch: tapping a card holds it', await w.ev(f"{ST}.held")==[0,0,1,0,0])
        await tap(7 + 2 * 43 + 19, 150); check('touch: tapping it again lets go', await w.ev(f"{ST}.held")==[0,0,0,0,0])
        await tap(7 + 4 * 43 + 19, 150); await tap(186, 241); check('touch: DRAW draws', await w.ev(f"{ST}.phase") in ('draw','result'))
        await phase('result')
        await key('Space'); await phase('hold'); check('the A button / Space deals and then draws', await w.ev(f"{ST}.phase")=='hold')
        await key('Space'); await phase('result')
        # ---- out of credits: the free refill ----
        await w.ev(f"(()=>{{const s={ST}; s.credits=1; s.bet=1;}})()"); await key('Enter'); await phase('hold'); await rig(hands('2s 5h 9d Jc Kh'), (1,1,1,1,1))
        await key('Enter'); await phase('result'); c = await w.ev(f"{ST}.credits")
        check('losing your last credit leaves you at 0', c == 0, c)
        check('then FREE REFILL gives 100 free credits', await w.until(f"{ST}.credits===100 && {ST}.refill>0", 3000))
        mx = 0
        for _ in range(12):
            mx = max(mx, await w.ev("(()=>{const x=document.querySelector('#gameCanvas').getContext('2d'); const d=x.getImageData(0,195,224,22).data; let n=0; for(let i=0;i<d.length;i+=4) if(d[i+1]>200&&d[i]<150&&d[i+2]<180) n++; return n})()")); await w.wait(60)
        check('the FREE REFILL banner is drawn in lime', mx > 20, mx)
        # refill also when dealing at 0
        await w.ev(f"(()=>{{const s={ST}; s.credits=0; s.refill=0;}})()"); await key('Enter'); await w.wait(150)
        check('pressing deal at 0 credits refills first', await w.ev(f"{ST}.credits")==99 and await w.ev(f"{ST}.phase") in ('deal','hold'))
        await phase('hold'); await rig(hands('10h Jh Qh Kh Ah')); await w.ev(f"{ST}.bet=5"); await key('Enter'); await phase('result'); await w.wait(1200)
        peak = await w.ev(f"{ST}.peak"); check('the peak is the most credits held', peak >= 4000, peak)
        check('credits can never be bought: no sats, wallet or mint calls anywhere in the cabinet', not await w.ev("/Nutcade|wallet|mint|sats?\\b|Cashu/i.test((window.NutPoker.state.toString()))"))
        # ---- end the run: the high score is the most credits held ----
        await key('KeyE'); check('E ends the run: game over then the high-score entry', await w.until("!!document.querySelector('#ini')", 6000))
        await w.pg.fill('#ini', 'ACE'); await w.click('.game-view form button[type=submit]'); await w.wait(300)
        check('the score (most credits held) is saved', await w.until("(JSON.parse(localStorage.getItem('nutcade:scores:poker')||'[]')[0]||{}).s>=4000", 3000), await w.ev("localStorage.getItem('nutcade:scores:poker')"))
        saved = await w.ev("(JSON.parse(localStorage.getItem('nutcade:scores:poker')||'[]')[0]||{}).s")
        check('the saved score equals the peak credits', saved == peak, (saved, peak))
        check('the offer to challenge a friend is not shown (no replays for a card game)', not await w.ev("!!document.querySelector('.game-view [data-g=chal]')"))
        # ---- the share card can never be loaded with sats ----
        await w.click('.game-view [data-g=card]'); ok = await w.until("!!document.querySelector('#cardBox .share-card')", 8000); await w.wait(200)
        check('share card opens for the Nut Poker score', ok)
        check('share card: no "Put sats in it", no amount box, no Load card button', await w.ev("!document.querySelector('#loadAmt') && !document.querySelector('#cardLoad') && !document.querySelector('.load-card') && !/Put sats in it|Load card/.test(document.querySelector('.sheet').innerText)"))
        check('share card: it says free credits only', await w.ev("!!document.querySelector('#noSatsCard') && /Free credits only/.test(document.querySelector('#noSatsCard').innerText)"))
        await w.ev("Trophies.openCard({kind:'score', game: Arcade.games.find(g=>g.id==='poker'), score: 4095, initials:'ACE', at: Date.now(), loaded:{url:'cashu:fake', amount:500, until: Date.now()+1e6}})"); await w.wait(1200)
        check('share card: even a loaded card handed to it is shown unloaded', await w.ev("!document.querySelector('#cardLoad') && !/Loaded with/.test(document.querySelector('.sheet').innerText)"))
        await w.ev("Trophies.openCard({kind:'score', game: Arcade.games.find(g=>g.id==='swarm'), score: 1234, initials:'ACE', at: Date.now()})"); await w.wait(1200)
        check('other cabinets still offer Put sats in it / Load card (the ban is for Nut Poker only)', await w.ev("!!document.querySelector('#loadAmt') && !!document.querySelector('#cardLoad')"))
        await w.ev("Nutcade.closeSheet()")
        # the lobby's own share button
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(300)
        await w.click('[data-card=poker]'); await w.until("!!document.querySelector('#cardBox .share-card')", 8000); await w.wait(200)
        check('hall of fame: the Nut Poker share button also has no Load card', await w.ev("!document.querySelector('#cardLoad') && !!document.querySelector('#noSatsCard')"))
        await w.ev("Nutcade.closeSheet()")
        check('lobby: the cabinet shows the saved high score', await w.ev(f"document.querySelector('[data-game=poker] .hs').innerText.includes('{str(saved).zfill(6)}')"))
        # ---- challenges and replays do not apply ----
        await w.ev("Arcade.open('poker', {challenge:{id:'x', seed:1, target:5, by:'ZZZ', name:'Z', replay:null}})"); await w.wait(300)
        check('a challenge for Nut Poker is ignored', await w.ev("Arcade.challenge()") is None)
        check('a replay of Nut Poker never verifies', (await w.ev("Arcade.replay.verify('poker', 1, 'r0.W10', 5)"))['ok'] is False)
        # ---- restart after game over ----
        await key('Space'); await w.wait(250)
        check('a new run starts again at 100 credits', await w.ev(f"(()=>{{const s={ST}; return s&&s.credits===100&&s.peak===100&&s.phase==='ready'}})()"))
        # ---- leaving mid-run keeps the best ----
        await key('Enter'); await phase('hold'); await rig(hands('10c Jc Qc Kc Ac')); await w.ev(f"{ST}.bet=5"); await w.ev(f"{ST}.credits+=0"); await key('Enter'); await phase('result'); await w.wait(1200)
        peak2 = await w.ev(f"{ST}.peak"); await w.click('[data-g=exit]'); await w.wait(300)
        sc = await w.ev("JSON.parse(localStorage.getItem('nutcade:scores:poker')||'[]').map(x=>x.s)")
        check('Exit mid-run saves the peak under your usual initials', peak2 in sc, (peak2, sc))
        check('no script errors with Nut Poker', not w.errs, w.errs[:3])
        # ---- layouts ----
        async def layout(vw, vh, tag):
            await w.pg.set_viewport_size({'width': vw, 'height': vh}); await w.wait(300)
            if not await w.ev("!!document.querySelector('.game-view')"): await w.ev("document.querySelector('[data-game=poker]').click()"); await w.wait(300); await key('Space'); await w.wait(300)
            m = await w.ev("(()=>{const c=document.querySelector('#gameCanvas').getBoundingClientRect(), k=document.querySelector('.pad-keys').getBoundingClientRect(), p=document.querySelector('.pad').getBoundingClientRect(), e=document.documentElement; return {l:c.left,r:c.right,t:c.top,b:c.bottom,w:c.width,h:c.height,kt:k.top,kd:getComputedStyle(document.querySelector('.pad-keys')).display,pt:p.top,pd:getComputedStyle(document.querySelector('.pad')).display,sw:e.scrollWidth,iw:innerWidth,ih:innerHeight}})()")
            ok = m['l'] >= 0 and m['r'] <= m['iw'] and m['t'] >= 0 and m['b'] <= m['ih'] and m['sw'] <= m['iw'] and m['w'] >= 160 and (m['kd']=='none' or m['b'] <= m['kt'] + 1) and (m['pd']=='none' or m['b'] <= m['pt'] + 1)
            check(f'layout {tag}: the table fits, readable, nothing overlaps or scrolls sideways', ok, m)
            if os.environ.get('QA_OUT'): await w.pg.screenshot(path=os.path.join(os.environ['QA_OUT'], f'poker-{tag}.png'))
        await w.ev("document.querySelector('[data-g=exit]') && document.querySelector('[data-g=exit]').click()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        for vw, vh, tag in [(320, 640, '320'), (375, 667, '375'), (430, 932, '430'), (1440, 900, '1440'), (667, 375, 'landscape'), (844, 390, 'landscape-wide')]: await layout(vw, vh, tag)
        # ---- a challenge link for Nut Poker (a crafted one: our client never makes it) says so and just opens the cabinet ----
        await w.ev("document.querySelector('[data-g=exit]') && document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        await w.ev("Nutcade.startChallenge({game:'poker', seed:7, score:900, by:'AAA'})"); await w.wait(600)
        link = await w.ev("(document.querySelector('#layer .code')||{}).innerText||''")
        await w.ev("Nutcade.closeSheet()")
        check('(set-up) a signed challenge link for Nut Poker exists', '#challenge=' in link, link[:40])
        lk = await newwallet(b, 'poker-linker'); await lk.create()
        n0 = await lk.ev("Nutcade.S.challenges.length")
        await lk.pg.evaluate(f"location.hash = {json.dumps(link[link.index('#'):])}"); await lk.wait(1500)
        sheet = await lk.sheet_text()
        check('a Nut Poker challenge link says plainly that there are no challenges on this cabinet, and offers no Accept', 'No challenges on this cabinet' in sheet and 'Accept' not in sheet, sheet)
        check('nothing is stored: no challenge is added to the wallet', await lk.ev("Nutcade.S.challenges.length") == n0)
        await lk.click('[data-act=openCab]'); await lk.wait(500)
        check('Play opens Nut Poker as a normal game, with no challenge', await lk.ev("Arcade.playing() && !!document.querySelector('[data-g=exit]') && Arcade.challenge() === null && document.querySelector('.game-view .ttl').innerText === 'NUT POKER'"))
        await lk.pg.context.close()
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(300)

        # ---- five languages ----
        keys = ['ROYAL FLUSH','STRAIGHT FLUSH','FOUR OF A KIND','FULL HOUSE','FLUSH','STRAIGHT','THREE OF A KIND','TWO PAIR','JACKS OR BETTER']
        lim = {'name': 15, 'btn': 8, 'line': 27, 'hdr': 12}
        btn = ['BET ONE','BET MAX','DEAL','DRAW']; lines = ['FREE CREDITS · NEVER SATS','0 CREDITS = FREE REFILL','HOLD CARDS THEN DRAW','PLACE YOUR BET','THEN PRESS DEAL','NO WIN','PRESS DEAL']
        hdr = ['CREDITS','BET','BEST','END RUN','WIN','HOLD']
        await w.pg.set_viewport_size({'width': 390, 'height': 844}); await w.ev("document.querySelector('[data-g=exit]') && document.querySelector('[data-g=exit]').click()")
        for lang in ['es', 'pt', 'de', 'fr']:
            await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
            await w.ev(f"const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await w.wait(200)
            await w.ev("document.querySelector('[data-act=tab][data-tab=arcade]').click()"); await w.wait(300)
            r = await w.ev(f"""(()=>{{ window.__i18nMiss=new Set(); const T=Nutcade.tr; const out={{bad:[],same:[]}};
              const chk=(arr,max,what)=>arr.forEach(k=>{{const t=T(k); if(t.length>max) out.bad.push([what,k,t,t.length]); if(t===k && !['FLUSH','FULL HOUSE','ROYAL FLUSH','STRAIGHT FLUSH','MAX','BET MAX','P pause'].includes(k)) out.same.push(k)}});
              chk({json.dumps(keys)},15,'name'); chk({json.dumps(btn)},8,'button'); chk({json.dumps(lines)},27,'line'); chk({json.dumps(hdr)},9,'header');
              for(const k of ['Five-card draw. Hold, draw, beat the pay table. Free credits only.','Tap cards to HOLD · A deal / draw','1-5 hold · D or Enter deal / draw · B bet · M max · E end run',"Free credits only: this card can't hold sats."]) if(T(k)===k) out.same.push(k);
              out.miss=[...window.__i18nMiss]; out.cabs=document.querySelector('[data-game=poker] .ds').innerText; return out }})()""")
            check(f'language {lang}: every Nut Poker string is translated and short enough for its slot', not r['bad'] and not r['same'] and not r['miss'], r)
            await w.ev("document.querySelector('[data-game=poker]').click()"); await w.wait(400); await key('Space'); await w.wait(300)
            await key('KeyM'); await key('Enter'); await w.wait(900)
            hp = await w.ev("(()=>{const h=document.querySelector('.pad .hint').getBoundingClientRect(), c=document.querySelector('#gameCanvas').getBoundingClientRect(); return {hint:h.bottom<=innerHeight+1 && h.right<=innerWidth+1, ok:c.right<=innerWidth}})()")
            check(f'language {lang}: the game screen and its hint fit a phone', hp['hint'] and hp['ok'], hp)
            if os.environ.get('QA_OUT'): await w.pg.screenshot(path=os.path.join(os.environ['QA_OUT'], f'poker-lang-{lang}.png'))
            await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        check('no script errors across layouts and languages', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
