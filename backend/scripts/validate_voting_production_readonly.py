"""Read-only production voting profile used by Prompt 2 validation.

The script prints aggregate/schema evidence only.  It explicitly marks the
transaction read-only before issuing any catalog or application-table query.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


QUERIES = {
    "identity": "SELECT current_database() AS database, current_user AS db_user",
    "voting_counts": """
        SELECT name, CASE WHEN to_regclass('public.' || name) IS NULL THEN NULL
                          ELSE (xpath('/row/c/text()', query_to_xml(
                              format('SELECT count(*) AS c FROM public.%I', name),
                              false, true, '')))[1]::text::bigint END AS row_count
        FROM unnest(ARRAY[
            'app_votes', 'contest_votes', 'contestant_rankings',
            'contestant_voting', 'user_vote_rankings', 'vote_rankings',
            'vote_sessions', 'votes', 'voting_type'
        ]) AS name
        ORDER BY name
    """,
    "vote_date_range": """
        SELECT min(vote_date) AS first_vote, max(vote_date) AS last_vote,
               count(*) AS total_votes
        FROM votes
    """,
    "vote_statuses": """
        SELECT status::text AS status, count(*) AS rows
        FROM votes GROUP BY status::text ORDER BY status::text
    """,
    "vote_point_rules": """
        SELECT rank_position, points, count(*) AS rows
        FROM votes GROUP BY rank_position, points
        ORDER BY rank_position, points
    """,
    "vote_integrity": """
        SELECT
          count(*) FILTER (WHERE u.id IS NULL) AS missing_voter,
          count(*) FILTER (WHERE c.id IS NULL) AS missing_contestant,
          count(*) FILTER (WHERE st.id IS NULL) AS missing_stage,
          count(*) FILTER (WHERE cs.id IS NULL) AS missing_season,
          count(*) FILTER (WHERE cseason.contestant_id IS NULL) AS contestant_not_in_stage_season
        FROM votes v
        LEFT JOIN users u ON u.id = v.voter_id
        LEFT JOIN contestants c ON c.id = v.contestant_id
        LEFT JOIN contest_stages st ON st.id = v.stage_id
        LEFT JOIN contest_seasons cs ON cs.id = st.season_id
        LEFT JOIN contestant_seasons cseason
          ON cseason.contestant_id = v.contestant_id
         AND cseason.season_id = st.season_id
    """,
    "stage_vote_scope": """
        SELECT st.id AS stage_id, st.season_id, st.stage_level::text AS stage_level,
               st.status::text AS stage_status, st.start_date, st.end_date,
               cs.round_id, count(DISTINCT v.id) AS votes,
               count(DISTINCT csl.contest_id) AS linked_contests
        FROM contest_stages st
        JOIN contest_seasons cs ON cs.id = st.season_id
        LEFT JOIN votes v ON v.stage_id = st.id
        LEFT JOIN contest_season_links csl ON csl.season_id = st.season_id
        GROUP BY st.id, st.season_id, st.stage_level, st.status,
                 st.start_date, st.end_date, cs.round_id
        ORDER BY st.id
    """,
    "contest_resolution": """
        WITH season_contests AS (
          SELECT season_id, count(DISTINCT contest_id) AS candidates
          FROM contest_season_links GROUP BY season_id
        ), vote_resolution AS (
          SELECT v.id,
                 coalesce(sc.candidates, 0) AS candidates,
                 EXISTS (
                   SELECT 1 FROM contest_season_links csl
                   WHERE csl.season_id = st.season_id
                     AND csl.contest_id = c.season_id
                 ) AS contestant_legacy_id_matches
          FROM votes v
          JOIN contest_stages st ON st.id = v.stage_id
          JOIN contestants c ON c.id = v.contestant_id
          LEFT JOIN season_contests sc ON sc.season_id = st.season_id
        )
        SELECT count(*) AS votes,
               count(*) FILTER (WHERE candidates = 0) AS no_linked_contest,
               count(*) FILTER (WHERE candidates = 1) AS one_linked_contest,
               count(*) FILTER (WHERE candidates > 1) AS multiple_linked_contests,
               count(*) FILTER (WHERE contestant_legacy_id_matches) AS legacy_contest_match,
               count(*) FILTER (
                 WHERE candidates = 1 OR contestant_legacy_id_matches
               ) AS deterministically_resolvable
        FROM vote_resolution
    """,
    "active_vote_unique_index": """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'votes'
        ORDER BY indexname
    """,
    "logical_duplicates": """
        SELECT count(*) AS duplicate_groups, coalesce(sum(rows - 1), 0) AS excess_rows
        FROM (
          SELECT voter_id, contestant_id, stage_id, count(*) AS rows
          FROM votes
          WHERE status::text = 'active'
          GROUP BY voter_id, contestant_id, stage_id
          HAVING count(*) > 1
        ) d
    """,
    "legacy_entry_columns": """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('contest_entry', 'contest_entries', 'contestants')
        ORDER BY table_name, ordinal_position
    """,
    "legacy_entry_foreign_keys": """
        SELECT tc.table_name, tc.constraint_name, kcu.column_name,
               ccu.table_name AS target_table, ccu.column_name AS target_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_schema = tc.constraint_schema
         AND kcu.constraint_name = tc.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_schema = tc.constraint_schema
         AND ccu.constraint_name = tc.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name IN ('contest_entry', 'contest_entries', 'contestants')
        ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
    """,
    "myhigh5_compatibility": """
        WITH voter_stage AS (
          SELECT voter_id, stage_id, count(*) AS rows,
                 count(*) FILTER (WHERE rank_position BETWEEN 1 AND 5
                                   AND points = 6 - rank_position) AS modern_rows
          FROM votes WHERE upper(status::text) = 'ACTIVE'
          GROUP BY voter_id, stage_id
        )
        SELECT count(*) AS voter_stage_groups,
               min(rows) AS min_rows, max(rows) AS max_rows,
               count(*) FILTER (WHERE rows > 5) AS groups_over_five,
               sum(rows) FILTER (WHERE rows > 5) AS rows_in_groups_over_five,
               sum(modern_rows) AS rows_matching_modern_points
        FROM voter_stage
    """,
    "vote_window_compatibility": """
        SELECT count(*) AS votes,
               count(*) FILTER (
                 WHERE v.vote_date::date < st.start_date::date
                    OR v.vote_date::date > st.end_date::date
               ) AS outside_stored_stage_window
        FROM votes v JOIN contest_stages st ON st.id = v.stage_id
    """,
    "contest_entry_counts": """
        SELECT
          CASE WHEN to_regclass('public.contest_entry') IS NULL THEN NULL
               ELSE (SELECT count(*) FROM contest_entry) END AS contest_entry,
          CASE WHEN to_regclass('public.contest_entries') IS NULL THEN NULL
               ELSE (SELECT count(*) FROM contest_entries) END AS contest_entries
    """,
}


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def main() -> None:
    url = make_url(settings.DATABASE_URL)
    query = dict(url.query)
    # Neon pooler rejects libpq startup options. Statement timeout is set after
    # the read-only transaction begins instead.
    query.pop("options", None)
    engine = create_engine(url.set(query=query), connect_args={"sslmode": "require"})
    output = {}
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            for name, sql in QUERIES.items():
                output[name] = [dict(row) for row in connection.execute(text(sql)).mappings()]
        finally:
            transaction.rollback()
    engine.dispose()
    print(json.dumps(output, indent=2, default=_json_default, sort_keys=True))


if __name__ == "__main__":
    main()
