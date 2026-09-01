"""FastAPI routes for triggering and monitoring intelligence pipeline executions."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.session import get_db_session
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest, PipelineRunResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Pipeline"])


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> bool:
    """Validate API key for protected pipeline operations."""
    if settings.app_env == "development" or not settings.api_key:
        return True
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key in X-API-Key header.",
        )
    return True


@router.post(
    "/pipeline/run",
    response_model=PipelineRunResult,
    status_code=status.HTTP_200_OK,
    summary="Trigger Pipeline Run",
    description="Trigger an intelligence pipeline execution (Ingestion -> Enrichment -> LLM Judgment).",
)
@router.post(
    "/run",
    response_model=PipelineRunResult,
    status_code=status.HTTP_200_OK,
    summary="Trigger Pipeline Run (Alias)",
    description="Alias endpoint for initiating a pipeline execution.",
)
async def trigger_pipeline_run(
    request: Optional[PipelineRunRequest] = None,
    session: AsyncSession = Depends(get_db_session),
    _authorized: bool = Depends(verify_api_key),
) -> PipelineRunResult:
    """Execute intelligence pipeline run asynchronously."""
    req = request or PipelineRunRequest()
    orchestrator = PipelineOrchestrator(session=session)
    return await orchestrator.run_pipeline(req)
