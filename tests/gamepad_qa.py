"""Game controllers (1.39.0, Gamepad API, standard mapping).

navigator.getGamepads is stubbed (add_init_script) and requestAnimationFrame is faked (the test calls the frames itself,
60 a second), so every step is exact and nothing depends on a real pad or display. Nothing else is touched: no network.

Covered: d-pad and left stick steer (and the stick inside the dead zone does nothing); A is 'a'; B and Start are 'b'
(pause); holding A gives one press, not one per frame; Start pauses and Start again resumes; Back exits; a pad
disconnecting mid-hold releases its key; a button already down as the game opens is not a press; two pads merge;
a non-standard pad is ignored; no pad, no API and a throwing getGamepads leave the games running; a game played with
the pad records the same replay frames as the same inputs on the keyboard, and the replay verifies to the same score; the
wallet screens (no game open) never poll the pad and ignore it."""
import os, sys, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright

STUB = """(() => {
  const P = window.__gp = { list: [], throws: false, calls: 0 };
  // a spec is { b: [pressed button numbers], x, y, map }; null is an empty slot
  const mk = (o, i) => o && ({ connected: o.connected !== false, mapping: o.map === undefined ? 'standard' : o.map, index: i, id: 'stub pad',
    buttons: Array.from({ length: 17 }, (_, j) => ({ pressed: (o.b || []).includes(j), touched: false, value: (o.b || []).includes(j) ? 1 : 0 })), axes: [o.x || 0, o.y || 0, 0, 0] });
  navigator.getGamepads = () => { P.calls++; if (P.throws) throw new Error('pad boom'); return P.list.map(mk); };
})()"""
FAKE = """(() => {
  const F = window.__F = { t: 1000, id: 0, q: new Map(), n: 0, hits: 0, cap: 0, S: null, seen: new WeakMap() };
  window.requestAnimationFrame = cb => { F.q.set(++F.id, cb); return F.id; };
  window.cancelAnimationFrame = id => { F.q.delete(id); };
  F.pump = n => { for (let i = 0; i < n; i++) { F.t += 1000 / 60; const cbs = [...F.q.values()]; F.q.clear(); cbs.forEach(cb => cb(F.t)); } };
  F.key = (code, down) => window.dispatchEvent(new KeyboardEvent(down ? 'keydown' : 'keyup', { code, bubbles: true, cancelable: true }));
  F.watch = id => { const g = Arcade.games.find(x => x.id === id); if (g.__w) return; g.__w = 1; const u = g.update;
    g.update = function (s, G) { F.n++; F.S = s; if (F.add && !F.seen.get(s)) G.addScore(F.add); if (G.hit('a')) F.hits++; const c = (F.seen.get(s) || 0) + 1; F.seen.set(s, c); if (F.cap && c === F.cap) G.over(); return u.apply(this, arguments); }; };
})()"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'pad'); await w.create()
        await w.pg.add_init_script(STUB)   # (for pages opened later; this one gets the stub by hand)
        await w.ev(STUB); await w.ev(FAKE)
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
        pump = lambda n: w.ev(f"__F.pump({n})")
        pad = lambda *specs: w.ev("__gp.list = " + __import__('json').dumps(list(specs)))
        held = lambda: w.ev("Arcade.held().sort()")
        px = lambda: w.ev("__F.S.p.x")
        async def open_game(gid='swarm', start=True):
            await pad()
            await w.ev(f"Arcade.open('{gid}'); __F.watch('{gid}'); __F.n = 0; __F.hits = 0; __F.cap = 0")
            await pump(3)
            if start:
                await pad({'b': [0]}); await pump(3); await pad(); await pump(3)
        async def leave():
            await pad(); await w.ev("document.querySelector('[data-g=exit]') && document.querySelector('[data-g=exit]').click()"); await w.wait(50)

        # --- the wallet screens: no game open, the pad is not even read, and nothing happens
        c0 = await w.ev("__gp.calls")
        await pad({'b': [0, 1, 8, 9, 12, 13, 14, 15], 'x': 1, 'y': 1}); await pump(30); await w.wait(100)
        check('wallet screens: the pad is not polled while no game is open', await w.ev("__gp.calls") == c0, await w.ev("__gp.calls") - c0)
        check('wallet screens: nothing held, no game opened, still on the Arcade tab', await held() == [] and await w.ev("!Arcade.playing()") and await w.ev("!!document.querySelector('[data-game]')"))
        await pad()
        await w.click('[data-act=tab][data-tab=wallet]'); await w.wait(200)
        await pad({'b': [0, 9]}); await pump(10)
        check('wallet screens: a pad press does not click anything on the wallet tab', await w.ev("!Arcade.playing()") and await held() == [])
        await pad(); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(300)

        # --- steering: d-pad
        await open_game()
        check('the pad A button started the game from the title', await w.ev("__F.n") > 0, await w.ev("__F.n"))
        x0 = await px()
        await pad({'b': [14]}); await pump(10)
        check('d-pad left holds left and moves the player left', await held() == ['left'] and await px() < x0 - 10, (await held(), x0, await px()))
        await pad({'b': [15]}); await pump(20)
        check('d-pad right holds right (left released) and moves the player right', await held() == ['right'] and await px() > x0 - 10, (await held(), await px()))
        await pad({'b': [12]}); await pump(2)
        check('d-pad up holds up', await held() == ['up'], await held())
        await pad({'b': [13]}); await pump(2)
        check('d-pad down holds down', await held() == ['down'], await held())
        await pad(); await pump(2)
        check('letting go releases everything', await held() == [])
        # --- the left stick and its dead zone
        x1 = await px()
        await pad({'x': 0.49, 'y': -0.49}); await pump(15)
        check('a stick inside the dead zone (0.49) does nothing', await held() == [] and await px() == x1, (await held(), x1, await px()))
        await pad({'x': -0.51}); await pump(10)
        check('stick left past the dead zone holds left and moves the player', await held() == ['left'] and await px() < x1 - 5, (await held(), x1, await px()))
        await pad({'x': 0.9, 'y': 0.7}); await pump(2)
        check('a stick diagonal holds two directions', await held() == ['down', 'right'], await held())
        await pad({'y': -1}); await pump(2)
        check('stick up holds up', await held() == ['up'], await held())
        await pad({'x': 'NaN-ish'}); await pump(2)   # (a bad axis value reads as 0)
        check('a garbage axis value reads as centered', await held() == [], await held())
        # --- A and B, edge detection
        await pad(); await pump(2); h0 = await w.ev("__F.hits")
        await pad({'b': [0]}); await pump(45)
        check('A held for 45 steps is ONE press of "a" (no repeat)', await w.ev("__F.hits") - h0 == 1, await w.ev("__F.hits") - h0)
        check('while A is held the game sees "a" held', await held() == ['a'], await held())
        await pad(); await pump(3)
        check('releasing A releases "a"', await held() == [])
        await pad({'b': [0]}); await pump(3); await pad(); await pump(3); await pad({'b': [0]}); await pump(3); await pad(); await pump(3)
        check('two separate A presses are two presses', await w.ev("__F.hits") - h0 == 3, await w.ev("__F.hits") - h0)
        # --- pause: Start, and Start again
        n0 = await w.ev("__F.n"); await pad({'b': [9]}); await pump(2); await pad(); await pump(20)
        n1 = await w.ev("__F.n")
        check('Start pauses: the game stops stepping', n1 - n0 <= 1, n1 - n0)
        await pad({'b': [9]}); await pump(2); await pad(); await pump(20)
        n2 = await w.ev("__F.n")
        check('Start again resumes: the game steps again', n2 - n1 >= 18, n2 - n1)
        await pad({'b': [1]}); await pump(2); await pad(); await pump(20); n3 = await w.ev("__F.n")
        check('B is the pause key too (like Enter)', n3 - n2 <= 3, n3 - n2)
        await pad({'b': [0]}); await pump(2); await pad(); await pump(10)
        check('A resumes from the pause (like the keyboard)', await w.ev("__F.n") - n3 >= 8, await w.ev("__F.n") - n3)
        # --- disconnect mid-hold
        await pad({'b': [14, 0]}); await pump(5)
        check('before the disconnect: left and a are held', await held() == ['a', 'left'], await held())
        await pad(None); await pump(2)
        check('a pad that disconnects (slot empty) releases what it held', await held() == [], await held())
        await pad({'b': [15]}); await pump(3)
        await pad({'b': [15], 'connected': False}); await pump(2)
        check('a pad whose connected flag turns false releases too', await held() == [], await held())
        # --- two pads merge
        await pad({'b': [14]}, {'b': [13]}); await pump(3)
        check('two pads are merged (left from one, down from the other)', await held() == ['down', 'left'], await held())
        await pad({'b': [14]}, None); await pump(3)
        check('one of two pads going away releases only its key', await held() == ['left'], await held())
        await pad({'b': [0], 'map': ''}); await pump(3)
        check('a pad without the standard mapping is ignored', await held() == [], await held())
        # --- Back exits
        await pad({'b': [8]}); await pump(3)
        check('Back (Select) exits the game like Escape', await w.ev("!Arcade.playing()"))
        await pad(); await pump(2)

        # --- a button held while the game opens is not a press
        await pad({'b': [0]})
        await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0"); await pump(10)
        check('A already down as the game opens does not start it', await w.ev("__F.n") == 0, await w.ev("__F.n"))
        await pad(); await pump(2); await pad({'b': [0]}); await pump(5)
        check('...the next press does', await w.ev("__F.n") > 0)
        await leave()

        # --- no pad, no API, a throwing getGamepads
        for name, setup in (('no pad connected', "__gp.list = []"), ('every slot empty', "__gp.list = [null, null, null, null]"),
                            ('getGamepads throwing', "__gp.throws = true"), ('no getGamepads at all', "navigator.getGamepads = undefined"),
                            ('getGamepads returning null', "navigator.getGamepads = () => null")):
            await w.ev("__gp.throws = false; __gp.list = []")
            await w.ev(setup)
            await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0"); await pump(3)
            await w.ev("__F.key('Space', true); __F.key('Space', false)"); await pump(3)
            await w.ev("__F.key('ArrowLeft', true)"); await pump(30)
            ok = await w.ev("__F.n") >= 25 and await held() == ['left']
            await w.ev("__F.key('ArrowLeft', false)")
            check(f'{name}: the game starts and plays with the keyboard', ok, (await w.ev("__F.n"), await held()))
            await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(50)
            await w.ev(STUB)   # put the stub back
        # a pad throwing in the middle of a game releases and the game goes on
        await open_game()
        await pad({'b': [14]}); await pump(5)
        n0 = await w.ev("__F.n"); await w.ev("__gp.throws = true"); await pump(20)
        check('getGamepads starting to throw mid-game releases the key and the game keeps running', await held() == [] and await w.ev("__F.n") - n0 >= 18, (await held(), await w.ev("__F.n") - n0))
        await w.ev("__gp.throws = false")
        await pad({'b': [15]}); await pump(3)
        check('...and the pad works again once it stops throwing', await held() == ['right'], await held())
        await leave()

        # --- Nut Poker (a cabinet with onKey): A deals, Start pauses
        await w.ev("Arcade.open('poker'); __F.watch('poker'); __F.n = 0"); await pump(3)
        await pad({'b': [0]}); await pump(3); await pad(); await pump(10)
        check('poker: the pad A button starts the cabinet and it keeps running', await w.ev("__F.n") >= 5 and await w.ev("Arcade.playing()"), await w.ev("__F.n"))
        n0 = await w.ev("__F.n"); await pad({'b': [9]}); await pump(2); await pad(); await pump(15)
        check('poker: Start pauses', await w.ev("__F.n") - n0 <= 1, await w.ev("__F.n") - n0)
        await leave()


        # --- fix round 1
        # F1: A and Back down in the same step: nothing of that step outlives the game (no stale 'a' starting the next cabinet / the Daily run)
        await open_game()
        await pad({'b': [0, 8]}); await pump(3); await pad(); await pump(3)
        check('F1: A + Back in one step closes the game', await w.ev("!Arcade.playing()"))
        await w.ev("Arcade.open('swarm', { daily: true }); __F.watch('swarm'); __F.n = 0"); await pump(15)
        check('F1: reopening (as a Daily Challenge) stays on the title: no run started, no update', await w.ev("__F.n") == 0 and await w.ev("Arcade.daily().run") is None, (await w.ev("__F.n"), await w.ev("Arcade.daily().run")))
        await leave()
        await w.ev("__F.key('Space', true); __F.key('Space', false)")   # a key press queued while no game is open must not survive an open either
        await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0"); await pump(15)
        check('F1: a press made before the game opened does not start it', await w.ev("__F.n") == 0, await w.ev("__F.n"))
        await leave()
        # F2: Back already down as the game opens is not a press
        await pad({'b': [8]})
        await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0"); await pump(10)
        check('F2: Back held while a game opens does not close it', await w.ev("Arcade.playing()"))
        await pad(); await pump(2); await pad({'b': [8]}); await pump(3)
        check('F2: ...a fresh Back press does', await w.ev("!Arcade.playing()"))
        await pad(); await pump(2)
        # F3: a pad release never lets go of a key the keyboard still holds
        await open_game()
        await w.ev("__F.key('ArrowLeft', true)"); await pump(3)
        await pad({'b': [14]}); await pump(3); await pad(); await pump(3)
        check('F3: keyboard left held + pad left tapped and released: still held', await held() == ['left'], await held())
        await w.ev("__F.key('ArrowLeft', false)"); await pump(2)
        check('F3: ...and the keyboard release lets go', await held() == [], await held())
        await pad({'b': [14]}); await pump(3); await w.ev("__F.key('ArrowLeft', true); __F.key('ArrowLeft', false)"); await pump(2)
        await pad(); await pump(2)
        check('F3: pad alone still releases (no key left behind)', await held() == [], await held())
        await leave()
        # F4: the screens after a game: a qualifying score gives the initials form (its input is focused)
        async def finish_run():
            await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0; __F.add = 100; __F.cap = 20"); await pump(3)
            await pad({'b': [0]}); await pump(3); await pad(); await pump(40); await w.wait(2200); await pump(2)
            await w.ev("__F.add = 0; __F.cap = 0")
        await finish_run()
        check('F4: the initials form is shown with its field focused', await w.ev("!!document.querySelector('#entry #ini') && document.activeElement.id === 'ini'"))
        await pad({'b': [14, 13]}); await pump(3); await pad(); await pump(2)
        check('F4: other pad input is ignored on the entry screen (still there, nothing held)', await w.ev("!!document.querySelector('#entry #ini')") and await held() == [])
        await pad({'b': [0]}); await pump(3); await pad(); await pump(2)
        check('F4: A submits the initials (the saved screen shows)', await w.ev("!!document.querySelector('#entry [data-g=card]') && !document.querySelector('#entry #ini')"))
        await pad({'b': [0]}); await pump(3); await pad(); await pump(2)
        check('F4: A on the saved screen takes its Continue (back to the title)', await w.ev("!document.querySelector('#entry .btn') && Arcade.playing()"))
        await pad({'b': [0]}); await pump(3); await pad(); await pump(3)
        check('F4: ...and the next A starts a new game from the title (no stale press)', await w.ev("__F.n") > 0)
        await leave()
        await finish_run()
        await pad({'b': [8]}); await pump(3); await pad(); await pump(2)
        check('F4: Back cancels the initials form and closes the game', await w.ev("!Arcade.playing()"))
        await finish_run()
        await pad({'b': [9]}); await pump(3); await pad(); await pump(2)
        check('F4: Start submits the initials too', await w.ev("!!document.querySelector('#entry [data-g=card]')"))
        await pad({'b': [8]}); await pump(3); await pad(); await pump(2)
        check('F4: Back closes the saved screen like Escape', await w.ev("!Arcade.playing()"))
        await pad(); await pump(2)

        # --- 1.41: a release from one source never lets go of a key another source still holds (one rule, anyHas)
        await open_game()
        await pad({'b': [14]}); await pump(3)
        check('1.41: pad left held', await held() == ['left'], await held())
        await w.ev("__F.key('ArrowLeft', true)"); await pump(2); await w.ev("__F.key('ArrowLeft', false)"); await pump(3)
        check('1.41: a keyboard keyup does not release a key the pad still holds', await held() == ['left'], await held())
        await pad(); await pump(2)
        check('1.41: ...and the pad letting go then releases it', await held() == [], await held())
        await w.ev("__F.key('ArrowLeft', true); __F.key('KeyA', true)"); await pump(2); await w.ev("__F.key('ArrowLeft', false)"); await pump(2)
        check('1.41: another keyboard code for the same key (A) still holds left after ArrowLeft is released', await held() == ['left'], await held())
        await w.ev("__F.key('KeyA', false)"); await pump(2)
        check('1.41: ...and the last code let go releases it', await held() == [], await held())
        await pad({'b': [0]}); await pump(3)
        bb = await w.ev("(() => { const r = document.querySelector('[data-k=a]').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        await w.pg.mouse.move(bb[0], bb[1]); await w.pg.mouse.down(); await pump(2); await w.pg.mouse.up(); await pump(3)
        check('1.41: a touch up does not release a key the pad still holds', await held() == ['a'], await held())
        await pad(); await pump(3)
        check('1.41: ...and the pad letting go then releases it', await held() == [], await held())
        await pad({'b': [14]}); await pump(3)
        await w.ev("window.__inp = document.createElement('input'); document.body.appendChild(__inp); __inp.focus()"); await pump(2)
        await pad({'b': [14, 13]}); await pump(2)
        check('1.41: while a text field has focus a NEW pad press is not made', await held() == ['left'], await held())
        await pad(); await pump(3)
        check('1.41: a pad button held when a text field got focus is released when let go', await held() == [], await held())
        await pad({'b': [15]}); await pump(3); await pad(); await pump(2); await w.ev("__inp.remove()"); await pump(2)
        check('1.41: ...and nothing is stuck after the field is gone', await held() == [], await held())
        await pad({'b': [14]}); await pump(1); await pad()
        await w.ev("window.__inp = document.createElement('input'); document.body.appendChild(__inp); __inp.focus()"); await pump(2)
        await pad({'b': [13]}); await pump(3); await w.ev("__inp.remove()"); await pump(2)
        check('1.41: a button pressed while typing and still held when the field goes away is pressed on the next poll', await held() == ['down'], await held())
        await pad(); await pump(2)
        await leave()
        # Space (a keyboard activation of the main button) and pad A in the same frame on a result screen: one activation
        await finish_run()
        await pad({'b': [0]}); await pump(3); await pad(); await pump(2)
        check('1.41: on the saved screen (Continue is there)', await w.ev("!!document.querySelector('#entry [data-g=card]') && !!document.querySelector('#entry [data-g=again]')"))
        await w.ev("__F.n = 0; document.querySelector('#entry [data-g=again]').focus()")
        await pad({'b': [0]}); await w.pg.keyboard.down('Space'); await pump(1); await w.pg.keyboard.up('Space'); await pump(3)   # (a real Space keydown and pad A in the same frame)
        check('1.41: real Space + pad A in the same frame on the result screen: ONE action (Continue; no game started from the title)', await w.ev("Arcade.playing()") and await w.ev("__F.n") == 0 and await w.ev("!document.querySelector('#entry [data-g=again]')"), (await w.ev("__F.n"), await held()))
        await pad(); await pump(3); await pad({'b': [0]}); await pump(3)
        check('1.41: ...and the next pad A (a frame later) starts the game as usual', await w.ev("__F.n") > 0, await w.ev("__F.n"))
        await leave(); await pad(); await pump(2)
        # Enter in the initials field and pad A in the same frame: the score is saved once and the SCORE SAVED screen stays (1.43)
        await w.ev("NutStore.set('scores:swarm', [])"); await finish_run()
        check('1.43: the initials form is shown, its field focused', await w.ev("!!document.querySelector('#entry #ini') && document.activeElement.id === 'ini'"))
        await pad({'b': [0]}); await w.pg.keyboard.down('Enter'); await pump(1); await w.pg.keyboard.up('Enter'); await pump(3)   # (a real Enter keydown in the field and pad A in the same frame)
        saved = "!!document.querySelector('#entry [data-g=again]') && !document.querySelector('#entry #ini')"
        check('1.43: Enter in the initials field + pad A in the same frame: ONE action (the score is saved and the SCORE SAVED screen stays)',
              await w.ev(saved) and len(await w.ev("NutStore.get('scores:swarm', [])")) == 1, (await w.ev(saved), await w.ev("NutStore.get('scores:swarm', []).length"), await w.ev("Arcade.playing()")))
        await pad(); await pump(3); await pad({'b': [0]}); await pump(3)
        check('1.43: ...and the next pad A (a frame later) goes on as usual (Continue)', not await w.ev(saved), await w.ev(saved))
        await leave(); await pad(); await pump(2)

        # --- replays: pad input is recorded exactly like the keyboard's
        async def run(kind):
            """the same schedule of inputs, from the pad or from the keyboard; returns the replay's frames and its verification"""
            await w.ev("Arcade.open('swarm'); __F.watch('swarm'); __F.n = 0; __F.cap = 400"); await pump(3)
            sched = [('a', 2), (None, 3), ('left', 25), (None, 4), ('right', 40), ('a', 30), (None, 5), ('up', 6), ('left', 12), ('a', 2), (None, 2), ('right', 33), (None, 3), ('a', 1), (None, 60), ('b', 3), (None, 30), ('b', 3), ('left', 50), (None, 400)]
            PB = {'left': [14], 'right': [15], 'up': [12], 'a': [0], 'b': [9]}
            KC = {'left': 'ArrowLeft', 'right': 'ArrowRight', 'up': 'ArrowUp', 'a': 'Space', 'b': 'Enter'}
            for k, n in sched:
                if kind == 'pad': await pad({'b': PB[k]} if k else {})
                else:
                    await w.ev("for (const c of Object.values({l:'ArrowLeft',r:'ArrowRight',u:'ArrowUp',a:'Space',b:'Enter'})) __F.key(c, false)")
                    if k: await w.ev(f"__F.key('{KC[k]}', true)")
                await pump(n)
            await pad(); await pump(5)
            return await w.pg.evaluate("""async () => {
              const rp = Arcade.lastReplay(); if (!rp) return { none: true };
              const packed = await Arcade.replay.pack(rp); const v = await Arcade.replay.verify(rp.game, rp.seed, packed, rp.score);
              return { ok: v.ok, ended: v.ended, frames: rp.frames, score: rp.score, vscore: v.score, seed: rp.seed }; }""")
        rp = await run('pad'); await leave()
        check('a game played with the pad ends and records a replay', not rp.get('none') and len(rp.get('frames', [])) >= 100, len(rp.get('frames', [])))
        check('the pad run re-verifies to the same score', rp.get('ok') and rp.get('ended') and rp.get('score') == rp.get('vscore'), {k: rp.get(k) for k in ('ok', 'ended', 'score', 'vscore')})
        check('the pad run really used the controls (moves and presses are in the replay)', any(f.split(',')[0] != '0' for f in rp['frames']) and any(f.split(',')[1] != '0' for f in rp['frames']))
        rk = await run('key'); await leave()
        check('the same inputs on the keyboard record exactly the same replay frames', rk.get('frames') == rp.get('frames'),
              (len(rk.get('frames', [])), len(rp.get('frames', [])), next((i for i, (a, c) in enumerate(zip(rk.get('frames', []), rp.get('frames', []))) if a != c), None)))
        check('the keyboard run verifies too', rk.get('ok') and rk.get('score') == rk.get('vscore'))
        check('no script errors', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
