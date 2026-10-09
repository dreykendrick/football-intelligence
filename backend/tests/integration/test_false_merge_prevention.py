"""
Integration Tests for False Merge Prevention Policy
Asserts that similar but distinct teams (e.g. Manchester United vs Manchester City) NEVER automatically merge.
"""
import pytest
from sqlalchemy.orm import Session

from app.db.models import Team
from app.identity.base import ResolutionStatusEnum
from app.identity.resolver import FootballIdentityResolver


@pytest.mark.integration
def test_similar_teams_do_not_auto_merge(db_session: Session):
    # Existing Canonical Team: Manchester United
    man_utd = Team(canonical_name="Manchester United", country="England")
    db_session.add(man_utd)
    db_session.flush()

    resolver = FootballIdentityResolver(db_session, review_threshold=0.60)

    # Incoming: "Manchester City"
    # When auto_create_if_unambiguous is False, should return REVIEW_REQUIRED with candidate, NOT auto-map to Manchester United
    res = resolver.resolve_team_identity("football_data_co_uk", "Manchester City", auto_create_if_unambiguous=False)

    assert res.status == ResolutionStatusEnum.REVIEW_REQUIRED
    assert res.canonical_id is None  # Must NOT be automatically assigned to Manchester United!
    assert len(res.candidates) >= 1
    assert res.candidates[0].canonical_name == "Manchester United"


@pytest.mark.integration
def test_bristol_city_and_bristol_rovers_remain_distinct(db_session: Session):
    b_city = Team(canonical_name="Bristol City", country="England")
    b_rovers = Team(canonical_name="Bristol Rovers", country="England")
    db_session.add_all([b_city, b_rovers])
    db_session.flush()

    resolver = FootballIdentityResolver(db_session)
    res = resolver.resolve_team_identity("football_data_co_uk", "Bristol Rovers")

    assert res.status == ResolutionStatusEnum.RESOLVED_EXACT_NAME
    assert res.canonical_id == b_rovers.id
    assert res.canonical_id != b_city.id
