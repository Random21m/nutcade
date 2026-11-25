"""The bundled cashu-ts and NUTCADE's own lock reading (1.35.0).
Uses the local test mint 3339 (no fees) and Nutshell's own wallet code (tests/lock_py.py, run with MINT_PY) as an
independent implementation.

bundle:   src/lib.min.js is exactly the pinned build (cashu-ts 5.0.0-rc.13 with the other libraries as listed in src/README.md),
          and its export list is exactly the names the app uses (AuthManager and OIDCAuth included). A library change is
          a deliberate change of this pin.
derive:   the coins of a wallet are the NUT-13 coins of its 12 words: every secret NUTCADE got from the mint is the one
          Nutshell derives for that keyset at a counter below the wallet's counter; the same 12 words restored on a second
          device find exactly the same coins and balance.
fixed:    fixed 12 words restored on a fresh test mint and paid 400 SAT hold exactly the coins (secret, signature, amount,
          keyset) and counter NUTCADE 1.34 made with cashu-ts 4.13.1; a token that uses only some coins leaves the others held;
          a second device restoring the words finds the same coins.
reader:   NUTCADE's lock reader (lockOf, app.js) against the library's rules, edge by edge: locktime 0 has expired,
          a lock expires only after its locktime second, a malformed locktime never expires (#1323); an HTLC hash is
          compared in lower case (#1415); P2PK data must be a key (#1393); n_sigs / n_sigs_refund need a whole value (#1413);
          and the library itself (PaymentRequest.toP2PKOptions) refuses the same malformed tags.
nutzap:   the nutzap lock check refuses the same edges.
bounty:   a bounty is read by the library's lock rules (malformed, or needing two signatures: no bounty); one whose hash is
          written in capitals is no bounty: the library would compare it in lower case (#1415), but the test mint refuses
          such a coin outright (shown with a real one made by Nutshell), while the same bounty in lower case is claimed.
heir:     an Extra Life copy is held only when the library could spend it by its refund path: locktime "0" (expired: held,
          and a real one from Nutshell is claimed at once), a malformed locktime, a refund threshold without a value or a lock
          whose data is no key: not held.
takeback: a gift is never taken back in its locktime's own second (the mint and the library still read it as locked).
giftkey:  a gift to a key that is no point on the curve is refused before anything is spent.
ys:       a journal record from before 1.35 (coins without keyset ids) asks the mint about its coins with the secp256k1 Y
          that cashu-ts 4.13.1 computed (Nutshell's hash_to_curve), whatever keysets the wallet holds (a v3 "02" keyset, or none).
b64:      a token in standard base64 ('+' '/' and '=' padding, which cashu-ts 4.13.1 read and 5 refuses) is read as before:
          cashuB and cashuA, pasted, and one saved waiting by 1.34 claimed when the wallet is online.
request:  a payment request asking for a lock NUTCADE can't make exactly (HTLC, another kind, data that isn't a key,
          an x-only key, an n_sigs without value) is refused before anything is spent (before 1.35 it was paid with an
          UNLOCKED token); a P2PK request with tags is paid with exactly the lock it asked for (library parity); a plain
          P2PK request is paid as before. The new text in five languages.
LIB_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, hashlib, json, os, re, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.environ.get('MINT_PY', 'python3')
TMP = tempfile.mkdtemp(prefix='lib-')
TOTAL = "Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)"
# sha256 of src/lib.min.js: cashu-ts 5.0.0-rc.13 (1.35.0; 4.13.1 before), nostr-tools 2.26.0 (its @noble/curves and @noble/hashes deduplicated to 2.4.0),
# @scure/bip32, bip39, base 2.4.0, @noble/hashes, curves, ciphers 2.4.0, qrcode-generator 2.0.4, jsqr 1.4.0, zxing-wasm 3.1.6
LIB_SHA = '431b4245e0db5e630e4fc20e9ec3a3156576502efedcc885552d4711781da68c'
EXPORTS = ['Amount', 'AuthManager', 'HDKey', 'Mint', 'OIDCAuth', 'PaymentRequest', 'Wallet', 'bech32', 'bytesToHex', 'decodePaymentRequest',
           'finalizeEvent', 'generateMnemonic', 'getDecodedToken', 'getDecodedTokenBinary', 'getEncodedToken', 'getEncodedTokenBinary',
           'getPubKeyFromPrivKey', 'getTokenMetadata', 'hexToBytes', 'jsQR', 'mnemonicToSeedSync', 'nip17', 'nip19decode', 'nip44', 'nip59',
           'nostrPub', 'nprofileEncode', 'npubEncode', 'prepareZXingModule', 'qrcode', 'readBarcodes', 'sha256', 'validateMnemonic',
           'verifyEvent', 'wordlist']
REQ_ERR = "This request asks for a lock NUTCADE can't make, so it can't be paid from here. Nothing was sent."
K1 = '02' + '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'   # (the generator: a valid key nobody here holds)
K2 = '03' + 'c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'
H = 'ab' * 32
FIXED = 'legal winner thank year wave sausage worth useful legal winner thank yellow'   # (a BIP-39 test vector)
# what NUTCADE 1.34/1.35 with cashu-ts 4.13.1 (a014cbe..d3ac69e) holds after restoring FIXED on a fresh test mint 3339 and a 400 SAT deposit
FIXED_PIN = {"ps": [{"id": "011e97640fd5b6c1b3e5a3111ff10d7983b7ca7833bedd2b55bf1da7eab178d446", "amount": 256, "secret": "750148f5000ddadbf9e813b7435697526d4f0a7cf1a59349febf6230f15ffd67", "C": "0352e58fd89a07a8190baf8b9a94a5c847a08caa5249b902784cc418cd7c67b3c0"}, {"id": "011e97640fd5b6c1b3e5a3111ff10d7983b7ca7833bedd2b55bf1da7eab178d446", "amount": 16, "secret": "8681f751bd95b19b93794328d43bfdd66f902a1b700d20ecbed39fecc6208d61", "C": "027d5cc8d8967054344fcaa527ed626856f9923dd9a8722b2e61030a91d1ab3378"}, {"id": "011e97640fd5b6c1b3e5a3111ff10d7983b7ca7833bedd2b55bf1da7eab178d446", "amount": 128, "secret": "e910905bc3028c580f07aead4940b7060859ab3995caa4d47fede70c6d43f91c", "C": "034033f96d1e06eb767dce41c7b45c746c922fa691badcbd89924ce7c71f30a37e"}], "ctr": {"011e97640fd5b6c1b3e5a3111ff10d7983b7ca7833bedd2b55bf1da7eab178d446": 3}}


def py(*args, inp=None):
    r = subprocess.run([PYW, '-I', os.path.join(HERE, 'lock_py.py')] + [str(a) for a in args], input=J(inp) if inp is not None else None,
                       capture_output=True, text=True, cwd=TMP, timeout=180)
    if r.returncode: raise RuntimeError('lock_py ' + args[0] + ': ' + (r.stderr or r.stdout)[-400:])
    return r.stdout.strip().splitlines()[-1]


def sec(kind, data, tags=None, nonce='00'):
    d = {'nonce': nonce, 'data': data}
    if tags is not None: d['tags'] = tags
    return J([kind, d])


async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def leave_gate(w):   # (as in backup_qa.py: after a restore from the start screen, past PLAYER 1 READY to the wallet)
    await w.ev("Nutcade.closeSheet()")
    if await w.until("!!document.querySelector('[data-act=gateStart]')", 4000): await w.gate_step('gateStart', "!!document.querySelector('.tabbar')")
    await w.wait(300); await w.ev("Nutcade.closeSheet()")


async def section(name, fn):
    only = [x for x in os.environ.get('LIB_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def funded(b, name, amt=300):
    w = await wallet(b, name); words = await w.create(); await w.add_mint(M); await w.use(M)
    ok = await w.receive_ln(amt)
    return w, words, ok


def fake_token(kid, secrets, amount=8):   # a token of made-up coins (never sent to a mint): for the readers only
    return {'mint': M, 'unit': 'sat', 'proofs': [{'id': kid, 'amount': amount, 'secret': s, 'C': K1} for s in secrets]}


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al, words, ok = await funded(b, 'lib-al', 400)
        check('setup: a wallet with 400 SAT at the test mint', ok and await al.bal() == 400, await al.bal())
        kid = await al.ev(f"Object.keys(Nutcade.S.counters).find(k => (Nutcade.S.proofs[{J(M)}]||[]).some(p=>p.id===k))")
        enc = lambda t: al.ev(f"CashuLib.getEncodedToken({J(t)})")

        async def bundle():
            got = hashlib.sha256(open(os.path.join(HERE, '..', 'src', 'lib.min.js'), 'rb').read()).hexdigest()
            check('bundle: src/lib.min.js is the pinned build (cashu-ts 5.0.0-rc.13); a library change changes this pin on purpose', got == LIB_SHA, got)
            names = await al.ev("Object.keys(CashuLib).sort()")
            check('bundle: the export list is exactly the names the app uses (AuthManager and OIDCAuth included)', names == sorted(EXPORTS), sorted(set(names) ^ set(EXPORTS)))
        await section('bundle', bundle)

        async def fixed():
            # the same 12 words on a fresh test mint (its keys fixed by start_mints.sh) give the same coins, byte for byte, as
            # NUTCADE 1.34 (a07f282, cashu-ts 4.13.1) gave: secrets, signatures, amounts, keyset and counter
            async def restored(name):
                f = await wallet(b, name)
                await f.gate_restore(); await f.fill('#phraseIn', FIXED); await f.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await f.fill('#rmExtra', M)
                await f.click('[data-act=doRestorePhrase]'); await f.until("!document.querySelector('[data-act=doRestorePhrase]')", 90000); await f.wait(600)
                await leave_gate(f); await f.use(M); return f
            f = await restored('lib-fixed')
            ok = await f.receive_ln(400)
            got = await f.ev(f"(() => {{ const ps = (Nutcade.S.proofs[{J(M)}]||[]).map(p => ({{id: p.id, amount: p.amount, secret: p.secret, C: p.C}})).sort((a, b) => a.secret < b.secret ? -1 : 1); return {{ps, ctr: Nutcade.S.counters}}; }})()")
            if os.environ.get('LIB_PIN_PRINT'): print('PINNED', J(got), flush=True)
            check('fixed: the fixed 12 words, restored and paid 400 SAT, hold exactly the coins and counter NUTCADE 1.34 (cashu-ts 4.13.1) made', ok and got == FIXED_PIN, got)
            # a payment that uses only some coins: the ones it leaves out stay, untouched (cashu-ts 5 hands them back beside the swap)
            before = {p['secret'] for p in got['ps']}
            tok, e = await f.send_ecash(20)
            left = await f.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).map(p => p.secret)")
            sent = await f.ev(f"CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.counters)).proofs.map(p => p.secret)") if tok else []
            spent_in = before - set(left)
            check('fixed: a 20 SAT token from 400 SAT: the balance is 380 and every coin the swap didn\'t take is still held, the same coin', not e and await f.bal() == 380 and len(spent_in) >= 1 and (before - spent_in) <= set(left) and len(sent) > 0, (e, await f.bal(), len(spent_in)))
            g = await restored('lib-fixed2')
            got2 = await g.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).map(p => p.secret).sort()")
            check('fixed: the same words restored on a second device find exactly the first device\'s coins and the unclaimed token\'s (400 SAT)', got2 == sorted(left + sent) and await g.bal() == 400, (len(got2), len(left), len(sent)))
            await f.pg.context.close(); await g.pg.context.close()
        await section('fixed', fixed)

        async def derive():
            ps = await al.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).map(p=>({{id:p.id, secret:p.secret, amount:p.amount}}))")
            n = await al.ev(f"Nutcade.S.counters[{J(kid)}]")
            ref = json.loads(py('derive', inp={'words': words, 'keyset': kid, 'n': n}))
            check('derive: every coin is the NUT-13 coin of the 12 words (Nutshell derives the same secret at a counter below the wallet\'s)',
                  ps and all(x['id'] == kid and x['secret'] in ref for x in ps), (kid, n, len(ps)))
            bo = await wallet(b, 'lib-restore')
            await bo.gate_restore(); await bo.fill('#phraseIn', words); await bo.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await bo.fill('#rmExtra', M)
            await bo.click('[data-act=doRestorePhrase]'); await bo.until("!document.querySelector('[data-act=doRestorePhrase]')", 90000); await bo.wait(600); await bo.ev("Nutcade.closeSheet()")
            got = await bo.ev(f"(Nutcade.S.proofs[{J(M)}]||[]).map(p=>p.secret).sort()")
            check('derive: the same 12 words restored on a second device find exactly the same coins and balance', got == sorted(x['secret'] for x in ps) and await bo.bal() == await al.bal(), (len(got), len(ps)))
            check('derive: and its counter goes on from where the first device is', await bo.ev(f"Nutcade.S.counters[{J(kid)}]||0") >= n)
            await bo.pg.context.close()
        await section('derive', derive)

        async def reader():
            now = int(time.time())
            cases = [   # (name, secret, expected: None = refused, else {field: value})
                ('P2PK, no tags', sec('P2PK', K1), {'kind': 'P2PK', 'keys': [K1], 'locktime': None, 'exp': False}),
                ('locktime "0" has expired (#1323)', sec('P2PK', K1, [['locktime', '0'], ['refund', K2]]), {'locktime': 0, 'exp': True}),
                ('locktime in the past has expired', sec('P2PK', K1, [['locktime', str(now - 100)], ['refund', K2]]), {'exp': True}),
                ('locktime in the future has not', sec('P2PK', K1, [['locktime', str(now + 3600)], ['refund', K2]]), {'exp': False}),
                ('a locktime with no value: never expires (no locktime)', sec('P2PK', K1, [['locktime']]), {'locktime': None, 'exp': False}),
                ('a malformed locktime ("1.7e9") never expires', sec('P2PK', K1, [['locktime', '1.7e9']]), {'locktime': None, 'exp': False}),
                ('a negative locktime never expires', sec('P2PK', K1, [['locktime', '-5']]), {'locktime': None, 'exp': False}),
                ('refund keys with a malformed locktime: refused', sec('P2PK', K1, [['locktime', 'soon'], ['refund', K2]]), None),
                ('refund keys without a locktime: refused', sec('P2PK', K1, [['refund', K2]]), None),
                ('two locktime values: refused', sec('P2PK', K1, [['locktime', '1', '2']]), None),
                ('P2PK data that is no key: refused (#1393)', sec('P2PK', ''), None),
                ('P2PK data that is a 64-hex x-only key: refused (the test mints refuse it too)', sec('P2PK', K1[2:]), None),
                ('n_sigs without a value: refused (#1413)', sec('P2PK', K1, [['n_sigs']]), None),
                ('n_sigs_refund without a value: refused (#1413)', sec('P2PK', K1, [['locktime', '1'], ['refund', K2], ['n_sigs_refund']]), None),
                ('n_sigs "1.0": refused', sec('P2PK', K1, [['n_sigs', '1.0']]), None),
                ('n_sigs 0: refused', sec('P2PK', K1, [['n_sigs', '0']]), None),
                ('n_sigs above the keys: refused', sec('P2PK', K1, [['n_sigs', '2']]), None),
                ('n_sigs 2 with two keys', sec('P2PK', K1, [['pubkeys', K2], ['n_sigs', '2']]), {'nSigs': 2, 'keys': [K1, K2]}),
                ('the same tag twice: refused', sec('P2PK', K1, [['sigflag', 'SIG_INPUTS'], ['sigflag', 'SIG_INPUTS']]), None),
                ('an unknown sigflag: refused', sec('P2PK', K1, [['sigflag', 'SIG_NONE']]), None),
                ('an empty tag: refused', sec('P2PK', K1, [[]]), None),
                ('the same key twice: refused', sec('P2PK', K1, [['pubkeys', K1]]), None),
                ('HTLC hash in capitals is read in lower case (#1415)', sec('HTLC', H.upper(), [['pubkeys', K1]]), {'kind': 'HTLC', 'hash': H}),
                ('HTLC hash that is not 32 bytes of hex: refused', sec('HTLC', 'zz', [['pubkeys', K1]]), None),
                ('another kind: refused', sec('NUT', K1), None),
                ('no nonce: refused', J(['P2PK', {'data': K1}]), None),
            ]
            res = await al.ev(f"""(() => {{ const now = {now * 1000}; return {J([c[1] for c in cases])}.map(s => {{ const l = Nutcade.lk.of(s); return l && {{ kind: l.kind, keys: l.keys, locktime: l.locktime,
                exp: l.expired(now), hash: l.hash, nSigs: l.nSigs }}; }}); }})()""")
            for (name, _, want), got in zip(cases, res):
                ok = (got is None) if want is None else (got is not None and all(got.get(k) == v for k, v in want.items()))
                check('reader: ' + name, ok, got)
            lt = now - 5
            edge = await al.ev(f"(() => {{ const l = Nutcade.lk.of({J(sec('P2PK', K1, [['locktime', str(lt)], ['refund', K2]]))}); return [l.expired({lt * 1000}), l.expired({lt * 1000 + 999}), l.expired({lt * 1000 + 1000})]; }})()")
            check('reader: a lock expires only AFTER its locktime second (not at it, not within it; from the next second on)', edge == [False, False, True], edge)
            # the library's own rules, where the bundle shows them: PaymentRequest.toP2PKOptions reads a request's lock as it would spend it
            lib = await al.ev(f"""(() => {{ const t = n => {{ try {{ const o = new CashuLib.PaymentRequest({{transport: [], id: 'x', amount: 10, unit: 'sat', mints: undefined, description: 'd', singleUse: true, nut10: n}}).toP2PKOptions(); return o ? 'ok' : 'none'; }} catch (e) {{ return 'refused'; }} }};
                return [t({{kind:'P2PK', data:{J(K1)}, tags:[['n_sigs']]}}), t({{kind:'P2PK', data:{J(K1)}, tags:[['n_sigs_refund']]}}), t({{kind:'P2PK', data:'', tags:[]}}),
                        t({{kind:'P2PK', data:{J(K1)}, tags:[['n_sigs','1.0']]}}), t({{kind:'P2PK', data:{J(K1)}, tags:[['locktime','1','2']]}}), t({{kind:'P2PK', data:{J(K1)}, tags:[['sigflag','SIG_NONE']]}}), t({{kind:'P2PK', data:{J(K1)}, tags:[['locktime','0']]}})]; }})()""")
            check('reader: the bundled library refuses the same: n_sigs or n_sigs_refund without a value, no data, n_sigs "1.0", two locktimes, an unknown sigflag; locktime 0 is read', lib == ['refused'] * 6 + ['ok'], lib)
        await section('reader', reader)

        async def nutzap():
            pub = await al.ev("NutZap.pub()")
            r = await al.ev(f"{J([sec('P2PK', pub, [['n_sigs']]), sec('P2PK', '', []), sec('P2PK', pub, [['locktime', '0']]), sec('P2PK', pub, [['n_sigs', '1.0']]), sec('P2PK', pub.upper()), sec('P2PK', pub, [['n_sigs', '1']])])}.map(s => NutZap.lock(s))")
            check('nutzap: the lock check refuses n_sigs without a value, no key, any locktime (0 too), n_sigs "1.0"; takes our key in any case and n_sigs 1',
                  [bool(x) for x in r[:4]] == [False] * 4 and r[4] == pub and r[5] == pub, r)
        await section('nutzap', nutzap)

        async def bounty():
            lp = await al.ev("NutP2BK.lockPub()")
            def bt(tags, data=H.upper()): return [sec('HTLC', data, tags, nonce=str(i)) for i in range(2)]
            res = []
            for tg in ([['pubkeys', lp]], [['pubkeys', lp], ['n_sigs']], [['pubkeys', lp, K1], ['n_sigs', '2']], [['pubkeys', lp], ['locktime', 'x'], ['refund', K2]]):   # (all with a capital hash but the last below)
                t = await enc(fake_token(kid, bt(tg)))
                res.append(await al.ev(f"NutP2BK.bounty({{token:{J(t)}, amount: 16}}).then(r => r && r.H)"))
            res.append(await al.ev(f"NutP2BK.bounty({{token:{J(await enc(fake_token(kid, bt([['pubkeys', lp]], data=H))))}, amount: 16}}).then(r => r && r.H)"))
            check('bounty: a well-formed bounty locked to our key is read', res[4] == H, res[4])
            check('bounty: a lock with n_sigs and no value, one needing two signatures, refund keys with a malformed locktime: no bounty', res[1:4] == [None, None, None], res[1:4])
            check('bounty: a hash written in capitals is no bounty (the library compares it in lower case, #1415, but the test mint refuses such a coin outright: below)', res[0] is None, res[0])
            # a real one: Nutshell locks coins with a capital hash to our key: NUTCADE doesn't show it, and the mint indeed refuses it
            pre = os.urandom(32).hex(); h = hashlib.sha256(bytes.fromhex(pre)).hexdigest()
            for hh, name in ((h.upper(), 'capital'), (h, 'lower-case')):
                tok = py('send', os.path.join(TMP, 'nb'), M, 24, inp={'kind': 'HTLC', 'data': hh, 'tags': [['pubkeys', lp], ['locktime', str(int(time.time()) + 3600)], ['refund', K2]]})
                got = await al.ev(f"NutP2BK.bounty({{token:{J(tok)}, amount: 24}}).then(r => r && r.H)")
                unlocked = await al.ev(f"(() => {{ const d = CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.counters)); return CashuLib.getEncodedToken({{mint: d.mint, unit: 'sat', proofs: d.proofs.map(p => Object.assign({{}}, p, {{witness: JSON.stringify({{preimage: {J(pre)}}})}}))}}); }})()")
                b0 = await al.bal(); _, e, _ = await al.receive_token(unlocked, 'bounty'); d = await al.bal() - b0
                if name == 'capital': check('bounty: a real Nutshell bounty with a capital hash: not shown, and the mint refuses its claim (nothing booked)', got is None and d == 0 and 'HTLC' in e, (got, d, e))
                else: check('bounty: the same bounty with its hash in lower case: shown, and claimed at the mint with the preimage and our key', got == h and d == 24, (got, d, e))
        await section('bounty', bounty)

        async def heir():
            lp = await al.ev("NutP2BK.lockPub()")
            async def held(tags, data=K1, frm='f' * 64):
                t = await enc(fake_token(kid, [sec('P2PK', data, tags, nonce=str(i)) for i in range(2)]))
                await al.ev(f"Nutcade.S.heirlooms = Nutcade.S.heirlooms.filter(h => h.from !== {J(frm)})")
                await al.ev(f"Nutcade.lk.heir({{t: 'nutcade-extralife', token: {J(t)}}}, {J(frm)})")
                return await al.ev(f"(Nutcade.S.heirlooms.find(h => h.from === {J(frm)} && h.state === 'waiting') || {{}}).until ?? null")
            fut = int(time.time()) + 86400
            r = [await held([['locktime', str(fut)], ['refund', lp]]), await held([['locktime', '0'], ['refund', lp]]), await held([['locktime', '1.7e9'], ['refund', lp]]),
                 await held([['locktime', str(fut)], ['refund', lp], ['n_sigs_refund']]), await held([['locktime', str(fut)], ['refund', lp]], data=''),
                 await held([['locktime', str(fut)], ['refund', lp, K1], ['n_sigs_refund', '2']])]
            check('heir: an Extra Life copy with a future locktime and our refund key is held until then', r[0] == fut * 1000, r[0])
            check('heir: locktime "0" has expired (#1323): held, claimable now (before 1.35 refused)', r[1] == 0, r[1])
            check('heir: a malformed locktime (never expires), n_sigs_refund without a value, data that is no key, two refund signatures: not held', r[2:] == [None] * 4, r[2:])
            await al.ev("Nutcade.S.heirlooms = Nutcade.S.heirlooms.filter(h => h.from !== 'f'.repeat(64))")
            tok = py('send', os.path.join(TMP, 'nh'), M, 32, inp={'kind': 'P2PK', 'data': K1, 'tags': [['locktime', '0'], ['refund', lp]]})
            b0 = await al.bal(); _, e, _ = await al.receive_token(tok, 'heir')
            check('heir: a real copy from Nutshell with locktime "0" is claimed at once with our refund key (library and mint read it as expired)', await al.bal() == b0 + 32, (e, await al.bal() - b0))
        await section('heir', heir)

        async def takeback():
            r = await al.ev("""(async () => { const now = Date.now(), s = Math.floor(now / 1000) * 1000; const out = [];
                for (const lu of [s, s - 1000 + 1]) { try { await Nutcade.lk.takeBack({ id: 'x' + lu, lockUntil: lu, giftTo: 'Bob', token: 'cashuBnone' }); out.push('went'); }
                  catch (e) { out.push(/locked to/.test(e.message) ? 'locked' : 'went'); } }
                return out; })()""")
            check('takeback: never in the locktime\'s own second (the mint still reads it as locked); from the next second on it is tried', r == ['locked', 'went'], r)
        await section('takeback', takeback)

        async def giftkey():
            # a gift locked to a key that is no point on the curve: cashu-ts 5 refuses such a lock, and NUTCADE says so first
            b0 = await al.bal()
            await al.home(); await al.click('[data-act=send]'); await al.wait(150); await al.pg.check('#giftOn')
            await al.ev("const s=document.querySelector('#giftTo'); if (s) { s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})) }")
            await al.fill('#giftKey', '02' + 'cd' * 32); await al.fill('#amtIn', '20'); await al.click('[data-act=doSendEcash]'); await al.wait(1500)
            e = await al.err(); await al.close()
            check('giftkey: a gift to a key that is not on the curve is refused with the usual "can\'t be read" and nothing is spent', "can't be read" in e and await al.bal() == b0, (e, b0, await al.bal()))
        await section('giftkey', giftkey)

        async def ys():
            ss = [os.urandom(32).hex() for _ in range(3)]
            ref = json.loads(py('y', inp=ss))
            V3 = '02' + 'ab' * 32
            got = await al.ev(f"""(async () => {{ const w = await Nutcade.lk.wallet({J(M)}), ss = {J(ss)}, out = [];
                const fakes = [w, {{ keyChain: {{ getKeysets: () => [{{ id: {J(V3)} }}] }}, keysetId: {J(V3)} }}, {{ keyChain: {{ getKeysets: () => [] }}, keysetId: undefined }}, {{}}];
                for (const f of fakes) {{ try {{ out.push(Nutcade.lk.ys(f, ss, null).map(q => w.computeY(q.secret, q.id))); }} catch (e) {{ out.push('threw: ' + e.message); }} }}
                const mixed = Nutcade.lk.ys(fakes[1], ss, {{ [ss[0]]: {J(kid)} }}).map(q => q.id);
                return {{ out, mixed }}; }})()""")
            names = ['the wallet\'s own keysets', 'a v3 ("02") keyset first', 'no keysets at all', 'no keychain']
            for name, o in zip(names, got['out']):
                check(f'ys: a record without keyset ids, {name}: each coin\'s Y is the 4.13.1 one (Nutshell hash_to_curve, secp256k1)', o == ref, (o, ref))
            check('ys: a coin whose id the record has keeps that id', got['mixed'][0] == kid and got['mixed'][1] != V3, got['mixed'])
        await section('ys', ys)

        async def b64():
            def std(t):
                body = t[6:].replace('-', '+').replace('_', '/'); return t[:6] + body + '=' * (-len(body) % 4)
            async def mk(amount, v3=False):
                for _ in range(8):
                    t = await al.ev(f"Nutcade.r8.sendEcash({amount}, 'b64', null, {J(M)}).then(x => x.token)")
                    if v3:   # (cashu-ts 5 makes no cashuA: written here as NUT-00 V3, JSON in base64url as 4.13.1 wrote it)
                        t = await al.ev(f"""(() => {{ const d = CashuLib.getDecodedToken({J(t)}, Object.keys(Nutcade.S.counters));
                            const j = JSON.stringify({{ token: [{{ mint: d.mint, proofs: d.proofs.map(p => ({{ id: p.id, amount: Number(String(p.amount)), secret: p.secret, C: p.C }})) }}], unit: d.unit }});
                            return 'cashuA' + btoa(j).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, ''); }})()""")
                    if re.search(r'[-_]', t[6:]): return std(t)
                    await al.receive_token(t)   # (no '-' or '_' in it: taken back, another one made)
                return None
            for name, v3 in (('cashuB', False), ('cashuA', True)):
                t = await mk(16, v3); b0 = await al.bal()
                _, e, _ = await al.receive_token(t)
                check(f'b64: a {name} token in standard base64 (+ / =) is received, all of it (on e9b0b98 "can\'t be read")', t and re.search(r'[+/]', t) and await al.bal() == b0 + 16, (e, await al.bal() - b0, (t or '')[:40]))
            t = await mk(24); b0 = await al.bal()
            await al.ev(f"Nutcade.S.txs.unshift({{ id: 'b64old', ts: Date.now(), type: 'in', method: 'ecash', amount: 24, mint: {J(M)}, note: 'saved by 1.34', status: 'pending', incoming: {J(t)}, offline: true }})")
            await al.ev("window.dispatchEvent(new Event('online'))")
            ok = await al.until(f"{TOTAL} >= {b0 + 24}", 20000); await al.wait(800)
            st = await al.ev("(Nutcade.S.txs.find(t => t.id === 'b64old') || {}).status || 'gone'")
            check('b64: a token saved waiting by 1.34 in standard base64 is claimed once online, all of it, its line not failed (on e9b0b98 marked "already claimed by someone else")', ok and await al.bal() == b0 + 24 and st != 'failed', (await al.bal() - b0, st))
        await section('b64', b64)

        async def request():
            async def pay(nut10, amount=20, nutroot=None, creqb=False):
                e = await al.ev(f"new CashuLib.PaymentRequest({{transport: [], id: 'r' + Math.random(), amount: {amount}, unit: 'sat', mints: [{J(M)}], description: 'lock test', singleUse: true, nut10: {J(nut10) if nut10 else 'undefined'}, nutroot: {J(nutroot) if nutroot else 'undefined'}}}).{'toEncodedCreqB' if creqb else 'toEncodedRequest'}()")
                b0 = await al.bal(); n0 = await al.ev("Nutcade.S.txs.length")
                await al.home(); await al.ev(f"Nutcade.handleScan({J(e)})"); await al.wait(400)
                note = await al.sheet_text(); btn = await al.ev("!!document.querySelector('[data-act=payReq]')")
                if btn: await al.click('[data-act=payReq]'); await al.until(f"Nutcade.S.txs.length > {n0} || !!((document.querySelector('#sheetErr')||{{}}).innerText||'').trim()", 15000); await al.wait(300)
                tok = await al.ev(f"Nutcade.S.txs.length > {n0} ? Nutcade.S.txs[0].token : null")
                await al.close()
                secs = await al.ev(f"CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.counters)).proofs.map(p => p.secret)") if tok else []
                return {'note': REQ_ERR in note, 'btn': btn, 'spent': b0 - await al.bal(), 'secrets': [json.loads(s) if s.startswith('[') else s for s in secs]}
            for name, n10 in [('an HTLC lock', {'kind': 'HTLC', 'data': H, 'tags': []}), ('another kind', {'kind': 'FOO', 'data': K1, 'tags': []}), ('P2PK data that is no key', {'kind': 'P2PK', 'data': '', 'tags': []}),
                              ('an x-only key', {'kind': 'P2PK', 'data': K1[2:], 'tags': []}), ('n_sigs without a value', {'kind': 'P2PK', 'data': K1, 'tags': [['n_sigs']]})]:
                r = await pay(n10)
                check(f'request: {name}: refused before anything is spent, with the reason on the screen (before 1.35 paid UNLOCKED)', r['note'] and not r['btn'] and r['spent'] == 0 and not r['secrets'], r)
            # cashu-ts 5: a request can carry its lock only in `nutroot` (the v3 lock); NUTCADE can't make that lock, so such a
            # request is refused before anything is spent (on e9b0b98 it was paid with an UNLOCKED token)
            for name, kw in [('a lock only in nutroot (creqA)', {'nutroot': {'receiverKey': K1}}), ('a lock only in nutroot (creqB)', {'nutroot': {'receiverKey': K1}, 'creqb': True}),
                             ('a nutroot tree only (leaves)', {'nutroot': {'receiverKey': K1, 'leaves': ['00' * 8]}})]:
                r = await pay(None, **kw)
                check(f'request: {name}: refused before anything is spent, with the reason on the screen (on e9b0b98 paid UNLOCKED)', r['note'] and not r['btn'] and r['spent'] == 0 and not r['secrets'], r)
            rd = await al.ev(f"""(() => {{ const t = x => {{ try {{ return Nutcade.lk.req(CashuLib.decodePaymentRequest(new CashuLib.PaymentRequest(Object.assign({{transport: [], id: 'x', amount: 5, unit: 'sat'}}, x)).toEncodedRequest())) ? 'lock' : 'none'; }} catch (e) {{ return e.message; }} }};
                return [t({{nutroot: {{receiverKey: {J(K1)}}}}}), t({{nutroot: {{receiverKey: {J(K1)}}}, nut10: {{kind: 'P2PK', data: {J(K2)}, tags: []}}}}), t({{}})]; }})()""")
            check('request: the lock reader: nutroot alone refused, nutroot with a P2PK nut10 read as that lock, no lock none', rd == [REQ_ERR, 'lock', 'none'], rd)
            r = await pay({'kind': 'P2PK', 'data': K2, 'tags': []}, nutroot={'receiverKey': K2})
            check('request: a request carrying both encodings (nut10 + nutroot) is paid with the nut10 lock, locked to its key', r['secrets'] and all(isinstance(s, list) and s[0] == 'P2PK' and s[1]['data'] == K2 for s in r['secrets']) and r['spent'] == 20, r)
            lt = str(int(time.time()) + 7200)
            r = await pay({'kind': 'P2PK', 'data': K1, 'tags': [['locktime', lt], ['refund', K2], ['sigflag', 'SIG_INPUTS']]})
            ok = r['secrets'] and all(isinstance(s, list) and s[0] == 'P2PK' and s[1]['data'] == K1 and dict((t[0], t[1:]) for t in s[1].get('tags', [])).get('locktime') == [lt]
                                      and dict((t[0], t[1:]) for t in s[1].get('tags', [])).get('refund') == [K2] for s in r['secrets'])
            check('request: a P2PK request with a locktime and refund key is paid with exactly that lock (the payee\'s wallet checks it is the one it asked for)', ok and r['spent'] == 20, r)
            r = await pay({'kind': 'P2PK', 'data': K2, 'tags': []})
            check('request: a plain P2PK request is paid locked to its key, as before', r['secrets'] and all(s[0] == 'P2PK' and s[1]['data'] == K2 and not [t for t in s[1].get('tags', []) if t[0] in ('locktime', 'refund', 'pubkeys')] for s in r['secrets']) and r['spent'] == 20, r)
            r = await pay(None)
            check('request: a request without a lock is paid with a plain token, as before', r['secrets'] and all(isinstance(s, str) for s in r['secrets']) and r['spent'] == 20, r)
            tr = await al.ev(f"['es','pt','de','fr'].map(l => (window.NUTCADE_I18N[l].t||{{}})[{J(REQ_ERR)}] || null)")
            check('request: the new text is translated in all five languages', all(tr), tr)
        await section('request', request)

        check('no page errors', not al.errs, al.errs[:3])
        await b.close()
    fails = [r for r in results if not r[1]]
    print(f'SUMMARY {len(results) - len(fails)}/{len(results)} passed')


if __name__ == '__main__':
    asyncio.run(main())
