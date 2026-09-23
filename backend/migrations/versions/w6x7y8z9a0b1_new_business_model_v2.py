"""New MyHigh5 business model (NEW_V2): direct affiliate, Referral Pool, Leaders, marketplace.

Revision ID: w6x7y8z9a0b1
Revises: c9d0e1f2a3b4, s3t4u5v6w7x8, v5w6x7y8z9a0
Create Date: 2026-09-23

Additive only. No existing row is updated or deleted:
- new nullable columns on journal_entries / deposits / affiliate_commissions / users
  (legacy rows keep NULL = LEGACY_V1; nothing is back-stamped);
- new tables for revenue policy, revenue subledger, Referral Pool, Leaders, marketplace;
- insert-if-missing reference data (new accounts, revenue policies, pool config,
  the referral_pool_entry product and the NEW_V2 version row whose effective_at is the
  moment this migration runs).
Merges the three existing heads into one.
"""
from alembic import op
from sqlalchemy.orm import Session


revision = "w6x7y8z9a0b1"
down_revision = ("c9d0e1f2a3b4", "s3t4u5v6w7x8", "v5w6x7y8z9a0")
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def upgrade() -> None:
    # --- structured linkage / version stamps on existing tables (nullable, no backfill)
    for stmt in (
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS business_model_version VARCHAR(20)",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS source_type VARCHAR(40)",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS source_id INTEGER",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS posting_type VARCHAR(40)",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(160)",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS reverses_entry_id INTEGER REFERENCES journal_entries(id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entries_idempotency_key ON journal_entries (idempotency_key)",
        "CREATE INDEX IF NOT EXISTS ix_journal_entries_source ON journal_entries (source_type, source_id)",
        "ALTER TABLE deposits ADD COLUMN IF NOT EXISTS business_model_version VARCHAR(20)",
        "ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS business_model_version VARCHAR(20)",
        "ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS revenue_category VARCHAR(50)",
        "ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS source_type VARCHAR(40)",
        "ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS source_id INTEGER",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_commissions_source_user "
        "ON affiliate_commissions (source_type, source_id, user_id) WHERE source_type IS NOT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sponsor_source VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sponsor_assigned_at TIMESTAMP",
    ):
        op.execute(stmt)

    # --- new tables
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_model_versions ({_BASE},
            version VARCHAR(20) NOT NULL UNIQUE,
            effective_at TIMESTAMP NOT NULL,
            notes TEXT)""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS revenue_policies ({_BASE},
            model_version VARCHAR(20) NOT NULL,
            product_code VARCHAR(50) NOT NULL,
            revenue_category VARCHAR(50) NOT NULL,
            revenue_account_code VARCHAR(20) NOT NULL,
            deferred_account_code VARCHAR(20),
            provider_cost_rate NUMERIC(7,4) NOT NULL DEFAULT 0,
            provider_cost_fixed NUMERIC(15,2) NOT NULL DEFAULT 0,
            provider_payable_account_code VARCHAR(20),
            commission_eligible BOOLEAN NOT NULL DEFAULT false,
            commission_rate NUMERIC(7,4) NOT NULL DEFAULT 0,
            leaders_revenue_eligible BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            notes TEXT,
            CONSTRAINT uq_revenue_policy_version_product UNIQUE (model_version, product_code))""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS revenue_recognitions ({_BASE},
            model_version VARCHAR(20) NOT NULL,
            source_type VARCHAR(40) NOT NULL,
            source_id INTEGER NOT NULL,
            idempotency_key VARCHAR(160) NOT NULL UNIQUE,
            user_id INTEGER REFERENCES users(id),
            product_code VARCHAR(50) NOT NULL,
            revenue_category VARCHAR(50) NOT NULL,
            gross_amount NUMERIC(15,2) NOT NULL,
            seller_base_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            provider_cost_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            website_revenue_amount NUMERIC(15,2) NOT NULL,
            commission_eligible BOOLEAN NOT NULL DEFAULT false,
            leaders_revenue_eligible BOOLEAN NOT NULL DEFAULT false,
            recognized_at TIMESTAMP NOT NULL,
            journal_entry_id INTEGER REFERENCES journal_entries(id),
            reverses_id INTEGER REFERENCES revenue_recognitions(id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_revenue_recognitions_source ON revenue_recognitions (source_type, source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_revenue_recognitions_recognized_at ON revenue_recognitions (recognized_at)")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_config ({_BASE},
            capacity INTEGER NOT NULL DEFAULT 10000,
            price_product_code VARCHAR(50) NOT NULL DEFAULT 'referral_pool_entry',
            reservation_minutes INTEGER NOT NULL DEFAULT 90,
            assignment_method VARCHAR(40) NOT NULL DEFAULT 'FAIR_RANDOM_V1',
            is_open BOOLEAN NOT NULL DEFAULT true)""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_memberships ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL,
            seat_number INTEGER CHECK (seat_number >= 1),
            entitlement_source VARCHAR(40) NOT NULL,
            source_deposit_id INTEGER UNIQUE REFERENCES deposits(id),
            migration_run_id VARCHAR(64),
            reserved_at TIMESTAMP,
            reservation_expires_at TIMESTAMP,
            joined_at TIMESTAMP,
            ended_at TIMESTAMP,
            assignment_eligible BOOLEAN NOT NULL DEFAULT true,
            assignments_count INTEGER NOT NULL DEFAULT 0,
            last_assigned_at TIMESTAMP,
            notes TEXT)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_memberships_user_id ON referral_pool_memberships (user_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_pool_seat ON referral_pool_memberships (seat_number) "
        "WHERE status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_pool_one_open_seat_per_user ON referral_pool_memberships (user_id) "
        "WHERE status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')"
    )
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_assignments ({_BASE},
            referred_user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            pool_member_user_id INTEGER NOT NULL REFERENCES users(id),
            membership_id INTEGER NOT NULL REFERENCES referral_pool_memberships(id),
            method VARCHAR(40) NOT NULL,
            candidate_count INTEGER NOT NULL,
            min_assignment_count INTEGER NOT NULL,
            assigned_at TIMESTAMP NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_assignments_pool_member_user_id ON referral_pool_assignments (pool_member_user_id)")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_migration_runs ({_BASE},
            run_id VARCHAR(64) NOT NULL UNIQUE,
            manifest_sha256 VARCHAR(64) NOT NULL,
            operator VARCHAR(120),
            automatic_eligible INTEGER NOT NULL DEFAULT 0,
            manual_review INTEGER NOT NULL DEFAULT 0,
            not_eligible INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0,
            manifest_json TEXT NOT NULL)""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS leaders_periods ({_BASE},
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            revenue_definition VARCHAR(60) NOT NULL,
            eligible_company_revenue NUMERIC(15,2) NOT NULL,
            pool_rate NUMERIC(7,4) NOT NULL,
            pool_amount NUMERIC(15,2) NOT NULL,
            max_members INTEGER NOT NULL,
            qualifying_count INTEGER NOT NULL DEFAULT 0,
            total_qualifying_commission NUMERIC(15,2) NOT NULL DEFAULT 0,
            allocated_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            snapshot_sha256 VARCHAR(64) NOT NULL,
            prepared_by_user_id INTEGER REFERENCES users(id),
            approved_by_user_id INTEGER REFERENCES users(id),
            posted_at TIMESTAMP,
            journal_entry_id INTEGER REFERENCES journal_entries(id),
            reversal_journal_entry_id INTEGER REFERENCES journal_entries(id),
            notes TEXT)""")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_leaders_one_live_period ON leaders_periods (period_year, period_month) "
        "WHERE status IN ('DRAFT','APPROVED','POSTED')"
    )
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS leaders_allocation_lines ({_BASE},
            period_id INTEGER NOT NULL REFERENCES leaders_periods(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            rank INTEGER NOT NULL,
            direct_commission_amount NUMERIC(15,2) NOT NULL,
            ratio NUMERIC(20,12) NOT NULL,
            reward_amount NUMERIC(15,2) NOT NULL,
            payout_status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
            CONSTRAINT uq_leaders_line_period_user UNIQUE (period_id, user_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leaders_allocation_lines_period_id ON leaders_allocation_lines (period_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leaders_allocation_lines_user_id ON leaders_allocation_lines (user_id)")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS market_orders ({_BASE},
            buyer_user_id INTEGER NOT NULL REFERENCES users(id),
            seller_user_id INTEGER NOT NULL REFERENCES users(id),
            item_type VARCHAR(40) NOT NULL,
            item_id INTEGER NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            seller_base_amount NUMERIC(15,2) NOT NULL,
            markup_rate NUMERIC(7,4) NOT NULL,
            markup_amount NUMERIC(15,2) NOT NULL,
            buyer_total_amount NUMERIC(15,2) NOT NULL,
            state VARCHAR(30) NOT NULL,
            custodian_provider VARCHAR(40),
            custodian_reference VARCHAR(160) UNIQUE,
            business_model_version VARCHAR(20) NOT NULL,
            funded_at TIMESTAMP, fulfilled_at TIMESTAMP, confirmed_at TIMESTAMP,
            released_at TIMESTAMP, markup_settled_at TIMESTAMP, refunded_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_orders_buyer_user_id ON market_orders (buyer_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_orders_seller_user_id ON market_orders (seller_user_id)")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS market_order_events ({_BASE},
            order_id INTEGER NOT NULL REFERENCES market_orders(id),
            from_state VARCHAR(30),
            to_state VARCHAR(30) NOT NULL,
            actor_user_id INTEGER REFERENCES users(id),
            actor_role VARCHAR(20) NOT NULL,
            external_event_id VARCHAR(160) UNIQUE,
            note TEXT)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_order_events_order_id ON market_order_events (order_id)")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS market_disputes ({_BASE},
            order_id INTEGER NOT NULL REFERENCES market_orders(id),
            opened_by_user_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
            resolution_note TEXT,
            resolved_by_user_id INTEGER REFERENCES users(id),
            resolved_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_disputes_order_id ON market_disputes (order_id)")

    # --- reference data (insert-if-missing; never overwrites)
    from app.services.new_model_reference_data import seed_new_model_reference_data

    session = Session(bind=op.get_bind())
    seed_new_model_reference_data(session)
    session.flush()


def downgrade() -> None:
    # Financial tables are never dropped automatically. Reverting the application code is the
    # supported rollback; the additive schema is harmless to the previous release.
    raise RuntimeError("w6x7y8z9a0b1 is not auto-downgradable; roll back the application release instead")
