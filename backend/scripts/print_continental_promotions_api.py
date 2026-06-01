#!/usr/bin/env python3
"""Print March nomination contestants promoted to the continent stage via public API."""
from __future__ import annotations

import argparse
from typing import Any

import requests


REGIONAL_POOLS: dict[str, list[str]] = {
    "East Africa": [
        "Tanzania",
        "Kenya",
        "Uganda",
        "Rwanda",
        "Burundi",
        "Ethiopia",
        "Eritrea",
        "Djibouti",
        "Somalia",
        "South Sudan",
        "Sudan",
    ],
    "West Africa": [
        "Nigeria",
        "Ghana",
        "Senegal",
        "Ivory Coast",
        "Benin",
        "Togo",
        "Burkina Faso",
        "Mali",
        "Niger",
        "Guinea",
        "Sierra Leone",
        "Liberia",
        "Gambia",
        "Cape Verde",
        "Guinea-Bissau",
    ],
    "Southern Africa": [
        "South Africa",
        "Zimbabwe",
        "Zambia",
        "Botswana",
        "Namibia",
        "Mozambique",
        "Malawi",
        "Angola",
        "Lesotho",
        "Eswatini",
        "Madagascar",
        "Mauritius",
        "Seychelles",
        "Comoros",
    ],
    "North Africa": ["Egypt", "Morocco", "Algeria", "Tunisia", "Libya"],
    "Central Africa": [
        "Cameroon",
        "Democratic Republic of the Congo",
        "Republic of the Congo",
        "Gabon",
        "Chad",
        "Central African Republic",
        "Equatorial Guinea",
        "Sao Tome and Principe",
    ],
}


def best_metric(row: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        int(row.get("points") or 0),
        int(row.get("shares") or 0),
        int(row.get("likes") or 0),
        int(row.get("comments") or 0),
        int(row.get("views") or 0),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://myhigh5.com/api/v1")
    parser.add_argument("--round-id", type=int, default=3)
    args = parser.parse_args()

    endpoint = f"{args.base_url.rstrip('/')}/seasons/top-high5"
    rows: dict[tuple[int, int], dict[str, Any]] = {}
    source_calls: list[tuple[str, int | str, int]] = []

    for pool, countries in REGIONAL_POOLS.items():
        for country in countries:
            try:
                response = requests.get(
                    endpoint,
                    params={
                        "round_id": args.round_id,
                        "level": "continent",
                        "country": country,
                    },
                    timeout=30,
                )
                if response.status_code != 200:
                    source_calls.append((country, response.status_code, 0))
                    continue
                payload = response.json()
            except Exception:
                source_calls.append((country, "ERR", 0))
                continue

            contests = payload.get("contests") or []
            source_calls.append((country, 200, len(contests)))
            for contest in contests:
                category = (
                    contest.get("category_name")
                    or contest.get("contest_name")
                    or f"Contest {contest.get('contest_id')}"
                )
                for api_row in contest.get("rows") or []:
                    contestant_id = api_row.get("contestant_id")
                    contest_id = contest.get("contest_id")
                    if not contestant_id or not contest_id:
                        continue
                    item = {
                        "contest_id": int(contest_id),
                        "category": category,
                        "contest": contest.get("contest_name") or "",
                        "contestant_id": int(contestant_id),
                        "title": (api_row.get("contestant_title") or "").strip(),
                        "author": api_row.get("author_name") or "",
                        "country": api_row.get("country") or country,
                        "region": api_row.get("region") or pool,
                        "continent": api_row.get("continent") or "Africa",
                        "rank": api_row.get("rank"),
                        "points": int(api_row.get("stars_points") or 0),
                        "shares": int(api_row.get("shares") or 0),
                        "likes": int(api_row.get("likes") or 0),
                        "comments": int(api_row.get("comments") or 0),
                        "views": int(api_row.get("views") or 0),
                        "pool": pool,
                    }
                    region = str(item["region"]).strip().lower()
                    for pool_name in REGIONAL_POOLS:
                        if region == pool_name.lower():
                            item["pool"] = pool_name
                            break

                    key = (item["contest_id"], item["contestant_id"])
                    previous = rows.get(key)
                    if previous is None or best_metric(item) > best_metric(previous):
                        rows[key] = item

    all_rows = sorted(
        rows.values(),
        key=lambda row: (
            str(row["category"]).lower(),
            str(row["pool"]),
            str(row["country"]),
            int(row["contestant_id"]),
        ),
    )
    east_rows = [
        row
        for row in all_rows
        if row["pool"] == "East Africa" or str(row["region"]).lower() == "east africa"
    ]

    print(f"Round {args.round_id} March 2026 - CONTINENT promoted roster from public API")
    print(f"Africa unique promoted rows: {len(all_rows)}")
    print(f"East Africa unique promoted rows: {len(east_rows)}")
    countries_with_data = [
        f"{country}:{count}"
        for country, status_code, count in source_calls
        if status_code == 200 and count
    ]
    print("Countries with data: " + ", ".join(countries_with_data))

    print("\n=== EAST AFRICA PROMOTED TO CONTINENTAL ===")
    for row in east_rows:
        print(
            f"[{row['category']}] #{row['contestant_id']} {row['title']} "
            f"| author={row['author']} | country={row['country']} "
            f"| region={row['region']} | pts={row['points']} sh={row['shares']} "
            f"lk={row['likes']} cm={row['comments']} vw={row['views']}"
        )

    print("\n=== ALL AFRICA PROMOTED TO CONTINENTAL, ALL REGIONS ===")
    for row in all_rows:
        print(
            f"[{row['pool']}] [{row['category']}] #{row['contestant_id']} {row['title']} "
            f"| author={row['author']} | country={row['country']} "
            f"| region={row['region']} | pts={row['points']} sh={row['shares']} "
            f"lk={row['likes']} cm={row['comments']} vw={row['views']}"
        )


if __name__ == "__main__":
    main()
