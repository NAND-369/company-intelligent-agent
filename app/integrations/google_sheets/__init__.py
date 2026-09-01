"""Google Sheets integration package."""

from app.integrations.google_sheets.client import (
    GoogleSheetsAuthError,
    GoogleSheetsClient,
    GoogleSheetsClientProtocol,
    GoogleSheetsError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from app.integrations.google_sheets.parser import SheetRowParser
from app.integrations.google_sheets.schemas import (
    IngestionResult,
    ParsedCompanyRow,
    RowValidationError,
)
from app.integrations.google_sheets.service import CompanyIngestionService

__all__ = [
    "CompanyIngestionService",
    "GoogleSheetsAuthError",
    "GoogleSheetsClient",
    "GoogleSheetsClientProtocol",
    "GoogleSheetsError",
    "IngestionResult",
    "ParsedCompanyRow",
    "RowValidationError",
    "SheetRowParser",
    "SpreadsheetNotFoundError",
    "WorksheetNotFoundError",
]
