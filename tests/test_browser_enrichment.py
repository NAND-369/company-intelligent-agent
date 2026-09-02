"""Tests for Playwright browser client, dynamic DOM evidence extraction, and browser enrichment service."""

import os
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, SignalStatus, SignalType
from app.database.models import Company, Signal
from app.database.repositories import CompanyRepository, SignalRepository
from app.enrichment.browser_client import PlaywrightBrowserClient
from app.enrichment.browser_enricher import BrowserEnricher
from app.enrichment.browser_extractor import BrowserEvidenceExtractor
from app.enrichment.extractor import HtmlEvidenceExtractor
from app.enrichment.service import HttpEnrichmentService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DYNAMIC_JOBS_FILE = FIXTURES_DIR / "dynamic_jobs.html"


# ==============================================================================
# 1. BrowserEvidenceExtractor Unit Tests
# ==============================================================================

def test_browser_extractor_dynamic_jobs() -> None:
    """Test extracting dynamic job cards and tech stack from rendered HTML."""
    rendered_html = """
    <html>
    <head><title>Apex AI Careers</title></head>
    <body>
        <h1>Careers at Apex AI</h1>
        <div class="jobs-list" data-total-jobs="2">
            <div class="job-card" data-job-id="job-1">
                <h3><a href="/jobs/1">Lead Python Engineer</a></h3>
                <span class="job-dept">Backend Engineering</span>
                <span class="job-loc">Remote (US)</span>
                <p>Tech: Python, FastAPI, PostgreSQL, Kubernetes</p>
            </div>
            <div class="job-card" data-job-id="job-2">
                <h3><a href="/jobs/2">Autonomous Systems Lead</a></h3>
                <span class="job-dept">Robotics</span>
                <span class="job-loc">San Francisco</span>
                <p>Tech: C++, ROS2, Computer Vision, Docker</p>
            </div>
        </div>
    </body>
    </html>
    """
    extractor = BrowserEvidenceExtractor()
    base_facts, career_facts = extractor.extract_rendered_page(
        rendered_html, page_url="https://apex.ai/careers"
    )

    assert base_facts.page_title == "Apex AI Careers"
    assert career_facts["active_jobs_count"] == 2
    assert "Lead Python Engineer" in career_facts["job_titles"]
    assert "Autonomous Systems Lead" in career_facts["job_titles"]
    assert "Backend Engineering" in career_facts["hiring_departments"]
    assert "Robotics" in career_facts["hiring_departments"]
    assert "Python" in career_facts["tech_stack_detected"]
    assert "C++" in career_facts["tech_stack_detected"]
    assert "FastAPI" in career_facts["tech_stack_detected"]
    assert "ROS2" in career_facts["tech_stack_detected"]
    assert career_facts["remote_friendly"] is True


# ==============================================================================
# 2. Playwright Live Browser Execution with Dynamic JS Fixture
# ==============================================================================

def test_browser_client_standard_user_agent_and_headers() -> None:
    """
    Verify that PlaywrightBrowserClient uses a realistic modern Chrome User-Agent
    without custom bot tokens and configures standard browser headers.
    """
    client = PlaywrightBrowserClient()
    assert "Mozilla/5.0" in client.user_agent
    assert "Chrome/124.0.0.0" in client.user_agent
    assert "CompanyIntelligenceAgent" not in client.user_agent
    assert "bot" not in client.user_agent.lower()
    assert "crawler" not in client.user_agent.lower()


@pytest.mark.asyncio
async def test_playwright_renders_dynamic_javascript_content() -> None:
    """
    CRITICAL PROOF TEST:
    Demonstrates that static HTML parser sees only 'Loading dynamic open positions...',
    while Playwright executes JavaScript to render actual job cards.
    """
    assert DYNAMIC_JOBS_FILE.exists(), f"Missing fixture at {DYNAMIC_JOBS_FILE}"
    raw_html = DYNAMIC_JOBS_FILE.read_text(encoding="utf-8")

    # Step A: Static HTML parser (httpx/BS4 equivalent) without JS execution
    static_extractor = HtmlEvidenceExtractor()
    static_facts = static_extractor.extract(raw_html, base_url="http://localhost")
    assert "Loading dynamic open positions" in static_facts.main_text_snippet
    assert "Senior Backend Engineer" not in static_facts.main_text_snippet

    # Step B: Playwright Browser execution with full JavaScript evaluation
    file_url = DYNAMIC_JOBS_FILE.as_uri()
    browser_client = PlaywrightBrowserClient(headless=True, hydration_wait_ms=300)

    try:
        status_code, rendered_html, page_title, _, duration_ms = (
            await browser_client.render_page(file_url, wait_for_selector=".job-card")
        )

        assert status_code == 200
        assert "Quantum Robotics" in page_title
        assert duration_ms > 0

        # Step C: Extract dynamic facts from rendered DOM
        browser_extractor = BrowserEvidenceExtractor()
        base_facts, career_facts = browser_extractor.extract_rendered_page(rendered_html, file_url)

        # Verified JavaScript executed and populated DOM
        assert career_facts["active_jobs_count"] == 3
        assert "Senior Backend Engineer" in career_facts["job_titles"]
        assert "Robotics Control Specialist" in career_facts["job_titles"]
        assert "Staff Data Platform Engineer" in career_facts["job_titles"]
        assert "Python" in career_facts["tech_stack_detected"]
        assert "FastAPI" in career_facts["tech_stack_detected"]
        assert "ROS2" in career_facts["tech_stack_detected"]
        assert "PostgreSQL" in career_facts["tech_stack_detected"]
        assert career_facts["remote_friendly"] is True

    finally:
        await browser_client.close()


@pytest.mark.asyncio
async def test_browser_enricher_end_to_end_with_local_fixture(db_session: AsyncSession) -> None:
    """Test BrowserEnricher collecting dynamic facts and persisting Signal in PostgreSQL."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Quantum Robotics",
        website_url=DYNAMIC_JOBS_FILE.as_uri(),
        sheet_row_id="row_playwright_test",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    browser_client = PlaywrightBrowserClient(headless=True, hydration_wait_ms=300)
    browser_enricher = BrowserEnricher(browser_client=browser_client)
    service = HttpEnrichmentService(session=db_session, browser_enricher=browser_enricher)

    try:
        result = await service.enrich_company_with_browser(company.id, fetch_careers_page=False)

        assert result.success is True
        assert len(result.signals_collected) == 1
        signal_res = result.signals_collected[0]
        assert signal_res.signal_type == SignalType.BROWSER_CAREERS
        assert signal_res.status == SignalStatus.SUCCESS

        # Verify Signal persisted in PostgreSQL
        signals = await SignalRepository.list_by_company(db_session, company.id)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == SignalType.BROWSER_CAREERS
        assert sig.status == SignalStatus.SUCCESS
        assert sig.raw_data["browser_engine"] == "Playwright Chromium (Headless)"

        # Verify Company updated to ENRICHED
        updated_company = await CompanyRepository.get_by_id(db_session, company.id)
        assert updated_company.status == CompanyStatus.ENRICHED

    finally:
        await browser_enricher.close()


@pytest.mark.asyncio
async def test_browser_enricher_handles_invalid_url() -> None:
    """Test that unreachable / invalid URLs return a structured failed signal rather than crashing."""
    browser_client = PlaywrightBrowserClient(headless=True, navigation_timeout_ms=3000)
    browser_enricher = BrowserEnricher(browser_client=browser_client)

    try:
        signal = await browser_enricher.collect(
            url="http://invalid-non-existent-domain-12345.xyz",
            company_name="Ghost Co",
            fetch_careers_page=False,
        )

        assert signal.signal_type == SignalType.BROWSER_CAREERS
        assert signal.status == SignalStatus.FAILED
        assert signal.error_message is not None
        assert "error" in signal.extracted_facts

    finally:
        await browser_enricher.close()
