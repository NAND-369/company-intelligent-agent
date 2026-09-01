# FastAPI REST API Specification

> **Status:** Approved API Specification  
> **Architecture Reference:** [`docs/ARCHITECTURE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/ARCHITECTURE.md)  
> **Pipeline Reference:** [`docs/PIPELINE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/PIPELINE.md)  
> **LLM Judge Reference:** [`docs/LLM_SPEC.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/LLM_SPEC.md)

---

## 1. Overview & Design Principles

The **Company Intelligence Agent REST API** provides a lightweight, purposeful HTTP interface for triggering evaluation runs, inspecting pipeline execution telemetry, and querying persisted company signals and verdicts.

### Key API Principles
- **Minimal & Purposeful:** Focused strictly on operational control, health monitoring, and data access.
- **Strict Security & Secret Isolation:** Database connection strings, LLM API keys, and Google OAuth credentials are NEVER exposed in any response body or error message.
- **Asynchronous Execution:** Heavy pipeline runs return `202 Accepted` with a trackable `run_id` to prevent HTTP timeouts.
- **Standardized Error Contracts:** Consistent JSON error envelopes for all 4xx/5xx responses.

---

## 2. Authentication & Authorization

All administrative and data endpoints are protected via an API Key mechanism.

| Mechanism | Header Format | Description |
| :--- | :--- | :--- |
| **API Key Header** | `X-API-Key: <SECRET_KEY>` | Primary authentication header validated against `API_KEY` configured in `.env`. |
| **Bearer Token (Fallback)** | `Authorization: Bearer <SECRET_KEY>` | Standard Bearer token alternative for automated HTTP clients. |

> [!NOTE]
> `GET /health` is the **only public endpoint** that does not require authentication, allowing cloud platform uptime checkers to probe service health.

---

## 3. Standard Error Response Schema

All error responses across all endpoints follow a uniform JSON structure:

```json
{
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "Company with ID '3fa85f64-5717-4562-b3fc-2c963f66afa6' was not found.",
    "details": null,
    "timestamp": "2026-09-01T20:15:00Z"
  }
}
```

---

## 4. API Endpoints

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            API ROUTE MAP                                    │
│                                                                             │
│  [PUBLIC]       GET   /health                                               │
│                                                                             │
│  [PROTECTED]    POST  /run                                                  │
│                 GET   /runs/{run_id}                                        │
│                 GET   /companies                                            │
│                 GET   /companies/{company_id}                               │
│                 POST  /companies/{company_id}/retry                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.1 `GET /health`

**Purpose:** Health check probe reporting system liveness and dependency readiness (PostgreSQL database connectivity, browser runtime status, and LLM configuration).

- **Method:** `GET`
- **Path:** `/health`
- **Authentication:** None (Public)

#### Request:
No request parameters or body.

#### Success Response (`200 OK`):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "dependencies": {
    "database": {
      "status": "connected",
      "latency_ms": 4
    },
    "browser_engine": {
      "status": "ready",
      "engine": "Chromium (Playwright)"
    },
    "llm_provider": {
      "status": "configured",
      "provider": "google-gemini"
    },
    "google_sheets": {
      "status": "authenticated"
    }
  },
  "timestamp": "2026-09-01T20:15:00Z"
}
```

#### Degraded Response (`503 Service Unavailable`):
```json
{
  "status": "unhealthy",
  "version": "1.0.0",
  "dependencies": {
    "database": {
      "status": "disconnected",
      "error": "Connection timeout to PostgreSQL server"
    }
  },
  "timestamp": "2026-09-01T20:15:00Z"
}
```

---

### 4.2 `POST /run`

**Purpose:** Trigger an on-demand batch pipeline run. Ingests unprocessed/new company rows from Google Sheets, acquires a processing lease lock, and begins asynchronous enrichment and evaluation.

- **Method:** `POST`
- **Path:** `/run`
- **Authentication:** Required (`X-API-Key`)

#### Request Body (Optional):
```json
{
  "batch_size": 10,
  "force_reprocess": false
}
```

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `batch_size` | integer | No | `20` | Max number of pending companies to process in this run (1–50). |
| `force_reprocess` | boolean | No | `false` | If `true`, re-evaluates companies even if previously marked `SYNCED`. |

#### Success Response (`202 Accepted`):
```json
{
  "run_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "status": "RUNNING",
  "message": "Pipeline run initiated successfully.",
  "batch_size": 10,
  "triggered_at": "2026-09-01T20:15:00Z",
  "links": {
    "status_url": "/runs/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
  }
}
```

#### Status Codes & Errors:
- `202 Accepted`: Run successfully enqueued and started in the background.
- `401 Unauthorized`: Missing or invalid `X-API-Key`.
- `409 Conflict`: Another pipeline run is actively in progress.
  ```json
  {
    "error": {
      "code": "PIPELINE_RUN_IN_PROGRESS",
      "message": "A pipeline run is already in progress with ID '9f8e7d6c-5b4a-3f2e-1d0c-9b8a7f6e5d4c'.",
      "timestamp": "2026-09-01T20:15:00Z"
    }
  }
  ```

---

### 4.3 `GET /runs/{run_id}`

**Purpose:** Expose real-time and historical execution status, progress counters, and execution metrics for a specific pipeline run.

- **Method:** `GET`
- **Path:** `/runs/{run_id}`
- **Authentication:** Required (`X-API-Key`)

#### Path Parameters:
- `run_id` (UUID, required): The unique identifier returned when the run was triggered.

#### Success Response (`200 OK`):
```json
{
  "run_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "status": "COMPLETED",
  "trigger_source": "ON_DEMAND_API",
  "started_at": "2026-09-01T20:15:00Z",
  "completed_at": "2026-09-01T20:16:15Z",
  "duration_seconds": 75.4,
  "metrics": {
    "total_companies_discovered": 10,
    "processed_count": 10,
    "success_count": 9,
    "failed_extraction_count": 1,
    "failed_evaluation_count": 0,
    "synced_to_sheet_count": 9
  },
  "summary": {
    "fit_yes": 4,
    "fit_no": 4,
    "fit_uncertain": 1
  },
  "errors": [
    {
      "company_id": "b3c4d5e6-f7a8-9b0c-1d2e-3f4a5b6c7d8e",
      "company_name": "Dead Domain LLC",
      "stage": "ENRICHMENT",
      "error_message": "DNS resolution failed: NXDOMAIN"
    }
  ]
}
```

#### Allowed `status` Values:
- `PENDING`: Enqueued and initializing.
- `RUNNING`: Actively processing company batch.
- `COMPLETED`: All companies processed successfully.
- `PARTIAL_FAILURE`: Completed, but some companies failed extraction/evaluation.
- `FAILED`: Fatal unrecoverable pipeline failure (e.g. Google Sheets authentication failure).

#### Status Codes & Errors:
- `200 OK`: Telemetry returned.
- `401 Unauthorized`: Missing or invalid `X-API-Key`.
- `404 Not Found`: No run found with the provided `run_id`.

---

### 4.4 `GET /companies`

**Purpose:** Query persisted companies with pagination, status filters, and search capabilities.

- **Method:** `GET`
- **Path:** `/companies`
- **Authentication:** Required (`X-API-Key`)

#### Query Parameters:
| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `status` | string | No | null | Filter by status (`PENDING`, `PROCESSING`, `EVALUATED`, `SYNCED`, `FAILED`). |
| `fit` | string | No | null | Filter by latest fit call (`YES`, `NO`, `UNCERTAIN`). |
| `search` | string | No | null | Case-insensitive substring search on company name or website domain. |
| `limit` | integer | No | `20` | Number of records to return (1–100). |
| `offset` | integer | No | `0` | Pagination offset. |

#### Success Response (`200 OK`):
```json
{
  "total": 45,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Acme Software",
      "website_url": "https://acme.io",
      "domain": "acme.io",
      "status": "SYNCED",
      "created_at": "2026-09-01T19:30:00Z",
      "latest_verdict": {
        "fit": "YES",
        "confidence": 0.92,
        "reasoning": [
          "Enterprise B2B pricing model with explicit multi-tenant support.",
          "Careers page lists 6 active backend/cloud engineering positions.",
          "Verified enterprise mail infrastructure on Google Workspace."
        ],
        "follow_up_question": "What is their current integration roadmap with existing ERP systems?",
        "evaluated_at": "2026-09-01T19:31:10Z"
      }
    }
  ]
}
```

#### Status Codes & Errors:
- `200 OK`: List returned successfully.
- `400 Bad Request`: Invalid filter parameters (e.g. invalid status enum).
- `401 Unauthorized`: Missing or invalid `X-API-Key`.

---

### 4.5 `GET /companies/{company_id}`

**Purpose:** Retrieve complete details for a single company, including all raw signals, DOM extracts, verdict history, and sync audit logs.

- **Method:** `GET`
- **Path:** `/companies/{company_id}`
- **Authentication:** Required (`X-API-Key`)

#### Path Parameters:
- `company_id` (UUID, required): The internal unique identifier of the company.

#### Success Response (`200 OK`):
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Acme Software",
  "website_url": "https://acme.io",
  "domain": "acme.io",
  "sheet_row_id": "Row_14",
  "status": "SYNCED",
  "created_at": "2026-09-01T19:30:00Z",
  "updated_at": "2026-09-01T19:31:15Z",
  "signals": [
    {
      "signal_type": "HTTP_WEBSITE",
      "status": "SUCCESS",
      "source_url": "https://acme.io",
      "duration_ms": 420,
      "extracted_facts": {
        "page_title": "Acme - Enterprise Cloud Platform",
        "value_proposition": "Automated workflow orchestration for supply chain operations.",
        "headings": ["Real-time Tracking", "Fleet Automation", "API Docs"]
      },
      "collected_at": "2026-09-01T19:30:15Z"
    },
    {
      "signal_type": "BROWSER_CAREERS",
      "status": "SUCCESS",
      "source_url": "https://acme.io/careers",
      "duration_ms": 3410,
      "extracted_facts": {
        "careers_page_found": true,
        "active_jobs_count": 6,
        "hiring_departments": {
          "Engineering": 4,
          "Sales": 2
        },
        "tech_stack_detected_in_jobs": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"]
      },
      "collected_at": "2026-09-01T19:30:20Z"
    },
    {
      "signal_type": "EXTERNAL_METADATA",
      "status": "SUCCESS",
      "source_url": "acme.io",
      "duration_ms": 110,
      "extracted_facts": {
        "mail_provider": "Google Workspace",
        "has_dmarc_record": true,
        "tls_issuer": "Let's Encrypt"
      },
      "collected_at": "2026-09-01T19:30:21Z"
    }
  ],
  "latest_verdict": {
    "id": "7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
    "fit": "YES",
    "confidence": 0.92,
    "reasoning": [
      "Enterprise B2B pricing model with explicit multi-tenant support.",
      "Careers page lists 6 active backend/cloud engineering positions.",
      "Verified enterprise mail infrastructure on Google Workspace."
    ],
    "follow_up_question": "What is their current integration roadmap with existing ERP systems?",
    "rubric_version": "1.0.0",
    "evaluated_at": "2026-09-01T19:30:30Z"
  }
}
```

#### Status Codes & Errors:
- `200 OK`: Full company detail returned.
- `401 Unauthorized`: Missing or invalid `X-API-Key`.
- `404 Not Found`: No company found matching `company_id`.

---

### 4.6 `POST /companies/{company_id}/retry`

**Purpose:** Trigger an immediate, isolated re-evaluation for a single company record (e.g. following an extraction or evaluation failure).

- **Method:** `POST`
- **Path:** `/companies/{company_id}/retry`
- **Authentication:** Required (`X-API-Key`)

#### Path Parameters:
- `company_id` (UUID, required): The target company ID to reprocess.

#### Request Body (Optional):
```json
{
  "force_re_enrichment": true
}
```

#### Success Response (`202 Accepted`):
```json
{
  "company_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "PROCESSING",
  "message": "Company scheduled for re-evaluation.",
  "scheduled_at": "2026-09-01T20:15:00Z"
}
```

#### Status Codes & Errors:
- `202 Accepted`: Re-evaluation enqueued.
- `401 Unauthorized`: Missing or invalid `X-API-Key`.
- `404 Not Found`: Company not found.
- `409 Conflict`: Company is currently in `PROCESSING` state.

---
*End of API Specification.*
