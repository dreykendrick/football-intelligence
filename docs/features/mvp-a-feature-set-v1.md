# MVP-A Feature Set Specification (`mvp_a_feature_set_v1`)

## Executive Summary

`mvp_a_feature_set_v1` is the canonical, frozen Phase 3 feature set specification for the Football Intelligence & Probability System. It provides 251 versioned, point-in-time, leakage-isolated statistical features designed explicitly to serve as input variables for Phase 4 prediction modeling (Poisson, Dixon-Coles, XGBoost, ensemble rating engines).

---

## 1. Feature Set Identity & Metadata

- **Feature Set Key:** `mvp_a_feature_set_v1`
- **Version:** `1.0.0`
- **Approved Historical Dataset Release Dependency:** `mvp_a_historical:v1`
- **Total Feature Count:** 251 pre-match statistical feature keys
- **Deterministic Manifest Fingerprint:** `b66cbdf6faeefbb5` (SHA-256 slice)
- **Cutoff Policy:** `STRICT_BEFORE_KICKOFF` (strictly bounded by target match `kickoff_utc` or 00:00:00 UTC on matchday when sub-day precision is absent)

---

## 2. Included Feature Categories & Breakdown

| Category | Key Count | Description & Key Examples |
|---|---|---|
| **Historical Counts** | 3 | Sample size counters (`home_matches_played_v1`, `away_matches_played_v1`, `total_matches_played_v1`) |
| **Historical Goal Rates** | 4 | Season-to-date home/away goal averages (`home_goals_scored_avg_v1`, `home_goals_conceded_avg_v1`, etc.) |
| **League Baselines** | 2 | Point-in-time competition season averages (`league_home_goals_per_match_v1`, `league_away_goals_per_match_v1`) |
| **Strength Ratios** | 8 | Attack/defense strength ratios relative to league average (STD and last 5 windowed) |
| **Elo Rating System** | 3 | Pre-match rating state (`home_elo_v1`, `away_elo_v1`, `elo_difference_v1`) |
| **Rest & Schedule Congestion** | 11 | Observed rest days and match counts across 7d, 14d, 21d, and season-to-date |
| **General Form (All Venues)** | 108 | $2 \text{ sides} \times 3 \text{ windows (3,5,10)} \times 18 \text{ metrics}$ (PPG, win/draw/loss rates, clean sheets, FTS, goal diff) |
| **Venue-Specific Form** | 108 | $2 \text{ sides} \times 3 \text{ windows (3,5,10)} \times 18 \text{ metrics}$ home-only & away-only performance |
| **Legacy Form Aliases** | 4 | Backward-compatible 5-match form aliases (`home_recent_ppg_v1`, etc.) |

---

## 3. Anti-Leakage & Safety Boundaries

### Explicitly Excluded Categories (Phase 4 Model Inputs & Labels)

To preserve scientific rigor and eliminate target/future data leakage, the following data categories are strictly forbidden in Phase 3 feature sets:

1. **Target Scorelines & Match Outcomes:**
   `home_goals`, `away_goals`, `home_win`, `draw`, `away_win`, `result`, `half_time_home_score`, `half_time_away_score`, `btts_label`, `over_2_5_label`
2. **Bookmaker Odds & Implied Probabilities:**
   `B365H`, `B365D`, `B365A`, `AvgH`, `AvgD`, `AvgA`, `implied_home_prob`, `implied_draw_prob`, `implied_away_prob`
3. **Phase 4 Probabilities & Lambda Parameters:**
   `predicted_home_goals`, `predicted_away_goals`, `lambda_home`, `lambda_away`, `elo_win_probability_home_v1`, `predicted_home_win_probability`, `btts_probability`, `over_under_probability`
4. **Unverified External Datasets:**
   `provider_xg`, `travel_distance_km`, `weather_temperature`, `injury_count`, `future_fixture_density`

---

## 4. Phase 4 Usage Contract

1. **Point-in-Time Scoping:** Phase 4 models MUST query feature values exclusively through `FeatureSetAssembler` or `FeatureSnapshot` records tagged with `feature_set_key="mvp_a_feature_set_v1"`.
2. **Missingness Handling:** Features marked `is_missing=True` contain explicit `MissingnessReason` codes (`INSUFFICIENT_HISTORY`, `DATE_OUT_OF_BOUNDS`). Phase 4 estimators must handle missing values according to feature category policies.
3. **Deterministic Vectors:** Feature order inside `FeatureSetVectorDTO.ordered_feature_values` is guaranteed to match the sorted manifest `included_feature_keys` order identically across all runtime environments.
