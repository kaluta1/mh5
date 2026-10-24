"""Multi-Unit Referral Pool: database foundation (P2). Schema only, nothing is activated.

Revision ID: a7c9e1f3b5d2
Revises: f2b4d6e8a0c1
Create Date: 2026-10-23

Additive. Every existing row (memberships, assignments, deposits, journals, account
2100 receipts, sponsor relationships) is left exactly as it is; no row is converted,
backfilled or rewritten.

New tables:
  * referral_pool_purchases    one row per pool deposit: how many $100 units it bought.
                               The deposit stays the payment record of truth; this row
                               only splits it into units (quantity x unit_price).
  * referral_pool_units        one row per unit (participation weight, never consumed),
                               unique per (purchase, unit_index); refund and ledger
                               references per unit for partial refunds.
  * referral_pool_rounds       quota rounds; at most one OPEN round (partial unique index).
  * referral_pool_round_slots  one slot per eligible unit and round, unique (round, unit).
  * referral_pool_pending      referrals waiting for a slot; one row per referred user.

Existing tables:
  * referral_pool_assignments  + round_id, slot_id (unique), unit_id, all nullable.
                               membership_id and min_assignment_count become nullable;
                               a check keeps every row either historical (membership)
                               or round-based (round + slot + unit). New assignments may
                               never name the referred user as their own sponsor (the
                               check is NOT VALID: historical rows are not re-judged).
  * referral_pool_config       optional limits (NULL = unlimited, the default) and two
                               switches, both false: nothing is sold or allocated.

Downgrade removes exactly what upgrade added and refuses while any round-based
assignment exists (it would have to delete or invent historical data). Re-running
the upgrade is a no-op.
"""
from alembic import op


revision = "a7c9e1f3b5d2"
down_revision = "f2b4d6e8a0c1"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def _constraint(table: str, name: str, definition: str) -> None:
    """Add a named constraint once (PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS)."""
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}'
                           AND conrelid = '{table}'::regclass) THEN
                ALTER TABLE {table} ADD CONSTRAINT {name} {definition};
            END IF;
        END $$""")


def upgrade() -> None:
    # --- configuration: optional limits (NULL = unlimited) and switches (off)
    for stmt in (
        "ALTER TABLE referral_pool_config ADD COLUMN IF NOT EXISTS multiunit_sales_enabled BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE referral_pool_config ADD COLUMN IF NOT EXISTS allocation_enabled BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE referral_pool_config ADD COLUMN IF NOT EXISTS max_units_per_member INTEGER",
        "ALTER TABLE referral_pool_config ADD COLUMN IF NOT EXISTS max_units_per_purchase INTEGER",
        "ALTER TABLE referral_pool_config ADD COLUMN IF NOT EXISTS max_active_units INTEGER",
    ):
        op.execute(stmt)
    _constraint("referral_pool_config", "ck_referral_pool_config_limits",
                "CHECK ((max_units_per_member IS NULL OR max_units_per_member >= 1) "
                "AND (max_units_per_purchase IS NULL OR max_units_per_purchase >= 1) "
                "AND (max_active_units IS NULL OR max_active_units >= 1))")

    # --- purchases: one per pool deposit
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_purchases ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id),
            deposit_id INTEGER NOT NULL REFERENCES deposits(id),
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(15,2) NOT NULL,
            total_amount NUMERIC(15,2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            status VARCHAR(30) NOT NULL DEFAULT 'PENDING_PAYMENT',
            refunded_quantity INTEGER NOT NULL DEFAULT 0,
            paid_at TIMESTAMP,
            units_created_at TIMESTAMP,
            notes TEXT,
            CONSTRAINT uq_referral_pool_purchase_deposit UNIQUE (deposit_id),
            CONSTRAINT ck_referral_pool_purchase_quantity CHECK (quantity >= 1),
            CONSTRAINT ck_referral_pool_purchase_price CHECK (unit_price > 0),
            CONSTRAINT ck_referral_pool_purchase_total CHECK (total_amount = quantity * unit_price),
            CONSTRAINT ck_referral_pool_purchase_refunded CHECK (refunded_quantity >= 0 AND refunded_quantity <= quantity),
            CONSTRAINT ck_referral_pool_purchase_status CHECK (status IN
                ('PENDING_PAYMENT','PAID','PARTIALLY_REFUNDED','REFUNDED','CANCELLED','HELD_FOR_REVIEW')))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_purchases_user_id ON referral_pool_purchases (user_id)")

    # --- units: one per $100, never consumed
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_units ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id),
            purchase_id INTEGER REFERENCES referral_pool_purchases(id),
            unit_index INTEGER,
            source VARCHAR(30) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            legacy_membership_id INTEGER REFERENCES referral_pool_memberships(id),
            activated_at TIMESTAMP,
            suspended_at TIMESTAMP,
            ended_at TIMESTAMP,
            status_reason TEXT,
            refunded_at TIMESTAMP,
            refund_reference VARCHAR(120),
            refund_journal_entry_id INTEGER REFERENCES journal_entries(id),
            revenue_recognition_id INTEGER REFERENCES revenue_recognitions(id),
            direct_commission_id INTEGER REFERENCES affiliate_commissions(id),
            CONSTRAINT uq_referral_pool_unit_purchase_index UNIQUE (purchase_id, unit_index),
            CONSTRAINT uq_referral_pool_unit_legacy_membership UNIQUE (legacy_membership_id),
            CONSTRAINT uq_referral_pool_unit_recognition UNIQUE (revenue_recognition_id),
            CONSTRAINT uq_referral_pool_unit_commission UNIQUE (direct_commission_id),
            CONSTRAINT ck_referral_pool_unit_index CHECK ((purchase_id IS NULL) = (unit_index IS NULL) AND (unit_index IS NULL OR unit_index >= 1)),
            CONSTRAINT ck_referral_pool_unit_source CHECK (source IN ('PAID','HISTORICAL_CONVERSION','ADMIN_GRANT')),
            CONSTRAINT ck_referral_pool_unit_paid_has_purchase CHECK (source <> 'PAID' OR purchase_id IS NOT NULL),
            CONSTRAINT ck_referral_pool_unit_historical_has_membership CHECK (source <> 'HISTORICAL_CONVERSION' OR legacy_membership_id IS NOT NULL),
            CONSTRAINT ck_referral_pool_unit_status CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','REFUNDED','REVOKED')),
            CONSTRAINT ck_referral_pool_unit_amount CHECK (amount >= 0),
            CONSTRAINT ck_referral_pool_unit_active_dated CHECK (status <> 'ACTIVE' OR activated_at IS NOT NULL),
            CONSTRAINT ck_referral_pool_unit_refund_dated CHECK (status <> 'REFUNDED' OR refunded_at IS NOT NULL))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_units_user_status ON referral_pool_units (user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_units_active ON referral_pool_units (id) WHERE status = 'ACTIVE'")

    # --- rounds: at most one OPEN
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_rounds ({_BASE},
            round_number INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            method VARCHAR(40) NOT NULL DEFAULT 'QUOTA_ROUND_V1',
            opened_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            closed_reason TEXT,
            total_slots INTEGER NOT NULL,
            filled_slots INTEGER NOT NULL DEFAULT 0,
            void_slots INTEGER NOT NULL DEFAULT 0,
            snapshot_sha256 VARCHAR(64) NOT NULL,
            CONSTRAINT uq_referral_pool_round_number UNIQUE (round_number),
            CONSTRAINT ck_referral_pool_round_number CHECK (round_number >= 1),
            CONSTRAINT ck_referral_pool_round_status CHECK (status IN ('OPEN','COMPLETED','CLOSED')),
            CONSTRAINT ck_referral_pool_round_counts CHECK (total_slots >= 1 AND filled_slots >= 0 AND void_slots >= 0
                AND filled_slots + void_slots <= total_slots),
            CONSTRAINT ck_referral_pool_round_completed CHECK (status <> 'COMPLETED' OR filled_slots + void_slots = total_slots),
            CONSTRAINT ck_referral_pool_round_ended CHECK ((status = 'OPEN') = (completed_at IS NULL)))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_pool_one_open_round ON referral_pool_rounds (status) "
               "WHERE status = 'OPEN'")

    # --- slots: one per eligible unit and round
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_round_slots ({_BASE},
            round_id INTEGER NOT NULL REFERENCES referral_pool_rounds(id),
            unit_id INTEGER NOT NULL REFERENCES referral_pool_units(id),
            member_user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            filled_at TIMESTAMP,
            voided_at TIMESTAMP,
            void_reason VARCHAR(60),
            CONSTRAINT uq_referral_pool_slot_round_unit UNIQUE (round_id, unit_id),
            CONSTRAINT ck_referral_pool_slot_status CHECK (status IN ('OPEN','FILLED','VOID')),
            CONSTRAINT ck_referral_pool_slot_filled_dated CHECK ((status = 'FILLED') = (filled_at IS NOT NULL)),
            CONSTRAINT ck_referral_pool_slot_void_dated CHECK ((status = 'VOID') = (voided_at IS NOT NULL)))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_slots_round_status ON referral_pool_round_slots (round_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_slots_unit ON referral_pool_round_slots (unit_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_slots_member ON referral_pool_round_slots (member_user_id)")

    # --- assignments: round-based references next to the historical ones
    for stmt in (
        "ALTER TABLE referral_pool_assignments ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES referral_pool_rounds(id)",
        "ALTER TABLE referral_pool_assignments ADD COLUMN IF NOT EXISTS slot_id INTEGER REFERENCES referral_pool_round_slots(id)",
        "ALTER TABLE referral_pool_assignments ADD COLUMN IF NOT EXISTS unit_id INTEGER REFERENCES referral_pool_units(id)",
        "ALTER TABLE referral_pool_assignments ALTER COLUMN membership_id DROP NOT NULL",
        "ALTER TABLE referral_pool_assignments ALTER COLUMN min_assignment_count DROP NOT NULL",
    ):
        op.execute(stmt)
    _constraint("referral_pool_assignments", "uq_referral_pool_assignment_slot", "UNIQUE (slot_id)")
    _constraint("referral_pool_assignments", "ck_referral_pool_assignment_round_refs",
                "CHECK ((round_id IS NULL) = (slot_id IS NULL) AND (slot_id IS NULL) = (unit_id IS NULL))")
    _constraint("referral_pool_assignments", "ck_referral_pool_assignment_kind",
                "CHECK ((slot_id IS NULL AND membership_id IS NOT NULL AND min_assignment_count IS NOT NULL) "
                "OR (slot_id IS NOT NULL AND membership_id IS NULL))")
    _constraint("referral_pool_assignments", "ck_referral_pool_assignment_not_self",
                "CHECK (referred_user_id <> pool_member_user_id) NOT VALID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_assignments_round ON referral_pool_assignments (round_id)")

    # --- pending queue: one row per referred user
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_pending ({_BASE},
            referred_user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'WAITING',
            trigger_event VARCHAR(30) NOT NULL DEFAULT 'KYC_APPROVED',
            kyc_verification_id INTEGER REFERENCES kyc_verifications(id),
            enqueued_at TIMESTAMP NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TIMESTAMP,
            last_error VARCHAR(200),
            resolved_at TIMESTAMP,
            resolution_reason VARCHAR(60),
            assignment_id INTEGER REFERENCES referral_pool_assignments(id),
            CONSTRAINT uq_referral_pool_pending_user UNIQUE (referred_user_id),
            CONSTRAINT uq_referral_pool_pending_assignment UNIQUE (assignment_id),
            CONSTRAINT ck_referral_pool_pending_status CHECK (status IN ('WAITING','ASSIGNED','CANCELLED')),
            CONSTRAINT ck_referral_pool_pending_trigger CHECK (trigger_event IN ('KYC_APPROVED')),
            CONSTRAINT ck_referral_pool_pending_attempts CHECK (attempts >= 0),
            CONSTRAINT ck_referral_pool_pending_assigned CHECK ((status = 'ASSIGNED') = (assignment_id IS NOT NULL)),
            CONSTRAINT ck_referral_pool_pending_resolved CHECK ((status = 'WAITING') = (resolved_at IS NULL)))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_pending_waiting ON referral_pool_pending (enqueued_at, id) "
               "WHERE status = 'WAITING'")


def downgrade() -> None:
    # Round-based assignments cannot be expressed in the old schema (membership_id NOT NULL):
    # refuse instead of deleting or inventing history.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'referral_pool_assignments' AND column_name = 'slot_id') THEN
                IF EXISTS (SELECT 1 FROM referral_pool_assignments WHERE slot_id IS NOT NULL) THEN
                    RAISE EXCEPTION 'referral_pool_assignments holds round-based assignments; downgrade refused';
                END IF;
            END IF;
        END $$""")
    op.execute("DROP TABLE IF EXISTS referral_pool_pending")
    for stmt in (
        "DROP INDEX IF EXISTS ix_referral_pool_assignments_round",
        "ALTER TABLE referral_pool_assignments DROP CONSTRAINT IF EXISTS ck_referral_pool_assignment_not_self",
        "ALTER TABLE referral_pool_assignments DROP CONSTRAINT IF EXISTS ck_referral_pool_assignment_kind",
        "ALTER TABLE referral_pool_assignments DROP CONSTRAINT IF EXISTS ck_referral_pool_assignment_round_refs",
        "ALTER TABLE referral_pool_assignments DROP CONSTRAINT IF EXISTS uq_referral_pool_assignment_slot",
        "ALTER TABLE referral_pool_assignments DROP COLUMN IF EXISTS unit_id",
        "ALTER TABLE referral_pool_assignments DROP COLUMN IF EXISTS slot_id",
        "ALTER TABLE referral_pool_assignments DROP COLUMN IF EXISTS round_id",
        "ALTER TABLE referral_pool_assignments ALTER COLUMN min_assignment_count SET NOT NULL",
        "ALTER TABLE referral_pool_assignments ALTER COLUMN membership_id SET NOT NULL",
    ):
        op.execute(stmt)
    op.execute("DROP TABLE IF EXISTS referral_pool_round_slots")
    op.execute("DROP TABLE IF EXISTS referral_pool_rounds")
    op.execute("DROP TABLE IF EXISTS referral_pool_units")
    op.execute("DROP TABLE IF EXISTS referral_pool_purchases")
    for stmt in (
        "ALTER TABLE referral_pool_config DROP CONSTRAINT IF EXISTS ck_referral_pool_config_limits",
        "ALTER TABLE referral_pool_config DROP COLUMN IF EXISTS max_active_units",
        "ALTER TABLE referral_pool_config DROP COLUMN IF EXISTS max_units_per_purchase",
        "ALTER TABLE referral_pool_config DROP COLUMN IF EXISTS max_units_per_member",
        "ALTER TABLE referral_pool_config DROP COLUMN IF EXISTS allocation_enabled",
        "ALTER TABLE referral_pool_config DROP COLUMN IF EXISTS multiunit_sales_enabled",
    ):
        op.execute(stmt)
