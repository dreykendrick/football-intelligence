"""
Unit Tests for Football Identity Resolver Pipeline
Verifies multi-stage resolution pipeline logic across explicit mapping, exact canonical name, alias, and candidate review.
"""
import pytest
from sqlalchemy.orm import Session

from app.db.models import Provider, ProviderTeamMapping, Team, TeamAliasMapping
from app.identity.base import ResolutionStatusEnum
from app.identity.resolver import FootballIdentityResolver


@pytest.mark.unit
def test_resolve_via_explicit_provider_mapping(db_session: Session):
    provider = Provider(provider_key="football_data_co_uk", display_name="Football Data")
    team = Team(canonical_name="Manchester United", country="England")
    db_session.add_all([provider, team])
    db_session.flush()

    mapping = ProviderTeamMapping(provider_id=provider.id, team_id=team.id, raw_alias="Man United")
    db_session.add(mapping)
    db_session.flush()

    resolver = FootballIdentityResolver(db_session)
    res = resolver.resolve_team_identity("football_data_co_uk", "Man United")

    assert res.status == ResolutionStatusEnum.RESOLVED_EXPLICIT_MAPPING
    assert res.canonical_id == team.id
    assert res.canonical_name == "Manchester United"


@pytest.mark.unit
def test_resolve_via_exact_canonical_name(db_session: Session):
    team = Team(canonical_name="Arsenal", country="England")
    db_session.add(team)
    db_session.flush()

    resolver = FootballIdentityResolver(db_session)
    res = resolver.resolve_team_identity("football_data_co_uk", "Arsenal")

    assert res.status == ResolutionStatusEnum.RESOLVED_EXACT_NAME
    assert res.canonical_id == team.id


@pytest.mark.unit
def test_resolve_via_alias_mapping(db_session: Session):
    team = Team(canonical_name="Newcastle United", country="England")
    db_session.add(team)
    db_session.flush()

    alias = TeamAliasMapping(team_id=team.id, provider_name="manual", raw_alias="Newcastle")
    db_session.add(alias)
    db_session.flush()

    resolver = FootballIdentityResolver(db_session)
    res = resolver.resolve_team_identity("football_data_co_uk", "Newcastle")

    assert res.status == ResolutionStatusEnum.RESOLVED_ALIAS
    assert res.canonical_id == team.id
