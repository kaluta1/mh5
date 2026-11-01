"""Contest-entry advertising revenue sharing (approved rules, ad_revenue_policy constants).

Eligible revenue = validated revenue earned by ad units on an individual contest-entry page:
  * ORDINARY (MyHigh5 campaigns): the validated charge of each viewable impression (net of
    reversals for invalid activity).
  * ADSENSE: Google's publisher earnings (already after Google's share - never deducted twice) per
    reporting bucket (day x ad unit x currency), shared in proportion to OUR valid impressions in the
    same bucket; impressions on non-entry pages keep their part for MyHigh5.
  * ANNUAL_ADS: never (the product cannot reach this code: no decision or event is ever ANNUAL_ADS).
Feeds, listings and discovery pages are platform revenue under this program.

Shares from the same base: creative 20% (personal submission) or 10% (nomination: the confirmed
nominee, never the nominator) + the creative's direct sponsor 1%, rounded DOWN to the cent; the
residual stays with MyHigh5. The original submission type comes from adv_entry_origins and never
changes with the contest level.

Monthly release (UTC month, after a grace period, all events validated; AdSense additionally needs
the month's finalized Google earnings). Estimates are never payable.
  RELEASED      -> affiliate_commissions row (AD_REVENUE, APPROVED), Dr 5006 / Cr 2001: the existing
                   wallet, holds, minimum, accumulation and cash-out rules apply unchanged.
  HELD_UNCLAIMED-> nominee not linked yet: Dr 5006 / Cr 2322, released to the nominee after the claim.
  HELD_SPONSOR  -> sponsor not determinable at the earning event (nominee not linked): Dr 5006 / Cr 2322,
                   kept until an administrator applies the confirmed policy. Never forfeited automatically.
  HELD_REVIEW   -> original type not provable: no amount until an administrator resolves the origin.
A sponsor that is missing or ineligible (existing direct-commission rule) gets no line; the creative's
percentage is never reduced.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.advertising_v2 import (AdvAdsenseBucket, AdvAdsenseImport, AdvAdsenseMonth, AdvAllocation,
                                       AdvEntryOrigin, AdvImpressionEvent)
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.services import ad_attribution
from app.services import ad_campaigns as camp
from app.services.ad_revenue_policy import CONTEST_PAGE_SPONSOR_RATE
from app.services.financial_integrity import FinancialIntegrityError, money

logger = logging.getLogger(__name__)

FINALIZE_GRACE_DAYS = int(os.getenv("AD_SHARING_FINALIZE_GRACE_DAYS", "3"))
CATEGORY_CREATIVE = "CONTEST_PAGE_AD_CREATIVE"
CATEGORY_SPONSOR = "CONTEST_PAGE_AD_SPONSOR"
Q8 = Decimal("0.00000001")


def floor2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end


def period_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


# ---------------------------------------------------------------- base amounts per earning group

@dataclass
class _Group:
    contestant_id: int
    season_key: int
    contest_level: Optional[str]
    creative_user_id: Optional[int]
    sponsor_user_id: Optional[int]
    sponsor_status: str
    rule_version: str
    base: Decimal = Decimal(0)
    impressions: int = 0


def _events(db: Session, period: str, source: str):
    start, end = period_bounds(period)
    return (db.query(AdvImpressionEvent)
            .filter(AdvImpressionEvent.event_type == "VIEWABLE", AdvImpressionEvent.validation_status == "VALID",
                    AdvImpressionEvent.reversed_at.is_(None), AdvImpressionEvent.source == source,
                    AdvImpressionEvent.earning_day >= start, AdvImpressionEvent.earning_day < end))


def _bucket_rates(db: Session, period: str, *, finalized: bool) -> dict:
    """Per (day, ad unit, currency): Google earnings per valid impression of ours in that bucket."""
    start, end = period_bounds(period)
    buckets = db.query(AdvAdsenseBucket).filter(AdvAdsenseBucket.day >= start, AdvAdsenseBucket.day < end).all()
    totals = dict(
        ((d, s), int(n)) for d, s, n in
        _events(db, period, "ADSENSE").with_entities(AdvImpressionEvent.earning_day, AdvImpressionEvent.adsense_slot,
                                                     func.count(AdvImpressionEvent.id))
        .group_by(AdvImpressionEvent.earning_day, AdvImpressionEvent.adsense_slot).all())
    rates = {}
    for b in buckets:
        if b.currency != "USD":
            continue                     # never mixed across currencies; non-USD buckets stay unallocated
        earnings = b.finalized_earnings if finalized else b.estimated_earnings
        if finalized and b.status != "FINALIZED":
            continue
        count = totals.get((b.day, _unit_slot(b.ad_unit)), 0)
        if earnings is None or count <= 0:
            continue
        rates[(b.day, _unit_slot(b.ad_unit))] = Decimal(str(earnings)) / Decimal(count)
    return rates


def _unit_slot(ad_unit: str) -> str:
    """AdSense reports 'ca-pub-...:1234567890'; our decisions store the slot id '1234567890'."""
    return (ad_unit or "").split(":")[-1]


def compute_groups(db: Session, period: str, source: str, *, finalized: bool) -> list[_Group]:
    groups: dict = {}
    rates = _bucket_rates(db, period, finalized=finalized) if source == "ADSENSE" else None
    rows = (_events(db, period, source).filter(AdvImpressionEvent.contestant_id.isnot(None))
            .with_entities(AdvImpressionEvent.contestant_id, AdvImpressionEvent.season_id,
                           AdvImpressionEvent.contest_level, AdvImpressionEvent.creative_user_id,
                           AdvImpressionEvent.sponsor_user_id, AdvImpressionEvent.sponsor_status,
                           AdvImpressionEvent.rule_version, AdvImpressionEvent.earning_day,
                           AdvImpressionEvent.adsense_slot, AdvImpressionEvent.charged_amount).all())
    for cid, season, level, creative, sponsor, sstatus, rule, day, slot, charged in rows:
        if source == "ADSENSE":
            amount = rates.get((day, slot))
            if amount is None:
                continue                 # no Google figure for this bucket (yet): nothing to share
        else:
            amount = Decimal(str(charged or 0))
        key = (cid, season or 0, creative, sponsor, sstatus)
        g = groups.get(key)
        if g is None:
            g = groups[key] = _Group(cid, season or 0, level, creative, sponsor, sstatus or "UNRESOLVED",
                                     rule or ad_attribution.RULE_VERSION)
        g.base += amount
        g.impressions += 1
    for g in groups.values():
        g.base = g.base.quantize(Q8)
    return list(groups.values())


def _origin(db: Session, contestant_id: int) -> Optional[AdvEntryOrigin]:
    return db.query(AdvEntryOrigin).filter(AdvEntryOrigin.contestant_id == contestant_id).first()


def plan_lines(db: Session, period: str, source: str, *, finalized: bool) -> list[dict]:
    """The lines a period would produce (used for estimates and for the final release)."""
    lines = []
    for g in compute_groups(db, period, source, finalized=finalized):
        origin = _origin(db, g.contestant_id)
        kind = origin.origin_kind if origin is not None and origin.status == "RESOLVED" else None
        rate = ad_attribution.creative_rate(kind)
        if kind is None:
            status, amount, rate = "HELD_REVIEW", Decimal("0.00"), Decimal("0")
        elif g.creative_user_id is None:
            status, amount = "HELD_UNCLAIMED", floor2(g.base * rate)
        else:
            status, amount = "RELEASED", floor2(g.base * rate)
        common = dict(period=period, contestant_id=g.contestant_id, source=source,
                      product="ORDINARY" if source == "MYHIGH5" else "ADSENSE", origin_kind=kind,
                      contest_level=g.contest_level, season_key=g.season_key, base_amount=g.base,
                      valid_impressions=g.impressions, rule_version=g.rule_version)
        lines.append(dict(common, role="CREATIVE", beneficiary_user_id=g.creative_user_id, rate=rate,
                          amount=amount, status=status))
        if kind is None:
            # Origin under review: the creative (and so the sponsor) is not known yet. Priced at resolution.
            lines.append(dict(common, role="SPONSOR", beneficiary_user_id=None, rate=CONTEST_PAGE_SPONSOR_RATE,
                              amount=Decimal("0.00"), status="HELD_REVIEW"))
        elif g.sponsor_status == "VALID" and g.sponsor_user_id:
            lines.append(dict(common, role="SPONSOR", beneficiary_user_id=g.sponsor_user_id,
                              rate=CONTEST_PAGE_SPONSOR_RATE, amount=floor2(g.base * CONTEST_PAGE_SPONSOR_RATE),
                              status="RELEASED" if kind is not None else "HELD_REVIEW"))
        elif g.sponsor_status == "UNRESOLVED":
            lines.append(dict(common, role="SPONSOR", beneficiary_user_id=None, rate=CONTEST_PAGE_SPONSOR_RATE,
                              amount=floor2(g.base * CONTEST_PAGE_SPONSOR_RATE), status="HELD_SPONSOR"))
        # NONE / INELIGIBLE: existing direct-commission rule - no sponsor share, creative share unchanged.
    return _merge(lines)


def _merge(lines: list[dict]) -> list[dict]:
    """Same (contestant, role, season, beneficiary) from several snapshot groups -> one line."""
    out: dict = {}
    for line in lines:
        key = (line["contestant_id"], line["role"], line["season_key"], line["beneficiary_user_id"] or 0,
               line["status"])
        if key in out:
            o = out[key]
            o["base_amount"] += line["base_amount"]
            o["valid_impressions"] += line["valid_impressions"]
            o["amount"] = floor2(o["base_amount"] * o["rate"]) if o["status"] != "HELD_REVIEW" else Decimal("0.00")
        else:
            out[key] = dict(line)
    return list(out.values())


# ---------------------------------------------------------------- ledger

def _post_commission(db: Session, line: AdvAllocation, *, from_held: bool) -> AffiliateCommission:
    from app.services.new_model_ledger import Line, PostingType, SourceType, post_entry
    from app.services.new_model_reference_data import NEW_MODEL_VERSION

    amount = money(line.amount)
    source_user = line.beneficiary_user_id
    if line.role == "SPONSOR":
        from app.models.contests import Contestant

        att_creative = (db.query(AdvAllocation.beneficiary_user_id)
                        .filter(AdvAllocation.period == line.period, AdvAllocation.contestant_id == line.contestant_id,
                                AdvAllocation.role == "CREATIVE", AdvAllocation.beneficiary_user_id.isnot(None))
                        .first())
        c = db.query(Contestant).filter(Contestant.id == line.contestant_id).first()
        source_user = (att_creative[0] if att_creative else None) or (c.user_id if c else line.beneficiary_user_id)
    commission = AffiliateCommission(
        user_id=line.beneficiary_user_id, source_user_id=source_user, commission_type=CommissionType.AD_REVENUE,
        level=1, base_amount=money(line.base_amount), commission_rate=line.rate, commission_amount=amount,
        status=CommissionStatus.APPROVED, transaction_date=datetime.utcnow(), business_model_version=NEW_MODEL_VERSION,
        revenue_category=CATEGORY_CREATIVE if line.role == "CREATIVE" else CATEGORY_SPONSOR,
        source_type=camp.SOURCE_AD_ALLOCATION, source_id=line.id,
        reference_type="contest_entry", reference_id=str(line.contestant_id))
    db.add(commission)
    db.flush()
    debit = camp.HELD_SHARES_ACCOUNT if from_held else camp.SHARE_EXPENSE_ACCOUNT
    post_entry(db, source_type=SourceType.COMMISSION, source_id=commission.id,
               posting_type=PostingType.COMMISSION_ACCRUAL,
               lines=[Line(debit, debit=amount, description=("Release held contest-page ad share" if from_held
                                                              else "Contest-page advertising revenue share expense")),
                      Line("2001", credit=amount,
                           description=f"Contest-page ad share payable - User #{line.beneficiary_user_id}")],
               description=f"Contest-page ad revenue share #{line.id} ({line.role}, entry {line.contestant_id}, "
                           f"{line.period}, {line.source})")
    line.commission_id, line.status, line.released_at = commission.id, "RELEASED", datetime.utcnow()
    from app.services.cashout_engine import request_cycle

    request_cycle()                       # a no-op while automatic payouts are off
    return commission


def _post_hold(db: Session, line: AdvAllocation) -> None:
    from app.services.new_model_ledger import Line, PostingType, post_entry

    amount = money(line.amount)
    if amount <= 0:
        return
    entry = post_entry(db, source_type=camp.SOURCE_AD_ALLOCATION, source_id=line.id, posting_type="HOLD",
                       lines=[Line(camp.SHARE_EXPENSE_ACCOUNT, debit=amount,
                                   description="Contest-page advertising revenue share expense"),
                              Line(camp.HELD_SHARES_ACCOUNT, credit=amount,
                                   description=f"Contest-page ad share held ({line.status}) - entry {line.contestant_id}")],
                       description=f"Contest-page ad share held #{line.id} ({line.role}, {line.status})")
    line.hold_journal_id = entry.id


def _apply(db: Session, line: AdvAllocation) -> None:
    if line.status == "RELEASED":
        if money(line.amount) > 0:
            _post_commission(db, line, from_held=False)
    elif line.status in ("HELD_UNCLAIMED", "HELD_SPONSOR"):
        _post_hold(db, line)


# ---------------------------------------------------------------- finalize a period

def _finalized_lines(db: Session, period: str, source: str):
    return (db.query(AdvAllocation).filter(AdvAllocation.period == period, AdvAllocation.source == source,
                                           AdvAllocation.status != "SUPERSEDED"))


def finalize_period(db: Session, *, period: str, source: str, actor_id: Optional[int] = None,
                    now: Optional[datetime] = None) -> dict:
    """Release one month of one source, once. Refuses an open month, unvalidated events, and (AdSense)
    a month without finalized Google earnings. Program switches must be on."""
    now = now or datetime.utcnow()
    cfg = camp.get_settings(db)
    if not cfg.contest_sharing_enabled:
        raise camp.AdError("SHARING_NOT_ACTIVATED", "Contest-entry revenue sharing is not activated")
    if source not in ("MYHIGH5", "ADSENSE"):
        raise camp.AdError("INVALID_SOURCE", "Source must be MYHIGH5 or ADSENSE", 400)
    if source == "ADSENSE" and not cfg.adsense_sharing_enabled:
        raise camp.AdError("ADSENSE_SHARING_NOT_ACTIVATED",
                           "AdSense revenue sharing is not activated (policy compatibility not confirmed)")
    start, end = period_bounds(period)
    if now.date() < end + timedelta(days=FINALIZE_GRACE_DAYS):
        raise camp.AdError("PERIOD_OPEN", f"{period} can be finalized from {end + timedelta(days=FINALIZE_GRACE_DAYS)}")
    waiting = (db.query(func.count(AdvImpressionEvent.id))
               .filter(AdvImpressionEvent.validation_status == "PENDING",
                       AdvImpressionEvent.received_at < datetime.combine(end, datetime.min.time()) + timedelta(days=1))
               .scalar())
    if int(waiting or 0) > 0:
        raise camp.AdError("EVENTS_PENDING", "Some impressions of this month are not validated yet")
    if source == "ADSENSE":
        month = db.query(AdvAdsenseMonth).filter(AdvAdsenseMonth.period == period,
                                                 AdvAdsenseMonth.currency == "USD").first()
        if month is None:
            raise camp.AdError("ADSENSE_NOT_FINALIZED", "Record the finalized Google earnings of this month first")
    if _finalized_lines(db, period, source).first() is not None:
        return {"status": "ALREADY_FINALIZED", "lines": _finalized_lines(db, period, source).count()}
    created = []
    for spec in plan_lines(db, period, source, finalized=True):
        line = AdvAllocation(**spec, beneficiary_key=spec["beneficiary_user_id"] or 0, currency="USD", version=1)
        db.add(line)
        db.flush()
        _apply(db, line)
        created.append(line)
    db.add(AuditTrail(table_name="adv_allocations", record_id=0, action="FINALIZE_PERIOD", old_values=None,
                      new_values={"period": period, "source": source, "lines": len(created),
                                  "released": str(sum((money(l.amount) for l in created if l.status == "RELEASED"),
                                                      Decimal("0.00")))}, user_id=actor_id))
    db.flush()
    check_invariants(db, period=period, source=source)
    return {"status": "FINALIZED", "lines": len(created)}


def check_invariants(db: Session, *, period: str, source: str) -> None:
    """Allocations never exceed the eligible base, per entry and in total."""
    total_base = Decimal(0)
    total_alloc = Decimal(0)
    for l in _finalized_lines(db, period, source).filter(AdvAllocation.status != "REVERSED").all():
        if money(l.amount) > Decimal(str(l.base_amount)):
            raise FinancialIntegrityError(f"Allocation {l.id} exceeds its eligible revenue base")
        if Decimal(str(l.rate)) > Decimal("0.20"):
            raise FinancialIntegrityError(f"Allocation {l.id} has an unapproved rate")
        if l.role == "CREATIVE":
            total_base += Decimal(str(l.base_amount))
        total_alloc += Decimal(str(l.amount))
    if total_alloc > total_base:
        raise FinancialIntegrityError(f"Allocations of {period} {source} exceed the eligible revenue")


# ---------------------------------------------------------------- held amounts

def release_claimed(db: Session) -> int:
    """HELD_UNCLAIMED creative lines whose nominee has since been linked (claim or admin link)."""
    from app.models.contests import Contestant
    from app.services import ad_revenue_policy as policy

    released = 0
    for line in (db.query(AdvAllocation).filter(AdvAllocation.status == "HELD_UNCLAIMED",
                                                AdvAllocation.role == "CREATIVE").with_for_update().all()):
        c = db.query(Contestant).filter(Contestant.id == line.contestant_id).first()
        if c is None:
            continue
        owner = policy.contest_page_owner(db, c, policy.ContestPageClass.NOMINATION
                                          if line.origin_kind == ad_attribution.NOMINATION
                                          else policy.ContestPageClass.PERSONAL)
        if owner is None:
            continue
        line.beneficiary_user_id, line.beneficiary_key = owner, owner
        if money(line.amount) > 0:
            _post_commission(db, line, from_held=True)
        else:
            line.status, line.released_at = "RELEASED", datetime.utcnow()
        released += 1
    db.flush()
    return released


def release_held_sponsor(db: Session, *, line_id: int, actor_id: int, note: str) -> AdvAllocation:
    """Administrator applies the confirmed sponsor policy to a HELD_SPONSOR line: pay the creative's
    valid direct sponsor (as recorded on the creative's account now). Never automatic."""
    from app.services import ad_revenue_policy as policy

    if not (note or "").strip():
        raise camp.AdError("NOTE_REQUIRED", "A note with the approved policy is required", 400)
    line = db.query(AdvAllocation).filter(AdvAllocation.id == line_id).with_for_update().one()
    if line.status != "HELD_SPONSOR":
        raise camp.AdError("INVALID_STATE", "Only a held sponsor share can be released")
    creative = (db.query(AdvAllocation).filter(AdvAllocation.period == line.period,
                                               AdvAllocation.contestant_id == line.contestant_id,
                                               AdvAllocation.role == "CREATIVE", AdvAllocation.source == line.source,
                                               AdvAllocation.beneficiary_user_id.isnot(None)).first())
    if creative is None:
        raise camp.AdError("CREATIVE_NOT_LINKED", "The creative's account is not linked yet")
    sponsor = policy.valid_direct_sponsor(db, creative.beneficiary_user_id)
    if sponsor is None:
        raise camp.AdError("NO_VALID_SPONSOR", "The creative has no valid direct sponsor; the share stays held")
    line.beneficiary_user_id, line.beneficiary_key = sponsor.id, sponsor.id
    line.note = note.strip()[:300]
    _post_commission(db, line, from_held=True)
    db.add(AuditTrail(table_name="adv_allocations", record_id=line.id, action="RELEASE_HELD_SPONSOR",
                      old_values=None, new_values={"sponsor": sponsor.id, "note": line.note}, user_id=actor_id))
    db.flush()
    return line


def apply_origin_resolution(db: Session, *, contestant_id: int) -> int:
    """After an administrator resolved an entry's origin: price its HELD_REVIEW lines."""
    from app.models.contests import Contestant
    from app.services import ad_revenue_policy as policy

    origin = _origin(db, contestant_id)
    if origin is None or origin.status != "RESOLVED":
        return 0
    c = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    page_class = (policy.ContestPageClass.PERSONAL if origin.origin_kind == ad_attribution.PERSONAL
                  else policy.ContestPageClass.NOMINATION)
    owner = policy.contest_page_owner(db, c, page_class) if c is not None else None
    done = 0
    for line in (db.query(AdvAllocation).filter(AdvAllocation.contestant_id == contestant_id,
                                                AdvAllocation.status == "HELD_REVIEW").with_for_update().all()):
        line.origin_kind = origin.origin_kind
        if line.role == "CREATIVE":
            line.rate = ad_attribution.creative_rate(origin.origin_kind)
            line.amount = floor2(Decimal(str(line.base_amount)) * Decimal(str(line.rate)))
            if owner is None:
                line.status = "HELD_UNCLAIMED"
            else:
                line.beneficiary_user_id, line.beneficiary_key, line.status = owner, owner, "RELEASED"
        else:
            # The creative is known only now: its direct sponsor as recorded at resolution.
            sponsor = policy.valid_direct_sponsor(db, owner) if owner is not None else None
            line.amount = floor2(Decimal(str(line.base_amount)) * CONTEST_PAGE_SPONSOR_RATE)
            if owner is None:
                line.status = "HELD_SPONSOR"
            elif sponsor is not None:
                line.beneficiary_user_id, line.beneficiary_key, line.status = sponsor.id, sponsor.id, "RELEASED"
            else:
                # Existing direct-commission rule: no valid sponsor -> no sponsor share (nothing was posted).
                line.amount, line.status, line.reversed_at = Decimal("0.00"), "REVERSED", datetime.utcnow()
                line.note = "No valid direct sponsor"
        db.flush()
        _apply(db, line)
        done += 1
    db.flush()
    return done


# ---------------------------------------------------------------- reversals of a finalized period

def _reverse_line(db: Session, line: AdvAllocation, reason: str) -> None:
    from app.services.new_model_ledger import Line, PostingType, SourceType, find_entry, idempotency_key, is_reversed
    from app.services.new_model_ledger import post_entry, reverse_entry
    from app.models.accounting import JournalEntry

    if line.commission_id:
        commission = (db.query(AffiliateCommission).filter(AffiliateCommission.id == line.commission_id)
                      .with_for_update().one())
        if commission.status == CommissionStatus.APPROVED and str(commission.payout_reference or "").startswith("intent:"):
            raise FinancialIntegrityError("A payout of this share is in progress; reconcile the payout first")
        accrual = find_entry(db, idempotency_key(SourceType.COMMISSION, commission.id, PostingType.COMMISSION_ACCRUAL))
        if commission.status == CommissionStatus.PAID:
            # Paid already: receivable from the member (account 1200); recovery needs an approved policy.
            post_entry(db, source_type=SourceType.COMMISSION, source_id=commission.id,
                       posting_type=PostingType.REVERSAL, key_suffix="clawback",
                       lines=[Line("1200", debit=money(commission.commission_amount),
                                   description=f"Receivable - paid ad share clawback - User #{commission.user_id}"),
                              Line(camp.SHARE_EXPENSE_ACCOUNT, credit=money(commission.commission_amount),
                                   description="Reverse contest-page ad share")],
                       description=f"Clawback of paid ad share #{commission.id}: {reason}",
                       reverses_entry_id=accrual.id if accrual else None)
        elif commission.status != CommissionStatus.CANCELLED and accrual is not None and not is_reversed(db, accrual):
            reverse_entry(db, accrual, reason=reason)
        was_paid = commission.status == CommissionStatus.PAID
        commission.status = CommissionStatus.CANCELLED
        if line.hold_journal_id and not was_paid:
            # Released from a hold: the hold entry moved into 2001 through this commission, whose
            # accrual (Dr 2322 / Cr 2001) was just reversed. Reverse the hold too: 2322 back to 5006.
            hold = db.query(JournalEntry).filter(JournalEntry.id == line.hold_journal_id).one()
            if not is_reversed(db, hold):
                reverse_entry(db, hold, reason=reason)
    elif line.hold_journal_id:
        hold = db.query(JournalEntry).filter(JournalEntry.id == line.hold_journal_id).one()
        if not is_reversed(db, hold):
            reverse_entry(db, hold, reason=reason)
    line.status, line.reversed_at = "SUPERSEDED", datetime.utcnow()
    line.note = (reason or "")[:300]


def adjust_after_reversal(db: Session, *, period: str, source: str, reason: str, actor_id: int) -> dict:
    """Invalid activity was reversed after this period was finalized: recompute, supersede changed lines
    (auditable reversal of their postings) and post the new version. Unchanged lines are kept."""
    current = {(l.contestant_id, l.role, l.season_key, l.beneficiary_key, l.status if l.status != "RELEASED" else "R"): l
               for l in _finalized_lines(db, period, source).with_for_update().all()}
    if not current:
        return {"status": "NOT_FINALIZED"}
    plan = {(s["contestant_id"], s["role"], s["season_key"], s["beneficiary_user_id"] or 0,
             s["status"] if s["status"] != "RELEASED" else "R"): s for s in plan_lines(db, period, source, finalized=True)}
    changed = 0
    for key, line in current.items():
        spec = plan.get(key)
        if spec is not None and money(spec["amount"]) == money(line.amount) \
                and Decimal(str(spec["base_amount"])) == Decimal(str(line.base_amount)):
            continue
        version = line.version + 1
        _reverse_line(db, line, reason)
        changed += 1
        if spec is not None:
            new = AdvAllocation(**spec, beneficiary_key=spec["beneficiary_user_id"] or 0, currency="USD",
                                version=version)
            db.add(new)
            db.flush()
            _apply(db, new)
    for key, spec in plan.items():
        if key not in current:
            new = AdvAllocation(**spec, beneficiary_key=spec["beneficiary_user_id"] or 0, currency="USD", version=1)
            db.add(new)
            db.flush()
            _apply(db, new)
            changed += 1
    db.add(AuditTrail(table_name="adv_allocations", record_id=0, action="ADJUST_AFTER_REVERSAL", old_values=None,
                      new_values={"period": period, "source": source, "changed": changed, "reason": reason[:200]},
                      user_id=actor_id))
    db.flush()
    check_invariants(db, period=period, source=source)
    return {"status": "ADJUSTED", "changed": changed}


# ---------------------------------------------------------------- AdSense

ADSENSE_API = "https://adsense.googleapis.com/v2"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def adsense_credentials() -> Optional[dict]:
    keys = {"account": "ADSENSE_ACCOUNT_ID", "client_id": "ADSENSE_OAUTH_CLIENT_ID",
            "client_secret": "ADSENSE_OAUTH_CLIENT_SECRET", "refresh_token": "ADSENSE_OAUTH_REFRESH_TOKEN"}
    values = {k: (os.getenv(v) or "").strip() for k, v in keys.items()}
    return values if all(values.values()) else None


def missing_adsense_credentials() -> list:
    return [v for v in ("ADSENSE_ACCOUNT_ID", "ADSENSE_OAUTH_CLIENT_ID", "ADSENSE_OAUTH_CLIENT_SECRET",
                        "ADSENSE_OAUTH_REFRESH_TOKEN") if not (os.getenv(v) or "").strip()]


def _fetch_report(creds: dict, start: date, end: date, transport=None) -> list[dict]:
    """AdSense Management API v2 reports:generate, DATE x AD_UNIT_ID, ESTIMATED_EARNINGS + IMPRESSIONS
    in USD and the account's reporting time zone."""
    import httpx

    client = transport or httpx.Client(timeout=20)
    token = client.post(TOKEN_URL, data={"client_id": creds["client_id"], "client_secret": creds["client_secret"],
                                         "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"})
    token.raise_for_status()
    access = token.json()["access_token"]
    account = creds["account"] if creds["account"].startswith("accounts/") else f"accounts/{creds['account']}"
    params = [("dateRange", "CUSTOM"), ("startDate.year", start.year), ("startDate.month", start.month),
              ("startDate.day", start.day), ("endDate.year", end.year), ("endDate.month", end.month),
              ("endDate.day", end.day), ("dimensions", "DATE"), ("dimensions", "AD_UNIT_ID"),
              ("metrics", "ESTIMATED_EARNINGS"), ("metrics", "IMPRESSIONS"), ("currencyCode", "USD"),
              ("reportingTimeZone", "ACCOUNT_TIME_ZONE")]
    resp = client.get(f"{ADSENSE_API}/{account}/reports:generate", params=params,
                      headers={"Authorization": f"Bearer {access}"})
    resp.raise_for_status()
    body = resp.json()
    names = [h.get("name") for h in body.get("headers", [])]
    currency = next((h.get("currencyCode") for h in body.get("headers", []) if h.get("currencyCode")), "USD")
    out = []
    for row in body.get("rows", []) or []:
        cells = [c.get("value") for c in row.get("cells", [])]
        rec = dict(zip(names, cells))
        out.append({"day": date.fromisoformat(rec["DATE"]), "ad_unit": str(rec["AD_UNIT_ID"]),
                    "earnings": Decimal(str(rec.get("ESTIMATED_EARNINGS") or "0")),
                    "impressions": int(rec.get("IMPRESSIONS") or 0), "currency": currency})
    return out


def import_adsense(db: Session, *, start: date, end: date, actor_id: Optional[int] = None, transport=None) -> AdvAdsenseImport:
    """Import Google's estimated earnings into buckets. Finalized buckets are never overwritten.
    Without credentials nothing is fabricated: the run is recorded as NO_CREDENTIALS."""
    creds = adsense_credentials()
    run = AdvAdsenseImport(status="NO_CREDENTIALS", period_start=start, period_end=end, rows=0,
                           actor_user_id=actor_id,
                           detail="Missing: " + ", ".join(missing_adsense_credentials()) if creds is None else None)
    db.add(run)
    db.flush()
    if creds is None:
        return run
    try:
        rows = _fetch_report(creds, start, end, transport=transport)
    except Exception as exc:  # noqa: BLE001
        run.status, run.detail = "ERROR", f"{type(exc).__name__}"[:500]
        db.flush()
        return run
    for r in rows:
        bucket = (db.query(AdvAdsenseBucket).filter(AdvAdsenseBucket.day == r["day"], AdvAdsenseBucket.ad_unit == r["ad_unit"],
                                                    AdvAdsenseBucket.currency == r["currency"]).with_for_update().first())
        if bucket is None:
            db.add(AdvAdsenseBucket(day=r["day"], ad_unit=r["ad_unit"], currency=r["currency"],
                                    estimated_earnings=r["earnings"], google_impressions=r["impressions"],
                                    status="ESTIMATED", import_id=run.id))
        elif bucket.status == "ESTIMATED":
            bucket.estimated_earnings, bucket.google_impressions, bucket.import_id = r["earnings"], r["impressions"], run.id
    run.status, run.rows = "OK", len(rows)
    db.flush()
    return run


def record_finalized_month(db: Session, *, period: str, finalized_total, actor_id: int, evidence_note: str,
                           currency: str = "USD", now: Optional[datetime] = None) -> AdvAdsenseMonth:
    """Finalized Google earnings of a month (AdSense Payments report). Scales that month's buckets to the
    finalized figure and books the revenue: Dr 1240 receivable / Cr 4021 AdSense revenue. Once."""
    from app.services.new_model_ledger import Line, PostingType, post_entry

    if currency != "USD":
        raise camp.AdError("CURRENCY_UNSUPPORTED", "Only USD AdSense earnings are booked", 400)
    if not (evidence_note or "").strip():
        raise camp.AdError("NOTE_REQUIRED", "Describe the evidence (AdSense Payments report reference)", 400)
    total = money(finalized_total)
    if total < 0:
        raise camp.AdError("INVALID_VALUE", "The finalized total cannot be negative", 400)
    if db.query(AdvAdsenseMonth.id).filter(AdvAdsenseMonth.period == period, AdvAdsenseMonth.currency == currency).first():
        raise camp.AdError("ALREADY_RECORDED", "This month's finalized earnings are already recorded")
    start, end = period_bounds(period)
    now = now or datetime.utcnow()
    if now.date() < end:
        raise camp.AdError("PERIOD_OPEN", "The month has not ended")
    buckets = (db.query(AdvAdsenseBucket).filter(AdvAdsenseBucket.day >= start, AdvAdsenseBucket.day < end,
                                                 AdvAdsenseBucket.currency == currency).with_for_update().all())
    estimated = sum((Decimal(str(b.estimated_earnings)) for b in buckets), Decimal(0))
    factor = (Decimal(total) / estimated) if estimated > 0 else Decimal(0)
    for b in buckets:
        b.finalized_earnings = (Decimal(str(b.estimated_earnings)) * factor).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        b.status, b.finalized_at = "FINALIZED", now
    month = AdvAdsenseMonth(period=period, currency=currency, finalized_total=total, estimated_total=estimated,
                            recorded_by_user_id=actor_id, evidence_note=evidence_note.strip()[:500])
    db.add(month)
    db.flush()
    if total > 0:
        entry = post_entry(db, source_type=camp.SOURCE_ADSENSE_MONTH, source_id=month.id,
                           posting_type=PostingType.RECOGNITION,
                           lines=[Line(camp.ADSENSE_RECEIVABLE_ACCOUNT, debit=total,
                                       description=f"AdSense publisher earnings receivable {period}"),
                                  Line(camp.ADSENSE_REVENUE_ACCOUNT, credit=total,
                                       description=f"Google AdSense revenue (finalized) {period}")],
                           description=f"AdSense finalized earnings {period}",
                           entry_date=datetime.combine(end - timedelta(days=1), datetime.max.time()).replace(microsecond=0))
        month.journal_entry_id = entry.id
    db.add(AuditTrail(table_name="adv_adsense_months", record_id=month.id, action="RECORD_FINALIZED", old_values=None,
                      new_values={"period": period, "finalized": str(total), "estimated": str(estimated),
                                  "note": month.evidence_note}, user_id=actor_id))
    db.flush()
    return month


def record_adsense_payment(db: Session, *, month_id: int, amount, actor_id: int, reference: str):
    """Google paid the month: Dr 1001 / Cr 1240 (once per month)."""
    from app.services.new_model_ledger import Line, PostingType, post_entry

    month = db.query(AdvAdsenseMonth).filter(AdvAdsenseMonth.id == month_id).one()
    if money(amount) != money(month.finalized_total):
        raise camp.AdError("AMOUNT_MISMATCH", "The payment must equal the finalized earnings; reconcile the difference")
    return post_entry(db, source_type=camp.SOURCE_ADSENSE_MONTH, source_id=month.id, posting_type=PostingType.RECEIPT,
                      lines=[Line("1001", debit=money(amount), description=f"Google AdSense payment {reference[:60]}"),
                             Line(camp.ADSENSE_RECEIVABLE_ACCOUNT, credit=money(amount),
                                  description=f"AdSense receivable settled {month.period}")],
                      description=f"AdSense payment received {month.period}")


# ---------------------------------------------------------------- reporting

def member_summary(db: Session, user_id: int, *, now: Optional[datetime] = None) -> dict:
    """Creative and sponsor earnings, kept separate. Estimates are never available funds."""
    now = now or datetime.utcnow()
    out = {}
    for role, column in (("creative", AdvImpressionEvent.creative_user_id), ("sponsor", AdvImpressionEvent.sponsor_user_id)):
        lines = db.query(AdvAllocation).filter(AdvAllocation.beneficiary_user_id == user_id,
                                               AdvAllocation.role == role.upper()).all()
        commission_ids = [l.commission_id for l in lines if l.commission_id and l.status == "RELEASED"]
        comms = {c.id: c for c in db.query(AffiliateCommission).filter(AffiliateCommission.id.in_(commission_ids)).all()} \
            if commission_ids else {}
        available = sum((money(c.commission_amount) for c in comms.values() if c.status == CommissionStatus.APPROVED),
                        Decimal("0.00"))
        paid = sum((money(c.commission_amount) for c in comms.values() if c.status == CommissionStatus.PAID),
                   Decimal("0.00"))
        held = sum((money(l.amount) for l in lines if l.status.startswith("HELD_")), Decimal("0.00"))
        adjustments = sum((money(l.amount) for l in lines if l.status == "SUPERSEDED"), Decimal("0.00"))
        estimated = Decimal(0)
        finalized_periods = {(p, s) for p, s in db.query(AdvAllocation.period, AdvAllocation.source).distinct().all()}
        for source in ("MYHIGH5", "ADSENSE"):
            q = (db.query(AdvImpressionEvent).filter(column == user_id, AdvImpressionEvent.source == source,
                                                     AdvImpressionEvent.validation_status == "VALID",
                                                     AdvImpressionEvent.event_type == "VIEWABLE",
                                                     AdvImpressionEvent.reversed_at.is_(None)))
            periods = {period_of(d) for (d,) in q.with_entities(AdvImpressionEvent.earning_day).distinct().all() if d}
            for p in periods - {fp for fp, s in finalized_periods if s == source}:
                for line in plan_lines(db, p, source, finalized=False):
                    if line["beneficiary_user_id"] == user_id and line["role"] == role.upper():
                        estimated += Decimal(str(line["amount"]))
        out[role] = {"estimated": str(floor2(estimated)), "held": str(held), "available": str(available),
                     "paid": str(paid), "adjustments_superseded": str(adjustments)}
    out["note"] = ("Estimates are not withdrawable. Earnings are released monthly after validation and, for AdSense, "
                   "after Google finalizes the month. Released earnings follow the usual wallet and cash-out rules.")
    return out


def member_lines(db: Session, user_id: int) -> list[dict]:
    rows = (db.query(AdvAllocation).filter(AdvAllocation.beneficiary_user_id == user_id)
            .order_by(AdvAllocation.period.desc(), AdvAllocation.id.desc()).limit(500).all())
    comm = {c.id: c for c in db.query(AffiliateCommission).filter(
        AffiliateCommission.id.in_([r.commission_id for r in rows if r.commission_id])).all()} if rows else {}
    return [{"id": r.id, "period": r.period, "role": r.role, "contest_entry_id": r.contestant_id,
             "original_submission_type": r.origin_kind, "contest_level": r.contest_level, "source": r.source,
             "applied_percentage": str((Decimal(str(r.rate)) * 100).quantize(Decimal("0.01"))),
             "eligible_revenue": str(Decimal(str(r.base_amount)).quantize(Decimal("0.0001"))),
             "amount": str(money(r.amount)), "status": r.status, "version": r.version,
             "payout_status": (comm[r.commission_id].status.value if r.commission_id in comm else None)}
            for r in rows]
