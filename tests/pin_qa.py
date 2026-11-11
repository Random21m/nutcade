import os
import asyncio, json, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wallet_qa
from wallet_qa import W, newwallet, check, results, B
from playwright.async_api import async_playwright
O=os.environ.get('QA_OUT','/tmp/qa-out')+'/'
async def pin(w, digits):
    for d in digits: await w.click(f'[data-pinpad] [data-k="{d}"]')
    await w.click('[data-pinpad] [data-k="ok"]')
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(**({'executable_path':os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w=await newwallet(b,'pin')
        # create wallet but stop on the ready screen to set a PIN there
        await w.pg.check('#ack'); await w.click('[data-act=gateCreate]'); await w.wait(300)
        words=(await w.ev("Nutcade.S.seed.mnemonic")).split(); phrase=' '.join(words)
        await w.pg.check('#wrote'); await w.click('[data-act=gateToConfirm]'); await w.wait(150)
        for el in await w.pg.query_selector_all('[data-cw]'): await el.fill(words[int(await el.get_attribute('data-cw'))])
        await w.click('[data-act=gateConfirm]'); await w.wait(400)
        check('ready screen offers Set a PIN', await w.ev("!!document.querySelector('.gate [data-act=pinSet]')"))
        await w.click('.gate [data-act=pinSet]'); await w.wait(200)
        await pin(w,'12345'); await w.wait(200); check('too-short PIN rejected', 'at least 6' in await w.ev("document.querySelector('#pinErr').innerText"))
        await pin(w,'246810'); await w.wait(200); await pin(w,'246811'); await w.wait(300)
        check("mismatched confirmation starts again", "didn't match" in await w.sheet_text())
        await pin(w,'246810'); await w.wait(200); await pin(w,'246810')
        await w.until("document.body.innerText.includes('LOCKED DOWN')", 20000); await w.pg.screenshot(path=O+'pin_done.png')
        ls=await w.ev("JSON.stringify(Object.keys(localStorage).sort())")
        check('vault created, no plain phrase or ecash in storage', 'nutcade:vault' in ls and 'nutcade:seed' not in ls and 'nutcade:proofs' not in ls and 'nutcade:txs' not in ls, ls)
        rawv=await w.ev("localStorage.getItem('nutcade:vault')") or ''
        check('phrase words do not appear in stored data', not any(x in rawv for x in words[:3]))
        await w.close(); await w.click('[data-act=gateStart]'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
        await w.add_mint(B); ok=await w.receive_ln(1000,'paid while locked-down')
        check('wallet works normally with encryption on', ok and await w.bal()==1000)
        await w.wait(500)
        rawv=await w.ev("localStorage.getItem('nutcade:vault')")
        check('new ecash is stored encrypted too', 'secret' not in rawv and 'paid while' not in rawv)
        # reload -> lock screen
        await w.pg.reload(); await w.wait(800); await w.pg.screenshot(path=O+'pin_lock.png')
        check('opening NUTCADE shows the lock screen', await w.ev("!!document.querySelector('[data-pinpad=unlock]') && !document.querySelector('.tabbar')"))
        check('nothing sensitive in memory while locked', await w.ev("!Nutcade.S.seed && Object.keys(Nutcade.S.proofs).length===0"))
        await pin(w,'111111'); await w.wait(1500); e=await w.ev("document.querySelector('#pinErr').innerText"); check('wrong PIN rejected', 'Wrong PIN' in e, e)
        # keyboard entry
        await w.pg.keyboard.type('246810'); await w.pg.keyboard.press('Enter'); await w.until("!!document.querySelector('.tabbar')", 15000)
        check('right PIN (typed on keyboard) unlocks with balance and notes intact', await w.bal()==1000 and await w.ev("Nutcade.S.txs.some(t=>t.note==='paid while locked-down')"))
        tok,e=await w.send_ecash(100,'after unlock'); check('can send after unlocking', bool(tok), e)
        # lock button
        await w.home(); await w.click('[data-act=lockNow]'); await w.wait(1200)
        check('lock button locks immediately', await w.ev("!!document.querySelector('[data-pinpad=unlock]')"))
        # lockout after 5 wrong
        for i in range(5): await pin(w,'000000'); await w.wait(1300)
        e=await w.ev("document.querySelector('#pinErr').innerText"); check('5 wrong PINs trigger a wait', 'Wait' in e, e)
        await pin(w,'246810'); await w.wait(1300); check('even the right PIN must wait during lockout', not await w.ev("!!document.querySelector('.tabbar')"))
        await w.ev("localStorage.setItem('nutcade:pinfails', JSON.stringify({n:0,until:0}))"); await w.pg.reload(); await w.wait(600)
        await pin(w,'246810'); await w.until("!!document.querySelector('.tabbar')", 15000)
        # change PIN
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        await w.click('[data-act=pinChange]'); await w.wait(150); await pin(w,'999999'); await w.wait(1500)
        check('change PIN asks for the current one', 'wrong' in await w.ev("document.querySelector('#pinErr').innerText"))
        await pin(w,'246810'); await w.wait(1500); await pin(w,'13572468'); await w.wait(200); await pin(w,'13572468'); await w.wait(2000)
        await w.pg.reload(); await w.wait(600); await pin(w,'246810'); await w.wait(1500)
        check('old PIN stops working after change', not await w.ev("!!document.querySelector('.tabbar')"))
        await pin(w,'13572468'); await w.until("!!document.querySelector('.tabbar')", 15000); check('new PIN works', await w.bal()==await w.ev("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)") and await w.bal()>800)
        # passkey (virtual authenticator with PRF)
        cdp=await w.pg.context.new_cdp_session(w.pg); await cdp.send('WebAuthn.enable')
        try:
            auth=await cdp.send('WebAuthn.addVirtualAuthenticator',{'options':{'protocol':'ctap2','transport':'internal','hasResidentKey':True,'hasUserVerification':True,'isUserVerified':True,'automaticPresenceSimulation':True,'hasPrf':True}})
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
            check('Face ID option shown', await w.ev("!!document.querySelector('[data-act=bioStart]')"))
            await w.click('[data-act=bioStart]'); await w.wait(150); await pin(w,'13572468'); await w.until("!document.querySelector('[data-pinpad]')", 20000); await w.wait(300)
            check('Face ID / fingerprint turned on', await w.ev("!!JSON.parse(localStorage.getItem('nutcade:vault')).bio"), await w.toast())
            await w.pg.reload(); await w.wait(700)
            check('lock screen offers Face ID', await w.ev("!!document.querySelector('[data-act=bioUnlock]')"))
            await w.click('[data-act=bioUnlock]'); await w.until("!!document.querySelector('.tabbar')", 15000)
            check('Face ID / fingerprint unlocks the wallet', await w.bal()>800)
        except Exception as ex:
            check('virtual passkey test', False, str(ex)[:200])
        # remove PIN
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150); await w.click('[data-act=pinRemove]'); await w.wait(150); await pin(w,'13572468'); await w.wait(2500)
        ls=await w.ev("JSON.stringify(Object.keys(localStorage).sort())")
        check('remove PIN restores plain storage', 'nutcade:vault' not in ls and 'nutcade:seed' in ls and 'nutcade:proofs' in ls, ls)
        await w.pg.reload(); await w.wait(700); check('no lock screen after removing PIN', await w.ev("!!document.querySelector('.tabbar')") and await w.bal()>800)
        # auto-lock after inactivity
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100); await w.click('[data-act=pinSet]'); await w.wait(100); await pin(w,'112233'); await w.wait(150); await pin(w,'112233'); await w.until("document.body.innerText.includes('LOCKED DOWN')", 15000); await w.close()
        await w.ev("Nutcade.S.prefs.lockAfter=1; localStorage.setItem('nutcade:prefs', JSON.stringify(Nutcade.S.prefs))")
        await w.pg.reload(); await w.wait(500); await pin(w,'112233'); await w.until("!!document.querySelector('.tabbar')", 15000)
        await w.ev("const r=Date.now; Date.now=()=>r()+120000")
        await w.wait(17000)
        check('auto-locks after the chosen idle time', await w.ev("!!document.querySelector('[data-pinpad=unlock]')"))
        # forgot PIN
        await w.click('[data-act=forgotPin]'); await w.wait(150); await w.fill('#confirmWord','RESET'); await w.click('[data-act=doReset]'); await w.wait(1200)
        check('forgot PIN resets to the start screen', await w.ev("!!document.querySelector('[data-act=gateCreate]') && !localStorage.getItem('nutcade:vault')"))
        await w.pg.check('#ack'); await w.click('[data-act=gateRestore]'); await w.wait(150); await w.fill('#phraseIn', phrase)
        await w.ev("document.querySelectorAll('[data-rmint]').forEach(i=>i.checked=false)"); await w.pg.fill('#rmExtra', B)
        await w.click('[data-act=doRestorePhrase]'); await w.until("!!document.querySelector('.sheet-body .credit-num')", 60000)
        check('…and the 12 words bring the sats back', await w.bal()>=890, await w.bal())
        check('no script errors', not w.errs, w.errs[:4])
        await b.close(); print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
