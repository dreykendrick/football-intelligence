import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_database_connection_query(db_session: Session):
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
