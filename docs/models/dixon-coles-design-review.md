# Technical Design Review: Dixon-Coles Goal Model

## Status: `DEFERRED_CANDIDATE`

---

## 1. Overview & Mathematical Formulation

The Dixon-Coles model (Dixon & Coles, 1997) extends independent Poisson goal models by introducing a low-score dependency parameter $\tau(h, a)$ to correct for the empirical inflation of low-scoring draws ($0-0, 1-1$) and low-scoring wins ($1-0, 0-1$).

### Low-Score Inflation Adjustment Matrix $\tau(h, a)$

$$\tau(h, a) = \begin{cases}
1 - \lambda_H \lambda_A \rho & \text{if } h=0, a=0 \\
1 + \lambda_A \rho & \text{if } h=1, a=0 \\
1 + \lambda_H \rho & \text{if } h=0, a=1 \\
1 - \rho & \text{if } h=1, a=1 \\
1 & \text{otherwise}
\end{cases}$$

where $\rho$ represents the low-score correlation parameter.

---

## 2. Compatibility with `GoalDistributionEngine`

The `GoalDistributionEngine` architecture supports non-independent score matrices via the `ScoreProbabilityMatrix` DTO:

- Modifies joint score cell: $P_{\text{DC}}(h, a) = \tau(h, a) \cdot P_{\text{Poisson}}(h, a)$.
- Re-normalizes matrix over retained mass $M_{\text{retained}}$.
- Derives 1X2, BTTS, Over/Under 2.5, and Top Exact Scores identically through existing matrix reduction functions.

---

## 3. Rationale for Deferred Status (`DEFERRED_CANDIDATE`)

1. **Sprint 4.2 Focus:** Sprint 4.2 prioritizes building the goal-distribution engine architecture and baseline goal models.
2. **Optimization Overhead:** Fitting $\rho$ via Maximum Likelihood Estimation (MLE) over joint bivariate log-likelihoods adds fitting complexity that is best evaluated in Sprint 4.3 or Phase 5.
3. **Architecture Readiness:** Current `GoalDistributionEngine` is fully prepared to consume Dixon-Coles parameters without architectural refactoring when introduced.
