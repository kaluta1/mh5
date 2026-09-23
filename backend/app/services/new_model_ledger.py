"""NEW_V2 business-model versioning and structured, idempotent journal posting.

Financial identity is always (source_type, source_id, posting_type) plus a unique
idempotency key -- never text matching on descriptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.business_model import BusinessModelVersion
from app.services.accounting_service import AccountingError, accounting_service
from app.services.financial_integrity import money
from app.services.new_model_reference_data import LEGACY_MODEL_VERSION, NEW_MODEL_VERSION


class SourceType:
    DEPOSIT = "DEPOSIT"
    COMMISSION = "COMMISSION"
    LEADERS_PERIOD = "LEADERS_PERIOD"
    MARKET_ORDER = "MARKET_ORDER"


class PostingType:
    RECEIPT = "RECEIPT"
    RECOGNITION = "RECOGNITION"
    COMMISSION_ACCRUAL = "COMMISSION_ACCRUAL"
    LEADERS_ALLOCATION = "LEADERS_ALLOCATION"
    CUSTODY_FUNDED = "CUSTODY_FUNDED"
    CUSTODY_RELEASED = "CUSTODY_RELEASED"
    MARKUP_SETTLED = "MARKUP_SETTLED"
    REVERSAL = "REVERSAL"


# ---------------------------------------------------------------- versioning

def active_new_model_version(db: Session, at: Optional[datetime] = None) -> Optional[BusinessModelVersion]:
    """The NEW_V2 row when it exists and is effective at ``at`` (UTC, naive)."""
    at = at or datetime.utcnow()
    row = db.query(BusinessModelVersion).filter(BusinessModelVersion.version == NEW_MODEL_VERSION).first()
    if row and row.effective_at <= at:
        return row
    return None


def model_version_for_new_event(db: Session, at: Optional[datetime] = None) -> str:
    """Version to stamp on a financial source created now. Deterministic: stored cutover row."""
    return NEW_MODEL_VERSION if active_new_model_version(db, at) else LEGACY_MODEL_VERSION


def is_new_model(stamp: Optional[str]) -> bool:
    """Unstamped rows predate the cutover by construction and are LEGACY."""
    return stamp == NEW_MODEL_VERSION


# ---------------------------------------------------------------- posting

@dataclass(frozen=True)
class Line:
    account_code: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str = ""


def idempotency_key(source_type: str, source_id: int, posting_type: str, suffix: str = "") -> str:
    key = f"{NEW_MODEL_VERSION}:{source_type}:{int(source_id)}:{posting_type}"
    return f"{key}:{suffix}" if suffix else key


def find_entry(db: Session, key: str) -> Optional[JournalEntry]:
    return db.query(JournalEntry).filter(JournalEntry.idempotency_key == key).first()


def post_entry(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    posting_type: str,
    lines: Iterable[Line],
    description: str,
    entry_date: Optional[datetime] = None,
    key_suffix: str = "",
    reverses_entry_id: Optional[int] = None,
) -> JournalEntry:
    """Insert-or-get a balanced NEW_V2 journal. Zero lines are dropped. Never commits."""
    key = idempotency_key(source_type, source_id, posting_type, key_suffix)
    existing = find_entry(db, key)
    if existing is not None:
        return existing
    payload = [
        {"account_code": l.account_code, "debit": money(l.debit), "credit": money(l.credit), "description": l.description}
        for l in lines
        if money(l.debit) != 0 or money(l.credit) != 0
    ]
    if not payload:
        raise AccountingError(f"Nothing to post for {key}")
    entry = accounting_service.create_journal_entry(
        db, description=description, lines=payload, date=entry_date or datetime.utcnow(), commit=False
    )
    entry.business_model_version = NEW_MODEL_VERSION
    entry.source_type = source_type
    entry.source_id = int(source_id)
    entry.posting_type = posting_type
    entry.idempotency_key = key
    entry.reverses_entry_id = reverses_entry_id
    db.flush()
    return entry


def reverse_entry(db: Session, original: JournalEntry, *, reason: str) -> JournalEntry:
    """Mirror an exact original entry (found by id/FK), once."""
    if original.reverses_entry_id is not None:
        raise AccountingError("A reversal entry cannot itself be reversed")
    rows = (
        db.query(ChartOfAccounts.account_code, JournalLine)
        .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
        .filter(JournalLine.entry_id == original.id)
        .all()
    )
    lines = [
        Line(code, debit=money(line.credit_amount), credit=money(line.debit_amount), description=f"Reverse {original.entry_number}")
        for code, line in rows
    ]
    return post_entry(
        db,
        source_type=original.source_type or "JOURNAL",
        source_id=original.source_id if original.source_id is not None else original.id,
        posting_type=PostingType.REVERSAL,
        key_suffix=f"of:{original.id}",
        lines=lines,
        description=f"Reversal of {original.entry_number}: {reason}",
        reverses_entry_id=original.id,
    )


def entries_for_source(db: Session, source_type: str, source_id: int) -> list[JournalEntry]:
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == source_type, JournalEntry.source_id == int(source_id))
        .order_by(JournalEntry.id.asc())
        .all()
    )


def is_reversed(db: Session, entry: JournalEntry) -> bool:
    return db.query(JournalEntry.id).filter(JournalEntry.reverses_entry_id == entry.id).first() is not None
