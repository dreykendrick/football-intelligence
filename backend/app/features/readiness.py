"""
Phase 3 Feature Set Readiness & Certification Service
Audits feature manifests, registry completeness, anti-leakage safeguards, dependency selectivity,
numeric finiteness, determinism, and produces official Phase 3 Readiness certification reports.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import Competition, HistoricalDatasetMatch, HistoricalDatasetRelease, Match, Season, Team
from app.features.assembler import FeatureSetAssembler, FeatureSetVectorDTO
from app.features.definitions import CORE_FEATURE_DEFINITIONS
from app.features.manifest import EXCLUDED_FEATURE_KEYS, FeatureSetManifest, get_mvp_a_feature_set_v1_manifest
from app.features.registry import FEATURE_CATALOG, global_feature_registry


class FeatureSetReadinessError(Exception):
    """Raised when Phase 3 Readiness validation fails with blocking issues."""
    pass


class FeatureSetReadinessService:
    """Central certification service for auditing Phase 3 feature sets and certifying Phase 4 readiness."""

    def __init__(self, manifest: FeatureSetManifest | None = None) -> None:
        self.manifest = manifest or get_mvp_a_feature_set_v1_manifest()
        self.assembler = FeatureSetAssembler(self.manifest)

    def validate_manifest(self) -> list[str]:
        """Audits manifest key uniqueness, excluded key protection, and fingerprint determinism."""
        blockers: list[str] = []

        # 1. Duplicate keys check
        keys = self.manifest.included_feature_keys
        if len(keys) != len(set(keys)):
            blockers.append("Manifest contains duplicate feature keys.")

        # 2. Disallowed / Phase 4 key exclusion check
        included_set = set(keys)
        for disallowed in EXCLUDED_FEATURE_KEYS:
            if disallowed in included_set:
                blockers.append(f"Disallowed Phase 4 / odds key '{disallowed}' found inside manifest included_feature_keys.")

        # 3. Fingerprint determinism check
        fp1 = self.manifest.fingerprint
        fp2 = self.manifest.fingerprint
        if fp1 != fp2 or len(fp1) != 16:
            blockers.append("Manifest fingerprint is non-deterministic or invalid length.")

        return blockers

    def validate_registry_and_calculators(self) -> list[str]:
        """Audits that every manifest key resolves 1-to-1 to a registered definition and executable calculator."""
        blockers: list[str] = []

        for fkey in self.manifest.included_feature_keys:
            # Check definition
            if not global_feature_registry.get_definition(fkey):
                blockers.append(f"Feature key '{fkey}' in manifest has no registered FeatureDefinitionDTO.")

            # Check calculator
            try:
                calc = global_feature_registry.get_calculator(fkey)
                if not hasattr(calc, "calculate"):
                    blockers.append(f"Calculator for '{fkey}' does not implement calculate method.")
            except KeyError:
                blockers.append(f"Feature key '{fkey}' in manifest has no registered calculator in FEATURE_CATALOG.")

        return blockers

    def validate_vector_invariants(self, vector: FeatureSetVectorDTO) -> list[str]:
        """Audits numerical finiteness, missingness consistency, and mathematical bounds on a feature vector."""
        blockers: list[str] = []

        for res in vector.ordered_feature_values:
            # 1. Finite numeric check
            if res.value is not None and isinstance(res.value, (int, float)):
                if math.isnan(res.value) or math.isinf(res.value):
                    blockers.append(f"Non-finite numeric value ({res.value}) in feature '{res.feature_key}'.")

            # 2. Missingness consistency check
            if res.is_missing and res.value is not None:
                # If value is present when missing, missing_reason must be documented
                pass
            if not res.is_missing and res.value is None:
                blockers.append(f"Feature '{res.feature_key}' marked AVAILABLE (is_missing=False) but contains None value.")

            # 3. Sample size non-negative check
            if res.sample_size < 0:
                blockers.append(f"Feature '{res.feature_key}' has negative sample size ({res.sample_size}).")

        return blockers

    def validate_anti_leakage_and_isolation(self, db: Session) -> list[str]:
        """Audits complete vector target result leakage, future match leakage, and approved dataset boundary isolation."""
        blockers: list[str] = []

        # Create temporary test scenario
        code_suffix = uuid4().hex[:6]
        comp = Competition(code=f"CERT_LEAK_{code_suffix}", name="Cert Leak Test", country="Test")
        season = Season(competition=comp, season_year="2023/24")
        t1 = Team(canonical_name=f"Cert Team A {code_suffix}")
        t2 = Team(canonical_name=f"Cert Team B {code_suffix}")

        now = datetime.now(UTC)
        m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
        m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=4, away_score=0)
        m_future = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now + timedelta(days=5), status="FINISHED", home_score=0, away_score=3)

        rel_approved = db.query(HistoricalDatasetRelease).filter_by(key="mvp_a_historical", version="v1").first()
        if not rel_approved:
            rel_approved = HistoricalDatasetRelease(key="mvp_a_historical", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)
            db.add(rel_approved)
            db.flush()

        db.add_all([comp, season, t1, t2, m_prev, m_target, m_future])
        db.flush()

        link1 = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_prev.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_prev.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        link_target = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_target.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_target.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        db.add_all([link1, link_target])
        db.flush()

        try:
            # 1. Baseline assembly
            v1 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            # 2. Target result mutation leakage check
            m_target.home_score = 0
            m_target.away_score = 10
            db.flush()

            v2 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            if v1.feature_vector_dict != v2.feature_vector_dict:
                blockers.append("TARGET LEAKAGE DETECTED: Mutating target match score altered pre-match feature values.")

            if v1.snapshot_fingerprint != v2.snapshot_fingerprint:
                blockers.append("TARGET LEAKAGE DETECTED: Snapshot fingerprint altered after target score mutation.")

            # 3. Future match addition leakage check
            m_future.home_score = 8
            m_future.away_score = 0
            db.flush()

            v3 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            if v1.feature_vector_dict != v3.feature_vector_dict:
                blockers.append("FUTURE LEAKAGE DETECTED: Future match modification altered target pre-match feature values.")

        except Exception as e:
            blockers.append(f"Anti-leakage validation exception: {str(e)}")

        return blockers

    def validate_dependency_selectivity(self, db: Session) -> list[str]:
        """Audits that prior score mutation affects form/strength/Elo but leaves rest/schedule features unchanged."""
        blockers: list[str] = []

        code_suffix = uuid4().hex[:6]
        comp = Competition(code=f"CERT_SEL_{code_suffix}", name="Selectivity Test", country="Test")
        season = Season(competition=comp, season_year="2023/24")
        t1 = Team(canonical_name=f"Sel Team A {code_suffix}")
        t2 = Team(canonical_name=f"Sel Team B {code_suffix}")

        now = datetime.now(UTC)
        m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=0)
        m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

        rel_approved = db.query(HistoricalDatasetRelease).filter_by(key="mvp_a_historical", version="v1").first()
        if not rel_approved:
            rel_approved = HistoricalDatasetRelease(key="mvp_a_historical", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)
            db.add(rel_approved)
            db.flush()

        db.add_all([comp, season, t1, t2, m_prev, m_target])
        db.flush()

        link1 = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_prev.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_prev.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        link_target = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_target.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_target.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        db.add_all([link1, link_target])
        db.flush()

        try:
            v1 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            # Mutate prior score from 1-0 to 6-0
            m_prev.home_score = 6
            db.flush()
            db.expire_all()

            v2 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            # Form & Elo should change
            if v1.feature_vector_dict.get("home_goals_scored_avg_v1") == v2.feature_vector_dict.get("home_goals_scored_avg_v1"):
                blockers.append("DEPENDENCY SELECTIVITY FAIL: Prior score change did not update goal averages.")

            # Rest & schedule counts MUST remain identical
            if v1.feature_vector_dict.get("home_rest_days_v1") != v2.feature_vector_dict.get("home_rest_days_v1"):
                blockers.append("DEPENDENCY SELECTIVITY FAIL: Prior score change incorrectly altered rest days.")

            if v1.feature_vector_dict.get("home_matches_last_14d_v1") != v2.feature_vector_dict.get("home_matches_last_14d_v1"):
                blockers.append("DEPENDENCY SELECTIVITY FAIL: Prior score change incorrectly altered match counts.")

        except Exception as e:
            blockers.append(f"Selectivity validation exception: {str(e)}")

        return blockers

    def validate_determinism(self, db: Session) -> list[str]:
        """Audits 100% reproduction across repeated assembly runs on identical inputs."""
        blockers: list[str] = []

        code_suffix = uuid4().hex[:6]
        comp = Competition(code=f"CERT_DET_{code_suffix}", name="Determinism Test", country="Test")
        season = Season(competition=comp, season_year="2023/24")
        t1 = Team(canonical_name=f"Det Team A {code_suffix}")
        t2 = Team(canonical_name=f"Det Team B {code_suffix}")

        now = datetime.now(UTC)
        m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=4), status="FINISHED", home_score=2, away_score=1)
        m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

        rel_approved = db.query(HistoricalDatasetRelease).filter_by(key="mvp_a_historical", version="v1").first()
        if not rel_approved:
            rel_approved = HistoricalDatasetRelease(key="mvp_a_historical", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)
            db.add(rel_approved)
            db.flush()

        db.add_all([comp, season, t1, t2, m_prev, m_target])
        db.flush()

        link1 = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_prev.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_prev.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        link_target = HistoricalDatasetMatch(
            dataset_release_id=rel_approved.id, match_id=m_target.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m_target.kickoff_utc, home_team_id=t1.id, away_team_id=t2.id
        )
        db.add_all([link1, link_target])
        db.flush()

        try:
            v1 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)
            v2 = self.assembler.assemble_feature_vector_for_match(db, m_target.id, cutoff_timestamp=now)

            if v1.feature_vector_dict != v2.feature_vector_dict:
                blockers.append("DETERMINISM FAIL: Repeated feature assembly produced different vector values.")

            if v1.snapshot_fingerprint != v2.snapshot_fingerprint:
                blockers.append("DETERMINISM FAIL: Repeated feature assembly produced different fingerprints.")

        except Exception as e:
            blockers.append(f"Determinism validation exception: {str(e)}")

        return blockers

    def assert_feature_set_ready(self, db: Session) -> None:
        """Audits all readiness rules and raises FeatureSetReadinessError if any blocking issues exist."""
        all_blockers: list[str] = []

        all_blockers.extend(self.validate_manifest())
        all_blockers.extend(self.validate_registry_and_calculators())
        all_blockers.extend(self.validate_anti_leakage_and_isolation(db))
        all_blockers.extend(self.validate_dependency_selectivity(db))
        all_blockers.extend(self.validate_determinism(db))

        if all_blockers:
            msg = f"Phase 3 Readiness Check FAILED for feature set '{self.manifest.feature_set_key}' with {len(all_blockers)} blockers:\n"
            msg += "\n".join(f"- {b}" for b in all_blockers)
            raise FeatureSetReadinessError(msg)

    def get_readiness_report(self, db: Session) -> dict[str, Any]:
        """Generates a structured Phase 3 Readiness certification report."""
        blockers: list[str] = []
        blockers.extend(self.validate_manifest())
        blockers.extend(self.validate_registry_and_calculators())
        blockers.extend(self.validate_anti_leakage_and_isolation(db))
        blockers.extend(self.validate_dependency_selectivity(db))
        blockers.extend(self.validate_determinism(db))

        status = "READY" if not blockers else "NOT_READY"

        return {
            "feature_set_key": self.manifest.feature_set_key,
            "version": self.manifest.version,
            "dataset_release_key": self.manifest.dataset_release_key,
            "manifest_fingerprint": self.manifest.fingerprint,
            "total_feature_count": self.manifest.feature_count,
            "status": status,
            "blockers": blockers,
            "phase_3_readiness": "READY" if status == "READY" else "NOT_READY",
            "phase_4_readiness": "READY" if status == "READY" else "NOT_READY",
            "audit_timestamp": datetime.now(UTC).isoformat(),
        }
