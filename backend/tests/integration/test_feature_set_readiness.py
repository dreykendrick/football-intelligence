"""
Integration Test Suite for Sprint 3.6 — Feature Set Assembly & Phase 3 Readiness Certification
Verifies manifest completeness, 247-feature composition, target outcome leakage isolation,
future match leakage isolation, dependency selectivity, numerical finiteness, determinism,
and Phase 3 readiness assertion.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import Competition, HistoricalDatasetMatch, HistoricalDatasetRelease, Match, Season, Team
from app.features.assembler import FeatureSetAssembler
from app.features.manifest import EXCLUDED_FEATURE_KEYS, get_mvp_a_feature_set_v1_manifest
from app.features.readiness import FeatureSetReadinessError, FeatureSetReadinessService


@pytest.mark.integration
def test_manifest_completeness_and_fingerprint_determinism():
    manifest1 = get_mvp_a_feature_set_v1_manifest()
    manifest2 = get_mvp_a_feature_set_v1_manifest()

    assert manifest1.feature_set_key == "mvp_a_feature_set_v1"
    assert manifest1.version == "1.0.0"
    assert manifest1.feature_count == 251
    assert manifest1.fingerprint == manifest2.fingerprint
    assert len(manifest1.fingerprint) == 16

    # Verify no excluded key is inside included keys
    included_set = set(manifest1.included_feature_keys)
    for excluded_key in EXCLUDED_FEATURE_KEYS:
        assert excluded_key not in included_set


@pytest.mark.integration
def test_feature_set_assembler_vector_generation(db_session: Session):
    comp = Competition(code="ASSM_TEST", name="Assembler Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Assm Team A")
    t2 = Team(canonical_name="Assm Team B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_prev, m_target])
    db_session.flush()

    assembler = FeatureSetAssembler()
    vector = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    assert vector.feature_set_key == "mvp_a_feature_set_v1"
    assert vector.total_feature_count == 251
    assert len(vector.ordered_feature_values) == 251
    assert len(vector.feature_vector_dict) == 251
    assert vector.snapshot_fingerprint is not None
    assert vector.coverage_percentage >= 0.0


@pytest.mark.integration
def test_complete_vector_target_result_leakage_isolation(db_session: Session):
    comp = Competition(code="LEAK_VEC", name="Vector Leak Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Leak Team A")
    t2 = Team(canonical_name="Leak Team B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=8), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=3, away_score=0)

    db_session.add_all([comp, season, t1, t2, m_prev, m_target])
    db_session.flush()

    assembler = FeatureSetAssembler()
    v1 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    # Mutate target result dramatically
    m_target.home_score = 0
    m_target.away_score = 10
    db_session.flush()

    v2 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    # All 247 pre-match features and fingerprints MUST remain strictly identical
    assert v1.feature_vector_dict == v2.feature_vector_dict
    assert v1.snapshot_fingerprint == v2.snapshot_fingerprint


@pytest.mark.integration
def test_complete_vector_future_match_leakage_isolation(db_session: Session):
    comp = Competition(code="LEAK_FUT", name="Future Leak Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Fut Team A")
    t2 = Team(canonical_name="Fut Team B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=6), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")
    m_future = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now + timedelta(days=4), status="FINISHED", home_score=5, away_score=0)

    db_session.add_all([comp, season, t1, t2, m_prev, m_target, m_future])
    db_session.flush()

    assembler = FeatureSetAssembler()
    v1 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    # Mutate future match
    m_future.home_score = 0
    m_future.away_score = 7
    db_session.flush()

    v2 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    assert v1.feature_vector_dict == v2.feature_vector_dict
    assert v1.snapshot_fingerprint == v2.snapshot_fingerprint


@pytest.mark.integration
def test_dependency_selectivity_prior_score_vs_date(db_session: Session):
    comp = Competition(code="DEP_SEL", name="Dependency Selectivity Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Dep Team A")
    t2 = Team(canonical_name="Dep Team B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=4), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_prev, m_target])
    db_session.flush()

    assembler = FeatureSetAssembler()
    v1 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)

    # 1. Mutate prior scoreline -> Goal form/Elo changes, rest days remains unchanged
    m_prev.home_score = 7
    db_session.flush()
    db_session.expire_all()

    v2 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)
    assert v1.feature_vector_dict["home_goals_scored_avg_v1"] != v2.feature_vector_dict["home_goals_scored_avg_v1"]
    assert v1.feature_vector_dict["home_rest_days_v1"] == v2.feature_vector_dict["home_rest_days_v1"] == 4.0

    # 2. Mutate prior kickoff date -> Rest days changes
    m_prev.kickoff_utc = now - timedelta(days=6)
    db_session.flush()
    db_session.expire_all()

    v3 = assembler.assemble_feature_vector_for_match(db_session, m_target.id, cutoff_timestamp=now)
    assert v3.feature_vector_dict["home_rest_days_v1"] == 6.0


@pytest.mark.integration
def test_phase_3_readiness_service_assertion(db_session: Session):
    service = FeatureSetReadinessService()

    # Readiness assertion MUST pass on a valid database session
    service.assert_feature_set_ready(db_session)

    report = service.get_readiness_report(db_session)
    assert report["status"] == "READY"
    assert report["phase_3_readiness"] == "READY"
    assert report["phase_4_readiness"] == "READY"
    assert report["total_feature_count"] == 251
    assert len(report["blockers"]) == 0
