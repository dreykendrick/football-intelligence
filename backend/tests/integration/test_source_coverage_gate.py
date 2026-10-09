"""
Integration Tests for Source Coverage Gate & Verifier
Verifies SourceCoverageGate assertion logic when historical files exist vs when missing or corrupted.
"""
import tempfile

import pytest

from app.providers.historical.gate import SourceCoverageGate, SourceCoverageGateException
from app.providers.historical.manifest import HistoricalManifestLoader
from app.providers.historical.service import HistoricalSourceAcquisitionService


@pytest.fixture
def temp_raw_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.integration
def test_coverage_gate_fails_when_sources_missing(temp_raw_dir):
    with pytest.raises(SourceCoverageGateException, match="Historical Source Coverage Gate FAILED!"):
        SourceCoverageGate.assert_required_historical_sources_available(raw_base_dir=temp_raw_dir)


@pytest.mark.integration
def test_coverage_gate_passes_when_all_sources_valid(temp_raw_dir):
    service = HistoricalSourceAcquisitionService(raw_base_dir=temp_raw_dir)
    specs = HistoricalManifestLoader.load_manifest()

    valid_csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,11/08/2023,Burnley,Man City,0,3,A\n"

    # Populate dummy valid files for all manifest entries
    for spec in specs:
        dest_path = service.get_destination_path(spec)
        dest_path.write_text(valid_csv, encoding="utf-8")

    verified = SourceCoverageGate.assert_required_historical_sources_available(raw_base_dir=temp_raw_dir)
    assert len(verified) == 12
    for item in verified:
        assert item["file_size"] > 0
        assert item["sha256"] is not None
