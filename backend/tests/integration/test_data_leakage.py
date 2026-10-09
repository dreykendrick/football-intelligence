"""
Integration Tests for Strict Data Leakage Prevention
Proves that modifying future matches or the target match's own result has ZERO effect on pre-match feature snapshots.
"""
from datetime import UTC, datetime

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


@pytest.mark.integration
def test_future_match_modification_does_not_affect_past_snapshot(db_session: Session):
    comp = Competition(code="LEAK_TEST_1", name="Leak League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Leak")
    t2 = Team(canonical_name="Chelsea Leak")

    t_jan1 = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    t_jan8 = datetime(2024, 1, 8, 12, 0, tzinfo=UTC)
    t_jan15 = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)  # Target Cutoff
    t_jan22 = datetime(2024, 1, 22, 12, 0, tzinfo=UTC)  # Future Match D

    mA = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_jan1, status="FINISHED", home_score=2, away_score=0)
    mB = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=t_jan8, status="FINISHED", home_score=1, away_score=1)
    mC = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_jan15, status="SCHEDULED")
    mD = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_jan22, status="FINISHED", home_score=1, away_score=0)

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    mapA = ProviderMatchMapping(provider=provider, match=mA, external_match_id="ext_leak_A")
    mapB = ProviderMatchMapping(provider=provider, match=mB, external_match_id="ext_leak_B")
    mapC = ProviderMatchMapping(provider=provider, match=mC, external_match_id="ext_leak_C")
    mapD = ProviderMatchMapping(provider=provider, match=mD, external_match_id="ext_leak_D")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Arsenal Leak")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Chelsea Leak")

    db_session.add_all([comp, season, t1, t2, mA, mB, mC, mD, provider, batch, mapA, mapB, mapC, mapD, pt1, pt2])
    db_session.commit()

    service = FeatureEngineService(db_session)

    # 1. Generate snapshot for Target Match C at cutoff Jan 15
    snapshot1 = service.generate_snapshot_for_match(mC.id, cutoff_timestamp=t_jan15)
    val1 = dict(snapshot1.feature_values)

    # 2. Dramatically modify Future Match D (Jan 22)
    mD.home_score = 10
    mD.away_score = 0
    db_session.commit()

    # 3. Recalculate feature values for Match C at cutoff Jan 15
    from app.features.registry import FEATURE_CATALOG
    recalculated_values = {}
    for fkey, calc in FEATURE_CATALOG.items():
        res = calc.calculate(db_session, mC, cutoff_timestamp=t_jan15)
        recalculated_values[fkey] = res.value

    # 4. Verify 100% strict equality
    assert val1 == recalculated_values


@pytest.mark.integration
def test_target_match_result_mutation_does_not_affect_pre_match_snapshot(db_session: Session):
    comp = Competition(code="LEAK_TEST_2", name="Leak League 2", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Liverpool Leak")
    t2 = Team(canonical_name="Everton Leak")

    t_past = datetime(2024, 2, 1, 12, 0, tzinfo=UTC)
    t_target = datetime(2024, 2, 10, 12, 0, tzinfo=UTC)

    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_past, status="FINISHED", home_score=3, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_target, status="SCHEDULED")

    provider = Provider(provider_key="football_data_co_uk", display_name="Test Provider")
    batch = IngestionBatch(provider=provider, source_type="HISTORICAL_CSV", source_reference="test.csv")
    map1 = ProviderMatchMapping(provider=provider, match=m1, external_match_id="ext_leak2_1")
    mapt = ProviderMatchMapping(provider=provider, match=m_target, external_match_id="ext_leak2_t")
    pt1 = ProviderTeamMapping(provider=provider, team=t1, raw_alias="Liverpool Leak")
    pt2 = ProviderTeamMapping(provider=provider, team=t2, raw_alias="Everton Leak")

    db_session.add_all([comp, season, t1, t2, m1, m_target, provider, batch, map1, mapt, pt1, pt2])
    db_session.commit()

    service = FeatureEngineService(db_session)

    # 1. Generate snapshot prior to match kickoff
    snapshot1 = service.generate_snapshot_for_match(m_target.id, cutoff_timestamp=t_target)
    val1 = dict(snapshot1.feature_values)

    # 2. Update target match's own result (simulate match completing)
    m_target.status = "FINISHED"
    m_target.home_score = 5
    m_target.away_score = 0
    db_session.commit()

    # 3. Recalculate pre-match features using cutoff = t_target
    from app.features.registry import FEATURE_CATALOG
    recalculated_values = {}
    for fkey, calc in FEATURE_CATALOG.items():
        res = calc.calculate(db_session, m_target, cutoff_timestamp=t_target)
        recalculated_values[fkey] = res.value

    # 4. Verify pre-match snapshot is completely unpolluted by target result
    assert val1 == recalculated_values
