"""Client-confirmed (2026-09-25) NEW_V2 commission rules:
Referral Pool 20% direct + Leaders revenue, KYC on the full fee, full-price products,
marketplace 20% of markup, Leaders ranking on PAID direct commission only."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.api_v1.endpoints import business_model as bm_api
from app.core.config import settings
from app.models.accounting import JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import LeadersPeriod, ReferralPoolMembership, RevenuePolicy, RevenueRecognition
from app.models.payment import DepositStatus, ProductType
from app.services import leaders_service, legacy_pool_migration, marketplace_service
from app.services import referral_pool_service as pool
from app.services.commission_distribution import process_payment_validation
from app.services.new_model_ledger import PostingType, SourceType, entries_for_source
from app.services.new_model_reference_data import NEW_MODEL_VERSION, REFERRAL_POOL_PRODUCT_CODE
from app.services.new_model_revenue import COMMISSION_BASE_DEFINITION, compute_breakdown, get_policy
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    LAST_MONTH,
    _assert_all_journals_balance,
    _balance,
    _commission,
    _deposit,
    _legacy_world,
    _listing,
    _retired_legacy,
    _revenue,
    _user,
    custodian,
    world,
)

pytestmark = pytest.mark.unit


def _chain(db, prefix):
    """payer -> direct -> l2 -> l3 ... (10 uplines) so a hierarchy walk would be visible."""
    top = _user(db, f"{prefix}-l10@t.com")
    uplines = [top]
    for lvl in range(9, 1, -1):
        uplines.append(_user(db, f"{prefix}-l{lvl}@t.com", sponsor=uplines[-1]))
    direct = _user(db, f"{prefix}-direct@t.com", sponsor=uplines[-1])
    payer = _user(db, f"{prefix}-payer@t.com", sponsor=direct)
    return payer, direct, uplines


def _buy_pool_seat(db, buyer):
    seat = pool.reserve_for_purchase(db, buyer)
    deposit = _deposit(db, buyer, REFERRAL_POOL_PRODUCT_CODE)
    pool.attach_deposit(db, seat, deposit.id)
    return seat, deposit


def _journal_lines_for(db, entry):
    return db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()


# ================================================================ A. Referral Pool

def test_pool_payment_pays_direct_sponsor_exactly_20_and_no_upline(world):
    db = world
    payer, direct, uplines = _chain(db, "rp")
    _, deposit = _buy_pool_seat(db, payer)
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()

    rows = db.query(AffiliateCommission).all()
    assert len(rows) == 1
    c = rows[0]
    assert (c.user_id, c.level, c.commission_amount, c.base_amount, c.commission_rate) == (
        direct.id, 1, Decimal("20.00"), Decimal("100.00"), Decimal("0.2000"))
    assert (c.source_type, c.source_id, c.deposit_id) == (SourceType.DEPOSIT, deposit.id, deposit.id)
    assert c.revenue_category == "REFERRAL_POOL_ENTRY" and c.business_model_version == NEW_MODEL_VERSION
    upline_ids = [u.id for u in uplines]  # Level 2..10
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id.in_(upline_ids)).count() == 0
    assert _balance(db, "2002") == 0 and _balance(db, "2104") == 0  # no multi-level / Founding payable
    # Revenue is the full $100; commission is a separate expense/payable.
    assert _balance(db, "1001") == Decimal("100.00") and _balance(db, "4008") == Decimal("-100.00")
    assert _balance(db, "5001") == Decimal("20.00") and _balance(db, "2001") == Decimal("-20.00")
    _assert_all_journals_balance(db)


def test_pool_payment_enters_leaders_revenue_base(world):
    db = world
    payer, _direct, _ = _chain(db, "lr")
    _, deposit = _buy_pool_seat(db, payer)
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    rec = db.query(RevenueRecognition).one()
    assert (rec.product_code, rec.website_revenue_amount, rec.leaders_revenue_eligible) == (
        REFERRAL_POOL_PRODUCT_CODE, Decimal("100.00"), True)
    now = datetime.utcnow()
    assert leaders_service.eligible_company_revenue(db, now.year, now.month) == Decimal("100.00")


def test_failed_or_pending_pool_payment_creates_no_commission_and_no_leaders_revenue(world):
    db = world
    payer, _direct, _ = _chain(db, "fp")
    pending_seat, pending_dep = _buy_pool_seat(db, payer)
    pending_dep.status = DepositStatus.PENDING
    db.commit()
    # Pending invoice: seat reserved only, nothing earned or recognized.
    assert pending_seat.status == pool.RESERVED
    assert db.query(AffiliateCommission).count() == 0 and db.query(RevenueRecognition).count() == 0
    # Invoice fails: reservation released, still nothing earned.
    pending_dep.status = DepositStatus.FAILED
    pool.release_reservation(db, pending_seat, "invoice failed")
    db.commit()
    assert pending_seat.status == pool.CANCELLED
    assert db.query(AffiliateCommission).count() == 0 and db.query(RevenueRecognition).count() == 0
    assert db.query(JournalEntry).count() == 0
    now = datetime.utcnow()
    assert leaders_service.eligible_company_revenue(db, now.year, now.month) == Decimal("0.00")


def test_pool_payment_retry_cannot_duplicate_commission_journal_or_seat(world):
    db = world
    payer, _direct, _ = _chain(db, "rt")
    _, deposit = _buy_pool_seat(db, payer)
    for _ in range(3):
        process_payment_validation(db, deposit, defer_commit=True)
        db.commit()
    c = db.query(AffiliateCommission).one()
    assert c.commission_amount == Decimal("20.00")
    deposit_entries = entries_for_source(db, SourceType.DEPOSIT, deposit.id)
    assert [e.posting_type for e in deposit_entries] == [PostingType.RECOGNITION]
    commission_entries = entries_for_source(db, SourceType.COMMISSION, c.id)
    assert [e.posting_type for e in commission_entries] == [PostingType.COMMISSION_ACCRUAL]
    assert all(e.idempotency_key for e in deposit_entries + commission_entries)
    assert db.query(RevenueRecognition).count() == 1
    assert db.query(ReferralPoolMembership).filter(ReferralPoolMembership.status == pool.ACTIVE).count() == 1
    assert _balance(db, "2001") == Decimal("-20.00")
    _assert_all_journals_balance(db)


def test_pool_refund_reverses_the_20_commission_and_leaders_revenue(world):
    from app.services.financial_reversal import reverse_provider_refund

    db = world
    payer, _direct, _ = _chain(db, "rf")
    _, deposit = _buy_pool_seat(db, payer)
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    assert reverse_provider_refund(db, deposit, {"refund_amount": "100.00"}) is True
    db.commit()
    assert db.query(AffiliateCommission).one().status == CommissionStatus.CANCELLED
    assert _balance(db, "2001") == 0 and _balance(db, "5001") == 0 and _balance(db, "4008") == 0
    now = datetime.utcnow()
    assert leaders_service.eligible_company_revenue(db, now.year, now.month) == Decimal("0.00")
    _assert_all_journals_balance(db)


def test_legacy_founding_migration_creates_no_commission_revenue_or_journal(world):
    db = world
    users, _d = _legacy_world(db)
    # Give the migrated members a sponsor: a paid pool entry would pay them $20, the migration must not.
    sponsor = _user(db, "legacy-sponsor@t.com")
    for u in users.values():
        u.sponsor_id = sponsor.id
    db.commit()
    journals_before = db.query(JournalEntry).count()
    lines_before = db.query(JournalLine).count()
    built = legacy_pool_migration.build_manifest(db)
    result = legacy_pool_migration.execute(db, expected_sha256=built["sha256"], operator="test")
    db.commit()
    assert result["inserted_deposit_ids"]
    assert db.query(ReferralPoolMembership).filter_by(entitlement_source=pool.SOURCE_LEGACY).count() == len(
        result["inserted_deposit_ids"])
    assert db.query(AffiliateCommission).count() == 0
    assert db.query(RevenueRecognition).count() == 0
    assert (db.query(JournalEntry).count(), db.query(JournalLine).count()) == (journals_before, lines_before)
    now = datetime.utcnow()
    assert leaders_service.eligible_company_revenue(db, now.year, now.month) == Decimal("0.00")


# ================================================================ B. KYC

def test_kyc_full_fee_is_commission_base_and_old_1_60_is_gone(world):
    db = world
    payer, direct, uplines = _chain(db, "kyc")
    breakdown = compute_breakdown(get_policy(db, "kyc"), Decimal("10.00"))
    assert breakdown.provider_cost == Decimal("2.00")  # provider cost still exists ...
    assert breakdown.commission_base == Decimal("10.00")  # ... but does not reduce the base
    assert breakdown.direct_commission == Decimal("2.00") != Decimal("1.60")

    from app.services.new_model_payments import recognize_deferred_deposit

    deposit = _deposit(db, payer, "kyc")
    process_payment_validation(db, deposit, defer_commit=True)
    recognize_deferred_deposit(db, deposit)
    db.commit()
    c = db.query(AffiliateCommission).one()
    assert (c.user_id, c.base_amount, c.commission_amount) == (direct.id, Decimal("10.00"), Decimal("2.00"))
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id.in_([u.id for u in uplines])).count() == 0
    rec = db.query(RevenueRecognition).one()
    assert (rec.gross_amount, rec.provider_cost_amount, rec.website_revenue_amount) == (
        Decimal("10.00"), Decimal("2.00"), Decimal("8.00"))
    assert _balance(db, "2003") == Decimal("-2.00")  # provider cost recognized separately
    assert _balance(db, "5001") == Decimal("2.00")
    _assert_all_journals_balance(db)


def test_kyc_higher_provider_cost_never_changes_commission(world):
    db = world
    policy = get_policy(db, "kyc")
    policy.provider_cost_rate = Decimal("0.50")
    b = compute_breakdown(policy, Decimal("10.00"))
    assert (b.provider_cost, b.website_revenue, b.commission_base, b.direct_commission) == (
        Decimal("5.00"), Decimal("5.00"), Decimal("10.00"), Decimal("2.00"))


# ================================================================ C. other MyHigh5 products

@pytest.mark.parametrize("price,expected", [("10.00", "2.00"), ("50.00", "10.00"), ("100.00", "20.00")])
def test_direct_products_commission_is_full_price_times_20pct(world, price, expected):
    db = world
    payer, direct, uplines = _chain(db, f"p{price}")
    deposit = _deposit(db, payer, "annual_membership", Decimal(price))
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    c = db.query(AffiliateCommission).one()
    assert (c.user_id, c.base_amount, c.commission_amount) == (direct.id, Decimal(price), Decimal(expected))
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id.in_([u.id for u in uplines])).count() == 0
    _assert_all_journals_balance(db)


def test_every_direct_product_policy_uses_full_price(world):
    db = world
    for p in db.query(RevenuePolicy).filter(RevenuePolicy.model_version == NEW_MODEL_VERSION).all():
        if p.product_code == "marketplace_markup":
            continue
        b = compute_breakdown(p, Decimal("100.00"))
        assert b.commission_eligible and b.commission_rate == Decimal("0.2000"), p.product_code
        assert (b.commission_base, b.direct_commission) == (Decimal("100.00"), Decimal("20.00")), p.product_code


# ================================================================ D. marketplace

def test_marketplace_commission_is_20pct_of_markup_only():
    base, markup, total = marketplace_service.price_for_seller_base("100.00")
    assert (base, markup, total) == (Decimal("100.00"), Decimal("20.00"), Decimal("120.00"))


def test_marketplace_order_seller_keeps_100_website_20_commission_4(world, custodian):
    db = world
    sponsor = _user(db, "mk-sponsor@t.com")
    upline = _user(db, "mk-upline@t.com")
    sponsor.sponsor_id = upline.id
    buyer = _user(db, "mk-buyer@t.com", sponsor=sponsor)
    seller = _user(db, "mk-seller@t.com")
    b = compute_breakdown(get_policy(db, "marketplace_markup"), Decimal("120.00"), Decimal("100.00"))
    assert (b.seller_base, b.website_revenue, b.commission_base, b.direct_commission) == (
        Decimal("100.00"), Decimal("20.00"), Decimal("20.00"), Decimal("4.00"))

    order = marketplace_service.create_order(db, buyer_user_id=buyer.id, item_type="digital_product",
                                             item_id=_listing(db, seller).id)
    marketplace_service.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="m-1", custodian_reference="C")
    marketplace_service.mark_fulfilled(db, order, seller_user_id=seller.id)
    marketplace_service.confirm_receipt(db, order, buyer_user_id=buyer.id)
    # Before release the seller liability is exactly the full $100 principal.
    assert _balance(db, "2121") == Decimal("-100.00")
    marketplace_service.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="m-2")
    marketplace_service.apply_custodian_event(db, order, event_type="MARKUP_SETTLED", external_event_id="m-3")
    db.commit()

    assert (order.seller_base_amount, order.markup_amount, order.buyer_total_amount) == (
        Decimal("100.00"), Decimal("20.00"), Decimal("120.00"))
    c = db.query(AffiliateCommission).one()
    assert (c.user_id, c.base_amount, c.commission_amount) == (sponsor.id, Decimal("20.00"), Decimal("4.00"))
    assert c.commission_amount not in (Decimal("24.00"), Decimal("20.00"))
    assert _balance(db, "4007") == Decimal("-20.00")  # website revenue = markup
    assert _balance(db, "5001") == Decimal("4.00")
    assert _balance(db, "2121") == 0  # seller principal released in full, not reduced by commission
    _assert_all_journals_balance(db)


def test_marketplace_stays_disabled_by_default_and_without_custodian(monkeypatch):
    monkeypatch.delenv("MARKETPLACE_ENABLED", raising=False)
    from app.core.config import Settings

    assert Settings().MARKETPLACE_ENABLED is False
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        bm_api._require_marketplace()
    assert exc.value.status_code == 503
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", "")
    with pytest.raises(marketplace_service.CustodianNotConfigured):
        marketplace_service.get_custodian().request_release(None)


# ================================================================ E. Leaders

def test_leaders_ranking_counts_only_paid_direct_commission(world):
    db = world
    a, b, c = (_user(db, f"lp-{k}@t.com") for k in "abc")
    _commission(db, a, 20, status=CommissionStatus.PAID)
    _commission(db, b, 50, status=CommissionStatus.APPROVED)
    _commission(db, c, 100, status=CommissionStatus.PENDING)
    _revenue(db, Decimal("1000.00"))
    db.commit()
    ranked = leaders_service.rank_members(db, LAST_MONTH.year, LAST_MONTH.month)
    totals = {r.user_id: r.direct_commission for r in ranked}
    assert totals == {a.id: Decimal("20.00")}  # B = 0, C = 0
    data = leaders_service.preview(db, LAST_MONTH.year, LAST_MONTH.month)
    assert data["ranking_definition"] == "PAID_DIRECT_COMMISSION_ONLY"
    assert data["total_qualifying_commission"] == Decimal("20.00")  # the denominator
    assert [(l["user_id"], l["reward"]) for l in data["lines"]] == [(a.id, Decimal("50.00"))]


def test_paid_status_without_paid_date_is_not_authoritative(world):
    db = world
    u = _user(db, "lp-nodate@t.com")
    _commission(db, u, 30, status=CommissionStatus.PAID)
    db.flush()
    db.query(AffiliateCommission).filter(AffiliateCommission.user_id == u.id).one().paid_date = None
    db.commit()
    assert leaders_service.rank_members(db, LAST_MONTH.year, LAST_MONTH.month) == []


def test_real_payout_path_makes_a_commission_count(world, monkeypatch):
    """The authoritative PAID state is the one set by the payout service."""
    from app.services import commission_payout_service as payouts

    db = world
    payer, direct, _ = _chain(db, "po")
    process_payment_validation(db, _deposit(db, payer, "annual_membership"), defer_commit=True)
    db.commit()
    now = datetime.utcnow()
    assert leaders_service.rank_members(db, now.year, now.month) == []  # APPROVED, not paid yet

    from app.models.accounting import AccountType, ChartOfAccounts

    for code in payouts._REQUIRED_PAYOUT_ACCOUNTS:
        if not db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first():
            db.add(ChartOfAccounts(account_code=code, account_name=code, is_active=True,
                                   account_type=AccountType.REVENUE if code.startswith("4") else AccountType.LIABILITY))
    db.commit()
    commission = db.query(AffiliateCommission).one()
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    monkeypatch.setattr(payouts, "_validated_payout_target", lambda user: (user.usdt_wallet_address, "usdttrc20"))
    monkeypatch.setattr(payouts, "send_single_payout_sync", lambda **kw: {"id": "prov-123"})
    assert payouts.trigger_commission_payout_sync(db, db.get(type(direct), direct.id), commission) is True
    db.refresh(commission)
    assert commission.status == CommissionStatus.PAID and commission.paid_date is not None
    ranked = leaders_service.rank_members(db, now.year, now.month)
    assert [(r.user_id, r.direct_commission) for r in ranked] == [(direct.id, Decimal("10.00"))]


def test_leaders_never_counts_legacy_or_level_2_to_10_even_if_paid(world):
    db = world
    u = _user(db, "lp-legacy@t.com")
    _commission(db, u, 500, version=None, status=CommissionStatus.PAID)
    for level in range(2, 11):
        _commission(db, u, 100, level=level, status=CommissionStatus.PAID)
    db.commit()
    assert leaders_service.rank_members(db, LAST_MONTH.year, LAST_MONTH.month) == []


def test_top_n_is_decided_by_paid_commission_only(world):
    db = world
    users = [_user(db, f"lp-top{i}@t.com") for i in range(4)]
    _commission(db, users[0], 5, status=CommissionStatus.PAID)
    _commission(db, users[1], 7, status=CommissionStatus.PAID)
    _commission(db, users[2], 1000, status=CommissionStatus.APPROVED)  # unpaid: no place in the top
    _commission(db, users[3], 6, status=CommissionStatus.PAID)
    db.commit()
    ranked = leaders_service.rank_members(db, LAST_MONTH.year, LAST_MONTH.month, limit=2)
    assert [r.user_id for r in ranked] == [users[1].id, users[3].id]


def test_leaders_month_cannot_be_posted_twice(world):
    db = world
    maker, checker, earner = (_user(db, f"lp-{k}@t.com") for k in ("maker", "checker", "earner"))
    _commission(db, earner, 50, status=CommissionStatus.PAID)
    _revenue(db, Decimal("200.00"))
    db.commit()
    period = leaders_service.prepare(db, year=LAST_MONTH.year, month=LAST_MONTH.month, preparer_user_id=maker.id)
    leaders_service.approve(db, period_id=period.id, approver_user_id=checker.id)
    leaders_service.post(db, period_id=period.id)
    leaders_service.post(db, period_id=period.id)  # idempotent
    db.commit()
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.prepare(db, year=LAST_MONTH.year, month=LAST_MONTH.month, preparer_user_id=maker.id)
    assert db.query(LeadersPeriod).filter(LeadersPeriod.status == "POSTED").count() == 1
    assert len(entries_for_source(db, SourceType.LEADERS_PERIOD, period.id)) == 1
    _assert_all_journals_balance(db)


# ================================================================ policy statement

def test_policy_rows_state_the_confirmed_rules(world):
    db = world
    pool_policy = get_policy(db, REFERRAL_POOL_PRODUCT_CODE)
    assert (pool_policy.commission_eligible, pool_policy.commission_rate, pool_policy.leaders_revenue_eligible) == (
        True, Decimal("0.2000"), True)
    assert "PROVISIONAL" not in (pool_policy.notes or "") and "PROVISIONAL" not in (get_policy(db, "kyc").notes or "")
    assert COMMISSION_BASE_DEFINITION == "GROSS_LESS_SELLER_BASE"
    summary = bm_api._commission_policy(db)
    assert summary["referral_pool"]["direct_commission"] == 20.0 and summary["referral_pool"]["leaders_revenue_eligible"]
    assert (summary["kyc"]["commission_base"], summary["kyc"]["direct_commission"]) == (10.0, 2.0)
    assert [p["direct_commission"] for p in summary["other_products"]] == [2.0, 10.0, 20.0]
    mk = summary["marketplace"]
    assert (mk["gross"], mk["seller_base"], mk["commission_base"], mk["direct_commission"]) == (120.0, 100.0, 20.0, 4.0)
    assert summary["leaders_ranking_definition"] == "PAID_DIRECT_COMMISSION_ONLY"
    assert db.query(ProductType).filter(ProductType.code == REFERRAL_POOL_PRODUCT_CODE).one().price == Decimal("100.00")
