"""Permanent 40% direct-affiliate rate (client rule confirmed 2026-09-28).

10,000 DIRECT referrals, KYC-verified within six calendar months of the sponsor's
registration -> permanent 40% for the categories that use the dynamic rate (ad slots).
All KYC state is local fixture data; no provider is contacted.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import insert

from app.models.business_model import AffiliateRateQualification, ReferralPoolAssignment
from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import affiliate_rate_policy as rates
from tests.unit.test_new_business_model import _retired_legacy, _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit

JOINED = datetime(2026, 1, 31, 10, 0, 0)          # month-end registration: exercises calendar clamping
DEADLINE = datetime(2026, 7, 31, 10, 0, 0)         # + 6 calendar months, same time of day


def _sponsor(db, email="sponsor@t.com", joined=JOINED) -> User:
    u = _user(db, email)
    u.created_at = joined
    db.flush()
    return u


def _referral(db, sponsor, tag, *, kyc_at=DEADLINE - timedelta(days=1), status=KYCStatus.APPROVED,
              source="PERSONAL_REFERRAL", attached_at=None, pool=False) -> User:
    r = _user(db, f"{tag}@r.com", sponsor=sponsor)
    r.created_at = JOINED + timedelta(days=1)
    r.sponsor_source = source
    r.sponsor_assigned_at = attached_at or JOINED + timedelta(days=1)
    if kyc_at is not None:
        db.add(KYCVerification(user_id=r.id, status=status, processed_at=kyc_at, submitted_at=kyc_at))
    if pool:
        db.add(ReferralPoolAssignment(referred_user_id=r.id, pool_member_user_id=sponsor.id, membership_id=1,
                                      method="FAIR_RANDOM_V1", candidate_count=1, min_assignment_count=0,
                                      assigned_at=r.sponsor_assigned_at))
    db.flush()
    return r


def _bulk_referrals(db, sponsor, n, *, kyc_at=DEADLINE - timedelta(days=1)):
    """n KYC-approved direct referrals, inserted in bulk (real threshold tests)."""
    base = JOINED + timedelta(days=1)
    db.execute(insert(User), [
        dict(email=f"bulk{i}@r.com", username=f"bulk{i}", hashed_password="x", personal_referral_code=f"BULK{i}",
             is_active=True, is_verified=False, is_admin=False, is_deleted=False, email_verified=False,
             preferred_language="en", affiliate_agreement_accepted=False, sponsor_id=sponsor.id,
             sponsor_source="PERSONAL_REFERRAL", sponsor_assigned_at=base, created_at=base, updated_at=base)
        for i in range(n)
    ])
    ids = [uid for (uid,) in db.query(User.id).filter(User.email.like("bulk%@r.com")).all()]
    db.execute(insert(KYCVerification), [
        dict(user_id=uid, status=KYCStatus.APPROVED, processed_at=kyc_at, submitted_at=kyc_at, attempts_count=0,
             max_attempts=3, identity_verified=True, address_verified=True, document_verified=True,
             face_verified=True, created_at=kyc_at, updated_at=kyc_at)
        for uid in ids
    ])
    db.flush()


@pytest.fixture
def small_threshold(monkeypatch):
    monkeypatch.setattr(rates, "QUALIFICATION_DIRECT_REFERRALS", 3)


# ---------------------------------------------------------------- central rules

def test_rules_are_central_and_only_ad_slots_use_the_dynamic_rate():
    assert (rates.STANDARD_DIRECT_RATE, rates.QUALIFIED_DIRECT_RATE) == (Decimal("0.20"), Decimal("0.40"))
    assert (rates.QUALIFICATION_DIRECT_REFERRALS, rates.QUALIFICATION_WINDOW_MONTHS) == (10000, 6)
    assert rates.DYNAMIC_RATE_REVENUE_CATEGORIES == {"AD_SLOT_PURCHASE"}


def test_six_calendar_months_follow_the_app_month_convention():
    assert rates.add_calendar_months(JOINED, 6) == DEADLINE
    assert rates.add_calendar_months(datetime(2026, 8, 31, 23, 59), 6) == datetime(2027, 2, 28, 23, 59)  # clamped
    assert rates.add_calendar_months(datetime(2027, 8, 31, 8, 0), 6) == datetime(2028, 2, 29, 8, 0)      # leap year


# ---------------------------------------------------------------- A / B: the real threshold

def test_A_9999_qualifying_direct_referrals_stay_at_20(world):
    db = world
    s = _sponsor(db)
    _bulk_referrals(db, s, 9999)
    st = rates.evaluate(db, s)
    assert (st.rate, st.permanently_qualified, st.qualifying_referral_count) == (Decimal("0.20"), False, 9999)
    assert db.query(AffiliateRateQualification).count() == 0


def test_B_10000_within_six_months_is_permanent_40(world):
    db = world
    s = _sponsor(db)
    _bulk_referrals(db, s, 10000)
    st = rates.evaluate(db, s)
    assert (st.rate, st.permanently_qualified, st.qualifying_referral_count) == (Decimal("0.40"), True, 10000)
    assert st.window_deadline == DEADLINE and st.qualified_at == DEADLINE - timedelta(days=1)
    row = db.query(AffiliateRateQualification).one()
    assert (row.user_id, row.qualified_rate, row.rule_version) == (s.id, Decimal("0.4000"), rates.RULE_VERSION)


# ---------------------------------------------------------------- C .. K (threshold lowered to 3 for readability)

def test_C_one_referral_not_kyc_verified_by_deadline_means_no_qualification(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "c1")
    _referral(db, s, "c2")
    _referral(db, s, "c3", status=KYCStatus.PENDING_PROOF_OF_ADDRESS)  # identity step only: not verified
    assert rates.evaluate(db, s).permanently_qualified is False


def test_D_indirect_referral_does_not_count(world, small_threshold):
    db = world
    s = _sponsor(db)
    a = _referral(db, s, "d1")
    _referral(db, s, "d2")
    _referral(db, a, "d3")  # referral of a referral
    assert rates.evaluate(db, s).qualifying_referral_count == 2


def test_E_referral_pool_and_historical_random_assignments_do_not_count(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "e1")
    _referral(db, s, "e2")
    _referral(db, s, "e3", source="REFERRAL_POOL")
    _referral(db, s, "e4", source=None, pool=True)  # legacy row, but it has a pool assignment record
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (2, False)


def test_F_self_referral_does_not_count(world, small_threshold):
    db = world
    s = _sponsor(db)
    s.sponsor_id = s.id
    s.sponsor_source = "PERSONAL_REFERRAL"
    db.add(KYCVerification(user_id=s.id, status=KYCStatus.APPROVED, processed_at=JOINED + timedelta(days=2)))
    _referral(db, s, "f1")
    _referral(db, s, "f2")
    assert rates.evaluate(db, s).qualifying_referral_count == 2


def test_G_kyc_payment_without_completed_kyc_does_not_count(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "g1")
    _referral(db, s, "g2")
    payer = _referral(db, s, "g3", kyc_at=None)
    product = db.query(ProductType).filter(ProductType.code == "kyc").one()
    db.add(Deposit(user_id=payer.id, product_type_id=product.id, amount=10, currency="USD",
                   status=DepositStatus.VALIDATED, order_id="kyc-paid-only"))
    payer.identity_verified = True  # even a partial identity flag is not completed KYC
    db.flush()
    assert rates.evaluate(db, s).permanently_qualified is False


def test_H_deadline_is_inclusive_to_the_second(world, small_threshold):
    db = world
    on_time = _sponsor(db, "h-on@t.com")
    for i in range(3):
        _referral(db, on_time, f"h-on{i}", kyc_at=DEADLINE)
    late = _sponsor(db, "h-late@t.com")
    for i in range(2):
        _referral(db, late, f"h-late{i}", kyc_at=DEADLINE)
    _referral(db, late, "h-late2", kyc_at=DEADLINE + timedelta(seconds=1))
    assert rates.evaluate(db, on_time).permanently_qualified is True
    assert rates.evaluate(db, on_time).qualified_at == DEADLINE
    assert rates.evaluate(db, late).permanently_qualified is False


def test_I_kyc_after_deadline_or_link_after_deadline_does_not_count(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "i1")
    _referral(db, s, "i2")
    _referral(db, s, "i3", kyc_at=DEADLINE + timedelta(days=1))
    _referral(db, s, "i4", source="JOIN_CODE", attached_at=DEADLINE + timedelta(hours=1))  # joined via code too late
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (2, False)


def test_J_permanent_rate_survives_later_changes_to_the_referrals(world, small_threshold):
    db = world
    s = _sponsor(db)
    refs = [_referral(db, s, f"j{i}") for i in range(3)]
    assert rates.evaluate(db, s).rate == Decimal("0.40")
    db.commit()
    # Afterwards: a KYC is revoked, a referral is closed, another loses its sponsor.
    db.query(KYCVerification).filter(KYCVerification.user_id == refs[0].id).one().status = KYCStatus.REJECTED
    refs[1].is_deleted = True
    refs[2].sponsor_id = None
    db.commit()
    st = rates.evaluate(db, s)
    assert (st.rate, st.permanently_qualified) == (Decimal("0.40"), True)
    assert db.query(AffiliateRateQualification).count() == 1


def test_K_normal_sponsor_stays_20_until_qualification_and_other_categories_are_untouched(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "k1")
    _referral(db, s, "k2")
    assert rates.direct_rate_for_category(db, s, rates.AD_SLOT_PURCHASE) == Decimal("0.20")
    _referral(db, s, "k3")
    assert rates.direct_rate_for_category(db, s, rates.AD_SLOT_PURCHASE) == Decimal("0.40")
    for category in ("KYC_VERIFICATION", "MEMBERSHIP", "PLATFORM_SUBSCRIPTION", "MARKETPLACE_MARKUP", "SERVICE_FEE"):
        assert rates.direct_rate_for_category(db, s, category) is None  # revenue policy rate applies, unchanged


# ---------------------------------------------------------------- recording and hooks

def test_evaluation_without_record_writes_nothing_and_recording_is_idempotent(world, small_threshold):
    db = world
    s = _sponsor(db)
    for i in range(3):
        _referral(db, s, f"r{i}")
    assert rates.evaluate(db, s, record=False).permanently_qualified is True
    assert db.query(AffiliateRateQualification).count() == 0
    rates.evaluate(db, s)
    rates.evaluate(db, s)
    assert db.query(AffiliateRateQualification).count() == 1


def test_kyc_approval_records_the_sponsor_qualification_at_that_moment(world, small_threshold):
    from app.crud.crud_kyc import kyc_verification as crud_kyc_verification

    db = world
    s = _sponsor(db, joined=datetime.utcnow() - timedelta(days=10))
    for i in range(2):
        _referral(db, s, f"hook{i}", kyc_at=datetime.utcnow() - timedelta(days=1))
    last = _referral(db, s, "hook-last", kyc_at=None)
    last.sponsor_assigned_at = datetime.utcnow() - timedelta(days=5)
    pending = KYCVerification(user_id=last.id, status=KYCStatus.REQUIRES_REVIEW)
    db.add(pending)
    db.commit()
    crud_kyc_verification.approve_verification(db, verification_id=pending.id, admin_user_id=None)
    row = db.query(AffiliateRateQualification).one()
    assert row.user_id == s.id and row.qualifying_referral_count == 3


def test_a_failing_qualification_check_never_blocks_kyc_approval(world, monkeypatch):
    from app.crud.crud_kyc import kyc_verification as crud_kyc_verification

    db = world
    s = _sponsor(db)
    r = _referral(db, s, "boom", kyc_at=None)
    v = KYCVerification(user_id=r.id, status=KYCStatus.REQUIRES_REVIEW)
    db.add(v)
    db.commit()

    def boom(*_a, **_k):
        raise RuntimeError("simulated")

    monkeypatch.setattr(rates, "evaluate", boom)
    crud_kyc_verification.approve_verification(db, verification_id=v.id, admin_user_id=None)
    db.refresh(v)
    assert v.status == KYCStatus.APPROVED


def test_qualification_changes_no_age_guardian_or_financial_state(world, small_threshold):
    db = world
    s = _sponsor(db)
    s.date_of_birth = None  # UNKNOWN age
    for i in range(3):
        _referral(db, s, f"safe{i}")
    before = (s.date_of_birth, s.identity_verified, s.is_verified)
    assert rates.evaluate(db, s).permanently_qualified is True
    db.refresh(s)
    assert (s.date_of_birth, s.identity_verified, s.is_verified) == before
    from app.services import financial_eligibility as fe

    assert not fe.evaluate(db, s, fe.FinancialOperation.WITHDRAWAL).allowed  # payout gate unchanged


# ---------------------------------------------------------------- sponsor provenance (fail closed)

def test_personal_referral_and_join_code_are_the_only_counting_sources(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "pv-personal", source="PERSONAL_REFERRAL")
    _referral(db, s, "pv-join", source="JOIN_CODE")
    _referral(db, s, "pv-pool", source="REFERRAL_POOL")
    _referral(db, s, "pv-none", source="NONE")
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (2, False)


def test_null_or_empty_legacy_source_never_counts(world, small_threshold):
    """NULL/empty provenance is ambiguous (e.g. the 2026-04 admin fallback sponsor), so it fails closed."""
    db = world
    s = _sponsor(db)
    for i in range(3):
        _referral(db, s, f"pv-null{i}", source=None)
    _referral(db, s, "pv-empty", source="")
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (0, False)
    assert db.query(AffiliateRateQualification).count() == 0


def test_real_threshold_of_null_source_referrals_does_not_qualify(world):
    db = world
    s = _sponsor(db)
    _bulk_referrals(db, s, 10000)
    db.query(User).filter(User.sponsor_id == s.id).update({User.sponsor_source: None}, synchronize_session=False)
    db.flush()
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (0, False)


def test_pool_assignment_record_excludes_even_a_relabelled_personal_source(world, small_threshold):
    db = world
    s = _sponsor(db)
    _referral(db, s, "pv-ok1")
    _referral(db, s, "pv-ok2")
    _referral(db, s, "pv-relabelled", source="PERSONAL_REFERRAL", pool=True)  # historical pool row, source edited
    st = rates.evaluate(db, s)
    assert (st.qualifying_referral_count, st.permanently_qualified) == (2, False)
