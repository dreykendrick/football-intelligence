"""
Analytical Data Quality Rules Implementation
Validates duplicate fixtures, team name similarity diagnostics, season completeness, and chronology.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.db.models import Match, Season, Team
from app.quality.base import QualityFinding, QualitySeverityEnum


def evaluate_analytical_rules(db: Session) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    matches = db.query(Match).all()

    # DQ_DUPLICATE_001: Suspicious Duplicate Fixture Candidate
    fixture_groups: dict[tuple, list[Match]] = defaultdict(list)
    for match in matches:
        date_str = match.kickoff_utc.strftime("%Y-%m-%d")
        group_key = (match.season_id, match.home_team_id, match.away_team_id, date_str)
        fixture_groups[group_key].append(match)

    for group_key, match_group in fixture_groups.items():
        if len(match_group) > 1:
            first_match = match_group[0]
            comp_code = first_match.season.competition.code if first_match.season and first_match.season.competition else "UNKNOWN"
            season_year = first_match.season.season_year if first_match.season else "UNKNOWN"

            for dup_match in match_group[1:]:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_DUPLICATE_001",
                        severity=QualitySeverityEnum.BLOCKING,
                        issue_key=f"match:{dup_match.id}:duplicate_fixture",
                        description=f"Duplicate match candidate detected for teams {dup_match.home_team.canonical_name} vs {dup_match.away_team.canonical_name} on {group_key[3]}.",
                        entity_type="MATCH",
                        entity_id=dup_match.id,
                        competition_code=comp_code,
                        season_year=season_year,
                        metadata_payload={"original_match_id": str(first_match.id)},
                    )
                )

    # DQ_TEAM_002: Suspicious Canonical Team Alias Similarity
    teams = db.query(Team).all()
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            t1 = teams[i].canonical_name.strip()
            t2 = teams[j].canonical_name.strip()

            ratio = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()

            # Token overlap check (e.g., "Man United" vs "Manchester United")
            tokens1 = set(t1.lower().split())
            tokens2 = set(t2.lower().split())
            common_tokens = tokens1 & tokens2
            significant_common = [tok for tok in common_tokens if tok not in ("fc", "cf", "afc", "sc", "club")]

            if (ratio >= 0.70 or len(significant_common) >= 1) and t1.lower() != t2.lower():
                findings.append(
                    QualityFinding(
                        rule_key="DQ_TEAM_002",
                        severity=QualitySeverityEnum.WARNING,
                        issue_key=f"team:{teams[i].id}:{teams[j].id}:similar_name",
                        description=f"Suspicious canonical team name similarity between '{t1}' and '{t2}' (Similarity: {ratio:.2f}). Requires manual review.",
                        entity_type="TEAM",
                        entity_id=teams[i].id,
                        metadata_payload={
                            "team1": t1,
                            "team2": t2,
                            "team2_id": str(teams[j].id),
                            "similarity_ratio": round(ratio, 4),
                        },
                    )
                )

    # DQ_SEASON_001 & DQ_CHRONO_001 & DQ_CHRONO_002
    seasons = db.query(Season).all()
    for season in seasons:
        comp_code = season.competition.code if season.competition else "UNKNOWN"
        season_matches = db.query(Match).filter_by(season_id=season.id).order_by(Match.kickoff_utc).all()

        if not season_matches:
            continue

        # Check unique teams in season
        team_ids = set()
        for m in season_matches:
            team_ids.add(m.home_team_id)
            team_ids.add(m.away_team_id)

        n_teams = len(team_ids)
        if n_teams > 1:
            expected_matches = n_teams * (n_teams - 1)
            actual_matches = len(season_matches)
            if actual_matches < expected_matches:
                findings.append(
                    QualityFinding(
                        rule_key="DQ_SEASON_001",
                        severity=QualitySeverityEnum.WARNING,
                        issue_key=f"season:{season.id}:incomplete_match_count",
                        description=f"Season {comp_code} {season.season_year} match count ({actual_matches}) is less than expected double round-robin ({expected_matches} for {n_teams} teams).",
                        entity_type="SEASON",
                        entity_id=season.id,
                        competition_code=comp_code,
                        season_year=season.season_year,
                        metadata_payload={"expected": expected_matches, "actual": actual_matches, "teams": n_teams},
                    )
                )

        # DQ_CHRONO_002: Date-only precision notification
        date_only_count = sum(1 for m in season_matches if m.kickoff_utc.hour == 12 and m.kickoff_utc.minute == 0)
        if date_only_count > 0:
            findings.append(
                QualityFinding(
                    rule_key="DQ_CHRONO_002",
                    severity=QualitySeverityEnum.INFO,
                    issue_key=f"season:{season.id}:date_only_precision",
                    description=f"Season {comp_code} {season.season_year} contains {date_only_count} matches with date-only precision (12:00 UTC).",
                    entity_type="SEASON",
                    entity_id=season.id,
                    competition_code=comp_code,
                    season_year=season.season_year,
                    metadata_payload={"date_only_count": date_only_count, "total_matches": len(season_matches)},
                )
            )

    return findings
