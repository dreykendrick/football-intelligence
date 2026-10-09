"""
Historical Dataset Release Builder Service
Transactionally constructs candidate dataset releases in DRAFT status.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.dataset.base import (
    DatasetBuildReport,
    DatasetCoverageMatrixRow,
    DatasetReleaseStatusEnum,
    DatasetSelectionPolicyEnum,
)
from app.dataset.fingerprint import DatasetFingerprintCalculator
from app.dataset.policy import DatasetSelectionPolicyEngine
from app.db.models import (
    HistoricalDatasetExclusion,
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    HistoricalDatasetSeason,
    Match,
    MatchStatistic,
    ProviderMatchMapping,
    RawSourceRecord,
)
from app.identity.gate import IdentityReadinessGate
from app.providers.historical.manifest import HistoricalSourceCatalog
from app.quality.base import QualitySeverityEnum
from app.quality.engine import DataQualityEngine
from app.quality.readiness import FeatureReadinessAssessor


class HistoricalDatasetBuilder:
    """Service for building explicit, versioned historical dataset releases."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def build_dataset_release(
        self,
        dataset_key: str = "mvp_a_historical",
        version: str = "v1",
        description: str | None = "Official MVP-A Historical Dataset Release",
        policy_key: str = DatasetSelectionPolicyEnum.MVP_A_RECENT_3_USABLE_SEASONS_V1.value,
        policy_version: str = "1.0.0",
        explicit_overrides: dict[str, list[str]] | None = None,
        dry_run: bool = False,
    ) -> DatasetBuildReport:
        """
        Builds a candidate historical dataset release.
        If dry_run=True, computes intended membership and report without committing changes to DB.
        """
        # 1. Check existing release
        existing = (
            self.db.query(HistoricalDatasetRelease)
            .filter_by(key=dataset_key, version=version)
            .first()
        )
        if existing and existing.status == DatasetReleaseStatusEnum.APPROVED.value:
            raise RuntimeError(
                f"Dataset release {dataset_key}:{version} is already APPROVED and immutable."
            )
        if existing and not dry_run:
            # Clean up existing DRAFT / FAILED candidate for re-building
            self.db.delete(existing)
            self.db.flush()

        # 2. Run Quality & Identity Assessment
        engine = DataQualityEngine(self.db)
        findings = engine.run_all_checks()
        assessor = FeatureReadinessAssessor(self.db)
        quality_report = assessor.generate_global_report(findings)
        identity_report = IdentityReadinessGate.evaluate_gate(self.db)

        # 3. Apply Selection Policy
        policy_engine = DatasetSelectionPolicyEngine(
            self.db, policy_key=policy_key, policy_version=policy_version
        )
        selected_seasons_specs = policy_engine.select_seasons(
            season_quality_reports=quality_report.season_reports,
            explicit_overrides=explicit_overrides or {},
        )

        # 4. Source Catalog Lookup
        catalog = HistoricalSourceCatalog.load_default_manifest()

        # Build season objects and match records
        dataset_seasons_data: list[dict[str, Any]] = []
        dataset_matches_data: list[dict[str, Any]] = []
        exclusions_data: list[dict[str, Any]] = []
        coverage_rows: list[DatasetCoverageMatrixRow] = []

        # Find open blocking match IDs
        blocking_match_ids = {
            f.entity_id
            for f in findings
            if f.severity == QualitySeverityEnum.BLOCKING
            and f.resolution_status == "OPEN"
            and f.entity_type == "MATCH"
            and f.entity_id is not None
        }

        # Bulk pre-fetch mappings and raw source records to eliminate N+1 queries
        prov_mappings_map = {
            m.match_id: m for m in self.db.query(ProviderMatchMapping).all()
        }
        raw_records_map = {
            r.external_reference: r for r in self.db.query(RawSourceRecord).all()
        }

        # Process each selected season
        for spec in selected_seasons_specs:
            comp_code = spec["competition_code"]
            year = spec["season_year"]
            comp_id = spec["competition_id"]
            season_id = spec["season_id"]

            # Lookup catalog source checksum
            source_spec = catalog.get_source_spec(comp_code, year)
            source_checksum = source_spec.expected_sha256 if source_spec else None
            source_provider_key = "football_data_uk"
            source_reference = source_spec.relative_path if source_spec else None

            # Fetch matches for season
            season_matches = (
                self.db.query(Match)
                .filter_by(season_id=season_id)
                .order_by(Match.kickoff_utc.asc())
                .all()
            )

            included_matches_count = 0
            for match in season_matches:
                # Inclusion check: FINISHED, valid scores, no blocking DQ log
                is_eligible = (
                    match.status == "FINISHED"
                    and match.home_score is not None
                    and match.away_score is not None
                    and match.id not in blocking_match_ids
                )

                if is_eligible:
                    # Find ingestion batch & raw checksum via pre-fetched maps
                    prov_mapping = prov_mappings_map.get(match.id)
                    batch_id = None
                    raw_checksum = source_checksum

                    if prov_mapping:
                        raw_rec = raw_records_map.get(prov_mapping.external_match_id)
                        if raw_rec:
                            batch_id = raw_rec.ingestion_batch_id
                            if raw_rec.checksum:
                                raw_checksum = raw_rec.checksum

                    dataset_matches_data.append({
                        "match_id": match.id,
                        "competition_id": comp_id,
                        "season_id": season_id,
                        "kickoff_utc": match.kickoff_utc,
                        "home_team_id": match.home_team_id,
                        "away_team_id": match.away_team_id,
                        "home_score": match.home_score,
                        "away_score": match.away_score,
                        "ingestion_batch_id": batch_id,
                        "raw_source_checksum": raw_checksum,
                    })
                    included_matches_count += 1
                else:
                    reason = "Match not finished or missing final score"
                    rule_key = "DQ_MATCH_001"
                    if match.id in blocking_match_ids:
                        reason = "Match has open BLOCKING data quality finding"
                        rule_key = "DQ_BLOCKING_ISSUE"

                    exclusions_data.append({
                        "match_id": match.id,
                        "competition_code": comp_code,
                        "season_year": year,
                        "exclusion_reason": reason,
                        "quality_rule_key": rule_key,
                        "metadata_payload": {"home_score": match.home_score, "away_score": match.away_score, "status": match.status},
                    })

            season_spec_data = {
                "competition_id": comp_id,
                "season_id": season_id,
                "competition_code": comp_code,
                "season_year": year,
                "readiness_status": spec["readiness_status"],
                "match_count": included_matches_count,
                "expected_matches": spec["expected_matches"],
                "source_provider_key": source_provider_key,
                "source_reference": source_reference,
                "source_checksum": source_checksum,
                "metadata_payload": {"raw_file": source_reference},
            }
            dataset_seasons_data.append(season_spec_data)

            coverage_rows.append(
                DatasetCoverageMatrixRow(
                    competition_code=comp_code,
                    competition_name=comp_code,
                    season_year=year,
                    matches=included_matches_count,
                    expected_matches=spec["expected_matches"],
                    quality_status=spec["readiness_status"],
                    source_checksum=source_checksum,
                    included=True,
                )
            )

        # 5. Compute Optional Field Coverage & Date Precision Breakdown
        total_matches_count = len(dataset_matches_data)
        date_precision_stats = {
            "EXACT_TIMESTAMP": total_matches_count,
            "DATE_ONLY": 0,
        }

        # Optional stats counts
        match_ids = [m["match_id"] for m in dataset_matches_data]
        shots_count = (
            self.db.query(MatchStatistic)
            .filter(MatchStatistic.match_id.in_(match_ids), MatchStatistic.shots.isnot(None))
            .count()
        ) if match_ids else 0

        optional_stats_snapshot = {
            "shots_coverage_percent": round((shots_count / (total_matches_count * 2 or 1)) * 100.0, 1),
            "provider_xg_coverage_percent": 0.0,
        }

        feature_readiness_snapshot = [
            f.model_dump() for f in quality_report.feature_readiness
        ]

        # 6. Compute Fingerprint
        fingerprint = DatasetFingerprintCalculator.compute_fingerprint(
            key=dataset_key,
            version=version,
            selection_policy_key=policy_key,
            selection_policy_version=policy_version,
            seasons_data=dataset_seasons_data,
            matches_data=dataset_matches_data,
        )

        metadata_payload = {
            "date_precision": date_precision_stats,
            "optional_stats_coverage": optional_stats_snapshot,
            "feature_readiness": feature_readiness_snapshot,
            "built_at": datetime.now(UTC).isoformat(),
        }

        unique_comp_codes = {s["competition_code"] for s in dataset_seasons_data}

        # 7. Persist to DB if not dry_run
        if not dry_run:
            release_entity = HistoricalDatasetRelease(
                key=dataset_key,
                version=version,
                description=description,
                status=DatasetReleaseStatusEnum.DRAFT.value,
                selection_policy_key=policy_key,
                selection_policy_version=policy_version,
                total_competitions=len(unique_comp_codes),
                total_seasons=len(dataset_seasons_data),
                total_matches=total_matches_count,
                dataset_fingerprint=fingerprint,
                quality_status=quality_report.global_status.value,
                identity_readiness_status=identity_report.overall_status.value,
                metadata_payload=metadata_payload,
            )
            self.db.add(release_entity)
            self.db.flush()

            for s_data in dataset_seasons_data:
                season_entity = HistoricalDatasetSeason(
                    dataset_release_id=release_entity.id,
                    competition_id=s_data["competition_id"],
                    season_id=s_data["season_id"],
                    competition_code=s_data["competition_code"],
                    season_year=s_data["season_year"],
                    readiness_status=s_data["readiness_status"],
                    match_count=s_data["match_count"],
                    expected_matches=s_data["expected_matches"],
                    source_provider_key=s_data["source_provider_key"],
                    source_reference=s_data["source_reference"],
                    source_checksum=s_data["source_checksum"],
                    metadata_payload=s_data["metadata_payload"],
                )
                self.db.add(season_entity)

            for m_data in dataset_matches_data:
                match_entity = HistoricalDatasetMatch(
                    dataset_release_id=release_entity.id,
                    match_id=m_data["match_id"],
                    competition_id=m_data["competition_id"],
                    season_id=m_data["season_id"],
                    kickoff_utc=m_data["kickoff_utc"],
                    home_team_id=m_data["home_team_id"],
                    away_team_id=m_data["away_team_id"],
                    ingestion_batch_id=m_data["ingestion_batch_id"],
                    raw_source_checksum=m_data["raw_source_checksum"],
                )
                self.db.add(match_entity)

            for e_data in exclusions_data:
                excl_entity = HistoricalDatasetExclusion(
                    dataset_release_id=release_entity.id,
                    match_id=e_data["match_id"],
                    competition_code=e_data["competition_code"],
                    season_year=e_data["season_year"],
                    exclusion_reason=e_data["exclusion_reason"],
                    quality_rule_key=e_data["quality_rule_key"],
                    metadata_payload=e_data["metadata_payload"],
                )
                self.db.add(excl_entity)

            self.db.commit()

        return DatasetBuildReport(
            dataset_key=dataset_key,
            version=version,
            status=DatasetReleaseStatusEnum.DRAFT,
            selection_policy_key=policy_key,
            total_competitions=len(unique_comp_codes),
            total_seasons=len(dataset_seasons_data),
            total_matches=total_matches_count,
            total_excluded_matches=len(exclusions_data),
            fingerprint=fingerprint,
            quality_status=quality_report.global_status.value,
            identity_readiness_status=identity_report.overall_status.value,
            coverage_matrix=coverage_rows,
            warnings_accepted=[],
            blocking_issues=[],
        )
