import re

with open("app/models/baselines/attack_defense_poisson.py", "r") as f:
    content = f.read()

new_func = """def _fit_competition_poisson(
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
    )"""

pattern = re.compile(r'def _fit_competition_poisson\(.*?\n    res = minimize\([\s\S]*?\n    \)', re.DOTALL)
new_content = pattern.sub(new_func, content)

with open("app/models/baselines/attack_defense_poisson.py", "w") as f:
    f.write(new_content)
