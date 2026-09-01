"""Tests for application settings and configuration loading."""

from app.config.settings import Settings


def test_default_settings_instantiation() -> None:
    """Test that Settings can be instantiated with defaults."""
    settings = Settings()
    assert settings.app_name == "Company Intelligence Agent"
    assert settings.port == 8000
    assert settings.log_level in ("INFO", "DEBUG", "WARNING", "ERROR")
    assert len(settings.database_url) > 0
    assert settings.llm_model == "gemini-3.1-flash-lite"
    assert settings.llm_provider == "gemini"


def test_settings_custom_values() -> None:
    """Test that Settings accepts custom field overrides."""
    custom = Settings(
        APP_NAME="Custom Agent",
        PORT=9000,
        LOG_LEVEL="DEBUG",
        DATABASE_URL="postgresql+asyncpg://user:pass@customhost:5432/custom_db",
        LLM_MODEL="gemini-3.1-flash-lite",
    )
    assert custom.app_name == "Custom Agent"
    assert custom.port == 9000
    assert custom.log_level == "DEBUG"
    assert custom.database_url == "postgresql+asyncpg://user:pass@customhost:5432/custom_db"
    assert custom.llm_model == "gemini-3.1-flash-lite"


def test_gemini_llm_client_model_url_construction() -> None:
    """Test that GeminiLLMClient formats the endpoint URL cleanly with and without models/ prefix."""
    from app.llm.client import GeminiLLMClient

    client1 = GeminiLLMClient(api_key="test-key", model="gemini-3.1-flash-lite")
    assert client1.base_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"

    client2 = GeminiLLMClient(api_key="test-key", model="models/gemini-3.1-flash-lite")
    assert client2.base_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"


def test_llm_model_env_var_override(monkeypatch) -> None:
    """Test that LLM_MODEL environment variable dynamically overrides the default model."""
    monkeypatch.setenv("LLM_MODEL", "custom-override-model")
    settings = Settings()
    assert settings.llm_model == "custom-override-model"
