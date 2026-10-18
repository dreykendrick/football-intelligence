"""
Phase 5.2 Canonical Quality & Fallback Policy Engine
Single source of truth for Phase 5.2 quality states, precedence hierarchy,
fallback triggers, model disagreement thresholds, and deterministic adapter mapping.
"""
from __future__ import annotations

from dataclasses import dataclass

# Frozen Phase 5.2 Policy Manifest Identity
FROZEN_PHASE5_2_POLICY_HASH = "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"

# Frozen Phase 5.2 Quality States
QUALITY_NORMAL = "NORMAL"
QUALITY_LIMITED_HISTORY = "LIMITED_HISTORY"
QUALITY_HIGH_MODEL_DISAGREEMENT = "HIGH_MODEL_DISAGREEMENT"
QUALITY_HIGH_DRIFT = "HIGH_DRIFT"
QUALITY_FEATURE_DEGRADED = "FEATURE_DEGRADED"
QUALITY_FALLBACK_MODEL_USED = "FALLBACK_MODEL_USED"
QUALITY_BLOCKED = "BLOCKED"

ALL_PHASE5_2_QUALITY_STATES = (
    QUALITY_NORMAL,
    QUALITY_LIMITED_HISTORY,
    QUALITY_HIGH_MODEL_DISAGREEMENT,
    QUALITY_HIGH_DRIFT,
    QUALITY_FEATURE_DEGRADED,
    QUALITY_FALLBACK_MODEL_USED,
    QUALITY_BLOCKED,
)

# Quality Precedence Order (Descending Severity: 7 highest, 1 lowest)
# BLOCKED > FALLBACK_MODEL_USED > FEATURE_DEGRADED > HIGH_DRIFT > HIGH_MODEL_DISAGREEMENT > LIMITED_HISTORY > NORMAL
QUALITY_PRECEDENCE_RANKS: dict[str, int] = {
    QUALITY_BLOCKED: 7,
    QUALITY_FALLBACK_MODEL_USED: 6,
    QUALITY_FEATURE_DEGRADED: 5,
    QUALITY_HIGH_DRIFT: 4,
    QUALITY_HIGH_MODEL_DISAGREEMENT: 3,
    QUALITY_LIMITED_HISTORY: 2,
    QUALITY_NORMAL: 1,
}

# Frozen Phase 5.2 Policy Thresholds
DISAGREEMENT_LOW_THRESHOLD = 0.15
DISAGREEMENT_HIGH_THRESHOLD = 0.25

MISSINGNESS_LIMITED_HISTORY_MIN = 1
MISSINGNESS_DEGRADED_THRESHOLD = 5

DRIFT_PSI_CRITICAL_THRESHOLD = 0.20
DRIFT_PSI_WARNING_THRESHOLD = 0.10

# Frozen Model Keys
PRIMARY_1X2_MODEL = "C1_Multinomial_Logistic_1X2"
FALLBACK_1X2_MODEL = "M1_Attack_Defense_Poisson"

# Sprint 6.3 Operational / Diagnostic Categories (Adapter Layer)
OPERATIONAL_HEALTHY = "HEALTHY"
OPERATIONAL_DEGRADED_IMPUTED = "DEGRADED_IMPUTED"
OPERATIONAL_CRITICAL_FEATURE_ABSENT = "CRITICAL_FEATURE_ABSENT"
OPERATIONAL_UNUSABLE = "UNUSABLE"


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Result of Phase 5.2 policy evaluation."""
    quality_state: str
    effective_model_1x2: str
    fallback_applied: bool
    fallback_model: str | None
    fallback_reason: str | None
    quality_reasons: list[str]
    disagreement_value: float
    disagreement_band: str
    policy_hash: str = FROZEN_PHASE5_2_POLICY_HASH


class Phase5_2_PolicyEngine:
    """
    Canonical evaluator for Phase 5.2 quality states, fallback routing, and precedence.
    Guarantees no new fallback rules or retuned thresholds exist outside certified policy.
    """

    @staticmethod
    def compute_model_disagreement(
        c1_prob_h: float,
        c1_prob_d: float,
        c1_prob_a: float,
        m1_prob_h: float,
        m1_prob_d: float,
        m1_prob_a: float,
    ) -> tuple[float, str]:
        """
        Total variation distance between C1 and M1 probability distributions:
        D_1X2 = 0.5 * (|p_c1_h - p_m1_h| + |p_c1_d - p_m1_d| + |p_c1_a - p_m1_a|)
        """
        disagreement = 0.5 * (
            abs(c1_prob_h - m1_prob_h) + abs(c1_prob_d - m1_prob_d) + abs(c1_prob_a - m1_prob_a)
        )
        if disagreement < DISAGREEMENT_LOW_THRESHOLD:
            band = "LOW"
        elif disagreement < DISAGREEMENT_HIGH_THRESHOLD:
            band = "MODERATE"
        else:
            band = "HIGH"
        return round(disagreement, 5), band

    @classmethod
    def evaluate(
        cls,
        *,
        is_eligible: bool,
        eligibility_reason: str | None,
        critical_feature_absent: bool,
        known_cold_start: bool,
        missingness_count: int,
        drift_psi: float,
        disagreement_value: float,
        disagreement_band: str,
    ) -> PolicyEvaluationResult:
        """
        Executes frozen Phase 5.2 quality precedence and fallback decision.
        Strict precedence:
        BLOCKED > FALLBACK_MODEL_USED > FEATURE_DEGRADED > HIGH_DRIFT > HIGH_MODEL_DISAGREEMENT > LIMITED_HISTORY > NORMAL
        """
        quality_reasons: list[str] = []

        # 1. Precedence Level 7: BLOCKED
        if not is_eligible:
            reason = eligibility_reason or "INELIGIBLE"
            quality_reasons.append(reason)
            return PolicyEvaluationResult(
                quality_state=QUALITY_BLOCKED,
                effective_model_1x2="NONE",
                fallback_applied=False,
                fallback_model=None,
                fallback_reason=reason,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 2. Precedence Level 6: FALLBACK_MODEL_USED
        if critical_feature_absent or known_cold_start:
            fallback_reason = "critical_feature_absent" if critical_feature_absent else "known_cold_start"
            quality_reasons.append(fallback_reason)
            return PolicyEvaluationResult(
                quality_state=QUALITY_FALLBACK_MODEL_USED,
                effective_model_1x2=FALLBACK_1X2_MODEL,
                fallback_applied=True,
                fallback_model=FALLBACK_1X2_MODEL,
                fallback_reason=fallback_reason,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 3. Precedence Level 5: FEATURE_DEGRADED
        if missingness_count > MISSINGNESS_DEGRADED_THRESHOLD:
            quality_reasons.append(f"high_missingness_{missingness_count}")
            return PolicyEvaluationResult(
                quality_state=QUALITY_FEATURE_DEGRADED,
                effective_model_1x2=PRIMARY_1X2_MODEL,
                fallback_applied=False,
                fallback_model=None,
                fallback_reason=None,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 4. Precedence Level 4: HIGH_DRIFT
        if drift_psi >= DRIFT_PSI_CRITICAL_THRESHOLD:
            quality_reasons.append(f"critical_drift_psi_{drift_psi:.3f}")
            return PolicyEvaluationResult(
                quality_state=QUALITY_HIGH_DRIFT,
                effective_model_1x2=PRIMARY_1X2_MODEL,
                fallback_applied=False,
                fallback_model=None,
                fallback_reason=None,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 5. Precedence Level 3: HIGH_MODEL_DISAGREEMENT
        if disagreement_band == "HIGH":
            quality_reasons.append(f"high_disagreement_{disagreement_value:.4f}")
            return PolicyEvaluationResult(
                quality_state=QUALITY_HIGH_MODEL_DISAGREEMENT,
                effective_model_1x2=PRIMARY_1X2_MODEL,
                fallback_applied=False,
                fallback_model=None,
                fallback_reason=None,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 6. Precedence Level 2: LIMITED_HISTORY
        if missingness_count >= MISSINGNESS_LIMITED_HISTORY_MIN:
            quality_reasons.append("limited_history_missingness")
            return PolicyEvaluationResult(
                quality_state=QUALITY_LIMITED_HISTORY,
                effective_model_1x2=PRIMARY_1X2_MODEL,
                fallback_applied=False,
                fallback_model=None,
                fallback_reason=None,
                quality_reasons=quality_reasons,
                disagreement_value=disagreement_value,
                disagreement_band=disagreement_band,
            )

        # 7. Precedence Level 1: NORMAL
        quality_reasons.append("normal_healthy_features")
        return PolicyEvaluationResult(
            quality_state=QUALITY_NORMAL,
            effective_model_1x2=PRIMARY_1X2_MODEL,
            fallback_applied=False,
            fallback_model=None,
            fallback_reason=None,
            quality_reasons=quality_reasons,
            disagreement_value=disagreement_value,
            disagreement_band=disagreement_band,
        )

    @classmethod
    def map_operational_category_to_frozen_policy(
        cls,
        operational_category: str,
        *,
        missingness_count: int = 0,
        disagreement_band: str = "LOW",
    ) -> str:
        """
        Deterministic mapping from adapter-layer operational diagnostic categories
        into frozen Phase 5.2 quality states.
        """
        if operational_category == OPERATIONAL_UNUSABLE:
            return QUALITY_BLOCKED

        if operational_category == OPERATIONAL_CRITICAL_FEATURE_ABSENT:
            return QUALITY_FALLBACK_MODEL_USED

        if operational_category == OPERATIONAL_DEGRADED_IMPUTED:
            if missingness_count > MISSINGNESS_DEGRADED_THRESHOLD:
                return QUALITY_FEATURE_DEGRADED
            return QUALITY_LIMITED_HISTORY

        if operational_category == OPERATIONAL_HEALTHY:
            if disagreement_band == "HIGH":
                return QUALITY_HIGH_MODEL_DISAGREEMENT
            return QUALITY_NORMAL

        raise ValueError(f"Unknown operational diagnostic category: '{operational_category}'")
