"""API Key authentication dependency and security validation."""

from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[dict] = None,
) -> JSONResponse:
    """Construct a uniform JSON error response compliant with docs/API_SPEC.md."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    return JSONResponse(status_code=status_code, content=payload)


class APIKeyValidator:
    """Validates API Key from X-API-Key or Authorization Bearer header."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def __call__(
        self,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        authorization: Optional[str] = Header(None, alias="Authorization"),
    ) -> bool:
        # Development bypass if no key is configured
        if not self.settings.api_key:
            return True

        provided_key: Optional[str] = None
        if x_api_key:
            provided_key = x_api_key
        elif authorization:
            if authorization.startswith("Bearer "):
                provided_key = authorization[7:].strip()
            else:
                provided_key = authorization.strip()

        if not provided_key or provided_key != self.settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key in X-API-Key or Authorization header.",
            )
        return True


def require_api_key(
    validator: APIKeyValidator = Depends(APIKeyValidator),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """FastAPI route dependency enforcing API key authentication."""
    return validator(x_api_key=x_api_key, authorization=authorization)
