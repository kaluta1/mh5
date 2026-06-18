#!/usr/bin/env python3
"""
Script to fetch all contests from the database
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import json
from datetime import datetime

# Load backend/.env via app.core.config (same as the API).
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@localhost/myhigh5":
    print(
        "ERROR: DATABASE_URL is not set. Please set DATABASE_URL in backend/.env.",
        file=sys.stderr,
    )
    sys.exit(2)

def format_date(date_obj):
    """Format date object to string"""
    if date_obj is None:
        return None
    if isinstance(date_obj, datetime):
        return date_obj.isoformat()
    return str(date_obj)

def fetch_all_contests():
    """Fetch all contests from the database.

    Returns a tuple (contests, has_voting_type_id).
    """
    try:
        # Create engine
        engine = create_engine(DATABASE_URL, echo=False)

        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()

        # First, get the actual columns in the table
        columns_query = text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'contest'
            ORDER BY ordinal_position
        """)
        columns_result = session.execute(columns_query)
        available_columns = [row[0] for row in columns_result]

        print(f"Available columns in contest table: {', '.join(available_columns)}")

        # Build query dynamically based on available columns
        select_fields = []
        for col in ['id', 'name', 'description', 'contest_type', 'cover_image_url',
                   'image_url', 'is_active', 'is_submission_open', 'is_voting_open',
                   'level', 'location_id', 'voting_type_id', 'category_id', 'template_id',
                   'gender_restriction', 'max_entries_per_user', 'created_at', 'updated_at']:
            if col in available_columns:
                select_fields.append(col)

        # Add date fields if they exist
        for col in ['submission_start_date', 'submission_end_date', 'voting_start_date', 'voting_end_date']:
            if col in available_columns:
                select_fields.append(col)

        # Remember which optional columns exist for display/summary logic
        has_voting_type_id = 'voting_type_id' in available_columns

        query_str = f"SELECT {', '.join(select_fields)} FROM contest ORDER BY id"
        query = text(query_str)

        result = session.execute(query)
        contests = []

        for row in result:
            # Create a dictionary from the row
            contest = {}
            for i, col in enumerate(select_fields):
                value = row[i]
                # Format dates
                if 'date' in col.lower() or col in ['created_at', 'updated_at']:
                    contest[col] = format_date(value)
                else:
                    contest[col] = value
            contests.append(contest)

        session.close()
        engine.dispose()

        return contests, has_voting_type_id

    except Exception as e:
        print(f"Error fetching contests: {str(e)}", file=sys.stderr)
        raise

def fetch_all_contestants_counts(contest_ids):
    """Fetch the count of contestants for all contests in one query.

    Modern contestants are linked to a contest through:
        contest -> contest_season_links -> contest_seasons -> contestant_seasons -> contestants

    The legacy `contestants.season_id` column is unreliable (it sometimes stored
    a contest id, sometimes a season id) and is the reason counts used to look
    Tanzania-only for continental contests: only legacy rows happened to match,
    and those rows were mostly Tanzania.
    """
    if not contest_ids:
        return {}

    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Proper count: join contest -> seasons -> contestant_seasons -> contestants
        query = text("""
            SELECT
                csl.contest_id AS contest_id,
                COUNT(DISTINCT cs.contestant_id) AS count
            FROM contest_season_links csl
            JOIN contest_seasons sess ON sess.id = csl.season_id
            JOIN contestant_seasons cs ON cs.season_id = sess.id
            JOIN contestants c ON c.id = cs.contestant_id
            WHERE csl.contest_id = ANY(:contest_ids)
              AND csl.is_active = true
              AND cs.is_active = true
              AND c.is_deleted = false
              AND sess.is_deleted = false
            GROUP BY csl.contest_id
        """)

        result = session.execute(query, {"contest_ids": contest_ids})
        counts = {row[0]: row[1] for row in result}

        session.close()
        engine.dispose()

        return counts

    except Exception as e:
        print(f"Error counting contestants: {str(e)}", file=sys.stderr)
        return {}

def main():
    """Main function"""
    print("Fetching all contests from database...")
    print("=" * 80)
    
    contests, has_voting_type_id = fetch_all_contests()

    print(f"\nTotal contests found: {len(contests)}\n")
    
    if not contests:
        print("No contests found in the database.")
        return
    
    # Fetch all contestant counts in one query
    print("Fetching contestant counts...")
    contest_ids = [c['id'] for c in contests]
    contestants_counts = fetch_all_contestants_counts(contest_ids)
    
    # Add counts to contests
    for contest in contests:
        contest['contestants_count'] = contestants_counts.get(contest['id'], 0)
    
    # Display contests (show only summary for large lists)
    if len(contests) > 20:
        print(f"\nShowing summary for {len(contests)} contests (use JSON export for full details)...\n")
        for i, contest in enumerate(contests[:20], 1):
            is_nomination = contest.get('voting_type_id') if has_voting_type_id else None
            print(f"{i}. ID: {contest['id']} | {contest['name']} | Type: {contest['contest_type']} | "
                  f"Active: {contest['is_active']} | Contestants: {contest['contestants_count']} | "
                  f"Nomination: {'Yes' if is_nomination else 'No'}")
        print(f"\n... and {len(contests) - 20} more contests")
    else:
        # Display all contests in detail
        for i, contest in enumerate(contests, 1):
            print(f"\n{'='*80}")
            print(f"Contest #{i} - ID: {contest['id']}")
            print(f"{'='*80}")
            print(f"Name: {contest['name']}")
            print(f"Type: {contest['contest_type']}")
            print(f"Level: {contest['level']}")
            print(f"Active: {contest['is_active']}")
            print(f"Submission Open: {contest['is_submission_open']}")
            print(f"Voting Open: {contest['is_voting_open']}")
            print(f"Gender Restriction: {contest['gender_restriction'] or 'None'}")
            print(f"Max Entries Per User: {contest['max_entries_per_user']}")
            
            if contest.get('description'):
                desc = contest['description'][:100] + "..." if len(contest['description']) > 100 else contest['description']
                print(f"Description: {desc}")
            
            if has_voting_type_id and contest.get('voting_type_id'):
                print(f"Voting Type ID: {contest['voting_type_id']} (This is a NOMINATION)")
            elif has_voting_type_id:
                print(f"Voting Type ID: None (This is a PARTICIPATION)")
            
            if 'submission_start_date' in contest or 'submission_end_date' in contest:
                print(f"\nDates:")
                if 'submission_start_date' in contest or 'submission_end_date' in contest:
                    print(f"  Submission: {contest.get('submission_start_date', 'N/A')} to {contest.get('submission_end_date', 'N/A')}")
                if 'voting_start_date' in contest or 'voting_end_date' in contest:
                    print(f"  Voting: {contest.get('voting_start_date', 'N/A')} to {contest.get('voting_end_date', 'N/A')}")
            
            print(f"\nContestants Count: {contest['contestants_count']}")
            
            print(f"\nCreated: {contest.get('created_at', 'N/A')}")
            print(f"Updated: {contest.get('updated_at', 'N/A')}")
    
    # Save to JSON file
    output_file = "contests_export.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(contests, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n{'='*80}")
    print(f"All contests exported to: {output_file}")
    print(f"{'='*80}")
    
    # Summary statistics
    print(f"\n{'='*80}")
    print("SUMMARY STATISTICS")
    print(f"{'='*80}")
    print(f"Total Contests: {len(contests)}")
    print(f"Active Contests: {sum(1 for c in contests if c['is_active'])}")
    print(f"Submission Open: {sum(1 for c in contests if c['is_submission_open'])}")
    print(f"Voting Open: {sum(1 for c in contests if c['is_voting_open'])}")
    if has_voting_type_id:
        print(f"Nominations (has voting_type_id): {sum(1 for c in contests if c['voting_type_id'])}")
        print(f"Participations (no voting_type_id): {sum(1 for c in contests if not c['voting_type_id'])}")
    else:
        print("Nominations/Participations: voting_type_id column not present in this database")
    
    # Count total contestants (already fetched)
    total_contestants = sum(c['contestants_count'] for c in contests)
    contests_with_contestants = sum(1 for c in contests if c['contestants_count'] > 0)
    
    print(f"\nContests with contestants: {contests_with_contestants}/{len(contests)}")
    print(f"Total contestants across all contests: {total_contestants}")

if __name__ == "__main__":
    main()
