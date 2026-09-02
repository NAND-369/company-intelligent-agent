"""API Key & server-side secure session authentication dependencies and security validation."""

from datetime import datetime, timezone
import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, Security, status
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "cia_session"
SESSION_MAX_AGE_SECONDS = 86400  # 24 hours

# OpenAPI Security Scheme for Swagger UI Authorize dialog
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_session_secret(settings: Settings) -> bytes:
    """Return configured independent session secret bytes."""
    return settings.session_secret.encode("utf-8")



def create_session_token(
    settings: Optional[Settings] = None,
    max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
) -> str:
    """Generate an HMAC-signed, timestamped server-side session token."""
    cfg = settings or get_settings()
    issued_at = int(time.time())
    secret = _get_session_secret(cfg)
    sig = hmac.new(secret, f"{issued_at}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{issued_at}.{sig}"


def verify_session_token(
    token: Optional[str],
    settings: Optional[Settings] = None,
    max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
) -> bool:
    """Verify validity and signature of a session token in constant time."""
    if not token or not isinstance(token, str) or "." not in token:
        return False

    parts = token.split(".", 1)
    if len(parts) != 2:
        return False

    issued_str, signature = parts[0], parts[1]
    try:
        issued_at = int(issued_str)
    except ValueError:
        return False

    now = int(time.time())
    # Reject expired sessions or tokens from the future (>60s clock skew)
    if (now - issued_at) > max_age_seconds or issued_at > (now + 60):
        return False

    cfg = settings or get_settings()
    secret = _get_session_secret(cfg)
    expected_sig = hmac.new(secret, issued_str.encode("utf-8"), hashlib.sha256).hexdigest()

    return secrets.compare_digest(expected_sig, signature)


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
    """
    Dual-mode authentication validator:
    1. Browser dashboard requests: Authenticates via HttpOnly 'cia_session' cookie.
    2. External API clients / Swagger / GitHub Actions: Authenticates via 'X-API-Key' or 'Authorization: Bearer' header.
    """

    def __call__(
        self,
        x_api_key: Optional[str] = Security(api_key_header_scheme),
        authorization: Optional[str] = Header(None, alias="Authorization"),
        cia_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    ) -> bool:
        settings = get_settings()

        # Development bypass if no key is configured
        if not settings.api_key:
            return True

        # 1. Check direct X-API-Key header with constant-time comparison
        if x_api_key and secrets.compare_digest(x_api_key.strip(), settings.api_key):
            return True

        # 2. Check Authorization Bearer header with constant-time comparison
        if authorization:
            if authorization.startswith("Bearer "):
                bearer_key = authorization[7:].strip()
            else:
                bearer_key = authorization.strip()

            if bearer_key and secrets.compare_digest(bearer_key, settings.api_key):
                return True

        # 3. Check browser dashboard secure session cookie
        if cia_session and verify_session_token(cia_session, settings=settings):
            return True

        # Authentication failed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials.",
        )


def require_api_key(
    x_api_key: Optional[str] = Security(api_key_header_scheme),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    cia_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> bool:
    """FastAPI route dependency enforcing API key or session cookie authentication."""
    validator = APIKeyValidator()
    return validator(
        x_api_key=x_api_key,
        authorization=authorization,
        cia_session=cia_session,
    )
