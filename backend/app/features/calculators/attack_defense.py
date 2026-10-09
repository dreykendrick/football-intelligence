"""
Attack & Defensive Strength Feature Calculators
Calculates point-in-time league scoring baselines and normalized home/away attack and defensive strength ratios.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Match
from app.features.base import (
    BaseFeatureCalculator,
    FeatureCalculationResult,
    MissingnessReason,
)
from app.features.query import HistoricalQueryLayer

def _get_league_baselines(
    db: Session,
    competition_id: UUID,
    cutoff_timestamp: datetime,
    season_id: UUID | None = None,
    target_match_id: UUID | None = None,
) -> tuple[float | None, float | None, int]:
    """
    Calculates empirical point-in-time league home and away goal scoring averages.
    Enforces strict point-in-time cutoff, competition-season scoping, and target match exclusion.
    Returns (avg_home_goals, avg_away_goals, match_count).
    """
    league_matches = HistoricalQueryLayer.get_league_matches_before(
        db,
        competition_id=competition_id,
        cutoff_timestamp=cutoff_timestamp,
        season_id=season_id,
        approved_only=False,
        enforce_date_only_precision=True,
    )

    if target_match_id:
        league_matches = [m for m in league_matches if m.id != target_match_id]

    count = len(league_matches)
    if count == 0:
        return None, None, 0

    total_home_goals = sum(m.home_score for m in league_matches if m.home_score is not None)
    total_away_goals = sum(m.away_score for m in league_matches if m.away_score is not None)

    avg_home = round(total_home_goals / count, 4)
    avg_away = round(total_away_goals / count, 4)

    return avg_home, avg_away, count


class LeagueHomeGoalsAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "league_home_goals_per_match_v1"
    version: str = "1.0.0"
    description: str = "Point-in-time league home goals scored per match prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        if not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        avg_home, _, count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if count == 0 or avg_home is None:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=avg_home,
            is_missing=False,
            sample_size=count,
            metadata_payload={"league_sample_size": count},
        )


class LeagueAwayGoalsAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "league_away_goals_per_match_v1"
    version: str = "1.0.0"
    description: str = "Point-in-time league away goals scored per match prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        if not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        _, avg_away, count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if count == 0 or avg_away is None:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=avg_away,
            is_missing=False,
            sample_size=count,
            metadata_payload={"league_sample_size": count},
        )


class HomeAttackStrengthCalculator(BaseFeatureCalculator):
    feature_key: str = "home_attack_strength_v1"
    version: str = "1.0.0"
    description: str = "Home team home goal scoring rate divided by league historical home goal scoring rate prior to cutoff."

    def __init__(self, window_size: int | None = None, feature_key: str = "home_attack_strength_v1") -> None:
        self.window_size = window_size
        self.feature_key = feature_key

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        team_matches = HistoricalQueryLayer.get_team_matches_before(
            db,
            approved_only=False,
            enforce_date_only_precision=True,
            team_id=match.home_team_id,
            cutoff_timestamp=cutoff_timestamp,
            limit=self.window_size,
            home_only=True,
            target_match_id=match.id,
        )

        if not team_matches or not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        avg_home_league, _, league_count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if avg_home_league is None or avg_home_league == 0.0 or league_count == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=len(team_matches),
                metadata_payload={"team_sample_size": len(team_matches), "league_sample_size": league_count},
            )

        team_home_avg = sum(m.home_score for m in team_matches if m.home_score is not None) / len(team_matches)
        ratio = round(team_home_avg / avg_home_league, 4)

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=ratio,
            is_missing=False,
            sample_size=len(team_matches),
            metadata_payload={
                "team_sample_size": len(team_matches),
                "league_sample_size": league_count,
                "team_home_avg": round(team_home_avg, 4),
                "league_home_avg": avg_home_league,
            },
        )


class AwayAttackStrengthCalculator(BaseFeatureCalculator):
    feature_key: str = "away_attack_strength_v1"
    version: str = "1.0.0"
    description: str = "Away team away goal scoring rate divided by league historical away goal scoring rate prior to cutoff."

    def __init__(self, window_size: int | None = None, feature_key: str = "away_attack_strength_v1") -> None:
        self.window_size = window_size
        self.feature_key = feature_key

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        team_matches = HistoricalQueryLayer.get_team_matches_before(
            db,
            approved_only=False,
            enforce_date_only_precision=True,
            team_id=match.away_team_id,
            cutoff_timestamp=cutoff_timestamp,
            limit=self.window_size,
            away_only=True,
            target_match_id=match.id,
        )

        if not team_matches or not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        _, avg_away_league, league_count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if avg_away_league is None or avg_away_league == 0.0 or league_count == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=len(team_matches),
                metadata_payload={"team_sample_size": len(team_matches), "league_sample_size": league_count},
            )

        team_away_avg = sum(m.away_score for m in team_matches if m.away_score is not None) / len(team_matches)
        ratio = round(team_away_avg / avg_away_league, 4)

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=ratio,
            is_missing=False,
            sample_size=len(team_matches),
            metadata_payload={
                "team_sample_size": len(team_matches),
                "league_sample_size": league_count,
                "team_away_avg": round(team_away_avg, 4),
                "league_away_avg": avg_away_league,
            },
        )


class HomeDefenseStrengthCalculator(BaseFeatureCalculator):
    feature_key: str = "home_defense_strength_v1"
    version: str = "1.0.0"
    description: str = "Home team home goal concession rate divided by league away goal scoring rate (>1.0 indicates weaker defense)."

    def __init__(self, window_size: int | None = None, feature_key: str = "home_defense_strength_v1") -> None:
        self.window_size = window_size
        self.feature_key = feature_key

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        team_matches = HistoricalQueryLayer.get_team_matches_before(
            db,
            approved_only=False,
            enforce_date_only_precision=True,
            team_id=match.home_team_id,
            cutoff_timestamp=cutoff_timestamp,
            limit=self.window_size,
            home_only=True,
            target_match_id=match.id,
        )

        if not team_matches or not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        _, avg_away_league, league_count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if avg_away_league is None or avg_away_league == 0.0 or league_count == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=len(team_matches),
                metadata_payload={"team_sample_size": len(team_matches), "league_sample_size": league_count},
            )

        team_home_conceded_avg = sum(m.away_score for m in team_matches if m.away_score is not None) / len(team_matches)
        ratio = round(team_home_conceded_avg / avg_away_league, 4)

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=ratio,
            is_missing=False,
            sample_size=len(team_matches),
            metadata_payload={
                "team_sample_size": len(team_matches),
                "league_sample_size": league_count,
                "team_home_conceded_avg": round(team_home_conceded_avg, 4),
                "league_away_avg": avg_away_league,
            },
        )


class AwayDefenseStrengthCalculator(BaseFeatureCalculator):
    feature_key: str = "away_defense_strength_v1"
    version: str = "1.0.0"
    description: str = "Away team away goal concession rate divided by league home goal scoring rate (>1.0 indicates weaker defense)."

    def __init__(self, window_size: int | None = None, feature_key: str = "away_defense_strength_v1") -> None:
        self.window_size = window_size
        self.feature_key = feature_key

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        team_matches = HistoricalQueryLayer.get_team_matches_before(
            db,
            approved_only=False,
            enforce_date_only_precision=True,
            team_id=match.away_team_id,
            cutoff_timestamp=cutoff_timestamp,
            limit=self.window_size,
            away_only=True,
            target_match_id=match.id,
        )

        if not team_matches or not match.season:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        avg_home_league, _, league_count = _get_league_baselines(
            db, match.season.competition_id, cutoff_timestamp, match.season_id, target_match_id=match.id
        )

        if avg_home_league is None or avg_home_league == 0.0 or league_count == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=len(team_matches),
                metadata_payload={"team_sample_size": len(team_matches), "league_sample_size": league_count},
            )

        team_away_conceded_avg = sum(m.home_score for m in team_matches if m.home_score is not None) / len(team_matches)
        ratio = round(team_away_conceded_avg / avg_home_league, 4)

        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=ratio,
            is_missing=False,
            sample_size=len(team_matches),
            metadata_payload={
                "team_sample_size": len(team_matches),
                "league_sample_size": league_count,
                "team_away_conceded_avg": round(team_away_conceded_avg, 4),
                "league_home_avg": avg_home_league,
            },
        )
