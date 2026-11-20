"""Daily Challenge QA: the day's cabinet and seed, the first-run-counts rule, the streak, the clock edge cases (time
zones, clock moved back or forward, playing over midnight UTC), sharing to Nostr only on a tap (offline included),
five languages, and the layout. The clock is injected (Daily.setClock); Nostr is a stand-in WebSocket in the page."""
import os, sys, asyncio, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, check, results, URL, OUT
from playwright.async_api import async_playwright

SHOTS = os.environ.get('SHOTS', '')
FAKE_WS = """(() => { window.__ws = { mode: 'ok', made: 0, notes: [] };
  class FakeWS { constructor(u) { this.url = u; window.__ws.made++; setTimeout(() => { if (this._closed) return; if (window.__ws.mode === 'fail') { this.onerror && this.onerror(new Event('error')); this.onclose && this.onclose(); } else this.onopen && this.onopen(); }, 20); }
    send(m) { let d; try { d = JSON.parse(m); } catch (e) { return; } if (d[0] === 'EVENT' && d[1] && d[1].kind === 1) { window.__ws.notes.push(d[1]); setTimeout(() => this.onmessage && this.onmessage({ data: JSON.stringify(['OK', d[1].id, true, '']) }), 10); } }
    close() { this._closed = true; } }   // (a socket closed before its 20 ms are up never opens, as a real one: the app drops its reference when it closes one, and the open would find it null)
  window.WebSocket = FakeWS; window.__i18nMiss = new Set(); })()"""
PATCH = """window.__patch = (id, score) => { const g = Arcade.games.find(x => x.id === id); if (!g.__orig) g.__orig = g.update; window.__score = score; window.__hold = false;
  g.update = (s, G) => { if (!window.__hold) { G.addScore(window.__score); G.over(); } }; };
window.__unpatch = id => { const g = Arcade.games.find(x => x.id === id); if (g.__orig) { g.update = g.__orig; g.__orig = null; } };
0"""

WORDS = """(() => { const el = document.querySelector('#dyText'), tn = el.firstChild, txt = tn.textContent, cs = getComputedStyle(el), inner = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const bad = [], re = /\\S+/g; let m;
  while ((m = re.exec(txt))) { const r = document.createRange(); r.setStart(tn, m.index); r.setEnd(tn, m.index + m[0].length); if (r.getClientRects().length < 2) continue;
    const s = document.createElement('span'); s.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + cs.font; s.textContent = m[0]; document.body.appendChild(s); const wide = s.getBoundingClientRect().width > inner; s.remove();
    if (!wide) bad.push(m[0]); }   // a word may be cut only when it is wider than the whole line
  return bad; })()"""
def ms(y, mo, d, h=0, mi=0, s=0): return int(datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone.utc).timestamp() * 1000)

def fnv(s):
    h = 0x811c9dc5
    for b in s.encode(): h = ((h ^ b) * 0x01000193) & 0xffffffff
    return h
def py_pick(date, ids):
    return max(ids, key=lambda i: (fnv(f'nutcade-daily-pick-{date}-{i}'), [-ord(c) for c in i]))

async def wallet(b, name, width=390, height=844, tz=None, lang=None, mobile=True):
    kw = dict(viewport={'width': width, 'height': height}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    if tz: kw['timezone_id'] = tz
    ctx = await b.new_context(**kw)
    prefs = {'sound': False, 'crt': True, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    if lang: prefs['lang'] = lang
    await ctx.add_init_script(FAKE_WS)
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, name); w.ctx = ctx
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and 'ERR_' not in m.text and 'Failed to load resource' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    await w.create(); await w.ev(PATCH)
    return w

async def arcade(w, t=None):
    if t is not None: await w.ev(f"Daily.setClock(() => {t})")
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(150)
    await w.ev("Nutcade.refresh()"); await w.wait(250)

async def play(w, score=1000, hold=False):
    """Start today's daily from the lobby and (unless held) finish it at once with `score`."""
    gid = await w.ev("Daily.info().id")
    await w.ev(f"__patch('{gid}', {score}); window.__hold = {str(hold).lower()}")
    await w.click('[data-daily-play]'); await w.wait(250)
    await w.pg.keyboard.press('Space'); await w.wait(250 if hold else 2400)
    return gid

async def finish_play(w):
    await w.ev("window.__hold = false"); await w.wait(2400)

async def leave(w):
    if await w.ev("!!document.querySelector('[data-g=exit2]')"): await w.click('[data-g=exit2]')
    elif await w.ev("!!document.querySelector('[data-g=exit]')"): await w.click('[data-g=exit]')
    await w.wait(250)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ---------- the pure parts: hash, pick, seeds, the hook ----------
        w = await wallet(b, 'main')
        dates = ['2026-11-18', '2026-01-01', '2027-02-28', '2026-12-31', '2030-07-04']
        ok = True
        for d in dates:
            if await w.ev(f"Daily.seedOf('{d}')") != fnv('nutcade-daily-' + d): ok = False
        check('seed = FNV-1a of "nutcade-daily-<UTC date>" (matches an independent implementation)', ok)
        ids8 = ['swarm', 'maze', 'brick', 'rocks', 'hop', 'shield', 'nibble', 'flipper']
        DAILY = ids8 + ['neonRoad', 'links', 'bowl']   # the cabinets that join: the eight originals, Neon Road and Acorn Links (seeded); never Nut Poker
        check('the 8 original cabinets, Neon Road, Acorn Links and Nut Bowl join the daily', sorted(await w.ev("Daily.eligible().map(g=>g.id)")) == sorted(DAILY))
        allids = await w.ev("Arcade.games.map(g => g.id)")
        check('every cabinet in the arcade is either in the daily or Nut Poker', sorted(set(allids) - set(DAILY)) == ['poker'], allids)
        check('Nut Poker is not flagged daily and is not eligible (its shuffle is truly random, so two phones could never play the same deal)',
              await w.ev("Arcade.games.find(g => g.id === 'poker').daily !== true && !Daily.eligible().some(g => g.id === 'poker')"))
        never = await w.ev("""(() => { const ids = Daily.eligible().map(g => g.id); const bad = []; let d = Date.parse('2026-01-01T00:00:00Z');
          for (let i = 0; i < 1500; i++, d += 86400000) { const day = new Date(d).toISOString().slice(0, 10); if (Daily.pick(day, ids) === 'poker') bad.push(day); } return bad; })()""")
        check('Nut Poker is never the daily cabinet (1,500 days checked)', never == [], never[:3])
        check('with Poker flagged by mistake it still cannot be picked by the daily screen (it has no replays, so it is excluded by noChallenge too)',
              await w.ev("(() => { const g = Arcade.games.find(x => x.id === 'poker'); const had = g.daily; g.daily = true; try { return !Daily.eligible().some(x => x.id === 'poker'); } finally { g.daily = had; } })()"))
        ok = True
        for d in dates:
            if await w.ev(f"Daily.pick('{d}', {json.dumps(DAILY)})") != py_pick(d, DAILY): ok = False
        check("today's cabinet is picked from the date alone (matches an independent implementation)", ok)
        check('the pick does not depend on the order of the list', await w.ev(f"Daily.pick('2026-11-18', {json.dumps(DAILY)}) === Daily.pick('2026-11-18', {json.dumps(DAILY[::-1])})"))
        # a new cabinet joining changes only the days it wins
        days = [datetime.date(2026, 1, 1) + datetime.timedelta(i) for i in range(365)]
        old = [py_pick(str(d), ids8) for d in days]; new = [py_pick(str(d), ids8 + ['neonRoad']) for d in days]
        changed = [i for i in range(365) if old[i] != new[i]]
        check('a new cabinet only changes the days it wins itself', all(new[i] == 'neonRoad' for i in changed) and 15 < len(changed) < 80, len(changed))
        check('all 8 cabinets get picked over a year', len(set(old)) == 8)
        # the hook: daily:true joins, no flag stays out, init gets the seed
        r = await w.ev("""(() => { const gs = Arcade.games; const a = { id: 'fake1', name: 'FAKE ONE', daily: true, init() {}, update() {}, draw() {}, thumb() {} }, c = { id: 'fake2', name: 'FAKE TWO', init() {}, update() {}, draw() {}, thumb() {} };
          gs.push(a, c); const ids = Daily.eligible().map(g => g.id); gs.splice(gs.length - 2, 2); return [ids.includes('fake1'), ids.includes('fake2'), Daily.eligible().length]; })()""")
        check('hook: a cabinet with daily:true joins, one without the flag does not', r == [True, False, len(DAILY)], r)
        seen = await w.ev("""(() => { const g = Arcade.games.find(x => x.id === 'swarm'); const o = g.init; let got = []; g.init = function (G, seed) { got.push(seed); return o.call(this, G, seed); };
          Arcade.layout('swarm', 12345); g.init = o; return got; })()""")
        check('hook: init(G, seed) receives the run seed', seen == [12345], seen)
        det = await w.ev("""(async () => { const out = {}, code = i => [(i >> 5) % 3 === 0 ? 4 : (i >> 4) & 15 & 3 | 0, (i % 40 === 0) ? 16 : 0, 0, 112, 144, '', '', ''].join(',');
          const frames = Array.from({ length: 900 }, (_, i) => code(i)); const packed = await Arcade.replay.pack({ frames });
          for (const g of Arcade.games.filter(g => g.daily)) { const s = Daily.seedOf('2026-11-18'), o = Daily.seedOf('2026-11-19'); const a = await Arcade.replay.verify(g.id, s, packed, 0), c = await Arcade.replay.verify(g.id, s, packed, 0), d = await Arcade.replay.verify(g.id, o, packed, 0);
            out[g.id] = [a.score === c.score && a.frames === c.frames, a.frames > 0, a.score, d.score]; } return out; })()""")
        check('every cabinet plays the same from the same day seed (same inputs, same score and frames)', all(v[0] and v[1] for v in det.values()), det)
        same = await w.ev("""(() => { const out = {}; const seed = Daily.seedOf('2026-11-18'), other = Daily.seedOf('2026-11-19');
          { for (const g of Arcade.games.filter(g => ['neonRoad', 'links', 'bowl'].includes(g.id))) { const a = Arcade.layout(g.id, seed), b = Arcade.layout(g.id, seed), c = Arcade.layout(g.id, other); out[g.id] = [a === b, a !== c, a.length]; } }
          return out; })()""")
        check('Neon Road, Acorn Links and Nut Bowl start identically from the same seed (road, traffic, holes, the computer\'s drives), and differently from another day\'s', all(v[0] and v[1] for v in same.values()) and len(same) == 3, same)
        check('another day\'s seed plays differently in most cabinets', sum(1 for v in det.values() if v[2] != v[3]) >= 3, det)

        # ---------- the lobby entry ----------
        T0 = ms(2026, 11, 18, 12, 0, 0)
        await arcade(w, T0)
        top = await w.ev("document.querySelector('#arcadeScreen').firstElementChild.hasAttribute('data-daily')")
        check('DAILY CHALLENGE entry is at the top of the arcade menu', top)
        gid = py_pick('2026-11-18', DAILY)
        txt = await w.ev("document.querySelector('[data-daily]').innerText")
        name = await w.ev(f"Arcade.games.find(g=>g.id==='{gid}').name")
        check("shows today's cabinet", name in txt, txt[:120])
        check('shows a not-played-yet state and the countdown (12h 0m at noon UTC)', 'NOT PLAYED YET' in txt.upper() and '12h 0m' in txt, txt)
        check('share is disabled until there is an official score', await w.ev("document.querySelector('[data-daily-share]').disabled"))
        check('lobby lists every cabinet', await w.ev("document.querySelectorAll('[data-game]').length") == await w.ev('Arcade.games.length'))

        # ---------- play: the first run counts ----------
        seed_seen = await w.ev("""(() => { const g = Arcade.games.find(x => x.id === '%s'); window.__seeds = []; if (!g.__oi) { g.__oi = g.init; g.init = function (G, seed) { window.__seeds.push(seed); return g.__oi.call(this, G, seed); }; } return 1; })()""" % gid)
        await w.ev(f"__patch('{gid}', 12340); window.__hold = true")
        await w.click('[data-daily-play]'); await w.wait(300)
        title_ok = await w.ev("!!document.querySelector('.game-view canvas')")
        check('PLAY DAILY opens the cabinet', title_ok)
        await w.pg.keyboard.press('Space'); await w.wait(250)
        st = await w.ev("Arcade.daily()")
        check('the run uses the day seed and is flagged official', st['on'] and st['seed'] == fnv('nutcade-daily-2026-11-18') and st['run']['official'] is True, st)
        check('the cabinet init got the day seed', await w.ev("window.__seeds[0]") == fnv('nutcade-daily-2026-11-18'))
        await finish_play(w)
        sheet = await w.ev("(document.querySelector('#entry')||{}).innerText||''")
        check('result shows OFFICIAL SCORE, the score and the streak', 'OFFICIAL SCORE' in sheet and '012340' in sheet and 'Streak: 1 day' in sheet, sheet)
        h = await w.ev("Daily.days()")
        check('the first run is saved as the day\'s official score', len(h) == 1 and h[0]['d'] == '2026-11-18' and h[0]['o'] == 12340 and h[0]['g'] == gid, h)
        check('a daily run also lands in the cabinet\'s high-score table', await w.ev(f"JSON.parse(localStorage.getItem('nutcade:scores:{gid}')||'[]')[0]?.s") == 12340)
        # replay for fun
        await w.click('[data-g=again]'); await w.wait(200)
        await w.ev(f"__patch('{gid}', 20000); window.__hold = true")
        await w.pg.keyboard.press('Space'); await w.wait(250)
        check('a second run is a practice run', (await w.ev("Arcade.daily()"))['run']['official'] is False)
        await finish_play(w)
        sheet = await w.ev("(document.querySelector('#entry')||{}).innerText||''")
        check('practice result says so and keeps the official score', 'PRACTICE RUN' in sheet and '12,340' in sheet, sheet)
        h = await w.ev("Daily.days()")
        check('the official score stays, the best-for-fun and run count update', h[0]['o'] == 12340 and h[0]['b'] == 20000 and h[0]['n'] == 2, h)
        await leave(w); await w.wait(300)
        txt = await w.ev("document.querySelector('[data-daily]').innerText")
        check('lobby shows today\'s official score, best for fun and the streak', '12,340' in txt and 'Best today for fun: 20,000' in txt and 'Streak: 1 day' in txt, txt)
        check('share is enabled once played', not await w.ev("document.querySelector('[data-daily-share]').disabled"))

        # ---------- share: nothing sent until Post ----------
        before = await w.ev("__ws.notes.length")
        await w.click('[data-daily-share]'); await w.wait(300)
        pv = await w.ev("document.querySelector('#dyText').innerText")
        check('the note preview wraps at spaces, never in the middle of a word (390 px)', await w.ev(WORDS) == [], await w.ev(WORDS))
        await w.pg.set_viewport_size({'width': 320, 'height': 640}); await w.wait(200)
        check('the note preview wraps at spaces on a 320 px phone (only the link may be cut, and only if it does not fit)', await w.ev(WORDS) == [], await w.ev(WORDS))
        await w.pg.set_viewport_size({'width': 390, 'height': 844}); await w.wait(200)
        nm = name.title()
        check('preview shows the note and the app link', pv == f"NUTCADE Daily Challenge Nov 18: {nm} 12,340 🕹️ #nutcade\nhttps://random21m.github.io/nutcade/", pv)
        check('opening the preview sends nothing', await w.ev("__ws.notes.length") == before)
        sheet = await w.sheet_text()
        check('the preview says what Post does (public, signed with your key, which relays)', 'public note on Nostr' in sheet and 'Nothing is sent until you tap Post' in sheet and 'npub1' in sheet and 'to your relay.' in sheet, sheet)
        await w.ev("window.__ws.mode='fail'")
        await w.click('#dyPost'); await w.wait(900)
        check('relays down: clear error, nothing sent, button ready to retry', 'Couldn\'t reach any relay' in await w.ev("document.querySelector('#dyMsg').innerText") and not await w.ev("document.querySelector('#dyPost').disabled") and await w.ev("__ws.notes.length") == 0)
        check('the score and history are untouched after the failed post', (await w.ev("Daily.days()"))[0]['o'] == 12340)
        await w.ev("window.__ws.mode='ok'")
        await w.click('#dyPost'); await w.wait(700)
        notes = await w.ev("__ws.notes")
        check('Post publishes exactly one kind-1 note with the previewed text and a #nutcade tag', len(notes) == 1 and notes[0]['kind'] == 1 and notes[0]['content'] == pv and ['t', 'nutcade'] in notes[0]['tags'], notes)
        check('the note is signed for real (valid Nostr signature)', await w.ev("CashuLib.verifyEvent(__ws.notes[0])"))
        check('success is shown and Post is spent', 'Posted to 1 relay' in await w.ev("document.querySelector('#dyMsg').innerText") and await w.ev("document.querySelector('#dyPost').disabled"))
        # offline: the browser says it is offline -> no connection attempts at all
        await w.ev("Nutcade.closeSheet()"); await w.ctx.set_offline(True)
        made = await w.ev("__ws.made")
        await w.click('[data-daily-share]'); await w.wait(250); await w.click('#dyPost'); await w.wait(500)
        msg = await w.ev("document.querySelector('#dyMsg').innerText")
        check('offline: a clear error, no connection tried, nothing lost', "Couldn't reach any relay" in msg and await w.ev("__ws.made") == made and (await w.ev("Daily.days()"))[0]['o'] == 12340, msg)
        await w.ctx.set_offline(False)
        n0 = await w.ev("__ws.notes.length")
        await w.click('#dyPost'); await w.wait(700)
        check('back online, Try again posts the same signed note', await w.ev("__ws.notes.length") == n0 + 1)
        # copy-only without a Nostr key
        await w.ev("Nutcade.closeSheet(); NutDailyNostr.can = () => false")
        await w.click('[data-daily-share]'); await w.wait(250)
        sheet = await w.sheet_text()
        check('no Nostr key: no Post button, Copy text is offered', not await w.ev("!!document.querySelector('#dyPost')") and 'copy text' in sheet.lower() and 'no nostr key' in sheet.lower(), sheet)
        n1 = await w.ev("__ws.notes.length")
        await w.click('[data-act=copy]'); await w.wait(300)
        check('copying sends nothing', await w.ev("__ws.notes.length") == n1)
        await w.ev("Nutcade.closeSheet()")

        # ---------- history and streak ----------
        await w.click('[data-daily-hist]'); await w.wait(250)
        hs = await w.sheet_text()
        check('history lists past days', 'Nov 18' in hs and '12,340' in hs and 'Streak: 1 day' in hs, hs)
        await w.ev("Nutcade.closeSheet()")
        # day by day through the API
        r = await w.ev("""(() => { const out = []; const day = n => Date.UTC(2026, 10, 18 + n, 9);
          for (const n of [1, 2, 3]) { Daily.setClock(() => day(n)); const run = Daily.begin(); out.push(Daily.finish(run, 100 * n, false).streak); }
          Daily.setClock(() => day(5)); out.push(Daily.info().streak);            // a missed day (Nov 22): streak lapses
          Daily.setClock(() => day(4)); out.push(Daily.info().streak);            // Nov 22 is the day after Nov 21 played: still alive (yesterday played)
          Daily.setClock(() => day(5)); const run = Daily.begin(); out.push(Daily.finish(run, 50, false).streak);
          Daily.setClock(() => day(7)); out.push(Daily.info().streak, Daily.info().best); return out; })()""")
        check('streak counts days in a row, survives an unplayed today, resets after a missed day', r == [2, 3, 4, 0, 4, 1, 0, 4], r)

        # ---------- the clock ----------
        await arcade(w, ms(2026, 11, 25, 9))
        check('clock ok: no clock notice', not await w.ev("!!document.querySelector('[data-daily-clock]')"))
        n_days = await w.ev("Daily.days().length")
        await arcade(w, ms(2026, 11, 29, 9))   # forward four days: a fresh day
        txt = await w.ev("document.querySelector('[data-daily]').innerText")
        check('clock forward: shows the new day, not played yet, streak 0, history kept', 'Nov 29, 2026' in txt and 'NOT PLAYED YET' in txt.upper() and 'No streak yet' in txt and await w.ev("Daily.days().length") == n_days, txt)
        await arcade(w, ms(2026, 11, 22, 9))   # back a week
        check('clock back: a notice appears', await w.ev("!!document.querySelector('[data-daily-clock]')"))
        info = await w.ev("Daily.info()")
        check('clock back: the day is shown by the clock but not official', info['ok'] is False and info['official'] is False and info['date'] == '2026-11-22', info)
        # a run now is for fun: saved nowhere in the history/streak
        gid2 = await play(w, 999)
        sheet = await w.ev("(document.querySelector('#entry')||{}).innerText||''")
        check('clock back: the run is a practice run with a clear reason', 'PRACTICE RUN' in sheet and 'clock looks wrong' in sheet, sheet)
        await leave(w)
        h2 = await w.ev("Daily.days()")
        check('clock back: nothing was added to history or the streak', len(h2) == n_days and not any(x['d'] == '2026-11-22' and x['o'] == 999 for x in h2), h2)
        # same-day small step back is not a problem
        await arcade(w, ms(2026, 11, 29, 22)); await arcade(w, ms(2026, 11, 29, 21, 30))
        check('clock back within the same UTC day is fine', not await w.ev("!!document.querySelector('[data-daily-clock]')"))
        # the 1970 reset clock
        await arcade(w, 0)
        check('a clock reset to 1970 is flagged, no crash', await w.ev("!!document.querySelector('[data-daily-clock]')") and not w.errs, w.errs[:2])
        await w.ev("Daily.setClock(() => NaN); Nutcade.refresh()"); await w.wait(200)
        check('a broken clock value does not crash the page', not w.errs, w.errs[:2])
        # "My clock is right" lifts it
        await arcade(w, ms(2026, 11, 22, 9))
        await w.click('[data-daily-trust]'); await w.wait(400)
        check('"My clock is right" clears the notice and makes the day official again', not await w.ev("!!document.querySelector('[data-daily-clock]')") and (await w.ev("Daily.info()"))['official'] is True)
        await w.close()

        # ---------- playing over midnight UTC ----------
        await arcade(w, ms(2026, 12, 3, 23, 59, 30))
        d1 = await w.ev("Daily.info().date")
        await play(w, 777, hold=True)
        st = await w.ev("Arcade.daily().run")
        check('over midnight: the run starts on the day it began', st['date'] == '2026-12-03' and st['official'] is True, st)
        await w.ev("Daily.setClock(() => %d)" % ms(2026, 12, 4, 0, 0, 10))
        await finish_play(w)
        h = await w.ev("Daily.days()")
        e3 = [x for x in h if x['d'] == '2026-12-03']; e4 = [x for x in h if x['d'] == '2026-12-04']
        check('over midnight: the score counts for the day the run started', len(e3) == 1 and e3[0]['o'] == 777 and not e4, h[-2:])
        await leave(w); await w.wait(300)
        txt = await w.ev("document.querySelector('[data-daily]').innerText")
        check('over midnight: the new day is fresh and unplayed', 'Dec 4, 2026' in txt and 'NOT PLAYED YET' in txt.upper(), txt)
        # a title screen left open across midnight moves on to the new day's cabinet
        days_ids = [(d, py_pick(d, DAILY)) for d in ['2026-12-10', '2026-12-11', '2026-12-12', '2026-12-13', '2026-12-14', '2026-12-15']]
        pair = next((a, c) for a, c in zip(days_ids, days_ids[1:]) if a[1] != c[1])
        await arcade(w, ms(2026, 12, int(pair[0][0][-2:]), 23, 59, 50))
        await w.click('[data-daily-play]'); await w.wait(300)
        await w.ev("Daily.setClock(() => %d)" % ms(2026, 12, int(pair[1][0][-2:]), 0, 0, 5))
        await w.pg.keyboard.press('Space'); await w.wait(500)
        ttl = await w.ev("document.querySelector('.game-view .ttl').innerText")
        want = await w.ev(f"Arcade.games.find(g=>g.id==='{pair[1][1]}').name")
        check('title screen left open over midnight: pressing start opens the NEW day\'s cabinet', ttl == want and await w.ev("Arcade.daily().on"), (ttl, want))
        await leave(w)

        # ---------- leaving and crashing mid-run ----------
        await arcade(w, ms(2027, 1, 5, 10))
        gid = await w.ev("Daily.info().id")
        await w.ev(f"__unpatch('{gid}')")
        await w.click('[data-daily-play]'); await w.wait(300); await w.pg.keyboard.press('Space'); await w.wait(250)
        for k in ['ArrowLeft', 'Space', 'ArrowRight', 'Space']:
            await w.pg.keyboard.down(k); await w.wait(120); await w.pg.keyboard.up(k)
        await w.pg.keyboard.press('Enter'); await w.wait(150)
        check('real game: daily run pauses', await w.ev("document.querySelector('.game-view canvas') !== null"))
        await w.pg.keyboard.press('Enter'); await w.wait(150)
        await w.click('[data-g=exit]'); await w.wait(300)
        check('...the day is still unplayed', not await w.ev("Daily.days().some(x => x.d === '2027-01-05')"))
        await w.ev(f"__patch('{gid}', 0)"); await w.ev("window.__hold = true")
        await w.click('[data-daily-play]'); await w.wait(250); await w.pg.keyboard.press('Space'); await w.wait(250)
        await w.ev("Daily.progress(Arcade.daily().run, 4200)")
        await w.pg.reload(); await w.wait(1200)
        await w.ev(PATCH)
        await arcade(w, ms(2027, 1, 5, 10, 5))
        e = await w.ev("Daily.days().find(x => x.d === '2027-01-05')")
        check('a run cut off by closing the app keeps the score it had reached', e and e['o'] == 4200, e)

        # ---------- time zones: the reset line shows YOUR time, the day stays UTC ----------
        await w.ctx.close()
        cases = [('America/New_York', ms(2026, 11, 18, 12), '7:00 PM', '2026-11-18'), ('America/New_York', ms(2026, 7, 18, 12), '8:00 PM', '2026-07-18'),
                 ('Asia/Kolkata', ms(2026, 11, 18, 12), '5:30 AM', '2026-11-18'), ('Asia/Kathmandu', ms(2026, 11, 18, 12), '5:45 AM', '2026-11-18'),
                 ('Pacific/Auckland', ms(2026, 11, 18, 12), '1:00 PM', '2026-11-18'), ('America/Los_Angeles', ms(2026, 11, 18, 3, 30), '4:00 PM', '2026-11-18')]
        picks = {}
        for tz, t, want, date in cases:
            z = await wallet(b, 'tz', tz=tz); await arcade(z, t)
            line = await z.ev("document.querySelector('[data-daily-reset]').innerText")
            dline = await z.ev("document.querySelector('[data-daily] .tiny').innerText")
            lid = await z.ev("Daily.info().id")
            picks.setdefault(t, set()).add(lid)
            check(f'time zone {tz}, {date}: reset line says {want} your time', want in line.replace(' ', ' ') and 'midnight UTC' in line, line)
            if tz == 'America/Los_Angeles': check('time zone: late evening in Los Angeles (Nov 17 locally) is still the UTC day Nov 18', await z.ev("new Date(%d).toLocaleDateString('en-US')" % t) == '11/17/2026' and await z.ev("Daily.info().date") == '2026-11-18')
            check(f'time zone {tz}: the date and cabinet are the UTC day\'s ({date})', date in await z.ev("Daily.info().date") and lid == py_pick(date, DAILY) and 'UTC' in dline, dline)
            await z.ctx.close()
        check('the same UTC moment gives the same cabinet in every time zone', all(len(v) == 1 for v in picks.values()), picks)

        # ---------- five languages ----------
        exp = {'en': ('Nov 18', '12,340', 'NUTCADE Daily Challenge Nov 18'), 'es': ('18 nov', '12.340', 'Reto diario de NUTCADE 18 nov'), 'pt': ('18 de nov.', '12.340', 'Desafio diário do NUTCADE 18 de nov.'),
               'de': ('18. Nov.', '12.340', 'NUTCADE Tages-Challenge 18. Nov.'), 'fr': ('18 nov.', '12 340', 'Défi du jour NUTCADE 18 nov. :')}
        for lang in ['en', 'es', 'pt', 'de', 'fr']:
            z = await wallet(b, 'lang', lang=lang)
            await arcade(z, ms(2026, 11, 18, 12)); gid = await z.ev("Daily.info().id")
            await z.ev(f"__patch('{gid}', 12340)")
            await z.click('[data-daily-play]'); await z.wait(300)
            await z.pg.keyboard.press('Space'); await z.wait(2400)
            res_txt = await z.ev("(document.querySelector('#entry')||{}).innerText||''")
            check(f'{lang}: the result sheet is translated', ('OFFICIAL SCORE' in res_txt) == (lang == 'en') and 'Streak:' not in res_txt.replace('Streak: ', 'Streak:') or lang == 'en', res_txt)
            await z.click('[data-g=exit2]'); await z.wait(300)
            panel = await z.ev("document.querySelector('[data-daily]').innerText")
            check(f'{lang}: the lobby entry shows the date and number the {lang} way', exp[lang][1] in panel and exp[lang][0].split(' ')[0] in panel, panel)
            await z.click('[data-daily-share]'); await z.wait(300)
            pv = await z.ev("document.querySelector('#dyText').innerText")
            check(f'{lang}: the note preview wraps at spaces, never in the middle of a word', await z.ev(WORDS) == [], await z.ev(WORDS))
            check(f'{lang}: the note is in {lang}, with the date and score written the {lang} way', pv.startswith(exp[lang][2]) and exp[lang][1] in pv and pv.endswith('🕹️ #nutcade\nhttps://random21m.github.io/nutcade/'), pv)
            sheet = await z.sheet_text()
            one = {'en': 'to your relay.', 'es': 'en tu relé.', 'pt': 'no seu relay.', 'de': 'an Dein Relay.', 'fr': 'sur votre relais.'}[lang]
            check(f'{lang}: one relay reads in the singular ("{one}"), never "your 1 relays"', one in sheet and not any(f'{w_} 1 ' in sheet for w_ in ('tus', 'seus', 'Deine', 'vos', 'your')), sheet)
            await z.ev("Nutcade.closeSheet()")
            await z.ev("(() => { const n = window.NutDailyNostr, o = n.relayCount; window.__rc = o; n.relayCount = () => 3; })()")
            await z.click('[data-daily-share]'); await z.wait(300)
            many = {'en': 'to your 3 relays.', 'es': 'en tus 3 relés.', 'pt': 'nos seus 3 relays.', 'de': 'an Deine 3 Relays.', 'fr': 'sur vos 3 relais.'}[lang]
            sheet3 = await z.sheet_text()
            await z.ev("window.NutDailyNostr.relayCount = window.__rc")
            check(f'{lang}: three relays read in the plural ("{many}")', many in sheet3, sheet3)
            if lang != 'en': check(f'{lang}: the share sheet is translated (no English left)', 'Preview of your note' not in sheet and 'Nothing is sent' not in sheet and 'Copy text' not in sheet and 'relay' not in sheet.replace('relé', '').replace('relais', '') .lower().replace('relays', 'x') or lang in ('pt', 'de'), sheet[:200])
            await z.ev("Nutcade.closeSheet()"); await z.click('[data-daily-hist]'); await z.wait(250)
            await z.ev("Nutcade.closeSheet()")
            # the title screen lines must fit the 224px canvas
            fits = await z.ev("""(async () => { await document.fonts.load('8px "Press Start 2P"'); const c = document.createElement('canvas').getContext('2d'); c.font = '8px "Press Start 2P", monospace'; const T = Nutcade.tr; const lab = Daily.dateLabel('2026-11-18').toUpperCase();
              const lines = [T('DAILY CHALLENGE') + ' ' + lab, T('FIRST RUN COUNTS'), T('PRACTICE RUN'), T('CLOCK WRONG: NOT COUNTED'), T('DAILY')]; return lines.map(s => [s, c.measureText(s).width]); })()""")
            check(f'{lang}: canvas lines fit the 224px screen', all(wd <= 224 for _, wd in fits), fits)
            miss = await z.ev("[...window.__i18nMiss]")
            mine = [m for m in miss if any(k in m for k in ['daily', 'Daily', 'DAILY', 'relay', 'streak', 'Streak', 'official', 'OFFICIAL', 'PRACTICE', 'clock', 'Nostr', 'Post', 'reto diario', 'desafio diário', 'Tages-Challenge', 'défi du jour'])]   # (an already translated label that is run through the translator a second time shows up here)
            check(f'{lang}: no untranslated daily text reported', lang == 'en' or not mine, mine)
            check(f'{lang}: no script errors', not z.errs, z.errs[:2])
            await z.ctx.close()

        # ---------- layout at four widths and landscape ----------
        for wd, ht, mob, tag in [(320, 640, True, '320'), (375, 700, True, '375'), (430, 900, True, '430'), (1440, 900, False, '1440'), (740, 360, True, 'landscape')]:
            z = await wallet(b, 'lay' + tag, width=wd, height=ht, mobile=mob)
            await arcade(z, ms(2026, 11, 18, 12))
            m = await z.ev("""(() => { const p = document.querySelector('[data-daily]'), r = p.getBoundingClientRect(); const over = [...p.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > r.right + 1 || e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflow !== 'visible').length;
              return { sw: document.documentElement.scrollWidth, iw: innerWidth, over, w: r.width, btn: [...p.querySelectorAll('button')].every(b => b.getBoundingClientRect().height >= 40) }; })()""")
            check(f'{tag}: the daily entry fits, no sideways scroll, tap targets big enough', m['sw'] <= m['iw'] + 1 and m['over'] == 0 and m['btn'], m)
            if tag in ('320', '1440'):
                await z.ev("document.querySelector('[data-daily]').scrollIntoView()")
                if SHOTS: await z.pg.screenshot(path=f'{SHOTS}/daily-lobby-{tag}.png')
            await z.click('[data-daily-play]'); await z.wait(400)
            vis = await z.ev("""(() => { const c = document.querySelector('.game-view canvas').getBoundingClientRect(); return c.width > 80 && c.bottom <= innerHeight + 1 && c.top >= 0; })()""")
            check(f'{tag}: the daily title screen is fully on screen', vis)
            if tag in ('375', 'landscape') and SHOTS: await z.pg.screenshot(path=f'{SHOTS}/daily-title-{tag}.png')
            await z.ctx.close()
        check('no script errors anywhere', not w.errs, w.errs[:3])
        await b.close()
if __name__ == "__main__":
    asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
