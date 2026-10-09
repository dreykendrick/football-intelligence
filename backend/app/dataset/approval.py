"""
Historical Dataset Release Approval & Lifecycle Workflow Service
Handles validation gating, transition to APPROVED status, supersession, retirement, and immutability enforcement.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.dataset.base import (
    DatasetAlreadyApprovedError,
    DatasetReleaseDTO,
    DatasetReleaseStatusEnum,
    DatasetSeasonDTO,
    DatasetValidationError,
    ImmutableDatasetError,
)
from app.dataset.validator import HistoricalDatasetValidator
from app.db.models import HistoricalDatasetRelease


class HistoricalDatasetApprover:
    """Approval workflow and lifecycle management service for dataset releases."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def approve_release(
        self,
        dataset_key: str = "mvp_a_historical",
        version: str = "v1",
        accepted_warnings: list[str] | None = None,
        approver_info: str = "Developer CLI Workflow",
    ) -> DatasetReleaseDTO:
        """
        Validates and approves a historical dataset release candidate.
        Transition from DRAFT / VALIDATING -> APPROVED.
        Once APPROVED, membership becomes strictly immutable.
        """
        accepted_warnings = accepted_warnings or []

        release = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=version)
            .first()
        )

        if not release:
            raise DatasetValidationError(f"Dataset release {dataset_key}:{version} does not exist.")

        if release.status == DatasetReleaseStatusEnum.APPROVED.value:
            raise DatasetAlreadyApprovedError(
                f"Dataset release {dataset_key}:{version} is already APPROVED and immutable."
            )

        # 1. Run validation engine
        validator = HistoricalDatasetValidator(self.db)
        val_report = validator.validate_release(
            dataset_key=dataset_key, version=version, accepted_warnings=accepted_warnings
        )

        if not val_report.is_valid:
            release.status = DatasetReleaseStatusEnum.FAILED.value
            self.db.commit()
            raise DatasetValidationError(
                f"Dataset approval FAILED for {dataset_key}:{version}! Blockers: {val_report.blockers}"
            )

        # 2. Transition to APPROVED atomically
        release.status = DatasetReleaseStatusEnum.APPROVED.value
        release.approved_at = datetime.now(UTC)
        release.warning_acceptances = {
            "accepted_warnings": accepted_warnings,
            "approved_by": approver_info,
            "approved_timestamp": release.approved_at.isoformat(),
        }

        self.db.commit()
        self.db.refresh(release)

        season_dtos = [
            DatasetSeasonDTO(
                id=s.id,
                competition_id=s.competition_id,
                season_id=s.season_id,
                competition_code=s.competition_code,
                season_year=s.season_year,
                readiness_status=s.readiness_status,
                match_count=s.match_count,
                expected_matches=s.expected_matches,
                source_provider_key=s.source_provider_key,
                source_reference=s.source_reference,
                source_checksum=s.source_checksum,
                metadata_payload=s.metadata_payload,
            )
            for s in release.seasons
        ]

        return DatasetReleaseDTO(
            id=release.id,
            key=release.key,
            version=release.version,
            description=release.description,
            status=DatasetReleaseStatusEnum(release.status),
            selection_policy_key=release.selection_policy_key,
            selection_policy_version=release.selection_policy_version,
            total_competitions=release.total_competitions,
            total_seasons=release.total_seasons,
            total_matches=release.total_matches,
            dataset_fingerprint=release.dataset_fingerprint,
            quality_run_id=release.quality_run_id,
            quality_status=release.quality_status,
            identity_readiness_status=release.identity_readiness_status,
            warning_acceptances=release.warning_acceptances,
            metadata_payload=release.metadata_payload,
            approved_at=release.approved_at,
            supersedes_dataset_id=release.supersedes_dataset_id,
            created_at=release.created_at,
            updated_at=release.updated_at,
            seasons=season_dtos,
        )

    def assert_immutable(self, release: HistoricalDatasetRelease) -> None:
        """Asserts that an APPROVED dataset release cannot be mutated."""
        if release.status == DatasetReleaseStatusEnum.APPROVED.value:
            raise ImmutableDatasetError(
                f"Dataset release {release.key}:{release.version} is APPROVED and strictly immutable."
            )

    def supersede_release(
        self,
        old_key: str,
        old_version: str,
        new_key: str,
        new_version: str,
    ) -> None:
        """Marks an old approved release as SUPERSEDED by a new release."""
        old_rel = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=old_key, version=old_version)
            .first()
        )
        new_rel = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=new_key, version=new_version)
            .first()
        )

        if not old_rel or not new_rel:
            raise DatasetValidationError("Both old and new releases must exist to execute supersession.")

        old_rel.status = DatasetReleaseStatusEnum.SUPERSEDED.value
        new_rel.supersedes_dataset_id = old_rel.id
        self.db.commit()

    def retire_release(self, key: str, version: str) -> None:
        """Transitions a dataset release to RETIRED status."""
        rel = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=key, version=version)
            .first()
        )
        if not rel:
            raise DatasetValidationError(f"Release {key}:{version} not found.")

        rel.status = DatasetReleaseStatusEnum.RETIRED.value
        self.db.commit()
