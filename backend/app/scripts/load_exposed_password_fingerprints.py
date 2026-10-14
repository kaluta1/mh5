#!/usr/bin/env python3
"""Record which stored password hashes have been exposed (fingerprints only).

Reads the `users` table of one or more database dumps that left the platform
(plain SQL, or pg_dump custom format through pg_restore) and stores the
SHA-256 FINGERPRINT of every `hashed_password` in it
(table exposed_password_fingerprints; app.services.password_exposure). It
stores no hash, no password, no account id and no email, and prints counts
only.

From then on an account whose CURRENT hash is one of those cannot be made a
Super Admin (bootstrap or Admin Panel) until its password has been changed.

DRY-RUN BY DEFAULT. Nothing is written without --apply.

    python -m app.scripts.load_exposed_password_fingerprints --dump /path/a.sql --dump /path/b.dump --source "repository dumps 2026-06"
    python -m app.scripts.load_exposed_password_fingerprints --dump /path/a.sql --source "repository dumps 2026-06" --apply
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import Iterable, List

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import password_exposure


class LoadError(Exception):
    pass


def hashes_from_copy(lines: Iterable[str]) -> List[str]:
    """Every hashed_password of the COPY public.users block in these lines."""
    out, cols, inside = [], None, False
    for line in lines:
        if not inside:
            m = re.match(r"COPY (?:public\.)?\"?users\"? \((.*)\) FROM stdin;", line)
            if m:
                cols = [c.strip().strip('"') for c in m.group(1).split(",")]
                if "hashed_password" not in cols:
                    raise LoadError("the users table in this dump has no hashed_password column")
                inside = True
            continue
        if line.startswith("\\."):
            break
        fields = line.rstrip("\r\n").split("\t")
        if len(fields) == len(cols):
            value = fields[cols.index("hashed_password")]
            if value and value != "\\N":
                out.append(value)
    if cols is None:
        raise LoadError("no users table data found in this dump")
    return out


def hashes_from_dump(path: str) -> List[str]:
    with open(path, "rb") as fh:
        custom = fh.read(5) == b"PGDMP"
    if not custom:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return hashes_from_copy(fh)
    proc = subprocess.run(["pg_restore", "--data-only", "--table=users", "--file=-", path], capture_output=True,
                          text=True, errors="replace")
    if proc.returncode != 0:
        raise LoadError("pg_restore could not read this dump")
    return hashes_from_copy(proc.stdout.splitlines())


def load(db: Session, dumps: List[str], *, source: str, apply: bool = False) -> dict:
    found = []
    for path in dumps:
        found.extend(hashes_from_dump(path))
    distinct = {password_exposure.fingerprint(h) for h in found}
    before = password_exposure.loaded_count(db)
    added = password_exposure.add(db, found, source=source)
    db.flush()
    current = sum(1 for (h,) in db.query(User.hashed_password).all()
                  if password_exposure.fingerprint(h) in distinct)
    if apply:
        db.commit()
    else:
        db.rollback()
    return {"hashes read": len(found), "distinct fingerprints": len(distinct), "already recorded": before,
            "new": added, "accounts whose current password is one of them": current}


def _database_label() -> str:
    from sqlalchemy.engine import make_url

    from app.core.config import settings

    try:
        url = make_url(settings.DATABASE_URL)
        return f"{url.host or 'local'}/{url.database}"
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dump", action="append", required=True, help="a dump containing the exposed users table")
    parser.add_argument("--source", required=True, help="a short label of where they were exposed (no path, no data)")
    parser.add_argument("--apply", action="store_true", help="write the fingerprints (default: dry run)")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    print(f"Database: {_database_label()}")
    db = SessionLocal()
    try:
        result = load(db, args.dump, source=args.source, apply=args.apply)
    except (LoadError, OSError) as exc:
        db.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        db.close()
    print("; ".join(f"{k}: {v}" for k, v in result.items()),
          "[APPLIED]" if args.apply else "[DRY RUN - nothing written (use --apply)]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
