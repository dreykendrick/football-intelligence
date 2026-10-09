"""
Football-Data.co.uk Historical Provider Adapter
Implements URL resolution, competition/season mapping, and CSV structural validation for Football-Data.co.uk.
"""
from __future__ import annotations

import csv
import hashlib
import os
from typing import ClassVar

from app.providers.historical.base import HistoricalDataProvider, SourceValidationResult


class FootballDataUKProvider(HistoricalDataProvider):
    """Historical data provider implementation for Football-Data.co.uk."""

    provider_key: str = "football_data_uk"
    display_name: str = "Football-Data.co.uk"
    base_url: str = "https://www.football-data.co.uk/mmz4281"

    COMPETITION_MAPPING: ClassVar[dict[str, str]] = {
        "EPL": "E0",
        "PREM": "E0",
        "LA_LIGA": "SP1",
        "LALIGA": "SP1",
        "SERIE_A": "I1",
        "BUNDESLIGA": "D1",
    }

    REQUIRED_HEADERS: ClassVar[set[str]] = {
        "Date",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
    }

    @classmethod
    def format_season_code(cls, season_year: str) -> str:
        """Translates canonical season (e.g. '2023-24' or '2023/24') to provider code '2324'."""
        clean_season = season_year.replace("/", "-").strip()
        parts = clean_season.split("-")
        if len(parts) == 2:
            s1 = parts[0][-2:]
            s2 = parts[1][-2:]
            return f"{s1}{s2}"
        raise ValueError(f"Invalid season_year format: {season_year}")

    @classmethod
    def format_competition_code(cls, competition_code: str) -> str:
        """Translates canonical competition code (e.g. 'EPL') to provider code 'E0'."""
        code = competition_code.upper().strip()
        if code in cls.COMPETITION_MAPPING:
            return cls.COMPETITION_MAPPING[code]
        # Return code as-is if already provider format
        return code

    def resolve_source_url(self, competition_code: str, season_year: str) -> str:
        provider_comp = self.format_competition_code(competition_code)
        provider_season = self.format_season_code(season_year)
        return f"{self.base_url}/{provider_season}/{provider_comp}.csv"

    def validate_source_file(self, file_path: str) -> SourceValidationResult:
        if not os.path.exists(file_path):
            return SourceValidationResult(is_valid=False, error_message=f"File does not exist: {file_path}")

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return SourceValidationResult(is_valid=False, error_message="Source file is 0 bytes (empty file)")

        try:
            with open(file_path, encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                try:
                    headers = next(reader)
                except StopIteration:
                    return SourceValidationResult(is_valid=False, error_message="File is empty or contains no CSV header row")

            headers_clean = [h.strip() for h in headers if h.strip()]
            header_set = set(headers_clean)

            # Detect HTML response masquerading as 200 OK
            if headers_clean and any("<html" in h.lower() or "<!doctype" in h.lower() for h in headers_clean):
                return SourceValidationResult(is_valid=False, error_message="File contains HTML error page instead of valid CSV dataset")

            missing = self.REQUIRED_HEADERS - header_set
            if missing:
                return SourceValidationResult(
                    is_valid=False,
                    error_message=f"Missing required CSV header columns: {', '.join(sorted(missing))}",
                    file_size_bytes=file_size,
                    header_columns=headers_clean,
                )

            # Compute schema fingerprint over header structure
            schema_str = ",".join(headers_clean)
            schema_fingerprint = hashlib.sha256(schema_str.encode("utf-8")).hexdigest()

            return SourceValidationResult(
                is_valid=True,
                file_size_bytes=file_size,
                header_columns=headers_clean,
                schema_fingerprint=schema_fingerprint,
            )
        except Exception as e:
            return SourceValidationResult(is_valid=False, error_message=f"Failed to parse CSV header: {e}")
