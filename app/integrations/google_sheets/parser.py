"""Parser and normalizer for raw Google Sheets company rows."""

import re
from typing import Any, Optional
from urllib.parse import urlparse

from app.config.settings import Settings, get_settings
from app.integrations.google_sheets.schemas import ParsedCompanyRow, RowValidationError


class SheetRowParser:
    """Parses, normalizes, and validates company row dictionaries from Google Sheets."""

    # Common column alias candidates for flexible header matching
    NAME_ALIASES = ("company name", "company", "name", "organization", "company_name")
    WEBSITE_ALIASES = ("website", "website url", "url", "domain", "web", "website_url", "link")
    STATUS_ALIASES = ("status", "processing status", "state", "processing_status")

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def _find_column_value(
        self,
        row_dict: dict[str, Any],
        primary_col: str,
        aliases: tuple[str, ...],
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Locate column value by primary name or fallback aliases (case-insensitive & trimmed).
        Returns tuple of (matched_value, matched_key).
        """
        # 1. Exact match on configured primary column name
        if primary_col in row_dict:
            val = row_dict[primary_col]
            if val is not None:
                return str(val).strip(), primary_col

        # 2. Case-insensitive match on primary column
        clean_primary = primary_col.strip().lower()
        for key, val in row_dict.items():
            if str(key).strip().lower() == clean_primary:
                if val is not None:
                    return str(val).strip(), key

        # 3. Fallback to alias candidates
        for alias in aliases:
            clean_alias = alias.strip().lower()
            for key, val in row_dict.items():
                if str(key).strip().lower() == clean_alias:
                    if val is not None:
                        return str(val).strip(), key

        return None, None

    @staticmethod
    def normalize_url(raw_url: str) -> tuple[str, Optional[str]]:
        """
        Normalize website URL and extract canonical domain.
        Example: '  example.com/path/ ' -> ('https://example.com/path', 'example.com')
        """
        cleaned = raw_url.strip()
        if not cleaned:
            return "", None

        # Add https scheme if missing
        if not re.match(r"^https?://", cleaned, re.IGNORECASE):
            cleaned = f"https://{cleaned}"

        # Clean trailing slash for consistency
        cleaned = cleaned.rstrip("/")

        # Parse domain
        try:
            parsed = urlparse(cleaned)
            hostname = parsed.hostname or ""
            # Strip leading 'www.' from domain
            domain = hostname.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return cleaned, domain if domain else None
        except Exception:
            return cleaned, None

    def parse_row(
        self,
        row_dict: dict[str, Any],
        row_index: int,
    ) -> tuple[Optional[ParsedCompanyRow], Optional[RowValidationError]]:
        """
        Parse a single row dictionary into a ParsedCompanyRow.
        Returns:
            - (ParsedCompanyRow, None) on success
            - (None, RowValidationError) if required fields are missing/malformed
            - (None, None) if the row is entirely empty (ignored blank row)
        """
        # Check if row is completely empty
        non_empty_values = [
            str(v).strip() for v in row_dict.values() if v is not None and str(v).strip()
        ]
        if not non_empty_values:
            return None, None

        # Extract Company Name
        name_val, name_key = self._find_column_value(
            row_dict,
            self.settings.google_sheets_company_name_col,
            self.NAME_ALIASES,
        )

        if not name_val:
            return None, RowValidationError(
                row_index=row_index,
                field="name",
                message="Missing required company name in row",
                raw_values=row_dict,
            )

        # Extract Website URL
        website_val, website_key = self._find_column_value(
            row_dict,
            self.settings.google_sheets_website_col,
            self.WEBSITE_ALIASES,
        )

        if not website_val:
            return None, RowValidationError(
                row_index=row_index,
                field="website",
                message="Missing required website URL in row",
                raw_values=row_dict,
            )

        # Extract Status
        status_val, status_key = self._find_column_value(
            row_dict,
            self.settings.google_sheets_status_col,
            self.STATUS_ALIASES,
        )

        # Normalize URL and extract domain
        normalized_url, domain = self.normalize_url(website_val)

        # Collect unmapped extra columns
        matched_keys = {k for k in (name_key, website_key, status_key) if k is not None}
        extra_data = {k: v for k, v in row_dict.items() if k not in matched_keys}

        parsed = ParsedCompanyRow(
            sheet_row_id=f"row_{row_index}",
            row_index=row_index,
            name=name_val,
            website_url=normalized_url,
            domain=domain,
            status_raw=status_val,
            extra_data=extra_data,
        )
        return parsed, None
