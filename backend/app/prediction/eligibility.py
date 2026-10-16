"""
Prediction Eligibility Verification Service (Section 8)
Strict pre-match assertions: competition support, resolved teams, usable kickoff, snapshot validity, and fingerprints.
"""
from __future__ import annotations

from app.prediction.domain import ShadowPredictionInput

SUPPORTED_COMPETITIONS = {"Premier League", "La Liga", "Serie A", "Bundesliga", "E0", "SP1", "I1", "D1"}
EXPECTED_FEATURE_COUNT = 251

FROZEN_PHASE5_MASTER_HASH = "68b151b2c9683d4a431605bfda45902d78a2335f533ab49256ef47713ce22524"
FROZEN_PHASE5_2_POLICY_HASH = "f974e06a3e2ad4730ed9e6d55ede58f10dd31f5400cd9e39c0c6b06df362887b"
FROZEN_PHASE6_1_INGESTION_HASH = "98c0e07bee158e0493dbfbff036bc6b3e8c2f763c87c9d715a8ee5a2df0423d7"
FROZEN_PHASE6_2_CANONICAL_HASH = "7ac6041ff6169a321524b39f7c2bd3610913c94c3b4fc350a89c2550690a8b7b"


class PredictionEligibilityService:
    """Validates all constraints required before a fixture enters inference."""

    @classmethod
    def check_eligibility(cls, inp: ShadowPredictionInput) -> tuple[bool, str | None]:
        if inp.competition_code not in SUPPORTED_COMPETITIONS:
            return False, f"UNSUPPORTED_COMPETITION: '{inp.competition_code}' is outside certified scope."

        if not inp.home_team_id:
            return False, "UNRESOLVED_TEAM: Canonical home team ID is missing."

        if not inp.away_team_id:
            return False, "UNRESOLVED_TEAM: Canonical away team ID is missing."

        if inp.home_team_id == inp.away_team_id:
            return False, "INVALID_FIXTURE: Home and away teams must be distinct."

        if not inp.kickoff_utc:
            return False, "UNUSABLE_KICKOFF: Kickoff timestamp is missing."

        # Pre-kickoff requirement: prediction must precede kickoff
        if inp.prediction_time >= inp.kickoff_utc:
            return False, (
                f"POST_KICKOFF_PROHIBITED: Prediction time ({inp.prediction_time}) is at or after kickoff ({inp.kickoff_utc})."
            )

        if inp.snapshot_quality_state != "VALID":
            return False, f"SNAPSHOT_INVALID: Feature snapshot state is '{inp.snapshot_quality_state}'."

        if inp.feature_count != EXPECTED_FEATURE_COUNT or len(inp.feature_values) != EXPECTED_FEATURE_COUNT:
            return False, (
                f"FEATURE_COUNT_MISMATCH: Expected {EXPECTED_FEATURE_COUNT} features, got {inp.feature_count}."
            )

        if not inp.feature_snapshot_fingerprint:
            return False, "MISSING_FINGERPRINT: Feature snapshot fingerprint is absent."

        if not inp.history_fingerprint:
            return False, "MISSING_FINGERPRINT: History fingerprint is absent."

        return True, None
