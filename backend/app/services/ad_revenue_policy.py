"""Advertising revenue rules (client, Shafi Abeid, confirmed 2026-09-28): central calculator.

POLICY-READY, NOT WIRED TO POSTING. No authoritative advertising revenue event exists in the
application today:
  * the internal advertising module (campaigns, placements, impressions, ad_revenue_shares)
    is not mounted and has no payment/revenue engine;
  * the Annual Ads webhook is mounted but disabled, records only an agent-net receipt and
    carries no verified MyHigh5 buyer identity, so no purchaser (and no sponsor) can be
    attributed from it.
Nothing here creates a journal, commission or payout. When a real ad-slot purchase or
contest-page ad revenue event exists, its posting code must call these functions (and use
the existing double-entry/idempotency conventions of new_model_ledger).

Type 1 - purchased ad slots (including Annual Ads): the buyer's DIRECT sponsor earns
  20% of the FULL purchase amount, or 40% once permanently qualified
  (affiliate_rate_policy; the 40% replaces the 20%).
Type 2 - contest-page ads: of the ad revenue generated on a contesting page
  PERSONAL submission (starts at City):     owner 20% + owner's direct sponsor 1%  (21%)
  NOMINATION (starts at Country):           owner 10% + owner's direct sponsor 1%  (11%)
  The class is the entry's original provenance and follows the creative through every
  later level; it is never derived from the current contest level.
Annual Ads: Type 1 only; Type 2 never applies.
No valid direct sponsor -> no sponsor share (never invented, never rolled up).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import affiliate_rate_policy as rates
from app.services.financial_integrity import money

PERSONAL_OWNER_RATE = Decimal("0.20")
NOMINATION_OWNER_RATE = Decimal("0.10")
CONTEST_PAGE_SPONSOR_RATE = Decimal("0.01")


class ContestPageClass(str, enum.Enum):
    PERSONAL = "PERSONAL_SUBMISSION"
    NOMINATION = "NOMINATION"


OWNER_RATE_BY_CLASS = {ContestPageClass.PERSONAL: PERSONAL_OWNER_RATE, ContestPageClass.NOMINATION: NOMINATION_OWNER_RATE}


@dataclass(frozen=True)
class AdSlotSplit:
    gross: Decimal
    sponsor_user_id: Optional[int]
    sponsor_rate: Decimal
    sponsor_commission: Decimal


@dataclass(frozen=True)
class ContestPageSplit:
    applicable: bool
    page_class: Optional[ContestPageClass]
    revenue: Decimal
    owner_user_id: Optional[int]
    owner_rate: Decimal
    owner_share: Decimal
    sponsor_user_id: Optional[int]
    sponsor_share: Decimal

    @property
    def total_distributed(self) -> Decimal:
        return self.owner_share + self.sponsor_share


def valid_direct_sponsor(db: Session, user_id: Optional[int]) -> Optional[User]:
    """Same eligibility as the existing direct commission: set, not self, active, not deleted."""
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.sponsor_id or int(user.sponsor_id) == int(user.id):
        return None
    sponsor = db.query(User).filter(User.id == user.sponsor_id).first()
    if sponsor is None or sponsor.is_active is False or sponsor.is_deleted is True:
        return None
    return sponsor


# ---------------------------------------------------------------- Type 1: purchased ad slots

def ad_slot_split(db: Session, *, buyer_user_id: int, gross_amount) -> AdSlotSplit:
    """Direct sponsor commission on a purchased ad slot (Annual Ads included): full gross base."""
    gross = money(gross_amount)
    sponsor = valid_direct_sponsor(db, buyer_user_id)
    if sponsor is None or gross <= 0:
        return AdSlotSplit(gross=gross, sponsor_user_id=None, sponsor_rate=Decimal("0"), sponsor_commission=Decimal("0.00"))
    rate = rates.direct_rate_for_category(db, sponsor, rates.AD_SLOT_PURCHASE)
    return AdSlotSplit(gross=gross, sponsor_user_id=sponsor.id, sponsor_rate=rate, sponsor_commission=money(gross * rate))


# ---------------------------------------------------------------- Type 2: contest-page ads

def classify_entry(db: Session, contestant) -> Optional[ContestPageClass]:
    """Original provenance: the Phase 5 entry-safety record, else the entry's own entry_type."""
    from app.models.contest_eligibility import ContestEntrySafety

    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant.id).first()
    kind = safety.entry_kind if safety is not None else None
    if kind == "PERSONAL_SUBMISSION":
        return ContestPageClass.PERSONAL
    if kind == "NOMINATION":
        return ContestPageClass.NOMINATION
    entry_type = (getattr(contestant, "entry_type", None) or "").strip().lower()
    if entry_type == "participation":
        return ContestPageClass.PERSONAL
    if entry_type == "nomination":
        return ContestPageClass.NOMINATION
    return None


def contest_page_owner(db: Session, contestant, page_class: ContestPageClass) -> Optional[int]:
    """The creative's owner account. For a nomination only an independently confirmed nominee
    (never the nominator); unconfirmed -> no owner share."""
    from app.models.contest_eligibility import ContestEntrySafety

    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant.id).first()
    if page_class == ContestPageClass.PERSONAL:
        if safety is not None and safety.creative_owner_user_id:
            return int(safety.creative_owner_user_id)
        return int(contestant.user_id)
    if safety is not None and safety.nominee_user_id:
        return int(safety.nominee_user_id)
    if safety is not None and safety.creative_owner_type == "NOMINEE" and safety.creative_owner_user_id:
        return int(safety.creative_owner_user_id)
    return None


def contest_page_split(db: Session, *, contestant, revenue_amount, is_annual_ad: bool = False) -> ContestPageSplit:
    revenue = money(revenue_amount)
    none = ContestPageSplit(applicable=False, page_class=None, revenue=revenue, owner_user_id=None,
                            owner_rate=Decimal("0"), owner_share=Decimal("0.00"), sponsor_user_id=None,
                            sponsor_share=Decimal("0.00"))
    if is_annual_ad or revenue <= 0:
        return none  # Annual Ads: contest-page revenue sharing never applies
    page_class = classify_entry(db, contestant)
    if page_class is None:
        return none
    owner_id = contest_page_owner(db, contestant, page_class)
    owner_rate = OWNER_RATE_BY_CLASS[page_class]
    if owner_id is None:
        return ContestPageSplit(applicable=True, page_class=page_class, revenue=revenue, owner_user_id=None,
                                owner_rate=owner_rate, owner_share=Decimal("0.00"), sponsor_user_id=None,
                                sponsor_share=Decimal("0.00"))
    sponsor = valid_direct_sponsor(db, owner_id)
    return ContestPageSplit(
        applicable=True, page_class=page_class, revenue=revenue, owner_user_id=owner_id, owner_rate=owner_rate,
        owner_share=money(revenue * owner_rate),
        sponsor_user_id=sponsor.id if sponsor else None,
        sponsor_share=money(revenue * CONTEST_PAGE_SPONSOR_RATE) if sponsor else Decimal("0.00"),
    )
