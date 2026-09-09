"""Read-only production contest lifecycle and historical attribution analysis.

This script never calls application CRUD/services. It opens an explicit
read-only transaction and executes only SELECT/catalog statements.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


ATTRIBUTION_CTES = r"""
WITH vote_base AS (
    SELECT
        v.id AS vote_id,
        v.voter_id,
        v.contestant_id,
        v.stage_id,
        v.vote_date,
        v.points,
        cs.id AS season_id,
        cs.round_id AS season_round_id,
        ct.user_id AS contestant_user_id,
        ct.round_id AS contestant_round_id,
        ct.season_id AS contestant_direct_season_id,
        CASE WHEN cts.contestant_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_season_membership
    FROM votes v
    LEFT JOIN contest_stages st ON st.id = v.stage_id
    LEFT JOIN contest_seasons cs ON cs.id = st.season_id
    LEFT JOIN contestants ct ON ct.id = v.contestant_id
    LEFT JOIN contestant_seasons cts
      ON cts.contestant_id = v.contestant_id
     AND cts.season_id = cs.id
),
season_candidates AS (
    SELECT DISTINCT
        vb.vote_id,
        csl.contest_id,
        vb.vote_date,
        vb.contestant_user_id,
        c.voting_start_date,
        c.voting_end_date
    FROM vote_base vb
    JOIN contest_season_links csl ON csl.season_id = vb.season_id
    JOIN contest c ON c.id = csl.contest_id
    WHERE vb.season_round_id IS NULL
       OR EXISTS (
            SELECT 1 FROM round_contests rc
            WHERE rc.round_id = vb.season_round_id
              AND rc.contest_id = csl.contest_id
       )
),
candidate_counts AS (
    SELECT vote_id, count(DISTINCT contest_id) AS candidate_count,
           min(contest_id) AS sole_candidate
    FROM season_candidates GROUP BY vote_id
),
entry_signals AS (
    SELECT sc.vote_id,
           count(DISTINCT ce.contest_id) AS entry_count,
           min(ce.contest_id) AS entry_contest
    FROM season_candidates sc
    JOIN contest_entries ce
      ON ce.user_id = sc.contestant_user_id
     AND ce.contest_id = sc.contest_id
    GROUP BY sc.vote_id
),
temporal_signals AS (
    SELECT sc.vote_id,
           count(DISTINCT sc.contest_id) FILTER (
             WHERE sc.voting_start_date IS NOT NULL
               AND sc.voting_end_date IS NOT NULL
               AND sc.vote_date::date BETWEEN sc.voting_start_date AND sc.voting_end_date
           ) AS temporal_count,
           min(sc.contest_id) FILTER (
             WHERE sc.voting_start_date IS NOT NULL
               AND sc.voting_end_date IS NOT NULL
               AND sc.vote_date::date BETWEEN sc.voting_start_date AND sc.voting_end_date
           ) AS temporal_contest
    FROM season_candidates sc GROUP BY sc.vote_id
),
classified AS (
    SELECT
      vb.*,
      coalesce(cc.candidate_count, 0) AS candidate_count,
      cc.sole_candidate,
      coalesce(es.entry_count, 0) AS entry_count,
      es.entry_contest,
      coalesce(ts.temporal_count, 0) AS temporal_count,
      ts.temporal_contest,
      CASE
        WHEN vb.season_id IS NULL OR vb.contestant_user_id IS NULL
          OR coalesce(cc.candidate_count, 0) = 0 THEN 'ORPHANED_INVALID'
        WHEN cc.candidate_count = 1 THEN 'EXACT'
        WHEN coalesce(es.entry_count, 0) = 1
          AND (coalesce(ts.temporal_count, 0) <> 1 OR es.entry_contest = ts.temporal_contest)
          THEN 'STRONG'
        WHEN coalesce(es.entry_count, 0) = 0 AND coalesce(ts.temporal_count, 0) = 1
          THEN 'STRONG'
        ELSE 'AMBIGUOUS'
      END AS attribution_class,
      CASE
        WHEN cc.candidate_count = 1 THEN cc.sole_candidate
        WHEN coalesce(es.entry_count, 0) = 1
          AND (coalesce(ts.temporal_count, 0) <> 1 OR es.entry_contest = ts.temporal_contest)
          THEN es.entry_contest
        WHEN coalesce(es.entry_count, 0) = 0 AND coalesce(ts.temporal_count, 0) = 1
          THEN ts.temporal_contest
        ELSE NULL
      END AS resolved_contest_id
    FROM vote_base vb
    LEFT JOIN candidate_counts cc ON cc.vote_id = vb.vote_id
    LEFT JOIN entry_signals es ON es.vote_id = vb.vote_id
    LEFT JOIN temporal_signals ts ON ts.vote_id = vb.vote_id
)
"""


QUERIES = {
    "identity": "SELECT current_database() AS database, current_user AS db_user",
    "core_counts": """
        SELECT
          (SELECT count(*) FROM contest) AS contests,
          (SELECT count(*) FROM contest_seasons) AS seasons,
          (SELECT count(*) FROM contest_stages) AS stages,
          (SELECT count(*) FROM contestants) AS contestants,
          (SELECT count(*) FROM contest_entries) AS contest_entries,
          (SELECT count(*) FROM contest_entry) AS legacy_contest_entry,
          (SELECT count(*) FROM rounds) AS rounds,
          (SELECT count(*) FROM round_contests) AS round_contests,
          (SELECT count(*) FROM contest_types) AS contest_types,
          (SELECT count(*) FROM categories) AS categories,
          (SELECT count(*) FROM contest_season_links) AS contest_season_links,
          (SELECT count(*) FROM contestant_seasons) AS contestant_seasons,
          (SELECT count(*) FROM votes) AS votes
    """,
    "attribution_counts": ATTRIBUTION_CTES + """
        SELECT attribution_class, count(*) AS votes,
               round(100.0 * count(*) / sum(count(*)) OVER (), 6) AS percentage
        FROM classified GROUP BY attribution_class ORDER BY attribution_class
    """,
    "attribution_signals": ATTRIBUTION_CTES + """
        SELECT candidate_count, entry_count, temporal_count,
               count(*) AS votes
        FROM classified
        GROUP BY candidate_count, entry_count, temporal_count
        ORDER BY votes DESC, candidate_count, entry_count, temporal_count
    """,
    "resolved_periods": ATTRIBUTION_CTES + """
        SELECT stage_id, season_id, resolved_contest_id, attribution_class,
               count(*) AS source_votes, sum(points) AS total_points,
               count(DISTINCT contestant_id) AS contestants
        FROM classified
        WHERE resolved_contest_id IS NOT NULL
        GROUP BY stage_id, season_id, resolved_contest_id, attribution_class
        ORDER BY stage_id, resolved_contest_id, attribution_class
    """,
    "replay_top5": ATTRIBUTION_CTES + """
        , ranked AS (
          SELECT stage_id, season_id, resolved_contest_id, contestant_id,
                 sum(points) AS total_points, count(*) AS total_votes,
                 row_number() OVER (
                   PARTITION BY stage_id, season_id, resolved_contest_id
                   ORDER BY sum(points) DESC, contestant_id ASC
                 ) AS rank
          FROM classified
          WHERE resolved_contest_id IS NOT NULL
          GROUP BY stage_id, season_id, resolved_contest_id, contestant_id
        )
        SELECT stage_id, season_id, resolved_contest_id, contestant_id,
               total_points, total_votes, rank
        FROM ranked WHERE rank <= 5
        ORDER BY stage_id, resolved_contest_id, rank
    """,
    "roster_evidence": ATTRIBUTION_CTES + """
        SELECT
          count(*) AS votes,
          count(*) FILTER (WHERE contestant_direct_season_id = season_id) AS direct_season_match,
          count(*) FILTER (WHERE has_season_membership) AS association_match,
          count(*) FILTER (
            WHERE contestant_direct_season_id = season_id OR has_season_membership
          ) AS any_season_roster_match,
          count(*) FILTER (
            WHERE NOT coalesce(contestant_direct_season_id = season_id, false)
              AND NOT coalesce(has_season_membership, false)
          ) AS no_season_roster_match,
          count(*) FILTER (
            WHERE season_round_id IS NOT NULL
              AND contestant_round_id = season_round_id
          ) AS contestant_round_match
        FROM classified
    """,
    "periods_with_votes": """
        SELECT st.id AS stage_id, st.season_id, cs.round_id, cs.level,
               st.stage_level, st.status, st.start_date, st.end_date,
               count(DISTINCT v.id) AS votes,
               count(DISTINCT v.contestant_id) AS voted_contestants,
               count(DISTINCT csl.contest_id) AS linked_contests
        FROM contest_stages st
        JOIN contest_seasons cs ON cs.id = st.season_id
        LEFT JOIN votes v ON v.stage_id = st.id
        LEFT JOIN contest_season_links csl ON csl.season_id = cs.id
        GROUP BY st.id, st.season_id, cs.round_id, cs.level,
                 st.stage_level, st.status, st.start_date, st.end_date
        HAVING count(DISTINCT v.id) > 0
        ORDER BY st.id
    """,
    "temporal_anomalies": """
        SELECT
          count(*) AS votes,
          count(*) FILTER (WHERE v.vote_date < st.start_date) AS before_stage,
          count(*) FILTER (WHERE v.vote_date > st.end_date) AS after_stage,
          count(*) FILTER (
            WHERE v.vote_date < st.start_date OR v.vote_date > st.end_date
          ) AS outside_stage,
          min(v.vote_date) AS first_vote,
          max(v.vote_date) AS last_vote
        FROM votes v JOIN contest_stages st ON st.id = v.stage_id
    """,
    "integrity_anomalies": """
        SELECT
          (SELECT count(*) FROM contest c WHERE NOT EXISTS (
             SELECT 1 FROM contest_season_links l WHERE l.contest_id = c.id
          )) AS contests_without_season,
          (SELECT count(*) FROM contest_seasons s WHERE NOT EXISTS (
             SELECT 1 FROM contest_season_links l WHERE l.season_id = s.id
          )) AS seasons_without_contest,
          (SELECT count(*) FROM contest_seasons s WHERE NOT EXISTS (
             SELECT 1 FROM contest_stages st WHERE st.season_id = s.id
          )) AS seasons_without_stage,
          (SELECT count(*) FROM contest_stages st WHERE NOT EXISTS (
             SELECT 1 FROM contest_seasons s WHERE s.id = st.season_id
          )) AS stages_without_parent,
          (SELECT count(*) FROM contestants c WHERE NOT EXISTS (
             SELECT 1 FROM users u WHERE u.id = c.user_id
          )) AS orphan_contestants,
          (SELECT count(*) FROM votes v WHERE NOT EXISTS (
             SELECT 1 FROM contestants c WHERE c.id = v.contestant_id
          ) OR NOT EXISTS (
             SELECT 1 FROM users u WHERE u.id = v.voter_id
          ) OR NOT EXISTS (
             SELECT 1 FROM contest_stages st WHERE st.id = v.stage_id
          )) AS orphan_votes,
          (SELECT coalesce(sum(n - 1), 0) FROM (
             SELECT count(*) n FROM contest_entries GROUP BY contest_id, user_id HAVING count(*) > 1
          ) d) AS duplicate_contest_entries,
          (SELECT coalesce(sum(n - 1), 0) FROM (
             SELECT count(*) n FROM contestant_seasons GROUP BY contestant_id, season_id HAVING count(*) > 1
          ) d) AS duplicate_contestant_seasons,
          (SELECT coalesce(sum(n - 1), 0) FROM (
             SELECT count(*) n FROM contest_season_links GROUP BY contest_id, season_id HAVING count(*) > 1
          ) d) AS duplicate_contest_season_links,
          (SELECT coalesce(sum(n - 1), 0) FROM (
             SELECT count(*) n FROM round_contests GROUP BY round_id, contest_id HAVING count(*) > 1
          ) d) AS duplicate_round_contests
    """,
    "active_anomalies": """
        SELECT
          (SELECT count(*) FROM contest WHERE is_active AND NOT is_deleted) AS active_contests,
          (SELECT count(*) FROM rounds WHERE status = 'ACTIVE') AS active_rounds,
          (SELECT count(*) FROM rounds WHERE is_submission_open) AS submission_open_rounds,
          (SELECT count(*) FROM rounds WHERE is_voting_open) AS voting_open_rounds,
          (SELECT count(*) FROM contest_stages WHERE status = 'VOTING_ACTIVE') AS voting_active_stages,
          (SELECT count(*) FROM contest WHERE is_voting_open AND NOT is_deleted) AS voting_open_contests
    """,
    "duplicate_periods": """
        SELECT round_id, level, count(*) AS seasons, array_agg(id ORDER BY id) AS season_ids
        FROM contest_seasons
        WHERE NOT is_deleted
        GROUP BY round_id, level HAVING count(*) > 1
        ORDER BY round_id NULLS FIRST, level
    """,
    "duplicate_round_months": """
        SELECT submission_start_date,
               count(*) FILTER (WHERE status <> 'CANCELLED') AS non_cancelled_rounds,
               array_agg(id ORDER BY id) FILTER (WHERE status <> 'CANCELLED') AS round_ids
        FROM rounds
        WHERE submission_start_date IS NOT NULL
        GROUP BY submission_start_date
        HAVING count(*) FILTER (WHERE status <> 'CANCELLED') > 1
        ORDER BY submission_start_date
    """,
    "overlapping_stages": """
        SELECT count(*) AS overlapping_pairs
        FROM contest_stages a
        JOIN contest_stages b ON a.id < b.id
          AND a.season_id = b.season_id
          AND a.stage_level = b.stage_level
          AND a.start_date <= b.end_date
          AND b.start_date <= a.end_date
    """,
    "incompatible_contestant_periods": """
        SELECT count(*) AS contestant_round_level_duplicate_groups,
               coalesce(sum(seasons - 1), 0) AS excess_memberships
        FROM (
          SELECT csn.contestant_id, s.round_id, s.level,
                 count(DISTINCT csn.season_id) AS seasons
          FROM contestant_seasons csn
          JOIN contest_seasons s ON s.id = csn.season_id
          WHERE csn.is_active AND NOT s.is_deleted
          GROUP BY csn.contestant_id, s.round_id, s.level
          HAVING count(DISTINCT csn.season_id) > 1
        ) d
    """,
    "engagement_temporal_ranges": """
        SELECT 'page_views' AS source, count(*) AS rows, min(viewed_at) AS first_at, max(viewed_at) AS last_at FROM page_views
        UNION ALL SELECT 'contest_likes', count(*), min(created_at), max(created_at) FROM contest_likes
        UNION ALL SELECT 'contest_comments', count(*), min(created_at), max(created_at) FROM contest_comments
        UNION ALL SELECT 'contestant_reactions', count(*), min(created_at), max(created_at) FROM contestant_reactions
        UNION ALL SELECT 'contestant_shares', count(*), min(created_at), max(created_at) FROM contestant_shares
        ORDER BY source
    """,
    "rounds": """
        SELECT id, name, status, contest_id, is_submission_open, is_voting_open,
               current_season_level, submission_start_date, submission_end_date,
               voting_start_date, voting_end_date, created_at
        FROM rounds ORDER BY submission_start_date NULLS LAST, id
    """,
    "schema_constraints": """
        SELECT tc.table_name, tc.constraint_name, tc.constraint_type
        FROM information_schema.table_constraints tc
        WHERE tc.table_schema = 'public'
          AND tc.table_name IN (
            'contest','contest_seasons','contest_stages','contestants',
            'contest_entries','rounds','round_contests','contest_season_links',
            'contestant_seasons','votes'
          )
          AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE','FOREIGN KEY')
        ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name
    """,
}


def main() -> None:
    url = make_url(settings.DATABASE_URL).difference_update_query(["options"])
    engine = create_engine(url, pool_pre_ping=True)
    output = {}
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            requested = set(sys.argv[1:])
            unknown = requested - set(QUERIES)
            if unknown:
                raise SystemExit(f"Unknown query names: {sorted(unknown)}")
            selected = (
                {name: sql for name, sql in QUERIES.items() if name in requested}
                if requested
                else QUERIES
            )
            for name, sql in selected.items():
                output[name] = [dict(row._mapping) for row in connection.execute(text(sql))]
        finally:
            transaction.rollback()
    engine.dispose()
    print(json.dumps(output, indent=2, default=_json_default, sort_keys=True))


if __name__ == "__main__":
    main()
