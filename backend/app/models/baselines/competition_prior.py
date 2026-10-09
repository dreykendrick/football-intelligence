"""
Competition-Aware Class Prior 1X2 Baseline Model Implementation
Implements competition-stratified empirical 1X2 outcome frequencies with global fallback.
"""
from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from app.models.base import IPredictionModel, ModelCapabilityEnum, ModelPredictionDTO, TrainedModelArtifact, TrainingWindow
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


class CompetitionPrior1X2Model(IPredictionModel):
    """Competition-Aware Empirical 1X2 Baseline Model."""

    model_key: str = "competition_prior_1x2_v1"
    model_family: str = "COMPETITION_PRIOR"
    version: str = "1.0.0"
    target_key: str = "match_result_1x2_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    def __init__(self, min_competition_samples: int = 10) -> None:
        self.min_competition_samples = min_competition_samples
        self.artifact: TrainedModelArtifact | None = None

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        """Fits empirical 1X2 class prior probabilities per competition with global fallback."""
        if not training_rows:
            raise ValueError("Cannot fit CompetitionPrior1X2Model on empty training rows.")

        total = len(training_rows)
        global_counts = {HOME_WIN_LABEL: 0, DRAW_LABEL: 0, AWAY_WIN_LABEL: 0}
        comp_counts: dict[str, dict[int, int]] = {}

        for r in training_rows:
            cid = str(r.competition_id)
            if cid not in comp_counts:
                comp_counts[cid] = {HOME_WIN_LABEL: 0, DRAW_LABEL: 0, AWAY_WIN_LABEL: 0}

            t = r.targets.get("match_result_1x2_v1")
            if t in (HOME_WIN_LABEL, DRAW_LABEL, AWAY_WIN_LABEL):
                global_counts[t] += 1
                comp_counts[cid][t] += 1

        # Global distribution
        g_tot = sum(global_counts.values()) or 1
        g_ph = round(global_counts[HOME_WIN_LABEL] / g_tot, 6)
        g_pd = round(global_counts[DRAW_LABEL] / g_tot, 6)
        g_pa = round(1.0 - (g_ph + g_pd), 6)

        # Per-competition distributions
        comp_priors: dict[str, dict[str, float]] = {}
        for cid, counts in comp_counts.items():
            c_tot = sum(counts.values())
            if c_tot >= self.min_competition_samples:
                c_ph = round(counts[HOME_WIN_LABEL] / c_tot, 6)
                c_pd = round(counts[DRAW_LABEL] / c_tot, 6)
                c_pa = round(1.0 - (c_ph + c_pd), 6)
                comp_priors[cid] = {
                    "prob_home_win": c_ph,
                    "prob_draw": c_pd,
                    "prob_away_win": c_pa,
                    "sample_size": c_tot,
                }
            else:
                # Insufficient sample -> fallback flag
                comp_priors[cid] = {
                    "prob_home_win": g_ph,
                    "prob_draw": g_pd,
                    "prob_away_win": g_pa,
                    "sample_size": c_tot,
                    "is_fallback": 1.0,
                }

        preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = preprocessor.fit(training_rows)

        if not training_window:
            training_window = TrainingWindow(
                row_count=total,
                modeling_dataset_key=training_rows[0].dataset_release_key,
                modeling_dataset_fingerprint=training_rows[0].dataset_release_fingerprint,
            )

        weights = {
            "global_priors": {
                "prob_home_win": g_ph,
                "prob_draw": g_pd,
                "prob_away_win": g_pa,
                "sample_size": total,
            },
            "competition_priors": comp_priors,
        }

        artifact = TrainedModelArtifact(
            model_key=self.model_key,
            model_family=self.model_family,
            version=self.version,
            target_key=self.target_key,
            feature_set_key=self.feature_set_key,
            lifecycle_status=self.lifecycle_status,
            training_window=training_window,
            preprocessor_artifact=prep_art,
            hyperparameters={"min_competition_samples": self.min_competition_samples},
            weights_payload=weights,
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates competition-stratified empirical 1X2 prediction."""
        if not self.artifact:
            raise RuntimeError("Model has not been fitted or loaded with an artifact.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed: payload has been tampered with.")

        if row.feature_set_key != self.artifact.feature_set_key:
            raise ValueError(f"Feature set mismatch: expected '{self.artifact.feature_set_key}', got '{row.feature_set_key}'")

        weights = self.artifact.weights_payload
        cid = str(row.competition_id)
        comp_priors = weights.get("competition_priors", {})

        if cid in comp_priors:
            p = comp_priors[cid]
        else:
            p = weights.get("global_priors", {"prob_home_win": 0.45, "prob_draw": 0.25, "prob_away_win": 0.30})

        ph = float(p["prob_home_win"])
        pd = float(p["prob_draw"])
        pa = float(p["prob_away_win"])

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=ph,
            prob_draw=pd,
            prob_away_win=pa,
            raw_outputs={"competition_prior_probabilities": [ph, pd, pa], "competition_id": cid},
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns 1X2 competition prior probabilities dict."""
        pred = self.predict_raw(row)
        return {
            "HOME_WIN": pred.prob_home_win,
            "DRAW": pred.prob_draw,
            "AWAY_WIN": pred.prob_away_win,
        }

    def save_artifact(self, filepath: str) -> None:
        """Serializes model artifact JSON to disk."""
        if not self.artifact:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))

    def load_artifact(self, filepath: str) -> None:
        """Deserializes model artifact JSON from disk."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)
        self.min_competition_samples = self.artifact.hyperparameters.get("min_competition_samples", 10)
