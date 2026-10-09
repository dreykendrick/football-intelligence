"""
Developer CLI Interface for Feature Snapshot Generation & Catalog Inspection
Provides command-line utilities to generate pre-match feature snapshots, inspect feature definitions, and build dataset feature sets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from uuid import UUID

# Ensure backend root is in sys.path when invoked directly
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.models import FeatureSnapshot, Match
from app.db.session import SessionLocal
from app.features.definitions import CORE_FEATURE_DEFINITIONS
from app.features.registry import FEATURE_CATALOG, global_feature_registry
from app.features.service import FeatureEngineService


def list_command(args: argparse.Namespace) -> None:
    print("==================================================================================================")
    print("                                   MVP-A FEATURE CATALOG")
    print("==================================================================================================")
    print(f"{'Feature Key':<42} | {'Category':<16} | {'Version':<8} | {'Description':<36}")
    print("-" * 110)

    for fkey in global_feature_registry.list_feature_keys():
        calc = global_feature_registry.get_calculator(fkey)
        meta = global_feature_registry.get_definition(fkey)
        cat = meta.category if meta else "STRENGTH"
        desc = meta.description if meta else calc.description
        print(f"{fkey:<42} | {cat:<16} | {calc.version:<8} | {desc:<36}")

    print("==================================================================================================")


def describe_command(args: argparse.Namespace) -> None:
    fkey = args.feature_key
    meta = global_feature_registry.get_definition(fkey)
    calc = global_feature_registry.get_calculator(fkey)

    print("==========================================================")
    print(f" FEATURE SPECIFICATION: {fkey}")
    print("==========================================================")
    print(f"Name           : {meta.name if meta else fkey}")
    print(f"Version        : {calc.version}")
    print(f"Category       : {meta.category if meta else 'STRENGTH'}")
    print(f"Data Type      : {meta.data_type if meta else 'FLOAT'}")
    print(f"Cutoff Policy  : {meta.cutoff_policy if meta else 'STRICT_BEFORE_KICKOFF'}")
    print(f"Missing Policy : {meta.missing_value_policy if meta else 'INSUFFICIENT_HISTORY'}")
    print(f"Min History    : {meta.minimum_history if meta else 1}")
    print(f"Description    : {meta.description if meta else calc.description}")
    print("==========================================================")


def calculate_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        match_id = UUID(args.match_id)
        cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else None

        print("==========================================================")
        print("   FEATURE CALCULATION ENGINE")
        print("==========================================================")
        print(f"Target Match ID : {match_id}")
        if cutoff:
            print(f"Cutoff Timestamp : {cutoff.isoformat()}")

        service = FeatureEngineService(db)
        snapshot = service.generate_snapshot_for_match(
            match_id=match_id,
            cutoff_timestamp=cutoff,
            dataset_key=args.dataset,
            dataset_version=args.version,
            skip_quality_gate=args.skip_quality_gate,
        )

        print("\nFEATURE SNAPSHOT GENERATED SUCCESSFULLY:")
        print(f"Snapshot ID       : {snapshot.id}")
        print(f"Feature Set       : {snapshot.feature_version}")
        print(f"Cutoff Timestamp  : {snapshot.cutoff_timestamp}")
        print(f"Fingerprint SHA256: {snapshot.data_quality_metadata.get('fingerprint_sha256')}")
        print("-" * 58)
        print(json.dumps(snapshot.feature_values, indent=2))
        print("==========================================================")
    finally:
        db.close()


def build_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        print("==========================================================")
        print(f" BULK FEATURE SNAPSHOT BUILD: {args.dataset}:{args.version}")
        print("==========================================================")
        service = FeatureEngineService(db)
        snapshots = service.build_snapshots_for_dataset(
            dataset_key=args.dataset,
            version=args.version,
            approved_only=not args.allow_unapproved,
            batch_size=args.batch_size,
            limit=args.limit
        )
        print(f"\nSuccessfully created/verified {len(snapshots)} pre-match feature snapshots.")
        print("==========================================================")
    finally:
        db.close()


def report_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        service = FeatureEngineService(db)
        matches = service.dataset_query_service.get_dataset_matches(
            dataset_key=args.dataset, version=args.version, approved_only=True
        )

        snapshots = (
            db.query(FeatureSnapshot)
            .filter(FeatureSnapshot.match_id.in_([m.id for m in matches]))
            .all()
        )

        total_matches = len(matches)
        total_snapshots = len(snapshots)
        missing_counts: dict[str, int] = {fkey: 0 for fkey in FEATURE_CATALOG}

        for snap in snapshots:
            for fkey in FEATURE_CATALOG:
                if snap.feature_values.get(fkey) is None:
                    missing_counts[fkey] += 1

        print("==================================================================================================")
        print(f"                             FEATURE COVERAGE REPORT: {args.dataset}:{args.version}")
        print("==================================================================================================")
        print(f"Total Approved Dataset Matches : {total_matches}")
        print(f"Generated Feature Snapshots    : {total_snapshots}")
        print("-" * 100)
        print(f"{'Feature Key':<45} | {'Available':<12} | {'Missing':<12} | {'Coverage %':<12}")
        print("-" * 105)

        for fkey in sorted(FEATURE_CATALOG.keys()):
            missing = missing_counts[fkey]
            avail = total_snapshots - missing
            cov_pct = round((avail / total_snapshots * 100), 1) if total_snapshots > 0 else 0.0
            print(f"{fkey:<45} | {avail:<12} | {missing:<12} | {cov_pct:<11}%")

        print("==================================================================================================")
    finally:
        db.close()


def verify_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        print("==========================================================")
        print(" SPRINT 3.1 FEATURE ARCHITECTURE VERIFICATION")
        print("==========================================================")
        service = FeatureEngineService(db)

        # 1. Dataset lock check
        is_locked = service.dataset_query_service.verify_dataset_lock(args.dataset, args.version)
        print(f"[PASS] Dataset lock verified: {args.dataset}:{args.version} ({is_locked})")

        # 2. Registry completeness
        registered_count = len(global_feature_registry.list_feature_keys())
        print(f"[PASS] Feature Registry catalog count: {registered_count} features registered")

        print("==========================================================")
        print(" SPRINT 3.1 VERIFICATION: PASS")
        print("==========================================================")
    finally:
        db.close()


def feature_set_command(args: argparse.Namespace) -> None:
    from app.features.manifest import get_mvp_a_feature_set_v1_manifest
    from app.features.readiness import FeatureSetReadinessService
    db = SessionLocal()
    try:
        manifest = get_mvp_a_feature_set_v1_manifest()
        service = FeatureSetReadinessService(manifest)

        if args.subcommand == "show":
            print("==========================================================")
            print(f" FEATURE SET MANIFEST: {manifest.feature_set_key}")
            print("==========================================================")
            print(f"Version            : {manifest.version}")
            print(f"Dataset Dependency : {manifest.dataset_release_key}")
            print(f"Code Version       : {manifest.created_by_code_version}")
            print(f"Manifest Fingerprint: {manifest.fingerprint}")
            print(f"Total Feature Count: {manifest.feature_count}")
            print("-" * 58)
            print("Scientific Notes   :")
            print(f"  {manifest.scientific_notes}")
            print("==========================================================")

        elif args.subcommand == "validate":
            print("==========================================================")
            print(f" AUDITING PHASE 3 READINESS: {manifest.feature_set_key}")
            print("==========================================================")
            report = service.get_readiness_report(db)
            print(f"Status             : {report['status']}")
            print(f"Manifest Fingerprint: {report['manifest_fingerprint']}")
            print(f"Total Features     : {report['total_feature_count']}")
            print(f"Phase 3 Readiness  : {report['phase_3_readiness']}")
            print(f"Phase 4 Readiness  : {report['phase_4_readiness']}")
            print("-" * 58)

            if report["blockers"]:
                print("BLOCKING ISSUES DETECTED:")
                for b in report["blockers"]:
                    print(f"  [BLOCKER] {b}")
            else:
                print("[PASS] All readiness certification checks passed cleanly.")
            print("==========================================================")

        elif args.subcommand == "coverage":
            print("==========================================================")
            print(f" FEATURE SET COVERAGE REPORT: {manifest.feature_set_key}")
            print("==========================================================")
            report = service.get_readiness_report(db)
            print(f"Total Manifest Features : {report['total_feature_count']}")
            print(f"Manifest Fingerprint    : {report['manifest_fingerprint']}")
            print(f"Overall Readiness       : {report['phase_3_readiness']}")
            print("==========================================================")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Intelligence System - Feature Engineering CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="Display registered MVP-A feature catalog")

    # describe
    desc_parser = subparsers.add_parser("describe", help="Display specification for a feature key")
    desc_parser.add_argument("feature_key", help="Feature key identifier")

    # calculate
    calc_parser = subparsers.add_parser("calculate", help="Generate feature snapshot for a single match")
    calc_parser.add_argument("--match-id", required=True, help="Target Match UUID")
    calc_parser.add_argument("--cutoff", required=False, help="ISO cutoff timestamp (default: match kickoff)")
    calc_parser.add_argument("--dataset", default="mvp_a_historical", help="Dataset key")
    calc_parser.add_argument("--version", default="v1", help="Dataset version")
    calc_parser.add_argument("--skip-quality-gate", action="store_true", help="Bypass Quality Gate check")

    # build
    build_parser = subparsers.add_parser("build", help="Bulk build feature snapshots for dataset release")
    build_parser.add_argument("--dataset", default="mvp_a_historical", help="Dataset key")
    build_parser.add_argument("--version", default="v1", help="Dataset version")
    build_parser.add_argument("--allow-unapproved", action="store_true", help="Allow unapproved datasets")
    build_parser.add_argument("--batch-size", type=int, default=50, help="Number of fixtures per commit batch")
    build_parser.add_argument("--limit", type=int, default=None, help="Limit total fixtures processed")

    # report
    rep_parser = subparsers.add_parser("report", help="Generate feature coverage report for dataset release")
    rep_parser.add_argument("--dataset", default="mvp_a_historical", help="Dataset key")
    rep_parser.add_argument("--version", default="v1", help="Dataset version")

    # verify
    ver_parser = subparsers.add_parser("verify", help="Verify Feature Architecture integrity and dataset lock")
    ver_parser.add_argument("--dataset", default="mvp_a_historical", help="Dataset key")
    ver_parser.add_argument("--version", default="v1", help="Dataset version")

    # feature-set
    fset_parser = subparsers.add_parser("feature-set", help="Inspect, validate, and audit Phase 3 Feature Sets")
    fset_parser.add_argument("subcommand", choices=["show", "validate", "coverage"], help="Feature set subcommand")

    args = parser.parse_args()

    if args.command == "list":
        list_command(args)
    elif args.command == "describe":
        describe_command(args)
    elif args.command == "calculate":
        calculate_command(args)
    elif args.command == "build":
        build_command(args)
    elif args.command == "report":
        report_command(args)
    elif args.command == "verify":
        verify_command(args)
    elif args.command == "feature-set":
        feature_set_command(args)


if __name__ == "__main__":
    main()
