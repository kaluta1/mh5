"""NEW_V2 business model: direct affiliate, Referral Pool, legacy Founding migration,
MyHigh5 Leaders, structured accounting, marketplace custody/dispute and the cutover."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.crud.crud_affiliate import affiliate_tree
from app.crud.crud_user import user as crud_user
from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.business_model import (
    BusinessModelVersion,
    LeadersAllocationLine,
    LeadersPeriod,
    MarketOrder,
    ReferralPoolAssignment,
    ReferralPoolConfig,
    ReferralPoolMembership,
    RevenueRecognition,
)
from app.models.dsp import DigitalProduct
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import leaders_service, legacy_pool_migration, marketplace_service
from app.services import referral_pool_service as pool
from app.services.commission_distribution import process_payment_validation
from app.services.financial_reversal import reverse_provider_refund
from app.services.new_model_ledger import (
    PostingType,
    SourceType,
    entries_for_source,
    model_version_for_new_event,
)
from app.services.new_model_payments import recognize_deferred_deposit
from app.services.new_model_reference_data import (
    LEGACY_MODEL_VERSION,
    NEW_MODEL_VERSION,
    REFERRAL_POOL_PRODUCT_CODE,
    seed_new_model_reference_data,
)

pytestmark = pytest.mark.unit

BASE_ACCOUNTS = {
    "1000": AccountType.ASSET, "1001": AccountType.ASSET, "1200": AccountType.ASSET,
    "2000": AccountType.LIABILITY, "2001": AccountType.LIABILITY, "2002": AccountType.LIABILITY,
    "2003": AccountType.LIABILITY, "2100": AccountType.LIABILITY, "2104": AccountType.LIABILITY,
    "2110": AccountType.LIABILITY, "2111": AccountType.LIABILITY, "2113": AccountType.LIABILITY,
    "4000": AccountType.REVENUE, "4001": AccountType.REVENUE, "4002": AccountType.REVENUE,
    "5000": AccountType.EXPENSE, "5001": AccountType.EXPENSE,
}
PASSWORD = "Str0ng!Passw0rd#26"


@pytest.fixture(autouse=True)
def _retired_legacy(monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False)


@pytest.fixture
def world(db):
    for code, kind in BASE_ACCOUNTS.items():
        db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind, is_active=True))
    db.flush()
    for code, price in [("kyc", 10), ("annual_membership", 50), ("efm_membership", 99),
                        ("mfm_membership", 100), ("founding_membership", 100)]:
        db.add(ProductType(code=code, name=code, price=price, currency="USD", validity_days=365))
    db.flush()
    seed_new_model_reference_data(db)
    version = db.query(BusinessModelVersion).one()
    version.effective_at = datetime.utcnow() - timedelta(days=1)
    db.commit()
    return db


def _user(db, email, *, sponsor=None, wallet=True, active=True) -> User:
    row = User(email=email, hashed_password="x", username=email.split("@")[0], is_active=active, is_deleted=False,
               sponsor_id=sponsor.id if sponsor else None, personal_referral_code=email.split("@")[0].upper(),
               usdt_wallet_address=("0x" + "1" * 40) if wallet else None)
    db.add(row)
    db.flush()
    return row


def _product(db, code) -> ProductType:
    return db.query(ProductType).filter(ProductType.code == code).one()


def _deposit(db, user, code, amount=None, *, version=NEW_MODEL_VERSION, deposit_id=None, **extra) -> Deposit:
    product = _product(db, code)
    kwargs = dict(user_id=user.id, product_type_id=product.id, amount=amount if amount is not None else product.price,
                  currency="USD", status=DepositStatus.VALIDATED, order_id=f"o-{code}-{user.id}-{deposit_id or ''}-{extra.get('tag', '')}",
                  external_payment_id=f"np-{user.id}-{code}-{deposit_id or ''}", business_model_version=version)
    extra.pop("tag", None)
    kwargs.update(extra)
    if deposit_id is not None:
        kwargs["id"] = deposit_id
    row = Deposit(**kwargs)
    db.add(row)
    db.flush()
    return row


def _balance(db, code) -> Decimal:
    """Signed debit - credit for an account."""
    rows = db.query(JournalLine).join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id) \
        .filter(ChartOfAccounts.account_code == code).all()
    return sum((Decimal(str(r.debit_amount)) - Decimal(str(r.credit_amount)) for r in rows), Decimal("0"))


def _assert_all_journals_balance(db):
    for entry in db.query(JournalEntry).all():
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert sum(Decimal(str(l.debit_amount)) for l in lines) == sum(Decimal(str(l.credit_amount)) for l in lines), entry.description


# ================================================================ direct affiliate

def test_direct_sponsor_earns_20pct_of_website_revenue_and_upline_earns_nothing(world):
    db = world
    l3 = _user(db, "l3@t.com")
    l2 = _user(db, "l2@t.com", sponsor=l3)
    direct = _user(db, "direct@t.com", sponsor=l2)
    payer = _user(db, "payer@t.com", sponsor=direct)
    deposit = _deposit(db, payer, "annual_membership")

    assert process_payment_validation(db, deposit, defer_commit=True) is True
    db.commit()

    rows = db.query(AffiliateCommission).all()
    assert len(rows) == 1
    c = rows[0]
    assert (c.user_id, c.level, c.commission_amount, c.base_amount) == (direct.id, 1, Decimal("10.00"), Decimal("50.00"))
    assert c.business_model_version == NEW_MODEL_VERSION and c.source_type == SourceType.DEPOSIT
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id.in_([l2.id, l3.id])).count() == 0
    assert _balance(db, "4002") == Decimal("-50.00")  # revenue gross of commission
    assert _balance(db, "5001") == Decimal("10.00") and _balance(db, "2001") == Decimal("-10.00")
    assert _balance(db, "2104") == 0 and _balance(db, "2002") == 0  # no Founding pool, no L2-10 payable
    _assert_all_journals_balance(db)


def test_kyc_commission_is_20pct_of_full_fee_provider_cost_separate_and_only_on_recognition(world):
    db = world
    sponsor = _user(db, "ks@t.com")
    payer = _user(db, "kp@t.com", sponsor=sponsor)
    deposit = _deposit(db, payer, "kyc")
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    assert db.query(AffiliateCommission).count() == 0  # service not performed yet
    assert _balance(db, "2113") == Decimal("-10.00")

    assert recognize_deferred_deposit(db, deposit) is True
    assert recognize_deferred_deposit(db, deposit) is False  # idempotent
    db.commit()
    c = db.query(AffiliateCommission).one()
    # Confirmed rule: full $10 is the commission base -> $2.00 (the old $1.60 is gone).
    assert (c.base_amount, c.commission_amount) == (Decimal("10.00"), Decimal("2.00"))
    assert c.commission_amount != Decimal("1.60")
    # Provider cost stays a separate pass-through; it does not reduce the commission.
    assert _balance(db, "4001") == Decimal("-8.00") and _balance(db, "2003") == Decimal("-2.00")
    assert _balance(db, "5001") == Decimal("2.00") and _balance(db, "2001") == Decimal("-2.00")
    assert _balance(db, "2113") == 0
    _assert_all_journals_balance(db)


def test_duplicate_processing_creates_one_commission_and_one_journal_set(world):
    db = world
    sponsor = _user(db, "ds@t.com")
    payer = _user(db, "dp@t.com", sponsor=sponsor)
    deposit = _deposit(db, payer, "annual_membership")
    for _ in range(3):
        process_payment_validation(db, deposit, defer_commit=True)
        db.commit()
    assert db.query(AffiliateCommission).count() == 1
    assert len(entries_for_source(db, SourceType.DEPOSIT, deposit.id)) == 1
    assert db.query(RevenueRecognition).count() == 1


def test_inactive_direct_sponsor_gets_nothing_and_nothing_rolls_up(world):
    db = world
    upline = _user(db, "up@t.com")
    inactive = _user(db, "inactive@t.com", sponsor=upline, active=False)
    payer = _user(db, "ip@t.com", sponsor=inactive)
    process_payment_validation(db, _deposit(db, payer, "annual_membership"), defer_commit=True)
    db.commit()
    assert db.query(AffiliateCommission).count() == 0


def test_refund_reverses_exactly_its_own_revenue_and_commission(world):
    db = world
    sponsor = _user(db, "rs@t.com")
    a = _user(db, "ra@t.com", sponsor=sponsor)
    b = _user(db, "rb@t.com", sponsor=sponsor)
    dep_a = _deposit(db, a, "annual_membership", deposit_id=5)
    dep_b = _deposit(db, b, "annual_membership", deposit_id=51)
    for d in (dep_a, dep_b):
        process_payment_validation(db, d, defer_commit=True)
    db.commit()

    assert reverse_provider_refund(db, dep_a, {"refund_amount": "50.00"}) is True
    assert reverse_provider_refund(db, dep_a, {"refund_amount": "50.00"}) is True  # idempotent
    comm_a = db.query(AffiliateCommission).filter(AffiliateCommission.source_id == 5).one()
    comm_b = db.query(AffiliateCommission).filter(AffiliateCommission.source_id == 51).one()
    assert comm_a.status == CommissionStatus.CANCELLED and comm_b.status != CommissionStatus.CANCELLED
    assert _balance(db, "4002") == Decimal("-50.00")  # only #51's revenue remains
    assert _balance(db, "2001") == Decimal("-10.00")
    reversals = db.query(JournalEntry).filter(JournalEntry.posting_type == PostingType.REVERSAL).all()
    originals = {db.get(JournalEntry, r.reverses_entry_id) for r in reversals}
    assert all(o.source_id in (5, comm_a.id) for o in originals)  # never #51
    assert db.query(RevenueRecognition).filter(RevenueRecognition.reverses_id.isnot(None)).count() == 1
    _assert_all_journals_balance(db)


def test_legacy_refund_text_match_no_longer_collides_5_with_51(world):
    db = world
    user = _user(db, "lg@t.com")
    cash = db.query(ChartOfAccounts).filter_by(account_code="1001").one()
    rev = db.query(ChartOfAccounts).filter_by(account_code="4002").one()
    deposits = {}
    for dep_id in (5, 51):
        deposits[dep_id] = _deposit(db, user, "annual_membership", version=None, deposit_id=dep_id, tag=str(dep_id))
        je = JournalEntry(entry_number=f"JE-L-{dep_id}", entry_date=datetime.utcnow(), total_debit=50, total_credit=50,
                          description=f"Membership Payment - Deposit #{dep_id} - User #{user.id}", status="posted")
        db.add(je)
        db.flush()
        db.add_all([JournalLine(entry_id=je.id, account_id=cash.id, debit_amount=50, credit_amount=0),
                    JournalLine(entry_id=je.id, account_id=rev.id, debit_amount=0, credit_amount=50)])
    db.commit()
    reverse_provider_refund(db, deposits[5], {"refund_amount": "50.00"})
    reversal = db.query(JournalEntry).filter(JournalEntry.description == "Refund reversal - Deposit #5").one()
    assert Decimal(str(reversal.total_debit)) == Decimal("50.00")  # only #5 mirrored, not #51


# ================================================================ referral pool

def test_referral_pool_purchase_activates_seat_books_revenue_and_pays_direct_sponsor_20(world):
    db = world
    sponsor = _user(db, "ps@t.com")
    buyer = _user(db, "pb@t.com", sponsor=sponsor)
    seat = pool.reserve_for_purchase(db, buyer)
    deposit = _deposit(db, buyer, REFERRAL_POOL_PRODUCT_CODE)
    pool.attach_deposit(db, seat, deposit.id)
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    m = db.query(ReferralPoolMembership).one()
    assert (m.status, m.entitlement_source, m.source_deposit_id, m.seat_number) == (pool.ACTIVE, pool.SOURCE_PAID, deposit.id, 1)
    assert _balance(db, "4008") == Decimal("-100.00")
    c = db.query(AffiliateCommission).one()  # confirmed policy: direct sponsor earns 20%
    assert (c.user_id, c.level, c.base_amount, c.commission_amount) == (sponsor.id, 1, Decimal("100.00"), Decimal("20.00"))


def test_pool_capacity_is_enforced_and_expired_or_failed_reservations_free_seats(world):
    db = world
    db.query(ReferralPoolConfig).one().capacity = 2
    u1, u2, u3 = (_user(db, f"c{i}@t.com") for i in range(3))
    s1 = pool.reserve_for_purchase(db, u1)
    pool.reserve_for_purchase(db, u2)
    with pytest.raises(pool.PoolFull):
        pool.reserve_for_purchase(db, u3)
    pool.release_reservation(db, s1, "invoice failed")
    s3 = pool.reserve_for_purchase(db, u3)
    assert s3.seat_number == 1
    s3.reservation_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()
    assert pool.reserve_for_purchase(db, u1).seat_number == 1  # expired seat reclaimed
    assert pool.seats_in_use(db) == 2


def test_database_rejects_two_holders_of_the_same_seat(world):
    db = world
    u1, u2 = _user(db, "x1@t.com"), _user(db, "x2@t.com")
    db.add(ReferralPoolMembership(user_id=u1.id, status=pool.ACTIVE, seat_number=7, entitlement_source=pool.SOURCE_PAID))
    db.flush()
    db.add(ReferralPoolMembership(user_id=u2.id, status=pool.ACTIVE, seat_number=7, entitlement_source=pool.SOURCE_PAID))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_race_on_the_last_seat_never_creates_member_capacity_plus_one(world, monkeypatch):
    """Simulates the stale read of a concurrent buyer: both pick seat 1; the DB lets only one hold it."""
    db = world
    db.query(ReferralPoolConfig).one().capacity = 1
    first, second = _user(db, "r1@t.com"), _user(db, "r2@t.com")
    pool.reserve_for_purchase(db, first)
    monkeypatch.setattr(pool, "_lowest_free_seat", lambda _db, _cap: 1)  # stale view: seat 1 looks free
    with pytest.raises(pool.ReferralPoolError):
        pool.reserve_for_purchase(db, second)
    assert db.query(ReferralPoolMembership).filter(ReferralPoolMembership.status.in_(pool.SEAT_STATUSES)).count() == 1


def test_payment_after_lapsed_reservation_with_full_pool_goes_to_review_not_over_capacity(world):
    db = world
    db.query(ReferralPoolConfig).one().capacity = 1
    late, other = _user(db, "late@t.com"), _user(db, "other@t.com")
    seat = pool.reserve_for_purchase(db, late)
    deposit = _deposit(db, late, REFERRAL_POOL_PRODUCT_CODE)
    pool.attach_deposit(db, seat, deposit.id)
    seat.reservation_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()
    pool.reserve_for_purchase(db, other)  # lapsed seat is reclaimed by someone else
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    parked = db.query(ReferralPoolMembership).filter_by(source_deposit_id=deposit.id).one()
    assert parked.status == pool.CAPACITY_REVIEW and parked.seat_number is None
    assert pool.seats_in_use(db) == 1
    assert _balance(db, "2100") == Decimal("-100.00") and _balance(db, "4008") == 0


# ================================================================ sponsor assignment

def _register(db, email, code=None) -> User:
    return crud_user.create_with_sponsor(db, UserCreate(email=email, password=PASSWORD, username="user_" + email.split("@")[0]),
                                         sponsor_code=code)


def _pool_member(db, email) -> User:
    u = _user(db, email)
    db.add(ReferralPoolMembership(user_id=u.id, status=pool.ACTIVE, seat_number=db.query(ReferralPoolMembership).count() + 1,
                                  entitlement_source=pool.SOURCE_PAID, joined_at=datetime.utcnow()))
    db.commit()
    return u


def test_personal_referral_wins_over_pool(world):
    db = world
    _pool_member(db, "pm@t.com")
    personal = _user(db, "personal@t.com")
    db.commit()
    new = _register(db, "newbie@t.com", personal.personal_referral_code)
    assert (new.sponsor_id, new.sponsor_source) == (personal.id, "PERSONAL_REFERRAL")
    assert db.query(ReferralPoolAssignment).count() == 0


def test_organic_and_invalid_code_signups_get_fair_pool_sponsors_with_audit(world):
    db = world
    a, b = _pool_member(db, "pa@t.com"), _pool_member(db, "pb@t.com")
    first = _register(db, "o1@t.com")
    second = _register(db, "o2@t.com", "NOT-A-REAL-CODE")
    assert {first.sponsor_id, second.sponsor_id} == {a.id, b.id}  # fewest-assignments tier -> one each
    assert first.sponsor_source == second.sponsor_source == "REFERRAL_POOL"
    rows = db.query(ReferralPoolAssignment).all()
    assert {r.referred_user_id for r in rows} == {first.id, second.id}
    assert all(r.method == "FAIR_RANDOM_V1" and r.candidate_count == 2 for r in rows)


def test_no_pool_member_leaves_no_sponsor_and_join_code_cannot_overwrite_assigned_sponsor(world):
    db = world
    lonely = _register(db, "lonely@t.com")
    assert lonely.sponsor_id is None and lonely.sponsor_source == "NONE"
    member = _pool_member(db, "pm2@t.com")
    assigned = _register(db, "assigned@t.com")
    assert assigned.sponsor_id == member.id
    other = _user(db, "other2@t.com")
    db.commit()
    result = affiliate_tree.join_via_referral(db, assigned.id, other.personal_referral_code)
    assert result["success"] is False
    db.refresh(assigned)
    assert assigned.sponsor_id == member.id
    with pytest.raises(IntegrityError):  # a user can never get a second pool assignment
        db.add(ReferralPoolAssignment(referred_user_id=assigned.id, pool_member_user_id=member.id, membership_id=1,
                                      method="X", candidate_count=1, min_assignment_count=0, assigned_at=datetime.utcnow()))
        db.flush()
    db.rollback()


# ================================================================ legacy Founding migration

def _cash_journal(db, deposit, amount=100):
    cash = db.query(ChartOfAccounts).filter_by(account_code="1001").one()
    deferred = db.query(ChartOfAccounts).filter_by(account_code="2111").one()
    je = JournalEntry(entry_number=f"JE-F-{deposit.id}", entry_date=datetime.utcnow(), total_debit=amount, total_credit=amount,
                      description=f"Founding Membership Payment - Deposit #{deposit.id} - User #{deposit.user_id} (Deferred receipt)",
                      status="posted")
    db.add(je)
    db.flush()
    db.add_all([JournalLine(entry_id=je.id, account_id=cash.id, debit_amount=amount, credit_amount=0),
                JournalLine(entry_id=je.id, account_id=deferred.id, debit_amount=0, credit_amount=amount)])
    db.flush()


def _legacy_world(db):
    users = {k: _user(db, f"{k}@legacy.com") for k in ("mfm", "fm", "admin_granted", "efm", "refunded", "pending", "dup", "nojournal")}
    d = {}
    d["mfm"] = _deposit(db, users["mfm"], "mfm_membership", version=None)
    d["fm"] = _deposit(db, users["fm"], "founding_membership", version=None)
    d["admin"] = _deposit(db, users["admin_granted"], "mfm_membership", version=None, order_id="ADMIN-abc",
                          external_payment_id=None, validated_by=users["mfm"].id)
    d["efm"] = _deposit(db, users["efm"], "efm_membership", version=None)
    d["refunded"] = _deposit(db, users["refunded"], "mfm_membership", version=None, status=DepositStatus.FAILED,
                             admin_notes="Provider refund reconciled at 2026-01-01Z")
    d["pending"] = _deposit(db, users["pending"], "mfm_membership", version=None, status=DepositStatus.PENDING)
    d["dup1"] = _deposit(db, users["dup"], "mfm_membership", version=None, tag="a")
    d["dup2"] = _deposit(db, users["dup"], "founding_membership", version=None, tag="b")
    d["nojournal"] = _deposit(db, users["nojournal"], "mfm_membership", version=None)
    for key in ("mfm", "fm", "admin", "efm", "dup1", "dup2"):
        _cash_journal(db, d[key])
    db.commit()
    return users, d


def test_legacy_founding_classification_by_payment_evidence(world):
    db = world
    users, d = _legacy_world(db)
    by_dep = {c.deposit_id: c for c in legacy_pool_migration.classify(db)}
    assert by_dep[d["mfm"].id].classification == legacy_pool_migration.AUTOMATIC
    assert by_dep[d["fm"].id].classification == legacy_pool_migration.AUTOMATIC
    assert by_dep[d["dup1"].id].classification == legacy_pool_migration.AUTOMATIC
    assert "ADMIN_GRANTED_NO_PROVIDER_PAYMENT" in by_dep[d["admin"].id].reasons
    assert by_dep[d["admin"].id].classification == legacy_pool_migration.MANUAL
    assert by_dep[d["dup2"].id].reasons == ["DUPLICATE_EXTRA_FOUNDING_PAYMENT"]
    assert by_dep[d["nojournal"].id].reasons == ["NO_CASH_JOURNAL"]
    assert by_dep[d["refunded"].id].classification == legacy_pool_migration.NOT_ELIGIBLE
    assert by_dep[d["pending"].id].classification == legacy_pool_migration.NOT_ELIGIBLE
    assert d["efm"].id not in by_dep  # EFM is never a $100 Founding product


def test_legacy_migration_executes_only_reviewed_manifest_is_idempotent_and_changes_no_money(world):
    db = world
    users, d = _legacy_world(db)
    built = legacy_pool_migration.build_manifest(db)
    with pytest.raises(legacy_pool_migration.MigrationAborted):
        legacy_pool_migration.execute(db, expected_sha256="0" * 64, operator="test")
    db.rollback()
    result = legacy_pool_migration.execute(db, expected_sha256=built["sha256"], operator="test")
    db.commit()
    assert sorted(result["inserted_deposit_ids"]) == sorted([d["mfm"].id, d["fm"].id, d["dup1"].id])
    seats = db.query(ReferralPoolMembership).all()
    assert {s.user_id for s in seats} == {users["mfm"].id, users["fm"].id, users["dup"].id}
    assert all(s.entitlement_source == pool.SOURCE_LEGACY and s.status == pool.ACTIVE for s in seats)
    assert db.query(Deposit).count() == result["before"]["deposits"]  # no payment manufactured
    assert result["before"]["journal_lines"] == result["after"]["journal_lines"]
    rerun = legacy_pool_migration.build_manifest(db)
    assert rerun["manifest"]["to_insert_deposit_ids"] == []
    again = legacy_pool_migration.execute(db, expected_sha256=rerun["sha256"], operator="test")
    assert again["inserted_deposit_ids"] == []


def test_legacy_migration_refuses_to_exceed_capacity(world):
    db = world
    _legacy_world(db)
    db.query(ReferralPoolConfig).one().capacity = 2
    db.commit()
    built = legacy_pool_migration.build_manifest(db)
    assert built["manifest"]["would_exceed_capacity_by"] == 1
    with pytest.raises(legacy_pool_migration.MigrationAborted):
        legacy_pool_migration.execute(db, expected_sha256=built["sha256"], operator="test")
    db.rollback()
    assert db.query(ReferralPoolMembership).count() == 0


# ================================================================ MyHigh5 Leaders

LAST_MONTH = (datetime.utcnow().replace(day=1) - timedelta(days=1))


def _commission(db, user, amount, *, level=1, version=NEW_MODEL_VERSION, when=None, status=CommissionStatus.PAID, src=[0]):
    src[0] += 1
    db.add(AffiliateCommission(user_id=user.id, source_user_id=user.id, commission_type=CommissionType.KYC_PAYMENT, level=level,
                               commission_amount=Decimal(str(amount)), base_amount=0, status=status,
                               paid_date=datetime.utcnow() if status == CommissionStatus.PAID else None,
                               transaction_date=when or LAST_MONTH.replace(day=10), business_model_version=version,
                               source_type="TEST" if version else None, source_id=src[0] if version else None))


def _revenue(db, amount, *, eligible=True, when=None, src=[0]):
    src[0] += 1
    db.add(RevenueRecognition(model_version=NEW_MODEL_VERSION, source_type="TEST", source_id=src[0],
                              idempotency_key=f"t:{src[0]}", product_code="x", revenue_category="X", gross_amount=amount,
                              website_revenue_amount=amount, leaders_revenue_eligible=eligible,
                              recognized_at=when or LAST_MONTH.replace(day=5)))


def test_leaders_ranks_direct_commission_only_and_allocates_5pct_exactly(world):
    db = world
    a, b, c, legacy_user = (_user(db, f"ld{i}@t.com") for i in range(4))
    _commission(db, a, 30)
    _commission(db, b, 20)
    _commission(db, c, 10)
    _commission(db, legacy_user, 500, version=None)  # old model: ignored
    _commission(db, legacy_user, 500, level=2)  # never counted
    _commission(db, b, 999, status=CommissionStatus.CANCELLED)
    _revenue(db, Decimal("1000.00"))
    _revenue(db, Decimal("777.00"), eligible=False)  # a policy marked not Leaders-eligible: excluded
    _revenue(db, Decimal("-100.00"))  # a refund nets out
    db.commit()

    data = leaders_service.preview(db, LAST_MONTH.year, LAST_MONTH.month)
    assert data["eligible_company_revenue"] == Decimal("900.00") and data["pool_amount"] == Decimal("45.00")
    assert [l["user_id"] for l in data["lines"]] == [a.id, b.id, c.id]
    assert [l["reward"] for l in data["lines"]] == [Decimal("22.50"), Decimal("15.00"), Decimal("7.50")]
    assert sum(l["reward"] for l in data["lines"]) == data["pool_amount"]


def test_leaders_limit_rounding_remainder_and_zero_denominator():
    Ranked = leaders_service.Ranked
    now = datetime.utcnow()
    three = [Ranked(1, Decimal("1"), now), Ranked(2, Decimal("1"), now), Ranked(3, Decimal("1"), now)]
    lines = leaders_service.allocate(Decimal("10.00"), three)
    assert [l[2] for l in lines] == [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]
    assert leaders_service.allocate(Decimal("10.00"), []) == []
    assert [l[2] for l in leaders_service.allocate(Decimal("0"), three)] == [Decimal("0.00")] * 3


def test_leaders_top_n_cut(world):
    db = world
    users = [_user(db, f"top{i}@t.com") for i in range(5)]
    for i, u in enumerate(users):
        _commission(db, u, 10 + i)
    db.commit()
    ranked = leaders_service.rank_members(db, LAST_MONTH.year, LAST_MONTH.month, limit=3)
    assert [r.user_id for r in ranked] == [users[4].id, users[3].id, users[2].id]


def test_leaders_workflow_maker_checker_idempotent_post_and_audited_reversal(world):
    db = world
    maker, checker, earner = _user(db, "maker@t.com"), _user(db, "checker@t.com"), _user(db, "earner@t.com")
    _commission(db, earner, 50)
    _revenue(db, Decimal("200.00"))
    db.commit()
    y, m = LAST_MONTH.year, LAST_MONTH.month
    now = datetime.utcnow()
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.prepare(db, year=now.year, month=now.month, preparer_user_id=maker.id)
    p = leaders_service.prepare(db, year=y, month=m, preparer_user_id=maker.id)
    p = leaders_service.prepare(db, year=y, month=m, preparer_user_id=maker.id)  # re-prepare supersedes the draft
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.approve(db, period_id=p.id, approver_user_id=maker.id)
    leaders_service.approve(db, period_id=p.id, approver_user_id=checker.id)
    leaders_service.post(db, period_id=p.id)
    leaders_service.post(db, period_id=p.id)  # idempotent
    db.commit()
    assert _balance(db, "5004") == Decimal("10.00") and _balance(db, "2106") == Decimal("-10.00")
    assert db.query(JournalEntry).filter(JournalEntry.posting_type == PostingType.LEADERS_ALLOCATION).count() == 1
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.prepare(db, year=y, month=m, preparer_user_id=maker.id)  # cannot rewrite posted month
    leaders_service.reverse(db, period_id=p.id, reason="Correction after refund")
    db.commit()
    assert _balance(db, "2106") == 0
    rev = db.query(JournalEntry).filter(JournalEntry.posting_type == PostingType.REVERSAL).one()
    assert rev.reverses_entry_id == p.journal_entry_id
    again = leaders_service.prepare(db, year=y, month=m, preparer_user_id=maker.id)
    assert again.status == "DRAFT"
    assert db.query(LeadersPeriod).filter(LeadersPeriod.status == "SUPERSEDED").count() == 1
    _assert_all_journals_balance(db)


def test_leaders_paid_reward_blocks_reversal_and_zero_pool_posts_nothing(world):
    db = world
    maker, checker, earner = _user(db, "m2@t.com"), _user(db, "c2@t.com"), _user(db, "e2@t.com")
    _commission(db, earner, 50)
    _revenue(db, Decimal("200.00"))
    db.commit()
    p = leaders_service.prepare(db, year=LAST_MONTH.year, month=LAST_MONTH.month, preparer_user_id=maker.id)
    leaders_service.approve(db, period_id=p.id, approver_user_id=checker.id)
    leaders_service.post(db, period_id=p.id)
    line = db.query(LeadersAllocationLine).one()
    leaders_service.record_external_payout(db, line_id=line.id, reference="TX-1")
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.record_external_payout(db, line_id=line.id, reference="TX-1")
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.reverse(db, period_id=p.id, reason="too late")
    assert _balance(db, "2106") == 0 and _balance(db, "1001") == Decimal("-10.00")

    empty_month = (LAST_MONTH.replace(day=1) - timedelta(days=1))
    z = leaders_service.prepare(db, year=empty_month.year, month=empty_month.month, preparer_user_id=maker.id)
    leaders_service.approve(db, period_id=z.id, approver_user_id=checker.id)
    leaders_service.post(db, period_id=z.id)
    assert z.status == "POSTED" and z.journal_entry_id is None and z.qualifying_count == 0


# ================================================================ marketplace

class FakeCustodian:
    name = "FAKE_TEST_CUSTODIAN"

    def __init__(self):
        self.calls = []

    def create_hold(self, order):
        self.calls.append(("hold", order.id))
        return {}

    def request_release(self, order):
        self.calls.append(("release", order.id))

    def request_refund(self, order):
        self.calls.append(("refund", order.id))


@pytest.fixture
def custodian(monkeypatch):
    fake = FakeCustodian()
    marketplace_service.register_custodian(fake)
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", fake.name)
    return fake


def _listing(db, seller, price="100.00"):
    p = DigitalProduct(seller_id=seller.id, title="E-book", description="d", category="books", price_dsp=0,
                       price_usd=Decimal(price), file_url="https://x/f", file_type="pdf", is_active=True)
    db.add(p)
    db.flush()
    return p


def test_marketplace_pricing_keeps_seller_base_and_markup_distinct():
    assert marketplace_service.price_for_seller_base("100.00") == (Decimal("100.00"), Decimal("20.00"), Decimal("120.00"))


def test_marketplace_happy_path_held_confirmed_released_settled(world, custodian):
    db = world
    sponsor = _user(db, "msp@t.com")
    buyer = _user(db, "mb@t.com", sponsor=sponsor)
    seller = _user(db, "ms@t.com")
    order = marketplace_service.create_order(db, buyer_user_id=buyer.id, item_type="digital_product",
                                             item_id=_listing(db, seller).id)
    assert (order.seller_base_amount, order.markup_amount, order.buyer_total_amount) == (Decimal("100.00"), Decimal("20.00"), Decimal("120.00"))
    marketplace_service.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="evt-1", custodian_reference="C-1")
    assert marketplace_service.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="evt-1") is False
    assert _balance(db, "1220") == Decimal("120.00") and _balance(db, "2121") == Decimal("-100.00")
    with pytest.raises(marketplace_service.MarketplaceError):
        marketplace_service.confirm_receipt(db, order, buyer_user_id=buyer.id)  # not delivered yet
    marketplace_service.mark_fulfilled(db, order, seller_user_id=seller.id)
    marketplace_service.confirm_receipt(db, order, buyer_user_id=buyer.id)
    assert order.state == marketplace_service.RELEASE_PENDING and ("release", order.id) in custodian.calls
    marketplace_service.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="evt-2")
    marketplace_service.apply_custodian_event(db, order, event_type="MARKUP_SETTLED", external_event_id="evt-3")
    db.commit()
    assert _balance(db, "4007") == Decimal("-20.00")  # MyHigh5 revenue = markup only
    assert _balance(db, "2121") == 0 and _balance(db, "1220") == 0 and _balance(db, "2114") == 0
    assert _balance(db, "1001") == Decimal("20.00")
    c = db.query(AffiliateCommission).one()
    assert (c.user_id, c.base_amount, c.commission_amount) == (sponsor.id, Decimal("20.00"), Decimal("4.00"))
    _assert_all_journals_balance(db)


def test_dispute_blocks_release_and_refund_reverses_custody_without_revenue(world, custodian):
    db = world
    buyer, seller = _user(db, "db@t.com"), _user(db, "dsl@t.com")
    order = marketplace_service.create_order(db, buyer_user_id=buyer.id, item_type="digital_product",
                                             item_id=_listing(db, seller, "50.00").id)
    marketplace_service.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="e-1")
    marketplace_service.mark_fulfilled(db, order, seller_user_id=seller.id)
    marketplace_service.open_dispute(db, order, user_id=buyer.id, reason="Item not as described")
    with pytest.raises(marketplace_service.MarketplaceError):
        marketplace_service.confirm_receipt(db, order, buyer_user_id=buyer.id)
    with pytest.raises(marketplace_service.MarketplaceError):
        marketplace_service.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="e-2")
    marketplace_service.resolve_dispute(db, order, admin_user_id=seller.id, outcome="REFUND", note="Refund approved")
    marketplace_service.apply_custodian_event(db, order, event_type="REFUNDED", external_event_id="e-3")
    db.commit()
    assert order.state == marketplace_service.REFUNDED
    assert _balance(db, "1220") == 0 and _balance(db, "2121") == 0 and _balance(db, "2114") == 0 and _balance(db, "4007") == 0
    assert db.query(AffiliateCommission).count() == 0
    _assert_all_journals_balance(db)


def test_without_a_configured_custodian_no_release_can_be_requested(world, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", "")
    buyer, seller = _user(db, "nb@t.com"), _user(db, "ns@t.com")
    order = marketplace_service.create_order(db, buyer_user_id=buyer.id, item_type="digital_product",
                                             item_id=_listing(db, seller).id)
    order.state = marketplace_service.FULFILLED
    with pytest.raises(marketplace_service.CustodianNotConfigured):
        marketplace_service.confirm_receipt(db, order, buyer_user_id=buyer.id)


# ================================================================ cutover

def test_model_selection_is_the_stored_cutover_and_legacy_deposits_stay_legacy(world):
    db = world
    version = db.query(BusinessModelVersion).one()
    assert model_version_for_new_event(db) == NEW_MODEL_VERSION
    assert model_version_for_new_event(db, at=version.effective_at - timedelta(seconds=1)) == LEGACY_MODEL_VERSION

    sponsor = _user(db, "cs@t.com")
    payer = _user(db, "cp@t.com", sponsor=sponsor)
    legacy = _deposit(db, payer, "annual_membership", version=None, tag="legacy")
    process_payment_validation(db, legacy, defer_commit=True)
    db.commit()
    assert db.query(AffiliateCommission).count() == 0  # retired 10-level engine
    assert _balance(db, "2104") == 0  # no new Founding accrual
    assert db.query(JournalEntry).filter(JournalEntry.business_model_version == NEW_MODEL_VERSION).count() == 0
    new = _deposit(db, payer, "annual_membership", tag="new")
    process_payment_validation(db, new, defer_commit=True)
    db.commit()
    assert db.query(AffiliateCommission).one().business_model_version == NEW_MODEL_VERSION
