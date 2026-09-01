"""System health check and readiness probe endpoint."""

import logging
import time
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import __version__
from app.api.schemas import HealthResponse
from app.config.settings import get_settings
from app.database.session import engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="System Health & Readiness Probe",
    description="Public probe verifying operational status and dependency connectivity.",
)
async def health_check(response: Response) -> HealthResponse:
    """Check liveness and connectivity of database, browser engine, and external providers."""
    settings = get_settings()
    dependencies: dict[str, dict] = {}
    is_healthy = True

    # 1. Database Connection & Latency Probe
    try:
        t0 = time.monotonic()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = int((time.monotonic() - t0) * 1000)
        dependencies["database"] = {
            "status": "connected",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        is_healthy = False
        dependencies["database"] = {
            "status": "disconnected",
            "error": str(exc),
        }

    # 2. Browser Engine Readiness
    dependencies["browser_engine"] = {
        "status": "ready" if settings.pipeline_enable_browser else "disabled",
        "engine": "Chromium (Playwright)",
    }

    # 3. LLM Provider Status
    llm_key_present = bool(
        settings.gemini_api_key
        or settings.groq_api_key
        or settings.openai_api_key
        or settings.llm_provider == "fake"
    )
    dependencies["llm_provider"] = {
        "status": "configured" if llm_key_present else "unconfigured (fallback to fake)",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }

    # 4. Google Sheets Integration Status
    sheets_auth_configured = bool(
        settings.google_service_account_info
        or settings.google_service_account_file
        or settings.google_sheets_spreadsheet_id
    )
    dependencies["google_sheets"] = {
        "status": "configured" if sheets_auth_configured else "unconfigured",
        "spreadsheet_id": settings.google_sheets_spreadsheet_id or None,
    }

    overall_status = "healthy" if is_healthy else "unhealthy"
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall_status,
        app_name=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        dependencies=dependencies,
    )
