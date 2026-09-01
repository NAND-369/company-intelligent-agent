# Development Phases & Implementation Roadmap

> **Status:** Approved Implementation Blueprint  
> **Architecture Reference:** [`docs/ARCHITECTURE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/ARCHITECTURE.md)  
> **Pipeline Reference:** [`docs/PIPELINE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/PIPELINE.md)  
> **System Requirements:** [`docs/PROJECT_SPEC.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/PROJECT_SPEC.md)

---

## Overview & Execution Rules

This document defines the strictly ordered, incremental implementation phases for the **Company Intelligence Agent**.

### Strict Implementation Rules
1. **Zero Premature Implementation:** A phase must NEVER implement components, abstractions, or routes that belong to future phases.
2. **Incremental Verification:** Every phase must produce working, testable code and satisfy its acceptance criteria before proceeding.
3. **No Third-Party Paid Crawlers:** `Firecrawl` is strictly excluded; all extraction is built using `httpx`, `BeautifulSoup`, and `Playwright`.
4. **Configurable Business Logic:** No business criteria for "fit" may be hardcoded.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      15-PHASE INCREMENTAL ROADMAP                           │
│                                                                             │
│  [PHASE 01] Project Foundation          ▶  [PHASE 02] Database Layer        │
│  [PHASE 03] Google Sheets Ingestion     ▶  [PHASE 04] HTTP Enrichment       │
│  [PHASE 05] Playwright Enrichment       ▶  [PHASE 06] LLM Judge Engine      │
│  [PHASE 07] Pipeline Orchestration      ▶  [PHASE 08] Google Sheets Sync    │
│  [PHASE 09] FastAPI API & Scheduling    ▶  [PHASE 10] Testing & Reliability │
│  [PHASE 11] Docker Containerization     ▶  [PHASE 12] Cloud Deployment      │
│  [PHASE 13] GitHub Actions Automation   ▶  [PHASE 14] Observability         │
│  [PHASE 15] Final Audit & Demo Video                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## PHASE 1: Project Foundation

### Objective
Establish the repository structure, Python package layout, dependency management, configuration loading via `pydantic-settings`, structured logging, and base application scaffolding.

- **Inputs:** `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`.
- **Outputs:** Verified Python virtual environment, package structure, configuration loader, and logging foundation.
- **Files Expected to Change:**
  - `pyproject.toml` / `requirements.txt`
  - `.env.example`
  - `.gitignore`
  - `app/__init__.py`
  - `app/core/__init__.py`
  - `app/core/config.py` (Pydantic `Settings`)
  - `app/core/logging.py`
  - `config/rubric.yaml` (Base rubric configuration template)
- **Dependencies:** `python >= 3.11`, `pydantic >= 2.0`, `pydantic-settings`, `pyyaml`, `python-dotenv`.
- **Tests Required:** Unit tests for loading `.env` settings and validating `config/rubric.yaml` parsing.
- **Acceptance Criteria:**
  - Application settings load cleanly from environment variables with fallback defaults.
  - Logging outputs structured timestamps and severity levels.
  - Pytest runs cleanly with 100% pass rate.
- **What Must NOT Be Implemented Yet:** Database models, API routes, scraping logic, Google OAuth, LLM clients.

---

## PHASE 2: Database Layer

### Objective
Implement the PostgreSQL relational schema, SQLAlchemy 2.0 async engine and session factory, Alembic migration infrastructure, and core repository operations.

- **Inputs:** `docs/ARCHITECTURE.md`, `docs/PIPELINE.md`.
- **Outputs:** Functional database models, Alembic migrations, and CRUD repository classes for `Company`, `Signal`, `Verdict`, `SyncLog`, and `PipelineRun`.
- **Files Expected to Change:**
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/versions/001_initial_schema.py`
  - `app/db/__init__.py`
  - `app/db/session.py` (Async engine & sessionmaker)
  - `app/db/base.py` (SQLAlchemy DeclarativeBase)
  - `app/db/models.py` (`Company`, `Signal`, `Verdict`, `SyncLog`, `PipelineRun`)
  - `app/db/repositories.py` (Data access methods)
- **Dependencies:** `sqlalchemy >= 2.0`, `alembic`, `asyncpg`, `psycopg2-binary`.
- **Tests Required:** Integration tests verifying database connection, table creation, CRUD operations, foreign key cascades, and unique constraints.
- **Acceptance Criteria:**
  - `alembic upgrade head` creates all tables successfully.
  - Repositories can insert and query companies, signals, and verdicts transactionally.
  - PostgreSQL is established as the isolated system of record.
- **What Must NOT Be Implemented Yet:** Google Sheets communication, Playwright, LLM reasoning, API endpoints.

---

## PHASE 3: Google Sheets Ingestion

### Objective
Build the authenticated Google Sheets reader using Google Service Account credentials, implementing row parsing, delta detection (identifying new/unprocessed rows), URL normalization, and staging into PostgreSQL.

- **Inputs:** `docs/PIPELINE.md`, `docs/PROJECT_SPEC.md`.
- **Outputs:** Ingestion module capable of reading Google Sheets and upserting `Company` records in `PENDING` status into PostgreSQL without application restart.
- **Files Expected to Change:**
  - `app/ingestion/__init__.py`
  - `app/ingestion/sheets_client.py` (Google Auth & Sheets v4 wrapper)
  - `app/ingestion/row_parser.py` (Header mapping & row delta detection)
  - `app/ingestion/service.py` (Ingestion coordinator)
- **Dependencies:** `gspread`, `google-auth`, `google-auth-oauthlib`.
- **Tests Required:** Unit tests for row parsing and URL normalization; integration tests with mocked Google Sheets API responses.
- **Acceptance Criteria:**
  - Authenticates with Google Sheets API using service account credentials.
  - Reads populated rows and identifies unprocessed rows based on empty status or URL changes.
  - Discovered companies are persisted to PostgreSQL with `status = 'PENDING'`.
  - Adding new rows in Google Sheets is picked up dynamically on next read without restarting the app.
- **What Must NOT Be Implemented Yet:** Web scraping, Playwright automation, LLM evaluation, writing back to Google Sheets.

---

## PHASE 4: HTTP & Metadata Enrichment

### Objective
Implement the fast, static HTTP enrichment provider (`WebsiteEnricher`) and independent infrastructure metadata provider (`ExternalSignalEnricher`), normalizing outputs into the unified `NormalizedSignal` schema.

- **Inputs:** `docs/ENRICHMENT_SPEC.md`.
- **Outputs:** `WebsiteEnricher` and `ExternalSignalEnricher` generating normalized, token-optimized facts.
- **Files Expected to Change:**
  - `app/enrichment/__init__.py`
  - `app/enrichment/schemas.py` (`NormalizedSignal`, `SignalType`, `SignalStatus`, `EnrichmentBundle`)
  - `app/enrichment/http_collector.py` (`httpx` + `BeautifulSoup4`)
  - `app/enrichment/metadata_collector.py` (`dnspython`, SSL/TLS, headers)
  - `app/enrichment/cleaner.py` (Boilerplate removal & text fact compression)
- **Dependencies:** `httpx`, `beautifulsoup4`, `lxml`, `dnspython`.
- **Tests Required:** Unit tests parsing sample HTML pages, extracting meta tags and schema.org JSON-LD, handling 404/500 HTTP errors, and DNS timeouts.
- **Acceptance Criteria:**
  - Fetches homepage HTML and distills title, description, headings, and value proposition into compact facts.
  - Resolves DNS MX records and security headers as independent third-source signals.
  - Enforces 10s timeout and catches connection errors gracefully without crashing.
- **What Must NOT Be Implemented Yet:** Playwright browser automation, LLM inference, Google Sheets synchronization.

---

## PHASE 5: Playwright Browser Enrichment

### Objective
Implement the genuine browser automation enricher (`BrowserEnricher`) using headless Chromium via Playwright, extracting dynamic, client-rendered career and hiring signals.

- **Inputs:** `docs/ENRICHMENT_SPEC.md`, `docs/PROJECT_SPEC.md`.
- **Outputs:** `BrowserEnricher` executing live headless Chromium to evaluate dynamic DOMs and extract job postings, department distributions, and tech stack mentions.
- **Files Expected to Change:**
  - `app/enrichment/browser_collector.py` (Playwright headless Chromium controller)
  - `app/enrichment/job_parser.py` (Dynamic DOM & ATS widget scraper)
- **Dependencies:** `playwright`.
- **Tests Required:** Integration tests validating Chromium launch, navigation to dynamic test pages, DOM wait hydration, and timeout handling.
- **Acceptance Criteria:**
  - Launches headless Chromium and navigates to target careers routes.
  - Waits for client-side JavaScript execution (SPAs, React/Vue, embedded job boards).
  - Extracts active job counts, departments, and tech stack keywords.
  - Resource semaphore restricts concurrent browser contexts to prevent OOM errors.
  - Captures browser errors gracefully and outputs a valid `NormalizedSignal(signal_type=BROWSER_CAREERS)`.
- **What Must NOT Be Implemented Yet:** LLM reasoning, pipeline orchestrator runner, Google Sheets write-back.

---

## PHASE 6: LLM Judge Engine

### Objective
Implement the evidence-based evaluation engine, model abstraction layer (`LLMClient`), prompt assembling engine, and Pydantic v2 structured verdict validator.

- **Inputs:** `docs/LLM_SPEC.md`, `config/rubric.yaml`.
- **Outputs:** Evaluator module that accepts persisted company facts + configured rubric and outputs a validated `StructuredLLMVerdict` (`fit`, `confidence`, `reasoning`, `follow_up_question`).
- **Files Expected to Change:**
  - `app/llm/__init__.py`
  - `app/llm/schemas.py` (`StructuredLLMVerdict`, `FitDecision`)
  - `app/llm/client.py` (`LLMClient` protocol & provider adapters for Gemini / Groq / OpenAI)
  - `app/llm/prompts.py` (System & User prompt templates)
  - `app/llm/judge.py` (Evaluation service with 1-shot repair handler)
- **Dependencies:** `google-genai` / `groq` / `openai` SDKs.
- **Tests Required:** Unit tests for prompt generation, mock LLM structured output parsing, Pydantic validation, schema repair retry, and fallback verdict generation.
- **Acceptance Criteria:**
  - Prompts are dynamically generated combining persisted facts and `config/rubric.yaml`.
  - Enforces strict Pydantic output validation (`fit: YES|NO|UNCERTAIN`, `confidence: 0.0-1.0`, `reasoning: List[str]`, `follow_up_question: Optional[str]`).
  - Zero web browsing performed by the LLM.
  - Recovers from malformed JSON via 1-shot format repair and provides fallback `UNCERTAIN` verdict on total provider failure.
- **What Must NOT Be Implemented Yet:** Full end-to-end pipeline loop, Google Sheets sync, FastAPI REST API.

---

## PHASE 7: Pipeline Orchestration

### Objective
Tie Ingestion, Multi-Source Enrichment, PostgreSQL Staging, and LLM Evaluation into a unified, sequential, fault-tolerant orchestration workflow.

- **Inputs:** `docs/PIPELINE.md`, `docs/ARCHITECTURE.md`.
- **Outputs:** `PipelineOrchestrator` managing the 15-step company lifecycle, lease locks, state transitions, and persistence of raw signals *before* LLM evaluation.
- **Files Expected to Change:**
  - `app/orchestration/__init__.py`
  - `app/orchestration/orchestrator.py` (Core pipeline runner)
  - `app/orchestration/state_machine.py` (State transition controller)
  - `app/orchestration/telemetry.py` (Run telemetry collector)
- **Dependencies:** Internal modules (`app.db`, `app.ingestion`, `app.enrichment`, `app.llm`).
- **Tests Required:** Integration tests running a mock company through Steps 1 to 12 (Ingestion → Enrichment → Signal Persistence → LLM Judgment → Verdict Persistence).
- **Acceptance Criteria:**
  - Manages atomic state progression (`PENDING` → `PROCESSING` → `EVALUATED`).
  - **Raw signals are committed to PostgreSQL *before* invoking the LLM Judge.**
  - Handles partial enrichment failures without aborting the batch.
  - Enforces idempotency and prevents concurrent duplicate execution via database lease locks.
- **What Must NOT Be Implemented Yet:** Google Sheets write-back, FastAPI HTTP endpoints, Docker packaging.

---

## PHASE 8: Google Sheets Synchronization

### Objective
Implement the authenticated write-back engine that updates Google Sheet rows with evaluation verdicts, confidence scores, reasoning summaries, follow-up questions, and timestamps.

- **Inputs:** `docs/PIPELINE.md`, `docs/PROJECT_SPEC.md`.
- **Outputs:** `SheetSyncWriter` synchronizing evaluated verdicts back to Google Sheets and logging audit entries in `sync_logs`.
- **Files Expected to Change:**
  - `app/sync/__init__.py`
  - `app/sync/writer.py` (Google Sheets batch cell writer)
  - `app/sync/service.py` (Sync coordinator & status updater)
- **Dependencies:** `gspread`, `google-auth`.
- **Tests Required:** Unit tests for cell mapping and payload formatting; integration tests with mocked Google Sheets API writes.
- **Acceptance Criteria:**
  - Authenticates and writes evaluation outcomes back to the exact matching rows in Google Sheets.
  - Handles rate limits via request batching and exponential backoff.
  - Updates PostgreSQL company status to `SYNCED` and records an audit trail in `sync_logs`.
- **What Must NOT Be Implemented Yet:** FastAPI REST API, Docker packaging, cloud deployment.

---

## PHASE 9: FastAPI REST API & Scheduling

### Objective
Expose the operational REST API endpoints (`/health`, `/run`, `/runs/{run_id}`, `/companies`, `/companies/{company_id}`, `/companies/{company_id}/retry`) with API Key security, background task execution, and an in-process scheduler.

- **Inputs:** `docs/API_SPEC.md`.
- **Outputs:** Fully functional FastAPI service with interactive OpenAPI documentation at `/docs` and automated background scheduling.
- **Files Expected to Change:**
  - `app/main.py` (FastAPI app entrypoint & lifespan)
  - `app/api/__init__.py`
  - `app/api/auth.py` (`X-API-Key` dependency)
  - `app/api/routes_health.py` (`GET /health`)
  - `app/api/routes_pipeline.py` (`POST /run`, `GET /runs/{run_id}`)
  - `app/api/routes_companies.py` (`GET /companies`, `GET /companies/{id}`, `POST /companies/{id}/retry`)
  - `app/core/scheduler.py` (Background periodic runner)
- **Dependencies:** `fastapi`, `uvicorn`, `apscheduler` / native `asyncio.create_task`.
- **Tests Required:** API integration tests with `httpx.AsyncClient(app=app)` testing all status codes (`200`, `202`, `401`, `404`, `409`, `503`).
- **Acceptance Criteria:**
  - `GET /health` returns liveness and dependency status without authentication.
  - `POST /run` triggers background processing and returns `202 Accepted` with a valid `run_id`.
  - All protected endpoints strictly require valid `X-API-Key`.
  - Zero secrets (DB passwords, LLM keys) exposed in responses.
- **What Must NOT Be Implemented Yet:** Cloud deployment, GitHub Actions workflows.

---

## PHASE 10: Testing & Reliability

### Objective
Harden the entire codebase with a comprehensive test suite covering unit, integration, resilience, edge-case, and end-to-end flows.

- **Inputs:** All previous component modules and specifications.
- **Outputs:** Complete pytest suite with high coverage, mocked network boundaries, and resilience verification.
- **Files Expected to Change:**
  - `tests/conftest.py` (Fixtures, DB test engine, mock clients)
  - `tests/test_ingestion.py`
  - `tests/test_enrichment_http.py`
  - `tests/test_enrichment_browser.py`
  - `tests/test_llm_judge.py`
  - `tests/test_pipeline.py`
  - `tests/test_api.py`
  - `tests/test_resilience.py` (Rate limits, timeouts, partial signal recovery)
- **Dependencies:** `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`.
- **Tests Required:** Full suite execution (`pytest -v --cov=app`).
- **Acceptance Criteria:**
  - All unit and integration tests pass deterministically.
  - Resilience tests verify graceful degradation when browser crashes or LLM rate limits occur.
- **What Must NOT Be Implemented Yet:** Production deployment.

---

## PHASE 11: Docker Containerization

### Objective
Package the modular monolith into an optimized, multi-stage Docker container with Playwright Chromium runtime dependencies and local orchestration via `docker-compose.yml`.

- **Inputs:** `docs/ARCHITECTURE.md`.
- **Outputs:** Production-ready `Dockerfile` and local `docker-compose.yml` bundling FastAPI app and PostgreSQL.
- **Files Expected to Change:**
  - `Dockerfile`
  - `docker-compose.yml`
  - `.dockerignore`
  - `entrypoint.sh`
- **Dependencies:** Docker engine, `playwright install --with-deps chromium`.
- **Tests Required:** Build and run container locally; execute test request against `http://localhost:8000/health`.
- **Acceptance Criteria:**
  - Multi-stage build minimizes final image size.
  - Headless Chromium operates properly inside the Linux container.
  - Executes as non-root user (`appuser`).
  - Container health check directive responds `200 OK`.
- **What Must NOT Be Implemented Yet:** Live cloud provisioning.

---

## PHASE 12: Cloud Deployment

### Objective
Deploy the containerized application and managed PostgreSQL database to a zero-cost free-tier cloud host (e.g. Render / Koyeb / Fly.io), configure environment secrets, and obtain a public HTTPS URL.

- **Inputs:** `Dockerfile`, `.env.example`, `docs/ARCHITECTURE.md`.
- **Outputs:** Live, publicly accessible web application with active SSL certificate and persistent database.
- **Files Expected to Change:**
  - Deployment configuration files (e.g., `render.yaml`, `fly.toml`, or hosting configuration docs)
- **Dependencies:** Free-tier cloud hosting platform account.
- **Tests Required:** Probe live public endpoint: `GET https://<PUBLIC_URL>/health` and test `POST /run`.
- **Acceptance Criteria:**
  - Application is reachable over a public HTTPS URL.
  - Database migrations run automatically on container startup.
  - Free-tier resource limits (RAM/CPU) are respected without container restarts.
- **What Must NOT Be Implemented Yet:** GitHub Actions CI/CD workflows.

---

## PHASE 13: GitHub Actions Automation

### Objective
Set up automated CI testing on code push and automated pipeline dispatch workflows.

- **Inputs:** `docs/ARCHITECTURE.md`, `docs/PROJECT_SPEC.md`.
- **Outputs:** `.github/workflows/ci.yml` and `.github/workflows/pipeline_trigger.yml`.
- **Files Expected to Change:**
  - `.github/workflows/ci.yml` (Lint with ruff, run pytest)
  - `.github/workflows/pipeline_trigger.yml` (Scheduled cron trigger & workflow_dispatch)
- **Dependencies:** GitHub repository secrets.
- **Tests Required:** Trigger workflow runs via Git push and manual GitHub Actions dispatch.
- **Acceptance Criteria:**
  - `ci.yml` runs tests and linter on every push and PR to `main`.
  - `pipeline_trigger.yml` triggers an authenticated run against the live public URL on schedule and on-demand.

---

## PHASE 14: Observability & Run Telemetry

### Objective
Finalize operational monitoring, structured execution logs, and queryable run metrics.

- **Inputs:** `docs/API_SPEC.md`, `docs/PIPELINE.md`.
- **Outputs:** Comprehensive run telemetry recorded in `pipeline_runs` table and exposed via `GET /runs/{run_id}`.
- **Files Expected to Change:**
  - `app/orchestration/telemetry.py`
  - `app/core/logging.py`
- **Dependencies:** Internal logging and telemetry modules.
- **Tests Required:** Verify metric accumulation during multi-company batch runs.
- **Acceptance Criteria:**
  - Telemetry records execution duration, signal counts, fit distribution, and error summaries.
  - Logs provide clear traceability of every company state transition.

---

## PHASE 15: Final Audit, Documentation & Demo Video

### Objective
Perform end-to-end verification across all 20 project requirements, finalize the project `README.md`, and record the 3–5 minute demonstration video.

- **Inputs:** All completed phases, live deployment URL, sample Google Sheet.
- **Outputs:** Final `README.md`, verified repository, and 3–5 minute demo video.
- **Files Expected to Change:**
  - `README.md`
  - `docs/PROJECT_SPEC.md` (Update status to Completed)
- **Dependencies:** Screen recording tool.
- **Tests Required:** Live end-to-end validation run with test Google Sheet.
- **Acceptance Criteria:**
  - `README.md` provides clear setup instructions, architecture diagrams, API documentation, and local execution steps.
  - Complete compliance with all 20 baseline project requirements.
  - 3–5 minute demo video demonstrating scheduled runs, on-demand API triggers, Playwright career signal extraction, LLM evidence reasoning, and live Google Sheet synchronization.

---

## Project Definition of Done (DoD)

The project is considered **100% complete** when all the following criteria are verified:

1. **Google Sheets Ingestion:** Rows are fetched dynamically without application restart.
2. **Multi-Source Signals:** Captures static HTTP (`httpx`/`BS4`), live dynamic career/job DOM signals (`Playwright`), and independent DNS/metadata.
3. **No External Paid Crawlers:** Zero usage of Firecrawl or commercial scraping APIs.
4. **Relational System of Record:** All companies, raw signals, and verdicts are persisted in PostgreSQL before LLM reasoning.
5. **Configurable LLM Judge:** LLM reasons over supplied evidence against `config/rubric.yaml` and produces `fit` (`YES`|`NO`|`UNCERTAIN`), `confidence` (`0.0`-`1.0`), `reasoning` (`List[str]`), and `follow_up_question`.
6. **Google Sheets Sync:** Authenticated write-back updates status, fit, confidence, rationale, and timestamps.
7. **FastAPI REST API:** Fully operational endpoints (`/health`, `/run`, `/runs/{run_id}`, `/companies`, `/companies/{id}`, `/companies/{id}/retry`) protected via `X-API-Key`.
8. **Scheduling & On-Demand:** Pipeline triggers automatically on schedule and on demand via API and GitHub Actions.
9. **Dockerized & Publicly Deployed:** Containerized application deployed on free-tier infrastructure with a live public HTTPS URL.
10. **Automated CI/CD:** GitHub Actions CI passes on push; separate workflow triggers the pipeline.
11. **Testing & Code Quality:** Comprehensive pytest test suite passes cleanly.
12. **Documentation & Deliverables:** Complete `README.md`, all `docs/*.md` specifications, and 3–5 minute demo video delivered.

---
*End of Development Phases Document.*
