# Data Validation & Quality Controls Architecture — Sprint 2.4

## 1. Overview

Sprint 2.4 establishes the scientific historical-data quality layer for the **Football Intelligence & Probability Analysis System**.

It enforces the foundational data quality principle:

> **`INGESTED ≠ VALIDATED ≠ COMPLETE ≠ FEATURE READY`**

A successful ingestion batch is NOT evidence that historical data is scientifically valid or complete. The quality layer audits canonical data across match integrity, result consistency, duplicate detection, identity mapping, season completeness, chronology, and feature readiness.

---

## 2. Quality Architecture & Subsystem Flow

```
[ Canonical PostgreSQL Database ]
               │
               ▼
[ HistoricalDataQualityEngine ]
               │
               ▼
[ Central Quality Rule Registry ] (15+ Deterministic Rules)
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
[Integrity] [Completeness] [Chronology]
   │           │           │
   └───────────┼───────────┘
               ▼
[ Persistent DataQualityLog Findings ] (Fingerprinted Lifecycle: OPEN -> RESOLVED)
               │
               ▼
[ FeatureReadinessAssessor ] (Per-Season Matrix & Feature Module Readiness)
               │
               ▼
[ Quality Readiness Gate ] (assert_historical_data_ready())
```

---

## 3. Quality Rule Catalog

| Rule ID | Name | Category | Severity | Blocks Readiness | Description |
|---|---|---|---|---|---|
| `DQ_MATCH_001` | Finished Match Missing Home Score | `DOMAIN` | `BLOCKING` | Yes | Finished match has NULL `home_score`. |
| `DQ_MATCH_002` | Finished Match Missing Away Score | `DOMAIN` | `BLOCKING` | Yes | Finished match has NULL `away_score`. |
| `DQ_MATCH_003` | Negative Home Score | `DOMAIN` | `BLOCKING` | Yes | Home score is less than zero. |
| `DQ_MATCH_004` | Negative Away Score | `DOMAIN` | `BLOCKING` | Yes | Away score is less than zero. |
| `DQ_MATCH_005` | Identical Home and Away Teams | `DOMAIN` | `BLOCKING` | Yes | `home_team_id` is identical to `away_team_id`. |
| `DQ_MATCH_006` | Match Has No Competition | `STRUCTURAL` | `BLOCKING` | Yes | Match lacks competition reference. |
| `DQ_MATCH_007` | Match Has No Season | `STRUCTURAL` | `BLOCKING` | Yes | Match lacks season reference. |
| `DQ_MATCH_008` | Season Competition Mismatch | `STRUCTURAL` | `BLOCKING` | Yes | Season competition disagrees with match. |
| `DQ_MATCH_009` | Broken Source Provenance | `STRUCTURAL` | `BLOCKING` | Yes | Match lacks `ProviderMatchMapping` / `IngestionBatch`. |
| `DQ_MATCH_010` | Result Score Conflict | `DOMAIN` | `BLOCKING` | Yes | Stored FTR disagrees with scores (`FTHG` vs `FTAG`). |
| `DQ_STAT_001` | Shots On Target Exceeds Total Shots | `DOMAIN` | `ERROR` | No | `shots_on_target > shots` for a team. |
| `DQ_STAT_002` | Extreme Goal Score Anomaly | `DOMAIN` | `WARNING` | No | Combined score $> 9$ goals. |
| `DQ_DUPLICATE_001` | Suspicious Duplicate Fixture | `ANALYTICAL` | `BLOCKING` | Yes | Duplicate competition, season, teams, kickoff date. |
| `DQ_TEAM_001` | Unmapped Provider Team Identity | `STRUCTURAL` | `ERROR` | No | Team lacks `ProviderTeamMapping`. |
| `DQ_TEAM_002` | Team Alias Similarity Candidate | `ANALYTICAL` | `WARNING` | No | High similarity candidate for manual review. |
| `DQ_SEASON_001` | Season Match Count Incomplete | `ANALYTICAL` | `WARNING` | No | Match count deviates from $N \times (N-1)$. |
| `DQ_CHRONO_001` | Non-Chronological Sequence | `ANALYTICAL` | `ERROR` | No | Match date outside reasonable bounds. |
| `DQ_CHRONO_002` | Date-Only Precision | `ANALYTICAL` | `INFO` | No | Date-only precision limitation documented. |

---

## 4. Finding Lifecycle & Fingerprinting

Every detected issue generates a fingerprinted `QualityFinding` persisted to PostgreSQL `data_quality_logs`:
* **Finding Statuses:** `OPEN`, `ACKNOWLEDGED`, `RESOLVED`, `ACCEPTED_LIMITATION`.
* **Idempotency:** Re-evaluating unchanged data updates existing findings by `issue_key` without creating duplicate active records.
* **Automatic Resolution:** When a previously detected issue is corrected in the database, the engine automatically transitions the finding to `RESOLVED`.

---

## 5. Non-Destructive Detection Policy

The quality engine **detects and reports** issues. It **NEVER silently alters or rewrites** canonical historical scores, raw files, or team identities. Corrections must be executed explicitly through ingestion/identity workflows.

---

## 6. Season Completeness Formula

For standard double round-robin leagues:
$$\text{expected\_matches} = N \times (N - 1)$$
where $N$ is the count of unique participating teams in the season:
* 20 Teams (EPL, La Liga, Serie A): $20 \times 19 = 380$ matches.
* 18 Teams (Bundesliga): $18 \times 17 = 306$ matches.

---

## 7. Feature Readiness Mapping

Declarative assessment of historical data readiness for upcoming model feature modules:

| Future Feature Module | Prerequisites | Status | Coverage | Limitations |
|---|---|---|---|---|
| **Elo Rating System** | Match Chronology, Canonical Teams, Result | `READY` | 100.0% | Kickoff times default to 12:00 UTC (`DATE_ONLY`). |
| **Goals Attack/Defense** | Full-Time Home/Away Goals, Chronology | `READY` | 100.0% | None. |
| **Recent Form** | Chronology, Team Identity, Result | `READY` | 100.0% | None. |
| **Rest Days & Congestion** | Match Dates, Canonical Team Resolution | `READY_WITH_WARNINGS` | 100.0% | Date-level resolution (`DATE_ONLY`). |
| **Shots-Based Features** | Optional Match Statistics (`HS`/`AS`/`HST`/`AST`) | `READY` | $> 90.0\%$ | Historical seasons prior to 2000 lack shot stats. |
| **Provider xG** | Provider xG Match Statistics | `NOT_READY` | 0.0% | Football-Data.co.uk CSVs lack provider xG. |

---

## 8. Developer CLI Commands

```bash
# 1. Run full historical quality validation
python scripts/validate_historical_quality.py validate-historical

# 2. Run quality validation and fail on BLOCKING issues (for CI/CD)
python scripts/validate_historical_quality.py validate-historical --fail-on-blocking

# 3. Generate machine-readable JSON quality report
python scripts/validate_historical_quality.py report --format json

# 4. Filter open BLOCKING findings
python scripts/validate_historical_quality.py findings --severity BLOCKING --status OPEN
```
