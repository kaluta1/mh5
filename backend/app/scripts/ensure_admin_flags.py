#!/usr/bin/env python3
"""
Ensure users with admin role have is_admin=True.
Run: python -m app.scripts.ensure_admin_flags
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.session import SessionLocal
from app.models.user import User, Role


def main():
    db = SessionLocal()
    try:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            print("No 'admin' role found in database.")
            return

        # Find users with admin role but is_admin=False
        users_to_fix = (
            db.query(User)
            .filter(User.role_id == admin_role.id, User.is_admin == False)
            .all()
        )

        if not users_to_fix:
            print("All admin-role users already have is_admin=True.")
            return

        for user in users_to_fix:
            user.is_admin = True
            print(f"Set is_admin=True for user {user.id} ({user.email})")

        db.commit()
        print(f"Updated {len(users_to_fix)} user(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
