"""SoncoPay payouts on REAL PostgreSQL: migration c9e1f3a5b7d0 and workers racing. A DISPOSABLE local
database per test (test_payments_postgres.pg), synthetic rows, an in-process fake of SoncoPay."""
from __future__ import annotations

import threading

import httpx
import pytest
from sqlalchemy import text

from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission
from app.models.checkout_gateway import SoncoPayPayoutDestination
from app.services import cashout_engine as engine_service
from app.services import payment_config
from app.services import soncopay_payouts as spo
from tests.integration.test_payments_postgres import engine_on, in_threads, migrate, pg, seed_ledger  # noqa: F401
from tests.unit.test_dual_cashout import FEE_RULES, NOW, commission, configure, member
from tests.unit.test_soncopay_payouts import FakeSoncoPay, soncopay_live

pytestmark = [pytest.mark.postgres, pytest.mark.discontinued]

MIGRATION = "c9e1f3a5b7d0_soncopay_payout_destinations.py"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    from app.core.config import settings

    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://api.example.test")


def test_migration_down_and_up_is_additive_and_downgrade_refuses_with_destinations(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select to_regclass('soncopay_payout_destinations')")).scalar() is None
    migrate(engine, MIGRATION, "upgrade")
    migrate(engine, MIGRATION, "upgrade")                               # re-running is a no-op
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        approval = db.execute(text("select id from payout_wallet_approvals where user_id = :u"), {"u": user.id}).scalar()
        db.add(SoncoPayPayoutDestination(user_id=user.id, wallet_approval_id=approval, address=user.usdt_wallet_address,
                                         environment="live", status="QUEUED"))
        db.commit()
        with pytest.raises(Exception):                                  # one destination per approval
            db.add(SoncoPayPayoutDestination(user_id=user.id, wallet_approval_id=approval, address="x",
                                             environment="live", status="QUEUED"))
            db.commit()
        db.rollback()
    with pytest.raises(Exception, match="holds payout destinations"):
        migrate(engine, MIGRATION, "downgrade")


def test_workers_racing_pay_each_commission_exactly_once(pg, engine_on, monkeypatch):
    _engine, Session = pg
    fake, lock = FakeSoncoPay(), threading.Lock()

    def handler(request):
        with lock:
            return fake.handler(request)

    monkeypatch.setattr(spo, "_transport", lambda: httpx.MockTransport(handler))
    with Session() as db:
        seed_ledger(db)
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "provider_fee_mode": payment_config.FEE_MODE_ADDED})
        soncopay_live(db)
        users = [member(db, f"m{i}", method="CRYPTO", wallet="0x" + str(i + 1) * 40) for i in range(3)]
        for user in users:
            for amount in ("2.00", "3.00"):
                commission(db, user, amount)
        user_ids = [u.id for u in users]
        engine_service.run_cycle(db, now=NOW)                            # registers the three wallets
        for pid in list(fake.destinations):
            fake.confirm(pid, usable=True)

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, now=NOW)

    reports = in_threads(4, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    assert len(fake.payouts) == 6 and len(fake.posts("/v1/payouts")) == 6
    assert len({p["reference"] for p in fake.payouts.values()}) == 6
    with Session() as db:
        ids = sorted(r.commission_id for r in db.query(AffiliateCashoutRequest)
                     .filter(AffiliateCashoutRequest.status == "processing").all())
        assert ids == sorted(c.id for c in db.query(AffiliateCommission).filter(
            AffiliateCommission.user_id.in_(user_ids)).all())
