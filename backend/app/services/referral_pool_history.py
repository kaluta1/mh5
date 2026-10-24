"""Multi-Unit Referral Pool, P9: classification of historical (single-seat) pool records and the
read-only conversion preview.

Pure functions over the redacted rows of the P9 read-only audit (CSV1 = pool/founding deposits,
CSV2 = memberships): no database access, nothing is written, nothing is converted. The same
rules are meant to drive a later, owner-approved conversion, so they are deterministic (sorted by
id) and every decision carries its reasons.

Groups (P9 brief):
  A  verified paid membership: a confirmed $100 provider payment, one seat, consistent ledger,
     at most one direct commission. Candidate for ONE unit; its revenue and commission already
     exist, so a conversion posts no revenue and no commission.
  B  founding or free membership (legacy Founding migration, admin grant): owner review, never
     an automatic paid unit.
  C  confirmed pool payment held in account 2100 with no seat: an owner decision per payment
     (convert, refund, or keep pending). A 2100 balance alone is never evidence enough.
  D  refunded or reversed: excluded.
  E  ambiguous or conflicting: manual review, nothing inferred.
  X  never paid (expired, pending, cancelled, rejected): not a membership, excluded.
F (historical assignments) is a property, not a group: every assignment is preserved as it is.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

A, B, C, D, E, X = "A_VERIFIED_PAID", "B_FOUNDING_OR_FREE", "C_HELD_IN_2100", "D_REFUNDED", "E_MANUAL_REVIEW", "X_NOT_PAID"
GROUPS = (A, B, C, D, E, X)
UNIT_PRICE = Decimal("100.00")
COMMISSION_RATE = Decimal("0.20")
POOL_PRODUCT = "referral_pool_entry"
FOUNDING_PRODUCTS = ("founding_membership", "mfm_membership")
SEAT_STATUSES = ("ACTIVE", "RESERVED", "CAPACITY_REVIEW")
UNPAID_DEPOSIT = ("pending", "expired", "rejected", "partially_paid")
REVERSED_DEPOSIT = ("failed",)
REVENUE_ACCOUNT, CASH_ACCOUNT, HOLD_ACCOUNT = "4008", "1001", "2100"


def _bool(value) -> bool:
    return str(value).strip().lower() in ("t", "true", "1", "yes")


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _money(value) -> Optional[Decimal]:
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def ledger(value: Optional[str]) -> dict:
    """'1001:100.00;2100:0.00;4008:-100.00' (debit minus credit per account) -> {code: Decimal}."""
    out: dict = {}
    for part in (value or "").split(";"):
        if ":" in part:
            code, amount = part.split(":", 1)
            parsed = _money(amount)
            if parsed is not None:
                out[code.strip()] = parsed
    return out


@dataclass
class Decision:
    kind: str                    # MEMBERSHIP or DEPOSIT
    record_id: int
    user_id: Optional[int]
    group: str
    reasons: list = field(default_factory=list)
    deposit_id: Optional[int] = None
    amount: Optional[str] = None
    assignments_to_preserve: int = 0
    unit_status_if_converted: Optional[str] = None     # ACTIVE or SUSPENDED (current eligibility)
    commission_exposure_if_converted: str = "0.00"


def _deposit_evidence(dep: dict) -> list:
    """Why a deposit is NOT clean payment evidence for one $100 pool seat (empty = clean)."""
    problems = []
    amount = _money(dep.get("amount"))
    if amount is None or amount != UNIT_PRICE:
        problems.append("AMOUNT_NOT_100")
    if str(dep.get("currency", "")).upper() != "USD":
        problems.append("CURRENCY_NOT_USD")
    if not (_bool(dep.get("has_provider_payment_id")) or _bool(dep.get("has_tx_hash"))):
        problems.append("NO_PROVIDER_EVIDENCE")
    if _bool(dep.get("admin_granted")):
        problems.append("ADMIN_GRANTED")
    if (_int(dep.get("same_provider_id_count")) or 0) > 1:
        problems.append("DUPLICATE_PROVIDER_PAYMENT_ID")
    if (_int(dep.get("commissions")) or 0) > 1:
        problems.append("MORE_THAN_ONE_COMMISSION")
    if str(dep.get("provider_env", "")).strip().lower() in ("test", "sandbox"):
        problems.append("TEST_ENVIRONMENT_PAYMENT")
    return problems


def _recognized(dep: dict) -> bool:
    """Cash in, revenue recognized, nothing left in 2100: what a seat paid before retirement looks like."""
    lines = ledger(dep.get("ledger_net_by_account"))
    return (lines.get(CASH_ACCOUNT) == UNIT_PRICE and lines.get(REVENUE_ACCOUNT) == -UNIT_PRICE
            and lines.get(HOLD_ACCOUNT, Decimal("0.00")) == Decimal("0.00"))


def _held(dep: dict) -> bool:
    lines = ledger(dep.get("ledger_net_by_account"))
    return (lines.get(CASH_ACCOUNT) == UNIT_PRICE and lines.get(HOLD_ACCOUNT) == -UNIT_PRICE
            and REVENUE_ACCOUNT not in lines)


def _eligible_now(m: dict) -> bool:
    return (_bool(m.get("account_ok")) and _bool(m.get("identity_verified"))
            and str(m.get("latest_kyc") or "").upper() == "APPROVED")


def classify(deposits: Iterable[dict], memberships: Iterable[dict]) -> list:
    """One decision per membership and one per pool/founding deposit no membership accounts for."""
    deps = {d_id: d for d in deposits if (d_id := _int(d.get("deposit_id"))) is not None}
    rows = sorted(memberships, key=lambda m: _int(m.get("membership_id")) or 0)
    per_user = Counter(_int(m.get("user_id")) for m in rows)
    per_deposit = Counter(_int(m.get("source_deposit_id")) for m in rows if _int(m.get("source_deposit_id")))
    decisions = []
    used_deposits = set()
    for m in rows:
        mid, uid, dep_id = _int(m.get("membership_id")), _int(m.get("user_id")), _int(m.get("source_deposit_id"))
        status, source = str(m.get("status") or "").upper(), str(m.get("entitlement_source") or "").upper()
        dep = deps.get(dep_id) if dep_id else None
        if dep_id:
            used_deposits.add(dep_id)
        decision = Decision("MEMBERSHIP", mid, uid, E, deposit_id=dep_id,
                            amount=str(_money(dep.get("amount"))) if dep else None,
                            assignments_to_preserve=max(_int(m.get("assignment_rows")) or 0, 0))
        reasons = decision.reasons
        if (_int(m.get("assignment_rows")) or 0) != (_int(m.get("assignments_count")) or 0):
            reasons.append("ASSIGNMENT_COUNTER_MISMATCH")
        dep_status = str(dep.get("deposit_status") or "").lower() if dep else ""
        if status in ("REFUNDED", "REVOKED") or (dep and (_bool(dep.get("refund_marker")) or dep_status in REVERSED_DEPOSIT)):
            decision.group = D
            reasons.append(f"MEMBERSHIP_{status}" if status in ("REFUNDED", "REVOKED") else "PAYMENT_REFUNDED_OR_REVERSED")
        elif source == "LEGACY_FOUNDING_MIGRATION" or (dep and dep.get("product") in FOUNDING_PRODUCTS):
            decision.group = B
            reasons.append("FOUNDING_MEMBERSHIP")
        elif source == "ADMIN_ADJUSTMENT" or (source != "PAID" and not dep_id):
            decision.group = B
            reasons.append("FREE_OR_ADMIN_GRANTED")
        elif status in ("EXPIRED", "CANCELLED", "RESERVED") and (not dep or dep_status in UNPAID_DEPOSIT):
            decision.group = X
            reasons.append(f"MEMBERSHIP_{status}_UNPAID")
        else:
            if not dep:
                reasons.append("PAYMENT_MISSING")
            else:
                if dep.get("product") != POOL_PRODUCT:
                    reasons.append("NOT_A_POOL_PRODUCT")
                if dep_status != "validated":
                    reasons.append(f"PAYMENT_{dep_status.upper() or 'UNKNOWN'}")
                reasons.extend(_deposit_evidence(dep))
                if not _recognized(dep):
                    reasons.append("LEDGER_NOT_RECOGNIZED_AS_REVENUE")
            if status not in SEAT_STATUSES:
                reasons.append(f"MEMBERSHIP_{status or 'UNKNOWN'}")
            if status == "CAPACITY_REVIEW":
                reasons.append("CAPACITY_REVIEW_SEAT")
            if per_user[uid] > 1:
                reasons.append("USER_HAS_SEVERAL_MEMBERSHIPS")
            if dep_id and per_deposit[dep_id] > 1:
                reasons.append("PAYMENT_BACKS_SEVERAL_MEMBERSHIPS")
            if not _bool(m.get("account_ok")):
                reasons.append("ACCOUNT_INACTIVE_OR_DELETED")
            blocking = [r for r in reasons if r != "ASSIGNMENT_COUNTER_MISMATCH"]
            if not blocking:
                decision.group = A
                decision.unit_status_if_converted = "ACTIVE" if _eligible_now(m) else "SUSPENDED"
            if "ASSIGNMENT_COUNTER_MISMATCH" in reasons and decision.group == A:
                decision.group = E            # the counter disagrees with the rows: look before converting
        decisions.append(decision)

    for dep_id in sorted(set(deps) - used_deposits):
        dep = deps[dep_id]
        status = str(dep.get("deposit_status") or "").lower()
        decision = Decision("DEPOSIT", dep_id, _int(dep.get("user_id")), E, deposit_id=dep_id,
                            amount=str(_money(dep.get("amount"))))
        reasons = decision.reasons
        if _bool(dep.get("refund_marker")) or status in REVERSED_DEPOSIT:
            decision.group = D
            reasons.append("PAYMENT_REFUNDED_OR_REVERSED")
        elif status in UNPAID_DEPOSIT or status == "":
            decision.group = X
            reasons.append(f"PAYMENT_{status.upper() or 'UNKNOWN'}")
        elif status != "validated":
            reasons.append(f"PAYMENT_{status.upper()}")
        elif dep.get("product") in FOUNDING_PRODUCTS:
            decision.group = B
            reasons.append("FOUNDING_PAYMENT_WITHOUT_MEMBERSHIP")
        else:
            reasons.extend(_deposit_evidence(dep))
            if (_int(dep.get("commissions")) or 0) > 0:
                reasons.append("COMMISSION_ALREADY_RECORDED")
            if _held(dep) and not reasons:
                decision.group = C
                reasons.append("CONFIRMED_PAYMENT_HELD_IN_2100")
                if _bool(dep.get("payer_has_sponsor")):
                    decision.commission_exposure_if_converted = str((UNIT_PRICE * COMMISSION_RATE).quantize(Decimal("0.01")))
            elif not reasons:
                reasons.append("LEDGER_NEITHER_HELD_NOR_RECOGNIZED")
        decisions.append(decision)
    return decisions


def preview(decisions: list) -> dict:
    """The dry-run summary and the owner approval table. Nothing here is executed."""
    by_group = {g: [d for d in decisions if d.group == g] for g in GROUPS}

    def total(items) -> str:
        return str(sum((_money(d.amount) or Decimal("0.00") for d in items), Decimal("0.00")))

    a, c = by_group[A], by_group[C]
    return {
        "counts": {g: len(items) for g, items in by_group.items()},
        "amounts": {g: total(items) for g, items in by_group.items()},
        "reasons": dict(sorted(Counter(r for d in decisions for r in d.reasons).items())),
        "conversion_candidates": {
            "memberships": len(a), "units": len(a),
            "units_active": sum(1 for d in a if d.unit_status_if_converted == "ACTIVE"),
            "units_suspended": sum(1 for d in a if d.unit_status_if_converted == "SUSPENDED"),
            "value": total(a),
            "new_revenue": "0.00", "new_commission": "0.00",       # already recognized and paid at purchase
        },
        "held_in_2100": {
            "payments": len(c), "value": total(c),
            "if_converted": {"revenue_dr2100_cr4008": total(c),
                             "commission_exposure": str(sum((Decimal(d.commission_exposure_if_converted) for d in c),
                                                            Decimal("0.00")))},
            "if_refunded": {"cash_out_dr2100_cr1001": total(c)},
        },
        "manual_review": len(by_group[B]) + len(by_group[E]),
        "excluded": len(by_group[D]) + len(by_group[X]),
        "assignments_to_preserve": sum(d.assignments_to_preserve for d in decisions),
        "expected_new_records_if_approved": {
            "referral_pool_units (source HISTORICAL_CONVERSION, one per group A membership)": len(a),
            "journal_entries": 0, "affiliate_commissions": 0, "assignment changes": 0,
        },
    }


def as_rows(decisions: list) -> list:
    return [{**asdict(d), "reasons": ";".join(d.reasons)} for d in decisions]
