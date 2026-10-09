#!/usr/bin/env python3
"""
Convenience script wrapper for Historical Data Ingestion Pipeline CLI.
Run:
  python scripts/ingest_historical.py ingest --competition EPL --season 2023-24
  python scripts/ingest_historical.py ingest-required --dry-run
  python scripts/ingest_historical.py summary
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
