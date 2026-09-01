"""Tests for application settings and configuration loading."""

from app.config.settings import Settings


def test_default_settings_instantiation() -> None:
    """Test that Settings can be instantiated with defaults."""
    settings = Settings()
    assert settings.app_name == "Company Intelligence Agent"
    assert settings.port == 8000
    assert settings.log_level in ("INFO", "DEBUG", "WARNING", "ERROR")
    assert len(settings.database_url) > 0


def test_settings_custom_values() -> None:
    """Test that Settings accepts custom field overrides."""
    custom = Settings(
        APP_NAME="Custom Agent",
        PORT=9000,
        LOG_LEVEL="DEBUG",
        DATABASE_URL="postgresql+asyncpg://user:pass@customhost:5432/custom_db",
    )
    assert custom.app_name == "Custom Agent"
    assert custom.port == 9000
    assert custom.log_level == "DEBUG"
    assert custom.database_url == "postgresql+asyncpg://user:pass@customhost:5432/custom_db"
