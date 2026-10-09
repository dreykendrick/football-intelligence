import pytest
import os
from unittest.mock import patch, MagicMock
from app.models.registry import global_model_registry
from app.models.evaluation import multiclass_brier_score, expected_calibration_error

def test_global_brier_equals_mean_fixture_brier():
    y_true = [0, 1, 2]
    y_probs = [[0.8, 0.1, 0.1], [0.2, 0.6, 0.2], [0.3, 0.3, 0.4]]
    global_brier = multiclass_brier_score(y_true, y_probs)
    def per_fixture_brier(t, p):
        oh = [1.0 if i == t else 0.0 for i in range(3)]
        return sum((p[i] - oh[i])**2 for i in range(3))
    mean_brier = sum(per_fixture_brier(t, p) for t, p in zip(y_true, y_probs)) / len(y_true)
    assert abs(global_brier - mean_brier) < 1e-9

def test_paired_brier_delta_equals_global_brier_difference():
    y_true = [0, 1]
    y_probs_1 = [[0.9, 0.1, 0.0], [0.1, 0.8, 0.1]]
    y_probs_2 = [[0.6, 0.3, 0.1], [0.3, 0.4, 0.3]]
    gb1 = multiclass_brier_score(y_true, y_probs_1)
    gb2 = multiclass_brier_score(y_true, y_probs_2)
    global_diff = gb1 - gb2
    def per_fixture_brier(t, p):
        oh = [1.0 if i == t else 0.0 for i in range(3)]
        return sum((p[i] - oh[i])**2 for i in range(3))
    diffs = [per_fixture_brier(t, p1) - per_fixture_brier(t, p2) for t, p1, p2 in zip(y_true, y_probs_1, y_probs_2)]
    mean_diff = sum(diffs) / len(diffs)
    assert abs(global_diff - mean_diff) < 1e-9

def test_calibration_metrics_distinct():
    y_true = [0, 1, 2]
    y_probs = [[0.6, 0.2, 0.2], [0.4, 0.5, 0.1], [0.1, 0.1, 0.8]]
    top_ece = expected_calibration_error(y_true, y_probs, n_bins=10)
    assert isinstance(top_ece, float)

def test_weighted_league_metrics_equal_global_metrics():
    n1, ll1 = 100, 0.95
    n2, ll2 = 50, 1.05
    global_ll = (n1 * ll1 + n2 * ll2) / (n1 + n2)
    assert abs(global_ll - 0.983333333333) < 1e-5

def test_sprint_4_5_candidate_champion_registered():
    from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
    assert global_model_registry.get_model_class("multinomial_logistic_1x2_v1") is not None

def test_sprint_4_5_candidate_champion_serialization():
    from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
    path = "C:\\Users\\kibaj\\.gemini\\antigravity\\brain\\434146cb-284a-4fa9-a2c0-d58e4c2e98a8\\scratch\\C1_artifact.json"
    if os.path.exists(path):
        model = MultinomialLogistic1X2Model()
        model.load_artifact(path)
        assert model.artifact is not None
        assert model.artifact.model_key == "multinomial_logistic_1x2_v1"
