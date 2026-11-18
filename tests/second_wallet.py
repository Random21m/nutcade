"""A second Cashu wallet for the tests (Nutshell's own wallet, not NUTCADE): claims a token the way any other Cashu
wallet would. Run with the mint environment's Python (MINT_PY):
  python second_wallet.py receive <token>   prints {"ok": true, "amount": <sats now in this wallet>} or {"ok": false, "error": ...}
"""
import asyncio, json, os, sys, tempfile


async def receive(token):
    from cashu.core.base import TokenV4
    from cashu.wallet.helpers import deserialize_token_from_string, receive as recv
    from cashu.wallet.wallet import Wallet
    t = deserialize_token_from_string(token)
    d = tempfile.mkdtemp(prefix='second-wallet-')
    w = await Wallet.with_db(t.mint, os.path.join(d, 'wallet'), name='second')
    await w.load_mint()
    w = await recv(w, t)
    await w.load_proofs()
    return sum(p.amount for p in w.proofs if not p.reserved)


if __name__ == '__main__':
    os.environ.setdefault('TOR', 'false')
    try:
        print(json.dumps({'ok': True, 'amount': asyncio.run(receive(sys.argv[2]))}))
    except Exception as e:
        print(json.dumps({'ok': False, 'error': str(e)[:300]}))
