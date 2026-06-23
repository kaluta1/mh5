#!/usr/bin/env python3
"""Verify March-start nomination pipeline for every category (list vs detail).

March cohort (round 3): continental vote when calendar anchor is June 2026.
April cohort (round 4): regional vote in June.
May cohort (round 21): country vote in June.
June cohort (round 26): submit — expect zero nominations when empty.

Usage:
  python scripts/verify_all_categories_march_pipeline.py --base-url https://myhigh5.com/api/v1
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any


def get(base: str, path: str) -> Any:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--filter-country", default="Tanzania")
    p.add_argument("--filter-region", default="East Africa")
    p.add_argument("--filter-continent", default="Africa")
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    stages = [
        ("submit_june", 26, None, {"filterCountry": args.filter_country}),
        # June vote anchor V=June: Country=May, Regional=April, Continental=March
        ("vote_country_june", 21, "country", {"filterCountry": args.filter_country}),
        ("vote_regional_june", 4, "regional", {"filterRegion": args.filter_region}),
        ("vote_continental_june", 3, "continental", {"filterContinent": args.filter_continent}),
    ]

    failures = 0
    checked = 0

    for stage_name, round_id, level, geo in stages:
        q = f"roundId={round_id}&contestMode=nomination&contestLimit=200"
        if level:
            q += f"&contestLevel={level}"
        for k, v in geo.items():
            q += f"&{k}={urllib.parse.quote(v)}"

        rounds = get(base, f"/rounds/?{q}")
        contests = (rounds[0].get("contests") if rounds else []) or []
        print(f"\n=== {stage_name} (round {round_id}) — {len(contests)} categories ===")

        stage_fail = 0
        for c in contests:
            cid = int(c["id"])
            list_count = int(c.get("participants_count") or 0)
            dq = f"entryType=nomination&roundId={round_id}"
            if level:
                dq += f"&contestLevel={level}"
            for k, v in geo.items():
                dq += f"&{k}={urllib.parse.quote(v)}"
            detail = get(base, f"/contests/{cid}?{dq}")
            detail_count = len(detail.get("contestants") or [])
            checked += 1
            if list_count != detail_count:
                failures += 1
                stage_fail += 1
                print(
                    f"  FAIL contest {cid} {c.get('name','')[:30]!r}: "
                    f"list={list_count} detail={detail_count}"
                )

        if stage_fail == 0:
            nonzero = sum(1 for c in contests if int(c.get("participants_count") or 0) > 0)
            print(f"  OK — {nonzero} categories with participants, all list/detail counts match")

        if stage_name == "submit_june" and any(int(c.get("participants_count") or 0) > 0 for c in contests):
            # Not a hard fail (some TZ nominations may exist) but warn loudly.
            print("  WARN: June submit has nonzero counts — verify these are real June nominations")

    print(f"\nChecked {checked} category×stage rows — {failures} mismatch(es)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
