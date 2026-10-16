"""
Observational Monitoring & Alerting Engine (Sections 59-63)
Computes label-free and label-aware metrics, validates minimum sample sizes,
and records immutable observational alerts against frozen Phase 5.2 policy thresholds.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.prediction.domain import MonitoringAlertDTO, ShadowEvaluationResult, ShadowPredictionResult

# Frozen Phase 5.2 Thresholds
MIN_CALIBRATION_SAMPLE = 100
MIN_LOG_LOSS_SAMPLE = 50

CRITICAL_PSI_THRESHOLD = 0.20
WARNING_PSI_THRESHOLD = 0.10

WARNING_LL_THRESHOLD = 1.05
CRITICAL_LL_THRESHOLD = 1.10

WARNING_BRIER_THRESHOLD = 0.62
CRITICAL_BRIER_THRESHOLD = 0.65

WARNING_FALLBACK_RATE = 0.05
CRITICAL_FALLBACK_RATE = 0.10


class ShadowMonitoringService:
    """Observational monitoring without automated intervention."""

    def __init__(self) -> None:
        self._alerts: list[MonitoringAlertDTO] = []

    def evaluate_label_free_cohort(
        self, predictions: list[ShadowPredictionResult], cohort_name: str = "LIVE_SHADOW_BATCH"
    ) -> dict[str, Any]:
        n = len(predictions)
        if n == 0:
            return {"status": "EMPTY_COHORT", "sample_size": 0}

        fallback_count = sum(1 for p in predictions if p.fallback_used)
        fallback_rate = fallback_count / n

        mean_h = sum(p.prob_home for p in predictions) / n
        mean_d = sum(p.prob_draw for p in predictions) / n
        mean_a = sum(p.prob_away for p in predictions) / n
        mean_max_p = sum(max(p.prob_home, p.prob_draw, p.prob_away) for p in predictions) / n
        mean_disagreement = sum(p.model_disagreement_value for p in predictions) / n

        metrics = {
            "sample_size": n,
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_rate, 4),
            "mean_prob_home": round(mean_h, 4),
            "mean_prob_draw": round(mean_d, 4),
            "mean_prob_away": round(mean_a, 4),
            "mean_max_prob": round(mean_max_p, 4),
            "mean_disagreement": round(mean_disagreement, 4),
        }

        # Check fallback rate alert
        if fallback_rate >= CRITICAL_FALLBACK_RATE:
            self._record_alert(
                severity="CRITICAL",
                metric="fallback_rate",
                value=fallback_rate,
                threshold=CRITICAL_FALLBACK_RATE,
                window=n,
                cohort=cohort_name,
                reason=f"Fallback rate ({fallback_rate:.2%}) exceeded critical threshold ({CRITICAL_FALLBACK_RATE:.2%}).",
            )
        elif fallback_rate >= WARNING_FALLBACK_RATE:
            self._record_alert(
                severity="WARNING",
                metric="fallback_rate",
                value=fallback_rate,
                threshold=WARNING_FALLBACK_RATE,
                window=n,
                cohort=cohort_name,
                reason=f"Fallback rate ({fallback_rate:.2%}) exceeded warning threshold ({WARNING_FALLBACK_RATE:.2%}).",
            )

        return metrics

    def evaluate_label_aware_cohort(
        self, evaluations: list[ShadowEvaluationResult], cohort_name: str = "EVALUATED_SHADOW_BATCH"
    ) -> dict[str, Any]:
        n = len(evaluations)
        if n < MIN_LOG_LOSS_SAMPLE:
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "sample_size": n,
                "required_sample": MIN_LOG_LOSS_SAMPLE,
            }

        mean_ll = sum(e.log_loss_1x2 for e in evaluations) / n
        mean_brier = sum(e.brier_1x2 for e in evaluations) / n
        mean_btts_ll = sum(e.btts_log_loss for e in evaluations) / n
        mean_ou_ll = sum(e.ou25_log_loss for e in evaluations) / n
        top1_acc = sum(1 for e in evaluations if e.top1_score_hit) / n
        top3_acc = sum(1 for e in evaluations if e.top3_score_hit) / n

        metrics = {
            "sample_size": n,
            "mean_1x2_log_loss": round(mean_ll, 4),
            "mean_1x2_brier": round(mean_brier, 4),
            "mean_btts_log_loss": round(mean_btts_ll, 4),
            "mean_ou25_log_loss": round(mean_ou_ll, 4),
            "top1_score_accuracy": round(top1_acc, 4),
            "top3_score_accuracy": round(top3_acc, 4),
        }

        # Check Log Loss alerts
        if mean_ll >= CRITICAL_LL_THRESHOLD:
            self._record_alert(
                severity="CRITICAL",
                metric="log_loss_1x2",
                value=mean_ll,
                threshold=CRITICAL_LL_THRESHOLD,
                window=n,
                cohort=cohort_name,
                reason=f"Rolling 1X2 Log Loss ({mean_ll:.4f}) exceeded critical threshold ({CRITICAL_LL_THRESHOLD}).",
            )
        elif mean_ll >= WARNING_LL_THRESHOLD:
            self._record_alert(
                severity="WARNING",
                metric="log_loss_1x2",
                value=mean_ll,
                threshold=WARNING_LL_THRESHOLD,
                window=n,
                cohort=cohort_name,
                reason=f"Rolling 1X2 Log Loss ({mean_ll:.4f}) exceeded warning threshold ({WARNING_LL_THRESHOLD}).",
            )

        # Check Brier alerts
        if mean_brier >= CRITICAL_BRIER_THRESHOLD:
            self._record_alert(
                severity="CRITICAL",
                metric="brier_1x2",
                value=mean_brier,
                threshold=CRITICAL_BRIER_THRESHOLD,
                window=n,
                cohort=cohort_name,
                reason=f"Rolling 1X2 Brier ({mean_brier:.4f}) exceeded critical threshold ({CRITICAL_BRIER_THRESHOLD}).",
            )

        return metrics

    def _record_alert(
        self,
        severity: str,
        metric: str,
        value: float,
        threshold: float,
        window: int,
        cohort: str,
        reason: str,
    ) -> MonitoringAlertDTO:
        alert = MonitoringAlertDTO(
            alert_id=uuid4(),
            created_at=datetime.now(UTC),
            severity=severity,
            metric=metric,
            value=round(value, 5),
            threshold=round(threshold, 5),
            window=window,
            model_identity="C1_Multinomial_Logistic_1X2 / M1_Attack_Defense_Poisson",
            prediction_cohort=cohort,
            reason=reason,
        )
        self._alerts.append(alert)
        return alert

    @property
    def alerts(self) -> list[MonitoringAlertDTO]:
        return list(self._alerts)
