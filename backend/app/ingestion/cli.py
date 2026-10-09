"""
Developer CLI Interface for Historical Data Ingestion Pipeline
Utilities to run single or bulk ingestion operations against verified raw source files.
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure backend root is in sys.path when invoked directly
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.models import IngestionBatch
from app.db.session import SessionLocal
from app.ingestion.pipeline import HistoricalIngestionPipeline
from app.providers.historical.manifest import HistoricalManifestLoader
from app.providers.historical.service import HistoricalSourceAcquisitionService


def ingest_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        service = HistoricalSourceAcquisitionService()
        specs = HistoricalManifestLoader.load_manifest()

        target_specs = [
            s for s in specs
            if s.competition_code.upper() == args.competition.upper() and s.season_year == args.season
        ]

        if not target_specs:
            print(f"[ERROR] Manifest specification not found for competition '{args.competition}' and season '{args.season}'.")
            sys.exit(1)

        spec = target_specs[0]
        dest_path = service.get_destination_path(spec)

        if not dest_path.exists():
            print(f"[ERROR] Source file missing for {spec.competition_code} {spec.season_year} ({dest_path}). Run 'scripts/historical_sources.py acquire-required' first.")
            sys.exit(1)

        print(f"Ingesting raw source file: {dest_path.name} (dry-run: {args.dry_run})...")
        pipeline = HistoricalIngestionPipeline(db)
        report = pipeline.ingest_file(
            str(dest_path),
            competition_override=spec.competition_code,
            season_override=spec.season_year,
            dry_run=args.dry_run,
        )

        print(report.to_formatted_string())
    finally:
        db.close()


def ingest_required_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        service = HistoricalSourceAcquisitionService()
        specs = HistoricalManifestLoader.load_manifest()

        print("==================================================================================================")
        print(f"               BULK HISTORICAL DATA INGESTION (Dry-Run: {args.dry_run})")
        print("==================================================================================================")

        pipeline = HistoricalIngestionPipeline(db)
        total_inserted = 0
        total_existing = 0
        total_failed = 0

        for spec in specs:
            dest_path = service.get_destination_path(spec)
            if not dest_path.exists():
                print(f"[SKIPPED] {spec.competition_code:<12} {spec.season_year:<8} -> Raw source file missing. Run acquire-required first.")
                total_failed += 1
                continue

            report = pipeline.ingest_file(
                str(dest_path),
                competition_override=spec.competition_code,
                season_override=spec.season_year,
                dry_run=args.dry_run,
            )

            total_inserted += report.inserted_matches
            total_existing += report.existing_matches
            total_failed += report.failed_rows

            print(f"[{report.status.value:<10}] {spec.competition_code:<12} {spec.season_year:<8} -> Inserted: {report.inserted_matches}, Existing: {report.existing_matches}, Failed: {report.failed_rows}")

        print("-" * 98)
        print(f"Bulk Ingestion Summary: {total_inserted} Inserted | {total_existing} Existing | {total_failed} Failed")
        print("==================================================================================================")
    finally:
        db.close()


def summary_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        batches = db.query(IngestionBatch).order_by(IngestionBatch.started_at.desc()).limit(20).all()

        print("==================================================================================================")
        print("                             RECENT INGESTION BATCH SUMMARY")
        print("==================================================================================================")
        print(f"{'Batch ID':<38} | {'Status':<10} | {'Inserted':<10} | {'Failed':<8} | {'Source Reference':<25}")
        print("-" * 98)

        for b in batches:
            ref = os.path.basename(b.source_reference) if b.source_reference else "N/A"
            print(f"{str(b.id):<38} | {b.status:<10} | {b.success_count:<10} | {b.failure_count:<8} | {ref:<25}")

        print("==================================================================================================")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Intelligence System - Historical Ingestion CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ingest
    ing_parser = subparsers.add_parser("ingest", help="Ingest single historical dataset")
    ing_parser.add_argument("--competition", required=True, help="Competition code (e.g. EPL, LA_LIGA)")
    ing_parser.add_argument("--season", required=True, help="Season year (e.g. 2023-24)")
    ing_parser.add_argument("--dry-run", action="store_true", help="Simulate ingestion without DB persistence")

    # ingest-required
    req_parser = subparsers.add_parser("ingest-required", help="Bulk ingest all required Sprint 2.1 datasets")
    req_parser.add_argument("--dry-run", action="store_true", help="Simulate bulk ingestion")

    # summary
    subparsers.add_parser("summary", help="Display recent ingestion batch execution summary")

    args = parser.parse_args()

    if args.command == "ingest":
        ingest_command(args)
    elif args.command == "ingest-required":
        ingest_required_command(args)
    elif args.command == "summary":
        summary_command(args)


if __name__ == "__main__":
    main()
