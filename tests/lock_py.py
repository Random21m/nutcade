"""Nutshell's own wallet code (cashu 0.21.0), run by tests/lib_qa.py with the test-mint Python (MINT_PY): an independent
implementation to check NUTCADE and its bundled cashu-ts against.
  lock_py.py derive              stdin {words, keyset, n}: Nutshell's NUT-13 secrets for counters 0..n-1 of that keyset
  lock_py.py send DIR MINT AMOUNT stdin {kind, data, tags}: a token of AMOUNT whose coins carry exactly that NUT-10 lock
                                 (each coin its own nonce), made by a Nutshell wallet kept in DIR, with DLEQ proofs
  lock_py.py y                   stdin [secret, ...]: Nutshell's NUT-00 hash_to_curve Y of each (secp256k1, compressed hex)"""
import asyncio, json, sys


async def derive(d):
    from mnemonic import Mnemonic
    from bip32 import BIP32
    from cashu.wallet.secrets import WalletSecrets
    w = object.__new__(WalletSecrets)
    w.seed = Mnemonic('english').to_seed(d['words']); w.bip32 = BIP32.from_seed(w.seed)
    out = []
    for c in range(int(d['n'])):
        s, _, _ = await w.generate_determinstic_secret(c, d['keyset'])
        out.append(s.hex())
    return out


async def send(dir, mint, amount, lock):
    from cashu.core.secret import Secret, Tags
    from cashu.wallet.wallet import Wallet
    w = await Wallet.with_db(mint, dir, name='lock')
    await w.load_mint()
    q = await w.request_mint(amount + 8)
    for _ in range(40):
        try: await w.mint(amount + 8, quote_id=q.quote); break
        except Exception: await asyncio.sleep(0.5)
    sec = Secret(kind=lock['kind'], data=lock['data'], tags=Tags(tags=lock.get('tags') or []))
    _, sendp = await w.swap_to_send(w.proofs, amount, secret_lock=sec)
    return await w.serialize_proofs(sendp, include_dleq=True)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'derive': print(json.dumps(asyncio.run(derive(json.load(sys.stdin)))))
    elif a[0] == 'y':
        from cashu.core.crypto.b_dhke import hash_to_curve
        print(json.dumps([hash_to_curve(x.encode()).format().hex() for x in json.load(sys.stdin)]))
    elif a[0] == 'send': print(asyncio.run(send(a[1], a[2], int(a[3]), json.load(sys.stdin))))
