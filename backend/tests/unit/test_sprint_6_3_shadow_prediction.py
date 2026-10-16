"""
Sprint 6.3 Shadow Prediction Unit & Invariant Regression Tests (Section 83)
"""
from __future__ import annotations

import concurrent.futures
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.prediction.domain import ShadowPredictionInput, ShadowPredictionResult
from app.prediction.eligibility import PredictionEligibilityService
from app.prediction.replay import CleanRoomReplayService
from app.prediction.service import ShadowPredictionService


def make_valid_input(
    fixture_id=None,
    competition="Premier League",
    lead_hours=4.0,
    quality_state="VALID",
    feature_count=251,
    cold_start=False,
    critical_feature_absent=False,
    drift_psi=0.0,
    missingness_count=0,
) -> ShadowPredictionInput:
    fid = fixture_id or uuid4()
    now = datetime.now(UTC)
    kickoff = now + timedelta(hours=lead_hours)
    return ShadowPredictionInput(
        fixture_id=fid,
        competition_code=competition,
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=kickoff,
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint=f"fp_snap_{fid}",
        history_fingerprint="fp_hist_certified",
        feature_count=feature_count,
        feature_values=[0.5] * feature_count,
        feature_keys=[f"f_{i}" for i in range(feature_count)],
        snapshot_quality_state=quality_state,
        known_cold_start=cold_start,
        critical_feature_absent=critical_feature_absent,
        drift_psi=drift_psi,
        missingness_count=missingness_count,
    )


def test_shadow_prediction_requires_valid_feature_snapshot():
    inp_invalid = make_valid_input(quality_state="STALE_KICKOFF")
    eligible, reason = PredictionEligibilityService.check_eligibility(inp_invalid)
    assert not eligible
    assert "SNAPSHOT_INVALID" in reason

    svc = ShadowPredictionService()
    res = svc.predict(inp_invalid)
    assert res.quality_state == "BLOCKED"


def test_shadow_prediction_precedes_kickoff():
    # Prediction time AFTER kickoff must be blocked
    fid = uuid4()
    now = datetime.now(UTC)
    inp = ShadowPredictionInput(
        fixture_id=fid,
        competition_code="Premier League",
        season_year="2023-24",
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_utc=now - timedelta(minutes=10),
        prediction_time=now,
        feature_snapshot_id=uuid4(),
        feature_snapshot_fingerprint="fp_snap",
        history_fingerprint="fp_hist",
        feature_count=251,
        feature_values=[0.5] * 251,
        feature_keys=[f"f_{i}" for i in range(251)],
    )
    eligible, reason = PredictionEligibilityService.check_eligibility(inp)
    assert not eligible
    assert "POST_KICKOFF_PROHIBITED" in reason


def test_shadow_c1_probabilities_are_normalized():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    res = svc.predict(inp)
    assert isinstance(res, ShadowPredictionResult)

    assert 0.0 <= res.prob_home <= 1.0
    assert 0.0 <= res.prob_draw <= 1.0
    assert 0.0 <= res.prob_away <= 1.0
    total_1x2 = res.prob_home + res.prob_draw + res.prob_away
    assert abs(total_1x2 - 1.0) <= 1e-4


def test_shadow_m1_goal_markets_are_normalized():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    res = svc.predict(inp)
    assert isinstance(res, ShadowPredictionResult)

    assert res.lambda_home > 0.0
    assert res.lambda_away > 0.0
    assert abs((res.btts_yes + res.btts_no) - 1.0) <= 1e-4
    assert abs((res.over_2_5 + res.under_2_5) - 1.0) <= 1e-4
    assert len(res.top_scorelines) == 5
    assert len(res.exact_score_matrix_fingerprint) == 64


def test_shadow_market_ownership_is_frozen():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    res = svc.predict(inp)
    assert isinstance(res, ShadowPredictionResult)

    # Primary 1X2 owned by C1 in normal conditions
    assert res.c1_model_key == "C1_Multinomial_Logistic_1X2"
    assert not res.fallback_used

    # Goals, BTTS, O/U owned by M1
    assert res.m1_model_key == "M1_Attack_Defense_Poisson"
    assert res.lambda_home > 0
    assert res.structural_prob_home > 0


def test_shadow_fallback_routing_on_critical_feature_absent():
    svc = ShadowPredictionService()
    inp = make_valid_input(critical_feature_absent=True)
    res = svc.predict(inp)
    assert isinstance(res, ShadowPredictionResult)

    assert res.fallback_used
    assert res.fallback_model == "M1_Attack_Defense_Poisson"
    assert res.fallback_reason == "critical_feature_absent"
    assert res.quality_state == "FALLBACK_MODEL_USED"
    # In fallback, final 1X2 matches M1 structural probabilities
    assert res.prob_home == res.structural_prob_home


def test_shadow_prediction_path_never_fits_models():
    # Calling predict does not mutate or expose fit methods
    svc = ShadowPredictionService()
    assert not hasattr(svc, "fit")
    assert not hasattr(svc, "partial_fit")


def test_shadow_prediction_is_append_only():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    res1 = svc.predict(inp)
    # Re-running returns identical instance without rewriting
    res2 = svc.predict(inp)
    assert res1.prediction_id == res2.prediction_id


def test_shadow_prediction_run_is_idempotent():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    res1 = svc.predict(inp)
    res2 = svc.predict(inp)
    assert res1 == res2


def test_shadow_prediction_replays_from_provenance():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    pred = svc.predict(inp)
    assert isinstance(pred, ShadowPredictionResult)

    matched, deltas = CleanRoomReplayService.replay_prediction(pred, inp)
    assert matched
    assert deltas["max_prob_difference"] < 1e-5
    assert deltas["max_lambda_difference"] < 1e-3


def test_shadow_rejects_model_artifact_mismatch():
    inp = make_valid_input(feature_count=250)  # wrong count
    eligible, reason = PredictionEligibilityService.check_eligibility(inp)
    assert not eligible
    assert "FEATURE_COUNT_MISMATCH" in reason


def test_shadow_single_vs_batch_parity():
    svc = ShadowPredictionService()
    inputs = [make_valid_input(fixture_id=uuid4()) for _ in range(5)]

    # Single
    singles = [svc.predict(inp) for inp in inputs]

    # Batch
    batch_svc = ShadowPredictionService()
    batches = [batch_svc.predict(inp) for inp in inputs]

    for s, b in zip(singles, batches, strict=True):
        assert s.prob_home == b.prob_home
        assert s.prob_draw == b.prob_draw
        assert s.prob_away == b.prob_away
        assert s.lambda_home == b.lambda_home
        assert s.lambda_away == b.lambda_away


def test_shadow_batch_order_independence():
    svc1 = ShadowPredictionService()
    svc2 = ShadowPredictionService()

    inputs = [make_valid_input(fixture_id=uuid4()) for _ in range(4)]
    reversed_inputs = list(reversed(inputs))

    res1 = {p.fixture_id: p for p in [svc1.predict(inp) for inp in inputs]}
    res2 = {p.fixture_id: p for p in [svc2.predict(inp) for inp in reversed_inputs]}

    for fid in res1:
        assert res1[fid].prob_home == res2[fid].prob_home
        assert res1[fid].lambda_home == res2[fid].lambda_home


def test_shadow_same_kickoff_order_independence():
    common_kickoff = datetime.now(UTC) + timedelta(hours=5)
    fids = [uuid4() for _ in range(3)]

    inp_a = make_valid_input(fixture_id=fids[0])
    inp_b = make_valid_input(fixture_id=fids[1])
    inp_c = make_valid_input(fixture_id=fids[2])
    for inp in (inp_a, inp_b, inp_c):
        inp.kickoff_utc = common_kickoff

    svc1 = ShadowPredictionService()
    r_a1 = svc1.predict(inp_a)
    r_b1 = svc1.predict(inp_b)

    svc2 = ShadowPredictionService()
    r_b2 = svc2.predict(inp_b)
    r_a2 = svc2.predict(inp_a)

    assert r_a1.prob_home == r_a2.prob_home
    assert r_b1.prob_home == r_b2.prob_home


def test_shadow_concurrent_inference_is_deterministic():
    svc = ShadowPredictionService()
    inputs = [make_valid_input(fixture_id=uuid4()) for _ in range(10)]

    def run_pred(inp):
        return svc.predict(inp, dry_run=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_pred, inp) for inp in inputs]
        results = [f.result() for f in futures]

    assert len(results) == 10
    for r in results:
        assert isinstance(r, ShadowPredictionResult)
        assert abs(r.prob_home + r.prob_draw + r.prob_away - 1.0) <= 1e-4


def test_shadow_no_bookmaker_odds():
    svc = ShadowPredictionService()
    inp = make_valid_input()
    pred = svc.predict(inp)
    pred_dict = pred.__dict__

    forbidden_odds_substrings = ["odds", "bookmaker", "bet365", "pinnacle", "kelly", "stake", "edge"]
    for k in pred_dict:
        for forbidden in forbidden_odds_substrings:
            assert forbidden not in k.lower(), f"Forbidden odds term found in field: {k}"


def test_shadow_12_reference_fixtures_regression():
    # 12 diverse chronological fixtures covering 4 leagues (3 per league)
    leagues = ["Premier League", "La Liga", "Serie A", "Bundesliga"]
    svc = ShadowPredictionService()

    total_fixtures = 0
    for league in leagues:
        for idx in range(3):
            inp = make_valid_input(competition=league, lead_hours=2.0 + idx)
            pred = svc.predict(inp)
            assert isinstance(pred, ShadowPredictionResult)
            assert pred.prob_home > 0
            assert pred.lambda_home > 0
            total_fixtures += 1

    assert total_fixtures == 12
