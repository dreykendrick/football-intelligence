# Probability Engine & Capability Router Architecture (`ProbabilityEngine`)

## Overview

The `ProbabilityEngine` acts as the central router for model predictions in Phase 4. It verifies artifact integrity, validates model capabilities, enforces preprocessor isolation, and returns unified `MatchProbabilityPrediction` DTOs.

---

## 1. Model Capabilities Architecture

Models declare explicit capabilities via `ModelCapabilityEnum`:

- `EXPECTED_GOALS`: Model outputs $\lambda_H, \lambda_A$.
- `EXACT_SCORE`: Model generates exact score matrix.
- `ONE_X_TWO`: Model outputs 1X2 probabilities.
- `BTTS`: Model outputs BTTS Yes/No.
- `OVER_UNDER`: Model outputs Over/Under 2.5.

### Capability Matrix

| Model Key | EXPECTED_GOALS | EXACT_SCORE | ONE_X_TWO | BTTS | OVER_UNDER |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `class_prior_1x2_v1` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `multinomial_logistic_1x2_v1` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `poisson_goals_v1` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `attack_defense_poisson_v1` | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 2. Unsupported Capability Enforcement

If a caller requests a market from a model that lacks the required capability (e.g., requesting BTTS from `multinomial_logistic_1x2_v1`), `ProbabilityEngine.assert_capability()` raises a structured error:

```text
ValueError: UNSUPPORTED_MODEL_CAPABILITY: Model 'multinomial_logistic_1x2_v1' does not support capability 'BTTS'
```

Direct models do NOT fabricate unsupported secondary probabilities.
