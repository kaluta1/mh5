"""Print the SoncoPay payment/payout readiness and the SoncoPay payment reconciliation as JSON.

READ-ONLY. Every transaction of the session is opened READ ONLY by PostgreSQL itself
(postgresql_readonly), and is rolled back. Nothing is
created or changed at MyHigh5 or at SoncoPay. With --provider, SoncoPay is asked only through its
documented read-only calls (GET /v1/methods, GET /v1/balances).

    python scripts/soncopay_readiness_readonly.py [--provider]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", action="store_true", help="also read SoncoPay (read-only calls)")
    args = parser.parse_args()

    from sqlalchemy.orm import Session

    from app.db.session import engine
    import app.models  # noqa: F401  (model registry)
    from app.services import soncopay_readiness

    # Every transaction (readiness() rolls back between steps) is READ ONLY at the database.
    db = Session(bind=engine.execution_options(postgresql_readonly=True), autoflush=False)
    try:
        report = asyncio.run(soncopay_readiness.readiness(db, read_provider=args.provider))
        print(json.dumps(report, indent=2, default=str))
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
