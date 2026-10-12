import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_database_connection_query(db_session: Session):
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1


@pytest.mark.integration
def test_ci_integration_database_is_postgresql(db_session: Session):
    """
    In CI / PostgreSQL integration testing, dialect must strictly be postgresql.
    When RUNNING_IN_CI=true, falling back to sqlite is a certification failure.
    """
    import os
    dialect_name = db_session.bind.dialect.name
    if os.environ.get("RUNNING_IN_CI") == "true":
        assert dialect_name == "postgresql", f"Expected PostgreSQL in CI, got dialect: {dialect_name}"
    else:
        assert dialect_name in ("postgresql", "sqlite")

