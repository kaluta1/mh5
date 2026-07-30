"""Admin transaction list + CSV export (deposits + user ledger)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.payment import Deposit, DepositStatus
from app.models.transaction import TransactionStatus, TransactionType, UserTransaction


def _deposit_to_row(deposit) -> dict[str, Any]:
    return {
        "record_source": "deposit",
        "id": deposit.id,
        "type": "deposit",
        "amount": float(deposit.amount),
        "currency": deposit.currency or "",
        "status": deposit.status.value if deposit.status else "",
        "description": f"Dépôt - {deposit.product_type.name if deposit.product_type else 'N/A'}",
        "reference": deposit.order_id,
        "created_at": deposit.created_at.isoformat() if deposit.created_at else None,
        "processed_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
        "user_id": deposit.user.id if deposit.user else None,
        "user_username": deposit.user.username if deposit.user else None,
        "user_email": deposit.user.email if deposit.user else None,
        "user_full_name": deposit.user.full_name if deposit.user else None,
        "user_avatar_url": deposit.user.avatar_url if deposit.user else None,
        "contest_id": None,
        "contest_name": None,
        "payment_method": deposit.payment_method.name if deposit.payment_method else None,
        "product_type": deposit.product_type.name if deposit.product_type else None,
        "order_id": deposit.order_id,
        "external_payment_id": deposit.external_payment_id,
        "tx_hash": deposit.tx_hash,
        "validated_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
        "validated_by": deposit.validated_by,
    }


def _user_transaction_to_row(transaction) -> dict[str, Any]:
    return {
        "record_source": "user_transaction",
        "id": transaction.id,
        "type": transaction.transaction_type.value,
        "amount": float(transaction.amount),
        "currency": transaction.currency or "",
        "status": transaction.status.value if transaction.status else "",
        "description": transaction.description,
        "reference": transaction.reference,
        "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
        "processed_at": transaction.processed_at.isoformat() if transaction.processed_at else None,
        "user_id": transaction.user.id if transaction.user else None,
        "user_username": transaction.user.username if transaction.user else None,
        "user_email": transaction.user.email if transaction.user else None,
        "user_full_name": transaction.user.full_name if transaction.user else None,
        "user_avatar_url": transaction.user.avatar_url if transaction.user else None,
        "contest_id": transaction.contest.id if transaction.contest else None,
        "contest_name": transaction.contest.name if transaction.contest else None,
        "payment_method": transaction.payment_method,
        "product_type": None,
        "order_id": None,
        "external_payment_id": transaction.payment_reference,
        "tx_hash": None,
        "validated_at": None,
        "validated_by": None,
    }


def _row_for_api(row: dict[str, Any]) -> dict[str, Any]:
    """Shape expected by TransactionEnriched response model."""
    user = None
    if row.get("user_id"):
        user = {
            "id": row["user_id"],
            "username": row.get("user_username"),
            "email": row.get("user_email"),
            "full_name": row.get("user_full_name"),
            "avatar_url": row.get("user_avatar_url"),
        }
    contest = None
    if row.get("contest_id"):
        contest = {"id": row["contest_id"], "name": row.get("contest_name")}
    return {
        "id": row["id"],
        "type": row["type"],
        "amount": row["amount"],
        "currency": row["currency"],
        "status": row["status"],
        "description": row.get("description"),
        "reference": row.get("reference"),
        "created_at": row.get("created_at"),
        "processed_at": row.get("processed_at"),
        "user": user,
        "contest": contest,
        "payment_method": row.get("payment_method"),
        "product_type": row.get("product_type"),
        "order_id": row.get("order_id"),
        "external_payment_id": row.get("external_payment_id"),
        "tx_hash": row.get("tx_hash"),
        "validated_at": row.get("validated_at"),
        "validated_by": row.get("validated_by"),
    }


def fetch_admin_transactions(
    db: Session,
    *,
    transaction_type: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = 0,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Merge deposits + user transactions, newest first."""
    from app.models.user import User as UserModel

    rows: list[dict[str, Any]] = []
    include_deposits = transaction_type is None or transaction_type == "deposit"

    if include_deposits:
        deposits_query = db.query(Deposit).options(
            joinedload(Deposit.user),
            joinedload(Deposit.product_type),
            joinedload(Deposit.payment_method),
        )
        if status:
            try:
                deposits_query = deposits_query.filter(
                    Deposit.status == DepositStatus(status)
                )
            except ValueError:
                pass
        if user_id:
            deposits_query = deposits_query.filter(Deposit.user_id == user_id)
        if date_from:
            deposits_query = deposits_query.filter(
                func.date(Deposit.created_at) >= date_from
            )
        if date_to:
            deposits_query = deposits_query.filter(
                func.date(Deposit.created_at) <= date_to
            )
        if search:
            search_term = f"%{search.lower()}%"
            deposits_query = deposits_query.join(UserModel).filter(
                or_(
                    func.lower(Deposit.order_id).like(search_term),
                    func.lower(Deposit.external_payment_id).like(search_term),
                    func.lower(UserModel.email).like(search_term),
                    func.lower(UserModel.username).like(search_term),
                )
            )
        for deposit in deposits_query.order_by(Deposit.created_at.desc()).all():
            rows.append(_deposit_to_row(deposit))

    include_user_tx = transaction_type is None or transaction_type != "deposit"
    if include_user_tx:
        transactions_query = db.query(UserTransaction).options(
            joinedload(UserTransaction.user),
            joinedload(UserTransaction.contest),
        )
        if transaction_type:
            try:
                transactions_query = transactions_query.filter(
                    UserTransaction.transaction_type
                    == TransactionType(transaction_type)
                )
            except ValueError:
                pass
        elif transaction_type is None:
            transactions_query = transactions_query.filter(
                UserTransaction.transaction_type != TransactionType.DEPOSIT
            )
        if status:
            try:
                transactions_query = transactions_query.filter(
                    UserTransaction.status == TransactionStatus(status)
                )
            except ValueError:
                pass
        if user_id:
            transactions_query = transactions_query.filter(
                UserTransaction.user_id == user_id
            )
        if date_from:
            transactions_query = transactions_query.filter(
                func.date(UserTransaction.created_at) >= date_from
            )
        if date_to:
            transactions_query = transactions_query.filter(
                func.date(UserTransaction.created_at) <= date_to
            )
        if search:
            search_term = f"%{search.lower()}%"
            transactions_query = transactions_query.join(UserModel).filter(
                or_(
                    func.lower(UserTransaction.reference).like(search_term),
                    func.lower(UserTransaction.description).like(search_term),
                    func.lower(UserModel.email).like(search_term),
                    func.lower(UserModel.username).like(search_term),
                )
            )
        for transaction in transactions_query.order_by(
            UserTransaction.created_at.desc()
        ).all():
            rows.append(_user_transaction_to_row(transaction))

    rows.sort(key=lambda x: x.get("created_at") or "1970-01-01T00:00:00", reverse=True)
    if limit is None:
        return rows[skip:]
    return rows[skip : skip + limit]


CSV_COLUMNS = [
    ("record_source", "Source"),
    ("id", "ID"),
    ("type", "Type"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("status", "Status"),
    ("description", "Description"),
    ("reference", "Reference"),
    ("user_id", "User ID"),
    ("user_email", "User Email"),
    ("user_username", "Username"),
    ("user_full_name", "Full Name"),
    ("contest_id", "Contest ID"),
    ("contest_name", "Contest"),
    ("payment_method", "Payment Method"),
    ("product_type", "Product Type"),
    ("order_id", "Order ID"),
    ("external_payment_id", "External Payment ID"),
    ("tx_hash", "Tx Hash"),
    ("created_at", "Created At"),
    ("processed_at", "Processed At"),
    ("validated_at", "Validated At"),
    ("validated_by", "Validated By"),
]


def admin_transactions_to_csv(rows: list[dict[str, Any]]) -> str:
    """UTF-8 CSV with BOM for Excel."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for row in rows:
        writer.writerow([row.get(key, "") or "" for key, _ in CSV_COLUMNS])
    return "\ufeff" + buffer.getvalue()


def export_filename(as_of: Optional[datetime] = None) -> str:
    day = (as_of or datetime.utcnow()).strftime("%Y-%m-%d")
    return f"myhigh5-transactions-{day}.csv"
