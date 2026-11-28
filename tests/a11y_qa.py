"""Screen reader pass (1.47.0 step a: Home and Receive; 1.48.0 step b: Send, Pay confirm, the over-limit PIN screen).
Uses the local mint 3339 (Mint B).

- A sheet that opens, and a sheet whose content is replaced (Create invoice shows the invoice), takes the focus. On a touch
  screen that is the sheet itself, never a text field (no keyboard pops up), so VoiceOver and TalkBack land in it instead
  of staying on the page behind it. With a mouse or keyboard it is the first field, as before.
- The page has one main area (role=main) holding the wallet's content, so "jump to main" works; the header and the tab
  bar stay outside it.
- Every visible control on Home and on Receive (the form and the invoice) has a name a screen reader can read.
Step b (1.48):
- A sheet's error box (#sheetErr, used by most sheets) is announced: it is an alert region, so "That isn't a complete
  Lightning invoice" is read out instead of appearing silently.
- Send (ecash and Lightning) and the Pay confirm screen: every visible control has a name; the confirm screen has the focus.
- The over-limit PIN screen (it sits outside the sheet layer): it takes the focus when it opens, Tab stays inside it (not
  in the sheet under it), Escape closes it (not the sheet under it, which stays open), and the focus goes back there.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
import urllib.request
from r8_qa import wallet, set_pin, set_limits

FOCUS = "(a => ({tag: a.tagName, inSheet: !!a.closest('#layer .sheet'), isSheet: a.matches('#layer .sheet'), field: /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName), id: a.id}))(document.activeElement)"
UNNAMED = r"""(() => {
  const name = el => (el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') && (document.getElementById(el.getAttribute('aria-labelledby'))||{}).innerText) || (el.labels && el.labels[0] && el.labels[0].innerText) || el.innerText || el.value || el.getAttribute('title') || el.getAttribute('alt') || '').trim();
  return [...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,[role=button],[tabindex]:not([tabindex="-1"])')]
    .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && !el.closest('[aria-hidden=true]'))
    .filter(el => { const n = name(el); return !n || /^[^\p{L}\p{N}]{0,3}$/u.test(n); }).map(el => el.tagName + ' ' + (el.dataset.act || el.id || el.className));
})()"""


async def open_receive(w):
    await w.ev("Nutcade.closeSheet()"); await w.home()
    await w.pg.locator('[data-act=receive]').click(); await w.wait(300)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"):
        await w.pg.locator('[data-act=recvMethod][data-m=ln]').click(); await w.wait(200)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # ---- a phone (touch screen)
        w = await wallet(b); await w.create(); await w.add_mint(B); await w.receive_ln(500)
        coarse = await w.ev("matchMedia('(pointer:coarse)').matches")
        check('phone: the test runs as a touch screen (pointer: coarse)', coarse)
        await w.home(); await w.wait(200)
        check('Home: every visible control has a name', not await w.ev(UNNAMED), await w.ev(UNNAMED))
        main = await w.ev("(()=>{const m=[...document.querySelectorAll('main,[role=main]')]; return {n:m.length, wallet: m[0] ? !!m[0].querySelector('[data-act=receive]') : false, header: m[0] ? !!m[0].querySelector('header') : null, nav: m[0] ? !!m[0].querySelector('nav,.tabbar') : null}})()")
        check('Home: one main area, holding the wallet, with the header and the tab bar outside it', main['n'] == 1 and main['wallet'] and not main['header'] and not main['nav'], main)
        await open_receive(w)
        f = await w.ev(FOCUS)
        check('phone, Receive opens: the focus is in the sheet, not on a text field (no keyboard), not left on the page behind', f['inSheet'] and not f['field'], f)
        check('Receive: every visible control has a name', not await w.ev(UNNAMED), await w.ev(UNNAMED))
        await w.fill('#amtIn', '100')
        await w.pg.locator('[data-act=doLnInvoice]').click()
        await w.until("!!document.querySelector('#layer [data-act=copyInv], #layer .qr, #layer [data-qr]') || /lnbc/i.test((document.querySelector('#layer .sheet-body')||{}).innerText||'')", 15000); await w.wait(400)
        f = await w.ev(FOCUS)
        check('phone, Create invoice: when the invoice replaces the form, the focus is in the sheet (not lost to the page)', f['inSheet'] and not f['field'], f)
        check('Receive, the invoice: every visible control has a name', not await w.ev(UNNAMED), await w.ev(UNNAMED))
        check('phone: no script errors', not w.errs, w.errs[:4])
        await w.pg.context.close()

        # ---- step b: Send, an error, Pay confirm, the over-limit screen (on a phone, as most screen reader users)
        def inv(n):
            q = urllib.request.Request(B + '/v1/mint/quote/bolt11', data=json.dumps({'amount': n, 'unit': 'sat'}).encode(), headers={'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(q).read())['request']
        w = await wallet(b); await w.create(); await w.add_mint(B); await w.receive_ln(500)
        await w.ev("Nutcade.closeSheet()"); await w.home(); await w.pg.locator('[data-act=send]').click(); await w.wait(300)
        check('Send (ecash): every visible control has a name', not await w.ev(UNNAMED), await w.ev(UNNAMED))
        await w.pg.locator('[data-act=sendMethod][data-m=ln]').click(); await w.wait(200)
        check('Send (Lightning): every visible control has a name', not await w.ev(UNNAMED), await w.ev(UNNAMED))
        await w.fill('#destIn', 'lnbc1notaninvoice'); await w.pg.locator('[data-act=doMeltQuote]').click()
        await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 10000)
        er = await w.ev("(e=>({text:e.innerText.trim().slice(0,60), alert: e.getAttribute('role')==='alert' || !!e.closest('[role=alert],[aria-live=assertive]')}))(document.querySelector('#sheetErr'))")
        check('Send: an error is announced (the error box is an alert region), not shown silently', er['text'] and er['alert'], er)
        await w.fill('#destIn', inv(100)); await w.pg.locator('[data-act=doMeltQuote]').click()
        await w.until("!!document.querySelector('#payBtn')", 15000); await w.wait(300)
        f = await w.ev(FOCUS)
        check('Pay confirm: the screen has the focus, and every visible control has a name', f['inSheet'] and not await w.ev(UNNAMED), (f, await w.ev(UNNAMED)))
        # the over-limit screen
        await w.ev("Nutcade.closeSheet()"); await set_pin(w); await set_limits(w, '50', '1000')
        await w.home(); await w.pg.locator('[data-act=send]').click(); await w.wait(300)
        await w.pg.locator('[data-act=sendMethod][data-m=ln]').click(); await w.wait(200)
        await w.fill('#destIn', inv(200)); await w.pg.locator('[data-act=doMeltQuote]').click()
        await w.until("!!document.querySelector('#payBtn')", 15000); await w.wait(300)
        await w.pg.locator('#payBtn').click()
        up = await w.until("!!document.querySelector('#limitLayer .sheet')", 15000); await w.wait(400)
        inlim = "!!document.activeElement.closest('#limitLayer')"
        check('over-limit screen: it opens (a payment over the 50 SAT limit) and takes the focus', up and await w.ev(inlim), await w.ev(FOCUS))
        stays = []
        for _ in range(8):
            await w.pg.keyboard.press('Tab'); stays.append(await w.ev(inlim))
        check('over-limit screen: Tab stays inside it (never in the sheet under it)', all(stays), stays)
        await w.pg.keyboard.press('Escape'); await w.wait(300)
        st = await w.ev("({limit: !!document.querySelector('#limitLayer'), sheet: !!document.querySelector('#layer .sheet'), focusInSheet: !!document.activeElement.closest('#layer .sheet')})")
        check('over-limit screen: Escape closes it, the Pay screen under it stays open, and the focus goes back there', not st['limit'] and st['sheet'] and st['focusInSheet'], st)
        check('step b: no script errors', not w.errs, w.errs[:4])
        await w.pg.context.close()

        # ---- a computer (mouse and keyboard): unchanged, the first field takes the focus
        d = await wallet(b, vw=1280, vh=800, mobile=False); await d.create(); await d.add_mint(B)
        check('computer: the test runs with a fine pointer', not await d.ev("matchMedia('(pointer:coarse)').matches"))
        await open_receive(d)
        f = await d.ev(FOCUS)
        check('computer, Receive opens: the first field (the amount) has the focus, as before', f['inSheet'] and f['id'] == 'amtIn', f)
        check('computer: no script errors', not d.errs, d.errs[:4])
        await d.pg.context.close()

        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
