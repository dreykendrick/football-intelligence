"""
Downstream Historical Dataset Query & Lock Verification Service
Provides strict, approved-only dataset query interfaces for feature engineering and scientific backtesting.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.dataset.base import (
    DatasetFingerprintMismatchError,
    DatasetReleaseStatusEnum,
    DatasetValidationError,
)
from app.dataset.fingerprint import DatasetFingerprintCalculator
from app.db.models import (
    Competition,
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    HistoricalDatasetSeason,
    Match,
)


class HistoricalDatasetQueryService:
    """Service providing explicit, approved-only historical dataset query access."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def get_dataset_matches(
        self,
        dataset_key: str = "mvp_a_historical",
        version: str = "v1",
        approved_only: bool = True,
        competition_code: str | None = None,
        season_year: str | None = None,
    ) -> list[Match]:
        """
        Retrieves canonical Match records belonging strictly to the specified dataset release.
        Enforces approved_only=True by default for production scientific workflows.
        """
        query = self.db.query(HistoricalDatasetRelease).filter_by(key=dataset_key, version=version)
        release = query.first()

        if not release:
            raise DatasetValidationError(f"Historical dataset release {dataset_key}:{version} does not exist.")

        if approved_only and release.status != DatasetReleaseStatusEnum.APPROVED.value:
            raise DatasetValidationError(
                f"Dataset release {dataset_key}:{version} is in status '{release.status}'. "
                "Official scientific workflows require APPROVED datasets."
            )

        match_query = (
            self.db.query(Match)
            .join(HistoricalDatasetMatch, Match.id == HistoricalDatasetMatch.match_id)
            .filter(HistoricalDatasetMatch.dataset_release_id == release.id)
        )

        if competition_code:
            comp = self.db.query(Competition).filter_by(code=competition_code).first()
            if comp:
                match_query = match_query.filter(Match.season.has(competition_id=comp.id))

        if season_year:
            match_query = match_query.filter(Match.season.has(season_year=season_year))

        return match_query.order_by(Match.kickoff_utc.asc()).all()

    def verify_dataset_lock(self, dataset_key: str, version: str) -> bool:
        """
        Recomputes fingerprint for an existing dataset release and verifies lock integrity.
        Raises DatasetFingerprintMismatchError if database content has drifted.
        """
        release = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=version)
            .first()
        )

        if not release:
            raise DatasetValidationError(f"Dataset release {dataset_key}:{version} not found.")

        seasons = (
            self.db.query(HistoricalDatasetSeason)
            .filter_by(dataset_release_id=release.id)
            .all()
        )
        matches = (
            self.db.query(HistoricalDatasetMatch)
            .filter_by(dataset_release_id=release.id)
            .all()
        )

        seasons_data = [
            {
                "competition_code": s.competition_code,
                "season_year": s.season_year,
                "source_checksum": s.source_checksum or "",
            }
            for s in seasons
        ]
        matches_data = [
            {
                "match_id": m.match_id,
                "kickoff_utc": m.kickoff_utc,
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_score": m.match.home_score if m.match else None,
                "away_score": m.match.away_score if m.match else None,
                "raw_source_checksum": m.raw_source_checksum or "",
            }
            for m in matches
        ]

        current_fp = DatasetFingerprintCalculator.compute_fingerprint(
            key=release.key,
            version=release.version,
            selection_policy_key=release.selection_policy_key,
            selection_policy_version=release.selection_policy_version,
            seasons_data=seasons_data,
            matches_data=matches_data,
        )

        if current_fp != release.dataset_fingerprint:
            raise DatasetFingerprintMismatchError(
                f"DRIFT DETECTED! Locked fingerprint ({release.dataset_fingerprint}) does not match current state ({current_fp})."
            )

        return True

    def get_approved_release(self, dataset_key: str, version: str) -> HistoricalDatasetRelease:
        """Fetches approved release entity."""
        release = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=version, status=DatasetReleaseStatusEnum.APPROVED.value)
            .first()
        )

        if not release:
            raise DatasetValidationError(f"No APPROVED dataset release found for {dataset_key}:{version}.")

        return release
