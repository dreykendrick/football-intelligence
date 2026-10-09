from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base as ModelsBase
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-wide database engine fixture for testing.
    Attempts connection to PostgreSQL; if unreachable, falls back to SQLite in-memory for offline unit test execution.
    """
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        yield engine
        engine.dispose()
    except Exception:
        # Fallback to SQLite in-memory for local unit testing when local PostgreSQL is not running
        fallback_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False}
        )
        ModelsBase.metadata.create_all(bind=fallback_engine)
        yield fallback_engine
        fallback_engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Function-scoped database session fixture.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient fixture with overridden database session dependency.
    """
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
