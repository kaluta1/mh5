"""Automated recovery of the advertiser's direct-sponsor commission (owner-approved policy, 2026-11-05).

The commission is 20% (40% once qualified, existing rule) of a campaign day's RECOGNIZED revenue, decided once
per day (ad_workflow.decide_sponsor_commission). When part of that revenue is later reversed (invalid traffic,
a reversed lead or booked day), the entitlement is recalculated on what remains:

    entitlement = money(remaining recognized revenue x rate)        reduction = before - after

and the reduction is handled automatically, without rewriting any earlier record:

  A/B  the current commission row is unpaid and untouched (APPROVED, no payout reservation, nothing spent with
       the internal wallet): it is CANCELLED through its ledger reversal and, when something is left, a
       replacement row for the reduced amount is issued (source ADV_SPONSOR_ADJ / adjustment id).
  C    the commission is paid, reserved by a payout, or partly spent: nothing is taken from it. A receivable
       from the sponsor is recorded (Dr 1200 / Cr 5001) and recovered ONLY by offsetting that same sponsor's
       later advertiser-sponsor commissions (never another member, never below zero, never an external wallet).
       An offset is applied when a later day's commission is decided: the gross row is cancelled, a net row is
       issued, and Dr 5001 / Cr 1200 settles the receivable. What cannot be offset yet is carried forward.
  D    a genuinely inconsistent case (the decided commission is missing or was cancelled outside this flow, the
       revenue base is unknown, the sponsor no longer exists) goes to FINANCE_REVIEW. Routine reversals never do.

A sponsor whose commission was missed (KYC not approved at the event) has no commission: the retained-revenue
classification is reduced proportionally (Dr 4030 / Cr 4020) and the missed earning closed at zero.

Idempotency: one adjustment per reversal key (unique), one offset per (receivable, day) (unique), the campaign
day row is locked for every decision, the sponsor row before any receivable. Other commission programmes and
Referral Pool earnings are never read or changed here.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.advertising_v2 import (AdvCampaignDay, AdvSponsorAdjustment, AdvSponsorOffset,
                                       AdvSponsorReceivable)
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.user import User
from app.services.financial_integrity import money

ADJ_SOURCE = "ADV_SPONSOR_ADJ"          # replacement commission rows (source_id = adjustment id)
NET_SOURCE = "ADV_SPONSOR_NET"          # net rows after an offset (source_id = campaign day id)
OFFSET_POSTING = "SPONSOR_OFFSET"
RECEIVABLE_ACCOUNT = "1200"
RETAINED_REVENUE_ACCOUNT = "4030"
ZERO = Decimal("0.00")

RECORDED, ADJUSTED, REVERSED, REVIEW, MISSED = "RECORDED", "ADJUSTED", "REVERSED", "FINANCE_REVIEW", "MISSED_KYC"
ACTIVE_DAY_STATUSES = (RECORDED, ADJUSTED, MISSED)


def entitlement(base, rate) -> Decimal:
    """Same rounding as the commission engine (RevenueBreakdown.direct_commission)."""
    base, rate = money(base), Decimal(str(rate or 0))
    if base <= 0 or rate <= 0:
        return ZERO
    return money(base * rate)


def _expense_account():
    from app.services.new_model_revenue import COMMISSION_EXPENSE_ACCOUNT
    return COMMISSION_EXPENSE_ACCOUNT


def is_untouched(db: Session, c: Optional[AffiliateCommission]) -> bool:
    """Unpaid, not reserved by any payout and never used by the internal wallet: safe to cancel."""
    from app.services.commission_usage import wallet_used

    if c is None or c.status != CommissionStatus.APPROVED or c.payout_reference is not None:
        return False
    return wallet_used(db, [c.id]).get(int(c.id), ZERO) == 0


def _cancel(db: Session, c: AffiliateCommission, reason: str) -> None:
    """Cancel an untouched commission through its own ledger reversal (the row and journals are kept)."""
    from app.services.new_model_ledger import PostingType, is_reversed, reverse_entry
    from app.services.new_model_revenue import COMMISSION_EXPENSE_RECOGNITION, _commission_entry

    for posting in (COMMISSION_EXPENSE_RECOGNITION, PostingType.COMMISSION_ACCRUAL):
        entry = _commission_entry(db, c, posting)
        if entry is not None and not is_reversed(db, entry):
            reverse_entry(db, entry, reason=reason[:200])
    c.status = CommissionStatus.CANCELLED


def _issue(db: Session, like: AffiliateCommission, amount: Decimal, *, source_type: str, source_id: int,
           note: str) -> AffiliateCommission:
    """A commission row for `amount`, same sponsor, payer, type and rate as `like`; available at once."""
    from app.services.new_model_ledger import Line, PostingType, SourceType, post_entry

    row = AffiliateCommission(
        user_id=like.user_id, source_user_id=like.source_user_id, commission_type=like.commission_type, level=1,
        base_amount=like.base_amount, commission_rate=like.commission_rate, commission_amount=money(amount),
        status=CommissionStatus.APPROVED, transaction_date=datetime.utcnow(),
        business_model_version=like.business_model_version, revenue_category=like.revenue_category,
        source_type=source_type, source_id=int(source_id))
    db.add(row)
    db.flush()
    post_entry(db, source_type=SourceType.COMMISSION, source_id=row.id, posting_type=PostingType.COMMISSION_ACCRUAL,
               lines=[Line(_expense_account(), debit=money(amount), description="Direct affiliate commission expense"),
                      Line("2001", credit=money(amount),
                           description=f"Direct affiliate commission payable - User #{row.user_id}")],
               description=f"Direct affiliate commission #{row.id} ({source_type} {source_id}): {note[:120]}")
    from app.services.cashout_engine import request_cycle

    request_cycle()
    return row


# ---------------------------------------------------------------- reversal -> adjustment

def _day_sponsor(db: Session, day: AdvCampaignDay) -> Optional[int]:
    """The sponsor the day's commission was decided for: its original row (source ADV_CAMPAIGN_DAY / day id) is
    never deleted, even when it was cancelled by an offset or a reversal and the day's pointer was cleared."""
    from app.services.ad_workflow import SPONSOR_SOURCE

    row = (db.query(AffiliateCommission.user_id)
           .filter(AffiliateCommission.source_type == SPONSOR_SOURCE, AffiliateCommission.source_id == day.id)
           .order_by(AffiliateCommission.id.asc()).first())
    return int(row[0]) if row is not None else None



def on_revenue_reversed(db: Session, day: AdvCampaignDay, *, reversed_amount, key: str, reason: str) -> Optional[str]:
    """The caller holds the campaign and day locks. Returns the adjustment method (or None when the day has
    no sponsor commission decision). Idempotent per `key`."""
    from app.services.new_model_ledger import Line, PostingType, post_entry

    status = day.sponsor_commission_status
    if status not in ACTIVE_DAY_STATUSES and status != REVIEW:
        return None
    full_key = f"day:{day.id}:{key}"[:160]
    done = db.query(AdvSponsorAdjustment).filter(AdvSponsorAdjustment.idempotency_key == full_key).first()
    if done is not None:
        return done.method
    now = datetime.utcnow()
    commission = db.get(AffiliateCommission, day.sponsor_commission_id) if day.sponsor_commission_id else None
    rate = Decimal(str(day.sponsor_rate or (commission.commission_rate if commission is not None else 0) or 0))
    base = day.sponsor_base_amount
    if base is None and commission is not None and commission.base_amount is not None:
        base = commission.base_amount                       # decided before a2c4e6f8b0d3
    sponsor_id = commission.user_id if commission is not None else _day_sponsor(db, day)
    if sponsor_id is None and status == MISSED:
        from app.models.missed_earning import CATEGORY_REFERRAL, MissedEarning
        from app.services.ad_workflow import SPONSOR_SOURCE

        m = (db.query(MissedEarning).filter(MissedEarning.source_type == SPONSOR_SOURCE,
                                            MissedEarning.source_id == day.id,
                                            MissedEarning.category == CATEGORY_REFERRAL).first())
        sponsor_id = m.user_id if m is not None else None
        if base is None and m is not None and m.base_amount is not None:
            base = m.base_amount
    reversed_before = money(day.sponsor_reversed_amount or 0)
    remaining_before = money(Decimal(str(base)) - reversed_before) if base is not None else ZERO
    rev = min(money(reversed_amount), max(remaining_before, ZERO))
    remaining_after = money(remaining_before - rev)
    e_before, e_after = entitlement(remaining_before, rate), entitlement(remaining_after, rate)
    reduction = money(e_before - e_after)
    adj = AdvSponsorAdjustment(idempotency_key=full_key, campaign_day_id=day.id, campaign_id=day.campaign_id,
                               sponsor_user_id=sponsor_id, original_commission_id=commission.id if commission else None,
                               reversed_revenue=rev, base_before=remaining_before, base_after=remaining_after,
                               rate=rate, entitlement_before=e_before, entitlement_after=e_after,
                               reduction=reduction, method="NONE", reason=(reason or "")[:200])
    db.add(adj)
    db.flush()
    day.sponsor_reversed_amount = money(reversed_before + rev)

    # Case D: nothing consistent to adjust against.
    unknown = base is None or (status != MISSED and commission is None and money(day.sponsor_offset_amount or 0) <= 0)
    foreign = commission is not None and sponsor_id is not None and int(commission.user_id) != int(sponsor_id)
    cancelled_elsewhere = commission is not None and commission.status == CommissionStatus.CANCELLED
    if status == REVIEW or unknown or foreign or cancelled_elsewhere:
        adj.method = "FINANCE_REVIEW"
        day.sponsor_commission_status = REVIEW
        return adj.method
    if reduction <= 0:
        return adj.method                                    # e.g. a reversal smaller than a cent of commission

    if status == MISSED:
        _reduce_missed(db, day, adj, sponsor_id, reduction, zero=e_after <= 0)
        adj.method = "MISSED_ADJUSTED"
        day.sponsor_commission_amount = e_after
        return adj.method

    # The sponsor row is locked before the commission and receivables (same order as accrual and cash-out).
    db.query(User).filter(User.id == sponsor_id).with_for_update().first()
    if commission is not None:
        commission = (db.query(AffiliateCommission).filter(AffiliateCommission.id == commission.id)
                      .with_for_update().one())
    take = min(reduction, money(commission.commission_amount)) if is_untouched(db, commission) else ZERO
    rest = money(reduction - take)
    if take > 0:
        left = money(Decimal(str(commission.commission_amount)) - take)
        _cancel(db, commission, f"Advertising revenue reversed: {reason}")
        if left > 0:
            replacement = _issue(db, commission, left, source_type=ADJ_SOURCE, source_id=adj.id,
                                 note=f"reduced after reversal of campaign day {day.id}")
            adj.replacement_commission_id = day.sponsor_commission_id = replacement.id
            adj.method = "REISSUED"
        else:
            day.sponsor_commission_id = None
            adj.method = "CANCELLED"
    if rest > 0:
        entry = post_entry(db, source_type=ADJ_SOURCE, source_id=adj.id, posting_type=PostingType.REVERSAL,
                           key_suffix="receivable",
                           lines=[Line(RECEIVABLE_ACCOUNT, debit=rest,
                                       description=f"Receivable - advertiser-sponsor commission recovery - "
                                                   f"User #{sponsor_id}"),
                                  Line(_expense_account(), credit=rest, description="Reverse direct commission cost")],
                           description=f"Advertiser-sponsor commission recovery receivable (adjustment {adj.id}, "
                                       f"campaign day {day.id})")
        sponsor = db.get(User, sponsor_id)
        gone = sponsor is None or sponsor.is_deleted is True
        db.add(AdvSponsorReceivable(sponsor_user_id=sponsor_id, adjustment_id=adj.id, campaign_day_id=day.id,
                                    original_commission_id=commission.id if commission else None, amount=rest,
                                    recovered=ZERO, status="FINANCE_REVIEW" if gone else "OPEN",
                                    journal_entry_id=entry.id, updated_at=now,
                                    note="Sponsor account no longer exists" if gone else None))
        adj.method = "RECEIVABLE"
    day.sponsor_commission_amount = e_after
    day.sponsor_commission_status = REVERSED if e_after <= 0 else ADJUSTED
    db.flush()
    return adj.method


def _reduce_missed(db: Session, day: AdvCampaignDay, adj: AdvSponsorAdjustment, sponsor_id, reduction: Decimal,
                   *, zero: bool) -> None:
    """Missed (KYC) commission: shrink the retained-revenue classification by the reduction (Dr 4030 / Cr 4020)."""
    from app.models.missed_earning import STATUS_RECORDED, STATUS_REVERSED, MissedEarning
    from app.services import ad_campaigns as camp
    from app.services.ad_workflow import SPONSOR_SOURCE
    from app.services.new_model_ledger import Line, PostingType, post_entry

    m = (db.query(MissedEarning).filter(MissedEarning.source_type == SPONSOR_SOURCE, MissedEarning.source_id == day.id,
                                        MissedEarning.status == STATUS_RECORDED).with_for_update().first())
    if m is not None and m.journal_entry_id:
        post_entry(db, source_type=ADJ_SOURCE, source_id=adj.id, posting_type=PostingType.REVERSAL,
                   key_suffix="missed",
                   lines=[Line(RETAINED_REVENUE_ACCOUNT, debit=reduction,
                               description=f"Retained revenue reduced - member #{sponsor_id} (revenue reversed)"),
                          Line(m.revenue_account or camp.ORDINARY_REVENUE_ACCOUNT, credit=reduction,
                               description="Reclassify back: advertising revenue reversed")],
                   description=f"Missed advertiser-sponsor commission reduced (adjustment {adj.id})")
    if m is not None and zero:
        m.status = STATUS_REVERSED
    if zero:
        day.sponsor_commission_status = REVERSED
    db.flush()


# ---------------------------------------------------------------- offset against later commissions

def outstanding(db: Session, sponsor_id: int) -> Decimal:
    rows = (db.query(AdvSponsorReceivable).filter(AdvSponsorReceivable.sponsor_user_id == int(sponsor_id),
                                                  AdvSponsorReceivable.status == "OPEN").all())
    return money(sum((Decimal(str(r.amount)) - Decimal(str(r.recovered)) for r in rows), ZERO))


def offset_new_commission(db: Session, day: AdvCampaignDay, commission: AffiliateCommission) -> Decimal:
    """Called right after a day's commission was recorded (same transaction, sponsor row locked by the accrual):
    recover the sponsor's OPEN receivables, oldest first, from it. Returns the amount offset."""
    from app.services.new_model_ledger import Line, post_entry

    if commission is None or not is_untouched(db, commission):
        return ZERO
    db.query(User).filter(User.id == commission.user_id).with_for_update().first()
    open_rows = (db.query(AdvSponsorReceivable)
                 .filter(AdvSponsorReceivable.sponsor_user_id == commission.user_id,
                         AdvSponsorReceivable.status == "OPEN")
                 .order_by(AdvSponsorReceivable.id.asc()).with_for_update().all())
    available = money(commission.commission_amount)
    plan = []
    for r in open_rows:
        if available <= 0:
            break
        if db.query(AdvSponsorOffset.id).filter(AdvSponsorOffset.receivable_id == r.id,
                                                AdvSponsorOffset.campaign_day_id == day.id).first():
            continue
        due = money(Decimal(str(r.amount)) - Decimal(str(r.recovered)))
        part = min(due, available)
        if part > 0:
            plan.append((r, part))
            available = money(available - part)
    total = money(sum((p for _, p in plan), ZERO))
    if total <= 0:
        return ZERO
    _cancel(db, commission, f"Offset against advertiser-sponsor recovery receivable(s) - campaign day {day.id}")
    net = money(Decimal(str(commission.commission_amount)) - total)
    net_row = _issue(db, commission, net, source_type=NET_SOURCE, source_id=day.id,
                     note=f"net of {total} recovered") if net > 0 else None
    entry = post_entry(db, source_type=NET_SOURCE, source_id=day.id, posting_type=OFFSET_POSTING,
                       lines=[Line(_expense_account(), debit=total,
                                   description=f"Commission earned, applied to recovery - User #{commission.user_id}"),
                              Line(RECEIVABLE_ACCOUNT, credit=total,
                                   description=f"Recovery receivable offset - User #{commission.user_id}")],
                       description=f"Advertiser-sponsor recovery offset from campaign day {day.id}")
    now = datetime.utcnow()
    for r, part in plan:
        db.add(AdvSponsorOffset(receivable_id=r.id, campaign_day_id=day.id, sponsor_user_id=commission.user_id,
                                gross_commission_id=commission.id, net_commission_id=net_row.id if net_row else None,
                                amount=part, journal_entry_id=entry.id))
        r.recovered = money(Decimal(str(r.recovered)) + part)
        r.updated_at = now
        if money(r.recovered) >= money(r.amount):
            r.status = "RECOVERED"
    day.sponsor_commission_id = net_row.id if net_row else None
    day.sponsor_offset_amount = money(Decimal(str(day.sponsor_offset_amount or 0)) + total)
    db.flush()
    return total


# ---------------------------------------------------------------- finance review (Case D only)

def resolve_receivable(db: Session, receivable_id: int, *, action: str, actor_id: int, note: str) -> AdvSponsorReceivable:
    """FINANCE_REVIEW -> OPEN (recover by offset) or WRITTEN_OFF (Dr 5001 / Cr 1200 for what is left). Audited."""
    from app.models.accounting import AuditTrail
    from app.services.new_model_ledger import Line, PostingType, post_entry

    if action not in ("OPEN", "WRITTEN_OFF") or len((note or "").strip()) < 3:
        raise ValueError("action must be OPEN or WRITTEN_OFF, with a note")
    r = db.query(AdvSponsorReceivable).filter(AdvSponsorReceivable.id == receivable_id).with_for_update().one()
    if r.status not in ("FINANCE_REVIEW", "OPEN"):
        raise ValueError(f"Receivable is {r.status}")
    old = r.status
    left = money(Decimal(str(r.amount)) - Decimal(str(r.recovered)))
    if action == "WRITTEN_OFF" and left > 0:
        post_entry(db, source_type=ADJ_SOURCE, source_id=r.adjustment_id, posting_type=PostingType.REVERSAL,
                   key_suffix="write-off",
                   lines=[Line(_expense_account(), debit=left, description="Recovery receivable written off"),
                          Line(RECEIVABLE_ACCOUNT, credit=left,
                               description=f"Receivable written off - User #{r.sponsor_user_id}")],
                   description=f"Advertiser-sponsor recovery receivable {r.id} written off: {note[:120]}")
    r.status, r.updated_at, r.note = action, datetime.utcnow(), note.strip()[:300]
    db.add(AuditTrail(table_name="adv_sponsor_receivables", record_id=r.id, action=f"RESOLVE_{action}",
                      old_values={"status": old}, new_values={"status": action, "note": note.strip()[:200]},
                      user_id=actor_id))
    db.flush()
    return r


def reconciliation(db: Session) -> dict:
    """Read-only invariants: receivables never over-recovered, offsets add up to what was recovered."""
    from sqlalchemy import func

    over = db.query(func.count(AdvSponsorReceivable.id)).filter(
        AdvSponsorReceivable.recovered > AdvSponsorReceivable.amount).scalar() or 0
    rec = {int(i): money(v) for i, v in db.query(AdvSponsorReceivable.id, AdvSponsorReceivable.recovered).all()}
    off = {int(i): money(v) for i, v in db.query(AdvSponsorOffset.receivable_id, func.sum(AdvSponsorOffset.amount))
           .group_by(AdvSponsorOffset.receivable_id).all()}
    mismatched = sorted(i for i in set(rec) | set(off) if rec.get(i, ZERO) != off.get(i, ZERO))
    totals = dict(db.query(AdvSponsorReceivable.status, func.coalesce(func.sum(AdvSponsorReceivable.amount
                                                                             - AdvSponsorReceivable.recovered), 0))
                  .group_by(AdvSponsorReceivable.status).all())
    return {"over_recovered": int(over), "offset_mismatch_receivables": mismatched,
            "outstanding_by_status": {k: str(money(v)) for k, v in totals.items()},
            "ok": not over and not mismatched}
