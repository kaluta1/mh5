#!/usr/bin/env python3
"""Idempotently reconcile the live schema without replaying legacy migrations.

The production database predates this repository's complete Alembic history and
uses an external consolidated revision marker. Replaying all historical
migrations would collide with existing tables. This script only adds structures
required by the current models; it never drops a table or column and it leaves
``alembic_version`` untouched.

Run without arguments for a read-only report, or with ``--apply`` after backup.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine  # noqa: E402


REQUIRED_COLUMNS = {
    "contestant_voting": {"vote_bucket_key"},
    "user_vote_rankings": {"round_id"},
    "member_fmp_ledger": {"id", "user_id", "source_type", "source_id", "points", "created_at"},
    "member_fmp_balances": {"user_id", "total_fmp", "updated_at"},
    "wallet": {"id", "user_id", "balance", "currency", "frozen_balance", "created_at", "updated_at"},
}


STATEMENTS = [
    "ALTER TABLE contestant_voting ADD COLUMN IF NOT EXISTS vote_bucket_key VARCHAR(128)",
    """
    UPDATE contestant_voting AS cv
    SET vote_bucket_key = CASE
        WHEN c.category_id IS NOT NULL THEN 'cat:' || c.category_id::text
        ELSE 'ty:' || COALESCE(c.contest_type, '') || ':' || COALESCE(c.contest_mode, '')
    END
    FROM contest AS c
    WHERE cv.contest_id = c.id
      AND (cv.vote_bucket_key IS NULL OR cv.vote_bucket_key = '')
    """,
    """
    UPDATE contestant_voting
    SET vote_bucket_key = 'ty:unknown:participation'
    WHERE vote_bucket_key IS NULL OR vote_bucket_key = ''
    """,
    "ALTER TABLE contestant_voting ALTER COLUMN vote_bucket_key SET NOT NULL",
    """
    CREATE INDEX IF NOT EXISTS ix_contestant_voting_user_season_bucket
    ON contestant_voting (user_id, season_id, vote_bucket_key)
    """,
    "ALTER TABLE user_vote_rankings ADD COLUMN IF NOT EXISTS round_id INTEGER",
    """
    UPDATE user_vote_rankings AS ranking
    SET round_id = contestant.round_id
    FROM contestants AS contestant
    WHERE ranking.contestant_id = contestant.id
      AND ranking.round_id IS NULL
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM user_vote_rankings WHERE round_id IS NULL) THEN
            RAISE EXCEPTION 'Cannot make user_vote_rankings.round_id required: unresolved rows remain';
        END IF;
    END $$
    """,
    "ALTER TABLE user_vote_rankings ALTER COLUMN round_id SET NOT NULL",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'user_vote_rankings_round_id_fkey'
        ) THEN
            ALTER TABLE user_vote_rankings
            ADD CONSTRAINT user_vote_rankings_round_id_fkey
            FOREIGN KEY (round_id) REFERENCES rounds(id) ON DELETE CASCADE;
        END IF;
    END $$
    """,
    "CREATE INDEX IF NOT EXISTS idx_vote_rankings_user_round ON user_vote_rankings (user_id, round_id)",
    "CREATE INDEX IF NOT EXISTS idx_vote_rankings_contestant ON user_vote_rankings (contestant_id)",
    "CREATE INDEX IF NOT EXISTS idx_vote_rankings_round ON user_vote_rankings (round_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS unique_user_round_contestant_vote
    ON user_vote_rankings (user_id, round_id, contestant_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS wallet (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
        balance NUMERIC(10, 2) NOT NULL DEFAULT 0,
        currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
        frozen_balance NUMERIC(10, 2) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_commissions_deposit_user
    ON affiliate_commissions (deposit_id, user_id)
    WHERE deposit_id IS NOT NULL
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verificationprovider') THEN
            ALTER TYPE verificationprovider ADD VALUE IF NOT EXISTS 'kaluta';
        END IF;
    END $$
    """,
]


def report() -> bool:
    inspector = inspect(engine)
    ok = True
    for table, required in REQUIRED_COLUMNS.items():
        if not inspector.has_table(table):
            print(f"MISSING TABLE: {table}")
            ok = False
            continue
        actual = {column["name"] for column in inspector.get_columns(table)}
        missing = sorted(required - actual)
        if missing:
            print(f"MISSING COLUMNS: {table}: {', '.join(missing)}")
            ok = False
        else:
            print(f"OK: {table}")

    with engine.connect() as connection:
        marker = connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars().all()
        duplicate_groups = connection.execute(
            text(
                """
                SELECT count(*) FROM (
                    SELECT deposit_id, user_id
                    FROM affiliate_commissions
                    WHERE deposit_id IS NOT NULL
                    GROUP BY deposit_id, user_id
                    HAVING count(*) > 1
                ) AS duplicates
                """
            )
        ).scalar_one()
    print(f"ALEMBIC MARKER (preserved): {', '.join(marker)}")
    print(f"DUPLICATE COMMISSION GROUPS: {duplicate_groups}")
    if duplicate_groups:
        print("REFUSING UNIQUE INDEX: duplicate commission groups require manual review")
        ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply additive reconciliation statements")
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        print("This reconciliation is PostgreSQL-only", file=sys.stderr)
        return 2

    print("BEFORE")
    before_ok = report()
    if not args.apply:
        print("READ-ONLY: pass --apply after taking a database backup")
        return 0 if before_ok else 1

    with engine.begin() as connection:
        duplicate_groups = connection.execute(
            text(
                """
                SELECT count(*) FROM (
                    SELECT deposit_id, user_id
                    FROM affiliate_commissions
                    WHERE deposit_id IS NOT NULL
                    GROUP BY deposit_id, user_id
                    HAVING count(*) > 1
                ) AS duplicates
                """
            )
        ).scalar_one()
        if duplicate_groups:
            raise RuntimeError("Duplicate affiliate commissions must be reviewed before reconciliation")
        for statement in STATEMENTS:
            connection.execute(text(statement))

    print("AFTER")
    return 0 if report() else 1


if __name__ == "__main__":
    raise SystemExit(main())
