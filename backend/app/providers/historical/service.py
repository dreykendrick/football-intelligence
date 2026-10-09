"""
Historical Source Acquisition Service
Handles safe HTTP file downloads, atomic storage, SHA-256 checksums, source change detection, and DB catalog logging.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import IngestionBatch, Provider
from app.providers.historical.base import (
    AcquisitionResult,
    SourceSpecification,
    SourceStatusEnum,
)
from app.providers.historical.football_data_uk import FootballDataUKProvider


class HistoricalSourceAcquisitionService:
    """Acquisition & Verification Service for Historical CSV Datasets."""

    def __init__(self, raw_base_dir: str | None = None) -> None:
        if raw_base_dir:
            self.raw_base_dir = Path(raw_base_dir).resolve()
        else:
            root_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.raw_base_dir = (root_dir / "data" / "raw").resolve()

        self.provider = FootballDataUKProvider()

    def get_destination_path(self, spec: SourceSpecification) -> Path:
        """Constructs safe, sanitized destination path: data/raw/football_data_uk/{comp}/{season}/{code}.csv"""
        clean_provider = os.path.basename(spec.provider_key)
        clean_comp = os.path.basename(spec.competition_code)
        clean_season = os.path.basename(spec.season_year)
        clean_code = os.path.basename(spec.provider_competition_code)

        dest_dir = self.raw_base_dir / clean_provider / clean_comp / clean_season
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file = (dest_dir / f"{clean_code}.csv").resolve()

        if not str(dest_file).startswith(str(self.raw_base_dir)):
            raise ValueError(f"Path traversal detected for specification: {spec}")

        return dest_file

    def calculate_sha256(self, file_path: str | Path) -> str:
        """Calculates SHA-256 checksum of a local file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def acquire_source(
        self,
        spec: SourceSpecification,
        db_session: Session | None = None,
        force_download: bool = False,
        dry_run: bool = False,
    ) -> AcquisitionResult:
        dest_path = self.get_destination_path(spec)

        if dry_run:
            return AcquisitionResult(
                specification=spec,
                status=SourceStatusEnum.AVAILABLE,
                local_path=str(dest_path),
                message="[DRY-RUN] Source acquisition simulation succeeded.",
            )

        # 1. Check existing local file if not forcing download
        if dest_path.exists() and not force_download:
            val_res = self.provider.validate_source_file(str(dest_path))
            if val_res.is_valid:
                sha256_val = self.calculate_sha256(dest_path)
                return AcquisitionResult(
                    specification=spec,
                    status=SourceStatusEnum.VALIDATED,
                    local_path=str(dest_path),
                    sha256_checksum=sha256_val,
                    file_size_bytes=val_res.file_size_bytes,
                    message="Existing raw historical file is valid and verified.",
                    metadata_payload={"schema_fingerprint": val_res.schema_fingerprint},
                )

        # 2. Safe Atomic Download
        fd, temp_path_str = tempfile.mkstemp(suffix=".tmp")
        os.close(fd)
        temp_path = Path(temp_path_str)

        try:
            req = urllib.request.Request(
                spec.source_url,
                headers={"User-Agent": "FootballIntelligenceSystem/0.1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response, open(temp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            return AcquisitionResult(
                specification=spec,
                status=SourceStatusEnum.FAILED,
                local_path=str(dest_path),
                message=f"HTTP download failed: {e}",
            )

        # 3. Validate Downloaded Temp File
        val_res = self.provider.validate_source_file(str(temp_path))
        if not val_res.is_valid:
            if temp_path.exists():
                temp_path.unlink()
            return AcquisitionResult(
                specification=spec,
                status=SourceStatusEnum.FAILED,
                local_path=str(dest_path),
                message=f"Source validation failed: {val_res.error_message}",
            )

        new_sha256 = self.calculate_sha256(temp_path)

        # 4. Check for Source Changes if File Already Exists
        if dest_path.exists():
            existing_sha256 = self.calculate_sha256(dest_path)
            if existing_sha256 == new_sha256:
                temp_path.unlink()
                return AcquisitionResult(
                    specification=spec,
                    status=SourceStatusEnum.UNCHANGED,
                    local_path=str(dest_path),
                    sha256_checksum=existing_sha256,
                    file_size_bytes=val_res.file_size_bytes,
                    message="Source file downloaded successfully and matches existing SHA-256 checksum (UNCHANGED).",
                )
            else:
                quarantine_path = dest_path.with_name(f"{dest_path.stem}_changed_{new_sha256[:8]}.csv")
                shutil.move(str(temp_path), str(quarantine_path))
                return AcquisitionResult(
                    specification=spec,
                    status=SourceStatusEnum.CHANGED,
                    local_path=str(dest_path),
                    sha256_checksum=new_sha256,
                    file_size_bytes=val_res.file_size_bytes,
                    message=f"WARNING: Source SHA-256 changed! Original preserved. New version saved to {quarantine_path.name}",
                    metadata_payload={"existing_sha256": existing_sha256, "new_sha256": new_sha256},
                )

        # 5. Atomic Move to Final Location
        shutil.move(str(temp_path), str(dest_path))

        # 6. Database Logging
        if db_session:
            try:
                self._log_acquisition_to_db(db_session, spec, dest_path, new_sha256, val_res.file_size_bytes)
            except Exception:
                db_session.rollback()

        return AcquisitionResult(
            specification=spec,
            status=SourceStatusEnum.ACQUIRED,
            local_path=str(dest_path),
            sha256_checksum=new_sha256,
            file_size_bytes=val_res.file_size_bytes,
            message="Source file successfully acquired, validated, and cataloged.",
            metadata_payload={"schema_fingerprint": val_res.schema_fingerprint},
        )

    def _log_acquisition_to_db(
        self, db: Session, spec: SourceSpecification, dest_path: Path, sha256_val: str, file_size: int
    ) -> None:
        db_provider = db.query(Provider).filter_by(provider_key=spec.provider_key).first()
        if not db_provider:
            db_provider = Provider(
                provider_key=spec.provider_key,
                display_name=self.provider.display_name,
                provider_type="HISTORICAL_CSV",
                base_url=self.provider.base_url,
            )
            db.add(db_provider)
            db.flush()

        batch = IngestionBatch(
            provider_id=db_provider.id,
            source_type="HISTORICAL_CSV_SOURCE",
            source_reference=str(dest_path),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="SUCCESS",
            checksum=sha256_val,
            metadata_payload={
                "competition_code": spec.competition_code,
                "season_year": spec.season_year,
                "source_url": spec.source_url,
                "file_size_bytes": file_size,
            },
        )
        db.add(batch)
        db.commit()
