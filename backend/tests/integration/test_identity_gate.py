"""
Integration Tests for Identity Readiness Gate & Verifier
Verifies IdentityReadinessGate assertion behavior under clean vs conflicting database states.
"""
import pytest
from sqlalchemy.orm import Session

from app.db.models import Team
from app.identity.gate import IdentityReadinessGate, IdentityReadinessGateException


@pytest.mark.integration
def test_identity_gate_passes_on_clean_database(db_session: Session):
    t1 = Team(canonical_name="Manchester United", country="England")
    t2 = Team(canonical_name="Arsenal", country="England")
    db_session.add_all([t1, t2])
    db_session.flush()

    audit = IdentityReadinessGate.assert_identity_ready(db_session)
    assert audit.canonical_teams_count == 2
    assert audit.exact_duplicate_names_count == 0


@pytest.mark.integration
def test_identity_gate_fails_on_duplicate_canonical_names(db_session: Session):
    t1 = Team(canonical_name="Manchester United", country="England")
    # Duplicate canonical name with different casing
    t2 = Team(canonical_name="MANCHESTER UNITED", country="England")
    db_session.add_all([t1, t2])
    db_session.flush()

    with pytest.raises(IdentityReadinessGateException, match="Identity Readiness Gate FAILED!"):
        IdentityReadinessGate.assert_identity_ready(db_session)
