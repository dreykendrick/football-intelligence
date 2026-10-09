# Goal Distribution Engine Architecture (`GoalDistributionEngine`)

## Overview

The `GoalDistributionEngine` is a decoupled mathematical service responsible for constructing joint score matrices and deriving probability markets (1X2, BTTS, Over/Under 2.5, Exact Scores) from expected goals $(\lambda_H, \lambda_A)$ parameters.

---

## 1. Score Matrix Construction & Grid Truncation

Given validated $\lambda_H > 0$ and $\lambda_A > 0$:

1. **Marginal PMFs:** Computes $P(H=i)$ and $P(A=j)$ for $i, j \in \{0, \dots, K\}$ where default grid size $K = 10$.
2. **Joint Score Matrix:** Computes outer product $P(H=i, A=j) = P(H=i) \cdot P(A=j)$.
3. **Mass Accounting:**
   - **Retained Mass:** $M_{\text{retained}} = \sum_{i=0}^K \sum_{j=0}^K P(i,j)$
   - **Tail Mass:** $M_{\text{tail}} = 1.0 - M_{\text{retained}}$
4. **Normalization Policy:** Normalized cell probabilities $P_{\text{norm}}(i,j) = \frac{P(i,j)}{M_{\text{retained}}}$ ensure total matrix mass equals $1.000000$.

---

## 2. Derived Probability Markets

### 1X2 Probabilities
- **Home Win:** $P(\text{Home}) = \sum_{i > j} P_{\text{norm}}(i,j)$
- **Draw:** $P(\text{Draw}) = \sum_{i = j} P_{\text{norm}}(i,j)$
- **Away Win:** $P(\text{Away}) = \sum_{i < j} P_{\text{norm}}(i,j)$

### Both Teams To Score (BTTS)
- **Matrix Derivation:** $P(\text{BTTS Yes}) = \sum_{i \ge 1, j \ge 1} P_{\text{norm}}(i,j)$
- **Analytical Cross-Check:** $P_{\text{analytical}}(\text{BTTS Yes}) = 1 - e^{-\lambda_H} - e^{-\lambda_A} + e^{-(\lambda_H + \lambda_A)}$
- Verifies $|P_{\text{matrix}} - P_{\text{analytical}}| \le M_{\text{tail}} + 10^{-4}$.

### Over/Under 2.5 Goals
- **Matrix Derivation:** $P(\text{Under 2.5}) = \sum_{i+j \le 2} P_{\text{norm}}(i,j)$, $P(\text{Over 2.5}) = 1 - P(\text{Under 2.5})$
- **Analytical Cross-Check:** Total goals $H+A \sim \text{Poisson}(\lambda_H + \lambda_A)$, $P_{\text{analytical}}(\text{Under 2.5}) = \sum_{k=0}^2 \frac{(\lambda_H + \lambda_A)^k e^{-(\lambda_H + \lambda_A)}}{k!}$.

### Top-N Exact Scores & Most Likely Score
- Exact scores are ranked deterministically by: `(probability DESC, home_goals ASC, away_goals ASC)`.
- `most_likely_score` returns the top-ranked exact score tuple $(h, a)$.
