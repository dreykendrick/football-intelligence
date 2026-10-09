# Home/Away & Strength Features (Sprint 3.3)

## 1. Executive Summary

**Sprint 3.3 — Home/Away & Strength Features** implements venue-specific historical performance calculation (home-only and away-only form) across windows $N \in \{3, 5, 10\}$, empirical point-in-time league scoring baselines, and normalized attack and defensive strength ratios.

All calculations execute strictly against approved historical dataset releases (`mvp_a_historical_v1`) via `PointInTimeQueryService` to preserve zero-leakage chronology.

---

## 2. Implemented Feature Families

### A. Venue-Specific Form Features
Evaluates team performance restricted to the venue of the target match (home-only matches for the target home team, away-only matches for the target away team) across windows $N \in \{3, 5, 10\}$:
- **Points & PPG:** `home_venue_points_last_N_v1`, `home_venue_ppg_last_N_v1`, `away_venue_points_last_N_v1`, `away_venue_ppg_last_N_v1`
- **W/D/L Counts & Rates:** `home_venue_wins_last_N_v1`, `home_venue_win_rate_last_N_v1`, `away_venue_wins_last_N_v1`, `away_venue_win_rate_last_N_v1`, etc.
- **Goals Scored & Conceded:** `home_venue_goals_scored_last_N_v1`, `home_venue_goals_scored_per_match_last_N_v1`, `home_venue_goals_conceded_last_N_v1`, `home_venue_goals_conceded_per_match_last_N_v1`, etc.
- **Goal Difference:** `home_venue_goal_difference_last_N_v1`, `home_venue_goal_difference_per_match_last_N_v1`, etc.
- **Clean Sheets & Failed to Score:** `home_venue_clean_sheets_last_N_v1`, `home_venue_clean_sheet_rate_last_N_v1`, `home_venue_failed_to_score_last_N_v1`, `home_venue_failed_to_score_rate_last_N_v1`, etc.

### B. Point-in-Time League Scoring Baselines
Evaluates competition-season league scoring environment using ONLY eligible league matches played before target cutoff $T$:
- `league_home_goals_per_match_v1` = $\sum(\text{home goals}) / \text{league\_sample\_size}$
- `league_away_goals_per_match_v1` = $\sum(\text{away goals}) / \text{league\_sample\_size}$

### C. Normalized Attack & Defensive Strength Ratios
- `home_attack_strength_v1` = $\text{home\_team\_home\_goals\_avg} / \text{league\_home\_goals\_per\_match}$
- `away_attack_strength_v1` = $\text{away\_team\_away\_goals\_avg} / \text{league\_away\_goals\_per\_match}$
- `home_defense_strength_v1` = $\text{home\_team\_home\_conceded\_avg} / \text{league\_away\_goals\_per\_match}$
- `away_defense_strength_v1` = $\text{away\_team\_away\_conceded\_avg} / \text{league\_home\_goals\_per\_match}$
- Windowed variants: `home_attack_strength_last_5_v1`, `away_attack_strength_last_5_v1`, `home_defense_strength_last_5_v1`, `away_defense_strength_last_5_v1`.

---

## 3. Core Anti-Contamination & Leakage Safeguards

- **No Final-Season Contamination:** League baselines are computed dynamically using only matches strictly prior to cutoff $T$. Final season averages are strictly forbidden.
- **Zero Denominator Protection:** If a league baseline is zero or unavailable, strength features return explicit missingness (`INSUFFICIENT_HISTORY`) with `value=None` rather than `NaN` or `Infinity`.
- **Target Match Isolation:** The target match is explicitly excluded from both team venue history and league baseline calculations.
- **DATE_ONLY Precision Rule:** Matches occurring on the exact same date as target cutoff date are conservatively excluded when sub-day time ordering is unverified (`Match.kickoff_utc < cutoff_start_of_day`).
