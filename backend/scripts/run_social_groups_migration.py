"""
Script to run the social groups migration
This can be run locally with your DATABASE_URL or on Render
"""
import os
import sys
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Run the Alembic migration"""
    print("Running social groups migration...")
    
    # Check if DATABASE_URL is set
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set!")
        print("Please set it to your Neon PostgreSQL connection string:")
        print("  export DATABASE_URL='postgresql://user:password@host/database'")
        print("\nOr on Windows PowerShell:")
        print("  $env:DATABASE_URL='postgresql://user:password@host/database'")
        return False
    
    print(f"Using database: {database_url.split('@')[-1] if '@' in database_url else '***'}")
    
    try:
        # Run alembic upgrade
        result = subprocess.run(
            ["alembic", "upgrade", "heads"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=os.environ.copy(),
            check=True
        )
        print("\n✅ Migration completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Migration failed: {e}")
        return False
    except FileNotFoundError:
        print("ERROR: Alembic not found. Make sure you're in a virtual environment with alembic installed.")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
