"""
Retire member accounts so their email address and username can be registered again.

Each account is named by BOTH its id and its email address (they must designate the same account).
Without --apply nothing is written: the transaction is rolled back after showing what would change.
With --apply every account is retired in ONE transaction, or none is.

  python -m app.scripts.retire_account --account 17644:someone@example.com --reason "owner request" [--apply]

See app/services/account_retirement.py for what retirement changes and what it never touches.
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--account", action="append", required=True, help="ID:EMAIL (repeatable)")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--actor-id", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal
    from app.services import account_retirement as ar

    targets = []
    for value in args.account:
        uid, _, email = value.partition(":")
        if not uid.isdigit() or not email:
            parser.error(f"--account must be ID:EMAIL, got {value!r}")
        targets.append((int(uid), email))

    db = SessionLocal()
    try:
        for uid, email in targets:
            row = ar.retire(db, uid, email, reason=args.reason, actor_id=args.actor_id)
            print(f"RETIRE user {uid}: email -> {ar.placeholder_email(uid)}, username -> {ar.placeholder_username(uid)}, "
                  f"inactive + deleted, sessions ended; retirement row {row.id}")
        if args.apply:
            db.commit()
            print(f"APPLIED {len(targets)}")
        else:
            db.rollback()
            print(f"DRY RUN: rolled back ({len(targets)} would be retired)")
        return 0
    except ar.RetirementRefused as exc:
        db.rollback()
        print(f"REFUSED: {exc} (nothing written)")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
