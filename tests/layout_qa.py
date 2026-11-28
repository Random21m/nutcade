"""Layout at narrow widths (1.46.0), in every language at 320, 375 and 430 px. Uses the local mint 3339 (Mint B).

From the visual review of 1.45.0:
- Settings, QR code center: "NUTCADE ACORN" (BELLOTA NUTCADE, BOLOTA NUTCADE, NUTCADE-EICHEL, GLAND NUTCADE) was cut off
  in its button at 320 px in every language and at 375 px in es, pt and de. No button of such a group cuts its text now.
- Toggle rows (Send's "Lock it to one person", and every other one): the row's layout squeezed the checkbox to 13 x 22 px.
  Every visible toggle checkbox keeps its full size now (the whole row was, and stays, the tap target).
Each language is checked to be the page's language, and the QR code center group to be there, so nothing passes on an empty page.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet

WIDTHS = [320, 375, 430]
LANGS = ['en', 'es', 'pt', 'de', 'fr']
CUT = "[...document.querySelectorAll('.seg button')].filter(b=>b.getClientRects().length && b.scrollWidth > b.clientWidth + 1).map(b=>b.innerText.trim())"
SQUASHED = "[...document.querySelectorAll('.toggle input[type=checkbox]')].filter(i=>i.getClientRects().length).map(i=>{const r=i.getBoundingClientRect(); return [i.id||'?', Math.round(r.width), Math.round(r.height)]}).filter(([,w,h])=>w<21||h<21)"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        w = await wallet(b); await w.create(); await w.add_mint(B)
        for lang in LANGS:
            await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
            await w.ev(f"const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await w.wait(500)
            for vw in WIDTHS:
                await w.pg.set_viewport_size({'width': vw, 'height': 740}); await w.wait(250)
                await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(300)
                cut = await w.ev(CUT); sq = await w.ev(SQUASHED)
                here = await w.ev("[document.documentElement.lang, document.querySelectorAll('[data-act=qrLogo]').length]")
                check(f'{lang} {vw}px, Settings: the page is in {lang} and the QR code center buttons are there', here[0].startswith(lang) and here[1] == 2, here)
                check(f'{lang} {vw}px, Settings: no button text cut off (QR code center and the rest)', not cut, cut)
                check(f'{lang} {vw}px, Settings: every toggle checkbox at full size', not sq, sq)
                await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=send]'); await w.wait(300)
                sq = await w.ev(SQUASHED)
                check(f'{lang} {vw}px, Send: the lock checkbox at full size, not squeezed', await w.ev("!!document.querySelector('#giftOn')") and not sq, sq)
        await w.pg.set_viewport_size({'width': 320, 'height': 740}); await w.wait(250)
        await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=send]'); await w.wait(300)
        await w.pg.locator('#giftOn').evaluate("i => i.closest('label').querySelector('.tl').scrollIntoView()")
        await w.pg.locator('label[for=giftOn] .tl').click(); await w.wait(150)
        check('320px, Send: a tap on the lock row\'s words still ticks it (the whole row is the tap target)', await w.ev("document.querySelector('#giftOn').checked"))
        check('no script errors', not w.errs, w.errs[:4])
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
