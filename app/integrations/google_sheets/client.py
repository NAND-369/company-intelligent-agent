"""Google Sheets API client and authentication provider with reading and writing capabilities."""

import json
import logging
import time
from typing import Any, Optional, Protocol
import gspread
from google.oauth2.service_account import Credentials

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class GoogleSheetsError(Exception):
    """Base exception for Google Sheets integration failures."""

    pass


class GoogleSheetsAuthError(GoogleSheetsError):
    """Raised when Google Service Account credentials cannot be loaded or authenticated."""

    pass


class SpreadsheetNotFoundError(GoogleSheetsError):
    """Raised when the specified Google Spreadsheet ID is not found or inaccessible."""

    pass


class WorksheetNotFoundError(GoogleSheetsError):
    """Raised when the specified worksheet/tab does not exist in the spreadsheet."""

    pass


class GoogleSheetsAPIError(GoogleSheetsError):
    """Raised for runtime Google Sheets API communication or quota errors."""

    pass


class GoogleSheetsClientProtocol(Protocol):
    """Interface protocol for Google Sheets client implementations."""

    def get_rows_with_indices(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> list[tuple[int, dict[str, Any]]]:
        """
        Fetch all data rows with their 1-based spreadsheet row indices.
        Returns a list of (row_index, row_dict).
        """
        ...

    def get_header_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> list[str]:
        """Fetch the header row (row 1) column names."""
        ...

    def update_row_cells(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        row_index: int,
        updates_by_col_index: dict[int, Any],
    ) -> bool:
        """Update specific cells in a row by 1-based column indices."""
        ...


class GoogleSheetsClient:
    """Production Google Sheets API client using Service Account credentials with retry capability."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._client: Optional[gspread.Client] = None

    def _authenticate(self) -> gspread.Client:
        """Create and authenticate a gspread Client using environment credentials."""
        if self._client is not None:
            return self._client

        try:
            # Option A: In-memory JSON string (ideal for container/cloud secrets)
            if self.settings.google_service_account_info:
                info_dict = json.loads(self.settings.google_service_account_info)
                credentials = Credentials.from_service_account_info(
                    info_dict, scopes=self.SCOPES
                )
                self._client = gspread.authorize(credentials)
                return self._client

            # Option B: File path to service account key
            if self.settings.google_service_account_file:
                credentials = Credentials.from_service_account_file(
                    self.settings.google_service_account_file, scopes=self.SCOPES
                )
                self._client = gspread.authorize(credentials)
                return self._client

            raise GoogleSheetsAuthError(
                "No Google credentials provided. Set GOOGLE_SERVICE_ACCOUNT_INFO "
                "or GOOGLE_SERVICE_ACCOUNT_FILE."
            )
        except GoogleSheetsAuthError:
            raise
        except Exception as exc:
            raise GoogleSheetsAuthError(
                f"Failed to authenticate with Google Sheets API: {exc!s}"
            ) from exc

    def _get_worksheet(self, spreadsheet_id: str, worksheet_name: str) -> gspread.Worksheet:
        """Retrieve target worksheet object with error translation."""
        client = self._authenticate()
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except gspread.SpreadsheetNotFound as exc:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet '{spreadsheet_id}' not found or access denied."
            ) from exc
        except Exception as exc:
            raise GoogleSheetsAPIError(f"Error opening spreadsheet: {exc!s}") from exc

        try:
            return spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound as exc:
            raise WorksheetNotFoundError(
                f"Worksheet '{worksheet_name}' not found in spreadsheet '{spreadsheet_id}'."
            ) from exc
        except Exception as exc:
            raise GoogleSheetsAPIError(f"Error opening worksheet: {exc!s}") from exc

    def _execute_with_retry(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a Google API call with exponential backoff on transient errors."""
        max_retries = self.settings.sync_max_retries
        backoff = self.settings.sync_retry_backoff_seconds

        for attempt in range(max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError):
                # Permanent structural errors should not be retried
                raise
            except Exception as exc:
                err_str = str(exc).lower()
                is_transient = any(code in err_str for code in ["429", "500", "502", "503", "504", "quota", "rate limit", "temporarily unavailable"])
                if attempt < max_retries and is_transient:
                    sleep_time = backoff * (2 ** attempt)
                    logger.warning(
                        "Google Sheets API transient error (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        max_retries,
                        exc,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                else:
                    raise GoogleSheetsAPIError(f"Google Sheets API call failed after retries: {exc!s}") from exc

    def get_header_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> list[str]:
        """Fetch the header row (row 1) column names."""
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        return self._execute_with_retry(worksheet.row_values, 1)

    def get_rows_with_indices(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> list[tuple[int, dict[str, Any]]]:
        """
        Fetch all records from the target worksheet alongside their exact spreadsheet row numbers.
        Returns a list of (row_number, record_dict), where row_number starts at 2 (row 1 is header).
        """
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        try:
            records = self._execute_with_retry(worksheet.get_all_records)
            return [(idx + 2, record) for idx, record in enumerate(records)]
        except Exception as exc:
            if isinstance(exc, (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError, GoogleSheetsAPIError)):
                raise
            raise GoogleSheetsAPIError(f"Error reading records from worksheet: {exc!s}") from exc

    def update_row_cells(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        row_index: int,
        updates_by_col_index: dict[int, Any],
    ) -> bool:
        """
        Update specific cells in a row by 1-based column indices.
        Only modifies the target cells without affecting other columns.
        """
        if not updates_by_col_index:
            return True

        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        cells_to_update = [
            gspread.Cell(row=row_index, col=col_idx, value=str(val) if val is not None else "")
            for col_idx, val in updates_by_col_index.items()
        ]

        try:
            self._execute_with_retry(worksheet.update_cells, cells_to_update)
            return True
        except Exception as exc:
            if isinstance(exc, (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError, GoogleSheetsAPIError)):
                raise
            raise GoogleSheetsAPIError(f"Error updating cells at row {row_index}: {exc!s}") from exc
