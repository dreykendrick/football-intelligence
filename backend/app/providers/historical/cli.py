"""
Developer CLI Interface for Historical Data Source Integration & Management
Utilities to discover, acquire, verify, and report historical source file coverage.
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure backend root is in sys.path when invoked directly
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.providers.historical.gate import SourceCoverageGate, SourceCoverageGateException
from app.providers.historical.manifest import HistoricalManifestLoader
from app.providers.historical.service import HistoricalSourceAcquisitionService


def list_command(args: argparse.Namespace) -> None:
    specs = HistoricalManifestLoader.load_manifest()
    print("==================================================================================================")
    print("                               HISTORICAL SOURCE MANIFEST")
    print("==================================================================================================")
    print(f"{'Competition':<15} | {'Season':<10} | {'Provider Code':<15} | {'Required':<8} | {'Source URL':<45}")
    print("-" * 100)

    for s in specs:
        print(f"{s.competition_code:<15} | {s.season_year:<10} | {s.provider_competition_code:<15} | {str(s.is_required):<8} | {s.source_url:<45}")

    print("==================================================================================================")


def status_command(args: argparse.Namespace) -> None:
    service = HistoricalSourceAcquisitionService()
    specs = HistoricalManifestLoader.load_manifest()

    print("==================================================================================================")
    print("                            HISTORICAL RAW SOURCE FILE STATUS")
    print("==================================================================================================")
    print(f"{'Competition':<15} | {'Season':<10} | {'Status':<12} | {'Size (KB)':<10} | {'SHA-256 Checksum':<40}")
    print("-" * 100)

    acquired_count = 0
    missing_count = 0

    for s in specs:
        dest_path = service.get_destination_path(s)
        if dest_path.exists():
            val_res = service.provider.validate_source_file(str(dest_path))
            if val_res.is_valid:
                status = "VALIDATED"
                sha = service.calculate_sha256(dest_path)[:12] + "..."
                size_kb = f"{val_res.file_size_bytes / 1024:.1f}"
                acquired_count += 1
            else:
                status = "INVALID"
                sha = "N/A"
                size_kb = "0"
        else:
            status = "MISSING"
            sha = "N/A"
            size_kb = "0"
            missing_count += 1

        print(f"{s.competition_code:<15} | {s.season_year:<10} | {status:<12} | {size_kb:<10} | {sha:<40}")

    print("-" * 100)
    print(f"Total Declared Datasets: {len(specs)} | Acquired & Validated: {acquired_count} | Missing: {missing_count}")
    print("==================================================================================================")


def acquire_command(args: argparse.Namespace) -> None:
    service = HistoricalSourceAcquisitionService()
    specs = HistoricalManifestLoader.load_manifest()

    target_specs = [
        s for s in specs
        if s.competition_code.upper() == args.competition.upper() and s.season_year == args.season
    ]

    if not target_specs:
        print(f"[ERROR] No manifest specification found for competition '{args.competition}' and season '{args.season}'.")
        sys.exit(1)

    db = SessionLocal()
    try:
        spec = target_specs[0]
        print(f"Acquiring {spec.competition_code} {spec.season_year} from {spec.source_url}...")
        res = service.acquire_source(spec, db_session=db, force_download=args.force)

        print(f"Result Status : {res.status.value}")
        print(f"Local Path    : {res.local_path}")
        print(f"SHA-256       : {res.sha256_checksum}")
        print(f"Message       : {res.message}")
    finally:
        db.close()


def acquire_required_command(args: argparse.Namespace) -> None:
    service = HistoricalSourceAcquisitionService()
    specs = HistoricalManifestLoader.load_manifest()

    db = SessionLocal()
    try:
        print(f"Acquiring {len(specs)} required historical datasets (dry-run: {args.dry_run}, refresh: {args.refresh})...")
        success_count = 0
        failed_count = 0

        for spec in specs:
            res = service.acquire_source(
                spec, db_session=db, force_download=args.refresh, dry_run=args.dry_run
            )
            print(f"[{res.status.value:<10}] {spec.competition_code:<12} {spec.season_year:<8} -> {res.message}")

            if res.status in (res.status.ACQUIRED, res.status.VALIDATED, res.status.UNCHANGED, res.status.AVAILABLE):
                success_count += 1
            else:
                failed_count += 1

        print(f"\nBulk Acquisition Complete: {success_count} succeeded, {failed_count} failed.")
    finally:
        db.close()


def verify_command(args: argparse.Namespace) -> None:
    print("Evaluating Source Coverage Gate for Historical Raw Files...")
    try:
        valid_sources = SourceCoverageGate.assert_required_historical_sources_available()
        print(f"\n[COVERAGE GATE PASSED] All {len(valid_sources)} required historical source files acquired and validated.")
    except SourceCoverageGateException as e:
        print(f"\n[COVERAGE GATE FAILED] {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Intelligence System - Historical Data Source Integration CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List declared target historical sources")

    # status
    subparsers.add_parser("status", help="Display local historical source file status")

    # acquire
    acq_parser = subparsers.add_parser("acquire", help="Acquire single historical source file")
    acq_parser.add_argument("--competition", required=True, help="Competition code (e.g. EPL, LA_LIGA)")
    acq_parser.add_argument("--season", required=True, help="Season year (e.g. 2023-24)")
    acq_parser.add_argument("--force", action="store_true", help="Force re-download")

    # acquire-required
    req_parser = subparsers.add_parser("acquire-required", help="Acquire all required historical datasets")
    req_parser.add_argument("--dry-run", action="store_true", help="Simulate download without acquiring files")
    req_parser.add_argument("--refresh", action="store_true", help="Force refresh of all datasets")

    # verify
    subparsers.add_parser("verify", help="Run Source Coverage Gate assertion")

    args = parser.parse_args()

    if args.command == "list":
        list_command(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "acquire":
        acquire_command(args)
    elif args.command == "acquire-required":
        acquire_required_command(args)
    elif args.command == "verify":
        verify_command(args)


if __name__ == "__main__":
    main()
