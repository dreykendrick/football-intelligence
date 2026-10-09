"""
Venue-Specific Team Form Feature Calculators
Calculates rolling home-only performance for home team and away-only performance for away team over windows N in {3, 5, 10}.
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
from app.features.observations import (
    RollingFormAggregator,
    RollingFormMetrics,
    TeamMatchObservationBuilder,
)
from app.features.query import HistoricalQueryLayer


def _get_venue_form_metrics(
    db: Session,
    team_id: UUID,
    cutoff_timestamp: datetime,
    target_match_id: UUID,
    window_size: int,
    home_only: bool,
    away_only: bool,
) -> RollingFormMetrics:
    """Helper retrieving venue-specific matches and aggregating form metrics."""
    matches = HistoricalQueryLayer.get_team_matches_before(
            db,
            approved_only=False,
            enforce_date_only_precision=True,
        team_id=team_id,
        cutoff_timestamp=cutoff_timestamp,
        limit=max(10, window_size),
        home_only=home_only,
        away_only=away_only,
        target_match_id=target_match_id,
    )
    observations = TeamMatchObservationBuilder.build_observations(matches, team_id)
    return RollingFormAggregator.aggregate(observations, window_size)


class BaseVenueFormCalculator(BaseFeatureCalculator):
    """Base class for venue-specific rolling team form calculators."""
    feature_key: str
    version: str = "1.0.0"
    description: str
    target_side: str  # "home" or "away"
    metric_name: str
    window_size: int

    def __init__(
        self,
        feature_key: str,
        target_side: str,
        metric_name: str,
        window_size: int,
        description: str,
        version: str = "1.0.0",
    ) -> None:
        self.feature_key = feature_key
        self.target_side = target_side
        self.metric_name = metric_name
        self.window_size = window_size
        self.description = description
        self.version = version

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        is_home = self.target_side == "home"
        team_id = match.home_team_id if is_home else match.away_team_id
        metrics = _get_venue_form_metrics(
            db=db,
            team_id=team_id,
            cutoff_timestamp=cutoff_timestamp,
            target_match_id=match.id,
            window_size=self.window_size,
            home_only=is_home,
            away_only=not is_home,
        )

        if metrics.sample_size == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
                metadata_payload={"requested_window": self.window_size, "venue": "HOME" if is_home else "AWAY"},
            )

        val = getattr(metrics, self.metric_name, None)
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=val,
            is_missing=False,
            missing_reason=MissingnessReason.AVAILABLE,
            sample_size=metrics.sample_size,
            metadata_payload={
                "requested_window": self.window_size,
                "actual_sample_size": metrics.sample_size,
                "venue": "HOME" if is_home else "AWAY",
            },
        )


def generate_venue_form_calculators() -> dict[str, BaseFeatureCalculator]:
    """Generates all Sprint 3.3 venue form feature calculators across windows 3, 5, 10."""
    calculators: dict[str, BaseFeatureCalculator] = {}
    windows = (3, 5, 10)
    sides = ("home", "away")

    metrics_map = [
        ("points", "points", "Total venue points earned"),
        ("ppg", "points_per_match", "Venue points per match"),
        ("wins", "wins", "Total venue wins"),
        ("draws", "draws", "Total venue draws"),
        ("losses", "losses", "Total venue losses"),
        ("win_rate", "win_rate", "Venue win rate ratio"),
        ("draw_rate", "draw_rate", "Venue draw rate ratio"),
        ("loss_rate", "loss_rate", "Venue loss rate ratio"),
        ("goals_scored", "goals_scored", "Total venue goals scored"),
        ("goals_scored_per_match", "goals_scored_per_match", "Venue goals scored per match"),
        ("goals_conceded", "goals_conceded", "Total venue goals conceded"),
        ("goals_conceded_per_match", "goals_conceded_per_match", "Venue goals conceded per match"),
        ("goal_difference", "goal_difference", "Total venue goal difference"),
        ("goal_difference_per_match", "goal_difference_per_match", "Venue goal difference per match"),
        ("clean_sheets", "clean_sheets", "Total venue clean sheets"),
        ("clean_sheet_rate", "clean_sheet_rate", "Venue clean sheet rate ratio"),
        ("failed_to_score", "failed_to_score", "Total venue matches failed to score"),
        ("failed_to_score_rate", "failed_to_score_rate", "Venue failed to score rate ratio"),
    ]

    for side in sides:
        venue_label = "home" if side == "home" else "away"
        for w in windows:
            for key_suffix, attr_name, label in metrics_map:
                fkey = f"{side}_venue_{key_suffix}_last_{w}_v1"
                desc = f"{side.title()} team {label.lower()} in last {w} {venue_label} matches prior to cutoff."
                calculators[fkey] = BaseVenueFormCalculator(
                    feature_key=fkey,
                    target_side=side,
                    metric_name=attr_name,
                    window_size=w,
                    description=desc,
                )

    return calculators
