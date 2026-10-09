"""
Sprint 4.2 Scientific Certification & Remediation Test Suite
Validates independent mathematical golden values, prediction self-consistency,
and serialized reconstruction invariants.
"""
from __future__ import annotations

import math
from uuid import uuid4
import pytest
from scipy.stats import poisson

from app.models.base import (
    BTTSProbabilityDTO,
    MatchProbabilityPrediction,
    OneXTwoProbabilityDTO,
    OverUnderProbabilityDTO,
)
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.baselines.poisson_goals import PoissonGoalsModel
from app.models.engine import GoalDistributionEngine, ProbabilityInvariantValidator
from app.models.router import ProbabilityEngine
from datetime import UTC, datetime
from app.models.dataset_dto import ModelingRowDTO

def create_mock_row(
    match_id=None,
    kickoff_utc=None,
    target_1x2="HOME_WIN",
    home_goals=2,
    away_goals=1,
    feature_dict=None,
    feature_set_key="mvp_a_feature_set_v1",
) -> ModelingRowDTO:
    if match_id is None:
        match_id = uuid4()
    if kickoff_utc is None:
        kickoff_utc = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)
    if feature_dict is None:
        feature_dict = {
            "league_home_goals_per_match_v1": 1.5,
            "league_away_goals_per_match_v1": 1.2,
            "home_attack_strength_v1": 1.2,
            "home_defense_strength_v1": 0.8,
            "away_attack_strength_v1": 0.9,
            "away_defense_strength_v1": 1.1,
            "team_home_ppg_L5": 2.1,
            "team_away_ppg_L5": 1.2,
            "elo_diff": 120.0,
            "rest_days_home": 7.0,
            "rest_days_away": 4.0,
        }
    fnames = sorted(list(feature_dict.keys()))
    fvals = [feature_dict[k] for k in fnames]
    return ModelingRowDTO(
        match_id=match_id,
        competition_id=uuid4(),
        season_id=uuid4(),
        kickoff_utc=kickoff_utc,
        temporal_precision="EXACT_TIMESTAMP",
        dataset_release_key="mvp_a_historical:v1",
        dataset_release_fingerprint="test_release_fp",
        feature_set_key=feature_set_key,
        feature_set_fingerprint="fset_fp_12345",
        ordered_feature_names=fnames,
        feature_values=fvals,
        missingness_metadata={},
        targets={
            "match_result_1x2_v1": target_1x2,
            "over_under_2_5_v1": (home_goals + away_goals) > 2.5,
            "btts_v1": home_goals > 0 and away_goals > 0,
            "home_goals_v1": home_goals,
            "away_goals_v1": away_goals,
        },
    )


def test_independent_poisson_golden_lambda_pair():
    """
    Independent Golden Test for (lambda_home=1.85, lambda_away=1.15)
    Evaluates primitive scipy Poisson formulas directly to ensure absolute mathematical truth.
    """
    lh, la = 1.85, 1.15

    # 1. Primitive PMF arrays up to k=10
    grid_size = 11
    h_pmf = [float(poisson.pmf(i, lh)) for i in range(grid_size)]
    a_pmf = [float(poisson.pmf(j, la)) for j in range(grid_size)]

    # 2. Score matrix P(H=i, A=j) = P(H=i)*P(A=j)
    matrix = [[h_pmf[i] * a_pmf[j] for j in range(grid_size)] for i in range(grid_size)]
    retained_mass = sum(sum(row) for row in matrix)
    tail_mass = 1.0 - retained_mass

    assert retained_mass == pytest.approx(0.9999959, abs=1e-5)
    assert tail_mass == pytest.approx(0.0000041, abs=1e-5)

    # 3. 1X2 Probabilities
    ph = sum(matrix[i][j] for i in range(grid_size) for j in range(grid_size) if i > j) / retained_mass
    pd = sum(matrix[i][i] for i in range(grid_size)) / retained_mass
    pa = sum(matrix[i][j] for i in range(grid_size) for j in range(grid_size) if i < j) / retained_mass

    assert ph == pytest.approx(0.53739, abs=1e-4)
    assert pd == pytest.approx(0.22729, abs=1e-4)
    assert pa == pytest.approx(0.23532, abs=1e-4)
    assert ph + pd + pa == pytest.approx(1.0, abs=1e-5)

    # 4. BTTS Probabilities
    btts_yes_analytical = 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh + la))
    btts_no_analytical = 1.0 - btts_yes_analytical

    assert btts_yes_analytical == pytest.approx(0.57591, abs=1e-4)
    assert btts_no_analytical == pytest.approx(0.42409, abs=1e-4)

    # 5. Over/Under 2.5 Probabilities
    ou_under_analytical = float(poisson.cdf(2, lh + la))
    ou_over_analytical = 1.0 - ou_under_analytical

    assert ou_under_analytical == pytest.approx(0.42319, abs=1e-4)
    assert ou_over_analytical == pytest.approx(0.57681, abs=1e-4)

    # 6. Top Exact Scores
    scores = []
    for i in range(grid_size):
        for j in range(grid_size):
            scores.append((matrix[i][j] / retained_mass, i, j))
    scores.sort(key=lambda x: (-x[0], x[1], x[2]))

    most_likely_score = (scores[0][1], scores[0][2])
    assert most_likely_score == (1, 1)  # 1-1 is most likely score (0.10592)
    assert scores[0][0] == pytest.approx(0.10592, abs=1e-4)
    assert (scores[1][1], scores[1][2]) == (2, 1)  # 2-1 is second (0.09798)
    assert scores[1][0] == pytest.approx(0.09798, abs=1e-4)


def test_prediction_self_consistency_validation_success():
    """Verifies valid goal prediction passes validate_goal_prediction_consistency."""
    row = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([row])

    router = ProbabilityEngine()
    pred = router.predict(model, row)

    # Should pass without exception
    ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)


def test_prediction_self_consistency_validation_detects_tampered_1x2():
    """Verifies validator rejects prediction where 1X2 does not match lambdas."""
    row = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([row])

    router = ProbabilityEngine()
    pred = router.predict(model, row)

    # Shift probability from draw to home_win so sum remains 1.0 but values mismatch lambdas
    pred.one_x_two.home_win += 0.1
    pred.one_x_two.draw -= 0.1

    with pytest.raises(ValueError, match="Home win probability mismatch"):
        ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)


def test_prediction_self_consistency_validation_detects_tampered_btts():
    """Verifies validator rejects prediction where BTTS does not match lambdas."""
    row = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([row])

    router = ProbabilityEngine()
    pred = router.predict(model, row)

    # Tamper BTTS yes probability
    pred.btts.yes = 0.99
    pred.btts.no = 0.01

    with pytest.raises(ValueError, match="BTTS Yes mismatch"):
        ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)


def test_prediction_self_consistency_validation_detects_tampered_ou():
    """Verifies validator rejects prediction where O/U 2.5 does not match lambdas."""
    row = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([row])

    router = ProbabilityEngine()
    pred = router.predict(model, row)

    # Tamper Over 2.5
    pred.over_under_2_5.over = 0.99
    pred.over_under_2_5.under = 0.01

    with pytest.raises(ValueError, match="Over 2.5 mismatch"):
        ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)


def test_serialized_prediction_reconstruction():
    """
    Verifies that serialized MatchProbabilityPrediction payload can be restored
    and mathematically reconstructed from stored lambdas.
    """
    row = create_mock_row()
    model = AttackDefensePoissonModel()
    model.fit([row])

    router = ProbabilityEngine()
    pred = router.predict(model, row)

    # Serialize to dict and back to DTO
    dumped = pred.model_dump(mode="json")
    reconstructed = MatchProbabilityPrediction.model_validate(dumped)

    # Validate invariant
    ProbabilityInvariantValidator.validate_goal_prediction_consistency(reconstructed)
    assert reconstructed.lambda_home == pred.lambda_home
    assert reconstructed.lambda_away == pred.lambda_away
    assert reconstructed.one_x_two.home_win == pred.one_x_two.home_win
