"""
Probability Engine Router & Capability Enforcement Architecture
Provides high-level prediction routing, capability verification, and unified DTO construction.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.base import (
    IPredictionModel,
    MatchProbabilityPrediction,
    ModelCapabilityEnum,
    ModelPredictionDTO,
    OneXTwoProbabilityDTO,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.engine import GoalDistributionEngine, ProbabilityInvariantValidator


class ProbabilityEngine:
    """
    Central router service managing prediction execution, model capabilities validation,
    and unified MatchProbabilityPrediction generation.
    """

    def __init__(self, distribution_engine: GoalDistributionEngine | None = None) -> None:
        self.distribution_engine = distribution_engine or GoalDistributionEngine()

    def predict(
        self, model: IPredictionModel, row: ModelingRowDTO, max_exact_scores: int = 5
    ) -> MatchProbabilityPrediction:
        """
        Executes prediction for target row, validating capabilities, preprocessor isolation,
        and artifact integrity. Returns unified MatchProbabilityPrediction.
        """
        if not model.artifact:
            raise RuntimeError(f"Model '{model.model_key}' must be fitted or loaded before prediction.")

        # 1. Verify artifact integrity
        if not model.artifact.verify_integrity():
            raise ValueError(f"Artifact verification failed for model '{model.model_key}': payload tampered.")

        # 2. Verify feature set key compatibility
        if row.feature_set_key != model.feature_set_key:
            raise ValueError(
                f"Feature set mismatch for model '{model.model_key}': expected '{model.feature_set_key}', got '{row.feature_set_key}'"
            )

        # 3. Generate raw prediction from model
        raw_pred: ModelPredictionDTO = model.predict_raw(row)

        caps = model.capabilities

        # Build 1X2 DTO
        one_x_two_dto = OneXTwoProbabilityDTO(
            home_win=raw_pred.prob_home_win,
            draw=raw_pred.prob_draw,
            away_win=raw_pred.prob_away_win,
            probability_status=raw_pred.probability_status,
            source_model=model.model_key,
        )

        # If model supports EXPECTED_GOALS, route through GoalDistributionEngine
        if ModelCapabilityEnum.EXPECTED_GOALS in caps and raw_pred.predicted_home_goals is not None and raw_pred.predicted_away_goals is not None:
            lh = raw_pred.predicted_home_goals
            la = raw_pred.predicted_away_goals

            matrix = self.distribution_engine.compute_score_matrix(lh, la)
            btts_dto = self.distribution_engine.derive_btts(matrix, lh, la)
            ou_dto = self.distribution_engine.derive_over_under_2_5(matrix, lh, la)
            top_scores = self.distribution_engine.top_exact_scores(matrix, n=max_exact_scores)
            mls = self.distribution_engine.most_likely_score(matrix)

            dist_meta = {
                "distribution_family": matrix.distribution_family,
                "assumptions": matrix.assumptions,
                "retained_probability_mass": matrix.retained_probability_mass,
                "tail_probability_mass": matrix.tail_probability_mass,
                "normalized": matrix.normalized,
            }

            pred = MatchProbabilityPrediction(
                match_id=row.match_id,
                model_key=model.model_key,
                model_version=model.version,
                model_artifact_fingerprint=model.artifact.artifact_fingerprint,
                feature_set_key=row.feature_set_key,
                feature_snapshot_fingerprint=row.feature_set_fingerprint,
                lambda_home=lh,
                lambda_away=la,
                one_x_two=one_x_two_dto,
                btts=btts_dto,
                over_under_2_5=ou_dto,
                most_likely_score=mls,
                top_exact_scores=top_scores,
                distribution_metadata=dist_meta,
                probability_status="RAW_UNCALIBRATED",
                lifecycle_status=model.lifecycle_status,
                prediction_horizon=raw_pred.prediction_horizon,
            )
            ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)
            return pred

        # Non-goal models (1X2 only)
        pred = MatchProbabilityPrediction(
            match_id=row.match_id,
            model_key=model.model_key,
            model_version=model.version,
            model_artifact_fingerprint=model.artifact.artifact_fingerprint,
            feature_set_key=row.feature_set_key,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            one_x_two=one_x_two_dto,
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=model.lifecycle_status,
            prediction_horizon=raw_pred.prediction_horizon,
        )
        ProbabilityInvariantValidator.validate_goal_prediction_consistency(pred)
        return pred

    def assert_capability(self, model: IPredictionModel, capability: ModelCapabilityEnum) -> None:
        """Asserts that model supports requested capability, raising UNSUPPORTED_MODEL_CAPABILITY error on mismatch."""
        if capability not in model.capabilities:
            raise ValueError(
                f"UNSUPPORTED_MODEL_CAPABILITY: Model '{model.model_key}' does not support capability '{capability.value}'"
            )
