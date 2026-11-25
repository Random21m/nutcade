"""Nostr sign-in with your own identity (1.37.0): a NIP-07 browser extension or a NIP-46 remote signer (bunker:// link).
Uses the local test mint 3339 and the stand-in Nostr relay (mock_nostr.py, port 3350), which checks every signature and
also plays a NIP-46 remote signer (kind 24133, NIP-44) that can be honest, slow, refuse, send an auth_url, answer connect
with a wrong secret, or return a swapped event. The browser extension is a fake window.nostr injected into the page,
steered by localStorage "__f07" (honest, slow, hang, refuse, otherpub, kind, tag, content, time; unset or "gone": no
extension at all, as after a reload without it).

Covered: Settings -> Nostr identity (the extension offered only when window.nostr exists; never a field that takes an
nsec); strict bunker link parsing (hostile inputs); each action moved to the identity is signed by it (nutzap info 10019
and its withdrawal, the nutzap listen, mint reviews and their deletion, the daily score note, the zap request) with the
right kind, tags and content and a valid signature; every money key stays on the 12 words while signed in (a gift's
refund key, Extra Life's lock and its message to the heir, ecash sent to your ecash address, npub.cash, the nutzap you
send, wallet sync, the mint-list backup; the bounty wraps by a pin on the built page); no silent fallback to the 12-word
key when the signer refuses, hangs, vanishes or returns another event; nutzaps to the old and the new key both arrive
after a switch, never credited twice; the offer to withdraw the old nutzap info; your own reviews by either key counted
once; the connection kept in the PIN vault, never in plain storage, the backup file or sync events, gone after Sign out
and Reset; the duress PIN's wallet shows and uses no identity; a locked wallet signs nothing; offline it says it needs a
connection; races (two signatures at once, Sign out while signing, another tab taking over while signing); everything
from the signer shown as text (npub, error text, auth_url, never opened by the app); five languages at 320 px.
SI_ONLY=a,b runs some sections (their names start with those letters)."""
import asyncio, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from wallet_qa import W, check, results, URL, outside_net, B as M
from r8_qa import set_pin, unlock, pad, PIN, DPIN

OUT = os.environ.get('QA_OUT', '/tmp/qa-out')
J = json.dumps
MOCK = 'http://127.0.0.1:3350'
RELAY = 'ws://127.0.0.1:3350/relay'
LANGS = ['en', 'es', 'pt', 'de', 'fr']
HERE = os.path.dirname(os.path.abspath(__file__))

def state(): return json.loads(urllib.request.urlopen(MOCK + '/test/state', timeout=10).read())
def post(path, body): return json.loads(urllib.request.urlopen(urllib.request.Request(MOCK + path, data=J(body).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
def get(path): return json.loads(urllib.request.urlopen(MOCK + path, timeout=10).read())
def evs(kind, author=None, p=None):
    out = []
    for e in state()['events']:
        if e['kind'] != kind or (author and e['pubkey'] != author): continue
        if p and not any(t[0] == 'p' and len(t) > 1 and t[1] == p for t in e['tags']): continue
        out.append(e)
    return out
def pubs(author, kind): return state()['pub_count'].get(f'{author}:{kind}', 0)
def tg(e, k): return [t for t in e['tags'] if t and t[0] == k]
def methods(): return [x.get('method') for x in get('/test/signer/log')['log']]

# a fake NIP-07 extension: present only while localStorage "__f07" names a mode (read on every call, so a mode can change
# without a reload); its key is localStorage "__f07sk". window.__f07log lists what was asked of it.
FAKE07 = """(() => { const md = () => localStorage.getItem('__f07') || ''; if (!md() || md() === 'gone') return;
  const sk = () => CashuLib.hexToBytes(localStorage.getItem('__f07sk')); const wait = ms => new Promise(r => setTimeout(r, ms));
  window.__f07log = [];
  window.nostr = {
    async getPublicKey() { window.__f07log.push('pk'); const m = md(); if (m === 'hang') return new Promise(() => {}); if (m === 'refuse') throw new Error('nope <b>pk</b>'); if (m === 'slow') await wait(2500); return CashuLib.nostrPub(sk()); },
    async signEvent(t) { window.__f07log.push('sign:' + t.kind); const m = md();
      if (m === 'refuse') throw new Error('User rejected <img src=x onerror="window.__pwned=1">');
      if (m === 'hang') return new Promise(() => {});
      if (m === 'slow') await wait(2500); if (m === 'slower') await wait(6000);
      const x = { kind: t.kind, created_at: t.created_at, tags: t.tags, content: t.content }; let key = sk();
      if (m === 'otherpub') key = crypto.getRandomValues(new Uint8Array(32));
      if (m === 'kind') x.kind = t.kind + 1;
      if (m === 'tag') x.tags = t.tags.concat([['t', 'injected']]);
      if (m === 'content') x.content = t.content + ' (edited)';
      if (m === 'time') x.created_at = t.created_at - 1000;
      return CashuLib.finalizeEvent(x, key); } };
})();"""
HELPERS = """
window.__opened = 0; { const o = window.open; window.open = function () { window.__opened++; return null; }; }
window.__sign = (sk, kind, tags, content, dt) => CashuLib.finalizeEvent({ kind, created_at: Math.floor(Date.now() / 1000) + (dt || 0), tags, content }, typeof sk === 'string' ? CashuLib.hexToBytes(sk) : sk);
window.__seedSk = () => CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic).slice(0, 32);
window.__seedPub = () => CashuLib.nostrPub(window.__seedSk());
window.__tagKey = tag => CashuLib.sha256(new Uint8Array([...CashuLib.mnemonicToSeedSync(Nutcade.S.seed.mnemonic), ...new TextEncoder().encode(tag)]));
window.__pub = ev => new Promise(r => { const ws = new WebSocket(%s); ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d[0] === 'OK') { try { ws.close(); } catch (e) {} r(d[2]); } }; setTimeout(() => r(false), 5000); });
window.__nz = (proofs, u, ps, dt) => CashuLib.finalizeEvent({ kind: 9321, created_at: Math.floor(Date.now() / 1000) + (dt || 0), content: 'zap',
  tags: proofs.map(p => ['proof', JSON.stringify({ id: p.id, amount: Number(String(p.amount)), secret: p.secret, C: p.C, dleq: p.dleq })]).concat([['u', u], ['unit', 'sat']], ps.map(p => ['p', p])) }, crypto.getRandomValues(new Uint8Array(32)));
""" % J(RELAY)
# every wss:// relay (the signer's wss://signer.test among them) reaches the stand-in relay
REDIRECT = "{ const _W = window.WebSocket; window.WebSocket = class extends _W { constructor(u, p) { super(/^wss:\\/\\//.test(String(u)) ? %s : u, p); } }; }" % J(RELAY)

async def forward(route, request):
    """https://lnurl.test/... is served by mock_nostr.py (zaps)"""
    u = request.url.replace('https://lnurl.test', MOCK, 1)
    def fetch():
        try:
            r = urllib.request.urlopen(u, timeout=30); return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    st, body = await asyncio.to_thread(fetch)
    try: await route.fulfill(status=st, body=body, headers={'content-type': 'application/json', 'access-control-allow-origin': '*'})
    except Exception: pass

async def wallet(b, name, lang='en', width=390, ctx=None):
    if ctx is None:
        ctx = await b.new_context(viewport={'width': width, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
        prefs = {'sound': False, 'music': False, 'crt': True, 'lang': lang, 'relays': [RELAY], 'npcHost': MOCK}
        await ctx.add_init_script("window.__i18nMiss = new Set(); if(!localStorage.getItem('nutcade:prefs'))localStorage.setItem('nutcade:prefs'," + J(J(prefs)) + ")")
        await ctx.add_init_script(HELPERS); await ctx.add_init_script(REDIRECT); await ctx.add_init_script(FAKE07)
        await ctx.route('https://lnurl.test/**', forward)
    pg = await ctx.new_page(); w = W(pg, name); w.ctx = ctx; w.logs = []
    pg.on('pageerror', lambda e: w.errs.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: (w.logs.append(m.text), w.errs.append('CONSOLE ' + m.text) if m.type == 'error' and not outside_net(m.text) and 'WebSocket' not in m.text else None))
    await pg.goto(URL); await pg.wait_for_timeout(700)
    return w
async def section(name, fn):
    only = [x for x in os.environ.get('SI_ONLY', '').split(',') if x]
    if only and not any(name.startswith(x) for x in only): return
    print('--- ' + name, flush=True)
    try: await fn()
    except Exception as e: check(f'{name}: ran to the end', False, repr(e)[:300])
async def settings(w): await w.ev("Nutcade.closeSheet()"); await w.click('[data-act=tab][data-tab=settings]'); await w.wait(250)
async def panel(w): await settings(w); return await w.ev("(document.querySelector('#set-identity')||{}).innerText||''")
async def ext_mode(w, mode, sk=None, reload=False):
    await w.ev(f"localStorage.setItem('__f07', {J(mode)})" if mode else "localStorage.removeItem('__f07')")
    if sk: await w.ev(f"localStorage.setItem('__f07sk', {J(sk)})")
    if reload: await w.pg.reload(); await w.wait(900)
async def sign_in_ext(w):
    await settings(w); await w.click('#set-identity [data-act=idExt]')
    return await w.until("window.NutId && NutId.active()", 12000)
async def sign_in_bunker(w, link, wait=True):
    await settings(w); await w.click('#set-identity [data-act=idBunker]'); await w.until("!!document.querySelector('#idLink')", 5000)
    await w.ev(f"(()=>{{const i=document.querySelector('#idLink'); i.value={J(link)}; i.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")
    await w.click('#layer [data-act=idConnect]')
    if wait: return await w.until("(window.NutId && NutId.active()) || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 20000) and await w.ev("NutId.active()")
async def sign_out(w, withdraw=False):
    await settings(w); await w.click('#set-identity [data-act=idOut]'); await w.until("!!document.querySelector('#layer [data-act=idOutGo]')", 5000)
    if withdraw: await w.ev("(()=>{const c=document.querySelector('#idOutWithdraw'); if(c&&!c.checked) c.click();})()")
    await w.click('#layer [data-act=idOutGo]')
    return await w.until("!NutId.active() && !document.querySelector('#layer [data-act=idOutGo] .spinner')", 20000)
async def nz_on(w):
    await settings(w)
    if not await w.ev("document.querySelector('#p_nutzap').checked"): await w.click('#p_nutzap')
    return await w.until("NutZap.info() && NutZap.info().pub === NutZap.pub()", 15000)
async def open_review(w):
    await w.ev("Nutcade.closeSheet()")
    await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='rvOpen'; b.dataset.url={J(M)}; document.body.appendChild(b); b.click(); b.remove();}})()")
    await w.until("!!document.querySelector('#layer #rvForm, #layer #rvMine')", 8000); await w.wait(250)
async def review(w, n, text, ms=20000):
    """publishes a review from the sheet; returns the error line (empty when it went out)"""
    await open_review(w)
    if await w.ev("!!document.querySelector('#layer [data-act=rvEdit]')"): await w.click('#layer [data-act=rvEdit]'); await w.wait(150)
    await w.click(f'#layer [data-act=rvStar][data-n="{n}"]'); await w.wait(80)
    await w.ev(f"(()=>{{const t=document.querySelector('#rvText'); t.value={J(text)}; t.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")
    await w.click('#layer [data-act=rvPublish]'); await w.wait(150)
    await w.until("!document.querySelector('#layer [data-act=rvPublish] .spinner') && !document.querySelector('#layer #rvBusy')", ms); await w.wait(300)
    return await w.err()
async def nz_in(w): return await w.ev("Nutcade.S.txs.filter(t=>t.type==='in'&&t.nz).map(t=>({status:t.status, amount:t.amount, ev:t.nz.id}))")
async def report(w):
    await w.ev("Nutcade.closeSheet()")
    await w.ev(f"(()=>{{const b=document.createElement('button'); b.dataset.act='reportOpen'; b.dataset.url={J(M)}; b.dataset.fresh=1; document.body.appendChild(b); b.click(); b.remove();}})()")
    await w.until("!!document.querySelector('#layer [data-act=reportOpen][data-fresh]')", 20000); await w.wait(200)
    return await w.sheet_text()
async def unwrap(w, wrap, sk):
    return await w.ev(f"(()=>{{try{{return CashuLib.nip59.unwrapEvent({J(wrap)}, CashuLib.hexToBytes({J(sk)})).pubkey}}catch(e){{return 'ERR '+e.message}}}})()")
async def keypair(w):
    return await w.ev("(()=>{const k=crypto.getRandomValues(new Uint8Array(32)); return [CashuLib.bytesToHex(k), CashuLib.nostrPub(k)]})()")

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        al = await wallet(b, 'si-alice'); await al.create(); await al.add_mint(M); await al.use(M)
        check('setup: the sender has sats', await al.receive_ln(6000))
        me = await wallet(b, 'si-me'); words = await me.create(); await me.add_mint(M); await me.use(M)
        await me.receive_ln(3000)
        SEED = await me.ev("__seedPub()")
        EXT_SK, EXT = await keypair(me)
        ctx = {}

        async def base():
            check('base: NUTCADE has an identity layer (window.NutId)', await me.ev("typeof window.NutId === 'object' && typeof NutId.sign === 'function'"))
            t = await panel(me)
            check('base: Settings has a Nostr identity section', bool(t) and 'identity' in t.lower(), t[:200])
            check('base: not signed in, the identity is the 12-word key', await me.ev("!NutId.active() && NutId.pub() === __seedPub()"))
            check('base: no browser extension here, so none is offered; the remote signer is', not await me.ev("!!document.querySelector('#set-identity [data-act=idExt]')") and await me.ev("!!document.querySelector('#set-identity [data-act=idBunker]')"))
            await me.click('#set-identity [data-act=idBunker]'); await me.until("!!document.querySelector('#idLink')", 5000)
            ins = await me.ev("[...document.querySelectorAll('#layer input, #layer textarea')].map(i=>[i.id, i.placeholder, i.type, (i.labels&&i.labels[0]||{}).innerText||''])")
            check('base: the remote signer sheet has one field, for a bunker:// link (no field for an nsec)', len(ins) == 1 and ins[0][0] == 'idLink' and 'bunker://' in ins[0][1] and 'nsec' not in (ins[0][1] + ins[0][3]).lower(), ins)
            nsec = await me.ev("CashuLib.nip19decode ? 'nsec1' + 'q'.repeat(58) : ''")
            await me.ev(f"(()=>{{const i=document.querySelector('#idLink'); i.value={J(nsec)}; i.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")
            await me.click('#layer [data-act=idConnect]'); await me.wait(400)
            e = await me.err()
            check('base: an nsec pasted there is refused (a private key is never taken), nothing kept, the field emptied', 'private key' in e.lower() and not await me.ev("NutId.active()") and await me.ev("document.querySelector('#idLink').value") == '' and 'nsec1' not in await me.ev("JSON.stringify(localStorage)"), e)
            await me.ev("Nutcade.closeSheet()")
        await section('base', base)

        async def parse():
            pk = await me.ev("CashuLib.nostrPub(crypto.getRandomValues(new Uint8Array(32)))")
            good = [f"bunker://{pk}?relay=wss://relay.example.com&secret=abc123", f"  bunker://{pk}?relay=wss%3A%2F%2Frelay.example.com&relay=wss://r2.example.org/path  ", f"bunker://{pk}?relay=wss://relay.example.com"]
            for g in good:
                r = await me.ev(f"NutId.parse({J(g)})")
                check(f'parse: a good link is read ({g.strip()[:60]}…)', r.get('ok') and r['remote'] == pk and all(x.startswith('wss://') for x in r['relays']) and r['relays'], r)
            r = await me.ev(f"NutId.parse({J(good[0])})")
            check('parse: relays and secret read exactly', r.get('relays') == ['wss://relay.example.com'] and r.get('secret') == 'abc123', r)
            bad = {'nsec': 'nsec1' + 'q' * 58, 'nsec in a link': f'bunker://{pk}?relay=wss://r.example.com&secret=nsec1' + 'q' * 58,
                   'nostrconnect': f'nostrconnect://{pk}?relay=wss://r.example.com&secret=x', 'npub instead of hex': 'bunker://' + await me.ev(f"CashuLib.npubEncode({J(pk)})") + '?relay=wss://r.example.com',
                   'uppercase hex': f'bunker://{pk.upper()}?relay=wss://r.example.com', '63 hex': f'bunker://{pk[:63]}?relay=wss://r.example.com', 'not a point': f'bunker://{"f" * 64}?relay=wss://r.example.com',
                   'ws relay': f'bunker://{pk}?relay=ws://r.example.com', 'https relay': f'bunker://{pk}?relay=https://r.example.com', 'user:pass relay': f'bunker://{pk}?relay=wss://u:p@r.example.com',
                   'javascript relay': f'bunker://{pk}?relay=javascript:alert(1)', 'no relay': f'bunker://{pk}?secret=x', 'four relays': f'bunker://{pk}?' + '&'.join(f'relay=wss://r{i}.example.com' for i in range(4)),
                   'long relay': f'bunker://{pk}?relay=wss://' + 'a' * 300 + '.com', 'long secret': f'bunker://{pk}?relay=wss://r.example.com&secret=' + 'a' * 200,
                   'markup secret': f'bunker://{pk}?relay=wss://r.example.com&secret=%3Cscript%3E', 'unknown param': f'bunker://{pk}?relay=wss://r.example.com&perms=sign_event',
                   'proto param': f'bunker://{pk}?relay=wss://r.example.com&__proto__=x', 'two secrets': f'bunker://{pk}?relay=wss://r.example.com&secret=a&secret=b',
                   'fragment': f'bunker://{pk}?relay=wss://r.example.com#x', 'space inside': f'bunker://{pk}?relay=wss://r.example.com &secret=a', 'huge': f'bunker://{pk}?relay=wss://r.example.com&secret=' + 'a' * 5000,
                   'relay with space': f'bunker://{pk}?relay=wss://r.exa%20mple.com', 'empty': '', 'scheme only': 'bunker://', 'http link': f'https://{pk}?relay=wss://r.example.com',
                   'control chars': f'bunker://{pk}?relay=wss://r.example.com\u0000&secret=a', 'relay fragment': f'bunker://{pk}?relay=wss%3A%2F%2Fr.example.com%23x'}
            for name, v in bad.items():
                r = await me.ev(f"NutId.parse({J(v)})")
                check(f'parse: refused: {name}', not r.get('ok') and isinstance(r.get('error'), str) and r['error'], r)
            r = await me.ev("NutId.parse({toString(){return 'x'}})")
            check('parse: refused: not a string', not r.get('ok'), r)
            r = await me.ev(f"NutId.parse({J(bad['nsec'])})")
            check('parse: an nsec gets its own message (never paste a private key)', 'private key' in r.get('error', '').lower(), r)
        await section('parse', parse)

        async def ext():
            await nz_on(me)
            old10019 = [e for e in evs(10019, SEED) if e['tags']]
            check('ext: (nutzaps on before signing in: nutzap info published under the 12-word key)', len(old10019) == 1)
            await ext_mode(me, 'honest', EXT_SK, reload=True)
            t = await panel(me)
            check('ext: with window.nostr there, the extension is offered', await me.ev("!!document.querySelector('#set-identity [data-act=idExt]')"), t[:200])
            ok = await sign_in_ext(me)
            check('ext: signing in with the extension uses its public key', ok and await me.ev(f"NutId.pub() === {J(EXT)} && NutId.type() === 'nip07'"))
            t = await panel(me); npub = await me.ev(f"CashuLib.npubEncode({J(EXT)})")
            check('ext: Settings shows the npub you are signed in as', npub[:12] in t and npub[-4:] in t, t[:300])
            uses = await me.ev("[...document.querySelectorAll('#idUses li')].map(l=>l.innerText)")
            check('ext: Settings lists what uses it (nutzap info, mint reviews, the daily note, zaps)', len(uses) == 4 and any('nutzap' in u.lower() for u in uses) and any('review' in u.lower() for u in uses) and any('daily' in u.lower() for u in uses) and any('zap' in u.lower() for u in uses[3:]), uses)
            check('ext: Settings says money stays on the 12 words', '12 words' in t, t[:400])
            ok = await me.until(f"NutZap.info() && NutZap.info().pk === {J(EXT)}", 15000)
            e = [x for x in evs(10019, EXT) if x['tags']]
            check('ext: the nutzap info is republished under the identity (kind 10019, same relays, mints and receiving key)', ok and len(e) == 1 and tg(e[0], 'pubkey') == [['pubkey', await me.ev("NutZap.pub()")]] and tg(e[0], 'mint') == [['mint', M, 'sat']] and tg(e[0], 'relay') == [['relay', RELAY]], e)
            check('ext: the receiving key is still the one from the 12 words (not the identity)', await me.ev("NutZap.pub()") != '02' + EXT and await me.ev("NutZap.pub()") == tg(old10019[0], 'pubkey')[0][1])
            keys = await me.ev("NutZap.keys()")
            check('ext: nutzaps are listened for on both keys', sorted(keys) == sorted([SEED, EXT]), keys)
            t = await panel(me)
            check('ext: Settings offers to withdraw the old nutzap info, with one plain sentence', await me.ev("!!document.querySelector('#set-identity [data-act=idRetract]')") and 'withdraw' in t.lower(), t[:600])
            await me.click('#set-identity [data-act=idRetract]')
            ok = await me.until(f"!document.querySelector('#set-identity [data-act=idRetract]')", 12000); await me.wait(500)
            dels = [x for x in evs(5, SEED) if ['a', f'10019:{SEED}:'] in x['tags']]
            check('ext: withdrawing sends a kind 5 for the old 10019 and an empty one, both by the 12-word key', ok and dels and not [x for x in evs(10019, SEED) if x['tags']], (len(dels), [x['tags'] for x in evs(10019, SEED)]))
            check('ext: the identity\'s nutzap info stays', [x for x in evs(10019, EXT) if x['tags']])
            ctx['ext'] = True
        await section('ext', ext)

        async def moved():
            n0 = pubs(SEED, 38000)
            e = await review(me, 4, 'signed by me')
            r = (evs(38000, EXT) or [None])[-1]
            check('moved: the mint review is signed by the identity (kind 38000, its tags, "[4/5] text")', not e and r and r['content'] == '[4/5] signed by me' and tg(r, 'k') == [['k', '38172']] and tg(r, 'u') == [['u', M, 'cashu']], (e, r))
            check('moved: nothing of it under the 12-word key', pubs(SEED, 38000) == n0)
            check('moved: the extension was asked to sign it', 'sign:38000' in await me.ev("window.__f07log"))
            # your own reviews by either key: one review counted
            mp = tg(r, 'd')[0][1]
            old = await me.ev(f"__sign(__seedSk(), 38000, [['k','38172'],['d',{J(mp)}],['u',{J(M)},'cashu']], '[2/5] old one under my words', -3600)")
            await me.ev(f"__pub({J(old)})")
            osk, opk = await keypair(me)
            other = await me.ev(f"__sign({J(osk)}, 38000, [['k','38172'],['d',{J(mp)}],['u',{J(M)},'cashu']], '[5/5] someone else', -60)")
            await me.ev(f"__pub({J(other)})")
            t = await report(me)
            check('moved: the report card counts your reviews by either key once (you and one other person: 2)', 'Recommended by 2 Nostr users' in t, t)
            mine = await me.ev(f"NutReview.mine({J(M)})")
            check('moved: your review is the newest of yours (the identity\'s)', mine and mine['stars'] == 4 and mine['pk'] == EXT, mine)
            # deleting it: a kind 5 by the identity
            await open_review(me); await me.click('#layer [data-act=rvDelAsk]'); await me.wait(150); await me.click('#layer [data-act=rvDel]')
            await me.until("!!document.querySelector('#layer #rvGone') || !!((document.querySelector('#sheetErr')||{}).innerText||'').trim()", 15000)
            d = [x for x in evs(5, EXT) if ['a', f'38000:{EXT}:{mp}'] in x['tags']]
            check('moved: deleting it sends a kind 5 signed by the identity', d, await me.err())
            # the daily note
            ev = await me.ev("NutDailyNostr.sign('daily score 123', [['t','nutcade']])")
            check('moved: the daily score note is signed by the identity (kind 1, its content and tags)', ev['pubkey'] == EXT and ev['kind'] == 1 and ev['content'] == 'daily score 123' and ev['tags'] == [['t', 'nutcade']] and await me.ev(f"CashuLib.verifyEvent({J(ev)})"), ev)
            check('moved: the daily screen shows the identity\'s npub', await me.ev(f"NutDailyNostr.npub() === CashuLib.npubEncode({J(EXT)})"))
            # the zap request
            post('/test/lnurlp', {'name': 'zed', 'zap': True}); pz = post('/test/profile', {'name': 'zed', 'lud16': 'zed@lnurl.test'})
            nz = len(state()['zaps'])
            await me.home(); await me.click('[data-act=send]'); await me.wait(150); await me.click('[data-act=sendMethod][data-m=ln]'); await me.wait(100)
            await me.fill('#destIn', pz['npub']); await me.click('[data-act=doMeltQuote]')
            await me.until("!!document.querySelector('[data-act=zapQuote]')", 12000)
            pre = await me.sheet_text()
            check('moved: the zap sheet says it is signed with your Nostr identity', 'your nostr identity' in pre.lower(), pre[:400])
            await me.fill('#amtIn', '21'); await me.click('[data-act=zapQuote]')
            await me.until("!!document.querySelector('#payBtn') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
            z = state()['zaps'][nz:]
            check('moved: the zap request (kind 9734) is signed by the identity', z and z[-1]['valid'] and z[-1]['event']['pubkey'] == EXT, z[-1:] and z[-1]['event'].get('pubkey'))
            await me.ev("Nutcade.closeSheet()")
            await me.home(); await me.click('[data-act=send]'); await me.wait(150); await me.click('[data-act=sendMethod][data-m=ln]'); await me.wait(100)
            await me.fill('#destIn', pz['npub']); await me.click('[data-act=doMeltQuote]'); await me.until("!!document.querySelector('[data-act=zapQuote]')", 12000)
            await me.fill('#amtIn', '22'); await me.click('#zapAnon'); await me.click('[data-act=zapQuote]')
            await me.until("!!document.querySelector('#payBtn') || !!(document.querySelector('#sheetErr')||{}).innerText", 15000)
            z = state()['zaps'][-1]
            check('moved: an anonymous zap is signed by a one-time key, neither the identity nor the 12-word key', z['valid'] and z['event']['pubkey'] not in (EXT, SEED), z['event'].get('pubkey'))
            await me.ev("Nutcade.closeSheet()")
        await section('moved', moved)

        async def money():
            # a gift with a refund date: the refund key is the 12-word key
            other = await me.ev("NutZap.randomPub()")
            t = await me.ev(f"Nutcade.r8.sendEcash(20, 'gift', {J(other)}, {J(M)}, {{locktime: Math.floor(Date.now()/1000)+3600}}).then(t=>t.sent.map(p=>JSON.parse(p.secret)))")
            rf = [x[1] for x in t[0][1]['tags'] if x[0] == 'refund']
            check('money: a lock-to-me send while signed in: its refund key is the 12-word key ("02" + x)', rf == ['02' + SEED], rf)
            # ecash address and ecash sent to it
            addr = await me.ev("CashuLib.nip19decode(document.createElement('x') && NutId.ecashAddress()).data.pubkey")
            check('money: your ecash address is still the 12-word key', addr == SEED, addr)
            await me.ev("Nutcade.S.prefs.nostrInbox = true; Nutcade.refresh()"); await me.wait(1500)
            b0 = await me.bal()
            r = await al.ev(f"""(async()=>{{const tx=await Nutcade.r8.sendEcash(33, '');
              const ev=CashuLib.nip17.wrapEvent(crypto.getRandomValues(new Uint8Array(32)), {{publicKey:{J(SEED)}}}, JSON.stringify({{mint:{J(M)}, unit:'sat', proofs:tx.sent}}));
              return __pub(ev)}})()""")
            ok = await me.until(f"Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0) >= {b0 + 33}", 20000)
            check('money: ecash sent to your ecash address (gift wrap to the 12-word key) arrives while signed in', r is True and ok, (r, await me.bal() - b0))
            # npub.cash
            await settings(me); await me.click('#set-lnaddr [data-act=lnAddr]'); await me.wait(250)
            await me.click('[data-act=lnAddrOn]'); await me.until("Nutcade.S.prefs.npc===true", 10000); await me.wait(500); await me.ev("Nutcade.closeSheet()")
            users = state()['users']
            check('money: npub.cash logs in with the 12-word key (NIP-98), never the identity', SEED in users and EXT not in users, list(users)[:4])
            # the nutzap you send: signed by the 12-word key
            await nz_on(al)
            apk = await al.ev("__seedPub()")
            r = await me.ev(f"NutZap.send({{pubkey:{J(apk)}, name:'Al'}}, 25, 'thanks').then(x=>x.ok, e=>e.message)")
            z = [x for x in evs(9321, p=apk)]
            check('money: a nutzap you send (kind 9321, it carries the locked coins) is signed by the 12-word key', r is True and z and z[-1]['pubkey'] == SEED, (r, z and z[-1]['pubkey']))
            # Extra Life: locked to the 12-word key, its message to the heir sealed by it
            hsk, hpk = await keypair(me)
            await me.ev(f"Nutcade.handleScan(CashuLib.npubEncode({J(hpk)}))"); await me.until("!!document.querySelector('#cName')", 5000)
            await me.fill('#cName', 'Heir'); await me.click('[data-act=contactSave]'); await me.wait(300); await me.ev("Nutcade.closeSheet()")
            await me.home(); await me.click('[data-act=extraOpen]'); await me.until("!!document.querySelector('#xlTo')", 5000); await me.wait(150)
            await me.ev("const s=document.querySelector('#xlTo'); s.value=[...s.options].find(o=>o.text==='Heir').value; s.dispatchEvent(new Event('change',{bubbles:true}))")
            await me.fill('#amtIn', '100'); await me.click('[data-act=extraStart]')
            ok = await me.until("!!Nutcade.S.extra && Nutcade.S.extra.delivered", 20000)
            sec = await me.ev("JSON.parse(Nutcade.S.extra.proofs[0].secret)") if ok else None
            check('money: Extra Life is locked to the 12-word key', ok and sec[1]['data'] == '02' + SEED, sec)
            wraps = evs(1059, p=hpk)
            who = await unwrap(me, wraps[-1], hsk) if wraps else None
            check('money: Extra Life\'s message to the heir is sealed by the 12-word key', who == SEED, who)
            await me.ev("Nutcade.closeSheet()")
            # wallet sync and the mint-list backup: their own keys from the 12 words
            await settings(me)
            if not await me.ev("document.querySelector('#p_nostrBackup').checked"): await me.click('#p_nostrBackup')
            bk = await me.ev("CashuLib.nostrPub(__tagKey('cashu-mint-backup'))")
            check('money: the mint-list backup is published under its own key from the 12 words', await me.until(f"fetch('{MOCK}/test/state').then(r=>r.json()).then(s=>s.events.some(e=>e.kind===30078&&e.pubkey==={J(bk)}))", 12000))
            # the built page still uses the 12-word key at every money site (the bounty wraps are pinned here)
            page = open(os.path.join(HERE, '..', 'public', 'index.html'), encoding='utf-8').read()
            pins = {"myLockPub": "const myLockPub = () => '02' + L.nostrPub(nostrKey());", "myLockPriv": "const myLockPriv = () => evenPriv(hex(nostrKey()));",
                    "gift-wrap receive": "rumor = L.nip59.unwrapEvent(ev, nostrKey());", "ecash address": "const myEcashAddress = () => L.nprofileEncode({ pubkey: L.nostrPub(nostrKey())",
                    "npub.cash key": "const npcPub = () => L.nostrPub(nostrKey());", "npub.cash NIP-98": "tags: [['u', url], ['method', method]], content: '' }, nostrKey());",
                    "payment request": "const pub = L.nostrPub(nostrKey());\n  const id = hex(rnd(4));", "bounty challenge wrap": "L.nip17.wrapEvent(bounty ? nostrKey() : rnd(32)",
                    "bounty release": "L.nip17.wrapEvent(nostrKey(), { publicKey: b.to }", "Extra Life heir copy": "L.nip17.wrapEvent(nostrKey(), { publicKey: x.heir.pubkey }",
                    "Extra Life end": "L.nip17.wrapEvent(nostrKey(), { publicKey: f.heir.pubkey }", "nutzap sent": "content: z.c || '', tags }, nostrKey())",
                    "mint-list backup key": "const sk = backupKeyFrom(seedFor()), pk = L.nostrPub(sk);"}
            for k, v in pins.items(): check(f'money: the built page keeps the 12-word key at: {k}', v in page)
        await section('money', money)

        async def nofallback():
            if not ctx.get('ext'): return
            n38, s38, s1 = pubs(EXT, 38000), pubs(SEED, 38000), pubs(SEED, 1)
            await ext_mode(me, 'refuse')
            e = await review(me, 3, 'refused')
            check('fallback: the extension saying no is shown, nothing published (not under the 12-word key either)', 'said no' in e.lower() and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38, e)
            check('fallback: its error text is shown as text', 'User rejected' in e and not await me.ev("!!document.querySelector('#layer img')") and not await me.ev("!!window.__pwned"), e)
            r = await me.ev("NutDailyNostr.sign('x', []).then(e=>e.pubkey, e=>'ERR '+e.message)")
            check('fallback: the daily note is not signed either', r.startswith('ERR') and pubs(SEED, 1) == s1, r)
            for mode in ('otherpub', 'kind', 'tag', 'content', 'time'):
                await ext_mode(me, mode)
                r = await me.ev("NutId.sign({kind: 1, created_at: Math.floor(Date.now()/1000), tags: [['t','nutcade']], content: 'exact'}).then(e=>'SIGNED '+e.pubkey, e=>'ERR '+e.message)")
                check(f'fallback: an extension returning another event ({mode}) is refused', r.startswith('ERR') and 'different' in r.lower(), r)
            await ext_mode(me, 'otherpub')
            e = await review(me, 3, 'swapped')
            check('fallback: ...and nothing is published from it', e and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38, e)
            await ext_mode(me, 'slow')
            t0 = time.time(); e = await review(me, 5, 'slow but fine'); dt = time.time() - t0
            r = (evs(38000, EXT) or [{}])[-1]
            check('fallback: a slow extension (2.5 s) is waited for, and its signature used', not e and r.get('content') == '[5/5] slow but fine' and dt > 2.4, (e, r.get('content'), round(dt, 1)))
            await ext_mode(me, 'hang'); await me.ev("window.__nutcadeTest = {idMs: 3000}")
            n38 = pubs(EXT, 38000); t0 = time.time(); e = await review(me, 2, 'hangs'); dt = time.time() - t0
            check('fallback: an extension that never answers times out with a clear message, nothing published', "didn't answer" in e.lower() and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38 and dt < 12, (e, round(dt, 1)))
            await me.ev("window.__nutcadeTest = null")
            # the extension gone after a reload
            await ext_mode(me, 'gone', reload=True)
            check('fallback: after a reload without the extension you are still signed in as the identity', await me.ev(f"NutId.active() && NutId.pub() === {J(EXT)}"))
            t = await panel(me)
            check('fallback: Settings says the extension is not here', await me.ev("!!document.querySelector('#set-identity #idWarn')") and 'extension' in t.lower(), t[:300])
            n38, s10 = pubs(EXT, 38000), pubs(SEED, 10019)
            e = await review(me, 1, 'no extension')
            check('fallback: without the extension nothing is signed (a clear message, nothing under the 12-word key)', 'extension' in e.lower() and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38, e)
            await me.ev("NutZap.tick(true)"); await me.wait(1500)
            check('fallback: the nutzap info is not republished under the 12-word key', pubs(SEED, 10019) == s10)
            await ext_mode(me, 'honest', reload=True)
        await section('nofallback', nofallback)

        async def race():
            if not ctx.get('ext'): return
            await ext_mode(me, 'slow')
            r = await me.ev("Promise.all([1,2].map(i=>NutId.sign({kind: 1, created_at: Math.floor(Date.now()/1000), tags: [], content: 'two at once ' + i}))).then(a=>a.map(e=>[e.content, e.pubkey, CashuLib.verifyEvent(e)]), e=>'ERR '+e.message)")
            check('race: two signatures at once both come back right', r == [['two at once 1', EXT, True], ['two at once 2', EXT, True]], r)
            # sign out while signing: nothing goes out
            n38, s38 = pubs(EXT, 38000), pubs(SEED, 38000)
            await ext_mode(me, 'slower'); n0 = await me.ev("window.__f07log.length")
            await me.ev(f"(()=>{{ window.__r = NutReview.publish({J(M)}, 3, 'sign out mid-sign').then(()=>'sent', e=>e.message) }})()")
            await me.until(f"window.__f07log.length > {n0}", 8000); await me.ev("NutId.out()")
            await me.until("typeof window.__r === 'string'", 12000); r = await me.ev("window.__r")
            check('race: signing out while the extension signs: nothing is published under any key, it says why', r != 'sent' and 'signed out' in str(r).lower() and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38, (r, await me.ev("window.__f07log.slice(-4)"), pubs(EXT, 38000) - n38, pubs(SEED, 38000) - s38))
            await ext_mode(me, 'honest'); await sign_in_ext(me)
            # signed out after the step started but before it was signed: not signed with the 12-word key instead
            await ext_mode(me, 'slower'); n0 = await me.ev("window.__f07log.length")
            await me.ev(f"(()=>{{ window.__r = NutReview.publish({J(M)}, 3, 'out before signing'); window.__r2 = NutId.sign({{kind: 1, created_at: Math.floor(Date.now()/1000), tags: [], content: 'queued'}}).then(()=>'signed', e=>e.message); window.__r = window.__r.then(()=>'sent', e=>e.message) }})()")
            await me.until(f"window.__f07log.length > {n0}", 8000); await me.ev("NutId.out()")
            await me.until("typeof window.__r2 === 'string'", 15000)
            check('race: a signature still waiting its turn when you sign out is dropped too (never the 12-word key)', await me.ev("window.__r2") != 'signed' and pubs(SEED, 1) == 0 and pubs(SEED, 38000) == s38, await me.ev("window.__r2"))
            await ext_mode(me, 'honest'); await sign_in_ext(me); await ext_mode(me, 'slower'); n0 = await me.ev("window.__f07log.length")
            # another tab takes over while signing
            await me.ev(f"(()=>{{ window.__r = NutReview.publish({J(M)}, 3, 'tab mid-sign').then(()=>'sent', e=>e.message) }})()")
            await me.until(f"window.__f07log.length > {n0}", 8000)
            t2 = await wallet(b, 'si-tab2', ctx=me.ctx); await t2.until("!!document.querySelector('[data-act=takeover]')", 8000)
            await t2.click('[data-act=takeover]')
            await me.until("typeof window.__r === 'string'", 12000); r = await me.ev("window.__r")
            check('race: another tab taking over while signing: nothing is published by the paused tab', r != 'sent' and pubs(EXT, 38000) == n38 and pubs(SEED, 38000) == s38, r)
            await t2.pg.close(); await me.pg.reload(); await me.wait(900); await ext_mode(me, 'honest')
        await section('race', race)

        async def switch():
            if not ctx.get('ext'): return
            s10 = pubs(SEED, 10019)
            await me.ev("NutZap.tick(true)"); await me.wait(1000)
            n5 = len(evs(5, EXT))
            ok = await sign_out(me, withdraw=True)
            check('switch: Sign out', ok and await me.ev("NutId.pub() === __seedPub()"))
            ok = await me.until(f"NutZap.info() && NutZap.info().pk === {J(SEED)}", 15000)
            check('switch: the nutzap info is republished under the 12-word key', ok and pubs(SEED, 10019) > s10 and [x for x in evs(10019, SEED) if x['tags']])
            check('switch: the identity\'s nutzap info was withdrawn (asked on Sign out, signed by the identity)', len(evs(5, EXT)) > n5 and not [x for x in evs(10019, EXT) if x['tags']])
            keys = await me.ev("NutZap.keys()")
            check('switch: nutzaps are still listened for on both keys', sorted(keys) == sorted([SEED, EXT]), keys)
            await me.ev("Nutcade.closeSheet()"); await me.wait(1500)
            nzp = await me.ev("NutZap.pub()"); b0 = await me.bal(); n0 = len(await nz_in(me))
            p1 = await al.ev(f"Nutcade.r8.sendEcash(11, 'nz old', {J(nzp)}).then(t=>t.sent)")
            p2 = await al.ev(f"Nutcade.r8.sendEcash(12, 'nz new', {J(nzp)}).then(t=>t.sent)")
            p3 = await al.ev(f"Nutcade.r8.sendEcash(13, 'nz both', {J(nzp)}).then(t=>t.sent)")
            e1 = await al.ev(f"__nz({J(p1)}, {J(M)}, [{J(SEED)}])"); e2 = await al.ev(f"__nz({J(p2)}, {J(M)}, [{J(EXT)}])"); e3 = await al.ev(f"__nz({J(p3)}, {J(M)}, [{J(SEED)}, {J(EXT)}])")
            for e in (e1, e2, e3, e2, e3): await al.ev(f"__pub({J(e)})")
            ok = await me.until(f"Nutcade.S.txs.filter(t=>t.type==='in'&&t.nz&&t.status==='done').length >= {n0 + 3}", 25000); await me.wait(2000)
            got = await nz_in(me)
            check('switch: nutzaps to the 12-word key and to the former identity both arrive', ok and await me.bal() - b0 == 36, (await me.bal() - b0, got[n0:]))
            await me.ev(f"NutZap.event({J(e3)})"); await me.ev(f"NutZap.event({J(e2)})"); await me.wait(800)
            check('switch: each is credited once (one tagged with both keys, the same ones again)', len(await nz_in(me)) == n0 + 3 and await me.bal() - b0 == 36, len(await nz_in(me)) - n0)
        await section('switch', switch)

        async def bunker():
            bk = await wallet(b, 'si-bunker'); ctx['bk'] = bk
            await bk.create(); await bk.add_mint(M); await bk.use(M); await bk.receive_ln(500)
            await set_pin(bk)
            S = post('/test/signer', {}); ctx['S'] = S
            ok = await sign_in_bunker(bk, S['bunker'])
            check('bunker: signing in with a bunker:// link', ok, await bk.err())
            check('bunker: the identity is the user key the signer gives (get_public_key), not the signer\'s own key', await bk.ev(f"NutId.pub() === {J(S['user'])} && NutId.type() === 'nip46'"))
            lg = get('/test/signer/log')['log']
            check('bunker: connect with the signer key and the secret, then get_public_key', [x['method'] for x in lg[:2]] == ['connect', 'get_public_key'] and lg[0]['params'][:2] == [S['remote'], S['secret']], lg[:2])
            reqs = evs(24133, p=S['remote'])
            cl = get('/test/signer/log')['clients']
            check('bunker: requests are kind 24133, tagged with the signer key, NIP-44 encrypted, from the app\'s own client key', reqs and all(r['tags'] == [['p', S['remote']]] for r in reqs) and all('method' not in r['content'] for r in reqs) and cl and cl[0] not in (S['user'], await bk.ev("__seedPub()")), (len(reqs), cl))
            await bk.ev("Nutcade.closeSheet()")
            e = await review(bk, 5, 'via bunker')
            r = (evs(38000, S['user']) or [None])[-1]
            check('bunker: a review is signed by the remote signer (sign_event), valid on the relay', not e and r and r['content'] == '[5/5] via bunker' and 'sign_event' in methods(), (e, r and r['content']))
            # storage
            v = await bk.ev("JSON.stringify(Nutcade.vault.data.nid || null)")
            nid = json.loads(v) or {}
            csk = nid.get('csk', '')
            check('bunker: the connection is in the PIN vault (client key, signer key, relays)', re.fullmatch(r'[0-9a-f]{64}', csk or '') and nid.get('remote') == S['remote'], {k: (x if k != 'csk' else '…') for k, x in nid.items()})
            check('bunker: the bunker secret is not kept anywhere', S['secret'] not in v and S['secret'] not in await bk.ev("JSON.stringify(localStorage)"))
            plain = await bk.ev("JSON.stringify(Object.fromEntries(Object.keys(localStorage).filter(k=>k!=='nutcade:vault').map(k=>[k, localStorage.getItem(k)])))")
            check('bunker: nothing of it in plain storage (with a PIN)', csk not in plain and S['remote'] not in plain and S['user'] not in plain)
            bd = await bk.ev("Nutcade.r8.backupData()")
            check('bunker: nothing of it in the backup file', csk not in bd and S['remote'] not in bd and 'nid' not in json.loads(bd))
            check('bunker: never written to the console', not any(csk in l for l in bk.logs))
            await settings(bk)
            if not await bk.ev("document.querySelector('#p_sync').checked"): await bk.click('#p_sync')
            await bk.wait(400); await bk.ev("Nutcade.closeSheet()")
            spk = await bk.ev("CashuLib.nostrPub(__tagKey('nutcade-nip60'))")
            await bk.until(f"fetch('{MOCK}/test/state').then(r=>r.json()).then(s=>s.events.some(e=>e.kind===17375&&e.pubkey==={J(spk)}))", 20000)
            sy = [x for x in state()['events'] if x['pubkey'] == spk]
            plain_sync = await bk.ev(f"(()=>{{const sk=__tagKey('nutcade-nip60'); const ck=CashuLib.nip44.v2.utils.getConversationKey(sk, CashuLib.nostrPub(sk)); return {J(sy)}.map(e=>{{try{{return CashuLib.nip44.v2.decrypt(e.content, ck)}}catch(x){{return ''}}}}).join('\\n')}})()")
            check('bunker: wallet sync is under its own key, and its events carry nothing of the connection', sy and all(x['pubkey'] != S['user'] for x in sy) and plain_sync and csk not in plain_sync and S['remote'] not in plain_sync and S['user'] not in plain_sync, (len(sy), len(plain_sync)))
            # locked: nothing signs
            await bk.pg.reload(); await bk.wait(900)
            n = len(get('/test/signer/log')['log'])
            r = await bk.ev("NutId.sign({kind:1, created_at: Math.floor(Date.now()/1000), tags: [], content: 'locked'}).then(()=>'signed', e=>e.message)")
            check('bunker: a locked wallet signs nothing and asks the signer nothing', r != 'signed' and not await bk.ev("NutId.active()") and len(get('/test/signer/log')['log']) == n, r)
            await unlock(bk, PIN)
            check('bunker: unlocked, the identity is back', await bk.ev(f"NutId.active() && NutId.pub() === {J(S['user'])}"))
        await section('bunker', bunker)

        async def signer():
            bk, S = ctx.get('bk'), ctx.get('S')
            if not bk: return
            await bk.ev("Nutcade.closeSheet()")
            U, SP = S['user'], await bk.ev("__seedPub()")
            def nothing(n): return pubs(U, 38000) == n and pubs(SP, 38000) == 0
            post('/test/signer/mode', {'sign': 'refuse'}); n = pubs(U, 38000)
            e = await review(bk, 3, 'refused')
            check('signer: the signer saying no is shown (its text as text), nothing published under any key', 'said no' in e.lower() and 'User said no' in e and nothing(n) and not await bk.ev("!!document.querySelector('#layer img') || !!window.__pwned"), e)
            post('/test/signer/mode', {'sign': 'slow'})
            e = await review(bk, 4, 'slow signer')
            check('signer: a slow signer (3 s) is waited for', not e and pubs(U, 38000) == n + 1, e)
            n = pubs(U, 38000)
            post('/test/signer/mode', {'sign': 'auth'})
            await open_review(bk)
            if await bk.ev("!!document.querySelector('#layer [data-act=rvEdit]')"): await bk.click('#layer [data-act=rvEdit]'); await bk.wait(150)
            await bk.click('#layer [data-act=rvStar][data-n="2"]')
            await bk.ev("(()=>{const t=document.querySelector('#rvText'); t.value='after approving'; t.dispatchEvent(new Event('input',{bubbles:true}));})()")
            pages = len(bk.ctx.pages)
            await bk.click('#layer [data-act=rvPublish]')
            shown = await bk.until("!!document.querySelector('#idAuth a')", 8000)
            a = await bk.ev("(()=>{const a=document.querySelector('#idAuth a'); return a && [a.getAttribute('href'), a.rel, a.target, document.querySelector('#idAuth').innerText, !!document.querySelector('#idAuth b')]})()")
            check('signer: an auth_url is shown as a link you open yourself (https, noopener, as text)', shown and a[0].startswith('https://signer.test/approve') and 'noopener' in a[1] and a[2] == '_blank' and not a[4], a)
            check('signer: ...never opened by the app', await bk.ev("window.__opened") == 0 and len(bk.ctx.pages) == pages)
            await bk.until("!document.querySelector('#layer [data-act=rvPublish] .spinner') && !document.querySelector('#layer #rvBusy')", 20000); await bk.wait(400)
            check('signer: after you approve, the signature arrives and the review goes out', pubs(U, 38000) == n + 1 and not await bk.err(), await bk.err())
            check('signer: the approval link goes away once answered', not await bk.ev("!!document.querySelector('#idAuth a')"))
            await bk.ev("window.__nutcadeTest = {idMs: 4000}")
            for mode, what in (('authjs', 'a javascript: auth_url'), ('swap', 'a swapped event'), ('wrongpub', 'an event by another key'), ('wrongid', 'a reply with another id'), ('huge', 'a huge reply'), ('silent', 'no answer')):
                post('/test/signer/mode', {'sign': mode}); n = pubs(U, 38000); t0 = time.time()
                e = await review(bk, 1, 'bad ' + mode); dt = time.time() - t0
                check(f'signer: {what}: refused with a message, nothing published under any key', e and nothing(n) and dt < 15, (e, round(dt, 1)))
                if mode == 'authjs': check('signer: a javascript: auth_url is never a link and never runs', not await bk.ev("!!document.querySelector('a[href^=\"javascript\"]') || !!window.__pwned"))
                if mode in ('wrongid', 'silent'): check(f'signer: {what}: says the signer didn\'t answer', "didn't answer" in e.lower(), e)
            await bk.ev("window.__nutcadeTest = null")
            post('/test/signer/mode', {'sign': 'ok'})
            # sign out while the remote signer signs
            post('/test/signer/mode', {'sign': 'slow'}); n = pubs(U, 38000)
            await bk.ev(f"(()=>{{ window.__r = NutReview.publish({J(M)}, 3, 'out mid-sign').then(()=>'sent', e=>e.message) }})()")
            await bk.wait(800); await bk.ev("NutId.out()"); await bk.wait(3500)
            r = await bk.ev("window.__r")
            check('signer: signing out while the remote signer signs: nothing is published', r != 'sent' and nothing(n), r)
            post('/test/signer/mode', {'sign': 'ok'})
            v = await bk.ev("JSON.stringify(Nutcade.vault.data)")
            check('signer: Sign out deletes the connection', not await bk.ev("NutId.active()") and '"nid"' not in v and S['remote'] not in v)
            # connect refused / wrong secret / silent
            await bk.ev("window.__nutcadeTest = {idMs: 4000}")
            for mode, want in (('badsecret', 'secret'), ('refuse', 'said no'), ('silent', "didn't answer")):
                S2 = post('/test/signer', {'connect': mode})
                ok = await sign_in_bunker(bk, S2['bunker'])
                e = await bk.err()
                check(f'signer: connect {mode}: not signed in, nothing kept, a clear message', not ok and want in e.lower() and '"nid"' not in await bk.ev("JSON.stringify(Nutcade.vault.data)"), e)
                if mode == 'refuse': check('signer: the signer\'s refusal is shown as text', 'refused' in e and not await bk.ev("!!document.querySelector('#layer b')"), e)
                await bk.ev("Nutcade.closeSheet()")
            await bk.ev("window.__nutcadeTest = null")
            S3 = post('/test/signer', {}); ctx['S'] = S3
            check('signer: signing in again', await sign_in_bunker(bk, S3['bunker']))
            await bk.ev("Nutcade.closeSheet()")
        await section('signer', signer)

        async def duress():
            bk, S = ctx.get('bk'), ctx.get('S')
            if not bk: return
            await settings(bk); await bk.click('[data-act=duressOpen]'); await bk.wait(250)
            await pad(bk, PIN); await bk.wait(800); await pad(bk, DPIN); await bk.wait(300); await pad(bk, DPIN); await bk.until("!!document.querySelector('#duressAmt')", 8000)
            await bk.fill('#duressAmt', '100'); await bk.click('[data-act=duressMake]'); await bk.until("/READY/.test((document.querySelector('.sheet-body')||{}).innerText||'')", 30000); await bk.ev("Nutcade.closeSheet()")
            await bk.pg.reload(); await bk.wait(800); await unlock(bk, DPIN); await bk.wait(800)
            n = len(get('/test/signer/log')['log']); U = S['user']; un = await bk.ev(f"CashuLib.npubEncode({J(U)})")
            check('duress: the duress PIN\'s wallet has no identity (its own 12-word key only)', not await bk.ev("NutId.active()") and await bk.ev(f"NutId.pub() !== {J(U)} && NutId.pub() === __seedPub()"))
            t = await panel(bk)
            check('duress: Settings shows no npub of the real identity, and not signed in', un[:12] not in t and un[-6:] not in t and not await bk.ev("!!document.querySelector('#set-identity [data-act=idOut]')") and await bk.ev("!!document.querySelector('#set-identity [data-act=idBunker]')"), t[:300])
            check('duress: nothing of it in the page', un[:16] not in await bk.ev("document.body.innerHTML") and U not in await bk.ev("document.body.innerHTML"))
            nu = pubs(U, 38000)
            e = await review(bk, 2, 'duress', 20000)
            check('duress: nothing is signed by the real identity, the signer is asked nothing', pubs(U, 38000) == nu and len(get('/test/signer/log')['log']) == n, e)
            S4 = post('/test/signer', {}); await bk.ev("window.__nutcadeTest = {idMs: 5000}")
            t0 = time.time(); ok = await sign_in_bunker(bk, S4['bunker']); dt = time.time() - t0
            await bk.ev("window.__nutcadeTest = null")
            e = await bk.err()
            check('duress: signing in there looks like a signer that doesn\'t answer, and keeps nothing, asks no signer', not ok and e and not get('/test/signer/log')['log'] and '"nid"' not in await bk.ev("JSON.stringify(Nutcade.vault.data)") and dt > 4, (e, round(dt, 1)))
            post('/test/signer', {}); ctx['S'] = None
            await bk.ev("Nutcade.closeSheet()")
            await bk.pg.reload(); await bk.wait(800); await unlock(bk, PIN); await bk.wait(800)
            check('duress: the real wallet still has its identity', await bk.ev(f"NutId.active() && NutId.pub() === {J(U)}"))
        await section('duress', duress)

        async def wipe():
            bk = ctx.get('bk')
            if bk:
                await settings(bk); await bk.click('[data-act=resetAsk]'); await bk.wait(300)
                if await bk.until("!!document.querySelector('[data-pinpad]') || !!document.querySelector('#confirmWord')", 5000) and await bk.ev("!!document.querySelector('[data-pinpad]')"): await pad(bk, PIN)
                await bk.until("!!document.querySelector('#confirmWord')", 8000)
                await bk.fill('#confirmWord', 'RESET'); await bk.click('[data-act=doReset]'); await bk.wait(2500)
                ls = await bk.ev("JSON.stringify(localStorage)")
                check('wipe: after Reset nothing of the connection is left anywhere', not await bk.ev("window.NutId && NutId.active()") and 'nutcade:nid' not in ls and 'nutcade:vault' not in ls, ls[:200])
            # new 12 words: the connection goes too
            await ext_mode(me, 'honest'); await sign_in_ext(me)
            await settings(me); await me.ev("(()=>{const b=document.createElement('button'); b.dataset.act='newSeedAsk'; document.querySelector('#app').appendChild(b); b.click(); b.remove()})()"); await me.until("!!document.querySelector('#confirmWord')", 8000)
            await me.fill('#confirmWord', 'NEW'); await me.click('[data-act=doNewSeed]'); await me.wait(800)
            check('wipe: a new recovery phrase drops the connection', not await me.ev("NutId.active()") and 'nutcade:nid' not in await me.ev("JSON.stringify(localStorage)"))
        await section('wipe', wipe)

        async def offline():
            ox = await wallet(b, 'si-off'); await ox.create(); await ox.add_mint(M)
            await ext_mode(ox, 'honest', EXT_SK, reload=True)
            await ox.ctx.set_offline(True); await ox.wait(300)
            await settings(ox); await ox.click('#set-identity [data-act=idExt]'); await ox.wait(800)
            t = (await ox.err()) + (await ox.toast())
            check('offline: signing in says it needs a connection, nothing kept', 'connection' in t.lower() and not await ox.ev("NutId.active()"), t)
            S5 = post('/test/signer', {})
            ok = await sign_in_bunker(ox, S5['bunker'])
            e = await ox.err()
            check('offline: a remote signer too (no request queued)', not ok and 'connection' in e.lower() and not get('/test/signer/log')['log'], e)
            await ox.ev("Nutcade.closeSheet()"); await ox.ctx.set_offline(False); await ox.wait(300)
            await sign_in_ext(ox); await ox.ctx.set_offline(True); await ox.wait(300)
            r = await ox.ev("NutId.sign({kind:1, created_at: Math.floor(Date.now()/1000), tags: [], content: 'offline'}).then(()=>'signed', e=>e.message)")
            check('offline: signing says it needs a connection', 'connection' in r.lower(), r)
            await ox.ctx.set_offline(False); await ox.pg.context.close()
        await section('offline', offline)

        async def langs():
            for lang in LANGS:
                x = await wallet(b, 'si-' + lang, lang, width=320); await x.create(); await x.add_mint(M)
                await ext_mode(x, 'honest', EXT_SK, reload=True)
                lay = "document.documentElement.scrollWidth > window.innerWidth + 1 || [...document.querySelectorAll('#set-identity *, #layer .sheet *')].some(e=>e.getBoundingClientRect().right > window.innerWidth + 1 || (e.scrollWidth>e.clientWidth+1 && /auto|scroll/.test(getComputedStyle(e).overflowX)===false && getComputedStyle(e).overflowX!=='hidden' && e.tagName!=='INPUT' && e.tagName!=='TEXTAREA'))"
                await panel(x); await x.ev("document.querySelector('#set-identity').scrollIntoView()")
                check(f'{lang} 320px: the identity section fits', not await x.ev(lay))
                await x.click('#set-identity [data-act=idBunker]'); await x.wait(300)
                check(f'{lang} 320px: the remote signer sheet fits', not await x.ev(lay))
                await x.ev("(()=>{const i=document.querySelector('#idLink'); i.value='bunker://nope'; i.dispatchEvent(new Event('input',{bubbles:true}));})()"); await x.click('#layer [data-act=idConnect]'); await x.wait(300)
                check(f'{lang} 320px: with an error it still fits', bool(await x.err()) and not await x.ev(lay))
                await sign_in_ext(x); await panel(x)
                check(f'{lang} 320px: signed in, it fits', not await x.ev(lay))
                await x.click('#set-identity [data-act=idOut]'); await x.wait(300)
                check(f'{lang} 320px: the sign-out sheet fits', not await x.ev(lay))
                await x.ev("Nutcade.closeSheet()")
                if lang != 'en':
                    eng = await x.ev("NutId.texts()")
                    trd = await x.ev(f"{J(eng)}.map(s=>Nutcade.tr(s))")
                    same = [s for s, t in zip(eng, trd) if s == t]
                    miss = await x.ev("[...(window.__i18nMiss||[])].filter(s=>/identity|signer|sign|extension|bunker|npub|nsec|withdraw|connection/i.test(s))")
                    check(f'{lang}: every identity text is translated (errors too), nothing missing on screen', eng and not same and not miss, (same[:3], miss[:3]))
                    if lang == 'fr':
                        frt = ' '.join(trd).lower()
                        check('fr: French uses "vous"', ('vous' in frt or 'votre' in frt) and ' tu ' not in frt and ' ton ' not in frt and ' ta ' not in frt, frt[:200])
                await x.pg.context.close()
        await section('langs', langs)

        check('end: no page errors', not me.errs and not al.errs and not (ctx.get('bk') and ctx['bk'].errs), (me.errs + al.errs)[:5])
        await me.pg.screenshot(path=os.path.join(OUT, 'signin.png'))
        await b.close()
    bad = [r for r in results if not r[1]]
    print('SUMMARY', sum(1 for r in results if r[1]), 'passed,', len(bad), 'failed')

if __name__ == '__main__':
    asyncio.run(main())
