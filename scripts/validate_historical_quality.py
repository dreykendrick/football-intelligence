#!/usr/bin/env python3
"""
Convenience script wrapper for Data Quality & Readiness CLI.
Run:
  python scripts/validate_historical_quality.py validate-historical
  python scripts/validate_historical_quality.py report
  python scripts/validate_historical_quality.py check-gate
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.quality.cli import main

if __name__ == "__main__":
    main()
