"""
Football-Data.co.uk Configuration & Mapping Specifications
Defines required headers, optional headers, league code maps, and bookmaker odds exclusion lists.
"""
from __future__ import annotations

# Mapping Football-Data.co.uk Division Codes to Canonical Competition Codes
FOOTBALL_DATA_LEAGUE_MAP: dict[str, str] = {
    "E0": "E0",
    "SP1": "SP1",
    "I1": "I1",
    "D1": "D1",
    "EPL": "E0",
    "PREMIER_LEAGUE": "E0",
    "PREM": "E0",
    "LA_LIGA": "SP1",
    "LALIGA": "SP1",
    "SERIE_A": "I1",
    "SERIEA": "I1",
    "BUNDESLIGA": "D1",
}

# Required Headers in Football-Data.co.uk CSV files
REQUIRED_HEADERS: set[str] = {
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
}

# Optional Match Statistics Column Mapping (CSV Column -> DTO Attribute)
OPTIONAL_STATS_MAP: dict[str, str] = {
    "HTHG": "half_time_home_goals",
    "HTAG": "half_time_away_goals",
    "HTR": "half_time_result",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
}

# Bookmaker Odds Column Prefixes / Identifiers (Explicitly Excluded from Domain Models)
BOOKMAKER_ODDS_PREFIXES: tuple[str, ...] = (
    "B365", "BS", "BW", "GB", "IW", "LB", "PS", "SO", "SB", "SJ", "VC", "WH", "P", "Max", "Avg", "Bb"
)
