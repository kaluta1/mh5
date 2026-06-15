#!/usr/bin/env python3
"""DB-only check: regional season for contest 7 exists on an earlier round (round 21 list bug)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("pip install psycopg2-binary")
    raise SystemExit(1)

LOG = Path(__file__).resolve().parents[2] / ".cursor" / "debug-e34593.log"
CONTEST_ID = 7
TARGET_ROUND = 21


def log(hypothesis_id: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "e34593",
        "runId": "db-minimal",
        "hypothesisId": hypothesis_id,
        "location": "verify_nomination_db_minimal.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("Set DATABASE_URL to run this script")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT cs.id, cs.round_id, cs.level::text, csl.is_active
        FROM contest_season_links csl
        JOIN contest_seasons cs ON cs.id = csl.season_id
        WHERE csl.contest_id = %s
          AND cs.is_deleted = false
          AND cs.level::text IN ('regional', 'REGIONAL')
        ORDER BY cs.round_id DESC
        """,
        (CONTEST_ID,),
    )
    regional_rows = cur.fetchall()

    cur.execute(
        """
        SELECT cs.id, cs.round_id, cs.level::text
        FROM contest_season_links csl
        JOIN contest_seasons cs ON cs.id = csl.season_id
        WHERE csl.contest_id = %s
          AND cs.round_id = %s
          AND cs.is_deleted = false
          AND cs.level::text IN ('regional', 'REGIONAL')
        LIMIT 1
        """,
        (CONTEST_ID, TARGET_ROUND),
    )
    exact_round_regional = cur.fetchone()

    cur.execute(
        """
        SELECT cs.id, cs.round_id, cs.level::text
        FROM contest_season_links csl
        JOIN contest_seasons cs ON cs.id = csl.season_id
        WHERE csl.contest_id = %s
          AND cs.is_deleted = false
          AND cs.level::text IN ('continental', 'CONTINENT')
        ORDER BY cs.round_id DESC
        LIMIT 5
        """,
        (CONTEST_ID,),
    )
    continental_rows = cur.fetchall()

    conn.close()

    cross_round = any(r[1] != TARGET_ROUND for r in regional_rows)
    old_eligible = exact_round_regional is not None
    new_eligible = len(regional_rows) > 0

    print(f"Regional seasons for contest {CONTEST_ID}: {regional_rows}")
    print(f"Exact round {TARGET_ROUND} regional season: {exact_round_regional}")
    print(f"Continental seasons: {continental_rows}")
    print(f"Old code eligible (exact round only): {old_eligible}")
    print(f"New code eligible (cross-round): {new_eligible}")

    log(
        "E",
        "regional season DB state",
        {
            "regional_rows": regional_rows,
            "exact_round_regional": exact_round_regional,
            "target_round": TARGET_ROUND,
            "old_code_eligible": old_eligible,
            "new_code_eligible": new_eligible,
            "cross_round_season": cross_round,
        },
    )
    log(
        "F",
        "continental season DB state",
        {
            "continental_rows": continental_rows,
            "has_continental_season": len(continental_rows) > 0,
        },
    )

    if cross_round and not old_eligible and new_eligible:
        print("\n[OK] DB confirms fix: regional season on earlier round, new eligibility logic required.")
        return 0
    print("\n[WARN] Unexpected DB state — review rows above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
