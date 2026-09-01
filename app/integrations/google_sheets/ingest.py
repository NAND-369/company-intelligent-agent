"""CLI entrypoint for manually running Google Sheets company ingestion during development."""

import argparse
import asyncio
import logging
import sys

from app.config.settings import get_settings
from app.database.session import async_session_factory
from app.integrations.google_sheets.service import CompanyIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.integrations.google_sheets.ingest")


async def run_ingestion_cli(spreadsheet_id: str | None = None, worksheet_name: str | None = None) -> None:
    """Run Google Sheets ingestion from command-line."""
    settings = get_settings()
    target_spreadsheet = spreadsheet_id or settings.google_sheets_spreadsheet_id
    target_worksheet = worksheet_name or settings.google_sheets_worksheet_name

    if not target_spreadsheet:
        print("\n[ERROR] No spreadsheet ID provided.")
        print("Set GOOGLE_SHEETS_SPREADSHEET_ID in .env or pass --spreadsheet-id <ID>\n")
        sys.exit(1)

    print("\n=======================================================")
    print("   Autonomous Company Agent: Google Sheets Ingestion   ")
    print("=======================================================")
    print(f"Spreadsheet ID: {target_spreadsheet}")
    print(f"Worksheet Name: {target_worksheet}")
    print("-------------------------------------------------------")

    async with async_session_factory() as session:
        service = CompanyIngestionService(session=session, settings=settings)
        result = await service.ingest_companies(
            spreadsheet_id=target_spreadsheet,
            worksheet_name=target_worksheet,
        )

        print("\n--- Ingestion Summary ---")
        print(f"Rows Read:          {result.rows_read}")
        print(f"Companies Created:  {result.companies_created}")
        print(f"Companies Updated:  {result.companies_updated}")
        print(f"Rows Skipped:       {result.rows_skipped}")

        if result.validation_errors:
            print(f"\nValidation Issues ({len(result.validation_errors)}):")
            for err in result.validation_errors:
                print(f"  - Row {err.row_index} [{err.field}]: {err.message}")

        if result.errors:
            print(f"\nSystem/API Errors ({len(result.errors)}):")
            for err_msg in result.errors:
                print(f"  - {err_msg}")

        print("=======================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest company records from Google Sheets into PostgreSQL.")
    parser.add_argument("--spreadsheet-id", "-s", type=str, default=None, help="Google Spreadsheet ID")
    parser.add_argument("--worksheet-name", "-w", type=str, default=None, help="Worksheet/Tab name (default: Companies)")
    args = parser.parse_args()

    asyncio.run(run_ingestion_cli(spreadsheet_id=args.spreadsheet_id, worksheet_name=args.worksheet_name))


if __name__ == "__main__":
    main()
