"""Round 9 (1.14): the keyset check-up. Mints rotate their keys; coins of an old (inactive, expiring or expired) keyset
are moved to the mint's active keyset through the journal, tiny coins are combined, and the mint's line in Mints says
what happened.

Starts its own local test mints (they are restarted to rotate their keys, so they are not the shared ones):
  R9_PORT (3438) fee mint (100 ppk), +1 no-fee mint, +2 no-fee mint taking at most 128 items per request (NUT-06),
  +3 no-fee mint for expiry, refusal and dropped keys.
Keys are rotated with tests/rotate_keyset.py (Nutshell's own rotate_next_keyset on the stopped mint's database; then
the mint is started again). R9_NOSTR (ws://127.0.0.1:3350/relay) is the mock relay; R9_ONLY=a,b runs some sections.

The grid: keyset active / inactive / expiring / expired-and-refused / dropped x fee and no-fee mint x automatic on and
off x a crash before and after the swap (and between parts) x two devices with one phrase (one after the other and at
once) x a backup taken before and imported after (same wallet, a new device, a backup holding the open step) x the
duress PIN's wallet x a mint that is down x coins already spent elsewhere x a 128-item mint with hundreds of coins x
the spending limit x five languages."""
import asyncio, json, math, os, re, shutil, subprocess, sys, time, urllib.request, urllib.error
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net

HERE = os.path.dirname(os.path.abspath(__file__))
P0 = int(os.environ.get('R9_PORT', '3438'))
FEE, FREE, LIM, AUX = (f'http://127.0.0.1:{P0 + i}' for i in range(4))
NOSTR = os.environ.get('R9_NOSTR', 'ws://127.0.0.1:3350/relay')
NPC = re.sub(r'^ws', 'http', NOSTR).rsplit('/', 1)[0]
MPY = os.environ.get('MINT_PY', 'python3')
MDIR = os.path.join(os.environ.get('QA_OUT', '/tmp/qa-out'), 'r9mints')
HOLD = os.path.join(MDIR, 'holds')   # (tests/stub/sitecustomize.py: a file here holds a deposit's mint request at the mint)
PIN, DPIN = '135791', '246802'
LEDGER = """(u=>{let s=0;for(const t of Nutcade.S.txs){if(t.mint!==u||t.status==='failed'||t.status==='expired')continue;if(t.type==='in'){if(t.status==='done'||t.status==='claimed')s+=t.amount}else s-=t.amount+(t.fee||0)}return [s,(Nutcade.S.proofs[u]||[]).reduce((a,p)=>a+p.amount,0)]})"""
MINTS = {FEE: ('Fee Mint', {}), FREE: ('Free Mint', {'MINT_INPUT_FEE_PPK': '0'}), LIM: ('Limit Mint', {'MINT_INPUT_FEE_PPK': '0', 'MINT_MAX_REQUEST_LENGTH': '128'}), AUX: ('Aux Mint', {'MINT_INPUT_FEE_PPK': '0'})}
procs = {}
J = json.dumps


# ---------------- the test mints ----------------
def mdir(u): return os.path.join(MDIR, u.rsplit(':', 1)[1])
def menv(u):
    name, extra = MINTS[u]; port = u.rsplit(':', 1)[1]
    e = dict(os.environ, MINT_BACKEND_BOLT11_SAT='FakeWallet', MINT_PRIVATE_KEY=f'nutcade-r9-{port}', MINT_LISTEN_HOST='127.0.0.1', MINT_LISTEN_PORT=port,
             MINT_DATABASE='data/mint', FAKEWALLET_BRR='TRUE', FAKEWALLET_DELAY_INCOMING_PAYMENT='0.5', FAKEWALLET_DELAY_OUTGOING_PAYMENT='0.5',
             MINT_INFO_NAME=name, NUTCADE_PREIMAGE_DIR=os.path.join(MDIR, 'preimages'), NUTCADE_HOLD_DIR=HOLD, PYTHONPATH=os.path.join(HERE, 'stub'))
    e.update(extra); return e
def up(u):
    try: return b'pubkey' in urllib.request.urlopen(u + '/v1/info', timeout=2).read()
    except Exception: return False
def start(u, fresh=False):
    d = mdir(u)
    if fresh: shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    procs[u] = subprocess.Popen([MPY, '-m', 'uvicorn', 'cashu.mint.app:app', '--host', '127.0.0.1', '--port', u.rsplit(':', 1)[1]], cwd=d, env=menv(u), stdout=open(os.path.join(d, 'log'), 'a'), stderr=subprocess.STDOUT)
    for _ in range(240):
        if up(u): return True
        time.sleep(0.25)
    raise RuntimeError(f'mint {u} did not start')
def stop(u):
    p = procs.pop(u, None)
    if not p: return
    p.terminate()
    try: p.wait(20)
    except Exception: p.kill(); p.wait(10)
    for _ in range(40):
        if not up(u): break
        time.sleep(0.25)
def keyset_cmd(u, *args):
    r = subprocess.run([MPY, os.path.join(HERE, 'rotate_keyset.py'), *map(str, args)], cwd=mdir(u), env=menv(u), capture_output=True, text=True, timeout=120)
    if r.returncode: raise RuntimeError(r.stderr[-600:])
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ''
async def rotate(u, *args, restart=True):
    """new active keyset (the old one inactive); returns its id. The mint is down in between, like a real restart."""
    def go():
        stop(u); kid = keyset_cmd(u, 'rotate', *args)
        if restart: start(u)
        return kid
    return await asyncio.to_thread(go)
async def keyset_do(u, *args):
    def go(): stop(u); r = keyset_cmd(u, *args); start(u); return r
    return await asyncio.to_thread(go)
def keysets(u): return json.loads(urllib.request.urlopen(u + '/v1/keysets', timeout=10).read())['keysets']
def active(u): return [k['id'] for k in keysets(u) if k['active'] and k['unit'] == 'sat']


# ---------------- wallets ----------------
async def wallet(b, lang='en', vw=375):
    ctx = await b.new_context(viewport={'width': vw, 'height': 740}, device_scale_factor=1, is_mobile=True, has_touch=True, accept_downloads=True)
    prefs = {'sound': False, 'music': False, 'crt': False, 'lang': lang, 'relays': [NOSTR], 'npcHost': NPC}
    await ctx.add_init_script("window.__i18nMiss=new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, 'r9'); w.swaps = []; w.ctx = ctx
    await attach(w, pg)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def attach(w, pg):
    w.pg = pg
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and not re.search(r'status of (4\d\d|5\d\d)|ERR_ABORTED|net::|Failed to fetch', m.text) else None)
    def req(r):
        if r.method == 'POST' and r.url.endswith('/v1/swap'):
            try: d = json.loads(r.post_data or '{}')
            except Exception: d = {}
            w.swaps.append((r.url.rsplit('/v1/', 1)[0], len(d.get('inputs', [])), len(d.get('outputs', [])), sorted({o.get('id') for o in d.get('outputs', [])})))
    pg.on('request', req)


async def fresh(b, *mints, lang='en'):
    w = await wallet(b, lang); await w.create()
    for u in mints: await w.add_mint(u)
    return w


async def fund(w, u, amt):
    await w.use(u); ok = await w.receive_ln(amt); return ok


async def status(w, u): return await w.ev(f"(window.Nutcade&&Nutcade.r9&&Nutcade.r9.status({J(u)}))||null")
async def ids(w, u): return await w.ev(f"(Nutcade.S.proofs[{J(u)}]||[]).map(p=>p.id)")
async def bal(w, u): return await w.bal(u)
async def count(w, u): return await w.ev(f"(Nutcade.S.proofs[{J(u)}]||[]).length")
async def lines(w, u, note=''): return await w.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(u)}&&(t.note||'').includes({J(note)}))")
async def books(w, u, step, broken):
    l, p = await w.ev(LEDGER + f"({J(u)})")
    if l != p: broken.append((step, u[-4:], l, p))
    return l == p
async def now(w): return await w.ev("Date.now()")


async def checked(w, u, t0, ms=40000):
    """the mint's check-up has run since t0 (page clock)"""
    return await w.until(f"(s=>!!s&&s.at>{t0})((window.Nutcade&&Nutcade.r9&&Nutcade.r9.status({J(u)}))||null) && Nutcade.S.ops.filter(o=>o.mint==={J(u)}).length===0", ms)


async def reopen(w, u, ms=40000, unroute=None):
    """NUTCADE closed and opened again; waits for the mint's check-up. unroute: a held route is removed only once the
    page it held is gone (removing it first could let the held request through a second time)"""
    t0 = await now(w); await w.pg.reload()
    if unroute: await w.pg.unroute(unroute)
    await w.wait(700)
    ok = await checked(w, u, t0, ms); await w.wait(400); return ok


async def mints_line(w, u):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(250)
    return await w.ev(f"(document.querySelector('[data-ks=\"{u}\"]')||{{}}).innerText||''")


async def ask_panel(w, u):
    await w.home(); await w.wait(200)
    return await w.ev(f"(document.querySelector('[data-ksask=\"{u}\"]')||{{}}).innerText||''")


INJECT = """(async([u,n])=>{const w=new CashuLib.Wallet(u,{unit:'sat'}); await w.loadMint(); let all=[];
  for(let left=n;left>0;){const c=Math.min(100,left); const q=await w.createMintQuoteBolt11(c);
    for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,250)); const s=await w.checkMintQuoteBolt11(q.quote); if(s.state==='PAID')break;}
    const ps=await w.mintProofsBolt11(c,q.quote,undefined,{type:'random',denominations:Array(c).fill(1)}); all=all.concat(ps); left-=c;}
  const N=x=>typeof x==='object'&&x&&x.toNumber?x.toNumber():Number(x);
  const coins=all.map(p=>{const o={id:p.id,amount:N(p.amount),secret:p.secret,C:p.C}; if(p.dleq)o.dleq=p.dleq; return o});
  const S=Nutcade.S; S.proofs[u]=(S.proofs[u]||[]).concat(coins);
  S.txs.unshift({id:'inj'+Date.now(),ts:Date.now(),type:'in',method:'ecash',amount:n,mint:u,status:'done',note:'test coins',fee:0});
  localStorage.setItem('nutcade:proofs',JSON.stringify(S.proofs)); localStorage.setItem('nutcade:txs',JSON.stringify(S.txs));
  localStorage.setItem('nutcade:gen',String(+(localStorage.getItem('nutcade:gen')||0)+1)); return coins.length})"""


async def inject(w, u, n):
    """n coins of 1 SAT, made with the library directly (random secrets), written into the wallet with an incoming line.
    A sheet stays open meanwhile, so the regular background check (it skips while a sheet is open) can't act on them
    before the test reopens NUTCADE."""
    await w.ev("Nutcade.openSheet('Test', '<p>test</p>')")
    return await w.ev(INJECT + f"([{J(u)},{n}])")


async def hang_swaps(w, u, after=0, signed=False):
    """the mint's answer to swap number after+1 (and later) never arrives: before the mint gets it, or (signed) after
    the mint has signed it; earlier swaps pass"""
    st = {'n': 0, 'held': [], 'signed': 0}
    async def h(route):
        st['n'] += 1
        if st['n'] <= after:
            try: await route.continue_()
            except Exception: pass
            return
        if signed:
            try: r = await route.fetch(); st['signed'] += 1 if r.status == 200 else 0
            except Exception: pass
        st['held'].append(route)   # (never answered: the page is closed next)
    await w.pg.route(u + '/v1/swap', h)
    return st


async def refuse_swaps(w, u, code=12003, detail='keyset has expired'):
    async def h(route):
        try: await route.fulfill(status=400, content_type='application/json', body=J({'detail': detail, 'code': code}))
        except Exception: pass
    await w.pg.route(u + '/v1/swap', h)


async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)


async def pad(w, pin, root='[data-pinpad]'):
    for k in pin: await w.click(f'{root} [data-k="{k}"]')
    await w.click(f'{root} [data-k=ok]')


async def set_limit_day(w, day):
    await settings(w); await w.click('[data-act=limOpen]'); await w.until("!!document.querySelector('#limDay')", 5000)
    await w.ev(f"(()=>{{const e=document.querySelector('#limDay');e.value={J(str(day))};e.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")
    await w.click('[data-act=limSave]'); await w.wait(500); await w.ev("Nutcade.closeSheet()")


async def restore_json(w, data):
    await settings(w); await w.click('[data-act=restore]'); await w.wait(250); await w.pg.wait_for_selector('#restoreIn', timeout=60000)
    await w.pg.evaluate("v => { const t = document.querySelector('#restoreIn'); t.value = v; t.dispatchEvent(new Event('input', {bubbles: true})) }", data)
    await w.click('[data-act=doRestore]'); await w.until("!document.querySelector('#restoreIn')", 90000); await w.wait(600)
    await w.until("Nutcade.S.ops.length===0&&Nutcade.S.pending.length===0", 60000); await w.wait(1500); await w.ev("Nutcade.closeSheet()")


async def backup(w): return await w.ev("Nutcade.r8.backupData()")


async def section(name, fn):
    only = [x for x in os.environ.get('R9_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    print(f'--- {name}', flush=True)
    try: await fn()
    except Exception as e:
        check(f'{name}: ran to the end', False, repr(e)[:400])


async def main():
    os.makedirs(MDIR, exist_ok=True)
    for u in MINTS: await asyncio.to_thread(start, u, True)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
            broken = []
            await run(b, broken)
            check('round 9: the books add up everywhere (history = balance)', not broken, broken)
            await b.close()
    finally:
        for u in list(procs): await asyncio.to_thread(stop, u)
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', sum(1 for r in results if not r[1]), 'failed')


async def run(b, broken):
    # ======================= a no-fee mint: active, inactive, refresh, automatic off =======================
    async def free():
        w = await fresh(b, FREE); await fund(w, FREE, 1000); await fund(w, FREE, 300)
        await set_limit_day(w, 500)
        tok, e = await w.send_ecash(400, 'r9 limit'); spent0 = await w.ev("Nutcade.r8.spentDay()")
        k0 = active(FREE)[0]; b0 = await bal(w, FREE)
        w.swaps.clear(); ok = await reopen(w, FREE)
        check('active keyset: the check-up runs when NUTCADE opens', ok)
        check('active keyset: nothing is sent to the mint (no swap)', not w.swaps, w.swaps)
        t = await mints_line(w, FREE)
        check('active keyset: the line in Mints says "Nothing to do"', 'Nothing to do' in t, t)
        check('active keyset: no history line', not await lines(w, FREE, 'Keyset check-up'))
        k1 = await rotate(FREE)
        check('test mint: rotated (old keyset inactive, a new one active)', active(FREE) == [k1] and k1 != k0, (k0, k1, active(FREE)))
        w.swaps.clear(); ok = await reopen(w, FREE)
        got = await ids(w, FREE)
        check('inactive keyset, no fee, automatic: every coin moved to the active keyset when NUTCADE opens', ok and got and all(x == k1 for x in got), (ok, set(got), k1))
        check('inactive keyset, no fee: the balance is the same', await bal(w, FREE) == b0, (await bal(w, FREE), b0))
        L1 = await lines(w, FREE, 'Keyset check-up')
        check('inactive keyset, no fee: one history line, fee 0, saying how many coins moved', len(L1) == 1 and L1[0]['fee'] == 0 and re.search(r'\d+ coins? moved', L1[0]['note']), L1)
        t = await mints_line(w, FREE)
        check('inactive keyset: the line in Mints says how many coins moved off an old keyset', re.search(r'\d+ coins? moved off an old keyset', t), t)
        check('inactive keyset: the swap asked the mint for coins of the active keyset only', w.swaps and all(s[0] == FREE and s[3] == [k1] for s in w.swaps), w.swaps)
        check('spending limit: the check-up does not count toward the day', await w.ev("Nutcade.r8.spentDay()") == spent0, (spent0, await w.ev("Nutcade.r8.spentDay()")))
        await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '200'); await w.click('[data-act=doSendEcash]'); await w.wait(1500)
        check('spending limit: still holds after a check-up (200 SAT over what is left is held)', await w.ev("!!document.querySelector('#limitLayer')"))
        await w.ev("document.querySelector('#limitLayer [data-act=limitNo]')?.click(); document.querySelector('#limitLayer')?.remove(); Nutcade.closeSheet()")
        await books(w, FREE, 'free inactive', broken)
        # a mint refresh (the page stays open while the mint rotates)
        k2 = await rotate(FREE)
        await mints_line(w, FREE); await w.click(f'[data-act=refreshMint][data-url="{FREE}"]')
        ok = await w.until(f"(Nutcade.S.proofs[{J(FREE)}]||[]).length>0 && (Nutcade.S.proofs[{J(FREE)}]||[]).every(p=>p.id==={J(k2)})", 30000)
        check('mint refresh: Refresh in Mints runs the check-up (coins moved to the new keys)', ok, (set(await ids(w, FREE)), k2))
        check('mint refresh: balance the same, a second history line', await bal(w, FREE) == b0 and len(await lines(w, FREE, 'Keyset check-up')) == 2)
        await books(w, FREE, 'free refresh', broken)
        # automatic off: asks, even with no fee
        await settings(w)
        check('setting: "Keyset check-up" toggle in Settings, on by default', await w.ev("!!document.querySelector('#p_ksAuto') && document.querySelector('#p_ksAuto').checked"))
        await w.click('#p_ksAuto'); await w.wait(200)
        check('setting: turned off', await w.ev("Nutcade.S.prefs.ksAuto===false"))
        k3 = await rotate(FREE); w.swaps.clear(); ok = await reopen(w, FREE)
        check('automatic off: nothing moved when NUTCADE opens', ok and all(x == k2 for x in await ids(w, FREE)) and not w.swaps, (ok, w.swaps))
        t = await ask_panel(w, FREE)
        check('automatic off: the wallet screen asks once, saying it costs no fee', 'old keyset' in t and 'no fee' in t, t)
        await w.click(f'[data-ksask="{FREE}"] [data-act=ksMove]')
        ok = await w.until(f"(Nutcade.S.proofs[{J(FREE)}]||[]).every(p=>p.id==={J(k3)})", 30000)
        check('automatic off: Move them moves the coins', ok and await bal(w, FREE) == b0)
        check('automatic off: the question is gone once done', not await ask_panel(w, FREE))
        await settings(w); await w.click('#p_ksAuto'); await w.wait(200)
        check('setting: on again', await w.ev("Nutcade.S.prefs.ksAuto!==false"))
        await books(w, FREE, 'free auto off', broken)
        check('no script errors (no-fee mint)', not w.errs, w.errs[:4])
        await w.pg.context.close()
    await section('free', free)

    # ======================= a fee mint: asked once with the fee, the fee is what the mint kept; tidy; languages =======================
    async def fee():
        w = await fresh(b, FEE); await fund(w, FEE, 2500); await fund(w, FEE, 21)
        n = await count(w, FEE); b0 = await bal(w, FEE); k0 = active(FEE)[0]
        k1 = await rotate(FEE); w.swaps.clear(); ok = await reopen(w, FEE)
        check('fee mint: nothing is moved before you agree', ok and all(x == k0 for x in await ids(w, FEE)) and not w.swaps and await bal(w, FEE) == b0, (ok, w.swaps))
        want = math.ceil(n * 100 / 1000)
        t = await ask_panel(w, FEE)
        check(f'fee mint: the wallet screen asks, with the fee ({want} SAT for {n} coins at 100 ppk)', 'old keyset' in t and f'It costs {want} SAT' in t, t)
        check('fee mint: the amount is shown as the language writes it (2,521 SAT)', '2,521 SAT' in t, t)
        for lang, num in (('es', '2.521'), ('pt', '2.521'), ('de', '2.521'), ('fr', '2 521')):
            await settings(w); await w.ev(f"(()=>{{const s=document.querySelector('#p_lang'); s.value={J(lang)}; s.dispatchEvent(new Event('change',{{bubbles:true}}))}})()"); await w.wait(300)
            await w.ev("window.__i18nMiss=new Set()")
            t = await ask_panel(w, FEE); ln = await mints_line(w, FEE)
            miss = await w.ev("[...(window.__i18nMiss||[])].filter(s=>/keyset|coin|fee|check-up|Move|Not now|aside/i.test(s))")
            check(f'{lang}: the question and the Mints line are translated, numbers the {lang} way ({num})', t and ln and 'old keyset' not in t and 'It costs' not in t and 'Keyset check-up' not in ln and num in t and not miss, (t[:200], ln[:160], miss))
        await settings(w); await w.ev("(()=>{const s=document.querySelector('#p_lang'); s.value='en'; s.dispatchEvent(new Event('change',{bubbles:true}))})()"); await w.wait(300)
        await w.home(); await w.click(f'[data-ksask="{FEE}"] [data-act=ksNo]'); await w.wait(300)
        check('fee mint: Not now closes the question', not await ask_panel(w, FEE))
        ok = await reopen(w, FEE)
        check('fee mint: asked once (not asked again when NUTCADE opens again)', ok and not await ask_panel(w, FEE))
        t = await mints_line(w, FEE)
        check('fee mint: the Mints line still offers to move them, with the fee', 'old keyset' in t and f'{want} SAT' in t and await w.ev(f"!!document.querySelector('[data-act=ksMove][data-url=\"{FEE}\"]')"), t)
        spent0 = await w.ev("Nutcade.r8.spentDay()")
        await w.click(f'[data-act=ksMove][data-url="{FEE}"]')
        ok = await w.until(f"(Nutcade.S.proofs[{J(FEE)}]||[]).every(p=>p.id==={J(k1)})", 30000); await w.wait(500)
        drop = b0 - await bal(w, FEE); L1 = await lines(w, FEE, 'Keyset check-up')
        check('fee mint: Move them moves every coin to the new keys', ok)
        check(f'fee mint: the fee is exactly what the mint kept ({want} SAT), on one line', drop == want and len(L1) == 1 and L1[0]['fee'] == drop, (drop, want, L1))
        check('fee mint: the fee does not count toward the spending limit', await w.ev("Nutcade.r8.spentDay()") == spent0)
        t = await mints_line(w, FEE)
        check('fee mint: the Mints line says how many coins moved and the fee', re.search(r'coins? moved off an old keyset', t) and f'Fee {want} SAT' in t, t)
        await books(w, FEE, 'fee move', broken)
        # automatic off on a fee mint: still asks (never moves on its own)
        await settings(w); await w.click('#p_ksAuto'); await w.wait(200)
        k2 = await rotate(FEE); ok = await reopen(w, FEE)
        check('fee mint, automatic off: asks, nothing moved', ok and all(x == k1 for x in await ids(w, FEE)) and 'old keyset' in await ask_panel(w, FEE))
        await settings(w); await w.click('#p_ksAuto'); await w.wait(200); await w.home()
        await w.click(f'[data-ksask="{FEE}"] [data-act=ksMove]'); await w.until(f"(Nutcade.S.proofs[{J(FEE)}]||[]).every(p=>p.id==={J(k2)})", 30000); await w.wait(400)
        # tiny coins on a fee mint: combining them is asked, with its fee
        await inject(w, FEE, 30); ok = await reopen(w, FEE)
        n1 = await count(w, FEE); b1 = await bal(w, FEE); t = await ask_panel(w, FEE)
        small = await w.ev(f"(Nutcade.S.proofs[{J(FEE)}]||[]).filter(p=>p.amount<=8).length"); want = math.ceil(small * 100 / 1000)
        check(f'tidy, fee mint: asks to combine the {small} small coins, with the fee ({want} SAT)', ok and f'{small} small coins' in t and f'It costs {want} SAT' in t, t)
        await w.click(f'[data-ksask="{FEE}"] [data-act=ksMove]'); await w.until(f"(Nutcade.S.proofs[{J(FEE)}]||[]).length<{n1 - 16}", 30000); await w.wait(500)
        Lt = await lines(w, FEE, 'small coins combined')
        check('tidy, fee mint: combined into fewer coins, the fee exactly what the mint kept', await count(w, FEE) < n1 - 16 and len(Lt) == 1 and b1 - await bal(w, FEE) == Lt[0]['fee'] == want, (await count(w, FEE), n1, b1 - await bal(w, FEE), Lt))
        await books(w, FEE, 'fee tidy', broken)
        check('no script errors (fee mint)', not w.errs, w.errs[:4])
        await w.pg.context.close()
    await section('fee', fee)

    # ======================= tiny coins on a no-fee mint: combined on their own =======================
    async def tidy():
        w = await fresh(b, FREE); await fund(w, FREE, 50); await inject(w, FREE, 40)
        n0 = await count(w, FREE); b0 = await bal(w, FREE); ok = await reopen(w, FREE)
        check('tidy, no fee: 40 small coins combined into a few when NUTCADE opens', ok and await count(w, FREE) <= n0 - 16 and await bal(w, FREE) == b0, (n0, await count(w, FREE)))
        L1 = await lines(w, FREE, 'small coins combined')
        check('tidy, no fee: one history line, fee 0', len(L1) == 1 and L1[0]['fee'] == 0, L1)
        t = await mints_line(w, FREE); check('tidy: the Mints line says small coins were combined', 'small coins combined' in t, t)
        n1 = await count(w, FREE); w.swaps.clear(); ok = await reopen(w, FREE)
        check('tidy: done once (the next opening has nothing to do)', ok and await count(w, FREE) == n1 and not w.swaps, w.swaps)
        await books(w, FREE, 'tidy', broken)
        await w.pg.context.close()
    await section('tidy', tidy)

    # ======================= crash before and after the swap =======================
    async def crash():
        w = await fresh(b, FREE); await fund(w, FREE, 500); b0 = await bal(w, FREE)
        k1 = await rotate(FREE)
        st = await hang_swaps(w, FREE)
        await w.pg.reload(); ok = await w.until("Nutcade.S.ops.some(o=>o.follow&&o.follow.k==='keyset')", 30000); await w.wait(500)
        check('crash before the swap reached the mint: the step is written down first', ok)
        ok = await reopen(w, FREE, unroute=FREE + '/v1/swap')
        check('crash before: settled on the next opening, then moved; balance the same', ok and all(x == k1 for x in await ids(w, FREE)) and await bal(w, FREE) == b0, (set(await ids(w, FREE)), await bal(w, FREE), b0))
        check('crash before: one check-up line, no "interrupted step" fee, nothing spent elsewhere', len(await lines(w, FREE, 'Keyset check-up')) == 1 and not await lines(w, FREE, 'interrupted') and not await lines(w, FREE, 'spent elsewhere'))
        await books(w, FREE, 'crash before', broken)
        k2 = await rotate(FREE)
        st = await hang_swaps(w, FREE, signed=True)
        await w.pg.reload(); ok = await w.until(f"!!document.querySelector('body')", 5000)
        for _ in range(120):
            if st['signed']: break
            await w.wait(250)
        check('crash after the mint signed: the mint did the swap, the answer never came', st['signed'] >= 1, st)
        ok = await reopen(w, FREE, unroute=FREE + '/v1/swap')
        check('crash after: the next opening settles it from its record (coins on the new keys, balance the same)', ok and all(x == k2 for x in await ids(w, FREE)) and await bal(w, FREE) == b0, (set(await ids(w, FREE)), await bal(w, FREE), b0))
        L1 = await lines(w, FREE, 'Keyset check-up')
        check('crash after: exactly one more check-up line (written when it settled), fee 0', len(L1) == 2 and all(x['fee'] == 0 for x in L1), L1)
        check('crash after: nothing "recovered", nothing "spent elsewhere", no interrupted-step fee', not await lines(w, FREE, 'Recovered') and not await lines(w, FREE, 'spent elsewhere') and not await lines(w, FREE, 'interrupted'), await w.ev("Nutcade.S.txs.map(t=>[t.note,t.type,t.amount,t.fee,t.status])"))
        await books(w, FREE, 'crash after', broken)
        # the normal recovery flows next to it still work: a token made and claimed back, a deposit
        tok, e = await w.send_ecash(100, 'after the check-up'); check('after a check-up: sending ecash works', tok and not e, e)
        check('after a check-up: a deposit works', await fund(w, FREE, 77))
        await books(w, FREE, 'crash normal flows', broken)
        check('no script errors (crash)', not w.errs, w.errs[:4])
        await w.pg.context.close()
    await section('crash', crash)

    # ======================= a mint taking at most 128 items per request, hundreds of coins =======================
    async def limit128():
        w = await fresh(b, LIM); await fund(w, LIM, 10); await inject(w, LIM, 200)
        n0 = await count(w, LIM); b0 = await bal(w, LIM); w.swaps.clear(); ok = await reopen(w, LIM, 60000)
        big = [s for s in w.swaps if s[1] > 128 or s[2] > 128]
        check('128-item mint: 200 small coins combined in requests of at most 128 coins in and out', ok and len(w.swaps) >= 2 and not big and await count(w, LIM) < n0 - 100 and await bal(w, LIM) == b0, (ok, w.swaps, await count(w, LIM)))
        await books(w, LIM, '128 tidy', broken)
        await inject(w, LIM, 250); b1 = await bal(w, LIM)
        k1 = await rotate(LIM)   # (the sheet inject left open keeps the regular check away from them until the reload)
        w.swaps.clear(); st = await hang_swaps(w, LIM, after=1, signed=True)
        await w.pg.reload()
        for _ in range(240):
            if st['signed']: break
            await w.wait(250)
        check('128-item mint: crash between parts (the first part done, the second signed, its answer lost)', st['n'] >= 2 and st['signed'] >= 1, st)
        w.swaps.clear(); ok = await reopen(w, LIM, 60000, unroute=LIM + '/v1/swap')
        check('128-item mint: after the crash every coin is on the new keys and the balance is the same', ok and all(x == k1 for x in await ids(w, LIM)) and await bal(w, LIM) == b1, (ok, set(await ids(w, LIM)), await bal(w, LIM), b1))
        check('128-item mint: no request over 128 items', not [s for s in w.swaps if s[1] > 128 or s[2] > 128], w.swaps)
        await books(w, LIM, '128 crash between parts', broken)
        check('no script errors (128-item mint)', not w.errs, w.errs[:4])
        await w.pg.context.close()
    await section('limit128', limit128)

    # ======================= expiring, expired-and-refused, dropped keys =======================
    async def expiry():
        soon = int(time.time()) + 3 * 86400
        k1 = await rotate(AUX, '--expiry', soon)
        w = await fresh(b, AUX); await fund(w, AUX, 500); b0 = await bal(w, AUX)
        check('expiring keyset: the coins are on it (the only active keyset)', all(x == k1 for x in await ids(w, AUX)))
        ok = await reopen(w, AUX)
        check('expiring keyset, nowhere to move: nothing to do, nothing moved', ok and all(x == k1 for x in await ids(w, AUX)) and 'Nothing to do' in await mints_line(w, AUX))
        k2 = await rotate(AUX); await keyset_do(AUX, 'activate', k1)
        check('test mint: two active keysets, one of them expiring in 3 days', set(active(AUX)) == {k1, k2}, active(AUX))
        ok = await reopen(w, AUX)
        check('expiring keyset (still active): coins moved to the keyset that does not expire', ok and all(x == k2 for x in await ids(w, AUX)) and await bal(w, AUX) == b0, (set(await ids(w, AUX)), k1, k2))
        await fund(w, AUX, 64)
        check('expiring keyset: new coins are made on the keyset that does not expire', all(x == k2 for x in await ids(w, AUX)), set(await ids(w, AUX)))
        await books(w, AUX, 'expiring', broken)
        # expired and refused: the mint answers 12003 (keyset has expired)
        await keyset_do(AUX, 'deactivate', k1)
        k3 = await rotate(AUX); b0 = await bal(w, AUX); nk = len(await lines(w, AUX, 'Keyset check-up'))
        await refuse_swaps(w, AUX); ok = await reopen(w, AUX)
        aside = await w.ev(f"((Nutcade.r9.status({J(AUX)})||{{}}).aside||[]).reduce((t,p)=>t+p.amount,0)")
        check('expired and refused (12003): the coins are set aside, out of the balance', ok and aside == b0 and await bal(w, AUX) == 0, (aside, b0, await bal(w, AUX)))
        L1 = await lines(w, AUX, 'Set aside')
        check('expired and refused: one history line for them, and no fee', len(L1) == 1 and L1[0]['amount'] == b0 and len(await lines(w, AUX, 'Keyset check-up')) == nk and not [t for t in await lines(w, AUX) if t.get('fee')], L1)
        t = await mints_line(w, AUX)
        check('expired and refused: the Mints line says they are set aside and offered again', 'set aside' in t and 'again' in t, t)
        bk = await backup(w)
        check('expired and refused: the backup holds the coins set aside', all(s in bk for s in await w.ev(f"Nutcade.r9.status({J(AUX)}).aside.map(p=>p.secret)")))
        await books(w, AUX, 'refused', broken)
        await w.pg.unroute(AUX + '/v1/swap')
        await mints_line(w, AUX); await w.click(f'[data-act=refreshMint][data-url="{AUX}"]')
        ok = await w.until(f"(Nutcade.S.proofs[{J(AUX)}]||[]).reduce((t,p)=>t+p.amount,0)=={b0}", 30000)
        check('set aside: the mint takes them again later: back in the balance, on the new keys, with a line', ok and all(x == k3 for x in await ids(w, AUX)) and len(await lines(w, AUX, 'accepts again')) == 1, (await bal(w, AUX), b0))
        await books(w, AUX, 'back', broken)
        # dropped: the mint no longer lists the keyset at all
        k4 = await rotate(AUX); await keyset_do(AUX, 'drop', k3); b0 = await bal(w, AUX)
        check('test mint: the old keyset is gone from its list', k3 not in [k['id'] for k in keysets(AUX)])
        ok = await reopen(w, AUX)
        check('dropped keyset: its coins are set aside with a line, nothing else changes', ok and await bal(w, AUX) == 0 and len(await lines(w, AUX, 'Set aside')) == 2, (await bal(w, AUX), b0))
        await fund(w, AUX, 100); tok, e = await w.send_ecash(50, 'after dropped keys')
        check('dropped keyset: the mint still works for the rest (deposit, send)', tok and not e, e)
        await books(w, AUX, 'dropped', broken)
        check('no script errors (expiry)', not w.errs, w.errs[:4])
        await w.pg.context.close()
    await section('expiry', expiry)

    # ======================= the mint is down =======================
    async def down():
        w = await fresh(b, FREE); await fund(w, FREE, 300); b0 = await bal(w, FREE); kold = set(await ids(w, FREE))
        def off(): stop(FREE); return keyset_cmd(FREE, 'rotate')
        k1 = await asyncio.to_thread(off)
        t0 = await now(w); await w.pg.reload(); await w.wait(9000)
        check('mint down: nothing changes (balance, coins, no line)', await bal(w, FREE) == b0 and set(await ids(w, FREE)) == kold and not await lines(w, FREE, 'Keyset check-up'))
        t = await mints_line(w, FREE)
        check('mint down: no alarm (no "turned down", nothing red about the check-up)', 'turned' not in t and 'set aside' not in t and not await w.ev(f"!!document.querySelector('[data-ks=\"{FREE}\"] .red, [data-ksask]')"), t)
        await asyncio.to_thread(start, FREE)
        await w.click(f'[data-act=refreshMint][data-url="{FREE}"]')
        ok = await w.until(f"(Nutcade.S.proofs[{J(FREE)}]||[]).every(p=>p.id==={J(k1)})", 40000)
        check('mint back: Refresh moves the coins', ok and await bal(w, FREE) == b0)
        await books(w, FREE, 'down', broken)
        await w.pg.context.close()
    await section('down', down)

    # ======================= two devices, one phrase; backups =======================
    async def devices():
        d1 = await fresh(b, FREE); await fund(d1, FREE, 400); b0 = await bal(d1, FREE)
        bk = await backup(d1)
        d2 = await fresh(b); await restore_json(d2, bk)
        check('two devices: the second holds the same coins', await bal(d2, FREE) == b0, await bal(d2, FREE))
        k1 = await rotate(FREE)
        ok = await reopen(d1, FREE)
        check('two devices: the first moves the coins', ok and all(x == k1 for x in await ids(d1, FREE)) and await bal(d1, FREE) == b0)
        ok = await reopen(d2, FREE)
        se = await lines(d2, FREE, 'already spent elsewhere'); fees2 = [t for t in await lines(d2, FREE) if t.get('fee')]
        check('two devices: on the second they are "already spent elsewhere", never a fee', ok and sum(t['amount'] for t in se) == b0 and await bal(d2, FREE) == 0 and not fees2, (se, fees2))
        check('two devices: the second writes no check-up line (it moved nothing)', not await lines(d2, FREE, 'Keyset check-up'))
        t = await mints_line(d2, FREE)
        check('two devices: its Mints line says already spent elsewhere', 'already spent elsewhere' in t, t)
        await books(d2, FREE, 'device 2', broken); await books(d1, FREE, 'device 1', broken)
        # at the same moment
        bk2 = await backup(d1); d3 = await fresh(b); await restore_json(d3, bk2)
        k2 = await rotate(FREE)
        r = await asyncio.gather(reopen(d1, FREE), reopen(d3, FREE))
        await d1.wait(1500); await d3.wait(1500)
        r = r + await asyncio.gather(reopen(d1, FREE), reopen(d3, FREE))   # (whatever one of them saw in flight is settled by the next opening)
        f1 = [t for t in await lines(d1, FREE) if t.get('fee')]; f3 = [t for t in await lines(d3, FREE) if t.get('fee')]
        k_1 = set(await ids(d1, FREE)); k_3 = set(await ids(d3, FREE))
        check('two devices at once: both settle, no fee anywhere, no old coins left', all(r) and not f1 and not f3 and k_1 <= {k2} and k_3 <= {k2}, (r, f1, f3, k_1, k_3))
        check('two devices at once: the books add up on both', await books(d1, FREE, 'race d1', broken) and await books(d3, FREE, 'race d3', broken))
        # a backup taken before the check-up, imported after it: the same wallet changes nothing
        n_l = len(await lines(d1, FREE)); bb = await bal(d1, FREE)
        await restore_json(d1, bk)
        check('backup from before, imported after (same wallet): balance and history unchanged', await bal(d1, FREE) == bb and len(await lines(d1, FREE)) == n_l, (await bal(d1, FREE), bb))
        # ... on a new device: the old coins are gone (spent elsewhere), the phrase finds the moved ones
        d4 = await fresh(b); await restore_json(d4, bk)
        check('backup from before, new device: the old coins count as spent elsewhere (no fee)', await bal(d4, FREE) == 0 and not [t for t in await lines(d4, FREE) if t.get('fee')])
        await settings(d4); await d4.click('[data-act=findLost]'); await d4.until("!document.querySelector('[data-act=findLost] .spinner')", 90000); await d4.wait(800)
        # (the 400 SAT exist once at the mint, unspent, held by whichever phone won the race above; the other one counts them
        # spent elsewhere. The 12 words find them either way.)
        check('backup from before, new device: "Find lost ecash" finds the moved coins', await bal(d4, FREE) == b0, (await bal(d4, FREE), b0, bb))
        await books(d4, FREE, 'new device', broken)
        for x in (d1, d2, d3, d4): await x.pg.context.close()
        # a backup holding an open check-up step
        d5 = await fresh(b, FREE); await fund(d5, FREE, 300)
        k3 = await rotate(FREE)
        st = await hang_swaps(d5, FREE, signed=True); await d5.pg.reload()
        for _ in range(120):
            if st['signed']: break
            await d5.wait(250)
        bko = await backup(d5); await d5.pg.context.close()
        check('backup during an open check-up step: the backup holds the step', '"keyset"' in bko and st['signed'] >= 1)
        d6 = await fresh(b); await restore_json(d6, bko); await d6.until(f"(Nutcade.S.proofs[{J(FREE)}]||[]).reduce((t,p)=>t+p.amount,0)>=300", 40000)
        check('backup with the open step, imported on a new device: settled there, the coins on the new keys', await bal(d6, FREE) == 300 and all(x == k3 for x in await ids(d6, FREE)), (await bal(d6, FREE), set(await ids(d6, FREE))))
        await books(d6, FREE, 'open step imported', broken)
        await d6.pg.context.close()
    await section('devices', devices)

    # ======================= the duress PIN's wallet =======================
    async def decoy():
        d = await fresh(b, FREE); await fund(d, FREE, 1000)
        await settings(d); await d.click('[data-act=pinSet]'); await d.wait(200); await pad(d, PIN); await d.wait(300); await pad(d, PIN)
        await d.until("Nutcade.vault.on && Nutcade.vault.open", 20000); await d.wait(500); await d.ev("Nutcade.closeSheet()")
        await settings(d); await d.click('[data-act=duressOpen]'); await d.wait(250); await pad(d, PIN); await d.wait(900); await pad(d, DPIN); await d.wait(300); await pad(d, DPIN)
        await d.until("!!document.querySelector('#duressAmt')", 8000); await d.fill('#duressAmt', '300'); await d.click('[data-act=duressMake]'); await d.until("/READY/.test(document.body.innerText)", 30000); await d.ev("Nutcade.closeSheet()")
        rb = await bal(d, FREE)
        k1 = await rotate(FREE)
        await d.pg.reload(); await d.until("!!document.querySelector('[data-pinpad]')", 8000)
        real_ct = await d.ev("JSON.parse(localStorage.getItem('nutcade:vault')).data.ct")
        t0 = await now(d); await pad(d, DPIN); await d.until("Nutcade.vault.open", 20000)
        ok = await checked(d, FREE, t0)
        check('duress wallet: its own coins are moved to the new keys', ok and await bal(d, FREE) == 300 and all(x == k1 for x in await ids(d, FREE)), (await bal(d, FREE), set(await ids(d, FREE))))
        check('duress wallet: its own check-up line', len(await lines(d, FREE, 'Keyset check-up')) == 1)
        check("duress wallet: the real wallet's part of the vault is untouched", await d.ev("JSON.parse(localStorage.getItem('nutcade:vault')).data.ct") == real_ct)
        await books(d, FREE, 'decoy', broken)
        await d.pg.reload(); await d.until("!!document.querySelector('[data-pinpad]')", 8000); t0 = await now(d); await pad(d, PIN); await d.until("Nutcade.vault.open", 20000)
        ok = await checked(d, FREE, t0)
        check('real wallet: its coins are moved too when it opens', ok and await bal(d, FREE) == rb and all(x == k1 for x in await ids(d, FREE)), (await bal(d, FREE), rb))
        check('real wallet: nothing spent elsewhere, one check-up line', not await lines(d, FREE, 'spent elsewhere') and len(await lines(d, FREE, 'Keyset check-up')) == 1)
        await books(d, FREE, 'real', broken)
        check('no script errors (duress)', not d.errs, d.errs[:4])
        await d.pg.context.close()
    await section('decoy', decoy)

    async def journal():
        await journal_followups(b, broken)
    await section('journal', journal)

    async def busy():
        await busy_mint(b, broken)
    await section('busy', busy)

    async def race():
        await deposit_race(b, broken)
    await section('race', race)

    async def stale():
        await stale_busy(b, broken)
    await section('stale', stale)


# ---------------- 1.13.1 journal follow-ups (steps whose request reaches the mint late) ----------------
def post_swap(u, body):
    try:
        q = urllib.request.Request(u + '/v1/swap', data=body.encode(), headers={'Content-Type': 'application/json'})
        return urllib.request.urlopen(q, timeout=20).status
    except urllib.error.HTTPError as e: return e.code
def body_kept(body): d = json.loads(body); return sum(int(p['amount']) for p in d['inputs']) - sum(int(o['amount']) for o in d['outputs'])


async def drop_send(w, u, amt):
    """a send whose request never reaches the mint, and NUTCADE is killed meanwhile; then opened again (the step is
    settled with nothing signed and waits aside). Returns the request, to be delivered to the mint late."""
    got = {}
    async def h(route): got.setdefault('body', route.request.post_data); got.setdefault('route', route)   # (held: never forwarded)
    await w.ctx.route(u + '/v1/swap', h)
    await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', str(amt)); await w.click('[data-act=doSendEcash]')
    for _ in range(120):
        if 'body' in got: break
        await w.wait(250)
    await w.wait(400)
    try: await got['route'].abort()   # (aborted before the tab is killed, or the browser may still deliver it)
    except Exception: pass
    await w.pg.close(run_before_unload=False); await w.ctx.unroute(u + '/v1/swap', h)
    pg = await w.ctx.new_page(); await attach(w, pg); await pg.goto(URL); await pg.wait_for_timeout(1500)
    await w.until("Nutcade.S.ops.length===0", 60000); await w.wait(500)
    return got.get('body')


async def oplate(w): return await w.ev("(Nutcade.S.oplate||[]).map(o=>({id:o.id,ins:o.inputs,lateAt:o.lateAt}))")


async def journal_followups(b, broken):
    # a) near the 24 h end: a waiting step whose request the mint signs in the last minutes before it is a day old,
    #    with NUTCADE left open: it is checked once more before it is dropped, and settled as itself
    w = await fresh(b, FREE); await fund(w, FREE, 2000); await fund(w, FREE, 345); b0 = await bal(w, FREE)
    body = await drop_send(w, FREE, 600); ol = await oplate(w)
    check('24 h end: the interrupted send waits aside (nothing signed yet)', len(ol) == 1 and body, ol)
    # its record is made 23 h 59 min 15 s old, and NUTCADE opens again (that check finds nothing yet)
    await w.ev("(()=>{for(const o of Nutcade.S.oplate)o.lateAt=Date.now()-(24*3600e3-45e3); localStorage.setItem('nutcade:oplate',JSON.stringify(Nutcade.S.oplate)); localStorage.setItem('nutcade:gen',String(+(localStorage.getItem('nutcade:gen')||0)+1))})()")
    await w.pg.reload(); await w.wait(4000); await w.home()
    check('24 h end: still waiting after the opening check', len(await oplate(w)) == 1)
    st = await asyncio.to_thread(post_swap, FREE, body)
    ins = ol[0]['ins'] if ol else []
    ok = await w.until(f"(Nutcade.S.oplate||[]).length===0 && Nutcade.S.ops.length===0 && Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)==={b0 - body_kept(body)} && !Object.values(Nutcade.S.proofs).flat().some(p=>{J(ins)}.includes(p.secret))", 150000)
    se = await lines(w, FREE, 'spent elsewhere')
    check('24 h end: the request the mint signed in the last minute is settled as itself while NUTCADE stays open (one last check before the record is dropped)', st == 200 and ok and not se, (st, await bal(w, FREE), b0 - body_kept(body), await oplate(w), se))
    check('24 h end: every coin left in the balance is unspent', await w.ev(f"(async()=>{{const w=new CashuLib.Wallet({J(FREE)},{{unit:'sat'}}); await w.loadMint(); const ps=Nutcade.S.proofs[{J(FREE)}]||[]; return (await w.checkProofsStates(ps)).every(s=>s.state==='UNSPENT')}})()"))
    await books(w, FREE, 'journal 24h', broken); await w.pg.context.close()
    # b) two waiting steps on the same single coin; the NEWER one's request is the one the mint signs late
    w = await fresh(b, FREE); await fund(w, FREE, 1024); b0 = await bal(w, FREE)
    body1 = await drop_send(w, FREE, 300); body2 = await drop_send(w, FREE, 500); ol = await oplate(w)
    check('shared coin: two waiting steps on the same coin', len(ol) == 2 and set(ol[0]['ins']) == set(ol[1]['ins']), ol)
    st = await asyncio.to_thread(post_swap, FREE, body2)
    await w.pg.reload(); await w.wait(1500); await w.until("Nutcade.S.ops.length===0 && (Nutcade.S.oplate||[]).length===0", 60000); await w.wait(1000)
    await w.pg.reload(); await w.wait(1500); await w.until("Nutcade.S.ops.length===0", 60000); await w.wait(1000)
    L = await w.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(FREE)}).map(t=>[t.note,t.type,t.amount,t.fee])")
    check(f'shared coin: balance exact ({b0 - body_kept(body2)})', st == 200 and await bal(w, FREE) == b0 - body_kept(body2), (st, await bal(w, FREE)))
    check('shared coin: the step the mint signed is booked as itself: no "spent elsewhere" + "Recovered" pair', not await lines(w, FREE, 'spent elsewhere') and not await lines(w, FREE, 'Recovered'), L)
    await books(w, FREE, 'journal shared', broken)
    check('no script errors (journal follow-ups)', not w.errs, w.errs[:4]); await w.pg.context.close()


# ---------------- the check-up never runs beside a deposit being collected (1.14.1) ----------------
LEGACY = """(async([U,amt])=>{ const S=Nutcade.S; const ws=new CashuLib.Wallet(U,{unit:'sat',bip39seed:CashuLib.mnemonicToSeedSync(S.seed.mnemonic),counterInit:{...S.counters}}); await ws.loadMint();
  const q=await ws.createMintQuoteBolt11(amt); const id='legacy'+Date.now();
  S.txs.unshift({id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'ln',amount:amt,mint:U,quote:q.quote,request:q.request});
  S.quotes.push({kind:'bolt11',quote:q.quote,request:q.request,amount:amt,mint:U,txId:id}); window.__legacy=id;
  localStorage.setItem('nutcade:txs',JSON.stringify(S.txs)); localStorage.setItem('nutcade:quotes',JSON.stringify(S.quotes));   // (as the app would have written it)
  const c0=JSON.stringify(S.counters); await Nutcade.r9.check(U,{startup:true}).catch(()=>{}); const c1=JSON.stringify(S.counters);   // (the check-up, forced at this very moment)
  await new Promise(r=>setTimeout(r,1200));
  try { await ws.mintProofsBolt11(amt,q.quote); } catch (e) { if (!/already (signed|issued)|issued|11003|20002|20003/i.test(String(e&&e.message||e))) throw e; }
  return c0===c1 })"""


async def busy_mint(b, broken):
    u = FREE; w = await fresh(b, u); await fund(w, u, 3000); await inject(w, u, 30)   # (30 tiny coins: a check-up would combine them; the sheet inject leaves open keeps the regular check away)
    n0 = await count(w, u)
    # a deposit whose answer was lost (the mint signed it at the counters on its record), and whose recovery fails for now
    async def lost(route):
        try: await route.fetch()
        except Exception: pass
        try: await route.abort()
        except Exception: pass
    async def fail(route):
        try: await route.fulfill(status=500, headers={'Access-Control-Allow-Origin': '*'}, content_type='application/json', body='{"detail":"test failure"}')
        except Exception: pass
    await w.pg.route(u + '/v1/mint/bolt11', lost); await w.pg.route(u + '/v1/restore', fail)
    await w.ev("Nutcade.closeSheet()"); await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
    await w.fill('#amtIn', '640'); await w.click('[data-act=doLnInvoice]')
    ok = await w.until(f"Nutcade.S.quotes.some(q=>q.mint==={J(u)}&&q.amount==640&&q.ctr)", 30000); await w.wait(1500)
    c0 = await w.ev("JSON.stringify(Nutcade.S.counters)"); w.swaps.clear(); L0 = len(await lines(w, u))
    await w.ev(f"Nutcade.r9.check({J(u)},{{startup:true}})"); await w.wait(500)
    check('busy mint: a deposit being collected there (its answer lost, its recovery failing for now) and a check-up at that moment: no swap, no counter taken, nothing booked', ok and not w.swaps and await w.ev("JSON.stringify(Nutcade.S.counters)") == c0 and await count(w, u) == n0 and len(await lines(w, u)) == L0, (ok, w.swaps, await count(w, u), n0))
    await w.pg.unroute(u + '/v1/restore'); await w.pg.unroute(u + '/v1/mint/bolt11')
    ok = await w.until(f"Nutcade.S.txs.some(t=>t.type==='in'&&t.method==='ln'&&t.amount===640&&t.status==='done'&&t.mint==={J(u)}) && !Nutcade.S.quotes.some(q=>q.amount==640)", 90000)
    check('busy mint: the deposit is then credited to itself (640 SAT), no "Recovered" line, nothing at 0', ok and not await lines(w, u, 'Recovered') and not await w.ev("Nutcade.S.txs.some(t=>t.type==='in'&&t.method==='ln'&&t.status==='done'&&t.amount===0)"))
    await w.ev("Nutcade.closeSheet(); Nutcade.openSheet('Test','<p>x</p>')"); await w.ev(f"Nutcade.r9.check({J(u)},{{startup:true}})"); await w.wait(500)
    check('busy mint: once it is settled, the check-up runs (the small coins combined)', await count(w, u) < n0 - 16 and len(await lines(w, u, 'small coins combined')) == 1, await count(w, u))
    await books(w, u, 'busy deposit', broken)
    # the r7 case: a deposit from before 1.12 (no counters on record) issued at the wallet's next counters, the check-up
    # forced at the moment it is waiting; its recovery's first restore fails
    await inject(w, u, 30); n1 = await count(w, u)
    left = {'n': 1}
    async def once(route):
        if left['n'] > 0:
            left['n'] -= 1
            try: await route.fulfill(status=500, headers={'Access-Control-Allow-Origin': '*'}, content_type='application/json', body='{"detail":"test failure"}')
            except Exception: pass
        else:
            try: await route.continue_()
            except Exception: pass
    await w.pg.route(u + '/v1/restore', once); w.swaps.clear()
    same = await w.ev(LEGACY + f"([{J(u)},640])")
    ok = await w.until("(Nutcade.S.txs.find(t=>t.id===window.__legacy)||{}).status==='done'", 60000); await w.wait(1000)
    ct = await w.ev("Nutcade.S.txs.find(t=>t.id===window.__legacy)")
    check('busy mint (r7 case): the check-up forced while the old-style deposit waits takes no counter and swaps nothing', same and not [s for s in w.swaps if s[1] >= 24], (same, w.swaps))
    check('busy mint (r7 case): the deposit is credited to itself, 640 SAT, no "Recovered" line', ok and ct and ct['amount'] == 640 and not await lines(w, u, 'Recovered'), ct)
    await w.pg.unroute(u + '/v1/restore')
    await books(w, u, 'busy legacy', broken)
    check('no script errors (busy mint)', not w.errs, w.errs[:4]); await w.pg.context.close()


# ---------------- a deposit's request refused while another copy of it is at work at the mint (1.14.1) ----------------
CORS = {'Access-Control-Allow-Origin': '*'}
def post_raw(u, path, body):
    try:
        q = urllib.request.Request(u + path, data=body.encode(), headers={'Content-Type': 'application/json'})
        r = urllib.request.urlopen(q, timeout=90); return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def qstate(u, qid):
    try: return json.loads(urllib.request.urlopen(f'{u}/v1/mint/quote/bolt11/{qid}', timeout=10).read())['state']
    except Exception: return None
def code_of(text):
    try: return json.loads(text).get('code')
    except Exception: return None
# (writes what a test put into the wallet, as the app would have: NUTCADE reads it back before its next step)
KEEP = "for (const k of ['txs','quotes','ops','proofs']) localStorage.setItem('nutcade:'+k, JSON.stringify(Nutcade.S[k])); localStorage.setItem('nutcade:gen', String(+(localStorage.getItem('nutcade:gen')||0)+1));"
DEP_LINE = """(u=>Nutcade.S.txs.filter(t=>t.mint===u&&t.type==='in'&&t.method==='ln'&&t.amount!==1000).map(t=>({status:t.status,amount:t.amount,note:t.note})))"""
DEP_REC = """(u=>Nutcade.S.quotes.filter(q=>q.mint===u).map(q=>({ctr:q.ctr||null,was:q.was||null,state:q.state||null})))"""
TAGS = {'pending': '"already pending" (20005), the mint says PENDING', 'store': '"outputs are pending" (11004), the mint says PENDING',
        'nostate': '"already pending", then the look at the quote fails', 'signed': '"already signed" (11003), the mint says ISSUED',
        'lost': 'its answer lost, asked again with new counters, the lost request signed late', 'paid': 'refused, the mint says PAID',
        'unpaid': 'refused, the mint says UNPAID'}


def race_routes(u, st, mode):
    """the page's mint requests for the deposit (post) and its looks at the quote (look), for one case"""
    async def answer(route):
        r = await route.fetch(); st['resp'].append((r.status, code_of(await r.text()))); await route.fulfill(response=r)
    async def post(route):
        if route.request.method != 'POST': await route.continue_(); return
        body = route.request.post_data; st['bodies'].append(body); first = len(st['bodies']) == 1
        st['qid'] = st['qid'] or json.loads(body)['quote']; qid = st['qid']
        if first and mode in ('pending', 'store', 'nostate'):
            hp = os.path.join(HOLD, 'mint-' + qid); open(hp, 'w').write('store' if mode == 'store' else 'pending')
            st['other'] = asyncio.ensure_future(asyncio.to_thread(post_raw, u, '/v1/mint/bolt11', body))   # (the other copy: held at the mint)
            for _ in range(400):
                if os.path.exists(hp + '.held'): break
                await asyncio.sleep(0.05)
            st['held'] = os.path.exists(hp + '.held') and await asyncio.to_thread(qstate, u, qid) == 'PENDING'
            if mode == 'nostate': st['arm'] = 'fail'   # (and the app's look at the quote right after the refusal fails)
            await answer(route); st['done1'] = True; return
        if first and mode == 'signed':   # the other copy got there first and was signed: the app's copy is "already signed"
            st['other_now'] = await asyncio.to_thread(post_raw, u, '/v1/mint/bolt11', body)
            await answer(route); st['done1'] = True; return
        if mode == 'lost':
            if body == st['bodies'][0]:   # its answer is lost (and the library's resends of it too)
                st['done1'] = True
                try: await route.abort()
                except Exception: pass
                return
            if 'late' not in st:   # the app asks again, with new counters; the lost request reaches the mint first, late
                st['late'] = await asyncio.to_thread(post_raw, u, '/v1/mint/bolt11', st['bodies'][0])
                await answer(route); return
        if first and mode in ('paid', 'unpaid'):   # turned down for another reason: nothing signed (the mint says PAID, or UNPAID)
            if mode == 'unpaid': st['arm'] = 'unpaid'
            st['done1'] = True
            await route.fulfill(status=400, headers=CORS, content_type='application/json', body=J({'detail': 'test refusal', 'code': 20003})); return
        await route.continue_()
    async def look(route):
        a = st['arm']
        if route.request.method == 'GET' and a and st['qid'] and route.request.url.endswith(st['qid']):
            st['arm'] = None
            if a == 'fail':
                await route.fulfill(status=500, headers=CORS, content_type='application/json', body='{"detail":"test failure"}'); return
            r = await route.fetch(); d = json.loads(await r.text()); d['state'] = 'UNPAID'
            await route.fulfill(status=200, headers=CORS, content_type='application/json', body=J(d)); return
        await route.continue_()
    return post, look


async def deposit_race(b, broken):
    """A 640 SAT deposit made with Receive. Its own mint request is turned down while an identical copy of that very
    request (the library's resend of a request whose answer was lost, or a second copy of it) is at work at the mint,
    or has been signed already. The overlap is forced, not timed: the copy is held at the mint (tests/stub) until the
    app has had its answer. In every case the deposit is credited in full, to itself, with no line at 0."""
    u = FREE; os.makedirs(HOLD, exist_ok=True)
    for mode in [m for m in os.environ.get('R9_RACE', 'pending,store,nostate,signed,lost,paid,unpaid').split(',') if m]:
        w = await fresh(b, u); await fund(w, u, 1000); b0 = await bal(w, u)
        st = {'bodies': [], 'resp': [], 'arm': None, 'qid': None, 'other': None, 'done1': False}
        post, look = race_routes(u, st, mode)
        await w.pg.route(u + '/v1/mint/bolt11', post); await w.pg.route(u + '/v1/mint/quote/bolt11/*', look)
        await w.home(); await w.click('[data-act=receive]'); await w.wait(150)
        if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
        await w.fill('#amtIn', '640'); await w.click('[data-act=doLnInvoice]')
        for _ in range(240):
            if st['done1']: break
            await w.wait(250)
        await w.wait(2500)   # (the app has had the answer and looked at the quote)
        mid = dict(line=await w.ev(DEP_LINE + f"({J(u)})"), rec=await w.ev(DEP_REC + f"({J(u)})"))
        tag = TAGS[mode]
        if mode in ('pending', 'store', 'nostate'):
            want = {'pending': 20005, 'store': 11004, 'nostate': 20005}[mode]
            check(f'deposit race ({tag}): the other copy is held at the mint and the app is refused with {want}', st.get('held') and st['resp'] and st['resp'][0][1] == want, (st.get('held'), st['resp']))
            check(f'deposit race ({tag}): the counters stay on the record and the deposit waits (not closed)', mid['rec'] and mid['rec'][0]['ctr'] and mid['line'] and mid['line'][0]['status'] == 'pending', mid)
            try: os.remove(os.path.join(HOLD, 'mint-' + st['qid']))   # the other copy goes on: signed at those very counters
            except Exception: pass
            o = await st['other'] if st['other'] else None
            check(f'deposit race ({tag}): the other copy is then signed (the mint says ISSUED)', o and o[0] == 200 and await asyncio.to_thread(qstate, u, st['qid']) == 'ISSUED', o and o[0])
        elif mode == 'signed':
            check(f'deposit race ({tag}): the other copy was signed and the app is refused with 11003', st.get('other_now', [0])[0] == 200 and st['resp'] and st['resp'][0][1] == 11003, (st.get('other_now', [0])[0], st['resp']))
        elif mode == 'lost':
            for _ in range(120):
                if 'late' in st and st['resp']: break
                await w.wait(250)
            check(f'deposit race ({tag}): the late copy is signed, the new request refused', st.get('late', [0])[0] == 200 and st['resp'] and st['resp'][0][0] == 400, (st.get('late', [0])[0], st['resp']))
        ok = await w.until(f"Nutcade.S.txs.some(t=>t.mint==={J(u)}&&t.type==='in'&&t.method==='ln'&&t.status==='done'&&t.amount===640) && !Nutcade.S.quotes.some(q=>q.mint==={J(u)})", 60000)
        await w.wait(500)
        end = dict(line=await w.ev(DEP_LINE + f"({J(u)})"), rec=await w.ev(DEP_REC + f"({J(u)})"), bal=await bal(w, u))
        if mode in ('paid', 'unpaid'):
            two = len(st['bodies']) >= 2 and json.loads(st['bodies'][0])['outputs'] != json.loads(st['bodies'][1])['outputs']
            check(f'deposit race ({tag}): nothing was signed at the first counters, so it is asked again with new ones', two, len(st['bodies']))
        check(f'deposit race ({tag}): the deposit is credited in full to itself (640 SAT), never closed at 0', ok and end['bal'] == b0 + 640 and [l['amount'] for l in end['line']] == [640], end)
        check(f'deposit race ({tag}): no "Recovered" line', not await lines(w, u, 'Recovered'), await lines(w, u, 'Recovered'))
        await w.pg.unroute(u + '/v1/mint/bolt11'); await w.pg.unroute(u + '/v1/mint/quote/bolt11/*')
        await books(w, u, 'race ' + mode, broken)
        check(f'no script errors (deposit race, {mode})', not w.errs, w.errs[:4]); await w.pg.context.close()
    if os.environ.get('R9_RACE'): return
    # a deposit step without coins going in (as an on-chain deposit is): its answer was "already pending" (or never came)
    # and nothing is at its counters yet. It waits; once the other copy is signed there, it is credited to its line.
    w = await fresh(b, u); await fund(w, u, 1000); b0 = await bal(w, u)
    await w.ev(f"""(async([U])=>{{ const S=Nutcade.S; const kid=(await (await fetch(U+'/v1/keysets')).json()).keysets.find(k=>k.active&&k.unit==='sat').id;
      const start=(S.counters[kid]||0)+500, id='dep'+Date.now();
      S.txs.unshift({{id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'onchain',amount:0,mint:U,quote:'q-'+id,request:'bc1qtest'}});
      S.ops.push({{id:'op'+id,kind:'receive',mint:U,inputs:[],amount:640,note:'',locked:false,extra:false,txId:id,tx:null,follow:null,own:null,created:Date.now(),ctr:[{{id:kid,start,n:2}}],outs:[],refused:1,pendRef:1,dep:1}});
      {KEEP} window.__dep={{id,op:'op'+id,kid,start}}; window.dispatchEvent(new Event('online')); }})([{J(u)}])""")
    await w.wait(4000)
    waiting = await w.ev("Nutcade.S.ops.some(o=>o.id===window.__dep.op) && (Nutcade.S.txs.find(t=>t.id===window.__dep.id)||{}).status==='pending'")
    check('deposit step ("already pending", nothing at its counters yet): it waits, not closed with nothing', waiting)
    await w.ev(f"""(async([U])=>{{ const S=Nutcade.S, d=window.__dep; const ws=new CashuLib.Wallet(U,{{unit:'sat',bip39seed:CashuLib.mnemonicToSeedSync(S.seed.mnemonic),counterInit:{{[d.kid]:d.start}}}}); await ws.loadMint();
      const q=await ws.createMintQuoteBolt11(640); for(let i=0;i<60;i++){{await new Promise(r=>setTimeout(r,250)); if((await ws.checkMintQuoteBolt11(q.quote)).state==='PAID')break;}}
      await ws.mintProofsBolt11(640,q.quote,{{keysetId:d.kid}}); window.dispatchEvent(new Event('online')); }})([{J(u)}])""")
    ok = await w.until("!Nutcade.S.ops.some(o=>o.id===window.__dep.op) && (Nutcade.S.txs.find(t=>t.id===window.__dep.id)||{}).status==='done'", 90000)
    t = await w.ev("Nutcade.S.txs.find(t=>t.id===window.__dep.id)")
    check('deposit step: once the other copy is signed at its counters, the line gets exactly those 640 SAT, no "Recovered" line', ok and t and t['amount'] == 640 and await bal(w, u) == b0 + 640 and not await lines(w, u, 'Recovered'), (t, await bal(w, u)))
    await books(w, u, 'race deposit step', broken)
    check('no script errors (deposit step)', not w.errs, w.errs[:4]); await w.pg.context.close()
    # a send refused "proofs are pending" (another copy of it is at work at the mint), that copy signed after the step was
    # settled with nothing: the step waits aside and is booked as itself, never "spent elsewhere"
    w = await fresh(b, u); await fund(w, u, 2000); await fund(w, u, 345); b0 = await bal(w, u)
    got = {}
    async def h(route):
        if 'body' not in got:
            got['body'] = route.request.post_data
            await route.fulfill(status=400, headers=CORS, content_type='application/json', body=J({'detail': 'proofs are pending', 'code': 11002})); return
        await route.continue_()
    await w.pg.route(u + '/v1/swap', h)
    await w.home(); await w.click('[data-act=send]'); await w.wait(150); await w.fill('#amtIn', '600'); await w.click('[data-act=doSendEcash]')
    for _ in range(120):
        if 'body' in got: break
        await w.wait(250)
    await w.until("Nutcade.S.ops.length===0", 30000); await w.wait(1500); await w.pg.unroute(u + '/v1/swap', h)
    ol = await oplate(w)
    check('send refused "proofs are pending": the step waits aside (its copy may still be signed)', got.get('body') and len(ol) == 1, ol)
    stc = await asyncio.to_thread(post_swap, u, got['body']) if got.get('body') else None
    await w.ev("Nutcade.closeSheet()")
    ins = ol[0]['ins'] if ol else []
    want = b0 - body_kept(got['body']) if got.get('body') else -1
    ok = await w.until(f"(Nutcade.S.oplate||[]).length===0 && Nutcade.S.ops.length===0 && Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)==={want} && !Object.values(Nutcade.S.proofs).flat().some(p=>{J(ins)}.includes(p.secret))", 150000)
    check('send refused "proofs are pending", its copy signed: booked as itself (balance exact), no "spent elsewhere" line', stc == 200 and ok and not await lines(w, u, 'spent elsewhere'), (stc, await bal(w, u), want, await lines(w, u, 'spent elsewhere')))
    await books(w, u, 'race send pending', broken)
    check('no script errors (send pending)', not w.errs, w.errs[:4]); await w.pg.context.close()


# ---------------- the check-up is never skipped for good (1.14.1) ----------------
async def stale_busy(b, broken):
    """A deposit record that looks like one being collected (one from before 1.12, one last seen PAID, one with its
    counters kept while the mint said PENDING) keeps the check-up away while the regular check still looks at it (its
    line under 14 days old); one older than that never does. And "Move them" never says done when it waited."""
    u = FREE; w = await fresh(b, u); await fund(w, u, 1000)
    for kind, extra in (('from before 1.12', ''), ('last seen PAID', ",rec:1,state:'PAID'"), ('counters kept, PENDING', ",rec:1,state:'PENDING',ctr:{id:'00',start:900,n:2}")):
        await inject(w, u, 30); n0 = await count(w, u)
        await w.ev(f"""(()=>{{const S=Nutcade.S, id='old'+Date.now();
          S.txs.push({{id,ts:Date.now()-60e3,note:'',status:'pending',fee:0,type:'in',method:'ln',amount:100,mint:{J(u)},quote:'q-'+id,request:'lnbc1test'}});
          S.quotes.push({{kind:'bolt11',quote:'q-'+id,request:'lnbc1test',amount:100,mint:{J(u)},txId:id{extra}}}); {KEEP} window.__old=id;}})()""")
        await w.ev(f"Nutcade.r9.check({J(u)},{{startup:true}})"); await w.wait(500)
        check(f'check-up beside a deposit ({kind}) under 14 days old: it waits (nothing combined)', await count(w, u) == n0, (await count(w, u), n0))
        await w.ev("(()=>{const t=Nutcade.S.txs.find(t=>t.id===window.__old); t.ts=Date.now()-15*86400e3; " + KEEP + "})()")
        await w.ev(f"Nutcade.r9.check({J(u)},{{startup:true}})"); await w.wait(500)
        check(f'check-up beside a deposit ({kind}) over 14 days old: it runs (the small coins combined)', await count(w, u) < n0 - 16, (await count(w, u), n0, await status(w, u)))
        await w.ev("Nutcade.S.quotes=Nutcade.S.quotes.filter(q=>q.txId!==window.__old); Nutcade.S.txs=Nutcade.S.txs.filter(t=>t.id!==window.__old); " + KEEP)
        await books(w, u, 'stale ' + kind, broken)
    # "Move them" while something is still being settled at the mint
    await settings(w); await w.click('#p_ksAuto'); await w.wait(200)
    await inject(w, u, 30); n0 = await count(w, u)
    await w.ev(f"Nutcade.r9.check({J(u)},{{startup:true}})"); await w.wait(500)
    t = await ask_panel(w, u)
    check('Move them: asked (automatic off)', await w.ev(f"!!document.querySelector('[data-ksask=\"{u}\"] [data-act=ksMove]')"), t)
    await w.ev(f"""(()=>{{const S=Nutcade.S, id='new'+Date.now();
      S.txs.push({{id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'ln',amount:100,mint:{J(u)},quote:'q-'+id,request:'lnbc1test'}});
      S.quotes.push({{kind:'bolt11',quote:'q-'+id,request:'lnbc1test',amount:100,mint:{J(u)},txId:id,rec:1}}); {KEEP} window.__new=id;}})()""")
    await w.ev("document.querySelector('#toast')&&(document.querySelector('#toast').hidden=true)")
    await w.click(f'[data-ksask="{u}"] [data-act=ksMove]'); await w.until("!!document.querySelector('#toast:not([hidden])')", 10000); tt = await w.toast()
    check('Move them while an invoice there is under an hour old: the toast says it runs at the next check, not "done"', 'next check' in tt and 'done' not in tt.lower() and await count(w, u) == n0, (tt, await count(w, u), n0))
    await w.ev("Nutcade.S.quotes=Nutcade.S.quotes.filter(q=>q.txId!==window.__new); Nutcade.S.txs=Nutcade.S.txs.filter(t=>t.id!==window.__new); " + KEEP)
    await w.ev("document.querySelector('#toast')&&(document.querySelector('#toast').hidden=true)")
    await ask_panel(w, u); await w.click(f'[data-ksask="{u}"] [data-act=ksMove]'); await w.until("!!document.querySelector('#toast:not([hidden])')", 10000); tt = await w.toast()
    check('Move them once nothing is open there: "Keyset check-up done", the coins combined', 'Keyset check-up done' in tt and await count(w, u) < n0 - 16, (tt, await count(w, u)))
    await settings(w); await w.click('#p_ksAuto'); await w.wait(200)
    await books(w, u, 'stale move', broken)
    check('no script errors (stale)', not w.errs, w.errs[:4]); await w.pg.context.close()


if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0 if results and all(r[1] for r in results) else 1)
