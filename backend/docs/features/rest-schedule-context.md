# Rest, Schedule & Context Features Architecture Specification

## 1. Executive Summary

Sprint 3.5 implements pre-match schedule context and rest features for the Football Intelligence & Probability Analysis System. These features capture pre-match schedule load, observed rest days, rolling fixture congestion across 7, 14, and 21-day windows, and season-to-date match experience for competing teams.

The primary exposed features are:
- `home_rest_days_v1`, `away_rest_days_v1`, `rest_days_difference_v1`
- `home_matches_last_7d_v1`, `away_matches_last_7d_v1`
- `home_matches_last_14d_v1`, `away_matches_last_14d_v1`
- `home_matches_last_21d_v1`, `away_matches_last_21d_v1`
- `home_season_matches_played_v1`, `away_season_matches_played_v1`

---

## 2. Dataset Scope Disclosure & Scientific Limitations

> [!IMPORTANT]
> **Observed Fixtures Only:** All rest and schedule load features describe observed fixtures contained within the approved historical dataset release (`mvp_a_historical_v1`) for a specific competition and season.
> 
> They do **NOT** claim to measure full real-world physical recovery or unobserved domestic cup, continental, friendly, or international matches absent from the release.
> 
> All feature payloads include metadata disclosures:
> - `schedule_scope`: `"APPROVED_DATASET_COMPETITION_ONLY"`
> - `includes_cup_matches`: `False`

---

## 3. Observed Rest Days Semantics

### Current-Season Only Policy
Rest days are measured relative to the most recent eligible observed match *within the same competition season* (`season_id`).

If a team has played no previous matches in the current season (e.g. season opener), the feature returns:
- `value = None`
- `is_missing = True`
- `missing_reason = INSUFFICIENT_HISTORY`

Multi-month off-season breaks across season boundaries are explicitly excluded to prevent distorting in-season rest comparisons.

### Timestamp & DATE_ONLY Precision
- **Exact Timestamps:** Rest days are computed as fractional days: $\text{rest\_days} = \frac{\Delta t_{\text{seconds}}}{86400.0}$, rounded to 2 decimals.
- **DATE_ONLY Precision:** When kickoff sub-day precision is unknown, rest days are computed as calendar-day separation: $(\text{target\_date} - \text{prev\_match\_date}).\text{days}$.

### Rest Days Difference
$$\text{rest\_days\_difference\_v1} = \text{home\_rest\_days\_v1} - \text{away\_rest\_days\_v1}$$
If either home or away rest days is missing, `rest_days_difference_v1` returns `is_missing = True` (`value = None`).

---

## 4. Rolling Match Window Counts & Season Experience

### Window Match Counts (7d, 14d, 21d)
Counts finished observed matches played by the team in the current season strictly within the window $[T - \text{window\_days}, T)$, where $T$ is the start of the target cutoff date.
- Same-day matches ($t = T$) are excluded by `DATE_ONLY` cutoff policy.
- **Zero Count Validity:** A value of `0` matches in a window is a **valid, available** feature value (`is_missing = False`, `value = 0`).

### Season Matches Played
Counts total finished observed matches played by the team in the current season prior to cutoff. Helps downstream models distinguish early-season uncertainty from late-season maturity.

---

## 5. Point-in-Time & Anti-Leakage Safeguards

1. **Target Outcome Isolation:** The target match is excluded (`match_id != target_match_id`). Mutating the target match result or scoreline does NOT change pre-match rest or schedule features.
2. **Prior Match Score Invariance:** Mutating the score of a prior match (e.g. from 1-0 to 5-4) leaves rest days and match counts strictly unchanged.
3. **Prior Date Sensitivity:** Changing the kickoff date of a prior match correctly updates rest days and rolling window counts.
4. **Future Match / Fixture Isolation:** Future matches or scheduled fixtures played or listed after the target cutoff date are strictly excluded.
