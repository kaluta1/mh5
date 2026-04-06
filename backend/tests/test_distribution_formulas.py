"""Unit tests for CoA distribution math (no DB)."""
from decimal import Decimal

from app.accounting.distribution_formulas import (
    annual_membership_split,
    ad_revenue_nominator_split,
    ad_revenue_participant_split,
    cashout_fee_and_net,
    club_markup_split,
    founding_membership_split,
)


def _sum(lines):
    return sum((x.amount for x in lines), Decimal("0"))


def test_annual_10_all_levels():
    lines = annual_membership_split(Decimal("10.00"))
    d = {x.label: x.amount for x in lines}
    assert d["level_1_sponsor"] == Decimal("1.00")
    assert d["level_2_to_10_sponsors"] == Decimal("0.90")
    assert d["founding_members_pool"] == Decimal("1.00")
    assert d["shufti_kyc_payable"] == Decimal("2.00")
    assert d["platform_revenue_net"] == Decimal("5.10")
    assert _sum(lines) == Decimal("10.00")


def test_founding_100():
    lines = founding_membership_split(Decimal("100"))
    d = {x.label: x.amount for x in lines}
    assert d["level_1_sponsor"] == Decimal("10.00")
    assert d["level_2_to_10_sponsors"] == Decimal("9.00")
    assert d["founding_members_pool"] == Decimal("10.00")
    assert d["platform_revenue_net"] == Decimal("71.00")
    assert _sum(lines) == Decimal("100.00")


def test_ad_participant_100():
    lines = ad_revenue_participant_split(Decimal("100"))
    d = {x.label: x.amount for x in lines}
    assert d["participant_share"] == Decimal("40.00")
    assert d["level_1_sponsor"] == Decimal("5.00")
    assert d["level_2_to_10_sponsors"] == Decimal("9.00")
    assert d["founding_members_pool"] == Decimal("10.00")
    assert d["platform_revenue_net"] == Decimal("36.00")
    assert _sum(lines) == Decimal("100.00")


def test_ad_nominator_100():
    lines = ad_revenue_nominator_split(Decimal("100"))
    d = {x.label: x.amount for x in lines}
    assert d["nominator_share"] == Decimal("10.00")
    assert d["level_1_sponsor"] == Decimal("2.50")
    assert d["level_2_to_10_sponsors"] == Decimal("9.00")
    assert d["founding_members_pool"] == Decimal("10.00")
    assert d["platform_revenue_net"] == Decimal("68.50")
    assert _sum(lines) == Decimal("100.00")


def test_club_markup_100_base():
    s = club_markup_split(Decimal("100"))
    assert s.gross_charge == Decimal("120.00")
    assert s.base_to_owner == Decimal("100.00")
    assert s.markup == Decimal("20.00")
    assert s.level1_sponsor == Decimal("2.00")
    assert s.level2_to_10 == Decimal("1.80")
    assert s.founding_pool == Decimal("2.00")
    assert s.platform_net == Decimal("14.20")


def test_cashout_fee():
    assert cashout_fee_and_net(Decimal("100")).fee == Decimal("20.00")
    assert cashout_fee_and_net(Decimal("5000")).fee == Decimal("50.00")
    assert cashout_fee_and_net(Decimal("200000")).fee == Decimal("1000.00")
