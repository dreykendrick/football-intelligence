"""
Data Quality Validation Engine
Orchestrates rule execution, findings deduplication, PostgreSQL persistence, and resolution management.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import DataQualityLog
from app.quality.base import FindingResolutionStatusEnum, QualityFinding
from app.quality.rules.analytical import evaluate_analytical_rules
from app.quality.rules.domain import evaluate_domain_rules
from app.quality.rules.registry import RULE_REGISTRY
from app.quality.rules.structural import evaluate_structural_rules


class DataQualityEngine:
    """Data Quality Validation Engine."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def run_all_checks(self) -> list[QualityFinding]:
        findings: list[QualityFinding] = []

        # 1. Structural Validation Rules
        findings.extend(evaluate_structural_rules(self.db))

        # 2. Domain Validation Rules
        findings.extend(evaluate_domain_rules(self.db))

        # 3. Analytical Validation Rules
        findings.extend(evaluate_analytical_rules(self.db))

        # 4. Persist Findings to Database with lifecycle tracking
        self.persist_findings(findings)

        return findings

    def persist_findings(self, findings: list[QualityFinding]) -> None:
        detected_issue_keys = {f.issue_key for f in findings}

        # 1. Persist or Update Active Findings
        for finding in findings:
            rule_spec = RULE_REGISTRY.get(finding.rule_key)
            quality_type = rule_spec.category.value if rule_spec else "UNKNOWN"

            existing_log = (
                self.db.query(DataQualityLog)
                .filter_by(issue_key=finding.issue_key)
                .first()
            )

            if not existing_log:
                db_log = DataQualityLog(
                    match_id=finding.entity_id if finding.entity_type == "MATCH" else None,
                    quality_type=quality_type,
                    rule_key=finding.rule_key,
                    severity=finding.severity.value,
                    quality_score=finding.quality_score,
                    issue_key=finding.issue_key,
                    description=finding.description,
                    entity_type=finding.entity_type,
                    entity_id=finding.entity_id,
                    competition_code=finding.competition_code,
                    season_year=finding.season_year,
                    resolution_status=finding.resolution_status.value,
                    resolution_reason=finding.resolution_reason,
                    metadata_payload=finding.metadata_payload,
                )
                self.db.add(db_log)
            else:
                existing_log.severity = finding.severity.value
                existing_log.description = finding.description
                existing_log.metadata_payload = finding.metadata_payload
                if existing_log.resolution_status == FindingResolutionStatusEnum.RESOLVED.value:
                    existing_log.resolution_status = FindingResolutionStatusEnum.OPEN.value
                    existing_log.resolution_reason = None

        # 2. Resolve Previous Findings No Longer Detected
        open_logs = (
            self.db.query(DataQualityLog)
            .filter_by(resolution_status=FindingResolutionStatusEnum.OPEN.value)
            .all()
        )
        for log in open_logs:
            if log.issue_key not in detected_issue_keys:
                log.resolution_status = FindingResolutionStatusEnum.RESOLVED.value
                log.resolution_reason = "Issue no longer detected during quality validation run."

        self.db.commit()

    def update_resolution_status(
        self, issue_key: str, status: str, reason: str | None = None
    ) -> bool:
        log = self.db.query(DataQualityLog).filter_by(issue_key=issue_key).first()
        if not log:
            return False

        log.resolution_status = status
        if reason:
            log.resolution_reason = reason

        self.db.commit()
        return True
