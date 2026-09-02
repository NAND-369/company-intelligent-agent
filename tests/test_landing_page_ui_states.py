"""Unit tests verifying landing page UI state resolution and centered container layout."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_landing_page_layout_is_centered_and_balanced(async_client: AsyncClient) -> None:
    """Verify landing page CSS contains centered container and symmetrical layout rules."""
    resp = await async_client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Verify mathematically centered container rules
    assert "max-width: 1200px" in html
    assert "margin-left: auto" in html
    assert "margin-right: auto" in html
    assert "padding-left: 2rem" in html
    assert "padding-right: 2rem" in html

    # Verify no asymmetrical col-span-3 vs col-span-9 layout offset
    assert "col-span-9" not in html
    assert "col-span-3" not in html


@pytest.mark.asyncio
async def test_landing_page_js_implements_persisted_state_priority(async_client: AsyncClient) -> None:
    """Verify that landing page JavaScript implements distinct display rules for persisted verdicts vs active run state."""
    resp = await async_client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Verify functions and state logic
    assert "getCompanyBadges" in html
    assert "loadPersistedCompanies" in html
    assert "badge-synced" in html
    assert "SYNCED TO SHEET" in html
    assert "NOT SYNCED" in html
    assert "NOT PROCESSED" in html
    assert "○ QUEUED" in html
    assert "PROCESSING..." in html
    assert "badge-yes" in html
    assert "badge-no" in html
    assert "badge-uncertain" in html
