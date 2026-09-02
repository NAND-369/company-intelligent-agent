import json
import logging
import time
from typing import Any, Optional, Protocol
import google.auth
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
import gspread

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class GoogleSheetsError(Exception):
    """Base exception for Google Sheets integration failures."""

    pass


class GoogleSheetsAuthError(GoogleSheetsError):
    """Raised when Google Service Account or OAuth credentials cannot be loaded or authenticated."""

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

    def find_company_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        company_name: str,
        website_url: Optional[str] = None,
    ) -> Optional[int]:
        """Find 1-based row index for a company by name or website/domain."""
        ...

    def append_row_values(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        updates_by_col_index: dict[int, Any],
    ) -> int:
        """Append a new row and return its 1-based row index."""
        ...

    def ensure_header_columns(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        required_headers: list[str],
    ) -> list[str]:
        """Ensure required column headers exist in row 1, appending any missing ones."""
        ...


class GoogleSheetsClient:
    """Production Google Sheets API client supporting Service Accounts, OAuth2 User Tokens, and ADC with retry capability."""

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
            # Option A: In-memory JSON string (Service Account or Authorized User OAuth2 JSON)
            if self.settings.google_service_account_info:
                info_dict = json.loads(self.settings.google_service_account_info)
                if info_dict.get("type") == "authorized_user" or "refresh_token" in info_dict:
                    credentials = UserCredentials.from_authorized_user_info(
                        info_dict, scopes=self.SCOPES
                    )
                else:
                    credentials = ServiceAccountCredentials.from_service_account_info(
                        info_dict, scopes=self.SCOPES
                    )
                self._client = gspread.authorize(credentials)
                return self._client

            # Option B: File path to credentials file
            if self.settings.google_service_account_file:
                try:
                    credentials = ServiceAccountCredentials.from_service_account_file(
                        self.settings.google_service_account_file, scopes=self.SCOPES
                    )
                except Exception:
                    credentials = UserCredentials.from_authorized_user_file(
                        self.settings.google_service_account_file, scopes=self.SCOPES
                    )
                self._client = gspread.authorize(credentials)
                return self._client

            # Option C: Google Application Default Credentials (ADC fallback)
            try:
                credentials, _ = google.auth.default(scopes=self.SCOPES)
                self._client = gspread.authorize(credentials)
                return self._client
            except Exception:
                pass

            raise GoogleSheetsAuthError(
                "No Google credentials provided. Set GOOGLE_SERVICE_ACCOUNT_INFO, "
                "GOOGLE_SERVICE_ACCOUNT_FILE, or configure Application Default Credentials."
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

    def find_company_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        company_name: str,
        website_url: Optional[str] = None,
    ) -> Optional[int]:
        """
        Search for an existing company row in the worksheet by name or normalized website domain.
        Returns 1-based row number if found, or None if not found.
        """
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        try:
            all_values = self._execute_with_retry(worksheet.get_all_values)
            if not all_values or len(all_values) <= 1:
                return None

            header = [str(h).strip().lower() for h in all_values[0]]
            name_col_idx = None
            web_col_idx = None

            for idx, h in enumerate(header):
                if h in ("company name", "company", "name", "organization", "company_name"):
                    name_col_idx = idx
                elif h in ("website", "website url", "url", "domain", "web", "website_url", "link"):
                    web_col_idx = idx

            target_name = company_name.strip().lower()
            target_domain = None
            if website_url:
                from app.integrations.google_sheets.parser import SheetRowParser
                _, target_domain = SheetRowParser.normalize_url(website_url)

            for row_idx, row_vals in enumerate(all_values[1:], start=2):
                if name_col_idx is not None and name_col_idx < len(row_vals):
                    row_name = str(row_vals[name_col_idx]).strip().lower()
                    if row_name and (row_name == target_name or target_name in row_name or row_name in target_name):
                        return row_idx

                if web_col_idx is not None and web_col_idx < len(row_vals) and target_domain:
                    from app.integrations.google_sheets.parser import SheetRowParser
                    _, row_domain = SheetRowParser.normalize_url(str(row_vals[web_col_idx]))
                    if row_domain and row_domain == target_domain:
                        return row_idx

            return None
        except Exception as exc:
            if isinstance(exc, (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError, GoogleSheetsAPIError)):
                raise
            raise GoogleSheetsAPIError(f"Error finding company row in worksheet: {exc!s}") from exc

    def append_row_values(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        updates_by_col_index: dict[int, Any],
    ) -> int:
        """
        Append a new row to the worksheet with the provided 1-based column updates.
        Returns the 1-based row number of the newly appended row.
        """
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        try:
            all_values = self._execute_with_retry(worksheet.get_all_values)
            new_row_idx = max(len(all_values) + 1, 2)
            cells_to_update = [
                gspread.Cell(row=new_row_idx, col=col_idx, value=str(val) if val is not None else "")
                for col_idx, val in updates_by_col_index.items()
            ]
            self._execute_with_retry(worksheet.update_cells, cells_to_update)
            return new_row_idx
        except Exception as exc:
            if isinstance(exc, (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError, GoogleSheetsAPIError)):
                raise
            raise GoogleSheetsAPIError(f"Error appending row to worksheet: {exc!s}") from exc

    def ensure_header_columns(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        required_headers: list[str],
    ) -> list[str]:
        """
        Ensure required header columns exist in row 1. Appends any missing headers.
        Returns the complete updated list of headers.
        """
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_name)
        try:
            headers = self._execute_with_retry(worksheet.row_values, 1) or []
            normalized_existing = ["".join(c for c in h.lower() if c.isalnum()) for h in headers]

            missing_headers: list[tuple[int, str]] = []
            current_col = len(headers) + 1

            for req in required_headers:
                norm_req = "".join(c for c in req.lower() if c.isalnum())
                if norm_req not in normalized_existing:
                    missing_headers.append((current_col, req))
                    normalized_existing.append(norm_req)
                    headers.append(req)
                    current_col += 1

            if missing_headers:
                cells_to_add = [
                    gspread.Cell(row=1, col=col_idx, value=title)
                    for col_idx, title in missing_headers
                ]
                self._execute_with_retry(worksheet.update_cells, cells_to_add)

            return headers
        except Exception as exc:
            if isinstance(exc, (SpreadsheetNotFoundError, WorksheetNotFoundError, GoogleSheetsAuthError, GoogleSheetsAPIError)):
                raise
            raise GoogleSheetsAPIError(f"Error ensuring header columns: {exc!s}") from exc
