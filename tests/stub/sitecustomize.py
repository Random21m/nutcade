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
