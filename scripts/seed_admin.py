#!/usr/bin/env python3
"""
Seed script — creates the default admin user if it does not already exist.

Usage (run from the project root):
    python -m scripts.seed_admin

Or directly:
    python scripts/seed_admin.py

The DATABASE_URL environment variable (or .env file) must be set before
running this script.
"""

import os
import sys

# Allow running as `python scripts/seed_admin.py` from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, UserRole
from app.auth import hash_password

# ---------------------------------------------------------------------------
# Admin seed configuration
# ---------------------------------------------------------------------------

ADMIN_EMAIL = "admin@assignly.com"
ADMIN_PASSWORD = "admin123"
ADMIN_NAME = "Admin"


def seed_admin(db: Session) -> bool:
    """
    Create the admin user if it does not already exist.

    Returns True if the user was created, False if it already existed.
    """
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
        print(f"[seed_admin] Admin user already exists (email={ADMIN_EMAIL}). Skipping.")
        return False

    admin = User(
        name=ADMIN_NAME,
        email=ADMIN_EMAIL,
        hashed_password=hash_password(ADMIN_PASSWORD),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    print(f"[seed_admin] Admin user created successfully (id={admin.id}, email={admin.email}).")
    return True


def main() -> None:
    db: Session = SessionLocal()
    try:
        seed_admin(db)
    except Exception as exc:
        print(f"[seed_admin] ERROR — failed to seed admin user: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
