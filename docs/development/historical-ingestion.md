# Historical Data Ingestion & Provider Architecture — Sprint 1.3

## 1. Overview

Sprint 1.3 implements the **Football-Data.co.uk** historical CSV data pipeline for MVP-A.

The ingestion pipeline converts raw CSV datasets into clean canonical PostgreSQL database records (`Competition`, `Season`, `Team`, `Match`, `MatchStatistic`) while preserving full raw provenance, enforcing team alias resolution, excluding bookmaker odds from predictive tables, and ensuring idempotent re-import execution.

---

## 2. Ingestion Pipeline Architecture

```
[ Football-Data.co.uk CSV File ]
               │
               ▼
[ FootballDataUKProvider ] (Header & Date Validation, CSV Parser)
               │
               ▼
[ RawMatchRowDTO ] (Structured raw data container)
               │
               ▼
[ DataNormalizer ] (Canonical identity resolution: Competition, Season, Team, Deterministic Key)
               │
               ▼
[ HistoricalIngestionPipeline ] (SHA-256 Checksum, IngestionBatch, RawSourceRecord, Transaction Commit)
               │
               ▼
[ PostgreSQL Database ] (Canonical domain entities & audit trail)
```

---

## 3. Directory Layout & Organization

Raw historical CSV files are stored in the project repository under `data/raw/football_data_uk/`:

```text
data/raw/football_data_uk/
├── premier_league/
│   ├── 2021-22.csv
│   ├── 2022-23.csv
│   └── 2023-24.csv
├── la_liga/
│   ├── 2021-22.csv
│   ├── 2022-23.csv
│   └── 2023-24.csv
├── serie_a/
│   ├── 2021-22.csv
│   ├── 2022-23.csv
│   └── 2023-24.csv
└── bundesliga/
    ├── 2021-22.csv
    ├── 2022-23.csv
    └── 2023-24.csv
```

---

## 4. Source Field Mapping Specification

| Football-Data.co.uk Header | Canonical DTO Attribute | Required? | Description / Transformation |
|---|---|---|---|
| `Div` | `competition_code` | Derived | Division code (`E0` $\rightarrow$ `EPL`, `SP1` $\rightarrow$ `LALIGA`, `I1` $\rightarrow$ `SERIEA`, `D1` $\rightarrow$ `BUNDESLIGA`) |
| `Date` | `match_date` | **Yes** | Parsed into UTC timestamp (`dd/mm/yyyy` or `dd/mm/yy`), defaulted to `12:00:00 UTC` (`DATE_ONLY`) |
| `HomeTeam` | `home_team_raw` | **Yes** | Raw home team name string resolved via `team_alias_mappings` |
| `AwayTeam` | `away_team_raw` | **Yes** | Raw away team name string resolved via `team_alias_mappings` |
| `FTHG` | `full_time_home_goals` | **Yes** | Full-time home score ($\ge 0$) |
| `FTAG` | `full_time_away_goals` | **Yes** | Full-time away score ($\ge 0$) |
| `FTR` | `full_time_result` | **Yes** | Full-time result code (`H` = Home win, `D` = Draw, `A` = Away win) |
| `HTHG` | `half_time_home_goals` | Optional | Half-time home score |
| `HTAG` | `half_time_away_goals` | Optional | Half-time away score |
| `HTR` | `half_time_result` | Optional | Half-time result code (`H`, `D`, `A`) |
| `HS` | `home_shots` | Optional | Home team total shots |
| `AS` | `away_shots` | Optional | Away team total shots |
| `HST` | `home_shots_on_target` | Optional | Home team shots on target |
| `AST` | `away_shots_on_target` | Optional | Away team shots on target |
| `HC` | `home_corners` | Optional | Home team corner kicks |
| `AC` | `away_corners` | Optional | Away team corner kicks |
| `HF` | `home_fouls` | Optional | Home team fouls committed |
| `AF` | `away_fouls` | Optional | Away team fouls committed |
| `HY` | `home_yellow_cards` | Optional | Home team yellow cards |
| `AY` | `away_yellow_cards` | Optional | Away team yellow cards |
| `HR` | `home_red_cards` | Optional | Home team red cards |
| `AR` | `away_red_cards` | Optional | Away team red cards |

---

## 5. Bookmaker Odds Exclusion Policy

> [!IMPORTANT]
> Raw CSV columns containing betting odds (`B365H`, `B365D`, `B365A`, `PSH`, `PSD`, `PSA`, `MaxH`, `AvgH`, etc.) are preserved **only** within raw JSON payloads inside `raw_source_records` for historical auditability.
> 
> They are **strictly excluded** from canonical `Match`, `MatchStatistic`, and future feature snapshot calculations. The core probability prediction engine is 100% independent from bookmaker odds.

---

## 6. Team & Match Identity Resolution

### Team Identity Strategy
When an incoming row presents a raw team alias (e.g. `"Man United"`):
1. Normalizes string casing and whitespace.
2. Checks `team_alias_mappings` for `(provider_name="football_data_co_uk", raw_alias="Man United")`.
3. If mapped, returns the canonical `Team` ID.
4. If unmapped, creates a new canonical `Team` and inserts a new `TeamAliasMapping` entry.

### Match Identity & Idempotency Strategy
Each match is assigned a deterministic external key:
`football_data_co_uk:{comp_code}:{season_year}:{date}:{home_canonical}:{away_canonical}`

On re-importing the same CSV file:
- The importer computes the SHA-256 file checksum.
- Lookup in `provider_match_mappings` detects existing matches.
- Existing matches are recognized and cleanly skipped (0 new rows inserted).
- Summary report returns `Inserted: 0 | Existing: N | Status: COMPLETED`.

---

## 7. Developer CLI Commands

### Import Single CSV File
```bash
python scripts/import_historical.py import-file \
  --path data/raw/football_data_uk/premier_league/2023-24.csv \
  --competition EPL \
  --season 2023/24
```

### Dry-Run File Import (Validation Only)
```bash
python scripts/import_historical.py import-file \
  --path data/raw/football_data_uk/la_liga/2023-24.csv \
  --dry-run
```

### Bulk Import Entire Directory
```bash
python scripts/import_historical.py import-dir \
  --path data/raw/football_data_uk
```

### Historical Coverage Report
```bash
python scripts/import_historical.py coverage-report
```
