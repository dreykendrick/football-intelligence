# Goal Models Architecture (`poisson_goals_v1` & `attack_defense_poisson_v1`)

## Overview

Goal models estimate conditional expected home goals ($\lambda_H$) and expected away goals ($\lambda_A$) from pre-match point-in-time features. These expected goal parameters serve as inputs to the `GoalDistributionEngine` to derive exact score matrices, 1X2, BTTS, and Over/Under 2.5 probabilities.

---

## 1. Registered Goal Models

| Model Key | Family | Version | Target Key | Inputs & Formulation |
| :--- | :--- | :--- | :--- | :--- |
| `poisson_goals_v1` | `POISSON_GOALS` | `1.0.0` | `home_goals_v1:away_goals_v1` | Dual Poisson GLM fitted on full 251-feature vector `mvp_a_feature_set_v1`. |
| `attack_defense_poisson_v1` | `ATTACK_DEFENSE_POISSON` | `1.0.0` | `home_goals_v1:away_goals_v1` | Structural reference model consuming point-in-time Phase 3 strength features. |

---

## 2. Independent Poisson Goals Model (`poisson_goals_v1`)

### Mathematical Formulation
Estimates conditional expected goal rates using log-linear Poisson regression:

$$\ln(\lambda_H) = \mathbf{w}_H^T \mathbf{x} + b_H, \quad \ln(\lambda_A) = \mathbf{w}_A^T \mathbf{x} + b_A$$

$$\lambda_H = \max(0.01, e^{\ln(\lambda_H)}), \quad \lambda_A = \max(0.01, e^{\ln(\lambda_A)})$$

### Conditional Independence Assumption
Assumes conditional independence of home and away goals given pre-match features:

$$\text{HomeGoals} \perp \text{AwayGoals} \mid \text{pre-match features}$$

$$P(H=i, A=j) = P(H=i) \cdot P(A=j) = \frac{\lambda_H^i e^{-\lambda_H}}{i!} \cdot \frac{\lambda_A^j e^{-\lambda_A}}{j!}$$

---

## 3. Attack/Defense Reference Model (`attack_defense_poisson_v1`)

### Mathematical Formulation
Provides an interpretable structural reference formulation consuming Phase 3 strength ratios:

$$\lambda_H = \text{league\_home\_goals\_per\_match\_v1} \times \text{home\_attack\_strength\_v1} \times \text{away\_defense\_strength\_v1}$$

$$\lambda_A = \text{league\_away\_goals\_per\_match\_v1} \times \text{away\_attack\_strength\_v1} \times \text{home\_defense\_strength\_v1}$$

### Home Advantage & Missingness Policy
- **Home Advantage:** No second home-advantage multiplier is applied because `league_home_goals_per_match_v1` already encodes empirical home advantage.
- **Missing Inputs:** If any required strength feature is missing, `predict_raw` raises `INSUFFICIENT_FEATURE_HISTORY` rather than substituting default $1.0$ fallbacks.

---

## 4. Governance & Lifecycle Status

All goal models remain strictly:
- **Lifecycle Status:** `EXPERIMENTAL`
- **Probability Status:** `RAW_UNCALIBRATED`
- **Backtesting & Calibration:** `NOT_PERFORMED`
