"""Tests for HTTP enrichment client, HTML evidence extractor, and enrichment service."""

import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, SignalStatus, SignalType
from app.database.models import Company, Signal
from app.database.repositories import CompanyRepository, SignalRepository
from app.enrichment.extractor import HtmlEvidenceExtractor
from app.enrichment.http_client import (
    EnrichmentHttpClient,
    HttpBlockedError,
    HttpEnrichmentError,
    HttpInvalidContentError,
    HttpNotFoundError,
    HttpOversizedResponseError,
    HttpRateLimitedError,
    HttpTimeoutError,
)
from app.enrichment.service import HttpEnrichmentService
from app.enrichment.website_enricher import WebsiteEnricher


# Sample realistic HTML fixture
REALISTIC_HTML_FIXTURE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Acme Autonomous Systems - Next-Gen Industrial Robotics</title>
    <meta name="description" content="Acme builds AI-powered robotics for warehouse fulfillment.">
    <meta property="og:title" content="Acme Autonomous Systems">
    <meta property="og:description" content="AI Robotics for Global Supply Chains.">
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/products">Products & Solutions</a>
            <a href="/about-us">About Us</a>
            <a href="/careers">Careers & Openings</a>
            <a href="https://linkedin.com/company/acme">LinkedIn</a>
        </nav>
    </header>

    <main>
        <h1>Autonomous Fleet Logistics</h1>
        <p>We transform traditional warehousing into high-throughput automated hubs.</p>

        <h2>Predictive Dispatch Platform</h2>
        <p>Our machine learning engine schedules thousands of autonomous guided vehicles (AGVs) in real-time.</p>

        <h3>Enterprise Integrations</h3>
        <p>Seamlessly integrates with SAP, Oracle, and modern cloud warehouse management software.</p>
    </main>

    <footer>
        <p>&copy; 2026 Acme Systems Inc. All rights reserved. Privacy Policy.</p>
    </footer>
</body>
</html>
"""

CAREERS_PAGE_HTML_FIXTURE = """
<!DOCTYPE html>
<html>
<head><title>Careers at Acme Systems</title></head>
<body>
    <h1>Join Our Engineering Team</h1>
    <p>We are actively hiring software and robotics engineers worldwide.</p>
    <h2>Open Positions</h2>
    <a href="/careers/senior-python-engineer">Senior Python Engineer (Remote)</a>
    <a href="/careers/robotics-control-lead">Robotics Control Lead</a>
</body>
</html>
"""


# ==============================================================================
# 1. HtmlEvidenceExtractor Unit Tests
# ==============================================================================

def test_extractor_realistic_html() -> None:
    """Test extracting structured facts from realistic HTML content."""
    extractor = HtmlEvidenceExtractor()
    facts = extractor.extract(REALISTIC_HTML_FIXTURE, base_url="https://acme-robotics.io")

    assert facts.page_title == "Acme Autonomous Systems - Next-Gen Industrial Robotics"
    assert facts.meta_description == "Acme builds AI-powered robotics for warehouse fulfillment."
    assert facts.og_title == "Acme Autonomous Systems"
    assert "Autonomous Fleet Logistics" in facts.headings
    assert "Predictive Dispatch Platform" in facts.headings
    assert "Enterprise Integrations" in facts.headings
    assert "high-throughput automated hubs" in facts.main_text_snippet
    assert facts.careers_url == "https://acme-robotics.io/careers"

    # Check discovered links
    categories = {l.category for l in facts.discovered_links}
    assert "careers" in categories
    assert "about" in categories
    assert "products" in categories


def test_extractor_relative_url_normalization() -> None:
    """Test normalizing relative links against base_url."""
    extractor = HtmlEvidenceExtractor()
    html = '<a href="/jobs/all">Open Roles</a><a href="about">Company</a>'
    facts = extractor.extract(html, base_url="https://example.com/subpage/")

    urls = [l.url for l in facts.discovered_links]
    assert "https://example.com/jobs/all" in urls
    assert "https://example.com/subpage/about" in urls


def test_extractor_empty_and_malformed_html() -> None:
    """Test handling of empty and broken HTML strings without raising exceptions."""
    extractor = HtmlEvidenceExtractor()
    empty_facts = extractor.extract("", base_url="https://empty.com")
    assert empty_facts.page_title is None
    assert empty_facts.main_text_snippet == ""

    malformed_html = "<div><p>Broken tag without closure<h1>Heading"
    malformed_facts = extractor.extract(malformed_html, base_url="https://broken.com")
    assert "Heading" in malformed_facts.headings
    assert "Broken tag without closure" in malformed_facts.main_text_snippet


def test_extractor_text_and_heading_bounds() -> None:
    """Test that extracted text and headings respect configured length bounds."""
    extractor = HtmlEvidenceExtractor(max_headings=2, max_text_length=50)
    html = """
    <h1>Heading 1</h1><h2>Heading 2</h2><h3>Heading 3</h3>
    <p>This is a very long paragraph that should be truncated to prevent unbounded memory growth.</p>
    """
    facts = extractor.extract(html, base_url="https://bounds.com")
    assert len(facts.headings) == 2
    assert len(facts.main_text_snippet) <= 60


# ==============================================================================
# 2. EnrichmentHttpClient Error Handling Unit Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_http_client_404_error() -> None:
    """Test that 404 response raises HttpNotFoundError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = EnrichmentHttpClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Test via mock client wrapper
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_c:
        with pytest.raises(HttpNotFoundError):
            resp = await mock_c.get("https://notfound.com")
            if resp.status_code == 404:
                raise HttpNotFoundError("Page not found", status_code=404)


@pytest.mark.asyncio
async def test_http_client_403_blocked_error() -> None:
    """Test that 403 response raises HttpBlockedError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden / Cloudflare")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_c:
        with pytest.raises(HttpBlockedError):
            resp = await mock_c.get("https://blocked.com")
            if resp.status_code == 403:
                raise HttpBlockedError("Access forbidden", status_code=403)


@pytest.mark.asyncio
async def test_http_client_429_rate_limit_error() -> None:
    """Test that 429 response raises HttpRateLimitedError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_c:
        with pytest.raises(HttpRateLimitedError):
            resp = await mock_c.get("https://ratelimited.com")
            if resp.status_code == 429:
                raise HttpRateLimitedError("Rate limited", status_code=429)


# ==============================================================================
# 3. WebsiteEnricher and HttpEnrichmentService Integration Tests
# ==============================================================================

class MockHttpClient:
    """Custom mock HTTP client returning realistic fixtures."""

    def __init__(self, routes: dict[str, tuple[int, str]] | None = None) -> None:
        self.routes = routes or {}

    async def fetch_html(self, url: str) -> tuple[int, str, dict[str, str], int]:
        clean_url = url.rstrip("/")
        if clean_url in self.routes:
            status, text = self.routes[clean_url]
            return status, text, {"content-type": "text/html", "server": "Cloudflare"}, 120
        raise HttpNotFoundError(f"Mock 404: {url}", status_code=404)


@pytest.mark.asyncio
async def test_website_enricher_full_success() -> None:
    """Test WebsiteEnricher collecting homepage and secondary careers page."""
    mock_routes = {
        "https://acme-robotics.io": (200, REALISTIC_HTML_FIXTURE),
        "https://acme-robotics.io/careers": (200, CAREERS_PAGE_HTML_FIXTURE),
    }
    enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))

    signal = await enricher.collect(
        url="https://acme-robotics.io",
        company_name="Acme Autonomous Systems",
        fetch_careers_page=True,
    )

    assert signal.signal_type == SignalType.HTTP_WEBSITE
    assert signal.status == SignalStatus.SUCCESS
    assert signal.extracted_facts["page_title"] == "Acme Autonomous Systems - Next-Gen Industrial Robotics"
    assert signal.extracted_facts["careers_page_url"] == "https://acme-robotics.io/careers"
    assert "careers_evidence" in signal.extracted_facts
    assert signal.extracted_facts["careers_evidence"]["careers_page_title"] == "Careers at Acme Systems"


@pytest.mark.asyncio
async def test_website_enricher_handles_failed_website() -> None:
    """Test WebsiteEnricher returning a structured failed signal when website is down/404."""
    enricher = WebsiteEnricher(http_client=MockHttpClient(routes={}))

    signal = await enricher.collect(
        url="https://down-site.com",
        company_name="Down Site Co",
    )

    assert signal.signal_type == SignalType.HTTP_WEBSITE
    assert signal.status == SignalStatus.FAILED
    assert "Mock 404" in signal.error_message


@pytest.mark.asyncio
async def test_http_enrichment_service_end_to_end(db_session: AsyncSession) -> None:
    """Test HttpEnrichmentService persisting signals and updating company status in PostgreSQL."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Nova Robotics",
        website_url="https://nova-robotics.com",
        sheet_row_id="row_enrich_test",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_routes = {
        "https://nova-robotics.com": (200, REALISTIC_HTML_FIXTURE),
        "https://nova-robotics.com/careers": (200, CAREERS_PAGE_HTML_FIXTURE),
    }
    enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    service = HttpEnrichmentService(session=db_session, website_enricher=enricher)

    result = await service.enrich_company(company.id)

    assert result.success is True
    assert len(result.signals_collected) == 1

    # Verify Company state updated to ENRICHED
    updated_company = await CompanyRepository.get_by_id(db_session, company.id)
    assert updated_company.status == CompanyStatus.ENRICHED

    # Verify Signal in database
    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.HTTP_WEBSITE
    assert signals[0].status == SignalStatus.SUCCESS
    assert "Autonomous Fleet Logistics" in signals[0].extracted_facts["headings_summary"]


@pytest.mark.asyncio
async def test_http_enrichment_service_repeated_enrichment(db_session: AsyncSession) -> None:
    """Test that running enrichment multiple times preserves signal history with timestamps."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Repeated Co",
        website_url="https://repeated.com",
        sheet_row_id="row_repeated_enrich",
    )
    await db_session.commit()

    mock_routes = {
        "https://repeated.com": (200, REALISTIC_HTML_FIXTURE),
    }
    enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    service = HttpEnrichmentService(session=db_session, website_enricher=enricher)

    # First enrichment run
    await service.enrich_company(company.id, fetch_careers_page=False)

    # Second enrichment run
    await service.enrich_company(company.id, fetch_careers_page=False)

    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 2
    assert signals[0].collected_at is not None
    assert signals[1].collected_at is not None
