"""A small OpenID Connect provider standing in for a mint's login server (NUT-21), used by auth_qa.py and the auth test mint.

Run: python mock_oidc.py [port]   (default 3348; the auth test mint, 3347, reads its discovery document at start)
  GET  /.well-known/openid-configuration   discovery: issuer, jwks_uri, token_endpoint, device_authorization_endpoint,
                                           authorization_endpoint (each can be left out or bent with /test/config)
  GET  /jwks                               the RS256 public key (kid "k1")
  POST /device                             device authorization grant (RFC 8628): device_code, user_code, verification_uri, interval 1
  GET  /activate?user_code=X               the page a person opens: approves that code at once (stands in for logging in there)
  GET  /authorize                          authorization code + PKCE (S256): redirects straight back with a code (no login page)
  POST /token                              grants: device_code (authorization_pending until approved), authorization_code (PKCE
                                           checked), refresh_token (fails with invalid_grant after /test/expire)
  POST /test/approve {user_code?}          approve that code (or every waiting one)
  POST /test/expire                        "expire now": every refresh token is revoked (the next refresh gets invalid_grant)
  POST /test/config {...}                  ttl (access token lifetime, s), down (every endpoint answers 503), delay (s before each
                                           answer), no_device, no_code (leave those endpoints out of discovery), token_endpoint /
                                           device_endpoint (replace them in discovery: a hostile document), sub (the account)
  POST /test/reset                         everything back to the start
  GET  /test/state                         counts of each grant, the codes, and the last refresh tokens seen
Access tokens are real RS256 JWTs (iss = this server, azp = cashu-client, sub = the account), checked by the mint for real.
"""
import asyncio, base64, hashlib, json, secrets, sys, time, urllib.parse
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
import uvicorn

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3348
BASE = f'http://127.0.0.1:{PORT}'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
JWK.update({'kid': 'k1', 'use': 'sig', 'alg': 'RS256'})
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


def start_state():
    return {'cfg': {'ttl': 3600, 'down': False, 'delay': 0, 'no_device': False, 'no_code': False, 'token_endpoint': None, 'device_endpoint': None, 'sub': 'player-1'},
            'devices': {}, 'codes': {}, 'refresh': {}, 'revoked': False,
            'n': {'device': 0, 'device_ok': 0, 'code': 0, 'refresh': 0, 'refresh_bad': 0, 'discovery': 0, 'activate': 0}}


ST = start_state()


def tokens(sub):
    now = int(time.time()); ttl = int(ST['cfg']['ttl'])
    at = jwt.encode({'iss': BASE, 'sub': sub, 'azp': 'cashu-client', 'aud': 'account', 'iat': now, 'exp': now + ttl, 'jti': secrets.token_hex(8)}, KEY, algorithm='RS256', headers={'kid': 'k1'})
    rt = 'rt-' + secrets.token_hex(16); ST['refresh'][rt] = sub
    return {'access_token': at, 'refresh_token': rt, 'token_type': 'Bearer', 'expires_in': ttl}


async def form(req):   # (application/x-www-form-urlencoded, read by hand: no python-multipart needed)
    return {k: v[0] for k, v in urllib.parse.parse_qs((await req.body()).decode()).items()}


async def gate():
    if ST['cfg']['delay']: await asyncio.sleep(float(ST['cfg']['delay']))
    if ST['cfg']['down']: return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503)
    return None


@app.get('/.well-known/openid-configuration')
async def discovery():
    g = await gate()
    if g: return g
    ST['n']['discovery'] += 1; c = ST['cfg']
    d = {'issuer': BASE, 'jwks_uri': BASE + '/jwks', 'token_endpoint': c['token_endpoint'] or BASE + '/token', 'response_types_supported': ['code'],
         'grant_types_supported': ['authorization_code', 'refresh_token', 'urn:ietf:params:oauth:grant-type:device_code'], 'code_challenge_methods_supported': ['S256']}
    if not c['no_device']: d['device_authorization_endpoint'] = c['device_endpoint'] or BASE + '/device'
    if not c['no_code']: d['authorization_endpoint'] = BASE + '/authorize'
    return d


@app.get('/jwks')
async def jwks(): return {'keys': [JWK]}


@app.post('/device')
async def device(req: Request):
    g = await gate()
    if g: return g
    f = await form(req); ST['n']['device'] += 1
    dc, uc = 'dc-' + secrets.token_hex(12), '%04d-%04d' % (secrets.randbelow(10000), secrets.randbelow(10000))
    ST['devices'][dc] = {'user_code': uc, 'ok': False, 'client': f.get('client_id'), 'at': time.time()}
    return {'device_code': dc, 'user_code': uc, 'verification_uri': BASE + '/activate', 'verification_uri_complete': BASE + '/activate?user_code=' + uc, 'expires_in': 600, 'interval': 1}


@app.get('/activate')
async def activate(user_code: str = ''):
    ST['n']['activate'] += 1
    for d in ST['devices'].values():
        if d['user_code'] == user_code: d['ok'] = True
    return HTMLResponse('<!doctype html><title>Logged in</title><p>You are logged in. Go back to the wallet.</p>')


@app.get('/authorize')
async def authorize(request: Request):
    q = request.query_params
    if q.get('code_challenge_method') != 'S256' or not q.get('code_challenge'): return JSONResponse({'error': 'invalid_request'}, status_code=400)
    code = 'code-' + secrets.token_hex(10)
    ST['codes'][code] = {'challenge': q['code_challenge'], 'redirect': q.get('redirect_uri'), 'client': q.get('client_id')}
    sep = '&' if '?' in q.get('redirect_uri', '') else '?'
    return RedirectResponse(q['redirect_uri'] + sep + 'code=' + code + '&state=' + q.get('state', ''), status_code=302)


@app.post('/token')
async def token(req: Request):
    g = await gate()
    if g: return g
    f = await form(req); gt = f.get('grant_type'); sub = ST['cfg']['sub']
    bad = lambda e, s=400: JSONResponse({'error': e}, status_code=s)
    if gt == 'urn:ietf:params:oauth:grant-type:device_code':
        d = ST['devices'].get(f.get('device_code') or '')
        if not d: return bad('invalid_grant')
        if not d['ok']: return bad('authorization_pending')
        del ST['devices'][f.get('device_code')]; ST['n']['device_ok'] += 1
        return tokens(sub)
    if gt == 'authorization_code':
        c = ST['codes'].pop(f.get('code') or '', None)
        if not c: return bad('invalid_grant')
        v = f.get('code_verifier') or ''
        if base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode() != c['challenge'] or f.get('redirect_uri') != c['redirect']: return bad('invalid_grant')
        ST['n']['code'] += 1
        return tokens(sub)
    if gt == 'refresh_token':
        rt = f.get('refresh_token') or ''
        if ST['revoked'] or rt not in ST['refresh']: ST['n']['refresh_bad'] += 1; return bad('invalid_grant')
        ST['n']['refresh'] += 1
        return tokens(ST['refresh'][rt])
    return bad('unsupported_grant_type')


@app.post('/test/approve')
async def approve(req: Request):
    b = await req.json() if (await req.body()) else {}
    for d in ST['devices'].values():
        if not b.get('user_code') or d['user_code'] == b['user_code']: d['ok'] = True
    return {'ok': True}


@app.post('/test/expire')
async def expire(): ST['revoked'] = True; return {'ok': True}


@app.post('/test/config')
async def config(req: Request): ST['cfg'].update(await req.json()); return ST['cfg']


@app.post('/test/reset')
async def reset():
    global ST
    ST = start_state(); return {'ok': True}


@app.get('/test/state')
async def state(): return {'n': ST['n'], 'revoked': ST['revoked'], 'waiting': [d['user_code'] for d in ST['devices'].values() if not d['ok']], 'cfg': ST['cfg']}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
