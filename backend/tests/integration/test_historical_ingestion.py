"""
Integration & Idempotency Tests for Historical Data Ingestion Pipeline
Verifies CSV -> PostgreSQL persistence, idempotency on re-import, dry-run mode, and provenance audit chains.
"""
import os

import pytest
from sqlalchemy.orm import Session

from app.db.models import IngestionBatch, Match, ProviderMatchMapping, RawSourceRecord
from app.ingestion.base import IngestionStatusEnum
from app.ingestion.pipeline import HistoricalIngestionPipeline


@pytest.fixture
def fixtures_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "csv"))


@pytest.mark.integration
def test_end_to_end_file_ingestion(db_session: Session, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "valid_epl_sample.csv")
    pipeline = HistoricalIngestionPipeline(db_session)

    report = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24")

    assert report.status == IngestionStatusEnum.COMPLETED
    assert report.inserted_matches == 5
    assert report.existing_matches == 0
    assert report.failed_rows == 0

    # Verify Database Tables
    match_count = db_session.query(Match).count()
    assert match_count == 5

    batch = db_session.query(IngestionBatch).filter_by(checksum=report.checksum).first()
    assert batch is not None
    assert batch.status == "COMPLETED"
    assert batch.success_count == 5

    raw_records_count = db_session.query(RawSourceRecord).filter_by(ingestion_batch_id=batch.id).count()
    assert raw_records_count == 5


@pytest.mark.integration
def test_idempotent_reimport(db_session: Session, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "valid_epl_sample.csv")
    pipeline = HistoricalIngestionPipeline(db_session)

    # First Import
    report1 = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24")
    assert report1.inserted_matches == 5

    # Second Import (Identical File)
    report2 = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24")

    assert report2.status == IngestionStatusEnum.COMPLETED
    assert report2.inserted_matches == 0
    assert report2.existing_matches == 5
    assert report2.failed_rows == 0

    # Total Match count in DB must remain 5
    match_count = db_session.query(Match).count()
    assert match_count == 5


@pytest.mark.integration
def test_dry_run_mode(db_session: Session, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "valid_epl_sample.csv")
    pipeline = HistoricalIngestionPipeline(db_session)

    report = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24", dry_run=True)

    assert report.is_dry_run is True
    assert report.inserted_matches == 5

    # Database must remain empty
    match_count = db_session.query(Match).count()
    assert match_count == 0


@pytest.mark.integration
def test_provenance_audit_chain(db_session: Session, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "valid_epl_sample.csv")
    pipeline = HistoricalIngestionPipeline(db_session)

    report = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24")

    # Fetch a canonical match
    match = db_session.query(Match).first()
    assert match is not None

    # Trace: Match -> ProviderMatchMapping -> IngestionBatch -> RawSourceRecord
    mapping = db_session.query(ProviderMatchMapping).filter_by(match_id=match.id).first()
    assert mapping is not None
    assert mapping.provider.provider_key == "football_data_co_uk"

    batch = db_session.query(IngestionBatch).filter_by(checksum=report.checksum).first()
    assert batch is not None

    raw_record = db_session.query(RawSourceRecord).filter_by(ingestion_batch_id=batch.id).first()
    assert raw_record is not None
    assert "HomeTeam" in raw_record.raw_payload


@pytest.mark.integration
def test_partial_failure_handling(db_session: Session, fixtures_dir):
    csv_path = os.path.join(fixtures_dir, "result_score_mismatch.csv")
    pipeline = HistoricalIngestionPipeline(db_session)

    report = pipeline.ingest_file(csv_path, competition_override="EPL", season_override="2023/24")

    assert report.status == IngestionStatusEnum.PARTIAL
    assert report.inserted_matches == 1
    assert report.failed_rows == 1

    # Verify 1 match saved in DB
    match_count = db_session.query(Match).count()
    assert match_count == 1
