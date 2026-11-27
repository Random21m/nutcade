"""Adding a mint while another add is still on its way (1.42.0). Uses the local mints 3338 (Mint A) and 3339 (Mint B).

1. The test helper add_mint() waits for the add itself to finish, never for "any toast": a toast left on screen from an
   earlier step (creating a wallet leaves one) made it move on while Mint A was still being added, and A's finish then
   closed the picker opened for Mint B (CI, Nov 27: Page.fill timed out waiting for #mintUrl).
2. In the app, an add that finishes late closes only the sheet it was started from: if you closed the picker and opened
   another sheet meanwhile, that sheet stays open (both Add buttons: by address, and a Popular mints card).
3. As before: a normal add closes the picker; an address that is not a mint leaves the picker open, saying why.
Mint A's replies are held back by the test (page.route) and let through at the chosen moment."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, A, B
from r8_qa import wallet

J = json.dumps
CARD = 'https://testnut.cashu.space'   # (a Popular mints card; its replies come from the local Mint A)


async def section(name, fn):
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def hold(w, pattern, target=None):
    """hold back every request to `pattern` until the returned event is set; with target, answer it from that mint instead"""
    go = asyncio.Event()
    async def h(route):
        await go.wait()
        if target:
            u = route.request.url.replace(CARD, target)
            r = await route.fetch(url=u); await route.fulfill(response=r)
        else: await route.continue_()
    await w.pg.route(pattern, h)
    return go


async def open_picker(w):
    await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(100); await w.ev("Nutcade.closeSheet()")
    await w.ev("document.querySelector('[data-act=pickMint]').click()")
    return await w.until("!!document.querySelector('#mintUrl')", 5000)


has = lambda url: f"Nutcade.S.mints.some(m=>m.url==={J(url)})"
SHEET = "((document.querySelector('#layer .sheet')||{}).getAttribute||(()=>null)).call(document.querySelector('#layer .sheet'),'aria-label')"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        async def helper():
            w = await wallet(b); await w.create()
            go = await hold(w, A + '/**')
            await w.ev("Nutcade.toast('A toast from an earlier step', 'gold')")   # (as creating the wallet leaves one; shown here, so a slow machine can't let it fade first)
            check('helper: a toast from an earlier step is on screen (the case that fooled the helper)', bool(await w.toast()), await w.toast())
            asyncio.get_running_loop().call_later(1.5, go.set)   # (Mint A answers 1.5 s late, as on a slow machine)
            await w.add_mint(A)
            check('helper: add_mint(A) returns only once Mint A is added', await w.ev(has(A)), await w.ev("Nutcade.S.mints.map(m=>m.url)"))
            await w.add_mint(B)
            check('helper: then add_mint(B) works: both mints are there, B is the active one',
                  await w.ev(has(A)) and await w.ev(has(B)) and await w.ev("Nutcade.S.active") == B, await w.ev("[Nutcade.S.mints.map(m=>m.url), Nutcade.S.active]"))
            check('helper: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def late(kind):
            w = await wallet(b); await w.create(); await w.add_mint(B)
            if kind == 'card':
                go = await hold(w, CARD + '/**', target=A); url = CARD
                await open_picker(w); await w.click(f'[data-act=addMint][data-url="{CARD}"]')
            else:
                go = await hold(w, A + '/**'); url = A
                await open_picker(w); await w.fill('#mintUrl', A); await w.click('[data-act=addMintUrl]')
            await w.wait(200)
            busy = await w.ev("!!document.querySelector('#layer [data-act^=addMint][disabled]')")
            await w.ev("Nutcade.closeSheet()"); await w.home()
            await w.click('[data-act=receive]'); await w.until("!!document.querySelector('#layer .sheet')", 3000)
            other = await w.ev(SHEET)
            go.set()
            added = await w.until(has(url), 15000); await w.wait(400)
            check(f'{kind}: the add was still on its way when the picker was closed', busy)
            check(f'{kind}: when it finishes, the mint is added and says so', added and 'added' in (await w.toast()), (added, await w.toast()))
            check(f'{kind}: ... and the sheet opened meanwhile ({other}) stays open', other and await w.ev(SHEET) == other, (other, await w.ev(SHEET)))
            check(f'{kind}: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def normal():
            w = await wallet(b); await w.create(); await w.add_mint(B)
            await open_picker(w); await w.fill('#mintUrl', A); await w.click('[data-act=addMintUrl]')
            ok = await w.until(f"{has(A)} && !document.querySelector('#layer .sheet')", 15000)
            check('normal: adding a mint closes the picker, as before', ok, await w.ev(SHEET))
            go = await hold(w, CARD + '/**', target=A); go.set()   # (before the picker opens: its probe of the card goes to the local mint too)
            await open_picker(w)
            await w.click(f'[data-act=addMint][data-url="{CARD}"]')
            ok = await w.until(f"{has(CARD)} && !document.querySelector('#layer .sheet')", 15000)
            check('normal: adding a Popular mints card closes the picker, as before', ok, await w.ev(SHEET))
            await open_picker(w); await w.fill('#mintUrl', 'notamint.invalid'); await w.click('[data-act=addMintUrl]')
            done = await w.until("!document.querySelector('#layer [data-act=addMintUrl][disabled]')", 20000); await w.wait(200)
            msg = await w.ev("((document.querySelector('#layer #sheetErr')||{}).innerText||'').trim() || ((t=>t&&t.style.getPropertyValue('--c').includes('red')?t.innerText:'')(document.querySelector('#toast:not([hidden])')))")
            check('normal: an address that is not a mint leaves the picker open, with a message', done and await w.ev("!!document.querySelector('#mintUrl')") and len(msg) > 0, msg[:160])
            check('normal: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        await section('helper', helper)
        await section('address', lambda: late('address'))
        await section('card', lambda: late('card'))
        async def enter_twice():   # (1.43) Enter pressed again in the address box while an add is on its way starts no second add
            w = await wallet(b); await w.create(); await w.add_mint(B)
            held, free = [], [False]   # (its requests are held and then refused in the order they came: without the fix the second add ends last)
            async def bad(route):
                if free[0]: await route.abort(); return
                held.append(route)
            await w.pg.route('https://notamint.invalid/**', bad)
            await open_picker(w); await w.fill('#mintUrl', 'notamint.invalid'); await w.pg.focus('#mintUrl')
            await w.pg.keyboard.press('Enter'); await w.wait(300); await w.pg.keyboard.press('Enter'); await w.wait(300)
            free[0] = True
            for r in list(held): await r.abort(); await w.wait(150)
            done = await w.until("!document.querySelector('#layer [data-act=addMintUrl][disabled]')", 20000); await w.wait(1500)
            btn = await w.ev("(b=>b?b.innerText.trim():null)(document.querySelector('#layer [data-act=addMintUrl]'))")
            check('enter twice, an address that is not a mint: afterwards the button says Add again, not ADDING (one add ran, not two)', done and btn and btn.upper() == 'ADD', btn)
            go = await hold(w, A + '/**')
            await w.fill('#mintUrl', A); await w.pg.focus('#mintUrl')
            await w.pg.keyboard.press('Enter'); await w.wait(200); await w.pg.keyboard.press('Enter'); await w.wait(200)
            go.set()
            ok = await w.until(f"{has(A)} && !document.querySelector('#layer .sheet')", 15000)
            check('enter twice, a real mint: it is added once and the picker closes', ok and await w.ev(f"Nutcade.S.mints.filter(m=>m.url==={J(A)}).length") == 1, await w.ev("Nutcade.S.mints.map(m=>m.url)"))
            check('enter twice: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        await section('normal', normal)
        await section('enter_twice', enter_twice)
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
