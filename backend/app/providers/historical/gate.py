"""
Source Coverage Gate & Historical File Verifier
Provides assertion gates verifying raw historical source availability and integrity before ingestion pipelines.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.providers.historical.manifest import HistoricalManifestLoader
from app.providers.historical.service import HistoricalSourceAcquisitionService


class SourceCoverageGateException(RuntimeError):
    """Exception raised when Historical Source Coverage Gate fails."""


class SourceCoverageGate:
    """Historical Source File Verification & Coverage Gate."""

    @classmethod
    def assert_required_historical_sources_available(
        cls,
        db_session: Session | None = None,
        manifest_path: str | None = None,
        raw_base_dir: str | None = None,
    ) -> list[dict]:
        service = HistoricalSourceAcquisitionService(raw_base_dir=raw_base_dir)
        specs = HistoricalManifestLoader.load_manifest(manifest_path=manifest_path)

        missing_sources = []
        invalid_sources = []
        valid_sources = []

        for spec in specs:
            dest_path = service.get_destination_path(spec)
            if not dest_path.exists():
                if spec.is_required:
                    missing_sources.append(f"{spec.competition_code} {spec.season_year} ({dest_path.name})")
                continue

            val_res = service.provider.validate_source_file(str(dest_path))
            if not val_res.is_valid:
                invalid_sources.append(f"{spec.competition_code} {spec.season_year}: {val_res.error_message}")
                continue

            valid_sources.append(
                {
                    "spec": spec,
                    "local_path": str(dest_path),
                    "file_size": val_res.file_size_bytes,
                    "sha256": service.calculate_sha256(dest_path),
                }
            )

        if missing_sources or invalid_sources:
            err_msg = "Historical Source Coverage Gate FAILED!\n"
            if missing_sources:
                err_msg += f"  - Missing Required Datasets ({len(missing_sources)}): {', '.join(missing_sources)}\n"
            if invalid_sources:
                err_msg += f"  - Invalid Datasets ({len(invalid_sources)}): {'; '.join(invalid_sources)}\n"
            raise SourceCoverageGateException(err_msg)

        return valid_sources
