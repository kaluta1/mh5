#!/usr/bin/env python3
"""Prompt 6 read-only reconciliation: Annual Ads (purchases, sponsor commissions, refunds), Referral Pool
(purchases, units, assignments, slots, unit ledger), DSM (identity and sponsor mapping) and the ledger.

READ ONLY: the session is opened with a PostgreSQL READ ONLY transaction, so nothing can be written even by
mistake. Prints JSON (ids and counts only; no e-mails or names). Prints the database host and name first.

    python scripts/reconciliation_readonly.py                 # every section
    python scripts/reconciliation_readonly.py --only pool dsm # some sections
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECTIONS = ("annual_ads", "pool", "dsm", "ledger")


def ledger(db) -> dict:
    from decimal import Decimal

    from sqlalchemy import func

    from app.models.accounting import ChartOfAccounts, JournalLine

    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
    clearing = (db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0) - func.coalesce(func.sum(JournalLine.credit_amount), 0))
                .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
                .filter(ChartOfAccounts.account_code == "1050").scalar())
    lines = db.query(func.count(JournalLine.id)).scalar()
    return {"lines": int(lines or 0), "debits": str(Decimal(str(d))), "credits": str(Decimal(str(c))),
            "balanced": Decimal(str(d)) == Decimal(str(c)), "internal_wallet_clearing_1050": str(clearing or 0)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", choices=SECTIONS, default=list(SECTIONS))
    args = parser.parse_args(argv)

    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401  (every mapper)
    from app.core.config import settings
    from app.db.session import engine

    url = make_url(settings.DATABASE_URL)
    print(json.dumps({"database": f"{url.host}/{url.database}", "mode": "READ ONLY"}), file=sys.stderr)
    ro = engine.execution_options(postgresql_readonly=True) if engine.dialect.name == "postgresql" else engine
    out = {}
    with Session(bind=ro) as db:
        if "annual_ads" in args.only:
            from app.services import annualads_commissions

            out["annual_ads"] = annualads_commissions.reconciliation(db)
        if "pool" in args.only:
            from app.services import referral_pool_reconciliation

            out["referral_pool"] = referral_pool_reconciliation.report(db)
        if "dsm" in args.only:
            from app.services import dsm_reconciliation

            out["dsm"] = dsm_reconciliation.report(db, sample=10)
        if "ledger" in args.only:
            out["ledger"] = ledger(db)
        db.rollback()
    print(json.dumps(out, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
