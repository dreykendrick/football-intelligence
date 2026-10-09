"""
Integration Tests for Historical Source Acquisition Service
Verifies mocked HTTP downloads, atomic storage, idempotency, source change detection, and path safety.
"""
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.providers.historical.base import SourceSpecification, SourceStatusEnum
from app.providers.historical.service import HistoricalSourceAcquisitionService


@pytest.fixture
def temp_raw_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.integration
def test_mocked_http_acquisition_success(temp_raw_dir, db_session: Session):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    spec = SourceSpecification(
        provider_key="football_data_uk",
        competition_code="EPL",
        season_year="2023-24",
        provider_competition_code="E0",
        provider_season_code="2324",
        source_url="https://www.football-data.co.uk/mmz4281/2324/E0.csv",
    )

    valid_csv = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,3,A\n"

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.side_effect = [valid_csv, b""]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = service.acquire_source(spec, db_session=db_session)

    assert res.status == SourceStatusEnum.ACQUIRED
    assert Path(res.local_path).exists()
    assert res.sha256_checksum is not None


@pytest.mark.integration
def test_mocked_http_acquisition_404_error(temp_raw_dir):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    spec = SourceSpecification(
        provider_key="football_data_uk",
        competition_code="EPL",
        season_year="2023-24",
        provider_competition_code="E0",
        provider_season_code="2324",
        source_url="https://www.football-data.co.uk/mmz4281/2324/INVALID.csv",
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(spec.source_url, 404, "Not Found", None, None)):
        res = service.acquire_source(spec)

    assert res.status == SourceStatusEnum.FAILED
    assert "HTTP download failed" in res.message


@pytest.mark.integration
def test_idempotent_redownload_returns_unchanged(temp_raw_dir):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    spec = SourceSpecification(
        provider_key="football_data_uk",
        competition_code="EPL",
        season_year="2023-24",
        provider_competition_code="E0",
        provider_season_code="2324",
        source_url="https://www.football-data.co.uk/mmz4281/2324/E0.csv",
    )

    valid_csv = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,3,A\n"

    # First acquisition
    mock_resp1 = MagicMock()
    mock_resp1.__enter__.return_value = mock_resp1
    mock_resp1.read.side_effect = [valid_csv, b""]
    with patch("urllib.request.urlopen", return_value=mock_resp1):
        res1 = service.acquire_source(spec)
    assert res1.status == SourceStatusEnum.ACQUIRED

    # Second acquisition with identical content
    mock_resp2 = MagicMock()
    mock_resp2.__enter__.return_value = mock_resp2
    mock_resp2.read.side_effect = [valid_csv, b""]
    with patch("urllib.request.urlopen", return_value=mock_resp2):
        res2 = service.acquire_source(spec, force_download=True)

    assert res2.status == SourceStatusEnum.UNCHANGED
    assert res1.sha256_checksum == res2.sha256_checksum


@pytest.mark.integration
def test_source_change_detection_preserves_original(temp_raw_dir):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    spec = SourceSpecification(
        provider_key="football_data_uk",
        competition_code="EPL",
        season_year="2023-24",
        provider_competition_code="E0",
        provider_season_code="2324",
        source_url="https://www.football-data.co.uk/mmz4281/2324/E0.csv",
    )

    v1_csv = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,3,A\n"
    v2_csv = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,4,A\n"  # Modified score

    # Download v1
    mock_resp1 = MagicMock()
    mock_resp1.__enter__.return_value = mock_resp1
    mock_resp1.read.side_effect = [v1_csv, b""]
    with patch("urllib.request.urlopen", return_value=mock_resp1):
        res1 = service.acquire_source(spec)
    assert res1.status == SourceStatusEnum.ACQUIRED

    # Download v2 (changed content)
    mock_resp2 = MagicMock()
    mock_resp2.__enter__.return_value = mock_resp2
    mock_resp2.read.side_effect = [v2_csv, b""]
    with patch("urllib.request.urlopen", return_value=mock_resp2):
        res2 = service.acquire_source(spec, force_download=True)

    assert res2.status == SourceStatusEnum.CHANGED
    assert "WARNING: Source SHA-256 changed!" in res2.message
    # Verify original file remains intact
    assert Path(res1.local_path).read_bytes() == v1_csv


@pytest.mark.integration
def test_path_traversal_prevention(temp_raw_dir):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    invalid_spec = SourceSpecification(
        provider_key="football_data_uk",
        competition_code="../escaped",
        season_year="2023-24",
        provider_competition_code="E0",
        provider_season_code="2324",
        source_url="https://www.football-data.co.uk/test.csv",
    )

    # Cleaned path basename should prevent escape
    dest_path = service.get_destination_path(invalid_spec)
    assert str(dest_path).startswith(temp_raw_dir)
