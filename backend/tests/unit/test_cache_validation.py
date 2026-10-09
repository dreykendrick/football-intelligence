import pytest
from uuid import uuid4
from datetime import datetime, UTC
from sqlalchemy.orm import Session
import inspect
import copy

from app.db.models import Match, Competition, Season, Team, FeatureSnapshot, HistoricalDatasetRelease
from app.dataset.base import DatasetReleaseStatusEnum
from app.features.service import FeatureEngineService
from app.features.fingerprint import FeatureImplementationFingerprintCalculator
from app.features.registry import FEATURE_CATALOG

@pytest.fixture
def test_match(db_session: Session) -> Match:
    comp = Competition(code="CACHE_TEST", name="Cache Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Cache Team A")
    t2 = Team(canonical_name="Cache Team B")
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime(2023, 10, 1, 12, 0, tzinfo=UTC), status="SCHEDULED")
    
    rel = HistoricalDatasetRelease(key="cache_test_hist", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)
    
    db_session.add_all([comp, season, t1, t2, m1, rel])
    db_session.flush()
    return m1

@pytest.fixture
def clean_fp_cache():
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None

@pytest.mark.unit
def test_implementation_fingerprint_deterministic(clean_fp_cache):
    keys = list(FEATURE_CATALOG.keys())
    fp1 = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    fp2 = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    assert fp1 == fp2

@pytest.mark.unit
def test_implementation_fingerprint_order_independent(clean_fp_cache):
    keys1 = list(FEATURE_CATALOG.keys())
    keys2 = list(reversed(keys1))
    
    fp1 = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys1)
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    
    fp2 = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys2)
    assert fp1 == fp2

@pytest.mark.unit
def test_unrelated_source_change_does_not_change_feature_fingerprint(clean_fp_cache, monkeypatch):
    keys = list(FEATURE_CATALOG.keys())
    fp_base = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    
    fp_new = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    assert fp_base == fp_new

@pytest.mark.unit
def test_source_change_changes_implementation_fingerprint(clean_fp_cache, monkeypatch):
    keys = list(FEATURE_CATALOG.keys())
    fp_base = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    
    original_getsource = inspect.getsource
    def mock_getsource(obj):
        src = original_getsource(obj)
        if hasattr(obj, '__name__') and obj.__name__ == 'EloRatingEngine':
            return src + "\n# Some new implementation logic affecting features\n"
        return src
    
    monkeypatch.setattr(inspect, 'getsource', mock_getsource)
    
    fp_new = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    assert fp_base != fp_new

@pytest.mark.unit
def test_manual_version_unchanged_does_not_hide_source_change(clean_fp_cache, monkeypatch):
    keys = list(FEATURE_CATALOG.keys())
    fp_base = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    
    original_getsource = inspect.getsource
    def mock_getsource(obj):
        src = original_getsource(obj)
        if hasattr(obj, '__name__') and obj.__name__ == 'BaseFormCalculator':
            return src + "\n# Modified\n"
        return src
        
    monkeypatch.setattr(inspect, 'getsource', mock_getsource)
    
    fp_new = FeatureImplementationFingerprintCalculator.compute_fingerprint(keys)
    assert fp_base != fp_new

@pytest.mark.unit
def test_snapshot_invalidated_by_automatic_source_fingerprint_change(db_session: Session, test_match: Match, clean_fp_cache, monkeypatch):
    from app.quality.gate import QualityGate
    monkeypatch.setattr(QualityGate, 'assert_historical_data_ready', lambda db: None)
    svc = FeatureEngineService(db_session)
    
    snap1 = svc.generate_snapshot_for_match(test_match.id, dataset_key="cache_test_hist", dataset_version="v1")
    assert not hasattr(snap1, "_is_cached")
    snap1_id = snap1.id
    db_session.commit()
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    original_getsource = inspect.getsource
    def mock_getsource(obj):
        src = original_getsource(obj)
        if hasattr(obj, '__name__') and obj.__name__ == 'EloRatingEngine':
            return src + "\n# Some new implementation logic affecting features\n"
        return src
    monkeypatch.setattr(inspect, 'getsource', mock_getsource)
    
    snap2 = svc.generate_snapshot_for_match(test_match.id, dataset_key="cache_test_hist", dataset_version="v1")
    assert not getattr(snap2, "_is_cached", False)
    assert snap2.id != snap1_id
    assert snap2.data_quality_metadata["implementation_fingerprint"] != snap1.data_quality_metadata["implementation_fingerprint"]

@pytest.mark.unit
def test_unchanged_implementation_reuses_snapshot(db_session: Session, test_match: Match, clean_fp_cache, monkeypatch):
    from app.quality.gate import QualityGate
    monkeypatch.setattr(QualityGate, 'assert_historical_data_ready', lambda db: None)
    svc = FeatureEngineService(db_session)
    
    snap1 = svc.generate_snapshot_for_match(test_match.id, dataset_key="cache_test_hist", dataset_version="v1")
    db_session.commit()
    
    FeatureImplementationFingerprintCalculator._cached_fingerprint = None
    FeatureImplementationFingerprintCalculator._cached_feature_keys = None
    
    snap2 = svc.generate_snapshot_for_match(test_match.id, dataset_key="cache_test_hist", dataset_version="v1")
    assert getattr(snap2, "_is_cached", False) is True
    assert snap1.id == snap2.id
