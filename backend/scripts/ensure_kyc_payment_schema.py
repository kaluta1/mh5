#!/usr/bin/env python3
"""Ensure the KYC + payment schema matches the models (idempotent, safe on prod).

The VPS systemd unit runs `uvicorn` directly and never applies Alembic
migrations, so the production database can drift and be missing columns that the
code reads. That makes read paths (e.g. "start KYC verification" -> get_by_user)
fail with a generic "Database error occurred" 503.

This script adds any missing columns / enum values used by the KYC and payment
flows. It is idempotent: it inspects the schema first and only issues DDL for
what is missing.

    cd backend
    .venv/bin/python scripts/ensure_kyc_payment_schema.py

Uses backend/.env via app.core.config. Requires the DB user to own the tables.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.core.config import settings  # noqa: E402


# table -> {column: DDL type/definition to ADD if missing}
COLUMNS: dict[str, dict[str, str]] = {
    "kyc_verifications": {
        "verified_first_name": "VARCHAR(100)",
        "verified_last_name": "VARCHAR(100)",
        "verified_date_of_birth": "TIMESTAMP",
        "verified_nationality": "VARCHAR(100)",
        "verified_address": "TEXT",
        "residential_address_locked_at": "TIMESTAMP",
        "identity_verified": "BOOLEAN NOT NULL DEFAULT false",
        "address_verified": "BOOLEAN NOT NULL DEFAULT false",
        "document_verified": "BOOLEAN NOT NULL DEFAULT false",
        "face_verified": "BOOLEAN NOT NULL DEFAULT false",
        "verification_url": "TEXT",
        "attempts_count": "INTEGER NOT NULL DEFAULT 0",
        "max_attempts": "INTEGER NOT NULL DEFAULT 3",
    },
    "users": {
        "identity_verified": "BOOLEAN NOT NULL DEFAULT false",
        "address_verified": "BOOLEAN NOT NULL DEFAULT false",
        "verification_date": "TIMESTAMP",
        "usdt_wallet_address": "VARCHAR(100)",
        "payout_currency": "VARCHAR(20) DEFAULT 'usdtbsc'",
    },
    "deposits": {
        "crypto_currency": "VARCHAR(20)",
        "crypto_amount": "NUMERIC(18, 8)",
        "payment_address": "VARCHAR(255)",
        "order_id": "VARCHAR(100)",
        "external_payment_id": "VARCHAR(255)",
        "tx_hash": "VARCHAR(255)",
        "from_address": "VARCHAR(255)",
        "admin_notes": "TEXT",
        "validated_by": "INTEGER",
    },
    "affiliate_commissions": {
        "payout_reference": "VARCHAR(255)",
    },
}

# enum type -> labels that must exist.
# NOTE: KYCVerification.status uses the default SQLEnum (no values_callable), so
# SQLAlchemy stores the enum *name* (e.g. PENDING_PROOF_OF_ADDRESS). Deposit.status
# uses values_callable, so it stores the *value* (lowercase). The labels below must
# match what SQLAlchemy actually sends for each column.
ENUM_VALUES: dict[str, list[str]] = {
    "kycstatus": ["PENDING_PROOF_OF_ADDRESS"],
    "depositstatus": ["partially_paid", "failed"],
    "verificationprovider": ["kaluta"],
}


def _existing_enum_labels(conn, enum_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname = :name
            """
        ),
        {"name": enum_name},
    ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    url = settings.DATABASE_URL
    if not url or url == "postgresql://user:password@localhost/myhigh5":
        print("DATABASE_URL missing in backend/.env", file=sys.stderr)
        return 1

    engine = create_engine(url)
    insp = inspect(engine)
    changed = 0

    # 1) Columns
    with engine.begin() as conn:
        for table, cols in COLUMNS.items():
            if not insp.has_table(table):
                print(f"- {table}: table missing, skipped")
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col in existing:
                    continue
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "{col}" {ddl}'))
                print(f"+ {table}.{col} ({ddl})")
                changed += 1

    # 2) Enum values (ADD VALUE cannot run inside a normal transaction on some
    #    PG setups; use an autocommit connection).
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        for enum_name, values in ENUM_VALUES.items():
            try:
                have = _existing_enum_labels(conn, enum_name)
            except Exception as exc:  # enum type may not exist
                print(f"- enum {enum_name}: {exc}")
                continue
            if not have:
                print(f"- enum {enum_name}: type not found, skipped")
                continue
            for value in values:
                if value in have:
                    continue
                conn.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'"))
                print(f"+ enum {enum_name} += '{value}'")
                changed += 1

    print(f"Done. {changed} change(s) applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
