"""Low-impact, read-only production performance inventory.

Only catalog/statistics reads and EXPLAIN (never EXPLAIN ANALYZE) are used.
The transaction is explicitly read-only and has a five-second statement limit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


QUERIES = {
    "identity": "SELECT current_database() AS database, current_user AS db_user",
    "table_stats": """
        SELECT relname AS table_name, n_live_tup, n_dead_tup,
               seq_scan, idx_scan,
               pg_size_pretty(pg_total_relation_size(relid)) AS total_size
        FROM pg_stat_user_tables
        WHERE relname IN (
          'contest','contestants','contest_seasons','contest_season_links',
          'votes','contestant_voting','page_views','contest_likes',
          'contest_comments','comment','contestant_reactions','contestant_shares',
          'categories','users','media'
        )
        ORDER BY pg_total_relation_size(relid) DESC
    """,
    "indexes": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname='public' AND tablename IN (
          'contest','contestants','contest_seasons','contest_season_links',
          'contest_stages','votes','contestant_voting','page_views','contest_likes',
          'contest_comments','comment','contestant_reactions','contestant_shares',
          'categories','users','media'
        )
        ORDER BY tablename,indexname
    """,
    "connection_state": """
        SELECT state, count(*) AS connections,
               max(EXTRACT(epoch FROM (now()-xact_start))) FILTER (WHERE xact_start IS NOT NULL)
                 AS longest_transaction_seconds
        FROM pg_stat_activity
        WHERE datname=current_database()
        GROUP BY state ORDER BY state
    """,
    "long_transactions": """
        SELECT state, application_name, backend_type, wait_event_type, wait_event,
               round(EXTRACT(epoch FROM (now()-xact_start))) AS transaction_seconds,
               round(EXTRACT(epoch FROM (now()-state_change))) AS state_seconds
        FROM pg_stat_activity
        WHERE datname=current_database()
          AND xact_start IS NOT NULL
          AND now()-xact_start > interval '30 seconds'
        ORDER BY xact_start ASC
        LIMIT 20
    """,
    "plan_current_ranking": """
        EXPLAIN (FORMAT JSON, COSTS true)
        SELECT contestant_id, coalesce(sum(points),0), count(id)
        FROM contestant_voting
        WHERE season_id IN (SELECT id FROM contest_seasons ORDER BY id DESC LIMIT 3)
          AND contestant_id IN (SELECT id FROM contestants ORDER BY id DESC LIMIT 100)
        GROUP BY contestant_id
    """,
    "plan_historical_ranking": """
        EXPLAIN (FORMAT JSON, COSTS true)
        SELECT v.contestant_id, coalesce(sum(v.points),0), count(v.id)
        FROM votes v JOIN contest_stages cs ON cs.id=v.stage_id
        WHERE cs.season_id IN (SELECT id FROM contest_seasons ORDER BY id DESC LIMIT 3)
          AND v.status='ACTIVE'
          AND v.contestant_id IN (SELECT id FROM contestants ORDER BY id DESC LIMIT 100)
        GROUP BY v.contestant_id
    """,
    "plan_page_views": """
        EXPLAIN (FORMAT JSON, COSTS true)
        SELECT contestant_id,count(id)
        FROM page_views
        WHERE contestant_id IN (SELECT id FROM contestants ORDER BY id DESC LIMIT 100)
          AND viewed_at >= now() - interval '31 days'
          AND viewed_at <= now()
        GROUP BY contestant_id
    """,
    "plan_contest_list": """
        EXPLAIN (FORMAT JSON, COSTS true)
        SELECT id,name,contest_type,contest_mode,category_id
        FROM contest
        WHERE is_deleted=false AND is_active=true
        ORDER BY id DESC LIMIT 12
    """,
    "plan_search": """
        EXPLAIN (FORMAT JSON, COSTS true)
        SELECT id,name FROM contest
        WHERE is_deleted=false
          AND (name ILIKE '%music%' OR description ILIKE '%music%')
        LIMIT 10
    """,
}


def main() -> None:
    requested = set(sys.argv[1:])
    selected_queries = (
        {name: sql for name, sql in QUERIES.items() if name in requested}
        if requested
        else QUERIES
    )
    engine = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    output = {}
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = 5000"))
                connection.execute(text("SET LOCAL lock_timeout = 1000"))
                for name, sql in selected_queries.items():
                    try:
                        rows = connection.execute(text(sql)).mappings().all()
                        output[name] = [dict(row) for row in rows]
                    except Exception as exc:
                        output[name] = {"error": type(exc).__name__}
                        transaction.rollback()
                        transaction = connection.begin()
                        connection.execute(text("SET TRANSACTION READ ONLY"))
                        connection.execute(text("SET LOCAL statement_timeout = 5000"))
                        connection.execute(text("SET LOCAL lock_timeout = 1000"))
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
