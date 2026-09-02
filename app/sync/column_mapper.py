"""Flexible column mapper translating structured Verdict models into Google Sheets cell updates."""

import hashlib
import json
import logging
from typing import Any, Optional
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.database.models import Company, Verdict

logger = logging.getLogger(__name__)


def _normalize_header(header: str) -> str:
    """Normalize a header string for case-insensitive, punctuation-resilient matching."""
    return "".join(c for c in header.lower() if c.isalnum())


class SheetColumnMapper:
    """Discovers and maps Google Sheet column header indices to Verdict attributes."""

    def __init__(self, headers: list[str], settings: Optional[Settings] = None) -> None:
        self.headers = headers
        self.settings = settings or get_settings()
        self.normalized_headers = [_normalize_header(h) for h in headers]
        self._col_indices: dict[str, int] = self._resolve_column_indices()

    def _find_column_index(self, configured_name: str, aliases: list[str]) -> Optional[int]:
        """Find 1-based column index matching configured name or aliases."""
        search_targets = [_normalize_header(configured_name)] + [_normalize_header(a) for a in aliases]
        for target in search_targets:
            for idx, norm_header in enumerate(self.normalized_headers):
                if norm_header == target:
                    return idx + 1  # 1-based column index for Sheets
        return None

    def _resolve_column_indices(self) -> dict[str, int]:
        """Resolve 1-based column index mapping for all supported output fields."""
        mapping: dict[str, int] = {}

        # 0. Identifying Columns
        idx = self._find_column_index(
            self.settings.google_sheets_company_name_col,
            ["company name", "company", "name", "organization", "company_name"],
        )
        if idx:
            mapping["name"] = idx

        idx = self._find_column_index(
            self.settings.google_sheets_website_col,
            ["website", "website url", "url", "domain", "web", "website_url", "link"],
        )
        if idx:
            mapping["website"] = idx

        # 1. Status Column
        idx = self._find_column_index(
            self.settings.google_sheets_status_col,
            ["status", "company_status", "processing_status", "state"],
        )
        if idx:
            mapping["status"] = idx

        # 2. Fit Column
        idx = self._find_column_index(
            self.settings.google_sheets_fit_col,
            ["fit", "fit_call", "recommendation", "verdict", "decision"],
        )
        if idx:
            mapping["fit"] = idx

        # 3. Confidence Column
        idx = self._find_column_index(
            self.settings.google_sheets_confidence_col,
            ["confidence", "confidence_score", "score", "conf"],
        )
        if idx:
            mapping["confidence"] = idx

        # 4. Reasoning Column
        idx = self._find_column_index(
            self.settings.google_sheets_reasoning_col,
            ["reasoning", "evidence_reasoning", "summary", "rationale", "notes"],
        )
        if idx:
            mapping["reasoning"] = idx

        # 5. Follow-up Question Column
        idx = self._find_column_index(
            self.settings.google_sheets_follow_up_col,
            ["follow_up_question", "follow_up", "discovery_question", "question", "next_step"],
        )
        if idx:
            mapping["follow_up_question"] = idx

        # 6. Last Synced Column
        idx = self._find_column_index(
            self.settings.google_sheets_last_synced_col,
            ["last_synced", "synced_at", "last_evaluated", "evaluated_at", "timestamp"],
        )
        if idx:
            mapping["last_synced"] = idx

        logger.debug("Resolved Google Sheet column mapping: %s", mapping)
        return mapping

    @property
    def mapped_fields(self) -> dict[str, int]:
        """Return the dictionary of field names to 1-based column indices."""
        return self._col_indices

    @property
    def standard_header_names(self) -> list[str]:
        """Return canonical list of configured Google Sheet header titles."""
        return [
            self.settings.google_sheets_company_name_col,
            self.settings.google_sheets_website_col,
            self.settings.google_sheets_status_col,
            self.settings.google_sheets_fit_col,
            self.settings.google_sheets_confidence_col,
            self.settings.google_sheets_reasoning_col,
            self.settings.google_sheets_follow_up_col,
            self.settings.google_sheets_last_synced_col,
        ]

    def compute_verdict_fingerprint(self, verdict: Verdict) -> str:
        """Compute a deterministic hash representing the exact verdict output content."""
        payload = {
            "fit": verdict.fit.value if hasattr(verdict.fit, "value") else str(verdict.fit),
            "confidence": round(verdict.confidence, 4),
            "reasoning": verdict.reasoning,
            "follow_up_question": verdict.follow_up_question or "",
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def format_updates(
        self,
        verdict: Verdict,
        company: Company,
        include_identifying_fields: bool = False,
    ) -> tuple[dict[int, Any], dict[str, Any]]:
        """
        Format Verdict into cell values and map them to specific column indices.
        Returns:
            - updates_by_col_idx: {col_index: string_value} (for gspread write)
            - readable_updates: {field_name: string_value} (for logging and telemetry)
        """
        # Format reasoning as numbered list
        if isinstance(verdict.reasoning, list):
            reasoning_str = "\n".join(f"{i+1}. {r}" for i, r in enumerate(verdict.reasoning))
        else:
            reasoning_str = str(verdict.reasoning or "")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

        values_by_field: dict[str, Any] = {
            "status": "SYNCED",
            "fit": verdict.fit.value if hasattr(verdict.fit, "value") else str(verdict.fit),
            "confidence": f"{verdict.confidence:.2f}",
            "reasoning": reasoning_str,
            "follow_up_question": verdict.follow_up_question or "",
            "last_synced": now_str,
        }

        if include_identifying_fields:
            values_by_field["name"] = company.name
            values_by_field["website"] = company.website_url

        updates_by_col_idx: dict[int, Any] = {}
        readable_updates: dict[str, Any] = {}

        for field_name, value in values_by_field.items():
            if field_name in self._col_indices:
                col_idx = self._col_indices[field_name]
                updates_by_col_idx[col_idx] = value
                readable_updates[field_name] = value

        return updates_by_col_idx, readable_updates
