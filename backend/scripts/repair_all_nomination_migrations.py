#!/usr/bin/env python3
"""
Repair COUNTRY → REGIONAL (and verify) for every official nomination cohort round.

Usage:
  cd backend && source .venv/bin/activate && export PYTHONPATH=.
  python scripts/repair_all_nomination_migrations.py
  python scripts/repair_all_nomination_migrations.py --apply
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.core.nomination_calendar import is_official_nomination_cohort_round
from app.db.session import SessionLocal
from app.models.round import Round


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair nomination level migrations for all cohort rounds")
    parser.add_argument("--apply", action="store_true", help="Write fixes (default dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rounds = (
            db.query(Round)
            .filter(Round.name.ilike("%2026%"))
            .order_by(Round.id.asc())
            .all()
        )
        cohort_rounds = [r for r in rounds if is_official_nomination_cohort_round(r)]
        print(f"Official nomination cohort rounds: {len(cohort_rounds)}")
        diagnose = os.path.join(SCRIPT_DIR, "diagnose_round_regional_migration.py")
        rc = 0
        for rnd in cohort_rounds:
            print(f"\n=== {rnd.name} (id={rnd.id}) ===")
            cmd = [
                sys.executable,
                diagnose,
                "--round-id",
                str(rnd.id),
                "--repair-existing",
            ]
            if args.apply:
                cmd.append("--apply")
            out = subprocess.run(cmd, cwd=BACKEND_ROOT, check=False)
            if out.returncode != 0:
                rc = out.returncode
        return rc
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
