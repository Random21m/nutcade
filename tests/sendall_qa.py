"""Send all (1.22.0): everything at the active mint, less the fees, as an ecash token, to a Lightning address / LNURL, or
on-chain. A grid of fee edge cases, each with exact balances afterwards, at the mint swept AND at the other mint (which must
never be touched). Uses the local mints 3338 (input fees, 100 ppk; Lightning fee reserve max(2 SAT, 1%)), 3339 (no fees;
a payment to one of its own invoices has no fee reserve), 3340 (every Lightning payment fails) and mock_nostr.py (the
Lightning addresses at lnurl.test). The mints have no on-chain backend, so on-chain is tested with the mint's info, quotes
and melt answered by the test (page.route): the swap before the melt and the coin checks are real.

Cases: zero fee (ecash, Lightning); input fees (ecash, with the token claimed by another wallet for exactly its amount;
Lightning); a balance of 1, 2 and 3 SAT at a fee mint (fee larger than, equal to, and just under the balance); dust below
an address's minimum; a fee quote that changes between quotes; the balance changing between the confirm screen and the
send (nothing sent); Cancel on every confirm screen; the spending limit and its PIN; a Lightning invoice has no Send all;
a failed payment (Lightning and on-chain) leaves every coin. SA_ONLY=a,b runs some sections (names start with those)."""
import asyncio, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, A, B, F, invoice
from r8_qa import wallet, set_pin, set_limits, layer_pin, PIN

J = json.dumps
MOCK = 'http://127.0.0.1:3350'
_n = [0]


def payee(mint, mn=1, mx=1000000):
    """a Lightning address at lnurl.test whose invoices come from `mint`"""
    _n[0] += 1; name = f'sa{int(time.time()) % 100000}x{_n[0]}'
    req = urllib.request.Request(MOCK + '/test/lnurlp', data=J({'name': name, 'zap': False, 'mint': mint, 'min': mn, 'max': mx}).encode(), method='POST', headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())['address']


async def section(name, fn):
    only = [x for x in os.environ.get('SA_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def two_mints(b, at_a, at_b, active, init=None):
    """a wallet holding at_a SAT at mint A and at_b at mint B (0: the mint is added, nothing received), with `active` picked"""
    w = await wallet(b, init=init)
    await w.create()
    for url, amt in ((A, at_a), (B, at_b)):
        await w.add_mint(url)
        for a in (amt if isinstance(amt, (list, tuple)) else [amt]):
            if a: await w.receive_ln(a)
    await w.use(active); await w.home(); await w.wait(300)
    return w


async def bals(w): return (await w.bal(A), await w.bal(B))
async def ntx(w): return await w.ev("Nutcade.S.txs.length")
KV = "[...document.querySelectorAll('#layer dl.kv dt')].reduce((o,dt)=>{o[dt.innerText.trim()]=parseInt(dt.nextElementSibling.innerText.replace(/[^0-9]/g,''),10); return o},{})"
WAIT_SHEET = "!!document.querySelector('{sel}') || !!((document.querySelector('#sheetErr')||{{}}).innerText||'').trim() || !!document.querySelector('#limitLayer')"


async def open_send(w, method='ecash'):
    await w.home(); await w.click('[data-act=send]'); await w.wait(150)
    if method != 'ecash': await w.click(f'[data-act=sendMethod][data-m={method}]'); await w.wait(150)


async def ecash_all(w):
    """Send -> Send all (ecash): (error text, the confirm screen's numbers)"""
    await open_send(w); await w.click('[data-act=allEcash]')
    await w.until(WAIT_SHEET.format(sel='#allGo'), 20000)
    return (await w.err()).strip(), await w.ev(KV)


async def create(w, n0):
    """press Create token on the confirm screen; ('ok', tx) / ('err', text) / ('limit', text)"""
    await w.click('#allGo')
    js = f"""(()=>{{const L=document.querySelector('#limitLayer'); if(L) return ['limit', L.innerText];
      const e=(document.querySelector('#sheetErr')||{{}}).innerText||''; if(e.trim()) return ['err', e];
      if(Nutcade.S.txs.length>{n0} && Nutcade.S.txs[0].token && !document.querySelector('#allGo')) return ['ok', Nutcade.S.txs[0]]; return null}})()"""
    for _ in range(120):
        r = await w.ev(js)
        if r: return r
        await w.wait(250)
    return ['timeout', await w.sheet_text()]


async def ln_all(w, addr):
    """Pay screen of a Lightning address -> Send all: (error text, the confirm screen's numbers)"""
    await w.home(); await w.ev(f"Nutcade.handleScan({J(addr)})"); await w.until("!!document.querySelector('[data-act=lnurlAll]')", 8000)
    await w.click('[data-act=lnurlAll]')
    await w.until(WAIT_SHEET.format(sel='#payBtn'), 30000)
    return (await w.err()).strip(), await w.ev(KV)


async def pay(w, n0, ms=40000):
    """press Pay; ('ok'|'pending'|'failed', tx) once its line has settled, ('err', text), ('limit', text)"""
    await w.click('#payBtn')
    js = f"""(()=>{{const L=document.querySelector('#limitLayer'); if(L) return ['limit', L.innerText];
      const e=(document.querySelector('#sheetErr')||{{}}).innerText||''; if(e.trim()) return ['err', e];
      const t=Nutcade.S.txs.slice(0, Nutcade.S.txs.length-{n0}).find(t=>t.type==='out'&&t.method!=='fee');
      if(t && !document.querySelector('#layer .spinner') && !Nutcade.S.pending.length) return [t.status==='done'?'ok':t.status, t]; return null}})()"""
    for _ in range(ms // 250):
        r = await w.ev(js)
        if r: return r
        await w.wait(250)
    return ['timeout', await w.sheet_text()]


def bech32_addr(hrp, prog=bytes(range(1, 21))):
    CH = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    def polymod(v):
        g = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; c = 1
        for x in v:
            b0 = c >> 25; c = (c & 0x1ffffff) << 5 ^ x
            for i in range(5): c ^= g[i] if ((b0 >> i) & 1) else 0
        return c
    acc, bits, d = 0, 0, [0]
    for x in prog:
        acc = (acc << 8) | x; bits += 8
        while bits >= 5: bits -= 5; d.append((acc >> bits) & 31)
    if bits: d.append((acc << (5 - bits)) & 31)
    hx = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = polymod(hx + d + [0] * 6) ^ 1
    return hrp + '1' + ''.join(CH[x] for x in d + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ======================= ecash, no fee: everything, exactly =======================
        async def ecash_zero():
            w = await two_mints(b, 300, [500, 200], B)
            a0, b0 = await bals(w); n0 = await ntx(w)
            e, kv = await ecash_all(w)
            check('ecash, no fee: the confirm screen shows the whole balance, a fee of 0 and nothing staying',
                  not e and kv.get('Token') == 700 and kv.get('Mint fee') == 0 and kv.get('Leaves your balance') == 700 and 'Stays at this mint' not in kv, (e, kv))
            txt = await w.sheet_text()
            check('ecash: the confirm screen says Send all and names the mint', 'Send all' in txt and 'Mint B' in txt, txt[:200])
            await w.click('#layer [data-act=close]'); await w.wait(300)
            check('ecash: Cancel on the confirm screen changes nothing (both mints, history)', await bals(w) == (a0, b0) and await ntx(w) == n0, await bals(w))
            e, kv = await ecash_all(w)
            r = await create(w, n0)
            t = r[1] if r[0] == 'ok' else {}
            check('ecash, no fee: the token is the whole balance (700), with no fee', r[0] == 'ok' and t.get('amount') == 700 and t.get('fee') == 0 and t.get('mint') == B, r)
            check('ecash, no fee: mint B is at 0 and mint A untouched (300)', await bals(w) == (300, 0), await bals(w))
            # the token is worth exactly that
            w2 = await two_mints(b, 0, 0, B)
            tr, e2, _ = await w2.receive_token(t.get('token', ''), 'all of it')
            check('ecash, no fee: the receiver gets exactly 700', not e2 and await w2.bal(B) == 700, (e2, await w2.bal(B)))
            # one SAT, no fee
            await w.use(B); await w.receive_ln(1); await w.use(B); await w.home()
            e, kv = await ecash_all(w); n1 = await ntx(w)
            r = await create(w, n1)
            check('ecash, no fee, a balance of 1 SAT: a token of 1, balance 0, A untouched', not e and kv.get('Token') == 1 and r[0] == 'ok' and r[1].get('amount') == 1 and await bals(w) == (300, 0), (e, kv, r[0], await bals(w)))
            e, kv = await ecash_all(w)
            check('ecash: an empty mint is refused with a sentence, nothing sent', 'Nothing to send' in e and await bals(w) == (300, 0), e)
            check('ecash, no fee: no script errors', not w.errs and not w2.errs, (w.errs + w2.errs)[:4])
            await w.pg.context.close(); await w2.pg.context.close()

        # ======================= ecash, input fees =======================
        async def ecash_fee():
            w = await two_mints(b, [500, 300, 77], 250, A)
            a0, b0 = await bals(w); n0 = await ntx(w)
            coins = await w.ev(f"Nutcade.S.proofs[{J(A)}].length")
            e, kv = await ecash_all(w)
            exp_in = -(-coins * 100 // 1000)
            check('ecash, input fees: the numbers add up: token + fee = what leaves; what leaves + what stays = the balance',
                  not e and kv.get('Token', 0) > 0 and kv['Token'] + kv['Mint fee'] == kv['Leaves your balance'] and kv['Leaves your balance'] + kv.get('Stays at this mint', 0) == a0, (e, kv, a0))
            check(f'ecash, input fees: the fee covers spending all {coins} coins ({exp_in}) and the token\'s own fee', kv.get('Mint fee', 0) >= exp_in + 1 and kv.get('Stays at this mint', 0) <= 2, kv)
            r = await create(w, n0); t = r[1] if r[0] == 'ok' else {}
            check('ecash, input fees: the token is exactly the amount shown, with exactly the fee shown', r[0] == 'ok' and t.get('amount') == kv['Token'] and t.get('fee') == kv['Mint fee'], (r[0], t.get('amount'), t.get('fee'), kv))
            check('ecash, input fees: mint A keeps exactly what the screen said stays; mint B untouched', await bals(w) == (kv.get('Stays at this mint', 0), b0), (await bals(w), kv))
            w2 = await two_mints(b, 0, 0, A)
            tr, e2, _ = await w2.receive_token(t.get('token', ''), 'all of it')
            check('ecash, input fees: the receiver gets exactly the token amount (its fee was carried)', not e2 and await w2.bal(A) == kv['Token'], (e2, await w2.bal(A), kv))
            await w2.pg.context.close()
            # 1, 2 and 3 SAT at the fee mint: fee larger than, equal to, and just under the balance
            await w.use(A); await w.ev(f"Nutcade.S.proofs[{J(A)}]=[]; Nutcade.render()")   # (the SAT or two that stayed are set aside, so A starts empty)
            await w.receive_ln(1); await w.use(A)
            e, kv = await ecash_all(w)
            check('ecash, 1 SAT at a fee mint: refused, the fee (2) is larger than the balance (1); nothing sent', 'The fees (2 SAT) are as much as' in e and 'balance of 1 SAT' in e and await bals(w) == (1, b0), (e, await bals(w)))
            await w.receive_ln(1); await w.use(A)
            e, kv = await ecash_all(w)
            check('ecash, 2 SAT at a fee mint (two coins): refused, the fee equals the balance; nothing sent', 'The fees (2 SAT)' in e and 'balance of 2 SAT' in e and await bals(w) == (2, b0), (e, await bals(w)))
            await w.receive_ln(1); await w.use(A); n2 = await ntx(w)
            e, kv = await ecash_all(w)
            check('ecash, 3 SAT at a fee mint: a token of 1, fee 2, nothing stays', not e and kv.get('Token') == 1 and kv.get('Mint fee') == 2 and kv.get('Leaves your balance') == 3 and 'Stays at this mint' not in kv, (e, kv))
            r = await create(w, n2)
            check('ecash, 3 SAT at a fee mint: sent; A at 0, B untouched', r[0] == 'ok' and r[1].get('amount') == 1 and r[1].get('fee') == 2 and await bals(w) == (0, b0), (r[0], await bals(w)))
            check('ecash, input fees: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= ecash: the balance changes after the confirm screen =======================
        async def ecash_changed():
            w = await two_mints(b, 100, 400, B)
            e, kv = await ecash_all(w)
            await w.ev(f"Nutcade.r8.sendEcash(5, 'meanwhile', null, {J(B)})"); await w.wait(500)   # (another step spends 5 at B)
            n0 = await ntx(w)
            r = await create(w, n0)
            check('ecash: the balance changed after the confirm screen: nothing is sent, with a sentence', r[0] == 'err' and 'changed' in r[1] and 'nothing was sent' in r[1], r)
            check('ecash: ... B lost only the other step\'s 5, A untouched, no new history line', await bals(w) == (100, 395) and await ntx(w) == n0, await bals(w))
            await w.close(); await w.ev("Nutcade.S.prefs.hideAmounts=true; Nutcade.render()"); e, kv = await ecash_all(w)
            check('ecash: Send all again shows the new amount, the real one even with Hide amounts on', kv.get('Token') == 395 and '•' not in await w.sheet_text(), kv)
            await w.ev("Nutcade.S.prefs.hideAmounts=false; Nutcade.render()")
            # the lock (gift) is on: refused
            await w.close(); await open_send(w)
            if await w.ev("!!document.querySelector('#giftOn')"):
                await w.ev("const g=document.querySelector('#giftOn'); g.checked=true; g.dispatchEvent(new Event('change',{bubbles:true}))")
                await w.click('[data-act=allEcash]'); await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 5000)
                check('ecash: Send all with the gift lock on is refused, nothing sent', 'Turn off the lock' in await w.err() and await bals(w) == (100, 395), await w.err())
            check('ecash changed: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= the spending limit and its PIN =======================
        async def limit():
            w = await two_mints(b, 100, 600, B)
            await set_pin(w); await set_limits(w, '50', '', PIN)
            a0, b0 = await bals(w); n0 = await ntx(w)
            e, kv = await ecash_all(w)
            r = await create(w, n0)
            check('limit: Send all over the per-payment limit waits for the PIN, saying the real amount', r[0] == 'limit' and '600 SAT' in r[1], r)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]').click()"); await w.wait(400)
            check('limit: Cancel there sends nothing', await bals(w) == (a0, b0) and await ntx(w) == n0, await bals(w))
            r = await create(w, n0)
            if r[0] == 'limit': await layer_pin(w)
            await w.until(f"Nutcade.S.txs.length>{n0} && !!Nutcade.S.txs[0].token", 20000)
            check('limit: with the PIN it goes through: B at 0, A untouched', await bals(w) == (100, 0) and await w.ev("Nutcade.S.txs[0].amount") == 600, await bals(w))
            # the daily limit counts it: Lightning Send all from A is now over the day's limit
            await w.close(); await set_limits(w, '', '650', PIN); await w.use(A)
            n1 = await ntx(w)
            e, kv = await ln_all(w, payee(B))
            r = await pay(w, n1)
            check('limit: Lightning Send all over the day\'s limit is held too; Cancel sends nothing', r[0] == 'limit' and 'a day' in r[1], r)
            await w.ev("document.querySelector('#limitLayer [data-act=limitNo]').click()"); await w.wait(400)
            check('limit: ... balances as they were', await bals(w) == (100, 0) and await ntx(w) == n1, await bals(w))
            check('limit: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= Lightning address: no fee, input fees, dust, fees >= balance =======================
        async def lightning():
            w = await two_mints(b, 400, 300, B)
            # an invoice (its own amount) has no Send all
            await open_send(w, 'ln')
            check('lightning: the invoice screen has no Send all', not await w.ev("!!document.querySelector('#layer [data-act=lnurlAll],#layer [data-act=allEcash]')"))
            await w.fill('#destIn', invoice(10, A)); await w.click('[data-act=doMeltQuote]'); await w.until("!!document.querySelector('#payBtn')", 15000)
            check('lightning: ... nor the confirm screen of an invoice', 'Send all' not in await w.sheet_text())
            await w.close()
            # no fee: an address whose invoices come from B itself (internal: no fee reserve), paid from B
            a0, b0 = await bals(w); n0 = await ntx(w)
            addr = payee(B)
            e, kv = await ln_all(w, addr)
            check('lightning, no fee: the confirm screen shows the whole balance and no fees', not e and kv.get('Pay') == 300 and kv.get('Fee reserve') == 0 and kv.get('Total, at most') == 300, (e, kv))
            check('lightning: the confirm screen says Send all and has Cancel', 'Send all' in await w.sheet_text() and await w.ev("!!document.querySelector('#layer [data-act=close]')"))
            await w.click('#layer [data-act=close]'); await w.wait(300)
            check('lightning: Cancel changes nothing', await bals(w) == (a0, b0) and await ntx(w) == n0)
            e, kv = await ln_all(w, addr)
            r = await pay(w, n0)
            check('lightning, no fee: paid 300, B at 0, A untouched', r[0] == 'ok' and r[1].get('amount') == 300 and await bals(w) == (400, 0), (r[0], await bals(w)))
            # input fees and a fee reserve: from A to an address at B
            await w.use(A); n1 = await ntx(w)
            e, kv = await ln_all(w, payee(B))
            check('lightning, fees: amount + fee reserve + mint fee fit the balance, with at most a few SAT spare',
                  not e and kv.get('Pay', 0) > 0 and kv.get('Total, at most', 10**9) <= 400 and kv['Total, at most'] >= 390 and kv['Pay'] + kv['Fee reserve'] + kv.get('Mint fee, at most', 0) == kv['Total, at most'], (e, kv))
            r = await pay(w, n1)
            t = r[1] if r[0] == 'ok' else {}
            check('lightning, fees: paid exactly the amount shown, never more than the balance; A holds 400 - amount - fee; B untouched',
                  r[0] == 'ok' and t.get('amount') == kv.get('Pay') and t['amount'] + t['fee'] <= 400 and await bals(w) == (400 - t['amount'] - t['fee'], 0), (r[0], t.get('amount'), t.get('fee'), await bals(w)))
            # dust: what is left after the fees is below the address's minimum
            await w.use(B); await w.receive_ln(40); await w.use(B)
            e, kv = await ln_all(w, payee(B, mn=50))
            check('lightning: below the address\'s minimum (40 < 50): refused with a sentence, nothing sent', 'less than the smallest payment allowed here (50 SAT)' in e and await w.bal(B) == 40, (e, await w.bal(B)))
            # fees as large as the balance: 3 SAT at A (fee reserve 2 + mint fees)
            await w.ev(f"Nutcade.S.proofs[{J(A)}]=[]"); await w.use(A); await w.receive_ln(3); await w.use(A)
            e, kv = await ln_all(w, payee(B))
            check('lightning: fees as large as the balance (3 SAT at the fee mint): refused, nothing sent', 'are as much as this mint\'s balance of 3 SAT' in e and await bals(w) == (3, 40), (e, await bals(w)))
            check('lightning: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= Lightning: the fee quote changes between quotes; the balance changes before paying =======================
        async def ln_quotes():
            w = await two_mints(b, 500, 200, A)
            calls = []
            async def bump(route):   # (the first quote's fee reserve is 20 higher, the next ones are the mint's own)
                r = await route.fetch(); d = await r.json(); calls.append(d.get('fee_reserve'))
                if len(calls) == 1: d['fee_reserve'] = int(d['fee_reserve']) + 20
                await route.fulfill(response=r, body=J(d))
            await w.pg.route('http://127.0.0.1:3338/v1/melt/quote/bolt11', bump)
            n0 = await ntx(w)
            e, kv = await ln_all(w, payee(B))
            await w.pg.unroute('http://127.0.0.1:3338/v1/melt/quote/bolt11')
            check('lightning, a fee that changes between quotes: asked again, and the quote shown fits (amount + fees <= 500)', not e and len(calls) >= 2 and kv.get('Total, at most', 10**9) <= 500 and kv.get('Pay', 0) >= 480, (e, calls, kv))
            r = await pay(w, n0); t = r[1] if r[0] == 'ok' else {}
            check('lightning, a fee that changed: paid the amount shown; A holds 500 - amount - fee; B untouched', r[0] == 'ok' and t.get('amount') == kv.get('Pay') and await bals(w) == (500 - t['amount'] - t['fee'], 200), (r[0], await bals(w)))
            # the balance drops between the confirm screen and Pay: the payment stops before anything is sent
            await w.use(B); n1 = await ntx(w)
            e, kv = await ln_all(w, payee(A))
            await w.ev(f"Nutcade.r8.sendEcash(7, 'meanwhile', null, {J(B)})"); await w.wait(500); n1 = await ntx(w)
            r = await pay(w, n1)
            check('lightning: the balance dropped after the confirm screen: refused, nothing paid', r[0] == 'err' and await w.bal(B) == 193 and await w.ev("Nutcade.S.pending.length") == 0 and await ntx(w) == n1, (r, await w.bal(B)))
            check('lightning quotes: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= Lightning: a payment that fails leaves every coin =======================
        async def ln_fail():
            w = await wallet(b); await w.create()
            await w.add_mint(B); await w.receive_ln(150)
            await w.add_mint(F); await w.receive_ln(300); await w.use(F); await w.home()
            n0 = await ntx(w)
            e, kv = await ln_all(w, payee(B))
            r = await pay(w, n0)
            await w.until("Nutcade.S.pending.length===0", 20000); await w.wait(500)
            check('lightning, a failed payment: the mint refused it, every coin is back (300 at the failing mint), B untouched',
                  r[0] in ('err', 'failed') and await w.bal(F) == 300 and await w.bal(B) == 150 and not await w.ev("Nutcade.S.pending.length"), (r[0], str(r[1])[:160], await w.bal(F), await w.bal(B)))
            check('lightning, a failed payment: its line says failed', await w.ev("Nutcade.S.txs.some(t=>t.type==='out'&&t.method==='ln'&&t.status==='failed')"))
            check('lightning fail: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= on-chain (the mint's on-chain answers played by the test) =======================
        async def onchain():
            OPTS = [{'fee_index': 0, 'fee_reserve': 300, 'estimated_blocks': 1}, {'fee_index': 1, 'fee_reserve': 120, 'estimated_blocks': 6}]
            st = {'n': 0, 'melt': 'fail', 'quotes': {}, 'bump': 0}
            async def info(route):
                r = await route.fetch(); d = await r.json()
                n5 = d.setdefault('nuts', {}).setdefault('5', {'methods': [], 'disabled': False})
                n5.setdefault('methods', []).append({'method': 'onchain', 'unit': 'sat', 'min_amount': 1000, 'max_amount': 1000000})
                await route.fulfill(response=r, body=J(d))
            async def quote(route):
                rq = route.request
                if rq.method == 'POST':
                    body = json.loads(rq.post_data or '{}'); st['n'] += 1; qid = f"oq{st['n']}x{int(time.time() * 1000)}"
                    extra = st['bump'] if st['n'] == 1 else 0
                    q = {'quote': qid, 'request': body.get('request'), 'amount': int(body.get('amount')), 'unit': 'sat', 'state': 'UNPAID', 'expiry': int(time.time()) + 3600,
                         'fee_options': [dict(o, fee_reserve=o['fee_reserve'] + extra) for o in OPTS], 'selected_fee_index': None, 'outpoint': None}
                    st['quotes'][qid] = q
                else:
                    q = st['quotes'].get(rq.url.rsplit('/', 1)[-1], {'quote': 'x', 'state': 'UNPAID'})
                await route.fulfill(status=200, body=J(q), headers={'content-type': 'application/json', 'access-control-allow-origin': '*'})
            async def melt(route):
                await route.fulfill(status=400, body=J({'detail': 'on-chain payment failed', 'code': 11000}), headers={'content-type': 'application/json', 'access-control-allow-origin': '*'})
            w = await wallet(b)
            await w.pg.context.route('http://127.0.0.1:3339/v1/info', info)
            await w.pg.context.route('http://127.0.0.1:3339/v1/melt/quote/onchain**', quote)
            await w.pg.context.route('http://127.0.0.1:3339/v1/melt/onchain', melt)
            await w.create(); await w.add_mint(A); await w.receive_ln(250); await w.add_mint(B); await w.receive_ln(5000); await w.use(B); await w.home()
            req = await w.ev("(Nutcade.S.txs.find(t=>t.request&&/^ln/.test(t.request))||{}).request||''")
            hrp = 'bcrt' if req.startswith('lnbcrt') else 'tb' if req.startswith('lntb') else 'bc'
            addr = bech32_addr(hrp)
            async def chain_all(a=addr):
                await open_send(w, 'onchain'); await w.fill('#destIn', a); await w.click('[data-act=allOnchain]')
                await w.until(WAIT_SHEET.format(sel='#payBtn'), 20000)
                return (await w.err()).strip(), await w.ev(KV)
            e, kv = await chain_all()
            check('on-chain: the fastest speed: amount + network fee = the balance (no mint fee at B)', not e and kv.get('Pay') == 4700 and kv.get('Network fee') == 300 and kv.get('Total, at most') == 5000, (e, kv))
            await w.ev("const r=document.querySelectorAll('#layer input[name=fee]')[1]; r.checked=true; r.dispatchEvent(new Event('change',{bubbles:true}))"); await w.wait(200)
            kv2 = await w.ev(KV); btn = await w.ev("document.querySelector('#payBtn').innerText")
            check('on-chain: each fee speed has its own amount (the slower one sends more), and the Pay button follows', kv2.get('Pay') == 4880 and kv2.get('Network fee') == 120 and kv2.get('Total, at most') == 5000 and '4,880' in btn, (kv2, btn))
            await w.click('#layer [data-act=close]'); await w.wait(300)
            check('on-chain: Cancel changes nothing', await bals(w) == (250, 5000))
            # the network fee changes between the first quote and the next: asked again, and it still fits
            st['n'] = 0; st['bump'] = 50
            e, kv = await chain_all()
            check('on-chain: a fee that changes between quotes is quoted again and what is shown fits the balance', not e and kv.get('Total, at most') == 5000 and kv.get('Pay') == 4700, (e, kv, st['n']))
            st['bump'] = 0
            # the payment fails at the mint: every coin comes back
            n0 = await ntx(w)
            r = await pay(w, n0)
            await w.until("Nutcade.S.pending.length===0", 20000); await w.wait(500)
            check('on-chain, a failed payment: nothing lost (B back at 5000, A untouched)', r[0] in ('err', 'failed') and await bals(w) == (250, 5000) and not await w.ev("Nutcade.S.pending.length"), (r[0], str(r[1])[:160], await bals(w)))
            # dust: below the mint's minimum on-chain amount (1,000)
            await w.use(B); await w.ev(f"Nutcade.S.proofs[{J(B)}]=[]"); await w.receive_ln(900); await w.use(B)
            e, kv = await chain_all()
            check('on-chain: what is left after the fee is below the mint\'s minimum: refused with a sentence, nothing sent', ('less than the smallest payment allowed here' in e or 'are as much as' in e) and await bals(w) == (250, 900), (e, await bals(w)))
            e, kv = await chain_all('bc1qnotanaddress')
            check('on-chain: a wrong address is refused before anything is asked', 'address' in e.lower() and await bals(w) == (250, 900), e)
            check('on-chain: no script errors', not [x for x in w.errs if '400' not in x], w.errs[:4])
            await w.pg.context.close()

        # ======================= five languages: the new screens are translated =======================
        async def langs():
            for lang in ('es', 'pt', 'de', 'fr'):
                w = await wallet(b, lang=lang); await w.create(); await w.add_mint(A); await w.receive_ln(20); await w.add_mint(B); await w.receive_ln(100); await w.use(B)
                await w.ev("window.__i18nMiss=new Set()")
                e, kv = await ecash_all(w); await w.close()
                await w.use(A); e2, kv2 = await ln_all(w, payee(B, mn=50)); await w.close()
                await w.ev(f"Nutcade.S.proofs[{J(A)}]=Nutcade.S.proofs[{J(A)}].slice(0,1)"); await w.use(A); e3, _ = await ecash_all(w)
                miss = [x for x in await w.ev("[...window.__i18nMiss]") if not re.search(r'cashu|lnurl\.test|Mint [AB]', x)]
                check(f'{lang}: the Send all screens and messages are translated', not miss and e2, (miss, e2[:80]))
                await w.pg.context.close()

        await section('ecash_zero', ecash_zero)
        await section('ecash_fee', ecash_fee)
        await section('ecash_changed', ecash_changed)
        await section('limit', limit)
        await section('lightning', lightning)
        await section('ln_quotes', ln_quotes)
        await section('ln_fail', ln_fail)
        await section('onchain', onchain)
        await section('langs', langs)
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
