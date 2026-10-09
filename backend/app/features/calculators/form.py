"""
Recent Form Feature Calculators
Re-exports form calculators and backward-compatible default calculator aliases.
"""
from __future__ import annotations

from app.features.calculators.form_calculators import (
    BaseFormCalculator,
    generate_form_calculators,
)

_form_calcs = generate_form_calculators()

HomeRecentPPGCalculator = lambda: _form_calcs["home_recent_ppg_v1"]
AwayRecentPPGCalculator = lambda: _form_calcs["away_recent_ppg_v1"]
HomeRecentGoalsScoredCalculator = lambda: _form_calcs["home_recent_goals_scored_v1"]
AwayRecentGoalsConcededCalculator = lambda: _form_calcs["away_recent_goals_conceded_v1"]
