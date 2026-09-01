"""Tests for Google Sheets parsing, normalization, client error handling, and ingestion service."""

from typing import Any
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, SyncDirection, SyncStatus
from app.database.models import Company, SyncLog
from app.integrations.google_sheets.client import (
    GoogleSheetsAuthError,
    GoogleSheetsClient,
    GoogleSheetsError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from app.integrations.google_sheets.parser import SheetRowParser
from app.integrations.google_sheets.schemas import IngestionResult
from app.integrations.google_sheets.service import CompanyIngestionService


class FakeGoogleSheetsClient:
    """Mock Google Sheets client returning predefined in-memory row data."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        error_to_raise: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.error_to_raise = error_to_raise

    def get_rows_with_indices(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> list[tuple[int, dict[str, Any]]]:
        if self.error_to_raise:
            raise self.error_to_raise
        # 1-based indexing where Row 1 is header, data rows start at 2
        return [(idx + 2, row) for idx, row in enumerate(self.rows)]


# ==============================================================================
# 1. SheetRowParser Unit Tests
# ==============================================================================

def test_parser_valid_standard_row() -> None:
    """Test parsing a well-formed row with standard column headers."""
    parser = SheetRowParser()
    raw_row = {
        "Company Name": "Stripe Inc",
        "Website": "https://stripe.com",
        "Status": "PENDING",
    }
    parsed, err = parser.parse_row(raw_row, row_index=2)

    assert err is None
    assert parsed is not None
    assert parsed.name == "Stripe Inc"
    assert parsed.website_url == "https://stripe.com"
    assert parsed.domain == "stripe.com"
    assert parsed.sheet_row_id == "row_2"
    assert parsed.status_raw == "PENDING"


def test_parser_whitespace_trimming_and_url_normalization() -> None:
    """Test trimming whitespace and prepending https:// scheme."""
    parser = SheetRowParser()
    raw_row = {
        "Company Name": "   Vercel Labs   ",
        "Website": "   www.vercel.com/enterprise/   ",
    }
    parsed, err = parser.parse_row(raw_row, row_index=3)

    assert err is None
    assert parsed is not None
    assert parsed.name == "Vercel Labs"
    assert parsed.website_url == "https://www.vercel.com/enterprise"
    assert parsed.domain == "vercel.com"
    assert parsed.sheet_row_id == "row_3"


def test_parser_case_insensitive_and_alias_headers() -> None:
    """Test resolving alias headers like 'company', 'url', and 'state'."""
    parser = SheetRowParser()
    raw_row = {
        "company": "Supabase",
        "url": "supabase.com",
        "state": "NEW",
        "Notes": "Open-source Firebase alternative",
    }
    parsed, err = parser.parse_row(raw_row, row_index=4)

    assert err is None
    assert parsed is not None
    assert parsed.name == "Supabase"
    assert parsed.website_url == "https://supabase.com"
    assert parsed.domain == "supabase.com"
    assert parsed.extra_data == {"Notes": "Open-source Firebase alternative"}


def test_parser_missing_required_company_name() -> None:
    """Test that missing or empty company name returns a validation error."""
    parser = SheetRowParser()
    raw_row = {
        "Company Name": "   ",
        "Website": "https://noname.com",
    }
    parsed, err = parser.parse_row(raw_row, row_index=5)

    assert parsed is None
    assert err is not None
    assert err.row_index == 5
    assert err.field == "name"
    assert "Missing required company name" in err.message


def test_parser_missing_required_website() -> None:
    """Test that missing or empty website URL returns a validation error."""
    parser = SheetRowParser()
    raw_row = {
        "Company Name": "No Website Co",
        "Website": "",
    }
    parsed, err = parser.parse_row(raw_row, row_index=6)

    assert parsed is None
    assert err is not None
    assert err.row_index == 6
    assert err.field == "website"
    assert "Missing required website URL" in err.message


def test_parser_empty_row_skipped() -> None:
    """Test that an entirely blank row is ignored without raising an error."""
    parser = SheetRowParser()
    raw_row = {
        "Company Name": "",
        "Website": "",
        "Status": "",
    }
    parsed, err = parser.parse_row(raw_row, row_index=7)

    assert parsed is None
    assert err is None


# ==============================================================================
# 2. CompanyIngestionService Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_ingestion_service_batch_success(db_session: AsyncSession) -> None:
    """Test successfully ingesting multiple valid company rows."""
    fake_rows = [
        {"Company Name": "OpenAI", "Website": "https://openai.com"},
        {"Company Name": "Anthropic", "Website": "https://anthropic.com"},
        {"Company Name": "Mistral AI", "Website": "https://mistral.ai"},
    ]
    fake_client = FakeGoogleSheetsClient(rows=fake_rows)
    service = CompanyIngestionService(session=db_session, client=fake_client)

    result = await service.ingest_companies(
        spreadsheet_id="test-sheet-id",
        worksheet_name="Companies",
    )

    assert result.rows_read == 3
    assert result.companies_created == 3
    assert result.companies_updated == 0
    assert result.rows_skipped == 0
    assert len(result.validation_errors) == 0
    assert len(result.errors) == 0

    # Verify records in database
    companies = (await db_session.execute(select(Company))).scalars().all()
    assert len(companies) == 3
    assert {c.name for c in companies} == {"OpenAI", "Anthropic", "Mistral AI"}
    assert {c.status for c in companies} == {CompanyStatus.PENDING}
    assert {c.sheet_row_id for c in companies} == {"row_2", "row_3", "row_4"}

    # Verify sync logs
    sync_logs = (await db_session.execute(select(SyncLog))).scalars().all()
    assert len(sync_logs) == 3
    assert all(l.sync_direction == SyncDirection.SHEET_TO_DB for l in sync_logs)
    assert all(l.status == SyncStatus.SUCCESS for l in sync_logs)


@pytest.mark.asyncio
async def test_ingestion_service_idempotency_and_update(db_session: AsyncSession) -> None:
    """Test that running ingestion twice updates existing rows without creating duplicates or changing IDs."""
    initial_rows = [
        {"Company Name": "Datadog", "Website": "https://datadoghq.com"},
    ]
    fake_client = FakeGoogleSheetsClient(rows=initial_rows)
    service = CompanyIngestionService(session=db_session, client=fake_client)

    # First Run
    result1 = await service.ingest_companies(spreadsheet_id="test-sheet-id")
    assert result1.companies_created == 1
    assert result1.companies_updated == 0

    first_company = (await db_session.execute(select(Company).where(Company.sheet_row_id == "row_2"))).scalar_one()
    original_id = first_company.id

    # Second Run with updated name
    updated_rows = [
        {"Company Name": "Datadog Inc.", "Website": "https://datadoghq.com/updated"},
    ]
    fake_client.rows = updated_rows

    result2 = await service.ingest_companies(spreadsheet_id="test-sheet-id")
    assert result2.companies_created == 0
    assert result2.companies_updated == 1
    assert result2.rows_read == 1

    second_company = (await db_session.execute(select(Company).where(Company.sheet_row_id == "row_2"))).scalar_one()
    assert second_company.id == original_id  # Database identity preserved
    assert second_company.name == "Datadog Inc."
    assert second_company.website_url == "https://datadoghq.com/updated"

    # Total company count remains 1
    total_count = len((await db_session.execute(select(Company))).scalars().all())
    assert total_count == 1


@pytest.mark.asyncio
async def test_ingestion_service_handles_malformed_and_blank_rows(db_session: AsyncSession) -> None:
    """Test that a malformed row or empty row does not halt processing of other valid rows."""
    mixed_rows = [
        {"Company Name": "Valid Company 1", "Website": "https://valid1.com"},
        {"Company Name": "", "Website": "https://missingname.com"},  # Invalid: no name
        {"Company Name": "", "Website": ""},  # Blank: skipped silently
        {"Company Name": "Valid Company 2", "Website": "https://valid2.com"},
    ]
    fake_client = FakeGoogleSheetsClient(rows=mixed_rows)
    service = CompanyIngestionService(session=db_session, client=fake_client)

    result = await service.ingest_companies(spreadsheet_id="test-sheet-id")

    assert result.rows_read == 4
    assert result.companies_created == 2
    assert result.rows_skipped == 2  # 1 invalid + 1 blank
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].row_index == 3
    assert result.validation_errors[0].field == "name"

    # Database contains exactly the 2 valid companies
    companies = (await db_session.execute(select(Company))).scalars().all()
    assert len(companies) == 2
    assert {c.name for c in companies} == {"Valid Company 1", "Valid Company 2"}


@pytest.mark.asyncio
async def test_ingestion_service_api_errors_handled_gracefully(db_session: AsyncSession) -> None:
    """Test that Google API errors (e.g. spreadsheet not found) are captured without crashing."""
    fake_client = FakeGoogleSheetsClient(
        error_to_raise=SpreadsheetNotFoundError("Spreadsheet 'invalid-id' not found")
    )
    service = CompanyIngestionService(session=db_session, client=fake_client)

    result = await service.ingest_companies(spreadsheet_id="invalid-id")

    assert result.rows_read == 0
    assert result.companies_created == 0
    assert len(result.errors) == 1
    assert "Spreadsheet 'invalid-id' not found" in result.errors[0]


@pytest.mark.asyncio
async def test_ingestion_service_missing_spreadsheet_id(db_session: AsyncSession) -> None:
    """Test that calling ingestion without a spreadsheet ID logs an error and returns gracefully."""
    fake_client = FakeGoogleSheetsClient(rows=[])
    service = CompanyIngestionService(session=db_session, client=fake_client)

    result = await service.ingest_companies(spreadsheet_id="")

    assert result.rows_read == 0
    assert result.companies_created == 0
    assert len(result.errors) == 1
    assert "Missing Google Sheets spreadsheet ID" in result.errors[0]


# ==============================================================================
# 3. Client Authentication Unit Tests
# ==============================================================================

def test_google_sheets_client_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that GoogleSheetsClient raises GoogleSheetsAuthError when no credentials are configured."""
    from app.config.settings import Settings
    import google.auth

    # Mock google.auth.default to raise DefaultCredentialsError so ADC doesn't pick up local machine creds
    def mock_default(*args, **kwargs):
        raise google.auth.exceptions.DefaultCredentialsError("No ADC configured")

    monkeypatch.setattr(google.auth, "default", mock_default)

    empty_settings = Settings(
        GOOGLE_SERVICE_ACCOUNT_INFO=None,
        GOOGLE_SERVICE_ACCOUNT_FILE=None,
    )
    client = GoogleSheetsClient(settings=empty_settings)

    with pytest.raises(GoogleSheetsAuthError) as exc_info:
        client._authenticate()

    assert "No Google credentials provided" in str(exc_info.value)


def test_google_sheets_client_authorized_user_oauth2_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that GoogleSheetsClient can authenticate using OAuth2 authorized user JSON."""
    import json
    import gspread
    from app.config.settings import Settings

    authorized_user_dict = {
        "type": "authorized_user",
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
    }

    class FakeGspreadClient:
        pass

    monkeypatch.setattr(gspread, "authorize", lambda creds: FakeGspreadClient())

    settings = Settings(
        GOOGLE_SERVICE_ACCOUNT_INFO=json.dumps(authorized_user_dict),
    )
    client = GoogleSheetsClient(settings=settings)
    authed_client = client._authenticate()
    assert isinstance(authed_client, FakeGspreadClient)

