"""
Team Match Observation Builder & Rolling Form Aggregator
Provides structured observation containers and reusable rolling form aggregation logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Match


class TeamMatchObservation(BaseModel):
    """Structured representation of a finished match from a single team's perspective."""
    match_id: UUID
    team_id: UUID
    opponent_id: UUID
    kickoff_utc: datetime
    venue: Literal["HOME", "AWAY"]
    goals_for: int
    goals_against: int
    result: Literal["WIN", "DRAW", "LOSS"]
    points: Literal[3, 1, 0]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TeamMatchObservationBuilder:
    """Converts canonical Match entities into team-perspective observations."""

    @staticmethod
    def build_observation(match: Match, team_id: UUID) -> TeamMatchObservation | None:
        if match.home_score is None or match.away_score is None:
            return None

        if match.home_team_id == team_id:
            venue: Literal["HOME", "AWAY"] = "HOME"
            opponent_id = match.away_team_id
            goals_for = match.home_score
            goals_against = match.away_score
        elif match.away_team_id == team_id:
            venue = "AWAY"
            opponent_id = match.home_team_id
            goals_for = match.away_score
            goals_against = match.home_score
        else:
            return None

        if goals_for > goals_against:
            res: Literal["WIN", "DRAW", "LOSS"] = "WIN"
            pts: Literal[3, 1, 0] = 3
        elif goals_for == goals_against:
            res = "DRAW"
            pts = 1
        else:
            res = "LOSS"
            pts = 0

        return TeamMatchObservation(
            match_id=match.id,
            team_id=team_id,
            opponent_id=opponent_id,
            kickoff_utc=match.kickoff_utc,
            venue=venue,
            goals_for=goals_for,
            goals_against=goals_against,
            result=res,
            points=pts,
        )

    @classmethod
    def build_observations(cls, matches: list[Match], team_id: UUID) -> list[TeamMatchObservation]:
        obs_list: list[TeamMatchObservation] = []
        for m in matches:
            obs = cls.build_observation(m, team_id)
            if obs is not None:
                obs_list.append(obs)
        return obs_list


class RollingFormMetrics(BaseModel):
    """Aggregated rolling performance metrics over an available sample window."""
    sample_size: int = 0
    points: int = 0
    points_per_match: float | None = None
    wins: int = 0
    draws: int = 0
    losses: int = 0
    win_rate: float | None = None
    draw_rate: float | None = None
    loss_rate: float | None = None
    goals_scored: int = 0
    goals_scored_per_match: float | None = None
    goals_conceded: int = 0
    goals_conceded_per_match: float | None = None
    goal_difference: int = 0
    goal_difference_per_match: float | None = None
    clean_sheets: int = 0
    clean_sheet_rate: float | None = None
    failed_to_score: int = 0
    failed_to_score_rate: float | None = None


class RollingFormAggregator:
    """Aggregates TeamMatchObservations over rolling windows."""

    @staticmethod
    def aggregate(observations: list[TeamMatchObservation], window_size: int) -> RollingFormMetrics:
        """
        Aggregates up to window_size observations (expected sorted newest to oldest).
        Handles partial windows using actual available sample_size.
        Returns sample_size=0 and None rates if no observations exist.
        """
        sample = observations[:window_size]
        n = len(sample)
        if n == 0:
            return RollingFormMetrics(sample_size=0)

        pts = sum(obs.points for obs in sample)
        wins = sum(1 for obs in sample if obs.result == "WIN")
        draws = sum(1 for obs in sample if obs.result == "DRAW")
        losses = sum(1 for obs in sample if obs.result == "LOSS")

        goals_for = sum(obs.goals_for for obs in sample)
        goals_against = sum(obs.goals_against for obs in sample)
        gd = goals_for - goals_against

        cs = sum(1 for obs in sample if obs.goals_against == 0)
        fts = sum(1 for obs in sample if obs.goals_for == 0)

        return RollingFormMetrics(
            sample_size=n,
            points=pts,
            points_per_match=round(pts / n, 4),
            wins=wins,
            draws=draws,
            losses=losses,
            win_rate=round(wins / n, 4),
            draw_rate=round(draws / n, 4),
            loss_rate=round(losses / n, 4),
            goals_scored=goals_for,
            goals_scored_per_match=round(goals_for / n, 4),
            goals_conceded=goals_against,
            goals_conceded_per_match=round(goals_against / n, 4),
            goal_difference=gd,
            goal_difference_per_match=round(gd / n, 4),
            clean_sheets=cs,
            clean_sheet_rate=round(cs / n, 4),
            failed_to_score=fts,
            failed_to_score_rate=round(fts / n, 4),
        )
