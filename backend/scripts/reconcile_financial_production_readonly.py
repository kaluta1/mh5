"""Low-impact, read-only production financial and affiliate reconciliation."""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402


FINANCIAL_NAME = re.compile(
    r"(wallet|transaction|journal|ledger|account|commission|affiliate|referr|sponsor|"
    r"withdraw|payout|payment|deposit|refund|invoice|purchase|revenue|earning|fmp|membership|founding)",
    re.IGNORECASE,
)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).fetchall()]


def _one(conn, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute(text(sql), params or {}).first()
    return dict(row._mapping) if row else {}


def main() -> None:
    result: dict[str, Any] = {}
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise RuntimeError("This production reconciliation requires PostgreSQL")
        transaction = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '8s'"))
            conn.execute(text("SET LOCAL lock_timeout = '1s'"))

            result["identity"] = _one(
                conn,
                "SELECT current_database() AS database, current_user AS db_user, true AS read_only",
            )
            all_tables = [
                row["table_name"]
                for row in _rows(
                    conn,
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """,
                )
            ]
            table_set = set(all_tables)
            financial_tables = [name for name in all_tables if FINANCIAL_NAME.search(name)]
            result["financial_tables"] = financial_tables

            counts: dict[str, int] = {}
            for table in financial_tables:
                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
                    continue
                counts[table] = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
            result["table_counts"] = counts

            result["financial_integrity_constraints"] = _rows(
                conn,
                """
                SELECT c.conrelid::regclass::text AS table_name,
                       c.conname AS constraint_name,
                       c.contype AS constraint_type,
                       pg_get_constraintdef(c.oid) AS definition
                FROM pg_constraint c
                WHERE c.connamespace = 'public'::regnamespace
                  AND c.conrelid::regclass::text IN (
                    'deposits', 'affiliate_commissions', 'affiliate_cashout_requests',
                    'journal_entries', 'journal_lines', 'member_fmp_ledger', 'wallet', 'wallets'
                  )
                ORDER BY table_name, constraint_name
                """,
            )
            result["financial_unique_indexes"] = _rows(
                conn,
                """
                SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'deposits', 'affiliate_commissions', 'affiliate_cashout_requests',
                    'journal_entries', 'member_fmp_ledger', 'wallet', 'wallets'
                  )
                  AND indexdef ILIKE '%UNIQUE%'
                ORDER BY tablename, indexname
                """,
            )

            if "product_types" in table_set:
                result["authoritative_product_prices"] = _rows(
                    conn,
                    """
                    SELECT code, price, currency, validity_days, is_active, has_affiliate_commission
                    FROM product_types ORDER BY code
                    """,
                )

            if "commission_rules" in table_set:
                result["commission_rules"] = _rows(
                    conn,
                    """
                    SELECT product_code, commission_type::text AS commission_type,
                           direct_percentage, indirect_percentage, max_levels, is_active
                    FROM commission_rules ORDER BY product_code
                    """,
                )

            user_columns = {
                row["column_name"]
                for row in _rows(
                    conn,
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'users'
                    """,
                )
            }
            if {"payout_currency", "usdt_wallet_address"}.issubset(user_columns):
                result["configured_payout_networks"] = _rows(
                    conn,
                    """
                    SELECT COALESCE(NULLIF(lower(payout_currency), ''), 'missing') AS payout_currency,
                           COUNT(*) AS users
                    FROM users
                    WHERE COALESCE(usdt_wallet_address, '') <> ''
                    GROUP BY COALESCE(NULLIF(lower(payout_currency), ''), 'missing')
                    ORDER BY payout_currency
                    """,
                )

            if {"journal_entries", "journal_lines"}.issubset(table_set):
                result["journal_integrity"] = _one(
                    conn,
                    """
                    WITH line_totals AS (
                        SELECT entry_id,
                               COALESCE(SUM(debit_amount), 0) AS debit,
                               COALESCE(SUM(credit_amount), 0) AS credit
                        FROM journal_lines GROUP BY entry_id
                    )
                    SELECT
                        COUNT(*) FILTER (WHERE je.total_debit <> je.total_credit) AS unbalanced_headers,
                        COUNT(*) FILTER (WHERE COALESCE(lt.debit, 0) <> COALESCE(lt.credit, 0)) AS unbalanced_line_sets,
                        COUNT(*) FILTER (
                            WHERE je.total_debit <> COALESCE(lt.debit, 0)
                               OR je.total_credit <> COALESCE(lt.credit, 0)
                        ) AS header_line_mismatches,
                        COALESCE(SUM(ABS(COALESCE(lt.debit, 0) - COALESCE(lt.credit, 0))), 0) AS total_line_imbalance
                    FROM journal_entries je
                    LEFT JOIN line_totals lt ON lt.entry_id = je.id
                    """,
                )

            if {"journal_lines", "chart_of_accounts"}.issubset(table_set):
                result["ledger_balances"] = _rows(
                    conn,
                    """
                    SELECT coa.account_code,
                           coa.account_name,
                           coa.account_type::text AS account_type,
                           COALESCE(SUM(jl.debit_amount), 0) AS debits,
                           COALESCE(SUM(jl.credit_amount), 0) AS credits,
                           CASE
                             WHEN lower(coa.account_type::text) IN ('asset', 'expense')
                             THEN COALESCE(SUM(jl.debit_amount), 0) - COALESCE(SUM(jl.credit_amount), 0)
                             ELSE COALESCE(SUM(jl.credit_amount), 0) - COALESCE(SUM(jl.debit_amount), 0)
                           END AS natural_balance
                    FROM chart_of_accounts coa
                    LEFT JOIN journal_lines jl ON jl.account_id = coa.id
                    GROUP BY coa.id, coa.account_code, coa.account_name, coa.account_type
                    ORDER BY coa.account_code
                    """,
                )

            if "affiliate_commissions" in table_set:
                result["commission_summary"] = _rows(
                    conn,
                    """
                    SELECT status::text AS status,
                           COUNT(*) AS row_count,
                           COALESCE(SUM(commission_amount), 0) AS amount
                    FROM affiliate_commissions
                    GROUP BY status::text ORDER BY status::text
                    """,
                )
                result["commission_anomalies"] = _one(
                    conn,
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE commission_amount < 0) AS negative_amount,
                      COUNT(*) FILTER (WHERE commission_amount = 0) AS zero_amount,
                      COUNT(*) FILTER (WHERE level < 1 OR level > 10) AS invalid_level,
                      COUNT(*) FILTER (WHERE deposit_id IS NULL AND reference_id IS NULL) AS missing_source,
                      COUNT(*) FILTER (WHERE status::text = 'PAID' AND COALESCE(payout_reference, '') = '') AS paid_without_payout_reference,
                      COUNT(*) FILTER (WHERE status::text <> 'PAID' AND paid_date IS NOT NULL) AS paid_date_status_mismatch
                    FROM affiliate_commissions
                    """,
                )
                result["duplicate_commission_sources"] = _rows(
                    conn,
                    """
                    SELECT deposit_id, user_id, COUNT(*) AS duplicates, SUM(commission_amount) AS amount
                    FROM affiliate_commissions
                    WHERE deposit_id IS NOT NULL
                    GROUP BY deposit_id, user_id
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, deposit_id
                    LIMIT 100
                    """,
                )
                result["commission_source_modes"] = _rows(
                    conn,
                    """
                    SELECT CASE WHEN deposit_id IS NULL THEN 'legacy_reference' ELSE 'deposit' END AS source_mode,
                           status::text AS status, COUNT(*) AS row_count,
                           COALESCE(SUM(commission_amount), 0) AS amount
                    FROM affiliate_commissions
                    GROUP BY source_mode, status::text
                    ORDER BY source_mode, status::text
                    """,
                )

            if {"affiliate_commissions", "users"}.issubset(table_set):
                result["commission_chain_mismatch"] = _one(
                    conn,
                    """
                    WITH RECURSIVE ancestors AS (
                      SELECT u.id AS source_user_id, u.sponsor_id, 1 AS level,
                             ARRAY[u.id]::integer[] AS path, false AS cycle
                      FROM users u
                      UNION ALL
                      SELECT a.source_user_id, sponsor.sponsor_id, a.level + 1,
                             a.path || a.sponsor_id,
                             a.sponsor_id = ANY(a.path)
                      FROM ancestors a
                      JOIN users sponsor ON sponsor.id = a.sponsor_id
                      WHERE a.sponsor_id IS NOT NULL AND a.level < 10 AND NOT a.cycle
                    )
                    SELECT COUNT(*) AS commissions_not_matching_sponsor_chain
                    FROM affiliate_commissions ac
                    LEFT JOIN ancestors a
                      ON a.source_user_id = ac.source_user_id
                     AND a.level = ac.level
                     AND a.sponsor_id = ac.user_id
                    WHERE a.source_user_id IS NULL
                    """,
                )

            if "deposits" in table_set:
                result["deposit_summary"] = _rows(
                    conn,
                    """
                    SELECT status::text AS status, currency, COUNT(*) AS row_count,
                           COALESCE(SUM(amount), 0) AS amount
                    FROM deposits GROUP BY status::text, currency
                    ORDER BY status::text, currency
                    """,
                )
                result["deposit_anomalies"] = _one(
                    conn,
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE amount <= 0) AS non_positive_amount,
                      COUNT(*) FILTER (WHERE status::text = 'validated' AND validated_at IS NULL) AS validated_without_timestamp,
                      COUNT(*) FILTER (WHERE external_payment_id IS NULL AND order_id IS NULL) AS missing_provider_and_order_reference
                    FROM deposits
                    """,
                )
                result["duplicate_provider_payment_ids"] = _rows(
                    conn,
                    """
                    SELECT external_payment_id, COUNT(*) AS duplicates
                    FROM deposits WHERE external_payment_id IS NOT NULL AND external_payment_id <> ''
                    GROUP BY external_payment_id HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC LIMIT 100
                    """,
                )

            if "affiliate_cashout_requests" in table_set:
                result["cashout_summary"] = _rows(
                    conn,
                    """
                    SELECT status, COUNT(*) AS row_count,
                           COALESCE(SUM(gross_amount), 0) AS gross,
                           COALESCE(SUM(fee), 0) AS fees,
                           COALESCE(SUM(net_amount), 0) AS net
                    FROM affiliate_cashout_requests GROUP BY status ORDER BY status
                    """,
                )

            if {"affiliate_commissions", "journal_lines", "chart_of_accounts"}.issubset(table_set):
                result["commission_subledger_vs_ledger"] = _one(
                    conn,
                    """
                    WITH subledger AS (
                      SELECT COALESCE(SUM(commission_amount), 0) AS outstanding
                      FROM affiliate_commissions
                      WHERE status::text IN ('PENDING', 'APPROVED')
                    ), ledger AS (
                      SELECT COALESCE(SUM(jl.credit_amount - jl.debit_amount), 0) AS payable
                      FROM journal_lines jl
                      JOIN chart_of_accounts coa ON coa.id = jl.account_id
                      WHERE coa.account_code IN ('2001', '2002')
                    )
                    SELECT subledger.outstanding AS commission_outstanding,
                           ledger.payable AS ledger_payable,
                           ledger.payable - subledger.outstanding AS discrepancy
                    FROM subledger CROSS JOIN ledger
                    """,
                )
                result["commission_source_ledger_mismatches"] = _rows(
                    conn,
                    """
                    WITH commission_sources AS (
                      SELECT deposit_id, COUNT(*) AS commission_rows,
                             SUM(commission_amount) AS commission_amount
                      FROM affiliate_commissions
                      WHERE deposit_id IS NOT NULL
                        AND status::text IN ('PENDING', 'APPROVED', 'PAID')
                      GROUP BY deposit_id
                    ), posted AS (
                      SELECT cs.deposit_id,
                             COALESCE(SUM(jl.credit_amount - jl.debit_amount), 0) AS payable_posted
                      FROM commission_sources cs
                      LEFT JOIN journal_entries je
                        ON je.description ~ ('Deposit #' || cs.deposit_id::text || '([^0-9]|$)')
                      LEFT JOIN journal_lines jl ON jl.entry_id = je.id
                      LEFT JOIN chart_of_accounts coa ON coa.id = jl.account_id
                                                   AND coa.account_code IN ('2001', '2002')
                      WHERE coa.id IS NOT NULL OR je.id IS NULL
                      GROUP BY cs.deposit_id
                    )
                    SELECT cs.deposit_id, cs.commission_rows, cs.commission_amount,
                           posted.payable_posted,
                           posted.payable_posted - cs.commission_amount AS discrepancy
                    FROM commission_sources cs
                    JOIN posted ON posted.deposit_id = cs.deposit_id
                    WHERE posted.payable_posted <> cs.commission_amount
                    ORDER BY cs.deposit_id
                    LIMIT 100
                    """,
                )
                result["unattributed_commission_payable_movements"] = _rows(
                    conn,
                    """
                    WITH commission_sources AS (
                      SELECT DISTINCT deposit_id FROM affiliate_commissions WHERE deposit_id IS NOT NULL
                    )
                    SELECT je.id AS journal_entry_id, je.description,
                           coa.account_code, jl.debit_amount, jl.credit_amount
                    FROM journal_lines jl
                    JOIN journal_entries je ON je.id = jl.entry_id
                    JOIN chart_of_accounts coa ON coa.id = jl.account_id
                    WHERE coa.account_code IN ('2001', '2002')
                      AND NOT EXISTS (
                        SELECT 1 FROM commission_sources cs
                        WHERE je.description ~ ('Deposit #' || cs.deposit_id::text || '([^0-9]|$)')
                      )
                    ORDER BY je.id, jl.id
                    LIMIT 100
                    """,
                )

            if "users" in table_set:
                result["referral_anomalies"] = _one(
                    conn,
                    """
                    WITH RECURSIVE walk AS (
                      SELECT u.id AS root_id, u.sponsor_id AS next_id,
                             ARRAY[u.id]::integer[] AS path, false AS cycle, 0 AS depth
                      FROM users u
                      UNION ALL
                      SELECT w.root_id, u.sponsor_id, w.path || u.id,
                             u.id = ANY(w.path), w.depth + 1
                      FROM walk w JOIN users u ON u.id = w.next_id
                      WHERE w.next_id IS NOT NULL AND NOT w.cycle AND w.depth < 100
                    )
                    SELECT
                      (SELECT COUNT(*) FROM users WHERE sponsor_id = id) AS self_referrals,
                      (SELECT COUNT(*) FROM users child LEFT JOIN users sponsor ON sponsor.id = child.sponsor_id
                        WHERE child.sponsor_id IS NOT NULL AND sponsor.id IS NULL) AS missing_sponsors,
                      COUNT(DISTINCT root_id) FILTER (WHERE cycle) AS users_in_or_leading_to_cycle,
                      COUNT(DISTINCT root_id) FILTER (WHERE depth >= 100 AND next_id IS NOT NULL) AS over_safety_depth
                    FROM walk
                    """,
                )

            for wallet_table in ("wallet", "wallets"):
                if wallet_table not in table_set:
                    continue
                wallet_columns = [
                    row["column_name"]
                    for row in _rows(
                        conn,
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = :table_name
                        ORDER BY ordinal_position
                        """,
                        {"table_name": wallet_table},
                    )
                ]
                result[f"{wallet_table}_columns"] = wallet_columns
                if {"balance", "currency"}.issubset(wallet_columns):
                    frozen_select = ", SUM(frozen_balance) AS frozen_balance" if "frozen_balance" in wallet_columns else ""
                    result[f"{wallet_table}_balances"] = _rows(
                        conn,
                        f'SELECT currency, COUNT(*) AS rows, SUM(balance) AS balance{frozen_select} FROM "{wallet_table}" GROUP BY currency ORDER BY currency',
                    )

            if {"affiliate_tree", "users"}.issubset(table_set):
                result["affiliate_tree_mismatch"] = _one(
                    conn,
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE at.user_id = at.sponsor_id) AS self_referrals,
                      COUNT(*) FILTER (WHERE u.id IS NULL OR s.id IS NULL) AS missing_user_or_sponsor,
                      COUNT(*) FILTER (WHERE u.sponsor_id IS DISTINCT FROM at.sponsor_id) AS user_tree_sponsor_mismatch
                    FROM affiliate_tree at
                    LEFT JOIN users u ON u.id = at.user_id
                    LEFT JOIN users s ON s.id = at.sponsor_id
                    """,
                )

            print(json.dumps(result, default=_json, indent=2, sort_keys=True))
        finally:
            transaction.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()
