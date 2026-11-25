"""Nutzaps (1.28.0, NIP-61): your nutzap info (kind 10019) and nutzaps (kind 9321), sent and received.
Uses the local test mint 3339 (no fees, so amounts are exact) and the stand-in Nostr relay (mock_nostr.py, port 3350).

Off by default (nothing published, nothing listened to); turned on, the wallet publishes kind 10019 with its relays, its
mints and a P2PK receiving key derived from the 12 words on its own path (not the Nostr key); a nutzap sent to a contact
picks a mint both sides accept, locks every proof to the recipient's key, is published as kind 9321 to the recipient's
relays and recorded in history; it is received (live), checked, claimed once and shown with its sender. Refused or
ignored: a recipient without a 10019 (nothing spent, nothing published), a duplicate event (the same event again, a
copy re-signed by someone else, after a reload), proofs not locked to the receiving key (unlocked, or locked to someone
else), a mint the receiver doesn't trust. Mint down while receiving: recorded as waiting, never credited until the mint
swaps it, then credited once; mint down while sending: nothing lost. Relays down while sending: kept and published
later, once. A crash mid-send (the mint swapped, its answer lost, the page reloaded): the locked coins come back from the
journal as the nutzap they were going to be, are published once, received once. Restore from the 12 words: the same key
is derived again, and nutzaps that arrived while the wallet was away are found and claimed (old, already claimed ones are
skipped, never shown). The duress PIN's wallet has no nutzaps ("aren't available right now"), the real wallet keeps them.
The new texts in five languages with no missing translation.
NZ_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from r8_qa import set_pin, unlock, pad, PIN, DPIN

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
PATH = "m/129372'/61'/0'/0'/0'"

def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def evs(kind, author=None, p=None):
    out = []
    for e in state()['events']:
        if e['kind'] != kind or (author and e['pubkey'] != author): continue
        if p and not any(t[0] == 'p' and t[1] == p for t in e['tags']): continue
        out.append(e)
    return out
def tags(e, k): return [t for t in e['tags'] if t and t[0] == k]

HELPERS = """
window.__nzEv = (proofs, x) => CashuLib.finalizeEvent({ kind: 9321, created_at: Math.floor(Date.now() / 1000) + (x.dt || 0), content: x.c || '',
  tags: proofs.map(p => ['proof', JSON.stringify(Object.assign({ id: p.id, amount: Number(String(p.amount)), secret: p.secret, C: p.C }, p.dleq && x.dleq !== false ? { dleq: p.dleq } : {}))]).concat([['u', x.u], ['unit', 'sat'], ['p', x.p]]) }, crypto.getRandomValues(new Uint8Array(32)));
window.__nzPublish = ev => new Promise(r => { const ws = new WebSocket(%s); ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d[0] === 'OK') { try { ws.close(); } catch (e) {} r(d[2]); } }; setTimeout(() => r(false), 5000); });
""" % J(RELAY)

async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    await ctx.add_init_script(HELPERS)
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def section(name, fn):
    only = [x for x in os.environ.get('NZ_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
async def nz_on(w):
    await settings(w)
    if not await w.ev("document.querySelector('#p_nutzap').checked"): await w.click('#p_nutzap')
    me = await w.ev("NutZap.me()")
    return await w.until(f"NutZap.info() && NutZap.info().pub === NutZap.pub()", 15000) and me
async def me(w): return await w.ev("NutZap.me()")
async def nz_in(w): return await w.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.nz).map(t=>({id:t.id, status:t.status, amount:t.amount, note:t.note, from:t.nz.from, ev:t.nz.id}))")
async def nz_out(w): return await w.ev("Nutcade.S.txs.filter(t=>t.type==='out'&&t.nz).map(t=>({id:t.id, status:t.status, amount:t.amount, note:t.note, delivered:!!t.delivered, locked:t.locked, ev:t.nz.ev&&t.nz.ev.id, to:t.nz.to}))")
def held(delay):   # the mint does it at once; its answer reaches the page `delay` s later (or never, after a reload)
    async def h(route):
        try: r = await route.fetch()
        except Exception: return
        await asyncio.sleep(delay)
        try: await route.fulfill(response=r)
        except Exception: pass
    return h
async def down(route):
    try: await route.abort()
    except Exception: pass

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al = await wallet(b, 'nz-alice'); await al.create(); await al.add_mint(M); await al.use(M)
        bo = await wallet(b, 'nz-bob'); bob_words = await bo.create(); await bo.add_mint(M); await bo.use(M)
        ok = await al.receive_ln(5000)
        check('setup: the sender has sats', ok)
        A_PK, B_PK = await me(al), await me(bo)
        ctx = {}

        async def off():
            check('off: nutzaps are off by default', await bo.ev("Nutcade.S.prefs.nutzap") is False)
            check('off: nothing is published (no kind 10019) and nothing listened to', not evs(10019, B_PK) and await bo.ev("NutZap.live()") == 0)
        await section('off', off)

        async def publish():
            await nz_on(bo)
            e = (evs(10019, B_PK) or [None])[-1]
            check('publish: turning it on publishes kind 10019, signed with the Nostr key', e is not None, len(evs(10019, B_PK)))
            pub = await bo.ev("NutZap.pub()"); ctx['bpub'] = pub
            check('publish: relay tags are the wallet\'s relays', e and [t[1] for t in tags(e, 'relay')] == [RELAY], e and e['tags'])
            check('publish: mint tags are the wallet\'s mints, with the unit sat', e and tags(e, 'mint') == [['mint', M, 'sat']], e and e['tags'])
            check('publish: one pubkey tag, the P2PK receiving key ("02" + x, 66 hex)', e and tags(e, 'pubkey') == [['pubkey', pub]] and re.fullmatch(r'02[0-9a-f]{64}', pub or ''), (pub, e and e['tags']))
            check('publish: the receiving key is not the Nostr key', pub != '02' + B_PK)
            ind = await bo.ev(f"(()=>{{const k=CashuLib.HDKey.fromMasterSeed(CashuLib.mnemonicToSeedSync({J(bob_words)})).derive({J(PATH)}); return CashuLib.bytesToHex(k.publicKey).slice(2)}})()")
            check(f'publish: the key is derived from the 12 words at {PATH} (x-only key matches)', pub[2:] == ind, (pub, ind))
            check('publish: Settings says it is published', 'PUBLISHED' in await bo.ev("document.querySelector('#set-privacy').innerText"))
            check('publish: it listens for nutzaps', await bo.until("NutZap.live() > 0", 8000))
        await section('publish', publish)

        async def norecip():
            ca = await wallet(b, 'nz-carol'); await ca.create(); await ca.add_mint(M); C_PK = await me(ca); ctx['carol'] = ca
            bal0, n0, z0 = await al.bal(), await al.ev("Nutcade.S.txs.length"), len(evs(9321))
            r = await al.ev(f"NutZap.send({{pubkey:{J(C_PK)}, name:'Carol'}}, 50, 'hi').then(()=>'sent', e=>e.message)")
            check('no 10019: a recipient who never published nutzap info is refused with a plain message', "can't receive nutzaps" in r, r)
            check('no 10019: nothing spent, no line, nothing published', await al.bal() == bal0 and await al.ev("Nutcade.S.txs.length") == n0 and len(evs(9321)) == z0 and await al.ev("Nutcade.S.ops.length") == 0)
            await al.ev(f"NutZap.open({{pubkey:{J(C_PK)}, name:'Carol'}})")
            await al.until("/can't receive nutzaps/.test(document.querySelector('#layer').innerText)", 10000)
            txt = await al.sheet_text()
            check('no 10019: the nutzap screen says so and offers nothing to send', "can't receive nutzaps" in txt and not await al.ev("!!document.querySelector('[data-act=nzSend]')"), txt[:200])
            await al.ev("Nutcade.closeSheet()")
        await section('norecip', norecip)

        async def send():
            npub = await al.ev(f"CashuLib.npubEncode({J(B_PK)})")
            await al.home(); await al.ev(f"Nutcade.handleScan({J(npub)})"); await al.until("!!document.querySelector('#cName')", 5000)
            await al.fill('#cName', 'Bob'); await al.click('[data-act=contactSave]'); await al.wait(300)
            await al.until("!!document.querySelector('[data-act=payContact]')", 5000); await al.click('[data-act=payContact]'); await al.wait(200)
            check('send: the contact\'s pay screen offers "Send a nutzap"', await al.ev("!!document.querySelector('[data-act=nzOpen]')"))
            await al.click('[data-act=nzOpen]'); await al.until("!!document.querySelector('[data-act=nzSend]')", 10000)
            txt = await al.sheet_text()
            check('send: the nutzap screen names the mint both take and says it is public', 'public on Nostr' in txt and '127.0.0.1:3339' in txt, txt[:300])
            ab0, bb0 = await al.bal(), await bo.bal()
            await al.fill('#amtIn', '100'); await al.fill('#nzComment', 'thanks'); await al.click('[data-act=nzSend]')
            got = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 100}", 25000); await al.wait(500)
            o = await nz_out(al)
            check('send: 100 SAT left the sender (no-fee mint), one history line "Nutzap to Bob", delivered', await al.bal() == ab0 - 100 and len(o) == 1 and o[0]['amount'] == 100 and o[0]['note'] == 'Nutzap to Bob' and o[0]['delivered'], (ab0, await al.bal(), o))
            check('send: the line is locked to the receiving key from Bob\'s 10019', o and o[0]['locked'] == ctx.get('bpub'), o)
            z = [e for e in evs(9321, A_PK, B_PK)]
            check('send: one kind 9321 on Bob\'s relay, signed by the sender\'s Nostr key', len(z) == 1 and o and z[0]['id'] == o[0]['ev'], (len(z), o))
            if z:
                e = z[0]; ps = [json.loads(t[1]) for t in tags(e, 'proof')]
                locks = [json.loads(p['secret']) for p in ps]
                check('send: tags u (the mint exactly as in the 10019), unit sat, p (Bob), comment as content', tags(e, 'u') == [['u', M]] and tags(e, 'unit') == [['unit', 'sat']] and tags(e, 'p') == [['p', B_PK]] and e['content'] == 'thanks', e['tags'][-3:])
                check('send: every proof is P2PK-locked to Bob\'s receiving key, 100 SAT in all', ps and all(l[0] == 'P2PK' and l[1]['data'] == ctx.get('bpub') for l in locks) and sum(p['amount'] for p in ps) == 100, locks[:1])
                check('send: the proofs carry their DLEQ proofs', all('dleq' in p for p in ps), list(ps[0].keys()) if ps else None)
                ctx['ev1'] = e
            i = await nz_in(bo)
            check('receive: Bob got exactly 100 SAT, once', got and await bo.bal() == bb0 + 100 and len(i) == 1, (await bo.bal() - bb0, i))
            check('receive: his line says who sent it, with the comment', i and i[0]['status'] == 'done' and i[0]['note'].startswith('Nutzap from npub1') and i[0]['note'].endswith(': "thanks"') and i[0]['from'] == A_PK, i)
            check('receive: nothing is left waiting', not await bo.ev("Nutcade.S.txs.some(t=>t.status==='pending'&&t.incoming)"))
            check('send/receive: no page errors', not al.errs and not bo.errs, (al.errs[:3], bo.errs[:3]))
        await section('send', send)

        async def dup():
            e = ctx['ev1']; bb0, n0 = await bo.bal(), len(await nz_in(bo))
            r1 = await bo.ev(f"NutZap.event({J(e)})")
            check('dup: the same event again is skipped (seen)', r1 == 'seen' and await bo.bal() == bb0, r1)
            ps = [json.loads(t[1]) for t in tags(e, 'proof')]
            e2 = await al.ev(f"__nzEv({J(ps)}, {{u:{J(M)}, p:{J(B_PK)}, c:'again', dt:1}})")
            await al.ev(f"__nzPublish({J(e2)})"); await bo.wait(2000)
            r2 = await bo.ev(f"NutZap.event({J(e2)})")
            check('dup: a new event carrying the same proofs credits nothing and adds no line', await bo.bal() == bb0 and len(await nz_in(bo)) == n0, (r2, await bo.bal() - bb0))
            await bo.pg.reload(); await bo.wait(3500)
            check('dup: after a reload (the seen list is kept) the relay\'s events credit nothing again', await bo.bal() == bb0 and len(await nz_in(bo)) == n0 and await bo.ev(f"NutZap.seen().includes({J(e['id'])})"))
        await section('dup', dup)

        async def wronglock():
            bb0, n0 = await bo.bal(), len(await nz_in(bo))
            other = '02' + 'a' * 64
            t1 = await al.ev(f"Nutcade.r8.sendEcash(30, 'nz wrong lock', {J(await al.ev('NutZap.randomPub()'))}).then(t=>t.sent)")
            t2 = await al.ev("Nutcade.r8.sendEcash(40, 'nz unlocked', null).then(t=>t.sent)")
            e1 = await al.ev(f"__nzEv({J(t1)}, {{u:{J(M)}, p:{J(B_PK)}}})"); e2 = await al.ev(f"__nzEv({J(t2)}, {{u:{J(M)}, p:{J(B_PK)}}})")
            await al.ev(f"__nzPublish({J(e1)})"); await al.ev(f"__nzPublish({J(e2)})"); await bo.wait(2500)
            check('wrong lock: proofs locked to another key and unlocked proofs, sent over the relay, credit nothing, add no line', await bo.bal() == bb0 and len(await nz_in(bo)) == n0 and not await bo.ev("Nutcade.S.txs.some(t=>t.status==='pending'&&t.incoming)"), await nz_in(bo))
            e3 = await al.ev(f"__nzEv({J(t1)}, {{u:{J(M)}, p:{J(B_PK)}, dt:2}})"); e4 = await al.ev(f"__nzEv({J(t2)}, {{u:{J(M)}, p:{J(B_PK)}, dt:2}})")
            r = [await bo.ev(f"NutZap.event({J(e3)})"), await bo.ev(f"NutZap.event({J(e4)})")]
            check('wrong lock: both are refused as not locked to this wallet\'s key', r == ['lock', 'lock'], r)
            ctx['plain'] = t2
        await section('wronglock', wronglock)

        async def untrusted():
            bb0, n0 = await bo.bal(), len(await nz_in(bo))
            ps = await al.ev(f"Nutcade.r8.sendEcash(25, 'nz untrusted', {J(ctx.get('bpub'))}).then(t=>t.sent)")
            e1 = await al.ev(f"__nzEv({J(ps)}, {{u:'http://127.0.0.1:3338', p:{J(B_PK)}}})")
            await al.ev(f"__nzPublish({J(e1)})"); await bo.wait(2000)
            e2 = await al.ev(f"__nzEv({J(ps)}, {{u:'http://127.0.0.1:3338', p:{J(B_PK)}, dt:3}})")
            r = await bo.ev(f"NutZap.event({J(e2)})")
            check('untrusted mint: a nutzap at a mint not in the 10019 is ignored: no line, no credit, the mint is not added',
                  r == 'untrusted' and await bo.bal() == bb0 and len(await nz_in(bo)) == n0 and not await bo.ev("Nutcade.S.mints.some(m=>m.url==='http://127.0.0.1:3338')"), r)
        await section('untrusted', untrusted)

        async def hardening():
            # (fix round 1) the receiver proves coins are the mint's before anything becomes a line
            bb0, n0 = await bo.bal(), len(await nz_in(bo)); bpub = ctx.get('bpub')
            ps = await al.ev(f"Nutcade.r8.sendEcash(20, 'nz hard', {J(bpub)}).then(t=>t.sent)")
            rp = await al.ev("NutZap.randomPub()")
            async def ev_of(proofs, **x):
                return await al.ev(f"__nzEv({J(proofs)}, Object.assign({{u:{J(M)}, p:{J(B_PK)}}}, {J(x)}))")
            async def res(proofs, **x): return await bo.ev(f"NutZap.event({J(await ev_of(proofs, **x))})")
            forged = [dict(p, C=rp) for p in ps]
            r = {'forged': await res(forged), 'noproof': await res(ps, dleq=False),
                 'keyset': await res([dict(p, id='00ffffffffffffff') for p in ps]),
                 'many': await res([dict(ps[0], secret=json.dumps(['P2PK', {'nonce': '%064x' % i, 'data': bpub}])) for i in range(65)]),
                 'long': await res([dict(ps[0], secret=json.dumps(['P2PK', {'nonce': 'a' * 600, 'data': bpub}]))])}
            check('hardening: coins whose DLEQ proof is wrong (made up) are refused as forged', r['forged'] == 'forged', r)
            check('hardening: coins without a DLEQ proof are refused', r['noproof'] == 'noproof', r)
            check('hardening: coins on a keyset that is not one of the mint\'s sat keysets are refused', r['keyset'] == 'keyset', r)
            check('hardening: more than 64 coins, or a secret over 512 characters, are refused', r['many'] == 'bad' and r['long'] == 'bad', r)
            check('hardening: none of them became a line or credited anything', await bo.bal() == bb0 and len(await nz_in(bo)) == n0 and not await bo.ev("Nutcade.S.txs.some(t=>t.incoming&&t.status==='pending')"))
            # the lock: only a plain P2PK lock to the receiving key
            def sec(tags): return json.dumps(['P2PK', {'nonce': 'ab' * 32, 'data': bpub, 'tags': tags}])
            ok_t = [[], [['sigflag', 'SIG_INPUTS']], [['sigflag', 'SIG_INPUTS'], ['n_sigs', '1']]]
            bad_t = [[['locktime', '1700000000']], [['refund', rp]], [['pubkeys', rp]], [['n_sigs', '2']], [['sigflag', 'SIG_ALL']], [['sigflag', 'SIG_INPUTS'], ['sigflag', 'SIG_ALL']], [['sigflag', 'SIG_INPUTS', 'x']]]
            lk_ok = [await bo.ev(f"NutZap.lock({J(sec(t))})") for t in ok_t]; lk_bad = [await bo.ev(f"NutZap.lock({J(sec(t))})") for t in bad_t]
            check('lock: no tags, sigflag SIG_INPUTS, and n_sigs 1 are taken', all(x == bpub for x in lk_ok), lk_ok)
            check('lock: locktime, refund keys, other pubkeys, n_sigs 2, SIG_ALL and mixed sigflags are refused', all(x is None for x in lk_bad), lk_bad)
            r2 = await res([dict(ps[0], secret=sec([['locktime', '1700000000']]))])
            check('lock: such a nutzap is refused as not locked to this wallet', r2 == 'lock', r2)
            # trust: only the mints used now (a mint once published is not trusted again by a nutzap), not kept as seen
            await bo.ev("Nutcade.S.prefs.nzInfo.mints.push('http://127.0.0.1:3338')")
            e3 = await ev_of(ps, u='http://127.0.0.1:3338', dt=5)
            r3 = await bo.ev(f"NutZap.event({J(e3)})")
            check('trust: a mint only in the info published before is not trusted, and the event is not kept as seen', r3 == 'untrusted' and not await bo.ev(f"NutZap.seen().includes({J(e3['id'])})") and not await bo.ev("Nutcade.S.mints.some(m=>m.url==='http://127.0.0.1:3338')"), r3)
            await bo.ev("Nutcade.S.prefs.nzInfo.mints=Nutcade.S.prefs.nzInfo.mints.filter(u=>u!=='http://127.0.0.1:3338')")
            # at most 20 nutzaps wait at once: more are looked at again later
            await bo.ev(f"for (let i=0;i<20;i++) Nutcade.S.txs.push({{id:'nzfake'+i, type:'in', method:'ecash', status:'pending', incoming:'cashuBfake'+i, amount:1, mint:{J(M)}, ts:Date.now(), nz:{{id:'f'+i, next:Date.now()+3600e3}}}})")
            good = await ev_of(ps, c='real', dt=6)
            r4 = await bo.ev(f"NutZap.event({J(good)})")
            check('cap: with 20 nutzaps already waiting, a new one is kept to look at later, no line', r4 == 'full' and await bo.ev("NutZap.waiting()") == 1 and await bo.bal() == bb0, r4)
            await bo.ev("Nutcade.S.txs=Nutcade.S.txs.filter(t=>!/^nzfake/.test(t.id))")
            await bo.ev("NutZap.tick(true)"); ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 20}", 20000)
            check('cap: once there is room it is taken: the real coins are credited, once', ok and await bo.bal() == bb0 + 20 and await bo.ev("NutZap.waiting()") == 0, await bo.bal() - bb0)
            # the mint turning a nutzap down while its coins are unspent: failed after 5 refusals, never credited; Try again works
            bb1 = await bo.bal(); SW = re.compile(re.escape(M) + r'/v1/swap$')
            async def refuse(route):
                try: await route.fulfill(status=400, content_type='application/json', body=J({'detail': 'nope', 'code': 11001}))
                except Exception: pass
            await bo.pg.route(SW, refuse)
            ps2 = await al.ev(f"Nutcade.r8.sendEcash(30, 'nz refused', {J(bpub)}).then(t=>t.sent)")
            r5 = await bo.ev(f"NutZap.event({J(await ev_of(ps2, dt=7))})")
            for _ in range(15):
                if await bo.ev("(Nutcade.S.txs.find(t=>t.type==='in'&&t.nz&&t.amount===30)||{}).status==='failed'"): break
                await bo.ev("NutZap.tick(true)"); await bo.wait(500)
            ln = await bo.ev("(Nutcade.S.txs.find(t=>t.type==='in'&&t.nz&&t.amount===30)||{})")
            check('refused: after 5 refusals with its coins unspent the line is marked failed, nothing credited', r5 == 'ok' and ln.get('status') == 'failed' and await bo.bal() == bb1, (r5, ln.get('status'), ln.get('nz')))
            await bo.pg.unroute(SW)
            await bo.ev(f"NutZap.claim({J(ln.get('id'))}).catch(e=>e.message)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb1 + 30}", 20000)
            check('refused: Try again claims it once the mint takes it (30 SAT, once)', ok and await bo.bal() == bb1 + 30 and not await bo.ev("Nutcade.S.txs.some(t=>t.nz&&t.type==='in'&&t.status!=='done')"), await bo.bal() - bb1)
            # comments: hashtags and quotes can't become history tags or pass for the app's text
            bb2 = await bo.bal()
            r6 = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 11, '#food \"Nutzap from Alice\" hi').then(x=>x.ok, e=>e.message)")
            await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb2 + 11}", 20000)
            note = await bo.ev("(Nutcade.S.txs.find(t=>t.type==='in'&&t.nz&&t.amount===11)||{}).note||''")
            check('comment: shown in quotes, without its hashtag or quote marks', r6 is True and '#' not in note and note.endswith(': "food Nutzap from Alice hi"'), note)
            # a 10019 with very many mints: only the first 32 are read
            e7 = await al.ev(f"""CashuLib.finalizeEvent({{kind:10019, created_at:Math.floor(Date.now()/1000), content:'', tags:[...Array(100).keys()].map(i=>['mint','https://m'+i+'.example','sat']).concat([['pubkey',{J(rp)}]])}}, crypto.getRandomValues(new Uint8Array(32)))""")
            await al.ev(f"__nzPublish({J(e7)})")
            f7 = await al.ev(f"NutZap.find({J(e7['pubkey'])}).then(x=>x.mints.length, e=>e.message)")
            check('10019: a list of 100 mints is read only up to 32', f7 == 32, f7)
        await section('hardening', hardening)

        async def taint():
            # (fix round 2) values from Nostr events: relays through one strict check, mints only as our own, keys own-only, text escaped
            bb0 = await bo.bal()
            bad = ['javascript:alert(1)', 'file:///etc/passwd', 'http://127.0.0.1:3350/relay', 'ws://user:pw@127.0.0.1:3350/relay', 'ws://127.0.0.1:3350/re lay', 'wss://', 'ws://' + 'a' * 300 + '.example']
            r1 = [await bo.ev(f"NutZap.relay({J(u)})") for u in bad]
            check('relays: javascript:, file:, http:, credentials, spaces, no host and over-long addresses are refused', all(x is None for x in r1), r1)
            r2 = await bo.ev(f"NutZap.relay({J(RELAY + '/')})")
            check('relays: a good one comes back in one fixed spelling', r2 == RELAY, r2)
            rp = await al.ev("NutZap.randomPub()")
            e1 = await al.ev(f"""CashuLib.finalizeEvent({{kind:10019, created_at:Math.floor(Date.now()/1000), content:'', tags:{J([['relay', u] for u in bad] + [['relay', 'wss://ok.example/relay'], ['mint', M, 'sat'], ['pubkey', rp]])}}}, crypto.getRandomValues(new Uint8Array(32)))""")
            await al.ev(f"__nzPublish({J(e1)})")
            f1 = await al.ev(f"NutZap.find({J(e1['pubkey'])}).then(x=>x, e=>e.message)")
            check('relays: from a 10019 only the valid relay is kept', isinstance(f1, dict) and f1['relays'] == ['wss://ok.example/relay'], f1)
            check('mints: a mint from a 10019 that is ours is used as our own stored address', isinstance(f1, dict) and f1['mints'][0].get('own') == M, f1)
            # a 9321 whose mint is not one of ours: never fetched, never a key
            hits = []
            async def watch(route):
                hits.append(route.request.url)
                try: await route.abort()
                except Exception: pass
            await bo.pg.route(re.compile(r'https?://evil\.example/.*'), watch)
            ps = await al.ev(f"Nutcade.r8.sendEcash(5, 'nz taint', {J(ctx.get('bpub'))}).then(t=>t.sent)")
            e2 = await al.ev(f"__nzEv({J(ps)}, {{u:'http://evil.example', p:{J(B_PK)}, dt:8}})")
            r3 = await bo.ev(f"NutZap.event({J(e2)})"); await bo.wait(800)
            gone = await bo.ev("!Object.keys(Nutcade.S.mintlog||{}).some(k=>/evil/.test(k)) && !Object.keys(Nutcade.S.mintkeys||{}).some(k=>/evil/.test(k)) && !Nutcade.S.mints.some(m=>/evil/.test(m.url))")
            check('mints: a 9321 at a mint that is not ours is refused, never fetched, never used as a key', r3 == 'untrusted' and not hits and gone, (r3, hits, gone))
            # a __proto__ keyset id does nothing
            e3 = await al.ev(f"__nzEv({J([dict(p, id='__proto__') for p in ps])}, {{u:{J(M)}, p:{J(B_PK)}, dt:9}})")
            r4 = await bo.ev(f"NutZap.event({J(e3)})")
            clean = await bo.ev("Object.getOwnPropertyNames(Object.prototype).every(k=>['constructor','__defineGetter__','__defineSetter__','hasOwnProperty','__lookupGetter__','__lookupSetter__','isPrototypeOf','propertyIsEnumerable','toString','valueOf','__proto__','toLocaleString'].includes(k))")
            check('keys: a proof on keyset "__proto__" is refused and nothing is added to Object.prototype', r4 == 'keyset' and clean and await bo.bal() == bb0, (r4, clean))
            # text from an event or a name shows as text
            r5 = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 6, '<img src=x onerror=window.__xss=1>').then(x=>x.ok, e=>e.message)")
            await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 6}", 20000)
            await bo.ev("Nutcade.closeSheet()"); await bo.click('[data-act=tab][data-tab=history]'); await bo.wait(300)
            tid = await bo.ev("(Nutcade.S.txs.find(t=>t.type==='in'&&t.nz&&t.amount===6)||{}).id")
            await bo.ev(f"document.querySelector('[data-act=tx][data-id=\"{tid}\"]').click()"); await bo.wait(400)
            x1 = await bo.ev("({xss: window.__xss === undefined, img: !document.querySelector('img[src=\"x\"]'), text: document.body.innerText.includes('<img src=x')})")
            check('text: a comment with <img onerror> shows as text in history and its screen, never as HTML', r5 is True and all(x1.values()), x1)
            await bo.ev("Nutcade.closeSheet()")
            await al.ev(f"NutZap.open({{pubkey:{J(B_PK)}, name:'<img src=x onerror=window.__xss2=1>'}})"); await al.until("!document.querySelector('#layer .spinner')", 12000); await al.wait(300)
            x2 = await al.ev("({xss: window.__xss2 === undefined, img: !document.querySelector('img[src=\"x\"]'), text: (document.querySelector('#layer')||{}).innerText.includes('<img src=x')})")
            check('text: a name with <img onerror> shows as text on the nutzap screen', all(x2.values()), x2)
            await al.ev("Nutcade.closeSheet()")
        await section('taint', taint)

        async def parts():
            # a waiting nutzap at a mint that starts limiting request size is claimed in parts; such a mint is left out of the 10019
            bb0 = await bo.bal(); SW = re.compile(re.escape(M) + r'/v1/swap$')
            await bo.pg.route(SW, down)
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 7, 'parts').then(x=>x.ok, e=>e.message)")
            w8 = await bo.until("Nutcade.S.txs.some(t=>t.type==='in'&&t.nz&&t.status==='pending'&&t.amount===7)", 20000)
            await bo.ev(f"NutRemind.wallet({J(M)}).getMintInfo()._mintInfo.max_array_length=2")
            lim = await bo.ev("NutZap.mints()")
            check('parts: a mint below the minimum request size is left out of the nutzap mints', r is True and w8 and lim == [], (r, w8, lim))
            await bo.pg.unroute(SW); await bo.ev("NutZap.tick(true)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 7}", 30000); await bo.wait(1500)
            n = await bo.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&/\\(part \\d+ of \\d+\\)/.test(t.note||'')&&/parts/.test(t.note||'')).length")
            check('parts: the waiting nutzap is claimed in parts, credited once (7 SAT)', ok and await bo.bal() == bb0 + 7 and n >= 2 and not await bo.ev("Nutcade.S.txs.some(t=>t.nz&&t.type==='in'&&t.status==='pending')"), (await bo.bal() - bb0, n))
            await bo.ev(f"delete NutRemind.wallet({J(M)}).getMintInfo()._mintInfo.max_array_length")
            check('parts: with the limit gone the mint is listed again', await bo.ev("NutZap.mints()") == [M])
            await bo.ev("NutZap.tick(true)")
            check('parts: and published again in the 10019', await bo.until(f"(NutZap.info()||{{}}).mints && NutZap.info().mints.join()==={J(M)}", 15000))
        await section('parts', parts)

        async def mintdown():
            # the receiver's mint is down: the nutzap waits, is never credited, then is credited once
            bb0 = await bo.bal(); RX = re.compile(re.escape(M) + r'/v1/.*')
            await bo.pg.route(RX, down)
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 150, '').then(x=>x.ok, e=>e.message)")
            check('mint down (receiver): the nutzap is sent', r is True, r)
            w8 = await bo.until("NutZap.waiting() === 1", 25000)
            await bo.ev("NutZap.tick()"); await bo.wait(1500)
            check('mint down (receiver): kept waiting to be checked (the mint can\'t say whether the coins are spent), no line, not credited', w8 and await bo.bal() == bb0 and not await bo.ev("Nutcade.S.txs.some(t=>t.nz&&t.type==='in'&&t.amount===150)"), (w8, await bo.bal() - bb0))
            await bo.pg.unroute(RX)
            await bo.ev("NutZap.tick(true)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 150}", 20000); await bo.wait(800)
            await bo.ev("NutZap.tick(true)"); await bo.wait(800)
            i = [x for x in await nz_in(bo) if x['amount'] == 150]
            check('mint down (receiver): once the mint is back it is credited, once, and the line is done', ok and await bo.bal() == bb0 + 150 and len(i) == 1 and i[0]['status'] == 'done' and await bo.ev("NutZap.waiting()") == 0, (await bo.bal() - bb0, i))
            # the sender's mint is down: nothing is lost
            ab0, z0 = await al.bal(), len(evs(9321, A_PK))
            await al.pg.route(RX, down)
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 60, '').then(x=>'sent', e=>e.message)")
            await al.pg.unroute(RX); await al.ev("NutZap.tick(true)"); await al.until("Nutcade.S.ops.length===0", 30000); await al.wait(500)
            check('mint down (sender): the send fails, nothing is published, the balance is whole again', r != 'sent' and len(evs(9321, A_PK)) == z0 and await al.bal() == ab0, (r, await al.bal() - ab0))
        await section('mintdown', mintdown)

        async def relaydown():
            # (the page's WebSockets drop kind 9321 events while blocked: no relay ever answers OK)
            await al.ev("""(()=>{ if (window.__nzSend) return; const os = WebSocket.prototype.send; window.__nzSend = os;
                WebSocket.prototype.send = function (d) { if (window.__nzBlock && typeof d === 'string' && d.startsWith('["EVENT"') && d.includes('"kind":9321')) return; return os.call(this, d); } })()""")
            ab0, bb0 = await al.bal(), await bo.bal(); await al.ev("window.__nzBlock=true")
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 120, '').then(x=>x.ok, e=>e.message)")
            o = [x for x in await nz_out(al) if x['amount'] == 120]
            check('relays down (sender): the nutzap is made and kept, marked not delivered, its event kept', r is False and len(o) == 1 and not o[0]['delivered'] and o[0]['ev'], (r, o))
            await bo.wait(1500)
            check('relays down (sender): nothing reached the receiver yet', await bo.bal() == bb0)
            await al.ev("window.__nzBlock=false")
            await al.ev("NutZap.tick(true)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 120}", 20000); await al.wait(500)
            o = [x for x in await nz_out(al) if x['amount'] == 120]
            z = [e for e in evs(9321, A_PK) if o and e['id'] == o[0]['ev']]
            check('relays down (sender): later it is published, the same event, once; Bob gets 120 SAT once', ok and o and o[0]['delivered'] and len(z) == 1 and await bo.bal() == bb0 + 120 and await al.bal() == ab0 - 120, (ok, o, len(z), await bo.bal() - bb0))
        await section('relaydown', relaydown)

        async def crash():
            ab0, bb0, z0 = await al.bal(), await bo.bal(), len(evs(9321, A_PK))
            SW = re.compile(re.escape(M) + r'/v1/swap$')
            await al.pg.route(SW, held(8))
            await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 130, 'crash').catch(()=>{{}}); 0")
            rec = await al.until("Nutcade.S.ops.some(o=>o.kind==='send'&&o.outs.length)", 10000); await al.wait(800)
            await al.pg.reload(); await al.wait(800); await al.pg.unroute(SW)
            await al.until("Nutcade.S.ops.length===0", 60000); await al.wait(500)
            await al.ev("NutZap.tick(true)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 130}", 25000); await al.wait(800)
            o = [x for x in await nz_out(al) if x['amount'] == 130]
            z = [e for e in evs(9321, A_PK) if e['content'] == 'crash']
            check('crash mid-send: the step was on record when the page went', rec)
            check('crash mid-send: the locked coins come back from the journal as the nutzap, one line, delivered', len(o) == 1 and o[0]['delivered'] and o[0]['locked'] == ctx.get('bpub'), o)
            check('crash mid-send: published once, Bob credited 130 SAT once, the sender down exactly 130 SAT', len(z) == 1 and ok and await bo.bal() == bb0 + 130 and await al.bal() == ab0 - 130, (len(z), await bo.bal() - bb0, ab0 - await al.bal()))
            await al.ev("NutZap.tick(true)"); await bo.wait(1500)
            check('crash mid-send: another round sends nothing more', len([e for e in evs(9321, A_PK) if e['content'] == 'crash']) == 1 and await bo.bal() == bb0 + 130)
        await section('crash', crash)

        async def restore():
            bbal = await bo.bal(); await bo.pg.context.close()
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 77, 'while away').then(x=>x.ok, e=>e.message)")
            check('restore: a nutzap sent while Bob\'s phone is gone', r is True, r)
            d = await wallet(b, 'nz-dave')
            await d.gate_restore(); await d.fill('#phraseIn', bob_words); await d.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await d.fill('#rmExtra', M)
            await d.click('[data-act=doRestorePhrase]'); await d.until("!document.querySelector('[data-act=doRestorePhrase]')", 90000); await d.wait(600)
            await d.ev("Nutcade.closeSheet()")
            if await d.until("!!document.querySelector('[data-act=gateStart]')", 4000): await d.gate_step('gateStart', "!!document.querySelector('.tabbar')")
            await d.wait(300); await d.ev("Nutcade.closeSheet()")
            check('restore: the 12 words bring back the same balance', await d.bal() == bbal, (await d.bal(), bbal))
            check('restore: the same receiving key is derived again', await d.ev("NutZap.pub()") == ctx.get('bpub'))
            check('restore: nutzaps stay off until turned on', await d.ev("Nutcade.S.prefs.nutzap") is False)
            await nz_on(d)
            ok = await d.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bbal + 77}", 25000); await d.wait(2500)
            i = await nz_in(d)
            check('restore: the nutzap that arrived meanwhile is found and claimed (77 SAT), once', ok and await d.bal() == bbal + 77 and [x['amount'] for x in i] == [77], (await d.bal() - bbal, i))
            check('restore: nutzaps claimed before are skipped, no lines for them, nothing waiting or failed', not await d.ev("Nutcade.S.txs.some(t=>t.nz&&t.status!=='done')"), await d.ev("Nutcade.S.txs.filter(t=>t.nz).map(t=>[t.status,t.amount])"))
            ctx['dave'] = d
        await section('restore', restore)

        async def duress():
            e = await wallet(b, 'nz-ed'); await e.create(); await e.add_mint(M); await e.use(M); await e.receive_ln(1000)
            await nz_on(e); E_PK = await me(e); epub = await e.ev("NutZap.pub()")
            await set_pin(e)
            await settings(e); await e.click('[data-act=duressOpen]'); await e.wait(250)
            await pad(e, PIN); await e.wait(800); await pad(e, DPIN); await e.wait(300); await pad(e, DPIN); await e.until("!!document.querySelector('#duressAmt')", 8000)
            await e.fill('#duressAmt', '100'); await e.click('[data-act=duressMake]'); await e.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await e.ev("Nutcade.closeSheet()")
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            dpk = await me(e); n10 = len(evs(10019)); db0 = await e.bal()
            check('duress: the duress wallet has nutzaps off and listens to nothing', await e.ev("Nutcade.S.prefs.nutzap") is not True and await e.ev("NutZap.live()") == 0)
            await settings(e); await e.click('#p_nutzap'); await e.wait(1000)
            st1 = await e.ev("document.querySelector('#set-privacy').innerText")
            await e.wait(8500); await settings(e); st2 = await e.ev("document.querySelector('#set-privacy').innerText")
            check('duress: the toggle appears to work: it stays on and shows SAVING…, then RELAYS DIDN\'T ANSWER, like a wallet whose relays are down',
                  await e.ev("Nutcade.S.prefs.nutzap") is True and await e.ev("document.querySelector('#p_nutzap').checked") and 'SAVING' in st1 and "RELAYS DIDN'T ANSWER" in st2, (st1[-200:], st2[-200:]))
            check('duress: nothing is published (no new 10019) and nothing listened to', len(evs(10019)) == n10 and not evs(10019, dpk) and await e.ev("NutZap.live()") == 0)
            r = await e.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 10, '').then(()=>'sent', x=>x.message)")
            check('duress: sending a nutzap answers as when relays can\'t be reached (as the real wallet could), nothing spent, nothing published', "Couldn't reach your Nostr relays" in r and await e.bal() == db0 and not evs(9321, dpk), r)
            r = await al.ev(f"NutZap.send({{pubkey:{J(E_PK)}, name:'Ed'}}, 55, '').then(x=>x.ok, x=>x.message)")
            await e.wait(3000)
            check('duress: a nutzap to the real wallet is not claimed by the duress wallet', r is True and await e.bal() == db0 and not await e.ev("Nutcade.S.txs.some(t=>t.nz)"), r)
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            rb0 = await e.bal()
            ok = await e.until(f"Nutcade.S.txs.some(t=>t.nz&&t.status==='done'&&t.amount===55)", 25000)
            check('duress: back in the real wallet, nutzaps are still on and the nutzap is claimed', ok and await e.ev("Nutcade.S.prefs.nutzap") is True and await e.ev("NutZap.pub()") == epub, (ok, await e.bal() - rb0))
            await e.pg.context.close()
        await section('duress', duress)

        async def unpub():
            # (fix round 1) turning nutzaps off always withdraws the 10019, whatever happened to the publish
            f = await wallet(b, 'nz-fred'); await f.create(); await f.add_mint(M); await f.use(M); FP = await me(f)
            def has_info(): return any(tags(e, 'pubkey') for e in evs(10019, FP))
            await settings(f); await f.click('#p_nutzap'); await f.click('#p_nutzap')   # (on and off at once: the publish is still on its way)
            ok = await f.until("!Nutcade.S.prefs.nzUnpub && !Nutcade.S.prefs.nzPubTry && !Nutcade.S.prefs.nzInfo", 20000); await f.wait(500)
            check('unpublish: on then off within the publish window leaves no nutzap info on the relay', ok and not has_info(), [e['tags'] for e in evs(10019, FP)])
            await nz_on(f); check('unpublish: (on again: published)', has_info())
            await f.ev("""(()=>{ const os = WebSocket.prototype.send; WebSocket.prototype.send = function (d) { if (window.__nzBlockU && typeof d === 'string' && d.startsWith('["EVENT"') && (d.includes('"kind":10019') || d.includes('"kind":5,'))) return; return os.call(this, d); } })()""")
            await f.ev("window.__nzBlockU=true"); await settings(f); await f.click('#p_nutzap')
            await f.until("!!(Nutcade.S.prefs.nzUnpub && Nutcade.S.prefs.nzUnpub.tries>0)", 20000)
            check('unpublish: a relay that did not confirm is kept to try again', await f.ev("(Nutcade.S.prefs.nzUnpub||{}).relays||[]") == [RELAY] and has_info())
            await f.ev("window.__nzBlockU=false"); await f.ev("NutZap.tick(true)")
            ok = await f.until("!Nutcade.S.prefs.nzUnpub", 20000); await f.wait(300)
            check('unpublish: tried again, the relay confirms and the info is gone', ok and not has_info(), [e['tags'] for e in evs(10019, FP)])
            r = await f.ev(f"NutZap.event(__nzEv([], {{u:{J(M)}, p:{J(FP)}}}))")
            check('off: with nutzaps off an incoming nutzap is not looked at', r == 'off', r)
            await nz_on(f)
            new = [e for e in evs(10019, FP) if tags(e, 'pubkey')]; dels = evs(5, FP)
            check('unpublish: published again later, after the deletion (never at or below its time)', new and dels and min(e['created_at'] for e in new) > max(e['created_at'] for e in dels) if True else False, ([e['created_at'] for e in new], [e['created_at'] for e in dels]))
            await f.pg.context.close()
        await section('unpub', unpub)

        async def relays2():
            g = await wallet(b, 'nz-gina'); await g.create(); await g.add_mint(M); await g.use(M)
            await g.ev(f"Nutcade.S.prefs.relays=[{J(RELAY)}, {J(RELAY + '?b=1')}]")
            await nz_on(g); ok = await g.until("NutZap.live() === 2", 10000)
            await g.ev("NutZap.socks()[0].close()"); await g.wait(500)
            dropped = await g.ev("NutZap.live()")
            back = await g.until("NutZap.live() === 2", 15000)
            check('listen: a relay that drops is opened again while the other stays up', ok and dropped == 1 and back, (ok, dropped, back))
            await g.pg.context.close()
        await section('relays2', relays2)

        async def langs():
            for lang in ('es', 'pt', 'de', 'fr'):
                x = await wallet(b, 'nz-' + lang, lang); await x.create(); await x.add_mint(M); await x.use(M)
                await settings(x); await x.click('#p_nutzap'); await x.wait(1500)
                await x.ev(f"NutZap.open({{pubkey:{J('ab' * 32)}, name:'Zed'}})"); await x.until("!document.querySelector('#layer .spinner')", 12000); await x.wait(300)
                txt = await x.sheet_text()
                await x.ev("Nutcade.closeSheet()"); await settings(x)
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/nutzap|NIP-61|receiving key|public on Nostr|can't receive/i.test(s))")
                check(f'{lang}: the nutzap texts show translated, with no missing translation', "can't receive" not in txt and 'Receive nutzaps' not in await x.ev("document.querySelector('#set-privacy').innerText") and not miss, (txt[:120], miss))
                await x.pg.context.close()
        await section('langs', langs)

        async def fields():
            # a waiting nutzap whose mint turns it down because some of its coins are spent is saved again with the coins
            # still good (NutZap.left, app_nutzap.js), each with every field it had (spend_info, witness, p2pk_e, dleq: on
            # e9b0b98 spend_info and witness were dropped)
            tok = await al.ev(f"Nutcade.r8.sendEcash(3, 'fields', null, {J(M)}).then(x => x.token)")
            ps = await al.ev(f"CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.counters)).proofs.map(p => Object.assign({{}}, p, {{ amount: Number(String(p.amount)) }}))")
            SI = {'k': '02' + 'cd' * 32, 'tree': ['00' * 8]}
            extra = {'spend_info': SI, 'witness': J({'signatures': ['ee' * 64]}), 'p2pk_e': '02' + 'ef' * 32}
            rest = [dict(p, **extra) for p in ps[1:]]
            t2 = await al.ev(f"CashuLib.getEncodedToken({{ mint: {J(M)}, unit: 'sat', proofs: {J(ps[:1] + rest)}.map(p => Object.assign({{}}, p, {{ amount: CashuLib.Amount.from(p.amount) }})) }})")
            got = await al.ev(f"""(() => {{ const d = CashuLib.getDecodedToken({J(t2)}, Object.keys(Nutcade.S.counters));
                const left = NutZap.left(d.proofs, d.proofs.map((p, i) => ({{ state: i ? 'UNSPENT' : 'SPENT' }})));
                const back = CashuLib.getDecodedToken(NutZap.leftToken({J(M)}, left), Object.keys(Nutcade.S.counters)).proofs;
                return back.map(p => ({{ secret: p.secret, amount: Number(String(p.amount)), si: p.spend_info || null, w: p.witness || null, e: p.p2pk_e || null, dleq: !!(p.dleq && p.dleq.r) }})); }})()""")
            check('fields: a waiting nutzap with a spent coin is saved again with only the good coins, each keeping spend_info, witness, p2pk_e and its DLEQ proof',
                  [p['secret'] for p in got] == [p['secret'] for p in rest] and all(p['si'] == SI and p['w'] == extra['witness'] and p['e'] == extra['p2pk_e'] and p['dleq'] for p in got)
                  and sum(p['amount'] for p in got) == sum(p['amount'] for p in rest), got)
            await al.receive_token(tok)   # (the coins back)
        await section('fields', fields)

        await al.pg.screenshot(path=os.path.join(OUT, 'nutzap.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
