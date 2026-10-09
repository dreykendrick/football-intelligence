# Historical Data Source Integration Architecture — Sprint 2.1

## 1. Overview

Sprint 2.1 establishes the provider-independent historical source acquisition and verification layer for the **Football Intelligence & Probability Analysis System**.

It answers:

> Where did our historical football data come from, exactly which files do we possess, which competition and season does each file represent, when was it acquired, and can we prove the source file has not silently changed?

---

## 2. Architecture & Data Flow

```
[ Football-Data.co.uk Source ]
              │
              ▼
[ HistoricalDataProvider Adapter ] (URL resolution & competition/season mappings)
              │
              ▼
[ HistoricalSourceAcquisitionService ] (Atomic download stream -> .tmp -> CSV validation -> SHA-256)
              │
              ▼
[ Raw Storage & Catalog ] (data/raw/football_data_uk/{comp}/{season}/{code}.csv + IngestionBatch DB)
              │
              ▼
[ Source Coverage Gate ] (SourceCoverageGate.assert_required_historical_sources_available())
```

---

## 3. Provider Configuration & Mappings

* **Provider Key:** `football_data_uk`
* **Base URL:** `https://www.football-data.co.uk/mmz4281`
* **Target Competition Mappings:**
  - `EPL` $\rightarrow$ `E0` (English Premier League)
  - `LA_LIGA` $\rightarrow$ `SP1` (La Liga)
  - `SERIE_A` $\rightarrow$ `I1` (Serie A)
  - `BUNDESLIGA` $\rightarrow$ `D1` (Bundesliga)
* **Season Formatting:**
  - `2021-22` $\rightarrow$ `2122`
  - `2022-23` $\rightarrow$ `2223`
  - `2023-24` $\rightarrow$ `2324`

---

## 4. Minimum Source Coverage Manifest (`manifest.yaml`)

The target MVP-A coverage manifest requires **12 datasets minimum**:

| Competition | Season | Provider Code | Source URL | Required |
|---|---|---|---|---|
| `EPL` | `2021-22` | `E0` | `https://www.football-data.co.uk/mmz4281/2122/E0.csv` | Yes |
| `EPL` | `2022-23` | `E0` | `https://www.football-data.co.uk/mmz4281/2223/E0.csv` | Yes |
| `EPL` | `2023-24` | `E0` | `https://www.football-data.co.uk/mmz4281/2324/E0.csv` | Yes |
| `LA_LIGA` | `2021-22` | `SP1` | `https://www.football-data.co.uk/mmz4281/2122/SP1.csv` | Yes |
| `LA_LIGA` | `2022-23` | `SP1` | `https://www.football-data.co.uk/mmz4281/2223/SP1.csv` | Yes |
| `LA_LIGA` | `2023-24` | `SP1` | `https://www.football-data.co.uk/mmz4281/2324/SP1.csv` | Yes |
| `SERIE_A` | `2021-22` | `I1` | `https://www.football-data.co.uk/mmz4281/2122/I1.csv` | Yes |
| `SERIE_A` | `2022-23` | `I1` | `https://www.football-data.co.uk/mmz4281/2223/I1.csv` | Yes |
| `SERIE_A` | `2023-24` | `I1` | `https://www.football-data.co.uk/mmz4281/2324/I1.csv` | Yes |
| `BUNDESLIGA` | `2021-22` | `D1` | `https://www.football-data.co.uk/mmz4281/2122/D1.csv` | Yes |
| `BUNDESLIGA` | `2022-23` | `D1` | `https://www.football-data.co.uk/mmz4281/2223/D1.csv` | Yes |
| `BUNDESLIGA` | `2023-24` | `D1` | `https://www.football-data.co.uk/mmz4281/2324/D1.csv` | Yes |

---

## 5. Developer CLI Commands

```bash
# 1. List manifest target sources
python scripts/historical_sources.py list

# 2. Display local raw source file status
python scripts/historical_sources.py status

# 3. Simulate acquiring all required sources (dry-run)
python scripts/historical_sources.py acquire-required --dry-run

# 4. Acquire single source file
python scripts/historical_sources.py acquire --competition EPL --season 2023-24

# 5. Run Source Coverage Gate assertion
python scripts/historical_sources.py verify
```
