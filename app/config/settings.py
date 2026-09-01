"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application Settings
    app_name: str = Field(default="Company Intelligence Agent", alias="APP_NAME")
    app_env: Literal["development", "testing", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # API Security
    api_key: str = Field(default="dev-insecure-key", alias="API_KEY")

    # Database Configuration (PostgreSQL)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/company_agent_db",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW")
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    # Google Sheets Ingestion & Sync Configuration
    google_sheets_spreadsheet_id: str = Field(default="", alias="GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_worksheet_name: str = Field(default="Companies", alias="GOOGLE_SHEETS_WORKSHEET_NAME")
    google_service_account_info: Optional[str] = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_INFO")
    google_service_account_file: Optional[str] = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_sheets_company_name_col: str = Field(default="Company Name", alias="GOOGLE_SHEETS_COMPANY_NAME_COL")
    google_sheets_website_col: str = Field(default="Website", alias="GOOGLE_SHEETS_WEBSITE_COL")
    google_sheets_status_col: str = Field(default="Status", alias="GOOGLE_SHEETS_STATUS_COL")
    google_sheets_fit_col: str = Field(default="Fit", alias="GOOGLE_SHEETS_FIT_COL")
    google_sheets_confidence_col: str = Field(default="Confidence", alias="GOOGLE_SHEETS_CONFIDENCE_COL")
    google_sheets_reasoning_col: str = Field(default="Reasoning", alias="GOOGLE_SHEETS_REASONING_COL")
    google_sheets_follow_up_col: str = Field(default="Follow-up Question", alias="GOOGLE_SHEETS_FOLLOW_UP_COL")
    google_sheets_last_synced_col: str = Field(default="Last Synced", alias="GOOGLE_SHEETS_LAST_SYNCED_COL")
    sync_max_retries: int = Field(default=3, alias="SYNC_MAX_RETRIES")
    sync_retry_backoff_seconds: float = Field(default=1.0, alias="SYNC_RETRY_BACKOFF_SECONDS")

    # LLM Judge Configuration
    llm_provider: Literal["gemini", "groq", "openai", "fake"] = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gemini-3.6-flash", alias="LLM_MODEL")
    rubric_path: str = Field(default="config/rubric.yaml", alias="RUBRIC_PATH")
    llm_timeout_seconds: float = Field(default=30.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")

    # Pipeline Orchestration Configuration
    pipeline_max_concurrency: int = Field(default=3, alias="PIPELINE_MAX_CONCURRENCY")
    pipeline_lease_duration_minutes: int = Field(default=5, alias="PIPELINE_LEASE_DURATION_MINUTES")
    pipeline_enable_browser: bool = Field(default=True, alias="PIPELINE_ENABLE_BROWSER")

    # In-Process Scheduler Configuration
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    scheduler_interval_minutes: int = Field(default=360, alias="SCHEDULER_INTERVAL_MINUTES")


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()
