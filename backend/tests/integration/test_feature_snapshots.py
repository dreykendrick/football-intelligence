"""
Integration Tests for Feature Snapshot Generation & Persistence
Verifies FeatureSnapshot persistence, SHA-256 fingerprinting, determinism, and Quality Gate integration.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Competition,
    IngestionBatch,
    Match,
    Provider,
    ProviderMatchMapping,
    ProviderTeamMapping,
    Season,
    Team,
)
from app.features.service import FeatureEngineService
from app.quality.gate import QualityGateException


@pytest.mark.integration
def test_feature_snapshot_generation_and_persistence(db_session: Session):
    comp = Competition(code="SNAP_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Snap")
    t2 = Team(canonical_name="Chelsea Snap")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    map1 = ProviderMatchMapping(provider=provider, match=m1, external_match_id="ext_snap_1")
    map2 = ProviderMatchMapping(provider=provider, match=m_target, external_match_id="ext_snap_2")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Arsenal Snap")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Chelsea Snap")

    db_session.add_all([comp, season, t1, t2, m1, m_target, provider, batch, map1, map2, pt1, pt2])
    db_session.commit()

    service = FeatureEngineService(db_session)
    snapshot = service.generate_snapshot_for_match(m_target.id, cutoff_timestamp=now)

    assert snapshot is not None
    assert snapshot.match_id == m_target.id
    assert snapshot.feature_version == "1.0.0"
    assert "home_goals_scored_avg_v1" in snapshot.feature_values
    assert snapshot.feature_values["home_goals_scored_avg_v1"] == 2.0
    assert "fingerprint_sha256" in snapshot.data_quality_metadata


@pytest.mark.integration
def test_feature_snapshot_determinism(db_session: Session):
    comp = Competition(code="DET_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Det 1")
    t2 = Team(canonical_name="Team Det 2")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    map1 = ProviderMatchMapping(provider=provider, match=m1, external_match_id="ext_det_1")
    map2 = ProviderMatchMapping(provider=provider, match=m_target, external_match_id="ext_det_2")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Team Det 1")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Team Det 2")

    db_session.add_all([comp, season, t1, t2, m1, m_target, provider, batch, map1, map2, pt1, pt2])
    db_session.commit()

    service = FeatureEngineService(db_session)
    s1 = service.generate_snapshot_for_match(m_target.id, cutoff_timestamp=now)
    s2 = service.generate_snapshot_for_match(m_target.id, cutoff_timestamp=now)

    assert s1.id == s2.id
    assert s1.feature_values == s2.feature_values
    assert s1.data_quality_metadata["fingerprint_sha256"] == s2.data_quality_metadata["fingerprint_sha256"]


@pytest.mark.integration
def test_quality_gate_blocks_feature_generation_on_blocking_issue(db_session: Session):
    comp = Competition(code="QG_BLOCK", name="Test League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team QG 1")
    t2 = Team(canonical_name="Team QG 2")

    now = datetime.now(UTC)

    # Finished match missing score (DQ_MATCH_001 BLOCKING)
    m_invalid = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=None, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_invalid, m_target])
    db_session.commit()

    service = FeatureEngineService(db_session)
    with pytest.raises(QualityGateException, match="Quality Gate FAILED"):
        service.generate_snapshot_for_match(m_target.id, cutoff_timestamp=now)
