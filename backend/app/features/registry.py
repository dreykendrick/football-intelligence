"""
Feature Calculator Registry & Metadata Engine
Holds formal instances of all implemented MVP-A feature calculators and maps metadata definitions.
"""
from __future__ import annotations

from app.features.base import BaseFeatureCalculator
from app.features.calculators.attack_defense import (
    AwayAttackStrengthCalculator,
    AwayDefenseStrengthCalculator,
    HomeAttackStrengthCalculator,
    HomeDefenseStrengthCalculator,
    LeagueAwayGoalsAvgCalculator,
    LeagueHomeGoalsAvgCalculator,
)
from app.features.calculators.elo import (
    AwayEloCalculator,
    EloDifferenceCalculator,
    HomeEloCalculator,
)
from app.features.calculators.form_calculators import generate_form_calculators
from app.features.calculators.goals import (
    AwayGoalsConcededAvgCalculator,
    AwayGoalsScoredAvgCalculator,
    HomeGoalsConcededAvgCalculator,
    HomeGoalsScoredAvgCalculator,
)
from app.features.calculators.historical_counts import (
    AwayMatchesPlayedCalculator,
    HomeMatchesPlayedCalculator,
    TotalMatchesPlayedCalculator,
)
from app.features.calculators.rest_congestion import (
    AwayMatchesLast14DaysCalculator,
    AwayMatchesLast21DaysCalculator,
    AwayMatchesLast7DaysCalculator,
    AwayRestDaysCalculator,
    AwaySeasonMatchesPlayedCalculator,
    HomeMatchesLast14DaysCalculator,
    HomeMatchesLast21DaysCalculator,
    HomeMatchesLast7DaysCalculator,
    HomeRestDaysCalculator,
    HomeSeasonMatchesPlayedCalculator,
    RestDaysDifferenceCalculator,
)
from app.features.calculators.venue_calculators import generate_venue_form_calculators
from app.features.definitions import CORE_FEATURE_DEFINITIONS, FeatureDefinitionDTO

FEATURE_CATALOG: dict[str, BaseFeatureCalculator] = {
    # Historical Counts
    "home_matches_played_v1": HomeMatchesPlayedCalculator(),
    "away_matches_played_v1": AwayMatchesPlayedCalculator(),
    "total_matches_played_v1": TotalMatchesPlayedCalculator(),
    # Goal Rates
    "home_goals_scored_avg_v1": HomeGoalsScoredAvgCalculator(),
    "home_goals_conceded_avg_v1": HomeGoalsConcededAvgCalculator(),
    "away_goals_scored_avg_v1": AwayGoalsScoredAvgCalculator(),
    "away_goals_conceded_avg_v1": AwayGoalsConcededAvgCalculator(),
    # League Point-in-Time Baselines
    "league_home_goals_per_match_v1": LeagueHomeGoalsAvgCalculator(),
    "league_away_goals_per_match_v1": LeagueAwayGoalsAvgCalculator(),
    # Attack & Defense Strength (Season-to-Date)
    "home_attack_strength_v1": HomeAttackStrengthCalculator(),
    "away_attack_strength_v1": AwayAttackStrengthCalculator(),
    "home_defense_strength_v1": HomeDefenseStrengthCalculator(),
    "away_defense_strength_v1": AwayDefenseStrengthCalculator(),
    # Attack & Defense Strength (Windowed Last 5)
    "home_attack_strength_last_5_v1": HomeAttackStrengthCalculator(window_size=5, feature_key="home_attack_strength_last_5_v1"),
    "away_attack_strength_last_5_v1": AwayAttackStrengthCalculator(window_size=5, feature_key="away_attack_strength_last_5_v1"),
    "home_defense_strength_last_5_v1": HomeDefenseStrengthCalculator(window_size=5, feature_key="home_defense_strength_last_5_v1"),
    "away_defense_strength_last_5_v1": AwayDefenseStrengthCalculator(window_size=5, feature_key="away_defense_strength_last_5_v1"),
    # Baseline Elo
    "home_elo_v1": HomeEloCalculator(),
    "away_elo_v1": AwayEloCalculator(),
    "elo_difference_v1": EloDifferenceCalculator(),
    # Rest Days & Congestion
    "home_rest_days_v1": HomeRestDaysCalculator(),
    "away_rest_days_v1": AwayRestDaysCalculator(),
    "rest_days_difference_v1": RestDaysDifferenceCalculator(),
    "home_matches_last_7d_v1": HomeMatchesLast7DaysCalculator(),
    "away_matches_last_7d_v1": AwayMatchesLast7DaysCalculator(),
    "home_matches_last_14d_v1": HomeMatchesLast14DaysCalculator(),
    "away_matches_last_14d_v1": AwayMatchesLast14DaysCalculator(),
    "home_matches_last_21d_v1": HomeMatchesLast21DaysCalculator(),
    "away_matches_last_21d_v1": AwayMatchesLast21DaysCalculator(),
    "home_season_matches_played_v1": HomeSeasonMatchesPlayedCalculator(),
    "away_season_matches_played_v1": AwaySeasonMatchesPlayedCalculator(),
}

# Merge all Sprint 3.2 form calculators across windows 3, 5, 10
FEATURE_CATALOG.update(generate_form_calculators())

# Merge all Sprint 3.3 venue form calculators across windows 3, 5, 10
FEATURE_CATALOG.update(generate_venue_form_calculators())


class FeatureRegistry:
    """Central manager providing feature calculator lookup and metadata registry services."""

    def __init__(self) -> None:
        self._calculators: dict[str, BaseFeatureCalculator] = dict(FEATURE_CATALOG)
        self._definitions: dict[str, FeatureDefinitionDTO] = dict(CORE_FEATURE_DEFINITIONS)

    def register(self, calculator: BaseFeatureCalculator, definition: FeatureDefinitionDTO | None = None) -> None:
        """Registers a calculator instance and optional metadata specification."""
        self._calculators[calculator.feature_key] = calculator
        if definition:
            self._definitions[calculator.feature_key] = definition

    def get_calculator(self, feature_key: str) -> BaseFeatureCalculator:
        """Retrieves calculator instance for a given feature key."""
        if feature_key not in self._calculators:
            raise KeyError(f"Feature calculator not found for feature key: '{feature_key}'")
        return self._calculators[feature_key]

    def get_definition(self, feature_key: str) -> FeatureDefinitionDTO | None:
        """Retrieves metadata definition DTO for a given feature key."""
        return self._definitions.get(feature_key)

    def list_feature_keys(self) -> list[str]:
        """Returns list of registered feature keys."""
        return sorted(self._calculators.keys())

    def list_definitions(self) -> list[FeatureDefinitionDTO]:
        """Returns list of registered feature definitions."""
        return [self._definitions[k] for k in sorted(self._definitions.keys()) if k in self._definitions]


# Default global instance
global_feature_registry = FeatureRegistry()
