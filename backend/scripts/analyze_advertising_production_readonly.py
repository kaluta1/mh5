"""Low-impact, read-only production advertising inventory and integrity audit.

The script accepts only PostgreSQL, opens an explicit READ ONLY transaction,
uses short statement/lock timeouts, executes SELECT/catalog queries, and always
rolls back.  It never calls AnnualAds, ad destinations, or any media provider.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402


AD_NAME = re.compile(
    r"(^ad_|advert|campaign|creative|placement|impression|click|sponsor|promot|boost)",
    re.IGNORECASE,
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).fetchall()]


def _one(conn, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute(text(sql), params or {}).first()
    return dict(row._mapping) if row else {}


def _safe_ident(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", value):
        raise ValueError("unsafe SQL identifier")
    return value


def main() -> None:
    result: dict[str, Any] = {}
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise RuntimeError("Production advertising audit requires PostgreSQL")
        transaction = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '8s'"))
            conn.execute(text("SET LOCAL lock_timeout = '1s'"))
            result["identity"] = _one(
                conn,
                "SELECT current_database() AS database, current_user AS db_user, true AS read_only",
            )

            all_tables = _rows(
                conn,
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
            )
            ad_tables = [row["table_name"] for row in all_tables if AD_NAME.search(row["table_name"])]
            result["advertising_tables"] = ad_tables
            result["table_counts"] = {
                table: int(conn.execute(text(f'SELECT count(*) FROM "{_safe_ident(table)}"')).scalar() or 0)
                for table in ad_tables
            }

            if ad_tables:
                result["columns"] = _rows(
                    conn,
                    """
                    SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = ANY(:tables)
                    ORDER BY table_name, ordinal_position
                    """,
                    {"tables": ad_tables},
                )
                result["constraints"] = _rows(
                    conn,
                    """
                    SELECT c.conrelid::regclass::text AS table_name,
                           c.conname AS constraint_name,
                           c.contype AS constraint_type,
                           pg_get_constraintdef(c.oid) AS definition
                    FROM pg_constraint c
                    WHERE c.connamespace = 'public'::regnamespace
                      AND c.conrelid::regclass::text = ANY(:tables)
                    ORDER BY table_name, constraint_name
                    """,
                    {"tables": ad_tables},
                )
                result["indexes"] = _rows(
                    conn,
                    """
                    SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
                    FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = ANY(:tables)
                    ORDER BY tablename, indexname
                    """,
                    {"tables": ad_tables},
                )
                result["enum_labels"] = _rows(
                    conn,
                    """
                    SELECT t.typname AS enum_name, e.enumlabel AS label, e.enumsortorder AS sort_order
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname IN (
                      SELECT DISTINCT udt_name FROM information_schema.columns
                      WHERE table_schema = 'public' AND table_name = ANY(:tables)
                    )
                    ORDER BY t.typname, e.enumsortorder
                    """,
                    {"tables": ad_tables},
                )

            table_set = set(ad_tables)
            columns_by_table: dict[str, set[str]] = {}
            for row in result.get("columns", []):
                columns_by_table.setdefault(row["table_name"], set()).add(row["column_name"])

            if "ad_campaigns" in table_set:
                campaign_columns = columns_by_table.get("ad_campaigns", set())
                result["campaign_statuses"] = _rows(
                    conn,
                    "SELECT status::text AS status, count(*) AS rows FROM ad_campaigns GROUP BY status::text ORDER BY status::text",
                ) if "status" in campaign_columns else []
                required = {"advertiser_id", "budget_amount", "remaining_budget", "spent_amount", "start_date", "end_date"}
                if required.issubset(campaign_columns):
                    result["campaign_anomalies"] = _one(
                        conn,
                        """
                        SELECT
                          count(*) FILTER (WHERE advertiser_id IS NULL) AS missing_owner,
                          count(*) FILTER (WHERE budget_amount IS NULL OR budget_amount <= 0) AS invalid_budget,
                          count(*) FILTER (WHERE spent_amount < 0 OR remaining_budget < 0) AS negative_money,
                          count(*) FILTER (WHERE spent_amount > budget_amount OR remaining_budget > budget_amount) AS budget_inconsistent,
                          count(*) FILTER (WHERE end_date IS NOT NULL AND start_date >= end_date) AS invalid_dates,
                          count(*) FILTER (WHERE u.id IS NULL) AS owner_not_found
                        FROM ad_campaigns c
                        LEFT JOIN users u ON u.id = c.advertiser_id
                        """,
                    )

            if {"ad_campaigns", "ad_creatives"}.issubset(table_set):
                creative_columns = columns_by_table.get("ad_creatives", set())
                if {"campaign_id", "landing_url"}.issubset(creative_columns):
                    result["creative_anomalies"] = _one(
                        conn,
                        """
                        SELECT
                          count(*) FILTER (WHERE c.id IS NULL) AS missing_campaign,
                          count(*) FILTER (WHERE COALESCE(btrim(cr.landing_url), '') = '') AS missing_destination,
                          count(*) FILTER (WHERE cr.landing_url !~* '^https?://') AS non_http_destination,
                          count(*) FILTER (WHERE cr.landing_url ~* '^https?://(localhost|127\\.0\\.0\\.1|\\[?::1\\]?)([:/]|$)') AS local_destination
                        FROM ad_creatives cr
                        LEFT JOIN ad_campaigns c ON c.id = cr.campaign_id
                        """,
                    )

            if "ad_placements" in table_set:
                placement_columns = columns_by_table.get("ad_placements", set())
                if {"page_type", "position", "is_active"}.issubset(placement_columns):
                    result["placements"] = _rows(
                        conn,
                        """
                        SELECT page_type, position, is_active, cost_model::text AS cost_model,
                               base_cpm, base_price, min_price_tier1, min_price_tier2,
                               min_price_ww, flat_period::text AS flat_period, flat_price,
                               count(*) AS rows
                        FROM ad_placements
                        GROUP BY page_type, position, is_active, cost_model, base_cpm, base_price,
                                 min_price_tier1, min_price_tier2, min_price_ww, flat_period, flat_price
                        ORDER BY page_type, position, is_active
                        """,
                    )

            if "ad_credit_accounts" in table_set:
                result["ad_credit_summary"] = _one(
                    conn,
                    """
                    SELECT count(*) AS accounts, COALESCE(sum(balance), 0) AS balance,
                           COALESCE(sum(total_deposited), 0) AS deposited,
                           COALESCE(sum(total_spent), 0) AS spent,
                           count(*) FILTER (WHERE balance < 0 OR total_deposited < 0 OR total_spent < 0) AS negative_rows,
                           count(*) FILTER (WHERE balance + total_spent <> total_deposited) AS reconciliation_mismatches
                    FROM ad_credit_accounts
                    """,
                )

            all_table_names = {row["table_name"] for row in all_tables}
            if "product_types" in all_table_names:
                result["ad_products"] = _rows(
                    conn,
                    """
                    SELECT code, name, price, currency, validity_days, is_active,
                           has_affiliate_commission, affiliate_direct_amount,
                           affiliate_direct_rate, affiliate_indirect_amount, affiliate_indirect_rate
                    FROM product_types
                    WHERE lower(code) LIKE '%ad%' OR lower(name) LIKE '%ad%'
                    ORDER BY code
                    """,
                )
            if "commission_rules" in all_table_names:
                result["ad_commission_rules"] = _rows(
                    conn,
                    """
                    SELECT product_code, commission_type::text AS commission_type,
                           direct_percentage, indirect_percentage, max_levels, is_active
                    FROM commission_rules
                    WHERE lower(product_code) LIKE '%ad%'
                    ORDER BY product_code
                    """,
                )

            if {"ad_impressions", "ad_clicks"}.issubset(table_set):
                result["event_integrity"] = _one(
                    conn,
                    """
                    SELECT
                      (SELECT count(*) FROM ad_impressions i LEFT JOIN ad_campaigns c ON c.id=i.campaign_id WHERE c.id IS NULL) AS impression_missing_campaign,
                      (SELECT count(*) FROM ad_impressions i LEFT JOIN ad_creatives cr ON cr.id=i.creative_id WHERE cr.id IS NULL) AS impression_missing_creative,
                      (SELECT count(*) FROM ad_impressions i LEFT JOIN ad_placements p ON p.id=i.placement_id WHERE p.id IS NULL) AS impression_missing_placement,
                      (SELECT count(*) FROM ad_clicks cl LEFT JOIN ad_impressions i ON i.id=cl.impression_id WHERE i.id IS NULL) AS click_missing_impression,
                      (SELECT count(*) FROM (SELECT impression_id FROM ad_clicks GROUP BY impression_id HAVING count(*) > 1) d) AS duplicate_click_impression_groups
                    """,
                )
                result["duplicate_impression_groups"] = _rows(
                    conn,
                    """
                    SELECT campaign_id, creative_id, placement_id, user_id,
                           date_trunc('minute', timestamp) AS minute, count(*) AS rows
                    FROM ad_impressions
                    GROUP BY campaign_id, creative_id, placement_id, user_id, date_trunc('minute', timestamp)
                    HAVING count(*) > 1
                    ORDER BY rows DESC
                    LIMIT 50
                    """,
                )

            if "ad_budget_transactions" in table_set:
                result["budget_transaction_summary"] = _rows(
                    conn,
                    """
                    SELECT transaction_type, count(*) AS rows, COALESCE(sum(amount), 0) AS amount
                    FROM ad_budget_transactions GROUP BY transaction_type ORDER BY transaction_type
                    """,
                )

            if "journal_entries" in all_table_names:
                result["annualads_journal_summary"] = _one(
                    conn,
                    """
                    SELECT count(*) AS journal_entries,
                           COALESCE(sum(total_debit), 0) AS amount
                    FROM journal_entries
                    WHERE description ILIKE 'AnnualAds sponsor payment received%'
                    """,
                )
                result["annualads_duplicate_tx_descriptions"] = _rows(
                    conn,
                    """
                    SELECT substring(description from 'tx:([^ ]+)') AS tx_reference,
                           count(*) AS rows, sum(total_debit) AS amount
                    FROM journal_entries
                    WHERE description ILIKE 'AnnualAds sponsor payment received%'
                    GROUP BY substring(description from 'tx:([^ ]+)')
                    HAVING count(*) > 1
                    ORDER BY rows DESC
                    LIMIT 50
                    """,
                )
        finally:
            transaction.rollback()
            engine.dispose()

    if "summary" in sys.argv[1:]:
        result.pop("columns", None)
        result.pop("constraints", None)
        result.pop("indexes", None)
    print(json.dumps(result, default=_json_default, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
