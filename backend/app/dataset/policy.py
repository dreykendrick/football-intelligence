"""
Dataset Selection Policy Engine
Executes deterministic selection of target competition-seasons based on quality readiness and configurable parameters.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.dataset.base import (
    BlockedSeasonError,
    DatasetSelectionPolicyEnum,
    InsufficientCoverageError,
)
from app.db.models import Competition, Season
from app.quality.base import ReadinessStatusEnum, SeasonCompletenessReport

if TYPE_CHECKING:
    pass


class DatasetSelectionPolicyEngine:
    """Deterministic Competition-Season Selection Policy Implementation."""

    TARGET_COMPETITIONS = ["E0", "SP1", "I1", "D1"]
    MIN_SEASONS_PER_COMPETITION = 3

    def __init__(
        self,
        db_session: Session,
        policy_key: str = DatasetSelectionPolicyEnum.MVP_A_RECENT_3_USABLE_SEASONS_V1.value,
        policy_version: str = "1.0.0",
    ) -> None:
        self.db = db_session
        self.policy_key = policy_key
        self.policy_version = policy_version

    def select_seasons(
        self,
        season_quality_reports: list[SeasonCompletenessReport],
        explicit_overrides: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Applies selection policy to determine which competition-seasons belong to the dataset release.
        Returns a list of selected season specifications.
        """
        # Map season completeness reports by (comp_code, season_year)
        reports_map = {
            (r.competition_code, r.season_year): r for r in season_quality_reports
        }

        selected_specs: list[dict[str, Any]] = []

        # Process each target competition
        for comp_code in self.TARGET_COMPETITIONS:
            comp = self.db.query(Competition).filter_by(code=comp_code).first()
            if not comp:
                continue

            available_seasons = (
                self.db.query(Season)
                .filter_by(competition_id=comp.id)
                .order_by(Season.season_year.desc())
                .all()
            )

            # Check explicit override for this competition if provided
            override_years = explicit_overrides.get(comp_code) if explicit_overrides else None

            competition_selected_count = 0

            for season in available_seasons:
                year = season.season_year
                report = reports_map.get((comp_code, year))
                readiness_status = (
                    report.readiness_status.value if report else ReadinessStatusEnum.NOT_READY.value
                )

                # Explicit selection filter
                if override_years is not None:
                    if year not in override_years:
                        continue
                    if readiness_status == ReadinessStatusEnum.BLOCKED.value:
                        raise BlockedSeasonError(
                            f"Season {comp_code} {year} is explicitly requested but has BLOCKED quality status."
                        )
                    should_include = True
                else:
                    # Automatic policy selection: skip BLOCKED or NOT_READY seasons, take top N usable
                    if readiness_status == ReadinessStatusEnum.BLOCKED.value:
                        continue
                    if readiness_status == ReadinessStatusEnum.NOT_READY.value:
                        continue

                    should_include = competition_selected_count < self.MIN_SEASONS_PER_COMPETITION

                if should_include:
                    selected_specs.append({
                        "competition_id": comp.id,
                        "season_id": season.id,
                        "competition_code": comp_code,
                        "season_year": year,
                        "readiness_status": readiness_status,
                        "expected_matches": report.expected_matches if report else None,
                        "actual_matches": report.total_matches if report else 0,
                    })
                    competition_selected_count += 1

        return selected_specs

    def validate_coverage(self, selected_specs: list[dict[str, Any]]) -> dict[str, int]:
        """
        Validates that all target competitions satisfy minimum season coverage.
        Raises InsufficientCoverageError if coverage is deficient.
        """
        counts: dict[str, int] = dict.fromkeys(self.TARGET_COMPETITIONS, 0)
        for spec in selected_specs:
            code = spec["competition_code"]
            counts[code] = counts.get(code, 0) + 1

        deficient = {code: count for code, count in counts.items() if count < self.MIN_SEASONS_PER_COMPETITION}
        if deficient:
            raise InsufficientCoverageError(
                f"Dataset release coverage deficient! Target competitions requiring >= {self.MIN_SEASONS_PER_COMPETITION} "
                f"usable completed seasons: {deficient}. Selected total: {counts}."
            )

        return counts
