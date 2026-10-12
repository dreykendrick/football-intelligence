import pytest

from app.core.config import Settings, get_settings


@pytest.mark.unit
def test_settings_initialization():
    settings = get_settings()
    assert settings.APP_NAME == "football-intelligence-system"
    assert settings.POSTGRES_PORT == 5432
    assert "postgresql" in settings.database_url


@pytest.mark.unit
def test_database_url_override():
    custom_settings = Settings(DATABASE_URL_OVERRIDE="postgresql://user:pass@localhost:5432/custom_db")
    assert custom_settings.database_url == "postgresql://user:pass@localhost:5432/custom_db"
