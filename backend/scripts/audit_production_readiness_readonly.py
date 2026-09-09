#!/usr/bin/env python3
"""Prompt 10 production-readiness audit.

The script performs metadata inspection and bounded SELECTs inside an explicit
PostgreSQL READ ONLY transaction. It never emits credentials, raw SQL text from
other sessions, or row-level PII and always rolls its transaction back.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.sql.sqltypes import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.models  # noqa: E402,F401 - register all ORM tables
from app.db.base_class import Base  # noqa: E402
from app.db.session import engine  # noqa: E402


def _json(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _type_signature(value: Any) -> str:
    """Compare semantic ORM/inspector types without dialect spelling noise."""
    if isinstance(value, SmallInteger):
        return "smallint"
    if isinstance(value, BigInteger):
        return "bigint"
    if isinstance(value, Integer):
        return "integer"
    if isinstance(value, Numeric):
        return f"numeric({value.precision},{value.scale})"
    if isinstance(value, Float):
        return "float"
    if isinstance(value, Enum):
        labels = tuple(str(item) for item in (getattr(value, "enums", None) or ()))
        return f"enum{labels}"
    if isinstance(value, Text):
        return "text"
    if isinstance(value, String):
        return f"varchar({value.length})"
    if isinstance(value, DateTime):
        return f"datetime(tz={bool(value.timezone)})"
    if isinstance(value, Date):
        return "date"
    if isinstance(value, Boolean):
        return "boolean"
    if isinstance(value, ARRAY):
        return f"array({_type_signature(value.item_type)})"
    if isinstance(value, JSON):
        return "json"
    if isinstance(value, LargeBinary):
        return "binary"
    return value.__class__.__name__.lower()


def _fk_signature(fk: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(fk.get("constrained_columns") or ()),
        fk.get("referred_table"),
        tuple(fk.get("referred_columns") or ()),
    )


def _orm_fk_signatures(table) -> set[tuple[Any, ...]]:
    result = set()
    for constraint in table.foreign_key_constraints:
        result.add(
            (
                tuple(element.parent.name for element in constraint.elements),
                next(iter(constraint.elements)).column.table.name,
                tuple(element.column.name for element in constraint.elements),
            )
        )
    return result


def _expected_unique_sets(table) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for column in table.columns:
        if column.unique:
            result.add((column.name,))
    for constraint in table.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            result.add(tuple(column.name for column in constraint.columns))
    for index in table.indexes:
        if index.unique:
            result.add(tuple(column.name for column in index.columns))
    return result


def _db_type_signature(row: dict[str, Any], enum_labels: dict[str, tuple[str, ...]]) -> str:
    data_type = row["data_type"]
    udt_name = row["udt_name"]
    if data_type in {"smallint", "integer", "bigint", "text", "date", "boolean"}:
        return data_type
    if data_type in {"numeric", "decimal"}:
        return f'numeric({row["numeric_precision"]},{row["numeric_scale"]})'
    if data_type == "character varying":
        return f'varchar({row["character_maximum_length"]})'
    if data_type == "timestamp without time zone":
        return "datetime(tz=False)"
    if data_type == "timestamp with time zone":
        return "datetime(tz=True)"
    if data_type in {"json", "jsonb"}:
        return "json"
    if data_type == "ARRAY":
        return "array"
    if data_type == "USER-DEFINED" and udt_name in enum_labels:
        return f"enum{enum_labels[udt_name]}"
    return str(data_type).lower()


def _scalar(conn, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar_one() or 0)


def _has(columns: dict[str, set[str]], table: str, *names: str) -> bool:
    return table in columns and set(names).issubset(columns[table])


def main() -> int:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Production readiness audit requires PostgreSQL")

    orm_tables = set(Base.metadata.tables)

    # Fetch the live catalog in four bounded round trips. SQLAlchemy's generic
    # per-table reflection is intentionally avoided because it is too chatty for
    # a remote 167-table Neon database.
    with engine.connect() as catalog_conn:
        catalog_tx = catalog_conn.begin()
        try:
            catalog_conn.execute(text("SET TRANSACTION READ ONLY"))
            catalog_conn.execute(text("SET LOCAL statement_timeout = '10s'"))
            catalog_conn.execute(text("SET LOCAL lock_timeout = '1s'"))
            prod_tables = {
                row[0]
                for row in catalog_conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                )
            }
            column_rows = [
                dict(row._mapping)
                for row in catalog_conn.execute(
                    text(
                        "SELECT table_name,column_name,data_type,udt_name,is_nullable,"
                        "character_maximum_length,numeric_precision,numeric_scale "
                        "FROM information_schema.columns WHERE table_schema='public' "
                        "ORDER BY table_name,ordinal_position"
                    )
                )
            ]
            enum_rows = [
                dict(row._mapping)
                for row in catalog_conn.execute(
                    text(
                        "SELECT t.typname enum_name,e.enumlabel,e.enumsortorder "
                        "FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid "
                        "ORDER BY t.typname,e.enumsortorder"
                    )
                )
            ]
            fk_rows = [
                dict(row._mapping)
                for row in catalog_conn.execute(
                    text(
                        "SELECT tc.table_name,tc.constraint_name,kcu.column_name,"
                        "ccu.table_name referred_table,ccu.column_name referred_column,kcu.ordinal_position "
                        "FROM information_schema.table_constraints tc "
                        "JOIN information_schema.key_column_usage kcu "
                        "ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema "
                        "JOIN information_schema.constraint_column_usage ccu "
                        "ON tc.constraint_name=ccu.constraint_name AND tc.constraint_schema=ccu.constraint_schema "
                        "WHERE tc.constraint_schema='public' AND tc.constraint_type='FOREIGN KEY' "
                        "ORDER BY tc.table_name,tc.constraint_name,kcu.ordinal_position"
                    )
                )
            ]
            index_rows = [
                dict(row._mapping)
                for row in catalog_conn.execute(
                    text(
                        "SELECT t.relname table_name,i.relname index_name,ix.indisunique unique_index,"
                        "array_agg(a.attname ORDER BY ord.n) FILTER (WHERE a.attname IS NOT NULL) columns,"
                        "pg_get_expr(ix.indpred,ix.indrelid) predicate "
                        "FROM pg_class t JOIN pg_namespace ns ON ns.oid=t.relnamespace "
                        "JOIN pg_index ix ON ix.indrelid=t.oid JOIN pg_class i ON i.oid=ix.indexrelid "
                        "JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY ord(attnum,n) ON true "
                        "LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=ord.attnum "
                        "WHERE ns.nspname='public' GROUP BY t.relname,i.relname,ix.indisunique,ix.indpred,ix.indrelid "
                        "ORDER BY t.relname,i.relname"
                    )
                )
            ]
        finally:
            catalog_tx.rollback()

    enum_labels: dict[str, tuple[str, ...]] = {}
    for row in enum_rows:
        enum_labels[row["enum_name"]] = enum_labels.get(row["enum_name"], ()) + (row["enumlabel"],)
    actual_columns_by_table: dict[str, dict[str, dict[str, Any]]] = {}
    for row in column_rows:
        actual_columns_by_table.setdefault(row["table_name"], {})[row["column_name"]] = row
    prod_columns = {table: set(rows) for table, rows in actual_columns_by_table.items()}

    fk_groups: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for row in fk_rows:
        key = (row["table_name"], row["constraint_name"], row["referred_table"])
        group = fk_groups.setdefault(key, {"local": [], "remote": []})
        group["local"].append(row["column_name"])
        group["remote"].append(row["referred_column"])
    actual_fks_by_table: dict[str, set[tuple[Any, ...]]] = {}
    for (table, _name, remote_table), group in fk_groups.items():
        actual_fks_by_table.setdefault(table, set()).add(
            (tuple(group["local"]), remote_table, tuple(group["remote"]))
        )

    indexes_by_table: dict[str, list[dict[str, Any]]] = {}
    for row in index_rows:
        indexes_by_table.setdefault(row["table_name"], []).append(
            {
                "name": row["index_name"],
                "columns": list(row["columns"] or ()),
                "unique": bool(row["unique_index"]),
                "predicate": row["predicate"],
            }
        )

    schema_mismatches: list[dict[str, Any]] = []
    for table_name in sorted(orm_tables & prod_tables):
        orm_table = Base.metadata.tables[table_name]
        actual_column_rows = actual_columns_by_table.get(table_name, {})
        expected_names = set(orm_table.columns.keys())
        actual_names = set(actual_column_rows)
        item: dict[str, Any] = {
            "table": table_name,
            "missing_columns": sorted(expected_names - actual_names),
            "database_only_columns": sorted(actual_names - expected_names),
            "type_mismatches": [],
            "nullability_mismatches": [],
        }
        for column_name in sorted(expected_names & actual_names):
            expected = orm_table.columns[column_name]
            actual = actual_column_rows[column_name]
            expected_type = _type_signature(expected.type)
            actual_type = _db_type_signature(actual, enum_labels)
            if expected_type.startswith("array("):
                expected_type = "array"
            if expected_type != actual_type:
                item["type_mismatches"].append(
                    {"column": column_name, "orm": expected_type, "database": actual_type}
                )
            actual_nullable = actual["is_nullable"] == "YES"
            if bool(expected.nullable) != actual_nullable:
                item["nullability_mismatches"].append(
                    {
                        "column": column_name,
                        "orm": bool(expected.nullable),
                        "database": actual_nullable,
                    }
                )

        expected_fks = _orm_fk_signatures(orm_table)
        actual_fks = actual_fks_by_table.get(table_name, set())
        item["missing_fks"] = sorted(expected_fks - actual_fks, key=str)
        item["database_only_fks"] = sorted(actual_fks - expected_fks, key=str)

        expected_unique = _expected_unique_sets(orm_table)
        actual_unique = {
            tuple(index["columns"])
            for index in indexes_by_table.get(table_name, ())
            if index["unique"] and index["columns"]
        }
        item["missing_uniques"] = sorted(expected_unique - actual_unique, key=str)
        item["database_only_uniques"] = sorted(actual_unique - expected_unique, key=str)
        if any(value for key, value in item.items() if key != "table"):
            schema_mismatches.append(item)

    output: dict[str, Any] = {
        "schema": {
            "production_table_count": len(prod_tables),
            "orm_table_count": len(orm_tables),
            "orm_missing_tables": sorted(orm_tables - prod_tables),
            "database_only_tables": sorted(prod_tables - orm_tables),
            "mismatch_table_count": len(schema_mismatches),
            "mismatches": schema_mismatches,
        },
        "prechecks": {},
    }

    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '10s'"))
            conn.execute(text("SET LOCAL lock_timeout = '1s'"))
            output["identity"] = dict(
                conn.execute(
                    text(
                        "SELECT current_database() database, current_user db_user, "
                        "current_setting('transaction_read_only')::boolean read_only"
                    )
                ).one()._mapping
            )
            output["alembic_markers"] = [
                row[0]
                for row in conn.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                )
            ]
            p = output["prechecks"]

            if "votes" in prod_tables:
                p["historical_votes"] = _scalar(conn, "SELECT COUNT(*) FROM votes")
                if _has(prod_columns, "votes", "stage_id"):
                    p["votes_missing_stage"] = _scalar(conn, "SELECT COUNT(*) FROM votes WHERE stage_id IS NULL")

            if _has(prod_columns, "categories", "name"):
                p["category_duplicate_normalized_name_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT lower(trim(name)) FROM categories "
                    "GROUP BY 1 HAVING COUNT(*)>1) d",
                )
            if _has(prod_columns, "categories", "slug"):
                p["category_duplicate_normalized_slug_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT lower(trim(slug)) FROM categories "
                    "WHERE slug IS NOT NULL GROUP BY 1 HAVING COUNT(*)>1) d",
                )
                p["category_malformed_slugs"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM categories WHERE slug IS NOT NULL "
                    "AND slug !~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
                )
            if _has(prod_columns, "contest", "category_id", "is_active"):
                p["active_contests_missing_category"] = _scalar(
                    conn, "SELECT COUNT(*) FROM contest WHERE is_active IS TRUE AND category_id IS NULL"
                )

            if _has(prod_columns, "contestant_voting", "user_id", "season_id", "vote_bucket_key", "contestant_id"):
                p["contestant_voting_duplicate_bucket_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT user_id,season_id,vote_bucket_key,contestant_id "
                    "FROM contestant_voting GROUP BY 1,2,3,4 HAVING COUNT(*)>1) d",
                )
                p["contestant_voting_missing_bucket"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM contestant_voting WHERE vote_bucket_key IS NULL OR trim(vote_bucket_key)=''",
                )
            if _has(prod_columns, "contestant_voting", "position"):
                p["contestant_voting_invalid_position"] = _scalar(
                    conn, "SELECT COUNT(*) FROM contestant_voting WHERE position IS NULL OR position<1 OR position>5"
                )

            if _has(prod_columns, "user_vote_rankings", "user_id", "round_id", "contestant_id"):
                p["ranking_duplicate_user_round_contestant_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT user_id,round_id,contestant_id FROM user_vote_rankings "
                    "GROUP BY 1,2,3 HAVING COUNT(*)>1) d",
                )
                p["ranking_missing_round"] = _scalar(
                    conn, "SELECT COUNT(*) FROM user_vote_rankings WHERE round_id IS NULL"
                )

            if _has(prod_columns, "affiliate_commissions", "deposit_id", "user_id"):
                p["commission_duplicate_deposit_user_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT deposit_id,user_id FROM affiliate_commissions "
                    "WHERE deposit_id IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1) d",
                )
            if _has(prod_columns, "affiliate_commissions", "level", "commission_amount"):
                p["commission_invalid_level_or_amount"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM affiliate_commissions WHERE level<1 OR level>10 OR commission_amount<=0",
                )
            if _has(prod_columns, "affiliate_commissions", "deposit_id") and "deposits" in prod_tables:
                p["commission_orphan_deposit"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM affiliate_commissions c LEFT JOIN deposits d ON d.id=c.deposit_id "
                    "WHERE c.deposit_id IS NOT NULL AND d.id IS NULL",
                )

            if _has(prod_columns, "deposits", "external_payment_id"):
                p["deposit_duplicate_external_payment_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT external_payment_id FROM deposits "
                    "WHERE COALESCE(external_payment_id,'')<>'' GROUP BY 1 HAVING COUNT(*)>1) d",
                )
            if _has(prod_columns, "deposits", "order_id"):
                p["deposit_duplicate_order_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT order_id FROM deposits WHERE COALESCE(order_id,'')<>'' "
                    "GROUP BY 1 HAVING COUNT(*)>1) d",
                )
            if _has(prod_columns, "deposits", "status"):
                p["deposit_status_counts"] = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            "SELECT status::text status,COUNT(*) rows FROM deposits "
                            "GROUP BY status::text ORDER BY status::text"
                        )
                    )
                ]

            if _has(prod_columns, "kyc_verifications", "provider", "status"):
                p["kyc_provider_status_counts"] = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            "SELECT provider::text provider,status::text status,COUNT(*) rows "
                            "FROM kyc_verifications GROUP BY provider::text,status::text "
                            "ORDER BY provider::text,status::text"
                        )
                    )
                ]

            if _has(prod_columns, "affiliate_cashout_requests", "payout_reference"):
                p["cashout_duplicate_payout_reference_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT payout_reference FROM affiliate_cashout_requests "
                    "WHERE COALESCE(payout_reference,'')<>'' GROUP BY 1 HAVING COUNT(*)>1) d",
                )
            if _has(prod_columns, "affiliate_cashout_requests", "idempotency_key"):
                p["cashout_duplicate_idempotency_groups"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM (SELECT idempotency_key FROM affiliate_cashout_requests "
                    "WHERE COALESCE(idempotency_key,'')<>'' GROUP BY 1 HAVING COUNT(*)>1) d",
                )
            else:
                p["cashout_idempotency_column_present"] = False

            p["provider_event_table_present"] = any(
                name in prod_tables for name in ("provider_events", "webhook_events", "integration_events")
            )
            p["refund_table_present"] = any(
                name in prod_tables for name in ("refunds", "payment_refunds", "financial_refunds")
            )

            if {"journal_entries", "journal_lines"}.issubset(prod_tables):
                p["journal_integrity"] = dict(
                    conn.execute(
                        text(
                            "WITH t AS (SELECT entry_id,COUNT(*) lines,COALESCE(SUM(debit_amount),0) debit,"
                            "COALESCE(SUM(credit_amount),0) credit FROM journal_lines GROUP BY entry_id) "
                            "SELECT COUNT(*) journals,COUNT(*) FILTER(WHERE t.entry_id IS NULL) missing_lines,"
                            "COUNT(*) FILTER(WHERE t.lines<2) one_sided,"
                            "COUNT(*) FILTER(WHERE t.debit<>t.credit) unbalanced,"
                            "COUNT(*) FILTER(WHERE je.total_debit<>t.debit OR je.total_credit<>t.credit) header_mismatch "
                            "FROM journal_entries je LEFT JOIN t ON t.entry_id=je.id"
                        )
                    ).one()._mapping
                )

            if {"affiliate_commissions", "journal_lines", "chart_of_accounts"}.issubset(prod_tables):
                p["commission_subledger_vs_ledger"] = dict(
                    conn.execute(
                        text(
                            "WITH subledger AS ("
                            " SELECT COALESCE(SUM(commission_amount),0) outstanding"
                            " FROM affiliate_commissions WHERE status::text IN ('PENDING','APPROVED')"
                            "), ledger AS ("
                            " SELECT COALESCE(SUM(jl.credit_amount-jl.debit_amount),0) payable"
                            " FROM journal_lines jl JOIN chart_of_accounts coa ON coa.id=jl.account_id"
                            " WHERE coa.account_code IN ('2001','2002')"
                            ") SELECT subledger.outstanding commission_outstanding,"
                            "ledger.payable ledger_payable,ledger.payable-subledger.outstanding discrepancy"
                            " FROM subledger CROSS JOIN ledger"
                        )
                    ).one()._mapping
                )
                p["commission_source_ledger_mismatches"] = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            "WITH sources AS ("
                            " SELECT deposit_id,COUNT(*) commission_rows,SUM(commission_amount) commission_amount"
                            " FROM affiliate_commissions WHERE deposit_id IS NOT NULL"
                            " AND status::text IN ('PENDING','APPROVED','PAID') GROUP BY deposit_id"
                            "), posted AS ("
                            " SELECT s.deposit_id,COALESCE(SUM(jl.credit_amount-jl.debit_amount),0) payable_posted"
                            " FROM sources s LEFT JOIN journal_entries je"
                            " ON je.description ~ ('Deposit #'||s.deposit_id::text||'([^0-9]|$)')"
                            " LEFT JOIN journal_lines jl ON jl.entry_id=je.id"
                            " LEFT JOIN chart_of_accounts coa ON coa.id=jl.account_id"
                            " AND coa.account_code IN ('2001','2002')"
                            " WHERE coa.id IS NOT NULL OR je.id IS NULL GROUP BY s.deposit_id"
                            ") SELECT s.deposit_id,s.commission_rows,s.commission_amount,p.payable_posted,"
                            "p.payable_posted-s.commission_amount discrepancy FROM sources s"
                            " JOIN posted p ON p.deposit_id=s.deposit_id"
                            " WHERE p.payable_posted<>s.commission_amount ORDER BY s.deposit_id LIMIT 100"
                        )
                    )
                ]

            if _has(prod_columns, "wallets", "currency", "balance"):
                frozen = ",COALESCE(SUM(frozen_balance),0) frozen_balance" if _has(
                    prod_columns, "wallets", "frozen_balance"
                ) else ""
                p["plural_wallet_balances"] = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            "SELECT currency,COUNT(*) rows,COALESCE(SUM(balance),0) balance"
                            + frozen
                            + " FROM wallets GROUP BY currency ORDER BY currency"
                        )
                    )
                ]

            important_tables = {
                "votes", "contestant_voting", "user_vote_rankings", "contest", "contestants",
                "contest_seasons", "contest_stages", "categories", "page_views", "contest_likes",
                "contest_comments", "contestant_reactions", "contestant_shares", "deposits",
                "affiliate_commissions", "affiliate_cashout_requests", "journal_entries", "journal_lines",
                "audit_trail", "wallet", "wallets",
            }
            output["important_indexes"] = {
                table: [
                    index
                    for index in indexes_by_table.get(table, ())
                ]
                for table in sorted(important_tables & prod_tables)
            }

            output["connection_summary"] = [
                dict(row._mapping)
                for row in conn.execute(
                    text(
                        "SELECT COALESCE(NULLIF(application_name,''),'unspecified') application_name,state,"
                        "COUNT(*) connections,MAX(EXTRACT(EPOCH FROM (clock_timestamp()-xact_start))) "
                        "FILTER (WHERE xact_start IS NOT NULL)::bigint oldest_transaction_seconds,"
                        "MAX(EXTRACT(EPOCH FROM (clock_timestamp()-query_start))) "
                        "FILTER (WHERE state='active')::bigint oldest_active_query_seconds "
                        "FROM pg_stat_activity WHERE datname=current_database() GROUP BY 1,2 ORDER BY 1,2"
                    )
                )
            ]
        finally:
            tx.rollback()

    if "--summary" in sys.argv:
        substantive = []
        for mismatch in output["schema"]["mismatches"]:
            if any(
                mismatch[key]
                for key in (
                    "missing_columns",
                    "database_only_columns",
                    "type_mismatches",
                    "nullability_mismatches",
                    "missing_fks",
                    "missing_uniques",
                )
            ):
                substantive.append(
                    {
                        key: value
                        for key, value in mismatch.items()
                        if key not in {"database_only_fks", "database_only_uniques"}
                    }
                )
        output["schema"]["mismatches"] = substantive
        output["schema"]["mismatch_table_count"] = len(substantive)
        output.pop("important_indexes", None)

    if "--prechecks-only" in sys.argv:
        output = {
            "database": output.get("database"),
            "alembic_versions": output.get("alembic_versions"),
            "prechecks": output.get("prechecks"),
            "connection_summary": output.get("connection_summary"),
        }

    print(json.dumps(output, default=_json, indent=2, sort_keys=True))
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
