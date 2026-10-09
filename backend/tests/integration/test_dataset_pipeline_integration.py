"""
Full Phase 2 Integration Test:
Ingestion (2.2) -> Identity (2.3) -> Quality (2.4) -> Dataset Assembly (2.5)
"""
from datetime import UTC, datetime

import pytest

from app.dataset.approval import HistoricalDatasetApprover
from app.dataset.base import DatasetReleaseStatusEnum
from app.dataset.builder import HistoricalDatasetBuilder
from app.dataset.query import HistoricalDatasetQueryService
from app.dataset.validator import HistoricalDatasetValidator
from app.db.models import Competition, Provider, Season
from app.ingestion.pipeline import HistoricalIngestionPipeline


@pytest.mark.integration
def test_full_phase_2_pipeline_to_approved_dataset(db_session, tmp_path):
    # 1. Setup Provider, Competitions, Seasons for 4 leagues x 3 seasons
    provider_entity = Provider(
        provider_key="football_data_co_uk",
        display_name="Football-Data.co.uk",
        provider_type="HISTORICAL_CSV",
    )
    db_session.add(provider_entity)
    db_session.flush()

    comp_codes = ["E0", "SP1", "I1", "D1"]
    season_years = ["2021-22", "2022-23", "2023-24"]

    for code in comp_codes:
        comp = Competition(code=code, name=f"League {code}", country="Country")
        db_session.add(comp)
        db_session.flush()
        for year in season_years:
            s = Season(competition_id=comp.id, season_year=year)
            db_session.add(s)
    db_session.commit()

    # 2. Ingest sample CSV content for each season using HistoricalIngestionPipeline
    sample_csv = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR
E0,13/08/2021,Brentford,Arsenal,2,0,H,1,0,H,8,22,3,4,12,8,2,5,0,0,0,0
E0,14/08/2021,Man United,Leeds,5,1,H,1,0,H,16,10,8,3,11,9,5,4,1,2,0,0
"""
    csv_file = tmp_path / "E0_2122.csv"
    csv_file.write_text(sample_csv, encoding="utf-8")

    pipeline = HistoricalIngestionPipeline(db_session)
    pipeline.ingest_file(str(csv_file), competition_override="E0", season_override="2021-22")

    # Add dummy matches for remaining 11 seasons so every season has matches
    all_seasons = db_session.query(Season).all()
    prov = db_session.query(Provider).first()
    for s in all_seasons:
        matches_in_season = len(s.matches)
        if matches_in_season == 0:
            # Seed 1 match per season
            from app.db.models import Match, ProviderMatchMapping, ProviderTeamMapping, Team
            t1 = db_session.query(Team).filter_by(canonical_name=f"Team A {s.id}").first()
            t2 = db_session.query(Team).filter_by(canonical_name=f"Team B {s.id}").first()
            if not t1 or not t2:
                t1 = Team(canonical_name=f"Team A {s.id}")
                t2 = Team(canonical_name=f"Team B {s.id}")
                db_session.add_all([t1, t2])
                db_session.flush()
                if prov:
                    db_session.add(ProviderTeamMapping(provider_id=prov.id, team_id=t1.id, raw_alias=t1.canonical_name))
                    db_session.add(ProviderTeamMapping(provider_id=prov.id, team_id=t2.id, raw_alias=t2.canonical_name))

            m = Match(
                season_id=s.id,
                home_team_id=t1.id,
                away_team_id=t2.id,
                kickoff_utc=datetime(2023, 9, 1, 15, 0, tzinfo=UTC),
                status="FINISHED",
                home_score=1,
                away_score=0,
            )
            db_session.add(m)
            db_session.flush()
            if prov:
                db_session.add(ProviderMatchMapping(provider_id=prov.id, match_id=m.id, external_match_id=f"ext_{m.id}"))
    db_session.commit()

    # 3. Build Historical Dataset Release Candidate
    builder = HistoricalDatasetBuilder(db_session)
    build_report = builder.build_dataset_release(
        dataset_key="mvp_a_pipeline_test",
        version="v1",
        description="Phase 2 Pipeline Integration Test Dataset",
    )

    assert build_report.total_competitions == 4
    assert build_report.total_seasons == 12
    assert build_report.total_matches >= 12
    assert build_report.fingerprint is not None

    # 4. Validate Dataset Candidate
    validator = HistoricalDatasetValidator(db_session)
    val_report = validator.validate_release(dataset_key="mvp_a_pipeline_test", version="v1")
    assert val_report.is_valid is True

    # 5. Approve Dataset Candidate
    approver = HistoricalDatasetApprover(db_session)
    approved_rel = approver.approve_release(
        dataset_key="mvp_a_pipeline_test",
        version="v1",
        accepted_warnings=["Date-only kickoff precision accepted"],
    )

    assert approved_rel.status == DatasetReleaseStatusEnum.APPROVED

    # 6. Verify Downstream Approved Query Access
    query_service = HistoricalDatasetQueryService(db_session)
    approved_matches = query_service.get_dataset_matches(
        dataset_key="mvp_a_pipeline_test", version="v1", approved_only=True
    )
    assert len(approved_matches) == build_report.total_matches

    # 7. Lock Verification
    assert query_service.verify_dataset_lock(dataset_key="mvp_a_pipeline_test", version="v1") is True
