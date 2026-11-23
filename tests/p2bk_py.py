"""Nutshell's own NUT-28 code (cashu 0.21.0, cashu/core/p2bk.py and cashu/wallet/p2bk.py), run by tests/p2bk_qa.py with the
test-mint Python (MINT_PY): an independent implementation to check NUTCADE's blinding against.
  p2bk_py.py vectors          stdin [{p, e}]: E and the receiver's key P blinded for slots 0..3, and the private keys derived back
  p2bk_py.py slots            stdin {proofs, privs}: for each proof, the slots each private key can sign (Nutshell's own derivation)
  p2bk_py.py pub DIR          the P2PK public key of a Nutshell wallet kept in DIR
  p2bk_py.py send DIR MINT AMOUNT PUBKEY [LOCKSECS REFUND]   a Nutshell-made P2BK token locked to PUBKEY
  p2bk_py.py redeem DIR MINT TOKEN   Nutshell's wallet claims a token (its own key, P2BK keys derived from p2pk_e); prints the amount"""
import asyncio, json, sys
from cashu.core.crypto.secp import PrivateKey, PublicKey
from cashu.core.p2bk import blind_pubkeys, derive_blinded_private_key
from cashu.core.secret import Secret, SecretKind, Tags


def vectors(cases):
    out = []
    for c in cases:
        p = PrivateKey(bytes.fromhex(c['p'])); P = p.public_key.format(compressed=True).hex()
        data, _, refund, E = blind_pubkeys(P, [], [P, P, P], ephemeral_privkey=PrivateKey(bytes.fromhex(c['e'])))
        blinded = [data] + refund
        derived = [derive_blinded_private_key(p, E, b, i) for i, b in enumerate(blinded)]
        out.append({'P': P, 'E': E, 'blinded': blinded, 'derived': [d.to_hex() if d else None for d in derived],
                    'derived_pub': [d.public_key.format(compressed=True).hex() if d else None for d in derived]})
    return out


def slots(d):
    privs = [PrivateKey(bytes.fromhex(x)) for x in d['privs']]
    out = []
    for pr in d['proofs']:
        s = Secret.deserialize(pr['secret'])
        sl = [] if s.kind == SecretKind.HTLC.value else [(0, s.data)]
        pk = s.tags.get_tag_all('pubkeys'); sl += [(i, k) for i, k in enumerate(pk, start=1)]
        off = 1 + len(pk); sl += [(off + i, k) for i, k in enumerate(s.tags.get_tag_all('refund'))]
        got = []
        for j, p in enumerate(privs):
            for i, k in sl:
                dk = derive_blinded_private_key(p, pr['p2pk_e'], k, i)
                if dk is not None and dk.public_key.format(compressed=True).hex() == k: got.append([j, i])
        out.append(got)
    return out


async def wallet(dir, mint):
    from cashu.wallet.wallet import Wallet
    w = await Wallet.with_db(mint, dir, name='p2bk')
    await w.load_mint()
    return w


async def send(dir, mint, amount, pub, locksecs=None, refund=None):
    w = await wallet(dir, mint)
    q = await w.request_mint(amount + 8)
    for _ in range(40):
        try: await w.mint(amount + 8, quote_id=q.quote); break
        except Exception: await asyncio.sleep(0.5)
    tags = Tags()
    if refund: tags['refund'] = [refund]
    lock, E = await w.create_p2bk_lock(pub, locktime_seconds=int(locksecs) if locksecs else None, tags=tags)
    _, sendp = await w.swap_to_send(w.proofs, amount, secret_lock=lock, p2pk_e=E)
    return await w.serialize_proofs(sendp, include_dleq=True)


async def redeem(dir, mint, token):
    from cashu.wallet.helpers import deserialize_token_from_string, receive
    w = await wallet(dir, mint)
    await w.load_proofs()
    before = sum(p.amount for p in w.proofs)
    await receive(w, deserialize_token_from_string(token))
    await w.load_proofs(reload=True)
    return sum(p.amount for p in w.proofs) - before


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'vectors': print(json.dumps(vectors(json.load(sys.stdin))))
    elif a[0] == 'slots': print(json.dumps(slots(json.load(sys.stdin))))
    elif a[0] == 'pub':
        async def pub():
            from cashu.wallet.wallet import Wallet
            w = await Wallet.with_db('http://127.0.0.1:3339', a[1], name='p2bk')
            return w.private_key.public_key.format(compressed=True).hex()
        print(asyncio.run(pub()))
    elif a[0] == 'send': print(asyncio.run(send(a[1], a[2], int(a[3]), a[4], *(a[5:7]))))
    elif a[0] == 'redeem': print(asyncio.run(redeem(a[1], a[2], a[3])))
