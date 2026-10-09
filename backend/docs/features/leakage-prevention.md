# Data Leakage Prevention & Scientific Integrity Policy

## 1. Core Principle

Data leakage occurs when future information (data after kickoff $T$) leaks into pre-match feature vectors.

In our system:

$$\text{FEATURE}(M, T) \implies \text{All Inputs} \in \{ m \mid \text{event\_time}(m) < T \}$$

---

## 2. Hard Architectural Rules

1. **Target Result Isolation:** The target match's score (`home_score`, `away_score`), result (`FTHG`, `FTAG`, `FTR`), and match statistics (`shots`, `fouls`, `corners`) must NEVER enter its own pre-match feature snapshot.
2. **Future Match Exclusion:** Matches scheduled or played after target cutoff $T$ are excluded by SQL queries in `PointInTimeQueryService`.
3. **No Full-Season Aggregates:** League averages and baselines are computed dynamically using only matches strictly prior to cutoff $T$. Full-season retro-computed league averages are strictly forbidden.
4. **Pre-Match Elo Sequencing:** Target match outcomes update Elo ratings ONLY after the target match's pre-match feature vector is recorded.
5. **No Bookmaker Odds:** Odds columns present in raw source files are preserved for audit purposes only and are forbidden from entering scientific feature definitions.

---

## 3. Adversarial Leakage Verification Suite

Our test suite enforces four automated adversarial leakage tests:

1. `test_target_outcome_isolation`: Altering target match score/result in the database produces identical pre-match feature vectors.
2. `test_same_day_date_only_exclusion`: Matches played on the same date as target date with `DATE_ONLY` precision are excluded.
3. `test_future_match_addition_isolation`: Adding new future matches played after target cutoff does NOT change target feature snapshots.
4. `test_past_match_modification_responsiveness`: Modifying a past match prior to cutoff correctly alters the target feature snapshot.
