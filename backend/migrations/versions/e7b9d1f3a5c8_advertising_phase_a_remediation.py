"""Advertising Phase A remediation (integration review D2, D3).

Revision ID: e7b9d1f3a5c8
Revises: d4f6a8b0c2e5
Create Date: 2026-11-04

Additive only. Nothing is backfilled: no member receives a geographic attestation for a past verification.
  * adv_geo_attestations: the city a member had on the profile when a proof of address was APPROVED. It is
    revoked when the profile city changes, so a changed city needs a new verification before it can count.
  * adv_bookings: status REVERSED (an earned day that fell below its threshold after invalid activity was
    reversed), reversed_at, reversal_reason.
  * adv_leads: status REVERSED (an accepted, charged lead reversed by a finance administrator), reversed_at,
    reversal_reason, reversed_by_user_id.
Downgrade refuses while any attestation or reversed booking / lead exists.
"""
import sqlalchemy as sa
from alembic import op

revision = "e7b9d1f3a5c8"
down_revision = "d4f6a8b0c2e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adv_geo_attestations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("kyc_verification_id", sa.Integer(), nullable=True),
        sa.Column("attested_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(40), nullable=True),
    )
    op.create_index("ix_adv_geo_attestation_user", "adv_geo_attestations", ["user_id", "revoked_at"])
    op.create_index("ix_adv_geo_attestations_id", "adv_geo_attestations", ["id"])

    op.execute("ALTER TABLE adv_bookings DROP CONSTRAINT IF EXISTS ck_adv_booking_status")
    op.execute("ALTER TABLE adv_bookings ADD CONSTRAINT ck_adv_booking_status "
               "CHECK (status IN ('BOOKED', 'EARNED', 'RETURNED', 'CANCELLED', 'REVERSED'))")
    op.add_column("adv_bookings", sa.Column("reversed_at", sa.DateTime(), nullable=True))
    op.add_column("adv_bookings", sa.Column("reversal_reason", sa.String(200), nullable=True))

    op.execute("ALTER TABLE adv_leads DROP CONSTRAINT IF EXISTS ck_adv_lead_status")
    op.execute("ALTER TABLE adv_leads ADD CONSTRAINT ck_adv_lead_status "
               "CHECK (status IN ('SUBMITTED', 'ACCEPTED', 'REJECTED', 'EXPIRED', 'REVERSED'))")
    op.add_column("adv_leads", sa.Column("reversed_at", sa.DateTime(), nullable=True))
    op.add_column("adv_leads", sa.Column("reversal_reason", sa.String(200), nullable=True))
    op.add_column("adv_leads", sa.Column("reversed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                                         nullable=True))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_geo_attestations)
               OR EXISTS (SELECT 1 FROM adv_bookings WHERE status = 'REVERSED' OR reversed_at IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_leads WHERE status = 'REVERSED' OR reversed_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Advertising Phase A remediation data exists: it cannot be dropped by downgrading e7b9d1f3a5c8';
            END IF;
        END $$;
    """)
    for name in ("reversed_by_user_id", "reversal_reason", "reversed_at"):
        op.drop_column("adv_leads", name)
    op.execute("ALTER TABLE adv_leads DROP CONSTRAINT IF EXISTS ck_adv_lead_status")
    op.execute("ALTER TABLE adv_leads ADD CONSTRAINT ck_adv_lead_status "
               "CHECK (status IN ('SUBMITTED', 'ACCEPTED', 'REJECTED', 'EXPIRED'))")
    for name in ("reversal_reason", "reversed_at"):
        op.drop_column("adv_bookings", name)
    op.execute("ALTER TABLE adv_bookings DROP CONSTRAINT IF EXISTS ck_adv_booking_status")
    op.execute("ALTER TABLE adv_bookings ADD CONSTRAINT ck_adv_booking_status "
               "CHECK (status IN ('BOOKED', 'EARNED', 'RETURNED', 'CANCELLED'))")
    op.drop_index("ix_adv_geo_attestations_id", table_name="adv_geo_attestations")
    op.drop_index("ix_adv_geo_attestation_user", table_name="adv_geo_attestations")
    op.drop_table("adv_geo_attestations")
