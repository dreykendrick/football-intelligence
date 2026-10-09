"""
Unit Tests for Dataset Fingerprint Calculator
"""
from datetime import UTC, datetime
from uuid import uuid4

from app.dataset.fingerprint import DatasetFingerprintCalculator


def test_fingerprint_determinism_identical_inputs():
    match_id_1 = uuid4()
    match_id_2 = uuid4()
    team_a = uuid4()
    team_b = uuid4()

    seasons = [
        {"competition_code": "E0", "season_year": "2023-24", "source_checksum": "abc123hash"},
        {"competition_code": "SP1", "season_year": "2023-24", "source_checksum": "xyz456hash"},
    ]

    matches = [
        {
            "match_id": match_id_1,
            "kickoff_utc": datetime(2023, 8, 11, 19, 0, tzinfo=UTC),
            "home_team_id": team_a,
            "away_team_id": team_b,
            "home_score": 2,
            "away_score": 1,
            "raw_source_checksum": "abc123hash",
        },
        {
            "match_id": match_id_2,
            "kickoff_utc": datetime(2023, 8, 12, 14, 0, tzinfo=UTC),
            "home_team_id": team_b,
            "away_team_id": team_a,
            "home_score": 0,
            "away_score": 0,
            "raw_source_checksum": "abc123hash",
        },
    ]

    fp1 = DatasetFingerprintCalculator.compute_fingerprint(
        key="mvp_a_historical",
        version="v1",
        selection_policy_key="mvp_a_recent_3_usable_seasons_v1",
        selection_policy_version="1.0.0",
        seasons_data=seasons,
        matches_data=matches,
    )

    fp2 = DatasetFingerprintCalculator.compute_fingerprint(
        key="mvp_a_historical",
        version="v1",
        selection_policy_key="mvp_a_recent_3_usable_seasons_v1",
        selection_policy_version="1.0.0",
        seasons_data=seasons,
        matches_data=matches,
    )

    assert len(fp1) == 64
    assert fp1 == fp2


def test_fingerprint_changes_when_match_score_modified():
    match_id_1 = uuid4()
    team_a = uuid4()
    team_b = uuid4()

    seasons = [{"competition_code": "E0", "season_year": "2023-24", "source_checksum": "hash"}]

    matches_base = [
        {
            "match_id": match_id_1,
            "kickoff_utc": datetime(2023, 8, 11, 19, 0, tzinfo=UTC),
            "home_team_id": team_a,
            "away_team_id": team_b,
            "home_score": 2,
            "away_score": 1,
            "raw_source_checksum": "hash",
        }
    ]

    matches_mutated = [
        {
            "match_id": match_id_1,
            "kickoff_utc": datetime(2023, 8, 11, 19, 0, tzinfo=UTC),
            "home_team_id": team_a,
            "away_team_id": team_b,
            "home_score": 3,  # Score mutated
            "away_score": 1,
            "raw_source_checksum": "hash",
        }
    ]

    fp_base = DatasetFingerprintCalculator.compute_fingerprint(
        key="mvp_a_historical", version="v1", selection_policy_key="p1", selection_policy_version="1.0.0",
        seasons_data=seasons, matches_data=matches_base
    )

    fp_mutated = DatasetFingerprintCalculator.compute_fingerprint(
        key="mvp_a_historical", version="v1", selection_policy_key="p1", selection_policy_version="1.0.0",
        seasons_data=seasons, matches_data=matches_mutated
    )

    assert fp_base != fp_mutated


def test_fingerprint_changes_when_source_checksum_modified():
    match_id_1 = uuid4()
    team_a = uuid4()
    team_b = uuid4()

    matches = [
        {
            "match_id": match_id_1,
            "kickoff_utc": datetime(2023, 8, 11, 19, 0, tzinfo=UTC),
            "home_team_id": team_a,
            "away_team_id": team_b,
            "home_score": 1,
            "away_score": 1,
            "raw_source_checksum": "hash1",
        }
    ]

    seasons1 = [{"competition_code": "E0", "season_year": "2023-24", "source_checksum": "hash1"}]
    seasons2 = [{"competition_code": "E0", "season_year": "2023-24", "source_checksum": "hash2_modified"}]

    fp1 = DatasetFingerprintCalculator.compute_fingerprint("key", "v1", "p1", "1.0.0", seasons1, matches)
    fp2 = DatasetFingerprintCalculator.compute_fingerprint("key", "v1", "p1", "1.0.0", seasons2, matches)

    assert fp1 != fp2
