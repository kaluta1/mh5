"""
Admin diagnostics: CoA coverage, orphan journal lines, KYC journal gaps vs new policy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit, DepositStatus, ProductType

# Codes added/renamed in recent CoA work — must exist for new flows.
EXPECTED_CRITICAL_COA_CODES = (
    "1001",
    "2003",
    "2104",
    "2105",
    "2113",
    "4001",
)


def _coa_codes_in_db(db: Session) -> Set[str]:
    bind = db.get_bind()
    if not inspect(bind).has_table("chart_of_accounts"):
        return set()
    rows = db.execute(text("SELECT account_code FROM chart_of_accounts")).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def orphan_journal_line_count(db: Session) -> int:
    bind = db.get_bind()
    insp = inspect(bind)
    if not insp.has_table("journal_lines") or not insp.has_table("chart_of_accounts"):
        return 0
    row = db.execute(
        text(
            """
            SELECT COUNT(*) FROM journal_lines jl
            LEFT JOIN chart_of_accounts ca ON ca.id = jl.account_id
            WHERE ca.id IS NULL
            """
        )
    ).scalar()
    return int(row or 0)


def account_codes_used_in_journals(db: Session) -> Set[str]:
    bind = db.get_bind()
    insp = inspect(bind)
    if not insp.has_table("journal_lines"):
        return set()
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ca.account_code
            FROM journal_lines jl
            INNER JOIN chart_of_accounts ca ON ca.id = jl.account_id
            """
        )
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def kyc_journal_gaps(db: Session, *, scan_limit: int = 500) -> Dict[str, Any]:
    """Validated KYC deposits that lack deferred or (if KYC approved) recognition journals."""
    from app.services.payment_accounting import (
        get_latest_validated_kyc_deposit,
        kyc_deferred_receipt_posted,
        kyc_recognition_posted,
    )

    kyc_pt = db.query(ProductType).filter(ProductType.code == "kyc").first()
    if not kyc_pt:
        return {
            "validated_kyc_deposits_scanned": 0,
            "missing_deferred_journal": 0,
            "missing_verification_recognition": 0,
            "samples": [],
            "note": "No product_types row for code kyc",
        }

    deps = (
        db.query(Deposit.id, Deposit.user_id)
        .filter(
            Deposit.product_type_id == kyc_pt.id,
            Deposit.status == DepositStatus.VALIDATED,
        )
        .order_by(Deposit.id.desc())
        .limit(scan_limit)
        .all()
    )

    missing_def = 0
    missing_rec = 0
    samples: List[Dict[str, Any]] = []

    for did, uid in deps:
        if not kyc_deferred_receipt_posted(db, did):
            missing_def += 1
            if len(samples) < 25:
                samples.append(
                    {
                        "deposit_id": did,
                        "user_id": uid,
                        "issue": "missing_deferred_cash_receipt",
                        "fix": "Run payment backfill or re-validate deposit accounting (Dr 1001 / Cr 2113)",
                    }
                )
            continue

        row = db.query(KYCVerification.status).filter(KYCVerification.user_id == uid).first()
        approved = row is not None and row[0] == KYCStatus.APPROVED
        if approved and not kyc_recognition_posted(db, did):
            missing_rec += 1
            if len(samples) < 25:
                samples.append(
                    {
                        "deposit_id": did,
                        "user_id": uid,
                        "issue": "missing_verification_performed_journals",
                        "fix": "Trigger KYC approval webhook/sync or call post_kyc_verification_recognition_for_user",
                    }
                )

    return {
        "validated_kyc_deposits_scanned": len(deps),
        "missing_deferred_journal": missing_def,
        "missing_verification_recognition": missing_rec,
        "samples": samples,
    }


def build_ledger_health_payload(db: Session, *, kyc_scan_limit: int = 500) -> Dict[str, Any]:
    codes = _coa_codes_in_db(db)
    used = account_codes_used_in_journals(db)
    orphans = orphan_journal_line_count(db)

    critical = {c: (c in codes) for c in EXPECTED_CRITICAL_COA_CODES}
    missing_critical = [c for c, ok in critical.items() if not ok]

    return {
        "chart_of_accounts_row_count": len(codes),
        "distinct_accounts_used_in_journals": len(used),
        "account_codes_with_posted_activity": sorted(used),
        "orphan_journal_lines": orphans,
        "critical_coa_codes_present": critical,
        "missing_critical_codes": missing_critical,
        "kyc_gaps": kyc_journal_gaps(db, scan_limit=kyc_scan_limit),
        "hints": [
            "Run POST /api/v1/admin/accounting/ensure-coa to insert/update CoA rows from init_coa.py.",
            "Run POST /api/v1/admin/accounting/backfill-journals?dry_run=false to post missing payment journals (uses current rules).",
            "If journals exist but Founding Members 10% (2104) is missing, run POST /api/v1/admin/accounting/backfill-founding-pool-accruals?dry_run=false after reviewing a dry run.",
            "Old journals keep the same account_id FKs; renaming accounts in CoA does not break prior entries.",
        ],
    }
