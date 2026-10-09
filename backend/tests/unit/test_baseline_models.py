"""
Unit Test Suite for Sprint 4.1 — Baseline Statistical Models
Verifies Class Prior 1X2, Multinomial Logistic Regression 1X2, and Poisson Expected Goals models.
Audits probability invariants (0 <= P <= 1, sum = 1.0), explicit class mapping, artifact serialization, and experimental status.
"""
import os
import tempfile
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.baselines import ClassPrior1X2Model, MultinomialLogistic1X2Model, PoissonGoalsModel
from app.models.dataset_dto import ModelingRowDTO
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


def _make_dummy_row(target_1x2: int = 0, h_goals: int = 2, a_goals: int = 1, f_vals: list[float] | None = None) -> ModelingRowDTO:
    if f_vals is None:
        f_vals = [1.5, 0.8, 1400.0, 1350.0, 4.0, 5.0]
    f_names = [
        "home_recent_ppg_v1", "away_recent_ppg_v1", "home_elo_v1", "away_elo_v1",
        "home_rest_days_v1", "away_rest_days_v1"
    ]
    return ModelingRowDTO(
        match_id=uuid4(),
        competition_id=uuid4(),
        season_id=uuid4(),
        kickoff_utc=datetime.now(UTC),
        ordered_feature_names=f_names,
        feature_values=f_vals,
        targets={
            "match_result_1x2_v1": target_1x2,
            "home_goals_v1": h_goals,
            "away_goals_v1": a_goals,
            "over_under_2_5_v1": (h_goals + a_goals) >= 3,
            "btts_v1": (h_goals > 0) and (a_goals > 0),
        },
    )


@pytest.mark.unit
def test_class_prior_1x2_model_fitting_and_probabilities():
    # 5 Home wins (0), 3 Draws (1), 2 Away wins (2)
    train_rows = (
        [_make_dummy_row(HOME_WIN_LABEL) for _ in range(5)]
        + [_make_dummy_row(DRAW_LABEL) for _ in range(3)]
        + [_make_dummy_row(AWAY_WIN_LABEL) for _ in range(2)]
    )

    model = ClassPrior1X2Model()
    artifact = model.fit(train_rows)

    assert artifact.model_key == "class_prior_1x2_v1"
    assert artifact.lifecycle_status == "EXPERIMENTAL"

    test_row = _make_dummy_row(0)
    pred = model.predict_raw(test_row)

    assert pred.prob_home_win == 0.5
    assert pred.prob_draw == 0.3
    assert pred.prob_away_win == 0.2
    assert abs((pred.prob_home_win + pred.prob_draw + pred.prob_away_win) - 1.0) < 1e-5
    assert pred.probability_status == "RAW_UNCALIBRATED"


@pytest.mark.unit
def test_multinomial_logistic_1x2_model_fitting_and_probabilities():
    # Construct distinct synthetic training rows
    train_rows = []
    # Strong home team rows -> HOME_WIN
    for i in range(15):
        train_rows.append(_make_dummy_row(HOME_WIN_LABEL, 3, 0, [2.5, 0.5, 1600.0, 1300.0, 6.0, 3.0]))
    # Balanced rows -> DRAW
    for i in range(15):
        train_rows.append(_make_dummy_row(DRAW_LABEL, 1, 1, [1.2, 1.2, 1400.0, 1400.0, 4.0, 4.0]))
    # Strong away team rows -> AWAY_WIN
    for i in range(15):
        train_rows.append(_make_dummy_row(AWAY_WIN_LABEL, 0, 3, [0.4, 2.4, 1300.0, 1600.0, 3.0, 7.0]))

    model = MultinomialLogistic1X2Model()
    artifact = model.fit(train_rows)

    assert artifact.model_key == "multinomial_logistic_1x2_v1"
    assert artifact.lifecycle_status == "EXPERIMENTAL"

    test_row = _make_dummy_row(HOME_WIN_LABEL, 3, 0, [2.5, 0.5, 1600.0, 1300.0, 6.0, 3.0])
    pred = model.predict_raw(test_row)

    # Invariants check
    assert 0.0 <= pred.prob_home_win <= 1.0
    assert 0.0 <= pred.prob_draw <= 1.0
    assert 0.0 <= pred.prob_away_win <= 1.0
    assert abs((pred.prob_home_win + pred.prob_draw + pred.prob_away_win) - 1.0) < 1e-4
    assert pred.probability_status == "RAW_UNCALIBRATED"
    assert pred.lifecycle_status == "EXPERIMENTAL"


@pytest.mark.unit
def test_multinomial_logistic_model_serialization_reload():
    train_rows = [
        _make_dummy_row(HOME_WIN_LABEL, 2, 0, [2.0, 0.8, 1500.0, 1350.0, 5.0, 4.0]),
        _make_dummy_row(DRAW_LABEL, 1, 1, [1.2, 1.2, 1400.0, 1400.0, 4.0, 4.0]),
        _make_dummy_row(AWAY_WIN_LABEL, 0, 2, [0.5, 2.1, 1350.0, 1550.0, 3.0, 6.0]),
    ] * 5

    m1 = MultinomialLogistic1X2Model()
    m1.fit(train_rows)

    test_row = _make_dummy_row(HOME_WIN_LABEL, 2, 0, [2.0, 0.8, 1500.0, 1350.0, 5.0, 4.0])
    pred1 = m1.predict_raw(test_row)

    with tempfile.TemporaryDirectory() as tmpdir:
        art_path = os.path.join(tmpdir, "model_artifact.json")
        m1.save_artifact(art_path)

        m2 = MultinomialLogistic1X2Model()
        m2.load_artifact(art_path)
        pred2 = m2.predict_raw(test_row)

        assert pred1.prob_home_win == pred2.prob_home_win
        assert pred1.prob_draw == pred2.prob_draw
        assert pred1.prob_away_win == pred2.prob_away_win
        assert pred1.model_artifact_fingerprint == pred2.model_artifact_fingerprint


@pytest.mark.unit
def test_poisson_goals_model_fitting_and_score_matrix_derivation():
    train_rows = [
        _make_dummy_row(HOME_WIN_LABEL, 3, 1, [2.2, 0.6, 1550.0, 1350.0, 6.0, 3.0]),
        _make_dummy_row(DRAW_LABEL, 1, 1, [1.1, 1.1, 1400.0, 1400.0, 4.0, 4.0]),
        _make_dummy_row(AWAY_WIN_LABEL, 0, 2, [0.6, 2.0, 1350.0, 1550.0, 3.0, 6.0]),
    ] * 6

    model = PoissonGoalsModel()
    artifact = model.fit(train_rows)

    assert artifact.model_key == "poisson_goals_v1"
    assert artifact.lifecycle_status == "EXPERIMENTAL"

    test_row = _make_dummy_row(HOME_WIN_LABEL, 3, 1, [2.2, 0.6, 1550.0, 1350.0, 6.0, 3.0])
    pred = model.predict_raw(test_row)

    # Expected goals lambda > 0
    assert pred.predicted_home_goals is not None and pred.predicted_home_goals > 0.0
    assert pred.predicted_away_goals is not None and pred.predicted_away_goals > 0.0

    # 1X2 Probabilities sum to 1.0
    assert 0.0 <= pred.prob_home_win <= 1.0
    assert 0.0 <= pred.prob_draw <= 1.0
    assert 0.0 <= pred.prob_away_win <= 1.0
    assert abs((pred.prob_home_win + pred.prob_draw + pred.prob_away_win) - 1.0) < 1e-4

    # Secondary probabilities bounds
    assert 0.0 <= pred.prob_over_25 <= 1.0
    assert abs((pred.prob_over_25 + pred.prob_under_25) - 1.0) < 1e-4
    assert 0.0 <= pred.prob_btts_yes <= 1.0
    assert abs((pred.prob_btts_yes + pred.prob_btts_no) - 1.0) < 1e-4

    assert pred.probability_status == "RAW_UNCALIBRATED"
    assert pred.lifecycle_status == "EXPERIMENTAL"
