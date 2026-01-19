from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api import deps
from app.models import Contest, User, FanClub, Contestant

router = APIRouter()


class SearchResult:
    def __init__(self, id: str, title: str, category: str, description: str = None):
        self.id = id
        self.title = title
        self.category = category
        self.description = description


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """
    Search for contests, contestants (users), and clubs.
    
    Categories:
    - contest: Contest entries
    - contestant: Users/Contestants
    - club: Clubs
    """
    results = {
        "contest": [],
        "contestant": [],
        "club": []
    }
    
    search_term = f"%{q}%"
    
    # Search contests (with basic geo info from level/location)
    contests = db.query(Contest).limit(10).filter(
        or_(
            Contest.name.ilike(search_term),
            Contest.description.ilike(search_term)
        )
    ).all()
    
    for contest in contests:
        location_name = None
        try:
            # Contest.location est optionnel, on récupère juste le nom si présent
            if contest.location is not None:
                location_name = contest.location.name
        except Exception:
            location_name = None

        results["contest"].append({
            "id": str(contest.id),
            "title": contest.name,
            "category": "contest",
            "description": contest.description[:100] if contest.description else None,
            "level": contest.level,
            "location_name": location_name,
        })
    
    # Search contestants (by submission, user name and geo fields)
    contestants = (
        db.query(Contestant)
        .join(Contestant.user)
        .filter(
            or_(
                Contestant.title.ilike(search_term),
                Contestant.description.ilike(search_term),
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.full_name.ilike(search_term),
                User.username.ilike(search_term),
                User.continent.ilike(search_term),
                User.region.ilike(search_term),
                User.country.ilike(search_term),
                User.city.ilike(search_term),
            )
        )
        .limit(10)
        .all()
    )
    
    for contestant in contestants:
        user = contestant.user
        full_name = (
            f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            if user
            else "Unknown"
        )
        location_parts = [
            part
            for part in [
                (user.city if user and user.city else None),
                (user.country if user and user.country else None),
                (user.continent if user and user.continent else None),
            ]
            if part
        ]
        location = " · ".join(location_parts) if location_parts else None
        description = (
            contestant.description[:100]
            if contestant.description
            else (location or full_name)
        )
        results["contestant"].append({
            "id": str(contestant.id),
            "title": contestant.title or full_name,
            "category": "contestant",
            "description": description,
            "full_name": full_name,
            "city": user.city if user and user.city else None,
            "country": user.country if user and user.country else None,
            "continent": user.continent if user and user.continent else None,
        })
    
    # Search clubs
    clubs = db.query(FanClub).filter(
        or_(
            FanClub.name.ilike(search_term),
            FanClub.description.ilike(search_term)
        )
    ).limit(10).all()
    
    for club in clubs:
        results["club"].append({
            "id": str(club.id),
            "title": club.name,
            "category": "club",
            "description": club.description[:100] if club.description else None
        })
    
    return results


@router.get("/search/contests")
def search_contests(
    q: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=10),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Search only contests"""
    search_term = f"%{q}%"
    
    contests = db.query(Contest).filter(
        or_(
            Contest.name.ilike(search_term),
            Contest.description.ilike(search_term)
        )
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": str(contest.id),
            "title": contest.name,
            "category": "contest",
            "description": contest.description[:100] if contest.description else None
        }
        for contest in contests
    ]


@router.get("/search/contestants")
def search_contestants(
    q: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=10),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Search only contestants (submissions + user name + geo)."""
    search_term = f"%{q}%"
    
    contestants = (
        db.query(Contestant)
        .join(Contestant.user)
        .filter(
            or_(
                Contestant.title.ilike(search_term),
                Contestant.description.ilike(search_term),
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.full_name.ilike(search_term),
                User.username.ilike(search_term),
                User.continent.ilike(search_term),
                User.region.ilike(search_term),
                User.country.ilike(search_term),
                User.city.ilike(search_term),
            )
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    results = []
    for contestant in contestants:
        user = contestant.user
        full_name = (
            f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            if user
            else "Unknown"
        )
        location_parts = [
            part
            for part in [
                (user.city if user and user.city else None),
                (user.country if user and user.country else None),
                (user.continent if user and user.continent else None),
            ]
            if part
        ]
        location = " · ".join(location_parts) if location_parts else None
        description = (
            contestant.description[:100]
            if contestant.description
            else (location or full_name)
        )
        results.append({
            "id": str(contestant.id),
            "title": contestant.title or full_name,
            "category": "contestant",
            "description": description,
        })
    
    return results


@router.get("/search/clubs")
def search_clubs(
    q: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=10),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Search only clubs"""
    search_term = f"%{q}%"
    
    clubs = db.query(FanClub).filter(
        or_(
            FanClub.name.ilike(search_term),
            FanClub.description.ilike(search_term)
        )
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": str(club.id),
            "title": club.name,
            "category": "club",
            "description": club.description[:100] if club.description else None
        }
        for club in clubs
    ]
