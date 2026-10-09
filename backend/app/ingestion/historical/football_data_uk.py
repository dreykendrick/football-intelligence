"""
Football-Data.co.uk Historical Provider Adapter
Parses, validates, and transforms raw CSV datasets into structured RawMatchRowDTO payloads.
"""
from __future__ import annotations

import csv
import hashlib
import os
from datetime import UTC, datetime
from typing import Any

from app.ingestion.base import (
    HistoricalFootballProvider,
    HistoricalProviderBatchResultDTO,
    RawMatchRowDTO,
)
from app.ingestion.historical.config import (
    FOOTBALL_DATA_LEAGUE_MAP,
    OPTIONAL_STATS_MAP,
    REQUIRED_HEADERS,
)


class FootballDataUKProvider(HistoricalFootballProvider):
    """Adapter for Football-Data.co.uk historical CSV files."""

    provider_key: str = "football_data_co_uk"

    def parse_file(
        self, file_path: str, competition_override: str | None = None, season_override: str | None = None
    ) -> HistoricalProviderBatchResultDTO:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")

        checksum = self._calculate_sha256(file_path)
        rows, headers = self._read_csv_rows(file_path)

        # Header Validation
        missing_headers = REQUIRED_HEADERS - set(headers)
        if missing_headers:
            raise ValueError(f"Missing required CSV headers: {sorted(missing_headers)}")

        valid_rows: list[RawMatchRowDTO] = []
        invalid_rows: list[dict[str, Any]] = []
        warnings: list[str] = []

        # Determine Competition Code
        file_div = self._extract_div_from_rows(rows, headers)
        comp_code = self._resolve_competition_code(file_div, file_path, competition_override)

        # Determine Season Label
        season_label = self._resolve_season_label(file_path, season_override)

        for index, row in enumerate(rows, start=2):  # 1-indexed row numbers (row 1 is header)
            if not any(row.values()):  # Skip completely empty rows
                continue

            try:
                dto = self._parse_row(row, index, comp_code, season_label)
                valid_rows.append(dto)
            except Exception as e:
                invalid_rows.append({
                    "row_index": index,
                    "raw_data": row,
                    "error": str(e),
                })
                warnings.append(f"Row {index} skipped: {e}")

        return HistoricalProviderBatchResultDTO(
            provider_key=self.provider_key,
            source_reference=os.path.basename(file_path),
            checksum=checksum,
            total_rows=len(rows),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            validation_warnings=warnings,
        )

    def _calculate_sha256(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _read_csv_rows(self, file_path: str) -> tuple[list[dict[str, str]], list[str]]:
        encodings = ["utf-8-sig", "latin-1", "utf-8"]
        for enc in encodings:
            try:
                with open(file_path, encoding=enc) as f:
                    reader = csv.DictReader(f)
                    headers = [h.strip() for h in (reader.fieldnames or []) if h]
                    rows = [{k.strip(): v.strip() for k, v in row.items() if k} for row in reader]
                    return rows, headers
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("utf-8", b"", 0, 1, f"Unable to decode file {file_path} with supported encodings.")

    def _extract_div_from_rows(self, rows: list[dict[str, str]], headers: list[str]) -> str | None:
        if "Div" in headers:
            for row in rows:
                div = row.get("Div")
                if div:
                    return div.strip()
        return None

    def _resolve_competition_code(
        self, file_div: str | None, file_path: str, override: str | None
    ) -> str:
        if override:
            return FOOTBALL_DATA_LEAGUE_MAP.get(override.upper(), override.upper())
        if file_div and file_div in FOOTBALL_DATA_LEAGUE_MAP:
            return FOOTBALL_DATA_LEAGUE_MAP[file_div]

        # Deduce from filename or folder path (e.g. E0.csv or premier_league)
        base_name = os.path.splitext(os.path.basename(file_path))[0].upper()
        if base_name in FOOTBALL_DATA_LEAGUE_MAP:
            return FOOTBALL_DATA_LEAGUE_MAP[base_name]

        path_parts = file_path.replace("\\", "/").upper().split("/")
        for part in path_parts:
            if part in FOOTBALL_DATA_LEAGUE_MAP:
                return FOOTBALL_DATA_LEAGUE_MAP[part]

        raise ValueError(f"Unable to resolve competition code from file {file_path}. Specify --competition.")

    def _resolve_season_label(self, file_path: str, override: str | None) -> str:
        if override:
            return self._normalize_season_string(override)

        # Attempt extraction from filename/path e.g. 2023-24.csv or 2324/E0.csv
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        if len(base_name) == 4 and base_name.isdigit():  # e.g. 2324
            return f"20{base_name[:2]}/20{base_name[2:]}"

        path_parts = file_path.replace("\\", "/").split("/")
        for part in reversed(path_parts):
            clean_part = os.path.splitext(part)[0]
            if "-" in clean_part or "/" in clean_part or len(clean_part) == 4:
                try:
                    return self._normalize_season_string(clean_part)
                except ValueError:
                    continue

        return "UNKNOWN_SEASON"

    def _normalize_season_string(self, s: str) -> str:
        s = s.strip().replace("-", "/")
        if len(s) == 4 and s.isdigit():  # e.g., 2324 -> 2023/2024
            return f"20{s[:2]}/20{s[2:]}"
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 2:
                y1 = parts[0].strip()
                y2 = parts[1].strip()
                if len(y1) == 2:
                    y1 = f"20{y1}"
                if len(y2) == 2:
                    y2 = f"20{y2}"
                return f"{y1}/{y2}"
        return s

    def _parse_row(
        self, row: dict[str, str], row_index: int, comp_code: str, season_label: str
    ) -> RawMatchRowDTO:
        home_team = row.get("HomeTeam", "").strip()
        away_team = row.get("AwayTeam", "").strip()

        if not home_team or not away_team:
            raise ValueError(f"Missing HomeTeam or AwayTeam at row {row_index}")

        if home_team == away_team:
            raise ValueError(f"HomeTeam and AwayTeam are identical ('{home_team}') at row {row_index}")

        date_str = row.get("Date", "").strip()
        if not date_str:
            raise ValueError(f"Missing Date at row {row_index}")

        match_date = self._parse_date(date_str)

        try:
            fthg = int(row.get("FTHG", ""))
            ftag = int(row.get("FTAG", ""))
        except ValueError as err:
            raise ValueError(f"Invalid full-time score (FTHG='{row.get('FTHG')}', FTAG='{row.get('FTAG')}') at row {row_index}") from err

        if fthg < 0 or ftag < 0:
            raise ValueError(f"Negative score goals (FTHG={fthg}, FTAG={ftag}) at row {row_index}")

        ftr = row.get("FTR", "").strip().upper()
        if ftr not in ("H", "D", "A"):
            raise ValueError(f"Invalid full-time result FTR='{ftr}' at row {row_index}")

        # Validate Score-Result Consistency
        if fthg > ftag and ftr != "H":
            raise ValueError(f"Score-Result mismatch: FTHG={fthg} > FTAG={ftag} but FTR='{ftr}' at row {row_index}")
        if fthg < ftag and ftr != "A":
            raise ValueError(f"Score-Result mismatch: FTHG={fthg} < FTAG={ftag} but FTR='{ftr}' at row {row_index}")
        if fthg == ftag and ftr != "D":
            raise ValueError(f"Score-Result mismatch: FTHG={fthg} == FTAG={ftag} but FTR='{ftr}' at row {row_index}")

        # Optional Statistics Parsing
        opt_stats: dict[str, Any] = {}
        for csv_col, dto_field in OPTIONAL_STATS_MAP.items():
            val = row.get(csv_col, "").strip()
            if val != "":
                if dto_field == "half_time_result":
                    opt_stats[dto_field] = val.upper() if val.upper() in ("H", "D", "A") else None
                else:
                    try:
                        parsed_val = int(val)
                        opt_stats[dto_field] = parsed_val if parsed_val >= 0 else None
                    except ValueError:
                        opt_stats[dto_field] = None

        # Validate shots on target <= total shots
        if opt_stats.get("home_shots") is not None and opt_stats.get("home_shots_on_target") is not None:
            if opt_stats["home_shots_on_target"] > opt_stats["home_shots"]:
                opt_stats["home_shots_on_target"] = None

        if opt_stats.get("away_shots") is not None and opt_stats.get("away_shots_on_target") is not None:
            if opt_stats["away_shots_on_target"] > opt_stats["away_shots"]:
                opt_stats["away_shots_on_target"] = None

        return RawMatchRowDTO(
            source_row_index=row_index,
            competition_code=comp_code,
            season_year=season_label,
            match_date=match_date,
            date_precision="DATE_ONLY",
            home_team_raw=home_team,
            away_team_raw=away_team,
            full_time_home_goals=fthg,
            full_time_away_goals=ftag,
            full_time_result=ftr,
            raw_payload=dict(row),
            **opt_stats,
        )

    def _parse_date(self, date_str: str) -> datetime:
        formats = [
            "%d/%m/%Y",
            "%d/%m/%y",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d-%m-%y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=2000 + dt.year if dt.year < 50 else 1900 + dt.year)
                return dt.replace(hour=12, minute=0, second=0, tzinfo=UTC)
            except ValueError:
                continue
        raise ValueError(f"Unrecognized date format: '{date_str}'")
