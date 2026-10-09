# Raw Historical Data Storage (`data/raw/`)

## Immutability Policy & Guidelines

This directory stores raw historical source CSV files acquired from external data providers (e.g. **Football-Data.co.uk**).

### Rules for Raw Historical Datasets:
1. **Raw Files Are Immutable:** Original downloaded CSV files must never be edited, renamed, re-encoded, or cleaned in place. They serve as unalterable historical evidence.
2. **Bookmaker Odds Retention:** Raw CSV files downloaded from Football-Data.co.uk may contain raw bookmaker odds columns (`B365H`, `B365D`, `B365A`, `PSH`, etc.). These fields remain in raw files as evidence but **MUST NOT** be ingested into predictive feature models or prediction snapshots.
3. **No Direct Model Access:** Predictive algorithms and backtesting engines consume normalized canonical database entities and `FeatureSnapshot` records, never raw CSV files directly.
4. **Git Exclusion:** Raw production CSV files are excluded from Git version control (see `.gitignore`). Developers reconstruct local raw datasets using `python scripts/historical_sources.py acquire-required`.
