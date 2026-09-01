"""Health check endpoint definition."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__
from app.config.settings import get_settings

router = APIRouter(tags=["Health"])
settings = get_settings()


class HealthResponse(BaseModel):
    """Structured response schema for health check endpoint."""

    status: str = Field(default="ok", description="Overall service status")
    app_name: str = Field(description="Name of the running service")
    version: str = Field(description="Application version")
    environment: str = Field(description="Active application runtime environment")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check probe",
    description="Public liveness probe returning basic service operational status without requiring authentication.",
)
async def health_check() -> HealthResponse:
    """Return application health and basic runtime metadata."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=__version__,
        environment=settings.app_env,
    )
