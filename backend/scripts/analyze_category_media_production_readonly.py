"""Read-only production category and media integrity analysis.

The script opens an explicit read-only PostgreSQL transaction and executes
only SELECT/catalog queries.  It intentionally does not probe remote media
URLs because doing so can disclose signed URLs or trigger third-party traffic.
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


MEDIA_VALUES = r"""
WITH media_values AS (
  SELECT 'categories.image_url' AS source, id AS owner_id, image_url AS value FROM categories
  UNION ALL SELECT 'contest.cover_image_url', id, cover_image_url FROM contest
  UNION ALL SELECT 'contest.image_url', id, image_url FROM contest
  UNION ALL SELECT 'users.avatar_url', id, avatar_url FROM users
  UNION ALL SELECT 'media.url', id, url FROM media
  UNION ALL SELECT 'media.path', id, path FROM media
  UNION ALL SELECT 'contest_submissions.file_url', id, file_url FROM contest_submissions
  UNION ALL SELECT 'contest_submissions.external_url', id, external_url FROM contest_submissions
), classified AS (
  SELECT source, owner_id, value,
    CASE
      WHEN value IS NULL OR btrim(value) = '' THEN 'EMPTY'
      WHEN value ~* '^data:' THEN 'DATA_URL'
      WHEN value ~* '^(file:/{0,3}|[a-z]:[\\/]|/(var|app|opt|home|tmp)/)' THEN 'LOCAL_PATH'
      WHEN value ~* '^https?://(localhost|127\.0\.0\.1|\[?::1\]?)' THEN 'LOCALHOST_URL'
      WHEN value ~* '^http://' THEN 'INSECURE_HTTP'
      WHEN value ~* '^https://' THEN 'ABSOLUTE_HTTPS'
      WHEN value ~ '^/api/v1/media/file/[0-9]+/[^/?#]+([?#].*)?$' THEN 'CANONICAL_RELATIVE'
      WHEN value ~ '^/(media|uploads)/' THEN 'LEGACY_RELATIVE'
      WHEN value ~ '^/' THEN 'OTHER_RELATIVE'
      ELSE 'MALFORMED_OR_BARE'
    END AS classification
  FROM media_values
)
"""


QUERIES = {
    "identity": "SELECT current_database() AS database, current_user AS db_user",
    "table_counts": """
      SELECT
        (SELECT count(*) FROM categories) AS categories,
        (SELECT count(*) FROM contest_types) AS contest_types,
        (SELECT count(*) FROM contest_categories) AS contest_categories,
        (SELECT count(*) FROM contest) AS contests,
        (SELECT count(*) FROM contestants) AS contestants,
        (SELECT count(*) FROM contest_entries) AS contest_entries,
        (SELECT count(*) FROM contest_entry) AS legacy_contest_entry,
        (SELECT count(*) FROM media) AS media,
        (SELECT count(*) FROM contest_submissions) AS contest_submissions,
        (SELECT count(*) FROM post_media) AS post_media,
        (SELECT count(*) FROM votes) AS votes
    """,
    "category_columns": """
      SELECT table_name, column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE table_schema='public'
        AND table_name IN ('categories','contest_types','contest_categories','contest')
      ORDER BY table_name, ordinal_position
    """,
    "category_constraints": """
      SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
             string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) AS columns
      FROM information_schema.table_constraints tc
      LEFT JOIN information_schema.key_column_usage kcu
        ON kcu.constraint_schema=tc.constraint_schema
       AND kcu.constraint_name=tc.constraint_name
       AND kcu.table_name=tc.table_name
      WHERE tc.table_schema='public'
        AND tc.table_name IN ('categories','contest_types','contest_categories','contest')
        AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE','FOREIGN KEY')
      GROUP BY tc.table_name,tc.constraint_name,tc.constraint_type
      ORDER BY tc.table_name,tc.constraint_type,tc.constraint_name
    """,
    "important_indexes": """
      SELECT tablename,indexname,indexdef
      FROM pg_indexes
      WHERE schemaname='public'
        AND tablename IN ('categories','contest','contest_types','contest_categories','media','contest_entries','contestants','contest_submissions','post_media')
      ORDER BY tablename,indexname
    """,
    "canonical_category_integrity": """
      SELECT
        count(*) AS total,
        count(*) FILTER (WHERE is_active) AS active,
        count(*) FILTER (WHERE NOT is_active) AS inactive,
        count(*) FILTER (WHERE btrim(name)='') AS empty_names,
        count(*) FILTER (WHERE btrim(slug)='') AS empty_slugs,
        count(*) FILTER (WHERE slug !~ '^[a-z0-9]+(?:-[a-z0-9]+)*$') AS malformed_slugs,
        (SELECT count(*) FROM (
           SELECT lower(btrim(name)) FROM categories GROUP BY lower(btrim(name)) HAVING count(*)>1
         ) d) AS duplicate_normalized_name_groups,
        (SELECT count(*) FROM (
           SELECT lower(btrim(slug)) FROM categories GROUP BY lower(btrim(slug)) HAVING count(*)>1
         ) d) AS duplicate_normalized_slug_groups,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM contest c WHERE c.category_id=categories.id)) AS unreferenced
      FROM categories
    """,
    "contest_category_integrity": """
      SELECT
        count(*) AS contests,
        count(*) FILTER (WHERE c.category_id IS NULL) AS null_category,
        count(*) FILTER (WHERE c.category_id IS NULL AND c.is_active AND NOT c.is_deleted) AS active_null_category,
        count(*) FILTER (WHERE c.category_id IS NOT NULL AND cat.id IS NULL) AS missing_category,
        count(*) FILTER (WHERE c.is_active AND NOT c.is_deleted AND cat.id IS NOT NULL AND NOT cat.is_active) AS active_using_disabled_category,
        count(*) FILTER (
          WHERE cat.id IS NOT NULL
            AND lower(btrim(coalesce(contest_type,''))) NOT IN (lower(btrim(cat.slug)), lower(btrim(cat.name)))
        ) AS legacy_label_differs_from_category
      FROM contest c LEFT JOIN categories cat ON cat.id=c.category_id
    """,
    "active_category_mode_duplicates": """
      SELECT category_id, lower(btrim(contest_type)) AS legacy_type,
             lower(btrim(contest_mode)) AS contest_mode,
             count(*) AS rows, array_agg(id ORDER BY id) AS contest_ids
      FROM contest
      WHERE is_active AND NOT is_deleted
      GROUP BY category_id, lower(btrim(contest_type)), lower(btrim(contest_mode))
      HAVING count(*)>1
      ORDER BY rows DESC, category_id NULLS LAST
    """,
    "contestant_category_integrity": """
      WITH memberships AS (
        SELECT id AS contestant_id, season_id FROM contestants WHERE season_id IS NOT NULL
        UNION
        SELECT contestant_id, season_id FROM contestant_seasons WHERE is_active
      ), resolved AS (
        SELECT c.id,
               count(DISTINCT co.category_id) FILTER (WHERE co.category_id IS NOT NULL) AS categories,
               count(DISTINCT co.id) AS contests
        FROM contestants c
        LEFT JOIN memberships m ON m.contestant_id=c.id
        LEFT JOIN contest_season_links csl ON csl.season_id=m.season_id AND csl.is_active
        LEFT JOIN contest co ON co.id=csl.contest_id AND NOT co.is_deleted
        GROUP BY c.id
      )
      SELECT
        count(*) FILTER (WHERE categories=0) AS no_resolvable_category,
        count(*) FILTER (WHERE categories=1) AS exactly_one_category,
        count(*) FILTER (WHERE categories>1) AS multiple_categories,
        count(*) FILTER (WHERE contests>1) AS multiple_contest_candidates
      FROM resolved
    """,
    "secondary_taxonomy_integrity": """
      SELECT
        (SELECT count(*) FROM contest_types) AS types_total,
        (SELECT count(*) FROM contest_types WHERE is_active) AS types_active,
        (SELECT count(*) FROM contest_categories) AS subcategories_total,
        (SELECT count(*) FROM contest_categories WHERE is_active) AS subcategories_active,
        (SELECT count(*) FROM contest_categories cc LEFT JOIN contest_types ct ON ct.id=cc.contest_type_id WHERE ct.id IS NULL) AS orphan_subcategories,
        (SELECT count(*) FROM (SELECT contest_type_id,lower(btrim(name)) FROM contest_categories GROUP BY contest_type_id,lower(btrim(name)) HAVING count(*)>1) d) AS duplicate_subcategory_name_groups,
        (SELECT count(*) FROM (SELECT contest_type_id,lower(btrim(slug)) FROM contest_categories GROUP BY contest_type_id,lower(btrim(slug)) HAVING count(*)>1) d) AS duplicate_subcategory_slug_groups,
        (SELECT count(*) FROM contest_types ct WHERE NOT EXISTS (
          SELECT 1 FROM contest c WHERE lower(btrim(c.contest_type)) IN (lower(btrim(ct.slug)),lower(btrim(ct.name)))
        )) AS types_unmatched_by_legacy_contest_label
    """,
    "category_examples": """
      SELECT id,name,slug,is_active,
             (SELECT count(*) FROM contest c WHERE c.category_id=categories.id) AS contests
      FROM categories ORDER BY id LIMIT 200
    """,
    "media_columns": """
      SELECT table_name, column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE table_schema='public'
        AND (table_name IN ('media','contest_submissions','post_media','contest_entry','contestants','users')
             OR column_name ~* '(image|video|avatar|media|thumbnail|cover|banner|gallery|attachment|file|photo)')
      ORDER BY table_name, ordinal_position
    """,
    "media_ownership_integrity": """
      SELECT
        (SELECT count(*) FROM media) AS media_rows,
        (SELECT count(*) FROM media WHERE user_id IS NULL) AS media_without_owner,
        (SELECT count(*) FROM media m LEFT JOIN users u ON u.id=m.user_id WHERE u.id IS NULL) AS media_orphan_owner,
        (SELECT count(*) FROM contest_entry ce LEFT JOIN media m ON m.id=ce.media_id WHERE m.id IS NULL) AS legacy_entries_missing_media,
        (SELECT count(*) FROM contest_entries ce LEFT JOIN media m ON m.id=ce.media_id WHERE ce.media_id IS NOT NULL AND m.id IS NULL) AS entries_missing_media,
        (SELECT count(*) FROM post_media pm LEFT JOIN media m ON m.id=pm.media_id WHERE m.id IS NULL) AS posts_missing_media,
        (SELECT count(*) FROM contest_submissions cs LEFT JOIN contestants c ON c.id=cs.contestant_id WHERE c.id IS NULL) AS submissions_missing_contestant,
        (SELECT count(*) FROM media m WHERE NOT EXISTS (SELECT 1 FROM contest_entry ce WHERE ce.media_id=m.id)
          AND NOT EXISTS (SELECT 1 FROM contest_entries ce2 WHERE ce2.media_id=m.id)
          AND NOT EXISTS (SELECT 1 FROM post_media pm WHERE pm.media_id=m.id)
          AND NOT EXISTS (SELECT 1 FROM comments co WHERE co.media_id=m.id)
          AND NOT EXISTS (SELECT 1 FROM likes li WHERE li.media_id=m.id)) AS media_without_direct_entity_reference
    """,
    "media_url_classes": MEDIA_VALUES + """
      SELECT source,classification,count(*) AS references
      FROM classified GROUP BY source,classification ORDER BY source,classification
    """,
    "media_url_examples": MEDIA_VALUES + """
      SELECT source,classification,owner_id,
             left(regexp_replace(value,'[?#].*$','','g'),180) AS redacted_example
      FROM (
        SELECT *,row_number() OVER (PARTITION BY source,classification ORDER BY owner_id) AS rn
        FROM classified WHERE classification NOT IN ('EMPTY','ABSOLUTE_HTTPS','CANONICAL_RELATIVE')
      ) q WHERE rn<=3 ORDER BY source,classification,owner_id
    """,
    "contestant_media_shapes": """
      SELECT field,shape,count(*) AS rows FROM (
        SELECT 'image_media_ids' AS field,
          CASE WHEN image_media_ids IS NULL OR btrim(image_media_ids)='' THEN 'EMPTY'
               WHEN image_media_ids ~ '^\\s*\\[' THEN 'JSON_ARRAY_LIKE'
               WHEN image_media_ids ~* '^https?://' THEN 'SINGLE_URL'
               ELSE 'OTHER' END AS shape FROM contestants
        UNION ALL
        SELECT 'video_media_ids',
          CASE WHEN video_media_ids IS NULL OR btrim(video_media_ids)='' THEN 'EMPTY'
               WHEN video_media_ids ~ '^\\s*\\[' THEN 'JSON_ARRAY_LIKE'
               WHEN video_media_ids ~* '^https?://' THEN 'SINGLE_URL'
               ELSE 'OTHER' END FROM contestants
      ) x GROUP BY field,shape ORDER BY field,shape
    """,
    "media_types": """
      SELECT media_type,count(*) AS rows,count(*) FILTER (WHERE file_size IS NULL) AS missing_file_size,
             count(*) FILTER (WHERE media_type='image' AND (width IS NULL OR height IS NULL)) AS missing_dimensions
      FROM media GROUP BY media_type ORDER BY media_type
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
            selected = ({k: v for k, v in QUERIES.items() if k in requested} if requested else QUERIES)
            for name, sql in selected.items():
                output[name] = [dict(row._mapping) for row in connection.execute(text(sql))]
        finally:
            transaction.rollback()
    engine.dispose()
    print(json.dumps(output, indent=2, default=_json_default, sort_keys=True))


if __name__ == "__main__":
    main()
