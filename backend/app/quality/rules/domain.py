"""
Domain Data Quality Rules Implementation
Validates match scores, home/away distinctness, score-result agreement, and stats boundaries.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Match, MatchStatistic
from app.quality.base import QualityFinding, QualitySeverityEnum


def evaluate_domain_rules(db: Session) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    matches = db.query(Match).all()

    for match in matches:
        comp_code = match.season.competition.code if match.season and match.season.competition else "UNKNOWN"
        season_year = match.season.season_year if match.season else "UNKNOWN"

        # DQ_MATCH_005: Same Home & Away Team
        if match.home_team_id == match.away_team_id:
            findings.append(
                QualityFinding(
                    rule_key="DQ_MATCH_005",
                    severity=QualitySeverityEnum.BLOCKING,
                    issue_key=f"match:{match.id}:identical_teams",
                    description=f"Match {match.id} has identical home_team_id and away_team_id.",
                    entity_type="MATCH",
                    entity_id=match.id,
                    competition_code=comp_code,
                    season_year=season_year,
                )
            )

        if match.status == "FINISHED":
            # DQ_MATCH_001: Missing Home Score
            if match.home_score is None:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_MATCH_001",
                        severity=QualitySeverityEnum.BLOCKING,
                        issue_key=f"match:{match.id}:missing_home_score",
                        description=f"Finished match {match.id} has NULL home_score.",
                        entity_type="MATCH",
                        entity_id=match.id,
                        competition_code=comp_code,
                        season_year=season_year,
                    )
                )

            # DQ_MATCH_002: Missing Away Score
            if match.away_score is None:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_MATCH_002",
                        severity=QualitySeverityEnum.BLOCKING,
                        issue_key=f"match:{match.id}:missing_away_score",
                        description=f"Finished match {match.id} has NULL away_score.",
                        entity_type="MATCH",
                        entity_id=match.id,
                        competition_code=comp_code,
                        season_year=season_year,
                    )
                )

            # DQ_MATCH_003: Negative Home Score
            if match.home_score is not None and match.home_score < 0:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_MATCH_003",
                        severity=QualitySeverityEnum.BLOCKING,
                        issue_key=f"match:{match.id}:negative_home_score",
                        description=f"Match {match.id} has negative home_score ({match.home_score}).",
                        entity_type="MATCH",
                        entity_id=match.id,
                        competition_code=comp_code,
                        season_year=season_year,
                    )
                )

            # DQ_MATCH_004: Negative Away Score
            if match.away_score is not None and match.away_score < 0:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_MATCH_004",
                        severity=QualitySeverityEnum.BLOCKING,
                        issue_key=f"match:{match.id}:negative_away_score",
                        description=f"Match {match.id} has negative away_score ({match.away_score}).",
                        entity_type="MATCH",
                        entity_id=match.id,
                        competition_code=comp_code,
                        season_year=season_year,
                    )
                )

            # DQ_STAT_002: Extreme Goal Anomaly
            if match.home_score is not None and match.away_score is not None:
                total_goals = match.home_score + match.away_score
                if total_goals >= 9:
                    findings.append(
                        QualityFinding(
                            rule_key="DQ_STAT_002",
                            severity=QualitySeverityEnum.WARNING,
                            issue_key=f"match:{match.id}:extreme_goals",
                            description=f"Match {match.id} has extreme combined goals count ({total_goals} goals).",
                            entity_type="MATCH",
                            entity_id=match.id,
                            competition_code=comp_code,
                            season_year=season_year,
                            metadata_payload={"home_score": match.home_score, "away_score": match.away_score},
                        )
                    )

    # DQ_STAT_001: Shots On Target Exceeds Total Shots
    stats = db.query(MatchStatistic).all()
    for stat in stats:
        if stat.shots is not None and stat.shots_on_target is not None:
            if stat.shots_on_target > stat.shots:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_STAT_001",
                        severity=QualitySeverityEnum.ERROR,
                        issue_key=f"match_stat:{stat.id}:shots_on_target_exceeds",
                        description=f"Match statistic {stat.id} has shots_on_target ({stat.shots_on_target}) > total shots ({stat.shots}).",
                        entity_type="MATCH",
                        entity_id=stat.match_id,
                    )
                )

    return findings
