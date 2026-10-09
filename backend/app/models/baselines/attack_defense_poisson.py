"""
Attack / Defense Poisson Reference Model Implementation
Implements a regularized, identifiable, team-specific log-linear Poisson model
estimating competition goal baselines (mu_c), home advantage (h_c), team attack strengths (alpha_t),
and team defensive strengths (delta_t) from historical completed match scores.
Integrates with the certified Phase 4 Probability Engine and GoalDistributionEngine.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any
from uuid import UUID
import numpy as np
from scipy.optimize import minimize

from app.models.base import (
    IPredictionModel,
    ModelCapabilityEnum,
    ModelPredictionDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.engine import GoalDistributionEngine
from app.models.preprocessing import ModelPreprocessor


def _fit_competition_poisson(
    home_indices: np.ndarray,
    away_indices: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    num_teams: int,
    gamma: float = 0.2,
    max_iter: int = 500,
    tol: float = 1e-6,
    match_weights: np.ndarray | None = None,
    optimize_rho: bool = False,
) -> dict[str, Any]:
    n_params = 2 + 2 * num_teams + (1 if optimize_rho else 0)

    # Initialize parameters
    if match_weights is not None:
        mean_home = float(np.average(home_goals, weights=match_weights)) if len(home_goals) > 0 else 1.3
        mean_away = float(np.average(away_goals, weights=match_weights)) if len(away_goals) > 0 else 1.0
    else:
        mean_home = float(np.mean(home_goals)) if len(home_goals) > 0 else 1.3
        mean_away = float(np.mean(away_goals)) if len(away_goals) > 0 else 1.0
        
    init_mu = float(np.log(max(0.2, mean_away)))
    init_h = float(np.log(max(0.2, mean_home)) - init_mu)

    theta0 = np.zeros(n_params, dtype=np.float64)
    theta0[0] = init_mu
    theta0[1] = init_h
    
    if match_weights is None:
        w = np.ones_like(home_goals, dtype=np.float64)
    else:
        w = match_weights
        
    mask_00 = (home_goals == 0) & (away_goals == 0)
    mask_01 = (home_goals == 0) & (away_goals == 1)
    mask_10 = (home_goals == 1) & (away_goals == 0)
    mask_11 = (home_goals == 1) & (away_goals == 1)

    def objective_and_grad(theta: np.ndarray) -> tuple[float, np.ndarray]:
        mu = theta[0]
        h = theta[1]
        alpha = theta[2 : 2 + num_teams]
        delta = theta[2 + num_teams : 2 + 2 * num_teams]
        rho = theta[-1] if optimize_rho else 0.0

        log_lh = np.clip(mu + h + alpha[home_indices] - delta[away_indices], -10.0, 10.0)
        log_la = np.clip(mu + alpha[away_indices] - delta[home_indices], -10.0, 10.0)

        lh = np.exp(log_lh)
        la = np.exp(log_la)

        # Baseline Poisson terms
        nll_base = lh - home_goals * log_lh + la - away_goals * log_la
        
        # Dixon-Coles terms
        tau = np.ones_like(lh)
        dtau_drho = np.zeros_like(lh)
        dtau_dlh = np.zeros_like(lh)
        dtau_dla = np.zeros_like(lh)
        
        if optimize_rho or abs(rho) > 1e-6:
            tau[mask_00] = 1.0 - lh[mask_00] * la[mask_00] * rho
            dtau_drho[mask_00] = -lh[mask_00] * la[mask_00]
            dtau_dlh[mask_00] = -la[mask_00] * rho
            dtau_dla[mask_00] = -lh[mask_00] * rho
            
            tau[mask_01] = 1.0 + lh[mask_01] * rho
            dtau_drho[mask_01] = lh[mask_01]
            dtau_dlh[mask_01] = rho
            
            tau[mask_10] = 1.0 + la[mask_10] * rho
            dtau_drho[mask_10] = la[mask_10]
            dtau_dla[mask_10] = rho
            
            tau[mask_11] = 1.0 - rho
            dtau_drho[mask_11] = -1.0
            
            tau = np.clip(tau, 1e-10, None)
            
        nll_terms = w * (nll_base - np.log(tau))
        nll = float(np.sum(nll_terms))

        reg_penalty = float(0.5 * gamma * (np.sum(alpha**2) + np.sum(delta**2)))
        total_loss = nll + reg_penalty

        r_h = w * (lh - home_goals - (1.0 / tau) * dtau_dlh * lh)
        r_a = w * (la - away_goals - (1.0 / tau) * dtau_dla * la)

        grad = np.zeros_like(theta)
        grad[0] = np.sum(r_h + r_a)
        grad[1] = np.sum(r_h)

        np.add.at(grad[2 : 2 + num_teams], home_indices, r_h)
        np.add.at(grad[2 : 2 + num_teams], away_indices, r_a)
        grad[2 : 2 + num_teams] += gamma * alpha

        np.add.at(grad[2 + num_teams : 2 + 2 * num_teams], away_indices, -r_h)
        np.add.at(grad[2 + num_teams : 2 + 2 * num_teams], home_indices, -r_a)
        grad[2 + num_teams : 2 + 2 * num_teams] += gamma * delta
        
        if optimize_rho:
            grad[-1] = np.sum(w * (-1.0 / tau) * dtau_drho)

        return total_loss, grad

    bounds = [(None, None)] * (2 + 2 * num_teams)
    if optimize_rho:
        bounds.append((-0.2, 0.2)) # Dixon-Coles rho bounds

    res = minimize(
        objective_and_grad,
        theta0,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": max_iter, "gtol": tol, "ftol": tol * 1e-3},
    )

    opt_theta = res.x
    mu_raw = float(opt_theta[0])
    h_raw = float(opt_theta[1])
    alpha_raw = opt_theta[2 : 2 + num_teams].copy()
    delta_raw = opt_theta[2 + num_teams : 2 + 2 * num_teams].copy()
    rho_val = float(opt_theta[-1]) if optimize_rho else 0.0

    # Identifiability zero-sum centering
    mean_alpha = float(np.mean(alpha_raw))
    mean_delta = float(np.mean(delta_raw))

    alpha_centered = alpha_raw - mean_alpha
    delta_centered = delta_raw - mean_delta
    if len(alpha_centered) > 1:
        alpha_centered[-1] = -float(np.sum(alpha_centered[:-1]))
    if len(delta_centered) > 1:
        delta_centered[-1] = -float(np.sum(delta_centered[:-1]))
    mu_centered = mu_raw + mean_alpha - mean_delta
    h_centered = h_raw

    # Verify zero-sum constraint residuals
    residual_alpha = float(abs(np.sum(alpha_centered)))
    residual_delta = float(abs(np.sum(delta_centered)))
    grad_norm = float(np.linalg.norm(res.jac)) if res.jac is not None else 0.0

    return {
        "success": bool(res.success),
        "status": int(res.status),
        "message": str(res.message),
        "iterations": int(res.nit),
        "final_objective": float(res.fun),
        "gradient_norm": grad_norm,
        "mu": mu_centered,
        "home_advantage": h_centered,
        "alpha": alpha_centered.tolist(),
        "delta": delta_centered.tolist(),
        "rho": rho_val,
        "identifiability_residual_alpha": residual_alpha,
        "identifiability_residual_delta": residual_delta,
        "regularization_gamma": gamma,
        "match_count": len(home_goals),
        "team_count": num_teams,
    }


class AttackDefensePoissonModel(IPredictionModel):
    """
    Production Team-Specific Attack/Defense Poisson Statistical Prediction Model.
    Learns log-linear competition scoring baselines, home advantage, and team-specific
    attack (alpha) and defense (delta) parameters with L2 regularization and zero-sum identifiability.
    """

    model_key: str = "attack_defense_poisson_v1"
    model_family: str = "ATTACK_DEFENSE_POISSON"
    version: str = "1.0.0"
    target_key: str = "home_goals_v1:away_goals_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [
        ModelCapabilityEnum.EXPECTED_GOALS,
        ModelCapabilityEnum.EXACT_SCORE,
        ModelCapabilityEnum.ONE_X_TWO,
        ModelCapabilityEnum.BTTS,
        ModelCapabilityEnum.OVER_UNDER,
    ]

    REQUIRED_STRENGTH_FEATURES: list[str] = [
        "league_home_goals_per_match_v1",
        "league_away_goals_per_match_v1",
        "home_attack_strength_v1",
        "home_defense_strength_v1",
        "away_attack_strength_v1",
        "away_defense_strength_v1",
    ]

    def __init__(
        self,
        regularization_gamma: float = 0.2,
        min_matches_history: int = 5,
        max_iter: int = 500,
        tol: float = 1e-6,
        time_decay_half_life_days: float | None = None,
        optimize_rho: bool = False,
    ) -> None:
        self.regularization_gamma = regularization_gamma
        self.min_matches_history = min_matches_history
        self.max_iter = max_iter
        self.tol = tol
        self.time_decay_half_life_days = time_decay_half_life_days
        self.optimize_rho = optimize_rho
        
        self.artifact: TrainedModelArtifact | None = None
        self._distribution_engine = GoalDistributionEngine()
        
        if self.optimize_rho:
            self.model_key = "dixon_coles_poisson_v1"
            self.model_family = "DIXON_COLES_POISSON"
        elif self.time_decay_half_life_days is not None:
            self.model_key = "attack_defense_poisson_decay_v1"
            self.model_family = "ATTACK_DEFENSE_POISSON"
        else:
            self.model_key = "attack_defense_poisson_v1"
            self.model_family = "ATTACK_DEFENSE_POISSON"

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        if not training_rows:
            raise ValueError("Cannot fit AttackDefensePoissonModel on empty training rows.")

        preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = preprocessor.fit(training_rows)

        max_kickoff = None
        if self.time_decay_half_life_days is not None:
            for r in training_rows:
                if r.kickoff_utc:
                    if max_kickoff is None or r.kickoff_utc > max_kickoff:
                        max_kickoff = r.kickoff_utc

        comp_rows: dict[str, list[ModelingRowDTO]] = {}
        for r in training_rows:
            c_key = str(r.competition_id)
            if c_key not in comp_rows:
                comp_rows[c_key] = []
            comp_rows[c_key].append(r)

        competitions_payload: dict[str, Any] = {}
        global_team_counts: dict[str, int] = {}

        for c_key, rows in comp_rows.items():
            has_team_ids = any(r.home_team_id is not None and r.away_team_id is not None for r in rows)
            has_goal_targets = any(
                "home_goals_v1" in r.targets and "away_goals_v1" in r.targets for r in rows
            )

            if has_team_ids and has_goal_targets:
                team_set = set()
                valid_rows = []
                for r in rows:
                    if (
                        r.home_team_id is not None
                        and r.away_team_id is not None
                        and "home_goals_v1" in r.targets
                        and "away_goals_v1" in r.targets
                        and r.targets["home_goals_v1"] is not None
                        and r.targets["away_goals_v1"] is not None
                    ):
                        h_id = str(r.home_team_id)
                        a_id = str(r.away_team_id)
                        team_set.add(h_id)
                        team_set.add(a_id)
                        valid_rows.append((r, h_id, a_id))

                team_list = sorted(list(team_set))
                team_to_idx = {tid: idx for idx, tid in enumerate(team_list)}
                team_names: dict[str, str] = {}
                team_counts: dict[str, int] = {tid: 0 for tid in team_list}

                w_list = []
                for r, h_id, a_id in valid_rows:
                    team_counts[h_id] += 1
                    team_counts[a_id] += 1
                    global_team_counts[h_id] = global_team_counts.get(h_id, 0) + 1
                    global_team_counts[a_id] = global_team_counts.get(a_id, 0) + 1
                    if r.home_team_name:
                        team_names[h_id] = r.home_team_name
                    if r.away_team_name:
                        team_names[a_id] = r.away_team_name
                        
                    if self.time_decay_half_life_days is not None and max_kickoff is not None and r.kickoff_utc is not None:
                        delta_days = (max_kickoff - r.kickoff_utc).total_seconds() / 86400.0
                        w_list.append(2.0 ** (-delta_days / self.time_decay_half_life_days))
                    else:
                        w_list.append(1.0)

                h_idx = np.array([team_to_idx[h_id] for _, h_id, _ in valid_rows], dtype=np.int32)
                a_idx = np.array([team_to_idx[a_id] for _, _, a_id in valid_rows], dtype=np.int32)
                y_h = np.array([float(r.targets["home_goals_v1"]) for r, _, _ in valid_rows], dtype=np.float64)
                y_a = np.array([float(r.targets["away_goals_v1"]) for r, _, _ in valid_rows], dtype=np.float64)
                match_weights = np.array(w_list, dtype=np.float64) if self.time_decay_half_life_days is not None else None

                fit_result = _fit_competition_poisson(
                    home_indices=h_idx,
                    away_indices=a_idx,
                    home_goals=y_h,
                    away_goals=y_a,
                    num_teams=len(team_list),
                    gamma=self.regularization_gamma,
                    max_iter=self.max_iter,
                    tol=self.tol,
                    match_weights=match_weights,
                    optimize_rho=self.optimize_rho,
                )

                alpha_dict = {
                    team_list[i]: float(fit_result["alpha"][i])
                    for i in range(len(team_list))
                }
                delta_dict = {
                    team_list[i]: float(fit_result["delta"][i])
                    for i in range(len(team_list))
                }

                competitions_payload[c_key] = {
                    "competition_id": c_key,
                    "goal_baseline_mu": float(fit_result["mu"]),
                    "home_advantage_h": float(fit_result["home_advantage"]),
                    "dixon_coles_rho": float(fit_result.get("rho", 0.0)),
                    "team_attack_strengths": alpha_dict,
                    "team_defense_strengths": delta_dict,
                    "team_match_counts": team_counts,
                    "team_names": team_names,
                    "team_list": team_list,
                    "diagnostics": {
                        "success": fit_result["success"],
                        "status": fit_result["status"],
                        "message": fit_result["message"],
                        "iterations": fit_result["iterations"],
                        "final_objective": round(fit_result["final_objective"], 4),
                        "gradient_norm": round(fit_result["gradient_norm"], 6),
                        "identifiability_residual_alpha": fit_result["identifiability_residual_alpha"],
                        "identifiability_residual_delta": fit_result["identifiability_residual_delta"],
                        "match_count": fit_result["match_count"],
                        "team_count": fit_result["team_count"],
                    },
                }

        all_mus = [c["goal_baseline_mu"] for c in competitions_payload.values() if "goal_baseline_mu" in c]
        all_hs = [c["home_advantage_h"] for c in competitions_payload.values() if "home_advantage_h" in c]
        default_mu = float(np.mean(all_mus)) if all_mus else 0.05
        default_h = float(np.mean(all_hs)) if all_hs else 0.25

        weights = {
            "competitions": competitions_payload,
            "default_goal_baseline_mu": round(default_mu, 6),
            "default_home_advantage_h": round(default_h, 6),
            "global_team_counts": global_team_counts,
            "required_features": self.REQUIRED_STRENGTH_FEATURES,
        }

        if not training_window:
            training_window = TrainingWindow(
                row_count=len(training_rows),
                modeling_dataset_key=training_rows[0].dataset_release_key,
                modeling_dataset_fingerprint=training_rows[0].dataset_release_fingerprint,
                competitions=list(comp_rows.keys()),
            )

        artifact = TrainedModelArtifact(
            model_key=self.model_key,
            model_family=self.model_family,
            version=self.version,
            target_key=self.target_key,
            feature_set_key=self.feature_set_key,
            lifecycle_status=self.lifecycle_status,
            training_window=training_window,
            preprocessor_artifact=prep_art,
            hyperparameters={
                "regularization_gamma": self.regularization_gamma,
                "min_matches_history": self.min_matches_history,
                "max_iter": self.max_iter,
                "tol": self.tol,
                "time_decay_half_life_days": self.time_decay_half_life_days,
                "optimize_rho": self.optimize_rho,
                "identifiability_strategy": "ZERO_SUM_CENTERING",
                "home_advantage_encoded_in_league_baselines": True,
            },
            weights_payload=weights,
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact

        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """
        Generates fixture-specific raw expected goals (lambda_home, lambda_away)
        and derived score-matrix probabilities using learned team parameters.
        """
        if not self.artifact:
            raise RuntimeError("Model has not been fitted or loaded with an artifact.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed: payload has been tampered with.")

        if row.feature_set_key != self.artifact.feature_set_key:
            raise ValueError(
                f"Feature set mismatch: expected '{self.artifact.feature_set_key}', got '{row.feature_set_key}'"
            )

        weights = self.artifact.weights_payload
        comp_payloads = weights.get("competitions", {})
        c_key = str(row.competition_id)
        comp_model = comp_payloads.get(c_key)

        h_id = str(row.home_team_id) if row.home_team_id else None
        a_id = str(row.away_team_id) if row.away_team_id else None

        # Check if we can perform team-parameter based prediction
        use_learned_teams = comp_model is not None and (h_id is not None or a_id is not None)

        if use_learned_teams:
            mu = float(comp_model.get("goal_baseline_mu", weights.get("default_goal_baseline_mu", 0.05)))
            h_adv = float(comp_model.get("home_advantage_h", weights.get("default_home_advantage_h", 0.25)))
            attacks = comp_model.get("team_attack_strengths", {})
            defenses = comp_model.get("team_defense_strengths", {})
            counts = comp_model.get("team_match_counts", {})

            # Home team parameters & cold start check
            h_count = counts.get(h_id, 0) if h_id else 0
            if h_id in attacks:
                alpha_h = float(attacks[h_id])
                delta_h = float(defenses[h_id])
                h_cold_start = False
                h_sparse = h_count < self.min_matches_history
            else:
                alpha_h = 0.0
                delta_h = 0.0
                h_cold_start = True
                h_sparse = True

            # Away team parameters & cold start check
            a_count = counts.get(a_id, 0) if a_id else 0
            if a_id in attacks:
                alpha_a = float(attacks[a_id])
                delta_a = float(defenses[a_id])
                a_cold_start = False
                a_sparse = a_count < self.min_matches_history
            else:
                alpha_a = 0.0
                delta_a = 0.0
                a_cold_start = True
                a_sparse = True

            # Log-linear formulations
            log_lh = mu + h_adv + alpha_h - delta_a
            log_la = mu + alpha_a - delta_h

            # Numerical stability clipping
            log_lh = max(-4.0, min(3.5, log_lh))
            log_la = max(-4.0, min(3.5, log_la))

            lambda_home = round(float(math.exp(log_lh)), 4)
            lambda_away = round(float(math.exp(log_la)), 4)

            # Operational bounds
            lambda_home = max(0.01, min(15.0, lambda_home))
            lambda_away = max(0.01, min(15.0, lambda_away))

            evidence_quality = "COLD_START" if (h_cold_start or a_cold_start) else (
                "LIMITED_HISTORY" if (h_sparse or a_sparse) else "HIGH"
            )

            raw_outputs_extra = {
                "home_lambda_components": {
                    "competition_baseline": mu,
                    "home_advantage": h_adv,
                    "home_attack": alpha_h,
                    "away_defence": delta_a,
                    "log_lambda": round(log_lh, 4),
                    "lambda": lambda_home,
                },
                "away_lambda_components": {
                    "competition_baseline": mu,
                    "away_attack": alpha_a,
                    "home_defence": delta_h,
                    "log_lambda": round(log_la, 4),
                    "lambda": lambda_away,
                },
                "team_strengths": {
                    "home_attack": alpha_h,
                    "home_defence": delta_h,
                    "away_attack": alpha_a,
                    "away_defence": delta_a,
                },
                "competition_parameters": {
                    "goal_baseline": mu,
                    "home_advantage": h_adv,
                },
                "evidence_quality": {
                    "home_history_count": h_count,
                    "away_history_count": a_count,
                    "home_cold_start": h_cold_start,
                    "away_cold_start": a_cold_start,
                    "quality_level": evidence_quality,
                },
            }

        else:
            # Fallback to feature-based point-in-time calculation (Sprint 4.2 backward compatibility)
            row_feat_map = dict(zip(row.ordered_feature_names, row.feature_values))
            l_home = row_feat_map.get("league_home_goals_per_match_v1")
            l_away = row_feat_map.get("league_away_goals_per_match_v1")
            h_att = row_feat_map.get("home_attack_strength_v1")
            h_def = row_feat_map.get("home_defense_strength_v1")
            a_att = row_feat_map.get("away_attack_strength_v1")
            a_def = row_feat_map.get("away_defense_strength_v1")

            missing = []
            if l_home is None or math.isnan(l_home): missing.append("league_home_goals_per_match_v1")
            if l_away is None or math.isnan(l_away): missing.append("league_away_goals_per_match_v1")
            if h_att is None or math.isnan(h_att): missing.append("home_attack_strength_v1")
            if h_def is None or math.isnan(h_def): missing.append("home_defense_strength_v1")
            if a_att is None or math.isnan(a_att): missing.append("away_attack_strength_v1")
            if a_def is None or math.isnan(a_def): missing.append("away_defense_strength_v1")

            if missing:
                raise ValueError(
                    f"INSUFFICIENT_FEATURE_HISTORY: Missing required attack/defense strength features: {missing}"
                )

            lambda_home = round(float(l_home * h_att * a_def), 4)
            lambda_away = round(float(l_away * a_att * h_def), 4)
            lambda_home = max(0.01, min(15.0, lambda_home))
            lambda_away = max(0.01, min(15.0, lambda_away))

            raw_outputs_extra = {
                "league_home_goals_per_match_v1": l_home,
                "league_away_goals_per_match_v1": l_away,
                "home_attack_strength_v1": h_att,
                "home_defense_strength_v1": h_def,
                "away_attack_strength_v1": a_att,
                "away_defense_strength_v1": a_def,
                "evidence_quality": {"quality_level": "FEATURE_BASED_RATIOS"},
            }

        # Derive probability distribution through GoalDistributionEngine
        rho_val = float(comp_model.get("dixon_coles_rho", 0.0)) if use_learned_teams else 0.0
        matrix = self._distribution_engine.compute_score_matrix(lambda_home, lambda_away, rho=rho_val)
        one_x_two = self._distribution_engine.derive_1x2(matrix, source_model=self.model_key)
        btts = self._distribution_engine.derive_btts(matrix, lambda_home, lambda_away, rho=rho_val)
        ou25 = self._distribution_engine.derive_over_under_2_5(matrix, lambda_home, lambda_away)

        raw_outputs = {
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            **raw_outputs_extra,
        }

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
            raw_outputs=raw_outputs,
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns 1X2 raw probabilities derived from score matrix."""
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
        self.regularization_gamma = self.artifact.hyperparameters.get("regularization_gamma", 0.2)
        self.min_matches_history = self.artifact.hyperparameters.get("min_matches_history", 5)
        self.max_iter = self.artifact.hyperparameters.get("max_iter", 500)
        self.tol = self.artifact.hyperparameters.get("tol", 1e-6)

