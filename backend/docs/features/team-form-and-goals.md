# Team Form & Goal Performance Features (Sprint 3.2)

## 1. Executive Summary

**Sprint 3.2 — Team Form & Goal Performance Features** implements historical rolling performance calculation over configurable windows ($N \in \{3, 5, 10\}$) for both home and away target teams prior to match kickoff.

All feature calculations consume eligible prior matches strictly via `PointInTimeQueryService` and `HistoricalDatasetQueryService` from an approved dataset release (`mvp_a_historical_v1`).

---

## 2. Implemented Feature Families

For both home and away target teams, the following rolling statistics are calculated across windows $N \in \{3, 5, 10\}$:

1. **Points & Points-Per-Game (PPG):**
   - `points_last_N` (Win=3, Draw=1, Loss=0)
   - `ppg_last_N` ($\text{points} / \text{sample\_size}$)
2. **Win / Draw / Loss Counts & Rates:**
   - `wins_last_N`, `draws_last_N`, `losses_last_N`
   - `win_rate_last_N`, `draw_rate_last_N`, `loss_rate_last_N` ($\text{count} / \text{sample\_size}$)
   - Invariant: $\text{wins} + \text{draws} + \text{losses} = \text{sample\_size}$
3. **Goals Scored & Conceded:**
   - `goals_scored_last_N`, `goals_scored_per_match_last_N`
   - `goals_conceded_last_N`, `goals_conceded_per_match_last_N`
4. **Goal Difference:**
   - `goal_difference_last_N`, `goal_difference_per_match_last_N`
   - Formula: $\text{goals\_scored} - \text{goals\_conceded}$
5. **Clean Sheets & Failed to Score:**
   - `clean_sheets_last_N`, `clean_sheet_rate_last_N` ($\text{goals\_conceded} = 0$)
   - `failed_to_score_last_N`, `failed_to_score_rate_last_N` ($\text{goals\_scored} = 0$)

---

## 3. Core Scientific & Anti-Leakage Policies

- **Sample Size Exposure:** Every feature result records `sample_size` (the true number of available prior matches used).
- **Partial Window Handling:** If requested $N=5$ but only 2 prior matches exist, averages/rates divide by $2$ (the available sample size), setting `sample_size=2`. History is never padded or duplicated.
- **Zero-History Policy:** If zero prior matches exist, `value=None`, `is_missing=True`, `missing_reason=INSUFFICIENT_HISTORY`, and `sample_size=0`.
- **General Form Scope:** Evaluates all eligible historical matches for a club across seasons within the approved dataset release regardless of venue.
- **DATE_ONLY Precision:** Matches occurring on the exact same calendar date as target cutoff date are conservatively excluded when sub-day time ordering is unverified (`Match.kickoff_utc < cutoff_start_of_day`).
- **Target Outcome Isolation:** Target match score, result, and statistics are strictly excluded from its own pre-match feature calculation.
