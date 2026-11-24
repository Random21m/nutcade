"""Storage safety (1.21.0): a wallet that can't be saved is never silent, storage use is measured and warned about, and iPhone
users running NUTCADE as a website are told to add it to the Home Screen. Uses the local mint 3339 (no fee) and mock_nostr.py.

Storage is made to fail in a real page by patching Storage.prototype.setItem to throw QuotaExceededError (for every
'nutcade:' key while window.__quota is true), in the middle of: a plain-wallet receive, a receive with a PIN (the vault
write), a swap (switched on while the mint is being asked), and with the duress PIN's wallet open. Each time: the red notice
on the wallet screen, one toast per episode, nothing silently lost (memory keeps it, storage gets it once writes work), the
notice clearing itself, and after a reload the balance that was on screen. Also: a step that needs new counters stops before
the mint with a PIN while the vault can't be saved; lock waits; Remove PIN keeps the vault; the 70% / 90% warnings and the
Settings line; the iPhone banner (user agent and navigator.standalone spoofed) and its steps, in five languages.
S_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet, set_pin, unlock, pad, settings, set_lang, PIN, DPIN

J = json.dumps
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
QUOTA = """window.__quota = false;
(() => { const o = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) { if ((window.__quota && String(k).startsWith('nutcade:')) || (window.__qmax && String(k) === 'nutcade:vault' && String(v).length > window.__qmax) || (window.__qkeys && window.__qkeys.includes(String(k)))) throw new DOMException('The quota has been exceeded.', 'QuotaExceededError'); return o.call(this, k, v); }; })();
document.addEventListener('DOMContentLoaded', () => { window.__toasts = []; new MutationObserver(() => { const t = document.querySelector('#toast');
  if (t && !t.hidden && t.textContent && window.__toasts[window.__toasts.length - 1] !== t.textContent) window.__toasts.push(t.textContent); })
  .observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden'] }); });"""
DISK_SUM = "Object.values(JSON.parse(localStorage.getItem('nutcade:proofs')||'{}')).flat().reduce((t,p)=>t+p.amount,0)"
FULL = "!!document.querySelector('.screen [data-storage=full]')"
HEALTH = "Nutcade.storage.health()"
SF_DONE = "Nutcade.S.txs.filter(t=>t.note==='still full' && t.status==='done').map(t=>t.amount)"
SAVE_TOASTS = "(window.__toasts||[]).filter(t=>/couldn't save your wallet/.test(t)).length"


async def section(name, fn):
    only = [x for x in os.environ.get('S_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def funded(b, amt=1000, **kw):
    w = await wallet(b, init=QUOTA, **kw)
    await w.create(); await w.add_mint(B); await w.receive_ln(amt, 'start')
    await w.home(); await w.wait(300)
    return w


async def full_at(w, pattern):
    """Storage becomes full the moment the mint is asked (pattern: a URL glob): the step's counters and records are already
    on disk, its result is not."""
    async def h(route):
        try: await w.pg.evaluate("window.__quota=true")
        except Exception: pass
        await route.continue_()
    await w.pg.route(pattern, h)
    return lambda: w.pg.unroute(pattern, h)


async def until_bal(w, n, ms=40000):
    try: await w.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)==={n}", ms)
    except Exception: pass
    return await w.bal()


async def chain(w): await w.ev("(async()=>{ if (Nutcade.vault.on) await Nutcade.vault.chain; await new Promise(r=>setTimeout(r,50)); })()")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ======================= plain wallet: a receive while storage is full =======================
        async def plain():
            w = await funded(b)
            check('plain: no notice while saving works', not await w.ev(FULL) and not (await w.ev(HEALTH))['bad'])
            off = await full_at(w, '**/v1/mint/bolt11')
            ok = await w.receive_ln(500, 'while full'); await w.home(); await w.wait(400); await off()
            h = await w.ev(HEALTH)
            check('plain: storage fills while the mint is asked for a deposit: the coins are in memory', ok and await w.bal() == 1500, await w.bal())
            check('plain: the failed writes are noted (proofs among them)', h['bad'] and 'proofs' in h['keys'], h)
            check('plain: storage still has the old coins (the write really failed)', await w.ev(DISK_SUM) == 1000, await w.ev(DISK_SUM))
            txt = await w.ev("(document.querySelector('.screen [data-storage=full]')||{}).innerText||''")
            check('plain: a red notice on the wallet screen says the newest coins exist only on this screen, not to close or reload',
                  await w.ev(FULL) and await w.ev("document.querySelector('.screen [data-storage=full]').classList.contains('red')") and 'only on this screen' in txt and "Don't close or reload" in txt, txt[:200])
            check('plain: the notice gives a way out: Try again, Download backup, and Find lost ecash as the recovery path',
                  await w.ev("!!document.querySelector('[data-storage=full] [data-act=saveRetry]') && !!document.querySelector('[data-storage=full] [data-act=backupDownload]')") and 'Find lost ecash' in txt)
            check('plain: one toast says so', await w.ev(SAVE_TOASTS) == 1, await w.ev("window.__toasts"))
            check('plain: the old "blocking storage" banner (private mode) is not shown for a full storage', 'blocking storage' not in await w.ev("document.body.innerText"))
            # a deposit started while storage is still full: its counters can't be saved, so the mint is not asked for coins;
            # the paid invoice waits in memory (shown in the notes) and is collected once saving works
            await w.receive_ln(200, 'still full'); await w.home(); await w.wait(400)
            check('plain: a deposit while storage is full stops before the mint is asked for coins, and waits', await w.bal() == 1500 and await w.ev("Nutcade.S.quotes.some(q=>q.amount===200)"), await w.bal())
            check('plain: a second failure in the same episode: no second toast, the notice stays', await w.ev(SAVE_TOASTS) == 1 and await w.ev(FULL), await w.ev("window.__toasts"))
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200); await w.home(); await w.wait(200)
            check('plain: the notice is persistent (still there after changing tabs)', await w.ev(FULL))
            # writes work again: the next ordinary write clears it by itself
            await w.ev("window.__quota=false")
            await w.receive_ln(100, 'space again'); await w.home(); await w.wait(500)
            check('plain: once a write works again the notice clears itself', not await w.ev(FULL) and not (await w.ev(HEALTH))['bad'], await w.ev(HEALTH))
            # (the 200 that waited may be claimed by now, in one batch with the 100 at a NUT-29 mint: 1,600 while it still
            # waits, 1,800 once claimed, and then booked exactly once)
            disk, bal, waits, lines = await w.ev(DISK_SUM), await w.bal(), await w.ev("Nutcade.S.quotes.some(q=>q.amount===200)"), await w.ev(SF_DONE)
            check('plain: storage holds every coin on screen, the waiting 200 booked at most once (1,600 while it waits, 1,800 with one line once claimed)',
                  disk == bal and ((bal == 1600 and waits and lines == []) or (bal == 1800 and not waits and lines == [200])), (disk, bal, waits, lines))
            await w.pg.reload(); await w.wait(1200)
            check('plain: after a reload nothing is lost: the waiting deposit is collected too (1,800), with the history (one line for the 200)', await until_bal(w, 1800) == 1800 and await w.ev("['while full','still full'].every(n=>Nutcade.S.txs.some(t=>t.note===n))") and await w.ev(SF_DONE) == [200], (await w.bal(), await w.ev(SF_DONE)))
            # a new episode toasts again
            await w.ev("window.__toasts=[]; window.__quota=true")
            await w.ev("document.querySelector('[data-act=hideToggle]').click()"); await w.wait(600)
            check('plain: a new episode gets its own toast', await w.ev(SAVE_TOASTS) == 1 and await w.ev(FULL), await w.ev("window.__toasts"))
            await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(600)
            check('plain: Try again saves it and the notice goes away', not await w.ev(FULL) and 'Saved' in await w.toast(), await w.toast())
            check('plain: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= a swap while storage is full =======================
        async def swap():
            w = await funded(b, 1000)
            async def on_swap(route):
                try: await w.pg.evaluate("window.__quota=true")
                except Exception: pass
                await route.continue_()
            await w.pg.route('**/v1/swap', on_swap)
            tok, e = await w.send_ecash(7, 'swapped while full'); await w.home(); await w.wait(500)
            await w.pg.unroute('**/v1/swap')
            check('swap: the swap completes in memory (a token of 7, the rest kept)', tok and not e and await w.bal() == 993, (e, await w.bal()))
            check('swap: the notice and one toast', await w.ev(FULL) and await w.ev(SAVE_TOASTS) == 1, await w.ev("window.__toasts"))
            check('swap: storage still has the coins from before the swap (its write failed)', await w.ev(DISK_SUM) == 1000, await w.ev(DISK_SUM))
            await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(600)
            check('swap: Try again: the swap\'s result is saved, notice gone', not await w.ev(FULL) and await w.ev(DISK_SUM) == 993, await w.ev(DISK_SUM))
            await w.pg.reload(); await w.wait(1200)
            check('swap: after a reload: 993 SAT and the sent token in the history', await w.bal() == 993 and await w.ev("Nutcade.S.txs.some(t=>t.note==='swapped while full' && t.token)"), await w.bal())
            check('swap: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= with a PIN: the vault write =======================
        async def vault():
            w = await funded(b, 1000); await set_pin(w); await w.home(); await chain(w)
            before = await w.ev("localStorage.getItem('nutcade:vault')")
            off = await full_at(w, '**/v1/mint/bolt11')
            ok = await w.receive_ln(300, 'vault full'); await w.home(); await chain(w); await w.wait(300); await off()
            h = await w.ev(HEALTH)
            check('PIN: the receive works in memory', ok and await w.bal() == 1300, await w.bal())
            check('PIN: the failed vault write is noted (not swallowed)', h['bad'] and 'vault' in h['keys'], h)
            check('PIN: the vault in storage is not the wallet on screen (its write really failed)', await w.ev("localStorage.getItem('nutcade:vault')") == await w.ev("(async()=>{const v=localStorage.getItem('nutcade:vault'); document.querySelector('[data-act=hideToggle]').click(); await Nutcade.vault.chain; return v})()") and 'vault' in (await w.ev(HEALTH))['keys'])
            check('PIN: the same red notice and one toast', await w.ev(FULL) and await w.ev(SAVE_TOASTS) == 1, await w.ev("window.__toasts"))
            # a step that needs new counters: stops before the mint (the counters could not be saved)
            n0 = await w.ev("Nutcade.S.txs.length")
            tok, e = await w.send_ecash(7, 'needs counters'); await w.home(); await w.wait(300)
            check("PIN: a swap that needs new counters stops before the mint is asked (\"won't save data\"), nothing lost", not tok and "won't save data" in e and await w.bal() == 1300 and await w.ev("Nutcade.S.ops.length") == 0, (e, await w.bal()))
            # lock waits
            await w.click('[data-act=lockNow]'); await w.wait(1500)
            check("PIN: Lock waits while the wallet isn't saved (no reload, a toast says why)", await w.ev("Nutcade.vault.open && !document.querySelector('[data-pinpad=unlock]')") and "Can't lock now" in ' '.join(await w.ev("window.__toasts")), await w.ev("window.__toasts"))
            # Remove PIN while full: refused, the vault stays
            await settings(w); await w.click('[data-act=pinRemove]'); await w.wait(250); await pad(w, PIN)
            await w.until("/won't save data|PIN/.test((document.querySelector('#pinErr')||document.querySelector('#sheetErr')||{}).innerText||'') || !Nutcade.vault.on", 20000); await w.wait(500)
            check('PIN: Remove PIN while storage is full keeps the PIN and the vault (no plain copy left behind)', await w.ev("Nutcade.vault.on && Nutcade.vault.open && !!localStorage.getItem('nutcade:vault') && !localStorage.getItem('nutcade:seed') && !localStorage.getItem('nutcade:proofs')"), await w.ev("Object.keys(localStorage)"))
            await w.ev("Nutcade.closeSheet()"); await w.home(); await w.wait(200)
            check('PIN: ... and the wallet is still all there in memory', await w.bal() == 1300 and await w.ev(FULL))
            # writes work again: Try again seals the whole current vault
            await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(800); await chain(w)
            check('PIN: Try again: the vault is written and the notice is gone', not await w.ev(FULL) and await w.ev("localStorage.getItem('nutcade:vault')") != before)
            tok, e = await w.send_ecash(7, 'after space'); await w.home(); await chain(w)
            check('PIN: a swap works again', tok and not e, e)
            await w.pg.reload(); await w.wait(800); await unlock(w); await w.home(); await w.wait(500)
            check('PIN: after a reload and unlock, the balance is what was on screen (1,293) with the receive made while full', await until_bal(w, 1293, 8000) == 1293 and await w.ev("Nutcade.S.txs.some(t=>t.note==='vault full')"), await w.bal())
            # the next vault write after a failure carries everything: fail, then a write of something else entirely
            off = await full_at(w, '**/v1/mint/bolt11'); await w.receive_ln(50, 'second full'); await chain(w); await off()
            await w.ev("window.__quota=false"); await w.ev("Nutcade.S.prefs.hideAmounts=false; document.querySelector('[data-act=hideToggle]').click()"); await chain(w); await w.wait(400)
            check('PIN: any later vault write clears it (the whole vault is sealed again)', not (await w.ev(HEALTH))['bad'] and not await w.ev(FULL), await w.ev(HEALTH))
            await w.pg.reload(); await w.wait(800); await unlock(w); await w.home()
            check('PIN: ... and it held the receive made while full (1,343 after a reload)', await until_bal(w, 1343, 8000) == 1343, await w.bal())
            check('PIN: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= with a PIN: a direct write of the vault record while its seal is failing =======================
        # Storage nearly full: the vault record as it is on disk still fits (window.__qmax), the newer, bigger sealed vault doesn't.
        # Turning off Face ID and changing the PIN write the record on disk again (the old sealed data in it): that write works,
        # but it must not count as the wallet being saved.
        async def direct():
            w = await funded(b, 1000); await set_pin(w); await w.home(); await chain(w)
            await w.ev("const r=JSON.parse(localStorage.getItem('nutcade:vault')); r.bio={credId:'AA==',prfSalt:'AA==',wrap:{iv:'AA==',ct:'AA=='}}; localStorage.setItem('nutcade:vault', JSON.stringify(r))")
            async def h(route):
                try: await w.pg.evaluate("window.__qmax = localStorage.getItem('nutcade:vault').length + 40")
                except Exception: pass
                await route.continue_()
            await w.pg.route('**/v1/mint/bolt11', h)
            ok = await w.receive_ln(300, 'direct full'); await w.home(); await chain(w); await w.wait(300)
            await w.pg.unroute('**/v1/mint/bolt11', h)
            check('direct: the receive works in memory and its seal failed (notice shown)', ok and await w.bal() == 1300 and 'vault' in (await w.ev(HEALTH))['keys'] and await w.ev(FULL), (await w.bal(), await w.ev(HEALTH)))
            await settings(w); await w.click('[data-act=bioDisable]'); await w.wait(300); await chain(w); await w.home(); await w.wait(300)
            check('direct: Turn off Face ID is written (the record on disk has no bio any more)', not await w.ev("!!JSON.parse(localStorage.getItem('nutcade:vault')).bio"))
            check('direct: ... but the failed seal stays noted and the notice stays', 'vault' in (await w.ev(HEALTH))['keys'] and await w.ev(FULL), await w.ev(HEALTH))
            await settings(w); await w.click('[data-act=pinChange]'); await w.wait(200); await pad(w, PIN); await w.wait(800); await pad(w, '111333'); await w.wait(300); await pad(w, '111333'); await w.wait(2500); await chain(w)
            await w.ev("Nutcade.closeSheet()"); await w.home(); await w.wait(300)
            check('direct: Change PIN is written, and the notice still stays', 'vault' in (await w.ev(HEALTH))['keys'] and await w.ev(FULL), await w.ev(HEALTH))
            await w.ev("window.__toasts=[]"); await w.click('[data-act=lockNow]'); await w.wait(1500)
            check("direct: Lock still waits (no reload)", await w.ev("Nutcade.vault.open && !document.querySelector('[data-pinpad=unlock]')") and "Can't lock now" in ' '.join(await w.ev("window.__toasts")), await w.ev("window.__toasts"))
            await w.ev("window.__qmax=0"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(800); await chain(w)
            check('direct: with space again, the vault is sealed and the notice is gone', not (await w.ev(HEALTH))['bad'] and not await w.ev(FULL), await w.ev(HEALTH))
            await w.pg.reload(); await w.wait(800); await unlock(w, '111333'); await w.home(); await w.wait(500)
            check('direct: after a reload and unlock with the new PIN, the coins received while full are there (1,300)', await until_bal(w, 1300, 8000) == 1300 and await w.ev("Nutcade.S.txs.some(t=>t.note==='direct full')"), await w.bal())
            check('direct: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= re-reading what another tab saved, while one record can't be saved =======================
        async def sync():
            w = await funded(b, 1000)
            await w.ev("window.__qkeys=['nutcade:txs']")
            ok = await w.receive_ln(200, 'txs unsaved'); await w.home(); await w.wait(300)
            check('sync: only the history failed to save (noted)', ok and (await w.ev(HEALTH))['keys'] == ['txs'], await w.ev(HEALTH))
            # another tab saved meanwhile: a higher counter and a new stamp
            ks = await w.ev("Object.keys(Nutcade.S.counters)[0]")
            await w.ev(f"const c=JSON.parse(localStorage.getItem('nutcade:counters')); c[{J(ks)}]=900; localStorage.setItem('nutcade:counters', JSON.stringify(c)); localStorage.setItem('nutcade:gen', String(JSON.parse(localStorage.getItem('nutcade:gen'))+5))")
            tok, e = await w.send_ecash(7, 'after sync'); await w.home(); await w.wait(300)
            check("sync: the other tab's counters are taken (higher wins) although a record is failing", tok and not e and await w.ev(f"Nutcade.S.counters[{J(ks)}]") > 900, (e, await w.ev(f"Nutcade.S.counters[{J(ks)}]")))
            check('sync: the failing record (history) is not read back over: the receive made while it failed is still there', await w.ev("Nutcade.S.txs.some(t=>t.note==='txs unsaved')") and await w.bal() == 1193, await w.bal())
            await w.ev("window.__qkeys=null"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(600)
            await w.pg.reload(); await w.wait(1000); await w.home()
            check('sync: after Try again and a reload, all of it is saved', await w.ev("Nutcade.S.txs.some(t=>t.note==='txs unsaved') && Nutcade.S.txs.some(t=>t.note==='after sync')") and await w.bal() == 1193, await w.bal())
            check('sync: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= the duress PIN's wallet =======================
        async def duress():
            w = await funded(b, 2000); await set_pin(w)
            await settings(w); await w.click('[data-act=duressOpen]'); await w.wait(250)
            await pad(w, PIN); await w.wait(800); await pad(w, DPIN); await w.wait(300); await pad(w, DPIN); await w.until("!!document.querySelector('#duressAmt')", 8000)
            await w.fill('#duressAmt', '300'); await w.click('[data-act=duressMake]'); await w.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000)
            await w.ev("Nutcade.closeSheet()"); await chain(w); await w.home(); await w.wait(300)
            # the real wallet's notice, for comparison
            await w.ev("window.__quota=true"); await w.ev("document.querySelector('[data-act=hideToggle]').click()"); await chain(w); await w.wait(400)
            real_html = await w.ev("document.querySelector('.screen [data-storage=full]').outerHTML")
            real_keys = await w.ev("Object.keys(localStorage).sort()")
            await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(600); await chain(w)
            await w.pg.reload(); await w.wait(800); await unlock(w, DPIN); await w.home(); await w.wait(1500)
            dbal = await w.bal()
            check('duress: the duress PIN opens its own wallet', await w.ev("Nutcade.vault.decoy") and 250 <= dbal <= 300, dbal)
            await w.ev("window.__toasts=[]; window.__quota=true"); await w.ev("document.querySelector('[data-act=hideToggle]').click()"); await chain(w); await w.wait(400)
            check('duress: a failed write in its wallet shows the same notice and one toast', await w.ev(FULL) and await w.ev(SAVE_TOASTS) == 1 and 'vault' in (await w.ev(HEALTH))['keys'])
            check('duress: the notice is exactly the one of the real wallet (nothing tells them apart)', await w.ev("document.querySelector('.screen [data-storage=full]').outerHTML") == real_html)
            check('duress: storage names are the same as in the real wallet', await w.ev("Object.keys(localStorage).sort()") == real_keys)
            await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]'); await w.wait(600); await chain(w)
            check('duress: Try again clears it', not await w.ev(FULL))
            check('duress: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= 70% / 90% =======================
        async def usage():
            w = await funded(b, 500)
            await settings(w); row = await w.ev("[...document.querySelectorAll('#set-backup .row')].map(r=>r.innerText).find(t=>/Storage used by NUTCADE/.test(t))||''")
            check('usage: Settings, Backup shows NUTCADE\'s storage use against 5 MB', bool(re.search(r'\d+\.\d MB / 5 MB \(\d+%\)', row)), row)
            await w.home()
            check('usage: no warning on a small wallet', not await w.ev("!!document.querySelector('[data-storage]')") and await w.ev("Nutcade.storage.pct()") < 10, await w.ev("Nutcade.storage.pct()"))
            await w.ev("localStorage.setItem('nutcade:scores:fill', 'x'.repeat(1900000))"); await w.pg.reload(); await w.wait(2500); await w.home()
            pct = await w.ev("Nutcade.storage.pct()")
            check('usage: about 72% used gives the soft warning (not red)', 70 <= pct < 90 and await w.ev("!!document.querySelector('.screen [data-storage=\"70\"]') && !document.querySelector('.screen [data-storage=\"70\"]').classList.contains('red')"), pct)
            await w.ev("NutStore.set('scores:fill', 'x'.repeat(2420000))"); await w.wait(3800)   # (a write through NUTCADE's own storage layer)
            pct = await w.ev("Nutcade.storage.pct()")
            check('usage: measured again after writes (a few seconds later, not on each write): about 92% is red', pct >= 90 and await w.ev("!!document.querySelector('.screen [data-storage=\"90\"].red')"), pct)
            await settings(w); row = await w.ev("[...document.querySelectorAll('#set-backup .row')].map(r=>r.innerText).find(t=>/Storage used by NUTCADE/.test(t))||''")
            check('usage: the Settings line shows it too', f'({pct}%)' in row, row)
            await w.ev("localStorage.removeItem('nutcade:scores:fill')"); await w.pg.reload(); await w.wait(2500); await w.home()
            check('usage: back to small: no warning', not await w.ev("!!document.querySelector('[data-storage]')"))
            check('usage: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        # ======================= iPhone: Home Screen =======================
        async def iphone():
            w = await wallet(b, init=QUOTA, ua=IPHONE)
            check('iPhone: the welcome screen says to add NUTCADE to the Home Screen first', await w.ev("!!document.querySelector('.gate [data-home-hint] [data-act=homeSteps]')"))
            await w.create(); await w.add_mint(B); await w.home(); await w.wait(300)
            check('iPhone: no banner while the wallet holds no sats', not await w.ev("!!document.querySelector('.screen [data-home-hint]')"))
            await w.receive_ln(500); await w.home(); await w.wait(300)
            txt = await w.ev("(document.querySelector('.screen [data-home-hint]')||{}).innerText||''")
            check('iPhone: with sats, the banner "Add NUTCADE to your Home Screen, or Safari may delete this wallet"', 'Add NUTCADE to your Home Screen, or Safari may delete this wallet' in txt, txt)
            await w.click('.screen [data-home-hint] [data-act=homeSteps]'); await w.wait(300)
            st = await w.sheet_text()
            check('iPhone: Show me how opens the steps (Download backup in Safari, Share, Add to Home Screen, the new icon starts empty, Import backup there; the 12 words as the fallback, with what they may miss)', 'Add to Home Screen' in st and 'Share' in st and 'Download backup' in st and 'Import backup' in st and st.index('Download backup') < st.index('Share') and 'No backup file? Tap Restore from recovery phrase' in st and 'tokens still waiting to be claimed' in st and 'locked ecash' in st and 'payments still in progress' in st and 'your sats come with them' not in st and await w.ev("!!document.querySelector('#layer a[href*=\"get-nutcade-add-it-to-your-home-screen\"]')"), st[:200])
            await w.ev("Nutcade.closeSheet()")
            await settings(w)
            check('iPhone: Settings, Backup has the same steps button', await w.ev("!!document.querySelector('#set-backup [data-act=homeSteps]')"))
            # five languages: banner, steps, the storage notice and the Settings line, with nothing left in English
            await w.home(); await w.ev("window.__quota=true"); await w.ev("document.querySelector('[data-act=hideToggle]').click()"); await w.wait(300)
            english = ['Home Screen', "can't save your wallet", 'only on this screen', 'Find lost ecash in Settings', 'Storage used by NUTCADE', 'Show me how', 'Not today', 'Steps for every device', 'Open NUTCADE in Safari', 'Download backup', 'Import backup', 'No backup file', 'payments still in progress']
            for lang in ['es', 'pt', 'de', 'fr']:
                await set_lang(w, lang); await w.home(); await w.wait(300)
                shown = await w.ev("document.querySelector('.screen').innerText")
                await w.click('.screen [data-home-hint] [data-act=homeSteps]'); await w.wait(300); shown += await w.sheet_text(); await w.ev("Nutcade.closeSheet()")
                await settings(w); shown += await w.ev("document.querySelector('#set-backup').innerText")
                left = [e for e in english if e in shown]
                check(f'iPhone: {lang}: the banner, the steps, the storage notice and the storage line are translated', not left, left)
            await set_lang(w, 'en'); await w.ev("window.__quota=false"); await w.click('[data-storage=full] [data-act=saveRetry]') if await w.ev(FULL) else None; await w.wait(400); await w.home()
            await w.click('.screen [data-home-hint] [data-act=homeLater]'); await w.wait(300)
            check('iPhone: Not today hides it, kept as a setting of this device (plain prefs)', not await w.ev("!!document.querySelector('.screen [data-home-hint]')") and bool(await w.ev("JSON.parse(localStorage.getItem('nutcade:prefs')).homeLater")))
            await w.pg.reload(); await w.wait(1200); await w.home()
            check('iPhone: ... also after a reload, the same day', not await w.ev("!!document.querySelector('.screen [data-home-hint]')"))
            await w.ev("const p=JSON.parse(localStorage.getItem('nutcade:prefs')); p.homeLater='Mon Jan 01 2001'; localStorage.setItem('nutcade:prefs', JSON.stringify(p))"); await w.pg.reload(); await w.wait(1200); await w.home()
            check('iPhone: ... and back on another day', await w.ev("!!document.querySelector('.screen [data-home-hint]')"))
            check('iPhone: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
            # installed (navigator.standalone) and not an iPhone: no banner
            w = await wallet(b, init=QUOTA + "\nObject.defineProperty(Navigator.prototype, 'standalone', { get: () => true });", ua=IPHONE)
            check('iPhone from the Home Screen (navigator.standalone): no hint on the welcome screen', not await w.ev("!!document.querySelector('[data-home-hint]')"))
            await w.create(); await w.add_mint(B); await w.receive_ln(300); await w.home(); await w.wait(300)
            check('iPhone from the Home Screen: no banner with sats either', not await w.ev("!!document.querySelector('[data-home-hint]')"))
            await w.pg.context.close()
            w = await funded(b, 300)
            check('not an iPhone: no banner', not await w.ev("!!document.querySelector('[data-home-hint]')"))
            await w.pg.context.close()

        await section('plain', plain)
        await section('swap', swap)
        await section('vault', vault)
        await section('direct', direct)
        await section('sync', sync)
        await section('duress', duress)
        await section('usage', usage)
        await section('iphone', iphone)
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
