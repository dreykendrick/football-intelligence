"""
Historical Dataset Management Package
Provides dataset selection policies, candidate builder, validator, approval workflow, fingerprint calculator, query service, and CLI interface.
"""
from app.dataset.approval import HistoricalDatasetApprover
from app.dataset.base import (
    BlockedSeasonError,
    DatasetAlreadyApprovedError,
    DatasetAssemblyError,
    DatasetBuildReport,
    DatasetCoverageMatrixRow,
    DatasetExclusionDTO,
    DatasetFingerprintMismatchError,
    DatasetMatchDTO,
    DatasetReleaseDTO,
    DatasetReleaseStatusEnum,
    DatasetSeasonDTO,
    DatasetSelectionPolicyEnum,
    DatasetValidationError,
    ImmutableDatasetError,
    InsufficientCoverageError,
    SourceIntegrityError,
)
from app.dataset.builder import HistoricalDatasetBuilder
from app.dataset.fingerprint import DatasetFingerprintCalculator
from app.dataset.policy import DatasetSelectionPolicyEngine
from app.dataset.query import HistoricalDatasetQueryService
from app.dataset.validator import HistoricalDatasetValidator

__all__ = [
    "DatasetReleaseStatusEnum",
    "DatasetSelectionPolicyEnum",
    "DatasetReleaseDTO",
    "DatasetSeasonDTO",
    "DatasetMatchDTO",
    "DatasetExclusionDTO",
    "DatasetBuildReport",
    "DatasetCoverageMatrixRow",
    "DatasetAssemblyError",
    "InsufficientCoverageError",
    "BlockedSeasonError",
    "SourceIntegrityError",
    "DatasetValidationError",
    "DatasetFingerprintMismatchError",
    "DatasetAlreadyApprovedError",
    "ImmutableDatasetError",
    "DatasetSelectionPolicyEngine",
    "DatasetFingerprintCalculator",
    "HistoricalDatasetBuilder",
    "HistoricalDatasetValidator",
    "HistoricalDatasetApprover",
    "HistoricalDatasetQueryService",
]
