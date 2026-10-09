"""
Unit Tests for Football-Data.co.uk CSV Provider Adapter
Verifies CSV parsing, multi-format date handling, header validation, and score consistency rules.
"""
import os

import pytest

from app.ingestion.historical.football_data_uk import FootballDataUKProvider


@pytest.fixture
def fixtures_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "csv"))


@pytest.mark.unit
def test_parse_valid_epl_sample(fixtures_dir):
    provider = FootballDataUKProvider()
    csv_path = os.path.join(fixtures_dir, "valid_epl_sample.csv")

    result = provider.parse_file(csv_path, competition_override="EPL", season_override="2023/24")

    assert result.provider_key == "football_data_co_uk"
    assert result.total_rows == 5
    assert len(result.valid_rows) == 5
    assert len(result.invalid_rows) == 0

    first_row = result.valid_rows[0]
    assert first_row.home_team_raw == "Burnley"
    assert first_row.away_team_raw == "Man City"
    assert first_row.full_time_home_goals == 0
    assert first_row.full_time_away_goals == 3
    assert first_row.full_time_result == "A"
    assert first_row.home_shots == 6
    assert first_row.away_shots == 17
    assert first_row.match_date.year == 2023
    assert first_row.match_date.month == 8
    assert first_row.match_date.day == 11
    assert first_row.match_date.hour == 12


@pytest.mark.unit
def test_parse_missing_required_column_fails(fixtures_dir):
    provider = FootballDataUKProvider()
    csv_path = os.path.join(fixtures_dir, "missing_required_column.csv")

    with pytest.raises(ValueError, match="Missing required CSV headers"):
        provider.parse_file(csv_path)


@pytest.mark.unit
def test_parse_score_result_mismatch_flags_row(fixtures_dir):
    provider = FootballDataUKProvider()
    csv_path = os.path.join(fixtures_dir, "result_score_mismatch.csv")

    result = provider.parse_file(csv_path, competition_override="EPL", season_override="2023/24")

    assert result.total_rows == 2
    assert len(result.valid_rows) == 1
    assert len(result.invalid_rows) == 1
    assert "Score-Result mismatch" in result.invalid_rows[0]["error"]


@pytest.mark.unit
def test_parse_optional_stats_missing(fixtures_dir):
    provider = FootballDataUKProvider()
    csv_path = os.path.join(fixtures_dir, "optional_stats_missing.csv")

    result = provider.parse_file(csv_path, competition_override="EPL", season_override="2000/01")

    assert len(result.valid_rows) == 2
    row = result.valid_rows[0]
    assert row.home_shots is None
    assert row.home_corners is None
    assert row.full_time_home_goals == 1
    assert row.full_time_away_goals == 3
