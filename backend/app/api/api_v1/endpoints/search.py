from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from app.api import deps
from app.models import Contest, User, FanClub, Contestant
from app.models.clubs import ClubStatus

router = APIRouter()


def _search_contestant_rows(db: Session, current_user, q: str, skip: int, limit: int):
    """Phase 7: age-safe contestant search.
    - Only entries this viewer may receive (Phase 5/6 exposure + rating), not deleted.
    - Real names and places are searchable only for DOB-adult authors; minors and
      UNKNOWN-age authors are findable by username / entry text only.
    - Output is minimized with the same privacy floor as every other surface."""
    from app.services import viewer_access as va

    viewer = va.viewer_for(db, current_user)
    search_term = f"%{q}%"
    adult = va.adult_dob_clause()
    contestants = (
        db.query(Contestant)
        .options(joinedload(Contestant.user))
        .join(Contestant.user)
        .filter(
            Contestant.is_deleted == False,  # noqa: E712
            va.listing_clause(viewer),
            or_(
                Contestant.title.ilike(search_term),
                Contestant.description.ilike(search_term),
                User.username.ilike(search_term),
                and_(adult, or_(
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                    User.full_name.ilike(search_term),
                    User.continent.ilike(search_term),
                    User.region.ilike(search_term),
                    User.country.ilike(search_term),
                    User.city.ilike(search_term),
                )),
            ),
        )
        .order_by(Contestant.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    privacy = va.PrivacyCache(db)
    rows = []
    for contestant in contestants:
        user = contestant.user
        perm = privacy.display(user)
        if user is None:
            full_name = "Unknown"
        elif perm["name"] or (current_user is not None and user.id == current_user.id):
            full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.username
        else:
            full_name = user.username
        show_place = user is not None and (perm["place"] or (current_user is not None and user.id == current_user.id))
        city = user.city if show_place and user.city else None
        country = user.country if show_place and user.country else None
        continent = user.continent if show_place and user.continent else None
        location = " · ".join([x for x in (city, country, continent) if x]) or None
        description = contestant.description[:100] if contestant.description else (location or full_name)
        rows.append({
            "id": str(contestant.id),
            "title": contestant.title or full_name,
            "category": "contestant",
            "description": description,
            "full_name": full_name,
            "city": city,
            "country": country,
            "continent": continent,
        })
    return rows


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
    contests = db.query(Contest).options(joinedload(Contest.location)).filter(
        or_(
            Contest.name.ilike(search_term),
            Contest.description.ilike(search_term)
        )
    ).limit(10).all()
    
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
    
    # Search contestants (Phase 7: age-safe, see _search_contestant_rows)
    results["contestant"] = _search_contestant_rows(db, current_user, q, 0, 10)

    # Search clubs
    clubs = (
        db.query(FanClub)
        .filter(
            FanClub.is_public.is_(True),
            FanClub.status == ClubStatus.ACTIVE,
            or_(
                FanClub.name.ilike(search_term),
                FanClub.description.ilike(search_term),
            ),
        )
        .order_by(FanClub.name.asc(), FanClub.id.asc())
        .limit(10)
        .all()
    )
    
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
    limit: int = Query(10, ge=1, le=100),
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
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Search only contestants (submissions + user name + geo; Phase 7 age-safe)."""
    return [
        {k: r[k] for k in ("id", "title", "category", "description")}
        for r in _search_contestant_rows(db, current_user, q, skip, limit)
    ]


@router.get("/search/clubs")
def search_clubs(
    q: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Search only clubs"""
    search_term = f"%{q}%"
    
    clubs = (
        db.query(FanClub)
        .filter(
            FanClub.is_public.is_(True),
            FanClub.status == ClubStatus.ACTIVE,
            or_(
                FanClub.name.ilike(search_term),
                FanClub.description.ilike(search_term),
            ),
        )
        .order_by(FanClub.name.asc(), FanClub.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": str(club.id),
            "title": club.name,
            "category": "club",
            "description": club.description[:100] if club.description else None
        }
        for club in clubs
    ]
