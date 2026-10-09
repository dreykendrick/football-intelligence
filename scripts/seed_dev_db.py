#!/usr/bin/env python3
"""
Development Database Seed Tool (DEVELOPMENT/TEST USE ONLY)
Populates local database with fixture records (1 provider, 1 competition, 1 season, 2 teams, 1 match, 1 feature set, 1 model version).
All records are explicitly tagged as test seed fixtures.
"""
import os
import sys
from datetime import UTC, datetime, timedelta

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.models import (
    Competition,
    FeatureSet,
    Match,
    Model,
    ModelVersion,
    Provider,
    Season,
    Team,
    TeamAliasMapping,
)
from app.db.session import SessionLocal


def seed_development_fixtures() -> None:
    print("==========================================================")
    print("   DEVELOPMENT DATABASE SEED WORKFLOW")
    print("==========================================================")

    db = SessionLocal()
    try:
        # 1. Provider
        provider = db.query(Provider).filter_by(provider_key="football_data_co_uk").first()
        if not provider:
            provider = Provider(
                provider_key="football_data_co_uk",
                display_name="Football-Data.co.uk Historical CSV Source",
                provider_type="HISTORICAL_CSV",
                base_url="https://www.football-data.co.uk",
                is_active=True,
            )
            db.add(provider)
            db.flush()
            print("  - Seeded Provider: Football-Data.co.uk")

        # 2. Competition
        competition = db.query(Competition).filter_by(code="EPL").first()
        if not competition:
            competition = Competition(
                code="EPL",
                name="English Premier League",
                country="England",
                competition_type="DOMESTIC_LEAGUE",
                is_active=True,
            )
            db.add(competition)
            db.flush()
            print("  - Seeded Competition: EPL")

        # 3. Season
        season = db.query(Season).filter_by(competition_id=competition.id, season_year="2023/24").first()
        if not season:
            season = Season(
                competition_id=competition.id,
                season_year="2023/24",
                start_year=2023,
                end_year=2024,
                is_current=False,
            )
            db.add(season)
            db.flush()
            print("  - Seeded Season: 2023/24")

        # 4. Teams
        team_home = db.query(Team).filter_by(canonical_name="Arsenal").first()
        if not team_home:
            team_home = Team(canonical_name="Arsenal", short_name="Arsenal", short_code="ARS", country="England")
            db.add(team_home)
            db.flush()

        team_away = db.query(Team).filter_by(canonical_name="Chelsea").first()
        if not team_away:
            team_away = Team(canonical_name="Chelsea", short_name="Chelsea", short_code="CHE", country="England")
            db.add(team_away)
            db.flush()
        print("  - Seeded Teams: Arsenal & Chelsea")

        # 5. Team Aliases
        alias1 = db.query(TeamAliasMapping).filter_by(provider_name="football_data_co_uk", raw_alias="Arsenal").first()
        if not alias1:
            db.add(TeamAliasMapping(team_id=team_home.id, provider_name="football_data_co_uk", raw_alias="Arsenal"))

        alias2 = db.query(TeamAliasMapping).filter_by(provider_name="football_data_co_uk", raw_alias="Chelsea").first()
        if not alias2:
            db.add(TeamAliasMapping(team_id=team_away.id, provider_name="football_data_co_uk", raw_alias="Chelsea"))

        # 6. Match
        match = db.query(Match).filter_by(season_id=season.id, home_team_id=team_home.id, away_team_id=team_away.id).first()
        if not match:
            match = Match(
                season_id=season.id,
                home_team_id=team_home.id,
                away_team_id=team_away.id,
                kickoff_utc=datetime.now(UTC) - timedelta(days=10),
                status="FINISHED",
                home_score=2,
                away_score=1,
            )
            db.add(match)
            db.flush()
            print("  - Seeded Match: Arsenal 2 - 1 Chelsea")

        # 7. FeatureSet
        fset = db.query(FeatureSet).filter_by(name="v1_poisson_baseline", version="1.0.0").first()
        if not fset:
            fset = FeatureSet(
                name="v1_poisson_baseline",
                version="1.0.0",
                description="Baseline Poisson feature set containing rolling attack/defense ratings and Elo.",
                is_active=True,
            )
            db.add(fset)
            db.flush()
            print("  - Seeded FeatureSet: v1_poisson_baseline v1.0.0")

        # 8. Model & Version
        model = db.query(Model).filter_by(model_key="basic_poisson").first()
        if not model:
            model = Model(
                model_key="basic_poisson",
                name="Basic Bivariate Poisson Goal Model",
                model_family="POISSON",
                description="Bivariate Poisson model with independent home/away expected goal parameters.",
            )
            db.add(model)
            db.flush()

        mver = db.query(ModelVersion).filter_by(model_id=model.id, version="1.0.0").first()
        if not mver:
            mver = ModelVersion(
                model_id=model.id,
                version="1.0.0",
                lifecycle_status="VALIDATED",
                feature_set_id=fset.id,
                notes="Initial validated baseline Poisson model for Sprint 1.2 test seed.",
            )
            db.add(mver)
            db.flush()
            print("  - Seeded Model & ModelVersion: basic_poisson v1.0.0 (VALIDATED)")

        db.commit()
        print("\nSeed workflow completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_development_fixtures()
