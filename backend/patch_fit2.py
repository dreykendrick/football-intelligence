import re

with open("app/models/baselines/attack_defense_poisson.py", "r") as f:
    content = f.read()

# 1. Patch return of _fit_competition_poisson
new_return = """    opt_theta = res.x
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
    }"""

pattern1 = re.compile(r'    opt_theta = res\.x[\s\S]*?    \}', re.MULTILINE)
content = pattern1.sub(new_return, content)

# 2. Patch AttackDefensePoissonModel.fit to handle weights and rho
new_fit = """    def fit(
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

        return self.artifact"""

pattern2 = re.compile(r'    def fit\([\s\S]*?return self\.artifact', re.MULTILINE)
content = pattern2.sub(new_fit, content)

with open("app/models/baselines/attack_defense_poisson.py", "w") as f:
    f.write(content)
