"""
Historical Dataset Release Validation Engine
Audits candidate releases against all scientific requirements prior to approval.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.dataset.base import (
    DatasetReleaseStatusEnum,
    DatasetValidationReport,
)
from app.dataset.fingerprint import DatasetFingerprintCalculator
from app.dataset.policy import DatasetSelectionPolicyEngine
from app.db.models import (
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    HistoricalDatasetSeason,
)
from app.identity.gate import IdentityReadinessGate
from app.providers.historical.manifest import HistoricalSourceCatalog
from app.quality.base import ReadinessStatusEnum


class HistoricalDatasetValidator:
    """Validator auditing dataset candidate release before official approval."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def validate_release(
        self,
        dataset_key: str = "mvp_a_historical",
        version: str = "v1",
        accepted_warnings: list[str] | None = None,
    ) -> DatasetValidationReport:
        """Audits dataset release candidate for MVP-A approval readiness."""
        accepted_warnings = accepted_warnings or []

        release = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=version)
            .first()
        )

        if not release:
            return DatasetValidationReport(
                dataset_key=dataset_key,
                version=version,
                is_valid=False,
                status=DatasetReleaseStatusEnum.FAILED,
                target_competitions_count=0,
                total_seasons_count=0,
                total_matches_count=0,
                blockers=[f"Dataset release {dataset_key}:{version} does not exist."],
            )

        checks_passed: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        seasons = (
            self.db.query(HistoricalDatasetSeason)
            .filter_by(dataset_release_id=release.id)
            .all()
        )
        matches = (
            self.db.query(HistoricalDatasetMatch)
            .filter_by(dataset_release_id=release.id)
            .all()
        )

        # 1. Target Competition Coverage Check (>= 3 usable seasons per target comp)
        comp_season_counts: dict[str, int] = dict.fromkeys(
            DatasetSelectionPolicyEngine.TARGET_COMPETITIONS, 0
        )
        for s in seasons:
            code = s.competition_code
            comp_season_counts[code] = comp_season_counts.get(code, 0) + 1

        deficient_comps = {
            code: count
            for code, count in comp_season_counts.items()
            if count < DatasetSelectionPolicyEngine.MIN_SEASONS_PER_COMPETITION
        }

        if deficient_comps:
            blockers.append(
                f"Deficient competition season coverage: {deficient_comps}. MVP-A requires >= 3 usable seasons per target competition."
            )
        else:
            checks_passed.append(
                f"Minimum coverage requirement PASSED ({len(comp_season_counts)} competitions × >= 3 seasons)."
            )

        # 2. Season Readiness Checks (No BLOCKED seasons)
        blocked_seasons = [
            f"{s.competition_code} {s.season_year}"
            for s in seasons
            if s.readiness_status == ReadinessStatusEnum.BLOCKED.value
        ]
        if blocked_seasons:
            blockers.append(
                f"Dataset contains BLOCKED seasons: {blocked_seasons}. Blocked seasons are prohibited from approved releases."
            )
        else:
            checks_passed.append("No BLOCKED seasons present in release candidate.")

        # 3. Warning Acceptance Verification
        warning_bearing_seasons = [
            f"{s.competition_code} {s.season_year}"
            for s in seasons
            if s.readiness_status == ReadinessStatusEnum.READY_WITH_WARNINGS.value
        ]
        if warning_bearing_seasons:
            if not accepted_warnings:
                warnings.append(
                    f"Seasons bear quality warnings ({warning_bearing_seasons}). Require explicit warning limitation acceptance."
                )
            else:
                checks_passed.append(
                    f"Warning limitations explicitly accepted for seasons: {warning_bearing_seasons}."
                )

        # 4. Source Catalog Checksum Verification
        catalog = HistoricalSourceCatalog.load_default_manifest()
        source_mismatches = []
        for s in seasons:
            spec = catalog.get_source_spec(s.competition_code, s.season_year)
            if not spec:
                source_mismatches.append(f"Missing catalog manifest entry for {s.competition_code} {s.season_year}")
            elif spec.expected_sha256 and spec.expected_sha256 != s.source_checksum:
                source_mismatches.append(
                    f"Checksum mismatch for {s.competition_code} {s.season_year}: DB={s.source_checksum}, Catalog={spec.expected_sha256}"
                )

        if source_mismatches:
            blockers.append(f"Source integrity verification failed: {source_mismatches}")
        else:
            checks_passed.append("All raw source locked checksums verified against catalog manifest.")

        # 5. Duplicate Match Check
        match_ids = [m.match_id for m in matches]
        if len(match_ids) != len(set(match_ids)):
            blockers.append("Duplicate match membership detected in release!")
        else:
            checks_passed.append("Match uniqueness verified (0 duplicates).")

        # 6. Match Count Consistency
        sum_season_matches = sum(s.match_count for s in seasons)
        if sum_season_matches != len(matches):
            blockers.append(
                f"Match count mismatch: sum of season match counts ({sum_season_matches}) != total dataset match count ({len(matches)})."
            )
        else:
            checks_passed.append(f"Match count consistency verified ({len(matches)} matches).")

        # 7. Identity Readiness Check
        identity_report = IdentityReadinessGate.evaluate_gate(self.db)
        if identity_report.overall_status.value not in [
            ReadinessStatusEnum.READY.value,
            ReadinessStatusEnum.READY_WITH_WARNINGS.value,
        ]:
            blockers.append(f"Identity readiness gate failed with status {identity_report.overall_status.value}.")
        else:
            checks_passed.append(f"Identity readiness verified ({identity_report.overall_status.value}).")

        # 8. Re-compute & Verify Fingerprint Determinism
        seasons_data = [
            {
                "competition_code": s.competition_code,
                "season_year": s.season_year,
                "source_checksum": s.source_checksum or "",
            }
            for s in seasons
        ]
        matches_data = [
            {
                "match_id": m.match_id,
                "kickoff_utc": m.kickoff_utc,
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_score": m.match.home_score if m.match else None,
                "away_score": m.match.away_score if m.match else None,
                "raw_source_checksum": m.raw_source_checksum or "",
            }
            for m in matches
        ]

        recalculated_fp = DatasetFingerprintCalculator.compute_fingerprint(
            key=release.key,
            version=release.version,
            selection_policy_key=release.selection_policy_key,
            selection_policy_version=release.selection_policy_version,
            seasons_data=seasons_data,
            matches_data=matches_data,
        )

        if recalculated_fp != release.dataset_fingerprint:
            blockers.append(
                f"Fingerprint integrity mismatch! Stored={release.dataset_fingerprint}, Recalculated={recalculated_fp}"
            )
        else:
            checks_passed.append(f"Dataset fingerprint verified ({recalculated_fp}).")

        is_valid = len(blockers) == 0

        return DatasetValidationReport(
            dataset_key=dataset_key,
            version=version,
            is_valid=is_valid,
            status=DatasetReleaseStatusEnum(release.status),
            target_competitions_count=len(comp_season_counts),
            total_seasons_count=len(seasons),
            total_matches_count=len(matches),
            checks_passed=checks_passed,
            blockers=blockers,
            warnings=warnings,
        )
