#!/usr/bin/env python3
"""
Development Database Reset Tool (DEVELOPMENT USE ONLY)
Drops and recreates all database tables via Alembic migrations.
DO NOT RUN IN PRODUCTION.
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from alembic.config import Config

from alembic import command
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


def reset_development_database() -> None:
    print("==========================================================")
    print("   DEVELOPMENT DATABASE RESET WORKFLOW")
    print("==========================================================")
    print(f"Target Database: {settings.POSTGRES_DB} on {settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}")

    if settings.APP_ENV.lower() == "production":
        print("[ERROR] Database reset is prohibited in production environment!")
        sys.exit(1)

    print("\n[1/3] Dropping all existing tables...")
    try:
        Base.metadata.drop_all(bind=engine)
        print("  - Drop all tables: SUCCESS")
    except Exception as e:
        print(f"  - Database connection or drop failed: {e}")
        print("  - Note: Ensure PostgreSQL is running if executing online reset.")

    print("\n[2/3] Running Alembic Migrations to HEAD...")
    try:
        alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
        command.upgrade(alembic_cfg, "head")
        print("  - Alembic Upgrade Head: SUCCESS")
    except Exception as e:
        print(f"  - Migration failed: {e}")

    print("\n[3/3] Database reset workflow complete.")


if __name__ == "__main__":
    reset_development_database()
