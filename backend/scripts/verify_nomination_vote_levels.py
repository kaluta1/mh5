#!/usr/bin/env python3
"""Verify list card counts match detail rosters for nomination vote levels.

Usage:
  python scripts/verify_nomination_vote_levels.py --base-url http://localhost:8001/api/v1 --round-id 21
  python scripts/verify_nomination_vote_levels.py --base-url https://myhigh5.com/api/v1 --round-id 21
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def get(base: str, path: str) -> dict | list:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=90) as resp:
        return json.loads(resp.read().decode())


def _debug_log(payload: dict) -> None:
    log_path = Path(__file__).resolve().parents[2] / ".cursor" / "debug-e34593.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload.setdefault("sessionId", "e34593")
        payload.setdefault("timestamp", int(time.time() * 1000))
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


def _fetch_build_id(base: str) -> str:
    try:
        data = get(base, "/build-info")
        if isinstance(data, dict):
            return data.get("build_id") or data.get("git_sha") or "unknown"
    except Exception:
        pass
    origin = base.replace("/api/v1", "").rstrip("/")
    for url in (f"{origin}/health", f"{base}/health"):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return data.get("build_id") or data.get("git_sha") or "unknown"
        except Exception:
            continue
    try:
        req = urllib.request.Request(
            f"{base}/rounds/?limit=1",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.headers.get("X-Backend-Build-Id", "unknown")
    except Exception:
        return "unknown"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--round-id", type=int, required=True)
    p.add_argument("--contest-id", type=int, default=7)
    args = p.parse_args()
    base = args.base_url.rstrip("/")
    cid = args.contest_id
    rid = args.round_id
    failures = 0

    # 0) Confirm backend build is deployed
    build_id = "unknown"
    try:
        build_id = _fetch_build_id(base)
        print(f"Backend build: {build_id}")
        if "nomination-roster-fix" not in str(build_id):
            print("[WARN] Old backend still running — run scripts/deploy_vps_backend.sh on VPS")
    except Exception as e:
        print(f"[WARN] Could not detect build id: {e}")

    _debug_log(
        {
            "runId": "verify-prod",
            "hypothesisId": "deploy",
            "location": "verify_nomination_vote_levels.py:main",
            "message": "backend build check",
            "data": {"build_id": build_id, "base_url": base, "round_id": rid},
        }
    )

    cases = [
        ("country", {"filterCountry": "Tanzania"}),
        ("regional", {"filterRegion": "East Africa"}),
        ("continental", {"filterContinent": "Africa"}),
    ]

    print(f"Checking contest {cid} on round {rid} @ {base}\n")
    for level, geo in cases:
        q = f"roundId={rid}&contestMode=nomination&contestLevel={level}&contestLimit=200"
        for k, v in geo.items():
            q += f"&{k}={urllib.parse.quote(v)}"
        rounds = get(base, f"/rounds/?{q}")
        contests = (rounds[0].get("contests") if rounds else []) or []
        row = next((c for c in contests if c.get("id") == cid), None)
        list_count = int(row.get("participants_count") or 0) if row else None
        list_total = len(contests)

        dq = f"entryType=nomination&contestLevel={level}&roundId={rid}"
        for k, v in geo.items():
            dq += f"&{k}={urllib.parse.quote(v)}"
        detail = get(base, f"/contests/{cid}?{dq}")
        rows = detail.get("contestants") or []
        detail_count = len(rows)
        season_level = (rows[0].get("season") or {}).get("level") if rows else None

        ok_count = list_count is not None and list_count == detail_count
        ok_season = True
        if level == "continental" and detail_count > 0:
            ok_season = season_level in ("continent", "continental")
        elif level == "regional" and detail_count > 0:
            ok_season = season_level in ("regional", "region")
        elif level == "country" and detail_count > 0:
            ok_season = season_level in ("country", "city")

        status = "OK" if ok_count and ok_season else "FAIL"
        if status == "FAIL":
            failures += 1
        in_list = list_count is not None
        print(
            f"[{status}] {level}: list_total={list_total} in_list={in_list} "
            f"list_count={list_count} detail={detail_count} season={season_level}"
        )
        if level == "regional" and list_total == 0 and detail_count > 0:
            print("       ^ regional list empty but detail has nominees (eligibility bug)")
        if level == "continental" and detail_count > 0 and not ok_season:
            print("       ^ continental tab showing non-continental season (fallback bug)")

        _debug_log(
            {
                "runId": "verify-prod",
                "hypothesisId": "E" if level == "regional" else "F" if level == "continental" else "A",
                "location": "verify_nomination_vote_levels.py:case",
                "message": f"{level} verification",
                "data": {
                    "status": status,
                    "round_id": rid,
                    "contest_id": cid,
                    "list_total": list_total,
                    "in_list": in_list,
                    "list_count": list_count,
                    "detail_count": detail_count,
                    "season_level": season_level,
                    "build_id": build_id,
                },
            }
        )

    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
