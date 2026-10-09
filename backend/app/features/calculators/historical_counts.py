"""
Historical Match Sample Size Count Calculators
Calculates total historical matches, home matches, and away matches available prior to cutoff.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Match
from app.features.base import BaseFeatureCalculator, FeatureCalculationResult
from app.features.query import HistoricalQueryLayer


class HomeMatchesPlayedCalculator(BaseFeatureCalculator):
    feature_key: str = "home_matches_played_v1"
    version: str = "1.0.0"
    description: str = "Number of historical home matches played by the home team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.home_team_id, cutoff_timestamp, home_only=True, target_match_id=match.id
        )
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=len(matches),
            is_missing=False,
            sample_size=len(matches),
        )


class AwayMatchesPlayedCalculator(BaseFeatureCalculator):
    feature_key: str = "away_matches_played_v1"
    version: str = "1.0.0"
    description: str = "Number of historical away matches played by the away team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.away_team_id, cutoff_timestamp, away_only=True, target_match_id=match.id
        )
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=len(matches),
            is_missing=False,
            sample_size=len(matches),
        )


class TotalMatchesPlayedCalculator(BaseFeatureCalculator):
    feature_key: str = "total_matches_played_v1"
    version: str = "1.0.0"
    description: str = "Total historical matches played by both teams combined prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        home_m = HistoricalQueryLayer.get_team_matches_before(
            db, match.home_team_id, cutoff_timestamp, target_match_id=match.id
        )
        away_m = HistoricalQueryLayer.get_team_matches_before(
            db, match.away_team_id, cutoff_timestamp, target_match_id=match.id
        )
        total = len(home_m) + len(away_m)
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=total,
            is_missing=False,
            sample_size=total,
        )
