"""Verified-only earnings on real PostgreSQL (opt-in like the other *_postgres tests; LOCAL server only, one
disposable database per test). SQLite cannot prove row locks or transactional DDL, so these are proven here:

* migration d4f6a8c0e2b5 against the schema production runs (b0d2f4a6c8e1): additive, reversible, repeatable,
  the old allocation statuses still accepted, the new one only after the upgrade;
* workers racing on the same earning event record ONE outcome (one missed earning, one reclassification),
  and a sponsor's commission and missed record are mutually exclusive.
Everything is SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.kyc import KYCStatus, KYCVerification
from app.models.missed_earning import MissedEarning
from app.models.user import User
from app.services.new_model_reference_data import seed_new_model_reference_data
from app.services.new_model_revenue import accrue_direct_commission, compute_breakdown, get_policy
from tests.integration.test_advertising_postgres import pg  # noqa: F401  (fixture)
from tests.integration.test_payments_postgres import in_threads, migrate
from tests.unit.test_new_business_model import BASE_ACCOUNTS

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
MIGRATION = "d4f6a8c0e2b5_missed_earnings_kyc_only.py"
OLD_STATUSES = "'ESTIMATED', 'HELD_UNCLAIMED', 'HELD_SPONSOR', 'HELD_REVIEW', 'RELEASED', 'REVERSED', 'SUPERSEDED'"


def to_production_schema(engine) -> None:
    """The model schema taken back to b0d2f4a6c8e1: no missed_earnings, no KYC snapshot, old statuses, no 4030."""
    with engine.begin() as c:
        c.execute(text("DROP TABLE missed_earnings"))
        c.execute(text("ALTER TABLE adv_impression_events DROP COLUMN creative_kyc_approved"))
        c.execute(text("ALTER TABLE adv_impression_events DROP COLUMN sponsor_kyc_approved"))
        c.execute(text("ALTER TABLE adv_allocations DROP CONSTRAINT ck_adv_alloc_status"))
        c.execute(text(f"ALTER TABLE adv_allocations ADD CONSTRAINT ck_adv_alloc_status CHECK (status IN ({OLD_STATUSES}))"))
        c.execute(text("DELETE FROM chart_of_accounts WHERE account_code = '4030'"))


def seed(Session) -> None:
    db = Session()
    for code, kind in BASE_ACCOUNTS.items():
        if not db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first():
            db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind, is_active=True))
    db.flush()
    seed_new_model_reference_data(db)
    db.commit()
    db.close()


def _member(Session, name) -> int:
    db = Session()
    row = User(email=f"{name}@example.com", username=name, hashed_password="x", is_active=True, is_deleted=False,
               date_of_birth=datetime(1990, 1, 1))
    db.add(row)
    db.commit()
    uid = row.id
    db.close()
    return uid


def shape(engine) -> tuple:
    with engine.connect() as c:
        table = c.execute(text("SELECT to_regclass('public.missed_earnings') IS NOT NULL")).scalar()
        cols = c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'adv_impression_events' "
                              "AND column_name IN ('creative_kyc_approved', 'sponsor_kyc_approved')")).scalar()
        status = c.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_adv_alloc_status'")).scalar()
        account = c.execute(text("SELECT count(*) FROM chart_of_accounts WHERE account_code = '4030'")).scalar()
    return table, cols, "MISSED_KYC" in status, account


def test_the_migration_is_additive_reversible_and_repeatable(pg):  # noqa: F811
    engine, Session = pg
    seed(Session)
    to_production_schema(engine)
    _member(Session, "h")                                            # production-like rows survive untouched
    assert shape(engine) == (False, 0, False, 0)
    migrate(engine, MIGRATION, "upgrade")
    assert shape(engine) == (True, 2, True, 1)
    migrate(engine, MIGRATION, "downgrade")
    assert shape(engine) == (False, 0, False, 0)
    migrate(engine, MIGRATION, "upgrade")
    assert shape(engine) == (True, 2, True, 1)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users WHERE email = 'h@example.com'")).scalar() == 1


def test_the_downgrade_refuses_to_drop_recorded_missed_earnings(pg):  # noqa: F811
    engine, Session = pg
    seed(Session)
    uid = _member(Session, "m")
    with engine.begin() as c:
        c.execute(text("INSERT INTO missed_earnings (user_id, category, source_type, source_id, amount, currency, "
                       "kyc_status, event_at, rule_version, status, created_at, updated_at) VALUES "
                       "(:u, 'REFERRAL_COMMISSION', 'DEPOSIT', 1, 2.00, 'USD', 'none', now(), 'V1', 'RECORDED', now(), now())"),
                  {"u": uid})
    with pytest.raises(Exception, match="Missed earnings exist"):
        migrate(engine, MIGRATION, "downgrade")
    assert shape(engine)[0] is True


def _world(Session, *, sponsor_kyc):
    db = Session()
    sponsor = User(email="s@example.com", username="s", hashed_password="x", is_active=True, is_deleted=False,
                   date_of_birth=datetime(1990, 1, 1))
    db.add(sponsor)
    db.flush()
    if sponsor_kyc is not None:
        db.add(KYCVerification(user_id=sponsor.id, status=sponsor_kyc, submitted_at=datetime.utcnow()))
    payer = User(email="p@example.com", username="p", hashed_password="x", is_active=True, is_deleted=False,
                 sponsor_id=sponsor.id, date_of_birth=datetime(1990, 1, 1))
    db.add(payer)
    db.commit()
    ids = sponsor.id, payer.id
    db.close()
    return ids


def _accrue(Session, payer_id):
    db = Session()
    try:
        breakdown = compute_breakdown(get_policy(db, "annual_membership"), Decimal("50.00"))
        result = accrue_direct_commission(db, source_type="DEPOSIT", source_id=4242, payer_user_id=payer_id,
                                          breakdown=breakdown)
        db.commit()
        return result.id if result is not None else None
    finally:
        db.close()


@pytest.mark.parametrize("kyc", [None, KYCStatus.PENDING])
def test_racing_workers_record_one_missed_earning_and_one_reclassification(pg, kyc):  # noqa: F811
    engine, Session = pg
    seed(Session)
    sponsor_id, payer_id = _world(Session, sponsor_kyc=kyc)
    results = in_threads(6, lambda _i: _accrue(Session, payer_id))
    assert not [r for r in results if isinstance(r, Exception)], results
    db = Session()
    [m] = db.query(MissedEarning).all()
    assert (m.user_id, m.amount) == (sponsor_id, Decimal("10.00"))
    assert db.query(AffiliateCommission).count() == 0
    assert db.query(JournalEntry).filter(JournalEntry.source_type == "MISSED_EARNING").count() == 1
    db.close()


def test_racing_workers_for_an_approved_sponsor_create_one_commission_and_no_missed_record(pg):  # noqa: F811
    engine, Session = pg
    seed(Session)
    sponsor_id, payer_id = _world(Session, sponsor_kyc=KYCStatus.APPROVED)
    results = in_threads(6, lambda _i: _accrue(Session, payer_id))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len({r for r in results}) == 1
    db = Session()
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id).count() == 1
    assert db.query(MissedEarning).count() == 0
    db.close()


def test_balances_stay_balanced_on_postgres(pg):  # noqa: F811
    engine, Session = pg
    seed(Session)
    _sponsor, payer_id = _world(Session, sponsor_kyc=KYCStatus.REJECTED)
    _accrue(Session, payer_id)
    with engine.connect() as c:
        d, cr = c.execute(text("SELECT coalesce(sum(debit_amount),0), coalesce(sum(credit_amount),0) FROM journal_lines")).one()
    assert Decimal(d) == Decimal(cr)
    assert AccountType  # imported for the seed's enum
