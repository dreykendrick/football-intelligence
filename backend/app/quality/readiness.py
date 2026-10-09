"""
Feature Readiness Assessor & Global Quality Reporter
Evaluates source data readiness for upcoming feature engineering modules and derives quality component scores.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Competition, Match, MatchStatistic, Season, Team
from app.quality.base import (
    FeatureReadinessReport,
    GlobalQualityReport,
    QualityFinding,
    QualitySeverityEnum,
    ReadinessStatusEnum,
    SeasonCompletenessReport,
)


class FeatureReadinessAssessor:
    """Evaluates readiness of stored data for future predictive feature generation."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def generate_global_report(self, findings: list[QualityFinding]) -> GlobalQualityReport:
        total_competitions = self.db.query(Competition).count()
        total_seasons = self.db.query(Season).count()
        total_matches = self.db.query(Match).count()
        total_teams = self.db.query(Team).count()

        blocking_count = sum(1 for f in findings if f.severity == QualitySeverityEnum.BLOCKING and f.resolution_status == "OPEN")
        warning_count = sum(1 for f in findings if f.severity == QualitySeverityEnum.WARNING and f.resolution_status == "OPEN")
        info_count = sum(1 for f in findings if f.severity == QualitySeverityEnum.INFO)

        # 1. Season Completeness Reports
        season_reports = self._generate_season_reports(findings)

        # 2. Feature Readiness Modules
        feature_readiness = self._assess_feature_modules(total_matches)

        # 3. Calculate Component Scores
        completeness_score = self._calculate_completeness_score(total_matches)
        chronology_score = 1.0  # 1.0 since all dates are parseable UTC timestamps
        mapping_score = 1.0 if not any(f.rule_key == "DQ_TEAM_001" for f in findings) else 0.9
        integrity_score = 1.0 if blocking_count == 0 else max(0.0, 1.0 - (blocking_count * 0.1))

        overall_score = round(
            (completeness_score * 0.3) + (chronology_score * 0.2) + (mapping_score * 0.2) + (integrity_score * 0.3),
            4,
        )

        # 4. Global Status Determination
        if blocking_count > 0:
            global_status = ReadinessStatusEnum.NOT_READY
        elif warning_count > 0:
            global_status = ReadinessStatusEnum.READY_WITH_WARNINGS
        elif total_matches > 0:
            global_status = ReadinessStatusEnum.READY
        else:
            global_status = ReadinessStatusEnum.NOT_READY

        return GlobalQualityReport(
            total_competitions=total_competitions,
            total_seasons=total_seasons,
            total_matches=total_matches,
            total_teams=total_teams,
            total_findings=len(findings),
            blocking_count=blocking_count,
            warning_count=warning_count,
            info_count=info_count,
            global_status=global_status,
            completeness_score=completeness_score,
            chronology_score=chronology_score,
            mapping_score=mapping_score,
            integrity_score=integrity_score,
            overall_quality_score=overall_score,
            season_reports=season_reports,
            feature_readiness=feature_readiness,
        )

    def _generate_season_reports(self, findings: list[QualityFinding]) -> list[SeasonCompletenessReport]:
        reports: list[SeasonCompletenessReport] = []
        seasons = self.db.query(Season).all()

        for season in seasons:
            comp_code = season.competition.code if season.competition else "UNKNOWN"
            season_matches = self.db.query(Match).filter_by(season_id=season.id).all()
            match_count = len(season_matches)

            team_ids = set()
            matches_with_scores = 0
            matches_missing_scores = 0

            for m in season_matches:
                team_ids.add(m.home_team_id)
                team_ids.add(m.away_team_id)
                if m.home_score is not None and m.away_score is not None:
                    matches_with_scores += 1
                else:
                    matches_missing_scores += 1

            n_teams = len(team_ids)
            expected_matches = n_teams * (n_teams - 1) if n_teams > 1 else None

            earliest = min((m.kickoff_utc for m in season_matches), default=None)
            latest = max((m.kickoff_utc for m in season_matches), default=None)

            season_blocking = sum(
                1 for f in findings if f.season_year == season.season_year and f.competition_code == comp_code and f.severity == QualitySeverityEnum.BLOCKING
            )
            season_warning = sum(
                1 for f in findings if f.season_year == season.season_year and f.competition_code == comp_code and f.severity == QualitySeverityEnum.WARNING
            )

            if season_blocking > 0:
                status = ReadinessStatusEnum.BLOCKED
            elif season_warning > 0:
                status = ReadinessStatusEnum.READY_WITH_WARNINGS
            elif match_count > 0:
                status = ReadinessStatusEnum.READY
            else:
                status = ReadinessStatusEnum.NOT_READY

            reports.append(
                SeasonCompletenessReport(
                    competition_code=comp_code,
                    season_year=season.season_year,
                    total_matches=match_count,
                    expected_matches=expected_matches,
                    unique_teams=n_teams,
                    matches_with_scores=matches_with_scores,
                    matches_missing_scores=matches_missing_scores,
                    earliest_match=earliest,
                    latest_match=latest,
                    blocking_findings_count=season_blocking,
                    warning_findings_count=season_warning,
                    readiness_status=status,
                )
            )

        return reports

    def _assess_feature_modules(self, total_matches: int) -> list[FeatureReadinessReport]:
        modules: list[FeatureReadinessReport] = []

        # 1. Elo Rating Module
        modules.append(
            FeatureReadinessReport(
                feature_module_key="elo_ratings",
                feature_module_name="Elo Rating System",
                prerequisites=["Match Kickoff Chronology", "Canonical Teams", "Full-Time Goals / Result"],
                status=ReadinessStatusEnum.READY if total_matches > 0 else ReadinessStatusEnum.NOT_READY,
                coverage_percentage=100.0 if total_matches > 0 else 0.0,
                limitations=["Kickoff times default to 12:00 UTC (date-only precision)"],
            )
        )

        # 2. Goals-Based Attack/Defense Module
        modules.append(
            FeatureReadinessReport(
                feature_module_key="goals_attack_defense",
                feature_module_name="Goals-Based Attack/Defense Strength",
                prerequisites=["Full-Time Home Goals", "Full-Time Away Goals", "Match Chronology"],
                status=ReadinessStatusEnum.READY if total_matches > 0 else ReadinessStatusEnum.NOT_READY,
                coverage_percentage=100.0 if total_matches > 0 else 0.0,
                limitations=[],
            )
        )

        # 3. Recent Form Module
        modules.append(
            FeatureReadinessReport(
                feature_module_key="recent_form",
                feature_module_name="Recent Form (Rolling W/D/L & Goals)",
                prerequisites=["Match Chronology", "Team Identity", "Full-Time Result"],
                status=ReadinessStatusEnum.READY if total_matches > 0 else ReadinessStatusEnum.NOT_READY,
                coverage_percentage=100.0 if total_matches > 0 else 0.0,
                limitations=[],
            )
        )

        # 4. Rest Days & Fixture Congestion
        modules.append(
            FeatureReadinessReport(
                feature_module_key="rest_days",
                feature_module_name="Rest Days & Fixture Congestion",
                prerequisites=["Match Dates", "Canonical Team Resolution"],
                status=ReadinessStatusEnum.READY_WITH_WARNINGS if total_matches > 0 else ReadinessStatusEnum.NOT_READY,
                coverage_percentage=100.0 if total_matches > 0 else 0.0,
                limitations=["Rest days computed with date-level resolution (precision: DATE_ONLY)"],
            )
        )

        # 5. Shots-Based Feature Module
        shots_count = self.db.query(MatchStatistic).filter(MatchStatistic.shots.isnot(None)).count()
        shots_coverage = round((shots_count / (total_matches * 2 or 1)) * 100.0, 1) if total_matches > 0 else 0.0

        modules.append(
            FeatureReadinessReport(
                feature_module_key="shots_based_features",
                feature_module_name="Shots & Shots-on-Target Features",
                prerequisites=["Optional Match Statistics (HS, AS, HST, AST)"],
                status=ReadinessStatusEnum.READY if shots_coverage > 80 else ReadinessStatusEnum.READY_WITH_WARNINGS,
                coverage_percentage=shots_coverage,
                limitations=["Historical seasons prior to 2000 lack shot statistics"],
            )
        )

        # 6. Provider xG Module
        xg_count = self.db.query(MatchStatistic).filter(MatchStatistic.provider_xg.isnot(None)).count()
        xg_coverage = round((xg_count / (total_matches * 2 or 1)) * 100.0, 1) if total_matches > 0 else 0.0

        modules.append(
            FeatureReadinessReport(
                feature_module_key="provider_xg",
                feature_module_name="Provider xG Expected Goals",
                prerequisites=["Provider xG Match Statistics"],
                status=ReadinessStatusEnum.NOT_READY,
                coverage_percentage=xg_coverage,
                limitations=["Football-Data.co.uk CSV files do not contain provider xG data"],
            )
        )

        return modules

    def _calculate_completeness_score(self, total_matches: int) -> float:
        if total_matches == 0:
            return 0.0
        matches_with_scores = self.db.query(Match).filter(Match.home_score.isnot(None), Match.away_score.isnot(None)).count()
        return round(matches_with_scores / total_matches, 4)
