"""Compact Prompt 9 production audit. Every database transaction is READ ONLY."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402


def _json(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def rows(conn, sql, params=None):
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).fetchall()]


def one(conn, sql, params=None):
    found = conn.execute(text(sql), params or {}).first()
    return dict(found._mapping) if found else {}


def main():
    out = {}
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise RuntimeError("Production audit requires PostgreSQL")
        tx = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '8s'"))
            conn.execute(text("SET LOCAL lock_timeout = '1s'"))
            out["identity"] = one(conn, "SELECT current_database() database, current_user db_user, true read_only")
            table_names = {r["table_name"] for r in rows(conn, "SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}

            out["user_roles"] = rows(conn, """
                SELECT COALESCE(r.name, CASE WHEN u.is_admin THEN 'is_admin' ELSE 'unassigned' END) role,
                       COUNT(*) users, COUNT(*) FILTER (WHERE u.is_active) active
                FROM users u LEFT JOIN roles r ON r.id=u.role_id
                GROUP BY 1 ORDER BY 1
            """)
            out["admin_count"] = one(conn, "SELECT COUNT(*) admins FROM users WHERE is_admin")

            out["journal_integrity"] = one(conn, """
                WITH totals AS (
                  SELECT entry_id, COUNT(*) lines, COALESCE(SUM(debit_amount),0) debit,
                         COALESCE(SUM(credit_amount),0) credit,
                         COUNT(*) FILTER (WHERE debit_amount > 0 AND credit_amount > 0) both_sides,
                         COUNT(*) FILTER (WHERE debit_amount = 0 AND credit_amount = 0) zero_lines
                  FROM journal_lines GROUP BY entry_id
                )
                SELECT COUNT(*) journals,
                  COUNT(*) FILTER (WHERE t.entry_id IS NULL) missing_lines,
                  COUNT(*) FILTER (WHERE t.lines < 2) fewer_than_two_lines,
                  COUNT(*) FILTER (WHERE t.debit <> t.credit) unbalanced_line_sets,
                  COUNT(*) FILTER (WHERE je.total_debit <> je.total_credit) unbalanced_headers,
                  COUNT(*) FILTER (WHERE je.total_debit <> t.debit OR je.total_credit <> t.credit) header_line_mismatches,
                  COALESCE(SUM(t.both_sides),0) lines_with_both_debit_and_credit,
                  COALESCE(SUM(t.zero_lines),0) zero_lines,
                  COUNT(*) FILTER (WHERE je.total_debit = 0 AND je.total_credit = 0) zero_value_journals
                FROM journal_entries je LEFT JOIN totals t ON t.entry_id=je.id
            """)
            out["orphan_journal_lines"] = one(conn, """
                SELECT COUNT(*) FILTER (WHERE je.id IS NULL) missing_journal,
                       COUNT(*) FILTER (WHERE coa.id IS NULL) missing_account
                FROM journal_lines jl LEFT JOIN journal_entries je ON je.id=jl.entry_id
                LEFT JOIN chart_of_accounts coa ON coa.id=jl.account_id
            """)
            out["duplicate_journal_descriptions"] = rows(conn, """
                SELECT description, COUNT(*) duplicates FROM journal_entries
                GROUP BY description HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 20
            """)

            out["approved_commission_vs_payable"] = one(conn, """
                WITH sub AS (
                  SELECT COALESCE(SUM(commission_amount),0) approved FROM affiliate_commissions
                  WHERE status::text='APPROVED'
                ), ledger AS (
                  SELECT COALESCE(SUM(jl.credit_amount-jl.debit_amount),0) payable
                  FROM journal_lines jl JOIN chart_of_accounts ca ON ca.id=jl.account_id
                  WHERE ca.account_code IN ('2001','2002')
                ) SELECT approved, payable, payable-approved difference FROM sub CROSS JOIN ledger
            """)
            out["approved_commission_sources"] = rows(conn, """
                WITH approved AS (
                  SELECT deposit_id, reference_id, COUNT(*) commission_rows,
                         SUM(commission_amount) expected
                  FROM affiliate_commissions WHERE status::text='APPROVED'
                  GROUP BY deposit_id, reference_id
                )
                SELECT a.deposit_id, a.reference_id, a.commission_rows, a.expected,
                       COALESCE(SUM(jl.credit_amount-jl.debit_amount) FILTER (WHERE ca.account_code IN ('2001','2002')),0) posted,
                       COALESCE(SUM(jl.credit_amount-jl.debit_amount) FILTER (WHERE ca.account_code IN ('2001','2002')),0)-a.expected difference
                FROM approved a
                LEFT JOIN journal_entries je ON a.deposit_id IS NOT NULL
                  AND je.description ~ ('Deposit #' || a.deposit_id::text || '([^0-9]|$)')
                LEFT JOIN journal_lines jl ON jl.entry_id=je.id
                LEFT JOIN chart_of_accounts ca ON ca.id=jl.account_id
                GROUP BY a.deposit_id,a.reference_id,a.commission_rows,a.expected
                ORDER BY a.deposit_id NULLS LAST,a.reference_id
            """)
            out["approved_commission_rows"] = rows(conn, """
                SELECT id, user_id, source_user_id, deposit_id, reference_id, level,
                       commission_amount, transaction_date
                FROM affiliate_commissions WHERE status::text='APPROVED'
                ORDER BY deposit_id NULLS LAST, id
            """)

            out["provider_reference_duplicates"] = {
                "deposit_payment_id": rows(conn, """SELECT external_payment_id reference,COUNT(*) duplicates FROM deposits WHERE COALESCE(external_payment_id,'')<>'' GROUP BY 1 HAVING COUNT(*)>1"""),
                "deposit_order_id": rows(conn, """SELECT order_id reference,COUNT(*) duplicates FROM deposits WHERE COALESCE(order_id,'')<>'' GROUP BY 1 HAVING COUNT(*)>1"""),
                "cashout_payout_reference": rows(conn, """SELECT payout_reference reference,COUNT(*) duplicates FROM affiliate_cashout_requests WHERE COALESCE(payout_reference,'')<>'' GROUP BY 1 HAVING COUNT(*)>1""") if "affiliate_cashout_requests" in table_names else [],
            }

            if "wallets" in table_names:
                columns = [r["column_name"] for r in rows(conn, "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='wallets' ORDER BY ordinal_position")]
                out["wallets_columns"] = columns
                safe = [c for c in ("id", "user_id", "balance", "currency", "frozen_balance", "created_at", "updated_at") if c in columns]
                select = ", ".join('w."%s"' % c for c in safe)
                owner = ", (u.id IS NOT NULL) owner_exists" if "user_id" in columns else ""
                join = " LEFT JOIN users u ON u.id=w.user_id" if "user_id" in columns else ""
                out["wallets_rows"] = rows(conn, f'SELECT {select}{owner} FROM wallets w{join} ORDER BY w.id')
                out["wallets_foreign_keys"] = rows(conn, """
                    SELECT conname constraint_name, pg_get_constraintdef(oid) definition
                    FROM pg_constraint WHERE conrelid='public.wallets'::regclass AND contype='f'
                """)

            out["connection_state"] = rows(conn, """
                SELECT state, COUNT(*) connections FROM pg_stat_activity
                WHERE datname=current_database() GROUP BY state ORDER BY state
            """)
            out["config_shape"] = {
                "environment_production": os.getenv("ENVIRONMENT", "").lower() == "production",
                "debug_enabled": os.getenv("DEBUG", "").lower() in ("1", "true", "yes"),
                "nowpayments_sandbox_explicit": "NOWPAYMENTS_SANDBOX" in os.environ,
                "nowpayments_sandbox": os.getenv("NOWPAYMENTS_SANDBOX", "").lower() == "true",
                "kyc_provider": os.getenv("KYC_PROVIDER", "kaluta").lower(),
                "cors_explicit": bool(os.getenv("BACKEND_CORS_ORIGINS", "").strip()),
                "provider_secret_presence": {
                    key: bool(os.getenv(key, "").strip()) for key in (
                        "NOWPAYMENTS_IPN_SECRET", "KALUTA_WEBHOOK_SECRET",
                        "SHUFTI_SECRET_KEY", "ANNUALADS_WEBHOOK_SECRET"
                    )
                },
            }
            print(json.dumps(out, default=_json, indent=2, sort_keys=True))
        finally:
            tx.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()
