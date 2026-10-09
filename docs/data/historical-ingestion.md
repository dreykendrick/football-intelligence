# Historical Data Ingestion Pipeline Architecture — Sprint 2.2

## 1. Overview

Sprint 2.2 converts verified **Football-Data.co.uk** raw historical source CSV files into canonical football records stored in PostgreSQL.

It answers:

> Which source row produced a historical match, which source version was used, how provider-specific values were normalized, how competition, season, and teams were resolved, and how repeat imports avoid creating duplicate football records.

---

## 2. Architecture & Data Flow

```
[ Verified Raw CSV (data/raw/) ]
              │
              ▼
[ FootballDataUKProvider Parser ] (Validates headers & parses row DTOs)
              │
              ▼
[ DataNormalizer & Resolver ] (Competition, Season & Conservative Team Resolution)
              │
              ▼
[ Ingestion Pipeline Orchestrator ] (Handles IngestionBatch, RawSourceRecord audit & ProviderMatchMapping)
              │
              ▼
[ PostgreSQL Canonical Database ] (Match, Team, MatchStatistic, ProviderTeamMapping)
```

---

## 3. CSV Field Mappings & Domain Rules

| Football-Data.co.uk CSV Field | Canonical Concept | Data Type | Validation Policy |
|---|---|---|---|
| `Date` | Match Kickoff Date | `DATETIME` | Required. Defaults to 12:00:00 UTC (`DATE_ONLY`). |
| `Time` | Kickoff Time | `STRING` | Optional. If provided, merged into kickoff timestamp. |
| `HomeTeam` | Home Provider Team | `STRING` | Required. Resolves/creates canonical `Team` & mapping. |
| `AwayTeam` | Away Provider Team | `STRING` | Required. Must be distinct from `HomeTeam`. |
| `FTHG` | Full-time Home Goals | `INTEGER` | Required. Must be $\ge 0$. |
| `FTAG` | Full-time Away Goals | `INTEGER` | Required. Must be $\ge 0$. |
| `FTR` | Full-time Result | `STRING` | Required (`H`/`D`/`A`). Must match goal scores. |
| `HTHG` | Half-time Home Goals | `INTEGER` | Optional. |
| `HTAG` | Half-time Away Goals | `INTEGER` | Optional. |
| `HS` / `AS` | Home / Away Shots | `INTEGER` | Optional. Stored as `NULL` if missing. |
| `HST` / `AST` | Home / Away Shots on Target | `INTEGER` | Optional. Must satisfy $\text{shots\_on\_target} \le \text{total\_shots}$. |
| `HC` / `AC` | Home / Away Corners | `INTEGER` | Optional. |
| `HF` / `AF` | Home / Away Fouls | `INTEGER` | Optional. |
| `HY` / `AY` | Home / Away Yellow Cards | `INTEGER` | Optional. |
| `HR` / `AR` | Home / Away Red Cards | `INTEGER` | Optional. |

---

## 4. Bookmaker Field Exclusion Policy

Football-Data.co.uk CSV files contain numerous bookmaker odds columns (`B365H`, `B365D`, `B365A`, `PSH`, `PSA`, etc.).

* **Raw Evidence Retention:** Odds columns remain preserved inside immutable raw CSV files and `RawSourceRecord` audit JSON payloads.
* **Canonical Persistence Exclusion:** Bookmaker fields are explicitly **ignored** during domain normalization. No bookmaker entities, odds tables, or odds features are persisted in the canonical football model.

---

## 5. Conservative Team Identity Resolution Policy

1. **Provider Mapping Lookup:** Checks existing `ProviderTeamMapping` for `(provider_id, raw_alias)`.
2. **Exact Canonical Match:** Checks exact `canonical_name` in `teams` table.
3. **Conservative Creation:** If unmapped, creates a new `Team` entity and `ProviderTeamMapping` preserving raw alias.
4. **No Automatic Fuzzy Merging:** Similar names (e.g. `Man United` vs `Manchester United`) remain separate entities until reconciled in Sprint 2.3.

---

## 6. Provenance Chain & Auditability

Every canonical historical match preserves a complete audit trail back to the source file:

```text
Canonical Match
       │
       ▼
ProviderMatchMapping (external_match_id)
       │
       ▼
IngestionBatch (batch_id, timestamp, status)
       │
       ▼
RawSourceRecord (raw_payload JSON & source_row_index)
       │
       ▼
Raw File SHA-256 Checksum (data/raw/...)
```

---

## 7. Developer CLI Commands

```bash
# 1. Ingest single historical dataset
python scripts/ingest_historical.py ingest --competition EPL --season 2023-24

# 2. Simulate bulk ingestion (dry-run mode)
python scripts/ingest_historical.py ingest-required --dry-run

# 3. Perform actual bulk ingestion across all 12 required datasets
python scripts/ingest_historical.py ingest-required

# 4. Display recent ingestion batch summary report
python scripts/ingest_historical.py summary
```
