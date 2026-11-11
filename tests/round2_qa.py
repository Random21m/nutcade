"""Round 2 features: trophies and share cards, instant updates (NUT-17), mint-list backup on Nostr (NUT-27)
and the npub.cash Lightning address. Uses the local mints plus mock_nostr.py on port 3350."""
import asyncio, hashlib, json, urllib.request
from playwright.async_api import async_playwright
from wallet_qa import W, newwallet, check, results, A, B
import os

MOCK = 'http://127.0.0.1:3350'

# --- independent key derivations (plain Python, no shared code with the app) ---
P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798, 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)
def _add(a, b):
    if a is None: return b
    if b is None: return a
    if a[0] == b[0] and (a[1] + b[1]) % P == 0: return None
    l = (3 * a[0] * a[0] * pow(2 * a[1], P - 2, P)) % P if a == b else ((b[1] - a[1]) * pow(b[0] - a[0], P - 2, P)) % P
    x = (l * l - a[0] - b[0]) % P
    return (x, (l * (a[0] - x) - a[1]) % P)
def xonly(sk):
    k = int.from_bytes(sk, 'big') % N; r = None; q = G
    while k:
        if k & 1: r = _add(r, q)
        q = _add(q, q); k >>= 1
    return r[0].to_bytes(32, 'big').hex()
CH = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
def _poly(v):
    g = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; c = 1
    for x in v:
        b = c >> 25; c = (c & 0x1ffffff) << 5 ^ x
        for i in range(5): c ^= g[i] if ((b >> i) & 1) else 0
    return c
def npub(hexpk):
    data = bytes.fromhex(hexpk); acc = 0; bits = 0; out = []
    for b in data:
        acc = (acc << 8) | b; bits += 8
        while bits >= 5: bits -= 5; out.append((acc >> bits) & 31)
    if bits: out.append((acc << (5 - bits)) & 31)
    hrp = 'npub'; ex = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = _poly(ex + out + [0] * 6) ^ 1
    return hrp + '1' + ''.join(CH[d] for d in out + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])
def seed_of(m): return hashlib.pbkdf2_hmac('sha512', m.encode(), b'mnemonic', 2048)

def mock(path, data=None):
    req = urllib.request.Request(MOCK + path, data=(json.dumps(data).encode() if data is not None else None), method='POST' if data is not None else 'GET', headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await newwallet(b, 'r2')
        phrase = await w.create()
        await w.wait(400)
        got = await w.ev("Trophies.got()")
        check('trophy: SAVE GAME unlocked after backing up', 'backup' in got, list(got))

        # ---------- NUT-17: a deposit lands without the invoice sheet open ----------
        await w.add_mint(B)
        sup = await w.ev(f"(async()=>{{const r=await fetch('{B}/v1/info').then(r=>r.json()); return !!(r.nuts['17'])}})()")
        check('test mint advertises NUT-17 websockets', sup)
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
        await w.fill('#amtIn', '777'); await w.click('[data-act=doLnInvoice]'); await w.wait(150)
        await w.ev("Nutcade.closeSheet()")   # stop the sheet's own polling: only the websocket (or the 30 s check) can claim it now
        ok = await w.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=777", 7000)
        check('NUT-17: deposit claimed within seconds with the sheet closed', ok, await w.bal())
        check('NUT-17: receive tx done', await w.ev("Nutcade.S.txs[0].status==='done' && Nutcade.S.txs[0].amount===777"))
        got = await w.ev("Trophies.got()")
        check('trophy: FIRST COIN and LIGHTNING ROD unlocked', 'first-in' in got and 'lightning' in got, list(got))

        # sent token claimed elsewhere -> marked claimed live
        tok, e = await w.send_ecash(100, 'For Bea')
        check('send 100 ecash token', bool(tok), e)
        bea = await newwallet(b, 'bea'); await bea.create()
        await bea.receive_token(tok)
        await bea.until("Object.values(Nutcade.S.proofs).flat().length>0", 15000)
        ok = await w.until("Nutcade.S.txs.find(t=>t.token) && Nutcade.S.txs.find(t=>t.token).status==='claimed'", 7000)
        check('NUT-17: sender sees the token claimed within seconds', ok, await w.ev("Nutcade.S.txs.find(t=>t.token).status"))
        await bea.pg.context.close()

        # ---------- NUT-27 mint-list backup ----------
        await w.add_mint(A)
        ok = await w.until("!!Nutcade.S.prefs.mintBackupAt", 9000)
        check('NUT-27: mint list backed up automatically after adding a mint', ok)
        st = mock('/test/state')
        seed = seed_of(phrase)
        bk = hashlib.sha256(seed + b'cashu-mint-backup').digest()
        bpk = xonly(bk)
        evs = [e for e in st['events'] if e['kind'] == 30078 and e['pubkey'] == bpk]
        check('NUT-27: event uses the cashu.me key derivation sha256(seed||"cashu-mint-backup")', len(evs) == 1, [e['pubkey'][:12] for e in st['events']])
        check('NUT-27: kind 30078 with d=mint-list', bool(evs) and ['d', 'mint-list'] in evs[0]['tags'])
        check('NUT-27: mint addresses are encrypted, not readable on the relay', bool(evs) and '127.0.0.1' not in evs[0]['content'])
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
        txt = await w.ev("document.querySelector('#set-backup').innerText")
        check('settings shows the mint-list backup status', 'mint list on nostr' in txt.lower() and 'last backup' in txt.lower(), txt[:300])

        # restore on a fresh device: Find my mints on Nostr
        r = await newwallet(b, 'restorer')
        await r.pg.check('#ack'); await r.click('[data-act=gateRestore]'); await r.wait(200)
        await r.fill('#phraseIn', phrase); await r.click('[data-act=findMints]')
        await r.until("document.querySelector('#nostrMints') && document.querySelector('#nostrMints').innerText.length>5", 9000)
        info = await r.ev("document.querySelector('#nostrMints').innerText")
        ticked = await r.ev("[...document.querySelectorAll('[data-rmint]')].filter(i=>i.checked).map(i=>i.dataset.rmint)")
        check('NUT-27: restore finds the mints from the Nostr backup', 'Found 2 mints' in info, info)
        check('NUT-27: found mints are ticked for scanning', A in ticked and B in ticked, ticked)
        await r.click('[data-act=doRestorePhrase]')
        ok = await r.until("document.querySelector('.sheet-body') && /CONTINUE|SCAN COMPLETE/.test(document.querySelector('.sheet-body').innerText)", 25000)
        rb = await r.bal(); wb = await w.bal()
        check('restore with the found mints recovers the balance', ok and rb == wb, (rb, wb))
        await r.pg.context.close()
        # a phrase with no backup says so
        r2 = await newwallet(b, 'nobackup')
        await r2.pg.check('#ack'); await r2.click('[data-act=gateRestore]'); await r2.wait(200)
        await r2.fill('#phraseIn', 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about')
        await r2.click('[data-act=findMints]')
        await r2.until("document.querySelector('#nostrMints').innerText.length>5", 9000)
        check('NUT-27: no backup found gives a clear message', 'No mint-list backup' in await r2.ev("document.querySelector('#nostrMints').innerText"))
        await r2.pg.context.close()

        # ---------- npub.cash Lightning address ----------
        await w.ev(f"Nutcade.S.active={json.dumps(B)}; Nutcade.render()")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        await w.click('#set-lnaddr [data-act=lnAddr]'); await w.wait(200)
        sheet = await w.sheet_text()
        npk = xonly(seed[:32]); want = npub(npk) + '@127.0.0.1:3350'
        check('Lightning address preview matches cashu.me derivation (seed[0:32])', want in sheet, (want, sheet[:160]))
        await w.click('[data-act=lnAddrOn]')
        await w.until("Nutcade.S.prefs.npc===true", 8000); await w.wait(600)
        st = mock('/test/state')
        check('npub.cash: account reached with valid NIP-98 auth', npk in st['users'], list(st['users']))
        check('npub.cash: payments set to the active mint', st['users'].get(npk, {}).get('mintUrl') == B, st['users'].get(npk))
        ok = await w.until(f"fetch('{MOCK}/test/state').then(r=>r.json()).then(s=>(s.sockets['{npk}']||0)>0)", 6000)
        check('npub.cash: live updates connected (websocket challenge signed)', ok)
        before = await w.bal()
        res = mock(f'/test/pay?pubkey={npk}&amount=2100&lock=1', {})
        ok = await w.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>={before + 2100}", 10000)
        check('npub.cash: locked (NUT-20) payment claimed automatically', ok, (before, await w.bal(), res))
        t = await w.ev(f"Nutcade.S.txs.find(t=>t.quote==={json.dumps(res['quote'])})")
        check('npub.cash: payment shows in notes as Lightning address', bool(t) and t['note'] == 'Lightning address' and t['status'] == 'done', t)
        before = await w.bal()
        res = mock(f'/test/pay?pubkey={npk}&amount=500&lock=0', {})
        ok = await w.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>={before + 500}", 10000)
        check('npub.cash: unlocked payment claimed too', ok)
        n = await w.ev("Nutcade.S.txs.filter(t=>t.note==='Lightning address').length")
        await w.ev("Nutcade.closeSheet()")
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
        await w.click('#set-lnaddr [data-act=lnAddr]'); await w.wait(150)
        await w.click('[data-act=lnAddrSync]'); await w.wait(1500)
        check('npub.cash: syncing again does not double-count', await w.ev("Nutcade.S.txs.filter(t=>t.note==='Lightning address').length") == n)
        await w.ev("Nutcade.closeSheet()"); await w.home()
        await w.click('[data-act=receive]'); await w.wait(150)
        rt = await w.sheet_text()
        check('Receive sheet shows your Lightning address', want in rt, rt[:200])
        await w.ev("Nutcade.closeSheet()")
        got = await w.ev("Trophies.got()")
        check('trophy: CALLING CARD unlocked', 'lnaddr' in got)
        # turn off
        await w.click('[data-act=tab][data-tab=settings]'); await w.wait(100)
        await w.click('#set-lnaddr [data-act=lnAddr]'); await w.wait(150)
        await w.click('[data-act=lnAddrOff]'); await w.wait(800)
        check('npub.cash: turning off stops checking', await w.ev("Nutcade.S.prefs.npc===false"))
        ok = await w.until(f"fetch('{MOCK}/test/state').then(r=>r.json()).then(s=>(s.sockets['{npk}']||0)===0)", 5000)
        check('npub.cash: websocket closed when off', ok)

        # ---------- trophies room + share cards ----------
        await w.click('[data-act=tab][data-tab=arcade]'); await w.wait(300)
        n = await w.ev("document.querySelectorAll('#trophyRoom .trophy').length")
        on = await w.ev("document.querySelectorAll('#trophyRoom .trophy.on').length")
        check('trophy room lists every trophy', n == 21, n)
        check('trophy room marks earned ones', on >= 5, on)
        await w.ev("Trophies.progress('swarm',{wave:3},12000)"); await w.wait(100)
        got = await w.ev("Trophies.got()")
        check('arcade trophies unlock (ACE PILOT, FIVE DIGITS)', 'g-swarm' in got and 'big' in got)
        await w.click('[data-trophy="first-in"]'); await w.wait(150)
        await w.click('#trophyShare')
        ok = await w.until("document.querySelector('.share-card') && document.querySelector('.share-card').naturalWidth===1200", 8000)
        check('trophy card renders at 1200x630', ok and await w.ev("document.querySelector('.share-card').naturalHeight") == 630)
        check('share card offers save and copy', await w.ev("!!document.querySelector('#cardSave') && !!document.querySelector('.sheet-body [data-act=copy]')"))
        await w.pg.screenshot(path=os.environ.get('QA_OUT', '/tmp/qa-out') + '/r2-trophy-card.png')
        # real play: a cabinet counts plays, a high score offers a score card
        await w.ev("Nutcade.closeSheet()")
        plays0 = await w.ev("(JSON.parse(localStorage.getItem('nutcade:plays'))||{n:0}).n")
        await w.ev("Arcade.open('nibble')"); await w.wait(300)
        await w.pg.keyboard.press('Space'); await w.wait(400)
        check('starting a game counts a play', await w.ev("JSON.parse(localStorage.getItem('nutcade:plays')).n") == plays0 + 1)
        await w.ev("document.querySelector('[data-g=exit]').click()"); await w.wait(200)
        await w.ev("localStorage.setItem('nutcade:scores:swarm', JSON.stringify([{n:'ACE',s:12340,t:Date.now()}])); Nutcade.render()")
        await w.wait(200)
        await w.click('[data-card=swarm]')
        ok = await w.until("document.querySelector('.share-card') && document.querySelector('.share-card').naturalWidth===1200", 8000)
        check('hall of fame score card renders', ok)
        dark = await w.ev("""(async()=>{const i=document.querySelector('.share-card'); const c=document.createElement('canvas'); c.width=1200;c.height=630; const x=c.getContext('2d'); x.drawImage(i,0,0); const d=x.getImageData(0,0,1200,630).data; let lit=0; for(let k=0;k<d.length;k+=400) if(d[k]+d[k+1]+d[k+2]>200) lit++; return lit})()""")
        check('score card has visible content', dark > 200, dark)
        alt = await w.ev("document.querySelector('.share-card').alt")
        check('score card text names game and score', 'STAR SWARM' in alt and '12,340' in alt, alt)
        await w.pg.screenshot(path=os.environ.get('QA_OUT', '/tmp/qa-out') + '/r2-score-card.png')
        await w.ev("Nutcade.closeSheet()")
        # existing wallet seeing trophies for the first time: one summary, not a flood
        await w.ev("localStorage.removeItem('nutcade:trophies')"); await w.pg.reload(); await w.wait(1500)
        tt = await w.toast()
        check('first trophy check on an existing wallet shows one summary', 'trophies' in tt and 'Arcade' in tt, tt)

        errs = [e for e in w.errs if 'WebSocket' not in e]
        check('no page errors', not errs, errs[:5])
        await b.close()
    fails = [r for r in results if not r[1]]
    print(f"SUMMARY {len(results) - len(fails)}/{len(results)} passed")

if __name__ == "__main__":
    asyncio.run(main())
