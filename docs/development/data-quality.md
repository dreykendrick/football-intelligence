# Data Validation & Quality Controls Architecture — Sprint 1.4

## 1. Overview

Sprint 1.4 establishes a scientific validation and data-quality layer between raw historical data ingestion and downstream feature engineering/predictive modeling.

The primary objective is to evaluate historical PostgreSQL data to answer:

> Can we scientifically trust the historical data stored in PostgreSQL enough to generate features and run backtests?

---

## 2. Architecture & Data Flow

```
[ PostgreSQL Historical Database ]
               │
               ▼
[ DataQualityEngine ] (Executes Structural, Domain & Analytical Validation Rules)
               │
               ▼
[ DataQualityLog Persistence ] (Stores findings with Rule Key, Severity & Resolution Status)
               │
               ▼
[ FeatureReadinessAssessor ] (Calculates Completeness, Chronology, Mapping & Integrity Scores)
               │
               ▼
[ QualityGate ] (Enforces assert_historical_data_ready() & verify_data_leakage_safety())
               │
               ▼
[ Global Quality & Readiness Report ] (READY / READY_WITH_WARNINGS / BLOCKED)
```

---

## 3. Data Quality Severity Classification

| Severity Level | Operational Meaning | Action / Impact |
|---|---|---|
| `INFO` | Observational diagnostic (e.g. `DATE_ONLY` timestamp precision). | Information only; no action required. |
| `WARNING` | Minor data anomaly that does not invalidate modeling (e.g. high goal count). | Review finding; pipeline continues. |
| `ERROR` | Substantial issue affecting modeling quality (e.g. missing shot statistics). | Logged error; affects optional features. |
| `BLOCKING` | Critical data error prohibiting feature engineering and backtesting. | **Fails Quality Gate; feature generation blocked.** |

---

## 4. Complete Quality Rule Registry

| Rule ID | Rule Name | Category | Severity | Blocks Feature Engineering? | Description |
|---|---|---|---|---|---|
| `DQ_MATCH_001` | Finished Match Missing Home Score | DOMAIN | `BLOCKING` | **Yes** | Completed match has `home_score IS NULL`. |
| `DQ_MATCH_002` | Finished Match Missing Away Score | DOMAIN | `BLOCKING` | **Yes** | Completed match has `away_score IS NULL`. |
| `DQ_MATCH_003` | Negative Home Score | DOMAIN | `BLOCKING` | **Yes** | `home_score < 0`. |
| `DQ_MATCH_004` | Negative Away Score | DOMAIN | `BLOCKING` | **Yes** | `away_score < 0`. |
| `DQ_MATCH_005` | Identical Home and Away Teams | DOMAIN | `BLOCKING` | **Yes** | `home_team_id == away_team_id`. |
| `DQ_MATCH_006` | Match Has No Competition | STRUCTURAL | `BLOCKING` | **Yes** | Match lacks competition reference. |
| `DQ_MATCH_007` | Match Has No Season | STRUCTURAL | `BLOCKING` | **Yes** | Match lacks season reference. |
| `DQ_MATCH_008` | Season Competition Mismatch | STRUCTURAL | `BLOCKING` | **Yes** | Season's competition does not match match competition. |
| `DQ_MATCH_009` | Broken Source Provenance | STRUCTURAL | `BLOCKING` | **Yes** | Match has no `ProviderMatchMapping` record. |
| `DQ_MATCH_010` | Result Score Conflict | DOMAIN | `BLOCKING` | **Yes** | Full-time result (`H`/`D`/`A`) disagrees with goals. |
| `DQ_TEAM_001` | Unmapped Provider Team Identity | STRUCTURAL | `ERROR` | No | Team lacks `ProviderTeamMapping` entry. |
| `DQ_TEAM_002` | Suspicious Team Alias Similarity | ANALYTICAL | `WARNING` | No | Candidate duplicate team name similarity ($\ge 0.85$). |
| `DQ_SEASON_001` | Season Match Count Incomplete | ANALYTICAL | `WARNING` | No | Match count deviates from $N \times (N-1)$. |
| `DQ_CHRONO_001` | Non-Chronological Sequence | ANALYTICAL | `ERROR` | No | Match date falls outside reasonable boundaries. |
| `DQ_CHRONO_002` | Date-Only Timestamp Precision | ANALYTICAL | `INFO` | No | Kickoff precision is date-only (12:00 UTC). |
| `DQ_STAT_001` | Shots On Target Exceeds Shots | DOMAIN | `ERROR` | No | `shots_on_target > shots`. |
| `DQ_STAT_002` | Extreme Goal Score Anomaly | DOMAIN | `WARNING` | No | Combined score $\ge 9$ goals. |
| `DQ_DUPLICATE_001` | Suspicious Duplicate Fixture Candidate | ANALYTICAL | `BLOCKING` | **Yes** | Duplicate match key exists for same date and teams. |

---

## 5. Feature Readiness Assessment

| Feature Module | Feature Module Name | Prerequisites | Readiness Status | Source Data Availability |
|---|---|---|---|---|
| `elo_ratings` | Elo Rating System | Match chronology, Canonical Teams, Scores | `READY` | 100.0% |
| `goals_attack_defense` | Goals Attack/Defense Strength | Full-Time Home & Away Goals, Chronology | `READY` | 100.0% |
| `recent_form` | Recent Form (Rolling W/D/L) | Match Chronology, Team Identity, Result | `READY` | 100.0% |
| `rest_days` | Rest Days & Fixture Congestion | Match Dates, Team Resolution | `READY_WITH_WARNINGS` | 100.0% (`DATE_ONLY` precision) |
| `shots_based_features` | Shots & Shots-on-Target | Optional Match Statistics (`HS`, `AS`, `HST`, `AST`) | `READY` | 100.0% (Post-2000 seasons) |
| `provider_xg` | Provider xG Expected Goals | Provider xG Match Statistics | `NOT_READY` | 0.0% (Unavailable in CSV) |

---

## 6. Developer CLI Commands

```bash
# 1. Run quality rules validation across database
python scripts/validate_historical_quality.py validate-historical

# 2. Run quality validation with fail-on-blocking flag
python scripts/validate_historical_quality.py validate-historical --fail-on-blocking

# 3. Output human-readable data quality & readiness report
python scripts/validate_historical_quality.py report

# 4. Output machine-readable JSON quality report
python scripts/validate_historical_quality.py report --format json

# 5. Enforce Quality Gate assertion
python scripts/validate_historical_quality.py check-gate
```
