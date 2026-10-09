"""
General Rolling Team Form & Goal Performance Feature Calculators
Calculates rolling historical points, PPG, wins/draws/losses, goals scored/conceded, goal difference, clean sheets, and failed to score over windows N in {3, 5, 10}.
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

def _get_team_form_metrics(
    db: Session,
    team_id: UUID,
    cutoff_timestamp: datetime,
    target_match_id: UUID,
    window_size: int,
) -> RollingFormMetrics:
    """Helper retrieving observations and computing rolling form metrics for a target team."""
    matches = HistoricalQueryLayer.get_team_matches_before(
        db,
        team_id=team_id,
        cutoff_timestamp=cutoff_timestamp,
        limit=max(10, window_size),
        target_match_id=target_match_id,
        approved_only=False,
        enforce_date_only_precision=True,
    )
    observations = TeamMatchObservationBuilder.build_observations(matches, team_id)
    return RollingFormAggregator.aggregate(observations, window_size)


class BaseFormCalculator(BaseFeatureCalculator):
    """Base class for rolling team form calculators."""
    feature_key: str
    version: str = "1.0.0"
    description: str
    target_side: str  # "home" or "away"
    metric_name: str  # e.g. "points", "ppg", "goals_scored", etc.
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
        team_id = match.home_team_id if self.target_side == "home" else match.away_team_id
        metrics = _get_team_form_metrics(
            db=db,
            team_id=team_id,
            cutoff_timestamp=cutoff_timestamp,
            target_match_id=match.id,
            window_size=self.window_size,
        )

        if metrics.sample_size == 0:
            return FeatureCalculationResult(
                feature_key=self.feature_key,
                version=self.version,
                value=None,
                is_missing=True,
                missing_reason=MissingnessReason.INSUFFICIENT_HISTORY,
                sample_size=0,
                metadata_payload={"requested_window": self.window_size},
            )

        val = getattr(metrics, self.metric_name, None)
        return FeatureCalculationResult(
            feature_key=self.feature_key,
            version=self.version,
            value=val,
            is_missing=False,
            missing_reason=MissingnessReason.AVAILABLE,
            sample_size=metrics.sample_size,
            metadata_payload={"requested_window": self.window_size, "actual_sample_size": metrics.sample_size},
        )


def generate_form_calculators() -> dict[str, BaseFeatureCalculator]:
    """Generates all Sprint 3.2 form feature calculators for windows 3, 5, 10."""
    calculators: dict[str, BaseFeatureCalculator] = {}
    windows = (3, 5, 10)
    sides = ("home", "away")

    metrics_map = [
        ("points", "points", "Total points earned"),
        ("ppg", "points_per_match", "Points per match"),
        ("wins", "wins", "Total wins"),
        ("draws", "draws", "Total draws"),
        ("losses", "losses", "Total losses"),
        ("win_rate", "win_rate", "Win rate ratio"),
        ("draw_rate", "draw_rate", "Draw rate ratio"),
        ("loss_rate", "loss_rate", "Loss rate ratio"),
        ("goals_scored", "goals_scored", "Total goals scored"),
        ("goals_scored_per_match", "goals_scored_per_match", "Goals scored per match"),
        ("goals_conceded", "goals_conceded", "Total goals conceded"),
        ("goals_conceded_per_match", "goals_conceded_per_match", "Goals conceded per match"),
        ("goal_difference", "goal_difference", "Total goal difference"),
        ("goal_difference_per_match", "goal_difference_per_match", "Goal difference per match"),
        ("clean_sheets", "clean_sheets", "Total clean sheets"),
        ("clean_sheet_rate", "clean_sheet_rate", "Clean sheet rate ratio"),
        ("failed_to_score", "failed_to_score", "Total matches failed to score"),
        ("failed_to_score_rate", "failed_to_score_rate", "Failed to score rate ratio"),
    ]

    for side in sides:
        for w in windows:
            for key_suffix, attr_name, label in metrics_map:
                fkey = f"{side}_{key_suffix}_last_{w}_v1"
                desc = f"{side.title()} team {label.lower()} in last {w} matches prior to cutoff."
                calculators[fkey] = BaseFormCalculator(
                    feature_key=fkey,
                    target_side=side,
                    metric_name=attr_name,
                    window_size=w,
                    description=desc,
                )

    # Legacy Sprint 3.1 default 5-match aliases
    calculators["home_recent_ppg_v1"] = BaseFormCalculator(
        feature_key="home_recent_ppg_v1",
        target_side="home",
        metric_name="points_per_match",
        window_size=5,
        description="Home team PPG in last 5 matches prior to cutoff.",
    )
    calculators["away_recent_ppg_v1"] = BaseFormCalculator(
        feature_key="away_recent_ppg_v1",
        target_side="away",
        metric_name="points_per_match",
        window_size=5,
        description="Away team PPG in last 5 matches prior to cutoff.",
    )
    calculators["home_recent_goals_scored_v1"] = BaseFormCalculator(
        feature_key="home_recent_goals_scored_v1",
        target_side="home",
        metric_name="goals_scored",
        window_size=5,
        description="Home team goals scored in last 5 matches prior to cutoff.",
    )
    calculators["away_recent_goals_conceded_v1"] = BaseFormCalculator(
        feature_key="away_recent_goals_conceded_v1",
        target_side="away",
        metric_name="goals_conceded",
        window_size=5,
        description="Away team goals conceded in last 5 matches prior to cutoff.",
    )

    return calculators
