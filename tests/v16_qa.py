"""v1.6 features: multinut (NUT-15), payment requests (NUT-18 over NIP-17 and HTTP POST) and NFC.
Uses the local mints (A and B allow multi-path payments in tests) and mock_nostr.py on port 3350.
Web NFC needs Android hardware, so these tests stand in a fake NDEFReader that records reads and writes."""
import asyncio, json, os, urllib.request
from playwright.async_api import async_playwright
from wallet_qa import W, newwallet, check, results, A, B, URL
from round2_qa import xonly, seed_of, mock

PEND = 'http://127.0.0.1:3341'
def invoice(n, mint=PEND):
    return json.loads(urllib.request.urlopen(urllib.request.Request(mint + '/v1/mint/quote/bolt11', data=json.dumps({'amount': n, 'unit': 'sat'}).encode(), headers={'Content-Type': 'application/json'})).read())['request']

FAKE_NFC = r"""
window.__nfcWritten = []; window.__nfcReaders = [];
window.NDEFReader = class { constructor(){ this.onreading=null; this.onreadingerror=null; }
  async scan(o){ window.__nfcReaders.push(this); if (o && o.signal) o.signal.addEventListener('abort', () => { window.__nfcReaders = window.__nfcReaders.filter(r => r !== this); }); }
  async write(m){ window.__nfcWritten.push(m.records.map(r => ({ recordType: r.recordType, mediaType: r.mediaType || null, text: typeof r.data === 'string' ? r.data : null, bytes: typeof r.data === 'string' ? null : Array.from(r.data) }))); } };
window.__nfcTap = recs => { const r = window.__nfcReaders[window.__nfcReaders.length - 1]; if (!r) return false;
  r.onreading && r.onreading({ serialNumber: '04:aa', message: { records: recs.map(x => ({ recordType: x.recordType, mediaType: x.mediaType, encoding: 'utf-8',
    data: new DataView((x.text != null ? new TextEncoder().encode(x.text) : new Uint8Array(x.bytes)).buffer) })) } }); return true; };
"""

async def funded(b, name, mints):
    w = await newwallet(b, name); await w.create()
    for url, amt in mints:
        await w.add_mint(url); await w.use(url); await w.receive_ln(amt)
    return w

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ---------------- multinut ----------------
        m = await funded(b, 'multi', [(A, 1000), (B, 1000)])
        a0, b0 = await m.bal(A), await m.bal(B)
        check('multinut: wallet holds sats at two mints', a0 == 1000 and b0 == 1000, (a0, b0))
        info = await m.ev(f"(async()=>{{const r=await fetch('{A}/v1/info').then(r=>r.json()); return !!r.nuts['15']}})()")
        check('multinut: test mints advertise NUT-15', info)
        inv = invoice(1500)
        await m.use(B); await m.home()
        await m.click('[data-act=send]'); await m.wait(150); await m.click('[data-act=sendMethod][data-m=ln]'); await m.wait(100)
        await m.fill('#destIn', inv); await m.click('[data-act=doMeltQuote]'); await m.wait(1500)
        txt = await m.sheet_text()
        check('multinut: quote screen says one mint is not enough', 'not enough on its own' in txt, txt[:200])
        check('multinut: offers to pay from several mints', await m.ev("!!document.querySelector('#mppBtn')"))
        await m.click('#mppBtn')
        ok = await m.until("!!document.querySelector('#mppPay')", 15000)
        plan = await m.sheet_text()
        check('multinut: plan splits the invoice across both mints', ok and plan.count('Mint ') >= 2 and '1,500' in plan, plan[:300])
        await m.click('#mppPay')
        ok = await m.until("document.querySelector('.sheet-body') && /SENT!/.test(document.querySelector('.sheet-body').innerText)", 20000)
        check('multinut: payment completes', ok, await m.sheet_text())
        a1, b1 = await m.bal(A), await m.bal(B)
        spent = (a0 + b0) - (a1 + b1)
        check('multinut: both mints paid a share', a1 < a0 and b1 < b0, (a1, b1))
        check('multinut: total spent is the invoice plus small fees', 1500 <= spent <= 1530, spent)
        parts = await m.ev("Nutcade.S.txs.filter(t=>/part \\d of 2/.test(t.note)).map(t=>t.status)")
        check('multinut: two parts recorded, both done', parts == ['done', 'done'], parts)
        check('multinut: nothing left in flight', await m.ev("Nutcade.S.pending.length") == 0)
        await m.close()
        # single mint: no split button
        one = await funded(b, 'onemint', [(B, 300)])
        await one.home(); await one.click('[data-act=send]'); await one.wait(150); await one.click('[data-act=sendMethod][data-m=ln]'); await one.wait(100)
        await one.fill('#destIn', invoice(100)); await one.click('[data-act=doMeltQuote]'); await one.wait(1200)
        check('multinut: no split offered with only one funded mint', not await one.ev("!!document.querySelector('#mppBtn')"))
        await one.pg.context.close()

        # ---------------- payment requests ----------------
        r = await funded(b, 'requester', [(B, 100)])
        phrase = await r.ev("Nutcade.S.seed.mnemonic")
        await r.home(); await r.click('[data-act=receive]'); await r.wait(150)
        await r.click('[data-act=recvMethod][data-m=ecash]'); await r.wait(100)
        await r.click('[data-act=reqOpen]'); await r.wait(150)
        await r.fill('#amtIn', '300'); await r.fill('#memoIn', 'Pizza night')
        await r.click('[data-act=reqCreate]'); await r.wait(400)
        enc = await r.ev("Nutcade.S.requests[0].encoded")
        check('request: creqA created', enc.startswith('creqA'), enc[:20])
        dec = await r.ev(f"(()=>{{const d=CashuLib.decodePaymentRequest({json.dumps(enc)}); const t=d.transport[0]; const n=CashuLib.nip19decode(t.target); return {{a:d.amount.toNumber(), memo:d.description, mints:d.mints, type:t.type, tags:t.tags, pub:n.data.pubkey}}}})()")
        check('request: amount, memo and mint list encoded', dec['a'] == 300 and dec['memo'] == 'Pizza night' and dec['mints'] == [B], dec)
        check('request: Nostr transport with NIP-17 tag', dec['type'] == 'nostr' and ['n', '17'] in dec['tags'], dec)
        check('request: delivered to the same Nostr key cashu.me uses (seed[0:32])', dec['pub'] == xonly(seed_of(phrase)[:32]), dec['pub'][:12])
        check('request: sheet shows QR and waits for payment', await r.ev("!!document.querySelector('.qr canvas, .qr img, canvas') && document.querySelector('#payState').innerText.includes('WAITING')"))
        ok = await r.until(f"fetch('{'http://127.0.0.1:3350'}/test/state').then(x=>x.json()).then(s=>true)", 3000)

        payer = await funded(b, 'payer', [(B, 2000)])
        await payer.ev(f"Nutcade.handleScan({json.dumps(enc)})"); await payer.wait(300)
        txt = await payer.sheet_text()
        check('pay request: scanning a creqA opens the pay sheet', 'pizza night' in txt.lower() and '300' in txt, txt[:200])
        await payer.click('[data-act=payReq]')
        ok = await payer.until("document.querySelector('.sheet-body') && /SENT!/.test(document.querySelector('.sheet-body').innerText)", 15000)
        check('pay request: delivered over Nostr', ok, await payer.sheet_text())
        ptx = await payer.ev("Nutcade.S.txs[0]")
        check('pay request: payer note and amount recorded', ptx['amount'] == 300 and ptx['note'] == 'Pizza night' and ptx.get('delivered'), {k: ptx.get(k) for k in ('amount', 'note', 'delivered')})
        st = mock('/test/state')
        wraps = [e for e in st['events'] if e['kind'] == 1059]
        check('pay request: sent as a NIP-17 gift wrap, contents encrypted', len(wraps) >= 1 and 'proofs' not in wraps[-1]['content'], len(wraps))
        check('pay request: one-time sender key, not the payer\'s identity', wraps and wraps[-1]['pubkey'] != xonly(seed_of(await payer.ev("Nutcade.S.seed.mnemonic"))[:32]))
        ok = await r.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=400", 12000)
        check('request: requester receives the 300 sats', ok, await r.bal())
        rtx = await r.ev("Nutcade.S.txs[0]")
        check('request: receipt noted with the request', rtx['note'] == 'Request: Pizza night' and rtx['status'] == 'done', rtx)
        check('request: open request sheet turns into 1UP', await r.until("document.querySelector('.sheet-body') && /1UP!/.test(document.querySelector('.sheet-body').innerText)", 4000))
        check('request: request marked paid', await r.ev("Nutcade.S.requests[0].paid.length") == 1)
        ok = await payer.until("Nutcade.S.txs[0].status==='claimed'", 10000)
        check('pay request: payer sees it claimed', ok)
        # duplicate delivery of the same payment is ignored
        n = await r.ev("Nutcade.S.txs.length")
        await r.ev("Nutcade.render()"); await r.wait(2500)
        check('request: same payment never counted twice', await r.ev("Nutcade.S.txs.length") == n)

        # a request limited to a mint the payer doesn't hold
        await r.close()
        await r.ev(f"(()=>{{const pr=new CashuLib.PaymentRequest([{{type:'post',target:'http://127.0.0.1:3350/test/post'}}],'post1',200,'sat',[{json.dumps(A)}],'Arcade tokens'); window.__post=pr.toEncodedRequest()}})()")
        post_req = await r.ev("window.__post")
        await payer.close(); await payer.ev(f"Nutcade.handleScan({json.dumps(post_req)})"); await payer.wait(300)
        txt = await payer.sheet_text()
        check('pay request: refuses mints the request does not accept', 'only accepts ecash from' in txt and '127.0.0.1:3338' in txt, txt[:200])
        # HTTP POST transport
        await payer.close(); await payer.add_mint(A); await payer.use(A); await payer.receive_ln(600)
        await payer.ev(f"Nutcade.handleScan({json.dumps(post_req)})"); await payer.wait(300)
        await payer.click('[data-act=payReq]')
        ok = await payer.until("document.querySelector('.sheet-body') && /SENT!/.test(document.querySelector('.sheet-body').innerText)", 15000)
        st = mock('/test/state')
        posted = st.get('posted', [])
        check('pay request: HTTP POST transport delivers the payload', ok and posted and posted[-1]['id'] == 'post1' and sum(int(x['amount']) for x in posted[-1]['proofs']) >= 200 and posted[-1]['mint'] == A, posted[-1:] and {k: posted[-1][k] for k in ('id', 'mint', 'unit')})
        await payer.close()

        # another Cashu wallet pays (built here from the bundled libraries, not NUTCADE's own code): ecash from a mint the requester doesn't use
        ext = await b.new_context(); xp = await ext.new_page(); await xp.goto(URL); await xp.wait_for_timeout(800)
        target = await r.ev("CashuLib.decodePaymentRequest(Nutcade.S.requests[0].encoded).transport[0].target")
        rid = await r.ev("Nutcade.S.requests[0].id")
        sent = await xp.evaluate(f"""(async()=>{{
          const L=CashuLib; const w=new L.Wallet({json.dumps(A)},{{unit:'sat'}}); await w.loadMint();
          const q=await w.createMintQuoteBolt11(150); for(let i=0;i<20;i++){{ const s=await w.checkMintQuoteBolt11(q.quote); if(s.state==='PAID') break; await new Promise(r=>setTimeout(r,300)); }}
          const proofs=(await w.mintProofsBolt11(150,q.quote)).map(p=>({{...p, amount: Number(p.amount)}}));
          const to=L.nip19decode({json.dumps(target)}).data.pubkey; const sk=crypto.getRandomValues(new Uint8Array(32));
          const ev=L.nip17.wrapEvent(sk,{{publicKey:to}},JSON.stringify({{id:{json.dumps(rid)},mint:{json.dumps(A)},unit:'sat',proofs}}));
          const ws=new WebSocket('ws://127.0.0.1:3350/relay'); await new Promise(r=>ws.onopen=r); ws.send(JSON.stringify(['EVENT',ev]));
          const ok=await new Promise(r=>ws.onmessage=m=>r(JSON.parse(m.data)[2])); ws.close(); return ok }})()""")
        check('external wallet published a gift-wrapped payment', sent)
        ok = await r.until(f"Nutcade.S.txs.some(t=>t.incoming && t.mint==={json.dumps(A)})", 12000)
        check('incoming ecash from an unknown mint waits for approval', ok and await r.ev(f"!Nutcade.S.mints.some(m=>m.url==={json.dumps(A)})"))
        tid = await r.ev("Nutcade.S.txs.find(t=>t.incoming).id")
        await r.click('[data-act=tab][data-tab=history]'); await r.wait(200); await r.click(f'[data-act=tx][data-id="{tid}"]'); await r.wait(200)
        await r.click('[data-act=claimIncoming]')
        ok = await r.until(f"(Nutcade.S.proofs[{json.dumps(A)}]||[]).reduce((t,p)=>t+p.amount,0)>=148", 12000)
        check('claiming it adds the mint and the sats', ok and not await r.ev("Nutcade.S.txs.some(t=>t.incoming)"), await r.bal(A))
        await ext.close(); await r.close()

        # ---------------- NFC ----------------
        nctx = await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        await nctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs',JSON.stringify({sound:true,crt:true,relays:['ws://127.0.0.1:3350/relay'],npcHost:'http://127.0.0.1:3350'}))")
        await nctx.add_init_script(FAKE_NFC)
        npg = await nctx.new_page(); n = W(npg, 'nfc'); npg.on('pageerror', lambda e: n.errs.append(str(e)))
        await npg.goto(URL); await npg.wait_for_timeout(800); await n.create(); await n.add_mint(B); await n.use(B); await n.receive_ln(800)
        await r.home()
        check('NFC: not offered where the browser lacks Web NFC', not await r.ev("document.querySelector('[data-act=scan]').click(), new Promise(res=>setTimeout(()=>res(!!document.querySelector('[data-act=nfcScan]')),300))"))
        await r.ev("Nutcade.closeSheet()")
        await n.home(); await n.click('[data-act=scan]'); await n.wait(300)
        check('NFC: scanner offers Tap NFC on supported phones', await n.ev("!!document.querySelector('[data-act=nfcScan]')"))
        # write a token to a card, then read it back as text and as compact binary
        tok, e = await n.send_ecash(120, 'card for Max')
        await n.click('[data-act=tab][data-tab=history]'); await n.wait(150)
        tid = await n.ev("Nutcade.S.txs.find(t=>t.token).id"); await n.click(f'[data-act=tx][data-id="{tid}"]'); await n.wait(200)
        await n.click('[data-act=nfcWrite]'); await n.wait(400)
        wr = await n.ev("window.__nfcWritten")
        check('NFC: token written to the card', wr and wr[-1][0]['recordType'] in ('text', 'mime'), wr and wr[-1][0]['recordType'])
        await n.close()
        friend = await newwallet(b, 'friend'); await friend.create(); await friend.add_mint(B)
        await friend.pg.evaluate(FAKE_NFC)
        await friend.home(); await friend.click('[data-act=scan]'); await friend.wait(200)
        await friend.click('[data-act=nfcScan]'); await friend.wait(200)
        rec = wr[-1][0]
        tapped = await friend.ev(f"window.__nfcTap([{json.dumps({'recordType': 'text', 'text': tok})}])")
        await friend.wait(500)
        got = await friend.ev("(document.querySelector('#tokIn')||{}).value||''")
        check('NFC: tapping the card opens Receive with the token', tapped and got == tok, got[:20])
        await friend.click('[data-act=doReceiveToken]'); await friend.wait(1200)
        if await friend.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await friend.click('[data-act=doReceiveToken]')
        ok = await friend.until("Object.values(Nutcade.S.proofs).flat().length>0", 10000)
        check('NFC: ecash from the card is claimed', ok, await friend.bal())
        await friend.close()
        bin_tok = await n.ev(f"Array.from(CashuLib.getEncodedTokenBinary(CashuLib.getDecodedToken({json.dumps(tok)}, Object.keys(Nutcade.S.counters))))")
        await friend.click('[data-act=scan]'); await friend.wait(200); await friend.click('[data-act=nfcScan]'); await friend.wait(200)
        await friend.ev(f"window.__nfcTap([{{recordType:'mime',mediaType:'application/octet-stream',bytes:{json.dumps(bin_tok)}}}])"); await friend.wait(500)
        check('NFC: compact binary cards (cashu.me format) are read too', await friend.ev("(document.querySelector('#tokIn')||{}).value||''") == tok)
        await friend.close()
        # a link to a token (as written by URL cards) opens Receive after unlock
        lp = await friend.pg.context.new_page(); await lp.goto(URL + '#token=' + tok); await lp.wait_for_timeout(1500)
        check('link with #token= opens Receive with the token', await lp.evaluate("(document.querySelector('#tokIn')||{}).value||''") == tok and '#token' not in await lp.evaluate("location.href"))
        await lp.close()
        # payment request onto an NFC tag
        await n.home(); await n.click('[data-act=receive]'); await n.wait(150); await n.click('[data-act=recvMethod][data-m=ecash]'); await n.wait(100)
        await n.click('[data-act=reqOpen]'); await n.wait(150); await n.click('[data-act=reqCreate]'); await n.wait(400)
        await n.click('[data-act=nfcWrite]'); await n.wait(300)
        wr = await n.ev("window.__nfcWritten")
        check('NFC: payment request written to a tag', wr[-1][0]['text'].startswith('creqA'))
        await n.close()

        errs = [e for w in (m, r, payer, n, friend) for e in w.errs if 'WebSocket' not in e]
        check('no page errors', not errs, errs[:5])
        await b.close()
    fails = [x for x in results if not x[1]]
    print(f"SUMMARY {len(results) - len(fails)}/{len(results)} passed")

asyncio.run(main())
