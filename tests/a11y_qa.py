"""Screen reader pass (1.47.0, step a: Home and Receive). Uses the local mint 3339 (Mint B).

- A sheet that opens, and a sheet whose content is replaced (Create invoice shows the invoice), takes the focus. On a touch
  screen that is the sheet itself, never a text field (no keyboard pops up), so VoiceOver and TalkBack land in it instead
  of staying on the page behind it. With a mouse or keyboard it is the first field, as before.
- The page has one main area (role=main) holding the wallet's content, so "jump to main" works; the header and the tab
  bar stay outside it.
- Every visible control on Home and on Receive (the form and the invoice) has a name a screen reader can read.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet

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
