"""
Script to manually create January round and link all contests.
This can be run independently or called from the scheduler.

Usage:
    python scripts/create_january_round.py
"""
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.monthly_round_scheduler import monthly_round_scheduler

def main():
    print("=" * 60)
    print("Creating January Round and Linking All Contests")
    print("=" * 60)
    
    try:
        round_obj = monthly_round_scheduler.ensure_january_round_exists()
        
        if round_obj:
            print(f"\n✅ Success! January round ready:")
            print(f"   - ID: {round_obj.id}")
            print(f"   - Name: {round_obj.name}")
            print(f"   - Status: {round_obj.status}")
            print(f"   - Submission Open: {round_obj.is_submission_open}")
            print(f"   - Voting Open: {round_obj.is_voting_open}")
        else:
            print("\n❌ Failed to create or retrieve January round")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
