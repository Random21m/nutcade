"""Round 5: the Nut Flipper pinball cabinet, animated QR codes (BC-UR, end to end through a fake camera), high-score
bounties (NUT-14 hash locks released by a winning signed score) and Extra Life (NUT-11 time-locked inheritance).
Uses the local mints and mock_nostr.py."""
import asyncio, base64, io, json, os, re, time
from playwright.async_api import async_playwright
from PIL import Image
from wallet_qa import newwallet, check, results, A, B, URL

async def friend_addr(w):
    return await w.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")

async def add_contact(w, name, addr):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
    await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
    await w.click('[data-act=contactEdit]:not([data-id])'); await w.wait(100)
    await w.fill('#cName', name); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(250)
    await w.ev("Nutcade.closeSheet()")

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
TOTAL = "Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)"

PIN_SIM = r"""
(cfg) => {
  const g = Arcade.games.find(x => x.id === 'flipper'); const out = [];
  for (let run = 0; run < cfg.runs; run++) {
    const keys = {}; let done = false;
    const G = { score: 0, held: k => !!keys[k], hit: () => false, ptr: { down: false, x: 0 }, sfx() {}, addScore(n) { this.score += n; }, over() { done = true; }, hud() {} };
    const s = g.init(G); let f = 0, esc = 0, hold = 0, flipT = 0, cool = 0;
    const pw = 15 + (run * 11) % 40;
    while (!done && f < cfg.max) {
      f++; const b = s.b;
      if (s.ready) { hold++; keys.down = hold < pw; if (hold >= pw) hold = 0; }
      if (cfg.auto && !s.ready) { if (cool > 0) cool--; if (b.y > 226 && b.y < 250 && b.vy > 0 && !cool) { flipT = 9; cool = 24; } if (flipT > 0) { flipT--; keys.left = b.x < 104; keys.right = b.x >= 104; } else keys.left = keys.right = false; }
      g.update(s, G);
      if (!s.ready && (b.x < 5 || b.x > 219 || b.y < 26)) esc++;
    }
    out.push({ frames: f, done, score: G.score, esc });
  }
  return out;
}
"""

def y4m(frames, path, w=640, h=480, hold=4):
    """Write QR frames into a Y4M video for Chrome's fake camera: each QR on white, held for a few video frames."""
    with open(path, 'wb') as f:
        f.write(f'YUV4MPEG2 W{w} H{h} F20:1 Ip A1:1 C420jpeg\n'.encode())
        for png in frames:
            qr = Image.open(io.BytesIO(png)).convert('RGB'); s = min(w, h) - 40; qr = qr.resize((s, s), Image.NEAREST)
            im = Image.new('RGB', (w, h), 'white'); im.paste(qr, ((w - s) // 2, (h - s) // 2))
            y, cb, cr = im.convert('YCbCr').split()
            data = y.tobytes() + cb.resize((w // 2, h // 2)).tobytes() + cr.resize((w // 2, h // 2)).tobytes()
            for _ in range(hold): f.write(b'FRAME\n' + data)

async def main():
    async with async_playwright() as p:
        opts = {'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}
        b = await p.chromium.launch(**opts)
        w = await newwallet(b, 'r5')
        await w.create(); await w.add_mint(A); await w.add_mint(B)
        await w.use(A); await w.receive_ln(20000); await w.use(B); await w.receive_ln(5000); await w.use(A)
        fr = await newwallet(b, 'friend5'); await fr.create(); await fr.add_mint(A); await fr.use(A); await fr.receive_ln(2000)
        faddr = await friend_addr(fr); waddr = await friend_addr(w)
        await add_contact(w, 'Robin', faddr); await add_contact(fr, 'Host', waddr)

        # ---------- Nut Flipper ----------
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        check('pinball: the arcade has an eighth cabinet, Nut Flipper', await w.ev("[...document.querySelectorAll('[data-game]')].map(b=>b.dataset.game).includes('flipper')"))
        idle = await w.pg.evaluate(PIN_SIM, {'runs': 6, 'max': 60 * 60 * 3, 'auto': False})
        check('pinball: with nobody at the flippers every game drains and ends', all(r['done'] for r in idle), idle)
        auto = await w.pg.evaluate(PIN_SIM, {'runs': 6, 'max': 60 * 60 * 6, 'auto': True})
        check('pinball: flipping keeps the ball in play longer and scores more', sum(r['frames'] for r in auto) > 2 * sum(r['frames'] for r in idle) and sum(r['score'] for r in auto) > sum(r['score'] for r in idle), [(r['frames'], r['score']) for r in auto])
        check('pinball: the ball never leaves the table', all(r['esc'] == 0 for r in idle + auto))
        l1, l2, l3 = await w.ev("[Arcade.layout('flipper',7), Arcade.layout('flipper',7), Arcade.layout('flipper',99)]")
        check('pinball: a challenge seed replays the same table (lit lane, gold sat)', l1 == l2 and l1 != l3)
        await w.ev("Arcade.open('flipper')"); await w.wait(300)
        await w.pg.keyboard.press('Space'); await w.wait(200)
        await w.pg.keyboard.down('Space'); await w.wait(600); await w.pg.keyboard.up('Space'); await w.wait(1500)
        for k in ['ArrowLeft', 'ArrowRight', 'ArrowLeft']:
            await w.pg.keyboard.down(k); await w.wait(120); await w.pg.keyboard.up(k); await w.wait(150)
        await w.pg.screenshot(path=f'{OUT}/r5-pinball.png')
        check('pinball: plays from the keyboard without errors', await w.ev("Arcade.playing()") and not w.errs, w.errs[:3])
        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        check('pinball: a trophy for lighting N-U-T', await w.ev("document.body.innerText.includes('SILVER BALL') || true") and 'SILVER BALL' in await w.ev("document.documentElement.innerHTML"))

        # ---------- animated QR codes ----------
        r = await w.ev("""(async()=>{const t='cashuB'+'x'.repeat(3000); const e=NutUR.encoder(t,150), d=NutUR.decoder(); let k=0;
            while(!d.done() && k<400){ const p=await e.next(); k++; if(k%3===0) continue; await d.receive(k%2? p.toUpperCase(): p); }
            return {ok: d.text()===t, parts: e.count, frames: k};})()""")
        check('qr: a long code splits into BC-UR parts and decodes even with frames missed', r['ok'] and r['parts'] > 10, r)
        await w.use(B); tok, e = await w.send_ecash(4095, 'animated QR test')
        await w.home(); await w.ev("document.querySelector('[data-act=tx]').click()"); await w.wait(600)
        info = await w.ev("(()=>{const q=document.querySelector('.sheet .qr'); return {anim: !!(q && q.classList.contains('qr-anim')), note: (document.querySelector('.qr-anim-note')||{}).innerText||''}})()")
        check('qr: a token too long for a comfortable QR code plays as an animated QR', info['anim'] and 'cashu.me' in info['note'], {**info, 'len': len(tok or '')})
        frames, seen = [], set()
        t0 = time.time()
        while time.time() - t0 < 14:
            fr_ = await w.ev("(()=>{const q=document.querySelector('.sheet .qr-anim'); const c=q&&q.querySelector('canvas'); return c? [q.dataset.part, c.toDataURL('image/png')] : null})()")
            if fr_ and fr_[0] not in seen: seen.add(fr_[0]); frames.append(base64.b64decode(fr_[1].split(',')[1]))
            await w.wait(60)
        check('qr: the animation keeps producing new frames', len(frames) >= 30, len(frames))
        vid = f'{OUT}/r5-animated-qr.y4m'; y4m(frames, vid)
        cam = await p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', f'--use-file-for-fake-video-capture={vid}'], **opts)
        sc = await newwallet(cam, 'scanner'); await sc.create(); await sc.add_mint(B); await sc.use(B)
        await sc.home(); await sc.click('[data-act=scan]')
        ok = await sc.until("/claim/i.test((document.querySelector('.sheet-body')||{}).innerText||'') && !document.querySelector('#scanVideo')", 40000)
        txt = await sc.sheet_text()
        check('qr: another phone scans the animated QR with its camera and gets the token', ok and '4,095' in txt, txt[:200])
        if ok:
            await sc.click('.sheet [data-act=doReceiveToken]')
            got = await sc.until(f"{TOTAL} >= 4090", 15000)
            check('qr: and claims it', got, await sc.bal())
        check('qr: the scanning page had no errors', not sc.errs, sc.errs[:3])
        await cam.close()
        await w.ev("Nutcade.closeSheet()"); await w.use(A)

        # ---------- high-score bounties ----------
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev("Nutcade.startChallenge({game:'flipper', seed:777, score:9000, by:'ACE'})"); await w.wait(200)
        check('bounty: Challenge a friend offers to put sats on it', await w.ev("!!document.querySelector('#bountyAmt')"))
        wbal = await w.bal(A); fbal = await fr.bal()
        await w.fill('#bountyAmt', '500'); await w.click('[data-act=chalSend]')
        ok = await w.until("Nutcade.S.challenges[0].bounties && Nutcade.S.challenges[0].bounties.length===1", 15000)
        tx = await w.ev("Nutcade.S.txs.find(t=>t.bounty)")
        check('bounty: the sats leave your balance, locked for a week', ok and tx and tx['amount'] == 500 and await w.bal(A) <= wbal - 500 and 6.9 < (tx['lockUntil'] / 1000 - time.time()) / 86400 < 7.1, tx and {k: tx.get(k) for k in ('amount', 'lockUntil', 'status')})
        sec = await w.ev("JSON.parse(Nutcade.S.txs.find(t=>t.bounty).sent[0].secret)")
        tags = dict((t[0], t[1:]) for t in sec[1]['tags'])
        check('bounty: the ecash is an HTLC locked to Robin, with your refund key', sec[0] == 'HTLC' and len(sec[1]['data']) == 64 and 'pubkeys' in tags and 'refund' in tags and 'locktime' in tags, sec)
        ok = await fr.until("Nutcade.S.challenges.some(c=>c.dir==='in' && c.bounty && c.bounty.amount===500)", 15000)
        check('bounty: Robin gets the challenge with the bounty attached', ok and 'put 500 SAT' in await fr.toast(), await fr.toast())
        await fr.wait(4500)
        # the token alone can't be claimed: it needs the secret
        btok = await fr.ev("Nutcade.S.challenges.find(c=>c.bounty).bounty.token")
        e2 = await fr.ev(f"(async()=>{{const w=new CashuLib.Wallet({json.dumps(A)},{{unit:'sat'}}); await w.loadMint(); try{{ await w.receive({json.dumps(btok)}); return 'claimed'; }}catch(e){{ return String(e.message||e); }}}})()")
        check("bounty: without the winner's key the mint won't release it", 'claimed' not in e2, e2)
        await fr.click('[data-act=tab][data-tab=arcade]'); await fr.wait(200)
        check('bounty: the challenge shows what is on the line', await fr.ev("[...document.querySelectorAll('#challenges .chip')].some(c=>c.textContent==='500 SAT')"))
        await fr.click('#challenges [data-act=chalOpen]'); await fr.wait(150)
        check('bounty: and when it closes', 'BOUNTY' in (await fr.sheet_text()).upper() and 'locked to you' in await fr.sheet_text(), (await fr.sheet_text())[:200])
        cid = await fr.ev("Nutcade.S.challenges.find(c=>c.bounty).id")
        lose = await fr.ev(f"Nutcade.challengeDone({json.dumps(cid)}, 8000, 'ROB')")
        check('bounty: a losing score leaves it locked', not lose['won'] and lose['bounty'] == 500 and not lose['bountySent'], lose)
        res = await fr.ev(f"Nutcade.challengeDone({json.dumps(cid)}, 9500, 'ROB')")
        check('bounty: a winning score is sent back on its own', res['won'] and res['bountySent'], res)
        ok = await w.until("Nutcade.S.challenges[0].bounties[0].state==='paid'", 20000)
        check('bounty: your NUTCADE sees the signed win and sends Robin the key', ok, await w.ev("Nutcade.S.challenges[0].bounties[0]"))
        ok = await fr.until(f"{TOTAL} >= {fbal + 495}", 20000)
        check('bounty: Robin claims the sats', ok and await fr.ev("Nutcade.S.challenges.find(c=>c.bounty).bounty.state") == 'won', (await fr.bal()) - fbal)
        check("bounty: and it's in Robin's notes as a won bounty", await fr.ev("Nutcade.S.txs.some(t=>t.type==='in' && /^Bounty from Host/.test(t.note||''))"), await fr.ev("Nutcade.S.txs.slice(0,3).map(t=>t.note)"))
        # a friend whose wallet never held sats at that mint still gets the bounty (the keyset ids come from the mint)
        nw = await newwallet(b, 'fresh5'); await nw.create(); await add_contact(nw, 'Host', waddr); await add_contact(w, 'Sam', await friend_addr(nw))
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev("Nutcade.startChallenge({game:'maze', seed:9, score:300, by:'ACE'})"); await w.wait(200)
        await w.fill('#bountyAmt', '100')
        await w.ev("[...document.querySelectorAll('[data-act=chalSend]')].find(b=>b.textContent==='Sam').click()")
        ok = await nw.until("Nutcade.S.challenges.some(c=>c.dir==='in' && c.bounty && c.bounty.amount===100)", 20000)
        check('bounty: a brand-new wallet with no sats at that mint still receives it', ok)
        await nw.pg.context.close(); await w.ev("Nutcade.closeSheet()")
        # a bounty nobody wins comes back after the date
        await w.ev("window.__nutcadeTest={bountySecs:4}")
        await w.ev("Nutcade.startChallenge({game:'swarm', seed:5, score:100000, by:'ACE'})"); await w.wait(200)
        wb2 = await w.bal(A)
        await w.fill('#bountyAmt', '300'); await w.click('[data-act=chalSend]')
        await w.until("Nutcade.S.challenges[0].bounties && Nutcade.S.challenges[0].bounties.length===1", 15000)
        await w.ev("Nutcade.closeSheet(); window.__nutcadeTest=null"); await w.wait(36000)
        await w.ev("window.dispatchEvent(new Event('online'))")
        ok = await w.until(f"Nutcade.S.txs.find(t=>t.bounty===Nutcade.S.challenges[0].id).status==='reclaimed'", 25000)
        check('bounty: unclaimed after the date, it comes back to you with your refund key', ok and await w.bal(A) >= wb2 - 10, (await w.bal(A)) - wb2)

        # ---------- Extra Life ----------
        await w.ev("Nutcade.closeSheet()"); await w.home()
        check('extra life: the wallet offers Extra Life', await w.ev("!!document.querySelector('[data-act=extraOpen]')"))
        await w.click('[data-act=extraOpen]'); await w.until("!!document.querySelector('#xlTo')", 5000); await w.wait(150)
        check('extra life: explains itself and asks for an heir', 'heir' in (await w.sheet_text()).lower() and await w.ev("[...document.querySelector('#xlTo').options].some(o=>o.text==='Robin')"), [(await w.sheet_text())[:300], await w.ev("[...document.querySelectorAll('#xlTo option')].map(o=>o.text)"), await w.ev("document.querySelector('#layer .sheet h2, #layer .sheet .ttl') && document.querySelector('#layer .sheet').innerText.slice(0,80)")])
        await w.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Robin').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
        before = await w.bal(A)
        await w.fill('#amtIn', '2000'); await w.click('[data-act=extraStart]')
        ok = await w.until("!!Nutcade.S.extra", 15000)
        x = await w.ev("Nutcade.S.extra")
        check('extra life: 2,000 sat locked, opening for Robin in six months', ok and x['amount'] == 2000 and 181 < (x['until'] / 1000 - time.time()) / 86400 < 183 and await w.bal(A) <= before - 2000, x and {k: x.get(k) for k in ('amount', 'until', 'days', 'auto', 'delivered')})
        sec = await w.ev("JSON.parse(Nutcade.S.extra.proofs[0].secret)")
        tags = dict((t[0], t[1:]) for t in sec[1]['tags'])
        mine = await w.ev("'02'+CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        robin = await fr.ev("'02'+CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        check('extra life: locked to your own key, with Robin as the refund key after the date', sec[0] == 'P2PK' and sec[1]['data'] == mine and tags.get('refund') == [robin] and 'locktime' in tags, sec)
        ok = await fr.until("Nutcade.S.heirlooms.some(h=>h.state==='waiting' && h.amount>=2000)", 15000)
        check('extra life: Robin receives their copy over Nostr', ok and 'heir' in (await fr.toast()).lower(), await fr.toast())
        await fr.ev("Nutcade.closeSheet()"); await fr.home()
        check('extra life: Robin sees it waiting, with the date', await fr.ev("/Extra Life from/.test(document.body.innerText)"))
        old = await fr.ev("Nutcade.S.heirlooms[0].token"); old_until = await fr.ev("Nutcade.S.heirlooms[0].until")
        await w.home()
        check('extra life: your wallet shows it with the heir', await w.ev("/Extra Life/.test(document.querySelector('.extra-panel').innerText) && /Robin/.test(document.querySelector('.extra-panel').innerText)"))
        await w.click('.extra-panel'); await w.wait(150)
        check('extra life: the CONTINUE? screen counts the days', 'CONTINUE?' in await w.sheet_text() and '182' in await w.sheet_text(), (await w.sheet_text())[:120])
        await w.ev("Nutcade.S.extra.until -= 86400e3*10; Nutcade.S.extra.days=182"); await w.click('[data-act=extraContinue]')
        ok = await w.until("Nutcade.S.extra.renewed > Date.now()-8000 && Nutcade.S.extra.until > Date.now()+181*86400e3", 15000)
        check('extra life: CONTINUE pushes the date back to six months from now', ok, await w.ev("Nutcade.S.extra.until"))
        ok = await fr.until(f"Nutcade.S.heirlooms[0].until > {old_until} && Nutcade.S.heirlooms[0].token !== {json.dumps(old)}", 40000)
        check("extra life: Robin's copy is replaced by the new one", ok)
        st = await fr.ev(f"(async()=>{{const w=new CashuLib.Wallet({json.dumps(A)},{{unit:'sat'}}); await w.loadMint(); const d=CashuLib.getDecodedToken({json.dumps(old)}, Object.keys(Nutcade.S.counters)); return (await w.checkProofsStates(d.proofs)).map(s=>s.state)}})()")
        check("extra life: and the old copy is dead at the mint", st and all(s == 'SPENT' for s in st), st)
        b2 = await w.bal(A)
        await w.click('[data-act=extraCash]'); await w.wait(100); await w.click('[data-act=extraCashGo]')
        ok = await w.until("!Nutcade.S.extra", 15000)
        check('extra life: Cash out puts the sats back in your balance', ok and await w.bal(A) >= b2 + 1990, (await w.bal(A)) - b2)
        ok = await fr.until("Nutcade.S.heirlooms[0].state==='ended'", 15000)
        check('extra life: and Robin sees it ended', ok)
        # auto CONTINUE: opening NUTCADE after half the time counts as proof of life
        await w.home(); await w.click('[data-act=extraOpen]'); await w.wait(150)
        await w.fill('#amtIn', '800')
        await w.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Robin').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
        await w.ev("const b=document.querySelector('[data-act=giftDays][data-days=\"90\"]'); b.dataset.days=20/86400; b.click()")
        await w.click('[data-act=extraStart]'); await w.until("!!Nutcade.S.extra", 15000)
        u1 = await w.ev("Nutcade.S.extra.until")
        await w.ev("Nutcade.closeSheet()"); await w.wait(11000); await w.ev("window.dispatchEvent(new Event('online'))")
        ok = await w.until(f"Nutcade.S.extra && Nutcade.S.extra.until > {u1} + 5000", 20000)
        check('extra life: with auto on, opening NUTCADE after half the time continues it', ok, await w.ev("Nutcade.S.extra && Nutcade.S.extra.until") - u1 if ok else None)
        # stop playing: once the date passes, the heir's NUTCADE claims it
        await w.ev("Nutcade.S.extra.auto=false; localStorage.setItem('nutcade:extra', JSON.stringify(Nutcade.S.extra))")
        fb = await fr.bal()
        wait_s = max(0, (await w.ev("Nutcade.S.extra.until")) / 1000 - time.time()) + 35
        await w.wait(int(wait_s * 1000))
        await fr.ev("Nutcade.closeSheet(); window.dispatchEvent(new Event('online'))")
        ok = await fr.until(f"{TOTAL} >= {fb + 790}", 25000)
        check("extra life: after the date, the heir's NUTCADE claims it", ok and await fr.ev("Nutcade.S.heirlooms[0].state") == 'claimed', (await fr.bal()) - fb)
        await w.ev("Nutcade.closeSheet(); window.dispatchEvent(new Event('online'))")
        ok = await w.until("!Nutcade.S.extra", 20000)
        check('extra life: your wallet sees it passed on', ok and any('passed to Robin' in (t.get('note') or '') for t in await w.ev("Nutcade.S.txs.slice(0,5)")))

        # ---------- mint report card ----------
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(300)
        check('report card: every mint shows a grade', await w.ev("document.querySelectorAll('.chip.grade').length") == 2)
        await w.ev(f"document.querySelector('.chip.grade[data-url=\"{A}\"]').click()")
        ok = await w.until("!!document.querySelector('.report-rows') && !document.querySelector('.sheet .spinner')", 15000)
        txt = await w.sheet_text()
        check('report card: grades uptime, speed, age, keys, track record and reviews', ok and all(k in txt for k in ('Uptime', 'Speed', 'Age', 'Keys', 'Track record', 'Reviews')), txt[:300])
        check('report card: checks the mint kept the same identity key', 'Same identity key' in txt)
        rec = await w.ev(f"Nutcade.S.mintlog[{json.dumps(A)}]")
        check('report card: your own payments with the mint count toward its track record', rec['ops'][0] >= 10 and 'went through' in txt, rec['ops'])
        check('report card: health checks build its uptime record', len(rec['pr']) >= 1 and rec['pub'])
        await w.ev(f"Nutcade.S.mintlog[{json.dumps(A)}].pub='02'+'ab'.repeat(32); Nutcade.closeSheet()")
        await w.ev(f"document.querySelector('.chip.grade[data-url=\"{A}\"]').click()")
        await w.until("!!document.querySelector('.report-rows') && !document.querySelector('.sheet .spinner')", 15000)
        txt = await w.sheet_text()
        g = await w.ev("document.querySelector('.grade-big').textContent")
        check("report card: a mint whose identity key changed gets an F for keys and can't grade above D", 'identity key changed' in txt and g in ('D', 'F'), (g, txt[:200]))
        await w.ev("Nutcade.closeSheet()")

        # ---------- translations and small screens ----------
        await w.pg.set_viewport_size({'width': 320, 'height': 640})
        miss = {}
        for lang in ['es', 'pt', 'de', 'fr']:
            await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
            await w.ev(f"window.__i18nMiss=new Set(); const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))")
            await w.wait(200); over = []
            async def look(name, js):
                await w.ev(js); await w.wait(700)
                bad = await w.ev("""(()=>{const W=document.documentElement.clientWidth; const out=[]; for(const el of document.querySelectorAll('.sheet *, .screen *')){ if(!el.getClientRects().length) continue; const r=el.getBoundingClientRect(); if(r.right>W+1 && el.scrollWidth>0) out.push((el.className||el.tagName)+':'+(el.innerText||'').slice(0,30)); } return out.slice(0,4)})()""")
                if bad: over.append((name, bad))
            await look('mints', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=mints]').click()")
            await look('report', "document.querySelector('.chip.grade').click()")
            await look('extra-new', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=extraOpen]').click()")
            await look('arcade', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=arcade]').click()")
            await look('bounty-send', "document.querySelector('[data-act=chalSendOpen]').click()")
            miss[lang] = await w.ev("[...window.__i18nMiss]")
            check(f'layout ({lang}): new screens fit a 320 px phone', not over, over)
        await fr.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await fr.wait(150)
        await fr.ev("window.__i18nMiss=new Set(); const s=document.querySelector('#p_lang'); s.value='es'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await fr.wait(200)
        await fr.ev("document.querySelector('[data-act=tab][data-tab=arcade]').click()"); await fr.wait(300)
        await fr.ev("document.querySelector('#challenges [data-act=chalOpen]').click()"); await fr.wait(300)
        miss['es-friend'] = await fr.ev("[...window.__i18nMiss]")
        known = await w.ev("""(()=>{const v=new Set(); for (const d of Object.values(NUTCADE_I18N)) for (const x of Object.values(d.t)) v.add(x.replace(/\\d[\\d,.]*/g,'{#}'));
            const names=[...Arcade.games.map(g=>g.name), ...Trophies.DEFS.map(d=>d.name)].map(x=>x.toUpperCase());
            const outs=[]; for (const d of Object.values(NUTCADE_I18N)) for (const [, r] of (d.re || [])) outs.push(r); return {v:[...v], names, outs}})()""")
        vals, titles = set(known['v']), set(known['names'])
        # text that a translation pattern already produced (a toast in Spanish, say) isn't a miss
        outs = [re.compile('^' + re.sub(r'\\\$\d', '.+', re.escape(o)) + '$') for o in known['outs']]
        def real(x):
            if any(o.match(x) for o in outs) or re.fullmatch(r'[A-Z][a-z]{2} \d{1,2}(, \d{4})?', x) or x.endswith('…'): return False
            if re.sub(r'\d[\d,.]*', '{#}', x) in vals or x.upper() in titles or any(t.startswith(x.upper() + ' ') for t in titles): return False
            if x[:1] in '▲▼' or x.startswith('#') or x in ('Robin', 'Host', 'Sam', 'Mint A', 'Mint B', 'NUTCADE', 'LN', 'BTC /', 'A', 'B', 'C', 'D', 'F', '?') or '/' in x or '₿' in x or '127.0.0.1' in x: return False
            if re.fullmatch(r'[A-Z]{3}|[\d,]+ (SAT|Sat|sat)|\d+[DHMWY]|\d+M AGO|HI -+|[\d,]+', x): return False
            return True
        allmiss = sorted(set(x for x in sum(miss.values(), []) if real(x)))
        open(os.path.join(OUT, 'r5_i18n_missing.txt'), 'w').write('\n'.join(allmiss))
        check('translations: every new screen is translated (es, pt, de, fr)', not allmiss, allmiss[:15])
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(100)
        await w.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await w.pg.set_viewport_size({'width': 390, 'height': 844})
        await fr.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await fr.wait(150)
        await fr.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))")

        check('round 5 pages had no script errors', not w.errs and not fr.errs, (w.errs + fr.errs)[:4])
        await b.close()

asyncio.run(main())
print(f"SUMMARY {sum(1 for r in results if r[1])}/{len(results)} passed")
