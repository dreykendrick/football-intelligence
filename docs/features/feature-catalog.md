# Feature Catalog & Feature Engineering Architecture — Sprint 1.5

## 1. Overview

Sprint 1.5 establishes the deterministic, versioned, and leakage-safe feature engineering foundation for the **Football Intelligence & Probability Analysis System**.

All pre-match prediction models (Phase 2+) consume immutable `FeatureSnapshot` records produced under an explicit `cutoff_timestamp`.

---

## 2. Architecture & Data Flow

```
[ Historical Match Data ]
           │
           ▼
[ Quality Gate ] (assert_historical_data_ready())
           │
           ▼
[ Cutoff-Safe Query Layer ] (HistoricalQueryLayer: t_match < cutoff_timestamp, excludes target match)
           │
           ▼
[ Feature Calculators ] (Historical Counts, Goals, Attack/Defense, Form, Elo, Rest/Congestion)
           │
           ▼
[ FeatureSet ] (mvp_a_core_features_v1, version 1.0.0)
           │
           ▼
[ FeatureEngineService ] (SHA-256 Fingerprint & FeatureSnapshot Database Persistence)
```

---

## 3. Core Feature Catalog (MVP-A Core Feature Set: `mvp_a_core_features_v1`)

| Feature Key | Version | Category | Data Type | Required Prior History | Leakage Safe? | Description |
|---|---|---|---|---|---|---|
| `home_matches_played_v1` | `1.0.0` | COUNTS | `INTEGER` | 0 matches | **Yes** | Historical home matches played by home team prior to cutoff. |
| `away_matches_played_v1` | `1.0.0` | COUNTS | `INTEGER` | 0 matches | **Yes** | Historical away matches played by away team prior to cutoff. |
| `total_matches_played_v1` | `1.0.0` | COUNTS | `INTEGER` | 0 matches | **Yes** | Total historical matches played by both teams combined prior to cutoff. |
| `home_goals_scored_avg_v1` | `1.0.0` | GOALS | `FLOAT` | 1 home match | **Yes** | Average goals scored per home match by home team prior to cutoff. |
| `home_goals_conceded_avg_v1` | `1.0.0` | GOALS | `FLOAT` | 1 home match | **Yes** | Average goals conceded per home match by home team prior to cutoff. |
| `away_goals_scored_avg_v1` | `1.0.0` | GOALS | `FLOAT` | 1 away match | **Yes** | Average goals scored per away match by away team prior to cutoff. |
| `away_goals_conceded_avg_v1` | `1.0.0` | GOALS | `FLOAT` | 1 away match | **Yes** | Average goals conceded per away match by away team prior to cutoff. |
| `home_attack_strength_v1` | `1.0.0` | STRENGTH | `FLOAT` | 1 home match | **Yes** | Home team home scoring rate relative to league historical home scoring rate prior to cutoff. |
| `away_attack_strength_v1` | `1.0.0` | STRENGTH | `FLOAT` | 1 away match | **Yes** | Away team away scoring rate relative to league historical away scoring rate prior to cutoff. |
| `home_defense_strength_v1` | `1.0.0` | STRENGTH | `FLOAT` | 1 home match | **Yes** | Home team home goal concession rate relative to league away scoring rate. |
| `away_defense_strength_v1` | `1.0.0` | STRENGTH | `FLOAT` | 1 away match | **Yes** | Away team away goal concession rate relative to league home scoring rate. |
| `home_recent_ppg_v1` | `1.0.0` | FORM | `FLOAT` | 1 match | **Yes** | Rolling Points-Per-Game for home team over recent N matches (default: 5). |
| `away_recent_ppg_v1` | `1.0.0` | FORM | `FLOAT` | 1 match | **Yes** | Rolling Points-Per-Game for away team over recent N matches (default: 5). |
| `home_recent_goals_scored_v1` | `1.0.0` | FORM | `INTEGER` | 1 match | **Yes** | Goals scored by home team over recent N matches (default: 5). |
| `away_recent_goals_conceded_v1` | `1.0.0` | FORM | `INTEGER` | 1 match | **Yes** | Goals conceded by away team over recent N matches (default: 5). |
| `home_elo_v1` | `1.0.0` | ELO | `FLOAT` | 0 matches | **Yes** | Pre-match Elo rating of home team strictly before cutoff ($R_0=1500, K=32$). |
| `away_elo_v1` | `1.0.0` | ELO | `FLOAT` | 0 matches | **Yes** | Pre-match Elo rating of away team strictly before cutoff ($R_0=1500, K=32$). |
| `elo_difference_v1` | `1.0.0` | ELO | `FLOAT` | 0 matches | **Yes** | Pre-match Elo difference incorporating home advantage ($R_H + 100.0 - R_A$). |
| `home_rest_days_v1` | `1.0.0` | REST | `FLOAT` | 1 match | **Yes** | Days of rest for home team since previous match prior to cutoff. |
| `away_rest_days_v1` | `1.0.0` | REST | `FLOAT` | 1 match | **Yes** | Days of rest for away team since previous match prior to cutoff. |
| `rest_days_difference_v1` | `1.0.0` | REST | `FLOAT` | 1 match | **Yes** | Difference in rest days ($\text{Home Rest Days} - \text{Away Rest Days}$). |
| `home_matches_last_14d_v1` | `1.0.0` | CONGESTION| `INTEGER` | 0 matches | **Yes** | Matches played by home team in the 14 days prior to cutoff. |
| `away_matches_last_14d_v1` | `1.0.0` | CONGESTION| `INTEGER` | 0 matches | **Yes** | Matches played by away team in the 14 days prior to cutoff. |

---

## 4. Mathematical Formulas & Definitions

### 1. Goals Attack Strength
$$\text{home\_attack\_strength} = \frac{\text{home\_goals\_scored\_per\_home\_match}}{\text{league\_home\_goals\_per\_match}}$$
$$\text{away\_attack\_strength} = \frac{\text{away\_goals\_scored\_per\_away\_match}}{\text{league\_away\_goals\_per\_match}}$$

### 2. Goals Defensive Concession Strength
$$\text{home\_defense\_strength} = \frac{\text{home\_goals\_conceded\_per\_home\_match}}{\text{league\_away\_goals\_per\_match}}$$
$$\text{away\_defense\_strength} = \frac{\text{away\_goals\_conceded\_per\_away\_match}}{\text{league\_home\_goals\_per\_match}}$$
*(Note: A defensive strength $> 1.0$ indicates conceding goals at a higher rate than the league average).*

### 3. Chronological Elo Rating Update
$$E_H = \frac{1}{1 + 10^{(R_A - (R_H + 100.0)) / 400.0}}$$
$$R_H' = R_H + 32 \times (S_H - E_H)$$
$$R_A' = R_A + 32 \times (S_A - E_A)$$

---

## 5. Cutoff Enforcement & Missingness Policy

1. **Mandatory Cutoff Parameter:** Every historical query requires an explicit `cutoff_timestamp`.
2. **Target Match Exclusion:** Target match $M$ is excluded from its own pre-match feature calculation.
3. **Missing Value Handling:** Missing features return `is_missing=True` and `value=None` rather than inventing artificial zeros. Fallback priors (e.g. $1.0$ for strength, $1500.0$ for Elo) are recorded in calculation metadata.
