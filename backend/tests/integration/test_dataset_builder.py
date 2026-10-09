"""
Integration Tests for Dataset Release Builder, Validation, Approval, and Query Service
"""
from datetime import UTC, datetime

import pytest

from app.dataset.approval import HistoricalDatasetApprover
from app.dataset.base import (
    DatasetAlreadyApprovedError,
    DatasetReleaseStatusEnum,
    DatasetValidationError,
)
from app.dataset.builder import HistoricalDatasetBuilder
from app.dataset.query import HistoricalDatasetQueryService
from app.dataset.validator import HistoricalDatasetValidator
from app.db.models import (
    Competition,
    HistoricalDatasetRelease,
    Match,
    Provider,
    ProviderMatchMapping,
    ProviderTeamMapping,
    Season,
    Team,
)


@pytest.mark.integration
def test_dataset_build_validation_approval_lifecycle(db_session):
    # Setup test entities for 4 target competitions x 3 seasons = 12 seasons
    comps = []
    comp_codes = ["E0", "SP1", "I1", "D1"]
    for code in comp_codes:
        c = Competition(code=code, name=f"Competition {code}", country="TestCountry")
        db_session.add(c)
        comps.append(c)
    db_session.flush()

    seasons = []
    season_years = ["2021-22", "2022-23", "2023-24"]
    for comp in comps:
        for year in season_years:
            s = Season(competition_id=comp.id, season_year=year)
            db_session.add(s)
            seasons.append(s)
    db_session.flush()

    # Create Provider, ProviderTeamMapping, and ProviderMatchMapping for provenance rule DQ_MATCH_009
    provider = Provider(provider_key="football_data_uk", display_name="Football-Data.co.uk", provider_type="HISTORICAL_CSV")
    db_session.add(provider)
    db_session.flush()

    # Create dummy teams & finished matches for each season
    team_a = Team(canonical_name="Canonical Alpha FC")
    team_b = Team(canonical_name="Canonical Beta United")
    db_session.add_all([team_a, team_b])
    db_session.flush()

    db_session.add(ProviderTeamMapping(provider_id=provider.id, team_id=team_a.id, raw_alias="Canonical Alpha FC"))
    db_session.add(ProviderTeamMapping(provider_id=provider.id, team_id=team_b.id, raw_alias="Canonical Beta United"))

    for s in seasons:
        m = Match(
            season_id=s.id,
            home_team_id=team_a.id,
            away_team_id=team_b.id,
            kickoff_utc=datetime(2023, 9, 1, 15, 0, tzinfo=UTC),
            status="FINISHED",
            home_score=2,
            away_score=1,
        )
        db_session.add(m)
        db_session.flush()
        db_session.add(ProviderMatchMapping(provider_id=provider.id, match_id=m.id, external_match_id=f"ext_{m.id}"))

    db_session.commit()

    # 1. Build dataset release candidate (DRAFT)
    builder = HistoricalDatasetBuilder(db_session)
    report = builder.build_dataset_release(
        dataset_key="test_dataset",
        version="v1",
        description="Test Dataset Candidate",
    )

    assert report.dataset_key == "test_dataset"
    assert report.version == "v1"
    assert report.status == DatasetReleaseStatusEnum.DRAFT
    assert report.total_competitions == 4
    assert report.total_seasons == 12
    assert report.total_matches == 12
    assert report.fingerprint is not None
    assert len(report.fingerprint) == 64

    # 2. Validate release candidate
    validator = HistoricalDatasetValidator(db_session)
    val_report = validator.validate_release(dataset_key="test_dataset", version="v1")
    assert val_report.is_valid is True
    assert len(val_report.blockers) == 0

    # 3. Approve release candidate
    approver = HistoricalDatasetApprover(db_session)
    approved_dto = approver.approve_release(
        dataset_key="test_dataset",
        version="v1",
        accepted_warnings=["Date-only kickoff precision accepted"],
    )

    assert approved_dto.status == DatasetReleaseStatusEnum.APPROVED
    assert approved_dto.approved_at is not None
    assert approved_dto.warning_acceptances is not None

    # 4. Verify approved query service returns correct matches
    query_service = HistoricalDatasetQueryService(db_session)
    matches = query_service.get_dataset_matches(dataset_key="test_dataset", version="v1")
    assert len(matches) == 12

    # 5. Verify fingerprint lock check passes
    assert query_service.verify_dataset_lock(dataset_key="test_dataset", version="v1") is True


@pytest.mark.integration
def test_approval_rejects_already_approved_release(db_session):
    # Create an APPROVED release entity directly
    release = HistoricalDatasetRelease(
        key="approved_test",
        version="v1",
        status=DatasetReleaseStatusEnum.APPROVED.value,
        selection_policy_key="p",
        selection_policy_version="1.0.0",
        total_competitions=4,
        total_seasons=12,
        total_matches=12,
        dataset_fingerprint="a" * 64,
        quality_status="READY",
        identity_readiness_status="READY",
    )
    db_session.add(release)
    db_session.commit()

    approver = HistoricalDatasetApprover(db_session)
    with pytest.raises(DatasetAlreadyApprovedError):
        approver.approve_release(dataset_key="approved_test", version="v1")


@pytest.mark.integration
def test_quality_blocker_prevents_dataset_approval(db_session):
    # Setup deficient dataset with open blocking issue
    comp = Competition(code="E0", name="EPL", country="England")
    db_session.add(comp)
    db_session.flush()

    season = Season(competition_id=comp.id, season_year="2023-24")
    db_session.add(season)
    db_session.flush()

    team_a = Team(canonical_name="Team A")
    team_b = Team(canonical_name="Team B")
    db_session.add_all([team_a, team_b])
    db_session.flush()

    provider = Provider(provider_key="football_data_uk", display_name="Football-Data.co.uk", provider_type="HISTORICAL_CSV")
    db_session.add(provider)
    db_session.flush()

    db_session.add(ProviderTeamMapping(provider_id=provider.id, team_id=team_a.id, raw_alias="Team A"))
    db_session.add(ProviderTeamMapping(provider_id=provider.id, team_id=team_b.id, raw_alias="Team B"))

    match = Match(
        season_id=season.id,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        kickoff_utc=datetime(2023, 9, 1, 15, 0, tzinfo=UTC),
        status="FINISHED",
        home_score=None,  # Triggers DQ_MATCH_001 BLOCKING issue
        away_score=0,
    )
    db_session.add(match)
    db_session.flush()

    db_session.add(ProviderMatchMapping(provider_id=provider.id, match_id=match.id, external_match_id=f"ext_{match.id}"))
    db_session.commit()

    # Attempt to build and validate
    builder = HistoricalDatasetBuilder(db_session)
    report = builder.build_dataset_release(dataset_key="blocked_dataset", version="v1")

    # Season with BLOCKED status is automatically excluded from policy selection
    assert report.total_seasons == 0
    assert report.total_matches == 0

    validator = HistoricalDatasetValidator(db_session)
    val_report = validator.validate_release(dataset_key="blocked_dataset", version="v1")
    assert val_report.is_valid is False
    assert any("Deficient competition season coverage" in b for b in val_report.blockers)

    approver = HistoricalDatasetApprover(db_session)
    with pytest.raises(DatasetValidationError):
        approver.approve_release(dataset_key="blocked_dataset", version="v1")
