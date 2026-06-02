"""
Temporary debug endpoint - like Laravel's dd().
Visit: /api/v1/debug/continental/15
Remove this file after the issue is resolved.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Any

from app.api import deps
from app.models.contests import (
    Contestant,
    ContestSeason,
    ContestSeasonLink,
    ContestantSeason,
    SeasonLevel,
)
from app.models.contest import Contest
from app.models.user import User

router = APIRouter()


@router.get("/continental/{contest_id}")
def debug_continental(
    contest_id: int,
    db: Session = Depends(deps.get_db),
) -> dict:
    """Raw database dump for debugging continental contest display."""
    result = {
        "contest_id": contest_id,
        "contest": None,
        "seasons": [],
        "continental_season": None,
        "member_count": 0,
        "members": [],
        "old_query_count": 0,
        "old_query_countries": {},
        "new_query_count": 0,
        "new_query_countries": {},
        "recommendation": None,
    }

    # 1. Contest info
    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
    if not contest:
        result["recommendation"] = "Contest not found"
        return result

    result["contest"] = {
        "name": contest.name,
        "level": contest.level,
        "contest_mode": getattr(contest, "contest_mode", None),
    }

    # 2. All active seasons
    season_links = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeason.is_deleted == False,
        )
        .all()
    )
    for link, season in season_links:
        result["seasons"].append({
            "season_id": season.id,
            "level": season.level.value if hasattr(season.level, "value") else str(season.level),
            "round_id": season.round_id,
            "link_active": link.is_active,
        })

    # 3. Find continental season
    continental = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True,
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
        )
        .first()
    )

    if not continental:
        result["recommendation"] = (
            "NO active continental season found. "
            "The regional -> continental migration never ran or failed. "
            "Code fix alone cannot help — run the migration first."
        )
        return result

    continental_season = continental[1]
    result["continental_season"] = {
        "season_id": continental_season.id,
        "round_id": continental_season.round_id,
        "level": continental_season.level.value,
    }

    # 4. Active members in continental season
    members = (
        db.query(ContestantSeason, Contestant, User)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .outerjoin(User, User.id == Contestant.user_id)
        .filter(
            ContestantSeason.season_id == continental_season.id,
            ContestantSeason.is_active == True,
            Contestant.is_deleted == False,
        )
        .all()
    )

    result["member_count"] = len(members)
    country_breakdown = {}
    member_ids = []
    for cs, c, u in members:
        member_ids.append(c.id)
        country = getattr(c, "country", None) or "UNKNOWN"
        country_breakdown[country] = country_breakdown.get(country, 0) + 1
        result["members"].append({
            "contestant_id": c.id,
            "user_id": c.user_id,
            "username": getattr(u, "username", None),
            "country": country,
            "region": getattr(c, "region", None),
            "continent": getattr(c, "continent", None),
            "season_id": c.season_id,
            "round_id": c.round_id,
        })

    result["member_countries"] = country_breakdown

    # 5. Old buggy query (season_id == contest_id)
    old_q = (
        db.query(Contestant)
        .filter(Contestant.season_id == contest_id, Contestant.is_deleted == False)
        .all()
    )
    result["old_query_count"] = len(old_q)
    old_countries = {}
    for c in old_q:
        country = getattr(c, "country", None) or "UNKNOWN"
        old_countries[country] = old_countries.get(country, 0) + 1
    result["old_query_countries"] = old_countries

    # 6. New fixed query (ContestantSeason membership)
    if member_ids:
        new_q = (
            db.query(Contestant)
            .filter(Contestant.id.in_(member_ids), Contestant.is_deleted == False)
            .all()
        )
        result["new_query_count"] = len(new_q)
        new_countries = {}
        for c in new_q:
            country = getattr(c, "country", None) or "UNKNOWN"
            new_countries[country] = new_countries.get(country, 0) + 1
        result["new_query_countries"] = new_countries

    # 7. Recommendation
    if len(members) == 0:
        result["recommendation"] = (
            "CRITICAL: No ContestantSeason links exist for continental season. "
            "The migration that promotes regional winners to continental never ran. "
            "You need to run: python scripts/process_season_migrations.py"
        )
    elif len(old_q) < len(members):
        result["recommendation"] = (
            f"OK: Database has {len(members)} continental members from multiple countries, "
            f"but old query only returns {len(old_q)}. "
            f"The code fix IS needed and should work after proper deploy+restart. "
            f"If still not working, the backend process did NOT restart — check PM2/systemctl."
        )
    else:
        result["recommendation"] = (
            "All members already have season_id == contest_id. "
            "The data looks correct — check if backend was actually restarted."
        )

    return result
