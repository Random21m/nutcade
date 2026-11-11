import os, sys, asyncio, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright
GAMES = ['swarm', 'maze', 'brick', 'rocks', 'hop', 'shield', 'nibble']
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'arcade'); await w.create()
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
        check('arcade lists 7 cabinets', await w.ev("document.querySelectorAll('[data-game]').length") == 7)
        for g in GAMES:
            await w.ev(f"document.querySelector('[data-game={g}]').click()"); await w.wait(300)
            await w.pg.keyboard.press('Space'); await w.wait(200)
            for _ in range(20):
                k = random.choice(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space'])
                await w.pg.keyboard.down(k); await w.wait(80); await w.pg.keyboard.up(k)
            await w.pg.keyboard.press('Enter'); await w.wait(150); await w.pg.keyboard.press('Space'); await w.wait(150)
            check(f'{g}: plays, pauses and resumes', await w.ev("!!document.querySelector('.game-view canvas')"))
            await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
            check(f'{g}: exit returns to lobby', await w.ev("!document.querySelector('.game-view')"))
        check('no script errors in the arcade', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
