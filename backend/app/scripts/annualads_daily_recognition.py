"""
AnnualAds deferred sponsor revenue daily recognition (Entry B).

Run daily (e.g. 00:05 UTC):
  cd ~/mh5/backend
  source venv/bin/activate
  python -m app.scripts.annualads_daily_recognition

This script:
1) Finds Entry A journals created by the AnnualAds webhook:
     "AnnualAds sponsor payment received (deferred) tx:<hash>"
2) Posts missing daily recognition entries up to today (max 365 days):
     Dr 2310 Deferred Sponsor Revenue
     Cr 4010 Sponsor Advertising Revenue — Net
3) Is idempotent by deterministic description per tx/day.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.accounting import JournalEntry
from app.services.accounting_service import accounting_service

ENTRY_A_PREFIX = "AnnualAds sponsor payment received (deferred) tx:"
ENTRY_B_PREFIX = "AnnualAds daily recognition tx:"
MAX_RECOGNITION_DAYS = 365


def _extract_tx_hash(description: str) -> str:
    if ENTRY_A_PREFIX not in description:
        return ""
    return description.split(ENTRY_A_PREFIX, 1)[1].strip().lower()


def _round_cents(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def run_daily_recognition(db: Session) -> dict[str, int]:
    now = datetime.utcnow()
    entry_a_rows = (
        db.query(JournalEntry)
        .filter(JournalEntry.description.like(f"{ENTRY_A_PREFIX}%"))
        .all()
    )

    processed = 0
    created = 0
    skipped = 0

    for base_entry in entry_a_rows:
        tx_hash = _extract_tx_hash(base_entry.description or "")
        if not tx_hash:
            skipped += 1
            continue

        processed += 1
        base_amount = Decimal(str(base_entry.total_credit or 0))
        if base_amount <= 0:
            skipped += 1
            continue

        start_day = base_entry.entry_date.date()
        elapsed_days = (now.date() - start_day).days
        target_days = min(max(elapsed_days, 0), MAX_RECOGNITION_DAYS)
        if target_days <= 0:
            continue

        daily_amount = _round_cents(base_amount / Decimal(MAX_RECOGNITION_DAYS))
        recognized_total = Decimal("0.00")

        for day_number in range(1, target_days + 1):
            desc = f"{ENTRY_B_PREFIX}{tx_hash} day:{day_number}"
            existing = db.query(JournalEntry).filter(JournalEntry.description == desc).first()
            if existing:
                recognized_total += Decimal(str(existing.total_credit or 0))
                continue

            # Keep total recognized exactly equal to base amount by adjusting final day.
            amount_for_day = daily_amount
            if day_number == MAX_RECOGNITION_DAYS:
                amount_for_day = _round_cents(base_amount - recognized_total)
            if amount_for_day <= 0:
                continue

            recognition_date = datetime.combine(start_day + timedelta(days=day_number), datetime.min.time())
            accounting_service.create_journal_entry(
                db=db,
                description=desc,
                lines=[
                    {
                        "account_code": "2310",
                        "debit": float(amount_for_day),
                        "credit": 0.0,
                        "description": f"AnnualAds deferred release tx:{tx_hash} day:{day_number}",
                    },
                    {
                        "account_code": "4010",
                        "debit": 0.0,
                        "credit": float(amount_for_day),
                        "description": f"AnnualAds revenue recognition tx:{tx_hash} day:{day_number}",
                    },
                ],
                date=recognition_date,
                commit=True,
            )
            recognized_total += amount_for_day
            created += 1

    return {"processed_entry_a": processed, "created_entry_b": created, "skipped": skipped}


if __name__ == "__main__":
    session = SessionLocal()
    try:
        result = run_daily_recognition(session)
        print(result)
    finally:
        session.close()

