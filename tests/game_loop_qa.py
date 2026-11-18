"""The arcade clock: every cabinet runs 60 steps a second whatever the screen's refresh rate, and replays still verify.
requestAnimationFrame is faked (the test calls the frames itself at 30, 60, 120 and 144 Hz), so it needs no real display."""
import os, sys, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import newwallet, check, results
from playwright.async_api import async_playwright

import glob
FILES = len(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'game_*.js')))   # cabinets in their own file; the eight originals come on top
HZ = [30, 60, 120, 144]
FAKE = """(() => {
  const F = window.__F = { t: 1000, id: 0, q: new Map(), steps: 0 };
  window.requestAnimationFrame = cb => { F.q.set(++F.id, cb); return F.id; };
  window.cancelAnimationFrame = id => { F.q.delete(id); };
  F.pump = (n, hz) => { for (let i = 0; i < n; i++) { F.t += 1000 / hz; const cbs = [...F.q.values()]; F.q.clear(); cbs.forEach(cb => cb(F.t)); } };
  F.jump = ms => { F.t += ms; const cbs = [...F.q.values()]; F.q.clear(); cbs.forEach(cb => cb(F.t)); };
  // count the real update() calls of the open cabinet, per run state (so a replay's own steps are not mixed in)
  F.count = id => { const g = Arcade.games.find(x => x.id === id); if (g.__wrapped) return; g.__wrapped = true; const u = g.update; F.n = 0; F.cap = 0; F.seen = new WeakMap();
    g.update = function (s, G) { F.n++; const c = (F.seen.get(s) || 0) + 1; F.seen.set(s, c); if (F.cap && c === F.cap) G.over(); if (F.stub) return; return u.apply(this, arguments); }; };
  F.key = (code, down) => window.dispatchEvent(new KeyboardEvent(down ? 'keydown' : 'keyup', { code, bubbles: true, cancelable: true }));
})()"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'loop'); await w.create()
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(500)
        ids = await w.ev("Arcade.games.map(g => g.id)")
        replayable = await w.ev("Arcade.games.filter(g => !g.noChallenge).map(g => g.id)")
        check('the loop test covers every cabinet in the arcade', len(ids) > FILES and len(ids) == await w.ev("document.querySelectorAll('[data-game]').length"), ids)
        await w.ev(FAKE)
        for hz in HZ:
            bad = []
            for gid in ids:
                await w.ev(f"Arcade.open('{gid}')")
                await w.ev(f"__F.count('{gid}'); __F.stub = true; __F.n = 0; __F.pump(3, {hz}); __F.key('Space', true); __F.key('Space', false)")
                await w.ev(f"__F.pump(6, {hz})")   # the title takes the press; the run starts
                n0 = await w.ev("__F.n")
                await w.ev(f"__F.pump({hz} * 3, {hz})")   # three seconds of screen refreshes
                n1 = await w.ev("__F.n")
                steps = n1 - n0
                if not 177 <= steps <= 183: bad.append((gid, steps))
                await w.ev("document.querySelector('[data-g=exit]').click()")
            check(f'{hz} Hz: all {len(ids)} cabinets take 180 steps in 3 seconds (60 a second)', not bad, bad)
        # a key press that lands between two steps (120 and 144 Hz skip frames) is not lost
        lost = []
        for hz in (120, 144):
            await w.ev(f"Arcade.open('swarm'); __F.count('swarm'); __F.stub = true; __F.n = 0; __F.pump(1, {hz})")
            await w.ev("__F.key('Space', true); __F.key('Space', false)")
            await w.ev(f"__F.pump(8, {hz})")
            if not await w.ev("__F.n") > 0: lost.append(hz)
            await w.ev("document.querySelector('[data-g=exit]').click()")
        check('a quick tap on a 120 or 144 Hz screen still starts the game', not lost, lost)
        # coming back to the tab: one frame with a huge gap runs one step, and a 100 ms hitch at most a few, never a spiral
        await w.ev("Arcade.open('swarm'); __F.count('swarm'); __F.stub = true; __F.pump(2, 60); __F.key('Space', true); __F.key('Space', false); __F.pump(4, 60); __F.n = 0; __F.jump(15000)")
        big = await w.ev("__F.n")
        await w.ev("__F.n = 0; __F.jump(100)")
        hitch = await w.ev("__F.n")
        await w.ev("__F.n = 0; __F.jump(2000)")
        two = await w.ev("__F.n")
        check('after a long pause (tab switch) the game takes one step, not hundreds', big <= 1, big)
        check('a 100 ms hitch is caught up with at most 5 steps', 1 <= hitch <= 5, hitch)
        check('a 2 s stall is capped as well', two <= 5, two)
        await w.ev("document.querySelector('[data-g=exit]').click()")
        # a replay counts steps, not time: a run recorded at any refresh rate verifies, for every cabinet that has replays
        for hz in HZ:
            bad = []
            for gid in replayable:
                await w.ev(f"Arcade.open('{gid}')")
                await w.ev(f"__F.count('{gid}'); __F.stub = false; __F.cap = 420; __F.n = 0; __F.pump(3, {hz}); __F.key('Space', true); __F.key('Space', false)")
                codes = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'Space']
                for i in range(70):   # a varied, repeatable stream of presses while the run goes on
                    c = codes[(i * 7 + hz) % len(codes)]
                    await w.ev(f"__F.key('{c}', true); __F.pump({max(1, hz // 20)}, {hz}); __F.key('{c}', false); __F.pump({max(1, hz // 30)}, {hz})")
                await w.ev(f"__F.pump({hz} * 12, {hz})")
                r = await w.pg.evaluate("""async () => {
                  const rp = Arcade.lastReplay(); if (!rp) return { none: true };
                  const packed = await Arcade.replay.pack(rp); const v = await Arcade.replay.verify(rp.game, rp.seed, packed, rp.score);
                  return { ok: v.ok, frames: rp.frames.length, score: rp.score, ended: v.ended }; }""")
                if not r.get('ok') or not r.get('ended') or r.get('frames', 0) < 60: bad.append((gid, r))
                await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(50)
            check(f'{hz} Hz: a recorded run verifies as a replay on all {len(replayable)} cabinets with replays (up to 420 steps each)', not bad, bad)
        check('Nut Poker has no replays, by design (its deck is shuffled for real)', 'poker' in ids and 'poker' not in replayable)
        check('no script errors in the loop tests', not w.errs, w.errs[:3])
        await b.close()
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
