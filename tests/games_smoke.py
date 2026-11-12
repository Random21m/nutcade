import os, sys, asyncio, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright
GAMES = ['swarm', 'maze', 'brick', 'rocks', 'hop', 'shield', 'nibble', 'flipper']
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'arcade'); await w.create()
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
        check('arcade lists 8 cabinets', await w.ev("document.querySelectorAll('[data-game]').length") == 8)
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
        # touch controls: a joystick by default, with a switch back to the D-pad
        await w.ev("document.querySelector('[data-game=swarm]').click()"); await w.wait(300)
        check('touch: games show a joystick', await w.ev("!!document.querySelector('.game-view .stick')"))
        box = await w.pg.locator('.game-view .stick').bounding_box()
        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        await w.pg.mouse.move(cx, cy); await w.pg.mouse.down(); await w.pg.mouse.move(cx - 50, cy, steps=4); await w.wait(80)
        check('touch: pushing the stick left holds left', await w.ev("Arcade.held()") == ['left'], await w.ev("Arcade.held()"))
        await w.pg.mouse.move(cx - 40, cy - 40, steps=3); await w.wait(80)
        check('touch: a diagonal holds two directions in Star Swarm', sorted(await w.ev("Arcade.held()")) == ['left', 'up'], await w.ev("Arcade.held()"))
        await w.pg.mouse.up(); await w.wait(80)
        check('touch: letting go releases everything', await w.ev("Arcade.held()") == [])
        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        await w.ev("document.querySelector('[data-game=nibble]').click()"); await w.wait(300)
        box = await w.pg.locator('.game-view .stick').bounding_box()
        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        await w.pg.mouse.move(cx, cy); await w.pg.mouse.down(); await w.pg.mouse.move(cx - 30, cy - 45, steps=4); await w.wait(80)
        check('touch: grid games like Nibble take one direction at a time', await w.ev("Arcade.held()") == ['up'], await w.ev("Arcade.held()"))
        await w.pg.mouse.up()
        await w.ev("document.querySelector('[data-g=pad]').click()"); await w.wait(100)
        check('touch: Use D-pad switches to the D-pad', await w.ev("!!document.querySelector('.game-view .dpad') && !document.querySelector('.game-view .stick')"))
        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        await w.ev("document.querySelector('[data-game=swarm]').click()"); await w.wait(300)
        check('touch: the choice is remembered', await w.ev("!!document.querySelector('.game-view .dpad')"))
        await w.ev("document.querySelector('[data-g=pad]').click(); document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        check('no script errors in the arcade', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
