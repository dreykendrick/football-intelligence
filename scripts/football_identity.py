#!/usr/bin/env python3
"""
Convenience script wrapper for Football Identity Resolution CLI.
Run:
  python scripts/football_identity.py audit
  python scripts/football_identity.py resolve --provider football_data_co_uk --external-name "Man United"
  python scripts/football_identity.py verify-gate
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.identity.cli import main

if __name__ == "__main__":
    main()
