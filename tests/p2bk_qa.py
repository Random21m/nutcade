"""Pay to Blinded Key (1.29.0, NUT-28): "Hide who gets it (P2BK)", gifts, bounties and nutzaps locked to blinded keys.
Uses the local test mint 3339 (no fees, so amounts are exact), the stand-in Nostr relay (mock_nostr.py, port 3350) and
Nutshell's own NUT-28 code (cashu 0.21.0, run through tests/p2bk_py.py with MINT_PY) as an independent implementation.

The setting is off by default, kept per wallet (persisted, the duress PIN's wallet has its own, not carried in backup files).
The grid: gift, bounty and nutzap, each sent with the setting off and on, received and claimed by NUTCADE end to end on the
test mint (real swaps): off locks the plain keys with no p2pk_e; on blinds the receiver's key and the refund key together
(never one alone), one E per coin, the line marked blinded. Nutshell derives exactly the keys NUTCADE's library wrote
(receiver at slot 0, our refund at slot 1; HTLC: receiver 1, refund 2), and NUTCADE's own blinding (the check of a
nutzap's lock) equals Nutshell's on vectors. A Nutshell-made P2BK token (and nutzap) is claimed by NUTCADE, and a
NUTCADE-made blinded gift is claimed by Nutshell's wallet. A wrong key can't claim; the sender can't claim before the date
and takes it back after it with the blinded refund key (a gift by hand, a bounty on its own). A blinded nutzap is taken
only when its E and key match (missing, wrong or invalid E refused), the lock rules are as strict as in 1.28, and p2pk_e
stays on the coins it claims. Extra Life stays unblinded. A crash mid-send keeps p2pk_e (the journal). A token with
p2pk_e survives encode/decode and a backup restored with the 12 words on a new phone (taken back there). New texts in five
languages. P2BK_ONLY=a,b runs some sections (their names start with those letters).
What the test mint can't show (a wallet without NUT-28 failing to spend) follows from the lock itself: the key in it is one
nobody holds; checked here only as "the plain key is not in the coin"."""
import asyncio, json, os, re, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from r8_qa import set_pin, unlock, pad, PIN, DPIN

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.environ.get('MINT_PY', 'python3')
TMP = tempfile.mkdtemp(prefix='p2bk-')
TOTAL = "Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)"
HEX66 = re.compile(r'0[23][0-9a-f]{64}')
WHATS = "New, optional and off by default: Hide who gets it (P2BK, Settings, Privacy) hides the receiver's key in the gifts and bounties you send. Turn it on only if their wallet supports it (NUTCADE 1.29 or newer does). Nutzaps are never hidden."
GIFTNOTE = "Only NUTCADE 1.29 or newer, or another wallet that supports NUT-28, can claim it: Hide who gets it is on. Locked ecash can't be sent offline."

def py(*args, inp=None):
    r = subprocess.run([PYW, os.path.join(HERE, 'p2bk_py.py')] + [str(a) for a in args], input=J(inp) if inp is not None else None,
                       capture_output=True, text=True, cwd=TMP, timeout=120)
    if r.returncode: raise RuntimeError('p2bk_py ' + args[0] + ': ' + (r.stderr or r.stdout)[-400:])
    return r.stdout.strip().splitlines()[-1]

def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def evs(kind, author=None, p=None):
    out = []
    for e in state()['events']:
        if e['kind'] != kind or (author and e['pubkey'] != author): continue
        if p and not any(t[0] == 'p' and t[1] == p for t in e['tags']): continue
        out.append(e)
    return out
def tags(e, k): return [t for t in e['tags'] if t and t[0] == k]
def lk(p):   # a proof's lock: kind, data, tags as a dict, E
    s = json.loads(p['secret']); t = {x[0]: x[1:] for x in (s[1].get('tags') or [])}
    return {'kind': s[0], 'data': s[1]['data'], 'tags': t, 'e': p.get('p2pk_e')}

HELPERS = """
window.__even = sk => { const N = BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141'); const h = CashuLib.bytesToHex(sk);
  return CashuLib.getPubKeyFromPrivKey(sk)[0] === 2 ? h : (N - BigInt('0x' + h)).toString(16).padStart(64, '0'); };
window.__seed = () => CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic);
window.__lockPriv = () => __even(__seed().slice(0, 32));
window.__nzPriv = () => __even(CashuLib.HDKey.fromMasterSeed(__seed()).derive("m/129372'/61'/0'/0'/0'").privateKey);
window.__nzEv = (proofs, x) => CashuLib.finalizeEvent({ kind: 9321, created_at: Math.floor(Date.now() / 1000) + (x.dt || 0), content: x.c || '',
  tags: proofs.map(p => ['proof', JSON.stringify(Object.assign({ id: p.id, amount: Number(p.amount), secret: p.secret, C: p.C }, p.dleq ? { dleq: p.dleq } : {}, x.noE ? {} : x.E !== undefined ? { p2pk_e: x.E } : p.p2pk_e ? { p2pk_e: p.p2pk_e } : {}))]).concat([['u', x.u], ['unit', 'sat'], ['p', x.p]]) }, crypto.getRandomValues(new Uint8Array(32)));
window.__nzPublish = ev => new Promise(r => { const ws = new WebSocket(%s); ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d[0] === 'OK') { try { ws.close(); } catch (e) {} r(d[2]); } }; setTimeout(() => r(false), 5000); });
window.__dec = t => CashuLib.getDecodedToken(t, Object.keys(Nutcade.S.counters).concat(...Object.values(Nutcade.S.mintkeys || {}).map(k => Object.keys(k)))).proofs.map(p => ({ id: p.id, amount: Number(p.amount), secret: p.secret, C: p.C, p2pk_e: p.p2pk_e, dleq: p.dleq }));
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
    only = [x for x in os.environ.get('P2BK_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
async def set_blind(w, on):
    await settings(w)
    if bool(await w.ev("document.querySelector('#p_p2bk').checked")) != on: await w.click('#p_p2bk'); await w.wait(150)
    return await w.ev("Nutcade.S.prefs.p2bk") is on
async def nz_on(w):
    await settings(w)
    if not await w.ev("document.querySelector('#p_nutzap').checked"): await w.click('#p_nutzap')
    return await w.until("NutZap.info() && NutZap.info().pub === NutZap.pub()", 15000)
async def nprofile(w): return await w.ev(f"CashuLib.nprofileEncode({{pubkey: NutZap.me(), relays:[{J(RELAY)}]}})")
async def add_contact(w, name, addr):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
    await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
    await w.click('[data-act=contactEdit]:not([data-id])'); await w.wait(100)
    await w.fill('#cName', name); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(250)
    await w.ev("Nutcade.closeSheet()")
async def gift(w, amount, contact=None, key=None, secs=None):
    """A gift from the Send sheet: to a contact (delivered over Nostr) or to a pasted key; secs: a short lock for the tests."""
    await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.pg.check('#giftOn')
    if key:
        await w.ev("const s=document.querySelector('#giftTo'); s.value=''; s.dispatchEvent(new Event('change',{bubbles:true}))")
        await w.fill('#giftKey', key)
    elif contact:
        await w.ev(f"const s=document.querySelector('#giftTo'); s.value=[...s.options].find(o=>o.text==={J(contact)}).value; s.dispatchEvent(new Event('change',{{bubbles:true}}))")
    if secs: await w.ev(f"const b=document.querySelector('[data-act=giftDays][data-days=\"1\"]'); b.dataset.days={secs}/86400; b.click()")
    n0 = await w.ev("Nutcade.S.txs.length")
    await w.fill('#amtIn', str(amount)); await w.click('[data-act=doSendEcash]')
    await w.until(f"Nutcade.S.txs.length>{n0} && !!Nutcade.S.txs[0].token && !!Nutcade.S.txs[0].lockUntil", 20000); await w.wait(600)
    t = await w.ev("Nutcade.S.txs[0]"); await w.ev("Nutcade.closeSheet()")
    return t

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al = await wallet(b, 'pb-alice'); await al.create(); await al.add_mint(M); await al.use(M)
        bo = await wallet(b, 'pb-bob'); bob_words = await bo.create(); await bo.add_mint(M); await bo.use(M)
        ok = await al.receive_ln(9000)
        check('setup: the sender has sats', ok)
        A_PK, B_PK = await al.ev("NutZap.me()"), await bo.ev("NutZap.me()")
        await add_contact(al, 'Bob', await nprofile(bo)); await add_contact(bo, 'Alice', await nprofile(al))
        await nz_on(bo)
        K = {'a_lock': await al.ev("__lockPriv()"), 'b_lock': await bo.ev("__lockPriv()"), 'b_nz': await bo.ev("__nzPriv()"),
             'a_pub': '02' + A_PK, 'b_pub': '02' + B_PK, 'b_nzpub': await bo.ev("NutZap.pub()")}
        check('setup: the test reads the same keys the wallet uses (lock key and nutzap key)', await al.ev("NutP2BK.lockPub()") == K['a_pub'] and await bo.ev(f"CashuLib.bytesToHex(CashuLib.getPubKeyFromPrivKey(CashuLib.hexToBytes({J(K['b_nz'])})))") == K['b_nzpub'])
        ctx = {}

        async def pref():
            check('pref: off by default (a new wallet)', await al.ev("Nutcade.S.prefs.p2bk") is False and await al.ev("NutP2BK.on()") is False)
            await settings(al)
            txt = await al.ev("document.querySelector('#set-privacy').innerText")
            check('pref: Settings, Privacy has "Hide who gets it (P2BK)", unticked, next to the nutzap setting', 'Hide who gets it (P2BK)' in txt and txt.index('Receive nutzaps') < txt.index('Hide who gets it') and not await al.ev("document.querySelector('#p_p2bk').checked"), txt[-600:])
            check('pref: its text says it hides the key in gifts and bounties, that the receiver\'s wallet must support it (NUTCADE 1.29 or newer) or it can\'t spend it, that it comes back after its time, and that nutzaps are never hidden',
                  all(x in txt for x in ("Hides the receiver's key in the gifts and bounties", 'NUTCADE 1.29 or newer does', "a wallet that doesn't can't spend it", 'comes back to you after its time runs out', 'Nutzaps you send are never hidden', 'Off by default')) and 'bounties and nutzaps' not in txt, txt[-500:])
            ok1 = await set_blind(al, True)
            await al.pg.reload(); await al.wait(1200); await settings(al)
            check('pref: turned on, it stays on after a reload (saved with the wallet)', ok1 and await al.ev("Nutcade.S.prefs.p2bk") is True and await al.ev("document.querySelector('#p_p2bk').checked"))
            d = json.loads(await al.ev("Nutcade.r8.backupData()"))
            check('pref: not carried in a backup file\'s settings', 'p2bk' not in (d.get('settings') or {}), d.get('settings'))
            await set_blind(al, False)
            n = await wallet(b, 'pb-imp'); await n.create(); await n.add_mint(M)
            d['settings'] = dict(d.get('settings') or {}, p2bk=True)
            await n.ev(f"Nutcade.r8.importBackup(JSON.parse({J(J(d))})).catch(()=>0)"); await n.wait(2000)
            check('pref: a backup file that says p2bk: true does not turn it on', await n.ev("Nutcade.S.prefs.p2bk") is False)
            await n.pg.context.close()
        await section('pref', pref)

        async def vectors():
            cases = [{'p': os.urandom(32).hex(), 'e': os.urandom(32).hex()} for _ in range(12)]
            vs = json.loads(py('vectors', inp=cases))
            got = [[await al.ev(f"NutP2BK.blind({J(c['p'])}, {J(v['E'])}, {i})") for i in range(4)] for c, v in zip(cases, vs)]
            check('vectors: NUTCADE\'s blinded key equals Nutshell\'s for 12 random keys, slots 0 to 3', all(g == v['blinded'] for g, v in zip(got, vs)), [(g[:1], v['blinded'][:1]) for g, v in zip(got, vs) if g != v['blinded']][:2])
            check('vectors: NUTCADE\'s blinded key also equals the public key of the private key Nutshell\'s receiver derives (derive_blinded_private_key), every slot', all(g == v['derived_pub'] for g, v in zip(got, vs)), [(g[:1], v['derived_pub'][:1]) for g, v in zip(got, vs) if g != v['derived_pub']][:2])
            c, v = cases[0], vs[0]
            other = await al.ev(f"NutP2BK.blind({J(cases[1]['p'])}, {J(v['E'])}, 0)")
            check('vectors: another key, another slot or another E gives another blinded key', other != v['blinded'][0] and len(set(v['blinded'])) == 4 and await al.ev(f"NutP2BK.blind({J(c['p'])}, {J(vs[1]['E'])}, 0)") != v['blinded'][0])
            x = v['E'][2:]
            bad = ['', 'zz' * 33, '04' + x, v['E'][:64], v['E'] + '00', '02' + 'f' * 64, '02' + '0' * 64, None, 5]
            r = [await al.ev(f"[NutP2BK.e({J(e)}), NutP2BK.blind({J(c['p'])}, {J(e)}, 0)]") for e in bad]
            check('vectors: an E that is not 66 hex characters, not 02/03 or not a point on the curve is refused (no key)', all(a is None and q is None for a, q in r), r)
            check('vectors: E in capitals is read as the same point', await al.ev(f"NutP2BK.e({J(v['E'].upper())})") == v['E'])
        await section('vectors', vectors)

        async def grid():
            win = await al.pg.evaluate("""async (v)=>{ const packed=await Arcade.replay.pack({frames: v}); const r=await Arcade.replay.verify('flipper', 777, packed, 0); return {packed, score:r.score}; }""",
                                       (['2,2,0,448,576,,,'] + ['2,0,0,448,576,,,'] * 43 + ['0,0,0,448,576,,,'] * 1500) * 8)
            for on in (False, True):
                tag = 'on' if on else 'off'
                check(f'grid {tag}: the setting is {tag}', await set_blind(al, on))
                # --- gift to the contact Bob, delivered over Nostr, claimed by his NUTCADE ---
                bb0 = await bo.bal()
                t = await gift(al, 300 + on, contact='Bob')
                ls = [lk(x) for x in t['sent']]
                if on:
                    check('grid on: gift: every coin carries its own E (p2pk_e, a point), the line says blinded', ls and all(l['e'] and HEX66.fullmatch(l['e']) for l in ls) and len({l['e'] for l in ls}) == len(ls) and t.get('blinded') is True, (ls[:1], t.get('blinded')))
                    check('grid on: gift: neither Bob\'s key nor your refund key is in the coins (both blinded, never one alone)', all(l['data'] != K['b_pub'] and l['tags'].get('refund') and l['tags']['refund'][0] not in (K['a_pub'],) for l in ls) and all('locktime' in l['tags'] for l in ls), ls[:1])
                    sl = json.loads(py('slots', inp={'proofs': t['sent'], 'privs': [K['b_lock'], K['a_lock']]}))
                    check('grid on: gift: Nutshell finds Bob\'s key at slot 0 and your refund key at slot 1 of every coin', all(s == [[0, 0], [1, 1]] for s in sl), sl[:2])
                    check('grid on: gift: NUTCADE\'s own check finds Bob\'s key blinded in slot 0', await bo.ev(f"{J(t['sent'])}.every(p=>NutP2BK.mine(JSON.parse(p.secret)[1].data, {J(K['b_pub'])}, __lockPriv(), p.p2pk_e, 0))"))
                    ctx['gift_on'] = t
                else:
                    check('grid off: gift: locked to Bob\'s key with your refund key, no E, not marked blinded', all(l['data'] == K['b_pub'] and l['tags'].get('refund') == [K['a_pub']] and not l['e'] for l in ls) and not t.get('blinded'), (ls[:1], t.get('blinded')))
                got = await bo.until(f"{TOTAL} >= {bb0 + 300 + on}", 25000); await bo.wait(400)
                check(f'grid {tag}: gift: Bob\'s NUTCADE claims it over Nostr, exactly once ({300 + on} SAT)', got and await bo.bal() == bb0 + 300 + on, await bo.bal() - bb0)
                # --- bounty to Bob: the real challenge, his winning replay, your NUTCADE sends the secret, his claims it ---
                bb0 = await bo.bal()
                await al.click('[data-act=tab][data-tab=arcade]'); await al.wait(200)
                await al.ev("Nutcade.startChallenge({game:'flipper', seed:777, score:1000, by:'ACE'})"); await al.wait(250)
                n0 = await al.ev("Nutcade.S.challenges.length")
                await al.fill('#bountyAmt', str(200 + on)); await al.ev("[...document.querySelectorAll('[data-act=chalSend]')].find(b=>b.textContent==='Bob').click()")
                await al.until(f"Nutcade.S.challenges.some(c=>(c.bounties||[]).some(x=>x.amount==={200 + on}))", 20000)
                bt = await al.ev(f"Nutcade.S.txs.find(t=>t.bounty && t.amount==={200 + on})")
                ls = [lk(x) for x in bt['sent']]
                if on:
                    check('grid on: bounty: an HTLC whose "pubkeys" and refund keys are blinded, one E per coin, the line says blinded', all(l['kind'] == 'HTLC' and l['e'] and l['tags']['pubkeys'][0] != K['b_pub'] and l['tags']['refund'][0] != K['a_pub'] for l in ls) and bt.get('blinded') is True, (ls[:1], bt.get('blinded')))
                    sl = json.loads(py('slots', inp={'proofs': bt['sent'], 'privs': [K['b_lock'], K['a_lock']]}))
                    check('grid on: bounty: Nutshell finds Bob\'s key at slot 1 and your refund key at slot 2 (HTLC slots)', all(s == [[0, 1], [1, 2]] for s in sl), sl[:2])
                else:
                    check('grid off: bounty: an HTLC locked to Bob\'s key with your refund key, no E', all(l['kind'] == 'HTLC' and l['tags']['pubkeys'] == [K['b_pub']] and l['tags']['refund'] == [K['a_pub']] and not l['e'] for l in ls) and not bt.get('blinded'), ls[:1])
                ok = await bo.until(f"Nutcade.S.challenges.some(c=>c.dir==='in' && c.bounty && c.bounty.amount==={200 + on})", 20000)
                check(f'grid {tag}: bounty: Bob\'s NUTCADE reads the bounty as locked to him and shows it', ok)
                cid = await bo.ev(f"(Nutcade.S.challenges.find(c=>c.dir==='in' && c.bounty && c.bounty.amount==={200 + on})||{{}}).id")
                res = await bo.ev(f"Nutcade.challengeDone({J(cid)}, {win['score']}, 'ROB', Promise.resolve({J(win['packed'])}))")
                ok = await bo.until(f"{TOTAL} >= {bb0 + 200 + on}", 30000); await bo.wait(500)
                check(f'grid {tag}: bounty: his winning replay is sent, your NUTCADE releases the secret, his claims it once ({200 + on} SAT)', res.get('won') and ok and await bo.bal() == bb0 + 200 + on and await bo.ev(f"Nutcade.S.challenges.find(c=>c.id==={J(cid)}).bounty.state") == 'won', (res, await bo.bal() - bb0))
                await al.ev("Nutcade.closeSheet()"); await bo.ev("Nutcade.closeSheet()")
                # --- nutzap to Bob ---
                bb0 = await bo.bal()
                r = await al.ev(f"NutZap.send({{pubkey:{J(B_PK)}, name:'Bob'}}, {100 + on}, {J('grid ' + tag)}).then(x=>x.ok, e=>e.message)")
                got = await bo.until(f"{TOTAL} >= {bb0 + 100 + on}", 25000); await bo.wait(400)
                z = [e for e in evs(9321, A_PK, B_PK) if e['content'] == 'grid ' + tag]
                ps = [json.loads(t[1]) for t in tags(z[0], 'proof')] if z else []
                ls = [lk(x) for x in ps]
                o = await al.ev(f"Nutcade.S.txs.find(t=>t.nz && t.type==='out' && t.amount==={100 + on})")
                # never blinded, whatever the setting says: a nutzap can't come back, and kind 10019 doesn't say whether the receiver supports NUT-28
                check(f'grid {tag}: nutzap: sent plain (setting {tag}): locked to Bob\'s receiving key itself, no p2pk_e on any coin, not marked blinded', r is True and ls and all(l['data'] == K['b_nzpub'] and not l['e'] and 'p2pk_e' not in p for l, p in zip(ls, ps)) and not o.get('blinded') and all('p2pk_e' not in x for x in o.get('sent') or [{}]), (r, ls[:1], o.get('blinded')))
                i = await bo.ev(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.nz&&t.amount==={100 + on}).map(t=>t.status)")
                check(f'grid {tag}: nutzap: Bob\'s NUTCADE takes it and claims it once ({100 + on} SAT)', got and await bo.bal() == bb0 + 100 + on and i == ['done'], (await bo.bal() - bb0, i))
            check('grid: no page errors', not al.errs and not bo.errs, (al.errs[:3], bo.errs[:3]))
        await section('grid', grid)

        async def wrongkey():
            await set_blind(al, True)
            ca = await wallet(b, 'pb-carol'); await ca.create(); await ca.add_mint(M); await ca.use(M); ctx['carol'] = ca
            t = await gift(al, 150, key=await al.ev(f"CashuLib.npubEncode({J(B_PK)})"))
            check('wrong key: a blinded gift to a pasted npub (not delivered)', t.get('blinded') is True and t.get('locked') == K['b_pub'], t.get('locked'))
            r1 = await ca.ev(f"Nutcade.r8.recv({J(t['token'])}, 'x').then(()=>'claimed', e=>e.message)")
            r2 = await al.ev(f"Nutcade.r8.recv({J(t['token'])}, 'x', {{own:true, hand:true}}).then(()=>'claimed', e=>e.message)")
            check('wrong key: someone else is told it\'s locked to someone else; nothing credited', 'locked' in r1 and await ca.bal() == 0, r1)
            check('wrong key: the sender can\'t take it back before the date (the refund key opens only after it)', r2 != 'claimed' and await al.ev(f"Nutcade.S.txs.find(t=>t.id==={J(t['id'])}).status") == 'pending', r2)
            bb0 = await bo.bal()
            r3 = await bo.ev(f"Nutcade.r8.recv({J(t['token'])}, 'gift').then(t=>t.amount, e=>e.message)")
            check('wrong key: Bob claims it with his key (pasted token, a real swap at the mint)', r3 == 150 and await bo.bal() == bb0 + 150, r3)
            r4 = await al.ev(f"Nutcade.r8.sendEcash(20, 'nz to someone', NutZap.randomPub(), undefined, {{blind:true}}).then(t=>t.sent)")
            ev = await al.ev(f"__nzEv({J(r4)}, {{u:{J(M)}, p:{J(B_PK)}}})")
            check('wrong key: a blinded nutzap locked to someone else\'s key is refused as not locked to this wallet', await bo.ev(f"NutZap.event({J(ev)})") == 'lock')
        await section('wrongkey', wrongkey)

        async def refund():
            await set_blind(al, True)
            # a gift taken back by hand after its date, with the blinded refund key
            g = await gift(al, 260, key=await al.ev("NutZap.randomPub()"), secs=4)
            ls = [lk(x) for x in g['sent']]
            check('refund: a blinded gift with a short lock (refund key blinded)', g.get('blinded') and all(l['e'] and l['tags']['refund'][0] != K['a_pub'] for l in ls), ls[:1])
            await al.wait(6000); ab0 = await al.bal()
            await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
            await al.ev(f"document.querySelector('[data-act=tx][data-id={J(g['id'])}]').click()"); await al.wait(250)
            check('refund: after the date, Take it back is offered', await al.ev("!!document.querySelector('[data-act=giftTake]')"))
            await al.click('[data-act=giftTake]')
            ok = await al.until(f"Nutcade.S.txs.find(t=>t.id==={J(g['id'])}).status==='reclaimed'", 20000); await al.wait(300)
            check('refund: taken back with the blinded refund key, all 260 SAT (no-fee mint)', ok and await al.bal() == ab0 + 260, await al.bal() - ab0)
            await al.ev("Nutcade.closeSheet()")
            # a bounty nobody wins comes back on its own
            await al.ev("window.__nutcadeTest={bountySecs:4}")
            await al.click('[data-act=tab][data-tab=arcade]'); await al.wait(200)
            await al.ev("Nutcade.startChallenge({game:'swarm', seed:5, score:100000, by:'ACE'})"); await al.wait(250)
            await al.fill('#bountyAmt', '240'); await al.ev("[...document.querySelectorAll('[data-act=chalSend]')].find(b=>b.textContent==='Bob').click()")
            await al.until("Nutcade.S.txs.some(t=>t.bounty && t.amount===240)", 20000)
            bt = await al.ev("Nutcade.S.txs.find(t=>t.bounty && t.amount===240)")
            await al.ev("Nutcade.closeSheet(); window.__nutcadeTest=null")
            check('refund: a blinded bounty with a short lock', bt.get('blinded') is True and all(lk(x)['e'] for x in bt['sent']))
            ab0 = await al.bal(); await al.wait(36000)
            ok = False
            for _ in range(6):
                await al.ev("window.dispatchEvent(new Event('online'))")
                if await al.until(f"Nutcade.S.txs.find(t=>t.id==={J(bt['id'])}).status==='reclaimed'", 4000): ok = True; break
            check('refund: the unclaimed blinded bounty comes back on its own after the date (HTLC refund slot), 240 SAT', ok and await al.bal() == ab0 + 240, await al.bal() - ab0)
            ctx['refunded'] = ok
        await section('refund', refund)

        async def nzlock():
            await set_blind(al, True)
            bpub = K['b_nzpub']; bb0, n0 = await bo.bal(), await bo.ev("Nutcade.S.txs.filter(t=>t.nz&&t.type==='in').length")
            ps = await al.ev(f"Nutcade.r8.sendEcash(20, 'nz blinded', {J(bpub)}, undefined, {{blind:true}}).then(t=>t.sent)")
            check('nutzap lock: test coins blinded for Bob\'s receiving key, each with its E', all(lk(x)['e'] and lk(x)['data'] != bpub for x in ps))
            async def res(proofs, **x): return await bo.ev(f"NutZap.event({J(await al.ev(f'__nzEv({J(proofs)}, Object.assign({{u:{J(M)}, p:{J(B_PK)}}}, {J(x)}))'))})")
            other = await al.ev("NutZap.randomPub()")
            r = {'noE': await res(ps, noE=True), 'wrongE': await res(ps, E=other, dt=1),
                 'swapE': await res([dict(ps[0], p2pk_e=ps[1]['p2pk_e'])] if len(ps) > 1 else [dict(ps[0], p2pk_e=other)], dt=2)}
            bad = {'short': ps[0]['p2pk_e'][:64], 'notpoint': '02' + 'f' * 64, 'prefix04': '04' + ps[0]['p2pk_e'][2:], 'nothex': 'zz' * 33, 'number': 5, 'empty': ''}
            for k, v in bad.items(): r[k] = await res(ps, E=v, dt=3)
            check('nutzap lock: blinded coins with no E are refused as not locked to this wallet', r['noE'] == 'lock', r)
            check('nutzap lock: with another (valid) E, or another coin\'s E, refused as not locked to this wallet', r['wrongE'] == 'lock' and r['swapE'] == 'lock', r)
            check('nutzap lock: an E that is short, not on the curve, 04-prefixed, not hex, a number or empty is refused as bad', all(r[k] == 'bad' for k in bad), r)
            plain = await al.ev(f"Nutcade.r8.sendEcash(15, 'nz plain', {J(bpub)}).then(t=>t.sent)")
            r2 = await res(plain, E=other, dt=4)
            check('nutzap lock: coins locked to the plain key but carrying an E are refused (never both ways)', r2 == 'lock', r2)
            check('nutzap lock: none of these credited anything or became a line', await bo.bal() == bb0 and await bo.ev("Nutcade.S.txs.filter(t=>t.nz&&t.type==='in').length") == n0 and not await bo.ev("Nutcade.S.txs.some(t=>t.incoming&&t.status==='pending')"))
            # the lock rules are as strict as in 1.28, with a blinded key in the data
            blk = lk(ps[0])['data']
            def sec(t): return J(['P2PK', {'nonce': 'ab' * 32, 'data': blk, 'tags': t}])
            ok_t = [[], [['sigflag', 'SIG_INPUTS']], [['sigflag', 'SIG_INPUTS'], ['n_sigs', '1']]]
            bad_t = [[['locktime', '1700000000']], [['refund', other]], [['pubkeys', other]], [['n_sigs', '2']], [['sigflag', 'SIG_ALL']], [['sigflag', 'SIG_INPUTS'], ['sigflag', 'SIG_ALL']], [['sigflag', 'SIG_INPUTS', 'x']]]
            a1 = [await bo.ev(f"NutZap.lock({J(sec(t))})") for t in ok_t]; a2 = [await bo.ev(f"NutZap.lock({J(sec(t))})") for t in bad_t]
            check('nutzap lock: (1.28 rules) no tags, sigflag SIG_INPUTS and n_sigs 1 are read; locktime, refund, other keys, n_sigs 2, SIG_ALL, mixed or long tags are refused', all(x == blk for x in a1) and all(x is None for x in a2), (a1, a2))
            lt = await al.ev(f"Nutcade.r8.sendEcash(12, 'nz refund', {J(bpub)}, undefined, {{blind:true, locktime: Math.floor(Date.now()/1000)+3600}}).then(t=>t.sent)")
            r3 = await res(lt, dt=5)
            check('nutzap lock: a blinded nutzap with a locktime and refund key is refused, as before', r3 == 'lock' and lk(lt[0])['e'], r3)
            # the good one: taken, its E kept on the waiting line's coins, then claimed (a real swap), credited once
            SW = re.compile(re.escape(M) + r'/v1/swap$')
            async def refuse(route):
                try: await route.abort()
                except Exception: pass
            await bo.pg.route(SW, refuse)
            r4 = await res(ps, dt=6)
            ln = await bo.ev("(Nutcade.S.txs.find(t=>t.type==='in'&&t.nz&&t.amount===20&&t.status==='pending')||{}).incoming||''")
            kept = await bo.ev(f"__dec({J(ln)})") if ln else []
            check('nutzap lock: the matching blinded nutzap is taken; the waiting line keeps every coin\'s E (encoded in the token)', r4 == 'ok' and len(kept) == len(ps) and [x['p2pk_e'] for x in kept] == [x['p2pk_e'] for x in ps], (r4, [x.get('p2pk_e') for x in kept][:2]))
            await bo.pg.unroute(SW); await bo.ev("NutZap.tick(true)")
            ok = await bo.until(f"{TOTAL} >= {bb0 + 20}", 20000); await bo.wait(500)
            check('nutzap lock: claimed through the usual claim (signed with the key derived from E), 20 SAT once', ok and await bo.bal() == bb0 + 20 and not await bo.ev("Nutcade.S.txs.some(t=>t.nz&&t.type==='in'&&t.status!=='done')"), await bo.bal() - bb0)
            r5 = await res(ps, dt=7)
            lines = await bo.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.nz&&t.amount===20).map(t=>t.status)")
            check('nutzap lock: the same coins again in a new event credit nothing and add no second line (spent: refused, one done line, none waiting)', await bo.bal() == bb0 + 20 and r5 == 'spent' and lines == ['done'] and not await bo.ev("Nutcade.S.txs.some(t=>t.nz&&t.type==='in'&&t.status==='pending')"), (r5, lines))
        await section('nzlock', nzlock)

        async def bounty():
            # readBounty (app_r5.js), the check of a bounty sent to us, on coins made here: only the lock is read (no mint), so
            # the coins need no signature. Bob's key blinded with E for HTLC slot 1 is the one good form
            mk = """(o => { const ids = Object.keys(Nutcade.S.counters); const id = ids[0]; const H = 'ab'.repeat(32);
              const rnd = () => CashuLib.bytesToHex(crypto.getRandomValues(new Uint8Array(32)));
              const coin = (i) => { const e = rnd(), E = CashuLib.bytesToHex(CashuLib.getPubKeyFromPrivKey(CashuLib.hexToBytes(e)));
                const slot = o.slot === undefined ? 1 : o.slot, mine = o.plain ? NutP2BK.lockPub() : NutP2BK.blind(__lockPriv(), E, slot);
                const keys = Array.from({ length: o.before || 0 }, () => NutZap.randomPub()).concat([mine]); while (keys.length < (o.nkeys || 1)) keys.unshift(NutZap.randomPub());
                const tags = [['pubkeys', ...keys], ['locktime', String(Math.floor(Date.now()/1000) + 3600)], ['refund', ...(Array(o.nrefund || 1).fill(0).map(() => NutZap.randomPub()))]];
                const p = { id, amount: 1, secret: JSON.stringify(['HTLC', { nonce: rnd(), data: o.H2 && i ? 'cd'.repeat(32) : H, tags }]), C: NutP2BK.lockPub() };
                if (!o.noE) p.p2pk_e = o.other ? NutZap.randomPub() : o.E !== undefined ? o.E : E;
                return p; };
              const proofs = Array.from({ length: o.n || 2 }, (_, i) => coin(i));
              return CashuLib.getEncodedToken({ mint: %s, unit: 'sat', proofs }); })""" % J(M)
            async def rb(**o):
                # (only the check is timed, in the page: building up to 65 test coins there costs about a second on a slow runner)
                r = await bo.ev(f"(async () => {{ const t = ({mk})({J(o)}); const t0 = performance.now(); const r = await NutP2BK.bounty({{ token: t, amount: 0, until: Date.now() + 3600e3 }}); return [r ? 'ok' : null, (performance.now() - t0) / 1000]; }})()")
                return r[0], r[1]
            r = {k: await rb(**o) for k, o in {
                'good': {}, 'plain': {'plain': True, 'noE': True}, 'slot0': {'slot': 0}, 'slot2': {'slot': 2}, 'noE': {'noE': True},
                'badE': {'E': '02' + 'f' * 64}, 'badE2': {'E': '04' + '1' * 64}, 'otherE': {'other': True}, 'hash': {'H2': True},
                'pos2': {'before': 1, 'slot': 2}, 'pos2wrong': {'before': 1, 'slot': 1},
                'keys10': {'nkeys': 10, 'slot': 10}, 'keys11': {'nkeys': 11, 'slot': 11}, 'refund11': {'nrefund': 11},
                'coins64': {'n': 64}, 'coins65': {'n': 65}, 'coins64keys10': {'n': 64, 'nkeys': 10, 'slot': 10}}.items()}
            print('bounty timings', {k: round(v[1], 2) for k, v in r.items()})
            check('bounty: Bob\'s key blinded with the coin\'s E for HTLC slot 1 is read as his bounty; the plain key with no E too', r['good'][0] == 'ok' and r['plain'][0] == 'ok', r)
            check('bounty: his key blinded for slot 0 or slot 2 in the first "pubkeys" place is refused', r['slot0'][0] is None and r['slot2'][0] is None, r)
            check('bounty: a blinded key with no E, an E that is not a point (02 off the curve, 04) or another valid E is refused', all(r[k][0] is None for k in ('noE', 'badE', 'badE2', 'otherE')), r)
            check('bounty: coins with different hashes are refused', r['hash'][0] is None, r)
            check('bounty: his key in the second "pubkeys" place is read for slot 2, and refused when blinded for slot 1 there', r['pos2'][0] == 'ok' and r['pos2wrong'][0] is None, r)
            check('bounty: 10 keys is read; 11 keys or 11 refund keys is refused', r['keys10'][0] == 'ok' and r['keys11'][0] is None and r['refund11'][0] is None, r)
            check('bounty: 64 coins is read; 65 coins is refused', r['coins64'][0] == 'ok' and r['coins65'][0] is None, r)
            check('bounty: the oversized ones are refused at once (under 1 s each, no point math); the largest allowed (64 coins, 10 keys, ours last) under 10 s',
                  all(r[k][1] < 1.0 for k in ('keys11', 'refund11', 'coins65')) and r['coins64keys10'][0] == 'ok' and r['coins64keys10'][1] < 10, {k: round(v[1], 2) for k, v in r.items()})
            # the same caps for a nutzap: 64 coins is the most (1.28), and its key check is one x(k·E) a coin
            # (the worst case: 63 coins blinded for Bob's receiving key, the 64th not, so every coin's x(k·E) is worked out)
            ps64 = await bo.ev("(() => { const id = Object.keys(Nutcade.S.counters)[0]; const rnd = () => CashuLib.bytesToHex(crypto.getRandomValues(new Uint8Array(32))); return Array.from({length: 65}, (_, i) => { const E = NutZap.randomPub(); return { id, amount: 1, secret: JSON.stringify(['P2PK', { nonce: rnd(), data: i >= 63 ? NutZap.randomPub() : NutP2BK.blind(__nzPriv(), E, 0) }]), C: NutP2BK.lockPub(), p2pk_e: E }; }); })()")
            ev65 = await al.ev(f'__nzEv({J(ps64)}, {{u:{J(M)}, p:{J(B_PK)}, dt:11}})')   # (built before the clock starts)
            t0 = time.time(); z65 = await bo.ev(f"NutZap.event({J(ev65)})"); t65 = time.time() - t0
            ev64 = await al.ev(f'__nzEv({J(ps64[:64])}, {{u:{J(M)}, p:{J(B_PK)}, dt:12}})')
            t0 = time.time(); z64 = await bo.ev(f"NutZap.event({J(ev64)})"); t64 = time.time() - t0
            check('bounty: a nutzap of 65 coins is refused as bad; one of 64 blinded coins, the last not for us, is refused as not ours, in under 5 s', z65 == 'bad' and z64 == 'lock' and t64 < 5, (z65, z64, round(t65, 2), round(t64, 2)))
        await section('bounty', bounty)

        async def giftnote():
            async def note(on):
                await set_blind(al, on); await al.home(); await al.click('[data-act=send]'); await al.wait(150); await al.pg.check('#giftOn'); await al.wait(100)
                t = await al.ev("document.querySelector('#giftBox').innerText"); await al.ev("Nutcade.closeSheet()"); return t
            on_t, off_t = await note(True), await note(False)
            check('gift sheet: with Hide who gets it on it says only NUTCADE 1.29 or newer or a NUT-28 wallet can claim it (no cashu.me)', GIFTNOTE in on_t and 'cashu.me' not in on_t, on_t[-250:])
            check('gift sheet: with it off it says NUTCADE or cashu.me with the same 12 words, as before', 'cashu.me using the same 12 words' in off_t and 'NUT-28' not in off_t, off_t[-250:])
        await section('giftnote', giftnote)

        async def nutshell():
            # a Nutshell-made P2BK token locked to Bob's key, claimed by NUTCADE; one to his receiving key, sent as a nutzap
            bb0 = await bo.bal()
            tok = py('send', os.path.join(TMP, 'ns-send'), M, 33, K['b_pub'])
            d = await bo.ev(f"__dec({J(tok)})")
            check('Nutshell: its P2BK token carries p2pk_e and a blinded key (not Bob\'s)', d and all(x['p2pk_e'] and lk(x)['data'] != K['b_pub'] for x in d), d[:1])
            r = await bo.ev(f"Nutcade.r8.recv({J(tok)}, 'from nutshell').then(t=>t.amount, e=>e.message)")
            check('Nutshell: Bob\'s NUTCADE claims a Nutshell-made P2BK token (33 SAT)', r == 33 and await bo.bal() == bb0 + 33, r)
            tok2 = py('send', os.path.join(TMP, 'ns-send'), M, 21, K['b_nzpub'])
            ps = await bo.ev(f"__dec({J(tok2)})")
            ev = await al.ev(f"__nzEv({J(ps)}, {{u:{J(M)}, p:{J(B_PK)}, c:'nutshell'}})")
            r2 = await bo.ev(f"NutZap.event({J(ev)})"); ok = await bo.until(f"{TOTAL} >= {bb0 + 54}", 20000)
            check('Nutshell: a nutzap made of Nutshell P2BK coins (to Bob\'s receiving key) is taken and claimed (21 SAT)', r2 == 'ok' and ok and await bo.bal() == bb0 + 54, (r2, await bo.bal() - bb0))
            # a NUTCADE-made blinded gift to a Nutshell wallet's key, claimed by Nutshell
            await set_blind(al, True)
            nsk = py('pub', os.path.join(TMP, 'ns-recv'))
            g = await gift(al, 44, key=nsk)
            check('Nutshell: a blinded NUTCADE gift to a Nutshell wallet\'s key', g.get('blinded') is True and g.get('locked') == nsk, g.get('locked'))
            got = py('redeem', os.path.join(TMP, 'ns-recv'), M, g['token'])
            check('Nutshell: Nutshell\'s wallet claims the blinded NUTCADE gift (44 SAT)', got == '44', got)
        await section('nutshell', nutshell)

        async def extralife():
            await set_blind(al, True)
            await al.ev("Nutcade.closeSheet()"); await al.home()
            await al.click('[data-act=extraOpen]'); await al.until("!!document.querySelector('#xlTo')", 5000); await al.wait(150)
            await al.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Bob').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
            ab0 = await al.bal()
            await al.fill('#amtIn', '500'); await al.click('[data-act=extraStart]')
            ok = await al.until("!!Nutcade.S.extra", 15000)
            ps = await al.ev("Nutcade.S.extra ? Nutcade.S.extra.proofs : []")
            ls = [lk(x) for x in ps]
            check('Extra Life: with Hide who gets it on, still locked to your own key with Bob\'s key as the refund key, no E (unchanged)', ok and ls and all(l['kind'] == 'P2PK' and l['data'] == K['a_pub'] and l['tags'].get('refund') == [K['b_pub']] and not l['e'] for l in ls), ls[:1])
            ok = await bo.until("Nutcade.S.heirlooms.some(h=>h.state==='waiting' && h.amount>=500)", 15000)
            check('Extra Life: Bob\'s NUTCADE accepts the heir copy as before', ok)
            await al.ev("Nutcade.closeSheet()"); await al.home(); await al.click('.extra-panel'); await al.wait(200)
            await al.click('[data-act=extraCash]'); await al.wait(100); await al.click('[data-act=extraCashGo]')
            ok = await al.until("!Nutcade.S.extra", 15000); await al.wait(400)
            check('Extra Life: cashed out with your own key, the 500 SAT back', ok and await al.bal() == ab0, await al.bal() - ab0)
            await al.ev("Nutcade.closeSheet()")
        await section('extralife', extralife)

        async def crash():
            # a blinded gift (nutzaps are never blinded) to Bob's key, the swap held and the page reloaded mid-send
            await set_blind(al, True)
            ab0, bb0 = await al.bal(), await bo.bal()
            SW = re.compile(re.escape(M) + r'/v1/swap$')
            async def held(route):
                try: r = await route.fetch()
                except Exception: return
                await asyncio.sleep(8)
                try: await route.fulfill(response=r)
                except Exception: pass
            await al.pg.route(SW, held)
            await al.ev(f"Nutcade.r8.sendEcash(130, 'crash', {J(K['b_pub'])}, undefined, {{blind:true, locktime: Math.floor(Date.now()/1000)+3600, txx:{{lockUntil:(Math.floor(Date.now()/1000)+3600)*1000, giftTo:'Bob'}}}}).catch(()=>{{}}); 0")
            rec = await al.until("Nutcade.S.ops.some(o=>o.kind==='send'&&o.outs.length)", 10000); await al.wait(800)
            outs_e = await al.ev("(Nutcade.S.ops.find(o=>o.kind==='send')||{outs:[]}).outs.filter(o=>o.send).map(o=>o.e)")
            await al.pg.reload(); await al.wait(800); await al.pg.unroute(SW)
            await al.until("Nutcade.S.ops.length===0", 60000); await al.wait(500)
            o = await al.ev("Nutcade.S.txs.filter(t=>t.type==='out'&&t.amount===130&&t.lockUntil)")
            check('crash: the journal record holds each locked output\'s E before the mint is asked', rec and outs_e and all(e and HEX66.fullmatch(e) for e in outs_e), outs_e)
            check('crash: after a reload the coins come back as the blinded gift, with their E, marked blinded', len(o) == 1 and o[0].get('blinded') is True and all(x.get('p2pk_e') for x in o[0]['sent']) and sorted(x['p2pk_e'] for x in o[0]['sent']) == sorted(outs_e), o[:1] and {k: o[0].get(k) for k in ('blinded', 'status')})
            r = await bo.ev(f"Nutcade.r8.recv({J(o[0]['token'] if o else '')}, 'crash gift').then(t=>t.amount, e=>e.message)")
            check('crash: Bob claims it once (130 SAT), the sender down exactly 130', r == 130 and await bo.bal() == bb0 + 130 and await al.bal() == ab0 - 130, (r, await bo.bal() - bb0, ab0 - await al.bal()))
        await section('crash', crash)

        async def tokens():
            await set_blind(al, True)
            SWA = re.compile(re.escape(M) + r'/v1/swap$')
            async def down(route):
                try: await route.abort()
                except Exception: pass
            g = await gift(al, 70, key=await al.ev("NutZap.randomPub()"), secs=5)
            d = await al.ev(f"__dec({J(g['token'])})")
            check('token: a blinded token decodes with every coin\'s p2pk_e (as on the line)', [x['p2pk_e'] for x in d] == [x['p2pk_e'] for x in g['sent']], (d[:1], g['sent'][:1]))
            re4 = await al.ev(f"CashuLib.getEncodedToken({{mint:{J(M)}, unit:'sat', proofs: __dec({J(g['token'])})}})")
            check('token: encoded again it is the same token (cashuB keeps "pe")', re4 == g['token'], (re4[:60], g['token'][:60]))
            # cashuA (V3): the bundled cashu-ts has no V3 encoder ({version:3} is ignored and a cashuB comes out: asserted, so a
            # library change is noticed), so the cashuA is written by hand, as wallets that still make V3 (Nutshell) write it,
            # and NUTCADE must read every coin's p2pk_e from it
            v3 = await al.ev(f"(()=>{{ try {{ return CashuLib.getEncodedToken({{mint:{J(M)}, unit:'sat', proofs: __dec({J(g['token'])})}}, {{version:3}}); }} catch (e) {{ return 'ERR '+e.message; }} }})()")
            check('token: the library writes no cashuA (V3) token: asked for one it writes the same cashuB', v3 == g['token'], v3[:40])
            ta = await al.ev(f"'cashuA' + btoa(JSON.stringify({{token:[{{mint:{J(M)}, proofs: __dec({J(g['token'])}).map(p=>({{id:p.id, amount:p.amount, secret:p.secret, C:p.C, p2pk_e:p.p2pk_e}}))}}], unit:'sat'}})).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'')")
            d3 = await al.ev(f"__dec({J(ta)})")
            check('token: a cashuA (V3) token of the blinded coins is read as a token with every coin\'s p2pk_e', ta.startswith('cashuA') and await al.ev(f"Nutcade.classify({J(ta)}).kind") == 'token' and [x['p2pk_e'] for x in d3] == [x['p2pk_e'] for x in g['sent']], d3[:1])
            # sound: the compact form has no room for E, so a blinded token goes as its whole text; a plain one is packed as before
            sb = await al.ev(f"(()=>{{ const b = Nutcade.soundBytes({J(g['token'])}); return {{ first: b[0], back: Nutcade.soundText(b), secs: Chiptune.seconds(b) }}; }})()")
            check('sound: a blinded gift is not packed (no 0xC1 compact form) but sent as its text, and comes back as the same token with its p2pk_e', sb['first'] != 0xC1 and sb['back'] == g['token'] and [x['p2pk_e'] for x in await al.ev(f"__dec({J(sb['back'])})")] == [x['p2pk_e'] for x in g['sent']] and sb['secs'] > 0, {k: sb[k] for k in ('first', 'secs')})
            sbf = await al.ev(f"Nutcade.soundBytes({J(g['token'])}, false)[0]")
            check('sound: "Faster, no proof" does not pack it either', sbf != 0xC1, sbf)
            plain = await al.ev("Nutcade.r8.sendEcash(9, 'plain for sound').then(t=>t.token)")
            sp = await al.ev(f"(()=>{{ const b = Nutcade.soundBytes({J(plain)}); return {{ first: b[0], n: b.length, back: __dec(Nutcade.soundText(b)), orig: __dec({J(plain)}) }}; }})()")
            check('sound: an unblinded token is still packed (0xC1) and comes back with the same coins', sp['first'] == 0xC1 and [(x['secret'], x['C'], x['amount']) for x in sp['back']] == [(x['secret'], x['C'], x['amount']) for x in sp['orig']] and len(plain) > sp['n'], {k: sp[k] for k in ('first', 'n')})
            await al.ev(f"Nutcade.r8.recv({J(plain)}, 'back', {{own:true, hand:true}}).catch(()=>0)")
            # the gift's own line: Play as sound opens the sound sheet with the text form (no error)
            if await al.ev("!!(window.Chiptune && Chiptune.canPlay && Chiptune.canPlay())"):
                await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
                await al.ev(f"document.querySelector('[data-act=tx][data-id={J(g['id'])}]').click()"); await al.wait(250)
                await al.ev("(document.querySelector('.sheet [data-act=ctPlay]')||{click(){}}).click()"); await al.wait(400)
                st = await al.sheet_text()
                check('sound: Play as sound on the blinded gift opens the sound sheet (the text form) without an error', 'Hold this phone near' in st and not al.errs, st[:200])
                await al.ev("Chiptune.stop && Chiptune.stop(); Nutcade.closeSheet()")
            # the backup, restored with the 12 words on a new phone, takes the gift back there (this phone's own return held off meanwhile)
            await al.pg.route(SWA, down)
            d = await al.ev("Nutcade.r8.backupData()")
            words = await al.ev("Nutcade.S.seed.mnemonic")
            n = await wallet(b, 'pb-newphone')
            await n.gate_restore(); await n.fill('#phraseIn', words); await n.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await n.fill('#rmExtra', M)
            await n.click('[data-act=doRestorePhrase]'); await n.until("!document.querySelector('[data-act=doRestorePhrase]')", 90000); await n.wait(600)
            await n.ev("Nutcade.closeSheet()")
            if await n.until("!!document.querySelector('[data-act=gateStart]')", 4000): await n.gate_step('gateStart', "!!document.querySelector('.tabbar')")
            await n.wait(300); await n.ev("Nutcade.closeSheet()"); nb0 = await n.bal()
            res = await n.ev(f"Nutcade.r8.importBackup(JSON.parse({J(d)})).then(()=>'ok', e=>'ERR '+e.message)"); await n.wait(2500)
            t = await n.ev(f"Nutcade.S.txs.find(t=>t.id==={J(g['id'])})||null")
            check('backup: the blinded gift comes in with the backup, its coins\' E and its blinded mark kept', res == 'ok' and t and t.get('blinded') is True and [x.get('p2pk_e') for x in t['sent']] == [x['p2pk_e'] for x in g['sent']] and t['token'] == g['token'], (res, t and t.get('status')))
            await n.wait(max(0, int(g['lockUntil'] / 1000 - time.time()) * 1000 + 1500))
            r = await n.ev(f"Nutcade.r8.recv({J(g['token'])}, 'back', {{own:true, hand:true}}).then(t=>t.amount, e=>e.message)")
            ok = await n.until(f"Nutcade.S.txs.find(t=>t.id==={J(g['id'])}).status==='reclaimed'", 15000)   # (by hand, or by its own background return)
            check('backup: after the date the new phone takes it back with the blinded refund key (70 SAT, once)', ok and await n.bal() == nb0 + 70, (r, await n.bal() - nb0))
            await n.pg.context.close(); await al.pg.unroute(SWA)
        await section('tokens', tokens)

        async def history():
            await al.ev("Nutcade.closeSheet()"); await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
            tid = await al.ev("(Nutcade.S.txs.find(t=>t.blinded)||{}).id"); pid = await al.ev("(Nutcade.S.txs.find(t=>t.lockUntil && !t.blinded)||{}).id")
            await al.ev(f"document.querySelector('[data-act=tx][data-id={J(tid)}]').click()"); await al.wait(250)
            t1 = await al.sheet_text(); await al.ev("Nutcade.closeSheet()")
            await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
            await al.ev(f"document.querySelector('[data-act=tx][data-id={J(pid)}]').click()"); await al.wait(250)
            t2 = await al.sheet_text(); await al.ev("Nutcade.closeSheet()")
            check('history: a blinded send says Receiver: Hidden in the ecash (P2BK); a plain one does not', 'Hidden in the ecash (P2BK)' in t1 and 'Hidden in the ecash' not in t2, (t1[-300:], t2[-200:]))
        await section('history', history)

        async def duress():
            e = await wallet(b, 'pb-ed'); await e.create(); await e.add_mint(M); await e.use(M); await e.receive_ln(1000)
            await set_blind(e, True); await set_pin(e)
            await settings(e); await e.click('[data-act=duressOpen]'); await e.wait(250)
            await pad(e, PIN); await e.wait(800); await pad(e, DPIN); await e.wait(300); await pad(e, DPIN); await e.until("!!document.querySelector('#duressAmt')", 8000)
            await e.fill('#duressAmt', '100'); await e.click('[data-act=duressMake]'); await e.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await e.ev("Nutcade.closeSheet()")
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            await settings(e)
            check('duress: the duress wallet has its own setting: off, though the real wallet has it on', await e.ev("Nutcade.S.prefs.p2bk") is not True and not await e.ev("document.querySelector('#p_p2bk').checked"))
            await e.click('#p_p2bk'); await e.wait(300)
            g = await gift(e, 30, key=await e.ev("NutZap.randomPub()"))
            check('duress: there it works like any wallet: on, and a gift is blinded', await e.ev("Nutcade.S.prefs.p2bk") is True and g.get('blinded') is True and all(lk(x)['e'] for x in g['sent']))
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            await set_blind(e, False)
            await e.pg.reload(); await e.wait(800); await unlock(e, DPIN); await e.wait(800)
            check('duress: turning it off in the real wallet leaves the duress wallet\'s on', await e.ev("Nutcade.S.prefs.p2bk") is True)
            await e.pg.reload(); await e.wait(800); await unlock(e, PIN); await e.wait(800)
            check('duress: and the real wallet\'s stays off', await e.ev("Nutcade.S.prefs.p2bk") is False)
            await e.pg.context.close()
        await section('duress', duress)

        async def langs():
            new = ["Hide who gets it (P2BK)", "Receiver", "Hidden in the ecash (P2BK)", WHATS, GIFTNOTE]
            page = urllib.request.urlopen(URL, timeout=10).read().decode('utf-8')
            check('langs: the What\'s new list has the P2BK line', J(WHATS)[1:-1].replace("'", "\\'") in page or WHATS.replace("'", "\\'") in page)
            for lang in ('es', 'pt', 'de', 'fr'):
                x = await wallet(b, 'pb-' + lang, lang); await x.create(); await x.add_mint(M); await x.use(M)
                await x.ev(f"Nutcade.S.txs.unshift({{id:'pbfake', type:'out', method:'ecash', amount:5, mint:{J(M)}, status:'claimed', ts:Date.now(), note:'x', blinded:true}}); Nutcade.refresh()")
                await settings(x); st = await x.ev("document.querySelector('#set-privacy').innerText")
                await x.click('[data-act=tab][data-tab=history]'); await x.wait(200)
                await x.ev("document.querySelector('[data-act=tx][data-id=pbfake]').click()"); await x.wait(250)
                dt = await x.sheet_text(); await x.ev("Nutcade.closeSheet()")
                tr = await x.ev(f"{J(new)}.map(s=>Nutcade.tr(s))")
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/P2BK|Hide who|receiver's key|Hidden in the ecash|Receiver/i.test(s))")
                check(f'{lang}: the P2BK texts show translated (Settings, the history row, What\'s new), no missing translation',
                      'Hide who gets it' not in st and "receiver's key" not in st and 'P2BK' in st and 'Hidden in the ecash' not in dt and 'P2BK' in dt and all(a != s for a, s in zip(tr, new)) and not miss, (st[-200:], dt[-150:], miss))
                await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not al.errs and not bo.errs, (al.errs[:3], bo.errs[:3]))
        await al.pg.screenshot(path=os.path.join(OUT, 'p2bk.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
