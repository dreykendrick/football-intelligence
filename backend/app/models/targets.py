"""
Target Definitions & Label Generation Architecture
Defines immutable target specifications (1X2, Over/Under 2.5, BTTS, Home Goals, Away Goals)
and provides strict post-match label derivation for finished fixtures.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from app.db.models import Match


class TargetDefinitionDTO(BaseModel):
    """Immutable specification for a target label."""
    target_key: str
    version: str = "1.0.0"
    target_type: str  # "CATEGORICAL", "BOOLEAN", "CONTINUOUS"
    description: str
    valid_match_policy: str = "FINISHED_ONLY"


# Canonical Target Catalog Specifications
CORE_TARGET_DEFINITIONS: dict[str, TargetDefinitionDTO] = {
    "match_result_1x2_v1": TargetDefinitionDTO(
        target_key="match_result_1x2_v1",
        version="1.0.0",
        target_type="CATEGORICAL",
        description="3-way match result label: HOME_WIN = 0, DRAW = 1, AWAY_WIN = 2",
    ),
    "over_under_2_5_v1": TargetDefinitionDTO(
        target_key="over_under_2_5_v1",
        version="1.0.0",
        target_type="BOOLEAN",
        description="Total match goals threshold label: True if total goals >= 3 else False",
    ),
    "btts_v1": TargetDefinitionDTO(
        target_key="btts_v1",
        version="1.0.0",
        target_type="BOOLEAN",
        description="Both Teams to Score label: True if both home_goals > 0 and away_goals > 0 else False",
    ),
    "home_goals_v1": TargetDefinitionDTO(
        target_key="home_goals_v1",
        version="1.0.0",
        target_type="CONTINUOUS",
        description="Non-negative integer final home goals scored label",
    ),
    "away_goals_v1": TargetDefinitionDTO(
        target_key="away_goals_v1",
        version="1.0.0",
        target_type="CONTINUOUS",
        description="Non-negative integer final away goals scored label",
    ),
}

# Explicit 1X2 Class Integer Encodings
HOME_WIN_LABEL: int = 0
DRAW_LABEL: int = 1
AWAY_WIN_LABEL: int = 2

CANONICAL_1X2_OUTCOMES: list[str] = ["HOME_WIN", "DRAW", "AWAY_WIN"]

INT_TO_1X2_MAP: dict[int, str] = {
    0: "HOME_WIN",
    1: "DRAW",
    2: "AWAY_WIN",
}

STR_TO_1X2_MAP: dict[str, int] = {
    "HOME_WIN": 0,
    "DRAW": 1,
    "AWAY_WIN": 2,
}


def encode_1x2(label: str | int) -> int:
    """Encodes a 1X2 outcome label string or integer to canonical int (0=HOME_WIN, 1=DRAW, 2=AWAY_WIN)."""
    if isinstance(label, int):
        if label in INT_TO_1X2_MAP:
            return label
        raise ValueError(f"Invalid integer 1X2 label: {label}. Must be one of {list(INT_TO_1X2_MAP.keys())}")
    label_str = str(label).strip().upper()
    if label_str in STR_TO_1X2_MAP:
        return STR_TO_1X2_MAP[label_str]
    raise ValueError(f"Invalid 1X2 string label: '{label}'. Must be one of {list(STR_TO_1X2_MAP.keys())}")


def decode_1x2(label_int: int) -> str:
    """Decodes a canonical integer 1X2 label to its standard semantic string."""
    if label_int in INT_TO_1X2_MAP:
        return INT_TO_1X2_MAP[label_int]
    raise ValueError(f"Invalid integer 1X2 label: {label_int}. Must be one of {list(INT_TO_1X2_MAP.keys())}")


def validate_1x2_label(label: str | int) -> None:
    """Validates that a 1X2 label is valid, raising ValueError otherwise."""
    encode_1x2(label)



class TargetLabelService:
    """Derives immutable post-match target labels strictly from finalized fixtures."""

    @staticmethod
    def validate_match_eligibility(match: Match) -> bool:
        """
        Validates whether a match is eligible for supervised label generation.
        Rejects scheduled, live, cancelled, postponed, abandoned, unresolved, or missing score fixtures.
        """
        if match.status != "FINISHED":
            return False
        if match.home_score is None or match.away_score is None:
            return False
        if match.home_score < 0 or match.away_score < 0:
            return False
        return True

    @classmethod
    def derive_labels_for_match(cls, match: Match) -> dict[str, Any]:
        """
        Derives all target labels for an eligible finished match.
        Raises ValueError if the match is ineligible.
        """
        if not cls.validate_match_eligibility(match):
            raise ValueError(
                f"Match {match.id} (status={match.status}, score={match.home_score}-{match.away_score}) "
                "is ineligible for target label generation."
            )

        home = match.home_score
        away = match.away_score

        # 1. 1X2 Category Encoding (0: HOME_WIN, 1: DRAW, 2: AWAY_WIN)
        if home > away:
            result_1x2 = HOME_WIN_LABEL
        elif home == away:
            result_1x2 = DRAW_LABEL
        else:
            result_1x2 = AWAY_WIN_LABEL

        # 2. Over/Under 2.5
        total_goals = home + away
        over_under_2_5 = total_goals >= 3

        # 3. Both Teams to Score (BTTS)
        btts = (home > 0) and (away > 0)

        return {
            "match_result_1x2_v1": result_1x2,
            "over_under_2_5_v1": over_under_2_5,
            "btts_v1": btts,
            "home_goals_v1": int(home),
            "away_goals_v1": int(away),
        }
