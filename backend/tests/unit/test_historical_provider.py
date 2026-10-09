"""
Unit Tests for Football-Data.co.uk Provider & Manifest Loader
Verifies URL resolution, competition/season formatting, header validation, and manifest specifications.
"""
import os
import tempfile

import pytest

from app.providers.historical.football_data_uk import FootballDataUKProvider
from app.providers.historical.manifest import HistoricalManifestLoader


@pytest.mark.unit
def test_season_code_formatting():
    assert FootballDataUKProvider.format_season_code("2023-24") == "2324"
    assert FootballDataUKProvider.format_season_code("2021/22") == "2122"


@pytest.mark.unit
def test_competition_code_formatting():
    assert FootballDataUKProvider.format_competition_code("EPL") == "E0"
    assert FootballDataUKProvider.format_competition_code("LA_LIGA") == "SP1"
    assert FootballDataUKProvider.format_competition_code("SERIE_A") == "I1"
    assert FootballDataUKProvider.format_competition_code("BUNDESLIGA") == "D1"


@pytest.mark.unit
def test_url_resolution():
    provider = FootballDataUKProvider()
    url = provider.resolve_source_url("EPL", "2023-24")
    assert url == "https://www.football-data.co.uk/mmz4281/2324/E0.csv"


@pytest.mark.unit
def test_manifest_loader_specifications():
    specs = HistoricalManifestLoader.load_manifest()
    assert len(specs) == 12
    epl_specs = [s for s in specs if s.competition_code == "EPL"]
    assert len(epl_specs) == 3
    assert epl_specs[0].source_url == "https://www.football-data.co.uk/mmz4281/2122/E0.csv"


@pytest.mark.unit
def test_csv_file_header_validation():
    provider = FootballDataUKProvider()

    # Valid CSV temp file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,3,A\n")
        temp_path = f.name

    try:
        val = provider.validate_source_file(temp_path)
        assert val.is_valid is True
        assert val.file_size_bytes > 0
        assert val.schema_fingerprint is not None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.unit
def test_csv_file_missing_headers_rejected():
    provider = FootballDataUKProvider()

    # Invalid CSV missing FTHG
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write("Div,Date,HomeTeam,AwayTeam,FTR\nE0,11/08/2023,Burnley,Man City,A\n")
        temp_path = f.name

    try:
        val = provider.validate_source_file(temp_path)
        assert val.is_valid is False
        assert "Missing required CSV header columns" in val.error_message
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
