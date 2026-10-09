#!/usr/bin/env python3
"""
Convenience script wrapper for Historical Data Source Integration CLI.
Run:
  python scripts/historical_sources.py list
  python scripts/historical_sources.py status
  python scripts/historical_sources.py acquire-required --dry-run
  python scripts/historical_sources.py verify
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.providers.historical.cli import main

if __name__ == "__main__":
    main()
