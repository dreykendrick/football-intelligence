# Modeling Dataset Contract & Post-Match Targets (`mvp_a_modeling_dataset_v1`)

## Overview

The `mvp_a_modeling_dataset_v1` specification establishes the strict boundary between pre-match historical feature vectors and post-match target labels. It forms the official dataset contract consumed by all Phase 4 predictive models.

---

## 1. Approved Dependencies & Invariants

The modeling dataset consumes historical data exclusively from certified upstream releases:

1. **Approved Historical Dataset Release:** `mvp_a_historical:v1` (derived from `Football-Data.co.uk` raw sources with SHA-256 integrity verification).
2. **Frozen Phase 3 Feature Set:** `mvp_a_feature_set_v1` (251 point-in-time feature keys, manifest fingerprint `b66cbdf6faeefbb5`).

No raw database rows, match outcomes, or uncertified feature sets may be accessed directly by Phase 4 models.

---

## 2. Post-Match Target Label Catalog

The target catalog defines 5 standard football target variables derived strictly post-match:

| Target Key | Data Type | Encoding / Values | Description |
| :--- | :--- | :--- | :--- |
| `match_result_1x2_v1` | `int` | `0` = Home Win, `1` = Draw, `2` = Away Win | Standard 3-way match result derived from full-time score |
| `over_under_2_5_v1` | `bool` | `True` = Over 2.5 goals, `False` = Under 2.5 goals | Binary total match goals threshold (`FTAG + FTHG > 2.5`) |
| `btts_v1` | `bool` | `True` = Both teams scored, `False` = Otherwise | Both Teams To Score (`FTHG > 0 and FTAG > 0`) |
| `home_goals_v1` | `int` | Non-negative integer | Full-time home goals scored (`FTHG`) |
| `away_goals_v1` | `int` | Non-negative integer | Full-time away goals scored (`FTAG`) |

---

## 3. Match Eligibility & Qualification Rules

A historical match fixture is included in `mvp_a_modeling_dataset_v1` if and only if it satisfies all of the following criteria:

1. **Match Status:** Status must be `FINISHED` (post-match score recorded).
2. **Score Validity:** Both `full_time_home_goals` (`FTHG`) and `full_time_away_goals` (`FTAG`) must be non-null integers $\ge 0$.
3. **Identity Resolution:** Both home and away team IDs must be canonically resolved with `resolution_status == "RESOLVED"`.
4. **Feature Availability:** A complete point-in-time Phase 3 feature vector (`mvp_a_feature_set_v1`) computed strictly before match kickoff date must exist.

---

## 4. Anti-Leakage Boundary (`assert_feature_label_isolation`)

To prevent target leakage during model training and feature preprocessing:

- **Strict Namespace Isolation:** No feature key inside `FeatureSetVectorDTO` may match or contain any target key (`match_result_1x2_v1`, `over_under_2_5_v1`, `btts_v1`, `home_goals_v1`, `away_goals_v1`) or post-match score outcome (`fthg`, `ftag`, `ftr`, `htg`, `htag`, `htr`).
- **Runtime Guard:** The validation function `assert_feature_label_isolation(feature_keys, target_keys)` is invoked automatically during dataset assembly and raises `ValueError` if any prohibited key is detected.

---

## 5. Dataset Manifest & Fingerprinting

Every generated modeling dataset produces a deterministic `ModelingDatasetManifest` containing:

- `dataset_key`: `mvp_a_modeling_dataset_v1`
- `historical_dataset_release`: `mvp_a_historical:v1`
- `feature_set_manifest_fingerprint`: `b66cbdf6faeefbb5...`
- `total_examples`: Number of eligible modeling rows
- `manifest_fingerprint`: SHA-256 digest of ordered match IDs, target keys, and feature set manifest fingerprint.
