"""FastAPI routes for triggering pipeline executions and inspecting execution telemetry."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.session as session_module
from app.api.auth import require_api_key
from app.api.schemas import (
    PipelineRunDetailResponse,
    PipelineRunMetrics,
    PipelineRunSummary,
    TriggerRunRequest,
    TriggerRunResponse,
)
from app.database.enums import PipelineRunStatus, TriggerType
from app.database.models import PipelineRun
from app.database.repositories import PipelineRunRepository
from app.database.session import get_db_session
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Pipeline Runs"])


async def _run_pipeline_background(
    run_id: uuid.UUID,
    req: TriggerRunRequest,
    trigger_type: TriggerType,
) -> None:
    """Execute pipeline in a dedicated background async task with isolated session."""
    logger.info("Starting background pipeline task for run_id=%s", run_id)
    try:
        async with session_module.async_session_factory() as session:
            orchestrator = PipelineOrchestrator(session=session)
            pipeline_request = PipelineRunRequest(
                limit=req.effective_batch_size,
                dry_run=req.dry_run,
                skip_ingestion=req.skip_ingestion,
                sync_to_sheets=req.sync_to_sheets,
                trigger_type=trigger_type,
            )
            await orchestrator.run_pipeline(pipeline_request)
    except Exception as exc:
        logger.exception("Fatal error executing background pipeline run %s: %s", run_id, exc)
        async with session_module.async_session_factory() as session:
            await PipelineRunRepository.complete_run(
                session=session,
                run_id=run_id,
                status=PipelineRunStatus.FAILED,
                error_summary={"fatal_error": str(exc)},
            )
            await session.commit()


@router.post(
    "/run",
    response_model=TriggerRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Pipeline Run",
    description="Enqueue an on-demand intelligence pipeline execution in the background.",
)
async def trigger_run(
    config: TriggerRunRequest = TriggerRunRequest(),
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> TriggerRunResponse:
    """Validate active runs, create RUNNING record, and dispatch background execution."""
    # 1. Check for active run conflict
    active_stmt = select(PipelineRun).where(PipelineRun.status == PipelineRunStatus.RUNNING).limit(1)
    active_res = await session.execute(active_stmt)
    active_run = active_res.scalar_one_or_none()

    if active_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pipeline run is already in progress with ID '{active_run.id}'.",
        )

    # 2. Pre-create PipelineRun in database
    run = await PipelineRunRepository.create(
        session=session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
    )
    await session.commit()

    # 3. Spawn background execution
    asyncio.create_task(_run_pipeline_background(run.id, config, TriggerType.ON_DEMAND_API))

    return TriggerRunResponse(
        run_id=run.id,
        status="RUNNING",
        message="Pipeline run initiated successfully.",
        batch_size=config.effective_batch_size,
        triggered_at=datetime.now(timezone.utc),
        links={"status_url": f"/runs/{run.id}"},
    )


@router.post(
    "/pipeline/run",
    response_model=TriggerRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Pipeline Run (Alias)",
    description="Alias endpoint for triggering a pipeline execution.",
)
async def trigger_pipeline_run(
    config: TriggerRunRequest = TriggerRunRequest(),
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> TriggerRunResponse:
    """Alias endpoint for triggering a pipeline execution."""
    return await trigger_run(config=config, session=session, _auth=_auth)


@router.get(
    "/runs/{run_id}",
    response_model=PipelineRunDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Pipeline Run Status & Metrics",
    description="Retrieve execution status, metrics counters, and error summaries for a run.",
)
async def get_run_status(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> PipelineRunDetailResponse:
    """Query execution telemetry for a specific pipeline run."""
    run = await PipelineRunRepository.get_by_id(session, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run with ID '{run_id}' was not found.",
        )

    # Parse errors from error_summary json
    error_list = []
    if run.error_summary and isinstance(run.error_summary, dict):
        if "errors" in run.error_summary and isinstance(run.error_summary["errors"], list):
            error_list = [{"error_message": err} for err in run.error_summary["errors"]]
        elif "fatal_error" in run.error_summary:
            error_list = [{"error_message": run.error_summary["fatal_error"]}]

    return PipelineRunDetailResponse(
        run_id=run.id,
        status=run.status,
        trigger_source=run.trigger_type,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        metrics=PipelineRunMetrics(
            total_companies_discovered=run.total_companies,
            processed_count=run.processed_count,
            success_count=run.success_count,
            failed_extraction_count=run.failed_extraction_count,
            failed_evaluation_count=run.failed_evaluation_count,
            synced_to_sheet_count=run.synced_count,
        ),
        summary=PipelineRunSummary(
            fit_yes=run.fit_yes_count,
            fit_no=run.fit_no_count,
            fit_uncertain=run.fit_uncertain_count,
        ),
        errors=error_list,
    )
