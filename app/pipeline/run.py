"""CLI entrypoint for running the intelligence pipeline from command line."""

import argparse
import asyncio
import json
import logging
import sys

from app.database.enums import PipelineRunStatus, TriggerType
from app.database.session import async_session_factory
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Company Intelligence Pipeline (Ingestion -> Enrichment -> LLM Evaluation -> Sheets Sync)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of companies to process in this run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview candidate companies and planned actions without mutating records.",
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Skip fetching new rows from Google Sheets; process pending database companies only.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchronize evaluated verdicts back to Google Sheets rows.",
    )
    parser.add_argument(
        "--trigger",
        type=str,
        default="ON_DEMAND_API",
        choices=["ON_DEMAND_API", "SCHEDULED", "GITHUB_ACTIONS"],
        help="Trigger origin category for pipeline telemetry.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    trigger_type = TriggerType(args.trigger)

    request = PipelineRunRequest(
        limit=args.limit,
        dry_run=args.dry_run,
        skip_ingestion=args.skip_ingestion,
        sync_to_sheets=args.sync,
        trigger_type=trigger_type,
    )

    logger.info("Executing Pipeline CLI runner (sync=%s)...", args.sync)
    async with async_session_factory() as session:
        orchestrator = PipelineOrchestrator(session=session)
        result = await orchestrator.run_pipeline(request)

        # Output formatted JSON telemetry for CI/CD or CLI consumption
        telemetry = result.model_dump(mode="json")
        print("\n" + "=" * 60)
        print("PIPELINE EXECUTION TELEMETRY RESULT:")
        print("=" * 60)
        print(json.dumps(telemetry, indent=2, default=str))
        print("=" * 60 + "\n")

        if result.status == PipelineRunStatus.FAILED:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
