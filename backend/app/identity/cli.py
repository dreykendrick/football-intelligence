"""
Developer CLI Interface for Football Identity Resolution
Utilities to audit identities, resolve provider aliases, inspect team mappings, merge teams, and run readiness gates.
"""
from __future__ import annotations

import argparse
import os
import sys
from uuid import UUID

# Ensure backend root is in sys.path when invoked directly
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.models import ProviderTeamMapping, Team, TeamAliasMapping
from app.db.session import SessionLocal
from app.identity.gate import IdentityReadinessGate, IdentityReadinessGateException
from app.identity.merger import TeamIdentityMerger
from app.identity.resolver import FootballIdentityResolver


def audit_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        audit = IdentityReadinessGate.audit_database(db)

        print("==================================================================================================")
        print("                               FOOTBALL IDENTITY AUDIT REPORT")
        print("==================================================================================================")
        print(f"Canonical Teams Count        : {audit.canonical_teams_count}")
        print(f"Provider Team Mappings Count : {audit.provider_mappings_count}")
        print(f"Exact Duplicate Team Names   : {audit.exact_duplicate_names_count}")
        print(f"Mapping Conflict Count       : {audit.mapping_conflicts_count}")
        print(f"Potential Duplicate Pairs    : {audit.potential_duplicate_teams_count}")
        print(f"Identity Resolution Status   : {audit.status.value}")

        if audit.warnings:
            print("-" * 98)
            print("Audit Warnings & Candidates:")
            for w in audit.warnings[:15]:
                print(f"  - {w}")
            if len(audit.warnings) > 15:
                print(f"  ... and {len(audit.warnings) - 15} more warnings.")

        print("==================================================================================================")
    except Exception as e:
        print(f"[OFFLINE/DATABASE NOTICE] Could not query database: {e}")
        print("Run with active database or execute unit/integration test suite.")
    finally:
        db.close()


def resolve_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        resolver = FootballIdentityResolver(db)
        res = resolver.resolve_team_identity(
            args.provider, args.external_name, auto_create_if_unambiguous=False
        )

        print(f"Provider        : {res.provider_key}")
        print(f"External Name   : {res.external_identity}")
        print(f"Normalized Name : {res.normalized_identity}")
        print(f"Status          : {res.status.value}")

        if res.canonical_id:
            print(f"Canonical ID    : {res.canonical_id}")
            print(f"Canonical Name  : {res.canonical_name}")

        if res.candidates:
            print("\nSimilarity Candidates:")
            for c in res.candidates:
                print(f"  - [{c.similarity_score:.2f}] {c.canonical_name} ({c.canonical_id})")

        print(f"Message         : {res.message}")
    finally:
        db.close()


def create_team_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        existing = db.query(Team).filter_by(canonical_name=args.name).first()
        if existing:
            print(f"[EXISTS] Canonical team '{args.name}' already exists with ID: {existing.id}")
            sys.exit(0)

        team = Team(canonical_name=args.name, short_name=args.name, country=args.country or "Unknown")
        db.add(team)
        db.commit()
        print(f"[CREATED] Canonical team '{args.name}' created with ID: {team.id}")
    finally:
        db.close()


def add_alias_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        team_id = UUID(args.team_id)
        team = db.query(Team).filter_by(id=team_id).first()
        if not team:
            print(f"[ERROR] Team not found for ID: {args.team_id}")
            sys.exit(1)

        alias = TeamAliasMapping(team_id=team_id, provider_name=args.provider, raw_alias=args.alias)
        db.add(alias)
        db.commit()
        print(f"[ADDED] Alias '{args.alias}' added for team '{team.canonical_name}' (Provider: {args.provider}).")
    finally:
        db.close()


def mappings_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        team_id = UUID(args.team_id)
        team = db.query(Team).filter_by(id=team_id).first()
        if not team:
            print(f"[ERROR] Team not found for ID: {args.team_id}")
            sys.exit(1)

        p_mappings = db.query(ProviderTeamMapping).filter_by(team_id=team_id).all()
        a_mappings = db.query(TeamAliasMapping).filter_by(team_id=team_id).all()

        print("==================================================================================================")
        print(f"                         MAPPINGS FOR TEAM: {team.canonical_name} ({team.id})")
        print("==================================================================================================")
        print("Provider Team Mappings:")
        for pm in p_mappings:
            prov_key = pm.provider.provider_key if pm.provider else str(pm.provider_id)
            print(f"  - Provider: {prov_key:<20} | Raw Alias: {pm.raw_alias}")

        print("\nTeam Aliases:")
        for am in a_mappings:
            print(f"  - Provider: {am.provider_name:<20} | Alias: {am.raw_alias}")

        print("==================================================================================================")
    finally:
        db.close()


def merge_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        source_id = UUID(args.source_team_id)
        target_id = UUID(args.target_team_id)

        if args.dry_run:
            print(f"[DRY-RUN] Simulating merge of team {source_id} into team {target_id}...")
            sys.exit(0)

        merger = TeamIdentityMerger(db)
        res = merger.merge_teams(source_id, target_id, reason=args.reason or "Manual CLI merge")
        db.commit()

        print(f"[MERGE SUCCESSFUL] Merged team {source_id} into team {target_id}.")
        print(f"  - Home Matches Migrated       : {res['home_matches_migrated']}")
        print(f"  - Away Matches Migrated       : {res['away_matches_migrated']}")
        print(f"  - Statistics Migrated         : {res['statistics_migrated']}")
        print(f"  - Provider Mappings Migrated  : {res['provider_mappings_migrated']}")
    finally:
        db.close()


def verify_gate_command(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        print("Evaluating Identity Readiness Gate...")
        audit = IdentityReadinessGate.assert_identity_ready(db)
        print(f"\n[IDENTITY GATE PASSED] Audited {audit.canonical_teams_count} teams and {audit.provider_mappings_count} mappings with 0 blocking conflicts.")
    except IdentityReadinessGateException as e:
        print(f"\n[IDENTITY GATE FAILED] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[OFFLINE/DATABASE NOTICE] Could not query database: {e}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Intelligence System - Identity Resolution CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    subparsers.add_parser("audit", help="Run database identity audit")

    # resolve
    res_parser = subparsers.add_parser("resolve", help="Resolve external provider identity")
    res_parser.add_argument("--provider", required=True, help="Provider key (e.g. football_data_co_uk)")
    res_parser.add_argument("--external-name", required=True, help="External team name")

    # create-team
    crt_parser = subparsers.add_parser("create-team", help="Explicitly create canonical team")
    crt_parser.add_argument("--name", required=True, help="Canonical team name")
    crt_parser.add_argument("--country", help="Country name")

    # add-alias
    alias_parser = subparsers.add_parser("add-alias", help="Add explicit team alias")
    alias_parser.add_argument("--team-id", required=True, help="Canonical team UUID")
    alias_parser.add_argument("--alias", required=True, help="Raw team alias string")
    alias_parser.add_argument("--provider", default="manual", help="Provider name or manual tag")

    # mappings
    map_parser = subparsers.add_parser("mappings", help="Inspect mappings for team")
    map_parser.add_argument("--team-id", required=True, help="Canonical team UUID")

    # merge
    mrg_parser = subparsers.add_parser("merge", help="Safely merge source team B into target team A")
    mrg_parser.add_argument("--source-team-id", required=True, help="Source team UUID (to be merged)")
    mrg_parser.add_argument("--target-team-id", required=True, help="Target team UUID (surviving team)")
    mrg_parser.add_argument("--reason", help="Reason for merge operation")
    mrg_parser.add_argument("--dry-run", action="store_true", help="Simulate merge without committing DB changes")

    # verify-gate
    subparsers.add_parser("verify-gate", help="Run Identity Readiness Gate assertion")

    args = parser.parse_args()

    if args.command == "audit":
        audit_command(args)
    elif args.command == "resolve":
        resolve_command(args)
    elif args.command == "create-team":
        create_team_command(args)
    elif args.command == "add-alias":
        add_alias_command(args)
    elif args.command == "mappings":
        mappings_command(args)
    elif args.command == "merge":
        merge_command(args)
    elif args.command == "verify-gate":
        verify_gate_command(args)


if __name__ == "__main__":
    main()
