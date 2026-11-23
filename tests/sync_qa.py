"""Wallet sync (1.30.0, a subset of NIP-60): two devices with the same 12 words, the mint as referee.
Uses ONE real local test mint (3339, Nutshell cashu==0.21.0, no fees, so amounts are exact) and the stand-in Nostr relay
(mock_nostr.py, port 3350, with switches that make it drop, reorder and duplicate events). Each "device" is its own
browser context (its own storage), and both hold the same 12 words.

Covered: sync is off by default and nothing is published or read while off; the key is the dedicated sync key
(sha256(seed || "nutcade-nip60")), not the Nostr identity; the events are NIP-44 encrypted to it (kind 7375 coins, kind
17375 wallet with the nutzap key, counters and "gone" marks, kind 5 deletions of our own events). A deposits, B sees the
coins (after the mint says they are unspent); A spends, B's balance drops, and B cannot spend the stale coins (the mint
refuses them, B gets no credit and loses nothing); BOTH spend the same coins at once (exactly one succeeds); a crash in
the middle of a spend, then sync; the relay drops, reorders, duplicates, forgets and replays events; forged, garbage,
oversized and other-mint events are ignored (another mint is only shown, never added); restore on a new device from the
12 words (coins from the relays, the NUT-13 scan after it adds nothing twice, unclaimed tokens of the other device are
not counted); the duress PIN's wallet never reads or publishes; a paused tab does nothing; turning sync off stops it and
offers (does not force) deleting our events. After every step that moves money, sats are conserved across both devices
and the mint: the distinct coins the devices hold plus the unclaimed tokens they made, that the mint says are unspent,
never add up to more than was issued, and once both have synced they add up to exactly that, with no spent coin counted
anywhere.

NOT proven here: real Nostr relays (rate limits, event size limits, NIP-09 handling, eventual consistency), other
wallets (no interop is intended: cashu.me and Minibits use another key and never see these events), real timing between
devices (clock skew, phones asleep, two devices writing the wallet event in the same second), mints other than Nutshell
0.21 (DLEQ always present here; a mint that leaves DLEQ proofs out would have its coins left unsynced), and more than two
devices at once. SY_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from r8_qa import set_pin, unlock, pad, PIN, DPIN

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
OTHER = 'http://127.0.0.1:3338'
SYNC_KINDS = (7375, 17375, 5)

def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def post(path, body): return json.loads(urllib.request.urlopen(urllib.request.Request(MOCK + path, data=J(body).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
def evs(kind=None, author=None):
    return [e for e in state()['events'] if (kind is None or e['kind'] == kind) and (author is None or e['pubkey'] == author)]
def mode(**k): post('/test/relay_mode', k)

HELPERS = """
window.__syKey = w => { const s = CashuLib.mnemonicToSeedSync(w), t = new TextEncoder().encode('nutcade-nip60'), b = new Uint8Array(s.length + t.length); b.set(s); b.set(t, s.length); return CashuLib.sha256(b); };
window.__syPub = w => CashuLib.nostrPub(__syKey(w));
window.__syCk = w => { const sk = __syKey(w); return CashuLib.nip44.v2.utils.getConversationKey(sk, CashuLib.nostrPub(sk)); };
window.__syDec = (w, c) => { try { return JSON.parse(CashuLib.nip44.v2.decrypt(c, __syCk(w))); } catch (e) { return null; } };
window.__syEnc = (w, text) => CashuLib.nip44.v2.encrypt(text, __syCk(w));
window.__syEv = (w, kind, content, tags, dt) => CashuLib.finalizeEvent({ kind, created_at: Math.floor(Date.now() / 1000) + (dt || 0), tags: tags || [],
  content: typeof content === 'string' ? content : __syEnc(w, JSON.stringify(content)) }, __syKey(w));
window.__syRnd = () => CashuLib.bytesToHex(crypto.getRandomValues(new Uint8Array(32)));
window.__syPublish = ev => new Promise(r => { const ws = new WebSocket(%s); ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d[0] === 'OK') { try { ws.close(); } catch (e) {} r(d[2]); } }; setTimeout(() => r(false), 5000); });
""" % J(RELAY)

async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    await ctx.add_init_script(HELPERS)
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text and 'Failed to load' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def restore(b, name, words):
    d = await wallet(b, name)
    await d.gate_restore(); await d.fill('#phraseIn', words); await d.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await d.fill('#rmExtra', M)
    await d.click('[data-act=doRestorePhrase]'); await d.until("!document.querySelector('[data-act=doRestorePhrase]')", 120000); await d.wait(600)
    await d.ev("Nutcade.closeSheet()")
    if await d.until("!!document.querySelector('[data-act=gateStart]')", 4000): await d.gate_step('gateStart', "!!document.querySelector('.tabbar')")
    await d.wait(300); await d.ev("Nutcade.closeSheet()"); await d.use(M)
    return d
async def section(name, fn):
    only = [x for x in os.environ.get('SY_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
async def priv(w): return await w.ev("document.querySelector('#set-privacy').innerText")
async def coins(w): return await w.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).map(p=>({{id:p.id,amount:p.amount,secret:p.secret,C:p.C}}))")
async def tokens(w): return await w.ev("Nutcade.S.txs.filter(t=>t.type==='out'&&t.status==='pending'&&Array.isArray(t.sent)).flatMap(t=>t.sent).map(p=>({id:p.id,amount:p.amount,secret:p.secret,C:p.C}))")
async def lines(w, note): return await w.ev(f"Nutcade.S.txs.filter(t=>t.note==={J(note)}).map(t=>[t.type,t.amount])")
async def pull(w): return await w.ev("NutSync.pull().then(r=>r, e=>({error:e.message}))")

async def main():
    os.makedirs(OUT, exist_ok=True)
    issued = [0]
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        A = await wallet(b, 'sy-A'); words = await A.create(); await A.add_mint(M); await A.use(M)
        B = await restore(b, 'sy-B', words)
        PK = await A.ev("NutSync.pk()")
        ctx = {'reqs0': len(state()['reqs'])}   # (a restore looks once for a wallet event of the sync key: that read is the restore's)

        def relay_events(kind): return evs(kind, PK)
        async def relay_secrets():
            out = set()
            for e in relay_events(7375):
                c = await A.ev(f"__syDec({J(words)}, {J(e['content'])})")
                if c and isinstance(c.get('proofs'), list): out |= {q.get('secret') for q in c['proofs'] if isinstance(q, dict)}
            return out
        async def on_relay(w, ms=20000):   # every coin this device holds is listed on the relay
            for _ in range(ms // 500):
                mine = {q['secret'] for q in await coins(w)}
                if mine and mine <= await relay_secrets(): return True
                await w.wait(500)
            return False
        async def deposit(w, n):
            ok = await w.receive_ln(n)
            if ok: issued[0] += n
            return ok
        async def ledger(label, devs, strict=True):
            held, toks, per = {}, {}, []
            for d in devs:
                cs = await coins(d); per.append(cs)
                for q in cs: held[q['secret']] = q
                for q in await tokens(d): toks[q['secret']] = q
            allp = list(held.values()) + [q for s, q in toks.items() if s not in held]
            st = dict(zip([q['secret'] for q in allp], await A.ev(f"NutSync.states({J(M)}, {J(allp)})") if allp else []))
            value = sum(q['amount'] for q in allp if st.get(q['secret']) == 'UNSPENT')
            spent_counted = [sum(q['amount'] for q in cs if st.get(q['secret']) != 'UNSPENT') for cs in per]
            bals = [sum(q['amount'] for q in cs) for cs in per]
            ok = value <= issued[0] and all(x <= issued[0] for x in bals)
            if strict: ok = ok and value == issued[0] and not any(spent_counted)
            check(f'{label}: sats conserved (distinct unspent coins + unclaimed tokens {"==" if strict else "<="} issued {issued[0]}; no spent coin counted)', ok, (value, issued[0], bals, spent_counted))

        async def off():
            check('off: the sync key is sha256(seed || "nutcade-nip60"), not the public Nostr identity', PK == await A.ev(f"__syPub({J(words)})") and PK != await A.ev("NutZap.me()"), PK)
            ok = await deposit(A, 1000); check('setup: A has sats (1000)', ok)
            await A.wait(3000)
            check('off: sync is off by default on both devices', await A.ev("Nutcade.S.prefs.sync") is not True and await B.ev("Nutcade.S.prefs.sync") is not True and not await A.ev("NutSync.on()"))
            check('off: nothing is published while off (no kind 7375, 17375 or 5 from the sync key)', not any(relay_events(k) for k in SYNC_KINDS))
            check('off: nothing is read while off (no REQ for the sync key)', not any(PK in (f.get('authors') or []) for fs in state()['reqs'][ctx['reqs0']:] for f in fs))
            await settings(A); t = await priv(A)
            check('off: Settings has the switch, off, with the privacy note in plain words', 'Sync this wallet across devices' in t and 'how many events you publish' in t and 'cashu.me' in t and not await A.ev("document.querySelector('#p_sync').checked"), t[-600:])
            check('off: B (same 12 words, sync off) does not see the coins', await B.bal() == 0)
            await ledger('off', [A, B])
        await section('off', off)

        async def on_a():
            await settings(A); await A.click('#p_sync')
            ok = await on_relay(A)
            check('on: turning sync on publishes A\'s coins (kind 7375) under the sync key', ok)
            e7 = relay_events(7375); w17 = relay_events(17375)
            c = await A.ev(f"__syDec({J(words)}, {J(e7[0]['content'])})") if e7 else None
            check('on: a coin event decrypts (NIP-44, to itself) to {mint, unit sat, proofs}, with no tags that say anything', c and c.get('mint') == M and c.get('unit') == 'sat' and isinstance(c.get('proofs'), list) and all(e['tags'] == [] for e in e7), c and list(c))
            ok17 = await A.until("true", 100)
            for _ in range(20):
                w17 = relay_events(17375)
                if w17: break
                await A.wait(500)
            wc = await A.ev(f"__syDec({J(words)}, {J(w17[0]['content'])})") if w17 else None
            pk_ok = False
            if wc:
                pv = [t[1] for t in wc if t[0] == 'privkey']
                pk_ok = bool(pv) and await A.ev(f"CashuLib.bytesToHex(CashuLib.getPubKeyFromPrivKey(CashuLib.hexToBytes({J(pv[0])}))) === NutZap.pub()")
            check('on: the wallet event (kind 17375) holds the nutzap receiving key, the mint and the NUT-13 counters', wc and pk_ok and ['mint', M] in wc and any(t[0] == 'counter' for t in wc), wc and [t[0] for t in wc])
            ctx['old7375'] = list(e7)
            t = await priv(A)
            check('on: Settings says IN SYNC, with a Sync now button', 'IN SYNC' in t and await A.ev("!!document.querySelector('[data-act=syncNow]')"), t[-300:])
        await section('on', on_a)

        async def on_b():
            n7 = len(relay_events(7375)); n17 = len(relay_events(17375))
            await settings(B); await B.click('#p_sync')
            ok = await B.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= 1000", 20000)
            check('B sees A\'s deposit: 1000 SAT, after the mint said the coins are unspent', ok and await B.bal() == await A.bal() == 1000, (await B.bal(), await A.bal()))
            check('B: one history line "From your other device (wallet sync)" for exactly that amount', await lines(B, 'From your other device (wallet sync)') == [['in', 1000]], await lines(B, 'From your other device (wallet sync)'))
            ca, cb = await A.ev("Nutcade.S.counters"), await B.ev("Nutcade.S.counters")
            check('B: the NUT-13 counters are merged highest-wins (B is not behind A)', ca and all(cb.get(k, 0) >= v for k, v in ca.items()), (ca, cb))
            await B.wait(3000)
            check('B: holding the same coins, B publishes nothing more (no ping-pong)', len(relay_events(7375)) == n7 and len(relay_events(17375)) == n17, (n7, len(relay_events(7375))))
            r = await pull(B)
            check('B: syncing again adds nothing (idempotent)', r and r.get('adopted') == 0 and await B.bal() == 1000, r)
            await ledger('two devices in sync', [A, B])
        await section('onb', on_b)

        async def auto():
            ok = await deposit(A, 200)
            check('auto: A deposits 200 more with sync on', ok)
            ok = await on_relay(A)
            check('auto: published on its own after the deposit settled', ok)
            await A.wait(1500)
            check('auto: the old coin event was replaced (kind 5 deletes it; one coin event left)', len(relay_events(7375)) == 1 and relay_events(5), (len(relay_events(7375)), len(relay_events(5))))
            r = await pull(B)
            check('auto: B syncs and has 1200, like A', await B.bal() == await A.bal() == 1200 and r and r.get('adopted') == 200, (await B.bal(), r))
            await ledger('after a deposit on A', [A, B])
        await section('auto', auto)

        async def spend():
            b_old = await coins(B)
            r = await A.ev("Nutcade.r8.sendEcash(300, 'to carol').then(t=>t.id, e=>'err:'+e.message)")
            check('spend: A makes a 300 SAT token', not str(r).startswith('err'), r)
            await A.until("!Nutcade.S.ops.length", 10000)
            ok = False
            for _ in range(40):
                rs = await relay_secrets(); mine = {q['secret'] for q in await coins(A)}
                if mine <= rs and not ({q['secret'] for q in b_old} - mine) & rs: ok = True; break
                await A.wait(500)
            check('spend: A publishes its new coins and the spent ones leave the relay', ok)
            st = await A.ev(f"NutSync.states({J(M)}, {J(b_old)})")
            check('spend: some of the coins B still shows are now spent at the mint', 'SPENT' in st, st)
            bb0, n0 = await B.bal(), await B.ev("Nutcade.S.txs.length")
            r = await B.ev("Nutcade.r8.sendEcash(1200, 'stale').then(t=>'ok', e=>'err:'+e.message)")
            check('spend: B cannot spend the stale coins: the mint refuses them, the send fails', str(r).startswith('err'), r)
            spent_line = await lines(B, 'Ecash already spent elsewhere')
            check('spend: B dropped the spent coins with a line, and gained nothing', await B.bal() < bb0 and spent_line and not await B.ev("Nutcade.S.txs.some(t=>t.note==='stale'&&t.status!=='failed')"), (bb0, await B.bal(), spent_line))
            ok = await B.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) === {await A.bal()}", 25000)
            check('spend: after the "already spent" error, B syncs on its own and has what A has (900)', ok and await B.bal() == await A.bal() == 900, (await B.bal(), await A.bal()))
            tok = await tokens(A)
            check('spend: A\'s unclaimed token coins are not counted by B', not ({q['secret'] for q in tok} & {q['secret'] for q in await coins(B)}))
            w17 = relay_events(17375)
            wc = await A.ev(f"__syDec({J(words)}, {J(w17[0]['content'])})") if w17 else []
            hs = set(await A.ev(f"{J([q['secret'] for q in tok])}.map(s=>NutSync.hash(s))"))
            check('spend: the wallet event marks the token\'s coins as gone (hashed), for the other device and a restore', hs and hs <= {t[1] for t in wc if t[0] == 'gone'}, len(hs))
            await ledger('after A spent and B tried the stale coins', [A, B])
        await section('spend', spend)

        async def race():
            await pull(A); await pull(B)
            check('race: (both hold the same 900)', await A.bal() == await B.bal() == 900, (await A.bal(), await B.bal()))
            ra, rb = await asyncio.gather(A.ev("Nutcade.r8.sendEcash(600, 'race A').then(t=>'ok', e=>'err:'+e.message)"), B.ev("Nutcade.r8.sendEcash(600, 'race B').then(t=>'ok', e=>'err:'+e.message)"))
            ta = {q['secret'] for q in await A.ev("Nutcade.S.txs.filter(t=>t.note==='race A').flatMap(t=>t.sent||[]).map(p=>({secret:p.secret}))")}
            tb = {q['secret'] for q in await B.ev("Nutcade.S.txs.filter(t=>t.note==='race B').flatMap(t=>t.sent||[]).map(p=>({secret:p.secret}))")}
            # (the same coins and the same NUT-13 counters on both make the very same request: the mint does it once, and the
            # device that comes second gets the mint's own answer back (NUT-09): both then show the one token, never two)
            check('race: both spend 600 of the same 900 at once: exactly one succeeds, or both made the very same request and hold the one token', [ra, rb].count('ok') == 1 or (ra == rb == 'ok' and ta and ta == tb), (ra, rb, len(ta), len(tb), ta == tb))
            for _ in range(3):
                await A.until("!Nutcade.S.ops.length", 15000); await B.until("!Nutcade.S.ops.length", 15000)
                await A.wait(2500); await pull(A); await pull(B); await A.wait(2500)
                if await A.bal() == await B.bal(): break
            check('race: after syncing, both devices show the same 300', await A.bal() == await B.bal() == 300, (await A.bal(), await B.bal()))
            await ledger('after the race', [A, B])
            # different amounts: different requests at the same counters; the mint takes one, the other is told "already
            # signed" or "already spent"; the device that loses must never count the winner's new token
            ok = await deposit(A, 600); await on_relay(A); await pull(B)
            check('race 2: (both hold the same 900 again)', ok and await A.bal() == await B.bal() == 900, (await A.bal(), await B.bal()))
            ra, rb = await asyncio.gather(A.ev("Nutcade.r8.sendEcash(600, 'race2 A').then(t=>'ok', e=>'err:'+e.message)"), B.ev("Nutcade.r8.sendEcash(700, 'race2 B').then(t=>'ok', e=>'err:'+e.message)"))
            check('race 2: 600 on A and 700 on B of the same 900 at once: exactly one succeeds', [ra, rb].count('ok') == 1, (ra, rb))
            for _ in range(4):
                await A.until("!Nutcade.S.ops.length", 15000); await B.until("!Nutcade.S.ops.length", 15000)
                await A.wait(2500); await pull(A); await pull(B); await A.wait(2500)
                if await A.bal() == await B.bal(): break
            tok = {q['secret'] for q in await tokens(A)} | {q['secret'] for q in await tokens(B)}
            check('race 2: after syncing, both devices show the same, and neither counts the winner\'s token', await A.bal() == await B.bal() and not (tok & ({q['secret'] for q in await coins(A)} | {q['secret'] for q in await coins(B)})), (await A.bal(), await B.bal()))
            await ledger('after race 2', [A, B])
        await section('race', race)

        async def crash():
            await pull(A); await pull(B)
            a0 = await A.bal()
            async def held(route):
                try: r = await route.fetch()
                except Exception: return
                await asyncio.sleep(6)
                try: await route.fulfill(response=r)
                except Exception: pass
            await A.pg.route('**/v1/swap', held)
            task = asyncio.ensure_future(A.pg.evaluate("Nutcade.r8.sendEcash(100, 'crash').then(()=>'ok', e=>'err')"))
            await asyncio.sleep(2.5)   # (the mint has done the swap; its answer has not reached A)
            r = await pull(B)
            check('crash: while A\'s answer is lost, B can sync: nothing is added, nothing published by A yet', r and r.get('adopted') == 0 and await B.bal() <= a0, (await B.bal(), a0, r))
            await ledger('crash: in the middle (the new coins are not written anywhere yet)', [A, B], strict=False)
            await A.pg.reload(); await A.pg.unroute('**/v1/swap')
            try: await asyncio.wait_for(task, 2)
            except BaseException: pass
            await A.wait(800); await A.use(M)
            ok = await A.until("!Nutcade.S.ops.length", 30000); await A.wait(1500)
            tk = await A.ev("Nutcade.S.txs.some(t=>t.note==='crash'&&t.status==='pending'&&t.token)")
            check('crash: after the reload, A settles the spend from its journal: nothing lost (the token, or all of it back in the balance)', ok and (await A.bal() == a0 - 100 if tk else await A.bal() == a0), (ok, tk, await A.bal(), a0))
            ok = await on_relay(A)
            r = await pull(B)
            check('crash: then B syncs and has what A has', ok and await B.bal() == await A.bal(), (await B.bal(), await A.bal(), r))
            await ledger('after the crash and sync', [A, B])
        await section('crash', crash)

        async def relay():
            bb, nt = await B.bal(), await B.ev("Nutcade.S.txs.length")
            mode(dup=True, reorder=True)
            r1 = await pull(B); r2 = await pull(B)
            check('relay: events sent twice and out of order change nothing', r1 and r2 and r1.get('adopted') == 0 and r2.get('adopted') == 0 and await B.bal() == bb and await B.ev("Nutcade.S.txs.length") == nt, (r1, r2))
            mode(drop=True, kinds=list(SYNC_KINDS))
            ok = await deposit(A, 128); await A.wait(5000)
            r = await pull(B)
            check('relay: a relay that says OK and keeps nothing: B gets nothing yet, loses nothing', ok and await B.bal() == bb, (await B.bal(), bb))
            mode()
            await pull(A); ok = await on_relay(A)
            r = await pull(B)
            check('relay: A notices its coins are missing from the relay, publishes again, and B gets the 128', ok and await B.bal() == bb + 128 == await A.bal(), (await B.bal(), bb, await A.bal()))
            post('/test/forget', {'ids': [e['id'] for e in relay_events(7375)]})
            r = await pull(B)
            check('relay: a relay that loses every coin event: B keeps its coins (nothing spent, nothing dropped)', await B.bal() == bb + 128, (await B.bal(), r))
            ok = await on_relay(B)
            check('relay: and B publishes its coins again', ok)
            # replay: old events (already replaced) served again, with the deletions hidden
            post('/test/forget', {'ids': [e['id'] for e in relay_events(5)]})
            for e in ctx.get('old7375', []): post('/test/inject', {'event': e})
            ra, rb = await pull(A), await pull(B)
            check('relay: old, replaced events replayed (their deletion hidden): their coins are spent, nothing is added', await B.bal() == bb + 128 == await A.bal() and ra and rb and ra.get('adopted') == 0 and rb.get('adopted') == 0, (await A.bal(), await B.bal(), ra, rb))
            await ledger('after the relay misbehaved', [A, B])
        await section('relay', relay)

        async def forged():
            await pull(B)
            bb, nm, nt = await B.bal(), await B.ev("Nutcade.S.mints.length"), await B.ev("Nutcade.S.txs.length")
            real = (await coins(A))[0]
            real_d = await A.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).find(p=>p.secret==={J(real['secret'])}).dleq")
            live_ids = ((await B.ev("NutSync.state()")).get('view') or {}).get('live') or []
            live = [e for e in relay_events(7375) if e['id'] in live_ids] or relay_events(7375)   # (an event B reads as live, not an old replaced one)
            mk = lambda js: A.ev(js)
            coin = lambda **k: J(dict({'id': real['id'], 'amount': real['amount'], 'C': real['C'], 'dleq': real_d}, **k))
            W_ = J(words)
            sent = []
            async def pub(js):
                e = await mk(js); sent.append(e); return await A.ev(f"__syPublish({J(e)})")
            await pub(f"__syEv({W_}, 7375, 'hello, not encrypted')")
            await pub(f"__syEv({W_}, 7375, __syEnc({W_}, 'not json'))")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:'x'}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:Array.from({{length:150}}, ()=>Object.assign({coin()}, {{secret:__syRnd()}}))}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin(amount=3)}, {{secret:__syRnd()}})]}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:'x'.repeat(600)}})]}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:JSON.stringify(['P2PK',{{nonce:'00',data:'02'+'11'.repeat(32),tags:[]}}])}})]}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin(C='04' + 'ab' * 32)}, {{secret:__syRnd()}})]}})")
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:__syRnd()}})]}})")   # (a made-up coin: someone else's DLEQ proof)
            await pub(f"__syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin(id='00ffffffffffffff')}, {{secret:__syRnd()}})]}})")   # (a keyset the mint never had)
            await pub(f"(()=>{{const c={coin()}; delete c.dleq; c.secret=__syRnd(); return __syEv({W_}, 7375, {{mint:{J(M)}, unit:'sat', proofs:[c]}})}})()")   # (no DLEQ proof: can't be checked)
            await pub(f"__syEv({W_}, 7375, {{mint:{J(OTHER)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:__syRnd()}})]}})")
            await pub(f"__syEv({W_}, 7375, 'x'.repeat(130000))")
            await pub(f"__syEv({W_}, 17375, __syEnc({W_}, 'not json'), [], -5)")
            # a lying relay: a copy of a real event with other content (signature no longer matches), and a forged kind 5
            fake = dict(live[0]); fake['id'] = 'f' * 64; fake['content'] = await A.ev(f"__syEnc({W_}, JSON.stringify({{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:__syRnd()}})]}}))")
            post('/test/inject', {'event': fake, 'raw': True})
            ctx['unreadable'] = {sent[0]['id'], sent[1]['id'], sent[12]['id'], fake['id']}   # (events NUTCADE can't read: never deleted by it)
            k5 = dict(sent[0]); k5.update({'kind': 5, 'tags': [['e', live[0]['id']]], 'content': ''})
            post('/test/inject', {'event': k5, 'raw': True})
            other_author = await A.ev(f"CashuLib.finalizeEvent({{kind:7375, created_at:Math.floor(Date.now()/1000), tags:[], content:__syEnc({W_}, JSON.stringify({{mint:{J(M)}, unit:'sat', proofs:[Object.assign({coin()}, {{secret:__syRnd()}})]}}))}}, crypto.getRandomValues(new Uint8Array(32)))")
            post('/test/inject', {'event': other_author})
            r = await pull(B)
            check('forged: garbage, oversized, malformed, made-up and wrongly signed events add nothing to B', await B.bal() == bb and r and r.get('adopted') == 0 and r.get('bad', 0) >= 10, (await B.bal(), bb, r))
            check('forged: coins that can\'t be checked (no DLEQ proof, unknown keyset) are left out and counted as unchecked', r and r.get('unchecked', 0) >= 2, r)
            check('forged: a deletion with a forged signature is ignored (the real event is still read as live)', r and live[0]['id'] in (r.get('ids') or []), (live[0]['id'][:12], r and r.get('ids')))
            check('forged: no mint is added by itself', await B.ev("Nutcade.S.mints.length") == nm and await B.ev("Nutcade.S.txs.length") == nt)
            await settings(B); t = await priv(B)
            check('forged: coins at another mint are only shown, with a question (its address escaped, an Add button)', 'mint you don\'t use' in t and '127.0.0.1:3338' in t and await B.ev("!!document.querySelector('[data-act=syncAddMint]')"), t[-500:])
            ra = await pull(A)
            check('forged: A is not fooled either, and publishes nothing over them', await A.bal() == bb and ra and ra.get('adopted') == 0, (await A.bal(), ra))
            check('forged: no page errors on either device', not [x for x in A.errs + B.errs if 'PAGEERROR' in x], [x for x in A.errs + B.errs if 'PAGEERROR' in x][:3])
            await ledger('after forged events', [A, B])
        await section('forged', forged)

        async def restore_new():
            a = await A.bal()
            D = await restore(b, 'sy-D', words); ctx['D'] = D
            check('restore: on a new device from the 12 words, sync is found and stays on', await D.ev("Nutcade.S.prefs.sync") is True)
            check('restore: the balance is exactly A\'s (coins from the relays; the scan after it adds nothing twice; A\'s unclaimed tokens not counted)', await D.bal() == a, (await D.bal(), a))
            check('restore: a "From your other device (wallet sync)" line, and nothing "Recovered" on top', (await lines(D, 'From your other device (wallet sync)')) and not await lines(D, 'Recovered with recovery phrase'), (await lines(D, 'From your other device (wallet sync)'), await lines(D, 'Recovered with recovery phrase')))
            ca, cd = await A.ev("Nutcade.S.counters"), await D.ev("Nutcade.S.counters")
            check('restore: the counters are not behind A\'s', all(cd.get(k, 0) >= v for k, v in ca.items()), (ca, cd))
            await ledger('after the restore (three devices)', [A, B, D])
            await D.pg.context.close()
        await section('restore', restore_new)

        async def paused():
            n = len(state()['events']); rq = len(state()['reqs'])
            p2 = await A.pg.context.new_page(); await p2.goto(URL); await p2.wait_for_timeout(1500)
            w2 = W(p2, 'sy-A2')
            locked = await w2.ev("!!document.querySelector('[data-act=takeover]') || /another tab|open in another/i.test(document.body.innerText)")
            r1 = await w2.ev("NutSync.push().then(r=>r, e=>'err')"); r2 = await w2.ev("NutSync.pull().then(r=>r, e=>'err')")
            check('paused: a tab paused because NUTCADE is open in another tab publishes and reads nothing', locked and not r1 and r2 is None and len(state()['events']) == n, (locked, r1, r2, n, len(state()['events'])))
            await p2.close()
        await section('paused', paused)

        async def duress():
            e = await wallet(b, 'sy-ed'); await e.create(); await e.add_mint(M); await e.use(M); await e.receive_ln(1000)   # (another wallet: not in the ledger)
            await set_pin(e)
            await settings(e); await e.click('[data-act=duressOpen]'); await e.wait(250)
            await pad(e, PIN); await e.wait(800); await pad(e, DPIN); await e.wait(300); await pad(e, DPIN); await e.until("!!document.querySelector('#duressAmt')", 8000)
            await e.fill('#duressAmt', '100'); await e.click('[data-act=duressMake]'); await e.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await e.ev("Nutcade.closeSheet()")
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            dpk = await e.ev("Nutcade.S.seed ? NutSync.pk() : null")
            n = len([x for x in state()['events'] if x['kind'] in SYNC_KINDS])
            await settings(e); await e.click('#p_sync'); await e.wait(1000)
            s1 = await priv(e); await e.wait(8500); await settings(e); s2 = await priv(e)
            r = await e.ev("NutSync.pull().then(r=>r, e=>'err')"); await e.ev("NutSync.push().catch(()=>0)")
            await e.wait(2500)
            reads = [f for fs in state()['reqs'] for f in fs if dpk and dpk in (f.get('authors') or [])]
            check('duress: the duress wallet\'s switch looks like a wallet whose relays don\'t answer', await e.ev("Nutcade.S.prefs.sync") is True and 'SYNCING' in s1 and "RELAYS DIDN'T ANSWER" in s2, (s1[-200:], s2[-200:]))
            check('duress: it never publishes and never reads (no event, no REQ for its sync key)', r is None and len([x for x in state()['events'] if x['kind'] in SYNC_KINDS]) == n and not (dpk and evs(None, dpk)) and not reads, (r, dpk and dpk[:12], len(reads)))
            await e.pg.context.close()
        await section('duress', duress)

        async def off2():
            await settings(B); await B.click('#p_sync'); await B.wait(400)
            t = await B.sheet_text()
            check('off: turning sync off offers (does not force) deleting our events from the relays', 'delete them from my relays' in t.lower() and 'keep them' in t.lower(), t[:300])
            n7 = len(relay_events(7375))
            await B.click('[data-act=close]'); await B.wait(300)
            check('off: "Keep them" deletes nothing', len(relay_events(7375)) == n7 and n7 > 0)
            ok = await deposit(B, 64); await B.wait(4000)
            mine = {q['secret'] for q in await coins(B)}
            check('off: with sync off, B publishes nothing more (its new coins are not on the relay)', ok and not mine <= await relay_secrets() and not await B.ev("NutSync.live()"))
            ab, bb = await A.bal(), await B.bal()
            await settings(A); await A.click('#p_sync'); await A.wait(400)
            await A.click('[data-act=syncDelete]')
            ok = await A.until("!document.querySelector('[data-act=syncDelete]')", 20000); await A.wait(500)
            left = {e['id'] for e in relay_events(7375)}
            check('off: "Delete them from my relays" removes our coin and wallet events (only events it could not read are left alone)', ok and left <= ctx.get('unreadable', set()) and not relay_events(17375), (len(left), len(relay_events(17375))))
            check('off: deleting from the relays never touches the coins on the devices', await A.bal() == ab and await B.bal() == bb, (await A.bal(), ab, await B.bal(), bb))
            await ledger('at the end', [A, B])
        await section('off2', off2)

        async def langs():
            for lang in ('es', 'pt', 'de', 'fr'):
                x = await wallet(b, 'sy-' + lang, lang); await x.create(); await x.add_mint(M); await x.use(M)
                await settings(x); await x.click('#p_sync'); await x.until("NutSync.state().view !== null", 15000); await settings(x)
                t = await priv(x)
                await x.click('#p_sync'); await x.wait(400); st = await x.sheet_text(); await x.ev("Nutcade.closeSheet()")
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/sync|relays|other device|Sync now|IN SYNC|SYNCING|NOT YET|Keep them|Delete them/i.test(s))")
                check(f'{lang}: the sync texts show translated, with no missing translation', 'Sync this wallet' not in t and 'Sync now' not in t and 'Keep them' not in st and not miss, (t[-200:], st[:100], miss))
                await x.pg.context.close()
        await section('langs', langs)

        errs = [x for x in A.errs + B.errs if 'PAGEERROR' in x]
        check('no page errors', not errs, errs[:3])
        await A.pg.screenshot(path=os.path.join(OUT, 'sync.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
