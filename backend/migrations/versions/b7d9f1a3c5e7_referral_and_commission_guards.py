"""Database guards for referrals and commissions.

Revision ID: b7d9f1a3c5e7
Revises: a8c0e2f4b6d8
Create Date: 2026-10-16

Additive only; no row is changed. Each guard is checked against the existing
data first and the migration STOPS (nothing created) if any row would violate
it, naming the guard.

users
  * ck_users_sponsor_not_self: nobody sponsors themselves.
  * trigger trg_users_sponsor_no_cycle (BEFORE UPDATE OF sponsor_id): refuses
    a new sponsor whose own ancestors include the member (a cycle). It walks
    at most 1,000 ancestors and stops quietly at a loop that does NOT involve
    the member, so a historical loop elsewhere never blocks an unrelated change
    or a registration. A new row (INSERT) has no descendants and cannot close
    a cycle; the CHECK above covers sponsor_id = id. Sponsor changes take one
    transaction-scoped advisory lock, so two concurrent changes cannot each
    pass and close a cycle together.

affiliate_commissions
  * ck_affiliate_commissions_amount_positive: commission_amount > 0.
  * ck_affiliate_commissions_level_range: level 1..10.
  * ck_affiliate_commissions_new_model_level_one: a NEW_V2 commission is level 1.
  * uq_affiliate_commissions_deposit_user / uq_affiliate_commissions_source_user:
    created if missing (declared by earlier revisions; production lacked the
    second one).

Downgrade removes the trigger, its function and the three CHECKs. It keeps
the two unique indexes: they belong to the earlier revisions' intent.
"""
from alembic import op

revision = "b7d9f1a3c5e7"
down_revision = "a8c0e2f4b6d8"
branch_labels = None
depends_on = None

_CHECKS = (
    ("users", "ck_users_sponsor_not_self", "sponsor_id IS NULL OR sponsor_id <> id"),
    ("affiliate_commissions", "ck_affiliate_commissions_amount_positive", "commission_amount > 0"),
    ("affiliate_commissions", "ck_affiliate_commissions_level_range", "level BETWEEN 1 AND 10"),
    ("affiliate_commissions", "ck_affiliate_commissions_new_model_level_one",
     "COALESCE(business_model_version, '') <> 'NEW_V2' OR level = 1"),
)


def upgrade() -> None:
    # 1. Existing data first: stop, naming the guard, if anything would violate it.
    for table, name, condition in _CHECKS:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM {table} WHERE NOT ({condition})) THEN
                    RAISE EXCEPTION 'existing {table} rows violate {name}; nothing was changed';
                END IF;
            END $$""")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM affiliate_commissions WHERE deposit_id IS NOT NULL
                       GROUP BY deposit_id, user_id HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'duplicate (deposit_id, user_id) commissions exist; nothing was changed';
            END IF;
            IF EXISTS (SELECT 1 FROM affiliate_commissions WHERE source_type IS NOT NULL
                       GROUP BY source_type, source_id, user_id HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'duplicate (source_type, source_id, user_id) commissions exist; nothing was changed';
            END IF;
        END $$""")

    # 2. CHECKs (added only if absent).
    for table, name, condition in _CHECKS:
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
                    ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition});
                END IF;
            END $$""")

    # 3. Unique indexes (if missing).
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_commissions_deposit_user
                  ON affiliate_commissions (deposit_id, user_id) WHERE deposit_id IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_commissions_source_user
                  ON affiliate_commissions (source_type, source_id, user_id) WHERE source_type IS NOT NULL""")

    # 4. Cycle trigger.
    op.execute("""
        CREATE OR REPLACE FUNCTION mh5_users_sponsor_no_cycle() RETURNS trigger AS $$
        DECLARE
            cur INTEGER := NEW.sponsor_id;
            seen INTEGER[] := ARRAY[]::INTEGER[];
            steps INTEGER := 0;
        BEGIN
            IF NEW.sponsor_id IS NULL OR NEW.sponsor_id IS NOT DISTINCT FROM OLD.sponsor_id THEN
                RETURN NEW;
            END IF;
            -- Two changes at once (A under B, B under A) would each pass on its own:
            -- sponsor changes wait for each other, and the walk below sees the other's result.
            PERFORM pg_advisory_xact_lock(hashtext('mh5_users_sponsor_tree'));
            WHILE cur IS NOT NULL AND steps < 1000 LOOP
                IF cur = NEW.id THEN
                    RAISE EXCEPTION 'sponsor cycle: member % cannot be sponsored by % (an ancestor of % is %)',
                        NEW.id, NEW.sponsor_id, NEW.sponsor_id, NEW.id
                        USING ERRCODE = 'check_violation';
                END IF;
                IF cur = ANY(seen) THEN
                    RETURN NEW;      -- a historical loop that does not involve this member
                END IF;
                seen := seen || cur;
                SELECT sponsor_id INTO cur FROM users WHERE id = cur;
                steps := steps + 1;
            END LOOP;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_users_sponsor_no_cycle ON users")
    op.execute("""CREATE TRIGGER trg_users_sponsor_no_cycle BEFORE UPDATE OF sponsor_id ON users
                  FOR EACH ROW EXECUTE FUNCTION mh5_users_sponsor_no_cycle()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_sponsor_no_cycle ON users")
    op.execute("DROP FUNCTION IF EXISTS mh5_users_sponsor_no_cycle()")
    for table, name, _condition in _CHECKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
