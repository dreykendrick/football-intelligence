# Feature Engineering Architecture & Point-in-Time Foundation (Sprint 3.1)

## 1. Executive Summary

The **Feature Engineering Architecture** converts historical matches into pre-match statistical state vectors strictly bounded by point-in-time cutoffs.

The core scientific question answered for every target match $M$ at time $T$ is:

> *What information about the home and away teams was genuinely available immediately before this match?*

---

## 2. Target Data Flow Architecture

```text
APPROVED HISTORICAL DATASET RELEASE (mvp_a_historical_v1)
                    │
                    ▼
      HistoricalDatasetQueryService
                    │
                    ▼
       PointInTimeQueryService (Cutoff & DATE_ONLY Scoping)
                    │
                    ▼
            FeatureRegistry
                    │
     ┌──────────────┼──────────────┐
     │              │              │
    Form        Strength          Elo
     │              │              │
   Goals        Home/Away     Rest/Schedule
     └──────────────┼──────────────┘
                    │
                    ▼
          FeatureCalculationResult
                    │
                    ▼
   FeatureSnapshotFingerprintCalculator
                    │
                    ▼
  Immutable FeatureSnapshot (PostgreSQL JSON)
```

---

## 3. Approved Dataset Release Dependency

Feature calculations operate exclusively against **APPROVED** historical dataset releases (`mvp_a_historical_v1`).

Un-gated queries (`SELECT * FROM matches`) are forbidden in predictive feature code. Every feature snapshot records scientific provenance:

- `dataset_release_id`
- `dataset_key`
- `dataset_version`
- `dataset_fingerprint`
- `feature_set_name`
- `feature_set_version`
- `fingerprint_sha256`

---

## 4. Cutoff Policy & DATE_ONLY Precision Rules

For a target match $M$ at time $T$:
- **Strict Timestamp Cutoff:** Only matches with `kickoff_utc < T` are queried.
- **Same-Day Exclusion Rule:** When source timestamps carry `DATE_ONLY` precision (or sub-day kickoff ordering is unverified), matches occurring on the exact same date as $M$'s kickoff date are conservatively excluded (`historical_match_date < target_match_date`).
- **Target Match Isolation:** $M$ itself is explicitly excluded from historical query sets (`match_id != target_match_id`).

---

## 5. Explicit Missingness & Sample-Size Policy

Missing data is represented explicitly via `MissingnessReason`:

1. `AVAILABLE`: Valid calculated value.
2. `INSUFFICIENT_HISTORY`: Insufficient prior matches available (e.g. 0 prior matches for a team).
3. `SOURCE_FIELD_UNAVAILABLE`: Raw statistic not captured in historical source (e.g. xG).
4. `DATE_PRECISION_LIMITATION`: Excluded due to same-day date precision limitation.
5. `NOT_APPLICABLE`: Non-applicable feature state.

Missing values are stored as explicit `None` values rather than fabricated zeros.
