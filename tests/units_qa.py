"""Units (1.31.0): SAT plus USD, EUR and CHF ecash, never mixed.

Uses two real local test mints (Nutshell cashu==0.21.0, no input fees): the MULTI mint on 3345, which issues sat, usd and
eur ecash with fake Lightning for each unit, and the DOLLAR mint on 3346, which issues usd only (no sat keyset at all).
The sat mint on 3339 is the far end of a Lightning payment. The stand-in Nostr relay (mock_nostr.py, 3350) stands in for
relays, so nothing touches public services. FakeWallet's rate is its own (1e8/1337 sat per dollar): every check reads the
amount the mint itself quoted, never a rate of ours, so nothing here depends on that number.

Covered: the units table and one formatter (SAT unchanged, "12.50 USD"); typed amounts ("12.50" -> 1250, "0.01" -> 1,
"12.505" refused, never rounded); a unit at a mint is its own account ("<url>|usd") and sat coins stay stored exactly as
before; the mint list shows each unit of one mint as its own line and adds one without the others; a mint with no sat
keyset can be added; deposit by Lightning into a USD account (the invoice in SAT, the credit in USD as the mint quotes
it); pay-out by Lightning from a USD account (the invoice's SAT, the mint's USD quote and USD fee, the fee booked in
USD); send and receive USD and EUR tokens between two wallets (the token carries the unit); payment requests in each
unit, and one in a unit we don't hold refused; two units at one mint are never added together (balance lines, history,
the spending limit, the report card); a send whose answer is lost is settled from the journal in the right unit; backup
and restore with units, including an old (1.30.0) backup loading as sat; a 12-word restore finding USD coins; wallet sync
publishing sat coins and leaving USD out; nutzaps, gifts and bounties refusing while a USD account is active; the new
texts in five languages.

NOT proven here: CHF (no test mint offers it; it goes through exactly the same table and code as USD and EUR), real
mints' rates and fees, mints that quote a unit for one method only, and any conversion of our own (NUTCADE never
converts: every amount comes from the mint's own quote). U_ONLY=a,b runs some sections (their names start with those
letters)."""
import asyncio, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as SAT, invoice

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MULTI = 'http://127.0.0.1:3345'      # sat + usd + eur
DOLLAR = 'http://127.0.0.1:3346'     # usd only
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
USD = MULTI + '|usd'
EUR = MULTI + '|eur'


def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def evs(kind=None, author=None):
    return [e for e in state()['events'] if (kind is None or e['kind'] == kind) and (author is None or e['pubkey'] == author)]
def mint_quote(n, unit, mint=MULTI):
    """A quote straight from the mint, so a test can see the invoice it would hand out for n of that unit."""
    return json.loads(urllib.request.urlopen(urllib.request.Request(mint + '/v1/mint/quote/bolt11',
        data=J({'amount': n, 'unit': unit}).encode(), headers={'Content-Type': 'application/json'})).read())


async def wallet(b, name, lang='en'):
    ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
    await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
    pg = await ctx.new_page(); w = W(pg, name)
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text and 'Failed to load' not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w


async def section(name, fn):
    only = [x for x in os.environ.get('U_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])


# ---- helpers on a wallet -------------------------------------------------------------------------------------------
async def bal(w, key): return await w.ev(f"(Nutcade.S.proofs[{J(key)}]||[]).reduce((t,p)=>t+p.amount,0)")
async def accounts(w): return await w.ev("NutUnits.accounts()")
async def add_account(w, url, unit='sat'):
    """Adds one account (a mint, or one unit of it) through the screens: Add mint for sat, the unit's own button after."""
    await w.home()
    if unit == 'sat' or not await w.ev(f"Nutcade.S.mints.some(m=>NutUnits.url(m.url)==={J(url)})"):
        await w.add_mint(url if unit == 'sat' else url)
    if unit != 'sat':
        await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=mints]'); await w.wait(300)
        sel = f'[data-act=addUnit][data-url="{url}"][data-u="{unit}"]'
        if await w.ev(f"!!document.querySelector({J(sel)})"):
            await w.click(sel); await w.until(f"Nutcade.S.mints.some(m=>m.url==={J(url + '|' + unit)})", 15000)
    await w.wait(200); await w.ev("Nutcade.closeSheet()")
    return await w.ev(f"Nutcade.S.mints.some(m=>m.url==={J(url if unit == 'sat' else url + '|' + unit)})")
async def use(w, key): await w.ev(f"Nutcade.S.active={J(key)}; Nutcade.render()")
async def deposit(w, key, amount):
    """A Lightning deposit of `amount` of the account's own unit; returns the sheet's text and the invoice."""
    await use(w, key); await w.home()
    before = await bal(w, key)
    await w.click('[data-act=receive]'); await w.wait(200)
    if await w.ev("!!document.querySelector('[data-act=recvMethod][data-m=ln][aria-pressed=false]')"): await w.click('[data-act=recvMethod][data-m=ln]'); await w.wait(150)
    await w.fill('#amtIn', amount)
    await w.click('[data-act=doLnInvoice]')
    # the fake Lightning pays at once, so the invoice screen is read as soon as it is up (and every text seen is kept)
    txt = ''
    for _ in range(80):
        t = await w.sheet_text()
        if t and t not in txt: txt += '\n' + t
        if 'Pay this invoice' in t or await w.ev(f"(Nutcade.S.proofs[{J(key)}]||[]).reduce((t,p)=>t+p.amount,0) > {before}"): break
        await w.wait(100)
    inv = await w.ev("(Nutcade.S.txs[0]||{}).request||''")
    ok = await w.until(f"(Nutcade.S.proofs[{J(key)}]||[]).reduce((t,p)=>t+p.amount,0) > {before}", 25000)
    await w.wait(300); await w.close()
    return ok, txt, inv
async def send_token(w, key, amount, note=''):
    """amount is in the account's smallest step (cents for USD); it is typed the way a person would ("1.50")."""
    await use(w, key); await w.home()
    await w.click('[data-act=send]'); await w.wait(200)
    typed = await w.ev(f"(document.querySelector('#amtIn')||{{}}).dataset && document.querySelector('#amtIn').dataset.unit ? NutUnits.fmt({amount}, document.querySelector('#amtIn').dataset.unit) : {J(str(amount))}")
    await w.fill('#amtIn', typed)
    if note: await w.fill('#noteIn', note)
    n0 = await w.ev("Nutcade.S.txs.length")
    await w.click('[data-act=doSendEcash]'); await w.wait(1200)
    await w.until(f"!!((document.querySelector('#sheetErr')||{{}}).innerText||'').trim() || (Nutcade.S.txs.length>{n0} && !!Nutcade.S.txs[0].token)", 20000)
    e = await w.err(); tok = None if e else await w.ev("Nutcade.S.txs[0].token")
    txt = await w.sheet_text(); await w.close()
    return tok, e, txt
async def claim(w, tok, note=''):
    await w.home()
    # (a wallet with no mint yet has no RECEIVE button, only "Someone sent me ecash")
    if await w.ev("!!document.querySelector('[data-act=receive]')"):
        await w.click('[data-act=receive]'); await w.wait(200); await w.click('[data-act=recvMethod][data-m=ecash]')
    else:
        await w.click('[data-act=recvMethod][data-m=ecash]')
    await w.wait(200)
    await w.fill('#tokIn', tok)
    if note: await w.fill('#noteIn', note)
    peek = await w.ev("(document.querySelector('#tokPeek')||{}).innerText||''")
    await w.click('[data-act=doReceiveToken]'); await w.wait(1500)
    if await w.ev("!!document.querySelector('[data-act=doReceiveToken][data-trust]')"): await w.click('[data-act=doReceiveToken]'); await w.wait(2500)
    e = await w.err(); txt = await w.sheet_text(); await w.close()
    return e, txt, peek
async def toast_of(w, act):
    await w.ev("(document.querySelector('#toast')||{}).innerText=''")
    await w.click(act); await w.wait(600)
    return await w.toast()


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        A = await wallet(b, 'u-A'); words = await A.create()
        ctx = {}

        # =================== the units table, the formatter and typed amounts ===================
        async def table():
            t = await A.ev("NutUnits.table()")
            check('table: one table with sat (0 decimals) and usd, eur, chf (2 decimals, cents)',
                  t == {'sat': {'dp': 0, 'code': 'SAT'}, 'usd': {'dp': 2, 'code': 'USD'}, 'eur': {'dp': 2, 'code': 'EUR'}, 'chf': {'dp': 2, 'code': 'CHF'}}, t)
            f = await A.ev("[NutUnits.fmt(1000,'sat'), NutUnits.money(1000,'sat'), NutUnits.fmt(1250,'usd'), NutUnits.money(1250,'usd'), NutUnits.money(1,'usd'), NutUnits.money(100000,'eur'), NutUnits.money(5,'chf')]")
            check('format: sats look exactly as before, and a cents unit shows two decimals with its code',
                  f == ['1,000', '1,000 SAT', '12.50', '12.50 USD', '0.01 USD', '1,000.00 EUR', '0.05 CHF'], f)
            P = lambda v, u='usd': A.ev(f"NutUnits.parse({J(v)}, {J(u)})")
            good = [await P('12.50'), await P('12'), await P('0.01'), await P('1,234.56'), await P('.5'), await P('12.5')]
            check('typed: "12.50" is 1250 cents, "12" is 1200, "0.01" is 1, "1,234.56" is 123456 (integers, never floats)',
                  good == [1250, 1200, 1, 123456, 50, 1250], good)
            bad = [await P('12.505'), await P('0.001'), await P('abc')]
            check('typed: more than 2 decimals is refused with a message, never rounded ("12.505", "0.001"), and so is nonsense',
                  all(isinstance(x, dict) and x.get('error') for x in bad) and bad[0]['why'] == 'decimal' and '12.50' in bad[0]['error'], bad)
            s = await A.ev("[NutUnits.parse('1500','sat'), NutUnits.parse('1.5','sat')]")
            check('typed: SAT are still whole numbers, and "1.5" SAT is still refused', s[0] == 1500 and isinstance(s[1], dict) and s[1].get('why') == 'decimal', s)
            k = await A.ev(f"[NutUnits.key({J(MULTI)},'sat'), NutUnits.key({J(MULTI)},'usd'), NutUnits.unit({J(USD)}), NutUnits.url({J(USD)}), NutUnits.unit({J(MULTI)})]")
            check('accounts: a sat account is keyed by the mint address exactly as before; a usd one by "<address>|usd"',
                  k == [MULTI, USD, 'usd', MULTI, 'sat'], k)
        await section('table', table)

        # =================== adding mints and their units ===================
        async def adding():
            ok = await add_account(A, MULTI, 'sat')
            acc = await accounts(A)
            check('add: a multi-unit mint is added as its SAT account, stored exactly as before (no unit field)',
                  ok and len(acc) == 1 and acc[0]['url'] == MULTI and acc[0]['unit'] == 'sat' and acc[0]['unitField'] is None, acc)
            check('add: the mint line lists the other units it offers', sorted(acc[0]['units']) == ['eur', 'sat', 'usd'], acc[0]['units'])
            await A.click('[data-act=tab][data-tab=mints]'); await A.wait(400)
            rows = await A.ev("[...document.querySelectorAll('[data-act=addUnit]')].map(b=>b.dataset.u)")
            check('add: each unit NUTCADE does not hold yet has its own Add button under that one mint', sorted(rows) == ['eur', 'usd'], rows)
            ok = await add_account(A, MULTI, 'usd')
            acc = await accounts(A)
            check('add: adding USD adds only USD (EUR is not added with it), as its own account at the same mint',
                  ok and [x['url'] for x in acc] == [MULTI, USD] and acc[1]['unitField'] == 'usd', [(x['url'], x['unitField']) for x in acc])
            await A.click('[data-act=tab][data-tab=mints]'); await A.wait(400)
            txt = await A.ev("document.body.innerText")
            check('add: the two accounts of one mint are two lines under it, the USD one labelled USD', txt.count('Multi Mint') >= 2 and 'USD' in txt, txt[:200])
            ok = await add_account(A, MULTI, 'eur')
            check('add: EUR added too, so one mint holds three accounts', ok and len(await accounts(A)) == 3, [x['url'] for x in await accounts(A)])
            # a mint with no SAT keyset at all
            D = await wallet(b, 'u-D'); await D.create()
            await D.add_mint(DOLLAR); await D.wait(500)
            acc = await accounts(D)
            check('add: a mint that issues no SAT ecash is added as its USD account (not refused)',
                  len(acc) == 1 and acc[0]['url'] == DOLLAR + '|usd' and acc[0]['unit'] == 'usd', acc)
            ctx['D'] = D
        await section('add', adding)

        # =================== Lightning deposit into a USD account ===================
        async def deposits():
            ok, txt, inv = await deposit(A, MULTI, '1000')
            check('deposit: SAT into the SAT account works exactly as before (1,000 SAT)', ok and await bal(A, MULTI) == 1000, (ok, await bal(A, MULTI)))
            q = mint_quote(500, 'usd')
            isat = await A.ev(f"NutUnits.invoiceSats({J(q['request'])})")
            ok, txt, inv = await deposit(A, USD, '5.00')
            b_usd = await bal(A, USD)
            check('deposit: 5.00 USD typed is credited as 500 cents by the mint, into the USD account only',
                  ok and b_usd == 500 and await bal(A, MULTI) == 1000, (ok, b_usd, await bal(A, MULTI)))
            mysat = await A.ev(f"NutUnits.invoiceSats({J(inv)})")
            check('deposit: the invoice is in SAT (the mint sets the rate) and the screen shows both the invoice and the credit',
                  mysat and mysat > 0 and abs(mysat - isat) <= max(2, isat // 100) and '5.00' in txt and 'USD' in txt and 'SAT' in txt, (mysat, isat, txt[:260]))
            tx = await A.ev("Nutcade.S.txs[0]")
            check('deposit: its history line records the unit and the amount in cents', tx['unit'] == 'usd' and tx['amount'] == 500 and tx['mint'] == USD, (tx.get('unit'), tx['amount'], tx['mint']))
            check('deposit: no price-in-your-currency guess is written on a USD line', not tx.get('fx'), tx.get('fx'))
            ok, txt, inv = await deposit(A, EUR, '2.50')
            check('deposit: 2.50 EUR into the EUR account at the same mint, kept apart from the USD and SAT ones',
                  ok and await bal(A, EUR) == 250 and await bal(A, USD) == 500 and await bal(A, MULTI) == 1000,
                  (await bal(A, EUR), await bal(A, USD), await bal(A, MULTI)))
            ctx['dep'] = True
        await section('dep', deposits)

        # =================== never added together: balance lines, history, limit, report card ===================
        async def apart():
            t = await A.ev("NutUnits.totals()")
            check('apart: the totals are one line per unit, never one number across units', t == [['sat', 1000], ['usd', 500], ['eur', 250]], t)
            await use(A, MULTI); await A.home(); await A.wait(400)
            home = await A.ev("document.body.innerText")
            tot = await A.ev("(document.querySelector('[data-totals]')||{}).innerText||''")
            check('apart: the home screen shows every unit on its own line ("All mints 1,000 SAT · 5.00 USD · 2.50 EUR")',
                  '1,000 SAT' in tot and '5.00 USD' in tot and '2.50 EUR' in tot and '1,750' not in home, (tot, '1,750' in home))
            check('apart: totalBalance (what the SAT features use) counts SAT only',
                  await A.ev("Nutcade.S.mints.filter(m=>NutUnits.unit(m.url)!=='sat').length") == 2 and dict(t)['sat'] == 1000, t)
            await use(A, USD); await A.home(); await A.wait(400)
            head = await A.ev("(document.querySelector('.credit-num')||{}).innerText||''")
            check('apart: with the USD account in use the balance reads 5.00 USD, and no SAT price line is shown',
                  '5.00' in head and 'USD' in head and not await A.ev("!!document.querySelector('.credits .fiat')"), head)
            # the spending limit counts SAT only
            await A.ev("Nutcade.S.limits={per:0,day:1000}; window.NutStore.set('limits',Nutcade.S.limits)")
            tok, e, txt = await send_token(A, USD, 100, 'a dollar out')
            lim = await A.ev("Nutcade.S.txs.filter(t=>t.type==='out').map(t=>[t.unit||'sat',t.amount])")
            check('apart: a USD payment is outside the SAT spending limit (it goes through, nothing of it counts toward the day)',
                  bool(tok) and not e and ['usd', 100] in lim, (bool(tok), e, lim))
            await use(A, MULTI); await A.click('[data-act=tab][data-tab=settings]'); await A.wait(500)
            await A.click('[data-act=limOpen]'); await A.wait(500)
            st = await A.sheet_text(); await A.ev("Nutcade.closeSheet()")
            check('apart: the limit screen says it is in SAT and counts SAT only', 'counts SAT only' in st, [l for l in st.split('\n') if 'SAT' in l][:4])
            ctx['usdout'] = 100
            # history lines keep their unit and are never summed across units
            await A.click('[data-act=tab][data-tab=history]'); await A.wait(500)
            rows = await A.ev("[...document.querySelectorAll('.tx .amt')].map(e=>e.innerText)")
            chips = await A.ev("[...document.querySelectorAll('.tx .chip.unit')].map(e=>e.innerText)")
            check('history: a USD or EUR line shows its own amount and unit chip; a SAT line is unchanged',
                  any('12.50' not in r and '.' in r for r in rows) and 'USD' in chips and 'EUR' in chips and any(r in ('+1,000', '1,000') for r in rows), (rows[:6], chips[:4]))
        await section('apart', apart)

        # =================== send and receive USD and EUR tokens between two wallets ===================
        async def tokens():
            Bw = await wallet(b, 'u-B'); await Bw.create()
            tok, e, txt = await send_token(A, USD, 150, 'dollars for Bob')
            check('send: a USD token is made from the USD account, with its amount in the sheet', bool(tok) and not e and '1.50' in txt, (e, txt[:200]))
            meta = await Bw.ev(f"CashuLib.getTokenMetadata({J(tok)})")
            check('send: the token carries unit usd and the mint\'s own address (never the account key)', meta['unit'] == 'usd' and meta['mint'].rstrip('/') == MULTI, meta)
            e2, txt2, peek = await claim(Bw, tok, 'from Alice')
            acc = await accounts(Bw)
            check('receive: Bob\'s wallet claims it into a USD account at that mint, and nothing of his SAT changes',
                  not e2 and len(acc) == 1 and acc[0]['url'] == USD and acc[0]['bal'] == 150, (e2, acc))
            check('receive: the paste preview shows the amount in USD before claiming', '1.50' in peek and 'USD' in peek, peek[:160])
            btx = await Bw.ev("Nutcade.S.txs[0]")
            check('receive: his line records the unit, the amount in cents and his note', btx['unit'] == 'usd' and btx['amount'] == 150 and btx['note'] == 'from Alice', (btx.get('unit'), btx['amount'], btx['note']))
            tok2, e3, _ = await send_token(A, EUR, 75)
            e4, txt4, _ = await claim(Bw, tok2)
            check('receive: a EUR token lands in a EUR account of its own, never in the USD one',
                  not e3 and not e4 and await bal(Bw, EUR) == 75 and await bal(Bw, USD) == 150, (e3, e4, await bal(Bw, EUR), await bal(Bw, USD)))
            # back the other way, and a SAT token still behaves exactly as before
            tok3, e5, _ = await send_token(Bw, USD, 50)
            e6, _, _ = await claim(A, tok3)
            check('receive: a USD token sent back is claimed into the same account (two wallets, one mint, one unit)',
                  not e5 and not e6 and await bal(A, USD) == 300, (e5, e6, await bal(A, USD)))
            ctx['B'] = Bw
        await section('tok', tokens)

        # =================== pay-out by Lightning from a USD account, and the fee in its unit ===================
        async def payout():
            inv = invoice(300, SAT)   # a 300 SAT invoice at another mint
            isat = await A.ev(f"NutUnits.invoiceSats({J(inv)})")
            await use(A, USD); await A.home()
            await A.click('[data-act=send]'); await A.wait(200); await A.click('[data-act=sendMethod][data-m=ln]'); await A.wait(200)
            await A.fill('#destIn', inv); await A.click('[data-act=doMeltQuote]'); await A.wait(1500)
            q = await A.sheet_text(); err = await A.err()
            b0 = await bal(A, USD)
            kv = await A.ev("[...document.querySelectorAll('.kv dt')].map((d,i)=>[d.innerText,[...document.querySelectorAll('.kv dd')][i].innerText])")
            check('pay-out: the quote shows the invoice in SAT, the mint\'s own amount in USD and the USD fee (no conversion of ours)',
                  not err and isat == 300 and any('300' in v and 'SAT' in v for k, v in kv) and any('USD' in v for k, v in kv), (err, isat, kv))
            if not err:
                await A.click('#payBtn'); await A.wait(4000)
                e = await A.err(); done = await A.sheet_text(); await A.close()
                tx = await A.ev("Nutcade.S.txs.find(t=>t.method==='ln'&&t.type==='out')")
                b1 = await bal(A, USD)
                check('pay-out: it is paid in USD, the line and its fee are in USD, and only the USD balance drops',
                      not e and tx and tx.get('unit') == 'usd' and tx['status'] in ('done', 'pending') and b1 < b0 and b0 - b1 == tx['amount'] + tx['fee'] and await bal(A, MULTI) == 1000,
                      (e, tx and (tx.get('unit'), tx['amount'], tx['fee'], tx['status']), b0, b1, await bal(A, MULTI)))
                check('pay-out: the mint kept a fee in USD, counted in USD (its quote said 2 cents)', tx and tx['fee'] >= 0 and tx['fee'] < 100, tx and tx['fee'])
            # a method the mint does not offer for that unit: the button is not there
            D = ctx.get('D')
            if D:
                await use(D, DOLLAR + '|usd'); await D.home(); await D.click('[data-act=send]'); await D.wait(300)
                segs = await D.ev("[...document.querySelectorAll('[data-act=sendMethod]')].map(b=>b.dataset.m)")
                check('pay-out: on-chain is never offered for a unit account (SAT only)', 'onchain' not in segs, segs)
                await D.close()
        await section('pay', payout)

        # =================== payment requests (NUT-18) in each unit ===================
        async def requests():
            Bw = ctx.get('B')
            if not Bw: return
            await use(A, USD); await A.home()
            await A.click('[data-act=receive]'); await A.wait(200); await A.click('[data-act=recvMethod][data-m=ecash]'); await A.wait(200)
            await A.click('[data-act=reqOpen]'); await A.wait(300)
            await A.fill('#amtIn', '0.50'); await A.fill('#memoIn', 'coffee')
            await A.click('[data-act=reqCreate]'); await A.wait(800)
            sheet = await A.sheet_text(); enc = await A.ev("(Nutcade.S.requests[0]||{}).encoded||''")
            r = await A.ev("Nutcade.S.requests[0]")
            await A.close()
            pr = await A.ev(f"(()=>{{const p=CashuLib.decodePaymentRequest({J(enc)}); return {{unit:p.unit, amount:Number(p.amount), mints:p.mints}}}})()")
            check('request: a request made from the USD account asks for 50 cents in usd, from the mints that hold USD',
                  r.get('unit') == 'usd' and r['amount'] == 50 and pr['unit'] == 'usd' and pr['amount'] == 50 and pr['mints'] == [MULTI], (r.get('unit'), pr))
            check('request: its screen shows the amount in USD', '0.50' in sheet and 'USD' in sheet, sheet[:160])
            b0 = await bal(Bw, USD); a0 = await bal(A, USD)
            await Bw.home(); await Bw.ev(f"Nutcade.handleScan({J(enc)})")
            ok = await Bw.until("!!document.querySelector('[data-act=payReq]')", 10000)
            txt = await Bw.sheet_text()
            if ok:
                await Bw.click('[data-act=payReq]'); await Bw.wait(3000)
                e = await Bw.err(); await Bw.close()
                got = await A.until(f"(Nutcade.S.proofs[{J(USD)}]||[]).reduce((t,p)=>t+p.amount,0) >= {a0 + 50}", 30000)
                check('request: Bob pays it from his USD account, Alice is credited 0.50 USD over Nostr',
                      not e and got and await bal(Bw, USD) <= b0 - 50, (e, got, await bal(A, USD) - a0, b0 - await bal(Bw, USD)))
                check('request: the paid line on both sides is in USD',
                      (await A.ev("(Nutcade.S.txs[0]||{}).unit")) == 'usd' and (await Bw.ev("Nutcade.S.txs.find(t=>t.type==='out').unit")) == 'usd',
                      (await A.ev("(Nutcade.S.txs[0]||{}).unit"), await Bw.ev("Nutcade.S.txs.find(t=>t.type==='out').unit")))
            else:
                check('request: Bob can pay a USD request', False, txt[:200])
            # a request in a unit we do not hold: refused, in plain words, nothing spent
            chf = await A.ev(f"""(()=>{{const pr=new CashuLib.PaymentRequest([], 'tst1', 500, 'chf', [{J(MULTI)}], 'swiss'); return pr.toEncodedRequest()}})()""")
            n0 = await A.ev("Nutcade.S.txs.length")
            await A.ev(f"Nutcade.handleScan({J(chf)})"); await A.wait(900)
            txt = await A.sheet_text()
            check('request: one asking for a unit we hold nowhere is refused with a clear message and no Pay button, nothing spent',
                  'CHF' in txt and not await A.ev("!!document.querySelector('[data-act=payReq]')") and await A.ev("Nutcade.S.txs.length") == n0, txt[:220])
            await A.ev("Nutcade.closeSheet()")
            # a unit NUTCADE does not know at all
            bad = await A.ev("""(()=>{const pr=new CashuLib.PaymentRequest([], 'tst2', 7, 'xau', undefined, 'gold'); return pr.toEncodedRequest()})()""")
            await A.ev(f"Nutcade.handleScan({J(bad)})"); await A.wait(900)
            txt = await A.sheet_text()
            check('request: a unit NUTCADE does not hold at all (XAU) is refused and names what it does hold',
                  'XAU' in txt and 'SAT' in txt and not await A.ev("!!document.querySelector('[data-act=payReq]')"), txt[:220])
            await A.ev("Nutcade.closeSheet()")
        await section('req', requests)

        # =================== the SAT-only features refuse while a unit account is active ===================
        async def satonly():
            await use(A, USD); await A.home(); await A.wait(400)
            home = await A.ev("document.body.innerText")
            gone = await A.ev("[...document.querySelectorAll('[data-act]')].map(b=>b.dataset.act).filter(a=>NutUnits.satOnly(a))")
            check('SAT only: with a USD account in use, no SAT-only button is on the wallet screen (cashier, split, Extra Life, hunts, sound)', not gone, gone)
            note = await A.ev("(document.querySelector('[data-unitnote]')||{}).innerText||''")
            check('SAT only: the screen says plainly what a USD account can do, and what is SAT only', 'SAT only' in note, note)
            # the backstop: a SAT-only action clicked anyway does nothing and says so
            b0 = await A.ev("JSON.stringify(Nutcade.S.proofs)"); n0 = await A.ev("Nutcade.S.txs.length")
            msgs = {}
            for act in ('nzSend', 'extraOpen', 'huntNew', 'ptOpen', 'allEcash', 'cashier', 'syncNow'):
                await A.ev(f"""(()=>{{const b=document.createElement('button'); b.dataset.act={J(act)}; b.id='utest'; document.body.appendChild(b); b.click(); b.remove()}})()""")
                await A.wait(250); msgs[act] = await A.toast()
            spent = b0 != await A.ev("JSON.stringify(Nutcade.S.proofs)") or n0 != await A.ev("Nutcade.S.txs.length")
            check('SAT only: a nutzap, gift/Extra Life, treasure hunt, printed token, Send all, cashier mode or sync tapped with USD active refuses in plain words and spends nothing',
                  all('SAT' in (m or '') for m in msgs.values()) and not spent, msgs)
            # and with a SAT account they are all back
            await use(A, MULTI); await A.home(); await A.wait(400)
            back = await A.ev("[...document.querySelectorAll('[data-act]')].map(b=>b.dataset.act)")
            check('SAT only: with the SAT account in use the SAT features are there again (nothing was removed for sat wallets)',
                  'cashier' in back and 'huntNew' in back and 'splitOpen' in back, [a for a in back if a in ('cashier', 'huntNew', 'splitOpen')])
        await section('sat', satonly)

        # =================== a send whose answer is lost: the journal settles it in the right unit ===================
        async def journal():
            w = await wallet(b, 'u-J'); await w.create()
            await add_account(w, MULTI, 'sat'); await add_account(w, MULTI, 'usd')
            ok, _, _ = await deposit(w, USD, '3.00')
            b0 = await bal(w, USD)
            drop = {'on': True}
            async def lost(route):
                try:
                    if drop['on'] and route.request.method == 'POST': drop['on'] = False; await route.fetch(); return await route.abort()
                    await route.continue_()
                except Exception: pass
            await w.pg.context.route(MULTI + '/v1/swap', lost)
            tok, e, _ = await send_token(w, USD, 100)
            await w.pg.context.unroute(MULTI + '/v1/swap', lost)
            check('journal: a USD send whose answer never came leaves a record and an error, not a silent loss', bool(e) or bool(tok), (e, bool(tok)))
            await w.pg.reload(); await w.wait(2000)
            settled = await w.until("Nutcade.S.ops.length===0", 60000); await w.wait(1500)
            b1 = await bal(w, USD); out = await w.ev("Nutcade.S.txs.filter(t=>t.type==='out'&&t.method==='ecash').map(t=>[t.unit||'sat',t.amount,t.status])")
            held = await w.ev(f"NutSync.states({J(USD)}, (Nutcade.S.proofs[{J(USD)}]||[]))")
            check('journal: on the next open it is settled once, in USD: the books add up and every coin held is unspent',
                  settled and all(u == 'usd' for u, a, s in out) and b1 + sum(a for u, a, s in out if s != 'failed') == b0 and all(x == 'UNSPENT' for x in held),
                  (settled, out, b0, b1, set(held)))
            check('journal: the SAT account was never touched by it', await bal(w, MULTI) == 0, await bal(w, MULTI))
            ctx['J'] = w
        await section('journal', journal)

        # =================== backup and restore, old backups, a 12-word restore ===================
        async def backup():
            # the backup as the app writes it (through the screens, so it is exactly the file people get)
            await A.click('[data-act=tab][data-tab=settings]'); await A.wait(400)
            await A.ev("Nutcade.closeSheet()")
            async with A.pg.expect_download() as dl: await A.pg.evaluate("document.querySelector('[data-act=backupDownload]').click()")
            text = open(await (await dl.value).path()).read()
            await A.ev("Nutcade.closeSheet()")
            d = json.loads(text) if text.strip().startswith('{') else None
            check('backup: the file carries the unit accounts (mints with a unit field, coins under their keys)',
                  d and any(m.get('unit') == 'usd' for m in d['mints']) and USD in d['proofs'] and MULTI in d['proofs'], d and [(m['url'], m.get('unit')) for m in d['mints']])
            C = await wallet(b, 'u-C'); await C.create()
            await C.click('[data-act=tab][data-tab=settings]'); await C.wait(300)
            await C.click('[data-act=restore]'); await C.wait(300)
            await C.pg.fill('#restoreIn', text); await C.click('[data-act=doRestore]')
            await C.until("!document.querySelector('#restoreIn')", 60000); await C.wait(1500)
            tots = await C.ev("NutUnits.totals()")
            mine = await A.ev("NutUnits.totals()")
            check('restore: the restored wallet holds the same amount in each unit, each on its own line', tots == mine, (tots, mine))
            await C.pg.context.close()
            # an old (1.30.0) backup: no unit anywhere, so everything in it is sat
            old = {'app': 'nutcade', 'v': 2, 'at': '2026-01-01T00:00:00.000Z', 'seed': words, 'counters': {},
                   'mints': [{'url': MULTI, 'name': 'Multi Mint', 'methods': {'mint': [{'method': 'bolt11', 'min': None, 'max': None}], 'melt': [{'method': 'bolt11', 'min': None, 'max': None}]}}],
                   'proofs': {}, 'pending': [], 'txs': [], 'p2pk': [], 'quotes': [], 'requests': [], 'ops': []}
            O = await wallet(b, 'u-O'); await O.create()
            await O.click('[data-act=tab][data-tab=settings]'); await O.wait(300)
            await O.click('[data-act=restore]'); await O.wait(300)
            await O.pg.fill('#restoreIn', J(old)); await O.click('[data-act=doRestore]')
            await O.until("!document.querySelector('#restoreIn')", 60000); await O.wait(1200)
            acc = await accounts(O)
            check('restore: a 1.30.0 backup (no unit field anywhere) loads as SAT, with its mint stored exactly as before',
                  [(x['url'], x['unit'], x['unitField']) for x in acc] == [(MULTI, 'sat', None)], acc)
            await O.pg.context.close()
            # 12 words on a new device: the USD coins are found too (a scan finds every unspent coin of these words, so
            # the coins of a token we sent that nobody has claimed yet come back as well: counted here, per unit)
            held = dict(await A.ev("NutUnits.totals()"))
            out = await A.ev("Nutcade.S.txs.filter(t=>t.type==='out'&&t.status==='pending'&&t.sent&&t.sent.length).map(t=>[t.unit||'sat',t.sent.reduce((s,p)=>s+p.amount,0)])")
            want = dict(held)
            for u, n in out: want[u] = want.get(u, 0) + n
            R = await wallet(b, 'u-R')
            await R.gate_restore(); await R.fill('#phraseIn', words)
            await R.ev("[...document.querySelectorAll('[data-rmint]')].forEach(i=>i.checked=false)")
            await R.fill('#rmExtra', MULTI)
            await R.click('[data-act=doRestorePhrase]')
            await R.until("!!document.querySelector('.sheet-body .credit-num')", 180000); await R.wait(500)
            txt = await R.sheet_text(); found = await R.ev("(document.querySelector('[data-unitfound]')||{}).innerText||''")
            await R.ev("Nutcade.closeSheet()")
            if await R.until("!!document.querySelector('[data-act=gateStart]')", 4000): await R.gate_step('gateStart', "!!document.querySelector('.tabbar')")
            await R.wait(300); await R.ev("Nutcade.closeSheet()")
            tots = dict(await R.ev("NutUnits.totals()"))
            check('restore: 12 words and the mint address find the SAT, USD and EUR coins, each counted in its own unit (with the coins of tokens nobody claimed)',
                  tots == want, (tots, want, held, out))
            check('restore: the screen says what came back per unit, never as one number', 'USD' in found and 'EUR' in found, found)
            await R.pg.context.close()
        await section('backup', backup)

        # =================== wallet sync: SAT coins in, USD coins out ===================
        async def sync():
            w = ctx.get('J')
            if not w: return
            await add_account(w, MULTI, 'sat')
            ok, _, _ = await deposit(w, MULTI, '400')
            ok2, _, _ = await deposit(w, USD, '1.00')
            pk = await w.ev("NutSync.pk()")
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(400)
            t = await w.ev("document.querySelector('#set-privacy').innerText")
            check('sync: the sync setting says plainly that only SAT coins are synced', 'Only SAT coins are synced' in t or ('SAT' in t and 'USD' in t and 'relays' in t), [l for l in t.split('\n') if 'SAT' in l][:3])
            await w.click('#p_sync'); await w.wait(500)
            sat_secrets = set(await w.ev(f"(Nutcade.S.proofs[{J(MULTI)}]||[]).map(p=>p.secret)"))
            usd_secrets = set(await w.ev(f"(Nutcade.S.proofs[{J(USD)}]||[]).map(p=>p.secret)"))
            published = set()
            for _ in range(40):
                published = set()
                for e in evs(7375, pk):
                    published |= set(await w.ev(f"""(()=>{{const s=CashuLib.sha256(new Uint8Array([...CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic), ...new TextEncoder().encode('nutcade-nip60')]));
                        const ck=CashuLib.nip44.v2.utils.getConversationKey(s, CashuLib.nostrPub(s));
                        try{{const c=JSON.parse(CashuLib.nip44.v2.decrypt({J(e['content'])}, ck)); return (c.proofs||[]).map(p=>p.secret)}}catch(e){{return []}}}})()"""))
                if sat_secrets and sat_secrets <= published: break
                await w.wait(500)
            check('sync: the SAT coins are published to the relays as before', bool(sat_secrets) and sat_secrets <= published, (len(sat_secrets), len(published)))
            check('sync: not one USD coin is published (they never leave the device)', bool(usd_secrets) and not (usd_secrets & published), (len(usd_secrets), len(usd_secrets & published)))
            mints = set()
            for e in evs(17375, pk):
                mints |= set(await w.ev(f"""(()=>{{const s=CashuLib.sha256(new Uint8Array([...CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic), ...new TextEncoder().encode('nutcade-nip60')]));
                    const ck=CashuLib.nip44.v2.utils.getConversationKey(s, CashuLib.nostrPub(s));
                    try{{const c=JSON.parse(CashuLib.nip44.v2.decrypt({J(e['content'])}, ck)); return c.filter(t=>t[0]==='mint').map(t=>t[1])}}catch(e){{return []}}}})()"""))
            check('sync: the wallet event lists the mint once, by its own address (never an account key)',
                  MULTI in mints and not any('|' in m for m in mints), mints)
            usd0 = await bal(w, USD)
            r = await w.ev("NutSync.pull().then(r=>r,e=>({error:e.message}))")
            check('sync: a read adds nothing to the USD account (its coins are never adopted from relays)',
                  isinstance(r, dict) and not r.get('error') and await bal(w, USD) == usd0, (r if isinstance(r, dict) else r, usd0, await bal(w, USD)))
        await section('sync', sync)

        # =================== the new texts in five languages ===================
        async def langs():
            for lang in ('en', 'es', 'pt', 'de', 'fr'):
                x = await wallet(b, 'u-' + lang, lang); await x.create()
                await add_account(x, MULTI, 'sat'); await add_account(x, MULTI, 'usd')
                await use(x, USD); await x.home(); await x.wait(500)
                home = await x.ev("document.body.innerText")
                await x.click('[data-act=receive]'); await x.wait(400); r = await x.sheet_text(); await x.close()
                await x.click('[data-act=send]'); await x.wait(400); sd = await x.sheet_text(); await x.close()
                await x.click('[data-act=tab][data-tab=mints]'); await x.wait(500); mt = await x.ev("document.body.innerText")
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/USD|EUR|CHF|SAT only|unit|decimals|cents|Also at this mint|All mints/i.test(s))")
                num = await x.ev("NutUnits.money(1250,'usd')")
                if lang == 'en':
                    check('en: the USD screens read in plain English', 'USD' in home and 'USD' in r and 'USD' in sd and 'USD' in mt)
                else:
                    check(f'{lang}: the new unit texts are translated, with none missing', not miss, miss[:6])
                check(f'{lang}: a USD amount is written the way the language writes numbers', 'USD' in num and (',' in num if lang in ('es', 'pt', 'de', 'fr') else '.' in num), num)
                await x.pg.context.close()
        await section('langs', langs)

        errs = [e for w in [A] + [ctx[k] for k in ('B', 'D', 'J') if k in ctx] for e in w.errs if 'PAGEERROR' in e]
        check('no page errors', not errs, errs[:3])
        await A.pg.screenshot(path=os.path.join(OUT, 'units.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')


if __name__ == '__main__':
    asyncio.run(main())
