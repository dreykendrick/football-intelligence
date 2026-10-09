"""
Integration Tests for Data Quality Engine & Finding Persistence
Verifies end-to-end quality validation execution, database findings persistence, and resolution management.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Competition,
    DataQualityLog,
    Match,
    Season,
    Team,
)
from app.quality.engine import DataQualityEngine


@pytest.mark.integration
def test_quality_engine_execution_and_persistence(db_session: Session):
    engine = DataQualityEngine(db_session)

    # Seed data with a missing provenance match (DQ_MATCH_009)
    comp = Competition(code="PREM_Q", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal QC")
    t2 = Team(canonical_name="Chelsea QC")
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=2, away_score=1)

    db_session.add_all([comp, season, t1, t2, match])
    db_session.commit()

    findings = engine.run_all_checks()
    assert len(findings) > 0

    # Verify findings saved to data_quality_logs table
    log_count = db_session.query(DataQualityLog).count()
    assert log_count > 0

    log = db_session.query(DataQualityLog).filter_by(rule_key="DQ_MATCH_009").first()
    assert log is not None
    assert log.severity == "BLOCKING"
    assert log.resolution_status == "OPEN"


@pytest.mark.integration
def test_finding_resolution_status_update(db_session: Session):
    engine = DataQualityEngine(db_session)

    comp = Competition(code="RES_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Res 1")
    t2 = Team(canonical_name="Team Res 2")
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=2, away_score=1)

    db_session.add_all([comp, season, t1, t2, match])
    db_session.commit()

    engine.run_all_checks()

    log = db_session.query(DataQualityLog).filter_by(rule_key="DQ_MATCH_009").first()
    assert log is not None

    success = engine.update_resolution_status(log.issue_key, "ACCEPTED_LIMITATION", "Historical legacy data approved by PM")
    assert success is True

    updated_log = db_session.query(DataQualityLog).filter_by(issue_key=log.issue_key).first()
    assert updated_log.resolution_status == "ACCEPTED_LIMITATION"
    assert updated_log.resolution_reason == "Historical legacy data approved by PM"
