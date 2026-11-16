"""Backup / restore / import grid (1.12.0 fix round). One source wallet per mint (3338 with input fees, 3339 without)
goes through every kind of record a backup can hold, and its backups are imported in every way:

  record kinds   plain coins, deposit (answer lost after the mint issued), deposit paid but never claimed, make (send),
                 gift, bounty, CONTINUE + Extra Life, claim, treasure hunt, Lightning payment in flight
  backup moment  before the step; while the mint's answer is held (record open); after settle; after the step's
                 outputs are partly spent elsewhere (stale)
  target         the same wallet; a fresh device; the same file twice; a 2nd-generation backup (made by a wallet
                 while part of an imported backup waits aside for its mint)
  mint state     up; down while importing, then back up (the part waits aside, Check now)
  PIN            on and off (source wallet with a PIN on the no-fee run, targets alternate)

Invariants in every cell: balance == expected sats (the source wallet's coins, by secret), history adds up to the
balance on both mints, no duplicate line / coin / token, fee lines only equal what the mint kept (the target books
exactly the source's fees), nothing settles or is claimed twice, the journal is empty at the end; a 12-word restore
finds nothing the wallet doesn't show (source wallet, and the fresh device from the 2nd-generation backup)."""
import asyncio, json, os, sys, time, urllib.request
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, A, B, URL, invoice, outside_net
from r7_qa import set_pin, unlock, words_ok

SNAP = """((M,O)=>{const S=Nutcade.S,ps=u=>S.proofs[u]||[],sm=a=>a.reduce((t,p)=>t+p.amount,0);
 const led=u=>{let s=0;for(const t of S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return s};
 const dup=[],ids=new Set(),sec=new Map(),toks={};
 for(const t of S.txs){if(ids.has(t.id))dup.push('line twice '+t.amount+' '+t.note);ids.add(t.id);
  for(const p of (t.sent||[])){if(sec.has(p.secret)&&sec.get(p.secret)!==t.id)dup.push('sent twice '+t.amount);sec.set(p.secret,t.id)}
  if(t.token){toks[t.token]=(toks[t.token]||0)+1;if(toks[t.token]>1)dup.push('token twice')}}
 const all=Object.values(S.proofs).flat().map(p=>p.secret).concat(S.extra?S.extra.proofs.map(p=>p.secret):[]);if(new Set(all).size!==all.length)dup.push('coin twice');
 const SE='Ecash already spent elsewhere';
 return {bal:sm(ps(M)),balO:sm(ps(O)),secs:ps(M).map(p=>[p.secret,p.amount]).sort(),ops:S.ops.length,pend:S.pending.length,imp:(S.imports||[]).length,
  q:S.quotes.length,led:[led(M),sm(ps(M)),led(O),sm(ps(O))],dup,x:S.extra&&S.extra.proofs.map(p=>p.secret).sort(),
  toks:S.txs.filter(t=>t.token&&t.status==='pending').map(t=>[t.amount,(t.sent||[]).map(p=>p.secret).sort().join('|')]).sort(),
  n:S.txs.length,lines:S.txs.filter(t=>t.note!==SE).map(t=>[t.type,t.amount,t.fee||0,t.status,t.mint===M?'M':'O']).sort(),
  fees:S.txs.reduce((a,t)=>a+(t.status==='failed'||t.status==='expired'?0:(+t.fee||0)),0),
  se:S.txs.filter(t=>t.note===SE).map(t=>[t.mint===M?'M':'O',t.amount]),rec:S.txs.filter(t=>/^Recovered/.test(t.note||'')).length,
  row:!!document.querySelector('[data-act=importsRetry]')}})"""
# every container that holds coins outside the balance and is still shown as holding them: none may hold coins the mint
# reports spent (an Extra Life, a token not claimed yet, a copy held as an heir, a bounty offered to us)
DEAD = """(async()=>{const S=Nutcade.S,out=[];const W={};const wal=async u=>{if(!W[u]){W[u]=new CashuLib.Wallet(u,{unit:'sat'});await W[u].loadMint()}return W[u]};
 const sp=async(u,ps)=>{const st=await (await wal(u)).checkProofsStates(ps);return st.map(s=>s.state)};
 const tok=async t=>{const m=CashuLib.getTokenMetadata(t).mint;const w=await wal(m);const d=w.decodeToken(t);return sp(m,d.proofs)};
 if(S.extra){const s=await sp(S.extra.mint,S.extra.proofs);if(s.includes('SPENT'))out.push('extra')}
 for(const t of S.txs.filter(t=>t.status==='pending'&&t.sent&&t.sent.length)){const s=await sp(t.mint,t.sent);if(s.every(x=>x==='SPENT'))out.push('token '+t.amount)}
 for(const h of S.heirlooms.filter(h=>h.state==='waiting')){if((await tok(h.token)).includes('SPENT'))out.push('heirloom '+h.name)}
 for(const c of S.challenges.filter(c=>c.dir==='in'&&c.bounty&&c.bounty.state==='open')){if((await tok(c.bounty.token)).includes('SPENT'))out.push('bounty '+c.id)}
 return out})()"""
HELD = "({h:Nutcade.S.heirlooms.map(h=>[h.name,h.state]).sort(),c:Nutcade.S.challenges.filter(c=>c.dir==='in'&&c.bounty).map(c=>[c.id,c.bounty.state]).sort(),offer:!!document.querySelector('[data-act=extraOpen]')&&!!Nutcade.S.extra})"
def norm(lines): return sorted(l[:3] + ['pc' if l[3] in ('pending', 'claimed') else l[3]] + l[4:] for l in lines)
ROW_STACK = """(()=>{const r=document.querySelector('[data-act=importsRetry]');if(!r)return 'no row';const mid=r.closest('.panel').querySelector('.mid');
 const k=[...mid.children].map(e=>e.getBoundingClientRect());for(let i=1;i<k.length;i++)if(k[i].top<k[i-1].bottom-1)return 'runs together';
 const p=r.closest('.panel').getBoundingClientRect();if(p.right>document.documentElement.clientWidth+1)return 'overflow';return 'ok'})()"""


def ledok(s): return s['led'][0] == s['led'][1] and s['led'][2] == s['led'][3]
def good(s): return ledok(s) and not s['dup'] and s['ops'] == 0 and s['pend'] == 0 and s['imp'] == 0 and s['rec'] == 0
def same(a, b): return a['secs'] == b['secs'] and a['x'] == b['x'] and a['toks'] == b['toks'] and a['balO'] == b['balO']
def brief(s): return {k: s[k] for k in ('bal', 'balO', 'n', 'fees', 'se', 'led', 'dup', 'ops', 'pend', 'imp', 'q', 'rec')}
def differ(a, b): return [k for k in ('secs', 'x', 'toks', 'balO', 'lines', 'fees') if a[k] != b[k]]


async def newwallet(b, tag, vw=375, vh=667):
    ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=1, is_mobile=True, has_touch=True, accept_downloads=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': 'en', 'relays': ['ws://127.0.0.1:3350/relay'], 'npcHost': 'http://127.0.0.1:3350'}
    await ctx.add_init_script("if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + json.dumps(json.dumps(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, tag)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    await pg.goto(URL); await pg.wait_for_timeout(600)
    return w


class Grid:
    def __init__(s, b, M, O, which):
        s.b, s.M, s.O, s.which = b, M, O, which

    async def awake(s, w):   # a PIN wallet left alone (clicks from the script don't count as activity) locks itself
        if await w.ev("Nutcade.vault.on && !Nutcade.vault.open && !!document.querySelector('[data-pinpad]')"): await unlock(w)

    async def snap(s, w): await s.awake(w); return await w.ev(SNAP + f"({json.dumps(s.M)},{json.dumps(s.O)})")

    async def backup(s, w):
        await s.awake(w)
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        async with w.pg.expect_download() as d: await w.pg.evaluate("document.querySelector('[data-act=backupDownload]').click()")
        return open(await (await d.value).path()).read()

    async def imp(s, w, data, settle=True):
        await s.awake(w)
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(150)
        await w.click('[data-act=restore]'); await w.wait(250); await w.fill('#restoreIn', data); await w.click('[data-act=doRestore]')
        await w.until("!document.querySelector('#restoreIn')", 90000); er = await w.err(); await w.wait(600)
        if settle: await w.until("Nutcade.S.ops.length===0&&Nutcade.S.pending.length===0", 90000); await w.wait(1500)
        await w.ev("Nutcade.closeSheet()"); return er

    async def fresh(s, tag, pin=False, vw=375):
        w = await newwallet(s.b, f'{tag}{s.which}', vw); await w.create()
        if pin: await set_pin(w)
        return w

    async def down(s, w, url):
        async def h(route): await route.abort()
        w.downh = h; await w.pg.context.route(url + '/**', h)

    async def up(s, w, url): await w.pg.context.unroute(url + '/**', w.downh)

    async def retry(s, w):
        await w.home(); await w.wait(300)
        if await w.ev("!!document.querySelector('[data-act=importsRetry]')"): await w.click('[data-act=importsRetry]')
        await w.until("(Nutcade.S.imports||[]).length===0", 60000)
        await w.until("Nutcade.S.ops.length===0&&Nutcade.S.pending.length===0", 90000); await w.wait(1500)


async def run_mint(b, M, O, which, pin_src):
    g = Grid(b, M, O, which); T = which
    # ---- setup: source wallet (coins on both mints, Extra Life on M), bob (for a token to claim)
    a = await newwallet(b, 'gA' + which); words = await a.create()
    await a.add_mint(O); await a.receive_ln(1500, 'fund O')
    await a.add_mint(M); await a.receive_ln(12000, 'fund M'); await a.wait(1200)
    if pin_src: await set_pin(a)
    bob = await newwallet(b, 'gbob' + which); await bob.create(); await bob.add_mint(M); await bob.receive_ln(3000)
    heir = await a.ev("CashuLib.nprofileEncode({pubkey: CashuLib.nostrPub(crypto.getRandomValues(new Uint8Array(32))), relays:['ws://127.0.0.1:3350/relay']})")
    await a.click('[data-act=tab][data-tab=settings]'); await a.click('[data-act=contactsOpen]'); await a.wait(150); await a.click('[data-act=contactEdit]'); await a.wait(150)
    await a.fill('#cName', 'Heir G'); await a.fill('#cNostr', heir); await a.click('[data-act=contactSave]'); await a.wait(300); await a.ev("Nutcade.closeSheet()")
    await a.use(M); await a.home(); await a.click('[data-act=extraOpen]'); await a.until("!!document.querySelector('#xlTo')", 5000); await a.wait(150)
    await a.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Heir G').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
    await a.fill('#amtIn', '500'); await a.click('[data-act=extraStart]'); await a.until("!!Nutcade.S.extra", 20000); await a.wait(800); await a.ev("Nutcade.closeSheet()")
    hold = {'ep': None, 'mode': 'held', 'hit': False, 'go': asyncio.Event(), 'lost': False}

    async def h(route):
        try:
            ep = route.request.url.split('/v1/', 1)[1].split('?')[0]; post = route.request.method == 'POST'
            if post and hold['lost'] and ep == 'mint/bolt11': hold['hit'] = True; return await route.abort()
            if post and hold['ep'] and ep == hold['ep']:
                hold['ep'] = None; await route.fetch(); hold['hit'] = True; await hold['go'].wait(); return await route.abort()
            await route.continue_()
        except Exception: pass
    await a.pg.context.route(M + '/v1/**', h)
    a0 = await g.snap(a)
    check(f'{T} setup: source wallet funded, Extra Life on the mint, history = balance', a0['x'] and a0['bal'] > 10000 and good(a0), brief(a0))

    # ---- backup BEFORE any step (plain coins + Extra Life): fresh device, same file twice, into the source itself
    B0 = await g.backup(a); a_b0 = a0
    c = await g.fresh('gC0', pin=(which == 'fee'))
    er = await g.imp(c, B0); c1 = await g.snap(c)
    check(f'{T} plain coins, backup before the steps -> fresh device{" (PIN)" if which == "fee" else ""}: same coins, Extra Life, history, fees', not er and same(c1, a0) and c1['lines'] == a0['lines'] and c1['fees'] == a0['fees'] and good(c1), (er, brief(c1), brief(a0)))
    er = await g.imp(c, B0); c2 = await g.snap(c)
    check(f'{T} plain coins: same file twice: nothing changes', not er and same(c2, c1) and c2['n'] == c1['n'] and good(c2), brief(c2))
    er = await g.imp(a, B0); a1 = await g.snap(a)
    check(f'{T} plain coins: into the wallet that made it: nothing changes', not er and same(a1, a0) and a1['n'] == a0['n'] and good(a1), brief(a1))
    await c.pg.context.close()

    # ---- record kinds: backup while the mint's answer is held; a fresh device restores it before the source settles
    snaps = {'before': (B0, a0)}
    kinds = ['deposit', 'make', 'gift', 'bounty', 'cont', 'claim', 'hunt', 'pay']
    downk = {'deposit', 'gift', 'cont', 'pay'}
    for i, k in enumerate(kinds):
        try:
            a0 = await g.snap(a); ep = 'swap'
            if k == 'deposit':
                ep = 'mint/bolt11'
                async def start():
                    await a.home(); await a.click('[data-act=receive]'); await a.wait(150)
                    if await a.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await a.click('[data-act=recvMethod][data-m=ln]'); await a.wait(100)
                    await a.fill('#amtIn', '222'); await a.click('[data-act=doLnInvoice]')
            elif k == 'make':
                async def start(): await a.home(); await a.click('[data-act=send]'); await a.wait(150); await a.fill('#amtIn', '500'); await a.click('[data-act=doSendEcash]')
            elif k == 'gift':
                async def start():
                    await a.home(); await a.click('[data-act=send]'); await a.wait(150); await a.pg.check('#giftOn')
                    await a.ev("const s=document.querySelector('#giftTo'); if (s) { s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})) }")
                    await a.fill('#giftKey', '02' + 'cd' * 32); await a.fill('#amtIn', '300'); await a.click('[data-act=doSendEcash]')
            elif k == 'bounty':
                async def start():
                    await a.ev("Nutcade.closeSheet()"); await a.click('[data-act=tab][data-tab=arcade]'); await a.wait(200)
                    await a.ev(f"Nutcade.startChallenge({{game:'flipper', seed:{4000 + i}, score:1200, by:'GRD'}})"); await a.wait(300); await a.fill('#bountyAmt', '250'); await a.click('[data-act=chalSend]')
            elif k == 'cont':
                async def start(): await a.home(); await a.click('[data-act=extraOpen]'); await a.wait(300); await a.click('[data-act=extraContinue]')
            elif k == 'claim':
                tok, e = await bob.send_ecash(700)
                async def start(): await a.home(); await a.click('[data-act=receive]'); await a.wait(150); await a.click('[data-act=recvMethod][data-m=ecash]'); await a.wait(100); await a.fill('#tokIn', tok); await a.click('[data-act=doReceiveToken]')
            elif k == 'hunt':
                async def start(): await a.home(); await a.click('[data-act=huntNew]'); await a.wait(200); await a.fill('#amtIn', '600'); await a.click('[data-act=huntCreate]')
            elif k == 'pay':
                ep = 'melt/bolt11'; inv = invoice(1234, O)
                async def start():
                    await a.home(); await a.click('[data-act=send]'); await a.wait(150); await a.click('[data-act=sendMethod][data-m=ln]'); await a.wait(100)
                    await a.fill('#destIn', inv); await a.click('[data-act=doMeltQuote]'); await a.until("!!document.querySelector('#payBtn')", 20000); await a.click('#payBtn')
            hold.update(ep=ep, hit=False); hold['go'] = asyncio.Event()
            await start()
            for _ in range(120):
                if hold['hit']: break
                await asyncio.sleep(0.25)
            await a.wait(1000); H = await g.backup(a); d = json.loads(H)
            open_rec = len(d.get('ops') or []) + len(d.get('pending') or []) + len([q for q in d.get('quotes') or [] if q.get('state') == 'PAID'])
            check(f'{T} {k}: backup taken while the mint\'s answer is held holds the open record', hold['hit'] and open_rec >= 1, (hold['hit'], open_rec))
            pin = (i % 2 == 0) == (which == 'fee'); dn = k in downk
            c = await g.fresh('gC' + k, pin=pin)
            if dn:
                await g.down(c, M); er = await g.imp(c, H, settle=False); await c.home(); await c.wait(300); cw = await g.snap(c)
                check(f'{T} {k}: restored with the mint down: its part waits aside (Check now row), the other mint\'s part is in', not er and cw['imp'] == 1 and cw['row'] and cw['bal'] == 0 and cw['balO'] == a0['balO'] and ledok(cw) and not cw['dup'], (er, brief(cw)))
                er = await g.imp(c, H, settle=False); await c.home(); await c.wait(300); cw2 = await g.snap(c)
                check(f'{T} {k}: same file again while the mint is down: still one waiting part, nothing doubled', cw2['imp'] == 1 and cw2['n'] == cw['n'] and cw2['balO'] == cw['balO'] and not cw2['dup'], brief(cw2))
                await g.up(c, M); await g.retry(c)
            else:
                er = await g.imp(c, H)
            if k in ('deposit',): await c.until(f"Nutcade.S.quotes.length===0", 40000); await c.wait(500)
            c1 = await g.snap(c)
            hold['go'].set()
            oka = await a.until("Nutcade.S.ops.length===0&&Nutcade.S.pending.length===0&&Nutcade.S.quotes.length===0", 90000); await a.wait(2000); await a.ev("Nutcade.closeSheet()")
            a1 = await g.snap(a); c1 = await g.snap(c)
            lbl = f'{T} {k} (record open{", mint down then Check now" if dn else ""}{", PIN" if pin else ""})'
            check(f'{lbl}: source and restored device both settle, journal empty', oka and good(a1) and good(c1), (brief(a1), brief(c1), er))
            check(f'{lbl}: both end with the SAME coins, Extra Life, open tokens, other-mint coins', same(c1, a1), (a1['bal'], c1['bal'], len(set(map(tuple, a1['secs'])) ^ set(map(tuple, c1['secs'])))))
            check(f'{lbl}: same history lines, same fees (no fake fee, no fake spent-elsewhere)', c1['lines'] == a1['lines'] and c1['fees'] == a1['fees'] and not c1['se'], ([x for x in c1['lines'] if x not in a1['lines']], [x for x in a1['lines'] if x not in c1['lines']], c1['fees'], a1['fees'], c1['se']))
            if k == 'deposit': check(f'{T} deposit: 222 credited once on each device', a1['bal'] - a0['bal'] == 222 and c1['bal'] == a1['bal'], (a0['bal'], a1['bal'], c1['bal']))
            if k == 'claim': check(f'{T} claim: credited once', 690 <= a1['bal'] - a0['bal'] <= 700, (a0['bal'], a1['bal']))
            if k == 'pay':
                t = await a.ev("(t=>t&&[t.status,t.amount,t.fee])(Nutcade.S.txs.find(t=>t.amount===1234&&t.method==='ln'&&t.type==='out'))")
                check(f'{T} pay: paid once, change back', t and t[0] == 'done' and a0['bal'] - a1['bal'] == 1234 + t[2] and t[2] <= 15, (a0['bal'], a1['bal'], t))
            if k == 'cont': check(f'{T} cont: CONTINUE once, balance unmoved', a1['bal'] == a0['bal'] and a1['x'] and a1['x'] != a0['x'], (a0['bal'], a1['bal']))
            er = await g.imp(c, H); c2 = await g.snap(c)
            check(f'{lbl}: same file twice into the restored device changes nothing', not er and same(c2, c1) and c2['n'] == c1['n'] and good(c2), brief(c2))
            er = await g.imp(a, H); a2 = await g.snap(a)
            check(f'{lbl}: same file into the wallet that made it (settled since) changes nothing', not er and same(a2, a1) and a2['n'] == a1['n'] and good(a2), brief(a2))
            snaps[k] = (H, a2)
            await c.pg.context.close()
        except Exception as e:
            check(f'{T} {k}: script error', False, repr(e)[:300]); hold['go'].set()

    # ---- after settle: backup F; 2nd generation (a backup made while part of F waits aside)
    aF = await g.snap(a); F = await g.backup(a)
    gw = await g.fresh('gG', pin=(which == 'nofee'), vw=320)
    await g.down(gw, M); er = await g.imp(gw, F, settle=False); await g.imp(gw, F, settle=False); await gw.home(); await gw.wait(300); gw1 = await g.snap(gw)
    check(f'{T} after settle, mint down, same file twice: ONE waiting part, other mint in, nothing doubled', not er and gw1['imp'] == 1 and gw1['balO'] == aF['balO'] and gw1['bal'] == 0 and ledok(gw1) and not gw1['dup'], brief(gw1))
    lay = {}
    for vw in (320, 375, 1440):
        await gw.pg.set_viewport_size({'width': vw, 'height': 800}); await gw.wait(250); lay[vw] = await gw.ev(ROW_STACK)
    await gw.pg.set_viewport_size({'width': 320, 'height': 667})
    check(f'{T} waiting row reads title / amount / explanation, one under the other (320, 375, 1440)', all(v == 'ok' for v in lay.values()), lay)
    F2 = await g.backup(gw); f2 = json.loads(F2)
    check(f'{T} 2nd-generation backup (made while waiting) holds the waiting part', len(f2.get('imports') or []) == 1, len(f2.get('imports') or []))
    if which == 'nofee':
        await gw.pg.reload(); await gw.wait(1200); await unlock(gw); await gw.wait(2500); gw2 = await g.snap(gw)
        check(f'{T} PIN wallet reloaded while the mint is still down: still waiting, nothing lost or added', gw2['imp'] == 1 and gw2['row'] and gw2['n'] == gw1['n'] and gw2['balO'] == gw1['balO'], brief(gw2))
    e = await g.fresh('gE', pin=False); er = await g.imp(e, F2); await e.until("(Nutcade.S.imports||[]).length===0", 30000); e1 = await g.snap(e)
    check(f'{T} 2nd-generation backup into a fresh device: same coins, lines, fees as the source, no duplicate', not er and same(e1, aF) and e1['lines'] == aF['lines'] and e1['fees'] == aF['fees'] and not e1['se'] and good(e1), (brief(e1), differ(e1, aF), [x for x in e1['lines'] if x not in aF['lines']]))
    er = await g.imp(e, F2); e2 = await g.snap(e)
    check(f'{T} 2nd-generation backup twice: nothing changes', same(e2, e1) and e2['n'] == e1['n'] and good(e2), brief(e2))
    ok, info = await words_ok(e, [M, O]); check(f'{T} 12-word restore on the fresh device = its balance', ok, info)
    await e.pg.context.close()
    await g.up(gw, M); await g.retry(gw); gw3 = await g.snap(gw)
    check(f'{T} Check now with the mint back: the part comes in ONCE, same coins, lines, fees as the source', same(gw3, aF) and gw3['lines'] == aF['lines'] and gw3['fees'] == aF['fees'] and not gw3['se'] and good(gw3), (brief(gw3), differ(gw3, aF), [x for x in gw3['lines'] if x not in aF['lines']]))
    er = await g.imp(gw, F2); gw4 = await g.snap(gw)
    check(f'{T} its own 2nd-generation backup imported again: nothing changes', same(gw4, gw3) and gw4['n'] == gw3['n'] and good(gw4), brief(gw4))
    await gw.pg.context.close()
    # the same wallet: its own backup imported while one of its mints is down (nothing new: no waiting part), then its
    # backup (2nd generation) into a fresh device
    await g.down(a, O); er = await g.imp(a, F, settle=False); await a.home(); a3 = await g.snap(a)
    check(f'{T} own backup imported while a mint is down: nothing waits aside for coins it holds, nothing changes', a3['imp'] == 0 and not a3['row'] and same(a3, aF) and a3['n'] == aF['n'] and good(a3), brief(a3))
    F3 = await g.backup(a); await g.up(a, O)
    e = await g.fresh('gE2'); er = await g.imp(e, F3); e3 = await g.snap(e)
    check(f'{T} its next backup into a fresh device: same coins, lines, fees', not er and same(e3, aF) and e3['lines'] == aF['lines'] and e3['fees'] == aF['fees'] and good(e3), (brief(e3), differ(e3, aF)))
    await e.pg.context.close()

    # ---- partly spent elsewhere: the source spends most of its coins (a token bob claims), then the old backups
    tok, e_ = await a.send_ecash(aF['bal'] * 6 // 10)
    # a backup with that token not claimed yet, holding (as an heir's copy and as a bounty offered to us) a token that
    # gets spent and one that stays unspent (an open gift of the source's)
    hs = json.loads(await g.backup(a)); live = await a.ev("Nutcade.S.txs.find(t=>t.status==='pending'&&t.token&&t.amount===300).token")
    far = int(time.time() * 1000) + 10**10
    hs['heirlooms'] = (hs.get('heirlooms') or []) + [{'from': 'ab' * 32, 'name': 'Dead', 'token': tok, 'amount': 1, 'mint': M, 'until': far, 'state': 'waiting', 'at': 1}, {'from': 'ac' * 32, 'name': 'Live', 'token': live, 'amount': 1, 'mint': M, 'until': far, 'state': 'waiting', 'at': 1}]
    hs['challenges'] = (hs.get('challenges') or []) + [{'dir': 'in', 'id': cid, 'game': 'flipper', 'seed': 5, 'score': 100, 'by': 'GRD', 'pubkey': 'ab' * 32, 'at': 1, 'best': None, 'bounty': {'token': tk, 'amount': 1, 'mint': M, 'H': '00' * 32, 'until': far, 'state': 'open', 'game': 'flipper'}} for cid, tk in (('gdead', tok), ('glive', live))]
    snaps['sent'] = (json.dumps(hs), await g.snap(a))
    await bob.receive_token(tok); await a.wait(1000)
    # and the source continues its Extra Life again: the CONTINUE record in the cont backup now renews spent coins
    x0 = (await g.snap(a))['x']; await a.home(); await a.click('[data-act=extraOpen]'); await a.wait(300); await a.click('[data-act=extraContinue]')
    await a.until(f"Nutcade.S.extra && JSON.stringify(Nutcade.S.extra.proofs.map(p=>p.secret).sort())!=={json.dumps(json.dumps(x0, separators=(',', ':')))}", 30000); await a.wait(1500); await a.ev("Nutcade.closeSheet()")
    an = await g.snap(a); now = {s for s, _ in an['secs']}
    check(f'{T} stale setup: bob claimed the source\'s token, the source continued its Extra Life again', not e_ and an['bal'] < aF['bal'] // 2 and an['x'] and an['x'] != x0, (e_, an['bal'], an['x'] != x0))
    for k in ('before', 'deposit', 'make', 'gift', 'claim', 'pay', 'cont', 'sent'):
        H, ak = snaps[k]
        exp = sorted(x for x in ak['secs'] if x[0] in now)
        pin = k == 'gift' or (k == 'cont') == (which == 'fee') and k in ('cont', 'sent')
        d_ = await g.fresh('gD' + k, pin=pin); er = await g.imp(d_, H)
        if k == 'deposit': await d_.until("Nutcade.S.quotes.length===0", 40000); await d_.wait(500)
        d1 = await g.snap(d_)
        lbl = f'{T} stale backup ({k}{": record open" if k not in ("before", "sent") else ""}) after its coins were partly spent elsewhere, into a fresh device{" (PIN)" if pin else ""}'
        check(f'{lbl}: exactly the coins still unspent ({sum(x[1] for x in exp)} SAT), history = balance, journal empty', not er and d1['secs'] == exp and good(d1), (er, brief(d1), sum(x[1] for x in exp)))
        check(f'{lbl}: fees = what the mint kept (as on the source), no fake fee line; one spent-elsewhere line', d1['fees'] == ak['fees'] and norm(d1['lines']) == norm(ak['lines']) and len(d1['se']) <= 1, (d1['fees'], ak['fees'], d1['se'], [x for x in d1['lines'] if x not in ak['lines']], [x for x in ak['lines'] if x not in d1['lines']]))
        await d_.wait(2500); dead = await d_.ev(DEAD); dh = await d_.ev(HELD)
        check(f'{lbl}: nothing still shown as holding coins the mint says are spent (Extra Life, unclaimed token, heir copy, bounty), live ones kept', not dead and (d1['x'] is None or d1['x'] == an['x']) and (k != 'sent' or (dh['h'] == [['Dead', 'ended'], ['Live', 'waiting']] and dh['c'] == [['gdead', 'gone'], ['glive', 'open']])) and (k != 'cont' or not dh['offer']), (dead, dh, d1['x'] is None))
        er = await g.imp(d_, H); d2 = await g.snap(d_)
        check(f'{lbl}: same file twice: nothing changes', same(d2, d1) and d2['n'] == d1['n'] and good(d2), brief(d2))
        await d_.pg.context.close()
        er = await g.imp(a, H); a4 = await g.snap(a)
        check(f'{T} stale backup ({k}) into the wallet that made it: nothing changes', not er and same(a4, an) and a4['n'] == an['n'] and good(a4), brief(a4))
        if k == 'sent':
            await a.wait(2500); ah = await a.ev(HELD)
            check(f'{T} stale backup (sent) into the wallet that made it: the spent heir copy and bounty it brings are closed, the live ones kept, its Extra Life untouched', ah['h'] == [['Dead', 'ended'], ['Live', 'waiting']] and ah['c'] == [['gdead', 'gone'], ['glive', 'open']] and (await g.snap(a))['x'] == an['x'], ah)
    await g.awake(a); ok, info = await words_ok(a, [M, O]); check(f'{T} END source wallet: 12-word restore = balance', ok, info)

    # ---- deposit paid but never claimed (the claim never reaches the mint), then the device is lost
    hold['lost'] = True; hold['hit'] = False
    await a.home(); await a.click('[data-act=receive]'); await a.wait(150)
    if await a.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await a.click('[data-act=recvMethod][data-m=ln]'); await a.wait(100)
    await a.fill('#amtIn', '222'); await a.click('[data-act=doLnInvoice]')
    await a.until("Nutcade.S.quotes.some(q=>q.state==='PAID')", 30000); await a.wait(800)
    qid = await a.ev("(Nutcade.S.quotes[0]||{}).quote"); HQ = await g.backup(a); hq = json.loads(HQ)
    hqbal = sum(p['amount'] for p in hq['proofs'].get(M, [])); hqo = sum(p['amount'] for p in hq['proofs'].get(O, []))
    st0 = json.loads(urllib.request.urlopen(f'{M}/v1/mint/quote/bolt11/{qid}').read())['state']
    check(f'{T} deposit paid, not claimed: the backup holds the deposit (mint says {st0})', st0 == 'PAID' and any(q.get('quote') == qid for q in hq.get('quotes') or []), [q.get('quote') for q in hq.get('quotes') or []])
    await a.pg.context.close(); await bob.pg.context.close()   # first device lost
    c = await g.fresh('gCq', pin=(which == 'nofee'))
    await g.down(c, M); er = await g.imp(c, HQ, settle=False); await g.imp(c, HQ, settle=False); await c.home(); cq = await g.snap(c)
    check(f'{T} paid deposit restored with its mint down (twice): one waiting part, nothing claimed yet', cq['imp'] == 1 and cq['bal'] == 0 and cq['balO'] == hqo and ledok(cq) and not cq['dup'], brief(cq))
    await g.up(c, M); await g.retry(c); await c.until(f"Nutcade.S.quotes.length===0&&(Nutcade.S.proofs[{json.dumps(M)}]||[]).reduce((a,p)=>a+p.amount,0)>={hqbal + 222}", 40000); await c.wait(1500); cq1 = await g.snap(c)
    st1 = json.loads(urllib.request.urlopen(f'{M}/v1/mint/quote/bolt11/{qid}').read())['state']
    dl = await c.ev(f"Nutcade.S.txs.filter(t=>t.quote==={json.dumps(qid)}).map(t=>[t.status,t.amount])")
    check(f'{T} Check now: the restored wallet claims the paid deposit ONCE (+222, its own line done), history = balance', cq1['bal'] == hqbal + 222 and dl == [['done', 222]] and st1 == 'ISSUED' and good(cq1) and cq1['q'] == 0, (brief(cq1), hqbal, dl, st1))
    er = await g.imp(c, HQ); await c.pg.reload(); await c.wait(1200)
    if which == 'nofee': await unlock(c)
    await c.wait(9000); cq2 = await g.snap(c)
    check(f'{T} same file again + reload: nothing claimed twice, no new line', same(cq2, cq1) and cq2['n'] == cq1['n'] and good(cq2) and cq2['q'] == 0, brief(cq2))
    await c.pg.context.close()
    e = await g.fresh('gEq'); er = await g.imp(e, HQ); await e.wait(9000); eq = await g.snap(e)
    dl = await e.ev(f"Nutcade.S.txs.filter(t=>t.quote==={json.dumps(qid)}).map(t=>[t.status,t.amount])")
    check(f'{T} the same backup into another device after the deposit was claimed: no second 222, history = balance', eq['bal'] == hqbal and ledok(eq) and not eq['dup'] and not any(x == ['done', 222] for x in dl), (brief(eq), dl))
    await e.pg.context.close()


async def main():
    only = sys.argv[1:] or ['fee', 'nofee']
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None)
        t0 = time.time()
        if 'fee' in only: await run_mint(b, A, B, 'fee', pin_src=False)
        if 'nofee' in only: await run_mint(b, B, A, 'nofee', pin_src=True)
        await b.close()
    n = len(results); ok = sum(1 for r in results if r[1])
    print(f'SUMMARY {ok}/{n} passed ({int(time.time() - t0)} s)')

if __name__ == '__main__':
    asyncio.run(main())
