"""Offline token check (1.26.0): the mint's signature on ecash checked with no connection (NUT-12 DLEQ proofs).
Uses the local test mints 3338 and 3339 and a second wallet that sends real tokens.

The checker against vectors made by Nutshell's own code (good proofs accepted, every changed field refused) and the NUT-00
hash_to_curve test vector; each mint's public keys saved when it is loaded (and kept after a reload); a real token received
while offline is saved with "Signature checked offline"; a token with a changed proof or signature is refused and nothing is
saved; a token without proofs, from a mint whose keys aren't saved, or on a keyset newer than the saved keys is saved as
"Not checked" (never called fake); back online the saved token is claimed; tokens sent by sound carry the proofs (flag bit 2)
and "Faster, no proof" leaves them out, an older payload without them still reads, an unknown flag is refused; printed
tokens keep the proofs; the new texts in five languages with no missing translation.
DQ_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, A, B

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
LANGS = ['en', 'es', 'pt', 'de', 'fr']
J = json.dumps
# made with Nutshell 0.16's b_dhke (step1_alice, step2_bob with its DLEQ, step3_alice), each checked there by alice_verify_dleq
SHORT = {"secret": "25631fb6bc7e756cd9fdf6dccbcc069873d780f905b080c025e1b2de2c896c09", "C": "03b65949d0ef98c6e8124b0b0d6a6e013c83c4e348ea40202b9d4ac9dae321f33d", "A": "033456b30415468961bee93dfd650a3386376b3b70bc742077dc530e612e7927a6", "dleq": {"e": "e11260bcc1721e31f48c8070ecdc56a85decf056172a06e2752793003b4a30bb", "s": "8bb77037c5d4e673216708f426c490d23d50fa6c79be6045a06e344f75206b68", "r": "0000000000000000000000000000000000000000000000000000000000003039"}}   # its r has leading zeros (blinding factor 12345)
VEC = [{"secret": "5cd4dc50a570b69080850ef62eedaee978ef093ed4723520b3131069a4a817f9", "C": "03c7ee3ae98e4609501688219e82832fe880f864ef12157023f83b1c6fd56f9337", "A": "0332b54311dfafde90b7f39b60b6413d210d015e28bfc931e0f900a311587b1b90", "dleq": {"e": "36b26c1bfe4a2e6e58662f1e5a4e81f636d001262b32c0e45c8ed9919a8f541d", "s": "53bab7216b282de1339458094b60d346b2cc35f9b0fef9a9ad7d59d3b0c4dca2", "r": "380f61ea82db1bfe4c54226d358a8e24ac0175c72e9100b5ae429a0f549a8c27"}}, {"secret": "[\"P2PK\",{\"nonce\":\"443e622147e52cea\",\"data\":\"02aa\"}]", "C": "03f3688d6d8a884f4be15bed11cbd7679c5b94e8f4e9993c8f42e11ee2020de8ec", "A": "03a539b44db2beb7d2398b2877481db37fafbcb552b61af9f4b5a808b2d99b7054", "dleq": {"e": "d2279fcd014da36b55f15a8ced54ffb0e3cdb56e2d9e8e8df62a5f3ad17b5397", "s": "097b9cb14ce92e0c49ba1a8d84f1fec512000009083ba146ab213d0621484188", "r": "14458410517e9a81f24a17cddd3e70e823fc3da18cb69e8a5a154ff3505fc894"}}, {"secret": "84cca0c122d1caafbd7c2a05be10f0ae20bab3d333b6dc4d2726fef39c793785", "C": "03aac5b49a4257adf4949dbbfc19a58440551bc081eee9a23d6fe2ea878899c743", "A": "02118598fd5621e533d0a8ab5d0677bf8253003137ceb010e5ee5e3b63e969741a", "dleq": {"e": "55c5a97edb4349d9cfc8e850aba43c66cb66398168aca23dfcd2642577ad808d", "s": "b09c74669d907e3a5d64aa8b10653566252316a9b282dcd5ca883b93f363506a", "r": "b3ea50668e942cdb280250cd51363db27d838a4a916f57143dd4eb165f23b14e"}}, {"secret": "[\"P2PK\",{\"nonce\":\"f702b2b6874a4f27\",\"data\":\"02aa\"}]", "C": "039bd17d31262954aca1f32f74ea7e8369bd6e3eb12b127c249a1dd59b327f2694", "A": "03b940a8af6cb4fd745b9997334e3dfad882ce6787ef9480c7621bdd36d0a90092", "dleq": {"e": "751a47d35ce17443408dd1d39ba63e920469bcb1eb4884ae92523e23597e22a1", "s": "e8e6398238e0c6b0f412598a646df03965c97ebbc642a3783129edb496f9554c", "r": "2dd3079998e196387b965c08fbb63ba9f34dc0d238093537f2ab3500a670d3f3"}}, {"secret": "dc0fb0a700b32facc88cafa863e8e55b0651a4dc1b03da6623f21fa9bda7b82a", "C": "03bda26dda31bc13f9cef8d6e39f81378969a2691ab05cbaca9dde2510debbbe2a", "A": "036beabbb4e3ad0e1e88f54d5143cd1049baeeeccd032d08bfeedb3186169707ac", "dleq": {"e": "0d653fb6cc5a5463049aa11352a5925aadea1672507205224d9e86818529be00", "s": "579fca53d29a085424d5ca7928a11ab18b24df52eaeb24feed97ef5034a4e4f8", "r": "33ff8ed7d4e25da8e49707fb2b69018d74c689d3f5f4b3f66d205df9bd635c36"}}, {"secret": "[\"P2PK\",{\"nonce\":\"25e8116a02c0ca44\",\"data\":\"02aa\"}]", "C": "027c2d2bca912a3fa096c32be0ce5f9d7710af6b9944c61fb07e8c68b90c9a3b08", "A": "02e01f3577e9c6c10b58947b144b7df88f0312ddfa5666d2b06ccdf2322db4c288", "dleq": {"e": "31e12d956d90382c933ea9b55a58536e2ac4b7483a7cd2b82f84a9bf8fa1ff5f", "s": "f593c7b470e628530c727e5d81df3b091472a875b5fd0e59b09c4d8bb268b530", "r": "6f8dedd6bab1917a1570e50b6c6fc12bedfd8779b06a3c0c0d51124c4481db94"}}]
async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def section(name, fn):
    only = [x for x in os.environ.get('DQ_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def offline(w, on): await w.pg.context.set_offline(on); await w.wait(300)
async def receive_off(w, tok):
    await offline(w, True)
    await w.home(); await w.click('[data-act=receive]'); await w.wait(150); await w.click('[data-act=recvMethod][data-m=ecash]'); await w.wait(100)
    await w.fill('#tokIn', tok); await w.click('[data-act=doReceiveToken]'); await w.wait(700)
    e = await w.err(); t = await w.sheet_text(); await w.close(); return e, t
def flip(h): return h[:-1] + ('1' if h[-1] != '1' else '2')
async def edit_tok(w, tok, js):   # the token's proofs changed by a bit of JavaScript (p: one proof)
    return await w.ev(f"(()=>{{const d=CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.mintkeys[Nutcade.S.active]||{{}})); d.proofs.forEach((p,i)=>{{ {js} }}); return CashuLib.getEncodedToken(d)}})()")
def Nutcade_tr_same(a, b): return a == b
async def held(w): return await w.ev("Nutcade.S.txs.filter(t=>t.status==='pending'&&t.incoming&&t.offline).map(t=>({dleq:t.dleq||null, amount:t.amount}))")

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))

        async def unit():
            w = await wallet(b, 'dq-unit')
            r = await w.ev(f"""(()=>{{const V={J(VEC)}; const f=h=>h.slice(0,-1)+(h.slice(-1)==='1'?'2':'1'); let good=0, bad=0, n=0;
                for (const [i,p] of V.entries()) {{ if (Nutcade.dq.ok(p,p.A)) good++;
                  for (const m of [q=>q.dleq.e=f(q.dleq.e), q=>q.dleq.s=f(q.dleq.s), q=>q.dleq.r=f(q.dleq.r), q=>q.C=f(q.C), q=>q.secret=q.secret+'x', q=>q.dleq.e='ff'.repeat(32), q=>delete q.dleq, q=>q.C='04'+q.C.slice(2)]) {{
                    const q=JSON.parse(JSON.stringify(p)); m(q); n++; if (!Nutcade.dq.ok(q,p.A)) bad++; }}
                  n++; if (!Nutcade.dq.ok(p, V[(i+1)%V.length].A)) bad++; }}
                return {{good, all:V.length, bad, n}}}})()""")
            check('unit: every proof Nutshell made is accepted', r['good'] == r['all'], r)
            check('unit: a changed e, s, r, signature or secret, a missing proof, a bad point or another key is refused', r['bad'] == r['n'], r)
            sh = await w.ev(f"(()=>{{const p={J(SHORT)}; const q=JSON.parse(JSON.stringify(p)); q.dleq.r=q.dleq.r.replace(/^0+/,''); return [q.dleq.r.length, Nutcade.dq.ok(p,p.A), Nutcade.dq.ok(q,p.A)]}})()")
            check('unit: a proof written without leading zeros is read like cashu-ts reads it (accepted)', sh[0] < 64 and sh[1] and sh[2], sh)
            z = await w.ev("(()=>{const u8=new Uint8Array(32); return null})()")
            v0 = await w.ev("(()=>{ return Nutcade.dq.h2c(String.fromCharCode(...new Uint8Array(32))) })()")
            check('unit: hash_to_curve matches the NUT-00 test vector (32 zero bytes)', v0[2:66] == '4cce997d3b518f739663b757deaec95bcd9473c30a14ac2fd04023a739d1a725', v0[:70])
            check('unit: no errors', not w.errs, w.errs[:2]); await w.pg.context.close()
        await section('unit', unit)

        async def flow():
            w = await wallet(b, 'dq-recv'); await w.create(); await w.add_mint(A); await w.add_mint(B); await w.use(A)
            fr = await wallet(b, 'dq-send'); await fr.create(); await fr.add_mint(A); await fr.use(A); await fr.receive_ln(9000)
            ks = await w.ev(f"(()=>{{const k=Nutcade.S.mintkeys[{J(A)}]||{{}}; const ids=Object.keys(k); return {{n:ids.length, keys: ids.length?Object.keys(k[ids[0]]).length:0, ok: ids.every(id=>Object.values(k[id]).every(v=>/^0[23][0-9a-f]{{64}}$/.test(v)))}}}})()")
            check('keys: a mint\'s public keys are saved when it is loaded', ks['n'] >= 1 and ks['keys'] >= 10 and ks['ok'], ks)
            await w.ev("location.reload()"); await w.wait(1500)
            ks2 = await w.ev(f"Object.keys(Nutcade.S.mintkeys[{J(A)}]||{{}}).length")
            check('keys: they are still there after a reload', ks2 == ks['n'], ks2)
            tok, e = await fr.send_ecash(700, 'offline good')
            hasdq = await w.ev(f"CashuLib.getDecodedToken({J(tok)}, Object.keys(Nutcade.S.mintkeys[{J(A)}])).proofs.every(p=>p.dleq&&p.dleq.e)")
            check('flow: a token from the test mint carries DLEQ proofs', hasdq, e)
            st = await w.ev(f"Nutcade.dq.check({J(tok)})")
            check('flow: the check finds every coin signed by the mint', st['state'] == 'ok' and st['n'] >= 1, st)
            e1, t1 = await receive_off(w, tok)
            check('flow: received offline, the token is saved with "Signature checked offline"', not e1 and 'Signature checked offline' in t1 and "isn't yours yet" in t1, (e1, t1[:200]))
            hd = await held(w)
            check('flow: the saved token records the check', [x['dleq'] for x in hd] == ['ok'], hd)
            await w.home(); await w.click('[data-act=tab][data-tab=history]'); await w.wait(200); await w.click('[data-act=tx]'); await w.wait(250)
            check('flow: its History screen shows the check too', 'Signature checked offline' in await w.sheet_text()); await w.close()
            # forged: a changed proof, or a changed signature
            tok2, _ = await fr.send_ecash(300, 'to be changed')
            for name, js in (('a changed proof', "if(i===0) p.dleq.e=p.dleq.e.slice(0,-1)+(p.dleq.e.slice(-1)==='1'?'2':'1')"), ('a changed signature', "if(i===0) p.C=p.C.slice(0,2)+p.C.slice(4)+p.C.slice(2,4)"), ('the same coin twice', "if(i===1) {const q=d.proofs[0]; p.secret=q.secret; p.C=q.C; p.dleq=q.dleq; p.amount=q.amount}")):
                bad = await edit_tok(w, tok2, js); n0 = len(await held(w))
                e2, t2 = await receive_off(w, bad)
                check(f'forged: a token with {name} is refused as possibly fake', e2 and "weren't signed by its mint" in e2, (e2, t2[:120]))
                check(f'forged: {name}: nothing is saved', len(await held(w)) == n0)
            st_amt = await w.ev(f"Nutcade.dq.check({J(await edit_tok(w, tok2, 'if(i===0) p.amount=3'))})")
            check('nokeys: an amount with no saved key is "Not checked", never called fake (the mint refuses it when claimed)', st_amt['state'] == 'nokeys', st_amt)
            many = await edit_tok(w, tok2, "")
            rep = await w.ev(f"(()=>{{const d=CashuLib.getDecodedToken({J(tok2)}, Object.keys(Nutcade.S.mintkeys[Nutcade.S.active])); const p=d.proofs[0]; d.proofs=Array.from({{length:50}},()=>Object.assign({{}},p)); return Nutcade.dq.check(CashuLib.getEncodedToken(d))}})()")
            check('forged: one real coin repeated 50 times is refused, never "checked" at 50 times its value', rep['state'] == 'bad', rep)
            bad_hex = await w.ev("(t=>{const d=CashuLib.getDecodedToken(t, Object.keys(Nutcade.S.mintkeys[Nutcade.S.active])); d.proofs[0].dleq.e='00'+d.proofs[0].dleq.e; return Nutcade.dq.check(CashuLib.getEncodedToken(d))})(" + J(tok2) + ")")
            check('noproof: a proof that can\'t be read is "Not checked", never called fake', bad_hex['state'] == 'noproof', bad_hex)
            # not checked: no proofs, no saved keys, a keyset newer than the saved keys
            slim = await fr.ev(f"Nutcade.dq.slim({J(tok2)})")
            e3, t3 = await receive_off(w, slim)
            check('noproof: a token without proofs is saved as "Not checked" (the other wallet left them out)', not e3 and 'left out the mint' in t3, (e3, t3[:160]))
            tok3, _ = await fr.send_ecash(200, 'no keys')
            saved = await w.ev(f"JSON.stringify(Nutcade.S.mintkeys[{J(A)}])")
            await w.ev(f"(()=>{{const k=Nutcade.S.mintkeys[{J(A)}]; const id=Object.keys(k)[0]; const v=k[id]; for (const x of Object.keys(k)) delete k[x]; k['00'+'ab'.repeat(7)]=v}})()")
            st4 = await w.ev(f"Nutcade.dq.check({J(tok3)})")
            check('nokeys: coins on a keyset newer than the saved keys are "Not checked", never called fake', st4['state'] == 'nokeys', st4)
            await w.ev(f"delete Nutcade.S.mintkeys[{J(A)}]")
            e4, t4 = await receive_off(w, tok3)
            check('nokeys: a mint whose keys aren\'t saved: saved as "Not checked"', not e4 and "doesn't have the keys" in t4, (e4, t4[:160]))
            await w.ev(f"Nutcade.S.mintkeys[{J(A)}]=JSON.parse({J(saved)})")
            again = await edit_tok(w, tok3, "d.memo='same coins, other text'")
            e5, _ = await receive_off(w, again)
            check('flow: the same coins in another token text are refused while they already wait', e5 and 'in another token' in e5, e5)
            hd = await held(w)
            check('flow: three tokens wait, each with its check', sorted(x['dleq'] for x in hd) == ['nokeys', 'noproof', 'ok'], hd)
            bal0 = await w.balance() if hasattr(w, 'balance') else None
            await offline(w, False); await w.ev("dispatchEvent(new Event('online'))"); await w.wait(4000)
            check('online: back online, every saved token is claimed', not await held(w), await held(w))
            check('flow: no errors', not w.errs and not fr.errs, (w.errs + fr.errs)[:3])

            # sound
            tok5, _ = await fr.send_ecash(1500, 'for sound')
            r = await fr.ev(f"""(()=>{{const t={J(tok5)}, ids=Object.keys(Nutcade.S.counters); const key=d=>JSON.stringify([d.mint, d.proofs.map(p=>[p.id, Number(p.amount), p.secret, p.C, p.dleq?[p.dleq.e,p.dleq.s,p.dleq.r]:null])]);
                const b1=Nutcade.soundBytes(t), b0=Nutcade.soundBytes(t,false); const d=CashuLib.getDecodedToken(t, ids), back1=CashuLib.getDecodedToken(Nutcade.soundText(b1), ids), back0=CashuLib.getDecodedToken(Nutcade.soundText(b0), ids);
                const strip=x=>JSON.stringify([x.mint, x.proofs.map(p=>[p.id, Number(p.amount), p.secret, p.C])]);
                return {{full: key(d)===key(back1), dq: back1.proofs.every(p=>p.dleq&&p.dleq.e), slim: strip(d)===strip(back0) && back0.proofs.every(p=>!p.dleq), l1:b1.length, l0:b0.length, n:d.proofs.length}}}})()""")
            check('sound: a token comes back with every proof and its DLEQ proofs', r['full'] and r['dq'], r)
            check('sound: "Faster, no proof" leaves the proofs out (96 bytes a coin)', r['slim'] and r['l1'] - r['l0'] == 96 * r['n'], r)
            st6 = await w.ev(f"Nutcade.dq.check(Nutcade.soundText(Nutcade.soundBytes({J(tok5)})))")
            check('sound: a token heard offline can be checked', st6['state'] == 'ok', st6)
            odd = await fr.ev(f"(()=>{{const b=Nutcade.soundBytes({J(tok5)},false); const i=b.indexOf(0,0); let k=0; try {{ const c=b.slice(); c[c.length-1]^=0; return Nutcade.soundText(c).slice(0,6) }} catch(e) {{ return 'ERR' }} }})()")
            check('sound: a payload without proofs (as 1.25 and older send it) still reads', odd.startswith('cashuB'), odd)
            bad8 = await fr.ev(f"""(()=>{{const b=Nutcade.soundBytes({J(tok5)}, false); let i=1; const sk=()=>{{let n=0,m=1,x; do {{x=b[i++]; n+=(x&127)*m; m*=128}} while(x&128); return n}};
                const skip=()=>{{const n=sk(); i+=n}}; skip(); skip(); skip(); sk(); skip(); sk(); sk(); const ok=b[i]<8; const c=b.slice(); c[i]|=8;
                let plain='read'; try {{ Nutcade.soundText(b) }} catch(e) {{ plain='refused' }}
                try {{ Nutcade.soundText(c); return [ok, plain, 'read'] }} catch(e) {{ return [ok, plain, 'refused'] }} }})()""")
            check('sound: a payload with a flag this version doesn\'t know is refused, never read wrong', bad8 == [True, 'read', 'refused'], bad8)
            await fr.home(); await fr.click('[data-act=tab][data-tab=history]'); await fr.wait(200); await fr.click('[data-act=tx]'); await fr.wait(250)
            await fr.click('.sheet [data-act=ctPlay]'); await fr.wait(500)
            s1 = await fr.sheet_text()
            check('sound: the sound screen offers "Faster, no proof", off by default', 'Faster, no proof' in s1 and 'Carries the mint' in s1 and await fr.ev("!document.querySelector('#ctFast').checked"), s1[:300])
            sec1 = await fr.ev("document.querySelector('#ctSub').innerText")
            await fr.click('#ctFast'); await fr.ev("document.querySelector('#ctFast') && document.querySelector('#ctFast').dispatchEvent(new Event('change'))"); await fr.wait(500)
            s2 = await fr.sheet_text(); sec2 = await fr.ev("document.querySelector('#ctSub').innerText")
            num = lambda s: int(re.findall(r'(\d+) S', s)[0]) if re.findall(r'(\d+) S', s) else 0
            check('sound: switched on, it plays faster and says the proofs are left out', 'left out' in s2 and num(sec2) < num(sec1) and await fr.ev("Nutcade.S.prefs.ctNoProof===true"), (sec1, sec2))
            await fr.ev("Nutcade.closeSheet()"); await fr.wait(100)
            check('sound: closing still stops the sound', await fr.ev("!Chiptune.isPlaying()"))
            # paper
            tok7, _ = await fr.send_ecash(1024, 'one coin')
            pt = await fr.ev(f"(()=>{{const ids=Object.keys(Nutcade.S.counters), t=Nutcade.dq.ptText({J(tok7)}), t2=Nutcade.dq.ptText({J(tok5)}); return {{same: t==={J(tok7)}, dq: CashuLib.getDecodedToken(t, ids).proofs.every(p=>p.dleq&&p.dleq.e), big: CashuLib.getDecodedToken(t2, ids).proofs.every(p=>!p.dleq)}}}})()")
            check('paper: a printed token keeps the mint\'s proofs', pt['same'] and pt['dq'], pt)
            check('paper: one too dense with them is printed without them, as before', pt['big'], pt)
            check('sound/paper: no errors', not fr.errs, fr.errs[:3])
            await w.pg.context.close(); await fr.pg.context.close()
        await section('flow', flow)

        async def langs():
            strs = ["✓ Signature checked offline: the mint really signed these coins. It can't show they're unspent: only the mint can say that when you claim.",
                    "Not checked: the wallet that made this token left out the mint's signature proofs.",
                    "Not checked: NUTCADE doesn't have the keys the mint signed these coins with yet. It gets them the next time it reaches the mint.",
                    "This token's coins weren't signed by its mint. It may be fake, so NUTCADE didn't save it.", "Faster, no proof",
                    "The mint's signature proofs are left out, so it plays faster. A phone that's offline can't check this token until it's back online.",
                    "Carries the mint's signature proofs, so a phone that's offline can check this token is real. Older versions of NUTCADE can't read it."]
            for lang in LANGS[1:]:
                w = await wallet(b, 'dq-' + lang, lang=lang)
                lines = await w.ev("['ok','noproof','nokeys'].map(s=>Nutcade.dq.line({dleq:s}).replace(/<[^>]+>/g,''))")
                left = [x for x in strs + lines if Nutcade_tr_same(await w.ev(f"Nutcade.tr({J(x)})"), x)]
                check(f'lang {lang}: every new text is translated', not left, left[:2])
                await w.ev("Nutcade.openSheet('x', '<div class=notice>' + Nutcade.dq.line({dleq:'ok'}) + '</div><label class=row><input type=checkbox> Faster, no proof</label>')"); await w.wait(200)
                t = await w.ev("document.querySelector('.sheet-body').innerText")
                check(f'lang {lang}: shown on a screen, no English is left', 'Signature checked' not in t and 'Faster, no proof' not in t, t[:160])
                check(f'lang {lang}: no errors', not w.errs, w.errs[:2]); await w.pg.context.close()
        await section('langs', langs)

        bad = [r for r in results if not r[1]]
        print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')
        await b.close()

if __name__ == '__main__':
    asyncio.run(main())
