"""
Historical Data Ingestion Pipeline Orchestrator
Executes provider file parsing, raw audit logging, domain normalization, and transaction management.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import IngestionBatch, RawSourceRecord
from app.ingestion.base import (
    HistoricalFootballProvider,
    HistoricalProviderBatchResultDTO,
    IngestionStatusEnum,
)
from app.ingestion.historical.football_data_uk import FootballDataUKProvider
from app.ingestion.normalizer import DataNormalizer


class IngestionSummaryReport:
    """Detailed Human-Readable Ingestion Execution Report."""

    def __init__(
        self,
        provider_key: str,
        source_reference: str,
        checksum: str,
        total_rows: int,
        inserted_matches: int,
        existing_matches: int,
        failed_rows: int,
        status: IngestionStatusEnum,
        is_dry_run: bool = False,
        warnings: list[str] | None = None,
    ) -> None:
        self.provider_key = provider_key
        self.source_reference = source_reference
        self.checksum = checksum
        self.total_rows = total_rows
        self.inserted_matches = inserted_matches
        self.existing_matches = existing_matches
        self.failed_rows = failed_rows
        self.status = status
        self.is_dry_run = is_dry_run
        self.warnings = warnings or []

    def to_formatted_string(self) -> str:
        mode_str = " (DRY-RUN MODE)" if self.is_dry_run else ""
        lines = [
            "==========================================================",
            f"   HISTORICAL DATA INGESTION REPORT{mode_str}",
            "==========================================================",
            f"Provider Source    : {self.provider_key}",
            f"Source File        : {self.source_reference}",
            f"SHA-256 Checksum   : {self.checksum[:16]}...",
            f"Total Rows Read    : {self.total_rows}",
            f"Canonical Inserted : {self.inserted_matches}",
            f"Existing / Skipped : {self.existing_matches}",
            f"Failed Rows        : {self.failed_rows}",
            f"Final Batch Status : {self.status.value}",
        ]
        if self.warnings:
            lines.append("----------------------------------------------------------")
            lines.append("Warnings / Validation Errors:")
            for w in self.warnings[:10]:
                lines.append(f"  - {w}")
            if len(self.warnings) > 10:
                lines.append(f"  ... and {len(self.warnings) - 10} more warnings.")
        lines.append("==========================================================")
        return "\n".join(lines)


class HistoricalIngestionPipeline:
    """Historical CSV Data Ingestion Pipeline Orchestrator."""

    def __init__(
        self, db_session: Session, provider: HistoricalFootballProvider | None = None
    ) -> None:
        self.db = db_session
        self.provider = provider or FootballDataUKProvider()
        self.normalizer = DataNormalizer(db_session)

    def ingest_file(
        self,
        file_path: str,
        competition_override: str | None = None,
        season_override: str | None = None,
        dry_run: bool = False,
    ) -> IngestionSummaryReport:
        # 1. Parse File & Validate Headers/Rows using Provider Adapter
        parse_result: HistoricalProviderBatchResultDTO = self.provider.parse_file(
            file_path, competition_override=competition_override, season_override=season_override
        )

        if dry_run:
            # Perform Dry-Run Validation without database mutations
            status = IngestionStatusEnum.COMPLETED if not parse_result.invalid_rows else IngestionStatusEnum.PARTIAL
            return IngestionSummaryReport(
                provider_key=parse_result.provider_key,
                source_reference=parse_result.source_reference,
                checksum=parse_result.checksum,
                total_rows=parse_result.total_rows,
                inserted_matches=len(parse_result.valid_rows),
                existing_matches=0,
                failed_rows=len(parse_result.invalid_rows),
                status=status,
                is_dry_run=True,
                warnings=parse_result.validation_warnings,
            )

        # 2. Get or Create Provider Record
        provider = self.normalizer.get_or_create_provider(
            provider_key=parse_result.provider_key,
            display_name="Football-Data.co.uk Historical Source",
            provider_type="HISTORICAL_CSV",
        )

        # 3. Create Ingestion Batch Record
        batch = IngestionBatch(
            provider_id=provider.id,
            source_type="HISTORICAL_CSV",
            source_reference=parse_result.source_reference,
            started_at=datetime.now(UTC),
            status=IngestionStatusEnum.RUNNING.value,
            checksum=parse_result.checksum,
            row_count=parse_result.total_rows,
        )
        self.db.add(batch)
        self.db.flush()

        inserted_count = 0
        existing_count = 0
        failed_count = len(parse_result.invalid_rows)

        # 4. Normalize & Persist Each Valid Raw Row
        for dto in parse_result.valid_rows:
            try:
                # Save Raw Source Audit Record (Preserving complete CSV row including bookmaker odds for traceability)
                raw_record = RawSourceRecord(
                    provider_id=provider.id,
                    ingestion_batch_id=batch.id,
                    entity_type="MATCH_ROW",
                    external_reference=f"{parse_result.source_reference}:row_{dto.source_row_index}",
                    raw_payload=dto.raw_payload,
                    checksum=parse_result.checksum,
                    processing_status="PROCESSED",
                    received_at=datetime.now(UTC),
                )
                self.db.add(raw_record)

                # Normalize Raw Row to Canonical Entities
                norm_result = self.normalizer.normalize_match(provider, dto)

                if norm_result.is_created:
                    inserted_count += 1
                else:
                    existing_count += 1
            except Exception as e:
                failed_count += 1
                parse_result.validation_warnings.append(f"Normalization failed at row {dto.source_row_index}: {e}")

        # 5. Finalize Batch Status
        batch.completed_at = datetime.now(UTC)
        batch.success_count = inserted_count + existing_count
        batch.failure_count = failed_count

        if failed_count == 0:
            final_status = IngestionStatusEnum.COMPLETED
        elif inserted_count + existing_count > 0:
            final_status = IngestionStatusEnum.PARTIAL
        else:
            final_status = IngestionStatusEnum.FAILED

        batch.status = final_status.value

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            batch.status = IngestionStatusEnum.FAILED.value
            raise RuntimeError(f"Database transaction failed during historical ingestion: {e}") from e

        return IngestionSummaryReport(
            provider_key=parse_result.provider_key,
            source_reference=parse_result.source_reference,
            checksum=parse_result.checksum,
            total_rows=parse_result.total_rows,
            inserted_matches=inserted_count,
            existing_matches=existing_count,
            failed_rows=failed_count,
            status=final_status,
            is_dry_run=False,
            warnings=parse_result.validation_warnings,
        )
