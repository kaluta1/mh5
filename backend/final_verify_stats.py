from app.db.session import SessionLocal
from app.crud.crud_contestant import crud_contestant
import json

db = SessionLocal()
cid = 6
data = crud_contestant.get_with_stats(db, cid)
if data:
    print(f"Contestant {cid} stats:")
    print(f"  Contestant Image: {data.get('contestant_image_url')}")
    print(f"  Contest Title: {data.get('contest_title')}")
    print(f"  Contest Image: {data.get('contest_image_url')}")
    print(f"  Author Avatar: {data.get('author_avatar_url')}")
else:
    print(f"Contestant {cid} not found")

db.close()
