"""Advertising revenue rules (client, confirmed 2026-09-28): central calculator only.

No authoritative advertising revenue event exists yet, so these test the policy calculator;
nothing here posts a journal, commission or payout.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.business_model import AffiliateRateQualification
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel
from app.services import ad_revenue_policy as ads
from app.services import affiliate_rate_policy as rates
from tests.unit.test_new_business_model import _retired_legacy, _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit


def _qualify(db, sponsor):
    now = datetime.utcnow()
    db.add(AffiliateRateQualification(
        user_id=sponsor.id, rule_version=rates.RULE_VERSION, qualified_rate=rates.QUALIFIED_DIRECT_RATE,
        qualified_at=now, window_start=now - timedelta(days=30), window_deadline=now + timedelta(days=150),
        qualifying_referral_count=10000, required_referral_count=10000))
    db.flush()


def _entry(db, owner, kind, *, nominee=None, entry_type=None):
    c = Contestant(user_id=owner.id, entry_type=entry_type or ("nomination" if kind == "NOMINATION" else "participation"),
                   title="t", is_active=True)
    db.add(c)
    db.flush()
    db.add(ContestEntrySafety(
        contestant_id=c.id, entry_kind=kind, submitted_by_user_id=owner.id, account_holder_user_id=owner.id,
        nominee_user_id=nominee.id if nominee else None,
        creative_owner_type="SELF" if kind == "PERSONAL_SUBMISSION" else ("NOMINEE" if nominee else "UNKNOWN"),
        creative_owner_user_id=owner.id if kind == "PERSONAL_SUBMISSION" else (nominee.id if nominee else None),
        exposure_status="PUBLIC", rights_status="NOT_REQUIRED", safety_status="CLEAR", metadata_status="NOT_REQUIRED",
        outcome="ALLOWED", last_evaluated_at=datetime.utcnow()))
    db.flush()
    return c


def _advance(db, contestant, level):
    season = ContestSeason(title=f"{level.value}", level=level)
    db.add(season)
    db.flush()
    db.add(ContestantSeason(contestant_id=contestant.id, season_id=season.id, is_active=True))
    db.flush()


# ---------------------------------------------------------------- Type 1: purchased ad slots

def test_L_ad_slot_normal_sponsor_earns_20_of_the_full_amount(world):
    db = world
    sponsor = _user(db, "l-s@t.com")
    buyer = _user(db, "l-b@t.com", sponsor=sponsor)
    split = ads.ad_slot_split(db, buyer_user_id=buyer.id, gross_amount="100.00")
    assert (split.sponsor_user_id, split.sponsor_rate, split.sponsor_commission) == (sponsor.id, Decimal("0.20"), Decimal("20.00"))


def test_M_ad_slot_permanently_qualified_sponsor_earns_40_instead_of_20(world):
    db = world
    sponsor = _user(db, "m-s@t.com")
    buyer = _user(db, "m-b@t.com", sponsor=sponsor)
    _qualify(db, sponsor)
    split = ads.ad_slot_split(db, buyer_user_id=buyer.id, gross_amount="100.00")
    assert (split.sponsor_rate, split.sponsor_commission) == (Decimal("0.40"), Decimal("40.00"))  # not 60


def test_ad_slot_without_valid_sponsor_pays_no_one(world):
    db = world
    organic = _user(db, "org@t.com")
    inactive = _user(db, "ina@t.com", active=False)
    orphan = _user(db, "orph@t.com", sponsor=inactive)
    for buyer in (organic, orphan):
        split = ads.ad_slot_split(db, buyer_user_id=buyer.id, gross_amount="100.00")
        assert (split.sponsor_user_id, split.sponsor_commission) == (None, Decimal("0.00"))


# ---------------------------------------------------------------- Type 2: contest-page ads

def test_N_personal_page_owner_20_plus_direct_sponsor_1(world):
    db = world
    sponsor = _user(db, "n-s@t.com")
    owner = _user(db, "n-o@t.com", sponsor=sponsor)
    split = ads.contest_page_split(db, contestant=_entry(db, owner, "PERSONAL_SUBMISSION"), revenue_amount="100.00")
    assert split.page_class == ads.ContestPageClass.PERSONAL
    assert (split.owner_user_id, split.owner_share, split.sponsor_user_id, split.sponsor_share) == (
        owner.id, Decimal("20.00"), sponsor.id, Decimal("1.00"))
    assert split.total_distributed == Decimal("21.00")


def test_O_nominated_page_owner_10_plus_direct_sponsor_1_and_nominator_is_not_the_owner(world):
    db = world
    nominator = _user(db, "o-nom@t.com")
    sponsor = _user(db, "o-s@t.com")
    nominee = _user(db, "o-nee@t.com", sponsor=sponsor)
    split = ads.contest_page_split(db, contestant=_entry(db, nominator, "NOMINATION", nominee=nominee), revenue_amount="100.00")
    assert split.page_class == ads.ContestPageClass.NOMINATION
    assert (split.owner_user_id, split.owner_share, split.sponsor_user_id, split.sponsor_share) == (
        nominee.id, Decimal("10.00"), sponsor.id, Decimal("1.00"))
    assert split.total_distributed == Decimal("11.00")


def test_unconfirmed_nominee_gets_no_share_and_nominator_gets_nothing(world):
    db = world
    nominator = _user(db, "u-nom@t.com", sponsor=_user(db, "u-s@t.com"))
    split = ads.contest_page_split(db, contestant=_entry(db, nominator, "NOMINATION"), revenue_amount="100.00")
    assert split.applicable and (split.owner_user_id, split.owner_share, split.sponsor_share) == (None, Decimal("0.00"), Decimal("0.00"))


def test_P_no_valid_direct_sponsor_means_no_fabricated_1_percent(world):
    db = world
    owner = _user(db, "p-o@t.com")  # organic: no sponsor
    split = ads.contest_page_split(db, contestant=_entry(db, owner, "PERSONAL_SUBMISSION"), revenue_amount="100.00")
    assert (split.owner_share, split.sponsor_user_id, split.sponsor_share) == (Decimal("20.00"), None, Decimal("0.00"))


def test_Q_personal_creative_keeps_20_plus_1_through_every_level(world):
    db = world
    owner = _user(db, "q-o@t.com", sponsor=_user(db, "q-s@t.com"))
    c = _entry(db, owner, "PERSONAL_SUBMISSION")
    for level in (SeasonLevel.CITY, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL):
        _advance(db, c, level)
        split = ads.contest_page_split(db, contestant=c, revenue_amount="100.00")
        assert (split.owner_share, split.sponsor_share) == (Decimal("20.00"), Decimal("1.00")), level


def test_R_nominated_creative_keeps_10_plus_1_through_every_level(world):
    db = world
    nominee = _user(db, "r-nee@t.com", sponsor=_user(db, "r-s@t.com"))
    c = _entry(db, _user(db, "r-nom@t.com"), "NOMINATION", nominee=nominee)
    for level in (SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL):
        _advance(db, c, level)
        split = ads.contest_page_split(db, contestant=c, revenue_amount="100.00")
        assert (split.owner_share, split.sponsor_share) == (Decimal("10.00"), Decimal("1.00")), level


def test_classification_uses_provenance_record_over_mutable_fields(world):
    db = world
    owner = _user(db, "prov@t.com")
    c = _entry(db, owner, "PERSONAL_SUBMISSION", entry_type="nomination")  # conflicting legacy field
    assert ads.classify_entry(db, c) == ads.ContestPageClass.PERSONAL
    legacy = Contestant(user_id=owner.id, entry_type="nomination", title="legacy", is_active=True)
    db.add(legacy)
    db.flush()
    assert ads.classify_entry(db, legacy) == ads.ContestPageClass.NOMINATION  # no safety record: entry_type


def test_S_annual_ads_get_no_contest_page_distribution_but_keep_the_ad_slot_commission(world):
    db = world
    sponsor = _user(db, "s-s@t.com")
    owner = _user(db, "s-o@t.com", sponsor=sponsor)
    c = _entry(db, owner, "PERSONAL_SUBMISSION")
    split = ads.contest_page_split(db, contestant=c, revenue_amount="100.00", is_annual_ad=True)
    assert (split.applicable, split.owner_share, split.sponsor_share, split.total_distributed) == (
        False, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
    slot = ads.ad_slot_split(db, buyer_user_id=owner.id, gross_amount="100.00")  # Annual Ad purchase: type 1 only
    assert slot.sponsor_commission == Decimal("20.00")


def test_T_calculation_is_deterministic_and_writes_nothing(world):
    db = world
    sponsor = _user(db, "t-s@t.com")
    owner = _user(db, "t-o@t.com", sponsor=sponsor)
    c = _entry(db, owner, "PERSONAL_SUBMISSION")
    db.commit()
    first = ads.contest_page_split(db, contestant=c, revenue_amount="100.00")
    again = ads.contest_page_split(db, contestant=c, revenue_amount="100.00")
    slot1 = ads.ad_slot_split(db, buyer_user_id=owner.id, gross_amount="100.00")
    slot2 = ads.ad_slot_split(db, buyer_user_id=owner.id, gross_amount="100.00")
    assert first == again and slot1 == slot2
    assert db.query(JournalEntry).count() == 0 and db.query(AffiliateCommission).count() == 0
    assert db.query(AffiliateRateQualification).count() == 0


def test_rounding_is_cent_exact():
    assert ads.PERSONAL_OWNER_RATE + ads.CONTEST_PAGE_SPONSOR_RATE == Decimal("0.21")
    assert ads.NOMINATION_OWNER_RATE + ads.CONTEST_PAGE_SPONSOR_RATE == Decimal("0.11")
