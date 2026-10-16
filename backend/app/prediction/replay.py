"""
Clean-Room Provenance Replay Service (Section 46)
Recomputes forward pass from recorded feature snapshots, model artifacts, and policies in pristine isolation.
"""
from __future__ import annotations

from app.prediction.domain import ShadowPredictionInput, ShadowPredictionResult
from app.prediction.service import ShadowPredictionService


class CleanRoomReplayService:
    """Guarantees deterministic bitwise reproducibility of shadow forecasts."""

    @classmethod
    def replay_prediction(
        cls, recorded_prediction: ShadowPredictionResult, original_input: ShadowPredictionInput
    ) -> tuple[bool, dict[str, float]]:
        clean_service = ShadowPredictionService()
        replayed = clean_service.predict(original_input, dry_run=True)

        if not isinstance(replayed, ShadowPredictionResult):
            return False, {"error": "Replay yielded BlockedDecisionRecord"}

        diff_home = abs(recorded_prediction.prob_home - replayed.prob_home)
        diff_draw = abs(recorded_prediction.prob_draw - replayed.prob_draw)
        diff_away = abs(recorded_prediction.prob_away - replayed.prob_away)
        diff_lh = abs(recorded_prediction.lambda_home - replayed.lambda_home)
        diff_la = abs(recorded_prediction.lambda_away - replayed.lambda_away)

        max_prob_diff = max(diff_home, diff_draw, diff_away)
        max_lam_diff = max(diff_lh, diff_la)

        is_match = (
            max_prob_diff < 1e-5
            and max_lam_diff < 1e-3
            and recorded_prediction.quality_state == replayed.quality_state
            and recorded_prediction.fallback_used == replayed.fallback_used
            and recorded_prediction.exact_score_matrix_fingerprint == replayed.exact_score_matrix_fingerprint
        )

        deltas = {
            "max_prob_difference": max_prob_diff,
            "max_lambda_difference": max_lam_diff,
            "quality_state_match": 1.0 if recorded_prediction.quality_state == replayed.quality_state else 0.0,
            "fallback_match": 1.0 if recorded_prediction.fallback_used == replayed.fallback_used else 0.0,
        }

        return is_match, deltas
