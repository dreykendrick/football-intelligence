# Elo Rating System Architecture Specification

## 1. Executive Summary

Sprint 3.4 implements the sequential pre-match **Elo Rating System** for the Football Intelligence & Probability Analysis System. The Elo rating engine provides continuous, point-in-time strength estimation for competing teams based on historical match results without future leakage or reliance on bookmaker odds.

The system exposes three descriptive pre-match features:
- `home_elo_v1`: Home team pre-match Elo rating.
- `away_elo_v1`: Away team pre-match Elo rating.
- `elo_difference_v1`: Raw pre-match Elo rating difference (`home_elo_v1 - away_elo_v1`).

---

## 2. Default Elo Hyperparameters

All Elo computations utilize centralized, immutable hyperparameters defined in `EloConfig`:

| Parameter | Value | Description |
| :--- | :--- | :--- |
| `INITIAL_RATING` | `1500.0` | Default rating for newly encountered or promoted teams. |
| `K_FACTOR` | `32.0` | Rating update weight constant. |
| `ELO_SCALE` | `400.0` | Logistic scale parameter for expected outcome. |
| `HOME_ADVANTAGE` | `100.0` | Rating boost added to home team during expected score calculation. |
| `MEAN_RATING` | `1500.0` | Population mean for inter-season regression. |
| `SEASON_CARRYOVER` | `0.75` | Regression carryover fraction across seasons. |
| `VERSION` | `"1.0.0"` | Configuration schema version. |

---

## 3. Mathematical Formulas

### Expected Score Calculation
Home advantage $H = 100.0$ is incorporated into the home team's effective rating $R_{home,eff}$:

$$R_{home,eff} = R_{home,pre} + H$$

The internal expected match outcome score for the home team $E_{home}$ is:

$$E_{home} = \frac{1}{1 + 10^{\frac{R_{away,pre} - R_{home,eff}}{S}}}$$

The away team expected score $E_{away}$ is:

$$E_{away} = 1.0 - E_{home}$$

### Match Outcome Score Mapping
The actual outcome score $S_{home}$ is mapped as:
- $S_{home} = 1.0$ (Home Win)
- $S_{home} = 0.5$ (Draw)
- $S_{home} = 0.0$ (Home Loss)

And $S_{away} = 1.0 - S_{home}$.

### Rating Update Formula
After match completion, team ratings update as:

$$R_{home,post} = R_{home,pre} + K \cdot (S_{home} - E_{home})$$

$$R_{away,post} = R_{away,pre} + K \cdot (S_{away} - E_{away})$$

Zero-sum property holds within floating-point precision: $\Delta R_{home} + \Delta R_{away} = 0$.

---

## 4. Competition Scope & Isolation

Elo ratings are **competition-specific**. Separate rating sequences are maintained for each competition (e.g., Premier League, La Liga, Serie A, Bundesliga). Results in one competition never alter team ratings in another competition.

---

## 5. Season Transition Policy

At the start of a new season in a competition, active teams regress towards the mean rating ($1500.0$):

$$R_{new} = 1500.0 + 0.75 \cdot (R_{old} - 1500.0)$$

Newly promoted teams or returning teams without active prior season state in the competition initialize at $1500.0$.

---

## 6. Point-in-Time & Anti-Leakage Safeguards

1. **DATE_ONLY Cutoff Policy:** Ratings for a target cutoff date only process finished matches strictly before the start of that cutoff date (`kickoff_utc < cutoff_start_of_day`).
2. **Target Outcome Isolation:** The target match's own result is strictly excluded from updating its pre-match Elo rating (`match_id != target_match_id`).
3. **Same-Day Batch Processing:** Multiple matches sharing the same date during historical replay calculate expected scores using start-of-day ratings and apply aggregated deltas at end-of-day to remove arbitrary intra-day order dependence.
4. **No Predictive Probability Outputs:** Internal expected scores are used strictly for Elo rating updates and are NOT exposed as match win/draw/loss probability features in Phase 3.
