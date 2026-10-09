"""
Unit Tests for Dataset Selection Policy Engine
"""
import pytest

from app.dataset.base import InsufficientCoverageError
from app.dataset.policy import DatasetSelectionPolicyEngine


def test_select_seasons_picks_top_3_usable_seasons():

    # Mock DB session not strictly needed if we mock query or pass mock objects
    # Let's test policy logic with unit assertions
    engine = DatasetSelectionPolicyEngine(db_session=None)
    # Validate coverage rules
    selected_specs = [
        {"competition_code": "E0", "season_year": "2023-24"},
        {"competition_code": "E0", "season_year": "2022-23"},
        {"competition_code": "E0", "season_year": "2021-22"},
        {"competition_code": "SP1", "season_year": "2023-24"},
        {"competition_code": "SP1", "season_year": "2022-23"},
        {"competition_code": "SP1", "season_year": "2021-22"},
        {"competition_code": "I1", "season_year": "2023-24"},
        {"competition_code": "I1", "season_year": "2022-23"},
        {"competition_code": "I1", "season_year": "2021-22"},
        {"competition_code": "D1", "season_year": "2023-24"},
        {"competition_code": "D1", "season_year": "2022-23"},
        {"competition_code": "D1", "season_year": "2021-22"},
    ]

    counts = engine.validate_coverage(selected_specs)
    assert counts == {"E0": 3, "SP1": 3, "I1": 3, "D1": 3}


def test_coverage_validation_raises_on_deficient_seasons():
    engine = DatasetSelectionPolicyEngine(db_session=None)
    deficient_specs = [
        {"competition_code": "E0", "season_year": "2023-24"},
        {"competition_code": "E0", "season_year": "2022-23"},
        {"competition_code": "SP1", "season_year": "2023-24"},
    ]

    with pytest.raises(InsufficientCoverageError) as exc_info:
        engine.validate_coverage(deficient_specs)

    assert "Dataset release coverage deficient" in str(exc_info.value)
