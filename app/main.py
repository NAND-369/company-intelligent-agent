"""FastAPI Application Entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes_companies import router as companies_router
from app.api.routes_health import router as health_router
from app.api.routes_landing import router as landing_router
from app.api.routes_pipeline import router as pipeline_router
from app.config.settings import get_settings
from app.core.scheduler import get_scheduler
from app.database.session import close_database_engine, init_database_tables

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    logger.info(
        "Starting %s v%s in [%s] mode...",
        settings.app_name,
        __version__,
        settings.app_env,
    )
    # Ensure database schema is initialized and recover any dangling runs from previous instance
    try:
        await init_database_tables()
        logger.info("Database schema verification/initialization completed.")

        from sqlalchemy import update
        from app.database.enums import PipelineRunStatus
        from app.database.models import PipelineRun
        import app.database.session as session_module

        async with session_module.async_session_factory() as session:
            # Recover dangling RUNNING pipeline runs from previous server instance
            stmt = (
                update(PipelineRun)
                .where(PipelineRun.status == PipelineRunStatus.RUNNING)
                .values(
                    status=PipelineRunStatus.FAILED,
                    completed_at=datetime.now(timezone.utc),
                    error_summary={"startup_recovery": "Interrupted by deployment or server restart."},
                )
            )
            res = await session.execute(stmt)
            if res.rowcount > 0:
                logger.info("Startup recovery: marked %d dangling RUNNING run(s) as FAILED.", res.rowcount)
            await session.commit()
    except Exception as db_err:
        logger.warning("Database table initialization/recovery deferred or failed: %s", db_err)

    scheduler = get_scheduler()
    scheduler.start()

    yield

    scheduler.stop()
    await close_database_engine()
    logger.info("Shutting down %s...", settings.app_name)


def create_app() -> FastAPI:
    """Factory function for creating and configuring the FastAPI instance."""
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Autonomous Company Intelligence & Signal Extraction Pipeline REST API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Basic CORS Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standardized Exception Handler for HTTPException
    @application.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code_map = {
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_404_NOT_FOUND: "ENTITY_NOT_FOUND",
            status.HTTP_409_CONFLICT: "CONFLICT",
            status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        if isinstance(exc.detail, dict):
            msg = exc.detail.get("message", "HTTP Error")
            details = exc.detail
        else:
            msg = str(exc.detail)
            details = None

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": msg,
                    "details": details,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    # Include Routes
    application.include_router(landing_router)
    application.include_router(health_router)
    application.include_router(pipeline_router)
    application.include_router(companies_router)

    return application


app = create_app()
