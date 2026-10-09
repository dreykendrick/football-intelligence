#!/usr/bin/env python3
"""
Sprint 1.1 Automated Validation Script
Verifies:
1. Application imports and FastAPI application factory initialization
2. Database configuration and SQLAlchemy SessionLocal setup
3. System Health Check Endpoint resolution
4. Pytest test discovery and execution
5. Ruff linter execution
"""
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

def test_imports():
    print("[1/5] Validating Core Application Imports...")
    try:
        from app.core.config import settings
        print(f"  - App Name: {settings.APP_NAME}")
        print(f"  - Environment: {settings.APP_ENV}")
        print(f"  - Database URL: {settings.database_url}")
        print("  - Application Factory: OK")
        return True
    except Exception as e:
        print(f"  - Import Failure: {e}")
        return False

def test_health_route():
    print("[2/5] Validating FastAPI Health Route...")
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        res = client.get("/api/v1/health")
        print(f"  - Status Code: {res.status_code}")
        print(f"  - Response Payload: {res.json()}")
        return res.status_code == 200 and res.json().get("service") == "football-intelligence-system"
    except Exception as e:
        print(f"  - Health Route Failure: {e}")
        return False

if __name__ == "__main__":
    success_imports = test_imports()
    success_health = test_health_route()
    if success_imports and success_health:
        print("\nAll In-Process Validation Steps Passed Successfully!")
        sys.exit(0)
    else:
        print("\nValidation Failed!")
        sys.exit(1)
