#!/usr/bin/env python3
"""
Script to delete all rounds and contestants, then create a new test round.
This is useful for testing purposes.
"""

import sys
import os
from datetime import date, datetime, timedelta
import calendar

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.round import Round, RoundStatus, round_contests
from app.models.contests import Contestant, ContestantSeason, ContestSubmission, ContestantRanking, ContestSeason
from app.models.contest import Contest, ContestVote, ContestantVerification
from app.models.voting import (
    Vote, MyFavorites, ContestLike, ContestComment, 
    ContestantReaction, ContestantShare, ContestantVoting
)
from app.models.vote_ranking import UserVoteRanking
from app.models.comment import Comment, Like
from app.models.notification import Notification
from app.crud.crud_round import CRUDRound
from sqlalchemy import text

def calculate_dates_for_month(month: int, year: int, is_nomination: bool = False):
    """Calculate all dates for a round given month/year"""
    def get_month_range(m, y):
        while m > 12:
            m -= 12
            y += 1
        last_day = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last_day)

    dates = {}
    
    # Submission (Month M)
    s_start, s_end = get_month_range(month, year)
    dates["submission_start_date"] = s_start
    dates["submission_end_date"] = s_end
    
    # Voting (Month M+1)
    v_start, v_end = get_month_range(month + 1, year)
    dates["voting_start_date"] = v_start
    dates["voting_end_date"] = v_end
    
    # City (M+2) - Participation Only
    c_start, c_end = get_month_range(month + 2, year)
    dates["city_season_start_date"] = c_start
    dates["city_season_end_date"] = c_end
    
    # Country (M+3)
    cty_start, cty_end = get_month_range(month + 3, year)
    dates["country_season_start_date"] = cty_start
    dates["country_season_end_date"] = cty_end

    # Regional (M+4)
    reg_start, reg_end = get_month_range(month + 4, year)
    dates["regional_start_date"] = reg_start
    dates["regional_end_date"] = reg_end

    # Continent (M+5)
    cont_start, cont_end = get_month_range(month + 5, year)
    dates["continental_start_date"] = cont_start
    dates["continental_end_date"] = cont_end
    
    # Global (M+6)
    glob_start, glob_end = get_month_range(month + 6, year)
    dates["global_start_date"] = glob_start
    dates["global_end_date"] = glob_end
    
    return dates

def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("RESET ROUNDS AND CONTESTANTS SCRIPT")
        print("=" * 60)
        
        # Step 1: Delete all related data first (respecting foreign key constraints)
        print("\n[1/4] Deleting related data (votes, submissions, seasons, etc.)...")
        
        # Delete in order to respect foreign key constraints
        # Order matters: delete child records before parent records
        tables_to_delete = [
            # First: Delete likes that reference comments
            ("likes", Like),
            # Then: Delete comments that reference contestants
            ("comments", Comment),
            # Then: Delete other records that reference contestants
            ("contestant_voting", ContestantVoting),
            ("user_vote_rankings", UserVoteRanking),
            ("contestant_shares", ContestantShare),
            ("contestant_reactions", ContestantReaction),
            ("contest_comments", ContestComment),
            ("contest_likes", ContestLike),
            ("my_favorites", MyFavorites),
            ("votes", Vote),
            ("contest_votes", ContestVote),
            ("notifications", Notification),
            ("contestant_verifications", ContestantVerification),
            ("contestant_rankings", ContestantRanking),
            ("contest_submissions", ContestSubmission),
            ("contestant_seasons", ContestantSeason),
        ]
        
        total_deleted = 0
        for table_name, model in tables_to_delete:
            try:
                count = db.query(model).count()
                if count > 0:
                    db.query(model).delete()
                    db.commit()
                    print(f"   ✓ Deleted {count} records from {table_name}")
                    total_deleted += count
                else:
                    print(f"   ✓ No records in {table_name}")
            except Exception as e:
                print(f"   ❌ ERROR: Could not delete from {table_name}: {str(e)}")
                db.rollback()
                # For critical tables, we need to fail or retry
                if table_name in ["likes", "comments"]:
                    print(f"   ⚠ Retrying deletion of {table_name}...")
                    try:
                        # Try using raw SQL to delete
                        # NOTE: "like" is a reserved keyword; quote it. "comment" is also safer quoted.
                        if table_name == "likes":
                            db.execute(text('DELETE FROM "like"'))
                        elif table_name == "comments":
                            db.execute(text('DELETE FROM "comment"'))
                        db.commit()
                        print(f"   ✓ Successfully deleted from {table_name} using raw SQL")
                        total_deleted += count if count > 0 else 0
                    except Exception as e2:
                        print(f"   ❌ CRITICAL: Still failed to delete {table_name}: {str(e2)}")
                        raise  # Re-raise if critical deletion fails
        
        if total_deleted == 0:
            print("   ✓ No related data to delete")
        else:
            print(f"   ✓ Total: {total_deleted} related records deleted")
        
        # Step 2: Verify critical deletions succeeded and clean up any remaining references
        print("\n[2/4] Verifying deletions and cleaning up remaining references...")
        
        # Check if comments still exist (they should be deleted)
        remaining_comments = db.query(Comment).filter(
            Comment.contestant_id.isnot(None)
        ).count()
        if remaining_comments > 0:
            print(f"   ⚠ Found {remaining_comments} comments still referencing contestants, deleting...")
            try:
                # Delete comments that reference contestants using raw SQL
                db.execute(text('DELETE FROM "comment" WHERE contestant_id IS NOT NULL'))
                db.commit()
                print(f"   ✓ Deleted {remaining_comments} comments referencing contestants")
            except Exception as e:
                print(f"   ❌ ERROR: Could not delete remaining comments: {str(e)}")
                db.rollback()
                raise
        
        # Check if likes still exist
        remaining_likes = db.query(Like).count()
        if remaining_likes > 0:
            print(f"   ⚠ Found {remaining_likes} likes still remaining, deleting...")
            try:
                db.execute(text('DELETE FROM "like"'))
                db.commit()
                print(f"   ✓ Deleted {remaining_likes} remaining likes")
            except Exception as e:
                print(f"   ⚠ Warning: Could not delete remaining likes: {str(e)}")
                db.rollback()
        
        # Step 3: Delete all contestants
        print("\n[3/4] Deleting all contestants...")
        contestants_count = db.query(Contestant).count()
        if contestants_count > 0:
            try:
                db.query(Contestant).delete()
                db.commit()
                print(f"   ✓ Deleted {contestants_count} contestants")
            except Exception as e:
                print(f"   ❌ ERROR: Could not delete contestants: {str(e)}")
                # Try using raw SQL as fallback
                try:
                    print("   ⚠ Retrying with raw SQL...")
                    db.execute(text("DELETE FROM contestants"))
                    db.commit()
                    print(f"   ✓ Deleted {contestants_count} contestants using raw SQL")
                except Exception as e2:
                    print(f"   ❌ CRITICAL: Failed to delete contestants: {str(e2)}")
                    db.rollback()
                    raise
        else:
            print("   ✓ No contestants to delete")
        
        # Step 4: Delete contest seasons that reference rounds
        print("\n[4/5] Deleting contest seasons...")
        try:
            seasons_count = db.query(ContestSeason).filter(
                ContestSeason.round_id.isnot(None)
            ).count()
            if seasons_count > 0:
                db.query(ContestSeason).filter(
                    ContestSeason.round_id.isnot(None)
                ).delete()
                db.commit()
                print(f"   ✓ Deleted {seasons_count} contest seasons linked to rounds")
            else:
                print("   ✓ No contest seasons to delete")
        except Exception as e:
            print(f"   ⚠ Warning: Could not delete contest seasons: {str(e)}")
            db.rollback()
        
        # Step 5: Delete all rounds (this will cascade delete round_contests entries)
        print("\n[5/6] Deleting all rounds...")
        rounds_count = db.query(Round).count()
        if rounds_count > 0:
            # First, delete entries from round_contests association table
            db.execute(text("DELETE FROM round_contests"))
            db.commit()
            print(f"   ✓ Deleted entries from round_contests association table")
            
            # Then delete all rounds
            db.query(Round).delete()
            db.commit()
            print(f"   ✓ Deleted {rounds_count} rounds")
        else:
            print("   ✓ No rounds to delete")
        
        # Step 6: Create a new test round
        print("\n[6/6] Creating new test round...")
        
        # Get current month and year
        today = date.today()
        current_month = today.month
        current_year = today.year
        
        # Get all active contests
        active_contests = db.query(Contest).filter(
            Contest.is_active == True,
            Contest.is_deleted == False
        ).all()
        
        if not active_contests:
            print("   ⚠ Warning: No active contests found. Creating round without contest links.")
        else:
            print(f"   ✓ Found {len(active_contests)} active contests")
        
        # Calculate dates for the current month
        dates = calculate_dates_for_month(current_month, current_year, is_nomination=False)
        
        # Create the round
        round_name = f"Round {today.strftime('%B %Y')} - Test"
        new_round = Round(
            name=round_name,
            status=RoundStatus.ACTIVE,
            is_submission_open=True,
            is_voting_open=False,
            current_season_level="submission",
            submission_start_date=dates["submission_start_date"],
            submission_end_date=dates["submission_end_date"],
            voting_start_date=dates["voting_start_date"],
            voting_end_date=dates["voting_end_date"],
            city_season_start_date=dates["city_season_start_date"],
            city_season_end_date=dates["city_season_end_date"],
            country_season_start_date=dates["country_season_start_date"],
            country_season_end_date=dates["country_season_end_date"],
            regional_start_date=dates["regional_start_date"],
            regional_end_date=dates["regional_end_date"],
            continental_start_date=dates["continental_start_date"],
            continental_end_date=dates["continental_end_date"],
            global_start_date=dates["global_start_date"],
            global_end_date=dates["global_end_date"],
        )
        
        db.add(new_round)
        db.flush()  # Get the ID without committing
        
        # Link the round to all active contests via the association table
        if active_contests:
            for contest in active_contests:
                # Insert into round_contests association table
                db.execute(
                    text("""
                        INSERT INTO round_contests (round_id, contest_id, created_at)
                        VALUES (:round_id, :contest_id, :created_at)
                    """),
                    {
                        "round_id": new_round.id,
                        "contest_id": contest.id,
                        "created_at": datetime.utcnow()
                    }
                )
        
        db.commit()
        db.refresh(new_round)
        
        print(f"   ✓ Created round: '{round_name}' (ID: {new_round.id})")
        if active_contests:
            print(f"   ✓ Linked to {len(active_contests)} active contests")
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS: Reset completed!")
        print("=" * 60)
        print(f"\nNew round details:")
        print(f"  - ID: {new_round.id}")
        print(f"  - Name: {new_round.name}")
        print(f"  - Status: {new_round.status.value}")
        print(f"  - Submission: {new_round.submission_start_date} to {new_round.submission_end_date}")
        print(f"  - Voting: {new_round.voting_start_date} to {new_round.voting_end_date}")
        print(f"  - Linked contests: {len(active_contests)}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
