# Google Sheets Synchronization Architecture & Implementation Guide

> **Phase:** Phase 8 (Google Sheets Synchronization / Output)  
> **Architecture Reference:** [`docs/ARCHITECTURE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/ARCHITECTURE.md)  
> **Pipeline Reference:** [`docs/PIPELINE.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/PIPELINE.md)  
> **Data Model Reference:** [`docs/DATA_MODEL.md`](file:///c:/Users/Lenovo/Desktop/company-intelligent%20agent/docs/DATA_MODEL.md)

---

## 1. Executive Summary & Synchronization Role

The **Google Sheets Synchronization Subsystem** (`app/sync/`) implements an authenticated, idempotent, and failure-isolated write-back engine. It translates evaluated `Verdict` records stored in PostgreSQL back into exact target Google Sheet rows identified by `company.sheet_row_id`.

```
PostgreSQL (Source of Truth)
  ├── Company (sheet_row_id = 'row_2', status = 'JUDGED')
  └── Verdict (fit = 'YES', confidence = 0.92, reasoning = [...], follow_up_question = "...")
               │
               ▼
       SheetColumnMapper
       ├── Matches dynamic header layout (Status, Fit, Confidence, Reasoning, etc.)
       └── Formats cells and generates deterministic content fingerprint
               │
               ▼
       SheetsSyncService (with Retry & Idempotency)
       ├── Idempotency Check (skips if verdict content unchanged)
       ├── Transient Error Retry (exponential backoff on HTTP 429/500/503)
       └── Single Batch Cell Update (modifies ONLY target output columns)
               │
               ▼
       Google Sheets API (Row 2 updated)
               │
               ▼
       PostgreSQL Audit
       ├── Company status advanced to `SYNCED`
       └── SyncLog created with `SyncDirection.DB_TO_SHEET` & `SyncStatus.SUCCESS`
```

---

## 2. Dynamic Column Mapping & Output Formatting

The `SheetColumnMapper` resolves 1-based column indices dynamically from row 1 header values, allowing flexible spreadsheet layouts without fragile hardcoded column numbers.

### 2.1 Supported Output Fields & Aliases

| Logical Field | Default Header Config | Recognized Aliases | Formatted Cell Value |
| :--- | :--- | :--- | :--- |
| **`status`** | `Status` | `company_status`, `processing_status`, `state` | `"SYNCED"` |
| **`fit`** | `Fit` | `fit_call`, `recommendation`, `verdict`, `decision` | `"YES"` / `"NO"` / `"UNCERTAIN"` |
| **`confidence`** | `Confidence` | `confidence_score`, `score`, `conf` | `"0.92"` |
| **`reasoning`** | `Reasoning` | `evidence_reasoning`, `summary`, `rationale`, `notes` | `"1. First fact\n2. Second deduction"` |
| **`follow_up_question`**| `Follow-up Question`| `follow_up`, `discovery_question`, `question` | `"What cloud deployment model is used?"` |
| **`last_synced`** | `Last Synced` | `synced_at`, `last_evaluated`, `evaluated_at` | `"2026-09-01 16:20:00Z"` |

### 2.2 Accidental Overwrite Protection
`SheetColumnMapper` strictly modifies **only** the resolved output column indices. Non-target columns (e.g. input company names, target URLs, internal notes) are untouched.

---

## 3. Idempotency & Resumability

1. **Deterministic Content Hash:** The synchronization service computes a SHA-256 fingerprint over `(fit, confidence, reasoning, follow_up_question)`.
2. **Skip Redundant Writes:** If a company is already in `CompanyStatus.SYNCED` and its verdict has not changed, the sync is skipped (`SyncOutcome.SKIPPED`), saving Google API quota.
3. **Automatic Re-sync on Verdict Updates:** If a human operator or prompt iteration updates a company's verdict in PostgreSQL, the updated fingerprint triggers re-synchronization.

---

## 4. Transient Error Handling & Retries

- **Transient Errors:** Rate limiting (`HTTP 429 Resource Exhausted`), server timeouts (`HTTP 500`, `502`, `503`, `504`), and quota errors are retried up to `SYNC_MAX_RETRIES = 3` with exponential backoff (`SYNC_RETRY_BACKOFF_SECONDS * 2^attempt`).
- **Permanent Errors:** Missing spreadsheets (`SpreadsheetNotFoundError`), missing worksheets (`WorksheetNotFoundError`), or authentication failures are not retried and fail safely.
- **Failure Isolation:** An API error on one company's row is logged to `sync_logs` with `SyncStatus.FAILED` and does not prevent remaining companies from synchronizing.

---

## 5. Audit Logging (`sync_logs`)

Every synchronization attempt creates an immutable audit record in PostgreSQL `sync_logs`:
- `company_id`: Foreign key link to company.
- `sync_direction`: `DB_TO_SHEET`.
- `status`: `SUCCESS` or `FAILED`.
- `error_details`: Exception trace on failure.
- `synced_at`: UTC timestamp.

---

## 6. CLI & API Operations

### 6.1 CLI Usage
```bash
# Run batch pipeline including Google Sheets synchronization
python -m app.pipeline.run --sync

# Dry-run preview with sync (no Sheets mutations or DB writes)
python -m app.pipeline.run --sync --dry-run
```

### 6.2 REST API Usage
```bash
POST /pipeline/run
Headers:
  Content-Type: application/json
  X-API-Key: <api_key>

Body:
{
  "sync_to_sheets": true,
  "dry_run": false,
  "limit": 25
}
```
