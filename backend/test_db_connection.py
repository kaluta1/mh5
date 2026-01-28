#!/usr/bin/env python3
"""
Diagnostic script to test database connection and authentication.
Run this to diagnose database connection issues.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from app.core.config import settings
from app.db.session import SessionLocal
from app.crud import user as crud_user
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_database_connection():
    """Test basic database connection"""
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)
    
    database_url = settings.SQLALCHEMY_DATABASE_URI
    print(f"\nDatabase URL: {database_url.split('@')[0]}@****@{database_url.split('@')[1] if '@' in database_url else 'N/A'}")
    
    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
            pool_timeout=10,
            connect_args={"connect_timeout": 10},
            echo=False
        )
        
        # Test connection
        print("\n1. Testing basic connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("   ✅ Basic connection successful!")
            print(f"   Result: {result.fetchone()}")
        
        # Test users table exists
        print("\n2. Testing users table access...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            count = result.fetchone()[0]
            print(f"   ✅ Users table accessible!")
            print(f"   Total users in database: {count}")
        
        # Test query a specific user
        print("\n3. Testing user query...")
        db = SessionLocal()
        try:
            # Try to get first user
            first_user = db.query(crud_user.user.get(db, 1))
            if first_user:
                print(f"   ✅ Can query users!")
            else:
                print("   ⚠️  No users found (this is OK if database is empty)")
        except Exception as e:
            print(f"   ❌ Error querying users: {e}")
        finally:
            db.close()
        
        return True
        
    except OperationalError as e:
        print(f"\n❌ Database connection error: {e}")
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        print(f"\nError details: {error_msg}")
        print("\nPossible issues:")
        print("  - DATABASE_URL is incorrect or missing")
        print("  - Database server is not accessible")
        print("  - Network/firewall issues")
        print("  - SSL configuration issues (for Neon PostgreSQL)")
        return False
    except SQLAlchemyError as e:
        print(f"\n❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_authentication(email_or_username: str, password: str):
    """Test authentication flow"""
    print("\n" + "=" * 60)
    print("Testing Authentication Flow")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        print(f"\nAttempting to authenticate: '{email_or_username}'")
        
        # Test get_by_email
        print("\n1. Testing get_by_email...")
        try:
            user_by_email = crud_user.get_by_email(db, email_or_username)
            if user_by_email:
                print(f"   ✅ User found by email: {user_by_email.email}")
            else:
                print(f"   ⚠️  No user found by email")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Test get_by_username
        print("\n2. Testing get_by_username...")
        try:
            user_by_username = crud_user.get_by_username(db, email_or_username)
            if user_by_username:
                print(f"   ✅ User found by username: {user_by_username.username}")
            else:
                print(f"   ⚠️  No user found by username")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Test authenticate
        print("\n3. Testing authenticate...")
        try:
            user = crud_user.authenticate(db, email_or_username, password)
            if user:
                print(f"   ✅ Authentication successful!")
                print(f"   User ID: {user.id}")
                print(f"   Email: {user.email}")
                print(f"   Username: {user.username}")
                print(f"   Is Active: {user.is_active}")
            else:
                print(f"   ❌ Authentication failed: User not found or password incorrect")
        except OperationalError as e:
            print(f"   ❌ Database connection error during authentication: {e}")
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            print(f"   Error details: {error_msg}")
        except Exception as e:
            print(f"   ❌ Error during authentication: {e}")
            import traceback
            traceback.print_exc()
            
    finally:
        db.close()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Database Connection Diagnostic Tool")
    print("=" * 60)
    
    # Test database connection
    connection_ok = test_database_connection()
    
    if not connection_ok:
        print("\n" + "=" * 60)
        print("❌ Database connection failed. Please fix connection issues first.")
        print("=" * 60)
        sys.exit(1)
    
    # If credentials provided, test authentication
    if len(sys.argv) >= 3:
        email_or_username = sys.argv[1]
        password = sys.argv[2]
        test_authentication(email_or_username, password)
    else:
        print("\n" + "=" * 60)
        print("To test authentication, run:")
        print(f"  python {sys.argv[0]} <email_or_username> <password>")
        print("=" * 60)
    
    print("\n" + "=" * 60)
    print("Diagnostic complete!")
    print("=" * 60)
