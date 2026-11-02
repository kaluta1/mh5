"""Prompt 6 on real PostgreSQL: concurrent Annual Ads confirmations and refunds (one commission, one
reversal), the Referral Pool reconciliation on real units, the DSM classification and the one-at-a-time sponsor
restoration under concurrency (legacy_import.dsm_members built here with synthetic rows), migration a8d0f2b4c6e9.

Opt-in: RUN_POSTGRES_TESTS=1. One disposable database per test. Everything is SYNTHETIC."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, text

from app.models.accounting import AccountType, AuditTrail, ChartOfAccounts, JournalLine
from app.models.advertising_v2 import AdvAnnualAdsPayment
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import ReferralPoolUnit
from app.models.dsm_restoration import DsmSponsorRestoration
from app.models.user import User
from app.services import annualads_commissions as ac
from app.services import annualads_records, dsm_reconciliation as dsm, referral_pool_reconciliation as pool_rec
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401
from tests.integration.test_referral_pool_accounting_postgres import sponsored_buyer
from tests.integration.test_referral_pool_units_postgres import activate, buy, confirm, member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal


def annual_accounts(Session):
    with Session() as db:
        for code, kind in (("1030", AccountType.ASSET), ("2310", AccountType.LIABILITY), ("4010", AccountType.REVENUE)):
            if not db.query(ChartOfAccounts).filter_by(account_code=code).first():
                db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind, is_active=True))
        db.commit()


def confirm_annual(Session, tx: str, buyer: int, gross="100.00"):
    """What the webhook does after the signature checks, under the same per-payment advisory lock."""
    with Session() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"annualads:{tx}"})
        row = annualads_records.record_payment(db, tx_hash=tx, event="sponsor_payment_confirmed",
                                               payment={"buyer_external_id": str(buyer)}, data={}, raw=b"{}",
                                               gross=D(gross), fee=D("30.00"), net=D(gross) - D("30.00"),
                                               journal_entry_id=None)
        status = ac.decide_commission(db, row)
        db.commit()
        return status


def refund_annual(Session, tx: str, amount="100.00"):
    with Session() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"annualads:{tx}"})
        row = db.query(AdvAnnualAdsPayment).filter_by(tx_hash=tx).with_for_update().one()
        out = ac.handle_refund(db, row, event="sponsor_payment_refunded", amount=D(amount), payload_sha256="x" * 64)
        db.commit()
        return out


def test_concurrent_confirmations_create_one_commission_and_refunds_reverse_once(world):  # noqa: F811
    _engine, Session = world
    annual_accounts(Session)
    buyer, sponsor = sponsored_buyer(Session)
    tx = f"0x{uuid.uuid4().hex}"
    results = in_threads(6, lambda i: confirm_annual(Session, tx, buyer))
    assert set(results) == {"RECORDED"}, results
    with Session() as db:
        rows = db.query(AffiliateCommission).filter_by(source_type=ac.SOURCE_TYPE).all()
        assert [(c.user_id, c.commission_amount, c.level) for c in rows] == [(sponsor, D("20.00"), 1)]
    outcomes = in_threads(4, lambda i: refund_annual(Session, tx))
    assert set(outcomes) == {"REVERSED"}, outcomes
    with Session() as db:
        c = db.query(AffiliateCommission).filter_by(source_type=ac.SOURCE_TYPE).one()
        assert c.status == CommissionStatus.CANCELLED
        d, cr = db.query(func.sum(JournalLine.debit_amount), func.sum(JournalLine.credit_amount)).one()
        assert D(d) == D(cr)
        assert ac.reconciliation(db)["ok"]


def test_pool_reconciliation_is_clean_then_finds_a_tampered_unit(world):  # noqa: F811
    _engine, Session = world
    buyer, _sponsor = sponsored_buyer(Session)
    purchase_id, deposit_id = buy(Session, buyer, 2)
    confirm(Session, deposit_id)
    activate(Session, deposit_id)
    with Session() as db:
        clean = pool_rec.report(db)
        assert clean["ok"], clean["issues"]
        assert clean["counts"]["units_by_status"] == {"ACTIVE": 2}
        before = clean["fingerprint"]
    stranger = member(Session)
    with Session() as db:
        unit = db.query(ReferralPoolUnit).filter_by(purchase_id=purchase_id).first()
        unit.user_id = stranger                                     # simulated corruption, test only
        db.commit()
    with Session() as db:
        found = pool_rec.report(db)
        assert "UNIT_OWNER_MISMATCH" in {i["type"] for i in found["issues"]}
        assert all(i["auto_fix_safe"] is False for i in found["issues"])
        assert found["fingerprint"] != before                       # the holder count moved: a change is visible


# ---------------------------------------------------------------- DSM

def dsm_table(engine):
    with engine.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS legacy_import"))
        c.execute(text("""CREATE TABLE IF NOT EXISTS legacy_import.dsm_members (
            dsm_id integer PRIMARY KEY, mh5_user_id integer, import_status text NOT NULL, sponsor_status text,
            dsm_sponsor_dsm_id integer, resolved_sponsor_mh5_id integer, dsm_joined_at date)"""))


def dsm_row(engine, dsm_id, user_id, status="CREATED", sponsor_dsm=None, sponsor_user=None, sponsor_status="CREATED"):
    with engine.begin() as c:
        c.execute(text("INSERT INTO legacy_import.dsm_members VALUES (:d, :u, :s, :ss, :sd, :su, '2025-01-01')"),
                  {"d": dsm_id, "u": user_id, "s": status, "ss": sponsor_status, "sd": sponsor_dsm, "su": sponsor_user})


def set_sponsor(Session, user_id, sponsor_id):
    with Session() as db:
        db.get(User, user_id).sponsor_id = sponsor_id
        db.commit()


def test_dsm_classification_and_a_single_audited_restoration(world):  # noqa: F811
    engine, Session = world
    dsm_table(engine)
    s1, s2 = member(Session), member(Session)
    linked, orphan, conflicted, nosponsor = member(Session), member(Session), member(Session), member(Session)
    set_sponsor(Session, linked, s1)
    set_sponsor(Session, conflicted, s2)
    dsm_row(engine, 1, s1)
    dsm_row(engine, 2, s2)
    dsm_row(engine, 3, linked, sponsor_dsm=1, sponsor_user=s1)              # verified existing relationship
    dsm_row(engine, 4, orphan, sponsor_dsm=1, sponsor_user=s1)              # no sponsor now: candidate
    dsm_row(engine, 5, conflicted, sponsor_dsm=1, sponsor_user=s1)          # another sponsor now: kept
    dsm_row(engine, 6, nosponsor, sponsor_dsm=99, sponsor_user=None, sponsor_status="SPONSOR_UNRESOLVED_REVIEW")
    dsm_row(engine, 7, None, status="REVIEW_AMBIGUOUS_EMAIL")
    dsm_row(engine, 8, None, status="SKIPPED_INVALID_EMAIL")
    with Session() as db:
        counts = dsm.report(db)["counts"]
        assert counts["VERIFIED_EXISTING_RELATIONSHIP"] == 1 and counts["SAFE_RESTORATION_CANDIDATE"] == 1
        assert counts["CONFLICTING_SPONSOR"] == 1 and counts["AMBIGUOUS_MATCH"] == 1
        assert counts["MISSING_SOURCE_EVIDENCE"] == 2 and counts["VERIFIED_MATCH"] == 2
        assert [c["user_id"] for c in dsm.candidates(db)] == [orphan]
        ledger_before = db.query(func.count(JournalLine.id)).scalar()
        commissions_before = db.query(func.count(AffiliateCommission.id)).scalar()
    admin = member(Session)

    def restore(_i):
        with Session() as db:
            try:
                out = dsm.restore(db, db.get(User, admin), user_id=orphan, note="DSM export record 4, verified")
                db.commit()
                return out["status"]
            except dsm.DsmError as exc:
                db.rollback()
                return exc.code

    results = in_threads(4, restore)
    assert results.count("APPLIED") == 1 and set(results) <= {"APPLIED", "ALREADY_DECIDED", "CHANGED",
                                                               "NOT_A_CANDIDATE"}, results
    with Session() as db:
        u = db.get(User, orphan)
        assert (u.sponsor_id, u.sponsor_source) == (s1, "DSM_RESTORE")
        assert db.query(DsmSponsorRestoration).count() == 1
        assert db.query(AuditTrail).filter_by(action="DSM_SPONSOR_RESTORED").count() == 1
        assert db.query(func.count(JournalLine.id)).scalar() == ledger_before                # no financial effect
        assert db.query(func.count(AffiliateCommission.id)).scalar() == commissions_before   # nothing retroactive
        for target in (conflicted, linked, nosponsor):
            with pytest.raises(dsm.DsmError):
                dsm.restore(db, db.get(User, admin), user_id=target, note="should be refused")
            db.rollback()
        assert db.get(User, conflicted).sponsor_id == s2                                    # never replaced


def test_dsm_restoration_refuses_a_cycle(world):  # noqa: F811
    engine, Session = world
    dsm_table(engine)
    a, b = member(Session), member(Session)
    set_sponsor(Session, b, a)                                                # a -> b exists (b sponsored by a)
    dsm_row(engine, 1, b)
    dsm_row(engine, 2, a, sponsor_dsm=1, sponsor_user=b)                      # restoring a under b = cycle
    with Session() as db:
        assert dsm.report(db)["counts"]["REQUIRES_MANUAL_REVIEW"] == 1
        with pytest.raises(dsm.DsmError) as e:
            dsm.restore(db, db.get(User, a), user_id=a, note="would create a cycle")
        assert e.value.code == "NOT_A_CANDIDATE"


def test_migration_is_additive_and_reversible(world):  # noqa: F811
    engine, Session = world
    migration = "a8d0f2b4c6e9_annualads_commission_dsm_restorations.py"
    with engine.begin() as c:
        c.execute(text("DROP TABLE dsm_sponsor_restorations"))
        c.execute(text("DROP TABLE adv_annualads_events"))
        for col in ("sponsor_user_id", "sponsor_rate", "sponsor_rule_version", "sponsor_commission_id",
                    "sponsor_commission_amount", "sponsor_decided_at", "sponsor_evidence", "refund_status",
                    "refund_event", "refund_amount", "refunded_at", "refund_payload_sha256"):
            c.execute(text(f"ALTER TABLE adv_annualads_payments DROP COLUMN {col}"))
    migrate(engine, migration, "upgrade")
    migrate(engine, migration, "downgrade")
    migrate(engine, migration, "upgrade")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM dsm_sponsor_restorations")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM adv_annualads_events")).scalar() == 0
    annual_accounts(Session)
    buyer, _ = sponsored_buyer(Session)
    confirm_annual(Session, "0xmig", buyer)
    with pytest.raises(Exception, match="cannot be dropped"):
        migrate(engine, migration, "downgrade")
