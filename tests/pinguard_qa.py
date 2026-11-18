"""PIN guard: with a PIN, every step that hands over the whole wallet asks for it first (the spending limit protects an
unlocked phone only if nothing goes around it). Uses the local mint 3339 (no fee) and mock_nostr.py.

The grid: every guarded step (show the recovery phrase, download the backup file, show the backup text, import a
backup, restore from 12 words, connect an app, reset, export a mint's ecash, make a new phrase, change the spending
limit) x no PIN / right PIN / wrong PIN / lockout / inside the duress PIN's wallet / cancel. Then: a thief's phrase
typed into Restore (and the other forms, reached without the pad) never moves a sat without the PIN; the start screen
and Forgot PIN are unchanged; the wording in all five languages."""
import asyncio, json, os, re, time
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet, pad, set_pin, unlock, settings, PIN, DPIN, LANGS

WRONG = '999999'
THIEF = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'   # (a valid phrase nobody here holds)
GUARD = {   # the step: (how it starts, what shows once it went ahead, the pad's title and line)
    'seed': ('#app [data-act=seedShow]', "document.querySelectorAll('#layer .words li').length===12", 'Recovery phrase', 'Enter your PIN to see your 12 words.'),
    'backup': ('#app [data-act=backupDownload]', "(window.__dl||[]).some(n=>/^nutcade-backup-/.test(n))", 'Backup file', 'Enter your PIN to get your backup file.'),
    'backuptext': ('backup', "/\"seed\"/.test((document.querySelector('#layer .code')||{}).innerText||'')", 'Backup file', 'Enter your PIN to get your backup file.'),
    'import': ('#app [data-act=restore]', "!!document.querySelector('#restoreIn')", 'Import backup', 'Enter your PIN to import a backup.'),
    'restore': ('#app [data-act=seedRestore]', "!!document.querySelector('#phraseIn') && !!document.querySelector('[data-act=doRestorePhrase]')", 'Restore wallet', 'Enter your PIN to restore a wallet from 12 words.'),
    'nwc': ('#app [data-act=nwcNew]', "!!document.querySelector('#nwcName')", 'Connect an app', 'Enter your PIN to connect an app to this wallet.'),
    'reset': ('#app [data-act=resetAsk]', "!!document.querySelector('[data-act=doReset]')", 'Reset wallet', 'Enter your PIN to reset this wallet.'),
    'export': ('exportToken', "/cashu[AB]/.test((document.querySelector('#layer .code')||{}).innerText||'')", 'Export ecash', 'Enter your PIN to export your ecash.'),
    'newseed': ('newSeedAsk', "!!document.querySelector('[data-act=doNewSeed]')", 'New recovery phrase', 'Enter your PIN to make a new recovery phrase.'),
}
# (downloads are recorded, not saved; the steps with no button on screen today are started the way a button would)
DL_JS = "window.__dl=[]; if(!window.__dlHook){window.__dlHook=1; document.addEventListener('click', e=>{ const a=e.target && e.target.closest && e.target.closest('a[download]'); if(a){ window.__dl.push(a.download); e.preventDefault(); } }, true)}"
PAD = "!!document.querySelector('#layer [data-pinpad=guard]')"
PINERR = "(document.querySelector('#pinErr')||{}).innerText||''"
FAILS = "JSON.parse(localStorage.getItem('nutcade:pinfails')||'{\"n\":0}').n"


def act_js(name):
    return f"(()=>{{const b=document.createElement('button'); b.dataset.act={json.dumps(name)}; document.querySelector('#app').appendChild(b); b.click(); b.remove()}})()"


async def start(w, k):
    """starts step k from Settings, as a person would"""
    await settings(w); await w.ev(DL_JS); await w.ev("localStorage.removeItem('nutcade:pinfails')")
    sel = GUARD[k][0]
    if sel.startswith('#'): await w.click(sel)
    else: await w.ev(act_js(sel))
    await w.wait(350)


async def enter(w, pin):
    """types a PIN on the guard's pad; returns once the step went ahead or the pad answered"""
    await pad(w, pin, '#layer [data-pinpad=guard]')
    await w.until(f"!document.querySelector('#layer [data-pinpad=guard]') || /wrong|Wait/i.test({PINERR})", 20000); await w.wait(300)


async def shown(w, k): return bool(await w.ev(GUARD[k][1]))


async def section(name, fn):
    only = [x for x in os.environ.get('PG_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e:
        check(f'{name}: ran to the end', False, repr(e)[:300])


async def funded(b, lang='en', amount=2000, pin=PIN):
    w = await wallet(b, lang=lang); words = await w.create(); await w.add_mint(B); await w.use(B); await w.receive_ln(amount)
    if pin: await set_pin(w, pin)
    return w, words


async def make_duress(w, amount=300):
    await settings(w); await w.click('[data-act=duressOpen]'); await w.wait(250); await pad(w, PIN); await w.wait(900); await pad(w, DPIN); await w.wait(300); await pad(w, DPIN)
    await w.until("!!document.querySelector('#duressAmt')", 8000); await w.fill('#duressAmt', str(amount)); await w.click('[data-act=duressMake]')
    await w.until("/READY/.test(document.body.innerText)", 30000); await w.ev("Nutcade.closeSheet()")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ======================= no PIN: nothing changes =======================
        async def no_pin():
            n, _ = await funded(b, pin=None)
            for k in GUARD:
                await start(n, k)
                check(f'no PIN, {k}: goes ahead at once, no PIN pad', await shown(n, k) and not await n.ev(PAD), await n.sheet_text())
                await n.ev("Nutcade.closeSheet()")
            # the start screen of a new wallet: Restore from 12 words, no pad
            g = await wallet(b); await g.pg.check('#ack'); await g.click('[data-act=gateRestore]'); await g.wait(300)
            check('start screen: Restore from recovery phrase opens its form, no PIN pad', await g.ev("!!document.querySelector('#phraseIn')") and not await g.ev(PAD))
            await g.pg.context.close(); await n.pg.context.close()
        await section('nopin', no_pin)

        # ======================= with a PIN: right / wrong / lockout / cancel, for every step =======================
        async def grid():
            w, words = await funded(b)
            texts = {}
            for k, (_, _, title, line) in GUARD.items():
                # cancel: the pad closes, nothing went ahead
                await start(w, k)
                pad_on = await w.ev(PAD); txt = await w.ev("(document.querySelector('#layer .sheet')||{}).innerText||''"); texts[k] = await w.ev("document.querySelector('#layer .sheet').innerHTML")
                check(f'PIN, {k}: asks for the PIN first, nothing shown yet ("{line}")', pad_on and not await shown(w, k) and title in txt and line in txt and 'ENTER PIN' in txt, txt[:200])
                check(f'PIN, {k}: no Face ID button on the pad (as for the spending limit)', not await w.ev("!!document.querySelector('#layer [data-act=bioUnlock]')"))
                await w.click('#layer [data-act=close]'); await w.wait(250)
                check(f'PIN, {k}, cancel: closes, nothing went ahead', not await w.ev("!!document.querySelector('#layer .sheet')") and not await shown(w, k))
                # wrong PIN: refused, counted like any wrong PIN
                await start(w, k); await enter(w, WRONG)
                e = await w.ev(PINERR)
                check(f'PIN, {k}, wrong PIN: "That PIN is wrong.", nothing shown, the try is counted', 'That PIN is wrong.' in e and not await shown(w, k) and await w.ev(FAILS) == 1, (e, await w.ev(FAILS)))
                await w.ev("Nutcade.closeSheet()")
                # lockout: the right PIN waits like everywhere else
                await start(w, k); await w.ev("localStorage.setItem('nutcade:pinfails', JSON.stringify({n:5, until:Date.now()+60000}))"); await enter(w, PIN)
                e = await w.ev(PINERR)
                check(f'PIN, {k}, during the wait after wrong tries: even the right PIN waits, nothing shown', re.search(r'Wait \d+s', e) and not await shown(w, k), e)
                await w.ev("Nutcade.closeSheet(); localStorage.removeItem('nutcade:pinfails')")
                # right PIN: goes ahead, the count is cleared
                await start(w, k); await w.ev("localStorage.setItem('nutcade:pinfails', JSON.stringify({n:2, until:0}))"); await enter(w, PIN)
                check(f'PIN, {k}, right PIN: goes ahead', await shown(w, k), await w.sheet_text())
                check(f'PIN, {k}, right PIN: the wrong-try count is cleared, as on unlock', await w.ev(FAILS) == 0)
                await w.ev("Nutcade.closeSheet()")
            # what went ahead is this wallet's
            await start(w, 'seed'); await enter(w, PIN)
            check('PIN, seed: shows this wallet\'s 12 words', await w.ev("[...document.querySelectorAll('#layer .words li')].map(l=>l.lastChild.textContent).join(' ')") == words)
            await w.ev("Nutcade.closeSheet()")
            # five wrong tries in a row: the wait starts, and it is the same count the lock screen uses
            await start(w, 'seed')
            for _ in range(5): await enter(w, WRONG)
            await enter(w, PIN); e = await w.ev(PINERR)
            check('PIN: five wrong tries on the guard start the wait (the right PIN then waits too)', re.search(r'Wait \d+s', e) and not await shown(w, 'seed'), e)
            await w.pg.reload(); await w.wait(800)
            lk = await w.ev("document.body.innerText")
            check('PIN: the lock screen counts the same tries (it says to wait)', 'Too many wrong tries' in lk, lk[:120])
            await w.ev("localStorage.removeItem('nutcade:pinfails')"); await w.pg.reload(); await w.wait(700); await unlock(w)
            # a pad left open and closed can't be finished later; the keyboard works on the pad like everywhere
            await start(w, 'seed')
            for ch in PIN: await w.pg.keyboard.press(ch)
            await w.pg.keyboard.press('Enter'); await w.until("document.querySelectorAll('#layer .words li').length===12", 15000)
            check('PIN, seed: typing the PIN on a keyboard works too', await shown(w, 'seed'))
            await w.ev("Nutcade.closeSheet()")
            w.texts = texts
            return w, words
        grid_w = {}
        async def grid_run():
            w, words = await grid(); grid_w['w'] = w; grid_w['words'] = words
        await section('grid', grid_run)

        # ======================= the duress PIN's wallet: its own PIN, the same prompts =======================
        async def duress():
            d, real_words = await funded(b)
            texts = {}
            for k in GUARD:
                await start(d, k); texts[k] = await d.ev("document.querySelector('#layer .sheet').innerHTML"); await d.ev("Nutcade.closeSheet()")
            # timing of a wrong PIN in the real wallet
            async def wrong_time(w):
                ts = []
                for _ in range(3):
                    await start(w, 'seed'); t0 = time.time(); await enter(w, WRONG); ts.append(time.time() - t0); await w.ev("Nutcade.closeSheet()")
                return sorted(ts)[1]
            t_real = await wrong_time(d)
            await make_duress(d)
            await d.ev("localStorage.setItem('nutcade:pinchg','[]')"); await d.pg.reload(); await d.wait(700); await unlock(d, DPIN)
            await d.until("Object.values(Nutcade.S.proofs).flat().length>0", 30000)
            decoy_words = await d.ev("Nutcade.S.seed.mnemonic")
            check('duress: its wallet is open (its own 12 words)', decoy_words and decoy_words != real_words)
            for k in GUARD:
                await start(d, k)
                same = await d.ev("document.querySelector('#layer .sheet').innerHTML") == texts[k]
                check(f'duress, {k}: asks for the PIN with exactly the same screen as the real wallet', same and await d.ev(PAD) and not await shown(d, k))
                await enter(d, PIN); e = await d.ev(PINERR)
                check(f'duress, {k}: the real wallet\'s PIN is just "That PIN is wrong." (nothing says there is another wallet)', 'That PIN is wrong.' in e and not await shown(d, k) and await d.ev(FAILS) == 1, e)
                await d.ev("Nutcade.closeSheet()"); await start(d, k); await enter(d, WRONG); e2 = await d.ev(PINERR)
                check(f'duress, {k}: a wrong PIN reads the same', e2 == e, (e, e2))
                await d.ev("Nutcade.closeSheet()"); await start(d, k)
                await d.ev("localStorage.setItem('nutcade:pinfails', JSON.stringify({n:5, until:Date.now()+60000}))"); await enter(d, DPIN)
                check(f'duress, {k}: the wait after wrong tries applies the same', re.search(r'Wait \d+s', await d.ev(PINERR)) and not await shown(d, k))
                await d.ev("Nutcade.closeSheet()"); await start(d, k); await enter(d, DPIN)
                check(f'duress, {k}: its own PIN lets it go ahead', await shown(d, k), await d.sheet_text())
                await d.ev("Nutcade.closeSheet()")
            await start(d, 'seed'); await enter(d, DPIN)
            check("duress, seed: shows the duress wallet's own words, never the real ones", await d.ev("[...document.querySelectorAll('#layer .words li')].map(l=>l.lastChild.textContent).join(' ')") == decoy_words)
            await d.ev("Nutcade.closeSheet()")
            await start(d, 'backuptext'); await enter(d, DPIN)
            bt = await d.ev("document.querySelector('#layer .code').innerText")
            check("duress, backup: the file holds the duress wallet's phrase and nothing of the real one", decoy_words in bt and real_words not in bt)
            await d.ev("Nutcade.closeSheet()")
            t_dec = await wrong_time(d)
            check(f'duress: a wrong PIN takes about as long in either wallet ({t_real:.2f}s / {t_dec:.2f}s)', t_dec < 3 * t_real + 0.5 and t_real < 3 * t_dec + 0.5, (t_real, t_dec))
            # Reset inside the duress wallet: its own PIN, then only that wallet starts over
            await start(d, 'reset'); await enter(d, DPIN); await d.fill('#confirmWord', 'RESET'); await d.click('[data-act=doReset]'); await d.wait(2500)
            await unlock(d, PIN)
            check('duress, reset with its PIN: the real wallet is all there', await d.ev("Nutcade.S.seed.mnemonic") == real_words and await d.bal() >= 1600, await d.bal())
            await d.pg.context.close()
        await section('duress', duress)

        # ======================= a thief's phrase (and the other forms) never move a sat without the PIN =======================
        async def thief():
            w, words = await funded(b, amount=3000)
            snap = "JSON.stringify([Nutcade.S.seed.mnemonic, Object.values(Nutcade.S.proofs).flat().map(p=>p.secret).sort(), (Nutcade.S.nwc||[]).length])"
            s0 = await w.ev(snap); hits = []
            w.pg.on('request', lambda r: hits.append(r.url) if re.search(r'/v1/(swap|restore|melt)', r.url) else None)
            # through the screens: cancel, wrong PIN
            await start(w, 'restore'); await w.click('#layer [data-act=close]'); await w.wait(200)
            await start(w, 'restore'); await enter(w, WRONG); await w.ev("Nutcade.closeSheet()")
            check('thief: Restore without the PIN (cancel, wrong PIN) changes nothing', await w.ev(snap) == s0)
            # the forms' buttons, reached without the pad (a form put on screen by hand): each closes and does nothing
            forms = {
                'doRestorePhrase': f"<textarea id=phraseIn>{THIEF}</textarea><input type=checkbox data-rmint={json.dumps(B)} checked><textarea id=rmExtra></textarea><div id=restoreLog></div>",
                'doRestore': "<textarea id=restoreIn>" + json.dumps({'app': 'nutcade', 'v': 2, 'seed': THIEF, 'mints': [], 'proofs': {}, 'txs': []}).replace('<', '') + "</textarea>",
                'nwcCreate': "<input id=nwcName value=Thief><input id=amtIn value=''>",
                'doNewSeed': "<input id=confirmWord value=NEW>",
                'doReset': "<input id=confirmWord value=RESET>",
            }
            for act, html in forms.items():
                await w.ev(f"Nutcade.openSheet('Form', {json.dumps(html + '<button data-act=' + act + '>Go</button><div id=sheetErr></div>')})")
                await w.click(f'#layer [data-act={act}]'); await w.wait(1500)
                check(f'thief: {act} on a form not opened through the PIN does nothing and closes it', await w.ev(snap) == s0 and not await w.ev("!!document.querySelector('#layer .sheet')") and await w.ev("!!localStorage.getItem('nutcade:vault') && Nutcade.vault.open"), await w.ev(snap))
            # a pass is for its own form only: the PIN for Connect an app doesn't restore, and a closed form's pass is gone
            await start(w, 'nwc'); await enter(w, PIN)
            await w.ev(f"document.querySelector('#layer .sheet-body').insertAdjacentHTML('beforeend', {json.dumps(forms['doRestorePhrase'] + '<button data-act=doRestorePhrase id=sneak>Go</button>')})")
            await w.click('#sneak'); await w.wait(1500)
            check('thief: the PIN entered for Connect an app does not let a restore through', await w.ev(snap) == s0)
            await start(w, 'restore'); await enter(w, PIN); await w.ev("Nutcade.closeSheet()")
            await w.ev(f"Nutcade.openSheet('Form', {json.dumps(forms['doRestorePhrase'] + '<button data-act=doRestorePhrase>Go</button><div id=sheetErr></div>')})")
            await w.click('#layer [data-act=doRestorePhrase]'); await w.wait(1500)
            check('thief: once the Restore form that the PIN opened is closed, its pass is gone', await w.ev(snap) == s0)
            check('thief: no request moved or looked for coins in all of that (no swap, melt or restore)', not hits, hits[:3])
            # the reset form, without the PIN: the wallet is still there after a reload
            await w.pg.reload(); await w.wait(700); await unlock(w)
            check('thief: after all that, the same phrase and the same coins', await w.ev(snap) == s0)
            # with the PIN (the owner): the restore goes through, and the sats move under the typed phrase
            b0 = await w.bal()
            await start(w, 'restore'); await enter(w, PIN)
            await w.fill('#phraseIn', THIEF)
            await w.ev(f"document.querySelectorAll('[data-rmint]').forEach(i=>i.checked = i.dataset.rmint==={json.dumps(B)})")
            await w.click('[data-act=doRestorePhrase]'); await w.until("/CONTINUE|SCAN COMPLETE/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 60000)
            check('owner, restore with the PIN: the typed phrase is the wallet now, and the sats moved under it', await w.ev("Nutcade.S.seed.mnemonic") == THIEF and await w.bal() >= b0 - 10 and await w.bal() > 0, (await w.bal(), b0))
            check('owner, restore with the PIN: the spending limit and the PIN are still on', await w.ev("Nutcade.vault.on"))
            await w.pg.context.close()
        await section('thief', thief)

        # ======================= the spending limit was already guarded: still so, also in the duress wallet =======================
        async def limit():
            w, _ = await funded(b, amount=500)
            async def save(day, pin):
                await settings(w); await w.click('[data-act=limOpen]'); await w.until("!!document.querySelector('#limDay')", 5000)
                await w.ev(f"(()=>{{const e=document.querySelector('#limDay'); e.value={json.dumps(day)}; e.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")
                await w.click('[data-act=limSave]'); await w.wait(400)
                asked = await w.ev("!!document.querySelector('#layer [data-pinpad=limitSave]')")
                if pin: await pad(w, pin, '#layer [data-pinpad]'); await w.until(f"!document.querySelector('#layer [data-pinpad]') || /wrong|Wait/i.test({PINERR})", 20000); await w.wait(300)
                e = await w.ev(PINERR); await w.ev("Nutcade.closeSheet()"); return asked, e
            a, e = await save('1000', PIN)
            check('limit: setting it asks for the PIN, and the right PIN saves it', a and await w.ev("Nutcade.S.limits && Nutcade.S.limits.day===1000"), e)
            await w.ev("localStorage.removeItem('nutcade:pinfails')")
            a, e = await save('', WRONG)
            check('limit: turning it off with a wrong PIN is refused, the limit stays', a and 'wrong' in e.lower() and await w.ev("Nutcade.S.limits.day===1000"), e)
            await w.ev("localStorage.removeItem('nutcade:pinfails')")
            a, _ = await save('', None)
            check('limit: cancelling the PIN leaves the limit on', a and await w.ev("Nutcade.S.limits.day===1000"))
            await make_duress(w, 0); await w.pg.reload(); await w.wait(700); await unlock(w, DPIN)
            a, e = await save('700', PIN)
            check("limit, duress wallet: the real wallet's PIN is wrong there", a and 'wrong' in e.lower() and not await w.ev("Nutcade.S.limits && Nutcade.S.limits.day===700"), e)
            await w.ev("localStorage.removeItem('nutcade:pinfails')")
            a, e = await save('700', DPIN)
            check("limit, duress wallet: its own PIN changes its own limit", a and await w.ev("Nutcade.S.limits && Nutcade.S.limits.day===700"), e)
            await w.pg.reload(); await w.wait(700); await unlock(w, PIN)
            check("limit, duress wallet: the real wallet's limit is untouched", await w.ev("Nutcade.S.limits.day===1000"))
            await w.pg.context.close()
        await section('limit', limit)

        # ======================= Forgot PIN on the lock screen still resets without the PIN =======================
        async def forgot():
            w, _ = await funded(b, amount=200)
            await w.pg.reload(); await w.wait(700)
            await w.click('[data-act=forgotPin]'); await w.wait(200); await w.fill('#confirmWord', 'RESET'); await w.click('[data-act=doReset]'); await w.wait(2000)
            check('Forgot PIN: resets from the lock screen with no PIN (unchanged), back to the start screen', await w.ev("!localStorage.getItem('nutcade:vault') && !!document.querySelector('[data-act=gateCreate]')"))
            await w.pg.context.close()
        await section('forgot', forgot)

        # ======================= the wording, in all five languages =======================
        async def lang():
            for lg in LANGS:
                w, _ = await funded(b, lang=lg, amount=100)
                miss = []
                for k, (_, _, title, line) in GUARD.items():
                    await start(w, k); txt = await w.ev("document.querySelector('#layer .sheet').innerText")
                    if lg != 'en' and (line in txt or title in txt or 'ENTER PIN' in txt): miss.append((k, txt[:80]))
                    await enter(w, WRONG); e = await w.ev(PINERR)
                    if lg != 'en' and 'That PIN is wrong.' in e: miss.append((k, e))
                    await w.ev("Nutcade.closeSheet(); localStorage.removeItem('nutcade:pinfails')")
                m = await w.ev("[...(window.__i18nMiss||[])].filter(s=>/PIN|backup|phrase|wallet|ecash|app/i.test(s))")
                check(f'{lg}: every guard pad is in the language (title, line, wrong PIN), nothing missing', not miss and not m, (miss[:3], m[:5]))
                await w.pg.context.close()
        await section('lang', lang)

        if grid_w.get('w'): await grid_w['w'].pg.context.close()
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', sum(1 for r in results if not r[1]), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
