#!/usr/bin/env python3
"""
Convenience script wrapper for Historical Dataset Release CLI.
Run:
  python scripts/historical_dataset.py list
  python scripts/historical_dataset.py build --dataset mvp_a_historical --version v1
  python scripts/historical_dataset.py validate --dataset mvp_a_historical --version v1
  python scripts/historical_dataset.py approve --dataset mvp_a_historical --version v1 --accept-warning "Kickoff times default to 12:00 UTC (date-only precision)"
  python scripts/historical_dataset.py verify --dataset mvp_a_historical --version v1
  python scripts/historical_dataset.py report --dataset mvp_a_historical --version v1
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.dataset.cli import main

if __name__ == "__main__":
    main()
