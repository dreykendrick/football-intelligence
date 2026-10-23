"""
Sprint 6.3 Policy Reconciliation & Governance Verification Tests
Validates that Phase 5.2 quality states, precedence hierarchy, fallback rules,
and operational adapter mappings are strictly preserved without deviation.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.prediction.domain import ShadowPredictionInput
from app.prediction.policy import (
    ALL_PHASE5_2_QUALITY_STATES,
    DISAGREEMENT_HIGH_THRESHOLD,
    DISAGREEMENT_LOW_THRESHOLD,
    DRIFT_PSI_CRITICAL_THRESHOLD,
    FALLBACK_1X2_MODEL,
    FROZEN_PHASE5_2_POLICY_HASH,
    MISSINGNESS_DEGRADED_THRESHOLD,
    MISSINGNESS_LIMITED_HISTORY_MIN,
    OPERATIONAL_CRITICAL_FEATURE_ABSENT,
    OPERATIONAL_DEGRADED_IMPUTED,
    OPERATIONAL_HEALTHY,
    OPERATIONAL_UNUSABLE,
    PRIMARY_1X2_MODEL,
    QUALITY_BLOCKED,
    QUALITY_FALLBACK_MODEL_USED,
    QUALITY_FEATURE_DEGRADED,
    QUALITY_HIGH_DRIFT,
    QUALITY_HIGH_MODEL_DISAGREEMENT,
    QUALITY_LIMITED_HISTORY,
    QUALITY_NORMAL,
    QUALITY_PRECEDENCE_RANKS,
    Phase5_2_PolicyEngine,
)
from app.prediction.service import ShadowPredictionService


def make_test_input(**kwargs) -> ShadowPredictionInput:
    now = datetime.now(UTC)
    defaults = {
        "fixture_id": uuid4(),
        "competition_code": "Premier League",
        "season_year": "2024-2025",
        "home_team_id": uuid4(),
        "away_team_id": uuid4(),
        "kickoff_utc": now + timedelta(hours=2),
        "prediction_time": now,
        "feature_snapshot_id": uuid4(),
        "feature_snapshot_fingerprint": "fset_fp_02f8b524_valid",
        "history_fingerprint": "hist_fp_valid",
        "feature_count": 251,
        "feature_values": [0.0] * 251,
        "feature_keys": [f"f_{i}" for i in range(251)],
        "snapshot_quality_state": "VALID",
        "missingness_count": 0,
        "drift_psi": 0.0,
        "known_cold_start": False,
        "critical_feature_absent": False,
    }
    defaults.update(kwargs)
    return ShadowPredictionInput(**defaults)


def test_shadow_quality_states_map_to_frozen_phase5_2_policy():
    """Assert all 7 quality states exist in policy and match frozen Phase 5.2 taxonomy."""
    expected_states = {
        "NORMAL",
        "LIMITED_HISTORY",
        "HIGH_MODEL_DISAGREEMENT",
        "HIGH_DRIFT",
        "FEATURE_DEGRADED",
        "FALLBACK_MODEL_USED",
        "BLOCKED",
    }
    assert set(ALL_PHASE5_2_QUALITY_STATES) == expected_states
    for state in expected_states:
        assert state in QUALITY_PRECEDENCE_RANKS


def test_shadow_fallback_decision_uses_frozen_phase5_2_policy():
    """Assert fallback routing switches 1X2 primary to M1 Poisson only under certified triggers."""
    svc = ShadowPredictionService()

    # Normal input -> C1 is primary
    inp_normal = make_test_input()
    res_normal = svc.predict(inp_normal)
    assert not res_normal.fallback_used
    assert res_normal.fallback_model is None
    assert res_normal.quality_state == QUALITY_NORMAL

    # Critical feature absent -> M1 is fallback
    inp_fallback = make_test_input(critical_feature_absent=True)
    res_fallback = svc.predict(inp_fallback)
    assert res_fallback.fallback_used
    assert res_fallback.fallback_model == FALLBACK_1X2_MODEL
    assert res_fallback.fallback_reason == "critical_feature_absent"
    assert res_fallback.quality_state == QUALITY_FALLBACK_MODEL_USED

    # Cold start -> M1 is fallback
    inp_cold = make_test_input(known_cold_start=True)
    res_cold = svc.predict(inp_cold)
    assert res_cold.fallback_used
    assert res_cold.fallback_model == FALLBACK_1X2_MODEL
    assert res_cold.fallback_reason == "known_cold_start"
    assert res_cold.quality_state == QUALITY_FALLBACK_MODEL_USED


def test_shadow_does_not_duplicate_fallback_thresholds():
    """Assert thresholds match frozen Phase 5.2 specifications exactly."""
    assert DISAGREEMENT_LOW_THRESHOLD == 0.15
    assert DISAGREEMENT_HIGH_THRESHOLD == 0.25
    assert MISSINGNESS_LIMITED_HISTORY_MIN == 1
    assert MISSINGNESS_DEGRADED_THRESHOLD == 5
    assert DRIFT_PSI_CRITICAL_THRESHOLD == 0.20
    assert FROZEN_PHASE5_2_POLICY_HASH == "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"


def test_shadow_blocked_state_matches_frozen_policy():
    """Assert ineligible fixture resolves to BLOCKED state with zero prediction issued."""
    svc = ShadowPredictionService()

    # Ineligible due to invalid snapshot
    inp_unusable = make_test_input(snapshot_quality_state="UNUSABLE")
    blocked = svc.predict(inp_unusable)
    assert blocked.quality_state == QUALITY_BLOCKED
    assert "SNAPSHOT_INVALID" in blocked.reason

    # Ineligible due to post-kickoff
    now = datetime.now(UTC)
    inp_late = make_test_input(prediction_time=now + timedelta(minutes=10), kickoff_utc=now)
    blocked_late = svc.predict(inp_late)
    assert blocked_late.quality_state == QUALITY_BLOCKED
    assert "POST_KICKOFF_PROHIBITED" in blocked_late.reason


def test_shadow_model_disagreement_uses_frozen_threshold():
    """Assert model disagreement calculation uses L1 total variation distance and frozen bands."""
    # Low disagreement (< 0.15)
    d_val, band = Phase5_2_PolicyEngine.compute_model_disagreement(
        0.50, 0.25, 0.25,
        0.52, 0.24, 0.24,
    )
    assert band == "LOW"
    assert d_val < DISAGREEMENT_LOW_THRESHOLD

    # Moderate disagreement (0.15 <= D < 0.25)
    d_val_mod, band_mod = Phase5_2_PolicyEngine.compute_model_disagreement(
        0.60, 0.20, 0.20,
        0.40, 0.30, 0.30,
    )
    assert band_mod == "MODERATE"
    assert DISAGREEMENT_LOW_THRESHOLD <= d_val_mod < DISAGREEMENT_HIGH_THRESHOLD

    # High disagreement (>= 0.25)
    d_val_high, band_high = Phase5_2_PolicyEngine.compute_model_disagreement(
        0.75, 0.15, 0.10,
        0.25, 0.35, 0.40,
    )
    assert band_high == "HIGH"
    assert d_val_high >= DISAGREEMENT_HIGH_THRESHOLD


def test_shadow_quality_precedence_matches_phase5_2():
    """Assert strict frozen quality precedence hierarchy: BLOCKED > FALLBACK > DEGRADED > DRIFT > DISAGREEMENT > LIMITED_HISTORY > NORMAL."""
    ranks = QUALITY_PRECEDENCE_RANKS
    assert ranks[QUALITY_BLOCKED] > ranks[QUALITY_FALLBACK_MODEL_USED]
    assert ranks[QUALITY_FALLBACK_MODEL_USED] > ranks[QUALITY_FEATURE_DEGRADED]
    assert ranks[QUALITY_FEATURE_DEGRADED] > ranks[QUALITY_HIGH_DRIFT]
    assert ranks[QUALITY_HIGH_DRIFT] > ranks[QUALITY_HIGH_MODEL_DISAGREEMENT]
    assert ranks[QUALITY_HIGH_MODEL_DISAGREEMENT] > ranks[QUALITY_LIMITED_HISTORY]
    assert ranks[QUALITY_LIMITED_HISTORY] > ranks[QUALITY_NORMAL]

    # Test conflicting condition 1: Both fallback (critical feature absent) AND high drift active
    # Precedence mandates FALLBACK_MODEL_USED wins
    res1 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=True,
        known_cold_start=False,
        missingness_count=0,
        drift_psi=0.35,
        disagreement_value=0.10,
        disagreement_band="LOW",
    )
    assert res1.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert res1.fallback_applied is True

    # Test conflicting condition 2: Both feature degraded (missingness > 5) AND high disagreement active
    # Precedence mandates FEATURE_DEGRADED wins
    res2 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=8,
        drift_psi=0.05,
        disagreement_value=0.32,
        disagreement_band="HIGH",
    )
    assert res2.quality_state == QUALITY_FEATURE_DEGRADED
    assert res2.fallback_applied is False
    assert res2.effective_model_1x2 == PRIMARY_1X2_MODEL

    # Test conflicting condition 3: Both high drift AND high disagreement active
    # Precedence mandates HIGH_DRIFT wins
    res3 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=0,
        drift_psi=0.25,
        disagreement_value=0.30,
        disagreement_band="HIGH",
    )
    assert res3.quality_state == QUALITY_HIGH_DRIFT
    assert res3.fallback_applied is False


def test_shadow_prediction_persists_phase5_2_policy_hash():
    """Assert all shadow prediction results bind and persist the frozen Phase 5.2 policy hash."""
    svc = ShadowPredictionService()
    inp = make_test_input()
    res = svc.predict(inp)
    assert res.phase5_2_policy_hash == FROZEN_PHASE5_2_POLICY_HASH
    assert res.phase5_2_policy_hash == "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"


def test_shadow_operational_aliases_map_deterministically():
    """Assert deterministic mapping from adapter operational categories into frozen Phase 5.2 quality states."""
    # UNUSABLE -> BLOCKED
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_UNUSABLE
    ) == QUALITY_BLOCKED

    # CRITICAL_FEATURE_ABSENT -> FALLBACK_MODEL_USED
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_CRITICAL_FEATURE_ABSENT
    ) == QUALITY_FALLBACK_MODEL_USED

    # DEGRADED_IMPUTED with minor missingness (<= 5) -> LIMITED_HISTORY
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_DEGRADED_IMPUTED, missingness_count=3
    ) == QUALITY_LIMITED_HISTORY

    # DEGRADED_IMPUTED with high missingness (> 5) -> FEATURE_DEGRADED
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_DEGRADED_IMPUTED, missingness_count=7
    ) == QUALITY_FEATURE_DEGRADED

    # HEALTHY without divergence -> NORMAL
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_HEALTHY, disagreement_band="LOW"
    ) == QUALITY_NORMAL

    # HEALTHY with high model disagreement -> HIGH_MODEL_DISAGREEMENT
    assert Phase5_2_PolicyEngine.map_operational_category_to_frozen_policy(
        OPERATIONAL_HEALTHY, disagreement_band="HIGH"
    ) == QUALITY_HIGH_MODEL_DISAGREEMENT


# --- Section 25-27 Forensic Reconciliation & Boundary Tests ---

def test_phase5_2_true_cold_start_behavior():
    """Assert true cold start (unseen club / zero history) routes to M1 fallback."""
    svc = ShadowPredictionService()
    inp = make_test_input(known_cold_start=True, missingness_count=0)
    res = svc.predict(inp)
    assert res.fallback_used is True
    assert res.fallback_model == FALLBACK_1X2_MODEL
    assert res.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert "known_cold_start" in res.quality_reasons


def test_phase5_2_limited_history_behavior():
    """Assert limited history (promoted/new team with sparse history 1..5) uses C1 with imputation."""
    svc = ShadowPredictionService()
    inp = make_test_input(known_cold_start=False, missingness_count=3)
    res = svc.predict(inp)
    assert res.fallback_used is False
    assert res.fallback_model is None
    assert res.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res.quality_state == QUALITY_LIMITED_HISTORY
    assert "limited_history_missingness" in res.quality_reasons


def test_phase5_2_critical_feature_absent_behavior():
    """Assert critical feature absence routes to M1 fallback."""
    svc = ShadowPredictionService()
    inp = make_test_input(critical_feature_absent=True)
    res = svc.predict(inp)
    assert res.fallback_used is True
    assert res.fallback_model == FALLBACK_1X2_MODEL
    assert res.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert "critical_feature_absent" in res.quality_reasons


def test_phase5_2_missingness_boundary_zero():
    """Boundary test: 0 missing features -> NORMAL (C1 primary)."""
    res = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=0,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res.quality_state == QUALITY_NORMAL
    assert res.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res.fallback_applied is False


def test_phase5_2_missingness_boundary_one():
    """Boundary test: 1 missing feature -> LIMITED_HISTORY (C1 primary)."""
    res = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=1,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res.quality_state == QUALITY_LIMITED_HISTORY
    assert res.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res.fallback_applied is False


def test_phase5_2_missingness_boundary_five():
    """Boundary test: 5 missing features -> LIMITED_HISTORY (C1 primary, upper boundary)."""
    res = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=5,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res.quality_state == QUALITY_LIMITED_HISTORY
    assert res.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res.fallback_applied is False


def test_phase5_2_missingness_boundary_six():
    """Boundary test: 6 missing features -> FEATURE_DEGRADED (C1 primary, transition boundary)."""
    res = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=False,
        missingness_count=6,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res.quality_state == QUALITY_FEATURE_DEGRADED
    assert res.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res.fallback_applied is False


def test_phase5_2_cold_start_and_missingness_precedence():
    """Assert cold start (precedence 6) overrides both limited history (2) and feature degraded (5)."""
    # Cold start with minor missingness (count=2)
    res_minor = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=True,
        missingness_count=2,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res_minor.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert res_minor.fallback_applied is True
    assert res_minor.effective_model_1x2 == FALLBACK_1X2_MODEL

    # Cold start with high missingness (count=10)
    res_major = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True,
        eligibility_reason=None,
        critical_feature_absent=False,
        known_cold_start=True,
        missingness_count=10,
        drift_psi=0.0,
        disagreement_value=0.05,
        disagreement_band="LOW",
    )
    assert res_major.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert res_major.fallback_applied is True
    assert res_major.effective_model_1x2 == FALLBACK_1X2_MODEL


def test_phase5_2_fallback_model_is_m1_only_when_policy_requires():
    """Assert M1 is effective 1X2 ONLY when fallback is applied."""
    svc = ShadowPredictionService()

    # Normal fixture -> C1 is effective 1X2 (fallback_used is False)
    res_normal = svc.predict(make_test_input())
    assert res_normal.effective_model_1x2 == PRIMARY_1X2_MODEL
    assert res_normal.fallback_used is False
    assert res_normal.fallback_model is None

    # Cold start -> M1 is effective 1X2 (fallback_used is True, prob_home matches structural)
    res_cold = svc.predict(make_test_input(known_cold_start=True))
    assert res_cold.effective_model_1x2 == FALLBACK_1X2_MODEL
    assert res_cold.fallback_used is True
    assert res_cold.fallback_model == FALLBACK_1X2_MODEL
    assert res_cold.prob_home == res_cold.structural_prob_home

    # Critical feature absent -> M1 is effective 1X2 (fallback_used is True, prob_home matches structural)
    res_crit = svc.predict(make_test_input(critical_feature_absent=True))
    assert res_crit.effective_model_1x2 == FALLBACK_1X2_MODEL
    assert res_crit.fallback_used is True
    assert res_crit.fallback_model == FALLBACK_1X2_MODEL
    assert res_crit.prob_home == res_crit.structural_prob_home


def test_phase5_2_policy_hash_is_persisted():
    """Assert policy hash matches frozen Phase 5.2 hash on all predictions."""
    svc = ShadowPredictionService()
    res = svc.predict(make_test_input())
    assert res.phase5_2_policy_hash == "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"


def test_phase5_2_all_precedence_combinations():
    """Assert exact precedence ordering across all multi-condition conflict combinations."""
    # 1. Cold start + High drift -> Fallback wins
    r1 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True, eligibility_reason=None, critical_feature_absent=False,
        known_cold_start=True, missingness_count=0, drift_psi=0.40,
        disagreement_value=0.05, disagreement_band="LOW"
    )
    assert r1.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert r1.fallback_applied is True

    # 2. Cold start + High disagreement -> Fallback wins
    r2 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True, eligibility_reason=None, critical_feature_absent=False,
        known_cold_start=True, missingness_count=0, drift_psi=0.0,
        disagreement_value=0.45, disagreement_band="HIGH"
    )
    assert r2.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert r2.fallback_applied is True

    # 3. Critical missing + High drift -> Fallback wins
    r3 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True, eligibility_reason=None, critical_feature_absent=True,
        known_cold_start=False, missingness_count=0, drift_psi=0.40,
        disagreement_value=0.05, disagreement_band="LOW"
    )
    assert r3.quality_state == QUALITY_FALLBACK_MODEL_USED
    assert r3.fallback_applied is True

    # 4. Feature degraded + High disagreement -> Feature degraded wins
    r4 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=True, eligibility_reason=None, critical_feature_absent=False,
        known_cold_start=False, missingness_count=8, drift_psi=0.05,
        disagreement_value=0.40, disagreement_band="HIGH"
    )
    assert r4.quality_state == QUALITY_FEATURE_DEGRADED
    assert r4.fallback_applied is False
    assert r4.effective_model_1x2 == PRIMARY_1X2_MODEL

    # 5. Blocked + everything else active -> Blocked wins
    r5 = Phase5_2_PolicyEngine.evaluate(
        is_eligible=False, eligibility_reason="POST_KICKOFF", critical_feature_absent=True,
        known_cold_start=True, missingness_count=20, drift_psi=0.90,
        disagreement_value=0.80, disagreement_band="HIGH"
    )
    assert r5.quality_state == QUALITY_BLOCKED
    assert r5.effective_model_1x2 == "NONE"
