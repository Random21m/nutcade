"""Round 4: chiptune transfer (codes as sound, end to end through a fake microphone), refundable gifts (NUT-11 locks with a
refund date), co-op bill split, mint health and moving sats, cashier mode, high-score challenges, round-up piggy bank,
plus translations and small-screen layout of the new screens. Uses the local mints and mock_nostr.py."""
import asyncio, csv, io, json, os, re, struct, wave, random, base64
from playwright.async_api import async_playwright
from wallet_qa import W, newwallet, check, results, A, B, F, URL

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
SHEET_DONE = "document.querySelector('.sheet-body') && /SENT!|1UP!/.test(document.querySelector('.sheet-body').innerText)"

async def friend_addr(w):
    return await w.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")

async def add_contact(w, name, addr):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
    await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
    await w.click('[data-act=contactEdit]'); await w.wait(100)
    await w.fill('#cName', name); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(250)
    await w.ev("Nutcade.closeSheet()")

def write_wav(path, samples, sr=48000, noise=0.02):
    rnd = random.Random(5)
    lead = [0.0] * int(sr * 0.4)
    with wave.open(path, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        data = bytearray()
        for v in lead + samples + lead:
            x = max(-1.0, min(1.0, 0.8 * v + rnd.gauss(0, noise)))
            data += struct.pack('<h', int(x * 32767))
        f.writeframes(bytes(data))

async def main():
    async with async_playwright() as p:
        opts = {'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}
        b = await p.chromium.launch(**opts)
        w = await newwallet(b, 'r4')
        # pin the Bitcoin price so results don't depend on the live market (CI can reach Coinbase)
        async def fixed_rate(route):
            if 'exchange-rates' in route.request.url: await route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '50000'}}}))
            else: await route.abort()
        await w.pg.context.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), fixed_rate)
        await w.pg.context.route_web_socket(re.compile('coinbase'), lambda ws: None)
        await w.create(); await w.add_mint(A); await w.add_mint(B)
        await w.use(A); await w.receive_ln(20000); await w.use(B); await w.receive_ln(3000); await w.use(A)
        fr = await newwallet(b, 'friend4'); await fr.create(); await fr.add_mint(A); await fr.add_mint(B); await fr.use(A); await fr.receive_ln(6000)
        faddr = await friend_addr(fr); waddr = await friend_addr(w)
        await add_contact(w, 'Robin', faddr); await add_contact(fr, 'Host', waddr)

        # ---------- chiptune: the modem in the page ----------
        r = await w.ev("""(()=>{const bytes=new Uint8Array(300).map((_,i)=>(i*91+7)&255); const pcm=Chiptune.encode(bytes,44100); let got=null;
            const d=new Chiptune.Decoder(44100,b=>{got=b}); for(let i=0;i<pcm.length;i+=4096) d.push(pcm.subarray(i,i+4096));
            return {ok: !!got && got.length===300 && got.every((v,i)=>v===bytes[i]), secs: Chiptune.seconds(bytes)}})()""")
        check('sound: the modem decodes its own signal in the browser', r['ok'], r)
        tok, e = await w.send_ecash(1500, 'for the sound test')
        rt = await w.ev(f"""(()=>{{const t={json.dumps(tok)}; const b=Nutcade.soundBytes(t); const back=Nutcade.soundText(b);
            const d1=CashuLib.getDecodedToken(t, Object.keys(Nutcade.S.counters)), d2=CashuLib.getDecodedToken(back, Object.keys(Nutcade.S.counters));
            const key=d=>JSON.stringify([d.mint, d.proofs.map(p=>[p.id, Number(p.amount), p.secret, p.C])]); return {{len:b.length, tlen:t.length, same: key(d1)===key(d2), magic: b[0]}}}})()""")
        check('sound: tokens travel in a compact form and come back with every proof intact', rt['same'] and rt['magic'] == 0xC1 and rt['len'] * 2.5 < rt['tlen'], rt)
        await w.home(); await w.click('[data-act=tx]'); await w.wait(200)
        check('sound: a sent token offers Play as sound', await w.ev("!!document.querySelector('.sheet [data-act=ctPlay]')"))
        await w.click('.sheet [data-act=ctPlay]'); await w.wait(600)
        check('sound: playing shows the tape loading screen', await w.ev("Chiptune.isPlaying() && !!document.querySelector('.tape.on')"), await w.sheet_text())
        await w.ev("Nutcade.closeSheet()"); await w.wait(100)
        check('sound: closing the screen stops the sound', await w.ev("!Chiptune.isPlaying()"))
        # end to end: the token is played into a fake microphone of another browser
        pcm = await w.ev(f"Array.from(Chiptune.encode(Nutcade.soundBytes({json.dumps(tok)}), 48000), v=>Math.round(v*10000)/10000)")
        wav = os.path.join(OUT, 'chiptune-token.wav'); write_wav(wav, pcm)
        mic = await p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', f'--use-file-for-fake-audio-capture={wav}', '--autoplay-policy=no-user-gesture-required'], **opts)
        lis = await newwallet(mic, 'listener'); await lis.create(); await lis.add_mint(B)
        await lis.pg.context.grant_permissions(['microphone'])
        await lis.home()
        check('sound: the wallet screen has a Listen button', await lis.ev("!!document.querySelector('[data-act=ctListen]')"))
        await lis.click('[data-act=ctListen]')
        amt0 = await w.ev(f"Number(CashuLib.getTokenMetadata({json.dumps(tok)}).amount)")
        ok = await lis.until(f"(()=>{{try{{const v=(document.querySelector('#tokIn')||{{}}).value; return !!v && Number(CashuLib.getTokenMetadata(v).amount)==={amt0}}}catch(e){{return false}}}})()", 75000)
        check('sound: another phone hears the token through its microphone', ok, await lis.ev("(()=>{const v=(document.querySelector('#tokIn')||{}).value||''; let m=''; try{m=String(Number(CashuLib.getTokenMetadata(v).amount))}catch(e){m=e.message} return v.slice(0,30)+' '+m})()"))
        if ok:
            await lis.click('[data-act=doReceiveToken]'); await lis.wait(400)
            if await lis.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await lis.click('[data-act=doReceiveToken]')
            ok2 = await lis.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=1400", 15000)
            check('sound: and claims it', ok2, await lis.sheet_text())
        check('sound: the listener page had no errors', not lis.errs, lis.errs[:3])
        await mic.close()

        # ---------- refundable gifts ----------
        await w.use(A); await w.home(); await w.click('[data-act=send]'); await w.wait(150)
        check('gift: Send has a lock option', await w.ev("!!document.querySelector('#giftOn') && document.querySelector('#giftBox').hidden"))
        await w.pg.check('#giftOn'); await w.wait(100)
        check('gift: turning it on shows who and when', await w.ev("!document.querySelector('#giftBox').hidden && document.querySelector('#giftTo').options[0].text==='Robin'"))
        fbal = await fr.bal()
        await w.fill('#amtIn', '700'); await w.fill('#noteIn', 'Birthday #gift')
        await w.click('[data-act=doSendEcash]')
        await w.until("document.querySelector('.sheet-body') && /Locked gift/i.test(document.querySelector('.sheet-body').innerText)", 15000)
        t = await w.ev("Nutcade.S.txs[0]")
        check('gift: locked to Robin with a refund date a week out', t.get('giftTo') == 'Robin' and 6.9 < (t['lockUntil'] / 1000 - __import__('time').time()) / 86400 < 7.1, {k: t.get(k) for k in ('giftTo', 'lockUntil', 'delivered')})
        locked_tok = t['token']
        secret = await w.ev("JSON.parse(Nutcade.S.txs[0].sent[0].secret)")
        check('gift: the ecash carries a P2PK lock, a locktime and your refund key', secret[0] == 'P2PK' and any(x[0] == 'locktime' for x in secret[1]['tags']) and any(x[0] == 'refund' for x in secret[1]['tags']), secret)
        ok = await fr.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {fbal + 690}", 15000)
        check('gift: Robin receives it over Nostr and can unlock it', ok, await fr.bal())
        # someone else can't claim a gift locked to Robin
        st = await newwallet(b, 'stranger'); await st.create(); await st.add_mint(A); await st.use(A)
        other = await w.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return Array.from(CashuLib.getPubKeyFromPrivKey(k),x=>x.toString(16).padStart(2,'0')).join('')})()")
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
        await w.ev("const s=document.querySelector('#giftTo'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true}))")
        await w.fill('#giftKey', other); await w.fill('#amtIn', '300'); await w.click('[data-act=doSendEcash]'); await w.wait(2500)
        tok2 = await w.ev("Nutcade.S.txs[0].token")
        _, e, _ = await st.receive_token(tok2)
        check("gift: anyone else is told it's locked to someone else", 'locked' in e, e)
        await w.close(); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        check('gift: shows as LOCKED in your notes', await w.ev("[...document.querySelectorAll('#txList .chip')].some(c=>c.textContent==='LOCKED')"))
        await w.ev("document.querySelector('#txList [data-act=tx]').click()"); await w.wait(150)
        check('gift: no early take-back before the date', await w.ev("!document.querySelector('[data-act=giftTake]') && /Back on/i.test(document.querySelector('.sheet-body').innerText) && !document.querySelector('.sheet [data-act=reclaim]')"))
        await w.close()
        # a short lock to a stranger's key: you take it back yourself once the date passes
        spub = '02' + await st.ev("CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
        async def short_gift(amount, secs):
            await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
            await w.ev("const s=document.querySelector('#giftTo'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true}))")
            await w.fill('#giftKey', 'nostr:' + await st.ev("CashuLib.npubEncode(CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)))"))
            await w.ev(f"const b=document.querySelector('[data-act=giftDays][data-days=\"1\"]'); b.dataset.days={secs}/86400; b.click()")
            await w.fill('#amtIn', str(amount)); await w.click('[data-act=doSendEcash]'); await w.wait(2500)
            return await w.ev("Nutcade.S.txs[0]")
        g1 = await short_gift(400, 4)
        check('gift: lock to a pasted npub', g1.get('locked') == spub and g1.get('lockUntil'), {k: g1.get(k) for k in ('locked', 'lockUntil')})
        await w.close(); await w.wait(6000)
        before = await w.bal(A)
        await w.ev(f"Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        await w.ev(f"document.querySelector('[data-act=tx][data-id={json.dumps(g1['id'])}]').click()"); await w.wait(200)
        check('gift: after the date, Take it back appears', await w.ev("!!document.querySelector('[data-act=giftTake]')"))
        await w.click('[data-act=giftTake]')
        ok = await w.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(g1['id'])}).status==='reclaimed'", 15000)
        check('gift: taken back with your refund key', ok and await w.bal(A) >= before + 395, (await w.bal(A)) - before)
        g2 = await short_gift(250, 3)
        await w.close(); await w.wait(34000)
        before = await w.bal(A)
        await w.ev("window.dispatchEvent(new Event('online'))")
        ok = await w.until(f"Nutcade.S.txs.find(t=>t.id==={json.dumps(g2['id'])}).status==='reclaimed'", 20000)
        check('gift: an unclaimed gift comes back on its own after the date', ok and await w.bal(A) >= before + 245, (await w.bal(A)) - before)
        await st.pg.context.close()

        # ---------- co-op bill split ----------
        await w.home(); await w.click('[data-act=splitOpen]'); await w.wait(150)
        await w.fill('#amtIn', '3000'); await w.fill('#splitN', '3'); await w.fill('#memoIn', 'Pizza night')
        await w.click('[data-act=splitCreate]'); await w.wait(400)
        txt = await w.sheet_text()
        check('split: summons a boss with the amount still to collect', 'BILL BOSS' in txt and '2,000' in txt and '1,000 SAT' in txt, txt[:200])
        enc = await w.ev("Nutcade.S.requests[0].encoded")
        check('split: the request asks each friend for their share', await w.ev(f"CashuLib.decodePaymentRequest({json.dumps(enc)}).amount==1000"))
        async def friend_pays():
            await fr.home(); await fr.ev(f"Nutcade.handleScan({json.dumps(enc)})"); await fr.wait(300)
            await fr.click('[data-act=payReq]'); await fr.until(SHEET_DONE, 15000); await fr.close()
        await friend_pays()
        ok = await w.until("/HIT FOR 1,000/.test(document.querySelector('.sheet-body').innerText)", 15000)
        check('split: a friend paying knocks off health', ok and '1,000' in await w.ev("document.querySelector('.hp').innerText"), await w.sheet_text())
        await w.close(); await w.home()
        check('split: an open bill shows on the wallet screen', await w.ev("!!document.querySelector('.boss-mini')"))
        await w.click('.boss-mini'); await w.wait(200)
        await friend_pays()
        ok = await w.until("/BOSS DEFEATED/.test(document.querySelector('.sheet-body').innerText)", 15000)
        check('split: the last share defeats the boss', ok, await w.sheet_text())
        await w.close(); await w.home()
        check('split: a defeated boss leaves the wallet screen', not await w.ev("!!document.querySelector('.boss-mini')"))

        # ---------- mint health and moving sats ----------
        await w.click('[data-act=tab][data-tab=mints]')
        ok = await w.until("[...document.querySelectorAll('.health')].length===2 && [...document.querySelectorAll('.health')].every(h=>/ONLINE/.test(h.innerText))", 10000)
        check('health: each mint shows that it answers, with a response time', ok, await w.ev("[...document.querySelectorAll('.health')].map(h=>h.innerText)"))
        check('health: the spread bar shows how sats are split', await w.ev("document.querySelectorAll('.spread i').length===2"))
        txt = await w.ev("document.querySelector('#mintHealth').innerText")
        check('health: warns when one mint holds most of your sats', re.search(r'\d+% of your sats are at Mint A', txt) is not None, txt)
        check('health: offers to even it out', await w.ev("!!document.querySelector('#mintHealth [data-act=moveOpen][data-amt]')"))
        a0, b0 = await w.bal(A), await w.bal(B)
        await w.click('#mintHealth [data-act=moveOpen][data-amt]'); await w.wait(200)
        amt = int(await w.ev("document.querySelector('#amtIn').value"))
        await w.click('[data-act=moveQuote]'); await w.until("!!document.querySelector('#mvGo')", 10000)
        await w.click('#mvGo')
        ok = await w.until("/MOVED!|ON ITS WAY/.test(document.querySelector('.sheet-body').innerText)", 30000)
        a1, b1 = await w.bal(A), await w.bal(B)
        check('health: Even out moves sats from Mint A to Mint B', ok and b1 == b0 + amt and a1 < a0 - amt + 5, {'moved': amt, 'A': a0 - a1, 'B': b1 - b0})
        check('health: both sides of the move are marked as a move', await w.ev("Nutcade.S.txs.slice(0,2).every(t=>t.move)"))
        await w.close()
        await w.pg.route('http://127.0.0.1:3339/v1/info', lambda r: r.abort())
        await w.click('[data-act=healthCheck]')
        ok = await w.until("[...document.querySelectorAll('.health')].some(h=>/NOT ANSWERING/.test(h.innerText))", 10000)
        check("health: a mint that doesn't answer is flagged, with a warning about its sats", ok and 'stuck' in await w.ev("document.querySelector('#mintHealth').innerText"))
        await w.pg.unroute('http://127.0.0.1:3339/v1/info')

        # ---------- cashier mode ----------
        await w.home(); await w.click('[data-act=cashier]'); await w.wait(200)
        check('cashier: opens full screen with a keypad', await w.ev("!!document.querySelector('.cashier .cash-keys') && document.querySelectorAll('.cashier .ck').length===12"))
        for k in '1234': await w.click(f'.cashier [data-ck="{k}"]')
        check('cashier: keys enter the amount', '1,234' in await w.ev("document.querySelector('.cash-amt').innerText"))
        await w.fill('#cashLabel', 'Coffee')
        await w.click('.cashier [data-ck=charge]')
        ok = await w.until("!!document.querySelector('.cashier .qr canvas')", 10000)
        check('cashier: Charge shows a QR code for the customer', ok)
        ok = await w.until("/PAID!/.test(document.querySelector('.cashier').innerText)", 20000)
        check('cashier: the payment lands with a PAID screen', ok)
        check("cashier: today's total counts the sale", await w.ev("/1,234/.test(document.querySelector('.cash-today').innerText) && /1 SALE/.test(document.querySelector('.cash-today').innerText)"))
        t = await w.ev("Nutcade.S.txs.find(t=>t.cashier)")
        check('cashier: the sale is noted with the item and #cashier', t and t['note'] == 'Sale: Coffee #cashier' and t['status'] == 'done', t and t.get('note'))
        # ecash at the till
        await w.click('.cashier [data-ck=next]'); await w.wait(100)
        for k in '500': await w.click(f'.cashier [data-ck="{k}"]')
        await w.click('.cashier [data-ck=m-ecash]'); await w.click('.cashier [data-ck=charge]'); await w.wait(600)
        renc = await w.ev("Nutcade.S.requests[0].encoded")
        await fr.home(); await fr.ev(f"Nutcade.handleScan({json.dumps(renc)})"); await fr.wait(300); await fr.click('[data-act=payReq]'); await fr.until(SHEET_DONE, 15000); await fr.close()
        ok = await w.until("/PAID!/.test(document.querySelector('.cashier').innerText)", 20000)
        check('cashier: ecash payment requests work at the till too', ok and await w.ev("/2 SALES/.test(document.querySelector('.cash-today').innerText)"))
        await w.ev("document.querySelector('#cashExit').dispatchEvent(new PointerEvent('pointerdown')); document.querySelector('#cashExit').dispatchEvent(new PointerEvent('pointerup'))"); await w.wait(1100)
        check('cashier: a quick tap on exit does nothing', await w.ev("!!document.querySelector('.cashier')"))
        await w.ev("document.querySelector('#cashExit').dispatchEvent(new PointerEvent('pointerdown'))"); await w.wait(1200)
        check('cashier: holding exit closes the till', await w.ev("!document.querySelector('.cashier')"))
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=tillOpen]'); await w.wait(150)
        async with w.pg.expect_download() as d: await w.click('[data-act=tillCsv]')
        rows = list(csv.DictReader(io.StringIO(open(await (await d.value).path(), encoding='utf-8-sig').read())))
        check("cashier: today's sales export as CSV", len(rows) == 2 and {r['amount_sat'] for r in rows} == {'1234', '500'}, [r['amount_sat'] for r in rows])
        await w.close()

        # ---------- high-score challenges ----------
        l1, l2, l3 = await w.ev("[Arcade.layout('maze',7), Arcade.layout('maze',7), Arcade.layout('maze',8)]")
        check('challenge: the same seed gives the same level layout', l1 == l2 and l1 != l3 and len(l1) > 100)
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(200)
        await w.ev("Nutcade.startChallenge({game:'swarm', seed:4242, score:4200, by:'ACE'})"); await w.wait(200)
        txt = await w.sheet_text()
        check('challenge: Challenge a friend shows the score, contacts and a link', '004200' in txt and 'Robin' in txt and '#challenge=' in txt, txt[:160])
        link = await w.ev("document.querySelector('.sheet .code').innerText")
        await w.click('[data-act=chalSend]')
        ok = await fr.until("Nutcade.S.challenges.some(c=>c.dir==='in' && c.score===4200 && c.seed===4242)", 15000)
        check('challenge: Robin receives it over Nostr', ok)
        check('challenge: and is told who it is from', 'Challenge from Host' in await fr.toast(), await fr.toast())
        await fr.ev("Nutcade.closeSheet()"); await fr.click('[data-act=tab][data-tab=arcade]'); await fr.wait(200)
        check('challenge: it waits in the Arcade', await fr.ev("!!document.querySelector('#challenges [data-act=chalOpen]')"))
        await fr.click('#challenges [data-act=chalOpen]'); await fr.wait(150); await fr.click('[data-act=chalPlay]'); await fr.wait(300)
        ch = await fr.ev("Arcade.playing() && Arcade.challenge()")
        check('challenge: Accept opens the game with the same seed and target', ch and ch['seed'] == 4242 and ch['target'] == 4200, ch)
        await fr.ev("document.querySelector('[data-g=exit]').click()"); await fr.wait(200)
        cid = await fr.ev("Nutcade.S.challenges[0].id")
        res = await fr.ev(f"Nutcade.challengeDone({json.dumps(cid)}, 5100, 'ROB')")
        check('challenge: a higher score wins', res['won'] and res['canReply'], res)
        await fr.ev(f"Nutcade.sendResult({json.dumps(cid)}, 5100, 'ROB')")
        ok = await w.until("Nutcade.S.challenges[0].results.some(r=>r.score===5100)", 15000)
        check('challenge: the result comes back to you, signed', ok and 'beat your challenge' in await w.toast(), await w.toast())
        # a challenge link, and a tampered one
        lk = await newwallet(b, 'linker'); await lk.create()
        await lk.pg.evaluate(f"location.hash = {json.dumps(link[link.index('#'):])}"); await lk.wait(1500)
        check('challenge: opening a challenge link shows it', 'challenges you' in (await lk.sheet_text()).lower(), await lk.sheet_text())
        ev = json.loads(base64.urlsafe_b64decode(link.split('#challenge=')[1] + '==='))
        body = json.loads(ev['content']); body['score'] = 10; ev['content'] = json.dumps(body)
        bad = base64.urlsafe_b64encode(json.dumps(ev).encode()).decode().rstrip('=')
        await lk.pg.goto('about:blank'); await lk.pg.goto(URL + '#challenge=' + bad); await lk.wait(1500)
        check('challenge: an edited score breaks the signature and is refused', "isn't valid" in await lk.toast() and await lk.ev("Nutcade.S.challenges.length") == 1, await lk.toast())
        await lk.pg.context.close()

        # ---------- round-up piggy bank ----------
        await w.home(); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
        await w.pg.check('#p_piggy'); await w.wait(200)
        check('piggy: turned on in Settings, rounding to 100', await w.ev("Nutcade.S.prefs.piggy===true && !!document.querySelector('#p_piggyStep')"))
        await w.use(A)
        tok, e = await w.send_ecash(1234, 'Snacks')
        t = await w.ev("Nutcade.S.txs[0]")
        check('piggy: a 1,234 sat payment puts 66 in the piggy bank', t.get('roundup') == 66 and await w.ev("Nutcade.piggySaved()") == 66, t.get('roundup'))
        await w.home()
        check('piggy: the wallet screen shows the piggy bank', await w.ev("!!document.querySelector('.piggy-panel') && /66 SAT in your piggy bank/.test(document.querySelector('.credits').innerText)"))
        tot, bA = await w.bal(), await w.bal(A)
        spend = bA - 300
        await w.ev(f"Nutcade.S.piggy.saved={tot - spend + 1000}; Nutcade.render()")
        n0 = await w.ev("Nutcade.S.txs.length")
        await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', str(spend)); await w.click('[data-act=doSendEcash]'); await w.wait(500)
        check('piggy: spending into it brings up BREAK THE PIGGY BANK?', await w.ev("!!document.querySelector('#piggyLayer') && document.querySelector('#pbYes').disabled"))
        await w.click('#pbNo'); await w.wait(200)
        check('piggy: Keep saving cancels the payment', await w.ev(f"!document.querySelector('#piggyLayer') && Nutcade.S.txs.length==={n0}"))
        await w.click('[data-act=doSendEcash]'); await w.wait(5600)
        check('piggy: the Break it button unlocks after a countdown', await w.ev("!document.querySelector('#pbYes').disabled"))
        await w.click('#pbYes')
        ok = await w.until(f"Nutcade.S.txs.length==={n0 + 1} && Nutcade.S.txs[0].amount==={spend}", 10000)
        check('piggy: breaking it lets the payment through', ok, await w.err())
        left = await w.ev("Nutcade.piggySaved()")
        check('piggy: what is left in the wallet stays saved', tot - spend - 20 <= left <= tot - spend, (left, tot - spend))
        await w.close()

        # ---------- translations and small screens ----------
        await w.pg.set_viewport_size({'width': 320, 'height': 640})
        miss = {}
        for lang in ['es', 'pt', 'de', 'fr']:
            await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
            await w.ev(f"window.__i18nMiss=new Set(); const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))")
            await w.wait(200); over = []
            check(f'translations ({lang}): the language switch applies', await w.ev(f"document.documentElement.lang.startsWith('{lang}')"))
            async def look(name, js):
                await w.ev(js); await w.wait(250)
                bad = await w.ev("""(()=>{const W=document.documentElement.clientWidth; const out=[]; for(const el of document.querySelectorAll('.sheet *, .cashier *, .screen *')){ if(!el.getClientRects().length) continue; const r=el.getBoundingClientRect(); if(r.right>W+1 || r.left<-1) out.push((el.className||el.tagName)+':'+Math.round(r.right)); } return out.slice(0,3)})()""")
                if bad: over.append((name, bad))
            await look('wallet', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click()")
            await look('mints', "document.querySelector('[data-act=tab][data-tab=mints]').click()")
            await look('settings', "document.querySelector('[data-act=tab][data-tab=settings]').click()")
            await look('send', "document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=send]').click(); document.querySelector('#giftOn').click()")
            await look('split', "document.querySelector('[data-act=splitOpen]').click()")
            await look('boss', "document.querySelector('#amtIn').value='900'; document.querySelector('#splitN').value='3'; document.querySelector('[data-act=splitCreate]').click()")
            await look('move', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=mints]').click(); document.querySelector('[data-act=moveOpen]').click()")
            await look('sound', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=history]').click(); document.querySelector('[data-act=tx]').click(); setTimeout(()=>{const b=document.querySelector('.sheet [data-act=ctPlay]'); if(b) b.click()},50)")
            await look('challenge', "Nutcade.closeSheet(); Chiptune.stop(); document.querySelector('[data-act=tab][data-tab=arcade]').click(); document.querySelector('[data-act=chalSendOpen]').click()")
            await look('till', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click(); document.querySelector('[data-act=tillOpen]').click()")
            await look('cashier', "Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=wallet]').click(); document.querySelector('[data-act=cashier]').click()")
            await w.ev("document.querySelector('.cashier') && document.querySelector('.cashier').remove(); document.body.style.overflow=''")
            m = await w.ev("[...window.__i18nMiss]")
            miss[lang] = m
            check(f'layout ({lang}): new screens fit a 320 px phone', not over, over)
        # Ignore what isn't a missing translation: text already translated (seen again after switching language),
        # names, #tags, numbers with units, dates, currency codes, and game and trophy titles, which stay in English.
        known = await w.ev("""(()=>{const v=new Set(); for (const d of Object.values(NUTCADE_I18N)) for (const x of Object.values(d.t)) v.add(x.replace(/\\d[\\d,.]*/g,'{#}'));
            const names=[...Arcade.games.map(g=>g.name), ...Trophies.DEFS.map(d=>d.name)].map(x=>x.toUpperCase()); return {v:[...v], names}})()""")
        vals, titles = set(known['v']), set(known['names'])
        def real(x):
            if re.sub(r'\d[\d,.]*', '{#}', x) in vals or x.upper() in titles or any(t.startswith(x.upper() + ' ') for t in titles): return False
            if x[:1] in '▲▼' or x.startswith('#') or x in ('Robin', 'Host', 'Mint A', 'Mint B', 'NUTCADE', 'LN', 'BTC /') or '/' in x or '₿' in x: return False
            if re.fullmatch(r'[A-Z]{3}|[\d,]+ (SAT|Sat|sat)|\d+[DHMWY]|\d+M AGO|HI -+', x): return False
            return True
        allmiss = sorted(set(x for x in sum(miss.values(), []) if real(x)))
        open(os.path.join(OUT, 'r4_i18n_missing.txt'), 'w').write('\n'.join(allmiss))
        check('translations: every new screen is translated (es, pt, de, fr)', not allmiss, allmiss[:12])
        await w.ev("Nutcade.closeSheet(); document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(100)
        await w.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))"); await w.pg.set_viewport_size({'width': 390, 'height': 844})

        check('no page errors in the main wallet', not w.errs, w.errs[:3])
        check('no page errors in the friend wallet', not fr.errs, fr.errs[:3])
        await b.close()
    n = len(results); ok = sum(1 for r in results if r[1])
    print(f'SUMMARY {ok}/{n} passed')

asyncio.run(main())
