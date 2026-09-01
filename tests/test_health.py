"""Tests for the health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_success(async_client: AsyncClient) -> None:
    """Test that GET /health returns 200 OK with expected JSON structure."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ("ok", "healthy")
    assert "app_name" in data
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_check_no_auth_required(async_client: AsyncClient) -> None:
    """Test that GET /health is publicly accessible without authentication headers."""
    response = await async_client.get("/health", headers={})
    assert response.status_code == 200
