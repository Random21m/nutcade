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
  tags: proofs.map(p => ['proof', JSON.stringify({ id: p.id, amount: Number(p.amount), secret: p.secret, C: p.C })]).concat([['u', x.u], ['unit', 'sat'], ['p', x.p]]) }, crypto.getRandomValues(new Uint8Array(32)));
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
            check('receive: his line says who sent it, with the comment', i and i[0]['status'] == 'done' and i[0]['note'].startswith('Nutzap from npub1') and i[0]['note'].endswith(': thanks') and i[0]['from'] == A_PK, i)
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

        async def mintdown():
            # the receiver's mint is down: the nutzap waits, is never credited, then is credited once
            bb0 = await bo.bal(); RX = re.compile(re.escape(M) + r'/v1/.*')
            await bo.pg.route(RX, down)
            r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 150, '').then(x=>x.ok, e=>e.message)")
            check('mint down (receiver): the nutzap is sent', r is True, r)
            w8 = await bo.until("Nutcade.S.txs.some(t=>t.type==='in'&&t.nz&&t.status==='pending'&&t.amount===150)", 15000)
            await bo.ev("NutZap.tick()"); await bo.wait(1500)
            check('mint down (receiver): recorded as waiting (150 SAT), not credited', w8 and await bo.bal() == bb0, (w8, await bo.bal() - bb0))
            await bo.pg.unroute(RX)
            await bo.ev("NutZap.tick(true)")
            ok = await bo.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {bb0 + 150}", 20000); await bo.wait(800)
            await bo.ev("NutZap.tick(true)"); await bo.wait(800)
            i = [x for x in await nz_in(bo) if x['amount'] == 150]
            check('mint down (receiver): once the mint is back it is credited, once, and the line is done', ok and await bo.bal() == bb0 + 150 and len(i) == 1 and i[0]['status'] == 'done', (await bo.bal() - bb0, i))
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
            await settings(e); await e.click('#p_nutzap'); await e.wait(1500)
            t = await e.toast()
            check('duress: turning nutzaps on answers "aren\'t available right now" and stays off', "aren't available right now" in t and await e.ev("Nutcade.S.prefs.nutzap") is not True and not await e.ev("document.querySelector('#p_nutzap').checked"), t)
            check('duress: nothing is published (no new 10019)', len(evs(10019)) == n10 and not evs(10019, dpk))
            r = await e.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, 10, '').then(()=>'sent', x=>x.message)")
            check('duress: sending a nutzap is refused the same way, nothing spent', "aren't available right now" in r and await e.bal() == db0, r)
            r = await al.ev(f"NutZap.send({{pubkey:{J(E_PK)}, name:'Ed'}}, 55, '').then(x=>x.ok, x=>x.message)")
            await e.wait(3000)
            check('duress: a nutzap to the real wallet is not claimed by the duress wallet', r is True and await e.bal() == db0 and not await e.ev("Nutcade.S.txs.some(t=>t.nz)"), r)
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            rb0 = await e.bal()
            ok = await e.until(f"Nutcade.S.txs.some(t=>t.nz&&t.status==='done'&&t.amount===55)", 25000)
            check('duress: back in the real wallet, nutzaps are still on and the nutzap is claimed', ok and await e.ev("Nutcade.S.prefs.nutzap") is True and await e.ev("NutZap.pub()") == epub, (ok, await e.bal() - rb0))
            await e.pg.context.close()
        await section('duress', duress)

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

        await al.pg.screenshot(path=os.path.join(OUT, 'nutzap.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
