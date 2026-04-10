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

    need_description = ("description" not in colset) and (
        not _pg_column_exists_public(db, "chart_of_accounts", "description")
    )
    if need_description:
        try:
            with db.begin_nested():
                db.execute(
                    text(
                        "ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS description TEXT"
                    )
                )
            altered = True
            logger.info("Added chart_of_accounts.description (legacy DB)")
        except Exception as e:
            logger.warning(
                "Could not ADD chart_of_accounts.description (need table owner?): %s",
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

    # Liste initiale des comptes (noms + descriptions alignés au modèle économique club / markup 20%).
    accounts = [
        # ASSETS (1000)
        {"code": "1000", "name": "Assets", "type": AccountType.ASSET, "parent": None},
        {
            "code": "1001",
            "name": "USDT Treasury (BSC)",
            "type": AccountType.ASSET,
            "parent": "1000",
            "description": "On-chain USDT (BEP-20) on BNB Smart Chain (BSC). Member and platform receipts post here (Dr 1001); "
            "settlements (e.g. Shufti) clear with Cr 1001. Not fiat cash or custodial wallet balance.",
        },
        {"code": "1200", "name": "Accounts Receivable", "type": AccountType.ASSET, "parent": "1000"},
        # LIABILITIES (2000)
        {"code": "2000", "name": "Liabilities", "type": AccountType.LIABILITY, "parent": None},
        {
            "code": "2001",
            "name": "Commissions Payable — Level 1 sponsor",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Accrued commission for the payer's Level 1 sponsor. For paid club membership subscriptions: "
            "10% of the 20% platform markup (member pays base × 1.2; markup is split from that 20%). "
            "Same account is used for other products' L1 commission accruals.",
        },
        {
            "code": "2002",
            "name": "Commissions Payable — Levels 2–10 sponsors",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Accrued commission for Levels 2–10. For club subs: 1% of the 20% markup per filled sponsor level. "
            "Missing sponsor levels are treated as platform revenue per policy. Also used for other L2–10 products.",
        },
        {
            "code": "2003",
            "name": "Accounts Payable - Shufti (KYC Provider)",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Pass-through to Shufti when KYC verification is performed (agent-style). "
            "Payment to provider: Dr 2003, Cr 1001. Not platform revenue.",
        },
        {"code": "2100", "name": "User Funds Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        {
            "code": "2104",
            "name": "Accrued Liability — Founding Members 10% Commission Pool",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "10% of gross on applicable flows (e.g. KYC verification fee, membership) accrued when revenue is "
            "recognized; pooled until calendar month-end allocation. Month-end: Dr 2104, Cr 2105 (member payables). "
            "Club markup: 10% of the 20% markup accrues here per policy.",
        },
        {
            "code": "2105",
            "name": "Payable - Founding Members (allocated)",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Member-level founding commission balances after month-end pool allocation (Dr 2104, Cr 2105). "
            "USDT withdrawals clear against user payables; cashout fee revenue uses 4005.",
        },
        {"code": "2110", "name": "Deferred Revenue - Annual Membership", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2111", "name": "Deferred Revenue - Founding Membership", "type": AccountType.LIABILITY, "parent": "2000"},
        {
            "code": "2112",
            "name": "Club subs — deferred / clearing (20% markup)",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Liability for the platform's 20% markup on paid club membership subscriptions: clearing, "
            "deferral, or unearned portion over the subscription term (monthly, quarterly, semi-annual, annual per club). "
            "Posting logic allocates markup to 2001, 2002, 2104, and revenue (4003/4006) per policy.",
        },
        {
            "code": "2113",
            "name": "Deferred Revenue - Verification (KYC)",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Unearned verification fees until KYC completes. Step 1 (USDT BSC in): Dr 1001, Cr 2113. "
            "Step 2 (Shufti/service performed): Dr 2113, Cr 4001 (net), Cr 2104 (10% founding pool accrual), Cr 2003 (Shufti). "
            "Sponsor commissions: separate Dr 5001 / Cr 2001–2002 entry when recognition posts.",
        },
        {
            "code": "2120",
            "name": "Club subs — payable to club owner (base fee)",
            "type": AccountType.LIABILITY,
            "parent": "2000",
            "description": "Pass-through to the club owner: the member's base subscription amount (owner's list price before "
            "platform markup). Not platform revenue. Billing cadence is set by the club owner (monthly, quarterly, "
            "semi-annual, or annual). Member total charge = base + 20% markup.",
        },
        {"code": "2130", "name": "Member Ad Revenue Share Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2200", "name": "GST Payable (Singapore)", "type": AccountType.LIABILITY, "parent": "2000"},
        # EQUITY (3000)
        {"code": "3000", "name": "Equity", "type": AccountType.EQUITY, "parent": None},
        {"code": "3001", "name": "Retained Earnings", "type": AccountType.EQUITY, "parent": "3000"},
        # REVENUE (4000)
        {"code": "4000", "name": "Revenue", "type": AccountType.REVENUE, "parent": None},
        {
            "code": "4001",
            "name": "Verification Fee Revenue",
            "type": AccountType.REVENUE,
            "parent": "4000",
            "description": "Net revenue when verification is performed: deferred 2113 released for gross less 10% founding "
            "pool (2104), less Shufti payable (2003), less sponsor commissions (recognized via 5001/2001–2002).",
        },
        {"code": "4002", "name": "Membership Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        {
            "code": "4003",
            "name": "Platform revenue — net (residual)",
            "type": AccountType.REVENUE,
            "parent": "4000",
            "description": "Residual platform revenue after accruals to sponsor commissions and pools — including the "
            "remainder of the club subscription 20% markup after 10% L1, 1%×9 L2–10, and 10% founding pool, "
            "plus other net membership and fee recognition.",
        },
        {"code": "4004", "name": "Ad Revenue - Platform Retained", "type": AccountType.REVENUE, "parent": "4000"},
        {
            "code": "4005",
            "name": "Cashout fee revenue",
            "type": AccountType.REVENUE,
            "parent": "4000",
            "description": "Revenue from affiliate/member commission cashouts: fee = 1% of the withdrawal request, "
            "minimum USD 20, maximum USD 1,000 per cashout; net is paid to the member from user funds.",
        },
        {
            "code": "4006",
            "name": "Club platform service fee (markup)",
            "type": AccountType.REVENUE,
            "parent": "4000",
            "description": "Recognized platform revenue from the 20% markup on paid club membership subscriptions "
            "(often used together with 2112 deferral and 4003 for the net remainder after accruals — follow posting policy).",
        },
        # EXPENSES (5000)
        {"code": "5000", "name": "Expenses", "type": AccountType.EXPENSE, "parent": None},
        {"code": "5001", "name": "Commission Expense", "type": AccountType.EXPENSE, "parent": "5000"},
        {"code": "5002", "name": "KYC Provider Expense", "type": AccountType.EXPENSE, "parent": "5000"},
        {"code": "5003", "name": "Ad Revenue Share to Members (Expense)", "type": AccountType.EXPENSE, "parent": "5000"},
    ]

    created_count = 0
    updated_count = 0

    for acc_data in accounts:
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["code"]).first()
        if not existing:
            parent_id = None
            if acc_data["parent"]:
                parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["parent"]).first()
                if parent:
                    parent_id = parent.id

            kwargs = dict(
                account_code=acc_data["code"],
                account_name=acc_data["name"],
                account_type=acc_data["type"],
                parent_id=parent_id,
                is_active=True,
            )
            if acc_data.get("description"):
                kwargs["description"] = acc_data["description"]
            new_account = ChartOfAccounts(**kwargs)
            db.add(new_account)
            db.flush()
            created_count += 1
        else:
            changed = False
            if existing.account_name != acc_data["name"]:
                existing.account_name = acc_data["name"]
                changed = True
            desc = acc_data.get("description")
            if desc is not None and getattr(existing, "description", None) != desc:
                existing.description = desc
                changed = True
            if changed:
                updated_count += 1

    try:
        db.commit()
        if created_count > 0:
            logger.info("Initialized %s new accounts in Chart of Accounts", created_count)
        if updated_count > 0:
            logger.info("Updated %s existing CoA rows (names/descriptions — club membership model)", updated_count)
    except Exception as e:
        logger.error(f"Error initializing CoA: {e}")
        db.rollback()
