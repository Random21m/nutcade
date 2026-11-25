"""Local stand-ins for a Nostr relay and the npub.cash v2 API, used by round2_qa.py.

Run: python mock_nostr.py [port]   (default 3350)
  ws://127.0.0.1:PORT/relay                 Nostr relay (EVENT / REQ / CLOSE, replaceable kinds incl. 10019 and 17375, NIP-09 deletion,
                                            the REQ "limit"; filters by kind, author, ids, since and #tags)
  POST /test/relay_mode {drop, reorder, dup, kinds}  a misbehaving relay (sync_qa.py): drop = say OK but keep nothing; reorder =
                                            answer a REQ in a shuffled order; dup = send every stored event twice. kinds: only these kinds
                                            (default: all). POST /test/relay_mode {} puts it back to normal.
                                            refuse = answer OK false (kinds as above). With "relay": NAME the switches
                                            are for ws://...:PORT/relay?r=NAME instead: r=liar answers every REQ at
                                            once with forged copies (same id and signature, other content) and keeps
                                            nothing; r=empty answers EOSE at once with nothing and keeps nothing;
                                            "delay": seconds before any relay answers a REQ (main included)
  POST /test/inject {event, raw}            store an event as a relay would serve it (raw: without checking its signature, as a lying relay)
  POST /test/forget {ids}                   the relay loses these events
  http://127.0.0.1:PORT/api/v2/...          npub.cash v2: user/info, user/mint, wallet/quotes (NIP-98 auth)
  ws://127.0.0.1:PORT/api/v2/ws/quote       npub.cash quote updates (challenge, then "update" messages)
  POST /test/pay?pubkey=HEX&amount=N&lock=1 test helper: create a (locked) mint quote at the user's mint
  /lnurlw/ID, /lnurlw/ID/cb                 LNURL-withdraw vouchers (LUD-03), set up with POST /test/lnurlw
  /.well-known/lnurlp/NAME, /lnurlp/NAME/cb LNURL-pay with zaps (LUD-06/16, NIP-57), set up with POST /test/lnurlp
  POST /test/profile                        publish a kind-0 profile (with lud16 / lud06) signed by a fresh key
  POST /test/nwc                            act as a Nostr Wallet Connect app (NIP-47, NIP-44 or NIP-04) talking to the wallet
  POST /test/signer {connect, sign, delay}  a NIP-46 remote signer (kind 24133, NIP-44): answers requests sent to it on this
                                            relay; returns its bunker:// link (relay wss://signer.test, which the tests point
                                            here). connect: ok | badsecret | refuse | silent; sign: ok | slow | refuse | auth |
                                            authjs | swap | wrongpub | wrongid | huge | silent. POST /test/signer/mode changes
                                            them; GET /test/signer/log lists the requests it got (method, params)
The LNURL services are reached by the tests as https://lnurl.test/... (Playwright forwards those requests here).
Signatures are checked for real (BIP-340 via coincurve), so a wallet that signs wrongly fails.
"""
import asyncio, base64, hashlib, hmac, json, os, sys, time, urllib.request, urllib.parse
import coincurve
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3350
BASE = f'http://127.0.0.1:{PORT}'
DEFAULT_MINT = 'http://127.0.0.1:3338'
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

events = {}        # id -> event
users = {}         # pubkey -> {mintUrl, name}
quotes = {}        # pubkey -> [quote]
sockets = {}       # pubkey -> set(WebSocket)
log = []
subs = {}        # WebSocket -> {sub_id: [filters]}  (live subscriptions, like a real relay)
reqs = []        # the last REQ filters received (sync_qa.py: the duress wallet never reads)
mode = {}        # a misbehaving relay (POST /test/relay_mode): drop, reorder, dup, refuse, kinds, delay
rmodes = {}      # the same for the named relays (?r=liar, ?r=empty, ...)
req_count = {}   # author -> REQs naming it (never cut)
pub_count = {}   # "pubkey:kind" -> EVENT messages received
import random


def misbehaves(what, kind):
    return bool(mode.get(what)) and (not mode.get('kinds') or kind in mode['kinds'])


def event_id(e):
    return hashlib.sha256(json.dumps([0, e['pubkey'], e['created_at'], e['kind'], e['tags'], e['content']], separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def verify(e):
    try:
        if event_id(e) != e['id']:
            return False
        return coincurve.PublicKeyXOnly(bytes.fromhex(e['pubkey'])).verify(bytes.fromhex(e['sig']), bytes.fromhex(e['id']))
    except Exception:
        return False


def matches(e, f):
    if 'ids' in f and e['id'] not in f['ids']: return False
    if 'kinds' in f and e['kind'] not in f['kinds']: return False
    if 'authors' in f and e['pubkey'] not in f['authors']: return False
    if 'since' in f and e['created_at'] < f['since']: return False
    for k, v in f.items():
        if k.startswith('#') and not any(t[0] == k[1:] and t[1] in v for t in e['tags'] if len(t) > 1): return False
    return True


async def fanout(e):
    for other, ss in list(subs.items()):
        for sid, fs in list(ss.items()):
            if any(matches(e, f) for f in fs):
                try: await other.send_text(json.dumps(['EVENT', sid, e]))
                except Exception: pass


@app.websocket('/relay')
async def relay(ws: WebSocket):
    await ws.accept()
    subs[ws] = {}
    name = ws.query_params.get('r', 'main')
    rm = mode if name == 'main' else rmodes.setdefault(name, {})
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if m[0] == 'EVENT':
                e = m[1]
                ck = f"{e.get('pubkey')}:{e.get('kind')}"; pub_count[ck] = pub_count.get(ck, 0) + 1
                if name in ('liar', 'empty'):   # (keeps nothing)
                    await ws.send_text(json.dumps(['OK', e.get('id'), True, ''])); continue
                ok = verify(e)
                if ok and misbehaves('refuse', e['kind']):
                    await ws.send_text(json.dumps(['OK', e.get('id'), False, 'blocked: refused'])); continue
                if ok and misbehaves('drop', e['kind']):   # (a relay that says OK and keeps nothing)
                    log.append(('dropped', e['kind'], True))
                    await ws.send_text(json.dumps(['OK', e.get('id'), True, '']))
                    continue
                if ok and (30000 <= e['kind'] < 40000 or e['kind'] in (10019, 17375)):   # (parameterized replaceable, NIP-61 nutzap info and the NIP-60 wallet event: one per author)
                    d = next((t[1] for t in e['tags'] if t[0] == 'd'), '')
                    for k, old in list(events.items()):
                        if old['kind'] == e['kind'] and old['pubkey'] == e['pubkey'] and next((t[1] for t in old['tags'] if t[0] == 'd'), '') == d:
                            if old['created_at'] > e['created_at']: ok = False
                            else: del events[k]
                if ok: events[e['id']] = e
                if ok and e['kind'] == 5:   # NIP-09 deletion requests: only the author's own events, up to the request's time
                    for t in e['tags']:
                        if len(t) < 2: continue
                        for k, old in list(events.items()):
                            if old['pubkey'] != e['pubkey'] or old['kind'] == 5 or old['created_at'] > e['created_at']: continue
                            od = next((x[1] for x in old['tags'] if x[0] == 'd'), '')
                            if (t[0] == 'e' and old['id'] == t[1]) or (t[0] == 'a' and t[1] == f"{old['kind']}:{old['pubkey']}:{od}"): del events[k]
                log.append(('event', e['kind'], ok))
                await ws.send_text(json.dumps(['OK', e.get('id'), ok, '' if ok else 'invalid: bad signature or older']))
                if ok: await fanout(e)
                if ok and e['kind'] == 24133: asyncio.create_task(signer_handle(e))
            elif m[0] == 'REQ':
                sub, fs = m[1], m[2:]
                reqs.append(fs); del reqs[:-300]
                for f in fs:
                    for a in f.get('authors') or []: req_count[a] = req_count.get(a, 0) + 1
                if rm.get('delay'): await asyncio.sleep(float(rm['delay']))
                if name == 'empty':
                    await ws.send_text(json.dumps(['EOSE', sub])); continue
                if name == 'liar':
                    for e in [e for e in events.values() if any(matches(e, f) for f in fs)]:
                        x = dict(e); x['content'] = base64.b64encode(os.urandom(120)).decode()
                        await ws.send_text(json.dumps(['EVENT', sub, x]))
                    await ws.send_text(json.dumps(['EOSE', sub])); continue
                hits = sorted([e for e in events.values() if any(matches(e, f) for f in fs)], key=lambda x: -x['created_at'])
                lim = min([f['limit'] for f in fs if isinstance(f.get('limit'), int)] or [len(hits)])
                hits = hits[:max(0, lim)]
                if any(misbehaves('reorder', e['kind']) for e in hits): random.shuffle(hits)
                for e in hits:
                    for _ in range(2 if misbehaves('dup', e['kind']) else 1):
                        await ws.send_text(json.dumps(['EVENT', sub, e]))
                await ws.send_text(json.dumps(['EOSE', sub]))
                subs[ws][sub] = fs
            elif m[0] == 'CLOSE':
                subs[ws].pop(m[1], None)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        subs.pop(ws, None)


def nip98(auth, url, method):
    if not auth or not auth.startswith('Nostr '):
        raise ValueError('missing NIP-98 header')
    e = json.loads(base64.b64decode(auth[6:]))
    if e.get('kind') != 27235 or not verify(e):
        raise ValueError('bad NIP-98 signature')
    tags = {t[0]: t[1] for t in e['tags'] if len(t) > 1}
    if tags.get('u') != url or tags.get('method', '').upper() != method.upper():
        raise ValueError(f"NIP-98 u/method mismatch: {tags} vs {url} {method}")
    if abs(time.time() - e['created_at']) > 120:
        raise ValueError('NIP-98 event too old')
    return e['pubkey']


def user(pk):
    if pk not in users:
        users[pk] = {'pubkey': pk, 'mintUrl': DEFAULT_MINT, 'name': '', 'lockQuote': True}
    return users[pk]


def err(msg, code=401):
    return JSONResponse({'error': True, 'message': msg}, status_code=code)


@app.get('/api/v2/user/info')
async def info(request: Request):
    try: pk = nip98(request.headers.get('authorization'), BASE + '/api/v2/user/info', 'GET')
    except ValueError as e: return err(str(e))
    return {'error': False, 'data': {'user': user(pk)}}


@app.patch('/api/v2/user/mint')
async def set_mint(request: Request):
    try: pk = nip98(request.headers.get('authorization'), BASE + '/api/v2/user/mint', 'PATCH')
    except ValueError as e: return err(str(e))
    body = await request.json()
    user(pk)['mintUrl'] = body['mint_url']
    return {'error': False, 'data': {'user': user(pk)}}


@app.get('/api/v2/wallet/quotes')
async def list_quotes(request: Request, limit: int = 50, offset: int = 0, since: int = 0):
    try: pk = nip98(request.headers.get('authorization'), BASE + '/api/v2/wallet/quotes', 'GET')
    except ValueError as e: return err(str(e))
    qs = [q for q in quotes.get(pk, []) if (q.get('paidAt') or q['createdAt']) >= since]
    return {'error': False, 'data': {'quotes': qs[offset:offset + limit]}, 'metadata': {'limit': limit, 'total': len(qs), 'since': since}}


@app.websocket('/api/v2/ws/quote')
async def quote_ws(ws: WebSocket):
    await ws.accept()
    url = f'ws://127.0.0.1:{PORT}/api/v2/ws/quote'
    await ws.send_text(json.dumps({'type': 'challenge', 'payload': {'url': url, 'method': 'GET'}}))
    pk = None
    try:
        m = json.loads(await ws.receive_text())
        pk = nip98(m.get('payload') if m.get('type') == 'challenge-response' else m.get('token'), url, 'GET')
        sockets.setdefault(pk, set()).add(ws)
        await ws.send_text(json.dumps({'type': 'challenge-success'}))
        while True:
            await ws.receive_text()
    except ValueError as e:
        await ws.send_text(json.dumps({'type': 'error', 'message': str(e)}))
        await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if pk and pk in sockets: sockets[pk].discard(ws)


def post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())


@app.post('/test/pay')
async def pay(pubkey: str, amount: int, lock: int = 1):
    u = user(pubkey)
    body = {'amount': amount, 'unit': 'sat'}
    if lock: body['pubkey'] = '02' + pubkey
    q = await asyncio.to_thread(post, u['mintUrl'] + '/v1/mint/quote/bolt11', body)
    for _ in range(40):   # the fake Lightning backend pays its own invoices after a short delay
        st = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(u['mintUrl'] + '/v1/mint/quote/bolt11/' + q['quote'], timeout=5).read()))
        if st['state'] == 'PAID': break
        await asyncio.sleep(0.25)
    now = int(time.time())
    rec = {'createdAt': now, 'paidAt': now, 'expiresAt': q.get('expiry'), 'mintUrl': u['mintUrl'], 'quoteId': q['quote'], 'request': q['request'], 'amount': amount, 'state': 'PAID', 'locked': bool(lock)}
    quotes.setdefault(pubkey, []).append(rec)
    for ws in list(sockets.get(pubkey, [])):
        try: await ws.send_text(json.dumps({'type': 'update', 'payload': {'quoteId': q['quote']}}))
        except Exception: pass
    return {'ok': True, 'quote': q['quote'], 'sockets': len(sockets.get(pubkey, []))}


posted = []


@app.post('/test/relay_mode')
async def relay_mode(request: Request):
    b = await request.json(); md = mode if b.get('relay', 'main') == 'main' else rmodes.setdefault(b['relay'], {})
    md.clear(); md.update({k: b[k] for k in ('drop', 'reorder', 'dup', 'refuse', 'kinds', 'delay') if k in b})
    return {'mode': md}


@app.post('/test/inject')
async def inject(request: Request):
    b = await request.json(); e = b['event']
    if not b.get('raw') and not verify(e): return {'ok': False}
    events[e['id']] = e; await fanout(e)
    return {'ok': True, 'id': e['id']}


@app.post('/test/forget')
async def forget(request: Request):
    b = await request.json(); n = 0
    for i in b.get('ids', []):
        if events.pop(i, None): n += 1
    return {'forgot': n}


@app.post('/test/post')
async def post_payment(request: Request):
    """Stand-in for a NUT-18 HTTP POST payment request endpoint."""
    posted.append(await request.json())
    return {'ok': True}


@app.get('/test/state')
async def state():
    return {'events': list(events.values()), 'posted': posted, 'users': users, 'quotes': quotes, 'sockets': {k: len(v) for k, v in sockets.items()}, 'log': log[-50:], 'reqs': reqs, 'mode': mode, 'req_count': req_count, 'pub_count': pub_count,
            'vouchers': vouchers, 'payees': payees, 'zaps': zaps}


# ---------------- Nostr helpers: keys, signing, bech32, NIP-44 and NIP-04 ----------------
from cryptography.hazmat.primitives import hashes, padding as cpad
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import bolt11 as b11

def xonly(sk): return coincurve.PublicKeyXOnly.from_secret(bytes.fromhex(sk)).format().hex()

def sign_event(sk, kind, tags, content, created_at=None):
    e = {'pubkey': xonly(sk), 'created_at': created_at or int(time.time()), 'kind': kind, 'tags': tags, 'content': content}
    e['id'] = event_id(e)
    e['sig'] = coincurve.PrivateKey(bytes.fromhex(sk)).sign_schnorr(bytes.fromhex(e['id']), os.urandom(32)).hex()
    return e

B32 = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
def _poly(v):
    g = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; c = 1
    for x in v:
        b = c >> 25; c = (c & 0x1ffffff) << 5 ^ x
        for i in range(5): c ^= g[i] if ((b >> i) & 1) else 0
    return c
def bech32(hrp, data):
    acc = bits = 0; out = []
    for b in data:
        acc = (acc << 8) | b; bits += 8
        while bits >= 5: bits -= 5; out.append((acc >> bits) & 31)
    if bits: out.append((acc << (5 - bits)) & 31)
    ex = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = _poly(ex + out + [0] * 6) ^ 1
    return hrp + '1' + ''.join(B32[d] for d in out + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])

def shared_x(sk, pub): return coincurve.PublicKey(b'\x02' + bytes.fromhex(pub)).multiply(bytes.fromhex(sk)).format(compressed=True)[1:]
def conv_key(sk, pub): return hmac.new(b'nip44-v2', shared_x(sk, pub), hashlib.sha256).digest()
def _keys(ck, nonce):
    k = HKDFExpand(hashes.SHA256(), 76, nonce).derive(ck); return k[:32], k[32:44], k[44:]
def _padlen(n):
    if n <= 32: return 32
    nxt = 1 << (n - 1).bit_length(); chunk = 32 if nxt <= 256 else nxt // 8
    return chunk * ((n - 1) // chunk + 1)
def nip44_enc(text, ck):
    b = text.encode(); padded = len(b).to_bytes(2, 'big') + b + bytes(_padlen(len(b)) - len(b))
    nonce = os.urandom(32); ek, n12, hk = _keys(ck, nonce)
    c = Cipher(algorithms.ChaCha20(ek, b'\0\0\0\0' + n12), None).encryptor().update(padded)
    return base64.b64encode(b'\x02' + nonce + c + hmac.new(hk, nonce + c, hashlib.sha256).digest()).decode()
def nip44_dec(payload, ck):
    d = base64.b64decode(payload); nonce, c, mac = d[1:33], d[33:-32], d[-32:]
    ek, n12, hk = _keys(ck, nonce)
    if d[0] != 2 or not hmac.compare_digest(mac, hmac.new(hk, nonce + c, hashlib.sha256).digest()): raise ValueError('bad nip44 mac')
    p = Cipher(algorithms.ChaCha20(ek, b'\0\0\0\0' + n12), None).decryptor().update(c)
    return p[2:2 + int.from_bytes(p[:2], 'big')].decode()
def nip04_enc(text, sk, pub):
    iv = os.urandom(16); pd = cpad.PKCS7(128).padder(); data = pd.update(text.encode()) + pd.finalize()
    ct = Cipher(algorithms.AES(shared_x(sk, pub)), modes.CBC(iv)).encryptor().update(data)
    return base64.b64encode(ct).decode() + '?iv=' + base64.b64encode(iv).decode()
def nip04_dec(payload, sk, pub):
    ct, iv = payload.split('?iv=')
    d = Cipher(algorithms.AES(shared_x(sk, pub)), modes.CBC(base64.b64decode(iv))).decryptor().update(base64.b64decode(ct))
    u = cpad.PKCS7(128).unpadder(); return (u.update(d) + u.finalize()).decode()

def cors(d, code=200): return JSONResponse(d, status_code=code, headers={'access-control-allow-origin': '*'})
LNURL_BASE = 'https://lnurl.test'


# ---------------- Nostr profiles (kind 0) ----------------
@app.post('/test/profile')
async def profile(request: Request):
    body = await request.json(); sk = os.urandom(32).hex()
    e = sign_event(sk, 0, [], json.dumps(body)); events[e['id']] = e; await fanout(e)
    return {'pubkey': e['pubkey'], 'npub': bech32('npub', bytes.fromhex(e['pubkey'])), 'sk': sk}


# ---------------- LNURL-withdraw vouchers (LUD-03) ----------------
vouchers = {}   # id -> {min, max, desc, mode, k1, used, prs: [], answered}

@app.post('/test/lnurlw')
async def setup_voucher(request: Request):
    b = await request.json(); vid = b['id']
    vouchers[vid] = {'min': b.get('min', 1), 'max': b.get('max', 1000), 'desc': b.get('desc', ''), 'mode': b.get('mode', 'ok'), 'k1': os.urandom(16).hex(), 'used': False, 'prs': [], 'calls': 0}
    url = f'{LNURL_BASE}/lnurlw/{vid}'
    return {'url': url, 'lnurl': bech32('lnurl', url.encode()).upper(), 'lud17': 'lnurlw://' + url[8:], 'k1': vouchers[vid]['k1']}

@app.get('/lnurlw/{vid}')
async def voucher(vid: str):
    v = vouchers.get(vid)
    if not v or v['mode'] == 'gone': return cors({'status': 'ERROR', 'reason': 'Withdraw link not found'}, 404)
    mx = 0 if v['mode'] == 'empty' else v['max']
    return cors({'tag': 'withdrawRequest', 'callback': f'{LNURL_BASE}/lnurlw/{vid}/cb?x=1', 'k1': v['k1'], 'defaultDescription': v['desc'], 'minWithdrawable': v['min'] * 1000, 'maxWithdrawable': mx * 1000})

@app.get('/lnurlw/{vid}/cb')
async def voucher_cb(vid: str, k1: str = '', pr: str = '', x: str = ''):
    v = vouchers.get(vid)
    if not v: return cors({'status': 'ERROR', 'reason': 'Withdraw link not found'}, 404)
    v['calls'] += 1
    if k1 != v['k1']: return cors({'status': 'ERROR', 'reason': 'Bad k1'}, 400)
    if v['mode'] == 'slow': await asyncio.sleep(6)
    if v['mode'] == 'error': return cors({'status': 'ERROR', 'reason': 'Voucher service is out of funds'}, 400)
    if v['used'] or v['mode'] == 'spent': return cors({'status': 'ERROR', 'reason': 'Withdraw link already used'}, 400)
    try: msat = int(b11.decode(pr).amount_msat)
    except Exception: return cors({'status': 'ERROR', 'reason': 'Invalid invoice'}, 400)
    if msat < v['min'] * 1000 or msat > v['max'] * 1000: return cors({'status': 'ERROR', 'reason': 'Amount out of range'}, 400)
    v['used'] = True; v['prs'].append({'pr': pr, 'msat': msat})
    return cors({'status': 'OK'})


# ---------------- LNURL-pay with zaps (LUD-06, LUD-16, NIP-57) ----------------
ZAPPER = os.urandom(32).hex()
payees = {}     # name -> {zap, extra (sats added to the invoice), mint, min, max}
zaps = []       # zap requests received

@app.post('/test/lnurlp')
async def setup_payee(request: Request):
    b = await request.json()
    payees[b['name']] = {'zap': b.get('zap', True), 'extra': b.get('extra', 0), 'mint': b.get('mint', 'http://127.0.0.1:3339'), 'min': b.get('min', 1), 'max': b.get('max', 1000000), 'calls': 0}
    url = f'{LNURL_BASE}/.well-known/lnurlp/{b["name"]}'
    return {'address': f'{b["name"]}@lnurl.test', 'lnurl': bech32('lnurl', url.encode()), 'zapper': xonly(ZAPPER)}

@app.get('/.well-known/lnurlp/{name}')
async def payee(name: str):
    p = payees.get(name)
    if not p: return cors({'status': 'ERROR', 'reason': 'No such user'}, 404)
    d = {'tag': 'payRequest', 'callback': f'{LNURL_BASE}/lnurlp/{name}/cb', 'minSendable': p['min'] * 1000, 'maxSendable': p['max'] * 1000, 'metadata': json.dumps([['text/plain', f'Pay {name}'], ['text/identifier', f'{name}@lnurl.test']]), 'commentAllowed': 100}
    if p['zap']: d.update({'allowsNostr': True, 'nostrPubkey': xonly(ZAPPER)})
    return cors(d)

@app.get('/lnurlp/{name}/cb')
async def payee_cb(name: str, amount: int = 0, nostr: str = '', lnurl: str = '', comment: str = ''):
    p = payees.get(name)
    if not p: return cors({'status': 'ERROR', 'reason': 'No such user'}, 404)
    p['calls'] += 1
    if nostr:
        try: z = json.loads(nostr)
        except Exception: return cors({'status': 'ERROR', 'reason': 'Invalid zap request'}, 400)
        tags = {t[0]: t[1:] for t in z.get('tags', []) if t}
        ok = verify(z) and z.get('kind') == 9734 and tags.get('amount', [''])[0] == str(amount) and len(tags.get('p', [])) == 1 and 'relays' in tags
        zaps.append({'name': name, 'event': z, 'valid': ok, 'amount': amount, 'lnurl': lnurl})
        if not ok: return cors({'status': 'ERROR', 'reason': 'Invalid zap request'}, 400)
    else: zaps.append({'name': name, 'event': None, 'valid': None, 'amount': amount, 'comment': comment})
    sats = amount // 1000 + p['extra']
    q = await asyncio.to_thread(post, p['mint'] + '/v1/mint/quote/bolt11', {'amount': sats, 'unit': 'sat'})
    return cors({'pr': q['request'], 'routes': []})


# ---------------- a Nostr Wallet Connect app (NIP-47) ----------------
def parse_uri(uri):
    u = urllib.parse.urlparse(uri.replace('nostr+walletconnect://', 'nwc://'))
    q = urllib.parse.parse_qs(u.query)
    return u.netloc, q.get('relay', []), q['secret'][0]

@app.post('/test/nwc')
async def nwc_call(request: Request):
    """{uri, method, params, enc: nip44|nip04, wait: seconds, age: seconds in the past, repeat: n (send the same event n times)}"""
    b = await request.json()
    wallet, rel, secret = parse_uri(b['uri'])
    enc = b.get('enc', 'nip44'); ck = conv_key(secret, wallet)
    body = json.dumps({'method': b['method'], 'params': b.get('params', {})})
    content = nip44_enc(body, ck) if enc == 'nip44' else nip04_enc(body, secret, wallet)
    tags = [['p', wallet]] + ([['encryption', 'nip44_v2']] if enc == 'nip44' else [])
    if b.get('expired'): tags.append(['expiration', str(int(time.time()) - 5)])
    e = sign_event(secret, 23194, tags, content, int(time.time()) - int(b.get('age', 0)))
    for _ in range(int(b.get('repeat', 1))):
        events[e['id']] = e; await fanout(e)
    if b.get('nowait'): return {'id': e['id']}
    end = time.time() + float(b.get('wait', 12))
    while time.time() < end:
        for r in list(events.values()):
            if r['kind'] == 23195 and r['pubkey'] == wallet and any(t[0] == 'e' and t[1] == e['id'] for t in r['tags']):
                txt = nip44_dec(r['content'], ck) if any(t[0] == 'encryption' and 'nip44' in t[1] for t in r['tags']) or '?iv=' not in r['content'] else nip04_dec(r['content'], secret, wallet)
                return {'id': e['id'], 'answer': json.loads(txt), 'tags': r['tags'], 'valid': verify(r), 'enc_tag': [t for t in r['tags'] if t[0] == 'encryption']}
        await asyncio.sleep(0.1)
    return {'id': e['id'], 'answer': None}

@app.post('/test/nwc/answer')
async def nwc_answer(request: Request):
    """the answer to an earlier request (sent with nowait), if the wallet gave one"""
    b = await request.json(); wallet, rel, secret = parse_uri(b['uri']); ck = conv_key(secret, wallet)
    end = time.time() + float(b.get('wait', 10))
    while time.time() < end:
        for r in list(events.values()):
            if r['kind'] == 23195 and r['pubkey'] == wallet and any(t[0] == 'e' and t[1] == b['id'] for t in r['tags']):
                txt = nip44_dec(r['content'], ck) if '?iv=' not in r['content'] else nip04_dec(r['content'], secret, wallet)
                return {'answer': json.loads(txt)}
        await asyncio.sleep(0.1)
    return {'answer': None}

@app.post('/test/nwc/notes')
async def nwc_notes(request: Request):
    """notifications (kinds 23196 / 23197) the wallet sent to this app, decrypted, and its info event"""
    b = await request.json(); wallet, rel, secret = parse_uri(b['uri']); ck = conv_key(secret, wallet); me = xonly(secret)
    out = []
    for r in list(events.values()):
        if r['kind'] in (23196, 23197) and r['pubkey'] == wallet and any(t[0] == 'p' and t[1] == me for t in r['tags']):
            try: out.append({'kind': r['kind'], 'note': json.loads(nip44_dec(r['content'], ck) if r['kind'] == 23197 else nip04_dec(r['content'], secret, wallet))})
            except Exception as x: out.append({'kind': r['kind'], 'error': str(x)})
    info = [r for r in events.values() if r['kind'] == 13194 and r['pubkey'] == wallet]
    return {'notes': out, 'info': info[-1] if info else None, 'client': me}



# ---------------- a NIP-46 remote signer (bunker) ----------------
signer = {}   # remote_sk, user_sk, secret, connect, sign, delay, log, clients

@app.post('/test/signer')
async def signer_new(request: Request):
    b = await request.json()
    signer.clear()
    signer.update({'remote_sk': os.urandom(32).hex(), 'user_sk': os.urandom(32).hex(), 'secret': os.urandom(8).hex(), 'connect': b.get('connect', 'ok'),
                   'sign': b.get('sign', 'ok'), 'delay': float(b.get('delay', 0)), 'log': [], 'clients': []})
    rp = xonly(signer['remote_sk'])
    return {'bunker': f"bunker://{rp}?relay=wss://signer.test&secret={signer['secret']}", 'remote': rp, 'user': xonly(signer['user_sk']),
            'user_sk': signer['user_sk'], 'secret': signer['secret']}

@app.post('/test/signer/mode')
async def signer_mode(request: Request):
    b = await request.json()
    for k in ('connect', 'sign', 'delay'):
        if k in b: signer[k] = float(b[k]) if k == 'delay' else b[k]
    return {k: signer.get(k) for k in ('connect', 'sign', 'delay')}

@app.get('/test/signer/log')
async def signer_log():
    return {'log': signer.get('log', []), 'clients': signer.get('clients', [])}

async def signer_send(client, body, created_at=None, sk=None):
    sk = sk or signer['remote_sk']
    e = sign_event(sk, 24133, [['p', client]], nip44_enc(json.dumps(body), conv_key(signer['remote_sk'], client)), created_at)
    events[e['id']] = e; await fanout(e)

async def signer_handle(e):
    if not signer or not any(t[0] == 'p' and len(t) > 1 and t[1] == xonly(signer['remote_sk']) for t in e['tags']): return
    client = e['pubkey']
    try: req = json.loads(nip44_dec(e['content'], conv_key(signer['remote_sk'], client)))
    except Exception as x:
        signer['log'].append({'error': str(x)}); return
    rid, method, params = req.get('id'), req.get('method'), req.get('params') or []
    signer['log'].append({'method': method, 'params': params, 'client': client, 'id': rid})
    if client not in signer['clients']: signer['clients'].append(client)
    if signer['delay']: await asyncio.sleep(signer['delay'])
    if method == 'connect':
        md = signer['connect']
        if md == 'silent': return
        if md == 'refuse': return await signer_send(client, {'id': rid, 'result': '', 'error': 'connection <b>refused</b> by policy'})
        if md == 'badsecret': return await signer_send(client, {'id': rid, 'result': 'not-the-secret-123', 'error': ''})
        ok = len(params) >= 2 and params[0] == xonly(signer['remote_sk']) and params[1] == signer['secret']
        return await signer_send(client, {'id': rid, 'result': 'ack' if ok else '', 'error': '' if ok else 'invalid secret'})
    if method == 'get_public_key':
        return await signer_send(client, {'id': rid, 'result': xonly(signer['user_sk']), 'error': ''})
    if method == 'ping':
        return await signer_send(client, {'id': rid, 'result': 'pong', 'error': ''})
    if method == 'sign_event':
        md = signer['sign']
        try: t = json.loads(params[0])
        except Exception: return await signer_send(client, {'id': rid, 'result': '', 'error': 'bad event'})
        def signed(sk=None, **over):
            x = dict(kind=t['kind'], tags=t['tags'], content=t['content'], created_at=t['created_at']); x.update(over)
            return sign_event(sk or signer['user_sk'], x['kind'], x['tags'], x['content'], x['created_at'])
        if md == 'silent': return
        if md == 'refuse': return await signer_send(client, {'id': rid, 'result': '', 'error': 'User said no <img src=x onerror="window.__pwned=1">'})
        if md == 'slow': await asyncio.sleep(3)
        if md in ('auth', 'authjs'):
            url = 'https://signer.test/approve?req=1&x=<b>' if md == 'auth' else 'javascript:window.__pwned=1'
            await signer_send(client, {'id': rid, 'result': 'auth_url', 'error': url})
            if md == 'authjs': return
            await asyncio.sleep(4)
        if md == 'swap': return await signer_send(client, {'id': rid, 'result': json.dumps(signed(content='swapped by the signer')), 'error': ''})
        if md == 'wrongpub': return await signer_send(client, {'id': rid, 'result': json.dumps(signed(sk=os.urandom(32).hex())), 'error': ''})
        if md == 'wrongid': return await signer_send(client, {'id': 'x' + str(rid), 'result': json.dumps(signed()), 'error': ''})
        if md == 'huge': return await signer_send(client, {'id': rid, 'result': json.dumps(signed()) + ' ' * 300000, 'error': ''})
        return await signer_send(client, {'id': rid, 'result': json.dumps(signed()), 'error': ''})
    await signer_send(client, {'id': rid, 'result': '', 'error': 'unknown method'})


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
