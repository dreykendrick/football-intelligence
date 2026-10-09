"""
Integration Tests for Approved Dataset Release Immutability
"""
import pytest

from app.dataset.approval import HistoricalDatasetApprover
from app.dataset.base import ImmutableDatasetError
from app.dataset.builder import HistoricalDatasetBuilder
from app.db.models import HistoricalDatasetRelease


@pytest.mark.integration
def test_approved_release_cannot_be_rebuilt(db_session):
    release = HistoricalDatasetRelease(
        key="immutable_dataset",
        version="v1",
        status="APPROVED",
        selection_policy_key="p",
        selection_policy_version="1.0.0",
        total_competitions=4,
        total_seasons=12,
        total_matches=12,
        dataset_fingerprint="f" * 64,
        quality_status="READY",
        identity_readiness_status="READY",
    )
    db_session.add(release)
    db_session.commit()

    builder = HistoricalDatasetBuilder(db_session)
    with pytest.raises(RuntimeError) as exc_info:
        builder.build_dataset_release(dataset_key="immutable_dataset", version="v1")

    assert "already APPROVED and immutable" in str(exc_info.value)


@pytest.mark.integration
def test_assert_immutable_raises_on_approved_release(db_session):
    release = HistoricalDatasetRelease(
        key="immutable_dataset_2",
        version="v1",
        status="APPROVED",
        selection_policy_key="p",
        selection_policy_version="1.0.0",
    )
    approver = HistoricalDatasetApprover(db_session)

    with pytest.raises(ImmutableDatasetError):
        approver.assert_immutable(release)
