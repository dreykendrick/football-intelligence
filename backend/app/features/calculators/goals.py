"""
Goal Rate Feature Calculators
Calculates historical average goals scored and conceded per match for home and away teams.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Match
from app.features.base import BaseFeatureCalculator, FeatureCalculationResult
from app.features.query import HistoricalQueryLayer


class HomeGoalsScoredAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "home_goals_scored_avg_v1"
    version: str = "1.0.0"
    description: str = "Average goals scored per home match by home team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.home_team_id, cutoff_timestamp, home_only=True, target_match_id=match.id
        )
        if not matches:
            return FeatureCalculationResult(
                feature_key=self.feature_key, version=self.version, value=None, is_missing=True, sample_size=0
            )
        total_goals = sum(m.home_score for m in matches if m.home_score is not None)
        avg = round(total_goals / len(matches), 4)
        return FeatureCalculationResult(
            feature_key=self.feature_key, version=self.version, value=avg, is_missing=False, sample_size=len(matches)
        )


class HomeGoalsConcededAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "home_goals_conceded_avg_v1"
    version: str = "1.0.0"
    description: str = "Average goals conceded per home match by home team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.home_team_id, cutoff_timestamp, home_only=True, target_match_id=match.id
        )
        if not matches:
            return FeatureCalculationResult(
                feature_key=self.feature_key, version=self.version, value=None, is_missing=True, sample_size=0
            )
        total_goals = sum(m.away_score for m in matches if m.away_score is not None)
        avg = round(total_goals / len(matches), 4)
        return FeatureCalculationResult(
            feature_key=self.feature_key, version=self.version, value=avg, is_missing=False, sample_size=len(matches)
        )


class AwayGoalsScoredAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "away_goals_scored_avg_v1"
    version: str = "1.0.0"
    description: str = "Average goals scored per away match by away team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.away_team_id, cutoff_timestamp, away_only=True, target_match_id=match.id
        )
        if not matches:
            return FeatureCalculationResult(
                feature_key=self.feature_key, version=self.version, value=None, is_missing=True, sample_size=0
            )
        total_goals = sum(m.away_score for m in matches if m.away_score is not None)
        avg = round(total_goals / len(matches), 4)
        return FeatureCalculationResult(
            feature_key=self.feature_key, version=self.version, value=avg, is_missing=False, sample_size=len(matches)
        )


class AwayGoalsConcededAvgCalculator(BaseFeatureCalculator):
    feature_key: str = "away_goals_conceded_avg_v1"
    version: str = "1.0.0"
    description: str = "Average goals conceded per away match by away team prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.away_team_id, cutoff_timestamp, away_only=True, target_match_id=match.id
        )
        if not matches:
            return FeatureCalculationResult(
                feature_key=self.feature_key, version=self.version, value=None, is_missing=True, sample_size=0
            )
        total_goals = sum(m.home_score for m in matches if m.home_score is not None)
        avg = round(total_goals / len(matches), 4)
        return FeatureCalculationResult(
            feature_key=self.feature_key, version=self.version, value=avg, is_missing=False, sample_size=len(matches)
        )
