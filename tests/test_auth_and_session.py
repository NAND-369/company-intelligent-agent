"""Comprehensive tests for API-key authentication, server-side session cookies, and secret isolation."""

import hashlib
import hmac
import time
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    verify_session_token,
)
from app.config.settings import Settings, get_settings


@pytest.mark.asyncio
async def test_landing_page_sets_secure_session_cookie(async_client: AsyncClient) -> None:
    """Verify that GET / renders dashboard and issues an HttpOnly, SameSite=lax session cookie."""
    response = await async_client.get("/")
    assert response.status_code == 200

    # Verify Set-Cookie header
    cookie_header = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


@pytest.mark.asyncio
async def test_dashboard_authenticated_via_session_cookie(async_client: AsyncClient) -> None:
    """Verify that protected API endpoints accept valid session cookies without X-API-Key header."""
    # 1. Access landing page to obtain session cookie
    landing_res = await async_client.get("/")
    assert landing_res.status_code == 200
    session_token = landing_res.cookies.get(SESSION_COOKIE_NAME)
    assert session_token is not None

    # 2. Call protected POST /companies using only the session cookie
    comp_res = await async_client.post(
        "/companies",
        json={"name": "Session Co", "website_url": "https://session-co.com"},
        cookies={SESSION_COOKIE_NAME: session_token},
    )
    assert comp_res.status_code == 201
    assert comp_res.json()["name"] == "Session Co"


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(async_client: AsyncClient) -> None:
    """Verify that requests without API key and without session cookie are rejected with 401."""
    response = await async_client.post(
        "/companies",
        json={"name": "No Auth Co", "website_url": "https://noauth.com"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_expired_session_cookie_rejected(async_client: AsyncClient) -> None:
    """Verify that an expired session cookie (>24 hours) is rejected with 401."""
    settings = get_settings()
    # Create token expired 25 hours ago
    expired_timestamp = int(time.time()) - (25 * 3600)
    secret = settings.session_secret.encode("utf-8")
    sig = hmac.new(secret, f"{expired_timestamp}".encode("utf-8"), hashlib.sha256).hexdigest()
    expired_token = f"{expired_timestamp}.{sig}"

    response = await async_client.post(
        "/companies",
        json={"name": "Expired Co", "website_url": "https://expired.com"},
        cookies={SESSION_COOKIE_NAME: expired_token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forged_session_cookie_rejected(async_client: AsyncClient) -> None:
    """Verify that a tampered or forged session signature is rejected with 401."""
    now = int(time.time())
    forged_token = f"{now}.invalid_forged_signature_hex_1234567890abcdef"

    response = await async_client.post(
        "/companies",
        json={"name": "Forged Co", "website_url": "https://forged.com"},
        cookies={SESSION_COOKIE_NAME: forged_token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_external_client_x_api_key_header_accepted(async_client: AsyncClient) -> None:
    """Verify that external clients authenticate successfully with valid X-API-Key header."""
    settings = get_settings()
    response = await async_client.post(
        "/companies",
        json={"name": "Machine API Co", "website_url": "https://machine-api.com"},
        headers={"X-API-Key": settings.api_key},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_external_client_bearer_token_accepted(async_client: AsyncClient) -> None:
    """Verify that external clients authenticate successfully with Authorization: Bearer <key>."""
    settings = get_settings()
    response = await async_client.post(
        "/companies",
        json={"name": "Bearer API Co", "website_url": "https://bearer-api.com"},
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_external_client_wrong_key_rejected(async_client: AsyncClient) -> None:
    """Verify that wrong API keys are rejected in constant time."""
    response = await async_client.post(
        "/companies",
        json={"name": "Wrong Key Co", "website_url": "https://wrongkey.com"},
        headers={"X-API-Key": "completely-invalid-key"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_secrets_never_leaked_in_responses_or_html(async_client: AsyncClient) -> None:
    """Verify that the master API key and session secrets are never returned in public responses or HTML."""
    settings = get_settings()
    master_key = settings.api_key
    session_sec = settings.session_secret

    # 1. Landing page HTML
    landing_res = await async_client.get("/")
    assert master_key not in landing_res.text
    assert session_sec not in landing_res.text
    assert "localStorage" not in landing_res.text
    assert "agent_api_key" not in landing_res.text
    assert "Set API Key" not in landing_res.text
    assert "prompt(" not in landing_res.text

    # 2. Health probe
    health_res = await async_client.get("/health")
    assert master_key not in health_res.text
    assert session_sec not in health_res.text

    # 3. OpenAPI documentation schema
    openapi_res = await async_client.get("/openapi.json")
    assert master_key not in openapi_res.text
    assert session_sec not in openapi_res.text


def test_session_token_unit_verification() -> None:
    """Unit test verify_session_token timing-safe and boundary checks."""
    settings = Settings(api_key="test-key-12345", session_secret="test-sec-abcde")
    token = create_session_token(settings, max_age_seconds=60)

    assert verify_session_token(token, settings, max_age_seconds=60) is True
    assert verify_session_token("malformed", settings) is False
    assert verify_session_token("", settings) is False
    assert verify_session_token(None, settings) is False


def test_session_secret_domain_independence() -> None:
    """Verify that session validation strictly uses SESSION_SECRET independently of X_API_KEY."""
    cfg1 = Settings(api_key="api-key-AAA", session_secret="session-secret-111")
    token = create_session_token(cfg1, max_age_seconds=300)

    # Changing API key does NOT invalidate session token
    cfg2 = Settings(api_key="api-key-BBB", session_secret="session-secret-111")
    assert verify_session_token(token, cfg2, max_age_seconds=300) is True

    # Changing SESSION_SECRET strictly invalidates session token
    cfg3 = Settings(api_key="api-key-AAA", session_secret="session-secret-222")
    assert verify_session_token(token, cfg3, max_age_seconds=300) is False


def test_production_secrets_strict_validation() -> None:
    """Verify that in production, both X_API_KEY and SESSION_SECRET are required and distinct."""
    # Production with default insecure API key fails
    with pytest.raises(ValueError, match="X_API_KEY must be configured"):
        Settings(app_env="production", api_key="dev-insecure-key", session_secret="secure-prod-session-sec")

    # Production with default insecure SESSION_SECRET fails
    with pytest.raises(ValueError, match="SESSION_SECRET must be configured"):
        Settings(app_env="production", api_key="secure-prod-api-key", session_secret="dev-insecure-session-secret")

    # Production with identical secrets fails
    with pytest.raises(ValueError, match="independent, distinct secrets"):
        Settings(app_env="production", api_key="same-secret-key", session_secret="same-secret-key")

    # Production with valid distinct secrets succeeds
    prod_cfg = Settings(
        app_env="production",
        api_key="prod-api-key-x9999",
        session_secret="prod-session-sec-y8888",
    )
    assert prod_cfg.api_key == "prod-api-key-x9999"
    assert prod_cfg.session_secret == "prod-session-sec-y8888"

