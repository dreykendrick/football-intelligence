"""
Integration Tests for Quality Gate & Data Leakage Prevention
Verifies QualityGate assertion logic and time-bounded anti-leakage query verification.
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
from app.quality.base import ReadinessStatusEnum
from app.quality.gate import QualityGate, QualityGateException


@pytest.mark.integration
def test_quality_gate_passes_on_valid_data(db_session: Session):
    comp = Competition(code="GATE_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Gate")
    t2 = Team(canonical_name="Chelsea Gate")
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=2, away_score=1)

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    mapping = ProviderMatchMapping(provider=provider, match=match, external_match_id="ext_gate_1")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Arsenal Gate")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Chelsea Gate")

    db_session.add_all([comp, season, t1, t2, match, provider, batch, mapping, pt1, pt2])
    db_session.commit()

    report = QualityGate.assert_historical_data_ready(db_session)
    assert report.global_status in (ReadinessStatusEnum.READY, ReadinessStatusEnum.READY_WITH_WARNINGS)
    assert report.blocking_count == 0


@pytest.mark.integration
def test_quality_gate_fails_on_blocking_issue(db_session: Session):
    comp = Competition(code="BLOCK_LEAGUE", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Block 1")
    t2 = Team(canonical_name="Team Block 2")
    # Match missing score (DQ_MATCH_001)
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=None, away_score=1)

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    mapping = ProviderMatchMapping(provider=provider, match=match, external_match_id="ext_block_1")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Team Block 1")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Team Block 2")

    db_session.add_all([comp, season, t1, t2, match, provider, mapping, pt1, pt2])
    db_session.commit()

    with pytest.raises(QualityGateException, match="Quality Gate FAILED"):
        QualityGate.assert_historical_data_ready(db_session)


@pytest.mark.integration
def test_data_leakage_safety_verification(db_session: Session):
    comp = Competition(code="LEAK_EPL", name="Leak League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Leak 1")
    t2 = Team(canonical_name="Team Leak 2")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=2)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now + timedelta(days=5), status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3])
    db_session.commit()

    # Cutoff set to now
    historical_matches = QualityGate.verify_data_leakage_safety(db_session, t1.id, cutoff_timestamp=now)

    assert len(historical_matches) == 2
    for m in historical_matches:
        m_kickoff = m.kickoff_utc.replace(tzinfo=UTC) if m.kickoff_utc.tzinfo is None else m.kickoff_utc
        assert m_kickoff < now
