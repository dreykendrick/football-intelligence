#!/usr/bin/env python3
"""
Convenience script wrapper for Feature Engineering CLI.
Run:
  python scripts/generate_features.py catalog
  python scripts/generate_features.py generate --match-id <UUID>
  python scripts/generate_features.py generate-bulk --competition PREM --season 2023/24
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.features.cli import main

if __name__ == "__main__":
    main()
