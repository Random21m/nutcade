"""Rotates the keys of a stopped local Nutshell test mint (run with the mint's Python, in the mint's folder, with the
mint's environment: MINT_PRIVATE_KEY, MINT_DATABASE, MINT_INPUT_FEE_PPK). Start the mint again afterwards: on start it
keeps the newest active keyset of its derivation path, so the rotation sticks.

  rotate_keyset.py rotate [--fee PPK] [--expiry UNIX]   new active keyset (Nutshell's own rotate_next_keyset: the
                                                       derivation counter + 1), the old one becomes inactive; prints
                                                       the new keyset id
  rotate_keyset.py activate ID                         mark a keyset active again (two active keysets at once)
  rotate_keyset.py deactivate ID                       mark it inactive again
  rotate_keyset.py drop ID                             forget a keyset (the mint no longer lists or accepts it), as a
                                                       mint does once a keyset is past its final expiry
  rotate_keyset.py list                                every keyset: id active fee final_expiry

Nutshell 0.21 also has a management RPC (rotate_next_keyset over gRPC with TLS); this helper calls the same ledger
function directly on the mint's database, so the tests need no certificates."""
import asyncio, sys
from cashu.core.base import Unit
from cashu.core.db import Database
from cashu.core.migrations import migrate_databases
from cashu.core.settings import settings
from cashu.mint import migrations
from cashu.mint.crud import LedgerCrudSqlite
from cashu.mint.ledger import Ledger


async def main(args):
    ledger = Ledger(db=Database('mint', settings.mint_database), seed=settings.mint_private_key, derivation_path=settings.mint_derivation_path, crud=LedgerCrudSqlite())
    await migrate_databases(ledger.db, migrations)
    await ledger.init_keysets()
    cmd = args[0] if args else 'list'
    if cmd == 'rotate':
        fee = int(args[args.index('--fee') + 1]) if '--fee' in args else settings.mint_input_fee_ppk
        exp = int(args[args.index('--expiry') + 1]) if '--expiry' in args else None
        ks = await ledger.rotate_next_keyset(Unit.sat, input_fee_ppk=fee, final_expiry=exp)
        print(ks.id)
    elif cmd in ('activate', 'deactivate'):
        k = ledger.keysets[args[1]]; k.active = cmd == 'activate'
        await ledger.crud.update_keyset(keyset=k, db=ledger.db); print(k.id)
    elif cmd == 'drop':
        await ledger.db.execute(f"DELETE FROM {ledger.db.table_with_schema('keysets')} WHERE id = :id", {'id': args[1]}); print(args[1])
    else:
        for k in ledger.keysets.values():
            if k.unit == Unit.sat: print(k.id, int(bool(k.active)), k.input_fee_ppk, k.final_expiry or '')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1:]))
