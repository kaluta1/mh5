from app.db.session import SessionLocal
from app.models.contests import Contestant, ContestantSeason, ContestSeasonLink
from app.models.contest import Contest

db = SessionLocal()
# Find a contest with image
contest = db.query(Contest).filter((Contest.image_url != None) | (Contest.cover_image_url != None)).first()
if contest:
    print(f"Contest {contest.id} has image: {contest.image_url or contest.cover_image_url}")
    # Find active seasons for this contest
    links = db.query(ContestSeasonLink).filter(ContestSeasonLink.contest_id == contest.id, ContestSeasonLink.is_active == True).all()
    season_ids = [l.season_id for l in links]
    print(f"Season IDs linked to contest {contest.id}: {season_ids}")
    
    # Find a contestant in any of these seasons
    c = db.query(Contestant).filter((Contestant.season_id.in_(season_ids)) | (Contestant.id.in_(
        db.query(ContestantSeason.contestant_id).filter(ContestantSeason.season_id.in_(season_ids), ContestantSeason.is_active == True)
    ))).first()
    
    if c:
        print(f"Contestant {c.id} is linked to contest {contest.id}")
    else:
        print("No contestant found for these seasons")
else:
    print("No contest with image found")
db.close()
