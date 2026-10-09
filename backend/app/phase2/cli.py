"""
Phase 2 Readiness & Verification CLI
Usage: python -m app.phase2.cli verify [--force-download] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal
from app.phase2.orchestrator import Phase2Orchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2 Football Data Infrastructure Readiness & Certification CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Phase 2 Commands")

    verify_parser = subparsers.add_parser("verify", help="Run full Phase 2 end-to-end empirical verification")
    verify_parser.add_argument(
        "--force-download", action="store_true", help="Force fresh download of all historical source files"
    )
    verify_parser.add_argument(
        "--release-key", default="mvp_a_historical_v1", help="Dataset release key (default: mvp_a_historical_v1)"
    )
    verify_parser.add_argument("--json", action="store_true", help="Output raw machine-readable JSON")

    args = parser.parse_args()

    if not args.command or args.command == "verify":
        db = SessionLocal()
        try:
            orchestrator = Phase2Orchestrator(db)
            force_download = getattr(args, "force_download", False)
            release_key = getattr(args, "release_key", "mvp_a_historical_v1")

            report = orchestrator.run_full_verification(
                release_key=release_key, force_download=force_download
            )
            json_file = orchestrator.save_report_json(report)

            if getattr(args, "json", False):
                print(json.dumps(report, indent=2))
            else:
                print("==========================================================")
                print("   PHASE 2 — FOOTBALL DATA INFRASTRUCTURE INTEGRATION")
                print("==========================================================")
                print(f"Provider           : {report['provider']}")
                print(f"Target Competitions: {', '.join(report['target_competitions'])}")
                print(f"Dataset Release    : {report['dataset_key']} ({report['dataset_status']})")
                print(f"SHA-256 Fingerprint: {report['dataset_fingerprint']}")
                print(f"Canonical Matches  : {report['db_counts']['canonical_matches']}")
                print(f"Dataset Matches    : {report['dataset_matches_count']}")
                print(f"Canonical Teams    : {report['db_counts']['canonical_teams']}")
                print(f"Ingestion Batches  : {report['db_counts']['ingestion_batches']}")
                print("----------------------------------------------------------")
                print("Validation Matrix Summary:")
                passed_count = sum(1 for v in report['validation_matrix'].values() if v == 'PASS')
                total_count = len(report['validation_matrix'])
                print(f"  Passed Checks    : {passed_count} / {total_count}")

                if report['blockers']:
                    print("----------------------------------------------------------")
                    print("Critical Blockers:")
                    for b in report['blockers']:
                        print(f"  [BLOCKER] {b}")

                if report['warnings']:
                    print("----------------------------------------------------------")
                    print("Non-Blocking Warnings:")
                    for w in report['warnings'][:5]:
                        print(f"  [WARNING] {w}")

                print("==========================================================")
                print(f"PHASE 2 STATUS     : {report['status']}")
                print(f"PHASE 3 READINESS  : {report['phase3_readiness']}")
                print("==========================================================")
                print(f"Detailed machine-readable JSON saved to: {json_file}")

            if report["status"] in ("READY", "READY_WITH_NON_BLOCKING_ISSUES"):
                sys.exit(0)
            else:
                sys.exit(1)
        finally:
            db.close()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
