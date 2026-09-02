"""Google Sheets Company Ingestion Service orchestrating parsing, validation, and persistence."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.enums import CompanyStatus, SyncDirection, SyncStatus
from app.database.repositories import CompanyRepository, SyncLogRepository, VerdictRepository
from app.integrations.google_sheets.client import (
    GoogleSheetsClient,
    GoogleSheetsClientProtocol,
    GoogleSheetsError,
)
from app.integrations.google_sheets.parser import SheetRowParser
from app.integrations.google_sheets.schemas import IngestionResult, RowValidationError

logger = logging.getLogger(__name__)


class CompanyIngestionService:
    """Service responsible for reading, normalizing, and ingesting companies from Google Sheets into PostgreSQL."""

    def __init__(
        self,
        session: AsyncSession,
        client: Optional[GoogleSheetsClientProtocol] = None,
        parser: Optional[SheetRowParser] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.client = client or GoogleSheetsClient(self.settings)
        self.parser = parser or SheetRowParser(self.settings)

    async def ingest_companies(
        self,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
    ) -> IngestionResult:
        """
        Execute full ingestion cycle from Google Sheets to PostgreSQL System of Record.
        Returns IngestionResult with structured metrics, validation errors, and imported company objects.
        """
        target_spreadsheet_id = spreadsheet_id or self.settings.google_sheets_spreadsheet_id
        target_worksheet_name = worksheet_name or self.settings.google_sheets_worksheet_name

        result = IngestionResult(
            spreadsheet_id=target_spreadsheet_id,
            worksheet_name=target_worksheet_name,
        )

        if not target_spreadsheet_id:
            msg = "Missing Google Sheets spreadsheet ID. Configure GOOGLE_SHEETS_SPREADSHEET_ID."
            logger.error(msg)
            result.errors.append(msg)
            return result

        logger.info(
            "Starting ingestion from spreadsheet '%s', worksheet '%s'",
            target_spreadsheet_id,
            target_worksheet_name,
        )

        # 1. Fetch rows from Google Sheets API
        try:
            raw_rows = self.client.get_rows_with_indices(
                spreadsheet_id=target_spreadsheet_id,
                worksheet_name=target_worksheet_name,
            )
            result.rows_read = len(raw_rows)
        except GoogleSheetsError as exc:
            msg = f"Google Sheets API error during fetch: {exc!s}"
            logger.error(msg)
            result.errors.append(msg)
            return result
        except Exception as exc:
            msg = f"Unexpected error communicating with Google Sheets: {exc!s}"
            logger.error(msg)
            result.errors.append(msg)
            return result

        # 2. Iterate and process each row
        for row_index, row_dict in raw_rows:
            parsed, val_error = self.parser.parse_row(row_dict, row_index)

            # Case A: Entirely empty row (skipped silently)
            if parsed is None and val_error is None:
                result.rows_skipped += 1
                continue

            # Case B: Validation error (missing required company name or website)
            if val_error is not None:
                logger.warning(
                    "Row %d failed validation: %s (field=%s)",
                    row_index,
                    val_error.message,
                    val_error.field,
                )
                result.rows_skipped += 1
                result.validation_errors.append(val_error)
                continue

            # Case C: Valid company row -> Persist in PostgreSQL via Repository
            try:
                company, created = await CompanyRepository.upsert_by_sheet_row_id(
                    session=self.session,
                    name=parsed.name,
                    website_url=parsed.website_url,
                    sheet_row_id=parsed.sheet_row_id,
                    domain=parsed.domain,
                )

                # Record sync audit log for tracking
                await SyncLogRepository.create(
                    session=self.session,
                    company_id=company.id,
                    sync_direction=SyncDirection.SHEET_TO_DB,
                    status=SyncStatus.SUCCESS,
                )

                # Fetch latest verdict if company was already evaluated
                latest_verdict = await VerdictRepository.get_latest_by_company(self.session, company.id)
                fit_str = "—"
                conf_str = "—"
                if latest_verdict and latest_verdict.fit:
                    raw_f = latest_verdict.fit.value if hasattr(latest_verdict.fit, "value") else str(latest_verdict.fit)
                    fit_str = raw_f.replace("FitDecision.", "").upper()
                    if latest_verdict.confidence is not None:
                        conf_str = f"{round(latest_verdict.confidence * 100)}%"

                result.imported_companies.append({
                    "id": str(company.id),
                    "name": company.name,
                    "website_url": company.website_url,
                    "domain": company.domain,
                    "sheet_row_id": company.sheet_row_id,
                    "status": company.status.value if hasattr(company.status, "value") else str(company.status),
                    "fit": fit_str,
                    "confidence": conf_str,
                    "is_synced": company.status == CompanyStatus.SYNCED,
                })

                if created:
                    result.companies_created += 1
                    result.created_company_ids.append(str(company.id))
                    logger.info(
                        "Created new company: '%s' (id=%s, sheet_row_id=%s)",
                        company.name,
                        company.id,
                        company.sheet_row_id,
                    )
                else:
                    result.companies_updated += 1
                    result.updated_company_ids.append(str(company.id))
                    logger.info(
                        "Updated existing company: '%s' (id=%s, sheet_row_id=%s)",
                        company.name,
                        company.id,
                        company.sheet_row_id,
                    )

            except Exception as exc:
                msg = f"Database error persisting row {row_index} ('{parsed.name}'): {exc!s}"
                logger.error(msg)
                result.errors.append(msg)
                result.rows_skipped += 1

        # 3. Commit database transaction
        await self.session.commit()

        logger.info(
            "Ingestion completed. Read=%d, Created=%d, Updated=%d, Skipped=%d, Errors=%d",
            result.rows_read,
            result.companies_created,
            result.companies_updated,
            result.rows_skipped,
            len(result.validation_errors) + len(result.errors),
        )
        return result
