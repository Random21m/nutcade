import os, sys, asyncio, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright
import glob
FILES = len(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'game_*.js')))   # cabinets that live in their own file
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'arcade'); await w.create()
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
        GAMES = await w.ev("Arcade.games.map(g => g.id)")   # every cabinet the arcade has, whatever their number
        check('arcade lists every cabinet', await w.ev("document.querySelectorAll('[data-game]').length") == len(GAMES) > FILES, GAMES)
        check('every src/game_*.js file registered exactly one cabinet through window.NutCabinets', await w.ev("(window.NutCabinets || []).length") == FILES, FILES)
        check('the cabinet ids are unique', len(set(GAMES)) == len(GAMES), GAMES)
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
        # GRAND TOUR means every cabinet in the arcade, counted from the list; an earned trophy is never taken back
        r = await w.ev("""(() => { const ids = Arcade.games.map(g => g.id), key = 'nutcade:plays', tkey = 'nutcade:trophies'; const t0 = Trophies.DEFS.find(d => d.id === 'tour');
          const reset = (by, got) => { localStorage.setItem(key, JSON.stringify({ n: 0, by })); localStorage.setItem(tkey, JSON.stringify(got || {})); Trophies.reload(); };
          const out = { how: t0.how, n: ids.length };
          reset({}); ids.slice(0, ids.length - 1).forEach(id => Trophies.played(id)); out.almost = !!Trophies.got().tour;
          Trophies.played(ids[ids.length - 1]); out.all = !!Trophies.got().tour;
          reset({}); ids.slice(0, 8).forEach(id => Trophies.played(id)); out.eight = !!Trophies.got().tour;
          reset({}, { tour: 12345 }); Trophies.played(ids[0]); out.kept = Trophies.got().tour === 12345;
          reset({}); return out; })()""")
        check('GRAND TOUR is earned by playing every cabinet, and not before', r['all'] and not r['almost'] and not r['eight'], r)
        check('GRAND TOUR says the number from the cabinet list', r['how'] == f"Play all {r['n']} cabinets.", r)
        check('a GRAND TOUR earned before the new cabinets arrived is kept', r['kept'], r)
        bad = {}; parts_bad = {}
        for lang in ('es', 'pt', 'de', 'fr'):
            await w.ev("document.querySelector('[data-act=tab][data-tab=settings]').click()"); await w.wait(150)
            await w.ev(f"const s=document.querySelector('#p_lang'); s.value='{lang}'; s.dispatchEvent(new Event('change',{{bubbles:true}}))"); await w.wait(250)
            t = await w.ev("Nutcade.tr(Trophies.DEFS.find(d => d.id === 'tour').how)")
            if t == r['how'] or str(r['n']) not in t: bad[lang] = t
            for src, want in (('(part 1 of 2)', {'es': '(parte 1 de 2)', 'pt': '(parte 1 de 2)', 'de': '(Teil 1 von 2)', 'fr': '(partie 1 sur 2)'}), ('ZZZ (part 2 of 3)', {'es': 'ZZZ (parte 2 de 3)', 'pt': 'ZZZ (parte 2 de 3)', 'de': 'ZZZ (Teil 2 von 3)', 'fr': 'ZZZ (partie 2 sur 3)'})):
                got = await w.ev(f"Nutcade.tr({src!r})")
                if got != want[lang]: parts_bad[lang + ' ' + src] = got
        await w.ev("const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))")
        check('a payment part with no note, "(part 1 of 2)", is translated in Spanish, Portuguese, German and French (history display text)', not parts_bad, parts_bad)
        check('GRAND TOUR text is translated, with the number, in Spanish, Portuguese, German and French', not bad, bad)
        check('no script errors in the arcade', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
