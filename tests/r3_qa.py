"""Round 3: amounts in your currency, #tags and CSV export, contacts (Lightning address and ecash over Nostr),
and offline use (service worker, offline send of exact amounts, tokens saved offline and claimed later).
Uses the local mints and mock_nostr.py; a Lightning address is stood in by routing https://pay.test."""
import asyncio, csv, io, json, os, re, urllib.request, urllib.parse
from playwright.async_api import async_playwright
from wallet_qa import W, newwallet, check, results, A, B, URL

PEND = 'http://127.0.0.1:3341'

async def lnurl_route(route):
    u = urllib.parse.urlparse(route.request.url)
    if u.path.startswith('/.well-known/lnurlp/'):
        await route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'},
                            body=json.dumps({'tag': 'payRequest', 'callback': 'https://pay.test/cb', 'minSendable': 1000, 'maxSendable': 10**10, 'metadata': '[["text/plain","alex"]]'}))
    elif u.path == '/cb':
        msat = int(urllib.parse.parse_qs(u.query)['amount'][0])
        q = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(urllib.request.Request(PEND + '/v1/mint/quote/bolt11', data=json.dumps({'amount': msat // 1000, 'unit': 'sat'}).encode(), headers={'Content-Type': 'application/json'})).read()))
        await route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'pr': q['request']}))
    else:
        await route.fulfill(status=404, body='')

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'r3')
        await w.pg.context.route('https://pay.test/**', lnurl_route)
        # pin the Bitcoin price so the currency checks don't depend on the live market (CI can reach Coinbase)
        async def fixed_rate(route):
            if 'exchange-rates' in route.request.url: await route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps({'data': {'currency': 'BTC', 'rates': {'USD': '50000'}}}))
            else: await route.abort()
        await w.pg.context.route(re.compile(r'https://api(\.exchange)?\.coinbase\.com/.*'), fixed_rate)
        await w.pg.context.route_web_socket(re.compile('coinbase'), lambda ws: None)
        await w.create(); await w.add_mint(B); await w.use(B)

        # ---------- amounts in your currency ----------
        await w.ev("Nutcade.livePrice(50000,'USD')")
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
        check('fiat: amount field has a SAT / currency switch', await w.ev("!!document.querySelector('.amtwrap .unitbtn')"))
        await w.click('.unitbtn'); await w.wait(100)
        check('fiat: switch shows the currency', await w.ev("document.querySelector('.unitbtn').textContent") == 'USD')
        await w.fill('#amtIn', '1.00'); await w.wait(100)
        conv = await w.ev("document.querySelector('.amtconv').textContent")
        check('fiat: $1.00 at $50,000 shows ≈ 2,000 SAT', '2,000' in conv, conv)
        await w.click('[data-act=doLnInvoice]')
        ok = await w.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=2000", 15000)
        tx = await w.ev("Nutcade.S.txs[0]")
        check('fiat: invoice made for the converted sats', ok and tx['amount'] == 2000, tx.get('amount'))
        check('fiat: rate recorded on the transaction', tx.get('fx') == {'cur': 'USD', 'rate': 50000}, tx.get('fx'))
        await w.close()
        await w.click('[data-act=send]'); await w.wait(150)
        check('fiat: the choice is remembered', await w.ev("document.querySelector('.unitbtn').textContent") == 'USD')
        await w.click('.unitbtn'); await w.close()
        await w.receive_ln(3000)

        # ---------- tags and CSV ----------
        await w.ev("""(()=>{const t=Nutcade.S.txs; t[0].note='Paycheck #work'; t[1].note='Lunch #food #friends'; Nutcade.render()})()""")
        await w.ev("Nutcade.S.txs.push({id:'x1',ts:Date.now()-1e6,type:'out',method:'ecash',amount:5,fee:0,status:'done',mint:'"+B+"',note:'=HYPERLINK(\"evil\") #food'}); Nutcade.render()")
        await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        tags = await w.ev("[...document.querySelectorAll('[data-act=htag]')].map(b=>b.dataset.tag)")
        check('tags: #tags from notes become filter chips', tags[:1] == ['food'] and set(tags) == {'food', 'work', 'friends'}, tags)
        await w.click('[data-act=htag][data-tag=food]'); await w.wait(100)
        check('tags: filtering by #food shows only those', await w.ev("document.querySelectorAll('#txList .tx').length") == 2)
        async with w.pg.expect_download() as d:
            await w.click('[data-act=csv]')
        dl = await d.value
        text = open(await dl.path(), encoding='utf-8-sig').read()
        rows = list(csv.DictReader(io.StringIO(text)))
        check('CSV: one row per transaction with the right columns', len(rows) == await w.ev("Nutcade.S.txs.length") and 'fiat_value' in rows[0], list(rows[0].keys())[:6])
        r0 = [r for r in rows if r['note'].startswith('Lunch')][0]
        check('CSV: amount, tags and fiat value', r0['amount_sat'] == '2000' and r0['tags'] == 'food friends' and r0['fiat_value'] == '1.00', r0)
        check('CSV: spreadsheet formulas in notes are neutralised', any(r['note'].startswith("'=HYPERLINK") for r in rows))
        await w.ev("Nutcade.S.txs.splice(Nutcade.S.txs.findIndex(t=>t.id==='x1'),1); Nutcade.render()")

        # ---------- contacts ----------
        friend = await newwallet(b, 'friend'); await friend.create(); await friend.add_mint(B)
        addr = await friend.ev("(()=>{document.querySelector('[data-act=tab][data-tab=settings]').click(); return CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})})()")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
        await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
        await w.click('[data-act=contactEdit]'); await w.wait(100)
        await w.fill('#cName', 'Alex'); await w.fill('#cLn', 'not-an-address'); await w.click('[data-act=contactSave]'); await w.wait(200)
        check('contacts: a bad Lightning address is refused clearly', 'look right' in await w.err())
        await w.fill('#cLn', 'alex@pay.test'); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(300)
        check('contacts: saved with Lightning and Nostr addresses', await w.ev("Nutcade.S.contacts.length===1 && Nutcade.S.contacts[0].ln==='alex@pay.test' && Nutcade.S.contacts[0].pubkey.length===64"))
        await w.close(); await w.home(); await w.click('[data-act=send]'); await w.wait(150)
        check('contacts: Send shows contact chips', await w.ev("!!document.querySelector('[data-act=payContact]')"))
        await w.click('[data-act=payContact]'); await w.wait(150)
        await w.fill('#amtIn', '150'); await w.fill('#noteIn', 'Movie #fun')
        await w.click('[data-act=contactEcash]')
        ok = await w.until("document.querySelector('.sheet-body') && /SENT!/.test(document.querySelector('.sheet-body').innerText)", 15000)
        check('contacts: ecash sent to Alex over Nostr', ok, await w.sheet_text())
        t = await w.ev("Nutcade.S.txs[0]")
        check('contacts: payment tagged with the contact', t.get('contactName') == 'Alex' and t.get('delivered') is True, {k: t.get(k) for k in ('contactName', 'delivered')})
        ok = await friend.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=150", 15000)
        ft = await friend.ev("Nutcade.S.txs[0]")
        check('contacts: friend receives it over Nostr with the note', ok and ft['note'] == 'Movie #fun', ft.get('note'))
        await w.close()
        # pay the Lightning address of a contact
        await w.click('[data-act=send]'); await w.wait(150); await w.click('[data-act=payContact]'); await w.wait(150)
        await w.fill('#amtIn', '100'); await w.click('[data-act=contactLn]')
        await w.until("!!document.querySelector('#payBtn')", 10000); await w.click('#payBtn')
        ok = await w.until("document.querySelector('.sheet-body') && /SENT!/.test(document.querySelector('.sheet-body').innerText)", 15000)
        t = await w.ev("Nutcade.S.txs[0]")
        check('contacts: Lightning address payment to Alex', ok and t['method'] == 'ln' and t.get('contactName') == 'Alex', {k: t.get(k) for k in ('method', 'status', 'contactName')})
        await w.close()
        # paying a new Lightning address offers to save it
        await w.ev("Nutcade.handleScan('sam@pay.test')"); await w.wait(200)
        await w.fill('#amtIn', '50'); await w.click('[data-act=lnurlQuote]')
        await w.until("!!document.querySelector('#payBtn')", 10000); await w.click('#payBtn')
        await w.until("!!document.querySelector('[data-act=contactFrom]')", 15000)
        await w.click('[data-act=contactFrom]'); await w.wait(150)
        check('contacts: offer to save a new Lightning address as a contact', await w.ev("document.querySelector('#cLn').value") == 'sam@pay.test')
        await w.close()
        await w.ev(f"Nutcade.handleScan('nostr:' + {json.dumps(addr)})"); await w.wait(200)
        check('contacts: scanning a known Nostr address opens Pay Alex', 'Alex' in await w.ev("document.querySelector('.sheet-head h3').textContent"))
        await w.close(); await friend.pg.context.close()

        # ---------- offline ----------
        ctx = w.pg.context
        ready = await w.ev("navigator.serviceWorker ? navigator.serviceWorker.ready.then(()=>true) : false")
        check('offline: service worker installed', ready)
        bal = await w.bal()
        await ctx.set_offline(True); await w.wait(300)
        check('offline: banner appears', await w.ev("!!document.getElementById('netBanner')"))
        await w.pg.reload(); await w.wait(1500)
        check('offline: the app still opens with your balance', await w.ev("!!document.querySelector('.credit-num')") and await w.bal() == bal, await w.bal())
        have = await w.ev(f"Nutcade.S.proofs[{json.dumps(B)}].map(p=>p.amount)")
        small = min(have)
        tok, e = await w.send_ecash(small, 'offline snack')
        check('offline: send an exact amount without the mint', bool(tok) and await w.ev("Nutcade.S.txs[0].offline===true"), e)
        odd = sum(have) + 1
        tok2, e2 = await w.send_ecash(3 if small != 1 and 3 not in have else odd, 'nope')
        check('offline: other amounts explain what can be sent', 'Offline' in e2 and 'Try' in e2 or 'Not enough' in e2, e2)
        await ctx.set_offline(False); await w.wait(300)
        # someone gives us a token while we're offline
        giver = await newwallet(b, 'giver'); await giver.create(); await giver.add_mint(B); await giver.receive_ln(400)
        gtok, _ = await giver.send_ecash(200, 'cash')
        await ctx.set_offline(True); await w.wait(200)
        before = await w.bal()
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100)
        await w.fill('#tokIn', gtok); await w.click('[data-act=doReceiveToken]'); await w.wait(600)
        check('offline: received token is saved to claim later', 'saved' in await w.sheet_text() and await w.ev("Nutcade.S.txs.some(t=>t.incoming && t.offline)"))
        await w.close()
        await ctx.set_offline(False)
        ok = await w.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>={before + 195}", 15000)
        check('offline: claimed automatically when back online', ok and not await w.ev("Nutcade.S.txs.some(t=>t.incoming && t.offline)"), (before, await w.bal()))
        check('offline: banner gone when online', not await w.ev("!!document.getElementById('netBanner')"))
        await giver.pg.context.close()

        # ---------- languages ----------
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        await w.pg.select_option('#p_lang', 'es'); await w.wait(400)
        tabs = await w.ev("[...document.querySelectorAll('.tab span')].map(s=>s.textContent)")
        check('languages: switching to Spanish translates the tabs', tabs[0] == 'CARTERA' and tabs[4] == 'AJUSTES', tabs)
        check('languages: settings text translated', 'Seguridad' in await w.ev("document.querySelector('#set-security').innerText"))
        await w.ev("Nutcade.toast('Note saved')"); await w.wait(100)
        check('languages: toasts translated', await w.toast() == 'Nota guardada', await w.toast())
        await w.ev("Nutcade.S.txs[0].note='Done'; Nutcade.render()"); await w.click('[data-act=tab][data-tab=history]'); await w.wait(150)
        check('languages: your own notes are never translated', await w.ev("[...document.querySelectorAll('#txList .note')].some(n=>n.textContent==='Done')"))
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=seedShow]'); await w.wait(200)
        words = await w.ev("[...document.querySelectorAll('.words li')].map(l=>l.lastChild.textContent).join(' ')")
        check('languages: recovery words are never translated', words == await w.ev("Nutcade.S.seed.mnemonic"), words[:30])
        await w.close(); await w.home()
        await w.click('[data-act=send]'); await w.wait(150)
        check('languages: amounts in sheets keep their numbers', 'disponibles' in await w.sheet_text())
        await w.close(); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
        await w.pg.select_option('#p_lang', 'en'); await w.wait(400)
        check('languages: switching back to English', await w.ev("document.querySelector('.tab span').textContent") == 'WALLET')
        dctx = await b.new_context(locale='de-DE'); dp = await dctx.new_page(); await dp.goto(URL); await dp.wait_for_timeout(900)
        check('languages: picks German automatically from the browser', 'WILLKOMMEN' in await dp.evaluate("document.querySelector('.gate-h').textContent") and await dp.evaluate("document.documentElement.lang") == 'de')
        await dctx.close()

        errs = [e for e in w.errs if 'WebSocket' not in e and 'ERR_INTERNET_DISCONNECTED' not in e and 'Failed to fetch' not in e]
        check('no page errors', not errs, errs[:5])
        await b.close()
    fails = [x for x in results if not x[1]]
    print(f"SUMMARY {len(results) - len(fails)}/{len(results)} passed")

if __name__ == '__main__':
    asyncio.run(main())
