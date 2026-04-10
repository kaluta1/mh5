from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from app.models.accounting import ChartOfAccounts, AccountType
import logging

logger = logging.getLogger(__name__)


def _pg_column_exists_public(db: Session, table: str, column: str) -> bool:
    """True if column exists on public.table (Neon/SQLAlchemy reflection can disagree with ORM)."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t
              AND column_name = :c
            LIMIT 1
            """
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _chart_of_accounts_colset(db: Session) -> set:
    bind = db.get_bind()
    insp = inspect(bind)
    if not insp.has_table("chart_of_accounts"):
        return set()
    try:
        return {c["name"] for c in insp.get_columns("chart_of_accounts")}
    except Exception as e:
        logger.warning("Could not reflect chart_of_accounts: %s", e)
        return set()


def _ensure_chart_of_accounts_columns(db: Session) -> None:
    """
    Legacy databases may lack columns expected by ChartOfAccounts (ORM SELECT fails).
    Adds missing columns so init_chart_of_accounts can run without Alembic first.
    Uses a savepoint per DDL so a permission error on one ALTER does not abort the whole session.
    """
    bind = db.get_bind()
    insp = inspect(bind)
    if not insp.has_table("chart_of_accounts"):
        return
    try:
        ident = db.execute(text("SELECT current_user::text, current_database()::text")).first()
        if ident:
            logger.info("init_coa: DB role=%r database=%r (must match table owner to run ALTER)", ident[0], ident[1])
    except Exception:
        pass

    colset = _chart_of_accounts_colset(db)
    if not colset:
        return

    altered = False

    # Any ALTER TABLE requires table ownership in PostgreSQL, even ADD IF NOT EXISTS when the
    # column is already there — so skip DDL when information_schema says the column exists.
    need_balance = ("balance" not in colset) and (not _pg_column_exists_public(db, "chart_of_accounts", "balance"))
    if need_balance:
        try:
            with db.begin_nested():
                db.execute(
                    text(
                        "ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS balance NUMERIC(15, 2)"
                    )
                )
            altered = True
            logger.info("Added chart_of_accounts.balance (legacy DB)")
        except Exception as e:
            logger.warning(
                "Could not ADD chart_of_accounts.balance (need table owner?): %s — "
                "run backend/scripts/sql/fix_chart_of_accounts_columns.sql as owner",
                e,
            )

    need_updated_at = ("updated_at" not in colset) and (
        not _pg_column_exists_public(db, "chart_of_accounts", "updated_at")
    )
    if need_updated_at:
        try:
            with db.begin_nested():
                db.execute(
                    text(
                        "ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"
                    )
                )
                db.execute(
                    text(
                        "UPDATE chart_of_accounts SET updated_at = COALESCE(created_at, NOW()) "
                        "WHERE updated_at IS NULL"
                    )
                )
            altered = True
            logger.info("Added chart_of_accounts.updated_at (legacy DB)")
        except Exception as e:
            logger.warning(
                "Could not ADD chart_of_accounts.updated_at (need table owner?): %s",
                e,
            )

    # Legacy schemas (e.g. create_coa.sql / GraphQL) had NOT NULL columns omitted from ORM model.
    # Inserts must receive defaults when those columns are not in the INSERT.
    _legacy_defaults = [
        ("total_liabilities", "0"),
        ("credit_balance", "0"),
        ("debit_balance", "0"),
        ("normal_balance", "'debit'"),
    ]
    for col, default_sql in _legacy_defaults:
        if col in colset:
            try:
                with db.begin_nested():
                    db.execute(
                        text(
                            f"ALTER TABLE chart_of_accounts ALTER COLUMN {col} SET DEFAULT {default_sql}"
                        )
                    )
                altered = True
            except Exception as ex:
                logger.debug("Skip legacy default for %s: %s", col, ex)

    if altered:
        db.commit()
    else:
        db.rollback()


def init_chart_of_accounts(db: Session):
    """
    Initialise le Plan Comptable (Chart of Accounts) par défaut.
    """
    _ensure_chart_of_accounts_columns(db)

    has_balance = _pg_column_exists_public(db, "chart_of_accounts", "balance") or (
        "balance" in _chart_of_accounts_colset(db)
    )
    if not has_balance:
        raise RuntimeError(
            "chart_of_accounts.balance is missing and the app DB user could not ALTER the table. "
            "Check the DB role in logs (must match pg_tables.tableowner). Use the same DATABASE_URL "
            "user as neondb_owner, or run backend/scripts/sql/fix_chart_of_accounts_columns.sql in "
            "Neon SQL Editor on this exact database branch. Avoid read-replica URLs for DDL."
        )

    # Liste initiale des comptes
    accounts = [
        # ASSETS (1000)
        {"code": "1000", "name": "Assets", "type": AccountType.ASSET, "parent": None},
        {"code": "1001", "name": "Platform Wallet", "type": AccountType.ASSET, "parent": "1000"},
        {"code": "1200", "name": "Accounts Receivable", "type": AccountType.ASSET, "parent": "1000"},
        
        # LIABILITIES (2000)
        {"code": "2000", "name": "Liabilities", "type": AccountType.LIABILITY, "parent": None},
        {"code": "2001", "name": "Commissions Payable L1", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2002", "name": "Commissions Payable L2-10", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2003", "name": "Service Fees Payable (KYC)", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2100", "name": "User Funds Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2104", "name": "Founding Members Pool Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2110", "name": "Deferred Revenue - Annual Membership", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2111", "name": "Deferred Revenue - Founding Membership", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2112", "name": "Deferred Platform Fee - Club Subscriptions", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2120", "name": "Club Owner Subscription Payable (Agent)", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2130", "name": "Member Ad Revenue Share Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2200", "name": "GST Payable (Singapore)", "type": AccountType.LIABILITY, "parent": "2000"},
        
        # EQUITY (3000)
        {"code": "3000", "name": "Equity", "type": AccountType.EQUITY, "parent": None},
        {"code": "3001", "name": "Retained Earnings", "type": AccountType.EQUITY, "parent": "3000"},
        
        # REVENUE (4000)
        {"code": "4000", "name": "Revenue", "type": AccountType.REVENUE, "parent": None},
        {"code": "4001", "name": "KYC Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4002", "name": "Membership Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4003", "name": "Platform Revenue (Net - Membership & Fees)", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4004", "name": "Ad Revenue - Platform Retained", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4005", "name": "Cashout Fee Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4006", "name": "Club Platform Service Fee Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        
        # EXPENSES (5000)
        {"code": "5000", "name": "Expenses", "type": AccountType.EXPENSE, "parent": None},
        {"code": "5001", "name": "Commission Expense", "type": AccountType.EXPENSE, "parent": "5000"},
        {"code": "5002", "name": "KYC Provider Expense", "type": AccountType.EXPENSE, "parent": "5000"},
        {"code": "5003", "name": "Ad Revenue Share to Members (Expense)", "type": AccountType.EXPENSE, "parent": "5000"},
    ]
    
    # 1. Créer les comptes (Parents d'abord idéalement, mais ici on gère l'ordre manuellement)
    # On fait deux passes pour gérer les relations parent-enfant si besoin, 
    # mais simplifions en créant tout puis en liant si code présent.
    
    created_count = 0
    
    for acc_data in accounts:
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["code"]).first()
        if not existing:
            # Récupérer l'ID du parent si défini
            parent_id = None
            if acc_data["parent"]:
                parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["parent"]).first()
                if parent:
                    parent_id = parent.id
            
            new_account = ChartOfAccounts(
                account_code=acc_data["code"],
                account_name=acc_data["name"],
                account_type=acc_data["type"],
                parent_id=parent_id,
                is_active=True
            )
            db.add(new_account)
            # One row at a time: batched INSERT sends VARCHAR to PG enum and fails (DatatypeMismatch).
            db.flush()
            created_count += 1
            
    try:
        db.commit()
        if created_count > 0:
            logger.info(f"Initialized {created_count} accounts in Chart of Accounts")
    except Exception as e:
        logger.error(f"Error initializing CoA: {e}")
        db.rollback()
