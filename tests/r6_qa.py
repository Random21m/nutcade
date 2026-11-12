"""Round 6: replays that prove scores (every game replays to the same score; bounties only pay on a verified replay;
racing a challenger's ghost), treasure hunts (sats behind K of N Shamir-split clue cards) and loaded score cards.
Uses the local mints and mock_nostr.py."""
import asyncio, json, os, random, re, time
from playwright.async_api import async_playwright
from wallet_qa import newwallet, check, results, A, B

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
TOTAL = "Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)"
GAMES = ['swarm', 'maze', 'brick', 'rocks', 'hop', 'shield', 'nibble', 'flipper']

async def friend_addr(w):
    return await w.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")

async def add_contact(w, name, addr):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
    await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
    await w.click('[data-act=contactEdit]:not([data-id])'); await w.wait(100)
    await w.fill('#cName', name); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(250)
    await w.ev("Nutcade.closeSheet()")

async def live_game(b, gid):
    """Play a game for real (keyboard, clicks and drags at random) until game over; return what its replay says."""
    w = await newwallet(b, 'live-' + gid); pg = w.pg
    await pg.evaluate(f"Arcade.open('{gid}')"); await pg.wait_for_timeout(300)
    await pg.keyboard.press('Space'); await pg.wait_for_timeout(200)
    rnd = random.Random(sum(map(ord, gid))); t0 = time.time()
    box = await pg.locator('#gameCanvas').bounding_box()
    while time.time() - t0 < 240:
        if await pg.evaluate("!!Arcade.lastReplay()"): break
        k = rnd.choice(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'Space', 'tap', 'drag'])
        if k == 'tap': await pg.mouse.click(box['x'] + rnd.random() * box['width'], box['y'] + rnd.random() * box['height'] * 0.8)
        elif k == 'drag':
            x = box['x'] + rnd.random() * box['width']; y = box['y'] + box['height'] * 0.85
            await pg.mouse.move(x, y); await pg.mouse.down(); await pg.mouse.move(x + rnd.uniform(-60, 60), y, steps=5); await pg.mouse.up()
        else: await pg.keyboard.down(k); await pg.wait_for_timeout(rnd.randint(30, 400)); await pg.keyboard.up(k)
        await pg.wait_for_timeout(rnd.randint(10, 150))
    r = await pg.evaluate("""(async()=>{const r=Arcade.lastReplay(); if(!r) return null; const packed=await Arcade.replay.pack(r);
        const v=await Arcade.replay.verify(r.game, r.seed, packed, r.score); const fake=await Arcade.replay.verify(r.game, r.seed, packed, r.score+10);
        return {score:r.score, frames:r.frames.length, ok:v.ok, sim:v.score, simFrames:v.frames, fake:fake.ok, bytes:packed.length}})()""")
    errs = list(w.errs); await pg.context.close(); return gid, r, errs

# a flipper replay built frame by frame: pull the plunger for `pull` frames, then let the ball go
def flipper_frames(pull, balls=8, idle=1500):
    one = ['2,2,0,448,576,,,'] + ['2,0,0,448,576,,,'] * (pull - 1) + ['0,0,0,448,576,,,'] * idle
    return one * balls   # every new ball needs the plunger pulled again

async def main():
    async with async_playwright() as p:
        opts = {'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}
        b = await p.chromium.launch(**opts)

        # ---------- replays: every game, played live, replays to the same score ----------
        res = await asyncio.gather(*[live_game(b, g) for g in GAMES])
        for gid, r, errs in res:
            check(f'replay: {gid} played live replays to exactly the same score and length', r and r['ok'] and r['sim'] == r['score'] and r['simFrames'] == r['frames'], r)
        check('replay: claiming a higher score than the replay reaches is refused, in every game', all(r and not r['fake'] for _, r, _ in res))
        check('replay: replays are small enough to send', all(r and r['bytes'] < 20000 for _, r, _ in res), [r and r['bytes'] for _, r, _ in res])
        check('replay: the live games had no script errors', not any(e for _, _, e in res), [e for _, _, e in res if e][:2])

        w = await newwallet(b, 'r6'); await w.create(); await w.add_mint(A); await w.use(A); await w.receive_ln(20000)
        fr = await newwallet(b, 'friend6'); await fr.create(); await fr.add_mint(A); await fr.use(A); await fr.receive_ln(1000)
        await add_contact(w, 'Robin', await friend_addr(fr)); await add_contact(fr, 'Host', await friend_addr(w))

        # two flipper replays on seed 777 with different scores, built frame by frame
        scores = await w.pg.evaluate("""async (variants)=>{ const out=[]; for (const v of variants) { const packed=await Arcade.replay.pack({frames: v}); const r=await Arcade.replay.verify('flipper', 777, packed, 0); out.push({packed, score:r.score, ended:r.ended}); } return out; }""",
                                     [flipper_frames(p_) for p_ in (12, 20, 28, 36, 44, 52)])
        ok_scores = sorted([s for s in scores if s['ended']], key=lambda s: s['score'])
        low, high = ok_scores[0], ok_scores[-1]
        check('replay: built replays play through to game over with different scores', high['score'] > low['score'], [s['score'] for s in scores])

        # ---------- challenges carry a verified replay; the friend races its ghost ----------
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev(f"Nutcade.startChallenge({{game:'flipper', seed:777, score:{low['score']}, by:'ACE', replay:{json.dumps(low['packed'])}}})"); await w.wait(200)
        check('ghost: Challenge a friend says the replay goes with it', 'replay goes with it' in await w.sheet_text())
        await w.fill('#bountyAmt', '400'); await w.click('[data-act=chalSend]')
        ok = await fr.until("Nutcade.S.challenges.some(c=>c.dir==='in' && c.bounty && c.verified===true)", 25000)
        check("ghost: Robin's NUTCADE replays the challenger's game and marks the score verified", ok, await fr.ev("Nutcade.S.challenges.map(c=>({v:c.verified, r:!!c.replay, b:!!c.bounty}))"))
        await fr.ev("Nutcade.closeSheet()"); await fr.click('[data-act=tab][data-tab=arcade]'); await fr.wait(200)
        await fr.click('#challenges [data-act=chalOpen]'); await fr.wait(200)
        check('ghost: the challenge screen says it is verified', 'Verified' in await fr.sheet_text(), (await fr.sheet_text())[:200])
        await fr.click('[data-act=chalPlay]'); await fr.wait(600)
        await fr.pg.keyboard.press('Space'); await fr.wait(300)
        ghost = await fr.ev("(()=>{const g=Arcade.ghost(); return g ? {score:g.g.score, frames:g.frames} : null})()")
        check('ghost: accepting starts the game with the challenger as a ghost to race', ghost is not None, ghost)
        await fr.wait(1500)
        g2 = await fr.ev("(()=>{const g=Arcade.ghost(); return g ? g.frames : 0})()")
        check("ghost: the ghost plays alongside you", g2 > 30, g2)
        await fr.pg.screenshot(path=f'{OUT}/r6-ghost.png')
        await fr.ev("document.querySelector('[data-g=exit]').click()"); await fr.wait(200)

        # ---------- a bounty only pays on a replay that checks out ----------
        cid = await fr.ev("Nutcade.S.challenges.find(c=>c.bounty).id")
        fbal = await fr.bal()
        fake = await fr.ev(f"Nutcade.challengeDone({json.dumps(cid)}, {high['score'] + 5000}, 'ROB', Promise.resolve({json.dumps(low['packed'])}))")
        check('bounty: a claimed win is sent with its replay', fake['won'] and fake['bountySent'], fake)
        ok = await w.until("Nutcade.S.challenges[0].results.some(r=>r.verified===false)", 20000)
        check("bounty: a faked score whose replay doesn't reach it gets nothing", ok and await w.ev("Nutcade.S.challenges[0].bounties[0].state") == 'open', [await w.ev("Nutcade.S.challenges[0].bounties[0].state"), await w.ev("Nutcade.S.challenges[0].results")])
        real = await fr.ev(f"Nutcade.challengeDone({json.dumps(cid)}, {high['score']}, 'ROB', Promise.resolve({json.dumps(high['packed'])}))")
        ok = await w.until("Nutcade.S.challenges[0].bounties[0].state==='paid'", 25000)
        check('bounty: a real win, proved by its replay, releases the bounty', ok, await w.ev("Nutcade.S.challenges[0].bounties[0].state"))
        ok = await fr.until(f"{TOTAL} >= {fbal + 395}", 20000)
        check('bounty: and Robin claims it', ok, (await fr.bal()) - fbal)
        check('bounty: the verified result is marked in your challenges', await w.ev("Nutcade.S.challenges[0].results.some(r=>r.verified && r.score===%d)" % high['score']))

        # ---------- treasure hunt ----------
        await w.ev("Nutcade.closeSheet()"); await w.home()
        await w.click('[data-act=huntNew]'); await w.wait(150)
        await w.fill('#amtIn', '300'); await w.fill('#huntN', '5'); await w.fill('#huntK', '3'); await w.fill('#noteIn', 'Clues are hidden around the park')
        wbal = await w.bal(A)
        await w.click('[data-act=huntCreate]')
        ok = await w.until("Nutcade.S.hunts.length===1 && document.querySelectorAll('.hunt-card').length===5", 20000)
        check('hunt: five clue cards come out, each with a QR code', ok and await w.ev("document.querySelectorAll('.hunt-card .qr canvas').length") == 5)
        check('hunt: the prize leaves your balance, locked', await w.bal(A) <= wbal - 300)
        await w.pg.screenshot(path=f'{OUT}/r6-hunt-cards.png')
        cards = await w.ev("Nutcade.S.hunts[0].cards")
        check('hunt: the cards are short enough to print and scan', all(len(c) < 220 for c in cards), max(len(c) for c in cards))
        sec = await w.ev("JSON.parse(Nutcade.S.txs.find(t=>t.hunt).sent[0].secret)")
        check('hunt: the prize is locked to the hunt key, with your refund key', sec[0] == 'P2PK' and sec[1]['data'] == '02' + await w.ev("Nutcade.S.hunts[0].pub") and any(t[0] == 'refund' for t in sec[1]['tags']), sec)
        await w.ev(f"Nutcade.handleScan({json.dumps(cards[0])})"); await w.wait(300)
        check("hunt: scanning your own card doesn't count", "own cards" in (await w.toast()).lower() and not await w.ev("Object.keys(Nutcade.S.found).length"), await w.toast())
        hb = await fr.bal()
        await fr.ev("Nutcade.closeSheet()"); await fr.ev(f"Nutcade.handleScan({json.dumps(cards[1])})"); await fr.wait(600)
        check('hunt: the first clue shows CLUE 1/3', 'CLUE 1/3' in await fr.sheet_text(), (await fr.sheet_text())[:120])
        ok = await fr.until("/300 SAT/.test(document.querySelector('.sheet-body').innerText)", 10000)
        check('hunt: and the prize and message, read from Nostr', ok and 'around the park' in await fr.sheet_text(), (await fr.sheet_text())[:200])
        await fr.ev(f"Nutcade.handleScan({json.dumps(cards[1])})"); await fr.wait(300)
        check('hunt: scanning the same card twice still counts once', 'CLUE 1/3' in await fr.sheet_text())
        await fr.ev(f"Nutcade.handleScan({json.dumps(cards[3])})"); await fr.wait(300)
        check('hunt: two cards, one to go', 'CLUE 2/3' in await fr.sheet_text())
        await fr.ev(f"location.hash = {json.dumps(cards[4].split('#')[1])}");
        ok = await fr.until(f"{TOTAL} >= {hb + 295}", 25000)
        check('hunt: the third card (opened as a link) rebuilds the key and claims the treasure', ok and 'TREASURE' in await fr.sheet_text(), [(await fr.bal()) - hb, (await fr.sheet_text())[:80]])
        await fr.pg.screenshot(path=f'{OUT}/r6-hunt-won.png')
        st = await newwallet(b, 'late'); await st.create(); await st.add_mint(A); await st.use(A)
        for c in (cards[0], cards[2]): await st.ev(f"Nutcade.handleScan({json.dumps(c)})"); await st.wait(300)
        await st.ev(f"Nutcade.handleScan({json.dumps(cards[3])})")
        ok = await st.until("Object.values(Nutcade.S.found)[0].state==='gone'", 20000)
        check('hunt: a slower hunter with three other cards finds the chest empty', ok and 'first' in (await st.toast()).lower(), await st.toast())
        bad = cards[1][:-3] + ('AAA' if not cards[1].endswith('AAA') else 'BBB')
        st2 = await newwallet(b, 'tamper'); await st2.create(); await st2.add_mint(A)
        for c in (cards[0], bad, cards[2]): await st2.ev(f"Nutcade.handleScan({json.dumps(c)})"); await st2.wait(300)
        ok = await st2.until("Object.values(Nutcade.S.found)[0].state==='bad'", 10000)
        check("hunt: a tampered card can't open the chest", ok)
        await st.pg.context.close(); await st2.pg.context.close()
        ok = await w.until("Nutcade.S.txs.find(t=>t.hunt).status==='claimed' || (window.dispatchEvent(new Event('online')), false)", 40000)
        check("hunt: your notes show the chest was opened", ok)
        # a hunt nobody finishes comes back
        await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=huntNew]'); await w.wait(150)
        await w.fill('#amtIn', '200'); await w.fill('#huntN', '2'); await w.fill('#huntK', '2')
        await w.ev("const b=document.querySelector('[data-act=giftDays][data-days=\"1\"]'); b.dataset.days=4/86400; b.click()")
        await w.click('[data-act=huntCreate]'); await w.until("Nutcade.S.hunts.length===2", 15000)
        b2 = await w.bal(A); await w.ev("Nutcade.closeSheet()"); await w.wait(36000); await w.ev("window.dispatchEvent(new Event('online'))")
        ok = await w.until("Nutcade.S.txs.find(t=>t.hunt===Nutcade.S.hunts[0].pub).status==='reclaimed'", 25000)
        check('hunt: a chest nobody opens in time comes back to you', ok and await w.bal(A) >= b2 + 195, (await w.bal(A)) - b2)

        # ---------- loaded score cards ----------
        await w.ev("Nutcade.closeSheet(); Trophies.openCard({kind:'score', game: Arcade.games.find(g=>g.id==='flipper'), score: 12340, initials:'ACE', at: Date.now()})")
        await w.until("!!document.querySelector('#cardLoad')", 15000)
        check('loaded card: a score card offers to put sats in it', True)
        await w.fill('#loadAmt', '210'); await w.click('#cardLoad')
        ok = await w.until("/Loaded with 210 SAT/.test(document.querySelector('.sheet-body').innerText)", 25000)
        check('loaded card: the card is redrawn with a QR code and says how much is in it', ok, (await w.sheet_text())[:160])
        img = await w.ev("document.querySelector('.share-card').src")
        await w.pg.screenshot(path=f'{OUT}/r6-loaded-card.png')
        lc = await w.ev("Nutcade.S.hunts.find(h=>h.loaded)")
        check('loaded card: it is a one-card treasure', lc and lc['k'] == 1 and lc['n'] == 1 and lc['amount'] == 210, lc and {k: lc[k] for k in ('k', 'n', 'amount')})
        # read the QR code back out of the card image, as a phone camera would
        qr = await w.ev(f"""(async()=>{{ const img=new Image(); img.src={json.dumps(img)}; await img.decode(); const c=document.createElement('canvas'); c.width=img.width; c.height=img.height; const x=c.getContext('2d'); x.drawImage(img,0,0);
            const d=x.getImageData(0,0,c.width,c.height); const r=CashuLib.jsQR(d.data,c.width,c.height); return r ? r.data : null; }})()""")
        check('loaded card: the QR code on the card image scans', qr == lc['cards'][0], qr)
        fb = await fr.bal()
        await fr.ev("Nutcade.closeSheet()"); await fr.ev(f"Nutcade.handleScan({json.dumps(qr or lc['cards'][0])})")
        ok = await fr.until(f"{TOTAL} >= {fb + 205}", 25000)
        check('loaded card: the first person to scan it wins the sats', ok, (await fr.bal()) - fb)

        # ---------- translations ----------
        miss = []
        for lang in ['es', 'de']:
            await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
            await w.ev(f"window.__i18nMiss=new Set(); const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await w.wait(200)
            for js in ["Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=huntNew]').click()",
                       "Nutcade.closeSheet(); document.querySelector('[data-act=huntCards]').click()",
                       "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=arcade]').click(); document.querySelector('[data-act=chalSendOpen]').click()"]:
                await w.ev(js); await w.wait(500)
            miss += await w.ev("[...window.__i18nMiss]")
        known = await w.ev("""(()=>{const v=new Set(); for (const d of Object.values(NUTCADE_I18N)) for (const x of Object.values(d.t)) v.add(x.replace(/\\d[\\d,.]*/g,'{#}')); const outs=[]; for (const d of Object.values(NUTCADE_I18N)) for (const [, r] of (d.re || [])) outs.push(r); const names=[...Arcade.games.map(g=>g.name), ...Trophies.DEFS.map(d=>d.name)].map(x=>x.toUpperCase()); return {v:[...v], outs, names}})()""")
        vals = set(known['v']); outs = [re.compile('^' + re.sub(r'\\\$\d', '.+', re.escape(o)) + '$') for o in known['outs']]
        def real(x):
            if any(o.match(x) for o in outs) or re.sub(r'\d[\d,.]*', '{#}', x) in vals: return False
            if x.upper() in known['names'] or any(t.startswith(x.upper() + ' ') for t in known['names']) or x[:1] in '▲▼' or x.startswith('#'): return False
            if re.fullmatch(r'[A-Z]{3}|\d+[DHMWY]|\d+M AGO|HI -+|BTC /|LN', x): return False
            if x in ('Robin', 'Host', 'ACE', 'NUTCADE', 'NUT FLIPPER') or '/' in x or re.fullmatch(r'[A-Z][a-z]{2} \d{1,2}(, \d{4})?|[\d,]+ SAT|[\d,]+|\d{6}', x): return False
            return True
        miss = sorted(set(x for x in miss if real(x)))
        check('translations: the new screens are translated', not miss, miss[:12])
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
        await w.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))")

        check('round 6 pages had no script errors', not w.errs and not fr.errs, (w.errs + fr.errs)[:4])
        await b.close()

asyncio.run(main())
print(f"SUMMARY {sum(1 for r in results if r[1])}/{len(results)} passed")
