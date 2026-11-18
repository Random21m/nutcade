"""Stress test for the wallet-creation helper (W.create): creates many fresh wallets, optionally on a throttled CPU, several
at once, and reports every failure. Not part of run_all.sh (it checks the test helper, not NUTCADE).
  python3 create_stress.py [--n 50] [--throttle 4] [--conc 1] [--wrong-every 3]
  --throttle N  CDP Emulation.setCPUThrottlingRate (4 = a page four times slower than this machine)
  --price-ms N  the price service (coinbase) answers after 0..N ms; the app redraws the gate screen when it does
  --storm-ms N  the page redraws itself every N ms (an extreme of the same thing)
  --conc K      K wallets (browser contexts) are created at the same time, in each of the --n rounds
Exits non-zero on any failure. Use NUTCADE_URL and QA_NOSTR_PORT like the suites do; CHROME for a browser binary."""
import argparse, asyncio, os, random, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import newwallet

PRICE = '{"data":{"currency":"BTC","rates":{"USD":"61000.5"}}}'
async def one(b, tag, throttle, wrong, price_ms, storm_ms):
    w = await newwallet(b, tag)
    try:
        if price_ms:   # the price service answers some time later, as on CI (where it is reachable): the app then redraws its screen
            async def price(route): await asyncio.sleep(random.uniform(0, price_ms) / 1000); await route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=PRICE)
            await w.pg.context.route('https://api.coinbase.com/**', price)
        if storm_ms: await w.ev(f"setInterval(()=>Nutcade.refresh(), {int(storm_ms)})")   # a redraw every N ms, whatever the screen
        if throttle > 1:
            cdp = await w.pg.context.new_cdp_session(w.pg); await cdp.send('Emulation.setCPUThrottlingRate', {'rate': throttle})
        t0 = time.time()
        phrase = await w.create(wrong_first=wrong)
        ok = (len(phrase.split()) == 12 and await w.ev("Nutcade.S.seed.backedUp") is True and await w.ev("!!document.querySelector('.tabbar')")
              and not await w.ev("!!document.querySelector('#layer .sheet')") and w.done_shown and (not wrong or "doesn't match" in w.wrong_msg))
        if not ok: raise AssertionError(f'wallet not in the expected state: backedUp={await w.ev("Nutcade.S.seed.backedUp")} done_shown={w.done_shown} wrong_msg={getattr(w, "wrong_msg", None)!r}')
        return time.time() - t0
    finally:
        await w.pg.context.close()

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--n', type=int, default=50); ap.add_argument('--throttle', type=float, default=1)
    ap.add_argument('--conc', type=int, default=1); ap.add_argument('--price-ms', type=int, default=0); ap.add_argument('--storm-ms', type=int, default=0); ap.add_argument('--wrong-every', type=int, default=3); a = ap.parse_args()
    fails, times = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        for r in range(a.n):
            res = await asyncio.gather(*[one(b, f'stress{r}.{k}', a.throttle, a.wrong_every > 0 and (r * a.conc + k) % a.wrong_every == 0, a.price_ms, a.storm_ms) for k in range(a.conc)], return_exceptions=True)
            for k, x in enumerate(res):
                if isinstance(x, BaseException): fails.append((r, k, ''.join(traceback.format_exception_only(type(x), x)).strip()[:300])); print(f'FAIL round {r}.{k}: {fails[-1][2]}', flush=True)
                else: times.append(x)
        await b.close()
    total = a.n * a.conc
    print(f'SUMMARY creates={total} ok={len(times)} failed={len(fails)} throttle={a.throttle} conc={a.conc} price_ms={a.price_ms} storm_ms={a.storm_ms} mean={sum(times)/max(1,len(times)):.2f}s max={max(times or [0]):.2f}s', flush=True)
    sys.exit(1 if fails else 0)
asyncio.run(main())
