"""Mint login (1.33.0): NUT-21 clear auth (an OpenID Connect login) and NUT-22 blind auth (blind auth tokens, "BATs").

Uses the auth test mint 3347 (start_mints.sh: a login on its swap, mint quote, mint, melt quote, melt, checkstate and restore,
at most 3 BATs per request) and its login server mock_oidc.py on 3348 (device code and code + PKCE, refresh, "expire now", down,
slow, a hostile discovery document), plus 3339 (Mint B, no login) and 3338 (Mint A) for payments and auto-move.
Every request to the auth mint is watched: each protected request carries exactly one BAT, every BAT is used once, the clear
auth token (CAT) goes only to /v1/auth/blind/mint, and the BATs minted add up to the BATs the mint accepted plus the ones still
held (nothing leaks).

The grid: logged out / logged in / login expired (refresh refused) / login server down x deposit, payment, token (swap) and
claim, with the expiry landing mid-flow (a deposit paid, then the login ends before the mint is asked: collected once after
logging in; a payment whose melt finds no login: its coins come back once after logging in) x one device / two devices with
one seed (a BAT spent on the other device: one fresh BAT, once) x a PIN vault x the five languages at 320/375/430/1440 px.
Plus: a mint without login unchanged (no auth header ever sent to it), BATs never in a balance, token, Send all, backup file
or wallet sync, Log out and Reset delete the login, a restore from the 12 words brings no login, auto-move into a mint with a
login (logged in / expired / logged out, and it resumes after logging in), hostile mint info (junk NUT-21/22, a discovery
document on http or pointing elsewhere), the login server down or slow, a reload in the middle of a login, browser login
(code + PKCE in a popup) when the login server has no device code.
NOT proven here: a real login server (Keycloak and others: only this stand-in), a real mint other than Nutshell 0.21 (CDK may
burn a BAT on a refused request), and a phone's browser handing the device-code page to another app. AU_ONLY=a,b runs some
sections (their names start with those letters)."""
import asyncio, json, os, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import check, results, URL, invoice
from auto_move_qa import wallet, fresh, am_set, settings, bal, autos, lines, ks, wait_run, settled
from r8_qa import set_pin, unlock, PIN

J = json.dumps
A, B, AU = 'http://127.0.0.1:3338', 'http://127.0.0.1:3339', 'http://127.0.0.1:3347'
AUP = 'http://127.0.0.1:3349'   # (the auth mint whose payments stay pending)
OIDC = 'http://127.0.0.1:3348'
PROT = {'/v1/swap', '/v1/mint/quote/bolt11', '/v1/mint/bolt11', '/v1/mint/bolt11/batch', '/v1/melt/quote/bolt11', '/v1/melt/bolt11', '/v1/checkstate', '/v1/restore'}
ST = f"Nutcade.auth.state({J(AU)})"
LANGS = ('en', 'es', 'pt', 'de', 'fr')


def oidc(path, body=None):
    r = urllib.request.Request(OIDC + path, data=None if path == '/test/state' else J(body or {}).encode(), headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())


def ostate(): return oidc('/test/state')


class Spy:
    """every request this page sends to the auth mint: method, path, its BAT and CAT headers, and BATs asked for"""
    def __init__(s, pg):
        s.reqs = []; s.other = []; pg.on('request', s.on)

    def on(s, r):
        try:
            h = r.headers; path = urllib.parse.urlparse(r.url).path
            if not r.url.startswith(AU):
                if h.get('blind-auth') or h.get('clear-auth'): s.other.append(r.url)
                return
            n = 0
            if path == '/v1/auth/blind/mint':
                try: n = len((r.post_data_json or {}).get('outputs') or [])
                except Exception: n = 0
            s.reqs.append({'m': r.method, 'p': path, 'b': h.get('blind-auth'), 'c': h.get('clear-auth'), 'n': n, 'r': r})
        except Exception:
            pass

    def mark(s): return len(s.reqs)

    async def report(s, since=0):
        """(protected requests and their status, BATs minted, CAT misuse, BATs used twice)"""
        out = {'prot': [], 'minted': 0, 'cat_elsewhere': [], 'no_bat': [], 'twice': [], 'unprot_bat': []}
        seen = {}
        for x in s.reqs[since:]:
            try:
                resp = await x['r'].response(); st = resp.status if resp else 0
            except Exception: st = 0
            if x['c'] and x['p'] != '/v1/auth/blind/mint': out['cat_elsewhere'].append(x['p'])
            if x['p'] == '/v1/auth/blind/mint' and st == 200: out['minted'] += x['n']
            if x['m'] == 'POST' and x['p'] in PROT:
                out['prot'].append((x['p'], st))
                if not x['b']: out['no_bat'].append(x['p'])
                elif st == 200:
                    if x['b'] in seen: out['twice'].append(x['p'])
                    seen[x['b']] = 1
            elif x['b']: out['unprot_bat'].append(x['p'])
        out['ok'] = sum(1 for p, st in out['prot'] if st == 200)
        return out


async def section(name, fn):
    only = [x for x in os.environ.get('AU_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


async def mints_tab(w):
    await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(200)


async def auth_line(w): return await w.ev(f"(document.querySelector('[data-auth=\"{AU}\"]')||{{}}).innerText||''")


async def login(w, approve=True, expect=True, mint=AU):
    """Mints tab -> Log in -> the code shown -> approved at the login server (as a person would there)"""
    await mints_tab(w)
    await w.click(f'[data-act=authLogin][data-url="{mint}"]')
    got = await w.until("!!((document.querySelector('#authCode')||{}).textContent||'').trim() || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
    code = await w.ev("((document.querySelector('#authCode')||{}).textContent||'').trim()")
    if not code: return {'code': '', 'err': await w.err()}
    if approve: oidc('/test/approve', {'user_code': code})
    ok = await w.until(f"Nutcade.auth.state({J(mint)}).inn", 20000) if expect else False
    await w.wait(300)
    return {'code': code, 'ok': ok, 'err': await w.err(), 'sheet': await w.sheet_text()}


async def pool(w): return await w.ev(f"{ST}.bats")


async def try_receive(w, n, url=AU):
    """Receive -> Lightning -> amount -> Create invoice; returns (error text, invoice shown)"""
    await w.use(url); await w.home()
    await w.click('[data-act=receive]'); await w.wait(150)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(100)
    await w.fill('#amtIn', str(n)); await w.click('[data-act=doLnInvoice]')
    await w.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim() || !!document.querySelector('#payState') || !document.querySelector('#amtIn')", 15000)
    return await w.err(), await w.ev("!!document.querySelector('#payState') || !document.querySelector('#amtIn')")


async def deposit(w, n, url=AU):
    b0 = await bal(w, url)
    e, shown = await try_receive(w, n, url)
    ok = not e and await w.until(f"(Nutcade.S.proofs[{J(url)}]||[]).reduce((t,p)=>t+p.amount,0) >= {b0 + n}", 25000)
    await w.wait(300); await w.ev("Nutcade.closeSheet()")
    return ok, e


async def send_token(w, n, url=AU):
    await w.use(url); return await w.send_ecash(n)


async def pay(w, n, url=AU, dest=B):
    await w.use(url); return await w.pay_ln(invoice(n, dest))


def expire_now(w_js=True): oidc('/test/expire')


async def end_login(w):
    """the login ends: no BAT left, the access token past its time, the refresh token refused (the server's "expire now")"""
    oidc('/test/expire')
    await w.ev(f"(()=>{{const e=Nutcade.S.auth[{J(AU)}]; e.bats=[]; e.exp=1; }})()")


async def main():
    os.makedirs(os.environ.get('QA_OUT', '/tmp/qa-out'), exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        errs = []
        oidc('/test/reset')

        # ======================= a mint without login is unchanged =======================
        async def plain():
            w = await fresh(b, 'au-plain', mints=(B,)); spy = Spy(w.pg)
            ok, e = await deposit(w, 300, B)
            tok, e2 = await send_token(w, 50, B)
            await mints_tab(w)
            txt = await w.ev("document.querySelector('.screen').innerText")
            check('plain: a mint without login: deposit and token work as before, no login line, nothing stored for it, no auth header ever sent',
                  ok and tok and not e2 and 'needs a login' not in txt and not await w.ev("Object.keys(Nutcade.S.auth||{}).length") and not spy.other and not await w.ev(f"!!document.querySelector('[data-auth]')"), (ok, e, e2, spy.other))
            errs.extend(w.errs); await w.pg.context.close()
        await section('plain', plain)

        # ======================= logged out, log in, BAT discipline, refresh, log out =======================
        async def flow():
            oidc('/test/reset')
            w = await fresh(b, 'au-flow', mints=(B, AU)); spy = Spy(w.pg)
            await mints_tab(w)
            txt = await auth_line(w)
            check('info: a mint that needs a login says so on its panel: "This mint needs a login", not logged in, a Log in button',
                  'This mint needs a login' in txt and 'Not logged in' in txt and await w.ev(f"!!document.querySelector('[data-act=authLogin][data-url=\"{AU}\"]')") and await w.ev(f"{ST}.need"), txt)
            m0 = spy.mark()
            e, shown = await try_receive(w, 100)
            check('out: a deposit while logged out stops before the mint is asked, with a clear "log in" message, nothing recorded',
                  re.search(r'log in', e, re.I) and not shown and not await w.ev(f"Nutcade.S.quotes.some(q=>q.mint==={J(AU)})") and not await w.ev(f"Nutcade.S.txs.some(t=>t.mint==={J(AU)})")
                  and not [x for x in spy.reqs[m0:] if x['p'] in PROT], (e, [x['p'] for x in spy.reqs[m0:]]))
            await w.ev("Nutcade.closeSheet()")
            r = await login(w)
            st = await w.ev(ST); txt = await auth_line(w)
            check('login: device code shown, approved at the login server: logged in, the account named, the sheet says so',
                  r['ok'] and re.match(r'^\d{4}-\d{4}$', r['code']) and st['inn'] and st['who'] == 'player-1' and 'Logged in' in txt and 'player-1' in txt and ostate()['n']['device_ok'] == 1, (r, st, txt))
            link = await w.ev("(document.querySelector('#authLink')||{}).href||''")
            check('login: the login page link went to the login server with the code, opened in a new tab without the opener', True if not link else link.startswith(OIDC + '/activate'), link)
            await w.ev("Nutcade.closeSheet()")
            m0 = spy.mark()
            ok, e = await deposit(w, 500)
            tok, e2 = await send_token(w, 40)
            e3, q = await pay(w, 60)
            rep = await spy.report(m0); bats = await pool(w)
            check('logged in: deposit, token (swap) and Lightning payment all work at the mint with a login', ok and tok and not e2 and not e3, (e, e2, e3))
            check('BATs: every protected request carried exactly one BAT, none used twice, none on other requests',
                  rep['prot'] and not rep['no_bat'] and not rep['twice'] and not rep['unprot_bat'], rep)
            check('BATs: the CAT went only to /v1/auth/blind/mint, never anywhere else (nor to any other server)', not rep['cat_elsewhere'] and not spy.other, (rep['cat_elsewhere'], spy.other))
            check('BATs: minted = accepted + still held (nothing leaked), and never more than the mint\'s 3 held', rep['minted'] == rep['ok'] + bats and 0 <= bats <= 3, (rep['minted'], rep['ok'], bats))
            # refresh: the access token past its time, no BAT left: a silent refresh, then on
            n0 = ostate()['n']['refresh']
            await w.ev(f"(()=>{{const e=Nutcade.S.auth[{J(AU)}]; e.bats=[]; e.exp=Date.now()-1000; }})()")
            ok, e = await deposit(w, 100)
            check('refresh: an expired access token is refreshed silently (once) and the deposit goes through', ok and ostate()['n']['refresh'] == n0 + 1 and (await w.ev(ST))['inn'], (e, ostate()['n']))
            # BATs are not money
            sec = await w.ev(f"Nutcade.S.auth[{J(AU)}].bats.map(p=>p.secret)")
            ids = await w.ev(f"Nutcade.S.auth[{J(AU)}].bats.map(p=>p.id)")
            held = await w.ev("Object.values(Nutcade.S.proofs).flat().map(p=>p.secret)")
            bk = await w.ev("Nutcade.r8.backupData()"); pj = J(await w.ev("Nutcade.S.proofs"))
            at, rt = await w.ev(f"[Nutcade.S.auth[{J(AU)}].at, Nutcade.S.auth[{J(AU)}].rt]")
            total = await w.ev(f"Nutcade.S.proofs[{J(AU)}].reduce((t,p)=>t+p.amount,0)")
            shown = await w.ev("document.body.innerText")
            check('BATs: held apart from the coins (no BAT secret or auth keyset among the coins), never in the backup file with the tokens',
                  sec and not set(sec) & set(held) and not any(i in pj for i in ids)
                  and not any(s_ in bk for s_ in sec) and at not in bk and rt not in bk and '"auth"' not in bk, (len(sec), at in bk))
            await w.use(AU); await w.home()
            await w.click('[data-act=send]'); await w.wait(200)
            await w.click('[data-act=allEcash]'); await w.until("/Create token for/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 15000)
            sa = await w.sheet_text()
            check('BATs: Send all offers exactly the coins at the mint (a no-fee mint: all of it), BATs not counted', f"create token for {total:,} sat" in sa.lower(), (total, sa[:300]))
            await w.ev("Nutcade.closeSheet()")
            # log out
            await mints_tab(w); await w.click(f'[data-act=authLogout][data-url="{AU}"]'); await w.wait(400)
            st = await w.ev(f"Nutcade.S.auth[{J(AU)}]"); txt = await auth_line(w)
            check('logout: the tokens and BATs are deleted from this device, the panel says not logged in, a deposit stops with "log in"',
                  not st.get('at') and not st.get('rt') and not st.get('bats') and 'Not logged in' in txt, (st, txt))
            e, shown = await try_receive(w, 10); await w.ev("Nutcade.closeSheet()")
            check('logout: then a deposit stops cleanly, nothing recorded', re.search('log in', e, re.I) and not shown, e)
            check('flow: no page errors and nothing logged to the console', not w.errs, w.errs[:5])
            errs.extend(w.errs); await w.pg.context.close()
        await section('flow', flow)

        # ======================= the login ending in the middle of a deposit, a payment, a token =======================
        async def mid():
            oidc('/test/reset')
            w = await fresh(b, 'au-mid', mints=(B, AU)); await login(w); await w.ev("Nutcade.closeSheet()")
            ok, _ = await deposit(w, 400)
            # a deposit: invoice made and paid, then the login ends before the mint is asked for the coins
            held = {'go': False}
            async def hold_check(route):
                try:
                    while not held['go']: await asyncio.sleep(0.1)
                    await route.continue_()
                except Exception: pass
            await w.pg.route(AU + '/v1/mint/quote/bolt11/*', hold_check)
            b0 = await bal(w, AU)
            e, shown = await try_receive(w, 250)
            await w.wait(1200); await end_login(w); held['go'] = True
            await w.until(f"{ST}.again", 15000); await w.wait(3000)
            ps = await w.ev("((document.querySelector('#payState')||{}).innerText||'')+' '+((document.querySelector('.sheet-body')||{}).innerText||'')")
            q = await w.ev(f"Nutcade.S.quotes.filter(q=>q.mint==={J(AU)}).length")
            check('mid-deposit: paid, then the login ended: nothing booked, the deposit waits (its line pending), the screen says to log in to collect it',
                  shown and await bal(w, AU) == b0 and q == 1 and re.search('log in', ps, re.I) and not await w.ev(f"Nutcade.S.ops.some(o=>o.mint==={J(AU)})"), (shown, q, ps[:200]))
            await w.ev("Nutcade.closeSheet()"); await w.pg.unroute(AU + '/v1/mint/quote/bolt11/*')
            await mints_tab(w); txt = await auth_line(w)
            check('mid-deposit: the mint\'s panel says the login ended: log in again', re.search('Log in again', txt) and await w.ev(f"!!document.querySelector('[data-act=authLogin][data-url=\"{AU}\"]')"), txt)
            oidc('/test/reset'); await login(w); await w.ev("Nutcade.closeSheet()")
            got = await w.until(f"(Nutcade.S.proofs[{J(AU)}]||[]).reduce((t,p)=>t+p.amount,0) === {b0 + 250}", 30000)
            await w.wait(3000)
            n_in = await w.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(AU)}&&t.type==='in'&&t.amount===250&&t.status==='done').length")
            check('mid-deposit: after logging in the deposit is collected once (+250, one line, no double credit)', got and await bal(w, AU) == b0 + 250 and n_in == 1 and not await w.ev(f"Nutcade.S.quotes.some(q=>q.mint==={J(AU)})"), (await bal(w, AU), n_in))
            # a payment: its coins ready (swap), then the melt finds no login
            b1 = await bal(w, AU)
            async def after_swap(route):
                try:
                    resp = await route.fetch(); body = await resp.body()
                    await end_login(w)
                    await route.fulfill(response=resp, body=body)
                except Exception: pass
            await w.pg.route(AU + '/v1/swap', after_swap)
            await w.ev(f"(()=>{{const e=Nutcade.S.auth[{J(AU)}]; e.bats=e.bats.slice(0,2); }})()")   # (one for the melt quote, one for the swap)
            e, qt = await pay(w, 37)
            await w.pg.unroute(AU + '/v1/swap'); await w.wait(800)
            pend = await w.ev(f"Nutcade.S.pending.filter(p=>p.mint==={J(AU)}).length")
            tx = await w.ev(f"Nutcade.S.txs.find(t=>t.mint==={J(AU)}&&t.type==='out'&&t.amount===37)")
            check('mid-pay: the melt found no login: a clear "log in" error, nothing paid, the coins held aside for the journal (none lost)',
                  re.search('log in', e, re.I) and await bal(w, AU) + await w.ev(f"Nutcade.S.pending.filter(p=>p.mint==={J(AU)}).flatMap(p=>p.proofs).reduce((t,p)=>t+p.amount,0)") == b1, (e, pend, tx and tx['status']))
            oidc('/test/reset'); await login(w); await w.ev("Nutcade.closeSheet()")
            back = await w.until(f"!Nutcade.S.pending.some(p=>p.mint==={J(AU)}) && (Nutcade.S.proofs[{J(AU)}]||[]).reduce((t,p)=>t+p.amount,0)==={b1}", 40000)
            tx = await w.ev(f"Nutcade.S.txs.find(t=>t.mint==={J(AU)}&&t.type==='out'&&t.amount===37)")
            check('mid-pay: after logging in the journal gives the coins back once (balance exactly as before, the line failed, no double credit)', back and await bal(w, AU) == b1 and (not tx or tx['status'] == 'failed'), (await bal(w, AU), b1, tx and tx['status']))
            e, q = await pay(w, 37)
            fee = await w.ev(f"(Nutcade.S.txs.find(t=>t.mint==={J(AU)}&&t.type==='out'&&t.amount===37&&t.status==='done')||{{}}).fee")
            check('mid-pay: then the same payment goes through (the balance down by the amount and the fee the mint kept, nothing more)', not e and fee is not None and await bal(w, AU) == b1 - 37 - fee, (e, fee, await bal(w, AU)))
            # a token (swap): the only BAT left was spent elsewhere and the login has ended
            b2 = await bal(w, AU)
            bat = await w.ev(f"Nutcade.S.auth[{J(AU)}].bats.slice(-1)[0]")
            spent = await w.ev("""(async (p)=>{const t='authA'+btoa(JSON.stringify({id:p.id,secret:p.secret,C:p.C})).replace(/\\+/g,'-').replace(/\\//g,'_');
                const r=await fetch(%s+'/v1/checkstate',{method:'POST',headers:{'Content-Type':'application/json','Blind-auth':t},body:JSON.stringify({Ys:[]})}); return r.status})""" % J(AU) + f"({J(bat)})")
            await w.ev(f"(()=>{{const e=Nutcade.S.auth[{J(AU)}]; e.bats=[{J(bat)}]; e.exp=1; }})()"); oidc('/test/expire')
            tok, e = await send_token(w, 20)
            check('mid-swap: the only BAT was spent elsewhere and the login ended: no token, a "log in" error, the balance unchanged',
                  spent == 200 and not tok and re.search('log in', e, re.I) and await bal(w, AU) == b2, (spent, tok, e, await bal(w, AU)))
            oidc('/test/reset'); await login(w); await w.ev("Nutcade.closeSheet()")
            await w.until(f"!Nutcade.S.ops.some(o=>o.mint==={J(AU)})", 30000)
            tok, e = await send_token(w, 20)
            ops = await w.ev(f"Nutcade.S.ops.filter(o=>o.mint==={J(AU)}).map(o=>[o.kind,o.refused||0])")
            check('mid-swap: after logging in the journal closed the step with nothing booked, and the token is made', tok and not e and await bal(w, AU) == b2 - 20 and not ops, (bool(tok), e, await bal(w, AU), b2, ops))
            check('mid: no page errors', not w.errs, w.errs[:5])
            errs.extend(w.errs); await w.pg.context.close()
        await section('mid', mid)

        # ======================= two devices, one seed; a BAT already spent elsewhere =======================
        async def two():
            oidc('/test/reset')
            w = await fresh(b, 'au-two', mints=(AU,)); await login(w); await w.ev("Nutcade.closeSheet()")
            await deposit(w, 300)
            words = await w.ev("Nutcade.S.seed.mnemonic")
            d = await wallet(b, 'au-two-b')
            await d.gate_restore(); await d.fill('#phraseIn', words); await d.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)"); await d.fill('#rmExtra', AU)
            await d.click('[data-act=doRestorePhrase]'); await d.until("!document.querySelector('[data-act=doRestorePhrase]')", 120000); await d.wait(600)
            rtxt = await d.sheet_text(); await d.ev("Nutcade.closeSheet()")
            if await d.until("!!document.querySelector('[data-act=gateStart]')", 4000): await d.gate_step('gateStart', "!!document.querySelector('.tabbar')")
            await d.wait(300); await d.ev("Nutcade.closeSheet()")
            st = await d.ev(f"Nutcade.auth.state({J(AU)})")
            check('two: a restore from the 12 words brings no login (log in again on the new device), and says the mint needs one',
                  not st['inn'] and not await d.ev(f"!!(Nutcade.S.auth[{J(AU)}]||{{}}).rt"), (st, rtxt[:200]))
            check('two: the restore says the mint needs a login before it can be scanned', re.search('log in', rtxt, re.I) and 'Find lost ecash' in rtxt, rtxt[:300])
            await login(d); await d.ev("Nutcade.closeSheet()")
            await d.ev("window.__toasts=[]")
            await settings(d); await d.click('[data-act=findLost]'); await d.until(f"(Nutcade.S.proofs[{J(AU)}]||[]).reduce((t,p)=>t+p.amount,0) >= 300", 30000)
            print('two: findLost toasts', await d.ev("window.__toasts"), await d.ev(f"Nutcade.auth.state({J(AU)})"), flush=True)
            check('two: logged in, Find lost ecash finds the 12 words\' coins at that mint', await bal(d, AU) == await bal(w, AU), (await bal(d, AU), await bal(w, AU)))
            # the other device spends a BAT this one still holds (its storage copied, say): a coin check there uses it
            spy = Spy(w.pg)
            mine = await w.ev(f"Nutcade.S.auth[{J(AU)}].bats")
            await d.ev(f"Nutcade.S.auth[{J(AU)}].bats = {J(mine[-1:])}")
            st_d = await d.ev(f"NutSync.states({J(AU)}, Nutcade.S.proofs[{J(AU)}].slice(0,1))")
            b0 = await bal(w, AU); m0 = spy.mark()
            tok, e = await send_token(w, 30)
            rep = await spy.report(m0)
            n31 = sum(1 for pth, st_ in rep['prot'] if st_ == 400)
            check('two: a BAT already spent on the other device: refused once, one fresh BAT fetched, the token made, nothing more',
                  st_d == ['UNSPENT'] and tok and not e and n31 == 1 and await bal(w, AU) == b0 - 30, (st_d, e, rep['prot']))
            check('two: the spent BAT is dropped, not kept', not set(x['secret'] for x in mine[-1:]) & set(await w.ev(f"Nutcade.S.auth[{J(AU)}].bats.map(p=>p.secret)")))
            # both devices then use the same 12 words' counters: the mint refuses the second one's outputs (Nutshell says only
            # "Blind authentication failed"), the usual catch-up scan runs, and the token is made
            ok_d, _ = await deposit(d, 50)
            b0 = await bal(w, AU)
            tok, e = await send_token(w, 25)
            check('two: counters used on the other device (refused with no reason by a mint with a login): caught up, the token made, the balance right (the other device\'s 50 found by the scan, or not yet)',
                  ok_d and tok and not e and await bal(w, AU) in (b0 - 25, b0 - 25 + 50) and not await w.ev(f"Nutcade.S.ops.some(o=>o.mint==={J(AU)})"), (ok_d, e, await bal(w, AU), b0))
            errs.extend(w.errs + d.errs); await w.pg.context.close(); await d.pg.context.close()
        await section('two', two)

        # ======================= a refusal Nutshell hides behind "Blind authentication failed" =======================
        # (Nutshell answers every refused protected request with 31002, whatever the reason: the wallet asks the mint
        # what is true, so it acts as it does at a mint without login: spent coins pruned, pending left pending,
        # an already claimed token said so)
        async def masked():
            from wallet_qa import W
            async def copies(mint, n):
                """a wallet with n SAT at mint, logged in, opened on two devices (its storage copied: same 12 words, coins, login)"""
                w = await fresh(b, 'au-m0', mints=(mint,)); await login(w, mint=mint); await w.ev("Nutcade.closeSheet()")
                await deposit(w, n, mint)
                ls = await w.ev("JSON.stringify(Object.fromEntries(Object.keys(localStorage).filter(k=>k.startsWith('nutcade:')).map(k=>[k,localStorage.getItem(k)])))")
                await w.pg.context.close(); out = []
                for i in range(2):
                    ctx = await b.new_context(viewport={'width': 390, 'height': 844})
                    await ctx.add_init_script(f"if(!sessionStorage.getItem('x')){{sessionStorage.setItem('x',1); const d={ls}; for(const k in d) localStorage.setItem(k,d[k]);}}")
                    pg = await ctx.new_page(); x = W(pg, 'au-m' + str(i + 1)); pg.on('pageerror', lambda e, x=x: x.errs.append('PAGEERROR ' + str(e)))
                    await pg.goto(URL); await pg.wait_for_timeout(2500); out.append(x)
                return out
            async def phantom(w, mint): return await w.ev(f"NutSync.states({J(mint)}, Nutcade.S.proofs[{J(mint)}]||[]).then(s=>Nutcade.S.proofs[{J(mint)}].filter((p,i)=>s[i]!=='UNSPENT').reduce((t,p)=>t+p.amount,0))")
            oidc('/test/reset')
            # spent on the other device
            d1, d2 = await copies(AU, 500)
            tok, e = await send_token(d1, 400)
            tok2, e2 = await send_token(d2, 50)
            await d2.wait(1500)
            ph, b2 = await phantom(d2, AU), await bal(d2, AU)
            notes = await d2.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(AU)}).map(t=>[t.type,t.amount,t.status,t.note||''])")
            check('masked: coins spent on the other device: the send goes through at once, the spent coins are removed (one line), no spent coin left in the balance',
                  tok and tok2 and not e2 and ph == 0 and b2 == 50 and any('spent elsewhere' in n[3] for n in notes), (bool(tok2), e2, b2, ph, notes[:5]))
            await d2.pg.reload(); await d2.wait(4000)
            check('masked: and still so after a reload', await phantom(d2, AU) == 0 and await bal(d2, AU) == 50, (await bal(d2, AU), await phantom(d2, AU)))
            # already claimed: the token claimed, then claimed again (and taken back by its sender)
            r = await fresh(b, 'au-m3', mints=(AU,)); await login(r); await r.ev("Nutcade.closeSheet()")
            tok2, _ = await send_token(d1, 30)
            async def rcv(x, t): await x.home(); return await x.receive_token(t)
            _, e3, _ = await rcv(r, tok2)
            _, e4, t4 = await rcv(r, tok2); await r.wait(1500)
            _, e5, t5 = await rcv(d1, tok2)
            check('masked: a token already claimed: claimed again or taken back by its sender, the mint\'s answer is "already spent", not "Blind authentication failed"',
                  not e3 and re.search('already (spent|claimed)', e4 + t4, re.I) and re.search('already (spent|claimed)', e5 + t5, re.I) and 'Blind authentication failed' not in e4 + e5, (e3, e4, e5))
            for x in (d1, d2, r): errs.extend(x.errs); await x.pg.context.close()
            # pending: a token made of coins that are in a payment still in flight at the mint (their state PENDING)
            p1 = await fresh(b, 'au-m4', mints=(AUP,)); await login(p1, mint=AUP); await p1.ev("Nutcade.closeSheet()")
            await deposit(p1, 300, AUP)
            e6, _ = await pay(p1, 100, AUP)
            await p1.until(f"Nutcade.S.pending.some(p=>p.mint==={J(AUP)})", 15000)
            ptok = await p1.ev(f"(()=>{{const p=Nutcade.S.pending.find(p=>p.mint==={J(AUP)}); return CashuLib.getEncodedToken({{mint:{J(AUP)}, proofs:p.proofs, unit:'sat'}})}})()")
            pre = await p1.ev(f"NutSync.states({J(AUP)}, Nutcade.S.pending.find(p=>p.mint==={J(AUP)}).proofs)")
            p2 = await fresh(b, 'au-m5', mints=(AUP,)); await login(p2, mint=AUP); await p2.ev("Nutcade.closeSheet()")
            await p2.home(); await p2.click('[data-act=receive]'); await p2.wait(150); await p2.click('[data-act=recvMethod][data-m=ecash]'); await p2.wait(100)
            await p2.fill('#tokIn', ptok); await p2.click('[data-act=doReceiveToken]'); await p2.wait(1200)
            if await p2.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await p2.click('[data-act=doReceiveToken]')
            await p2.until("!!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000)
            e7, t7 = await p2.err(), ''; await p2.ev("Nutcade.closeSheet()")
            notes = await p2.ev(f"Nutcade.S.txs.filter(t=>t.mint==={J(AUP)}&&t.status==='done').map(t=>[t.type,t.amount,t.note||''])")
            check('masked: a token whose coins are pending in a payment: refused as pending (as at a mint without login), nothing booked',
                  set(pre) == {'PENDING'} and re.search('pending', e7 + t7, re.I) and 'Blind authentication failed' not in e7 and await bal(p2, AUP) == 0 and not notes, (pre, e7, t7[:200], notes[:3]))
            for x in (p1, p2): errs.extend(x.errs); await x.pg.context.close()
        await section('masked', masked)

        # ======================= storage: PIN vault, wallet sync, Reset =======================
        async def store():
            oidc('/test/reset')
            w = await fresh(b, 'au-store', mints=(AU,)); await login(w); await w.ev("Nutcade.closeSheet()")
            await deposit(w, 200)
            rt = await w.ev(f"Nutcade.S.auth[{J(AU)}].rt")
            plain = await w.ev("Object.keys(localStorage).filter(k=>k.startsWith('nutcade:')).map(k=>localStorage.getItem(k)).join('\\n')")
            check('store: without a PIN the login is kept on this device with the wallet (local storage)', rt in plain)
            await set_pin(w)
            plain = await w.ev("Object.keys(localStorage).map(k=>localStorage.getItem(k)).join('\\n')")
            check('store: with a PIN the login is only inside the encrypted vault, never in plain storage', rt not in plain and 'nutcade:auth' not in await w.ev("Object.keys(localStorage).join(' ')"))
            await w.pg.reload(); await unlock(w)
            check('store: after a reload and the PIN the login is back', (await w.ev(ST))['inn'])
            # wallet sync: no BAT, no token on the relays
            sec = await w.ev(f"Nutcade.S.auth[{J(AU)}].bats.map(p=>p.secret)")
            await settings(w)
            if await w.ev("!!document.querySelector('#p_sync')"):
                await w.click('#p_sync'); await w.wait(500)
                if await w.ev("!!document.querySelector('[data-act=syncOnOk]')"): await w.click('[data-act=syncOnOk]')
                await w.ev("NutSync.push && NutSync.push()"); await w.wait(4000)
                words = await w.ev("Nutcade.S.seed.mnemonic")
                evs = json.loads(urllib.request.urlopen('http://127.0.0.1:3350/test/state', timeout=10).read())['events']
                pk = await w.ev("NutSync.pk()")
                dec = await w.ev("""(([w, cs])=>{const s=CashuLib.mnemonicToSeedSync(w), t=new TextEncoder().encode('nutcade-nip60'), b=new Uint8Array(s.length+t.length); b.set(s); b.set(t,s.length);
                    const sk=CashuLib.sha256(b), ck=CashuLib.nip44.v2.utils.getConversationKey(sk, CashuLib.nostrPub(sk)); return cs.map(c=>{try{return CashuLib.nip44.v2.decrypt(c, ck)}catch(e){return ''}}).join('\\n')})""" + f"([{J(words)}, {J([e['content'] for e in evs if e['pubkey'] == pk])}])")
                check('sync: the wallet\'s events on the relays hold its coins but no BAT and no login token', dec and AU in dec and not any(s_ in dec for s_ in sec) and rt not in dec and 'authA' not in dec, (len(dec), any(s_ in dec for s_ in sec)))
                await settings(w); await w.click('#p_sync'); await w.wait(300); await w.ev("Nutcade.closeSheet()")
            # Reset: the login goes, and the sheet says so
            await settings(w); await w.click('[data-act=resetAsk]'); await w.wait(300)
            if await w.ev("!!document.querySelector('[data-pinpad]')"): await unlock(w)
            await w.until("!!document.querySelector('#confirmWord')", 5000)
            rtxt = await w.sheet_text()
            await w.fill('#confirmWord', 'RESET'); await w.click('[data-act=doReset]'); await w.wait(2500)
            left = await w.ev("Object.keys(localStorage).map(k=>localStorage.getItem(k)).join('\\n')")
            check('reset: the sheet says mint logins are deleted too, and after Reset no token is left in storage', re.search('log', rtxt, re.I) and 'mint login' in rtxt.lower() and rt not in left and 'nutcade:auth' not in await w.ev("Object.keys(localStorage).join(' ')"), rtxt[:300])
            errs.extend(w.errs); await w.pg.context.close()
        await section('store', store)

        # ======================= auto-move into a mint with a login =======================
        async def move():
            oidc('/test/reset')
            w = await fresh(b, 'au-move', mints=(B, AU))
            await am_set(w, True, my=AU, mn=100)
            ok, _ = await deposit(w, 600, B)
            await w.ev("Nutcade.closeSheet()"); ls = await w.ev("NutAutoMove.run('test')")
            check('move: logged out: nothing moves, the line says to log in to your mint', ks(ls) == ['mylogin'] and re.search('[Ll]og in to', await w.ev("NutAutoMove.txt('mylogin',[])")) and await bal(w, B) == 600, ls)
            t0 = await w.ev("NutAutoMove.at()")
            await login(w); await w.ev("Nutcade.closeSheet()")
            moved = await wait_run(w, t0, 90000) and await settled(w)
            check('move: logging in resumes auto-move by itself: the sats move into the mint with a login', moved and await bal(w, B) < 100 and await bal(w, AU) > 400, (await bal(w, B), await bal(w, AU), await lines(w)))
            await end_login(w)
            ok, _ = await deposit(w, 600, B); await w.ev("Nutcade.closeSheet()")
            ls = await w.ev("NutAutoMove.run('test')")
            check('move: the login ended: nothing moves, "log in to your mint", the sats stay at the sending mint', ks(ls) == ['mylogin'] and await bal(w, B) >= 600 and not await w.ev("Nutcade.S.pending.length"), ls)
            errs.extend(w.errs); await w.pg.context.close()
        await section('move', move)

        # ======================= hostile mint info, login server down / slow / reload, browser login =======================
        async def hostile():
            oidc('/test/reset')
            w = await fresh(b, 'au-host', mints=(AU,)); spy = Spy(w.pg)
            info = json.loads(urllib.request.urlopen(AU + '/v1/info', timeout=10).read())
            async def bent(n21, n22=None):
                async def h(route):
                    try:
                        d = json.loads(json.dumps(info)); d['nuts']['21'] = n21
                        if n22 is not None: d['nuts']['22'] = n22
                        await route.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'}, body=J(d))
                    except Exception: pass
                await w.pg.unroute(AU + '/v1/info'); await w.pg.route(AU + '/v1/info', h)
                await w.ev(f"Nutcade.authForget && Nutcade.authForget({J(AU)})"); await mints_tab(w); await w.click(f'[data-act=refreshMint][data-url="{AU}"]'); await w.wait(1500)
            asked = []
            await w.pg.route('**/evil.example/**', lambda r: (asked.append(r.request.url), asyncio.ensure_future(r.abort())))
            for name, n21, n22 in (('junk NUT-21/22', 'garbage', {'bat_max_mint': -5, 'protected_endpoints': 'x'}),
                                   ('a discovery document on plain http elsewhere', {'openid_discovery': 'http://evil.example/.well-known/openid-configuration', 'client_id': 'x', 'protected_endpoints': []}, None),
                                   ('a discovery URL that is not a URL', {'openid_discovery': 'javascript:alert(1)', 'protected_endpoints': []}, None)):
                await bent(n21, n22)
                r = await login(w, approve=False, expect=False) if await w.ev(f"!!document.querySelector('[data-act=authLogin][data-url=\"{AU}\"]')") else {'err': 'no login button', 'code': ''}
                check(f'hostile: {name}: no crash, no login started, nothing sent to that address, a plain message', not r['code'] and not asked and not w.errs, (r, asked, w.errs[:2]))
                await w.ev("Nutcade.closeSheet()")
            await w.pg.unroute(AU + '/v1/info'); await w.ev(f"Nutcade.authForget && Nutcade.authForget({J(AU)})"); await mints_tab(w); await w.click(f'[data-act=refreshMint][data-url="{AU}"]'); await w.wait(1500)
            # a discovery document whose token endpoint is on plain http elsewhere
            oidc('/test/config', {'token_endpoint': 'http://evil.example/token'})
            r = await login(w, approve=False, expect=False)
            check('hostile: a discovery document sending the token to plain http elsewhere: refused before anything is sent there', not r['code'] and not asked and r['err'], r)
            await w.ev("Nutcade.closeSheet()"); oidc('/test/reset')
            # the login server down: a plain message; down while logged in: the login is kept, it works again once back
            oidc('/test/config', {'down': True})
            r = await login(w, approve=False, expect=False)
            check('down: the login server not answering: a plain message, no login', not r['code'] and re.search("login server isn't answering", r['err'], re.I), r)
            await w.ev("Nutcade.closeSheet()"); oidc('/test/config', {'down': False})
            await login(w); await w.ev("Nutcade.closeSheet()")
            await w.ev(f"(()=>{{const e=Nutcade.S.auth[{J(AU)}]; e.bats=[]; e.exp=1; }})()"); oidc('/test/config', {'down': True})
            e, shown = await try_receive(w, 10); await w.ev("Nutcade.closeSheet()")
            st = await w.ev(f"Nutcade.S.auth[{J(AU)}]")
            check('down: logged in but the login server is down: "isn\'t answering", the login is kept (no "log in again")', re.search("login server", e, re.I) and not shown and st.get('rt') and not st.get('again'), (e, st.get('again')))
            oidc('/test/config', {'down': False}); await w.ev(f"Nutcade.auth.cool({J(AU)})")
            ok, e = await deposit(w, 20)
            check('down: back up: the same login works again with no new login', ok, e)
            # slow login server
            await mints_tab(w); await w.click(f'[data-act=authLogout][data-url="{AU}"]'); await w.wait(300)
            oidc('/test/config', {'delay': 3})
            r = await login(w)
            check('slow: a slow login server: the sheet waits, the login completes', r['ok'], r)
            await w.ev("Nutcade.closeSheet()"); oidc('/test/config', {'delay': 0})
            # a reload in the middle of a login
            await mints_tab(w); await w.click(f'[data-act=authLogout][data-url="{AU}"]'); await w.wait(300)
            r = await login(w, approve=False, expect=False)
            await w.pg.reload(); await w.wait(1500)
            oidc('/test/approve', {'user_code': r['code']}); await w.wait(4000)
            st = await w.ev(ST); await mints_tab(w)
            check('reload: a reload in the middle of a login leaves it cleanly logged out, the Log in button works again', r['code'] and not st['inn'] and await w.ev(f"!!document.querySelector('[data-act=authLogin][data-url=\"{AU}\"]')"), (r, st))
            r = await login(w)
            check('reload: logging in again after that works', r['ok'], r)
            await w.ev("Nutcade.closeSheet()")
            # browser login (code + PKCE in a popup) when the login server has no device code
            await mints_tab(w); await w.click(f'[data-act=authLogout][data-url="{AU}"]'); await w.wait(300)
            oidc('/test/config', {'no_device': True})
            async with w.pg.context.expect_page(timeout=15000) as pop:
                await w.click(f'[data-act=authLogin][data-url="{AU}"]')
            pp = await pop.value
            ok = await w.until(f"{ST}.inn", 20000)
            check('pkce: no device code: a login window opens, comes back with the code, logged in (PKCE checked by the server)', ok and ostate()['n']['code'] == 1, ostate()['n'])
            await w.ev("Nutcade.closeSheet()"); oidc('/test/reset')
            ok, e = await deposit(w, 20)
            check('pkce: then the mint works', ok, e)
            check('hostile: no page errors', not w.errs, w.errs[:5])
            errs.extend(w.errs); await w.pg.context.close()
        await section('hostile', hostile)

        # ======================= the five languages at four widths =======================
        async def langs():
            oidc('/test/reset')
            page = urllib.request.urlopen(URL, timeout=10).read().decode('utf-8')
            check('langs: the What\'s new list has the mint login lines', 'log in' in page.lower() and "1.33.0" in page)
            for lang in LANGS:
                x = await fresh(b, 'au-' + lang, mints=(AU,), lang=lang)
                for wd in (320, 375, 430, 1440):
                    await x.pg.set_viewport_size({'width': wd, 'height': 800})
                    await mints_tab(x); await x.wait(200)
                    over = await x.ev("document.documentElement.scrollWidth > window.innerWidth + 1 || [...document.querySelectorAll('[data-auth], [data-auth] *')].some(e=>e.scrollWidth>e.clientWidth+1 && getComputedStyle(e).overflow!=='visible')")
                    check(f'{lang} {wd}px: the mint panel with its login line fits (no overflow)', not over)
                    if wd == 375:
                        await x.click(f'[data-act=authLogin][data-url="{AU}"]'); await x.until("!!((document.querySelector('#authCode')||{}).textContent||'').trim()", 15000)
                        over = await x.ev("document.documentElement.scrollWidth > window.innerWidth + 1 || [...document.querySelectorAll('.sheet *')].some(e=>e.scrollWidth>e.clientWidth+1 && /auto|scroll|hidden/.test(getComputedStyle(e).overflowX) && e.tagName!=='TEXTAREA')")
                        check(f'{lang} 375px: the login sheet with its code fits', not over)
                        await x.ev("Nutcade.closeSheet()")
                await x.pg.set_viewport_size({'width': 390, 'height': 844})
                if lang != 'en':
                    eng = await x.ev("Nutcade.auth.texts()")
                    trd = await x.ev(f"{J(eng)}.map(s=>Nutcade.tr(s))")
                    same = [s_ for s_, t in zip(eng, trd) if s_ == t]
                    miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/log ?in|login|Log out|BAT|login server/i.test(s))")
                    check(f'{lang}: every mint login text is translated, nothing missing on screen', eng and not same and not miss, (same[:3], miss[:3]))
                errs.extend(x.errs); await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not errs, errs[:5])
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
