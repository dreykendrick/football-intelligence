"""
Deterministic Feature Set and Feature Snapshot Fingerprint Calculators
Provides immutable SHA-256 fingerprinting routines for feature sets and pre-match feature snapshots.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID


class FeatureSetFingerprintCalculator:
    """Calculates deterministic SHA-256 fingerprint for a versioned FeatureSet definition."""

    @staticmethod
    def compute_fingerprint(
        name: str,
        version: str,
        feature_keys: list[str],
        dataset_key: str = "mvp_a_historical",
        dataset_version: str = "v1",
    ) -> str:
        payload = {
            "name": name,
            "version": version,
            "dataset_key": dataset_key,
            "dataset_version": dataset_version,
            "feature_keys": sorted(feature_keys),
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class FeatureSnapshotFingerprintCalculator:
    """Calculates deterministic SHA-256 fingerprint for pre-match feature snapshot payloads."""

    @staticmethod
    def compute_fingerprint(
        feature_set_version: str,
        cutoff_timestamp: datetime,
        feature_values: dict[str, Any],
        match_id: UUID | str | None = None,
        dataset_release_id: UUID | str | None = None,
    ) -> str:
        # Exclude volatile timestamps (like created_at) to guarantee determinism
        payload = {
            "dataset_release_id": str(dataset_release_id) if dataset_release_id else "",
            "feature_set_version": feature_set_version,
            "match_id": str(match_id) if match_id else "",
            "cutoff": cutoff_timestamp.isoformat(),
            "features": {k: feature_values[k] for k in sorted(feature_values.keys())},
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

class FeatureImplementationFingerprintCalculator:
    """Calculates deterministic SHA-256 fingerprint for the backend implementation used to generate features."""

    _cached_fingerprint = None
    _cached_feature_keys = None

    @classmethod
    def compute_fingerprint(
        cls,
        feature_keys: list[str],
        engine_version: str = "4.5.1",
        query_layer_version: str = "1.1.0", 
    ) -> str:
        # Check cache (assuming feature_keys don't change within the same process often)
        sorted_keys = tuple(sorted(feature_keys))
        if cls._cached_fingerprint is not None and cls._cached_feature_keys == sorted_keys:
            return cls._cached_fingerprint

        import json, hashlib, inspect
        from app.features.registry import FEATURE_CATALOG
        from app.features.service import FeatureEngineService
        from app.features.assembler import FeatureSetAssembler
        from app.features.query import HistoricalQueryLayer, PointInTimeQueryService
        
        # We also want to include core engines
        from app.features.calculators.elo import EloRatingEngine
        
        core_classes = [
            FeatureEngineService,
            FeatureSetAssembler,
            HistoricalQueryLayer,
            PointInTimeQueryService,
            EloRatingEngine
        ]
        
        payload = {
            "engine_version": engine_version,
            "query_layer_version": query_layer_version,
            "core_sources": {},
            "calculators": {},
        }
        
        for c in core_classes:
            try:
                src = inspect.getsource(c)
                payload["core_sources"][c.__name__] = hashlib.sha256(src.encode("utf-8")).hexdigest()
            except Exception:
                payload["core_sources"][c.__name__] = "source_unavailable"
        
        for k in sorted_keys:
            if k in FEATURE_CATALOG:
                calc = FEATURE_CATALOG[k]
                try:
                    src = inspect.getsource(calc.__class__)
                    src_hash = hashlib.sha256(src.encode("utf-8")).hexdigest()
                except Exception:
                    src_hash = "source_unavailable"
                
                payload["calculators"][k] = {
                    "class": calc.__class__.__name__,
                    "version": calc.version,
                    "source_hash": src_hash
                }
            else:
                payload["calculators"][k] = "unknown"
                
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        fp = hashlib.sha256(encoded).hexdigest()
        
        cls._cached_fingerprint = fp
        cls._cached_feature_keys = sorted_keys
        
        return fp
