#!/usr/bin/env python3
"""Diagnose login 503 — find missing DB columns or connection issues.

Run on VPS:
    cd /root/mh5/backend
    .venv/bin/python scripts/diagnose_login_db.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User


def main() -> int:
    url = settings.DATABASE_URL
    if not url:
        print("ERROR: DATABASE_URL not set in backend/.env")
        return 1

    # Mask password in output
    safe = url.split("@")[-1] if "@" in url else "(local)"
    print(f"DATABASE_URL host/db: ...@{safe}")
    print(f"KYC_PROVIDER: {getattr(settings, 'KYC_PROVIDER', '?')}")
    print()

    engine = create_engine(url, connect_args={"connect_timeout": 10})

    # 1) Connection
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT current_user, current_database()")).fetchone()
            print(f"Connected as: {row[0]} @ {row[1]}")
    except Exception as exc:
        print(f"CONNECTION FAILED: {exc}")
        return 1

    # 2) users columns vs SQLAlchemy model
    insp = inspect(engine)
    if not insp.has_table("users"):
        print("ERROR: table 'users' does not exist")
        return 1

    db_cols = {c["name"] for c in insp.get_columns("users")}
    model_cols = {c.key for c in User.__table__.columns}
    missing = sorted(model_cols - db_cols)
    extra = sorted(db_cols - model_cols)

    print(f"\nusers columns in DB: {len(db_cols)}")
    print(f"users columns in model: {len(model_cols)}")
    if missing:
        print("\n*** MISSING COLUMNS (cause login 503) ***")
        for col in missing:
            print(f"  - {col}")
    else:
        print("\nOK: all User model columns exist in DB")

    if extra:
        print(f"\nExtra DB columns (harmless): {', '.join(extra[:10])}{'...' if len(extra) > 10 else ''}")

    # 3) ORM login-style query
    print("\nTrying ORM: SELECT one user by email...")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = db.query(User).filter(User.is_deleted == False).first()  # noqa: E712
        if user:
            print(f"OK: loaded user id={user.id} email={user.email}")
        else:
            print("OK: query ran (no users in table)")
    except Exception as exc:
        print(f"ORM QUERY FAILED: {type(exc).__name__}: {exc}")
        print("\nFix: run backend/scripts/neon_manual_migrations.sql in Neon SQL Editor")
        return 1
    finally:
        db.close()

    # 4) alembic version
    try:
        with engine.connect() as conn:
            if insp.has_table("alembic_version"):
                ver = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
                print(f"\nalembic_version: {ver}")
            else:
                print("\nalembic_version table: missing")
    except Exception as exc:
        print(f"\nalembic_version check: {exc}")

    print("\nIf missing columns listed above, run neon_manual_migrations.sql in Neon.")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
