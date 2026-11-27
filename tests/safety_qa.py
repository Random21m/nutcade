"""Safety fixes (1.44.0). Uses the local mints 3338 (Mint A), 3339 (Mint B), 3345 (MULTI: sat, usd, eur) and mock_nostr.py.

1. Removing a mint while money is on its way there is refused with a sentence: a Lightning deposit being collected, a
   payment in flight (its coins sit in the payment record, so the balance reads 0), an open step. A deposit nobody has
   paid yet does not block removal, but if it is paid later the mint comes back with the sats instead of them being
   hidden. The confirm screen checks again when Remove is tapped.
3. Change PIN, Remove PIN and Face ID setup wait out the wrong-PIN pause like the lock screen does.
4. Receive: the "trust this mint" step is for that token's mint only; a token from another unknown mint pasted in its
   place gets its own notice, not a silent claim.
5. A USD deposit recovered after its answer was lost comes in on its USD line (its toast's unit, arrMoneyU as on the line
   beside it, is checked by reading: the recovery path these local mints take shows the arrival screen, not that toast).
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, A, B
from r8_qa import wallet, set_pin, pad, PIN
from units_qa import add_account, MULTI

J = json.dumps
USD = MULTI + '|usd'


async def section(name, fn):
    only = [x for x in os.environ.get('SF_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def held_route(w, pattern):
    """hold requests to `pattern` until the returned event is set"""
    go = asyncio.Event()
    async def h(route):
        await go.wait()
        try: await route.continue_()
        except Exception: pass
    await w.pg.route(pattern, h)
    return go


async def invoice_at(w, url, amount, unpaid=False):
    """A Lightning deposit at `url`. Default: the fake Lightning pays it and the app's mint step is held (being collected).
    unpaid: nobody has paid it as far as the app can tell (its status reads UNPAID, the mint's live updates are cut) until
    the returned event is set, when the real status is let through (an invoice paid later)."""
    if unpaid:
        go = asyncio.Event()
        async def status(route):
            if go.is_set():
                try: await route.continue_()
                except Exception: pass
                return
            try:
                r = await route.fetch(); d = await r.json(); d['state'] = 'UNPAID'
                await route.fulfill(response=r, body=json.dumps(d))
            except Exception:
                try: await route.abort()
                except Exception: pass
        await w.pg.route(url + '/v1/mint/quote/bolt11/**', status)
        await w.pg.route_web_socket(url.replace('http', 'ws') + '/**', lambda ws: None)   # (no live "paid" message from this mint)
    else:
        go = await held_route(w, url + '/v1/mint/bolt11')
    await w.ev(f"Nutcade.S.active={J(url)}; Nutcade.render()"); await w.home()
    await w.click('[data-act=receive]'); await w.wait(150)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
    await w.fill('#amtIn', str(amount)); await w.click('[data-act=doLnInvoice]')
    ok = await w.until(f"Nutcade.S.quotes.some(q=>q.mint==={J(url)}&&q.amount=={amount})", 15000)
    await w.ev("Nutcade.closeSheet()"); await w.wait(200)
    return go, ok


async def remove(w, url):
    """Mints tab → Remove → (if offered) the confirm screen. Returns (refusal toast or '', confirm screen text or None)."""
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(300)
    await w.ev("document.querySelector('#toast') && (document.querySelector('#toast').hidden = true)")
    await w.click(f'[data-act=removeMint][data-url="{url}"]'); await w.wait(300)
    conf = await w.ev("document.querySelector('#layer [data-act=confirmRemove]') ? document.querySelector('#layer .sheet-body').innerText : null")
    return (await w.toast()), conf


has = lambda url: f"Nutcade.S.mints.some(m=>m.url==={J(url)})"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        async def remove_deposit():
            w = await wallet(b); await w.create(); await w.add_mint(A); await w.add_mint(B)
            go, ok = await invoice_at(w, A, 100)
            t, conf = await remove(w, A)
            check('remove, a deposit being collected (balance 0): refused with a sentence, no confirm screen', ok and 'on its way' in t and conf is None, (ok, t, conf))
            check('remove, a deposit being collected: the mint is still there', await w.ev(has(A)))
            go.set(); arrived = await w.until(f"(Nutcade.S.proofs[{J(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= 100", 30000)
            check('remove, a deposit being collected: when it comes in, the sats are in the balance', arrived and await w.ev(has(A)))
            check('remove, deposit: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def remove_payment():
            w = await wallet(b); await w.create(); await w.add_mint(B); await w.receive_ln(100); await w.add_mint(A)
            await w.ev(f"Nutcade.S.active={J(B)}; Nutcade.render()")
            go = await held_route(w, B + '/v1/melt/bolt11')
            inv = json.loads(__import__('urllib.request').request.urlopen(__import__('urllib.request').request.Request(B + '/v1/mint/quote/bolt11', data=J({'amount': 100, 'unit': 'sat'}).encode(), headers={'Content-Type': 'application/json'})).read())['request']
            task = asyncio.ensure_future(w.pay_ln(inv))
            inflight = await w.until(f"Nutcade.S.pending.some(p=>p.mint==={J(B)})", 15000)
            bal = await w.bal(B)
            t, conf = await remove(w, B)
            check('remove, a payment in flight (its coins in the payment record, balance 0): refused, no confirm screen', inflight and bal == 0 and 'on its way' in t and conf is None, (inflight, bal, t, conf))
            go.set(); await task
            await w.until(f"!Nutcade.S.pending.some(p=>p.mint==={J(B)})", 30000)
            t, conf = await remove(w, B)
            check('remove, once the payment has settled (paid, or refunded to the balance): no "on its way" refusal any more', 'on its way' not in t and (conf is not None or 'Send or move' in t), (t, conf))
            check('remove, payment: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def remove_unpaid():
            w = await wallet(b); await w.create(); await w.add_mint(A); await w.add_mint(B)
            go, ok = await invoice_at(w, A, 120, unpaid=True)
            t, conf = await remove(w, A)
            check('remove, a deposit nobody has paid yet: the confirm screen is offered and says it stays watched', ok and conf is not None and 'watched' in conf, (t, conf))
            # the deposit lands while the confirm screen is open: Remove is then refused
            go.set(); landed = await w.until(f"(Nutcade.S.proofs[{J(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= 120", 30000)
            await w.ev("document.querySelector('#toast') && (document.querySelector('#toast').hidden = true)")
            if await w.ev("!!document.querySelector('#layer [data-act=confirmRemove]')"): await w.click('#layer [data-act=confirmRemove]'); await w.wait(300)
            check('remove, the deposit landed while the confirm screen was open: Remove is refused, the mint and its 120 SAT stay', landed and await w.ev(has(A)) and await w.bal(A) >= 120 and 'Send or move' in await w.toast(), (landed, await w.bal(A), await w.toast()))
            check('remove, unpaid: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def remove_comeback():
            w = await wallet(b); await w.create(); await w.add_mint(A); await w.add_mint(B)
            go, ok = await invoice_at(w, A, 130, unpaid=True)
            t, conf = await remove(w, A)
            if conf is not None: await w.click('#layer [data-act=confirmRemove]'); await w.wait(400)
            gone = not await w.ev(has(A))
            go.set()
            back = await w.until(f"{has(A)} && (Nutcade.S.proofs[{J(A)}]||[]).reduce((t,p)=>t+p.amount,0) >= 130", 40000)
            check('remove, then the open deposit is paid: the mint comes back with the 130 SAT (never hidden)', ok and gone and back, (ok, gone, back, await w.ev("Nutcade.S.mints.map(m=>m.url)")))
            check('remove, comeback: the total balance counts them', await w.ev("Object.entries(Nutcade.S.proofs).filter(([u])=>Nutcade.S.mints.some(m=>m.url===u)).flatMap(([,ps])=>ps).reduce((t,p)=>t+p.amount,0)") >= 130)
            check('remove, comeback: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def pin_wait():
            w = await wallet(b); await w.create(); await w.add_mint(B); await set_pin(w)
            wrong = '0' * len(PIN) if PIN != '0' * len(PIN) else '1' * len(PIN)
            async def open_pad(act):
                await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
                await w.ev(f"(()=>{{let x=document.querySelector('[data-act={act}]'); if(!x){{x=document.createElement('button'); x.dataset.act={J(act)}; x.hidden=true; document.body.appendChild(x)}} x.click()}})()")
                return await w.until("!!document.querySelector('#layer [data-pinpad]')", 3000)
            await open_pad('pinChange')
            fails = "(JSON.parse(localStorage.getItem('nutcade:pinfails')||'{}').n||0)"
            for _ in range(5):   # (each wrong PIN is let count before the next: on a slow machine the key stretching takes a while)
                n0 = await w.ev(fails); await pad(w, wrong, '#layer [data-pinpad]'); await w.until(f"{fails} > {n0}", 15000); await w.wait(150)
            waiting = await w.ev("(JSON.parse(localStorage.getItem('nutcade:pinfails')||'{}').until||0) > Date.now()")
            await pad(w, PIN, '#layer [data-pinpad]'); await w.wait(800)
            msg = await w.ev("(document.querySelector('#layer #pinErr')||{}).innerText||''")
            check('Change PIN: after 5 wrong PINs the right one is refused until the pause is over (no NEW PIN screen)', waiting and 'Wait' in msg and 'NEW PIN' not in await w.sheet_text(), (waiting, msg))
            for act, name in (('pinRemove', 'Remove PIN'), ('bioStart', 'Face ID setup')):
                await open_pad(act); await pad(w, PIN, '#layer [data-pinpad]'); await w.wait(800)
                msg = await w.ev("(document.querySelector('#layer #pinErr')||{}).innerText||''")
                check(f'{name}: the right PIN is refused during the pause too', 'Wait' in msg and await w.ev("Nutcade.vault.on"), (msg, await w.ev("Nutcade.vault.on")))
            check('PIN wait: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def trust():
            giver = await wallet(b); await giver.create(); await giver.add_mint(A); await giver.receive_ln(50); await giver.add_mint(B); await giver.receive_ln(50)
            toks = {}
            for u in (A, B):
                await giver.ev(f"Nutcade.S.active={J(u)}; Nutcade.render()"); tx = await giver.send_ecash(10)
                toks[u] = await giver.ev("Nutcade.S.txs[0].token")
            w = await wallet(b); await w.create(); await add_account(w, MULTI)
            await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100)
            await w.fill('#tokIn', toks[A]); await w.click('[data-act=doReceiveToken]'); await w.wait(800)
            first = await w.ev("(document.querySelector('#tokPeek')||{}).innerText||''")
            check('trust: a token from an unknown mint (A) shows the trust notice first', 'haven\'t added' in first and not await w.ev(has(A)), first[:160])
            await w.fill('#tokIn', toks[B]); await w.wait(200)
            check('trust: pasting a token from another mint (B) in its place resets the button (no "Trust mint" left over)', await w.ev("!document.querySelector('[data-act=doReceiveToken][data-trust]') && !document.querySelector('[data-act=swapToken]')"), await w.ev("(document.querySelector('[data-act=doReceiveToken]')||{}).outerHTML||''"))
            await w.click('[data-act=doReceiveToken]'); await w.wait(1500)
            second = await w.ev("(document.querySelector('#tokPeek')||{}).innerText||''")
            check('trust: ...and the B token gets its own notice, nothing claimed, B not added', 'haven\'t added' in second and '127.0.0.1:3339' in second and not await w.ev(has(B)), (second[:160], await w.ev("Nutcade.S.mints.map(m=>m.url)")))
            check('trust: no script errors', not w.errs and not giver.errs, (w.errs + giver.errs)[:4])
            await w.pg.context.close(); await giver.pg.context.close()

        async def unit_toast():
            w = await wallet(b); await w.create(); ok = await add_account(w, MULTI, 'usd')
            async def lost(route):   # (the mint signs the deposit, its answer is lost on the way back)
                try: await route.fetch()
                except Exception: pass
                try: await route.abort()
                except Exception: pass
            await w.pg.route(MULTI + '/v1/mint/bolt11', lost)
            await w.ev(f"Nutcade.S.active={J(USD)}; Nutcade.render()"); await w.home()
            await w.click('[data-act=receive]'); await w.wait(150)
            if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
            await w.fill('#amtIn', '12.50'); await w.click('[data-act=doLnInvoice]')
            await w.until(f"Nutcade.S.quotes.some(q=>q.mint==={J(USD)})", 15000); await w.wait(3000)
            await w.pg.unroute(MULTI + '/v1/mint/bolt11'); await w.ev("Nutcade.closeSheet()")
            got = await w.until(f"(Nutcade.S.proofs[{J(USD)}]||[]).reduce((t,p)=>t+p.amount,0) >= 1250", 60000); await w.wait(800)
            check('unit deposit: a USD deposit recovered after a lost answer comes in (1,250 cents, on a USD line)', ok and got and await w.ev(f"Nutcade.S.txs.some(t=>t.mint==={J(USD)}&&t.status==='done'&&t.amount===1250)"), (ok, got))
            check('unit deposit: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        for name, fn in (('remove_deposit', remove_deposit), ('remove_payment', remove_payment), ('remove_unpaid', remove_unpaid),
                         ('remove_comeback', remove_comeback), ('pin_wait', pin_wait), ('trust', trust), ('unit_toast', unit_toast)):
            await section(name, fn)
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
