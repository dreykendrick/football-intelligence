"""
Feature Engine Orchestrator Service
Generates, validates via Quality Gate, fingerprints, and persists reproducible FeatureSnapshot records.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum, DatasetValidationError
from app.dataset.query import HistoricalDatasetQueryService
from app.db.models import FeatureSnapshot, HistoricalDatasetRelease, Match
from app.features.base import FeatureCalculationResult, MissingnessReason
from app.features.fingerprint import FeatureSnapshotFingerprintCalculator
from app.features.query import PointInTimeQueryService
from app.features.registry import FEATURE_CATALOG, global_feature_registry
from app.features.sets import FeatureSetManager
from app.quality.gate import QualityGate


class FeatureEngineService:
    """Feature Snapshot Generation Engine enforcing approved dataset dependencies and point-in-time calculation."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session
        self.dataset_query_service = HistoricalDatasetQueryService(db_session)

    def generate_snapshot_for_match(
        self,
        match_id: UUID,
        cutoff_timestamp: datetime | None = None,
        snapshot_type: str = "FINAL",
        skip_quality_gate: bool = False,
        dataset_key: str = "mvp_a_historical",
        dataset_version: str = "v1",
        approved_only: bool = True,
        enforce_date_only_precision: bool = True,
    ) -> FeatureSnapshot:
        # 1. Quality Gate Assertion
        if not skip_quality_gate:
            QualityGate.assert_historical_data_ready(self.db)

        # 2. Verify Dataset Release
        release = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=dataset_version)
            .first()
        )

        total_releases = self.db.query(HistoricalDatasetRelease).count()
        if release:
            if approved_only and release.status != DatasetReleaseStatusEnum.APPROVED.value:
                raise DatasetValidationError(
                    f"Dataset release '{dataset_key}:{dataset_version}' is in status '{release.status}'. "
                    "Official point-in-time feature calculations require APPROVED datasets."
                )
            rel_id = release.id
            rel_key = release.key
            rel_version = release.version
            rel_fp = release.dataset_fingerprint
        else:
            if total_releases > 0 and approved_only:
                raise DatasetValidationError(
                    f"Historical dataset release '{dataset_key}:{dataset_version}' does not exist."
                )
            rel_id = None
            rel_key = dataset_key
            rel_version = dataset_version
            rel_fp = "UNTRACKED_TEST_RELEASE"

        # 3. Fetch Target Match
        match = self.db.query(Match).filter_by(id=match_id).first()
        if not match:
            raise ValueError(f"Match not found: {match_id}")

        # Default cutoff to match kickoff timestamp if unspecified
        if cutoff_timestamp is None:
            cutoff_timestamp = match.kickoff_utc

        if cutoff_timestamp.tzinfo is None:
            cutoff_timestamp = cutoff_timestamp.replace(tzinfo=UTC)

        # 4. Fetch or Create Feature Set
        fset = FeatureSetManager.get_or_create_mvp_a_feature_set(self.db)

        import time
        t_exist_0 = time.time()
        # Check existing snapshot
        existing = (
            self.db.query(FeatureSnapshot)
            .filter_by(match_id=match.id, feature_set_id=fset.id, snapshot_type=snapshot_type)
            .first()
        )
        t_exist_1 = time.time()
        if existing:
            from app.features.fingerprint import FeatureImplementationFingerprintCalculator
            expected_impl_fp = FeatureImplementationFingerprintCalculator.compute_fingerprint(list(FEATURE_CATALOG.keys()))
            
            actual_impl_fp = existing.data_quality_metadata.get("implementation_fingerprint") if existing.data_quality_metadata else None
            
            # Semantic fingerprint is already the hash of values, so if implementation matches, we assume semantic is valid.
            # But we can also check feature_set_version matches.
            
            if actual_impl_fp != expected_impl_fp:
                # implementation changed, mark as stale and regenerate
                existing._stale_reason = "STALE_IMPLEMENTATION"
                self.db.delete(existing)
                self.db.flush()
            else:
                existing._is_cached = True
                return existing

        # 5. Point-in-Time Query Helper
        pit_query = PointInTimeQueryService(
            db_session=self.db,
            dataset_key=dataset_key,
            version=dataset_version,
            approved_only=approved_only,
            enforce_date_only_precision=enforce_date_only_precision,
        )

        # 6. Calculate Feature Values
        feature_values: dict[str, Any] = {}
        missing_features: dict[str, Any] = {}
        quality_metadata: dict[str, Any] = {
            "match_kickoff": match.kickoff_utc.isoformat(),
            "cutoff_timestamp": cutoff_timestamp.isoformat(),
            "feature_set_name": fset.name,
            "feature_set_version": fset.version,
            "dataset_release_id": str(rel_id) if rel_id else None,
            "dataset_key": rel_key,
            "dataset_version": rel_version,
            "dataset_fingerprint": rel_fp,
        }

        for fkey, calculator in FEATURE_CATALOG.items():
            try:
                res: FeatureCalculationResult = calculator.calculate(self.db, match, cutoff_timestamp)
                if res.is_missing or res.value is None:
                    reason = res.missing_reason.value if hasattr(res.missing_reason, "value") else str(res.missing_reason)
                    missing_features[fkey] = reason
                    feature_values[fkey] = None
                else:
                    feature_values[fkey] = res.value
            except Exception as e:
                missing_features[fkey] = MissingnessReason.SOURCE_FIELD_UNAVAILABLE.value
                feature_values[fkey] = None
                quality_metadata[f"error_{fkey}"] = str(e)

        # 7. Compute Deterministic Fingerprint
        fingerprint = FeatureSnapshotFingerprintCalculator.compute_fingerprint(
            feature_set_version=fset.version,
            cutoff_timestamp=cutoff_timestamp,
            feature_values=feature_values,
            match_id=match.id,
            dataset_release_id=rel_id,
        )
        quality_metadata["fingerprint_sha256"] = fingerprint
        
        from app.features.fingerprint import FeatureImplementationFingerprintCalculator
        impl_fp = FeatureImplementationFingerprintCalculator.compute_fingerprint(list(FEATURE_CATALOG.keys()))
        quality_metadata["implementation_fingerprint"] = impl_fp

        # 8. Persist Immutable FeatureSnapshot
        snapshot = FeatureSnapshot(
            match_id=match.id,
            feature_set_id=fset.id,
            snapshot_type=snapshot_type,
            feature_version=fset.version,
            cutoff_timestamp=cutoff_timestamp,
            feature_values=feature_values,
            missing_features=missing_features,
            data_quality_metadata=quality_metadata,
        )
        self.db.add(snapshot)
        self.db.flush()

        return snapshot

    def build_snapshots_for_dataset(
        self,
        dataset_key: str = "mvp_a_historical",
        version: str = "v1",
        approved_only: bool = True,
        batch_size: int = 50,
        limit: int | None = None
    ) -> list[FeatureSnapshot]:
        import time
        from sqlalchemy.exc import OperationalError
        
        print(f"Loading match list for dataset {dataset_key}:{version}...")
        t0 = time.time()
        matches = self.dataset_query_service.get_dataset_matches(
            dataset_key=dataset_key, version=version, approved_only=approved_only
        )
        t1 = time.time()
        print(f"Loaded {len(matches)} matches in {t1 - t0:.2f} seconds.")
        if limit is not None:
            matches = matches[:limit]
            
        from app.quality.gate import QualityGate
        print("Running Quality Gate assertion once for the build...")
        QualityGate.assert_historical_data_ready(self.db)
        print("Quality Gate Passed.")

        total = len(matches)
        print(f"Targeting {total} matches to evaluate...")

        snapshots: list[FeatureSnapshot] = []
        skipped = 0
        built = 0
        failed = 0
        
        batch_chunk = []
        
        for idx, m in enumerate(matches, 1):
            batch_chunk.append(m)
            
            if len(batch_chunk) >= batch_size or idx == total:
                # Process batch
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        batch_snaps = []
                        for bm in batch_chunk:
                            try:
                                snap = self.generate_snapshot_for_match(
                                    match_id=bm.id,
                                    cutoff_timestamp=bm.kickoff_utc,
                                    dataset_key=dataset_key,
                                    dataset_version=version,
                                    approved_only=approved_only,
                                    skip_quality_gate=True,
                                )
                                batch_snaps.append(snap)
                                if getattr(snap, "_is_cached", False):
                                    skipped += 1
                                else:
                                    built += 1
                            except Exception as e:
                                print(f"Error generating snapshot for match {bm.id}: {e}")
                                failed += 1
                        
                        # Commit the batch
                        self.db.commit()
                        snapshots.extend(batch_snaps)
                        print(f"Processed {idx}/{total} matches (Batch committed)")
                        break # Success
                    except OperationalError as e:
                        self.db.rollback()
                        if "database is locked" in str(e) or "database is busy" in str(e):
                            if attempt < max_retries - 1:
                                sleep_time = (attempt + 1) * 2
                                print(f"Database locked. Retrying in {sleep_time}s... (Attempt {attempt+1}/{max_retries})")
                                time.sleep(sleep_time)
                            else:
                                print("Max retries exceeded for database lock.")
                                raise e
                        else:
                            raise e
                    except Exception as e:
                        self.db.rollback()
                        raise e
                        
                batch_chunk = []

        print(f"Build complete. Built: {built}, Skipped: {skipped}, Failed: {failed}")
        return snapshots

    @staticmethod
    def compute_snapshot_fingerprint(
        feature_version: str, cutoff_timestamp: datetime, feature_values: dict[str, Any]
    ) -> str:
        """Backward-compatible helper delegating to FeatureSnapshotFingerprintCalculator."""
        return FeatureSnapshotFingerprintCalculator.compute_fingerprint(
            feature_set_version=feature_version,
            cutoff_timestamp=cutoff_timestamp,
            feature_values=feature_values,
        )
