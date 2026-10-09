from __future__ import annotations
import collections
import hashlib
import functools
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import HistoricalDatasetMatch, HistoricalDatasetRelease, Match
from app.features.base import BaseFeatureCalculator, FeatureCalculationResult
from app.features.query import HistoricalQueryLayer
from pydantic import BaseModel

class EloConfig(BaseModel):
    initial_rating: float = 1500.0
    k_factor: float = 20.0
    scale: float = 400.0
    home_advantage: float = 40.0
    mean_rating: float = 1500.0
    season_carryover: float = 0.75
    version: str = "1.0.0"

    @property
    def fingerprint(self) -> str:
        raw = f"{self.initial_rating}:{self.k_factor}:{self.scale}:{self.home_advantage}:{self.mean_rating}:{self.season_carryover}:{self.version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

class EloRatingEngine:
    """Chronological, competition-isolated, point-in-time Elo Rating Engine."""

    @classmethod
    def compute_team_ratings_before(
        cls,
        db: Session,
        competition_id: UUID,
        cutoff_timestamp: datetime,
        target_match_id: UUID | None = None,
        target_season_id: UUID | None = None,
        config: EloConfig | None = None,
        approved_only: bool = True,
        dataset_key: str = "mvp_a_historical",
        dataset_version: str = "v1",
    ) -> tuple[dict[UUID, float], dict[UUID, int]]:
        if config is None:
            config = EloConfig()
        if cutoff_timestamp.tzinfo is None:
            cutoff_timestamp = cutoff_timestamp.replace(tzinfo=UTC)
        cutoff_start_of_day = datetime(cutoff_timestamp.year, cutoff_timestamp.month, cutoff_timestamp.day, 0, 0, 0, tzinfo=UTC)
        
        # Call the cached inner function
        return cls._cached_compute_team_ratings(
            db, competition_id, cutoff_start_of_day, target_season_id,
            config.fingerprint, approved_only, dataset_key, dataset_version
        )

    @classmethod
    def clear_cache(cls):
        """Explicitly clear the lru_cache."""
        cls._cached_compute_team_ratings.cache_clear()

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def _cached_compute_team_ratings(
        db: Session,
        competition_id: UUID,
        cutoff_start_of_day: datetime,
        target_season_id: UUID | None,
        config_fp: str,
        approved_only: bool,
        dataset_key: str,
        dataset_version: str,
    ) -> tuple[dict[UUID, float], dict[UUID, int]]:
        config = EloConfig() # Use defaults since we hash on fingerprint
        from app.dataset.base import DatasetReleaseStatusEnum
        release_id: UUID | None = None
        release = db.query(HistoricalDatasetRelease).filter_by(key=dataset_key, version=dataset_version).first()
        if release:
            if approved_only and release.status != DatasetReleaseStatusEnum.APPROVED.value:
                release_id = None
            else:
                release_id = release.id
        query = db.query(Match).join(Match.season).filter(Match.status == "FINISHED", Match.kickoff_utc < cutoff_start_of_day, Match.season.has(competition_id=competition_id))
        if release_id:
            query = query.join(HistoricalDatasetMatch, Match.id == HistoricalDatasetMatch.match_id).filter(HistoricalDatasetMatch.dataset_release_id == release_id)
        league_matches = query.order_by(Match.kickoff_utc.asc()).all()
        ratings: dict[UUID, float] = {}
        matches_processed = collections.defaultdict(int)
        matches_by_day = collections.defaultdict(list)
        for m in league_matches:
            d_key = m.kickoff_utc.date()
            matches_by_day[d_key].append(m)
        sorted_days = sorted(matches_by_day.keys())
        current_season_id = None
        curr_season_teams: set[UUID] = set()
        prev_season_teams: set[UUID] = set()
        for day in sorted_days:
            day_matches = matches_by_day[day]
            if not day_matches: continue
            first_match_season = day_matches[0].season_id
            if current_season_id is None:
                current_season_id = first_match_season
            elif first_match_season != current_season_id:
                for team_id in list(ratings.keys()):
                    if team_id in curr_season_teams or team_id in prev_season_teams:
                        r_old = ratings[team_id]
                        r_new = config.mean_rating + config.season_carryover * (r_old - config.mean_rating)
                        ratings[team_id] = round(r_new, 2)
                    else:
                        ratings[team_id] = config.initial_rating
                prev_season_teams = set(curr_season_teams)
                curr_season_teams = set()
                current_season_id = first_match_season
            daily_deltas: dict[UUID, float] = collections.defaultdict(float)
            for m in day_matches:
                if m.home_score is None or m.away_score is None: continue
                curr_season_teams.add(m.home_team_id)
                curr_season_teams.add(m.away_team_id)
                r_home = ratings.get(m.home_team_id, config.initial_rating)
                r_away = ratings.get(m.away_team_id, config.initial_rating)
                r_home_eff = r_home + config.home_advantage
                exp_home = 1.0 / (1.0 + 10.0 ** ((r_away - r_home_eff) / config.scale))
                exp_away = 1.0 - exp_home
                if m.home_score > m.away_score:
                    score_home, score_away = 1.0, 0.0
                elif m.home_score == m.away_score:
                    score_home, score_away = 0.5, 0.5
                else:
                    score_home, score_away = 0.0, 1.0
                d_home = config.k_factor * (score_home - exp_home)
                d_away = config.k_factor * (score_away - exp_away)
                daily_deltas[m.home_team_id] += d_home
                daily_deltas[m.away_team_id] += d_away
                matches_processed[m.home_team_id] += 1
                matches_processed[m.away_team_id] += 1
            for team_id, total_delta in daily_deltas.items():
                r_start = ratings.get(team_id, config.initial_rating)
                ratings[team_id] = round(r_start + total_delta, 2)
        if target_season_id and current_season_id and current_season_id != target_season_id:
            for team_id in list(ratings.keys()):
                r_old = ratings[team_id]
                r_new = config.mean_rating + config.season_carryover * (r_old - config.mean_rating)
                ratings[team_id] = round(r_new, 2)
        return ratings, dict(matches_processed)

class HomeEloCalculator(BaseFeatureCalculator):
    feature_key: str = "home_elo_v1"
    version: str = "1.0.0"
    description: str = "Sequential pre-match Elo rating for the home team prior to target kickoff."
    def calculate(self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None) -> FeatureCalculationResult:
        elo_config = EloConfig()
        comp_id = match.season.competition_id if match.season else None
        if not comp_id:
            return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=elo_config.initial_rating, is_missing=False, sample_size=0)
        ratings, match_counts = EloRatingEngine.compute_team_ratings_before(db, competition_id=comp_id, cutoff_timestamp=cutoff_timestamp, target_match_id=match.id, target_season_id=match.season_id, config=elo_config)
        r_home = ratings.get(match.home_team_id, elo_config.initial_rating)
        proc_count = match_counts.get(match.home_team_id, 0)
        return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=r_home, is_missing=False, sample_size=proc_count, metadata_payload={"matches_processed": proc_count, "is_initial_rating": proc_count == 0, "elo_config_version": elo_config.version, "elo_config_fingerprint": elo_config.fingerprint})

class AwayEloCalculator(BaseFeatureCalculator):
    feature_key: str = "away_elo_v1"
    version: str = "1.0.0"
    description: str = "Sequential pre-match Elo rating for the away team prior to target kickoff."
    def calculate(self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None) -> FeatureCalculationResult:
        elo_config = EloConfig()
        comp_id = match.season.competition_id if match.season else None
        if not comp_id:
            return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=elo_config.initial_rating, is_missing=False, sample_size=0)
        ratings, match_counts = EloRatingEngine.compute_team_ratings_before(db, competition_id=comp_id, cutoff_timestamp=cutoff_timestamp, target_match_id=match.id, target_season_id=match.season_id, config=elo_config)
        r_away = ratings.get(match.away_team_id, elo_config.initial_rating)
        proc_count = match_counts.get(match.away_team_id, 0)
        return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=r_away, is_missing=False, sample_size=proc_count, metadata_payload={"matches_processed": proc_count, "is_initial_rating": proc_count == 0, "elo_config_version": elo_config.version, "elo_config_fingerprint": elo_config.fingerprint})

class EloDifferenceCalculator(BaseFeatureCalculator):
    feature_key: str = "elo_difference_v1"
    version: str = "1.0.0"
    description: str = "Home pre-match Elo rating minus away pre-match Elo rating."
    def calculate(self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None) -> FeatureCalculationResult:
        elo_config = EloConfig()
        comp_id = match.season.competition_id if match.season else None
        if not comp_id:
            return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=0.0, is_missing=False, sample_size=0)
        ratings, match_counts = EloRatingEngine.compute_team_ratings_before(db, competition_id=comp_id, cutoff_timestamp=cutoff_timestamp, target_match_id=match.id, target_season_id=match.season_id, config=elo_config)
        r_home = ratings.get(match.home_team_id, elo_config.initial_rating)
        r_away = ratings.get(match.away_team_id, elo_config.initial_rating)
        diff = round(r_home - r_away, 2)
        proc_home = match_counts.get(match.home_team_id, 0)
        proc_away = match_counts.get(match.away_team_id, 0)
        return FeatureCalculationResult(feature_key=self.feature_key, version=self.version, value=diff, is_missing=False, sample_size=min(proc_home, proc_away), metadata_payload={"home_matches_processed": proc_home, "away_matches_processed": proc_away, "elo_config_version": elo_config.version, "elo_config_fingerprint": elo_config.fingerprint})
