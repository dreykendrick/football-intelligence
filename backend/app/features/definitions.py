"""
Feature Metadata Definitions & Catalog Specifications
Defines formal DTO schemas and catalog metadata for all supported Phase 3 statistical features.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from app.features.base import MissingnessReason


class FeatureDefinitionDTO(BaseModel):
    """Metadata specification for a versioned feature definition."""

    feature_key: str
    name: str
    version: str = "1.0.0"
    description: str
    category: str  # e.g., "HISTORICAL_COUNTS", "GOALS", "FORM", "VENUE_FORM", "LEAGUE_BASELINE", "STRENGTH", "ELO", "REST_SCHEDULE"
    data_type: str = "FLOAT"  # FLOAT, INT, BOOL, STRING
    cutoff_policy: str = "STRICT_BEFORE_KICKOFF"
    missing_value_policy: MissingnessReason = MissingnessReason.INSUFFICIENT_HISTORY
    minimum_history: int = 1
    required_inputs: list[str] = Field(default_factory=list)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


# Standard MVP-A Feature Metadata Definitions
CORE_FEATURE_DEFINITIONS: dict[str, FeatureDefinitionDTO] = {
    # Historical Counts
    "home_matches_played_v1": FeatureDefinitionDTO(
        feature_key="home_matches_played_v1",
        name="Home Matches Played Count",
        version="1.0.0",
        description="Number of matches played by the home team prior to cutoff.",
        category="HISTORICAL_COUNTS",
        data_type="INT",
        minimum_history=0,
    ),
    "away_matches_played_v1": FeatureDefinitionDTO(
        feature_key="away_matches_played_v1",
        name="Away Matches Played Count",
        version="1.0.0",
        description="Number of matches played by the away team prior to cutoff.",
        category="HISTORICAL_COUNTS",
        data_type="INT",
        minimum_history=0,
    ),
    "total_matches_played_v1": FeatureDefinitionDTO(
        feature_key="total_matches_played_v1",
        name="Total Matches Played Count",
        version="1.0.0",
        description="Combined total historical matches played by home and away teams.",
        category="HISTORICAL_COUNTS",
        data_type="INT",
        minimum_history=0,
    ),
    # Historical Goal Averages
    "home_goals_scored_avg_v1": FeatureDefinitionDTO(
        feature_key="home_goals_scored_avg_v1",
        name="Home Goals Scored Average",
        version="1.0.0",
        description="Average goals scored per home match by the home team prior to cutoff.",
        category="GOALS",
        minimum_history=1,
    ),
    "home_goals_conceded_avg_v1": FeatureDefinitionDTO(
        feature_key="home_goals_conceded_avg_v1",
        name="Home Goals Conceded Average",
        version="1.0.0",
        description="Average goals conceded per home match by the home team prior to cutoff.",
        category="GOALS",
        minimum_history=1,
    ),
    "away_goals_scored_avg_v1": FeatureDefinitionDTO(
        feature_key="away_goals_scored_avg_v1",
        name="Away Goals Scored Average",
        version="1.0.0",
        description="Average goals scored per away match by the away team prior to cutoff.",
        category="GOALS",
        minimum_history=1,
    ),
    "away_goals_conceded_avg_v1": FeatureDefinitionDTO(
        feature_key="away_goals_conceded_avg_v1",
        name="Away Goals Conceded Average",
        version="1.0.0",
        description="Average goals conceded per away match by the away team prior to cutoff.",
        category="GOALS",
        minimum_history=1,
    ),
    # League Point-in-Time Baselines
    "league_home_goals_per_match_v1": FeatureDefinitionDTO(
        feature_key="league_home_goals_per_match_v1",
        name="League Point-in-Time Home Goals Per Match",
        version="1.0.0",
        description="Point-in-time average home goals scored in the target competition-season prior to cutoff.",
        category="LEAGUE_BASELINE",
        minimum_history=1,
    ),
    "league_away_goals_per_match_v1": FeatureDefinitionDTO(
        feature_key="league_away_goals_per_match_v1",
        name="League Point-in-Time Away Goals Per Match",
        version="1.0.0",
        description="Point-in-time average away goals scored in the target competition-season prior to cutoff.",
        category="LEAGUE_BASELINE",
        minimum_history=1,
    ),
    # Attack & Defense Strength Ratios (Season-to-Date)
    "home_attack_strength_v1": FeatureDefinitionDTO(
        feature_key="home_attack_strength_v1",
        name="Home Attack Strength Ratio",
        version="1.0.0",
        description="Home team average home goals scored divided by league home average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    "away_attack_strength_v1": FeatureDefinitionDTO(
        feature_key="away_attack_strength_v1",
        name="Away Attack Strength Ratio",
        version="1.0.0",
        description="Away team average away goals scored divided by league away average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    "home_defense_strength_v1": FeatureDefinitionDTO(
        feature_key="home_defense_strength_v1",
        name="Home Defense Strength Ratio",
        version="1.0.0",
        description="Home team average home goals conceded divided by league away average goals (>1.0 indicates weaker defense).",
        category="STRENGTH",
        minimum_history=1,
    ),
    "away_defense_strength_v1": FeatureDefinitionDTO(
        feature_key="away_defense_strength_v1",
        name="Away Defense Strength Ratio",
        version="1.0.0",
        description="Away team average away goals conceded divided by league home average goals (>1.0 indicates weaker defense).",
        category="STRENGTH",
        minimum_history=1,
    ),
    # Attack & Defense Strength Ratios (Windowed Last 5)
    "home_attack_strength_last_5_v1": FeatureDefinitionDTO(
        feature_key="home_attack_strength_last_5_v1",
        name="Home Attack Strength Ratio (Last 5 Home Matches)",
        version="1.0.0",
        description="Home team home goals scored per match in last 5 home matches divided by league home average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    "away_attack_strength_last_5_v1": FeatureDefinitionDTO(
        feature_key="away_attack_strength_last_5_v1",
        name="Away Attack Strength Ratio (Last 5 Away Matches)",
        version="1.0.0",
        description="Away team away goals scored per match in last 5 away matches divided by league away average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    "home_defense_strength_last_5_v1": FeatureDefinitionDTO(
        feature_key="home_defense_strength_last_5_v1",
        name="Home Defense Strength Ratio (Last 5 Home Matches)",
        version="1.0.0",
        description="Home team home goals conceded per match in last 5 home matches divided by league away average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    "away_defense_strength_last_5_v1": FeatureDefinitionDTO(
        feature_key="away_defense_strength_last_5_v1",
        name="Away Defense Strength Ratio (Last 5 Away Matches)",
        version="1.0.0",
        description="Away team away goals conceded per match in last 5 away matches divided by league home average goals.",
        category="STRENGTH",
        minimum_history=1,
    ),
    # Legacy 5-Match Form Aliases
    "home_recent_ppg_v1": FeatureDefinitionDTO(
        feature_key="home_recent_ppg_v1",
        name="Home Recent Points Per Match",
        version="1.0.0",
        description="Points per match earned by home team in last 5 matches prior to cutoff.",
        category="FORM",
        minimum_history=1,
    ),
    "away_recent_ppg_v1": FeatureDefinitionDTO(
        feature_key="away_recent_ppg_v1",
        name="Away Recent Points Per Match",
        version="1.0.0",
        description="Points per match earned by away team in last 5 matches prior to cutoff.",
        category="FORM",
        minimum_history=1,
    ),
    "home_recent_goals_scored_v1": FeatureDefinitionDTO(
        feature_key="home_recent_goals_scored_v1",
        name="Home Recent Goals Scored Total",
        version="1.0.0",
        description="Total goals scored by home team in last 5 matches prior to cutoff.",
        category="FORM",
        minimum_history=1,
    ),
    "away_recent_goals_conceded_v1": FeatureDefinitionDTO(
        feature_key="away_recent_goals_conceded_v1",
        name="Away Recent Goals Conceded Total",
        version="1.0.0",
        description="Total goals conceded by away team in last 5 matches prior to cutoff.",
        category="FORM",
        minimum_history=1,
    ),
    # Elo & Schedule
    "home_elo_v1": FeatureDefinitionDTO(
        feature_key="home_elo_v1",
        name="Home Pre-Match Elo Rating",
        version="1.0.0",
        description="Sequential pre-match Elo rating for the home team prior to target kickoff.",
        category="ELO",
        minimum_history=0,
    ),
    "away_elo_v1": FeatureDefinitionDTO(
        feature_key="away_elo_v1",
        name="Away Pre-Match Elo Rating",
        version="1.0.0",
        description="Sequential pre-match Elo rating for the away team prior to target kickoff.",
        category="ELO",
        minimum_history=0,
    ),
    "elo_difference_v1": FeatureDefinitionDTO(
        feature_key="elo_difference_v1",
        name="Pre-Match Elo Rating Difference",
        version="1.0.0",
        description="Home pre-match Elo rating minus away pre-match Elo rating.",
        category="ELO",
        minimum_history=0,
    ),
    "home_rest_days_v1": FeatureDefinitionDTO(
        feature_key="home_rest_days_v1",
        name="Home Rest Days",
        version="1.0.0",
        description="Days elapsed since the home team's previous finished match.",
        category="REST_SCHEDULE",
        minimum_history=1,
    ),
    "away_rest_days_v1": FeatureDefinitionDTO(
        feature_key="away_rest_days_v1",
        name="Away Rest Days",
        version="1.0.0",
        description="Days elapsed since the away team's previous finished match.",
        category="REST_SCHEDULE",
        minimum_history=1,
    ),
    "rest_days_difference_v1": FeatureDefinitionDTO(
        feature_key="rest_days_difference_v1",
        name="Rest Days Difference",
        version="1.0.0",
        description="Home rest days minus away rest days.",
        category="REST_SCHEDULE",
        minimum_history=1,
    ),
    "home_matches_last_14d_v1": FeatureDefinitionDTO(
        feature_key="home_matches_last_14d_v1",
        name="Home Matches Played in Last 14 Days",
        version="1.0.0",
        description="Number of matches played by the home team within 14 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "away_matches_last_14d_v1": FeatureDefinitionDTO(
        feature_key="away_matches_last_14d_v1",
        name="Away Matches Played in Last 14 Days",
        version="1.0.0",
        description="Number of matches played by the away team within 14 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "home_matches_last_7d_v1": FeatureDefinitionDTO(
        feature_key="home_matches_last_7d_v1",
        name="Home Matches Played in Last 7 Days",
        version="1.0.0",
        description="Number of observed matches played by the home team within 7 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "away_matches_last_7d_v1": FeatureDefinitionDTO(
        feature_key="away_matches_last_7d_v1",
        name="Away Matches Played in Last 7 Days",
        version="1.0.0",
        description="Number of observed matches played by the away team within 7 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "home_matches_last_21d_v1": FeatureDefinitionDTO(
        feature_key="home_matches_last_21d_v1",
        name="Home Matches Played in Last 21 Days",
        version="1.0.0",
        description="Number of observed matches played by the home team within 21 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "away_matches_last_21d_v1": FeatureDefinitionDTO(
        feature_key="away_matches_last_21d_v1",
        name="Away Matches Played in Last 21 Days",
        version="1.0.0",
        description="Number of observed matches played by the away team within 21 days prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "home_season_matches_played_v1": FeatureDefinitionDTO(
        feature_key="home_season_matches_played_v1",
        name="Home Season Matches Played Count",
        version="1.0.0",
        description="Number of observed matches played by the home team in the current season prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
    "away_season_matches_played_v1": FeatureDefinitionDTO(
        feature_key="away_season_matches_played_v1",
        name="Away Season Matches Played Count",
        version="1.0.0",
        description="Number of observed matches played by the away team in the current season prior to cutoff.",
        category="REST_SCHEDULE",
        data_type="INT",
        minimum_history=0,
    ),
}

# Dynamically populate Sprint 3.2 general form feature definitions across windows 3, 5, 10
_windows = (3, 5, 10)
_sides = ("home", "away")
_metrics_spec = [
    ("points", "Points", "INT", "Total points earned"),
    ("ppg", "Points Per Match", "FLOAT", "Points per match"),
    ("wins", "Wins", "INT", "Total wins"),
    ("draws", "Draws", "INT", "Total draws"),
    ("losses", "Losses", "INT", "Total losses"),
    ("win_rate", "Win Rate", "FLOAT", "Win rate ratio"),
    ("draw_rate", "Draw Rate", "FLOAT", "Draw rate ratio"),
    ("loss_rate", "Loss Rate", "FLOAT", "Loss rate ratio"),
    ("goals_scored", "Goals Scored", "INT", "Total goals scored"),
    ("goals_scored_per_match", "Goals Scored Per Match", "FLOAT", "Goals scored per match"),
    ("goals_conceded", "Goals Conceded", "INT", "Total goals conceded"),
    ("goals_conceded_per_match", "Goals Conceded Per Match", "FLOAT", "Goals conceded per match"),
    ("goal_difference", "Goal Difference", "INT", "Total goal difference"),
    ("goal_difference_per_match", "Goal Difference Per Match", "FLOAT", "Goal difference per match"),
    ("clean_sheets", "Clean Sheets", "INT", "Total clean sheets"),
    ("clean_sheet_rate", "Clean Sheet Rate", "FLOAT", "Clean sheet rate ratio"),
    ("failed_to_score", "Failed to Score Matches", "INT", "Total matches failed to score"),
    ("failed_to_score_rate", "Failed to Score Rate", "FLOAT", "Failed to score rate ratio"),
]

for _side in _sides:
    for _w in _windows:
        for _key_suffix, _label_name, _dtype, _desc in _metrics_spec:
            _fkey = f"{_side}_{_key_suffix}_last_{_w}_v1"
            if _fkey not in CORE_FEATURE_DEFINITIONS:
                CORE_FEATURE_DEFINITIONS[_fkey] = FeatureDefinitionDTO(
                    feature_key=_fkey,
                    name=f"{_side.title()} {_label_name} (Last {_w})",
                    version="1.0.0",
                    description=f"{_side.title()} team {_desc.lower()} in last {_w} matches prior to cutoff.",
                    category="FORM" if "goals" not in _key_suffix else "GOALS",
                    data_type=_dtype,
                    minimum_history=1,
                )

# Dynamically populate Sprint 3.3 venue form feature definitions across windows 3, 5, 10
for _side in _sides:
    _vlabel = "home" if _side == "home" else "away"
    for _w in _windows:
        for _key_suffix, _label_name, _dtype, _desc in _metrics_spec:
            _vfkey = f"{_side}_venue_{_key_suffix}_last_{_w}_v1"
            if _vfkey not in CORE_FEATURE_DEFINITIONS:
                CORE_FEATURE_DEFINITIONS[_vfkey] = FeatureDefinitionDTO(
                    feature_key=_vfkey,
                    name=f"{_side.title()} Venue {_label_name} (Last {_w} {_vlabel.title()})",
                    version="1.0.0",
                    description=f"{_side.title()} team {_desc.lower()} in last {_w} {_vlabel} matches prior to cutoff.",
                    category="VENUE_FORM",
                    data_type=_dtype,
                    minimum_history=1,
                )
