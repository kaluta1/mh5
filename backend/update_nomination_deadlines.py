#!/usr/bin/env python3
"""
Script to update existing nomination rounds to have +32 days deadline.
This updates the submission_end_date for all rounds linked to contests with voting_type_id (nominations).
"""

import sys
import os

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.round import Round
from app.models.contest import Contest
from datetime import timedelta
from sqlalchemy import and_

def update_nomination_rounds():
    """Update all nomination rounds to have +32 days deadline"""
    db = SessionLocal()
    
    try:
        # Find all contests that are nominations (have voting_type_id)
        nomination_contests = db.query(Contest).filter(
            Contest.voting_type_id.isnot(None)
        ).all()
        
        print(f"Found {len(nomination_contests)} nomination contests")
        
        updated_rounds = 0
        for contest in nomination_contests:
            # Find all rounds linked to this contest
            rounds = db.query(Round).filter(
                Round.contest_id == contest.id
            ).all()
            
            for round_obj in rounds:
                if round_obj.submission_end_date:
                    # Add 32 days to the existing submission_end_date
                    new_end_date = round_obj.submission_end_date + timedelta(days=32)
                    old_date = round_obj.submission_end_date
                    round_obj.submission_end_date = new_end_date
                    updated_rounds += 1
                    print(f"  - Round {round_obj.id} ({round_obj.name}): {old_date} -> {new_end_date}")
        
        if updated_rounds > 0:
            db.commit()
            print(f"\n[OK] Updated {updated_rounds} rounds with +32 days deadline")
        else:
            print("\n[INFO] No rounds found to update")
            
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Failed to update rounds: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Updating nomination rounds to have +32 days deadline")
    print("=" * 60)
    
    success = update_nomination_rounds()
    
    if success:
        print("\n[OK] Script completed successfully")
        sys.exit(0)
    else:
        print("\n[ERROR] Script failed")
        sys.exit(1)
