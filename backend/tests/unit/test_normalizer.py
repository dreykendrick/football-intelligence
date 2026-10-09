"""
Unit Tests for Data Normalizer & Identity Resolution
Verifies competition, season, team alias resolution, and deterministic match key generation.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.ingestion.base import RawMatchRowDTO
from app.ingestion.normalizer import DataNormalizer


@pytest.mark.unit
def test_resolve_competition_and_season(db_session: Session):
    normalizer = DataNormalizer(db_session)

    comp = normalizer.get_or_create_competition("EPL")
    assert comp.code == "EPL"
    assert comp.country == "England"

    season = normalizer.get_or_create_season(comp.id, "2023/24")
    assert season.season_year == "2023/24"
    assert season.start_year == 2023
    assert season.end_year == 2024


@pytest.mark.unit
def test_team_alias_resolution_caching(db_session: Session):
    normalizer = DataNormalizer(db_session)

    t1 = normalizer.resolve_team("football_data_co_uk", "Man United", country="England")
    assert t1.canonical_name == "Man United"

    # Second resolution with exact alias returns existing canonical team
    t2 = normalizer.resolve_team("football_data_co_uk", "Man United", country="England")
    assert t2.id == t1.id


@pytest.mark.unit
def test_normalize_match_structure(db_session: Session):
    normalizer = DataNormalizer(db_session)
    provider = normalizer.get_or_create_provider("football_data_co_uk", "Football-Data.co.uk")

    dto = RawMatchRowDTO(
        source_row_index=2,
        competition_code="EPL",
        season_year="2023/24",
        match_date=datetime(2023, 8, 11, 12, 0, tzinfo=UTC),
        home_team_raw="Burnley",
        away_team_raw="Man City",
        full_time_home_goals=0,
        full_time_away_goals=3,
        full_time_result="A",
        home_shots=6,
        away_shots=17,
        raw_payload={"HomeTeam": "Burnley", "AwayTeam": "Man City"},
    )

    result = normalizer.normalize_match(provider, dto)

    assert result.is_created is True
    assert result.match.home_score == 0
    assert result.match.away_score == 3
    assert result.match.home_team.canonical_name == "Burnley"
    assert result.match.away_team.canonical_name == "Man City"
    assert "football_data_co_uk:EPL:2023/24:2023-08-11:Burnley:Man City" in result.provider_match_key
