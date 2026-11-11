import os
import asyncio, json, urllib.request, re, sys
from playwright.async_api import async_playwright
OUT=os.environ.get('QA_OUT','/tmp/qa-out')+'/'
URL=os.environ.get('NUTCADE_URL','http://localhost:8099/index.html')
A,B,F,P='http://127.0.0.1:3338','http://127.0.0.1:3339','http://127.0.0.1:3340','http://127.0.0.1:3341'
results=[]
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail)); print(('PASS ' if ok else 'FAIL ')+name+(' — '+str(detail) if detail else ''), flush=True)
def invoice(n, mint=B):
    return json.loads(urllib.request.urlopen(urllib.request.Request(mint+'/v1/mint/quote/bolt11', data=json.dumps({'amount':n,'unit':'sat'}).encode(), headers={'Content-Type':'application/json'})).read())['request']
class W:
    def __init__(s, pg, name): s.pg=pg; s.name=pg, name; s.errs=[]
    async def ev(s, js): return await s.pg.evaluate(js)
    async def click(s, sel): await s.pg.evaluate(f"(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e) throw new Error('missing '+{json.dumps(sel)}); e.click()}})()")
    async def fill(s, sel, v): await s.pg.fill(sel, v); await s.pg.dispatch_event(sel,'input')
    async def wait(s, ms=400): await s.pg.wait_for_timeout(ms)
    async def bal(s, url=None):
        return await s.ev(f"(Nutcade.S.proofs[{json.dumps(url)}]||[]).reduce((t,p)=>t+p.amount,0)" if url else "Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)")
    async def err(s): return await s.ev("(document.querySelector('#sheetErr')||{}).innerText||''")
    async def toast(s): return await s.ev("(document.querySelector('#toast:not([hidden])')||{}).innerText||''")
    async def sheet_text(s): return await s.ev("(document.querySelector('.sheet-body')||{}).innerText||''")
    async def close(s):
        if await s.ev("!!document.querySelector('[data-act=close]')"): await s.click('[data-act=close]'); await s.wait(150)
    async def until(s, js, ms=15000):
        for i in range(ms//250):
            if await s.ev(js): return True
            await s.wait(250)
        return False
    async def create(s, wrong_first=False):
        await s.pg.check('#ack'); await s.click('[data-act=gateCreate]'); await s.wait(400)
        phrase=await s.ev("Nutcade.S.seed.mnemonic"); words=phrase.split()
        await s.pg.check('#wrote'); await s.click('[data-act=gateToConfirm]'); await s.wait(200)
        if wrong_first:
            for el in await s.pg.query_selector_all('[data-cw]'): await el.fill('zebra')
            await s.click('[data-act=gateConfirm]'); await s.wait(300)
            s.wrong_msg=await s.ev("(document.querySelector('#gateErr')||{}).innerText||''")
        for el in await s.pg.query_selector_all('[data-cw]'):
            i=int(await el.get_attribute('data-cw')); await el.fill(words[i])
        await s.click('[data-act=gateConfirm]'); await s.wait(500)
        s.done_shown=await s.ev("document.body.innerText.includes('PLAYER 1 READY')")
        await s.click('[data-act=gateStart]'); await s.wait(400); await s.ev("Nutcade.closeSheet()")
        return phrase
    async def add_mint(s, url):
        await s.click('[data-act=tab][data-tab=wallet]'); await s.wait(100)
        await s.ev("Nutcade.closeSheet()")
        await s.ev("document.querySelector('[data-act=pickMint]').click()"); await s.wait(200)
        await s.fill('#mintUrl', url); await s.click('[data-act=addMintUrl]')
        await s.until("!document.querySelector('#mintUrl') || !!document.querySelector('#toast:not([hidden])')", 8000); await s.wait(200)
    async def use(s, url): await s.ev(f"Nutcade.S.active={json.dumps(url)}; Nutcade.render()")
    async def home(s):
        await s.ev("Nutcade.closeSheet()")
        if await s.ev("!!document.querySelector('[data-act=tab][data-tab=wallet]:not([aria-current])')"): await s.click('[data-act=tab][data-tab=wallet]'); await s.wait(120)
    async def receive_ln(s, amt, note=''):
        await s.home()
        await s.click('[data-act=receive]'); await s.wait(150)
        if await s.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await s.click('[data-act=recvMethod][data-m=ln]'); await s.wait(100)
        before=await s.bal()
        await s.fill('#amtIn', str(amt)); 
        if note: await s.fill('#noteIn', note)
        await s.click('[data-act=doLnInvoice]')
        ok=await s.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {before+amt}", 20000)
        await s.wait(300); await s.close(); return ok
    async def send_ecash(s, amt, note=''):
        await s.home()
        await s.click('[data-act=send]'); await s.wait(150)
        await s.fill('#amtIn', str(amt));
        if note: await s.fill('#noteIn', note)
        await s.click('[data-act=doSendEcash]'); await s.wait(1500)
        e=await s.err(); tok=None
        if not e: tok=await s.ev("Nutcade.S.txs[0].token")
        await s.close(); return tok, e
    async def receive_token(s, tok, note='', trust=True):
        if await s.ev("!!document.querySelector('[data-act=receive]')"): await s.click('[data-act=receive]'); await s.wait(150)
        await s.click('[data-act=recvMethod][data-m=ecash]'); await s.wait(100)
        await s.fill('#tokIn', tok)
        if note: await s.fill('#noteIn', note)
        await s.click('[data-act=doReceiveToken]'); await s.wait(1200)
        trustShown=await s.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')")
        if trustShown and trust: await s.click('[data-act=doReceiveToken]'); await s.wait(1800)
        e=await s.err(); txt=await s.sheet_text(); await s.close(); return trustShown, e, txt
    async def pay_ln(s, inv, note='', confirm=True):
        await s.home()
        await s.click('[data-act=send]'); await s.wait(150); await s.click('[data-act=sendMethod][data-m=ln]'); await s.wait(100)
        await s.fill('#destIn', inv)
        if note: await s.fill('#noteIn', note)
        await s.click('[data-act=doMeltQuote]'); await s.wait(1200)
        e=await s.err()
        if e or not confirm: q=await s.sheet_text(); await s.close(); return e, q
        q=await s.sheet_text()
        await s.click('#payBtn'); await s.wait(3500)
        e=await s.err(); txt=await s.sheet_text(); await s.close(); return e, txt+' || '+q

async def newwallet(b, name):
    ctx=await b.new_context(viewport={'width':390,'height':844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    # Nostr relays and npub.cash point at the local stand-ins (mock_nostr.py), so tests never touch public services.
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs',JSON.stringify({sound:true,crt:true,relays:['ws://127.0.0.1:3350/relay'],npcHost:'http://127.0.0.1:3350'}))")
    pg=await ctx.new_page(); w=W(pg,name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR '+str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE '+m.text) if m.type=='error' and 'ERR_TUNNEL' not in m.text and 'ERR_CONNECTION' not in m.text and 'Failed to load resource' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(800); return w

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(**({'executable_path':os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al=await newwallet(b,'alice')
        check('setup gate shown on first open', await al.ev("!!document.querySelector('[data-act=gateCreate]')"))
        check('no tab bar / arcade before setup', not await al.ev("!!document.querySelector('.tabbar')"))
        check('create button locked until checkbox ticked', await al.ev("document.querySelector('[data-act=gateCreate]').disabled"))
        await al.pg.check('#ack'); check('checkbox unlocks create', not await al.ev("document.querySelector('[data-act=gateCreate]').disabled")); await al.pg.uncheck('#ack')
        await al.pg.reload(); await al.wait(800)
        phrase=await al.create(wrong_first=True)
        check('wrong confirmation word rejected', "doesn't match" in al.wrong_msg, al.wrong_msg)
        check('ready screen shown after backup', al.done_shown)
        check('phrase marked backed up', await al.ev("Nutcade.S.seed.backedUp"))
        check('tab bar appears after setup', await al.ev("!!document.querySelector('.tabbar')"))
        # reload mid-setup resumes at words step (no new phrase)
        mid=await newwallet(b,'mid'); await mid.pg.check('#ack'); await mid.click('[data-act=gateCreate]'); await mid.wait(300)
        p1=await mid.ev("Nutcade.S.seed.mnemonic"); await mid.pg.reload(); await mid.wait(800)
        check('reload during setup keeps same phrase and returns to words', await mid.ev("Nutcade.S.seed.mnemonic")==p1 and await mid.ev("!!document.querySelector('.words')") and not await mid.ev("!!document.querySelector('.tabbar')"))
        await mid.pg.context.close()
        await al.add_mint('notamint.invalid'); t=await al.toast(); check('bad mint address gives readable error', len(t)>10 and 'undefined' not in t, t)
        await al.ev("Nutcade.closeSheet()")
        await al.add_mint(A); check('mint A added + active', await al.ev(f"Nutcade.S.active==={json.dumps(A)}"))
        ok=await al.receive_ln(2000,'Paycheck'); check('LN receive 2000 on A', ok and await al.bal(A)==2000, await al.bal(A))
        tx=await al.ev("Nutcade.S.txs[0]"); check('receive tx has note + done', tx['note']=='Paycheck' and tx['status']=='done', tx)
        await al.add_mint(B); ok=await al.receive_ln(5000); check('LN receive 5000 on B (second mint)', ok and await al.bal(B)==5000)
        await al.use(A)
        tok,e=await al.send_ecash(300,'Pizza for Bob'); check('send 300 ecash token', tok and tok.startswith('cashuB'), e)
        a_after_send=await al.bal(A); check('A balance dropped by 300 + fee', 1695<=a_after_send<=1700, a_after_send)
        tok2,e=await al.send_ecash(99999); check('send more than balance refused', 'Not enough' in e, e)
        # Bob
        bob=await newwallet(b,'bob'); await bob.create()
        trust,e,txt=await bob.receive_token(tok,'From Alice')
        check('unknown-mint token asks to trust first', trust)
        check('bob received ~300', 295<=await bob.bal()<=300 and not e, (await bob.bal(), e))
        btx=await bob.ev("Nutcade.S.txs[0]"); check('bob tx note kept', btx['note']=='From Alice', btx['note'])
        trust,e,txt=await bob.receive_token(tok)
        check('double-claim of same token rejected with clear message', bool(e) and 'undefined' not in e, e)
        # Alice: check claimed
        tid=await al.ev("Nutcade.S.txs.find(t=>t.token)&&Nutcade.S.txs.find(t=>t.token).id")
        await al.ev(f"Nutcade.S.txs.find(t=>t.id==='{tid}')"); 
        await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
        await al.click(f'[data-act=tx][data-id="{tid}"]'); await al.wait(200)
        # with instant updates (NUT-17) the claim may already be known; otherwise the manual check finds it
        if await al.ev("!!document.querySelector('[data-act=checkClaim]')"): await al.click('[data-act=checkClaim]'); await al.wait(1500)
        check('sender sees token claimed', await al.ev(f"Nutcade.S.txs.find(t=>t.id==='{tid}').status")=='claimed')
        await al.close(); await al.click('[data-act=tab][data-tab=wallet]'); await al.wait(150)
        # reclaim
        tok3,e=await al.send_ecash(400,'maybe Carol'); bal_mid=await al.bal(A)
        tid3=await al.ev("Nutcade.S.txs[0].id")
        await al.click('[data-act=tab][data-tab=history]'); await al.wait(200); await al.click(f'[data-act=tx][data-id="{tid3}"]'); await al.wait(200)
        await al.click('[data-act=reclaim]'); await al.wait(2000)
        st=await al.ev(f"Nutcade.S.txs.find(t=>t.id==='{tid3}').status"); check('unclaimed token reclaimed', st=='reclaimed' and await al.bal(A)>=bal_mid+398, (st, await al.bal(A), bal_mid))
        await al.ev("Nutcade.closeSheet()"); await al.click('[data-act=tab][data-tab=wallet]'); await al.wait(150)
        # LN pay
        pre=await al.bal(A)
        e,txt=await al.pay_ln(invoice(500),'Electric bill'); post=await al.bal(A)
        check('LN pay 500 from A succeeds', not e and 'SENT' in txt and pre-post>=500 and pre-post<=510, (e, pre, post))
        ptx=await al.ev("Nutcade.S.txs[0]"); check('LN pay tx done with note', ptx['status']=='done' and ptx['note']=='Electric bill' and ptx['type']=='out', ptx)
        e,q=await al.pay_ln('lnbc123'); check('garbage invoice refused with plain message', 'Lightning invoice' in e and 'Bech32' not in e, e)
        e,q=await al.pay_ln(invoice(50000)); check('over-balance invoice refused before paying', 'Not enough' in e or 'Not enough' in q, (e,q[:120]))
        # failing mint
        await al.add_mint(F); await al.receive_ln(1000)
        pre=await al.bal(F); e,txt=await al.pay_ln(invoice(200),'should fail')
        await al.wait(500); post=await al.bal(F); ftx=await al.ev("Nutcade.S.txs[0]")
        check('failed LN payment returns all sats', post==pre, (pre,post,e))
        check('failed payment shown as failed with message', ftx['status'] in ('failed',) and bool(e), (ftx['status'], e))
        # pending mint
        await al.add_mint(P); await al.receive_ln(1000)
        pre=await al.bal(P); e,txt=await al.pay_ln(invoice(200),'stuck payment')
        ptx=await al.ev("Nutcade.S.txs[0]"); inflight=await al.ev("Nutcade.S.pending.length")
        check('stuck LN payment kept as pending, not lost', ptx['status']=='pending' and inflight>=1, (ptx['status'], inflight, e, txt[:150]))
        await al.click('[data-act=tab][data-tab=wallet]'); await al.wait(200)
        check('in-flight amount shown on wallet', await al.ev("document.body.innerText.includes('in flight')"))
        # notes
        await al.click('[data-act=tab][data-tab=history]'); await al.wait(200)
        await al.fill('#hq','pizza'); await al.wait(300)
        n=await al.ev("document.querySelectorAll('#txList .tx').length"); check('search notes finds pizza only', n==1, n)
        check('search box keeps focus while typing', await al.ev("document.activeElement && document.activeElement.id==='hq'"))
        await al.fill('#hq',''); await al.wait(200)
        await al.click('[data-act=hf][data-f=out]'); await al.wait(200)
        outs=await al.ev("[...document.querySelectorAll('#txList .tx')].every(x=>x.classList.contains('out'))"); check('OUT filter shows only outgoing', outs)
        await al.click('[data-act=hf][data-f=all]'); await al.wait(150)
        tid=await al.ev("Nutcade.S.txs.find(t=>t.note==='Electric bill').id")
        await al.click(f'[data-act=tx][data-id="{tid}"]'); await al.wait(150); await al.pg.fill('#noteEdit','Electric bill (Nov)'); await al.click('[data-act=saveNote]'); await al.wait(200)
        check('edit note saved', await al.ev(f"Nutcade.S.txs.find(t=>t.id==='{tid}').note")=='Electric bill (Nov)')
        # remove mint w/ balance blocked
        await al.click('[data-act=tab][data-tab=mints]'); await al.wait(200)
        await al.click(f'[data-act=removeMint][data-url="{B}"]'); await al.wait(300); t=await al.toast()
        check('removing a mint with sats is blocked', 'before removing' in t, t)
        # backup/restore JSON to Carol
        backup=await al.ev("JSON.stringify({ app: 'nutcade', v: 2, seed: Nutcade.S.seed.mnemonic, counters: Nutcade.S.counters, mints: Nutcade.S.mints, proofs: Nutcade.S.proofs, pending: Nutcade.S.pending, txs: Nutcade.S.txs })")
        await al.ev("Nutcade.closeSheet()"); await al.click('[data-act=tab][data-tab=settings]'); await al.wait(200)
        async with al.pg.expect_download() as dl: await al.click('[data-act=backupDownload]')
        shown=open(await (await dl.value).path()).read()
        check('backup file contains phrase + proofs', phrase in shown and '"proofs"' in shown)
        total_alice=await al.bal()
        carol=await newwallet(b,'carol')
        await carol.create(); await carol.click('[data-act=tab][data-tab=settings]'); await carol.wait(150)
        has=await carol.ev("!!document.querySelector('[data-act=restore]')"); check('JSON backup restore reachable', has)
        if has:
            await carol.click('[data-act=restore]'); await carol.wait(150); await carol.pg.fill('#restoreIn', shown); await carol.click('[data-act=doRestore]'); await carol.wait(500)
            check('JSON restore brings same balance', await carol.bal()==total_alice, (await carol.bal(), total_alice))
        # phrase restore in fresh Dave
        dave=await newwallet(b,'dave')
        await dave.pg.check('#ack'); await dave.click('[data-act=gateRestore]'); await dave.wait(200); await dave.fill('#phraseIn', phrase)
        check('phrase validator says valid', 'Valid' in await dave.ev("document.querySelector('#phraseOk').innerText"))
        await dave.ev("document.querySelectorAll('[data-rmint]').forEach(i=>i.checked=false)")
        await dave.pg.fill('#rmExtra', '\n'.join([A,B,F,P]))
        await dave.click('[data-act=doRestorePhrase]')
        await dave.until("!!document.querySelector('.sheet-body .credit-num')", 90000)
        rest=await dave.bal(); pend_alice=await al.ev("Nutcade.S.pending.reduce((t,p)=>t+p.proofs.reduce((a,x)=>a+x.amount,0),0)")
        check('phrase restore recovers full spendable balance', rest==total_alice, (rest, total_alice, 'alice pending', pend_alice))
        check('restore lists recovered tx notes', await dave.ev("Nutcade.S.txs.some(t=>t.note==='Recovered with recovery phrase')"))
        await dave.close(); await dave.wait(300)
        check('restore from gate enters the app', await dave.ev("!!document.querySelector('.tabbar')"))
        dave_mint=await dave.ev("Nutcade.S.active"); dave_ctr=await dave.ev("JSON.stringify(Nutcade.S.counters)")
        ok=await dave.receive_ln(10) if dave_mint else False
        check('restored wallet can receive (no reused secrets)', ok)
        # same phrase on two devices: Dave used counters Alice hasn't seen; Alice receives on A without rescanning
        await al.click('[data-act=tab][data-tab=wallet]'); await al.wait(150); await al.use(dave_mint)
        await al.ev(f"Object.assign(Nutcade.S.counters, {dave_ctr}); localStorage.setItem('nutcade:counters', JSON.stringify(Nutcade.S.counters))")
        before=await al.bal()
        ok=await al.receive_ln(25)
        after=await al.bal()
        check('second device with same phrase: receive auto-repairs and succeeds', ok and after>=before+25, (before, after))
        check('…and picks up the sats the other device received', after==before+25+10, (before, after))
        before=await al.bal(); await al.click('[data-act=tab][data-tab=settings]'); await al.wait(150); await al.click('[data-act=findLost]'); await al.until("!document.querySelector('[data-act=findLost] .spinner')", 60000); await al.wait(500)
        check('find lost ecash then finds nothing extra', await al.bal()==before, (await al.bal(), before, await al.toast()))
        for w in (al,bob,carol,dave):
            check(f'no script errors ({w.name[1]})', not w.errs, w.errs[:5])
        await b.close()
        json.dump(results, open(OUT+'wallet_results.json','w'))
        print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
if __name__=="__main__":
    asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
