"""Other 12 words, the old lock key kept (1.45.0). Uses the local mint 3339 (Mint B, no fees) and mock_nostr.py.

Your lock key (and your nutzap key) come from your 12 words. Gifts and treasure hunts you sent carry it as their refund key,
ecash locked to you was locked to it, an Extra Life is locked to it, and an Extra Life left to you names it as its heir.
Restoring other 12 words used to forget it: none of those could be claimed, taken back or renewed any more. Now the old
words' keys are kept (in the wallet's P2PK keys, which the backup file carries too):
- ecash locked to your old key, sent before you restored other words, is still claimed;
- an Extra Life copy left to your old key is still recognised as yours;
- your own Extra Life, made under the old words, is still renewed (CONTINUE), now locked to the new words' key;
- (1.52.0) a bounty locked to your old key, plain or blinded (P2BK), is still recognised as yours; one locked to someone
  else's key still isn't.
"""
import asyncio, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, B
from r8_qa import wallet


# (as in r4_qa.py, which runs its whole suite when imported)
async def friend_addr(w):
    return await w.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32)), relays:['ws://127.0.0.1:3350/relay']})")
async def add_contact(w, name, addr):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
    await w.click('#set-contacts [data-act=contactsOpen]'); await w.wait(150)
    await w.click('[data-act=contactEdit]'); await w.wait(100)
    await w.fill('#cName', name); await w.fill('#cNostr', addr); await w.click('[data-act=contactSave]'); await w.wait(250)
    await w.ev("Nutcade.closeSheet()")

J = json.dumps
LOCKPUB = "'02'+CashuLib.nostrPub(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))"


async def section(name, fn):
    only = [x for x in os.environ.get('KQ_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def restore_other_words(w, mint=B):
    """Settings → Restore from 12 words, with new words; returns them"""
    words = await w.ev("CashuLib.generateMnemonic(CashuLib.wordlist, 128)")
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
    await w.ev("(()=>{let x=document.querySelector('[data-act=seedRestore]'); if(!x){x=document.createElement('button'); x.dataset.act='seedRestore'; x.hidden=true; document.body.appendChild(x)} x.click()})()")
    await w.until("!!document.querySelector('#phraseIn')", 5000)
    await w.fill('#phraseIn', words)
    await w.ev(f"(()=>{{const t=document.querySelector('#rmExtra'); t.value={J(mint)}; t.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")
    await w.click('[data-act=doRestorePhrase]')
    await w.until(f"Nutcade.S.seed.mnemonic==={J(words)} && /CONTINUE|SCAN COMPLETE|DONE/i.test((document.querySelector('.sheet-body')||{{}}).innerText||'')", 90000)
    await w.wait(500); await w.ev("Nutcade.closeSheet()")
    return words


def keyset_id(mint):
    return [k for k in json.loads(urllib.request.urlopen(mint + '/v1/keysets', timeout=10).read())['keysets'] if k['unit'] == 'sat' and k['active']][0]['id']


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        async def locked_token():
            g = await wallet(b); await g.create(); await g.add_mint(B); await g.receive_ln(200)
            w = await wallet(b); await w.create(); await w.add_mint(B)
            old = await w.ev(LOCKPUB)
            # the friend sends 20 SAT locked to your key (a gift, Send → Lock)
            await g.home(); await g.click('[data-act=send]'); await g.wait(150)
            await g.fill('#amtIn', '20')
            await g.ev("(()=>{const c=document.querySelector('#giftOn'); c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}))})()"); await g.wait(100)
            await g.fill('#giftKey', old); n0 = await g.ev("Nutcade.S.txs.length")
            await g.click('[data-act=doSendEcash]')
            await g.until(f"Nutcade.S.txs.length>{n0} && !!Nutcade.S.txs[0].token", 20000)
            tok = await g.ev("Nutcade.S.txs[0].token")
            words = await restore_other_words(w)
            new = await w.ev(LOCKPUB)
            check('locked token: the wallet has other 12 words now (another lock key)', words and new != old, (old, new))
            await w.ev("Nutcade.closeSheet()"); await w.home(); await w.wait(300)
            tr, e, txt = await w.receive_token(tok)
            check('locked token: ecash locked to your OLD key, sent before the restore, is still claimed (20 SAT)', not e and await w.bal(B) == 20, (e, await w.bal(B), txt[:160]))
            check('locked token: no script errors', not w.errs and not g.errs, (w.errs + g.errs)[:4])
            await w.pg.context.close(); await g.pg.context.close()

        async def heir():
            w = await wallet(b); await w.create(); await w.add_mint(B)
            old = await w.ev(LOCKPUB); kid = keyset_id(B)
            sec = J(['P2PK', {'nonce': '33' * 16, 'data': '02' + '2' * 64, 'tags': [['locktime', str(int(time.time()) + 86400)], ['refund', old]]}])
            tok = f"CashuLib.getEncodedToken({{mint:{J(B)}, unit:'sat', proofs:[{{id:{J(kid)}, amount:8, secret:{J(sec)}, C:'02'+'1'.repeat(64)}}]}})"
            before = await w.ev(f"NutUnits.heir({tok})")
            await restore_other_words(w)
            after = await w.ev(f"NutUnits.heir({tok})")
            check('heir: an Extra Life copy left to your OLD key is still recognised as yours after other words', before and after and after['amount'] == 8, (before, after))
            check('heir: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def bounty():
            w = await wallet(b); await w.create(); await w.add_mint(B)
            old = await w.ev(LOCKPUB); kid = keyset_id(B)
            oldpriv = await w.ev("CashuLib.bytesToHex(CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0,32))")
            E = await w.ev("CashuLib.bytesToHex(CashuLib.getPubKeyFromPrivKey(crypto.getRandomValues(new Uint8Array(32))))")
            blinded = await w.ev(f"NutP2BK.blind({J(oldpriv)}, {J(E)}, 1)")   # (the old key blinded with E, for the lock's first "pubkeys" slot)
            stranger = await w.ev("'02'+CashuLib.nostrPub(crypto.getRandomValues(new Uint8Array(32)))")
            def htlc(key): return J(['HTLC', {'nonce': '44' * 16, 'data': 'ab' * 32, 'tags': [['pubkeys', key]]}])
            def tok(key, e=None): return f"CashuLib.getEncodedToken({{mint:{J(B)}, unit:'sat', proofs:[Object.assign({{id:{J(kid)}, amount:8, secret:{J(htlc(key))}, C:'02'+'1'.repeat(64)}}, {J({'p2pk_e': e} if e else {})})]}})"
            before = [await w.ev(f"NutP2BK.bounty({{token:{tok(old)}, amount:8}})"), await w.ev(f"NutP2BK.bounty({{token:{tok(blinded, E)}, amount:8}})")]
            await restore_other_words(w)
            after = [await w.ev(f"NutP2BK.bounty({{token:{tok(old)}, amount:8}})"), await w.ev(f"NutP2BK.bounty({{token:{tok(blinded, E)}, amount:8}})")]
            check('bounty: (the test reads it as the wallet does) both are bounties for you under the words they were made for', all(x and x['amount'] == 8 for x in before), before)
            check('bounty: a bounty locked to your OLD key is still yours after other words (8 SAT)', after[0] and after[0]['amount'] == 8, after[0])
            check('bounty: ...and one locked to your old key blinded (P2BK) too', after[1] and after[1]['amount'] == 8, after[1])
            check("bounty: one locked to someone else's key is still not yours", await w.ev(f"NutP2BK.bounty({{token:{tok(stranger)}, amount:8}})") is None)
            check('bounty: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close()

        async def extra():
            w = await wallet(b); await w.create(); await w.add_mint(B); await w.receive_ln(3000)
            fr = await wallet(b); await fr.create(); await fr.add_mint(B)
            await add_contact(w, 'Robin', await friend_addr(fr))
            await w.home(); await w.click('[data-act=extraOpen]'); await w.until("!!document.querySelector('#xlTo')", 5000); await w.wait(150)
            await w.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Robin').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
            await w.fill('#amtIn', '2000'); await w.click('[data-act=extraStart]')
            made = await w.until("!!Nutcade.S.extra", 20000); await w.wait(1500); await w.ev("Nutcade.closeSheet()")
            old = await w.ev(LOCKPUB)
            await restore_other_words(w)
            new = await w.ev(LOCKPUB)
            await w.home(); await w.ev("Nutcade.S.extra.until -= 86400e3*10; Nutcade.S.extra.days=182; Nutcade.render()")
            await w.click('.extra-panel'); await w.wait(200)
            if await w.ev("!!document.querySelector('[data-act=extraContinue]')"): await w.click('[data-act=extraContinue]')
            ok = await w.until("Nutcade.S.extra && Nutcade.S.extra.renewed > Date.now()-15000 && Nutcade.S.extra.until > Date.now()+181*86400e3", 30000)
            data = await w.ev("Nutcade.S.extra ? JSON.parse(Nutcade.S.extra.proofs[0].secret)[1].data : null")
            check('extra: an Extra Life made under the old words is still renewed after other words (CONTINUE)', made and ok, (made, ok, await w.err()))
            check('extra: ...and is now locked to the new words\' key', data == new and new != old, (data, new, old))
            check('extra: no script errors', not w.errs, w.errs[:4])
            await w.pg.context.close(); await fr.pg.context.close()

        for name, fn in (('locked_token', locked_token), ('heir', heir), ('bounty', bounty), ('extra', extra)):
            await section(name, fn)
        await b.close()
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
    sys.exit(0 if results and all(r[1] for r in results) else 1)


if __name__ == '__main__':
    asyncio.run(main())
