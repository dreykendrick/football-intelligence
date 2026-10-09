#!/usr/bin/env python3
"""
Convenience script wrapper for Historical Ingestion CLI.
Run:
  python scripts/import_historical.py import-file --path <file_path>
  python scripts/import_historical.py import-dir --path data/raw/football_data_uk
  python scripts/import_historical.py coverage-report
"""
import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.ingestion.cli import main

if __name__ == "__main__":
    main()
