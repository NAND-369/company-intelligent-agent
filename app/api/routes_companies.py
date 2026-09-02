"""FastAPI routes for querying company records, signals, verdicts, and triggering retries."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.session as session_module
from app.api.auth import require_api_key
from app.api.schemas import (
    CompanyCreateRequest,
    CompanyCreateResponse,
    CompanyDetailResponse,
    CompanyListItem,
    CompanyListResponse,
    CompanyRetryRequest,
    CompanyRetryResponse,
    CompanyVerdictSummary,
    SignalDetail,
    SyncLogDetail,
)
from app.database.enums import CompanyStatus, FitDecision
from app.database.models import Company
from app.database.repositories import (
    CompanyRepository,
    SignalRepository,
    SyncLogRepository,
    VerdictRepository,
)
from app.database.session import get_db_session
from app.pipeline.company_processor import CompanyProcessor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["Companies"])


async def _retry_company_background(
    company_id: uuid.UUID,
    force_re_enrichment: bool,
) -> None:
    """Execute single-company re-processing in a dedicated background async task."""
    logger.info("Executing background retry for company_id=%s (force_re_enrichment=%s)", company_id, force_re_enrichment)
    try:
        async with session_module.async_session_factory() as session:
            company = await CompanyRepository.get_by_id(session, company_id)
            if not company:
                logger.error("Company %s not found for retry.", company_id)
                return

            processor = CompanyProcessor(session=session)
            await processor.process_company(company)
            await session.commit()
    except Exception as exc:
        logger.exception("Error executing background retry for company %s: %s", company_id, exc)


@router.get(
    "",
    response_model=CompanyListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Companies",
    description="Retrieve paginated list of companies with optional status and text search filtering.",
)
async def list_companies(
    status_filter: Optional[CompanyStatus] = Query(None, alias="status", description="Filter by company processing status"),
    fit_filter: Optional[FitDecision] = Query(None, alias="fit", description="Filter by latest fit evaluation verdict"),
    search: Optional[str] = Query(None, description="Substring search on company name or domain"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> CompanyListResponse:
    """Query company records with pagination and evaluation summaries."""
    companies, total = await CompanyRepository.list_companies(
        session=session,
        status=status_filter,
        search=search,
        limit=limit,
        offset=offset,
    )

    items: list[CompanyListItem] = []
    for company in companies:
        verdict = await VerdictRepository.get_latest_by_company(session, company.id)
        if fit_filter and (not verdict or verdict.fit != fit_filter):
            continue

        verdict_summary = None
        if verdict:
            verdict_summary = CompanyVerdictSummary(
                id=verdict.id,
                fit=verdict.fit,
                confidence=verdict.confidence,
                reasoning=verdict.reasoning if isinstance(verdict.reasoning, list) else [str(verdict.reasoning)],
                follow_up_question=verdict.follow_up_question,
                rubric_version=verdict.rubric_version,
                evaluated_at=verdict.evaluated_at,
            )

        items.append(
            CompanyListItem(
                id=company.id,
                name=company.name,
                website_url=company.website_url,
                domain=company.domain,
                sheet_row_id=company.sheet_row_id,
                status=company.status,
                created_at=company.created_at,
                latest_verdict=verdict_summary,
            )
        )

    return CompanyListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get(
    "/{company_id}",
    response_model=CompanyDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Company Details",
    description="Retrieve full company entity including raw signals, verdict, and sync logs.",
)
async def get_company_detail(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> CompanyDetailResponse:
    """Query complete detail view for a specific company."""
    company = await CompanyRepository.get_by_id(session, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' was not found.",
        )

    signals = await SignalRepository.list_by_company(session, company.id)
    latest_verdict = await VerdictRepository.get_latest_by_company(session, company.id)
    sync_logs = await SyncLogRepository.list_by_company(session, company.id)

    verdict_summary = None
    if latest_verdict:
        verdict_summary = CompanyVerdictSummary(
            id=latest_verdict.id,
            fit=latest_verdict.fit,
            confidence=latest_verdict.confidence,
            reasoning=latest_verdict.reasoning if isinstance(latest_verdict.reasoning, list) else [str(latest_verdict.reasoning)],
            follow_up_question=latest_verdict.follow_up_question,
            rubric_version=latest_verdict.rubric_version,
            evaluated_at=latest_verdict.evaluated_at,
        )

    signal_details = [
        SignalDetail(
            signal_type=s.signal_type.value if hasattr(s.signal_type, "value") else str(s.signal_type),
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            source_url=s.source_url,
            extracted_facts=s.extracted_facts if isinstance(s.extracted_facts, dict) else {},
            error_message=s.error_message,
            collected_at=s.collected_at,
        )
        for s in signals
    ]

    sync_log_details = [
        SyncLogDetail(
            id=log.id,
            sync_direction=log.sync_direction.value if hasattr(log.sync_direction, "value") else str(log.sync_direction),
            status=log.status.value if hasattr(log.status, "value") else str(log.status),
            error_details=log.error_details,
            synced_at=log.synced_at,
        )
        for log in sync_logs
    ]

    return CompanyDetailResponse(
        id=company.id,
        name=company.name,
        website_url=company.website_url,
        domain=company.domain,
        sheet_row_id=company.sheet_row_id,
        status=company.status,
        created_at=company.created_at,
        updated_at=company.updated_at,
        signals=signal_details,
        latest_verdict=verdict_summary,
        sync_logs=sync_log_details,
    )


@router.post(
    "",
    response_model=CompanyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Company",
    description="Manually ingest a new company into PostgreSQL for pipeline intelligence processing.",
)
async def create_company(
    company_in: CompanyCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> CompanyCreateResponse:
    """Register a new company and optionally enqueue immediate evaluation."""
    clean_url = company_in.website_url.strip()
    clean_name = company_in.name.strip()

    # Extract domain
    domain = None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(clean_url if "://" in clean_url else f"https://{clean_url}")
        domain = parsed.netloc.lower().replace("www.", "") if parsed.netloc else None
    except Exception:
        pass

    # Check for existing company by normalized website URL or domain
    existing = await CompanyRepository.get_by_website(session, clean_url)
    if not existing and domain:
        from sqlalchemy import select
        existing_res = await session.execute(select(Company).where(Company.domain == domain))
        existing = existing_res.scalars().first()

    if existing:
        latest_verdict = await VerdictRepository.get_latest_by_company(session, existing.id)
        verdict_dict = None
        if latest_verdict:
            verdict_dict = {
                "fit": latest_verdict.fit.value if hasattr(latest_verdict.fit, "value") else str(latest_verdict.fit),
                "confidence": latest_verdict.confidence,
                "confidence_rationale": latest_verdict.confidence_rationale,
                "reasoning": latest_verdict.reasoning if isinstance(latest_verdict.reasoning, list) else [str(latest_verdict.reasoning)],
                "follow_up_question": latest_verdict.follow_up_question,
                "evaluated_at": latest_verdict.evaluated_at.isoformat() if latest_verdict.evaluated_at else None,
            }

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"{existing.name} already exists.",
                "duplicate": True,
                "company_id": str(existing.id),
                "name": existing.name,
                "website_url": existing.website_url,
                "status": existing.status.value if hasattr(existing.status, "value") else str(existing.status),
                "has_result": bool(latest_verdict is not None and latest_verdict.fit),
                "latest_verdict": verdict_dict,
            },
        )

    company = await CompanyRepository.create(
        session=session,
        name=clean_name,
        website_url=clean_url,
        domain=domain,
        sheet_row_id=company_in.sheet_row_id,
        status=CompanyStatus.PENDING,
    )
    await session.commit()

    if company_in.process_immediately:
        asyncio.create_task(_retry_company_background(company.id, force_re_enrichment=True))

    return CompanyCreateResponse(
        id=company.id,
        name=company.name,
        website_url=company.website_url,
        domain=company.domain,
        sheet_row_id=company.sheet_row_id,
        status=company.status,
        created_at=company.created_at,
        message="Company registered successfully and queued for intelligence processing.",
    )


@router.post(
    "/{company_id}/retry",
    response_model=CompanyRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry Company Evaluation",
    description="Trigger an immediate, isolated re-evaluation for a single company.",
)
async def retry_company(
    company_id: uuid.UUID,
    options: CompanyRetryRequest = CompanyRetryRequest(),
    session: AsyncSession = Depends(get_db_session),
    _auth: bool = Depends(require_api_key),
) -> CompanyRetryResponse:
    """Reset company processing lease and trigger single-company re-evaluation."""
    req = options
    company = await CompanyRepository.get_by_id(session, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' was not found.",
        )

    # Check if actively processing under unexpired lease
    now = datetime.now(timezone.utc)
    if company.status == CompanyStatus.PROCESSING and company.lease_expires_at and company.lease_expires_at > now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company '{company.name}' is currently in PROCESSING state with an active lease.",
        )

    # Reset company to PENDING
    await CompanyRepository.update_status(session, company.id, CompanyStatus.PENDING)
    await session.commit()

    # Dispatch background retry task
    asyncio.create_task(_retry_company_background(company.id, req.force_re_enrichment))

    return CompanyRetryResponse(
        company_id=company.id,
        status="PROCESSING",
        message="Company scheduled for re-evaluation.",
        scheduled_at=datetime.now(timezone.utc),
    )
