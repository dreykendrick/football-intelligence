# Baseline Statistical Models Specification

## Overview

Sprint 4.1 introduces three baseline statistical models in the `EXPERIMENTAL` lifecycle status with `RAW_UNCALIBRATED` probability outputs. These baselines provide initial reference benchmarks for evaluating model performance in Phase 4.

---

## 1. Class Prior Baseline Model (`class_prior_1x2_v1`)

### Description
The Class Prior baseline model computes empirical outcome frequencies directly from historical training target labels without utilizing any pre-match features.

### Mathematical Formulation
For outcomes $k \in \{0, 1, 2\}$ representing Home Win, Draw, Away Win:

$$P(Y = k) = \frac{\sum_{i=1}^N \mathbb{I}(y_i = k) + \alpha}{N + 3\alpha}$$

where $\alpha = 1.0$ (Laplace smoothing) prevents zero probabilities when target classes are sparse.

### Intended Purpose
Serves as the absolute bottom-line benchmark. Any machine learning or feature-based model must significantly outperform class prior distribution to prove value.

---

## 2. Multinomial Logistic Regression Baseline Model (`multinomial_logistic_1x2_v1`)

### Description
Implements multiclass logistic regression over preprocessed Phase 3 feature vectors (`mvp_a_feature_set_v1`).

### Mathematical Formulation
Given preprocessed feature vector $\mathbf{x} \in \mathbb{R}^D$:

$$P(Y = k \mid \mathbf{x}) = \frac{\exp(\mathbf{w}_k^T \mathbf{x} + b_k)}{\sum_{j=0}^2 \exp(\mathbf{w}_j^T \mathbf{x} + b_j)}$$

### Key Characteristics
- **Solvers & Optimization:** L-BFGS optimizer with L2 regularization penalty ($C = 1.0$).
- **Interpretability:** Coefficient weights $\mathbf{w}_k$ directly reflect feature importance per outcome class.
- **Preprocessing:** Consumes Z-score normalized features with median imputation and missingness indicators.

---

## 3. Independent Poisson Expected Goals Baseline Model (`poisson_goals_v1`)

### Description
Fits independent Poisson regression models for expected home goals ($\lambda_H$) and expected away goals ($\lambda_A$), deriving 1X2, Over/Under 2.5, and BTTS probabilities via bivariate score matrix integration.

### Mathematical Formulation
Given expected goals parameters $\lambda_H, \lambda_A$:

$$P(H = h) = \frac{\lambda_H^h e^{-\lambda_H}}{h!}, \quad P(A = a) = \frac{\lambda_A^a e^{-\lambda_A}}{a!}$$

Joint score probability assuming independence:

$$P(H = h, A = a) = P(H = h) \cdot P(A = a)$$

Match probabilities derived via truncation up to max score $K = 10$:

- **Home Win:** $P(H > A) = \sum_{h=1}^K \sum_{a=0}^{h-1} P(h, a)$
- **Draw:** $P(H = A) = \sum_{g=0}^K P(g, g)$
- **Away Win:** $P(H < A) = \sum_{a=1}^K \sum_{h=0}^{a-1} P(h, a)$
- **Over 2.5:** $P(H + A > 2.5) = \sum_{h+a > 2.5} P(h, a)$
- **BTTS:** $P(H > 0 \land A > 0) = \sum_{h=1}^K \sum_{a=1}^K P(h, a)$

---

## 4. Lifecycle & Governance Invariants

- **Status:** All baseline models are explicitly marked `EXPERIMENTAL`.
- **Probabilities:** Outputs are strictly tagged `RAW_UNCALIBRATED`.
- **No Betting Claims:** No backtesting performance, calibration, ROI analysis, or bookmaker odds comparisons are performed in Sprint 4.1.
