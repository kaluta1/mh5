"""
Print MYHIGH5_NOMINATION_EXTENSION_UNTIL for copy-paste (UTC naive, matches backend).

Usage:
  python backend/scripts/print_nomination_extension_until.py
  python backend/scripts/print_nomination_extension_until.py 3

Default is 3 hours (short testing window). Set on the API server environment and restart.
While now < that instant and the round is in its voting calendar, nominations stay open
and voting stays off; then normal rules apply.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone


def main() -> None:
    p = argparse.ArgumentParser(description="Print MYHIGH5_NOMINATION_EXTENSION_UNTIL (UTC)")
    p.add_argument(
        "hours",
        nargs="?",
        type=float,
        default=3.0,
        help="Hours from now (UTC). Default: 3 (testing)",
    )
    args = p.parse_args()
    until = (datetime.now(timezone.utc) + timedelta(hours=args.hours)).replace(tzinfo=None)
    value = until.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"MYHIGH5_NOMINATION_EXTENSION_UNTIL={value}")
    print()
    print("# PowerShell (session):")
    print(f'$env:MYHIGH5_NOMINATION_EXTENSION_UNTIL = "{value}"')


if __name__ == "__main__":
    main()
