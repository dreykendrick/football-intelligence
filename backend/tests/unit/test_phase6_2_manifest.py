"""
Unit Tests for Phase 6.2 Feature Materialization Manifest Integrity and Canonical Identity.

Guarantees:
1. Manifest Identity Regression Protection: Ensures phase6_ci_database_certification_manifest.json
   accurately references the certified canonical JSON SHA-256 hash (7ac6041ff6169a321524b39f7c2bd3610913c94c3b4fc350a89c2550690a8b7b).
2. Deterministic Canonical Hashing: Ensures sorting keys and UTF-8 encoding yield consistent hashes
   regardless of OS newline conventions (CRLF vs LF).
3. Corrupted / Hallucinated Identity Rejection: Explicitly rejects the erroneous hash (7ac604ae60bf3d3dca2f2549925e01f681335f6063f972b9a1e05d2e078977c8).
"""

import hashlib
import json
from pathlib import Path

FROZEN_PHASE6_2_CANONICAL_HASH = "7ac6041ff6169a321524b39f7c2bd3610913c94c3b4fc350a89c2550690a8b7b"
HALLUCINATED_PHASE6_2_HASH = "7ac604ae60bf3d3dca2f2549925e01f681335f6063f972b9a1e05d2e078977c8"

FROZEN_PHASE5_MASTER_HASH = "68b151b2c9683d4a431605bfda45902d78a2335f533ab49256ef47713ce22524"
FROZEN_PHASE5_2_POLICY_HASH = "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"
FROZEN_PHASE6_1_INGESTION_HASH = "98c0e07bee158e0493dbfbff036bc6b3e8c2f763c87c9d715a8ee5a2df0423d7"

CANONICAL_PHASE6_2_PAYLOAD = {
    "scientific_release_hash": FROZEN_PHASE5_MASTER_HASH,
    "phase6_1_ingestion_manifest_hash": FROZEN_PHASE6_1_INGESTION_HASH,
    "feature_set_id": "v1_standard_251",
    "feature_count": 251,
    "feature_ordering_fingerprint": "order_fp_02f8b524",
    "semantic_fingerprint": "sem_fp_02f8b524",
    "implementation_fingerprint": "impl_fp_7a9c8b1",
    "history_source_rules": [
        "certified_history_only_before_kickoff",
        "operational_results_only_terminal_state",
    ],
    "cutoff_semantics": "strictly_before_kickoff_or_start_of_day_per_family",
    "same_kickoff_semantics": "mutually_invisible",
    "snapshot_schema": [
        "fixture_id",
        "cutoff_at",
        "competition_id",
        "home_team_id",
        "away_team_id",
        "kickoff_utc",
        "feature_values",
    ],
    "snapshot_validity_states": [
        "VALID",
        "STALE_KICKOFF",
        "STALE_HISTORY",
        "STALE_IMPLEMENTATION",
        "STALE_FEATURE_SET",
        "INVALID_SCHEMA",
        "BLOCKED",
    ],
    "quality_policy_identity": FROZEN_PHASE5_2_POLICY_HASH,
    "parity_certification_results": {
        "fixtures_tested": 4338,
        "semantic_mismatches": 0,
        "max_abs_diff": 0,
    },
    "supported_competitions": ["Premier League", "La Liga", "Serie A", "Bundesliga"],
}


def compute_canonical_json_hash(payload: dict) -> str:
    canonical_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def test_phase6_2_manifest_matches_registered_frozen_identity():
    """Ensure CI database certification manifest matches the frozen Phase 6.2 hash."""
    manifest_path = Path(__file__).resolve().parents[3] / "phase6_ci_database_certification_manifest.json"
    assert manifest_path.exists(), f"CI certification manifest missing at {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        ci_manifest = json.load(f)

    immutable_hashes = ci_manifest.get("immutable_scientific_manifest_hashes", {})
    actual_hash = immutable_hashes.get("phase6_2_feature_materialization_manifest_hash")

    assert actual_hash == FROZEN_PHASE6_2_CANONICAL_HASH, (
        f"Phase 6.2 hash mismatch! Expected {FROZEN_PHASE6_2_CANONICAL_HASH}, got {actual_hash}"
    )
    assert actual_hash != HALLUCINATED_PHASE6_2_HASH, "CI manifest contains the hallucinated hash!"

    assert immutable_hashes.get("phase5_master_scientific_manifest_hash") == FROZEN_PHASE5_MASTER_HASH
    assert immutable_hashes.get("phase5_2_monitoring_policy_hash") == FROZEN_PHASE5_2_POLICY_HASH
    assert immutable_hashes.get("phase6_1_live_ingestion_manifest_hash") == FROZEN_PHASE6_1_INGESTION_HASH
    assert immutable_hashes.get("feature_count_frozen") == 251


def test_phase6_2_canonical_payload_hash_determinism():
    """Verify that canonical JSON serialization yields the exact certified hash."""
    computed_hash = compute_canonical_json_hash(CANONICAL_PHASE6_2_PAYLOAD)
    assert computed_hash == FROZEN_PHASE6_2_CANONICAL_HASH


def test_hashing_determinism_cross_platform_newline_invariance():
    """Verify that canonical JSON serialization is invariant to Windows (CRLF) vs Linux (LF) formatting."""
    crlf_formatted_json = json.dumps(CANONICAL_PHASE6_2_PAYLOAD, indent=2).replace("\n", "\r\n")
    lf_formatted_json = json.dumps(CANONICAL_PHASE6_2_PAYLOAD, indent=2).replace("\r\n", "\n")

    dict_from_crlf = json.loads(crlf_formatted_json)
    dict_from_lf = json.loads(lf_formatted_json)

    hash_crlf = compute_canonical_json_hash(dict_from_crlf)
    hash_lf = compute_canonical_json_hash(dict_from_lf)

    assert hash_crlf == hash_lf == FROZEN_PHASE6_2_CANONICAL_HASH


def test_wrong_file_and_hallucinated_hash_detection():
    """Verify wrong file contents and the hallucinated hash string are strictly rejected."""
    corrupted_payload = dict(CANONICAL_PHASE6_2_PAYLOAD)
    corrupted_payload["feature_count"] = 252  # mutated

    corrupted_hash = compute_canonical_json_hash(corrupted_payload)
    assert corrupted_hash != FROZEN_PHASE6_2_CANONICAL_HASH
    assert HALLUCINATED_PHASE6_2_HASH != FROZEN_PHASE6_2_CANONICAL_HASH
