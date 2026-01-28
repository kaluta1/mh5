from app.db.session import SessionLocal
from app.models.contests import Contestant, ContestantSeason, ContestSeasonLink, ContestSeason
from app.models.contest import Contest
import json

db = SessionLocal()
cid = 14
c = db.query(Contestant).filter(Contestant.id == cid).first()
if not c:
    print(f"Contestant {cid} not found")
else:
    print(f"Contestant {cid} found. Season ID: {c.season_id}")
    
    # Logic from crud_contestant.py
    contestant_season_link = db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == cid,
        ContestantSeason.is_active == True
    ).first()
    
    season = None
    if contestant_season_link:
        print(f"Found active ContestantSeason link: {contestant_season_link.season_id}")
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contestant_season_link.season_id,
            ContestSeason.is_deleted == False
        ).first()
    
    if not season:
        print("No active season found via ContestantSeason, trying fallback")
        season = db.query(ContestSeason).filter(ContestSeason.id == c.season_id).first()

    if season:
        print(f"Found Season: {season.id}, Title: {season.title}")
        contest_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if contest_link:
            print(f"Found active ContestSeasonLink. Contest ID: {contest_link.contest_id}")
            contest = db.query(Contest).filter(Contest.id == contest_link.contest_id).first()
            if contest:
                print(f"Found Contest: {contest.id}, Name: {contest.name}, Img: {contest.image_url}")
            else:
                print("Contest not found")
        else:
            print("No active ContestSeasonLink found for this season")
    else:
        print("Season not found")

db.close()
