from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.round import Round, round_contests

db = SessionLocal()

print("--- Checking Contests Voting Type ---")

# Check all contests
total = db.query(Contest).count()
with_voting = db.query(Contest).filter(Contest.voting_type_id.isnot(None)).count()
without_voting = db.query(Contest).filter(Contest.voting_type_id.is_(None)).count()

print(f"Total Contests: {total}")
print(f"With Voting Type (Nomination): {with_voting}")
print(f"Without Voting Type (Participation): {without_voting}")

# Check linked to active rounds?
print("\n--- Checking Filter Logic Simulation ---")
# Simulate the join logic used in schema.py
# Query: Rounds with Voting Type Contests
rounds_voting = db.query(Round.id).join(round_contests).join(Contest).filter(Contest.voting_type_id.isnot(None)).distinct().all()
print(f"Rounds containing Nomination contests: {[r[0] for r in rounds_voting]}")

rounds_part = db.query(Round.id).join(round_contests).join(Contest).filter(Contest.voting_type_id.is_(None)).distinct().all()
print(f"Rounds containing Participation contests: {[r[0] for r in rounds_part]}")

db.close()
