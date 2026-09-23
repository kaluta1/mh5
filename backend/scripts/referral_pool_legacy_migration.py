"""Legacy $100 Founding -> Referral Pool migration (dry run by default).

    python scripts/referral_pool_legacy_migration.py                       # dry run, prints manifest summary
    python scripts/referral_pool_legacy_migration.py --out manifest.json   # also writes the full manifest
    python scripts/referral_pool_legacy_migration.py --execute --manifest-sha256 <sha> --operator <name>

The execute path recomputes the manifest and refuses to run unless its SHA-256 equals the
reviewed one. It commits only after in-transaction reconciliation passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services import legacy_pool_migration as mig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--operator", default="")
    parser.add_argument("--out")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.execute:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))  # the dry run cannot write
            built = mig.build_manifest(db)
            m = built["manifest"]
            summary = {k: m[k] for k in m if k != "candidates"}
            summary["sha256"] = built["sha256"]
            summary["reconciliation"] = mig.reconciliation_snapshot(db)
            print(json.dumps(summary, indent=2, default=str))
            for c in m["candidates"]:
                print(f"deposit={c['deposit_id']} user={c['user_id']} {c['product_code']} {c['amount']} "
                      f"{c['deposit_status']} -> {c['classification']} {','.join(c['reasons'])}")
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(built, fh, indent=2, sort_keys=True, default=str)
            db.rollback()
            return 0
        if not args.manifest_sha256 or not args.operator:
            print("--execute requires --manifest-sha256 and --operator", file=sys.stderr)
            return 2
        result = mig.execute(db, expected_sha256=args.manifest_sha256, operator=args.operator)
        db.commit()
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
