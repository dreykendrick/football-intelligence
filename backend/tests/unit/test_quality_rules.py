"""
Unit Tests for Data Quality Validation Rules
Verifies rule registry definitions, structural, domain, and analytical validation logic.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, MatchStatistic, Season, Team
from app.quality.rules.analytical import evaluate_analytical_rules
from app.quality.rules.domain import evaluate_domain_rules
from app.quality.rules.registry import RULE_REGISTRY


@pytest.mark.unit
def test_rule_registry_completeness():
    assert "DQ_MATCH_001" in RULE_REGISTRY
    assert "DQ_MATCH_005" in RULE_REGISTRY
    assert "DQ_MATCH_010" in RULE_REGISTRY
    assert "DQ_DUPLICATE_001" in RULE_REGISTRY
    assert "DQ_TEAM_002" in RULE_REGISTRY
    assert RULE_REGISTRY["DQ_MATCH_001"].blocks_feature_engineering is True


@pytest.mark.unit
def test_domain_rules_detect_missing_scores(db_session: Session):
    comp = Competition(code="TEST_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team A")
    t2 = Team(canonical_name="Team B")
    # Finished match missing score
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=None, away_score=1)

    db_session.add_all([comp, season, t1, t2, match])
    db_session.flush()

    findings = evaluate_domain_rules(db_session)
    finding_keys = [f.rule_key for f in findings]
    assert "DQ_MATCH_001" in finding_keys


@pytest.mark.unit
def test_domain_rules_detect_shots_on_target_exceeds(db_session: Session):
    comp = Competition(code="TEST_S", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team A Shot")
    t2 = Team(canonical_name="Team B Shot")
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC), status="FINISHED", home_score=2, away_score=1)
    stat = MatchStatistic(match=match, team=t1, shots=5, shots_on_target=8)

    db_session.add_all([comp, season, t1, t2, match, stat])
    db_session.flush()

    findings = evaluate_domain_rules(db_session)
    finding_keys = [f.rule_key for f in findings]
    assert "DQ_STAT_001" in finding_keys


@pytest.mark.unit
def test_analytical_rules_detect_team_similarity(db_session: Session):
    t1 = Team(canonical_name="Manchester United")
    t2 = Team(canonical_name="Man United")

    db_session.add_all([t1, t2])
    db_session.flush()

    findings = evaluate_analytical_rules(db_session)
    finding_keys = [f.rule_key for f in findings]
    assert "DQ_TEAM_002" in finding_keys
