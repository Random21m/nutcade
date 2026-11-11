"""Local stand-ins for a Nostr relay and the npub.cash v2 API, used by round2_qa.py.

Run: python mock_nostr.py [port]   (default 3350)
  ws://127.0.0.1:PORT/relay                 Nostr relay (EVENT / REQ / CLOSE, replaceable kinds)
  http://127.0.0.1:PORT/api/v2/...          npub.cash v2: user/info, user/mint, wallet/quotes (NIP-98 auth)
  ws://127.0.0.1:PORT/api/v2/ws/quote       npub.cash quote updates (challenge, then "update" messages)
  POST /test/pay?pubkey=HEX&amount=N&lock=1 test helper: create a (locked) mint quote at the user's mint
Signatures are checked for real (BIP-340 via coincurve), so a wallet that signs wrongly fails.
"""
import asyncio, base64, hashlib, json, sys, time, urllib.request
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
    for k, v in f.items():
        if k.startswith('#') and not any(t[0] == k[1:] and t[1] in v for t in e['tags'] if len(t) > 1): return False
    return True


@app.websocket('/relay')
async def relay(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if m[0] == 'EVENT':
                e = m[1]
                ok = verify(e)
                if ok and 30000 <= e['kind'] < 40000:
                    d = next((t[1] for t in e['tags'] if t[0] == 'd'), '')
                    for k, old in list(events.items()):
                        if old['kind'] == e['kind'] and old['pubkey'] == e['pubkey'] and next((t[1] for t in old['tags'] if t[0] == 'd'), '') == d:
                            if old['created_at'] > e['created_at']: ok = False
                            else: del events[k]
                if ok: events[e['id']] = e
                log.append(('event', e['kind'], ok))
                await ws.send_text(json.dumps(['OK', e.get('id'), ok, '' if ok else 'invalid: bad signature or older']))
            elif m[0] == 'REQ':
                sub, fs = m[1], m[2:]
                hits = [e for e in events.values() if any(matches(e, f) for f in fs)]
                for e in sorted(hits, key=lambda x: -x['created_at']):
                    await ws.send_text(json.dumps(['EVENT', sub, e]))
                await ws.send_text(json.dumps(['EOSE', sub]))
    except (WebSocketDisconnect, RuntimeError):
        pass


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


@app.get('/test/state')
async def state():
    return {'events': list(events.values()), 'users': users, 'quotes': quotes, 'sockets': {k: len(v) for k, v in sockets.items()}, 'log': log[-50:]}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
