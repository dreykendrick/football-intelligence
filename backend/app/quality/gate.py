"""
Quality Gate & Data Leakage Prevention Verifier
Provides reusable quality gates for feature/backtesting pipelines and verifies time-bounded cutoff queries.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Match
from app.quality.base import GlobalQualityReport, ReadinessStatusEnum
from app.quality.engine import DataQualityEngine
from app.quality.readiness import FeatureReadinessAssessor


class QualityGateException(RuntimeError):
    """Exception raised when Quality Gate fails due to blocking data quality issues."""


class QualityGate:
    """Reusable Quality Gate Enforcer."""

    @staticmethod
    def evaluate_gate(db: Session) -> GlobalQualityReport:
        engine = DataQualityEngine(db)
        findings = engine.run_all_checks()

        assessor = FeatureReadinessAssessor(db)
        report = assessor.generate_global_report(findings)
        return report

    @classmethod
    def assert_historical_data_ready(cls, db: Session) -> GlobalQualityReport:
        report = cls.evaluate_gate(db)
        if report.global_status == ReadinessStatusEnum.NOT_READY or report.blocking_count > 0:
            raise QualityGateException(
                f"Quality Gate FAILED! Historical data contains {report.blocking_count} BLOCKING quality issues. "
                "Feature engineering and backtesting are prohibited until resolved."
            )
        return report

    @staticmethod
    def verify_data_leakage_safety(
        db: Session, team_id: UUID, cutoff_timestamp: datetime
    ) -> list[Match]:
        """Anti-leakage query verification: Retrieves historical matches strictly before cutoff_timestamp."""
        # Ensure cutoff_timestamp is tz-aware
        if cutoff_timestamp.tzinfo is None:
            cutoff_timestamp = cutoff_timestamp.replace(tzinfo=UTC)

        matches = (
            db.query(Match)
            .filter(
                (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
                Match.kickoff_utc < cutoff_timestamp,
            )
            .order_by(Match.kickoff_utc.desc())
            .all()
        )

        # Assert no returned match has kickoff_utc >= cutoff_timestamp
        for m in matches:
            m_kickoff = m.kickoff_utc
            if m_kickoff.tzinfo is None:
                m_kickoff = m_kickoff.replace(tzinfo=UTC)

            if m_kickoff >= cutoff_timestamp:
                raise QualityGateException(
                    f"DATA LEAKAGE DETECTED! Match {m.id} kickoff ({m_kickoff}) is >= cutoff timestamp ({cutoff_timestamp})."
                )

        return matches
