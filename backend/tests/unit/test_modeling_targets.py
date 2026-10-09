"""
Unit Test Suite for Sprint 4.1 — Target Label Service & Post-Match Label Derivation
Verifies 1X2, Over/Under 2.5, BTTS, and Home/Away Goal target definitions, scoreline derivations, and invalid match exclusions.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.db.models import Competition, Match, Season, Team
from app.models.targets import (
    AWAY_WIN_LABEL,
    CORE_TARGET_DEFINITIONS,
    DRAW_LABEL,
    HOME_WIN_LABEL,
    TargetLabelService,
)


@pytest.mark.unit
def test_target_definitions_catalog_completeness():
    expected_keys = {
        "match_result_1x2_v1",
        "over_under_2_5_v1",
        "btts_v1",
        "home_goals_v1",
        "away_goals_v1",
    }
    assert set(CORE_TARGET_DEFINITIONS.keys()) == expected_keys
    for key, spec in CORE_TARGET_DEFINITIONS.items():
        assert spec.target_key == key
        assert spec.version == "1.0.0"
        assert spec.valid_match_policy == "FINISHED_ONLY"


@pytest.mark.unit
def test_target_label_derivation_home_win():
    match = Match(
        id=uuid4(),
        status="FINISHED",
        home_score=3,
        away_score=1,
        kickoff_utc=datetime.now(UTC),
    )
    assert TargetLabelService.validate_match_eligibility(match) is True

    labels = TargetLabelService.derive_labels_for_match(match)
    assert labels["match_result_1x2_v1"] == HOME_WIN_LABEL
    assert labels["over_under_2_5_v1"] is True  # 3 + 1 = 4 >= 3
    assert labels["btts_v1"] is True  # 3 > 0 and 1 > 0
    assert labels["home_goals_v1"] == 3
    assert labels["away_goals_v1"] == 1


@pytest.mark.unit
def test_target_label_derivation_draw():
    match = Match(
        id=uuid4(),
        status="FINISHED",
        home_score=0,
        away_score=0,
        kickoff_utc=datetime.now(UTC),
    )
    assert TargetLabelService.validate_match_eligibility(match) is True

    labels = TargetLabelService.derive_labels_for_match(match)
    assert labels["match_result_1x2_v1"] == DRAW_LABEL
    assert labels["over_under_2_5_v1"] is False  # 0 + 0 = 0 < 3
    assert labels["btts_v1"] is False  # not (0 > 0 and 0 > 0)
    assert labels["home_goals_v1"] == 0
    assert labels["away_goals_v1"] == 0


@pytest.mark.unit
def test_target_label_derivation_away_win():
    match = Match(
        id=uuid4(),
        status="FINISHED",
        home_score=1,
        away_score=2,
        kickoff_utc=datetime.now(UTC),
    )
    assert TargetLabelService.validate_match_eligibility(match) is True

    labels = TargetLabelService.derive_labels_for_match(match)
    assert labels["match_result_1x2_v1"] == AWAY_WIN_LABEL
    assert labels["over_under_2_5_v1"] is True  # 1 + 2 = 3 >= 3
    assert labels["btts_v1"] is True
    assert labels["home_goals_v1"] == 1
    assert labels["away_goals_v1"] == 2


@pytest.mark.unit
def test_invalid_match_status_exclusion():
    # Scheduled match
    m_scheduled = Match(id=uuid4(), status="SCHEDULED", home_score=None, away_score=None)
    assert TargetLabelService.validate_match_eligibility(m_scheduled) is False
    with pytest.raises(ValueError, match="is ineligible for target label generation"):
        TargetLabelService.derive_labels_for_match(m_scheduled)

    # Postponed match
    m_postponed = Match(id=uuid4(), status="POSTPONED", home_score=None, away_score=None)
    assert TargetLabelService.validate_match_eligibility(m_postponed) is False

    # Missing score match marked finished
    m_missing_score = Match(id=uuid4(), status="FINISHED", home_score=None, away_score=2)
    assert TargetLabelService.validate_match_eligibility(m_missing_score) is False
