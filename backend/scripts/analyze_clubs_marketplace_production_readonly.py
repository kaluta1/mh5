"""Read-only production inventory/reconciliation for clubs and marketplace.

Only PostgreSQL SELECT/catalog queries run inside an explicit READ ONLY
transaction with short statement/lock timeouts.  The transaction is always
rolled back and no external service is contacted.
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

DOMAIN = re.compile(r"(club|member|subscription|digital|product|purchase|shop|market|seller|vendor|order|cart|dsp|escrow|payout|refund|review)", re.I)


def _rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).fetchall()]


def _one(conn, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute(text(sql), params or {}).first()
    return dict(row._mapping) if row else {}


def _ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("Unsafe identifier")
    return name


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def main() -> None:
    out: dict[str, Any] = {}
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise RuntimeError("Production reconciliation requires PostgreSQL")
        tx = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '8s'"))
            conn.execute(text("SET LOCAL lock_timeout = '1s'"))
            out["identity"] = _one(conn, "SELECT current_database() AS database, current_user AS db_user, true AS read_only")
            tables = [r["table_name"] for r in _rows(conn, """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name
            """)]
            domain_tables = [t for t in tables if DOMAIN.search(t)]
            table_set = set(tables)
            out["domain_tables"] = domain_tables
            out["counts"] = {
                t: int(conn.execute(text(f'SELECT count(*) FROM "{_ident(t)}"')).scalar() or 0)
                for t in domain_tables
            }
            out["columns"] = _rows(conn, """
                SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=ANY(:tables)
                ORDER BY table_name,ordinal_position
            """, {"tables": domain_tables})
            out["constraints"] = _rows(conn, """
                SELECT c.conrelid::regclass::text AS table_name,c.conname AS constraint_name,
                       c.contype AS constraint_type,pg_get_constraintdef(c.oid) AS definition
                FROM pg_constraint c
                WHERE c.connamespace='public'::regnamespace
                  AND c.conrelid::regclass::text=ANY(:tables)
                ORDER BY table_name,constraint_name
            """, {"tables": domain_tables})
            out["indexes"] = _rows(conn, """
                SELECT tablename AS table_name,indexname AS index_name,indexdef AS definition
                FROM pg_indexes WHERE schemaname='public' AND tablename=ANY(:tables)
                ORDER BY tablename,indexname
            """, {"tables": domain_tables})

            if "fan_clubs" in table_set:
                out["club_statuses"] = _rows(conn, "SELECT status::text AS status,count(*) AS rows FROM fan_clubs GROUP BY status::text ORDER BY status::text")
                out["club_anomalies"] = _one(conn, """
                    SELECT count(*) FILTER (WHERE owner_id IS NULL OR u.id IS NULL) AS missing_owner,
                           count(*) FILTER (WHERE premium_fee < 0) AS negative_price,
                           count(*) FILTER (WHERE max_members IS NOT NULL AND max_members <= 0) AS invalid_max_members,
                           count(*) FILTER (WHERE multisig_threshold < 1) AS invalid_multisig
                    FROM fan_clubs c LEFT JOIN users u ON u.id=c.owner_id
                """)
            if "club_memberships" in table_set:
                out["membership_statuses"] = _rows(conn, "SELECT status::text AS status,count(*) AS rows,COALESCE(sum(amount_paid),0) AS amount FROM club_memberships GROUP BY status::text ORDER BY status::text")
                out["membership_anomalies"] = _one(conn, """
                    SELECT count(*) FILTER (WHERE c.id IS NULL OR u.id IS NULL) AS orphan_rows,
                           count(*) FILTER (WHERE start_date >= end_date) AS invalid_dates,
                           count(*) FILTER (WHERE amount_paid < 0 OR payment_amount < 0 OR COALESCE(fee_amount,0) < 0) AS negative_money,
                           count(*) FILTER (WHERE m.status::text ILIKE '%active%' AND m.end_date <= now()) AS expired_but_active,
                           (SELECT count(*) FROM (SELECT club_id,member_id,count(*) FROM club_memberships
                             WHERE status::text ILIKE '%active%' GROUP BY club_id,member_id HAVING count(*)>1) d) AS duplicate_active_groups
                    FROM club_memberships m
                    LEFT JOIN fan_clubs c ON c.id=m.club_id LEFT JOIN users u ON u.id=m.member_id
                """)
            if "club_wallets" in table_set:
                out["club_wallet_summary"] = _one(conn, """
                    SELECT count(*) AS wallets,COALESCE(sum(balance_cad),0) AS balance_cad,
                           COALESCE(sum(fiat_balance),0) AS fiat_balance,
                           COALESCE(sum(total_membership_fee),0) AS membership_total,
                           COALESCE(sum(total_ad_revenue),0) AS ad_total,
                           count(*) FILTER (WHERE balance_cad<0 OR fiat_balance<0) AS negative_rows
                    FROM club_wallets
                """)
            if "club_transactions" in table_set:
                out["club_transactions"] = _rows(conn, """
                    SELECT transaction_type,currency,is_approved,count(*) AS rows,COALESCE(sum(amount),0) AS amount
                    FROM club_transactions GROUP BY transaction_type,currency,is_approved
                    ORDER BY transaction_type,currency,is_approved
                """)
                out["duplicate_club_references"] = _rows(conn, """
                    SELECT reference_id,count(*) AS rows,COALESCE(sum(amount),0) AS amount
                    FROM club_transactions WHERE reference_id IS NOT NULL AND btrim(reference_id)<>''
                    GROUP BY reference_id HAVING count(*)>1 ORDER BY rows DESC LIMIT 50
                """)
            if "digital_products" in table_set:
                out["product_summary"] = _one(conn, """
                    SELECT count(*) AS products,count(*) FILTER (WHERE p.is_active) AS active,
                           count(*) FILTER (WHERE p.seller_id IS NULL OR u.id IS NULL) AS missing_seller,
                           count(*) FILTER (WHERE p.price_dsp<0 OR COALESCE(p.price_cad,0)<0 OR COALESCE(p.price_usd,0)<0) AS negative_price,
                           count(*) FILTER (WHERE COALESCE(p.file_url,'')='') AS missing_file,
                           count(*) FILTER (WHERE p.file_url ~* '^https?://') AS public_http_files
                    FROM digital_products p LEFT JOIN users u ON u.id=p.seller_id
                """)
                out["product_categories"] = _rows(conn, "SELECT category,count(*) AS rows FROM digital_products GROUP BY category ORDER BY rows DESC,category LIMIT 100")
            if "digital_purchases" in table_set:
                out["purchase_summary"] = _one(conn, """
                    SELECT count(*) AS purchases,COALESCE(sum(dp.total_paid),0) AS gross,
                           COALESCE(sum(dp.platform_fee),0) AS platform_fee,
                           COALESCE(sum(dp.seller_earnings),0) AS seller_earnings,
                           count(*) FILTER (WHERE p.id IS NULL OR u.id IS NULL) AS orphan_rows,
                           count(*) FILTER (WHERE dp.total_paid<0 OR dp.dsp_paid<0 OR dp.fiat_paid<0 OR dp.platform_fee<0 OR dp.seller_earnings<0) AS negative_money,
                           count(*) FILTER (WHERE dp.total_paid<>dp.dsp_paid+dp.fiat_paid) AS payment_split_mismatch,
                           count(*) FILTER (WHERE dp.total_paid<>dp.platform_fee+dp.seller_earnings) AS earning_split_mismatch,
                           count(*) FILTER (WHERE dp.download_count>dp.max_downloads) AS excess_downloads
                    FROM digital_purchases dp LEFT JOIN digital_products p ON p.id=dp.product_id
                    LEFT JOIN users u ON u.id=dp.buyer_id
                """)
                out["duplicate_entitlements"] = _rows(conn, """
                    SELECT buyer_id,product_id,count(*) AS rows FROM digital_purchases
                    GROUP BY buyer_id,product_id HAVING count(*)>1 ORDER BY rows DESC LIMIT 50
                """)
            if "product_reviews" in table_set:
                out["review_anomalies"] = _one(conn, """
                    SELECT count(*) FILTER (WHERE rating<1 OR rating>5) AS invalid_rating,
                           count(*) FILTER (WHERE p.seller_id=reviewer_id) AS self_review,
                           count(*) FILTER (WHERE is_verified_purchase AND NOT EXISTS (
                             SELECT 1 FROM digital_purchases dp WHERE dp.product_id=r.product_id AND dp.buyer_id=r.reviewer_id
                           )) AS falsely_verified,
                           (SELECT count(*) FROM (SELECT product_id,reviewer_id,count(*) FROM product_reviews
                             GROUP BY product_id,reviewer_id HAVING count(*)>1) d) AS duplicate_groups
                    FROM product_reviews r LEFT JOIN digital_products p ON p.id=r.product_id
                """)
            if "dsp_wallets" in table_set:
                out["dsp_wallet_summary"] = _one(conn, """
                    SELECT count(*) AS wallets,COALESCE(sum(balance_dsp),0) AS balance,
                           COALESCE(sum(frozen_balance),0) AS frozen,
                           COALESCE(sum(total_earned),0) AS earned,COALESCE(sum(total_spent),0) AS spent,
                           count(*) FILTER (WHERE balance_dsp<0 OR frozen_balance<0 OR frozen_balance>balance_dsp) AS invalid_rows
                    FROM dsp_wallets
                """)
            if "dsp_transactions" in table_set:
                out["dsp_transactions"] = _rows(conn, """
                    SELECT transaction_type::text AS transaction_type,status::text AS status,
                           count(*) AS rows,COALESCE(sum(amount),0) AS amount
                    FROM dsp_transactions GROUP BY transaction_type::text,status::text
                    ORDER BY transaction_type::text,status::text
                """)
                out["duplicate_dsp_references"] = _rows(conn, """
                    SELECT reference_type,reference_id,count(*) AS rows,COALESCE(sum(amount),0) AS amount
                    FROM dsp_transactions WHERE reference_id IS NOT NULL AND btrim(reference_id)<>''
                    GROUP BY reference_type,reference_id HAVING count(*)>1 ORDER BY rows DESC LIMIT 50
                """)
            if "product_types" in table_set:
                out["club_shop_products"] = _rows(conn, """
                    SELECT code,name,price,currency,validity_days,is_active,is_consumable,
                           has_affiliate_commission,affiliate_direct_amount,affiliate_direct_rate,
                           affiliate_indirect_amount,affiliate_indirect_rate
                    FROM product_types WHERE code IN ('club_membership','shop_purchase','efm_membership')
                    ORDER BY code
                """)
            if "commission_rules" in table_set:
                out["club_shop_commission_rules"] = _rows(conn, """
                    SELECT product_code,commission_type::text AS commission_type,direct_percentage,
                           indirect_percentage,max_levels,is_active FROM commission_rules
                    WHERE product_code IN ('club_membership','shop_purchase','efm_membership') ORDER BY product_code
                """)
            if {"deposits", "product_types"}.issubset(table_set):
                out["club_shop_deposits"] = _rows(conn, """
                    SELECT pt.code,d.status::text AS status,count(*) AS rows,
                           COALESCE(sum(d.amount),0) AS amount
                    FROM deposits d JOIN product_types pt ON pt.id=d.product_type_id
                    WHERE pt.code IN ('club_membership','shop_purchase')
                    GROUP BY pt.code,d.status::text ORDER BY pt.code,d.status::text
                """)
            if {"affiliate_commissions", "product_types"}.issubset(table_set):
                out["club_shop_affiliate_commissions"] = _rows(conn, """
                    SELECT pt.code,ac.status::text AS status,count(*) AS rows,
                           COALESCE(sum(ac.commission_amount),0) AS amount,
                           count(*) FILTER (WHERE ac.deposit_id IS NULL) AS without_deposit
                    FROM affiliate_commissions ac
                    JOIN product_types pt ON pt.id=ac.product_type_id
                    WHERE pt.code IN ('club_membership','shop_purchase')
                    GROUP BY pt.code,ac.status::text ORDER BY pt.code,ac.status::text
                """)
            if "transaction_approvals" in table_set:
                out["club_transaction_approvals"] = _one(
                    conn, "SELECT count(*) AS rows FROM transaction_approvals"
                )
            if "journal_entries" in table_set:
                out["domain_journals"] = _rows(conn, """
                    SELECT CASE WHEN description ILIKE '%club%' THEN 'club'
                                WHEN description ILIKE '%shop%' OR description ILIKE '%digital%' THEN 'marketplace'
                                ELSE 'other' END AS domain,
                           count(*) AS rows,COALESCE(sum(total_debit),0) AS amount
                    FROM journal_entries
                    WHERE description ILIKE '%club%' OR description ILIKE '%shop%' OR description ILIKE '%digital%'
                    GROUP BY 1 ORDER BY 1
                """)
        finally:
            tx.rollback()
            engine.dispose()

    if "summary" in sys.argv[1:]:
        out.pop("columns", None)
        out.pop("constraints", None)
        out.pop("indexes", None)
    print(json.dumps(out, default=_json, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
