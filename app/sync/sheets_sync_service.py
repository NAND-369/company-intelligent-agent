"""Google Sheets synchronization service writing evaluated verdicts back to spreadsheet rows."""

import logging
from typing import Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.enums import CompanyStatus, SyncDirection, SyncStatus
from app.database.models import Company, Verdict
from app.database.repositories import (
    CompanyRepository,
    SyncLogRepository,
    VerdictRepository,
)
from app.integrations.google_sheets.client import (
    GoogleSheetsClient,
    GoogleSheetsClientProtocol,
    GoogleSheetsError,
)
from app.sync.column_mapper import SheetColumnMapper
from app.sync.schemas import SyncBatchResult, SyncCompanyResult, SyncOutcome

logger = logging.getLogger(__name__)


class SheetsSyncService:
    """Synchronizes persisted PostgreSQL verdicts back to target Google Sheet rows."""

    def __init__(
        self,
        session: AsyncSession,
        client: Optional[GoogleSheetsClientProtocol] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.client = client or GoogleSheetsClient(self.settings)
        self._mapper_cache: dict[str, SheetColumnMapper] = {}

    def _get_mapper(self, spreadsheet_id: str, worksheet_name: str) -> SheetColumnMapper:
        """Fetch worksheet headers and cache SheetColumnMapper instance."""
        cache_key = f"{spreadsheet_id}:{worksheet_name}"
        if cache_key in self._mapper_cache:
            return self._mapper_cache[cache_key]

        headers = self.client.get_header_row(spreadsheet_id, worksheet_name)
        mapper = SheetColumnMapper(headers=headers, settings=self.settings)
        self._mapper_cache[cache_key] = mapper
        return mapper

    async def sync_company(
        self,
        company_id: uuid.UUID,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> SyncCompanyResult:
        """
        Synchronize a single company's latest verdict to its Google Sheet row.
        Guarantees idempotency and safe failure recording in sync_logs.
        """
        target_spreadsheet_id = spreadsheet_id or self.settings.google_sheets_spreadsheet_id
        target_worksheet_name = worksheet_name or self.settings.google_sheets_worksheet_name

        company = await CompanyRepository.get_by_id(self.session, company_id)
        if not company:
            return SyncCompanyResult(
                company_id=company_id,
                company_name="Unknown",
                sheet_row_id="",
                row_index=0,
                status=SyncOutcome.FAILED,
                error_details=f"Company '{company_id}' not found in database.",
            )

        # 1. Retrieve latest verdict
        verdict = await VerdictRepository.get_latest_by_company(self.session, company.id)
        if not verdict:
            msg = f"No verdict found for company '{company.name}'. Cannot sync to Google Sheets."
            logger.warning(msg)
            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id or "",
                row_index=0,
                status=SyncOutcome.FAILED,
                error_details=msg,
            )

        # 2. Resolve Column Mapper and ensure required header columns exist
        try:
            mapper = self._get_mapper(target_spreadsheet_id, target_worksheet_name)
            # Ensure output columns exist in Google Sheet if supported
            if hasattr(self.client, "ensure_header_columns"):
                updated_headers = self.client.ensure_header_columns(
                    target_spreadsheet_id, target_worksheet_name, mapper.standard_header_names
                )
                if updated_headers != mapper.headers:
                    cache_key = f"{target_spreadsheet_id}:{target_worksheet_name}"
                    mapper = SheetColumnMapper(headers=updated_headers, settings=self.settings)
                    self._mapper_cache[cache_key] = mapper
        except Exception as exc:
            msg = f"Failed to connect or retrieve Google Sheet headers: {exc!s}"
            logger.error(msg)
            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id or "",
                row_index=0,
                status=SyncOutcome.FAILED,
                error_details=msg,
            )

        # 3. Determine target row index (from existing sheet_row_id or by matching / appending)
        row_index: Optional[int] = None
        is_appended = False

        if company.sheet_row_id:
            try:
                row_index = int(company.sheet_row_id.replace("row_", ""))
            except ValueError:
                row_index = None

        if row_index is None:
            # Check if company already exists in the Google Sheet by name or website
            if hasattr(self.client, "find_company_row"):
                try:
                    found_row = self.client.find_company_row(
                        spreadsheet_id=target_spreadsheet_id,
                        worksheet_name=target_worksheet_name,
                        company_name=company.name,
                        website_url=company.website_url,
                    )
                    if found_row:
                        row_index = found_row
                        company.sheet_row_id = f"row_{row_index}"
                        await CompanyRepository.update_sheet_row_id(self.session, company.id, company.sheet_row_id)
                        logger.info("Matched company '%s' to existing Google Sheet row %d", company.name, row_index)
                    else:
                        is_appended = True
                except Exception as exc:
                    msg = f"Error querying existing rows for company '{company.name}': {exc!s}"
                    logger.error(msg)
            else:
                is_appended = True

        fingerprint = mapper.compute_verdict_fingerprint(verdict)
        col_updates, readable_updates = mapper.format_updates(
            verdict, company, include_identifying_fields=is_appended
        )

        if not col_updates:
            msg = "No configured output columns found in Google Sheet header row."
            logger.error(msg)
            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id or "",
                row_index=row_index or 0,
                status=SyncOutcome.FAILED,
                error_details=msg,
            )

        # 4. Idempotency Check
        if not force and company.status == CompanyStatus.SYNCED and row_index is not None and not is_appended:
            recent_logs = await SyncLogRepository.list_by_company(self.session, company.id)
            has_prior_success = any(
                log.sync_direction == SyncDirection.DB_TO_SHEET and log.status == SyncStatus.SUCCESS
                for log in recent_logs
            )
            if has_prior_success:
                logger.info("Company '%s' (row %d) is already synced. Skipping.", company.name, row_index)
                return SyncCompanyResult(
                    company_id=company.id,
                    company_name=company.name,
                    sheet_row_id=company.sheet_row_id or f"row_{row_index}",
                    row_index=row_index,
                    status=SyncOutcome.SKIPPED,
                    fingerprint=fingerprint,
                    updates=readable_updates,
                )

        # 5. Handle Dry Run Preview
        if dry_run:
            simulated_row = row_index or 999
            logger.info("[Dry Run] Would %s Google Sheet row %d for '%s': %s", "append" if is_appended else "update", simulated_row, company.name, readable_updates)
            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id or f"row_{simulated_row}",
                row_index=simulated_row,
                status=SyncOutcome.SUCCESS,
                fingerprint=fingerprint,
                updates=readable_updates,
            )

        # 6. Execute Cell Writes to Google Sheet
        try:
            if is_appended or row_index is None:
                logger.info("Appending new row for company '%s' to Google Sheet...", company.name)
                row_index = self.client.append_row_values(
                    spreadsheet_id=target_spreadsheet_id,
                    worksheet_name=target_worksheet_name,
                    updates_by_col_index=col_updates,
                )
                company.sheet_row_id = f"row_{row_index}"
                await CompanyRepository.update_sheet_row_id(self.session, company.id, company.sheet_row_id)
            else:
                logger.info("Writing verdict to Google Sheet row %d for company '%s'...", row_index, company.name)
                self.client.update_row_cells(
                    spreadsheet_id=target_spreadsheet_id,
                    worksheet_name=target_worksheet_name,
                    row_index=row_index,
                    updates_by_col_index=col_updates,
                )

            # 7. Update PostgreSQL Status and Audit Trail
            await CompanyRepository.update_status(self.session, company.id, CompanyStatus.SYNCED)
            await SyncLogRepository.create(
                session=self.session,
                company_id=company.id,
                sync_direction=SyncDirection.DB_TO_SHEET,
                status=SyncStatus.SUCCESS,
            )
            await self.session.commit()

            logger.info(
                "[DIAGNOSTIC_SHEETS_SYNC] COMPANY_ID=%s COMPANY_NAME=%s SHEET_ROW_ID=%s SPREADSHEET_ID=%s STATUS=SUCCESS ERROR=None",
                company.id,
                company.name,
                company.sheet_row_id,
                target_spreadsheet_id,
            )

            logger.info("Successfully synced verdict for company '%s' (row %d) to Google Sheets.", company.name, row_index)
            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id,
                row_index=row_index,
                status=SyncOutcome.SUCCESS,
                fingerprint=fingerprint,
                updates=readable_updates,
            )

        except Exception as exc:
            msg = f"Google Sheets write error for company '{company.name}' (row {row_index}): {exc!s}"
            logger.error(msg)
            logger.info(
                "[DIAGNOSTIC_SHEETS_SYNC] COMPANY_ID=%s COMPANY_NAME=%s SHEET_ROW_ID=%s SPREADSHEET_ID=%s STATUS=FAILED ERROR=%s",
                company.id,
                company.name,
                company.sheet_row_id,
                target_spreadsheet_id,
                msg,
            )
            await SyncLogRepository.create(
                session=self.session,
                company_id=company.id,
                sync_direction=SyncDirection.DB_TO_SHEET,
                status=SyncStatus.FAILED,
                error_details=msg,
            )
            await self.session.commit()

            return SyncCompanyResult(
                company_id=company.id,
                company_name=company.name,
                sheet_row_id=company.sheet_row_id or "",
                row_index=row_index or 0,
                status=SyncOutcome.FAILED,
                error_details=msg,
            )

    async def sync_evaluated_companies(
        self,
        limit: Optional[int] = None,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> SyncBatchResult:
        """
        Synchronize all companies in JUDGED state (or all if force=True) to Google Sheets.
        Isolates failures across companies.
        """
        target_spreadsheet_id = spreadsheet_id or self.settings.google_sheets_spreadsheet_id
        target_worksheet_name = worksheet_name or self.settings.google_sheets_worksheet_name

        result = SyncBatchResult(
            spreadsheet_id=target_spreadsheet_id,
            worksheet_name=target_worksheet_name,
        )

        if not target_spreadsheet_id:
            msg = "Missing Google Sheets spreadsheet ID. Configure GOOGLE_SHEETS_SPREADSHEET_ID."
            logger.error(msg)
            result.errors.append(msg)
            return result

        # Query companies eligible for synchronization
        stmt = (
            select(Company)
            .where(Company.status.in_([CompanyStatus.JUDGED, CompanyStatus.ENRICHED]))
            .order_by(Company.created_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)

        candidates_res = await self.session.execute(stmt)
        candidates = list(candidates_res.scalars().all())
        result.total_candidates = len(candidates)

        logger.info("Found %d evaluated companies ready for Google Sheets synchronization.", len(candidates))

        for company in candidates:
            co_res = await self.sync_company(
                company_id=company.id,
                spreadsheet_id=target_spreadsheet_id,
                worksheet_name=target_worksheet_name,
                force=force,
                dry_run=dry_run,
            )
            result.company_results.append(co_res)

            if co_res.status == SyncOutcome.SUCCESS:
                result.synced_count += 1
            elif co_res.status == SyncOutcome.SKIPPED:
                result.skipped_count += 1
            elif co_res.status == SyncOutcome.FAILED:
                result.failed_count += 1
                if co_res.error_details:
                    result.errors.append(f"{company.name}: {co_res.error_details}")

        logger.info(
            "Sync batch complete: synced=%d, skipped=%d, failed=%d",
            result.synced_count,
            result.skipped_count,
            result.failed_count,
        )
        return result
