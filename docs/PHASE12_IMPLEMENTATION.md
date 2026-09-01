# Phase 12: Railway Cloud Deployment & Production Hosting Guide

## 1. Executive Summary

Phase 12 prepares the Company Intelligence Agent for cloud deployment on Railway with managed PostgreSQL, automated container healthchecks, environment-variable-driven credentials, and zero committed secrets.

The architecture preserves complete parity with local development (`docker-compose.yml`) while supporting dynamic cloud port bindings, database URL schemes, and non-root execution.

---

## 2. Railway Architecture & Service Topology

```
+-----------------------------------------------------------------------------------------+
|                                    Railway Project                                      |
|                                                                                         |
|   +---------------------------------------+       +----------------------------------+  |
|   |         Web Service (API)             |       |     PostgreSQL Plugin Service    |  |
|   |                                       |       |                                  |  |
|   | - Builder: Dockerfile (railway.json)  |       | - Managed PostgreSQL 16          |  |
|   | - Non-root user: appuser (UID 1000)   |       | - Auto-provisioned DATABASE_URL  |  |
|   | - Headless Chromium (/ms-playwright)  |       | - Persistent storage volume      |  |
|   | - Server: uvicorn (dynamic ${PORT})   |       +----------------------------------+  |
|   | - Healthcheck: /health (HTTP 200)     |                         ▲                   |
|   +---------------------------------------+                         │                   |
|                       │                                             │                   |
|                       └───────── Connection: asyncpg ───────────────┘                   |
|                                                                                         |
|   External HTTPS: https://company-agent.up.railway.app                                  |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Required Railway Services

1. **Railway PostgreSQL Plugin Service**:
   - Provisioned directly in Railway project.
   - Generates private `DATABASE_URL` (e.g. `postgresql://postgres:password@junction.proxy.rlwy.net:5432/railway`).
2. **Railway Web Service (Container)**:
   - Built from repository GitHub connection using `Dockerfile` and `railway.json`.
   - Exposes public HTTPS endpoint with automatic TLS certificates.

---

## 4. Environment Variables Configuration

Configure the following variables in the Railway Web Service Dashboard under the **Variables** tab:

### 4.1. Required Variables

| Variable | Description | Example / Instructions |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string | Referenced via Railway template: `${{Postgres.DATABASE_URL}}` |
| `API_KEY` | Secret token protecting REST endpoints | Generate a random 32+ character string |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Target Google Sheet ID | Extracted from your Google Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_INFO` | Full JSON service account key | Paste raw JSON content: `{"type": "service_account", ...}` |
| `LLM_PROVIDER` | LLM Judge provider backend | `gemini` (or `groq` / `openai`) |
| `GEMINI_API_KEY` | Google AI Studio API key | `AIzaSy...` (or `GROQ_API_KEY` / `OPENAI_API_KEY`) |

### 4.2. Optional Production Defaults

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `APP_ENV` | `production` | Enables production log formatting |
| `LOG_LEVEL` | `INFO` | Standard structured logging |
| `DB_POOL_SIZE` | `5` | Async database connection pool size |
| `DB_MAX_OVERFLOW` | `5` | Max burst database connections |
| `PIPELINE_MAX_CONCURRENCY` | `3` | Parallel company enrichment workers |
| `PIPELINE_ENABLE_BROWSER` | `true` | Headless Playwright dynamic JS scraping |
| `SCHEDULER_ENABLED` | `false` | In-process periodic scheduler (leave false initially) |
| `SCHEDULER_INTERVAL_MINUTES`| `360` | Scheduled pipeline execution interval |

---

## 5. Deployment Metadata (`railway.json`)

The repository includes [`railway.json`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/railway.json) to declare deployment policies:
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 60,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

---

## 6. Step-by-Step Railway Deployment Procedure

### Step 1: Push Repository to GitHub
Ensure the latest code including `Dockerfile`, `railway.json`, and `.dockerignore` is committed and pushed to your GitHub repository.

### Step 2: Create Railway Project
1. Log in to [Railway](https://railway.com).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select your repository.

### Step 3: Add PostgreSQL Database
1. Inside the Railway project canvas, click **New** → **Database** → **Add PostgreSQL**.
2. Railway will deploy PostgreSQL and export `DATABASE_URL`.

### Step 4: Configure Web Service Variables
1. Click on the API web service.
2. Go to the **Variables** tab.
3. Click **Add Reference** → select `DATABASE_URL` from the PostgreSQL service.
4. Add the remaining variables (`API_KEY`, `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_INFO`, `LLM_PROVIDER`, `GEMINI_API_KEY`).

### Step 5: Generate Public Domain
1. In the Web Service settings under **Networking**, click **Generate Domain**.
2. Note your public URL (e.g., `https://company-intelligent-agent.up.railway.app`).

### Step 6: Deploy & Monitor
Railway will build the image, install Playwright Chromium, initialize database tables on startup, and mark the service healthy after `/health` responds with HTTP 200.

---

## 7. Post-Deployment Verification

### 1. Probe Public Health Endpoint
```bash
curl -s https://<YOUR_RAILWAY_URL>/health | jq .
```
Expected output:
```json
{
  "status": "healthy",
  "app_name": "Company Intelligence Agent",
  "version": "0.1.0",
  "environment": "production",
  "dependencies": {
    "database": { "status": "connected", "latency_ms": 2 },
    "browser_engine": { "status": "ready", "engine": "Chromium (Playwright)" },
    "llm_provider": { "status": "ready", "provider": "gemini", "model": "gemini-1.5-flash" },
    "google_sheets": { "status": "ready", "spreadsheet_id": "..." }
  }
}
```

### 2. Trigger Dry-Run Pipeline
```bash
curl -X POST https://<YOUR_RAILWAY_URL>/run \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "batch_size": 5, "skip_ingestion": true}'
```

### 3. Inspect Companies
```bash
curl -s https://<YOUR_RAILWAY_URL>/companies \
  -H "X-API-Key: <YOUR_API_KEY>" | jq .
```

---

## 8. Rollback & Disaster Recovery

- **One-Click Rollback**: In the Railway Dashboard under the **Deployments** tab, click **Redeploy** on any prior stable build.
- **Data Persistence**: The PostgreSQL database runs as an isolated persistent service; code rollbacks do not affect stored companies, signals, verdicts, or sync logs.
- **Zero Orphaned Browsers**: Process termination via `SIGTERM` cleanly shuts down any active Playwright browser contexts.

---

## 9. Security & Hardening Checklist

- [x] No credentials or `.env` files present in repository.
- [x] Unprivileged `appuser` (UID 1000) execution in container.
- [x] `GET /health` requires zero auth and incurs no external LLM/Sheets quota.
- [x] All mutation endpoints (`POST /run`, `POST /companies/{id}/retry`) require `X-API-Key` or `Authorization: Bearer <token>`.
- [x] Database URL scheme automatically normalizes `postgresql://` to `postgresql+asyncpg://`.
- [x] Atomic relational leasing prevents duplicate execution.
