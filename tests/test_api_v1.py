from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SignalStatus,
    SignalType,
    SyncDirection,
    SyncStatus,
    TriggerType,
)
from app.database.models import Company, PipelineRun, Signal, SyncLog, Verdict
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SignalRepository,
    SyncLogRepository,
    VerdictRepository,
)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Provide valid authentication headers using test configuration."""
    settings = get_settings()
    return {"X-API-Key": settings.api_key}


# ==============================================================================
# 1. Health Probe Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_check_detailed_dependencies(async_client: AsyncClient) -> None:
    """Test GET /health returns dependencies status."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "dependencies" in data
    assert "database" in data["dependencies"]
    assert data["dependencies"]["database"]["status"] == "connected"
    assert "browser_engine" in data["dependencies"]
    assert "llm_provider" in data["dependencies"]
    assert "google_sheets" in data["dependencies"]


# ==============================================================================
# 2. Pipeline Execution & Status Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_trigger_run_success_accepted(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /run triggers background run and returns 202 Accepted."""
    response = await async_client.post(
        "/run",
        json={"batch_size": 15, "skip_ingestion": True},
        headers=auth_headers,
    )
    assert response.status_code == 202

    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"
    assert data["batch_size"] == 15
    assert "links" in data
    assert data["links"]["status_url"] == f"/runs/{data['run_id']}"


@pytest.mark.asyncio
async def test_trigger_run_unauthorized(async_client: AsyncClient) -> None:
    """Test POST /run returns 401 Unauthorized without API key."""
    response = await async_client.post(
        "/run",
        json={"batch_size": 10},
        headers={"X-API-Key": "wrong-insecure-key"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_trigger_run_bearer_token_auth(
    async_client: AsyncClient,
) -> None:
    """Test POST /run supports Authorization: Bearer <key> header."""
    settings = get_settings()
    response = await async_client.post(
        "/run",
        json={"skip_ingestion": True},
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_trigger_run_conflict_when_already_running(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /run returns 409 Conflict if an active run is in progress."""
    await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
    )
    await db_session.commit()

    response = await async_client.post(
        "/run",
        json={"batch_size": 10},
        headers=auth_headers,
    )
    assert response.status_code == 409
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_get_run_status_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /runs/{run_id} returns detailed run telemetry."""
    run = await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.COMPLETED,
    )
    await PipelineRunRepository.update_counters(
        session=db_session,
        run_id=run.id,
        total_companies=5,
        processed_count=5,
        success_count=4,
        failed_extraction_count=1,
        synced_count=4,
        fit_yes_count=2,
        fit_no_count=2,
    )
    await db_session.commit()

    response = await async_client.get(f"/runs/{run.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == str(run.id)
    assert data["status"] == "COMPLETED"
    assert data["metrics"]["total_companies_discovered"] == 5
    assert data["metrics"]["success_count"] == 4
    assert data["summary"]["fit_yes"] == 2


@pytest.mark.asyncio
async def test_get_run_status_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /runs/{run_id} returns 404 for non-existent run ID."""
    random_id = uuid.uuid4()
    response = await async_client.get(f"/runs/{random_id}", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ENTITY_NOT_FOUND"


# ==============================================================================
# 3. Company Listing & Filtering Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_companies_pagination_and_verdicts(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /companies returns paginated list with attached verdicts."""
    co = await CompanyRepository.create(
        session=db_session,
        name="Acme Quantum Corp",
        website_url="https://acmequantum.com",
        domain="acmequantum.com",
        sheet_row_id="row_10",
        status=CompanyStatus.SYNCED,
    )
    await VerdictRepository.create(
        session=db_session,
        company_id=co.id,
        fit=FitDecision.YES,
        confidence=0.94,
        reasoning=["Quantum computing SDK for logistics."],
        follow_up_question="What quantum backends are supported?",
    )
    await db_session.commit()

    response = await async_client.get("/companies?limit=10&offset=0", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1

    item = [c for c in data["items"] if c["name"] == "Acme Quantum Corp"][0]
    assert item["status"] == "SYNCED"
    assert item["latest_verdict"] is not None
    assert item["latest_verdict"]["fit"] == "YES"
    assert item["latest_verdict"]["confidence"] == 0.94


@pytest.mark.asyncio
async def test_list_companies_search_and_status_filtering(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /companies with status and text search query filters."""
    await CompanyRepository.create(session=db_session, name="Skyline AI", website_url="https://skyline.ai", domain="skyline.ai", sheet_row_id="row_20", status=CompanyStatus.PENDING)
    await CompanyRepository.create(session=db_session, name="Deepsea Tech", website_url="https://deepsea.io", domain="deepsea.io", sheet_row_id="row_21", status=CompanyStatus.JUDGED)
    await db_session.commit()

    # Search by keyword
    resp_search = await async_client.get("/companies?search=Skyline", headers=auth_headers)
    assert resp_search.status_code == 200
    search_data = resp_search.json()
    assert any(c["name"] == "Skyline AI" for c in search_data["items"])
    assert not any(c["name"] == "Deepsea Tech" for c in search_data["items"])

    # Filter by status
    resp_status = await async_client.get("/companies?status=PENDING", headers=auth_headers)
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert any(c["name"] == "Skyline AI" for c in status_data["items"])


# ==============================================================================
# 4. Single Company Detail & Retry Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_company_detail_full_entity(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /companies/{company_id} returns all signals, verdicts, and sync logs."""
    co = await CompanyRepository.create(
        session=db_session,
        name="Nexus BioTech",
        website_url="https://nexusbio.com",
        sheet_row_id="row_12",
        status=CompanyStatus.SYNCED,
    )
    await SignalRepository.create(
        session=db_session,
        company_id=co.id,
        signal_type=SignalType.HTTP_WEBSITE,
        status=SignalStatus.SUCCESS,
        source_url="https://nexusbio.com",
        extracted_facts={"title": "Nexus BioTech Homepage"},
    )
    await VerdictRepository.create(
        session=db_session,
        company_id=co.id,
        fit=FitDecision.NO,
        confidence=0.89,
        reasoning=["Biotech pharmaceuticals focus."],
    )
    await SyncLogRepository.create(
        session=db_session,
        company_id=co.id,
        sync_direction=SyncDirection.DB_TO_SHEET,
        status=SyncStatus.SUCCESS,
    )
    await db_session.commit()

    response = await async_client.get(f"/companies/{co.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(co.id)
    assert data["name"] == "Nexus BioTech"
    assert len(data["signals"]) == 1
    assert data["latest_verdict"]["fit"] == "NO"
    assert len(data["sync_logs"]) == 1


@pytest.mark.asyncio
async def test_get_company_detail_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test GET /companies/{company_id} returns 404 for missing company ID."""
    random_id = uuid.uuid4()
    response = await async_client.get(f"/companies/{random_id}", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_retry_company_evaluation_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /companies/{company_id}/retry enqueues single company re-evaluation."""
    co = await CompanyRepository.create(
        session=db_session,
        name="Retry Test Corp",
        website_url="https://retrytest.com",
        sheet_row_id="row_15",
        status=CompanyStatus.FAILED,
    )
    await db_session.commit()

    response = await async_client.post(
        f"/companies/{co.id}/retry",
        json={"force_re_enrichment": True},
        headers=auth_headers,
    )
    assert response.status_code == 202

    data = response.json()
    assert data["company_id"] == str(co.id)
    assert data["status"] == "PROCESSING"
    assert "scheduled_at" in data


@pytest.mark.asyncio
async def test_create_company_manual_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /companies manually creates a new company record in PostgreSQL."""
    payload = {
        "name": "Manual Ingestion Corp",
        "website_url": "https://manual-ingest.com",
        "sheet_row_id": "api_101",
        "process_immediately": False,
    }
    response = await async_client.post("/companies", json=payload, headers=auth_headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Manual Ingestion Corp"
    assert data["website_url"] == "https://manual-ingest.com"
    assert data["domain"] == "manual-ingest.com"
    assert data["status"] == "PENDING"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_company_duplicate_conflict(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /companies returns 409 Conflict for duplicate website URL."""
    payload = {
        "name": "Duplicate Target Corp",
        "website_url": "https://duplicate-target.com",
    }
    res1 = await async_client.post("/companies", json=payload, headers=auth_headers)
    assert res1.status_code == 201

    res2 = await async_client.post("/companies", json=payload, headers=auth_headers)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_create_company_validation_error(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test POST /companies returns 422 Unprocessable Entity for invalid payload."""
    payload = {"name": "Missing Website Corp"}
    response = await async_client.post("/companies", json=payload, headers=auth_headers)
    assert response.status_code == 422


# ==============================================================================
# 5. Pipeline Run Concurrency & Lifecycle Regression Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_completed_run_does_not_block_subsequent_run(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test that a completed pipeline run does not block subsequent POST /run requests."""
    # 1. Create previous run in COMPLETED state
    await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.COMPLETED,
    )
    await db_session.commit()

    # 2. Trigger new run via POST /run
    response = await async_client.post(
        "/run",
        json={"skip_ingestion": True, "batch_size": 5},
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_failed_run_does_not_block_subsequent_run(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test that a failed pipeline run does not block subsequent POST /run requests."""
    # 1. Create previous run in FAILED state
    await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.FAILED,
    )
    await db_session.commit()

    # 2. Trigger new run via POST /run
    response = await async_client.post(
        "/run",
        json={"skip_ingestion": True, "batch_size": 5},
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_stale_orphaned_run_recovers_automatically(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test that an orphaned RUNNING record older than 30 minutes is automatically recovered."""
    # 1. Create a stale run started 45 minutes ago
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    stale_run = PipelineRun(
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
        started_at=stale_time,
    )
    db_session.add(stale_run)
    await db_session.commit()

    # 2. POST /run should recover the stale run and allow the new run to start
    response = await async_client.post(
        "/run",
        json={"skip_ingestion": True},
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"
    assert data["run_id"] != str(stale_run.id)

    # 3. Verify stale run was transitioned to FAILED
    refreshed_stale = await PipelineRunRepository.get_by_id(db_session, stale_run.id)
    assert refreshed_stale is not None
    assert refreshed_stale.status == PipelineRunStatus.FAILED
    assert refreshed_stale.error_summary is not None
    assert "stale_recovery" in refreshed_stale.error_summary
