"""
Rest Days & Fixture Congestion Feature Calculators
Calculates current-season-isolated rest days, rolling window match counts (7d, 14d, 21d), and season matches played for home and away teams.
"""
from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Match
from app.features.base import BaseFeatureCalculator, FeatureCalculationResult, MissingnessReason
from app.features.query import HistoricalQueryLayer


def _get_team_rest_days(
    db: Session,
    team_id: UUID,
    match: Match,
    cutoff_timestamp: datetime,
    feature_key: str,
    version: str,
) -> FeatureCalculationResult:
    """Helper to compute current-season observed rest days for a team."""
    prev_match = HistoricalQueryLayer.get_previous_match(
        db, team_id, cutoff_timestamp, target_match_id=match.id, season_id=match.season_id,
        approved_only=True, enforce_date_only_precision=True
    )

    if not prev_match:
        return FeatureCalculationResult(
            feature_key=feature_key,
            version=version,
            value=None,
            is_missing=True,
            missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
            sample_size=0,
            metadata_payload={
                "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
                "includes_cup_matches": False,
                "previous_match_id": None,
            },
        )

    match_time = match.kickoff_utc.replace(tzinfo=UTC) if match.kickoff_utc.tzinfo is None else match.kickoff_utc
    prev_time = prev_match.kickoff_utc.replace(tzinfo=UTC) if prev_match.kickoff_utc.tzinfo is None else prev_match.kickoff_utc

    # Check for date-only precision vs exact timestamp
    if match_time.time() == time(0, 0) or prev_time.time() == time(0, 0):
        rest_days = float((match_time.date() - prev_time.date()).days)
        precision = "DATE_ONLY_DERIVED"
    else:
        rest_days = round((match_time - prev_time).total_seconds() / 86400.0, 2)
        precision = "EXACT_TIMESTAMP"

    return FeatureCalculationResult(
        feature_key=feature_key,
        version=version,
        value=rest_days,
        is_missing=False,
        sample_size=1,
        metadata_payload={
            "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
            "includes_cup_matches": False,
            "previous_match_id": str(prev_match.id),
            "previous_match_kickoff": prev_match.kickoff_utc.isoformat(),
            "precision": precision,
        },
    )


class HomeRestDaysCalculator(BaseFeatureCalculator):
    feature_key: str = "home_rest_days_v1"
    version: str = "1.0.0"
    description: str = "Days of observed rest for home team since previous match in current season."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_team_rest_days(db, match.home_team_id, match, cutoff_timestamp, self.feature_key, self.version)


class AwayRestDaysCalculator(BaseFeatureCalculator):
    feature_key: str = "away_rest_days_v1"
    version: str = "1.0.0"
    description: str = "Days of observed rest for away team since previous match in current season."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_team_rest_days(db, match.away_team_id, match, cutoff_timestamp, self.feature_key, self.version)


class RestDaysDifferenceCalculator(BaseFeatureCalculator):
    feature_key: str = "rest_days_difference_v1"
    version: str = "1.0.0"
    description: str = "Difference in observed rest days (Home Rest Days - Away Rest Days)."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        home_res = HomeRestDaysCalculator().calculate(db, match, cutoff_timestamp, config)
        away_res = AwayRestDaysCalculator().calculate(db, match, cutoff_timestamp, config)

        if home_res.value is None or away_res.value is None:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
            )

        diff = round(float(home_res.value) - float(away_res.value), 2)
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=diff,
            is_missing=False,
            sample_size=2,
            metadata_payload={
                "home_rest_days": home_res.value,
                "away_rest_days": away_res.value,
                "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
            },
        )


def _get_window_match_count(
    db: Session,
    team_id: UUID,
    match: Match,
    cutoff_timestamp: datetime,
    window_days: int,
    feature_key: str,
    version: str,
) -> FeatureCalculationResult:
    """Helper to count observed matches played by a team in the last N days prior to cutoff in current season."""
    matches = HistoricalQueryLayer.get_team_matches_before(
        db, team_id, cutoff_timestamp, target_match_id=match.id, season_id=match.season_id,
        approved_only=True, enforce_date_only_precision=True
    )

    cutoff_tz = cutoff_timestamp.replace(tzinfo=UTC) if cutoff_timestamp.tzinfo is None else cutoff_timestamp
    cutoff_start_of_day = datetime(
        cutoff_tz.year, cutoff_tz.month, cutoff_tz.day, 0, 0, 0, tzinfo=UTC
    )
    window_start = cutoff_start_of_day - timedelta(days=window_days)

    count = 0
    for m in matches:
        m_time = m.kickoff_utc.replace(tzinfo=UTC) if m.kickoff_utc.tzinfo is None else m.kickoff_utc
        if window_start <= m_time < cutoff_start_of_day:
            count += 1

    return FeatureCalculationResult(
        feature_key=feature_key,
        version=version,
        value=count,
        is_missing=False,
        sample_size=len(matches),
        metadata_payload={
            "window_days": window_days,
            "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
            "includes_cup_matches": False,
        },
    )


class HomeMatchesLast7DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "home_matches_last_7d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by home team in last 7 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.home_team_id, match, cutoff_timestamp, 7, self.feature_key, self.version)


class AwayMatchesLast7DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "away_matches_last_7d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by away team in last 7 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.away_team_id, match, cutoff_timestamp, 7, self.feature_key, self.version)


class HomeMatchesLast14DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "home_matches_last_14d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by home team in last 14 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.home_team_id, match, cutoff_timestamp, 14, self.feature_key, self.version)


class AwayMatchesLast14DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "away_matches_last_14d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by away team in last 14 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.away_team_id, match, cutoff_timestamp, 14, self.feature_key, self.version)


class HomeMatchesLast21DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "home_matches_last_21d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by home team in last 21 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.home_team_id, match, cutoff_timestamp, 21, self.feature_key, self.version)


class AwayMatchesLast21DaysCalculator(BaseFeatureCalculator):
    feature_key: str = "away_matches_last_21d_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by away team in last 21 days prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        return _get_window_match_count(db, match.away_team_id, match, cutoff_timestamp, 21, self.feature_key, self.version)


class HomeSeasonMatchesPlayedCalculator(BaseFeatureCalculator):
    feature_key: str = "home_season_matches_played_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by home team in current season prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.home_team_id, cutoff_timestamp, target_match_id=match.id, season_id=match.season_id,
            approved_only=True, enforce_date_only_precision=True
        )
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=len(matches),
            is_missing=False,
            sample_size=len(matches),
            metadata_payload={
                "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
                "includes_cup_matches": False,
            },
        )


class AwaySeasonMatchesPlayedCalculator(BaseFeatureCalculator):
    feature_key: str = "away_season_matches_played_v1"
    version: str = "1.0.0"
    description: str = "Number of observed matches played by away team in current season prior to cutoff."

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        matches = HistoricalQueryLayer.get_team_matches_before(
            db, match.away_team_id, cutoff_timestamp, target_match_id=match.id, season_id=match.season_id,
            approved_only=True, enforce_date_only_precision=True
        )
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=len(matches),
            is_missing=False,
            sample_size=len(matches),
            metadata_payload={
                "schedule_scope": "APPROVED_DATASET_COMPETITION_ONLY",
                "includes_cup_matches": False,
            },
        )
