"""The affiliate program is DIRECT referrals only (level 1). Management rule, 2026-10-03.

    A -> B -> C -> D   (users.sponsor_id)

A sees and earns from B only. C and D are not A's affiliates. The stored
sponsor relationship and every historical commission row (including level
2-10 rows of the retired program) are left untouched.

Synthetic users, deposits and commissions only (SQLite). No provider is called.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.crud.crud_affiliate import affiliate_tree
from app.crud.crud_user import user as crud_user
from app.models.affiliate import AffiliateCommission, AffiliateTree, CommissionStatus, CommissionType, ReferralLink
from app.models.invitation import Invitation
from app.services.affiliate_hierarchy import ACTIVE_AFFILIATE_LEVELS, MAX_AFFILIATE_LEVELS
from app.services.commission_distribution import process_payment_validation
from app.services.financial_reversal import reverse_provider_refund
from app.services.new_model_reference_data import LEGACY_MODEL_VERSION, NEW_MODEL_VERSION
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    _deposit,
    _register,
    _retired_legacy,
    _user,
    world,
)

pytestmark = pytest.mark.unit
API = "/api/v1/affiliates"


@pytest.fixture
def chain(world):
    """A -> B -> C -> D, plus the old affiliate_tree rows a 10-level program wrote."""
    db = world
    a = _user(db, "a@t.com")
    b = _user(db, "b@t.com", sponsor=a)
    c = _user(db, "c@t.com", sponsor=b)
    d = _user(db, "d@t.com", sponsor=c)
    db.add_all([
        AffiliateTree(user_id=a.id, sponsor_id=None, level=0, path=""),
        AffiliateTree(user_id=b.id, sponsor_id=a.id, level=1, path=f"/{a.id}"),
        AffiliateTree(user_id=c.id, sponsor_id=b.id, level=2, path=f"/{a.id}/{b.id}"),
        AffiliateTree(user_id=d.id, sponsor_id=c.id, level=3, path=f"/{a.id}/{b.id}/{c.id}"),
    ])
    db.commit()
    return db, a, b, c, d


def listed(client, user, **params):
    r = client.get(f"{API}/referrals/all", headers=auth(user), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ids(payload):
    return [row["id"] for row in payload["referrals"]]


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_the_active_program_has_exactly_one_level():
    assert ACTIVE_AFFILIATE_LEVELS == 1
    assert MAX_AFFILIATE_LEVELS == 10          # retired depth: history / admin audit only


# ---------------------------------------------------------------------------
# Affiliate list: direct referrals only
# ---------------------------------------------------------------------------

def test_each_member_sees_only_their_direct_referral(client, chain):
    db, a, b, c, d = chain
    assert ids(listed(client, a)) == [b.id]            # 1. contains B  2. not C  3. not D
    assert ids(listed(client, b)) == [c.id]            # 4. contains C  5. not D
    assert ids(listed(client, c)) == [d.id]            # 6. contains D
    assert ids(listed(client, d)) == []
    payload = listed(client, a)
    assert payload["total"] == payload["total_all_levels"] == 1
    assert list(payload["level_stats"]) == ["1"] and payload["level_stats"]["1"]["count"] == 1
    assert {row["level"] for row in payload["referrals"]} == {1}
    # Nothing about the referral's own downline is exposed.
    assert "referrals_count" not in payload["referrals"][0]


def test_every_direct_referral_endpoint_agrees(client, chain):
    db, a, b, c, d = chain
    assert [u["id"] for u in client.get(f"{API}/referrals", headers=auth(a)).json()] == [b.id]
    assert [u["id"] for u in client.get(f"{API}/referrals/detailed", headers=auth(a)).json()] == [b.id]
    assert client.get(f"{API}/referrals/count", headers=auth(a)).json() == {"count": 1}
    assert crud_user.count_referrals(db, a.id) == 1
    assert ids(crud_user.get_direct_referrals_detailed(db, a.id, limit=100)) == [b.id]


def test_filters_search_and_pagination_never_reach_descendants(client, chain):
    db, a, b, c, d = chain
    extra = [_user(db, f"direct{i}@t.com", sponsor=a) for i in range(3)]
    _user(db, "grandchild@t.com", sponsor=extra[0])
    db.commit()
    direct = {b.id, *(u.id for u in extra)}
    seen = []
    for skip in range(0, 8, 2):
        seen += ids(listed(client, a, skip=skip, limit=2))
    assert set(seen) == direct and len(seen) == 4
    # Searching for a descendant by name, username or email finds nothing.
    for term in ("c@t.com", "d@t.com", "grandchild"):
        assert ids(listed(client, a, search=term)) == []
    assert ids(listed(client, a, search="b@t.com")) == [b.id]
    assert set(ids(listed(client, a, status="active", limit=100))) == direct
    assert set(ids(listed(client, a, level=1, limit=100))) == direct


@pytest.mark.parametrize("level", [2, 3, 10])
def test_asking_for_a_deeper_level_is_rejected(client, chain, level):
    db, a, *_ = chain
    r = client.get(f"{API}/referrals/all", headers=auth(a), params={"level": level})
    assert r.status_code == 422, r.text


def test_genealogy_is_the_member_and_direct_referrals_only(client, chain):
    db, a, b, c, d = chain
    for depth in (2, 5, 10):
        assert client.get(f"{API}/genealogy/{depth}", headers=auth(a)).status_code == 400
    tree = client.get(f"{API}/genealogy/1", headers=auth(a)).json()
    assert tree["user_id"] == a.id
    assert [child["user_id"] for child in tree["referrals"]] == [b.id]
    assert tree["referrals"][0]["referrals"] == [] and tree["total_descendants"] == 1
    # The service itself caps the depth whatever it is asked for.
    deep = affiliate_tree.get_genealogy(db, a.id, levels=10)
    assert [child["user_id"] for child in deep["referrals"]] == [b.id]
    assert deep["referrals"][0]["referrals"] == []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_total_affiliates_is_the_direct_count_and_nothing_leaks_from_descendants(client, chain):
    db, a, b, c, d = chain
    stats = client.get(f"{API}/stats", headers=auth(a)).json()
    assert stats["total_affiliates"] == 1 and stats["direct_referrals"] == 1      # 7.
    assert stats["indirect_referrals"] == 0                                        # 8.
    assert [row["level"] for row in stats["level_stats"]] == [1]
    assert client.get(f"{API}/stats", headers=auth(d)).json()["total_affiliates"] == 0


def test_conversion_rate_is_direct_referrals_over_link_clicks(client, chain):
    db, a, b, c, d = chain
    assert client.get(f"{API}/stats", headers=auth(a)).json()["conversion_rate"] == 0.0     # no click yet
    db.add(ReferralLink(user_id=a.id, referral_code="A-LINK", clicks=4, conversions=0))
    db.commit()
    stats = client.get(f"{API}/stats", headers=auth(a)).json()
    # 1 direct referral / 4 clicks. With descendants it would have been 3 / 4.
    assert (stats["conversions"], stats["clicks"], stats["conversion_rate"]) == (1, 4, 25.0)


def test_total_commissions_keeps_ledger_truth_and_separates_historical_levels(client, chain):
    db, a, b, c, d = chain
    when = datetime.utcnow() - timedelta(days=200)

    def row(level, amount, version, source, day, status=CommissionStatus.PAID):
        db.add(AffiliateCommission(user_id=a.id, source_user_id=source.id, commission_type=CommissionType.KYC_PAYMENT,
                                   level=level, commission_amount=Decimal(amount), base_amount=Decimal("10.00"),
                                   status=status, transaction_date=when + timedelta(days=day),
                                   business_model_version=version))

    row(1, "2.00", NEW_MODEL_VERSION, b, 0)
    row(2, "0.10", LEGACY_MODEL_VERSION, c, 1)     # historical rows of the retired 10-level program
    row(5, "0.10", LEGACY_MODEL_VERSION, d, 2)
    row(1, "9.00", NEW_MODEL_VERSION, b, 3, CommissionStatus.PENDING)
    db.commit()
    before = sorted((r.id, r.level, r.commission_amount, r.status, r.user_id) for r in db.query(AffiliateCommission).all())

    stats = client.get(f"{API}/stats", headers=auth(a)).json()
    assert stats["total_commissions"] == pytest.approx(2.20)              # lifetime earned, nothing erased
    assert stats["direct_commissions"] == pytest.approx(2.00)
    assert stats["historical_indirect_commissions"] == pytest.approx(0.20)
    assert stats["pending_commissions"] == pytest.approx(9.00)
    assert sorted((r.id, r.level, r.commission_amount, r.status, r.user_id)
                  for r in db.query(AffiliateCommission).all()) == before
    # Historical rows stay visible, with their real level, in the commission history.
    history = client.get(f"{API}/commissions", headers=auth(a), params={"limit": 50}).json()
    rows = history["commissions"] if isinstance(history, dict) else history
    assert sorted(r["level"] for r in rows) == [1, 1, 2, 5]


# ---------------------------------------------------------------------------
# Pending / links / invite
# ---------------------------------------------------------------------------

def test_pending_tab_shows_only_the_members_own_invitations(client, chain):
    db, a, b, c, d = chain
    for inviter, email in ((a, "a-invitee@t.com"), (b, "b-invitee@t.com"), (c, "c-invitee@t.com")):
        db.add(Invitation(inviter_id=inviter.id, email=email, referral_code=inviter.personal_referral_code,
                          status="pending", expires_at=datetime.utcnow() + timedelta(days=7)))
    db.commit()
    pending = client.get(f"{API}/invitations/pending", headers=auth(a)).json()
    assert [row["email"] for row in pending] == ["a-invitee@t.com"]                # 9.
    assert client.get(f"{API}/invitations/stats", headers=auth(a)).json()["pending"] == 1
    assert [row["email"] for row in client.get(f"{API}/invitations", headers=auth(a)).json()] == ["a-invitee@t.com"]


def test_referral_link_assigns_the_inviter_as_direct_sponsor_only(world):
    db = world
    a = _user(db, "linka@t.com")
    db.commit()
    b = _register(db, "linkb@t.com", a.personal_referral_code)
    c = _register(db, "linkc@t.com", b.personal_referral_code)
    assert (b.sponsor_id, c.sponsor_id) == (a.id, b.id)
    assert ids(crud_user.get_direct_referrals_detailed(db, a.id)) == [b.id]
    assert ids(crud_user.get_direct_referrals_detailed(db, b.id)) == [c.id]


# ---------------------------------------------------------------------------
# Commission generation: direct sponsor only
# ---------------------------------------------------------------------------

def test_purchase_by_c_pays_b_only_and_retries_never_duplicate(chain):
    db, a, b, c, d = chain
    deposit = _deposit(db, c, "annual_membership")
    for _ in range(4):                                   # first settlement + webhook / scheduler / admin retries
        assert process_payment_validation(db, deposit, defer_commit=True) is True
        db.commit()
    rows = db.query(AffiliateCommission).all()
    assert [(r.user_id, r.source_user_id, r.level, r.commission_amount) for r in rows] == [
        (b.id, c.id, 1, Decimal("10.00"))]               # the approved direct commission, once
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id == a.id).count() == 0     # A: $0
    assert db.query(AffiliateCommission).filter(AffiliateCommission.level > 1).count() == 0


def test_each_buyer_pays_exactly_their_own_direct_sponsor(chain):
    db, a, b, c, d = chain
    for buyer in (b, c, d):
        process_payment_validation(db, _deposit(db, buyer, "annual_membership"), defer_commit=True)
    db.commit()
    paid = sorted((r.user_id, r.source_user_id, r.level) for r in db.query(AffiliateCommission).all())
    assert paid == sorted([(a.id, b.id, 1), (b.id, c.id, 1), (c.id, d.id, 1)])


def test_buyer_without_a_sponsor_creates_no_commission(chain):
    db, a, *_ = chain
    process_payment_validation(db, _deposit(db, a, "annual_membership"), defer_commit=True)
    db.commit()
    assert db.query(AffiliateCommission).count() == 0


def test_kyc_purchase_recognised_later_is_direct_only_too(chain):
    from app.services.new_model_payments import recognize_deferred_deposit

    db, a, b, c, d = chain
    deposit = _deposit(db, c, "kyc")
    process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    for _ in range(2):
        recognize_deferred_deposit(db, deposit)
        db.commit()
    rows = db.query(AffiliateCommission).all()
    assert [(r.user_id, r.level) for r in rows] == [(b.id, 1)]


def test_re_enabled_legacy_engine_still_pays_the_direct_sponsor_only(chain, monkeypatch):
    """The emergency lever for the retired engine cannot bring levels 2-10 back."""
    from app.models.affiliate import CommissionRule
    from app.services.commission_distribution import distribute_commissions

    db, a, b, c, d = chain
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", True)
    db.add(CommissionRule(product_code="annual_membership", commission_type=CommissionType.ANNUAL_MEMBERSHIP_FEE,
                          direct_percentage=10.0, indirect_percentage=1.0, max_levels=10, is_active=True))
    db.commit()
    deposit = _deposit(db, d, "annual_membership", version=LEGACY_MODEL_VERSION)
    for _ in range(3):
        distribute_commissions(db, deposit, "annual_membership", commit=True)
    rows = db.query(AffiliateCommission).all()
    assert [(r.user_id, r.level) for r in rows] == [(c.id, 1)]
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id.in_([a.id, b.id])).count() == 0


def test_refund_cancels_the_direct_commission_and_touches_no_other(chain):
    db, a, b, c, d = chain
    dep_c = _deposit(db, c, "annual_membership", deposit_id=7)
    dep_d = _deposit(db, d, "annual_membership", deposit_id=71)
    for deposit in (dep_c, dep_d):
        process_payment_validation(db, deposit, defer_commit=True)
    db.commit()
    assert reverse_provider_refund(db, dep_c, {"refund_amount": "50.00"}) is True
    by_beneficiary = {r.user_id: r.status for r in db.query(AffiliateCommission).all()}
    assert by_beneficiary[b.id] == CommissionStatus.CANCELLED
    assert by_beneficiary[c.id] != CommissionStatus.CANCELLED
    assert a.id not in by_beneficiary


def test_deep_historical_tree_and_old_commission_rows_are_not_modified(chain):
    db, a, b, c, d = chain
    old = AffiliateCommission(user_id=a.id, source_user_id=d.id, commission_type=CommissionType.KYC_PAYMENT, level=3,
                              commission_amount=Decimal("0.10"), base_amount=Decimal("10.00"),
                              status=CommissionStatus.PAID, transaction_date=datetime(2026, 4, 1),
                              business_model_version=LEGACY_MODEL_VERSION)
    db.add(old)
    db.commit()
    snapshot = (old.id, old.user_id, old.level, old.commission_amount, old.status)
    sponsors = [(u.id, u.sponsor_id) for u in (a, b, c, d)]
    trees = sorted((t.user_id, t.sponsor_id, t.level, t.path) for t in db.query(AffiliateTree).all())

    process_payment_validation(db, _deposit(db, d, "annual_membership"), defer_commit=True)
    db.commit()
    affiliate_tree.get_user_stats(db, a.id)
    crud_user.get_direct_referrals_detailed(db, a.id)

    db.refresh(old)
    assert (old.id, old.user_id, old.level, old.commission_amount, old.status) == snapshot
    assert [(u.id, u.sponsor_id) for u in (a, b, c, d)] == sponsors          # the referral tree is not flattened
    assert sorted((t.user_id, t.sponsor_id, t.level, t.path) for t in db.query(AffiliateTree).all()) == trees
    # The stored tree is still readable for audit, by the admin-only function.
    audit = crud_user.get_sponsor_tree_for_admin(db, a.id, limit=100)
    assert {row["id"]: row["level"] for row in audit["referrals"]} == {b.id: 1, c.id: 2, d.id: 3}


# ---------------------------------------------------------------------------
# Ownership / security
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["referrals/all", "referrals", "referrals/detailed", "referrals/count", "stats",
                                  "commissions", "invitations/pending", "genealogy/1"])
def test_affiliate_data_requires_authentication(client, chain, path):
    assert client.get(f"{API}/{path}").status_code in (401, 403)


def test_identity_comes_from_the_token_not_from_request_parameters(client, chain):
    db, a, b, c, d = chain
    for params in ({"user_id": b.id}, {"sponsor_id": b.id}, {"affiliate_id": c.id}, {"user_id": c.id, "level": 1}):
        assert ids(listed(client, a, **params)) == [b.id]            # never B's or C's referrals
        stats = client.get(f"{API}/stats", headers=auth(a), params=params).json()
        assert stats["total_affiliates"] == 1
        detailed = client.get(f"{API}/referrals/detailed", headers=auth(a), params=params).json()
        assert [u["id"] for u in detailed] == [b.id]
    # D, who referred nobody, cannot see anything of the tree above or around them.
    assert ids(listed(client, d, user_id=a.id)) == []


def test_admin_user_detail_tree_is_not_reachable_by_a_member(client, chain):
    db, a, *_ = chain
    r = client.get(f"/api/v1/admin/users/{a.id}", headers=auth(a))
    assert r.status_code in (401, 403, 404)
