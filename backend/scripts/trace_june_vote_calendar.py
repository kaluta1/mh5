#!/usr/bin/env python3
"""End-to-end trace for June 2026 nomination/vote calendar (March official start).

Prints:
  - All rounds and flags
  - Vote calendar anchor (current month)
  - Available geography chips and cohort round ids
  - Sample API counts for one contest across stages

Usage:
  python scripts/trace_june_vote_calendar.py --base-url https://myhigh5.com/api/v1
  python scripts/trace_june_vote_calendar.py --base-url http://127.0.0.1:8000/api/v1
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

OFFICIAL_START = date(2026, 3, 1)
VOTE_OFFSETS = {"country": 1, "regional": 2, "continental": 3, "global": 4}
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def get(base: str, path: str) -> Any:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=120) as resp:
        return json.loads(resp.read().decode())


def month_from_round_name(name: str) -> tuple[int, int] | None:
    n = name.lower()
    for i, m in enumerate(MONTHS):
        token = m.lower()
        if token in n:
            for y in range(2024, 2032):
                if str(y) in n:
                    return y, i
    return None


def add_months(y: int, m: int, delta: int) -> tuple[int, int]:
    total = y * 12 + m - delta
    return total // 12, total % 12


def cohort_month(vote_y: int, vote_m: int, level: str) -> tuple[int, int]:
    return add_months(vote_y, vote_m, VOTE_OFFSETS[level])


def level_available(vote_y: int, vote_m: int, level: str, round_months: set[tuple[int, int]]) -> bool:
    cy, cm = cohort_month(vote_y, vote_m, level)
    cohort = date(cy, cm + 1, 1)
    if cohort < OFFICIAL_START:
        return False
    if (cy, cm) not in round_months:
        return False
    open_y, open_m = add_months(cy, cm, -VOTE_OFFSETS[level])
    vote_anchor = date(vote_y, vote_m + 1, 1)
    phase_open = date(open_y, open_m + 1, 1)
    return vote_anchor >= phase_open


def find_round_for_month(rounds: list[dict], y: int, m: int) -> dict | None:
    for r in rounds:
        parsed = month_from_round_name(str(r.get("name") or ""))
        if parsed == (y, m):
            return r
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--sample-contest-id", type=int, default=177)
    p.add_argument("--filter-country", default="Tanzania")
    p.add_argument("--filter-region", default="East Africa")
    p.add_argument("--filter-continent", default="Africa")
    args = p.parse_args()
    base = args.base_url.rstrip("/")
    today = date.today()
    anchor_y, anchor_m = today.year, today.month - 1

    print("=" * 72)
    print(f"June vote calendar trace — today {today.isoformat()}")
    print(f"Official nomination start: {OFFICIAL_START.isoformat()}")
    print("=" * 72)

    build = get(base, "/build-info")
    print(f"\nBackend build: {build.get('build_id') or build}")

    rounds = get(base, "/rounds/?limit=50")
    round_months: set[tuple[int, int]] = set()
    print("\n--- Rounds ---")
    for r in sorted(rounds, key=lambda x: int(x.get("id") or 0)):
        rid = r.get("id")
        name = r.get("name")
        parsed = month_from_round_name(str(name or ""))
        if parsed:
            round_months.add(parsed)
        print(
            f"  id={rid:>3}  sub_open={str(r.get('is_submission_open')):5}  "
            f"vote_open={str(r.get('is_voting_open')):5}  {name}"
        )

    vote_anchor = find_round_for_month(rounds, anchor_y, anchor_m)
    live_vote = next((r for r in rounds if r.get("is_voting_open")), None)
    print(f"\n--- Vote calendar anchor ({MONTHS[anchor_m]} {anchor_y}) ---")
    if vote_anchor:
        print(f"  Round id={vote_anchor['id']}  {vote_anchor.get('name')}")
    else:
        print("  No round for current calendar month — would fall back to live vote row")
        if live_vote:
            print(f"  Live vote fallback id={live_vote['id']}  {live_vote.get('name')}")

    anchor = vote_anchor or live_vote
    if not anchor:
        print("ERROR: no vote anchor", file=sys.stderr)
        return 1

    ay, am = month_from_round_name(str(anchor.get("name") or "")) or (anchor_y, anchor_m)
    print(f"\n--- Geography chips (V={MONTHS[am]} {ay}) ---")
    stages: list[tuple[str, str | None, int | None, dict[str, str]]] = [
        ("submit", None, None, {"filterCountry": args.filter_country}),
    ]

    for level in ("country", "regional", "continental", "global"):
        cy, cm = cohort_month(ay, am, level)
        avail = level_available(ay, am, level, round_months)
        cohort = find_round_for_month(rounds, cy, cm)
        rid = int(cohort["id"]) if cohort else None
        status = "AVAILABLE" if avail else "hidden"
        print(
            f"  {level:12} cohort={MONTHS[cm]} {cy}  round_id={rid or '-':>3}  [{status}]"
        )
        if avail and rid:
            geo: dict[str, str] = {}
            if level == "country":
                geo["filterCountry"] = args.filter_country
            elif level == "regional":
                geo["filterRegion"] = args.filter_region
            elif level == "continental":
                geo["filterContinent"] = args.filter_continent
            stages.append((f"vote_{level}", level, rid, geo))

    print(f"\n--- Sample contest {args.sample_contest_id} counts ---")
    for stage_name, level, round_id, geo in stages:
        if stage_name == "submit":
            round_id = int(find_round_for_month(rounds, anchor_y, anchor_m)["id"]) if vote_anchor else 26
        q = f"entryType=nomination&roundId={round_id}"
        if level:
            q += f"&contestLevel={level}"
        for k, v in geo.items():
            q += f"&{k}={urllib.parse.quote(v)}"
        detail = get(base, f"/contests/{args.sample_contest_id}?{q}")
        count = len(detail.get("contestants") or [])
        print(f"  {stage_name:22} round={round_id}  nominees={count}")

    print("\n--- All categories list vs detail (quick) ---")
    failures = 0
    for stage_name, level, round_id, geo in stages:
        if stage_name == "submit":
            continue
        q = f"roundId={round_id}&contestMode=nomination&contestLimit=200&contestLevel={level}"
        for k, v in geo.items():
            q += f"&{k}={urllib.parse.quote(v)}"
        data = get(base, f"/rounds/?{q}")
        contests = (data[0].get("contests") if data else []) or []
        mismatches = 0
        for c in contests[:5]:
            cid = int(c["id"])
            list_count = int(c.get("participants_count") or 0)
            dq = f"entryType=nomination&roundId={round_id}&contestLevel={level}"
            for k, v in geo.items():
                dq += f"&{k}={urllib.parse.quote(v)}"
            d = get(base, f"/contests/{cid}?{dq}")
            dc = len(d.get("contestants") or [])
            if list_count != dc:
                mismatches += 1
                failures += 1
        print(f"  {stage_name}: {len(contests)} categories, sample mismatches={mismatches}")

    print("\n" + ("PASS" if failures == 0 else f"FAIL ({failures} mismatches)"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
