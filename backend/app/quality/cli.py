"""
Developer CLI Interface for Data Quality Validation & Readiness Reporting
Executes quality validation rules, displays human-readable / JSON reports, and enforces quality gates.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Add backend root directory to sys.path if invoked standalone
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.quality.engine import DataQualityEngine
from app.quality.gate import QualityGate, QualityGateException
from app.quality.readiness import FeatureReadinessAssessor


def validate_historical_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        print("==========================================================")
        print("   DATA QUALITY VALIDATION ENGINE")
        print("==========================================================")
        engine = DataQualityEngine(db)
        findings = engine.run_all_checks()

        blocking_count = sum(1 for f in findings if f.severity.value == "BLOCKING")
        warning_count = sum(1 for f in findings if f.severity.value == "WARNING")
        error_count = sum(1 for f in findings if f.severity.value == "ERROR")

        print(f"Total Quality Findings Detected: {len(findings)}")
        print(f"  - BLOCKING Issues: {blocking_count}")
        print(f"  - ERROR Issues   : {error_count}")
        print(f"  - WARNING Issues : {warning_count}")
        print("==========================================================")

        if args.fail_on_blocking and blocking_count > 0:
            print("\n[ERROR] Fail-on-blocking flag enabled and BLOCKING issues detected!")
            sys.exit(1)
    finally:
        db.close()


def report_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        engine = DataQualityEngine(db)
        findings = engine.run_all_checks()

        assessor = FeatureReadinessAssessor(db)
        report = assessor.generate_global_report(findings)

        if args.format == "json":
            print(json.dumps(report.model_dump(mode="json"), indent=2))
            return

        print("============================================================================================")
        print("                        HISTORICAL DATA QUALITY & READINESS REPORT")
        print("============================================================================================")
        print(f"Global Data Readiness Status : {report.global_status.value}")
        print(f"Overall Quality Score        : {report.overall_quality_score:.4f} (Completeness: {report.completeness_score:.2f}, Chrono: {report.chronology_score:.2f}, Mapping: {report.mapping_score:.2f}, Integrity: {report.integrity_score:.2f})")
        print(f"Total Competitions / Seasons : {report.total_competitions} leagues | {report.total_seasons} seasons")
        print(f"Total Matches / Teams        : {report.total_matches} matches | {report.total_teams} teams")
        print(f"Total Quality Findings       : {report.total_findings} ({report.blocking_count} BLOCKING, {report.warning_count} WARNING, {report.info_count} INFO)")
        print("-" * 92)
        print("LEAGUE-SEASON READINESS BREAKDOWN:")
        print(f"{'League':<10} | {'Season':<10} | {'Matches':<8} | {'Teams':<6} | {'Status':<22} | {'Findings (B/W)':<14}")
        print("-" * 92)

        for sr in report.season_reports:
            print(f"{sr.competition_code:<10} | {sr.season_year:<10} | {sr.total_matches:<8} | {sr.unique_teams:<6} | {sr.readiness_status.value:<22} | B:{sr.blocking_findings_count} / W:{sr.warning_findings_count}")

        print("-" * 92)
        print("FEATURE MODULE READINESS:")
        for fr in report.feature_readiness:
            lim_str = f" ({', '.join(fr.limitations)})" if fr.limitations else ""
            print(f"  - {fr.feature_module_name:<38}: {fr.status.value:<20} [Coverage: {fr.coverage_percentage:.1f}%]{lim_str}")

        print("============================================================================================")
    finally:
        db.close()


def check_gate_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        print("Evaluating Quality Gate for Historical Data...")
        try:
            report = QualityGate.assert_historical_data_ready(db)
            print(f"\n[QUALITY GATE PASSED] Status: {report.global_status.value}")
            print(f"Overall Quality Score: {report.overall_quality_score:.4f}")
        except QualityGateException as e:
            print(f"\n[QUALITY GATE FAILED] {e}")
            sys.exit(1)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Intelligence System - Data Quality & Readiness CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-historical
    val_parser = subparsers.add_parser("validate-historical", help="Run data quality validation rules across database")
    val_parser.add_argument("--competition", required=False, help="Filter validation by competition code")
    val_parser.add_argument("--season", required=False, help="Filter validation by season year")
    val_parser.add_argument("--fail-on-blocking", action="store_true", help="Exit with code 1 if blocking issues exist")

    # report
    rep_parser = subparsers.add_parser("report", help="Display human-readable or JSON data quality report")
    rep_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format (text or json)")

    # check-gate
    subparsers.add_parser("check-gate", help="Enforce quality gate check for downstream pipelines")

    args = parser.parse_args()

    if args.command == "validate-historical":
        validate_historical_command(args)
    elif args.command == "report":
        report_command(args)
    elif args.command == "check-gate":
        check_gate_command(args)


if __name__ == "__main__":
    main()
