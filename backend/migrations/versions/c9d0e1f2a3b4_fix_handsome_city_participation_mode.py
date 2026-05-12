"""Fix Handsome Contest duplicate: city / participate row must be participation.

Cards read ``contest_mode`` from DB; nomination mode forces a Country badge via
``_contest_card_level_for_round``. The city-level Handsome row must be
``contest_mode = participation`` so it appears under Participations as City.

Revision ID: c9d0e1f2a3b4
Revises: b4c5d6e7f8a9
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Obvious rows: stored city level or copy that mentions city participation
    conn.execute(
        sa.text(
            """
            UPDATE contest
            SET contest_mode = 'participation', level = 'city'
            WHERE contest_type = 'handsome'
              AND is_deleted = false
              AND (
                lower(level) = 'city'
                OR lower(coalesce(description, '')) LIKE '%participate%your city%'
                OR lower(coalesce(description, '')) LIKE '%in your city%'
              )
            """
        )
    )

    # 2) Country-level handsome that are clearly the nomination copy
    conn.execute(
        sa.text(
            """
            UPDATE contest
            SET contest_mode = 'nomination', level = 'country'
            WHERE contest_type = 'handsome'
              AND is_deleted = false
              AND lower(coalesce(level, '')) = 'country'
              AND coalesce(contest_mode, '') != 'participation'
              AND NOT (
                lower(coalesce(description, '')) LIKE '%participate%your city%'
                OR lower(coalesce(description, '')) LIKE '%in your city%'
              )
            """
        )
    )

    # 3) Fallback: exactly two active handsome contests still both nomination →
    #    move the one with fewer participants to participation + city (product rule).
    rows = conn.execute(
        sa.text(
            """
            SELECT id, coalesce(participant_count, 0) AS pc
            FROM contest
            WHERE contest_type = 'handsome' AND is_deleted = false
            ORDER BY id
            """
        )
    ).fetchall()

    if len(rows) != 2:
        return

    modes = conn.execute(
        sa.text(
            """
            SELECT id, lower(coalesce(contest_mode, '')) AS m
            FROM contest
            WHERE contest_type = 'handsome' AND is_deleted = false
            """
        )
    ).fetchall()
    if len(modes) != 2:
        return
    if modes[0][1] == "nomination" and modes[1][1] == "nomination":
        move_id = sorted(rows, key=lambda r: (int(r[1] or 0), int(r[0])))[0][0]
        conn.execute(
            sa.text(
                "UPDATE contest SET contest_mode = 'participation', level = 'city' WHERE id = :id"
            ),
            {"id": move_id},
        )


def downgrade() -> None:
    # Data fix — no safe automatic reversal.
    pass
