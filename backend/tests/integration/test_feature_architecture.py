"""
Integration Tests for Feature Architecture & Point-in-Time Foundation (Sprint 3.1)
Verifies Feature Registry, FeatureSet fingerprinting, approved dataset scoping, and feature snapshot persistence.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum, DatasetValidationError
from app.db.models import (
    Competition,
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    HistoricalDatasetSeason,
    IngestionBatch,
    Match,
    Provider,
    ProviderMatchMapping,
    ProviderTeamMapping,
    Season,
    Team,
)
from app.features.definitions import CORE_FEATURE_DEFINITIONS
from app.features.fingerprint import FeatureSetFingerprintCalculator
from app.features.registry import global_feature_registry
from app.features.service import FeatureEngineService
from app.features.sets import FeatureSetManager


@pytest.mark.integration
def test_feature_registry_and_definitions():
    """Verifies that all MVP-A feature calculators are registered with valid metadata definitions."""
    keys = global_feature_registry.list_feature_keys()
    assert len(keys) >= 20

    for fkey in keys:
        calc = global_feature_registry.get_calculator(fkey)
        assert calc is not None
        meta = global_feature_registry.get_definition(fkey)
        assert meta is not None
        assert meta.feature_key == fkey


@pytest.mark.integration
def test_feature_set_fingerprinting(db_session: Session):
    """Verifies FeatureSet creation, metadata linking, and SHA-256 fingerprint determinism."""
    fset = FeatureSetManager.get_or_create_mvp_a_feature_set(db_session)
    assert fset is not None
    assert fset.name == "mvp_a_feature_set_v1"
    assert fset.version == "1.0.0"

    keys = [item.feature_definition.feature_key for item in fset.features]
    fp = FeatureSetFingerprintCalculator.compute_fingerprint(
        name=fset.name, version=fset.version, feature_keys=keys
    )
    assert len(fp) == 64


@pytest.mark.integration
def test_approved_dataset_enforcement(db_session: Session):
    """Verifies that feature calculation against an unapproved dataset release raises DatasetValidationError."""
    comp = Competition(code="UNAPP_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Unapp 1")
    t2 = Team(canonical_name="Team Unapp 2")
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="SCHEDULED")

    # Draft release (unapproved)
    release = HistoricalDatasetRelease(
        key="unapproved_dataset",
        version="v1",
        description="Unapproved Dataset",
        selection_policy_key="mvp_a_recent_3_usable_seasons_v1",
        selection_policy_version="1.0.0",
        status=DatasetReleaseStatusEnum.DRAFT.value,
        dataset_fingerprint="0000000000000000000000000000000000000000000000000000000000000000",
    )
    db_session.add_all([comp, season, t1, t2, m1, release])
    db_session.commit()

    service = FeatureEngineService(db_session)
    with pytest.raises(DatasetValidationError, match="is in status 'DRAFT'"):
        service.generate_snapshot_for_match(
            match_id=m1.id,
            dataset_key="unapproved_dataset",
            dataset_version="v1",
            approved_only=True,
            skip_quality_gate=True,
        )


@pytest.mark.integration
def test_feature_snapshot_provenance_and_persistence(db_session: Session):
    """Verifies feature snapshot generation with approved dataset provenance and fingerprinting."""
    comp = Competition(code="PROV_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Prov")
    t2 = Team(canonical_name="Chelsea Prov")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    map1 = ProviderMatchMapping(provider=provider, match=m1, external_match_id="ext_prov_1")
    map2 = ProviderMatchMapping(provider=provider, match=m_target, external_match_id="ext_prov_2")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Arsenal Prov")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Chelsea Prov")

    release = HistoricalDatasetRelease(
        key="mvp_a_historical",
        version="v1",
        description="MVP-A Approved Historical Dataset Release v1",
        selection_policy_key="mvp_a_recent_3_usable_seasons_v1",
        selection_policy_version="1.0.0",
        status=DatasetReleaseStatusEnum.APPROVED.value,
        dataset_fingerprint="1111111111111111111111111111111111111111111111111111111111111111",
    )
    db_session.add_all([comp, season, t1, t2, m1, m_target, provider, batch, map1, map2, pt1, pt2, release])
    db_session.flush()

    hm1 = HistoricalDatasetMatch(dataset_release_id=release.id, match_id=m1.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m1.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id)
    hm2 = HistoricalDatasetMatch(dataset_release_id=release.id, match_id=m_target.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_target.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id)
    db_session.add_all([hm1, hm2])
    db_session.commit()

    service = FeatureEngineService(db_session)
    snapshot = service.generate_snapshot_for_match(
        match_id=m_target.id,
        cutoff_timestamp=now,
        dataset_key="mvp_a_historical",
        dataset_version="v1",
        skip_quality_gate=True,
    )

    assert snapshot is not None
    assert snapshot.match_id == m_target.id
    assert snapshot.data_quality_metadata["dataset_key"] == "mvp_a_historical"
    assert snapshot.data_quality_metadata["dataset_version"] == "v1"
    assert "fingerprint_sha256" in snapshot.data_quality_metadata
