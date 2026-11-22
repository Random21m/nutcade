"""Unclaimed-token reminders (1.27.0): "N tokens you sent are still unclaimed — take them back?" on the wallet screen.
Uses the local test mint 3339 (no fees) and a second wallet that claims some of the tokens.

Fresh tokens are not counted; tokens older than 30 days are, with their total; gifts, treasure hunts, bounties, payments
for a request and incoming tokens never are; a token its mint is retiring the keys of (inactive, expiring within 7 days,
or no longer listed) is counted at any age and marked; the background check marks a token claimed meanwhile as claimed;
Later hides the line (7 days, 1 day with retiring keys) and a token whose keys start retiring after that shows it again;
Take them back uses the usual take-back (balance up, lines marked taken back) and one someone claimed first is said so and
changes nothing; the setting turns it off; tokens locked to a key, the duress wallet's sats, a take-back still open in the
journal, coins already saved to claim in parts and partly claimed tokens are never counted; one failing check doesn't stop
the rest; the new texts in five languages with no missing translation.
RM_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as A   # (the mint without fees, so amounts are exact)

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
DAY = 86400000

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
    only = [x for x in os.environ.get('RM_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def age(w, tid, days):
    await w.ev(f"(()=>{{const t=Nutcade.S.txs.find(t=>t.id==={J(tid)}); t.ts=Date.now()-{days}*{DAY}; Nutcade.refresh()}})()"); await w.wait(150)
async def panel(w):
    await w.home(); await w.ev("Nutcade.refresh()"); await w.wait(150)
    return await w.ev("(()=>{const p=document.querySelector('.rm-ask'); return p?{n:+p.dataset.n, text:p.innerText, rows:p.querySelectorAll('.rm-row').length, soon:p.querySelectorAll('.rm-soon').length}:null})()")
# the mint's keysets as the app sees them, changed for a moment (k: a keyset; return the changed copy)
async def keys_as(w, js):
    await w.ev(f"""(()=>{{const x=NutRemind.wallet({J(A)}); const kc=x.keyChain; if(!kc.__orig) kc.__orig=kc.getKeysets.bind(kc);
        kc.getKeysets=()=>kc.__orig().map(k=>{{const o={{id:k.id, unit:k.unit, isActive:k.isActive, expiry:k.expiry, fee:k.fee, hasHexId:k.hasHexId, hasKeys:k.hasKeys}}; return ((k)=>{{ {js}; return k }})(o)}})}})()""")
async def keys_back(w): await w.ev(f"(()=>{{const kc=NutRemind.wallet({J(A)}).keyChain; if(kc.__orig){{kc.getKeysets=kc.__orig; delete kc.__orig}}}})()")
async def tx(w, tid): return await w.ev(f"(()=>{{const t=Nutcade.S.txs.find(t=>t.id==={J(tid)}); return t?{{status:t.status}}:null}})()")

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w = await wallet(b, 'rm-send'); await w.create(); await w.add_mint(A); await w.use(A)
        fr = await wallet(b, 'rm-friend'); await fr.create(); await fr.add_mint(A); await fr.use(A)
        ok = await w.receive_ln(6000)
        check('setup: the wallet has sats to send', ok)
        ids = {}
        for k, amt in (('t1', 100), ('t2', 200), ('t3', 300), ('t4', 400), ('t5', 500)):
            tok, e = await w.send_ecash(amt, 'note ' + k)
            ids[k] = await w.ev("Nutcade.S.txs[0].id"); ids[k + 'tok'] = tok
        check('setup: five tokens sent', all(ids.get(k + 'tok') for k in ('t1', 't2', 't3', 't4', 't5')), list(ids))
        await w.ev("Nutcade.S.prefs.checkSent=false")   # (the background check is run by hand below)

        async def fresh():
            check('fresh: tokens sent today are not counted', await w.ev("NutRemind.due().length") == 0)
            check('fresh: no reminder on the wallet screen', await panel(w) is None)
        await section('fresh', fresh)

        async def old():
            await age(w, ids['t1'], 31); await age(w, ids['t2'], 45); await age(w, ids['t4'], 29)
            d = await w.ev("NutRemind.due()")
            check('old: tokens older than 30 days are counted, a 29-day-old one is not', sorted(x['id'] for x in d) == sorted([ids['t1'], ids['t2']]), d)
            pn = await panel(w)
            check('old: the wallet screen says "2 tokens you sent are still unclaimed — take them back?"', pn and pn['n'] == 2 and '2 tokens you sent are still unclaimed — take them back?' in pn['text'], pn)
            check('old: with their total (300 SAT) and both listed, none marked retiring', pn and '300 SAT in all' in pn['text'] and pn['rows'] == 2 and pn['soon'] == 0, pn)
            check('old: it says that taking back cancels the token', pn and 'can no longer claim it' in pn['text'], pn)
        await section('old', old)

        async def kinds():
            r = await w.ev("""(()=>{const base={type:'out',method:'ecash',status:'pending',token:'cashuBx',ts:1};
                const o=x=>NutRemind.open(Object.assign({},base,x));
                return {plain:o({}), gift:o({lockUntil:5}), giftTo:o({giftTo:'Ann'}), hunt:o({hunt:'h'}), bounty:o({bounty:1}), req:o({reqPay:{req:'x'}}), locked:o({locked:'02'+'a'.repeat(64)}), duress:o({duressFund:true}), duressNote:o({note:'Sats for the duress PIN wallet'}), part:o({rmPart:true}), incoming:o({incoming:true}), claimed:o({status:'claimed'}), reclaimed:o({status:'reclaimed'}), ln:o({method:'ln'}), notoken:o({token:''})}})()""")
            check('kinds: an ordinary sent token counts', r['plain'], r)
            check('kinds: gifts, treasure hunts, bounties, request payments, locked tokens, the duress wallet\'s sats, partly claimed, incoming, claimed, taken back, Lightning and tokenless lines never count',
                  not any(v for k, v in r.items() if k != 'plain'), r)
            t4 = J(ids['t4'])
            r2 = await w.ev(f"""(()=>{{const S=Nutcade.S, t=S.txs.find(t=>t.id==={t4}), was=NutRemind.open(t);
                S.ops.push({{id:'rmop', kind:'receive', mint:t.mint, own:t.id, inputs:[]}}); const op=NutRemind.open(t); S.ops=S.ops.filter(o=>o.id!=='rmop');
                const tok=CashuLib.getEncodedToken({{mint:t.mint, proofs:t.sent}}); S.txs.push({{id:'rmheld', type:'in', method:'ecash', status:'pending', incoming:tok, amount:t.amount, mint:t.mint, ts:Date.now()}});
                const held=NutRemind.open(t); S.txs=S.txs.filter(x=>x.id!=='rmheld'); return {{was, op, held, after:NutRemind.open(t)}}}})()""")
            check('kinds: a token whose take-back is still open in the journal is not counted', r2['was'] and not r2['op'] and r2['after'], r2)
            check('kinds: a token whose coins already wait in saved lines (a take-back in parts) is not counted', not r2['held'], r2)
        await section('kinds', kinds)

        async def claimed_meanwhile():
            _, e, _ = await fr.receive_token(ids['t2tok'])
            check('claimed: the friend claims one of the old tokens', not e, e)
            await w.ev("Nutcade.S.prefs.checkSent=true"); await w.ev(f"NutRemind.check({J(A)})"); await w.ev("Nutcade.S.prefs.checkSent=false"); await w.wait(300)
            check('claimed: the background check marks it claimed', (await tx(w, ids['t2']))['status'] == 'claimed', await tx(w, ids['t2']))
            pn = await panel(w)
            check('claimed: the reminder now says "1 token you sent is still unclaimed — take it back?"', pn and pn['n'] == 1 and '1 token you sent is still unclaimed — take it back?' in pn['text'], pn)
            check('claimed: and offers "Take it back"', pn and 'take it back' in pn['text'].lower().split('\n')[-2], pn)
        await section('claimed', claimed_meanwhile)

        async def later():
            await w.click('[data-act=rmLater]'); await w.wait(200)
            check('later: Later hides the reminder', await panel(w) is None)
            lt = await w.ev("Nutcade.S.prefs.rmLater")
            check('later: for 7 days', lt and 6.9 * DAY < lt['until'] - await w.ev("Date.now()") <= 7 * DAY, lt)
            check('later: it comes back after that', ids['t1'] in await w.ev(f"NutRemind.shown(Date.now()+7*{DAY}+1000)") and not await w.ev(f"NutRemind.shown(Date.now()+7*{DAY}-60000).length"))
        await section('later', later)

        async def retiring():
            await keys_as(w, "k.isActive=false")
            d = await w.ev("NutRemind.due()")
            check('retiring: with the keys inactive, every open token counts at any age', sorted(x['id'] for x in d) == sorted([ids['t1'], ids['t3'], ids['t4'], ids['t5']]) and all(x['soon'] for x in d), d)
            pn = await panel(w)
            check('retiring: a token whose keys start retiring shows the reminder again at once, despite Later', pn and pn['n'] == 4, pn)
            check('retiring: each is marked KEYS RETIRING and the warning says the sats would be lost', pn and pn['soon'] == 4 and 'lost for everyone' in pn['text'], pn)
            await w.click('[data-act=rmLater]'); await w.wait(200)
            lt = await w.ev("Nutcade.S.prefs.rmLater")
            check('retiring: Later now hides it for 1 day only', lt and lt['until'] - await w.ev("Date.now()") <= DAY and await panel(w) is None, lt)
            await keys_as(w, f"k.expiry=Math.floor((Date.now()+3*{DAY})/1000)")
            d = await w.ev("NutRemind.due()")
            check('retiring: keys expiring within 7 days count as retiring', len(d) == 4 and all(x['soon'] for x in d), d)
            await keys_as(w, f"k.expiry=Math.floor((Date.now()+30*{DAY})/1000)")
            d = await w.ev("NutRemind.due()")
            check('retiring: keys expiring in 30 days do not', sorted(x['id'] for x in d) == [ids['t1']] and not d[0]['soon'], d)
            await keys_as(w, "k.id='00ffffffffffffff'")
            d = await w.ev("NutRemind.due()")
            check('retiring: keys the mint no longer lists count as retiring', len(d) == 4 and all(x['soon'] for x in d), d)
            await keys_back(w)
            check('retiring: back to normal, only the old token counts', [x['id'] for x in await w.ev("NutRemind.due()")] == [ids['t1']])
        await section('retiring', retiring)

        async def take():
            await age(w, ids['t3'], 40); await age(w, ids['t5'], 40)
            _, e, _ = await fr.receive_token(ids['t5tok'])   # (claimed, but this wallet hasn't checked yet)
            check('take: the friend claims another old token (not checked yet here)', not e, e)
            await w.ev("Nutcade.S.prefs.rmLater=null")
            pn = await panel(w)
            check('take: three tokens are shown', pn and pn['n'] == 3, pn)
            before = await w.bal()
            await w.click('[data-act=rmTake]')
            await w.until(f"['reclaimed','claimed'].includes((Nutcade.S.txs.find(t=>t.id==={J(ids['t5'])})||{{}}).status) && (Nutcade.S.txs.find(t=>t.id==={J(ids['t3'])})||{{}}).status==='reclaimed'", 30000); await w.wait(800)
            st = {k: (await tx(w, ids[k]))['status'] for k in ('t1', 't3', 't5', 't4')}
            check('take: the two unclaimed ones are taken back', st['t1'] == 'reclaimed' and st['t3'] == 'reclaimed', st)
            check('take: the one claimed first is marked claimed', st['t5'] == 'claimed', st)
            check('take: the 29-day-old one is left alone', st['t4'] == 'pending', st)
            after = await w.bal()
            check('take: the balance went up by the two tokens taken back (400 SAT), nothing for the claimed one', after - before == 400, (before, after))
            lines = await w.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&/^Reclaimed: note t[135]/.test(t.note||'')).map(t=>t.note)")
            check('take: one "Reclaimed" line for each token taken back', sorted(lines) == ['Reclaimed: note t1', 'Reclaimed: note t3'], lines)
            check('take: nothing left to remind about', await panel(w) is None)
            check('take: no page errors', not w.errs, w.errs[:3])
        await section('take', take)

        async def setting():
            await age(w, ids['t4'], 31)
            check('setting: an old token shows the reminder', (await panel(w) or {}).get('n') == 1)
            await w.click('[data-act=tab][data-tab=settings]'); await w.wait(200)
            has = await w.ev("!!document.querySelector('#p_remind') && document.querySelector('#p_remind').checked")
            check('setting: "Remind me about unclaimed tokens" is in Settings, on by default', has)
            await w.click('#p_remind'); await w.wait(150)
            check('setting: turning it off hides the reminder', await w.ev("Nutcade.S.prefs.remind") is False and await panel(w) is None)
            await w.ev("Nutcade.S.prefs.remind=true")
        await section('setting', setting)

        async def resilient():
            r3 = await w.ev(f"""(async()=>{{const S=Nutcade.S; S.prefs.checkSent=true; S.txs.push({{id:'rmnosent', type:'out', method:'ecash', status:'pending', token:'cashuBbad', amount:5, mint:{J(A)}, ts:1}});
                let ok=true; try {{ await NutRemind.check({J(A)}) }} catch(e) {{ ok=false }} S.txs=S.txs.filter(x=>x.id!=='rmnosent'); S.prefs.checkSent=false; return ok}})()""")
            check('resilient: the background check runs past a line it cannot check', r3)
            check('resilient: the old token it could check is still open', (await tx(w, ids['t4']))['status'] == 'pending')
        await section('resilient', resilient)

        async def langs():
            for lang in ('es', 'pt', 'de', 'fr'):
                x = await wallet(b, 'rm-' + lang, lang); await x.create(); await x.add_mint(A); await x.use(A)
                await x.ev(f"""(()=>{{const S=Nutcade.S; for (const [i,a] of [[1,100],[2,250]]) S.txs.unshift({{id:'rm'+i, type:'out', method:'ecash', status:'pending', token:'cashuBx'+i, amount:a, fee:0, ts:Date.now()-40*{DAY}, mint:{J(A)}, note:''}}); Nutcade.refresh()}})()""")
                await x.wait(200); pn = await panel(x)
                await x.click('[data-act=tab][data-tab=settings]'); await x.wait(200)
                miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/unclaimed|take (it|them) back|in all|Notes|Remind me|retiring/i.test(s))")
                check(f'{lang}: the reminder shows translated, with no missing translation', pn and pn['n'] == 2 and 'unclaimed' not in pn['text'] and not miss, (pn, miss))
                await x.pg.context.close()
        await section('langs', langs)

        await w.pg.screenshot(path=os.path.join(OUT, 'remind.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
