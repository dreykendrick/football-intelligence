"""
Feature Set Assembler Engine
Calculates, validates, orders, and packages pre-match feature vectors according to frozen manifest specifications.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Match
from app.features.base import FeatureCalculationResult, MissingnessReason
from app.features.fingerprint import FeatureSnapshotFingerprintCalculator
from app.features.manifest import FeatureSetManifest, get_mvp_a_feature_set_v1_manifest
from app.features.registry import global_feature_registry


class FeatureSetVectorDTO(BaseModel):
    """Structured pre-match feature vector DTO produced for predictive modeling consumption."""

    feature_set_key: str
    feature_set_version: str
    target_match_id: UUID
    cutoff_timestamp: datetime
    ordered_feature_values: list[FeatureCalculationResult]
    feature_vector_dict: dict[str, Any]
    snapshot_fingerprint: str
    missing_feature_count: int
    total_feature_count: int

    @property
    def coverage_percentage(self) -> float:
        if self.total_feature_count == 0:
            return 0.0
        available = self.total_feature_count - self.missing_feature_count
        return round((available / self.total_feature_count) * 100.0, 2)


class FeatureSetAssembler:
    """Assembles, validates, and packages pre-match feature vectors according to manifest rules."""

    def __init__(self, manifest: FeatureSetManifest | None = None) -> None:
        self.manifest = manifest or get_mvp_a_feature_set_v1_manifest()

    def assemble_feature_vector_for_match(
        self,
        db: Session,
        match_id: UUID,
        cutoff_timestamp: datetime | None = None,
        dataset_key: str = "mvp_a_historical",
        dataset_version: str = "v1",
    ) -> FeatureSetVectorDTO:
        """
        Calculates all included features for a target match in exact manifest order,
        enforcing anti-leakage cutoffs, numerical finiteness, and schema validation.
        """
        match = db.query(Match).filter_by(id=match_id).first()
        if not match:
            raise ValueError(f"Target match ID '{match_id}' not found in database.")

        if cutoff_timestamp is None:
            cutoff_timestamp = match.kickoff_utc

        if cutoff_timestamp.tzinfo is None:
            cutoff_timestamp = cutoff_timestamp.replace(tzinfo=UTC)

        ordered_results: list[FeatureCalculationResult] = []
        vector_dict: dict[str, Any] = {}
        missing_count = 0

        # Process each feature strictly in manifest order
        for fkey in self.manifest.included_feature_keys:
            calc = global_feature_registry.get_calculator(fkey)
            res = calc.calculate(db, match, cutoff_timestamp=cutoff_timestamp)

            # 1. Finite numeric validation
            if res.value is not None and isinstance(res.value, (int, float)):
                if math.isnan(res.value) or math.isinf(res.value):
                    raise ValueError(
                        f"Non-finite numeric value ({res.value}) generated for feature '{fkey}' on match '{match_id}'."
                    )

            # 2. Missingness consistency checks
            if res.is_missing and res.value is not None:
                # If marked missing with a fallback value, ensure explicit missing reason is set
                if res.missing_reason == MissingnessReason.AVAILABLE:
                    res.missing_reason = MissingnessReason.INSUFFICIENT_HISTORY

            if not res.is_missing and res.value is None:
                raise ValueError(
                    f"Feature '{fkey}' marked AVAILABLE (is_missing=False) but contains None value."
                )

            if res.is_missing:
                missing_count += 1

            ordered_results.append(res)
            vector_dict[fkey] = res.value

        feature_values_json = {res.feature_key: res.value for res in ordered_results}
        from app.dataset.query import HistoricalDatasetQueryService
        query_service = HistoricalDatasetQueryService(db)
        
        try:
            rel = query_service.get_dataset_release(dataset_key, dataset_version)
            rel_id = rel.id if rel else UUID("00000000-0000-0000-0000-000000000000")
        except Exception:
            rel_id = UUID("00000000-0000-0000-0000-000000000000")

        fingerprint = FeatureSnapshotFingerprintCalculator.compute_fingerprint(
            match_id=match_id,
            cutoff_timestamp=cutoff_timestamp,
            feature_set_version=f"{self.manifest.feature_set_key}:{self.manifest.version}",
            dataset_release_id=rel_id,
            feature_values=feature_values_json,
        )

        return FeatureSetVectorDTO(
            feature_set_key=self.manifest.feature_set_key,
            feature_set_version=self.manifest.version,
            target_match_id=match_id,
            cutoff_timestamp=cutoff_timestamp,
            ordered_feature_values=ordered_results,
            feature_vector_dict=vector_dict,
            snapshot_fingerprint=fingerprint,
            missing_feature_count=missing_count,
            total_feature_count=len(ordered_results),
        )
