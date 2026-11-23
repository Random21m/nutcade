# Test-only: lets the fake Lightning backend take part in multi-path payments (NUT-15),
# so the multinut tests can split one invoice across two local mints. Enabled per mint
# with NUTCADE_FAKE_MPP=1; the real Nutshell code is otherwise unchanged.
import os
if os.environ.get('NUTCADE_FAKE_MPP') == '1':
    try:
        from cashu.lightning import fake
        from cashu.core.base import Amount, Unit
        from cashu.lightning.base import PaymentQuoteResponse
        _orig = fake.FakeWallet.get_payment_quote
        async def _quote(self, melt_quote):
            r = await _orig(self, melt_quote)
            if getattr(melt_quote, 'is_mpp', False):
                amt = Amount(unit=Unit.msat, amount=melt_quote.mpp_amount)
                fee = Amount(unit=Unit.msat, amount=fake.fee_reserve(melt_quote.mpp_amount))
                return PaymentQuoteResponse(checking_id=r.checking_id, fee=fee.to(self.unit, round='up'), amount=amt.to(self.unit, round='up'))
            return r
        fake.FakeWallet.get_payment_quote = _quote
        fake.FakeWallet.supports_mpp = True
    except Exception as e:  # never stop the mint from starting
        print('sitecustomize: MPP patch failed', e)

# Test-only: real payment preimages. Nutshell's fake Lightning hashes a hex string, so its "preimages" never match
# the invoice's payment hash and wallets (rightly) discard them. With NUTCADE_PREIMAGE_DIR set, invoices are made
# from a random 32-byte preimage, kept in that shared folder, and a mint paying another mint's invoice returns it,
# so the wallet gets a preimage that really matches the invoice (as with real Lightning).
_pdir = os.environ.get('NUTCADE_PREIMAGE_DIR')
if _pdir:
    try:
        import hashlib as _h
        from datetime import datetime as _dt
        from cashu.lightning import fake as _f
        from cashu.lightning.base import InvoiceResponse as _IR
        from cashu.core.settings import settings as _s
        from bolt11 import Bolt11 as _B, Feature as _Fe, Features as _Fs, FeatureState as _FS, MilliSatoshi as _M, TagChar as _T, Tags as _Tg, encode as _enc
        import asyncio as _a
        os.makedirs(_pdir, exist_ok=True)
        async def _create(self, amount, memo=None, description_hash=None, unhashed_description=None, expiry=None, payment_secret=None):
            self.assert_unit_supported(amount.unit)
            tags = _Tg()
            tags.add(_T.features, _Fs.from_feature_list({_Fe.payment_secret: _FS.supported}))
            if description_hash: tags.add(_T.description_hash, description_hash.hex())
            elif unhashed_description: tags.add(_T.description_hash, _h.sha256(unhashed_description).hexdigest())
            else: tags.add(_T.description, memo or '')
            tags.add(_T.expire_time, expiry or 3600)
            pre = os.urandom(32); payment_hash = _h.sha256(pre).hexdigest()
            tags.add(_T.payment_secret, (payment_secret or os.urandom(32)).hex())
            tags.add(_T.payment_hash, payment_hash)
            self.payment_secrets[payment_hash] = pre.hex()
            with open(os.path.join(_pdir, payment_hash), 'w') as fh: fh.write(pre.hex())
            from cashu.core.base import Unit as _U
            # (usd and eur at FakeWallet's own fixed rate, exactly as its create_invoice does: a multi-unit test mint)
            amount_msat = _M(amount.to(_U.msat, round='up').amount) if amount.unit in (_U.sat, _U.msat) else _M(__import__('math').ceil(amount.amount / self.fake_btc_price * 1e9))
            b = _B(currency='bc', amount_msat=amount_msat, date=int(_dt.now().timestamp()), tags=tags)
            self.created_invoices.append(b)
            pr = _enc(b, self.privkey)
            if _s.fakewallet_brr: _a.create_task(self.mark_invoice_paid(b))
            return _IR(ok=True, checking_id=payment_hash, payment_request=pr)
        _f.FakeWallet.create_invoice = _create
        _orig_pay = _f.FakeWallet.pay_invoice
        async def _pay(self, quote, fee_limit):
            r = await _orig_pay(self, quote, fee_limit)
            try:
                h = _f.decode(quote.request).payment_hash
                p = os.path.join(_pdir, h)
                if getattr(r, 'preimage', None) in (None, '0' * 64) and os.path.exists(p): r.preimage = open(p).read().strip()
            except Exception: pass
            return r
        _f.FakeWallet.pay_invoice = _pay
    except Exception as e:  # never stop the mint from starting
        print('sitecustomize: preimage patch failed', e)

# Test-only: hold a deposit's mint request at the mint, so a test can force two copies of it to overlap there (the
# race behind a "Mint quote already pending" answer) instead of hoping for the timing. With NUTCADE_HOLD_DIR set, a
# file named mint-<quote id> in that folder holds that quote's mint request (up to 60 s, until the file is removed):
# "pending" right after the mint marks the quote PENDING (an identical copy then gets 20005, quote pending), "store"
# after it has also stored the request's outputs (an identical copy then gets 11004, outputs pending). While it holds,
# the file mint-<quote id>.held exists.
_hdir = os.environ.get('NUTCADE_HOLD_DIR')
if _hdir:
    try:
        import asyncio as _ha, time as _ht
        from cashu.mint import ledger as _hl
        from cashu.mint.db import write as _hw
        os.makedirs(_hdir, exist_ok=True)
        async def _hold(qid, mode):
            p = os.path.join(_hdir, 'mint-' + str(qid)); t = _ht.time()
            while _ht.time() - t < 60:
                try: m = open(p).read().strip()
                except Exception: return
                if m != mode: return
                if not os.path.exists(p + '.held'): open(p + '.held', 'w').write(mode)   # (the test sees it is held here now)
                await _ha.sleep(0.05)
        _o_pend = _hw.DbWriteHelper._set_mint_quote_pending
        async def _set_pending(self, quote_id, *a, **k):
            r = await _o_pend(self, quote_id, *a, **k); await _hold(quote_id, 'pending'); return r
        _hw.DbWriteHelper._set_mint_quote_pending = _set_pending
        _o_store = _hl.Ledger._store_blinded_messages
        async def _store(self, outputs, *a, **k):
            r = await _o_store(self, outputs, *a, **k)
            if k.get('mint_id'): await _hold(k['mint_id'], 'store')
            return r
        _hl.Ledger._store_blinded_messages = _store
    except Exception as e:  # never stop the mint from starting
        print('sitecustomize: hold patch failed', e)
