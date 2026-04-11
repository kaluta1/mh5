"""KYC: pending proof-of-address step, lock residential address, user.address_verified.

Revision ID: p8q9r0s1t2u3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "p8q9r0s1t2u3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kyc_verifications",
        sa.Column("residential_address_locked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "address_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("users", "address_verified", server_default=None)

    bind = op.get_bind()
    try:
        bind.execute(
            text(
                "ALTER TYPE kycstatus ADD VALUE IF NOT EXISTS 'pending_proof_of_address'"
            )
        )
    except Exception:
        try:
            bind.execute(text("ALTER TYPE kycstatus ADD VALUE 'pending_proof_of_address'"))
        except Exception:
            pass

    bind.execute(
        text(
            "UPDATE users SET address_verified = true "
            "WHERE identity_verified IS TRUE AND COALESCE(address_verified, false) IS NOT TRUE"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "address_verified")
    op.drop_column("kyc_verifications", "residential_address_locked_at")
    # PostgreSQL: cannot remove enum value easily; leave kycstatus value in place.
