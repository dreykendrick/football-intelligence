"""
League Average Poisson Reference Model (M0)
Estimates mean home and away goals per competition and predicts these static lambdas.
Used as the fundamental defensible baseline against which all models are evaluated.
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.models.base import (
    IPredictionModel,
    ModelPredictionDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.engine import GoalDistributionEngine
from app.models.preprocessing import ModelPreprocessor

class LeagueAveragePoissonModel(IPredictionModel):
    model_key = "league_average_poisson_v1"
    model_family = "LEAGUE_AVERAGE_POISSON"

    def __init__(self, version: str = "1.0.0"):
        self.version = version
        self.target_key = "home_away_goals_v1"
        self.feature_set_key = "mvp_a_feature_set_v1"
        self.lifecycle_status = "EXPERIMENTAL"
        self.artifact: TrainedModelArtifact | None = None
        self._distribution_engine = GoalDistributionEngine()

    def fit(self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None) -> TrainedModelArtifact:
        if not training_rows:
            raise ValueError("Cannot fit LeagueAveragePoissonModel on empty training rows.")

        preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = preprocessor.fit(training_rows)

        comp_stats: dict[str, dict[str, Any]] = {}
        global_h_goals = []
        global_a_goals = []

        for r in training_rows:
            c_key = str(r.competition_id)
            if "home_goals_v1" in r.targets and "away_goals_v1" in r.targets:
                h = r.targets["home_goals_v1"]
                a = r.targets["away_goals_v1"]
                if h is not None and a is not None:
                    if c_key not in comp_stats:
                        comp_stats[c_key] = {"home_goals": [], "away_goals": []}
                    comp_stats[c_key]["home_goals"].append(float(h))
                    comp_stats[c_key]["away_goals"].append(float(a))
                    global_h_goals.append(float(h))
                    global_a_goals.append(float(a))

        competitions_payload: dict[str, Any] = {}
        for c_key, stats in comp_stats.items():
            mean_h = sum(stats["home_goals"]) / len(stats["home_goals"]) if stats["home_goals"] else 1.3
            mean_a = sum(stats["away_goals"]) / len(stats["away_goals"]) if stats["away_goals"] else 1.0
            competitions_payload[c_key] = {
                "mean_home_goals": round(mean_h, 4),
                "mean_away_goals": round(mean_a, 4),
                "n_matches": len(stats["home_goals"])
            }

        default_h = sum(global_h_goals) / len(global_h_goals) if global_h_goals else 1.3
        default_a = sum(global_a_goals) / len(global_a_goals) if global_a_goals else 1.0

        weights = {
            "competitions": competitions_payload,
            "default_mean_home_goals": round(default_h, 4),
            "default_mean_away_goals": round(default_a, 4)
        }

        if not training_window:
            training_window = TrainingWindow(
                row_count=len(training_rows),
                modeling_dataset_key=training_rows[0].dataset_release_key,
                modeling_dataset_fingerprint=training_rows[0].dataset_release_fingerprint,
                competitions=list(comp_stats.keys()),
            )

        self.artifact = TrainedModelArtifact(
            model_key=self.model_key,
            model_family=self.model_family,
            version=self.version,
            target_key=self.target_key,
            feature_set_key=self.feature_set_key,
            lifecycle_status=self.lifecycle_status,
            training_window=training_window,
            preprocessor_artifact=prep_art,
            weights_payload=weights,
        )
        self.artifact.artifact_fingerprint = self.artifact.compute_fingerprint()
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        if not self.artifact:
            raise RuntimeError("Model is not fitted.")

        c_key = str(row.competition_id)
        comps = self.artifact.weights_payload.get("competitions", {})
        
        if c_key in comps:
            lambda_home = comps[c_key]["mean_home_goals"]
            lambda_away = comps[c_key]["mean_away_goals"]
            eq = "COMPETITION_AVERAGE"
        else:
            lambda_home = self.artifact.weights_payload.get("default_mean_home_goals", 1.3)
            lambda_away = self.artifact.weights_payload.get("default_mean_away_goals", 1.0)
            eq = "GLOBAL_AVERAGE_FALLBACK"

        matrix = self._distribution_engine.compute_score_matrix(lambda_home, lambda_away)
        one_x_two = self._distribution_engine.derive_1x2(matrix, source_model=self.model_key)
        btts = self._distribution_engine.derive_btts(matrix, lambda_home, lambda_away)
        ou25 = self._distribution_engine.derive_over_under_2_5(matrix, lambda_home, lambda_away)

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=one_x_two.home_win,
            prob_draw=one_x_two.draw,
            prob_away_win=one_x_two.away_win,
            predicted_home_goals=lambda_home,
            predicted_away_goals=lambda_away,
            prob_over_25=ou25.over,
            prob_under_25=ou25.under,
            prob_btts_yes=btts.yes,
            prob_btts_no=btts.no,
            raw_outputs={"evidence_quality": {"quality_level": eq}},
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        pred = self.predict_raw(row)
        return {
            "HOME_WIN": pred.prob_home_win,
            "DRAW": pred.prob_draw,
            "AWAY_WIN": pred.prob_away_win,
        }

    def save_artifact(self, filepath: str) -> None:
        if not self.artifact:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))

    def load_artifact(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)

    def metadata(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key,
            "model_family": self.model_family,
            "version": self.version,
            "target_key": self.target_key,
            "feature_set_key": self.feature_set_key,
            "lifecycle_status": self.lifecycle_status,
        }
