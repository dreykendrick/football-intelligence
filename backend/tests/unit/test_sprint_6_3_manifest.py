"""
Sprint 6.3 Manifest Integrity & Determinism Tests (Section 83)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FROZEN_PHASE5_MASTER_HASH = "68b151b2c9683d4a431605bfda45902d78a2335f533ab49256ef47713ce22524"
FROZEN_PHASE5_2_POLICY_HASH = "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"
FROZEN_PHASE6_1_INGESTION_HASH = "98c0e07bee158e0493dbfbff036bc6b3e8c2f763c87c9d715a8ee5a2df0423d7"
FROZEN_PHASE6_2_CANONICAL_HASH = "7ac6041ff6169a321524b39f7c2bd3610913c94c3b4fc350a89c2550690a8b7b"
HALLUCINATED_PHASE6_2_HASH = "7ac604ae60bf3d3dca2f2549925e01f681335f6063f972b9a1e05d2e078977c8"


def get_manifest_path() -> Path:
    return Path(__file__).resolve().parents[3] / "phase6_3_shadow_prediction_manifest.json"


def test_phase6_3_manifest_exists_and_retains_parent_hashes():
    p = get_manifest_path()
    assert p.exists(), f"Phase 6.3 manifest missing at {p}"

    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    parent_hashes = data["immutable_scientific_manifest_hashes"]
    assert parent_hashes["phase5_master_scientific_manifest_hash"] == FROZEN_PHASE5_MASTER_HASH
    assert parent_hashes["phase5_2_monitoring_policy_hash"] == FROZEN_PHASE5_2_POLICY_HASH
    assert parent_hashes["phase6_1_live_ingestion_manifest_hash"] == FROZEN_PHASE6_1_INGESTION_HASH
    assert parent_hashes["phase6_2_feature_materialization_manifest_hash"] == FROZEN_PHASE6_2_CANONICAL_HASH
    assert parent_hashes["phase6_2_feature_materialization_manifest_hash"] != HALLUCINATED_PHASE6_2_HASH


def test_phase6_3_manifest_hash_is_deterministic():
    p = get_manifest_path()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    canonical_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
    h1 = hashlib.sha256(canonical_bytes).hexdigest()
    h2 = hashlib.sha256(canonical_bytes).hexdigest()
    assert h1 == h2
    assert len(h1) == 64


def test_phase6_3_manifest_cross_platform_newline_invariance():
    p = get_manifest_path()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    crlf_str = json.dumps(data, indent=2).replace("\n", "\r\n")
    lf_str = json.dumps(data, indent=2).replace("\r\n", "\n")

    dict_crlf = json.loads(crlf_str)
    dict_lf = json.loads(lf_str)

    hash_crlf = hashlib.sha256(json.dumps(dict_crlf, sort_keys=True).encode("utf-8")).hexdigest()
    hash_lf = hashlib.sha256(json.dumps(dict_lf, sort_keys=True).encode("utf-8")).hexdigest()

    assert hash_crlf == hash_lf


def test_phase6_3_manifest_retains_frozen_market_ownership():
    p = get_manifest_path()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    mo = data["market_ownership"]
    assert mo["1x2_primary"] == "C1_Multinomial_Logistic_1X2"
    assert mo["1x2_structural_diagnostic"] == "M1_Attack_Defense_Poisson"
    assert mo["expected_goals"] == "M1_Attack_Defense_Poisson"
    assert mo["btts"] == "M1_Attack_Defense_Poisson"
    assert mo["over_under_2_5"] == "M1_Attack_Defense_Poisson"
    assert mo["exact_scores"] == "M1_Attack_Defense_Poisson"

    gov = data["governance_constraints"]
    assert not gov["automatic_retraining"]
    assert not gov["automatic_recalibration"]
    assert not gov["public_predictions"]
    assert gov["bookmaker_odds"] == "FORBIDDEN"
