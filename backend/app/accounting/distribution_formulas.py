"""
Pure distribution math for MyHigh5 payment flows (Singapore-oriented CoA).

**Founding Members 10% pool (ledger 2104)** accrues on gross for every flow we model here (KYC fee, annual/founding membership gross, ad shares, and 10% of club *markup*), before month-end
allocation (2104 → 2105). Payment journals implement the same policy in `payment_accounting`.

Percentages apply to gross (membership / ad revenue) unless noted.
Missing affiliate levels are treated as platform revenue (no separate line here).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List

Q2 = Decimal("0.01")


def _d(x: Decimal) -> Decimal:
    return x.quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DistributionLine:
    """One economic slice of a gross amount."""

    label: str
    amount: Decimal


@dataclass(frozen=True)
class ClubMarkupSplit:
    """20% markup on club subscription: split of markup only (base is pass-through)."""

    gross_charge: Decimal
    base_to_owner: Decimal
    markup: Decimal
    level1_sponsor: Decimal  # 10% of markup
    level2_to_10: Decimal  # 9 × 1% of markup
    founding_pool: Decimal  # 10% of markup
    platform_net: Decimal  # remainder of markup


@dataclass(frozen=True)
class CashoutFeeResult:
    requested: Decimal
    fee: Decimal  # 1% of request, min 20, max 1000
    net_to_member: Decimal


@dataclass(frozen=True)
class KycVerificationRecognitionSplit:
    """When verification service is performed: release deferred fee (ex. $10 gross)."""

    gross: Decimal
    founding_pool_accrual: Decimal  # 10% of gross →2104 (monthly pool)
    shufti_payable: Decimal  # provider fee (e.g. 20% of gross) → 2003
    sponsor_commissions_total: Decimal  # sum of L1–L10 accruals (separate JE:5001 / 2001–2002)
    net_verification_revenue: Decimal  # remainder → 4001


def kyc_verification_recognition_split(
    gross: Decimal,
    sponsor_commissions_total: Decimal,
    *,
    founding_rate: Decimal = Decimal("0.10"),
    shufti_rate: Decimal = Decimal("0.20"),
) -> KycVerificationRecognitionSplit:
    """
    Net verification revenue = gross − founding accrual − Shufti − sponsor commissions.
    Sponsor lines are posted in a separate journal (commission expense / payables).
    """
    g = _d(gross)
    founding = _d(g * founding_rate)
    shufti = _d(g * shufti_rate)
    s = _d(max(Decimal("0"), sponsor_commissions_total))
    net = _d(g - founding - shufti - s)
    if net < 0:
        net = Decimal("0.00")
    return KycVerificationRecognitionSplit(
        gross=g,
        founding_pool_accrual=founding,
        shufti_payable=shufti,
        sponsor_commissions_total=s,
        net_verification_revenue=net,
    )


def annual_membership_split(
    gross: Decimal,
    *,
    shufti_fixed: Decimal = Decimal("2.00"),
    levels_2_to_10_filled: int = 9,
) -> List[DistributionLine]:
    """
    Annual membership fee (e.g. $10): L1 10%; L2–L10 1% each; pool 10%; Shufti fixed; remainder platform.

    `levels_2_to_10_filled`: how many of levels 2–10 have a sponsor (0–9). Missing slots increase platform net.
    """
    g = _d(gross)
    l1 = _d(g * Decimal("0.10"))
    per_l = _d(g * Decimal("0.01"))
    filled = max(0, min(9, levels_2_to_10_filled))
    l2_10 = _d(per_l * filled)
    pool = _d(g * Decimal("0.10"))
    shufti = _d(shufti_fixed)
    allocated = _d(l1 + l2_10 + pool + shufti)
    platform = _d(g - allocated)
    return [
        DistributionLine("level_1_sponsor", l1),
        DistributionLine("level_2_to_10_sponsors", l2_10),
        DistributionLine("founding_members_pool", pool),
        DistributionLine("shufti_kyc_payable", shufti),
        DistributionLine("platform_revenue_net", platform),
    ]


def founding_membership_split(
    gross: Decimal, *, levels_2_to_10_filled: int = 9
) -> List[DistributionLine]:
    """Founding membership (e.g. $100): L1 10%; L2–L10 1% each; pool 10%; remainder platform."""
    g = _d(gross)
    l1 = _d(g * Decimal("0.10"))
    per_l = _d(g * Decimal("0.01"))
    filled = max(0, min(9, levels_2_to_10_filled))
    l2_10 = _d(per_l * filled)
    pool = _d(g * Decimal("0.10"))
    allocated = _d(l1 + l2_10 + pool)
    platform = _d(g - allocated)
    return [
        DistributionLine("level_1_sponsor", l1),
        DistributionLine("level_2_to_10_sponsors", l2_10),
        DistributionLine("founding_members_pool", pool),
        DistributionLine("platform_revenue_net", platform),
    ]


def ad_revenue_participant_split(
    gross: Decimal, *, levels_2_to_10_filled: int = 9
) -> List[DistributionLine]:
    """Ad share on participant page: member 40%; L1 5%; L2–L10 1% each; pool 10%; remainder platform."""
    g = _d(gross)
    member = _d(g * Decimal("0.40"))
    l1 = _d(g * Decimal("0.05"))
    per_l = _d(g * Decimal("0.01"))
    filled = max(0, min(9, levels_2_to_10_filled))
    l2_10 = _d(per_l * filled)
    pool = _d(g * Decimal("0.10"))
    allocated = _d(member + l1 + l2_10 + pool)
    platform = _d(g - allocated)
    return [
        DistributionLine("participant_share", member),
        DistributionLine("level_1_sponsor", l1),
        DistributionLine("level_2_to_10_sponsors", l2_10),
        DistributionLine("founding_members_pool", pool),
        DistributionLine("platform_revenue_net", platform),
    ]


def ad_revenue_nominator_split(
    gross: Decimal, *, levels_2_to_10_filled: int = 9
) -> List[DistributionLine]:
    """Ad share on nominator page: nominator 10%; L1 2.5%; L2–L10 1% each; pool 10%; remainder platform."""
    g = _d(gross)
    nom = _d(g * Decimal("0.10"))
    l1 = _d(g * Decimal("0.025"))
    per_l = _d(g * Decimal("0.01"))
    filled = max(0, min(9, levels_2_to_10_filled))
    l2_10 = _d(per_l * filled)
    pool = _d(g * Decimal("0.10"))
    allocated = _d(nom + l1 + l2_10 + pool)
    platform = _d(g - allocated)
    return [
        DistributionLine("nominator_share", nom),
        DistributionLine("level_1_sponsor", l1),
        DistributionLine("level_2_to_10_sponsors", l2_10),
        DistributionLine("founding_members_pool", pool),
        DistributionLine("platform_revenue_net", platform),
    ]


def club_markup_split(
    base_subscription: Decimal,
    *,
    markup_rate: Decimal = Decimal("0.20"),
    levels_2_to_10_filled: int = 9,
) -> ClubMarkupSplit:
    """
    Club subscription: charge = base × (1 + markup_rate). Splits apply to markup only.
    Base is agent pass-through (payable to club owner), not platform revenue.
    From markup: L1 10%; L2–L10 1% each; pool 10%; remainder platform.
    """
    base = _d(base_subscription)
    markup = _d(base * markup_rate)
    charge = _d(base + markup)
    l1 = _d(markup * Decimal("0.10"))
    per_l = _d(markup * Decimal("0.01"))
    filled = max(0, min(9, levels_2_to_10_filled))
    l2_10 = _d(per_l * filled)
    pool = _d(markup * Decimal("0.10"))
    allocated = _d(l1 + l2_10 + pool)
    plat = _d(markup - allocated)
    return ClubMarkupSplit(
        gross_charge=charge,
        base_to_owner=base,
        markup=markup,
        level1_sponsor=l1,
        level2_to_10=l2_10,
        founding_pool=pool,
        platform_net=plat,
    )


def cashout_fee_and_net(requested: Decimal) -> CashoutFeeResult:
    """
    Cashout fee: 1% of request, minimum $20, maximum $1,000.
    """
    req = _d(requested)
    raw = _d(req * Decimal("0.01"))
    fee = max(Decimal("20"), min(raw, Decimal("1000")))
    fee = _d(fee)
    net = _d(req - fee)
    return CashoutFeeResult(requested=req, fee=fee, net_to_member=net)
