"""
Domain Normalization & Canonical Identity Resolution Engine
Transforms raw provider match DTOs into canonical database entities.
Handles competition, season, team, and match identity resolution with duplicate detection.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    Competition,
    Match,
    MatchStatistic,
    Provider,
    ProviderMatchMapping,
    ProviderTeamMapping,
    Season,
    Team,
)
from app.ingestion.base import RawMatchRowDTO


class NormalizationResultDTO:
    """Outcome container for single match normalization."""

    def __init__(
        self,
        match: Match,
        is_created: bool,
        provider_match_key: str,
        match_statistic: MatchStatistic | None = None,
    ) -> None:
        self.match = match
        self.is_created = is_created
        self.provider_match_key = provider_match_key
        self.match_statistic = match_statistic


class DataNormalizer:
    """Domain Normalization Engine."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session
        self._provider_cache: dict[str, Provider] = {}
        self._team_alias_cache: dict[tuple[str, str], UUID] = {}

    def get_or_create_provider(
        self, provider_key: str, display_name: str, provider_type: str = "HISTORICAL_CSV"
    ) -> Provider:
        if provider_key in self._provider_cache:
            return self._provider_cache[provider_key]

        provider = self.db.query(Provider).filter_by(provider_key=provider_key).first()
        if not provider:
            provider = Provider(
                provider_key=provider_key,
                display_name=display_name,
                provider_type=provider_type,
                is_active=True,
            )
            self.db.add(provider)
            self.db.flush()

        self._provider_cache[provider_key] = provider
        return provider

    def get_or_create_competition(self, code: str, name: str | None = None, country: str | None = None) -> Competition:
        clean_code = code.upper().strip()
        comp = self.db.query(Competition).filter_by(code=clean_code).first()
        if not comp:
            names = {
                "EPL": ("English Premier League", "England"),
                "PREM": ("English Premier League", "England"),
                "LA_LIGA": ("La Liga", "Spain"),
                "LALIGA": ("La Liga", "Spain"),
                "SERIE_A": ("Serie A", "Italy"),
                "SERIEA": ("Serie A", "Italy"),
                "BUNDESLIGA": ("Bundesliga", "Germany"),
            }
            default_name, default_country = names.get(clean_code, (f"{clean_code} League", "Unknown"))
            comp = Competition(
                code=clean_code,
                name=name or default_name,
                country=country or default_country,
                competition_type="DOMESTIC_LEAGUE",
                is_active=True,
            )
            self.db.add(comp)
            self.db.flush()
        return comp

    def get_or_create_season(self, competition_id: UUID, season_year: str) -> Season:
        clean_season = season_year.replace("-", "/").strip()
        season = (
            self.db.query(Season)
            .filter_by(competition_id=competition_id, season_year=clean_season)
            .first()
        )
        if not season:
            start_year = None
            end_year = None
            if "/" in clean_season:
                parts = clean_season.split("/")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    s1, s2 = parts[0].strip(), parts[1].strip()
                    start_year = int(s1) if len(s1) == 4 else 2000 + int(s1)
                    end_year = int(s2) if len(s2) == 4 else 2000 + int(s2)

            season = Season(
                competition_id=competition_id,
                season_year=clean_season,
                start_year=start_year,
                end_year=end_year,
                is_current=False,
            )
            self.db.add(season)
            self.db.flush()
        return season

    def resolve_team(self, provider: Provider | str, raw_team_name: str, country: str | None = None) -> Team:
        if isinstance(provider, str):
            provider_obj = self.get_or_create_provider(provider, provider)
        else:
            provider_obj = provider

        provider_key = provider_obj.provider_key
        clean_alias = raw_team_name.strip()
        cache_key = (provider_key.lower(), clean_alias.lower())

        if cache_key in self._team_alias_cache:
            team_id = self._team_alias_cache[cache_key]
            team = self.db.query(Team).filter_by(id=team_id).first()
            if team:
                return team

        # 1. Lookup existing ProviderTeamMapping
        team_mapping = (
            self.db.query(ProviderTeamMapping)
            .filter_by(provider_id=provider_obj.id, raw_alias=clean_alias)
            .first()
        )
        if team_mapping:
            self._team_alias_cache[cache_key] = team_mapping.team_id
            return team_mapping.team

        # 2. Check exact canonical team name match
        team = self.db.query(Team).filter_by(canonical_name=clean_alias).first()
        if not team:
            # 3. Conservative initial creation of canonical team
            team = Team(
                canonical_name=clean_alias,
                short_name=clean_alias,
                country=country or "Unknown",
                is_active=True,
            )
            self.db.add(team)
            self.db.flush()

        # Persist ProviderTeamMapping for future lookups
        new_mapping = ProviderTeamMapping(
            provider_id=provider_obj.id,
            team_id=team.id,
            raw_alias=clean_alias,
            normalized_alias=clean_alias.lower(),
        )
        self.db.add(new_mapping)
        self.db.flush()

        self._team_alias_cache[cache_key] = team.id
        return team

    def normalize_match(
        self, provider: Provider, dto: RawMatchRowDTO
    ) -> NormalizationResultDTO:
        comp = self.get_or_create_competition(dto.competition_code)
        season = self.get_or_create_season(comp.id, dto.season_year)

        home_team = self.resolve_team(provider, dto.home_team_raw, country=comp.country)
        away_team = self.resolve_team(provider, dto.away_team_raw, country=comp.country)

        # Generate Deterministic External Match Key
        date_key = dto.match_date.strftime("%Y-%m-%d")
        ext_match_key = f"{provider.provider_key}:{comp.code}:{season.season_year}:{date_key}:{home_team.canonical_name}:{away_team.canonical_name}"

        # Check existing match provider mapping
        existing_mapping = (
            self.db.query(ProviderMatchMapping)
            .filter_by(provider_id=provider.id, external_match_id=ext_match_key)
            .first()
        )
        if existing_mapping:
            existing_match = self.db.query(Match).filter_by(id=existing_mapping.match_id).first()
            if existing_match:
                return NormalizationResultDTO(
                    match=existing_match,
                    is_created=False,
                    provider_match_key=ext_match_key,
                )

        # Check canonical match by (season, home_team, away_team, kickoff)
        existing_match = (
            self.db.query(Match)
            .filter_by(
                season_id=season.id,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff_utc=dto.match_date,
            )
            .first()
        )

        if not existing_match:
            match = Match(
                season_id=season.id,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff_utc=dto.match_date,
                status="FINISHED",
                home_score=dto.full_time_home_goals,
                away_score=dto.full_time_away_goals,
                half_time_home_score=dto.half_time_home_goals,
                half_time_away_score=dto.half_time_away_goals,
                completed_at=dto.match_date,
            )
            self.db.add(match)
            self.db.flush()
            is_created = True
        else:
            match = existing_match
            is_created = False

        # Persist Provider Match Mapping
        match_mapping = ProviderMatchMapping(
            provider_id=provider.id,
            match_id=match.id,
            external_match_id=ext_match_key,
            raw_match_key=f"{dto.home_team_raw} vs {dto.away_team_raw} ({date_key})",
        )
        self.db.add(match_mapping)

        # Persist Optional Match Statistics (preserving NULL semantics)
        match_stat = None
        if any([
            dto.home_shots is not None,
            dto.home_shots_on_target is not None,
            dto.home_corners is not None,
            dto.home_fouls is not None,
        ]):
            match_stat = MatchStatistic(
                match_id=match.id,
                team_id=home_team.id,
                shots=dto.home_shots,
                shots_on_target=dto.home_shots_on_target,
                corners=dto.home_corners,
                fouls=dto.home_fouls,
                yellow_cards=dto.home_yellow_cards,
                red_cards=dto.home_red_cards,
            )
            self.db.add(match_stat)

        self.db.flush()

        return NormalizationResultDTO(
            match=match,
            is_created=is_created,
            provider_match_key=ext_match_key,
            match_statistic=match_stat,
        )
