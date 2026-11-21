"""Better backups (1.23.0): a password on the backup file, the file also carrying contacts, settings, trophies and arcade
progress, and "Back up with my phone" (a passkey's PRF output locks the 12 words; the locked copy is kept on Nostr relays).
Uses the local mint 3339 (no fee), mock_nostr.py, and Chromium's virtual WebAuthn authenticator (with PRF) over CDP.

Password: create / restore / wrong password / plain old file / never stored. Extras: contacts, settings, trophies, arcade
scores come back, money is never overwritten. Duress: a backup of the real wallet carries no trace of the duress PIN's wallet.
Phone: create / restore / wrong passkey / no PRF support (hidden, and a passkey without PRF) / relay down / two devices /
PIN + duress / reset deletes the backup; the 12 words never appear in a toast, a log or on screen.
S_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, socket, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet, set_pin, unlock, pad, settings, set_lang, PIN, DPIN, LANGS

J = json.dumps
NOSTR = 'http://127.0.0.1:3350'
AUTH = {'protocol': 'ctap2', 'ctap2Version': 'ctap2_1', 'transport': 'internal', 'hasResidentKey': True, 'hasUserVerification': True, 'isUserVerified': True, 'automaticPresenceSimulation': True, 'hasPrf': True}
# NUTCADE's default relays (relay.damus.io, nos.lol, relay.primal.net) are pointed at the stand-in relay, so tests never reach a
# public relay; window.__relayDown sends every relay to a closed port; window.__ws lists the relays each page opened
RELAY_SHIM = """(() => { const W = window.WebSocket; if (!W || W.__shim) return; window.__ws = [];
  const MAP = { 'wss://relay.damus.io': 'ws://127.0.0.1:3350/relay', 'wss://nos.lol': 'ws://127.0.0.1:3350/relay', 'wss://relay.primal.net': 'ws://127.0.0.1:3350/relay' };
  const S = function (u, p) { u = String(u); window.__ws.push(u); const k = u.replace(/\\/+$/, ''); let t = MAP[k] || u;
    if (window.__relayDown && (MAP[k] || /\\/relay$/.test(k))) t = 'ws://127.0.0.1:3359/relay';
    if (window.__blackhole && (k === 'wss://nos.lol' || k === 'wss://relay.primal.net')) t = 'ws://127.0.0.1:3357/relay';   // (a relay that never answers)
    return p === undefined ? new W(t) : new W(t, p); };
  S.prototype = W.prototype; S.__shim = 1; for (const k of ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED']) S[k] = W[k]; window.WebSocket = S; })();
"""
WATCH = RELAY_SHIM + """window.__toasts = []; window.__logs = [];
(() => { for (const k of ['log', 'info', 'warn', 'error', 'debug']) { const o = console[k]; console[k] = function (...a) { try { window.__logs.push(a.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' ')); } catch (e) {} return o.apply(this, a); }; } })();
document.addEventListener('DOMContentLoaded', () => { new MutationObserver(() => { const t = document.querySelector('#toast');
  if (t && !t.hidden && t.textContent && window.__toasts[window.__toasts.length - 1] !== t.textContent) window.__toasts.push(t.textContent); })
  .observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden'] }); });"""
# a browser without PRF, on any Chromium: no capability list (older Chromium has none) and no platform authenticator either
NO_PRF_CAP = "(() => { if (window.PublicKeyCredential) { try { delete PublicKeyCredential.getClientCapabilities; } catch (e) {} PublicKeyCredential.getClientCapabilities = undefined; PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable = () => Promise.resolve(false); } })();"
PB = 'nutcade-phone-backup'


def state(): return json.loads(urllib.request.urlopen(NOSTR + '/test/state').read())
def pb_events(): return [e for e in state()['events'] if e['kind'] == 30078 and any(t[0] == 'd' and t[1] == PB for t in e['tags'])]


async def section(name, fn):
    only = [x for x in os.environ.get('S_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def authn(w, prf=True):
    cdp = await w.pg.context.new_cdp_session(w.pg); await cdp.send('WebAuthn.enable')
    a = await cdp.send('WebAuthn.addVirtualAuthenticator', {'options': dict(AUTH, hasPrf=prf)})
    await w.ev("Nutcade.bk.cap()")
    return cdp, a['authenticatorId']


async def forgot(w, cdp, aid):
    """the passkey is forgotten where the browser can be told (signalUnknownCredential); elsewhere it simply stays"""
    if await w.ev("!!(window.PublicKeyCredential && PublicKeyCredential.signalUnknownCredential)"): return await creds(cdp, aid) == 0
    return True


async def creds(cdp, aid): return len((await cdp.send('WebAuthn.getCredentials', {'authenticatorId': aid}))['credentials'])


async def funded(b, amt=1000, init=WATCH, **kw):
    w = await wallet(b, init=init, **kw)
    words = await w.create(); await w.add_mint(B); await w.receive_ln(amt, 'start'); await w.home(); await w.wait(300)
    return w, words


async def fresh(w):
    """the same browser tab as a new phone: storage wiped (the passkeys stay, like a synced passkey), back at the start screen"""
    await w.ev("localStorage.clear()")
    await w.ev("localStorage.setItem('nutcade:prefs', JSON.stringify({sound:false,music:false,crt:true,lang:'en',relays:['ws://127.0.0.1:3350/relay'],npcHost:'http://127.0.0.1:3350'}))")
    await w.pg.reload(); await w.wait(900); await w.ev("Nutcade.bk.cap()"); await w.ev("Nutcade.render()"); await w.wait(200)


async def guard_if(w, pin):
    if await w.until("!!document.querySelector('#layer [data-pinpad=guard]')", 1500):
        await pad(w, pin, '#layer [data-pinpad=guard]'); await w.until("!document.querySelector('#layer [data-pinpad=guard]') || /wrong|Wait/i.test((document.querySelector('#pinErr')||{}).innerText||'')", 20000); await w.wait(300)


async def phone_backup(w, pin=None):
    """Settings -> Back up with my phone -> the button; returns (sheet text, error)"""
    await settings(w); await w.click('[data-act=phoneOpen]'); await w.wait(250)
    if pin: await guard_if(w, pin)
    await w.until("!!document.querySelector('[data-act=phoneGo]')", 5000)
    await w.click('[data-act=phoneGo]')
    await w.until("!document.querySelector('[data-act=phoneGo]') || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 30000); await w.wait(300)
    return await w.sheet_text(), await w.err()


PB_DONE = "!!document.querySelector('#phraseField .notice') || (window.__toasts||[]).some(t=>/Nothing was changed|available|wasn't found/.test(t))"


async def gate_phone(w):
    """the start screen's Restore with my phone; returns the sheet text or the red toast (waits for the real outcome)"""
    await w.gate_step('gatePhone', PB_DONE, tick='#ack', ms=60000)
    await w.until(PB_DONE, 60000); await w.wait(800)
    return await w.sheet_text() if await w.ev("!!document.querySelector('#phraseField')") else ' | '.join(await w.ev("window.__toasts"))


async def restore_now(w):
    await w.click('[data-act=doRestorePhrase]'); await w.until("!document.querySelector('[data-act=doRestorePhrase]')", 60000); await w.wait(600)


async def leave_gate(w):
    """after a restore from the start screen: past PLAYER 1 READY, to the wallet"""
    await w.ev("Nutcade.closeSheet()")
    if await w.until("!!document.querySelector('[data-act=gateStart]')", 4000): await w.gate_step('gateStart', "!!document.querySelector('.tabbar')")
    await w.wait(300); await w.ev("Nutcade.closeSheet()")


def leaks(words, texts): return [t for t in texts if any(x in t for x in (words, ' '.join(words.split()[:4])))]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        # ======================= the backup file: a password, and contacts / settings / trophies / arcade =======================
        async def file_pw():
            w, words = await funded(b)
            await w.ev("Nutcade.S.contacts.push({id:'c1',name:'Alice',ln:'alice@example.com',nostr:'',created:1}); Nutcade.NutStoreSet && 0")
            await w.ev("window.NutStore.set('contacts', Nutcade.S.contacts); Nutcade.S.prefs.theme='amber'; Nutcade.S.prefs.currency='EUR'; Nutcade.S.prefs.hideAmounts=false")
            await w.ev("window.NutStore.set('trophies', {rat: 1700000000000}); Trophies.reload(); window.NutStore.set('plays', {n: 7, by: {swarm: 7}})")
            await w.ev("localStorage.setItem('nutcade:scores:swarm', JSON.stringify([{n:'ZED',s:4321,t:5}])); localStorage.setItem('nutcade:initials', JSON.stringify('ZED')); localStorage.setItem('nutcade:scores:daily', JSON.stringify([{d:'2026-11-01',o:900,g:'swarm'}]))")
            await settings(w)
            check('file: Protect with a password is offered and off by default', await w.ev("!!document.querySelector('#bkLock') && !document.querySelector('#bkLock').checked"))
            async with w.pg.expect_download() as dl: await w.click('[data-act=backupDownload]')
            plain = json.loads(open(await (await dl.value).path()).read())
            check('file: without a password the file is plain, as before (seed, coins, v 2)', plain.get('v') == 2 and plain.get('seed') == words and 'kind' not in plain)
            check('file: it also carries contacts, settings, trophies, plays and arcade scores', plain['contacts'][0]['name'] == 'Alice' and plain['settings'].get('theme') == 'amber' and plain['trophies'].get('rat') and plain['plays']['n'] == 7 and plain['arcade']['scores']['swarm'][0]['s'] == 4321 and plain['arcade']['initials'] == 'ZED', {k: plain.get(k) for k in ('settings', 'plays', 'arcade')})
            check('file: settings carry no keys or addresses (no npc, no backupFileAt, no lang)', not any(k in plain['settings'] for k in ('npc', 'npcName', 'backupFileAt', 'lang', 'mintBackupList')), list(plain['settings']))
            await w.ev("document.querySelector('#bkLock').click()"); await w.wait(100)
            await w.click('[data-act=backupDownload]'); await w.until("!!document.querySelector('#bkPw')", 5000)
            await w.fill('#bkPw', 'short'); await w.fill('#bkPw2', 'short'); await w.click('[data-act=bkLockGo]'); await w.wait(300)
            check('file: a password under 8 characters is refused', 'at least 8' in await w.err(), await w.err())
            await w.fill('#bkPw', 'correct horse'); await w.fill('#bkPw2', 'correct house'); await w.click('[data-act=bkLockGo]'); await w.wait(300)
            check("file: two passwords that don't match are refused", "don't match" in await w.err(), await w.err())
            await w.fill('#bkPw2', 'correct horse')
            async with w.pg.expect_download() as dl: await w.click('[data-act=bkLockGo]')
            txt = open(await (await dl.value).path()).read(); env = json.loads(txt)
            check('file: the locked file is a self-describing envelope (PBKDF2-SHA256 600000, AES-256-GCM, v 1)', env.get('app') == 'nutcade' and env.get('kind') == 'locked-backup' and env.get('v') == 1 and env['kdf'] == {'alg': 'PBKDF2-SHA256', 'iter': 600000, 'salt': env['kdf']['salt']} and env['cipher']['alg'] == 'AES-256-GCM', {k: env.get(k) for k in ('kind', 'v', 'kdf', 'cipher')})
            check('file: nothing readable inside (no words, no seed, no contact)', words.split()[0] not in txt.split('"ct"')[0] and '"seed"' not in txt and 'Alice' not in txt and words not in txt)
            await w.wait(300); await w.click('[data-act=backupDownload]'); await w.until("!!document.querySelector('#bkPw')", 5000); await w.fill('#bkPw', 'correct horse'); await w.fill('#bkPw2', 'correct horse')
            async with w.pg.expect_download() as dl: await w.click('[data-act=bkLockGo]')
            env2 = json.loads(open(await (await dl.value).path()).read())
            check('file: a new salt and iv every time', env2['kdf']['salt'] != env['kdf']['salt'] and env2['cipher']['iv'] != env['cipher']['iv'])
            stored = await w.ev("JSON.stringify(Object.assign({}, localStorage))") + ' '.join(await w.ev("window.__toasts")) + ' '.join(await w.ev("window.__logs"))
            check('file: the password is never stored, shown or logged', 'correct horse' not in stored)
            check('file: no toast or log carries the 12 words', not leaks(words, await w.ev("window.__toasts.concat(window.__logs)")))

            # a new wallet imports the locked file: the password is asked for; a wrong one changes nothing
            n = await wallet(b, init=WATCH); nwords = await n.create(); await n.add_mint(B); await n.home()
            await settings(n); await n.click('[data-act=restore]'); await n.until("!!document.querySelector('#restoreIn')", 5000)
            await n.pg.evaluate("v => { const t = document.querySelector('#restoreIn'); t.value = v; t.dispatchEvent(new Event('input', {bubbles: true})) }", txt)
            await n.click('[data-act=doRestore]'); await n.wait(400)
            check('import: a locked file is recognised and its password asked for', await n.ev("!!document.querySelector('#restorePw')") and await n.bal() == 0)
            await n.fill('#restorePw', 'wrong password'); await n.click('[data-act=doRestore]'); await n.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
            check('import: a wrong password is a clear error and nothing changed', 'Wrong password' in await n.err() and await n.bal() == 0 and await n.ev("Nutcade.S.seed.mnemonic") == nwords and await n.ev("Nutcade.S.contacts.length") == 0 and await n.ev("Nutcade.S.prefs.theme") != 'amber', await n.err())
            await n.fill('#restorePw', 'correct horse'); await n.click('[data-act=doRestore]'); await n.until("!document.querySelector('#restoreIn')", 60000); await n.wait(800)
            check('import: the right password restores the wallet (coins checked at the mint)', await n.bal() == 1000 and await n.ev("Nutcade.S.seed.mnemonic") == words, await n.bal())
            check('import: contacts, settings, trophies, plays and arcade scores came back', await n.ev("Nutcade.S.contacts.some(c=>c.name==='Alice') && Nutcade.S.prefs.theme==='amber' && Nutcade.S.prefs.currency==='EUR' && !!Trophies.got().rat && window.NutStore.get('plays').n===7 && JSON.parse(localStorage.getItem('nutcade:scores:swarm'))[0].s===4321 && JSON.parse(localStorage.getItem('nutcade:scores:daily')).length===1"))
            await n.until("(window.__toasts||[]).some(t=>/^Contacts: /.test(t))", 8000)
            check('import: it says how many contacts were added and skipped', any(t.startswith('Contacts: 1 added, 0 skipped') for t in await n.ev("window.__toasts")), await n.ev("window.__toasts"))
            check('import: the password field is emptied and the password is not stored', 'correct horse' not in await n.ev("JSON.stringify(Object.assign({}, localStorage))"))

            # a plain old file (1.22 and before: no extras) still imports; a wallet holding sats keeps them, its words and contacts
            x, xwords = await funded(b, 500)
            await x.ev("Nutcade.S.contacts.push({id:'c9',name:'Bob',ln:'bob@example.com',nostr:'',created:1}); window.NutStore.set('contacts', Nutcade.S.contacts)")
            old = await w.ev("JSON.stringify({ app: 'nutcade', v: 2, seed: Nutcade.S.seed.mnemonic, counters: Nutcade.S.counters, mints: Nutcade.S.mints, proofs: Nutcade.S.proofs, pending: Nutcade.S.pending, txs: Nutcade.S.txs })")
            await settings(x); await x.click('[data-act=restore]'); await x.until("!!document.querySelector('#restoreIn')", 5000)
            await x.pg.evaluate("v => { const t = document.querySelector('#restoreIn'); t.value = v; t.dispatchEvent(new Event('input', {bubbles: true})) }", old)
            await x.click('[data-act=doRestore]'); await x.until("!document.querySelector('#restoreIn')", 60000); await x.wait(800)
            check('import: a plain old file (no password, no extras) still imports', await x.bal() == 1500, await x.bal())
            check('import: a wallet holding sats keeps its own words and contacts (nothing silently replaced)', await x.ev("Nutcade.S.seed.mnemonic") == xwords and await x.ev("Nutcade.S.contacts.some(c=>c.name==='Bob')"))
            check('file: no script errors', not (w.errs + n.errs + x.errs), (w.errs + n.errs + x.errs)[:4])
            for z in (w, n, x): await z.pg.context.close()
        await section('file', file_pw)

        # ======================= a backup of the real wallet carries no trace of the duress PIN's wallet =======================
        async def duress_trace():
            plain, _ = await funded(b, 1000)
            keys_plain = sorted(json.loads(await plain.ev("Nutcade.r8.backupData()")).keys())
            w, words = await funded(b, 2000); await set_pin(w)
            await settings(w); await w.click('[data-act=duressOpen]'); await w.wait(250)
            await pad(w, PIN); await w.wait(800); await pad(w, DPIN); await w.wait(300); await pad(w, DPIN); await w.until("!!document.querySelector('#duressAmt')", 8000)
            await w.fill('#duressAmt', '300'); await w.click('[data-act=duressMake]'); await w.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await w.ev("Nutcade.closeSheet()")
            await w.pg.reload(); await w.wait(800); await unlock(w, DPIN); await w.wait(500)
            dwords = await w.ev("Nutcade.S.seed.mnemonic")
            await w.ev("Nutcade.S.contacts.push({id:'d1',name:'Decoy Dan',ln:'dan@example.com',nostr:'',created:1}); window.NutStore.set('contacts', Nutcade.S.contacts); window.NutStore.set('trophies', {top5: 1}); Trophies.reload(); Nutcade.S.prefs.theme='phosphor'; Nutcade.save && 0")
            await w.ev("(async()=>{ await Nutcade.vault.chain })()"); await w.wait(300)
            await w.pg.reload(); await w.wait(800); await unlock(w, PIN); await w.wait(500)
            bk = await w.ev("Nutcade.r8.backupData()"); d = json.loads(bk)
            check('duress: the real wallet backup has exactly the keys of a wallet without a duress PIN', sorted(d.keys()) == keys_plain, (sorted(d.keys()), keys_plain))
            check('duress: no trace of it (no "duress", "slot", its words, contacts or trophies)', not any(t in bk for t in ('duress', 'slot', 'decoy', 'Decoy Dan', dwords.split()[0] + ' ' + dwords.split()[1])) and 'top5' not in d['trophies'] and d['seed'] == words)
            check('duress: no trace of a phone backup either (no phonebk record or key in it)', 'phonebk' not in bk and '"sk"' not in bk)
            await w.pg.context.close(); await plain.pg.context.close()
        await section('duress', duress_trace)

        # ======================= Back up with my phone: create, restore =======================
        async def phone_create_restore():
            w, words = await funded(b)
            cdp, aid = await authn(w)
            await settings(w)
            check('phone: shown in Settings > Backup where passkeys with PRF work', await w.ev("!document.querySelector('#set-backup [data-phonecap]').hidden") and 'NOT SET UP' in await w.ev("document.querySelector('#set-backup').innerText"))
            n0 = len(pb_events())
            await w.click('[data-act=phoneOpen]'); await w.wait(250); txt = await w.sheet_text()
            check('phone: the screen warns that the Apple or Google account becomes a key, and that the 12 words stay the main backup', 'Apple or Google account becomes a key' in txt and 'main backup' in txt, txt[:200])
            await w.click('[data-act=phoneGo]'); await w.until("!document.querySelector('[data-act=phoneGo]') || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 30000); await w.wait(300)
            txt = await w.sheet_text(); evs = pb_events()
            check('phone: backed up (one passkey made, one locked copy on the relay)', 'BACKED UP' in txt and await creds(cdp, aid) == 1 and len(evs) == n0 + 1, (txt[:120], await w.err()))
            rec = await w.ev("Nutcade.bk.rec()")
            ev = [e for e in evs if e['pubkey'] == rec['pk']]
            check("phone: the copy is signed by the passkey's own key (not the wallet's Nostr key) and holds no readable words", len(ev) == 1 and all(x not in ev[0]['content'] for x in words.split()[:3]) and json.loads(ev[0]['content'])['alg'] == 'A256GCM')
            await settings(w)
            check('phone: Settings shows when it was saved', 'NOT SET UP' not in await w.ev("document.querySelector('#set-backup').innerText"))
            check('phone: no toast or log carries the 12 words', not leaks(words, await w.ev("window.__toasts.concat(window.__logs)")))
            # back up again: the same passkey, the copy replaced (still one)
            t1 = ev[0]['created_at']; await phone_backup(w); await w.ev("Nutcade.closeSheet()")
            ev2 = [e for e in pb_events() if e['pubkey'] == rec['pk']]
            check('phone: Back up again uses the same passkey and replaces the copy', await creds(cdp, aid) == 1 and len(ev2) == 1 and ev2[0]['created_at'] > t1)
            # a new phone (storage wiped, the passkey synced): Restore with my phone on the start screen
            await fresh(w)
            check('phone: Restore with my phone is on the start screen', await w.ev("!document.querySelector('[data-act=gatePhone]').hidden"))
            txt = await gate_phone(w)
            check('phone: the passkey opens the copy; the Restore sheet is filled, the words are not shown', 'came from your phone backup' in txt and words.split()[2] not in await w.ev("document.body.innerText") and await w.ev("document.querySelector('#phraseIn').type") == 'hidden', txt[:200])
            check('phone: the mints from the backup are ticked', await w.ev(f"[...document.querySelectorAll('[data-rmint]')].some(i=>i.checked && i.dataset.rmint==={J(B)})"))
            await restore_now(w)
            check('phone: restored (the same words, the sats found at the mint)', await w.ev("Nutcade.S.seed && Nutcade.S.seed.mnemonic") == words and await w.bal() == 1000, await w.bal())
            check('phone: no toast or log carries the 12 words (restore)', not leaks(words, await w.ev("window.__toasts.concat(window.__logs)")))
            check('phone: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
        await section('phone', phone_create_restore)

        # ======================= wrong passkey, no PRF, relay down =======================
        async def wrong_passkey():
            # another passkey (not a NUTCADE phone backup) on a new phone: an error, nothing changes
            w = await wallet(b, init=WATCH); cdp, aid = await authn(w)
            await w.ev("navigator.credentials.create({publicKey:{rp:{name:'x',id:location.hostname},user:{id:new Uint8Array([9,9,9,9]),name:'other',displayName:'other'},challenge:new Uint8Array(32),pubKeyCredParams:[{type:'public-key',alg:-7}],authenticatorSelection:{residentKey:'required',userVerification:'required'},extensions:{prf:{eval:{first:new Uint8Array(32)}}}}}).then(()=>1)")
            await w.ev("Nutcade.render()")
            r = await gate_phone(w)
            check("wrong passkey: another passkey is refused (\"isn't a NUTCADE phone backup\"), nothing changed", "isn't a NUTCADE phone backup" in r and not await w.ev("Nutcade.S.seed"), r[:200])
            await w.pg.context.close()
            # a NUTCADE passkey with no copy on the relays (another wallet's, or one removed): a wallet with sats is never touched
            x, xwords = await funded(b, 700); cdp, aid = await authn(x)
            await x.ev("""(async()=>{ const id=new Uint8Array(16); id.set(new TextEncoder().encode('NCPB')); crypto.getRandomValues(id.subarray(4));
              await navigator.credentials.create({publicKey:{rp:{name:'NUTCADE',id:location.hostname},user:{id,name:'n',displayName:'n'},challenge:new Uint8Array(32),pubKeyCredParams:[{type:'public-key',alg:-7}],authenticatorSelection:{residentKey:'required',userVerification:'required'},extensions:{prf:{eval:{first:new Uint8Array(32)}}}}}); })()""")
            await settings(x); await x.click('[data-act=seedRestore]'); await x.until("!!document.querySelector('[data-act=phoneRestore]')", 5000)
            await x.click('[data-act=phoneRestore]'); await x.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
            e = await x.err()
            check('wrong passkey: a passkey with no backup says so; the wallet with sats is unchanged (words, balance, the typed-words box)', 'No phone backup was found' in e and await x.ev("Nutcade.S.seed.mnemonic") == xwords and await x.bal() == 700 and await x.ev("document.querySelector('#phraseIn').tagName") == 'TEXTAREA', e)
            # a tampered copy (signed right, but not openable with this passkey): a hard error
            await x.ev("Nutcade.closeSheet()")
            check('wrong passkey: no script errors', not x.errs, x.errs[:4])
            await x.pg.context.close()
        await section('wrong', wrong_passkey)

        async def no_prf():
            # the browser says PRF isn't supported: the option is hidden (Settings, the start screen, the Restore sheet)
            h = await wallet(b, init=WATCH + NO_PRF_CAP); await authn(h); await h.ev("Nutcade.render()")
            check('no PRF: hidden on the start screen', await h.ev("document.querySelector('[data-act=gatePhone]').hidden"))
            await h.create(); await settings(h)
            check('no PRF: hidden in Settings', await h.ev("document.querySelector('#set-backup [data-phonecap]').hidden"))
            await h.click('[data-act=seedRestore]'); await h.wait(250)
            check('no PRF: hidden on the Restore sheet', await h.ev("document.querySelector('[data-act=phoneRestore]').hidden"))
            await h.pg.context.close()
            # no WebAuthn at all: hidden too
            z = await wallet(b, init=WATCH + "delete window.PublicKeyCredential;"); await z.ev("Nutcade.render()")
            check('no WebAuthn: hidden on the start screen', await z.ev("Nutcade.bk.cap().then(c=>!c)") and await z.ev("document.querySelector('[data-act=gatePhone]').hidden"))
            await z.pg.context.close()
            # a passkey that turns out to have no PRF: a clear error, nothing saved, nothing sent
            w, words = await funded(b); cdp, aid = await authn(w, prf=False); n0 = len(pb_events())
            txt, e = await phone_backup(w)
            check("no PRF: a passkey without PRF is a clear error; nothing saved or sent", "can't lock your words" in e and not await w.ev("Nutcade.bk.rec()") and len(pb_events()) == n0, (e, txt[:100]))
            check('no PRF: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
        await section('noprf', no_prf)

        async def relay_down():
            w, words = await funded(b); cdp, aid = await authn(w)
            await w.ev("window.__relayDown=true")
            n0 = len(pb_events())
            txt, e = await phone_backup(w)
            check("relay down: a clear error, no 'backed up' state, nothing half-saved", 'No Nostr relay answered' in e and not await w.ev("Nutcade.bk.rec()") and len(pb_events()) == n0, e)
            await settings(w)
            check('relay down: Settings still says NOT SET UP', 'NOT SET UP' in await w.ev("document.querySelector('#set-backup').innerText"))
            # with the relay back: it works; then restoring while the relay is down changes nothing
            await w.ev("window.__relayDown=false")
            txt, e = await phone_backup(w); await w.ev("Nutcade.closeSheet()")
            check('relay down: once a relay answers, the backup is saved', 'BACKED UP' in txt and await w.ev("!!Nutcade.bk.rec()"), e)
            await settings(w); await w.click('[data-act=seedRestore]'); await w.until("!!document.querySelector('[data-act=phoneRestore]')", 5000)
            await w.ev("window.__relayDown=true")
            await w.click('[data-act=phoneRestore]'); await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
            check('relay down: restoring says no relay answered; nothing changed', 'No Nostr relay answered' in await w.err() and await w.ev("Nutcade.S.seed.mnemonic") == words and await w.bal() == 1000, await w.err())
            check('relay down: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
        await section('relay', relay_down)

        # ======================= two devices =======================
        async def two_devices():
            a, words = await funded(b); ca, aa = await authn(a)
            await phone_backup(a); await a.ev("Nutcade.closeSheet()"); pka = (await a.ev("Nutcade.bk.rec()"))['pk']
            # a second phone with the same wallet (restored from the 12 words) and its own passkey
            d = await wallet(b, init=WATCH); cd, ad = await authn(d)
            await d.gate_restore(); await d.fill('#phraseIn', words); await d.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await d.fill('#rmExtra', B)
            await restore_now(d); await leave_gate(d)
            check('two devices: the second phone has the wallet', await d.bal() == 1000, await d.bal())
            await phone_backup(d); await d.ev("Nutcade.closeSheet()"); pkd = (await d.ev("Nutcade.bk.rec()"))['pk']
            evs = pb_events()
            check('two devices: each passkey keeps its own copy (two copies, two keys)', pka != pkd and any(e['pubkey'] == pka for e in evs) and any(e['pubkey'] == pkd for e in evs))
            for z, label in ((a, 'first'), (d, 'second')):
                await fresh(z); r = await gate_phone(z)
                ok = 'came from your phone backup' in r
                if ok: await restore_now(z)
                check(f'two devices: the {label} phone restores with its own passkey', ok and await z.ev("Nutcade.S.seed && Nutcade.S.seed.mnemonic") == words, r[:150])
            check('two devices: no script errors', not (a.errs + d.errs), (a.errs + d.errs)[:4])
            await a.pg.context.close(); await d.pg.context.close()
        await section('two', two_devices)

        # ======================= PIN + duress =======================
        async def pin_duress():
            w, words = await funded(b, 2000); cdp, aid = await authn(w); await set_pin(w)
            await settings(w); await w.click('[data-act=phoneOpen]'); await w.wait(300)
            check('PIN: Back up with my phone asks for the PIN first', await w.ev("!!document.querySelector('#layer [data-pinpad=guard]')") and 'Enter your PIN to back up your 12 words with your phone.' in await w.sheet_text())
            await pad(w, '999999', '#layer [data-pinpad=guard]'); await w.until("/wrong/i.test((document.querySelector('#pinErr')||{}).innerText||'')", 20000)
            check('PIN: a wrong PIN goes no further (no passkey made)', not await w.ev("!!document.querySelector('[data-act=phoneGo]')") and await creds(cdp, aid) == 0)
            await w.ev("Nutcade.closeSheet(); localStorage.removeItem('nutcade:pinfails')")
            txt, e = await phone_backup(w, PIN)
            check('PIN: with the right PIN it is made', 'BACKED UP' in txt and await creds(cdp, aid) == 1, e)
            await w.ev("Nutcade.closeSheet()")
            # the duress PIN's wallet: same screens, but no passkey is ever made and nothing is sent
            await settings(w); await w.click('[data-act=duressOpen]'); await w.wait(250)
            await pad(w, PIN); await w.wait(800); await pad(w, DPIN); await w.wait(300); await pad(w, DPIN); await w.until("!!document.querySelector('#duressAmt')", 8000)
            await w.fill('#duressAmt', '300'); await w.click('[data-act=duressMake]'); await w.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await w.ev("Nutcade.closeSheet()")
            await w.pg.reload(); await w.wait(800); await unlock(w, DPIN); await w.wait(600); await w.ev("Nutcade.bk.cap()")
            await settings(w)
            check('duress: Settings shows the phone backup as not set up (the real one is not revealed)', 'NOT SET UP' in await w.ev("document.querySelector('#set-backup').innerText") and not await w.ev("Nutcade.bk.rec()"))
            n0, c0 = len(state()['events']), await creds(cdp, aid)
            txt, e = await phone_backup(w, DPIN)
            check("duress: Back up with my phone answers \"isn't available right now\"; no passkey made, nothing sent", "isn't available right now" in e and await creds(cdp, aid) == c0 and len(state()['events']) == n0 and not await w.ev("Nutcade.bk.rec()"), e)
            await w.ev("Nutcade.closeSheet()"); await settings(w); await w.click('[data-act=seedRestore]'); await guard_if(w, DPIN)
            await w.until("!!document.querySelector('[data-act=phoneRestore]')", 5000); await w.click('[data-act=phoneRestore]')
            await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
            check("duress: Restore with my phone answers \"isn't available right now\" too", "isn't available right now" in await w.err(), await w.err())
            await w.ev("Nutcade.closeSheet()")
            # the real wallet still has its phone backup
            await w.pg.reload(); await w.wait(800); await unlock(w, PIN); await w.wait(500)
            check('duress: the real wallet still has its phone backup', await w.ev("!!Nutcade.bk.rec()"))
            check('PIN + duress: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
        await section('pin', pin_duress)

        # ======================= reset deletes the backup =======================
        async def reset_deletes():
            w, words = await funded(b); cdp, aid = await authn(w); await set_pin(w)
            await phone_backup(w, PIN); await w.ev("Nutcade.closeSheet()")
            pk = (await w.ev("Nutcade.bk.rec()"))['pk']
            check('reset: the copy is on the relay before', any(e['pubkey'] == pk and e['content'] for e in pb_events()))
            # every step that deletes the phone backup or makes it out of date says so on its screen
            for act, key, pat in (('resetAsk', 'reset', 'also deletes your phone backup'), ('seedRestore', 'restore', 'out of date until'), ('restore', 'import', 'out of date until'), ('newSeedAsk', 'newseed', 'out of date until'), ('phoneRemoveAsk', 'phone', 'will not bring this wallet back')):
                await settings(w)
                if act == 'newSeedAsk': await w.ev("(()=>{const b=document.createElement('button'); b.dataset.act='newSeedAsk'; document.querySelector('#app').appendChild(b); b.click(); b.remove()})()")   # (no button for it on screen today)
                else: await w.click(f'[data-act={act}]')
                await guard_if(w, PIN); await w.wait(250)
                check(f'warned: {act} says what happens to the phone backup', pat in await w.sheet_text(), (await w.sheet_text())[:160])
                await w.ev("Nutcade.closeSheet()")
            await w.pg.reload(); await w.wait(800); await w.ev("Nutcade.bk.cap()"); await w.click('[data-act=forgotPin]'); await w.wait(300)
            check('warned: Forgot PIN says a phone backup is not deleted by that reset', 'is not deleted by this reset' in await w.sheet_text())
            await w.ev("Nutcade.closeSheet()"); await unlock(w, PIN)
            await settings(w); await w.click('[data-act=resetAsk]'); await guard_if(w, PIN); await w.until("!!document.querySelector('#confirmWord')", 5000)
            await w.fill('#confirmWord', 'RESET'); await w.click('[data-act=doReset]')
            await w.until("!!document.querySelector('[data-act=gateCreate]')", 20000); await w.wait(800)
            st = state()
            check('reset: the copy on the relay is gone (replaced, and a deletion asked for)', not any(e['pubkey'] == pk and e['content'] for e in st['events']) and any(e['pubkey'] == pk and e['kind'] == 5 for e in st['events']))
            check('reset: nothing of it is left on this phone (the record, and the passkey forgotten where the browser allows)', 'phonebk' not in await w.ev("Object.keys(localStorage).join(' ')") and not await w.ev("Nutcade.bk.rec()") and await forgot(w, cdp, aid))
            await w.ev("Nutcade.bk.cap()"); await w.ev("Nutcade.render()")
            r = await gate_phone(w)
            check('reset: Restore with my phone then restores nothing; nothing changed', 'Nothing was changed' in r and not await w.ev("Nutcade.S.seed"), r[:150])
            # Remove phone backup (Settings) does the same, after the PIN
            y, ywords = await funded(b); cy, ay = await authn(y)
            await settings(y); await y.click('[data-act=resetAsk]'); await y.wait(250)
            check('warned: without a phone backup the Reset sheet does not mention one', 'phone backup' not in await y.sheet_text())
            await y.ev("Nutcade.closeSheet()")
            await phone_backup(y); await y.ev("Nutcade.closeSheet()"); ypk = (await y.ev("Nutcade.bk.rec()"))['pk']
            # the passkey deleted in the password manager: Back up again says so and points to Remove (which needs no passkey)
            await cy.send('WebAuthn.clearCredentials', {'authenticatorId': ay})
            txt, e = await phone_backup(y)
            check("passkey gone: Back up again says the passkey wasn't found and offers Remove phone backup", "passkey wasn't found" in e and await y.ev("!!document.querySelector('#sheetErr [data-act=phoneRemoveAsk]')"), e)
            await y.click('#sheetErr [data-act=phoneRemoveAsk]'); await y.until("!!document.querySelector('[data-act=phoneRemoveGo]')", 5000); await y.click('[data-act=phoneRemoveGo]'); await y.until("!document.querySelector('[data-act=phoneRemoveGo]')", 15000); await y.wait(300)
            check('remove: Remove phone backup deletes the copy, the record and the passkey', not await y.ev("Nutcade.bk.rec()") and not any(e['pubkey'] == ypk and e['content'] for e in pb_events()) and await forgot(y, cy, ay))
            check('reset/remove: no script errors', not (w.errs + y.errs), (w.errs + y.errs)[:4])
            await w.pg.context.close(); await y.pg.context.close()
        await section('reset', reset_deletes)

        # ======================= custom relays, the record after a restore, a stale backup =======================
        async def custom_relays():
            w, words = await funded(b); cdp, aid = await authn(w)
            await w.ev("Nutcade.S.prefs.relays=['ws://127.0.0.1:3358/relay']; window.__ws=[]")   # (a relay of your own, down right now)
            txt, e = await phone_backup(w); await w.ev("Nutcade.closeSheet()")
            opened = await w.ev("window.__ws")
            check('custom relays: the copy goes to your relays AND the default ones (it is saved although yours is down)', 'BACKED UP' in txt and any(urllib.parse.urlparse(u).port == 3358 for u in opened) and any(urllib.parse.urlparse(u).hostname == 'relay' + '.damus.io' for u in opened), (e, opened[:6]))
            # a new phone that only has the default relays finds it
            await w.ev("localStorage.clear()"); await w.ev("localStorage.setItem('nutcade:prefs', JSON.stringify({sound:false,music:false,lang:'en'}))")
            await w.pg.reload(); await w.wait(900); await w.ev("Nutcade.bk.cap()"); await w.ev("Nutcade.render()")
            r = await gate_phone(w)
            ok = 'came from your phone backup' in r
            if ok: await restore_now(w); await leave_gate(w)
            check('custom relays: a new phone with only the default relays restores it', ok and await w.ev("Nutcade.S.seed && Nutcade.S.seed.mnemonic") == words, r[:150])
            rec = await w.ev("Nutcade.bk.rec()")
            check('after a phone restore: this wallet keeps the phone backup record (no key in it, only the signed removal)', bool(rec) and 'sk' not in rec and len(rec.get('erase', [])) == 2 and '"sk"' not in await w.ev("JSON.stringify(Object.assign({},localStorage))"))
            n0 = await creds(cdp, aid)
            txt, e = await phone_backup(w); await w.ev("Nutcade.closeSheet()")
            check('after a phone restore: Back up again reuses the same passkey (no second one)', 'BACKED UP' in txt and await creds(cdp, aid) == n0 and (await w.ev("Nutcade.bk.rec()"))['pk'] == rec['pk'], e)
            # two phones with the same synced passkey: phone A's record, phone B updates to new words, then A taps Back up again
            rec_a = await w.ev("Nutcade.bk.rec()")
            w2 = 'legal winner thank year wave sausage worth useful legal winner thank yellow'
            await w.ev(f"Nutcade.S.seed.mnemonic={J(w2)}")   # (phone B: its own copy, new words)
            txt, e = await phone_backup(w); await w.ev("Nutcade.closeSheet()")
            check('synced passkey: a copy this phone saved itself is updated to its new words without asking', 'BACKED UP' in txt, e)
            await w.ev(f"window.NutStore.set('phonebk', {J(rec_a)}); Nutcade.S.seed.mnemonic={J(words)}")   # (phone A, with its older record)
            t0 = [x['created_at'] for x in pb_events() if x['pubkey'] == rec['pk']]
            txt, e = await phone_backup(w)
            check('synced passkey: a newer copy with other words is never replaced silently (a warning and Replace anyway)', 'holds other 12 words' in e and await w.ev("!!document.querySelector('#sheetErr [data-act=phoneGoForce]')") and [x['created_at'] for x in pb_events() if x['pubkey'] == rec['pk']] == t0, e)
            await w.click('#sheetErr [data-act=phoneGoForce]'); await w.until("/BACKED UP/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000)
            check('synced passkey: Replace anyway replaces it', 'BACKED UP' in await w.sheet_text(), await w.err())
            await w.ev("Nutcade.closeSheet()")
            # new words: the phone backup shows OUT OF DATE and says to back up again
            await w.ev("Nutcade.S.seed.mnemonic='abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'")
            await settings(w); await w.wait(400)
            t = await w.ev("document.querySelector('#set-backup').innerText")
            check('stale: a phone backup of other words shows OUT OF DATE and a line to back up again', 'OUT OF DATE' in t and 'Back up again to save the new ones' in t, t[-300:])
            check('custom relays: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()
        await section('custom', custom_relays)

        # ======================= a hostile backup file: the extras can't plant a payee, weaken a setting or stop the import =======================
        async def hostile():
            src, words = await funded(b, 600)
            pk1 = 'a' * 64; pk2 = 'b' * 64
            d = json.loads(await src.ev("Nutcade.r8.backupData()"))
            d['contacts'] = [
                {'id': 'x1', 'name': 'Alice twin', 'ln': 'ALICE@example.com', 'nostr': ''},              # twin of a contact here (same address)
                {'id': 'c1', 'name': 'Same id', 'ln': 'mallory@example.com', 'nostr': ''},               # same id as the one here: never replaces it
                {'id': 'x3', 'name': 'Planted', 'ln': '', 'nostr': pk1, 'pubkey': pk2, 'relays': ['wss://evil.example']},   # the key comes from nostr, not the file
                {'id': 'x4', 'name': 'Bad ln', 'ln': 'javascript:alert(1)', 'nostr': ''},
                {'id': 'x5', 'name': {'toString': 0}, 'ln': 'bob@example.com'},
                {'id': 'x6', 'name': 'N' * 90, 'ln': 'carol@example.com', 'nostr': '', 'created': {'toString': 0}},
                {'id': 'x7', 'name': ' alice ', 'ln': 'evil2@example.com', 'nostr': ''},              # the same name as a contact here: skipped
                'not a contact', None]
            d['settings'] = {'relays': ['wss://evil.example'], 'lockAfter': 60, 'fiat': True, 'nostrInbox': True, 'arrNotify': True, 'qrLogo': {'toString': 0}, 'theme': {}, 'currency': 'EUR', 'hideAmounts': 'yes', 'crt': False, 'piggyStep': 50}
            d['trophies'] = {'rat': {'toString': 0}, 'big': 'x', 'top5': 123}
            d['plays'] = {'n': {'toString': 0}, 'by': {'swarm': '9', 'maze': 4}}
            d['arcade'] = {'scores': {'swarm': [{'n': '<img src=x onerror=alert(1)>', 's': 99999, 't': 1}, {'n': 'ABC', 's': {'toString': 0}}, {'n': 'XYZ', 's': 50, 't': 2}], 'daily': 'oops', 'maze': {'toString': 0}}, 'initials': '<b>'}
            n = await wallet(b, init=WATCH); await n.create(); await n.add_mint(B); await n.home()
            await n.ev("Nutcade.S.contacts.push({id:'c1',name:'Alice',ln:'alice@example.com',nostr:'',pubkey:'',relays:[],created:1}); window.NutStore.set('contacts', Nutcade.S.contacts); localStorage.removeItem('nutcade:initials')")
            await n.ev("Nutcade.S.prefs.lockAfter=5; Nutcade.S.prefs.fiat=false; Nutcade.S.prefs.nostrInbox=false; Nutcade.S.prefs.arrNotify=false")
            res = await n.ev(f"Nutcade.r8.importBackup(JSON.parse({J(J(d))})).then(()=>'ok', e=>'ERR '+e.message)"); await n.wait(2500)
            check('hostile: the import itself goes through (coins checked and added, saved)', res == 'ok' and await n.bal() == 600 and await n.ev("JSON.parse(localStorage.getItem('nutcade:proofs')||'{}')") != {}, (res, await n.bal()))
            cs = await n.ev("Nutcade.S.contacts")
            by = {c['name']: c for c in cs}
            check('hostile: a contact here is never replaced (same id, same address)', by.get('Alice', {}).get('ln') == 'alice@example.com' and 'Alice twin' not in by, [c['name'] for c in cs])
            check('hostile: a contact with the same name as one here (any case) is skipped', not any(c['ln'] == 'evil2@example.com' for c in cs))
            check('hostile: a piggy-bank step other than 10, 100 or 1000 is skipped', (await n.ev("Nutcade.S.prefs.piggyStep")) != 50 and await n.ev("Nutcade.bk.extras({settings:{piggyStep:1000}}), Nutcade.S.prefs.piggyStep") == 1000)
            check('hostile: a contact with the same id comes in as a new, visible contact (its own id)', 'Same id' in by and by['Same id']['id'] != 'c1')
            check("hostile: a Nostr contact's key is read from its address, never taken from the file", by.get('Planted', {}).get('pubkey') == pk1 and by['Planted']['relays'] == [], by.get('Planted'))
            check('hostile: a bad Lightning address and a non-text name are dropped; names are cut to 40', 'Bad ln' not in by and not any(c['ln'] == 'bob@example.com' for c in cs) and any(len(c['name']) == 40 for c in cs))
            p = await n.ev("Nutcade.S.prefs")
            check('hostile: settings never point Nostr elsewhere, lengthen the auto-lock or turn on a service', p.get('relays') != ['wss://evil.example'] and p.get('lockAfter') == 5 and p.get('nostrInbox') is False and p.get('fiat') is False and p.get('arrNotify') is False, {k: p.get(k) for k in ('relays', 'lockAfter', 'fiat', 'nostrInbox', 'arrNotify')})
            check('hostile: values of the wrong type are skipped, good ones kept', p.get('theme') != {} and p.get('qrLogo') in (None, 'acorn', 'none') and p.get('hideAmounts') != 'yes' and p.get('currency') == 'EUR' and p.get('crt') is False)
            t = await n.ev("Trophies.got()"); pl = await n.ev("window.NutStore.get('plays', null)")
            check('hostile: trophies and plays take only numbers', 'rat' not in t and 'big' not in t and t.get('top5') == 123 and pl['by'].get('maze') == 4 and 'swarm' not in pl['by'] and isinstance(pl['n'], int), (t, pl))
            sw = await n.ev("JSON.parse(localStorage.getItem('nutcade:scores:swarm')||'[]')")
            check('hostile: high scores take only 3-letter initials and number scores; initials too', [x['n'] for x in sw] == ['XYZ'] and not await n.ev("localStorage.getItem('nutcade:initials')"), sw)
            await n.click('[data-act=tab][data-tab=arcade]'); await n.wait(600)
            check('hostile: nothing from the file runs on the Arcade screen', not await n.ev("!!document.querySelector('.cabinets img, .scores img')"))
            # a lockAfter that is shorter does come in, and the auto-lock is armed again
            await n.ev("Nutcade.bk.extras({settings:{lockAfter:1}})")
            check('hostile: a shorter auto-lock comes in', await n.ev("Nutcade.S.prefs.lockAfter") == 1)
            check('hostile: no script errors', not (n.errs + src.errs), (n.errs + src.errs)[:4])
            await n.pg.context.close(); await src.pg.context.close()
        await section('hostile', hostile)

        # ======================= a relay that never answers doesn't hold anything up =======================
        async def slow_relay():
            hole = socket.socket(); hole.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); hole.bind(('127.0.0.1', 3357)); hole.listen(64)   # (takes connections, never answers)
            try:
                w, words = await funded(b); cdp, aid = await authn(w); await w.ev("window.__blackhole=true")
                t0 = time.time(); txt, e = await phone_backup(w); dt = time.time() - t0; await w.ev("Nutcade.closeSheet()")
                check(f'dead relay: Back up with my phone finishes in a few seconds ({dt:.1f} s)', 'BACKED UP' in txt and dt < 10, e)
                await fresh(w); await w.ev("window.__blackhole=true")
                t0 = time.time(); r = await gate_phone(w); dt = time.time() - t0
                check(f'dead relay: Restore with my phone finishes in a few seconds ({dt:.1f} s)', 'came from your phone backup' in r and dt < 12, r[:120])
                await restore_now(w); await leave_gate(w)
                await phone_backup(w); await w.ev("Nutcade.closeSheet(); window.__blackhole=true")
                await settings(w); await w.click('[data-act=resetAsk]'); await w.wait(250); await w.fill('#confirmWord', 'RESET')
                t0 = time.time(); await w.click('[data-act=doReset]')
                for _ in range(100):   # (the page reloads on its own: ask again until the start screen is there)
                    try:
                        if await w.ev("!!document.querySelector('[data-act=gateCreate]')"): break
                    except Exception: pass
                    await asyncio.sleep(0.2)
                dt = time.time() - t0
                check(f'dead relay: Reset still takes only a few seconds ({dt:.1f} s)', dt < 8)
                check('dead relay: no script errors', not w.errs, w.errs[:4])
                await w.pg.context.close()
            finally: hole.close()
        await section('slow', slow_relay)

        # ======================= the new text in every language =======================
        async def langs():
            w, words = await funded(b); await authn(w)
            for lang in LANGS[1:]:
                await set_lang(w, lang); await w.ev("window.__i18nMiss=new Set()")
                await settings(w); await w.ev("document.querySelector('#bkLock').checked || document.querySelector('#bkLock').click()")
                miss = set(await w.ev("[...window.__i18nMiss]"))
                await w.click('[data-act=backupDownload]'); await w.wait(250); await w.fill('#bkPw', 'x'); await w.click('[data-act=bkLockGo]'); await w.wait(250)
                await w.fill('#bkPw', 'abcdefgh'); await w.fill('#bkPw2', 'abcdefgx'); await w.click('[data-act=bkLockGo]'); await w.wait(250)
                await w.click('[data-act=phoneOpen]'); await w.wait(250)
                await w.click('[data-act=restore]'); await w.wait(250)
                await w.pg.evaluate("v => { const t = document.querySelector('#restoreIn'); t.value = v; }", J({'app': 'nutcade', 'kind': 'locked-backup', 'v': 1, 'kdf': {'alg': 'PBKDF2-SHA256', 'iter': 100000, 'salt': 'AAAA'}, 'cipher': {'alg': 'AES-256-GCM', 'iv': 'AAAA'}, 'ct': 'AAAA'}))
                await w.click('[data-act=doRestore]'); await w.wait(300); await w.fill('#restorePw', 'nope'); await w.click('[data-act=doRestore]'); await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
                await w.ev("Nutcade.closeSheet()"); await settings(w); await w.click('[data-act=seedRestore]'); await w.wait(250); await w.ev("Nutcade.closeSheet()")
                await w.ev("Nutcade.toast(\"Back up with my phone isn't available right now. Try again later.\")")
                miss |= set(await w.ev("[...window.__i18nMiss]"))
                miss = [m for m in miss if any(k in m for k in ('password', 'phone', 'passkey', 'Passkey', 'Apple', 'relay', 'contacts', 'locked', 'Locked', 'NOT SET UP', 'main backup', 'Protect'))]
                check(f'{lang}: the new backup screens and errors are translated', not miss, miss[:6])
                await w.ev("document.querySelector('#bkLock') && document.querySelector('#bkLock').checked && document.querySelector('#bkLock').click()")
            await w.pg.context.close()
        await section('langs', langs)

        await b.close()
    bad = [r for r in results if not r[1]]
    print(f'\nSUMMARY {len(results) - len(bad)}/{len(results)} passed')
    if bad: sys.exit(1)

asyncio.run(main())
