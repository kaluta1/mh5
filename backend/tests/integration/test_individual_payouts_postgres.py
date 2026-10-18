"""Individual USDT payouts and wallet approval on REAL PostgreSQL (2026-10-18).

Migration c8e0f2a4b6d8 against a production-like schema, the database rules it
adds, and workers racing. Same safety rules as test_payments_postgres.py: a
DISPOSABLE local database per test, synthetic rows, a fake payout provider.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, PayoutWalletApproval
from app.models.payment import DepositStatus
from app.services import cashout_engine as engine_service
from app.services import payout_wallet_approval as approvals
from app.services.commission_distribution import process_payment_validation
from tests.integration.test_payments_postgres import (  # noqa: F401
    INDIVIDUAL_PAYOUTS,
    _settings,
    cashout_row,
    engine_on,
    in_threads,
    migrate,
    pg,
    refused,
    schema_snapshot,
    seed_ledger,
    slow_provider,
)
from tests.unit.test_dual_cashout import FEE_RULES, NOW, PASSWORD, WALLET, commission, configure, member
from tests.unit.test_new_business_model import _deposit

pytestmark = [pytest.mark.postgres]


def _indexes(engine) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("select indexname, indexdef from pg_indexes where schemaname = 'public' "
                                   "and tablename = 'affiliate_cashout_requests'")).fetchall())


def test_migration_down_and_up_keeps_every_existing_row_and_rebuilds_the_same_schema(pg):
    engine, Session = pg
    built = schema_snapshot(engine)
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO", approved=False)   # production today: no wallet decision yet
        commission(db, user, "5.00")
        db.add(cashout_row(user.id, "completed", "intent:done-1"))
        db.commit()
    with engine.connect() as c:
        before = c.execute(text("select id, status, gross_amount from affiliate_cashout_requests order by id")).fetchall()
    migrate(engine, INDIVIDUAL_PAYOUTS, "downgrade")
    assert "uq_cashout_commission_live" not in _indexes(engine)
    assert "commission_id IS NULL" not in _indexes(engine)["uq_cashout_one_active_per_user"]
    migrate(engine, INDIVIDUAL_PAYOUTS, "upgrade")
    migrate(engine, INDIVIDUAL_PAYOUTS, "upgrade")                     # re-running is a no-op
    assert schema_snapshot(engine) == built
    with engine.connect() as c:
        after = c.execute(text("select id, status, gross_amount from affiliate_cashout_requests order by id")).fetchall()
        assert after == before
        assert c.execute(text("select count(*) from chart_of_accounts where account_code = '1230'")).scalar() == 1


def test_downgrade_refuses_while_individual_payouts_or_wallet_decisions_exist(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")            # its approved wallet is a decision record
    with pytest.raises(Exception, match="payout_wallet_approvals holds records"):
        migrate(engine, INDIVIDUAL_PAYOUTS, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select count(*) from payout_wallet_approvals")).scalar() == 1


def test_the_database_enforces_one_live_payout_per_commission_and_no_self_approval(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        row = commission(db, user, "5.00")
        cid, uid = row.id, user.id

    def attempt(status, ref):
        return lambda db: db.add(AffiliateCashoutRequest(
            user_id=uid, gross_amount=Decimal("5"), fee=0, net_amount=Decimal("5"), status=status,
            cashout_method="CRYPTO", commission_id=cid, payout_reference=ref, requested_at=NOW))

    assert not refused(Session, attempt("failed", "intent:c1-a1"))         # a failed attempt frees it
    assert not refused(Session, attempt("processing", "intent:c1-a2"))
    assert refused(Session, attempt("unknown", "intent:c1-a3"))            # a second live attempt
    assert refused(Session, attempt("completed", "intent:c1-a4"))
    # Several individual payouts of one member may be open together; a pooled one stays one per member.
    other = None
    with Session() as db:
        other = commission(db, db.get(type(user), uid), "2.00").id
    assert not refused(Session, lambda db: db.add(AffiliateCashoutRequest(
        user_id=uid, gross_amount=Decimal("2"), fee=0, net_amount=Decimal("2"), status="processing",
        cashout_method="CRYPTO", commission_id=other, payout_reference="intent:c2-a1", requested_at=NOW)))
    assert not refused(Session, lambda db: db.add(cashout_row(uid, "requested", "intent:pooled-1")))
    assert refused(Session, lambda db: db.add(cashout_row(uid, "requested", "intent:pooled-2")))
    assert refused(Session, lambda db: db.add(PayoutWalletApproval(
        user_id=uid, address=WALLET, currency="usdtbsc", status="APPROVED", submitted_at=NOW,
        decided_by=uid, decided_at=NOW)))                                    # self-approval
    assert refused(Session, lambda db: db.add(PayoutWalletApproval(
        user_id=uid, address=WALLET, currency="usdtbsc", status="MAYBE", submitted_at=NOW)))


def test_concurrent_kyc_payment_callbacks_create_one_commission(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        sponsor = member(db, "sponsor", method="CRYPTO")
        payer = member(db, "payer", sponsor=sponsor, wallet=None)
        dep = _deposit(db, payer, "kyc")
        db.commit()
        dep_id = dep.id

    def callback(_i):
        from app.models.payment import Deposit

        with Session() as db:
            d = db.query(Deposit).filter(Deposit.id == dep_id).with_for_update().one()
            process_payment_validation(db, d, defer_commit=True)
            db.commit()
            return "OK"

    results = in_threads(6, callback)
    assert all(r == "OK" or isinstance(r, Exception) for r in results)
    with Session() as db:
        assert db.query(AffiliateCommission).count() == 1
        assert db.query(AffiliateCommission).one().status.value == "APPROVED"


def test_two_administrators_deciding_the_same_wallet_decide_it_once(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO", approved=False)
        first, second = member(db, "boss1", admin=True), member(db, "boss2", admin=True)
        db.add(PayoutWalletApproval(user_id=user.id, address=WALLET, currency="usdtbsc", status="PENDING",
                                    submitted_at=NOW))
        db.commit()
        pending = db.query(PayoutWalletApproval).filter_by(user_id=user.id).one().id
        admins = [first.id, second.id]

    def decide(i):
        from app.models.user import User

        with Session() as db:
            try:
                row = approvals.decide(db, db.get(User, admins[i]), pending,
                                       decision="APPROVE" if i == 0 else "REJECT",
                                       note="Different decision of the second administrator", password=PASSWORD)
                return row.status
            except approvals.WalletApprovalError as exc:
                return exc.code

    results = in_threads(2, decide)
    assert sorted(results, key=str).count("ALREADY_DECIDED") == 1, results
    with Session() as db:
        row = db.get(PayoutWalletApproval, pending)
        assert row.status in ("APPROVED", "REJECTED") and row.decided_by in admins


def test_workers_racing_with_several_commissions_pay_each_exactly_once(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        users = [member(db, f"m{i}", method="CRYPTO") for i in range(3)]
        for user in users:
            for amount in ("1.00", "2.00"):
                commission(db, user, amount)
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
    provider = slow_provider()

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW)

    reports = in_threads(4, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    assert len(provider.created) == 6
    assert len({c["external_id"] for c in provider.created}) == 6
    with Session() as db:
        ids = [r.commission_id for r in db.query(AffiliateCashoutRequest).filter(
            AffiliateCashoutRequest.status == "processing").all()]
        assert sorted(ids) == sorted(c.id for c in db.query(AffiliateCommission).all())
