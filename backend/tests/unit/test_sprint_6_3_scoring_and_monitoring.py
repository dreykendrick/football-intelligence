"""
Sprint 6.3 Post-Match Scoring & Monitoring Regression Tests (Section 83)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.prediction.domain import ShadowPredictionInput, ShadowPredictionResult
from app.prediction.monitoring import ShadowMonitoringService
from app.prediction.scoring import (
    PostMatchScoringService,
    calculate_1x2_metrics,
    calculate_binary_metrics,
)
from app.prediction.service import ShadowPredictionService


def make_sample_prediction() -> ShadowPredictionResult:
    now = datetime.now(UTC)
    inp = ShadowPredictionInput(
        fixture_id=uuid4(),
        competition_code="Premier League",
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=now + timedelta(hours=3),
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint="fp_snap_sample",
        history_fingerprint="fp_hist_sample",
        feature_count=251,
        feature_values=[0.5] * 251,
        feature_keys=[f"f_{i}" for i in range(251)],
    )
    svc = ShadowPredictionService()
    pred = svc.predict(inp)
    assert isinstance(pred, ShadowPredictionResult)
    return pred


def test_shadow_scoring_is_idempotent():
    pred = make_sample_prediction()
    scoring_svc = PostMatchScoringService()

    ev1 = scoring_svc.score_prediction(pred, actual_home_goals=2, actual_away_goals=1, match_status="FINISHED", result_version=1)
    ev2 = scoring_svc.score_prediction(pred, actual_home_goals=2, actual_away_goals=1, match_status="FINISHED", result_version=1)

    assert ev1.evaluation_id == ev2.evaluation_id
    assert ev1.log_loss_1x2 == ev2.log_loss_1x2
    assert ev1.brier_1x2 == ev2.brier_1x2


def test_shadow_scoring_rejects_non_terminal_match():
    pred = make_sample_prediction()
    scoring_svc = PostMatchScoringService()

    with pytest.raises(ValueError, match="CANNOT_SCORE_NON_TERMINAL_RESULT"):
        scoring_svc.score_prediction(pred, actual_home_goals=1, actual_away_goals=0, match_status="LIVE")


def test_shadow_result_correction_is_auditable():
    pred = make_sample_prediction()
    scoring_svc = PostMatchScoringService()

    # Original evaluation (v1): 2-1 Home win
    ev1 = scoring_svc.score_prediction(pred, actual_home_goals=2, actual_away_goals=1, result_version=1)
    # Corrected evaluation (v2): 1-1 Draw
    ev2 = scoring_svc.score_prediction(pred, actual_home_goals=1, actual_away_goals=1, result_version=2)

    assert ev1.evaluation_id != ev2.evaluation_id
    assert ev1.result_version == 1
    assert ev2.result_version == 2
    assert ev1.actual_1x2 == "HOME_WIN"
    assert ev2.actual_1x2 == "DRAW"
    # Original prediction object is completely untouched
    assert pred.prob_home > 0


def test_shadow_1x2_scoring_metrics_accuracy():
    # If pred is H=0.6, D=0.3, A=0.1 and actual is HOME_WIN (y=(1, 0, 0))
    ll, brier = calculate_1x2_metrics(0.6, 0.3, 0.1, "HOME_WIN")
    # Expected LL = -ln(0.6) = ~0.51083
    # Expected Brier = (0.6 - 1)^2 + (0.3 - 0)^2 + (0.1 - 0)^2 = 0.16 + 0.09 + 0.01 = 0.26
    assert abs(ll - 0.51083) < 1e-4
    assert abs(brier - 0.26) < 1e-4


def test_shadow_btts_and_ou_metrics_accuracy():
    # Yes=0.7, actual=True -> LL = -ln(0.7) = ~0.35667, Brier = (0.7 - 1)^2 = 0.09
    ll, brier = calculate_binary_metrics(0.7, True)
    assert abs(ll - 0.35667) < 1e-4
    assert abs(brier - 0.09) < 1e-4

    # Yes=0.7, actual=False -> LL = -ln(0.3) = ~1.20397, Brier = (0.7 - 0)^2 = 0.49
    ll2, brier2 = calculate_binary_metrics(0.7, False)
    assert abs(ll2 - 1.20397) < 1e-4
    assert abs(brier2 - 0.49) < 1e-4


def test_shadow_minimum_sample_size_protection():
    mon = ShadowMonitoringService()
    pred = make_sample_prediction()
    scoring_svc = PostMatchScoringService()

    evaluations = [
        scoring_svc.score_prediction(pred, actual_home_goals=1, actual_away_goals=0, result_version=i + 1)
        for i in range(10)
    ]

    res = mon.evaluate_label_aware_cohort(evaluations)
    assert res["status"] == "INSUFFICIENT_SAMPLE"
    assert res["sample_size"] == 10
    assert res["required_sample"] == 50


def test_shadow_observational_alerting_does_not_retrain():
    mon = ShadowMonitoringService()
    pred = make_sample_prediction()
    pred.fallback_used = True

    # 100 predictions with 100% fallback rate triggers alert
    batch = [pred] * 100
    mon.evaluate_label_free_cohort(batch)

    assert len(mon.alerts) > 0
    alert = mon.alerts[0]
    assert alert.severity == "CRITICAL"
    assert alert.metric == "fallback_rate"

    # Monitoring service has zero retraining capabilities
    assert not hasattr(mon, "retrain")
    assert not hasattr(mon, "update_weights")
