"""
Developer CLI Interface for Historical Dataset Release Operations
Subcommands: list, build, validate, approve, verify, report, export-manifest.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.dataset.approval import HistoricalDatasetApprover
from app.dataset.builder import HistoricalDatasetBuilder
from app.dataset.query import HistoricalDatasetQueryService
from app.dataset.validator import HistoricalDatasetValidator
from app.db.models import HistoricalDatasetRelease
from app.db.session import SessionLocal


def list_datasets_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        releases = db.query(HistoricalDatasetRelease).order_by(HistoricalDatasetRelease.created_at.desc()).all()
        if not releases:
            print("No historical dataset releases found in database.")
            return

        print("\n=== HISTORICAL DATASET RELEASES ===")
        print(f"{'KEY':<20} {'VERSION':<10} {'STATUS':<12} {'COMPS':<6} {'SEASONS':<8} {'MATCHES':<8} {'FINGERPRINT'}")
        print("-" * 110)
        for r in releases:
            fp = (r.dataset_fingerprint[:16] + "...") if r.dataset_fingerprint else "N/A"
            print(f"{r.key:<20} {r.version:<10} {r.status:<12} {r.total_competitions:<6} {r.total_seasons:<8} {r.total_matches:<8} {fp}")
        print()
    finally:
        db.close()


def build_dataset_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        builder = HistoricalDatasetBuilder(db)
        overrides = {}
        if args.season:
            for s_item in args.season:
                if ":" in s_item:
                    c, y = s_item.split(":", 1)
                    overrides.setdefault(c, []).append(y)

        print(f"Building historical dataset candidate '{args.dataset}:{args.version}' (dry_run={args.dry_run})...")
        report = builder.build_dataset_release(
            dataset_key=args.dataset,
            version=args.version,
            description=args.description,
            explicit_overrides=overrides if overrides else None,
            dry_run=args.dry_run,
        )

        if args.format == "json":
            print(json.dumps(report.model_dump(), indent=2))
        else:
            print("\n=== HISTORICAL DATASET BUILD REPORT ===")
            print(f"Dataset Key:      {report.dataset_key}")
            print(f"Version:          {report.version}")
            print(f"Status:           {report.status}")
            print(f"Competitions:     {report.total_competitions}")
            print(f"Seasons:          {report.total_seasons}")
            print(f"Total Matches:    {report.total_matches}")
            print(f"Excluded Matches: {report.total_excluded_matches}")
            print(f"Quality Status:   {report.quality_status}")
            print(f"Identity Status:  {report.identity_readiness_status}")
            print(f"Fingerprint:      {report.fingerprint}")
            print("\nCoverage Matrix:")
            print(f"  {'COMP':<6} {'SEASON':<10} {'MATCHES':<8} {'EXPECTED':<10} {'QUALITY':<20} {'CHECKSUM'}")
            print("  " + "-" * 85)
            for row in report.coverage_matrix:
                exp = str(row.expected_matches) if row.expected_matches else "N/A"
                c_hash = (row.source_checksum[:12] + "...") if row.source_checksum else "N/A"
                print(f"  {row.competition_code:<6} {row.season_year:<10} {row.matches:<8} {exp:<10} {row.quality_status:<20} {c_hash}")
            print()
    finally:
        db.close()


def validate_dataset_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        validator = HistoricalDatasetValidator(db)
        accepted = args.accept_warning or []
        report = validator.validate_release(
            dataset_key=args.dataset, version=args.version, accepted_warnings=accepted
        )

        if args.format == "json":
            print(json.dumps(report.model_dump(), indent=2))
        else:
            print(f"\n=== DATASET VALIDATION REPORT: {args.dataset}:{args.version} ===")
            print(f"Valid for Approval: {'YES' if report.is_valid else 'NO'}")
            print(f"Status:             {report.status}")
            print(f"Seasons Count:      {report.total_seasons_count}")
            print(f"Matches Count:      {report.total_matches_count}")
            print("\nChecks Passed:")
            for check in report.checks_passed:
                print(f"  [PASS] {check}")
            if report.warnings:
                print("\nWarnings:")
                for w in report.warnings:
                    print(f"  [WARN] {w}")
            if report.blockers:
                print("\nBlockers:")
                for b in report.blockers:
                    print(f"  [BLOCK] {b}")
            print()
    finally:
        db.close()


def approve_dataset_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        approver = HistoricalDatasetApprover(db)
        accepted = args.accept_warning or []
        release_dto = approver.approve_release(
            dataset_key=args.dataset, version=args.version, accepted_warnings=accepted
        )

        print(f"\nSUCCESS: Dataset release {release_dto.key}:{release_dto.version} APPROVED!")
        print(f"Status:      {release_dto.status}")
        print(f"Approved At: {release_dto.approved_at}")
        print(f"Fingerprint: {release_dto.dataset_fingerprint}")
        print(f"Total Matches: {release_dto.total_matches}")
        print()
    finally:
        db.close()


def verify_dataset_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        service = HistoricalDatasetQueryService(db)
        is_ok = service.verify_dataset_lock(dataset_key=args.dataset, version=args.version)
        if is_ok:
            print(f"\nLOCK VERIFIED: Historical dataset release {args.dataset}:{args.version} fingerprint matches database state perfectly!")
        else:
            print(f"\nLOCK FAILED for dataset release {args.dataset}:{args.version}!")
            sys.exit(1)
    finally:
        db.close()


def report_dataset_cmd(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        rel = (
            db.query(HistoricalDatasetRelease)
            .filter_by(key=args.dataset, version=args.version)
            .first()
        )
        if not rel:
            print(f"Dataset release {args.dataset}:{args.version} not found.")
            return

        report_data = {
            "key": rel.key,
            "version": rel.version,
            "status": rel.status,
            "total_competitions": rel.total_competitions,
            "total_seasons": rel.total_seasons,
            "total_matches": rel.total_matches,
            "dataset_fingerprint": rel.dataset_fingerprint,
            "quality_status": rel.quality_status,
            "identity_readiness_status": rel.identity_readiness_status,
            "approved_at": rel.approved_at.isoformat() if rel.approved_at else None,
            "seasons": [
                {
                    "competition_code": s.competition_code,
                    "season_year": s.season_year,
                    "matches": s.match_count,
                    "readiness_status": s.readiness_status,
                    "source_checksum": s.source_checksum,
                }
                for s in rel.seasons
            ],
            "metadata_payload": rel.metadata_payload,
        }

        if args.format == "json":
            print(json.dumps(report_data, indent=2))
        else:
            print(f"\n=== HISTORICAL DATASET RELEASE REPORT: {rel.key}:{rel.version} ===")
            print(f"Status:                 {rel.status}")
            print(f"Selection Policy:       {rel.selection_policy_key} ({rel.selection_policy_version})")
            print(f"Competitions Count:     {rel.total_competitions}")
            print(f"Seasons Count:          {rel.total_seasons}")
            print(f"Matches Count:          {rel.total_matches}")
            print(f"Fingerprint:            {rel.dataset_fingerprint}")
            print(f"Approved At:            {rel.approved_at}")
            print("\nIncluded Seasons:")
            for s in rel.seasons:
                c_hash = (s.source_checksum[:12] + "...") if s.source_checksum else "N/A"
                print(f"  - {s.competition_code:<6} {s.season_year:<10} Matches: {s.match_count:<6} Status: {s.readiness_status:<20} Hash: {c_hash}")
            print()
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical Dataset Release Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List historical dataset releases")
    p_list.set_defaults(func=list_datasets_cmd)

    # build
    p_build = subparsers.add_parser("build", help="Build a historical dataset release candidate")
    p_build.add_argument("--dataset", default="mvp_a_historical", help="Dataset release key")
    p_build.add_argument("--version", default="v1", help="Dataset release version")
    p_build.add_argument("--description", default="Official MVP-A Historical Dataset Release", help="Dataset description")
    p_build.add_argument("--season", action="append", help="Explicit season override, e.g., --season E0:2023-24")
    p_build.add_argument("--dry-run", action="store_true", help="Perform dry-run without persisting")
    p_build.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_build.set_defaults(func=build_dataset_cmd)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate a dataset release candidate")
    p_val.add_argument("--dataset", default="mvp_a_historical", help="Dataset release key")
    p_val.add_argument("--version", default="v1", help="Dataset release version")
    p_val.add_argument("--accept-warning", action="append", help="Documented warning limitation acceptance string")
    p_val.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_val.set_defaults(func=validate_dataset_cmd)

    # approve
    p_app = subparsers.add_parser("approve", help="Approve a validated dataset release")
    p_app.add_argument("--dataset", default="mvp_a_historical", help="Dataset release key")
    p_app.add_argument("--version", default="v1", help="Dataset release version")
    p_app.add_argument("--accept-warning", action="append", help="Documented warning limitation acceptance string")
    p_app.set_defaults(func=approve_dataset_cmd)

    # verify
    p_ver = subparsers.add_parser("verify", help="Verify dataset fingerprint & lock integrity")
    p_ver.add_argument("--dataset", default="mvp_a_historical", help="Dataset release key")
    p_ver.add_argument("--version", default="v1", help="Dataset release version")
    p_ver.set_defaults(func=verify_dataset_cmd)

    # report
    p_rep = subparsers.add_parser("report", help="Report detailed dataset release manifest")
    p_rep.add_argument("--dataset", default="mvp_a_historical", help="Dataset release key")
    p_rep.add_argument("--version", default="v1", help="Dataset release version")
    p_rep.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_rep.set_defaults(func=report_dataset_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
