"""Public root interactive demo dashboard for Company Intelligence Agent."""

from fastapi import APIRouter, Response, status
from fastapi.responses import HTMLResponse

from app.api.auth import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, create_session_token
from app.config.settings import get_settings

router = APIRouter(tags=["Landing"])


LANDING_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Company Intelligence Agent — Autonomous Research & Evaluation</title>
  <style>
    :root {
      --bg: #E3E2DE;
      --text-main: #141414;
      --text-secondary: #444343;
      --text-muted: #7A7A7A;
      --border: #C7C7C7;
      --accent: #1351AA;
      --accent-hover: #0E3D82;
      --green: #10B981;
      --red: #DC2626;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      border-radius: 0 !important;
    }

    body {
      background-color: var(--bg);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    /* Layout Grid */
    .container {
      max-width: 1320px;
      margin: 0 auto;
      padding: 0 2rem;
    }

    .grid-12 {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 2rem;
    }

    .col-span-3 { grid-column: span 3; }
    .col-span-4 { grid-column: span 4; }
    .col-span-6 { grid-column: span 6; }
    .col-span-8 { grid-column: span 8; }
    .col-span-9 { grid-column: span 9; }
    .col-span-12 { grid-column: span 12; }

    /* Typography */
    .label-meta {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text-muted);
      line-height: 1.6;
    }

    .label-accent {
      color: var(--accent);
    }

    .mono-text {
      font-family: var(--font-mono);
    }

    /* Sticky Navigation */
    nav {
      position: sticky;
      top: 0;
      z-index: 100;
      background-color: var(--bg);
      border-bottom: 1px solid var(--border);
      height: 76px;
      display: flex;
      align-items: center;
    }

    .nav-inner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
    }

    .nav-title {
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0.15em;
      text-transform: uppercase;
    }

    .nav-status {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-secondary);
    }

    .status-dot {
      display: inline-block;
      width: 7px;
      height: 7px;
      background-color: var(--green);
    }

    .nav-links {
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }

    .nav-link {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-secondary);
      transition: color 0.2s ease;
      cursor: pointer;
    }

    .nav-link:hover {
      color: var(--accent);
    }

    .key-btn {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 0.35rem 0.75rem;
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .key-btn:hover {
      border-color: var(--text-main);
      color: var(--text-main);
    }

    /* Hero Section */
    .hero-section {
      padding: 5rem 0 4.5rem 0;
      border-bottom: 1px solid var(--border);
    }

    .hero-meta-block {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .hero-meta-title {
      font-size: 13px;
      font-weight: 700;
      line-height: 1.4;
      letter-spacing: 0.1em;
      color: var(--text-secondary);
      text-transform: uppercase;
    }

    .hero-headline {
      font-size: clamp(3rem, 6.5vw, 5.8rem);
      font-weight: 900;
      line-height: 0.95;
      letter-spacing: -0.04em;
      text-transform: uppercase;
      color: var(--text-main);
      margin-bottom: 1.75rem;
    }

    .hero-headline .accent-word {
      color: var(--accent);
    }

    .hero-description {
      font-size: 18px;
      line-height: 1.55;
      color: var(--text-secondary);
      max-width: 760px;
      margin-bottom: 2.25rem;
    }

    .hero-actions {
      display: flex;
      gap: 1rem;
      align-items: center;
      flex-wrap: wrap;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.9rem 2rem;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      border: 1px solid transparent;
      cursor: pointer;
      transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .btn-primary {
      background-color: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }

    .btn-primary:hover:not(:disabled) {
      background-color: var(--accent-hover);
      border-color: var(--accent-hover);
    }

    .btn-secondary {
      background-color: var(--text-main);
      color: #ffffff;
      border-color: var(--text-main);
    }

    .btn-secondary:hover:not(:disabled) {
      background-color: #2B2A2A;
      border-color: #2B2A2A;
    }

    .btn-outline {
      background-color: transparent;
      color: var(--text-main);
      border-color: var(--text-main);
    }

    .btn-outline:hover:not(:disabled) {
      background-color: var(--text-main);
      color: #ffffff;
    }

    /* Live System Strip */
    .system-strip {
      border-bottom: 1px solid var(--border);
      background-color: var(--bg);
    }

    .strip-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
    }

    .strip-item {
      padding: 1.25rem 1.5rem;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }

    .strip-item:last-child {
      border-right: none;
    }

    .strip-item .strip-val {
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.1em;
      color: var(--text-main);
    }

    /* General Section Styling */
    .section-wrap {
      padding: 5rem 0;
      border-bottom: 1px solid var(--border);
    }

    .section-heading-large {
      font-size: clamp(2.2rem, 4vw, 3.6rem);
      font-weight: 900;
      line-height: 1.0;
      letter-spacing: -0.03em;
      text-transform: uppercase;
      margin-bottom: 2rem;
    }

    .section-subtext {
      font-size: 16px;
      color: var(--text-secondary);
      max-width: 680px;
      margin-bottom: 2rem;
      line-height: 1.55;
    }

    /* Form Controls */
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-bottom: 1.25rem;
    }

    .form-label {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-secondary);
    }

    .form-input {
      font-family: var(--font-mono);
      font-size: 14px;
      padding: 0.85rem 1rem;
      background-color: #ffffff;
      border: 1px solid var(--border);
      color: var(--text-main);
      outline: none;
      transition: border-color 0.2s ease;
      width: 100%;
    }

    .form-input:focus {
      border-color: var(--accent);
    }

    .form-grid-2 {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1.25rem;
    }

    /* Dual Input Source Grid */
    .source-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
    }

    @media (max-width: 900px) {
      .source-grid {
        grid-template-columns: 1fr;
      }
    }

    .source-card {
      border: 1px solid var(--border);
      background-color: #ffffff;
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .source-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border);
    }

    .source-badge {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      padding: 0.25rem 0.5rem;
      border: 1px solid var(--border);
      background: var(--bg);
    }

    /* Notification Box */
    .alert-box {
      padding: 1rem 1.25rem;
      border: 1px solid var(--border);
      background-color: #ffffff;
      font-family: var(--font-mono);
      font-size: 13px;
      margin-top: 1rem;
      display: none;
    }

    .alert-box.success {
      display: block;
      border-color: var(--green);
      color: #065F46;
      background-color: #ECFDF5;
    }

    .alert-box.error {
      display: block;
      border-color: var(--red);
      color: #991B1B;
      background-color: #FEF2F2;
    }

    /* Modernist Table */
    .table-container {
      border: 1px solid var(--border);
      background-color: #ffffff;
      overflow-x: auto;
      margin-top: 1.5rem;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }

    th {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-muted);
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      background-color: var(--bg);
    }

    td {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      color: var(--text-main);
    }

    tr:last-child td {
      border-bottom: none;
    }

    tr:hover td {
      background-color: #FAFAFA;
    }

    .badge {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.1em;
      padding: 0.2rem 0.5rem;
      text-transform: uppercase;
      border: 1px solid var(--border);
    }

    .badge-yes {
      background-color: #ECFDF5;
      color: #065F46;
      border-color: #A7F3D0;
    }

    .badge-no {
      background-color: #FEF2F2;
      color: #991B1B;
      border-color: #FECACA;
    }

    .badge-uncertain {
      background-color: #FFFBEB;
      color: #92400E;
      border-color: #FDE68A;
    }

    .badge-synced {
      background-color: #EFF6FF;
      color: #1E40AF;
      border-color: #BFDBFE;
    }

    .badge-pending {
      background-color: #F3F4F6;
      color: #374151;
      border-color: #E5E7EB;
    }

    .badge-failed {
      background-color: #FEF2F2;
      color: #991B1B;
      border-color: #FECACA;
    }

    /* Live Run Monitor Box */
    .monitor-box {
      border: 1px solid var(--border);
      background-color: #ffffff;
      padding: 2rem;
      margin-top: 1.5rem;
      display: none;
    }

    .monitor-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }

    .monitor-title {
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }

    .monitor-status {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      padding: 0.35rem 0.85rem;
      border: 1px solid var(--border);
    }

    .status-running {
      background-color: #EFF6FF;
      color: #1E40AF;
      border-color: #BFDBFE;
    }

    .status-completed {
      background-color: #ECFDF5;
      color: #065F46;
      border-color: #A7F3D0;
    }

    .status-failed {
      background-color: #FEF2F2;
      color: #991B1B;
      border-color: #FECACA;
    }

    .stage-list {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
      font-family: var(--font-mono);
      font-size: 13px;
    }

    .stage-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      color: var(--text-secondary);
    }

    .stage-item.active {
      color: var(--accent);
      font-weight: 700;
    }

    .stage-item.done {
      color: var(--green);
    }

    .stage-icon {
      width: 18px;
      text-align: center;
    }

    .metrics-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 1rem;
      margin-top: 1.5rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--border);
    }

    .metric-cell {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .metric-label {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .metric-val {
      font-family: var(--font-mono);
      font-size: 18px;
      font-weight: 800;
      color: var(--text-main);
    }

    /* Verdict Result Cards */
    .verdicts-list {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
      margin-top: 1.5rem;
    }

    .verdict-card {
      border: 1px solid var(--border);
      background-color: #ffffff;
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .verdict-top {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.75rem;
    }

    .verdict-co-name {
      font-size: 1.35rem;
      font-weight: 800;
      letter-spacing: -0.01em;
      text-transform: uppercase;
    }

    .verdict-co-url {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-muted);
      margin-left: 0.75rem;
    }

    .verdict-decision-grid {
      display: grid;
      grid-template-columns: 140px 140px 1fr;
      gap: 1.25rem;
      padding: 0.75rem 0;
    }

    .verdict-block-title {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
    }

    .reasoning-list {
      margin-top: 0.5rem;
      padding-left: 1.25rem;
      color: var(--text-secondary);
      font-size: 14px;
      line-height: 1.6;
    }

    .reasoning-list li {
      margin-bottom: 0.35rem;
    }

    .followup-box {
      margin-top: 0.75rem;
      padding: 0.85rem 1rem;
      background-color: var(--bg);
      border-left: 3px solid var(--accent);
      font-size: 14px;
      color: var(--text-main);
    }

    /* Pipeline Sequence Section */
    .pipeline-container {
      display: flex;
      flex-direction: column;
      border-top: 1px solid var(--border);
    }

    .pipeline-row {
      display: grid;
      grid-template-columns: 80px 1fr 1fr;
      align-items: baseline;
      padding: 1.25rem 0;
      border-bottom: 1px solid var(--border);
    }

    .pipeline-num {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--accent);
      letter-spacing: 0.1em;
    }

    .pipeline-name {
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .pipeline-desc {
      font-size: 14px;
      color: var(--text-secondary);
    }

    /* Footer */
    footer {
      padding: 3.5rem 0;
      background-color: var(--bg);
      border-top: 1px solid var(--border);
    }

    .footer-grid {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1.5rem;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .footer-brand {
      color: var(--text-main);
    }

    /* Responsive Breakdown */
    @media (max-width: 1024px) {
      .grid-12 {
        grid-template-columns: 1fr;
        gap: 1.5rem;
      }
      .col-span-3, .col-span-4, .col-span-6, .col-span-8, .col-span-9, .col-span-12 {
        grid-column: span 1;
      }
      .strip-grid {
        grid-template-columns: repeat(2, 1fr);
      }
      .strip-item:nth-child(2n) {
        border-right: none;
      }
      .strip-item {
        border-bottom: 1px solid var(--border);
      }
      .verdict-decision-grid {
        grid-template-columns: 1fr;
      }
      .form-grid-2 {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 640px) {
      .container { padding: 0 1.25rem; }
      nav { height: auto; padding: 1rem 0; }
      .nav-inner { flex-direction: column; gap: 1rem; align-items: flex-start; }
      .nav-links { width: 100%; justify-content: flex-start; }
      .strip-grid { grid-template-columns: 1fr; }
      .strip-item { border-right: none; }
      .hero-headline { font-size: 2.6rem; }
      .hero-section { padding: 3.5rem 0 2.5rem 0; }
      .section-wrap { padding: 3.5rem 0; }
      .footer-grid { flex-direction: column; align-items: flex-start; }
      .verdict-top { flex-direction: column; gap: 0.25rem; }
    }
  </style>
</head>
<body>

  <!-- Navigation Bar -->
  <nav>
    <div class="container nav-inner">
      <div class="nav-title">Company Intelligence Agent</div>
      <div class="nav-status">
        <span class="status-dot"></span>
        Production &bull; Online
      </div>
      <div class="nav-links">
        <a href="/docs" class="nav-link">Docs</a>
        <a href="/health" class="nav-link">Health</a>
      </div>
    </div>
  </nav>

  <!-- HERO SECTION -->
  <header class="container hero-section">
    <div class="grid-12">
      <div class="col-span-3 hero-meta-block">
        <div class="label-meta">00 / INTELLIGENCE SYSTEM</div>
        <div class="hero-meta-title">
          PRODUCTION<br>
          AUTONOMOUS<br>
          COMPANY<br>
          RESEARCH
        </div>
      </div>
      <div class="col-span-9">
        <h1 class="hero-headline">
          COMPANIES IN.<br>
          <span class="accent-word">JUDGMENT</span> OUT.
        </h1>
        <p class="hero-description">
          An autonomous company-intelligence pipeline that collects independent evidence, evaluates it with an LLM, persists the result, and synchronizes the decision back to the source.
        </p>
        <div class="hero-actions">
          <button class="btn btn-primary" onclick="triggerPipelineRun()">RUN PIPELINE NOW</button>
          <button class="btn btn-secondary" onclick="syncFromGoogleSheet()">SYNC FROM SHEET</button>
          <a href="/docs" class="btn btn-outline">EXPLORE API</a>
        </div>
      </div>
    </div>
  </header>

  <!-- LIVE SYSTEM STRIP -->
  <div class="system-strip">
    <div class="container">
      <div class="strip-grid">
        <div class="strip-item">
          <span class="label-meta">SYSTEM STATUS</span>
          <span class="strip-val" id="stripStatus">ONLINE</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">DATABASE</span>
          <span class="strip-val" id="stripDb">CONNECTED</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">BROWSER ENGINE</span>
          <span class="strip-val" id="stripBrowser">READY</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">LLM</span>
          <span class="strip-val" id="stripLlm">CONFIGURED</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">SHEETS</span>
          <span class="strip-val" id="stripSheets">CONNECTED</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 01 / INPUT SOURCES SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">01 / INPUT SOURCES</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">ADD COMPANIES</h2>
          <p class="section-subtext">
            Ingest companies from either source. Both input flows converge into the same active working list and evaluate through the single company intelligence pipeline.
          </p>

          <div class="source-grid">
            <!-- SOURCE A: MANUAL URL INPUT -->
            <div class="source-card">
              <div>
                <div class="source-card-header">
                  <span class="label-meta">SOURCE A &bull; MANUAL INPUT</span>
                  <span class="source-badge">URL / FORM</span>
                </div>
                <h3 style="font-size: 18px; font-weight: 800; margin-bottom: 0.5rem; text-transform: uppercase;">ADD COMPANY MANUALLY</h3>
                <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1.25rem;">
                  Enter a company name and target website URL to stage directly into the working list.
                </p>
                <form id="addCompanyForm" onsubmit="handleAddCompany(event)">
                  <div class="form-group">
                    <label class="form-label" for="compName">Company Name</label>
                    <input class="form-input" type="text" id="compName" placeholder="e.g. Anthropic" required />
                  </div>
                  <div class="form-group">
                    <label class="form-label" for="compUrl">Website URL</label>
                    <input class="form-input" type="url" id="compUrl" placeholder="https://www.anthropic.com" required />
                  </div>
                  <button type="submit" id="addCompBtn" class="btn btn-primary" style="width: 100%; margin-top: 0.25rem;">ADD COMPANY</button>
                </form>
              </div>
              <div id="addCompanyNotice" class="alert-box"></div>
            </div>

            <!-- SOURCE B: GOOGLE SHEETS -->
            <div class="source-card">
              <div>
                <div class="source-card-header">
                  <span class="label-meta">SOURCE B &bull; GOOGLE SHEETS</span>
                  <span class="source-badge" style="background: #EFF6FF; color: #1E40AF; border-color: #BFDBFE;">CONNECTED: ✓</span>
                </div>
                <h3 style="font-size: 18px; font-weight: 800; margin-bottom: 0.5rem; text-transform: uppercase;">SYNC FROM GOOGLE SHEETS</h3>
                <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1.25rem;">
                  Pull new or updated company rows from the configured worksheet into the working list.
                </p>
                <div style="background: var(--bg); border: 1px solid var(--border); padding: 1rem; margin-bottom: 1.25rem;">
                  <div class="label-meta" style="margin-bottom: 0.25rem;">TARGET WORKSHEET</div>
                  <div style="font-family: var(--font-mono); font-size: 14px; font-weight: 700;">
                    Companies &bull; <span style="color: var(--green);">● ONLINE</span>
                  </div>
                </div>
                <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
                  Preserves existing row associations and prepares queued companies for pipeline judgment.
                </p>
                <button id="syncSheetBtn" class="btn btn-secondary" onclick="syncFromGoogleSheet()" style="width: 100%;">SYNC FROM GOOGLE SHEETS</button>
              </div>
              <div id="sheetSyncNotice" class="alert-box"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 02 / CURRENT WORKING LIST & EXECUTION SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">02 / WORKING LIST</div>
        </div>
        <div class="col-span-9">
          <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 1rem;">
            <div>
              <h2 class="section-heading-large" style="margin-bottom: 0.25rem;">CURRENT WORKING LIST</h2>
              <div class="mono-text" style="font-size: 13px; color: var(--text-muted);">
                <span id="workingListCountBadge" class="badge badge-synced" style="font-size: 12px; margin-right: 0.5rem;">0 COMPANIES</span>
                Staged for evaluation through the single intelligence pipeline
              </div>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button class="key-btn" onclick="clearSessionCompanies()">CLEAR LIST</button>
            </div>
          </div>

          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th style="width: 40px; text-align: center;"><input type="checkbox" id="selectAllCheckbox" onchange="toggleSelectAll(event)" checked /></th>
                  <th>Company</th>
                  <th>Website</th>
                  <th>Source / Row ID</th>
                  <th>Status</th>
                  <th>Fit</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody id="companiesTableBody">
                <tr>
                  <td colspan="7" class="mono-text" style="text-align: center; color: var(--text-muted); padding: 2rem;">No companies added yet. Add a company manually or sync from Google Sheets above.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pipeline Execution Trigger Controls -->
          <div style="margin-top: 1.5rem; display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap; background: #ffffff; border: 1px solid var(--border); padding: 1.5rem;">
            <button id="runPipelineBtn" class="btn btn-primary" onclick="triggerPipelineRun()" style="padding: 1rem 2.5rem; font-size: 13px;">RUN PIPELINE</button>
            <label class="mono-text" style="font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
              <input type="checkbox" id="forceReprocessCheckbox" /> Force reprocess already evaluated companies
            </label>
          </div>

          <!-- Live Run Monitor Box -->
          <div id="pipelineMonitor" class="monitor-box">
            <div class="monitor-header">
              <div>
                <div class="monitor-title">PIPELINE RUN EXECUTION</div>
                <div class="mono-text" id="runIdDisplay" style="font-size: 12px; color: var(--text-muted); margin-top: 0.25rem;"></div>
              </div>
              <div id="runStatusBadge" class="monitor-status status-running">RUNNING</div>
            </div>

            <div class="stage-list">
              <div id="stageDiscovery" class="stage-item">
                <span class="stage-icon">&bull;</span>
                <span>01. Company Discovery &amp; Ingestion</span>
              </div>
              <div id="stageEnrichment" class="stage-item">
                <span class="stage-icon">&bull;</span>
                <span>02. Multi-Source HTTP &amp; Playwright Browser Research</span>
              </div>
              <div id="stageJudgment" class="stage-item">
                <span class="stage-icon">&bull;</span>
                <span>03. Gemini 3.1 Flash-Lite Evidence-Based Judgment</span>
              </div>
              <div id="stagePersistence" class="stage-item">
                <span class="stage-icon">&bull;</span>
                <span>04. PostgreSQL Persistence &amp; Lease Release</span>
              </div>
              <div id="stageSync" class="stage-item">
                <span class="stage-icon">&bull;</span>
                <span>05. Google Sheets Bidirectional Synchronization</span>
              </div>
            </div>

            <div id="runMetricsRow" class="metrics-row">
              <div class="metric-cell">
                <span class="metric-label">Discovered</span>
                <span class="metric-val" id="metricDiscovered">0</span>
              </div>
              <div class="metric-cell">
                <span class="metric-label">Processed</span>
                <span class="metric-val" id="metricProcessed">0</span>
              </div>
              <div class="metric-cell">
                <span class="metric-label">Success</span>
                <span class="metric-val" id="metricSuccess">0</span>
              </div>
              <div class="metric-cell">
                <span class="metric-label">Synced to Sheet</span>
                <span class="metric-val" id="metricSynced">0</span>
              </div>
              <div class="metric-cell">
                <span class="metric-label">Fit Decisions</span>
                <span class="metric-val" id="metricDecisions">—</span>
              </div>
            </div>

            <div id="syncConfirmationBanner" class="alert-box success" style="margin-top: 1.25rem; display: none;">
              &check; DATABASE PERSISTED &nbsp;&bull;&nbsp; &check; GOOGLE SHEET SYNCED
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 05 / LATEST RUN RESULTS SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">05 / RESULTS</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">LATEST RUN RESULTS</h2>
          <p class="section-subtext">
            Verdicts and evidence evaluated specifically during the active/most recent pipeline execution.
          </p>

          <div id="latestRunVerdictsList" class="verdicts-list">
            <div class="mono-text" style="color: var(--text-muted); padding: 1.5rem 0;">No pipeline run has been executed in this session yet. Add companies above and click "RUN PIPELINE".</div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 06 / SYSTEM ARCHITECTURE & SEQUENCE -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">06 / PIPELINE</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">THE PIPELINE</h2>
          <div class="pipeline-container">
            <div class="pipeline-row">
              <span class="pipeline-num">01</span>
              <span class="pipeline-name">GOOGLE SHEETS</span>
              <span class="pipeline-desc">Source companies</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">02</span>
              <span class="pipeline-name">INGESTION</span>
              <span class="pipeline-desc">Detect and persist companies</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">03</span>
              <span class="pipeline-name">ENRICHMENT</span>
              <span class="pipeline-desc">Independent company signals</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">04</span>
              <span class="pipeline-name">BROWSER AUTOMATION</span>
              <span class="pipeline-desc">Playwright-rendered web evidence</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">05</span>
              <span class="pipeline-name">LLM JUDGMENT</span>
              <span class="pipeline-desc">Evidence &rarr; structured verdict</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">06</span>
              <span class="pipeline-name">POSTGRESQL</span>
              <span class="pipeline-desc">Persistent processing state</span>
            </div>
            <div class="pipeline-row">
              <span class="pipeline-num">07</span>
              <span class="pipeline-name">SHEET SYNC</span>
              <span class="pipeline-desc">Verdict returned to source</span>
            </div>
          </div>
        </div>
      </div>
  <!-- EXISTING RESULT MODAL -->
  <div id="existingResultModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 1000; align-items: center; justify-content: center; padding: 1.5rem;">
    <div style="background: var(--bg); border: 2px solid var(--text-main); max-width: 820px; width: 100%; max-height: 90vh; overflow-y: auto; padding: 2rem; position: relative;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">
        <div>
          <div class="label-meta label-accent">EXISTING EVALUATION RECORD</div>
          <h3 id="modalCoName" style="font-size: 24px; font-weight: 900; text-transform: uppercase; margin-top: 0.25rem;">Company Name</h3>
          <a id="modalCoUrl" href="#" target="_blank" class="mono-text" style="font-size: 13px; color: var(--text-secondary); text-decoration: underline;"></a>
        </div>
        <button class="key-btn" onclick="closeExistingResultModal()" style="font-size: 13px; padding: 0.5rem 1rem;">&times; CLOSE</button>
      </div>
      <div id="modalContent"></div>
    </div>
  </div>

  <!-- FOOTER -->
  <footer>
    <div class="container footer-grid">
      <div class="footer-brand">COMPANY INTELLIGENCE AGENT</div>
      <div>FASTAPI / POSTGRESQL / PLAYWRIGHT / GEMINI</div>
      <div>RAILWAY / GITHUB ACTIONS</div>
    </div>
  </footer>

  <!-- JAVASCRIPT DASHBOARD LOGIC -->
  <script>
    let activePollingInterval = null;
    let sessionCompanies = [];

    function getHeaders() {
      return { 'Content-Type': 'application/json' };
    }

    async function checkHealth() {
      try {
        const res = await fetch('/health');
        if (res.ok) {
          const data = await res.json();
          const deps = data.dependencies || {};
          if (deps.database) document.getElementById('stripDb').innerText = deps.database.status.toUpperCase();
          if (deps.browser_engine) document.getElementById('stripBrowser').innerText = deps.browser_engine.status.toUpperCase();
          if (deps.llm_provider) document.getElementById('stripLlm').innerText = (deps.llm_provider.model || 'CONFIGURED').toUpperCase();
          if (deps.google_sheets) document.getElementById('stripSheets').innerText = deps.google_sheets.status.toUpperCase();
        }
      } catch (err) {
        console.warn('Health check failed', err);
      }
    }

    function clearSessionCompanies() {
      sessionCompanies = [];
      renderSessionCompanies();
      const notice = document.getElementById('addCompanyNotice');
      if (notice) {
        notice.className = 'alert-box';
        notice.style.display = 'none';
      }
      const sheetNotice = document.getElementById('sheetSyncNotice');
      if (sheetNotice) {
        sheetNotice.className = 'alert-box';
        sheetNotice.style.display = 'none';
      }
    }

    function toggleSelectAll(e) {
      const isChecked = e.target.checked;
      sessionCompanies.forEach(c => { c.selected = isChecked; });
      renderSessionCompanies();
    }

    function toggleSelectCompany(id) {
      const co = sessionCompanies.find(c => c.id === id);
      if (co) {
        co.selected = !co.selected;
      }
      const allSelected = sessionCompanies.length > 0 && sessionCompanies.every(c => c.selected !== false);
      const selectAll = document.getElementById('selectAllCheckbox');
      if (selectAll) selectAll.checked = allSelected;
    }

    function renderSessionCompanies() {
      const tbody = document.getElementById('companiesTableBody');
      const countBadge = document.getElementById('workingListCountBadge');
      if (countBadge) {
        countBadge.innerText = `${sessionCompanies.length} COMPANIES`;
      }

      if (sessionCompanies.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="mono-text" style="text-align: center; color: var(--text-muted); padding: 2rem;">No companies added yet. Add a company manually or sync from Google Sheets above.</td></tr>`;
        return;
      }

      tbody.innerHTML = sessionCompanies.map(c => {
        const rawFit = c.fit || '—';
        const fit = (typeof rawFit === 'string' ? rawFit.replace('FitDecision.', '') : '—').toUpperCase();
        let fitBadge = `<span class="badge badge-pending">—</span>`;
        if (fit === 'YES') fitBadge = `<span class="badge badge-yes">YES</span>`;
        else if (fit === 'NO') fitBadge = `<span class="badge badge-no">NO</span>`;
        else if (fit === 'UNCERTAIN') fitBadge = `<span class="badge badge-uncertain">UNCERTAIN</span>`;

        const conf = (c.confidence !== null && c.confidence !== undefined && c.confidence !== '—') ? (typeof c.confidence === 'number' ? `${Math.round(c.confidence * 100)}%` : c.confidence) : '—';
        const statusClass = `badge-${(c.status || 'pending').toLowerCase()}`;
        const sheetRow = c.sheet_row_id || 'Manual Input';
        const isChecked = c.selected !== false;

        return `
          <tr>
            <td style="text-align: center;">
              <input type="checkbox" onchange="toggleSelectCompany('${c.id}')" ${isChecked ? 'checked' : ''} />
            </td>
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td><a href="${escapeHtml(c.website_url)}" target="_blank" class="mono-text" style="font-size:13px; color:var(--text-secondary); text-decoration: underline;">${escapeHtml(c.website_url || '—')}</a></td>
            <td class="mono-text" style="font-size:12px;">${escapeHtml(sheetRow)}</td>
            <td><span class="badge ${statusClass}">${escapeHtml(c.status || 'PENDING')}</span></td>
            <td>${fitBadge}</td>
            <td class="mono-text" style="font-weight:700;">${conf}</td>
          </tr>
        `;
      }).join('');
    }

    function renderLatestRunResults(companyResults, runMetrics) {
      const container = document.getElementById('latestRunVerdictsList');
      if (!companyResults || companyResults.length === 0 || (runMetrics && runMetrics.processed_count === 0)) {
        container.innerHTML = `<div class="mono-text" style="color: var(--text-muted); padding: 1.5rem 0;">No companies were processed in this run (0 discovered / all companies already evaluated).</div>`;
        return;
      }

      const validJudged = companyResults.filter(c => c.fit && c.fit !== 'None' && c.status !== 'FAILED');
      const failed = companyResults.filter(c => c.status === 'FAILED');

      if (validJudged.length === 0 && failed.length === 0) {
        container.innerHTML = `<div class="mono-text" style="color: var(--text-muted); padding: 1.5rem 0;">No companies were processed in this run.</div>`;
        return;
      }

      let html = '';
      if (failed.length > 0) {
        html += `
          <div class="alert-box error" style="display:block; margin-bottom: 1.5rem;">
            ⚠️ ${failed.length} company evaluation(s) encountered technical provider/network failures and were removed from PostgreSQL:
            <ul style="margin-top:0.5rem; padding-left:1.25rem;">
              ${failed.map(f => `<li><strong>${escapeHtml(f.company_name)}</strong>: ${escapeHtml(f.error || 'Evaluation failure')}</li>`).join('')}
            </ul>
          </div>
        `;
      }

      if (validJudged.length > 0) {
        html += validJudged.map(c => {
          const rawFit = c.fit || 'UNCERTAIN';
          const fit = (typeof rawFit === 'string' ? rawFit.replace('FitDecision.', '') : 'UNCERTAIN').toUpperCase();
          let fitBadge = `<span class="badge badge-uncertain" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: UNCERTAIN</span>`;
          if (fit === 'YES') fitBadge = `<span class="badge badge-yes" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: YES</span>`;
          else if (fit === 'NO') fitBadge = `<span class="badge badge-no" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: NO</span>`;

          const conf = (c.confidence !== null && c.confidence !== undefined) ? `${Math.round(c.confidence * 100)}%` : '—';
          const reasoningItems = Array.isArray(c.reasoning) ? c.reasoning : (c.reasoning ? [c.reasoning] : []);

          return `
            <div class="verdict-card">
              <div class="verdict-top">
                <div>
                  <span class="verdict-co-name">${escapeHtml(c.company_name)}</span>
                  <span class="verdict-co-url">${escapeHtml(c.website_url || '')}</span>
                </div>
                <div class="mono-text" style="font-size:11px; color:var(--accent); font-weight:700;">
                  [LATEST RUN RESULT] &bull; ${c.is_synced ? 'SYNCED TO SHEET' : 'PERSISTED IN DB'}
                </div>
              </div>

              <div class="verdict-decision-grid">
                <div>
                  <div class="verdict-block-title">DECISION</div>
                  <div>${fitBadge}</div>
                </div>
                <div>
                  <div class="verdict-block-title">CONFIDENCE</div>
                  <div class="mono-text" style="font-size: 20px; font-weight: 800;">${conf}</div>
                </div>
                <div>
                  <div class="verdict-block-title">EVIDENCE REASONING</div>
                  <ul class="reasoning-list">
                    ${reasoningItems.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                  </ul>
                </div>
              </div>

              ${c.follow_up_question ? `
                <div class="followup-box">
                  <span class="mono-text" style="font-size:10px; font-weight:700; letter-spacing:0.15em; color:var(--accent); display:block; margin-bottom:0.25rem;">SUGGESTED DISCOVERY FOLLOW-UP:</span>
                  ${escapeHtml(c.follow_up_question)}
                </div>
              ` : ''}
            </div>
          `;
        }).join('');
      } else if (failed.length > 0) {
        html += `<div class="mono-text" style="color: var(--text-muted); padding: 1rem 0;">No successful company evaluations in this run.</div>`;
      }

      container.innerHTML = html;
    }

    async function syncFromGoogleSheet() {
      const btn = document.getElementById('syncSheetBtn');
      const notice = document.getElementById('sheetSyncNotice');
      btn.disabled = true;
      btn.innerText = 'SYNCING...';
      notice.className = 'alert-box';
      notice.style.display = 'none';

      try {
        const res = await fetch('/sheets/sync', {
          method: 'POST',
          headers: getHeaders(),
        });

        if (res.status === 401) {
          notice.className = 'alert-box error';
          notice.innerText = 'Authentication session expired or invalid. Please refresh the page.';
          notice.style.display = 'block';
          return;
        }

        const data = await res.json();
        if (res.ok && data.status === 'success') {
          const imported = data.imported_companies || [];
          let addedCount = 0;
          for (const item of imported) {
            const existingIdx = sessionCompanies.findIndex(
              c => c.id === item.id || (item.domain && c.domain && c.domain === item.domain) || c.name.toLowerCase() === item.name.toLowerCase()
            );
            const coObj = {
              id: item.id,
              name: item.name,
              website_url: item.website_url,
              domain: item.domain,
              sheet_row_id: item.sheet_row_id || '—',
              status: item.status || 'PENDING',
              fit: item.fit || '—',
              confidence: item.confidence || '—',
              selected: true,
            };
            if (existingIdx >= 0) {
              sessionCompanies[existingIdx] = { ...sessionCompanies[existingIdx], ...coObj };
            } else {
              sessionCompanies.push(coObj);
              addedCount++;
            }
          }
          renderSessionCompanies();

          notice.className = 'alert-box success';
          notice.innerText = `✓ Synced from Google Sheets: ${data.rows_read} rows read, ${data.companies_created} created, ${data.companies_updated} updated. Staged ${sessionCompanies.length} companies in working list.`;
          notice.style.display = 'block';
        } else {
          notice.className = 'alert-box error';
          notice.innerText = `Sync failed: ${data.errors ? data.errors.join(', ') : (data.detail || 'Unknown error')}`;
          notice.style.display = 'block';
        }
      } catch (err) {
        notice.className = 'alert-box error';
        notice.innerText = `Network error during sync: ${err.message}`;
        notice.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.innerText = 'SYNC FROM GOOGLE SHEETS';
      }
    }

    function closeExistingResultModal() {
      const modal = document.getElementById('existingResultModal');
      if (modal) modal.style.display = 'none';
    }

    async function viewExistingCompanyResult(companyId) {
      const modal = document.getElementById('existingResultModal');
      const modalContent = document.getElementById('modalContent');
      const modalCoName = document.getElementById('modalCoName');
      const modalCoUrl = document.getElementById('modalCoUrl');

      modal.style.display = 'flex';
      modalContent.innerHTML = `<div class="mono-text" style="color: var(--text-muted); padding: 2rem 0; text-align: center;">Loading existing company evaluation...</div>`;

      try {
        const res = await fetch(`/companies/${companyId}`, { headers: getHeaders() });
        if (!res.ok) {
          modalContent.innerHTML = `<div class="alert-box error" style="display:block;">Failed to fetch company details (${res.status}).</div>`;
          return;
        }
        const data = await res.json();
        modalCoName.innerText = data.name || 'Company';
        modalCoUrl.innerText = data.website_url || '';
        modalCoUrl.href = data.website_url || '#';

        if (!data.latest_verdict || !data.latest_verdict.fit) {
          modalContent.innerHTML = `
            <div style="padding: 2rem 0; text-align: center;">
              <div class="mono-text" style="font-size: 14px; font-weight: 700; color: var(--text-secondary); margin-bottom: 0.5rem;">No result available yet.</div>
              <div class="mono-text" style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.5rem;">The company is currently status: <span class="badge badge-pending">${escapeHtml(data.status)}</span></div>
              <button type="button" class="btn btn-primary" onclick="closeExistingResultModal(); recomputeExistingCompany('${data.id}', '${escapeHtml(data.name)}', '${escapeHtml(data.website_url)}');">🔄 RECOMPUTE COMPANY</button>
            </div>
          `;
          return;
        }

        const v = data.latest_verdict;
        const rawFit = v.fit || 'UNCERTAIN';
        const fit = (typeof rawFit === 'string' ? rawFit.replace('FitDecision.', '') : 'UNCERTAIN').toUpperCase();
        let fitBadge = `<span class="badge badge-uncertain" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: UNCERTAIN</span>`;
        if (fit === 'YES') fitBadge = `<span class="badge badge-yes" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: YES</span>`;
        else if (fit === 'NO') fitBadge = `<span class="badge badge-no" style="font-size:14px; padding:0.35rem 0.75rem;">FIT: NO</span>`;

        const conf = (v.confidence !== null && v.confidence !== undefined) ? `${Math.round(v.confidence * 100)}%` : '—';
        const reasoningItems = Array.isArray(v.reasoning) ? v.reasoning : (v.reasoning ? [v.reasoning] : []);

        modalContent.innerHTML = `
          <div class="verdict-card" style="margin-top: 0; background: #ffffff;">
            <div class="verdict-decision-grid">
              <div>
                <div class="verdict-block-title">DECISION</div>
                <div>${fitBadge}</div>
              </div>
              <div>
                <div class="verdict-block-title">CONFIDENCE</div>
                <div class="mono-text" style="font-size: 22px; font-weight: 800;">${conf}</div>
                ${v.confidence_rationale ? `<div class="mono-text" style="font-size: 11px; color: var(--text-secondary); margin-top: 0.25rem;">${escapeHtml(v.confidence_rationale)}</div>` : ''}
              </div>
              <div>
                <div class="verdict-block-title">EVIDENCE REASONING</div>
                <ul class="reasoning-list">
                  ${reasoningItems.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                </ul>
              </div>
            </div>

            ${v.follow_up_question ? `
              <div class="followup-box" style="margin-top: 1rem;">
                <span class="mono-text" style="font-size:10px; font-weight:700; letter-spacing:0.15em; color:var(--accent); display:block; margin-bottom:0.25rem;">SUGGESTED DISCOVERY FOLLOW-UP:</span>
                ${escapeHtml(v.follow_up_question)}
              </div>
            ` : ''}

            <div style="margin-top: 1.5rem; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border); padding-top: 1rem;">
              <span class="mono-text" style="font-size: 11px; color: var(--text-muted);">Evaluated: ${v.evaluated_at ? new Date(v.evaluated_at).toLocaleString() : 'N/A'}</span>
              <button type="button" class="btn btn-primary" onclick="closeExistingResultModal(); recomputeExistingCompany('${data.id}', '${escapeHtml(data.name)}', '${escapeHtml(data.website_url)}');">🔄 RECOMPUTE</button>
            </div>
          </div>
        `;
      } catch (err) {
        modalContent.innerHTML = `<div class="alert-box error" style="display:block;">Error: ${escapeHtml(err.message)}</div>`;
      }
    }

    async function recomputeExistingCompany(companyId, companyName, companyUrl) {
      // 1. Add to session working list if not present, or reset status to PENDING
      let co = sessionCompanies.find(c => c.id === companyId);
      if (!co) {
        co = {
          id: companyId,
          name: companyName,
          website_url: companyUrl,
          status: 'PENDING',
          fit: '—',
          confidence: '—',
          sheet_row_id: '—',
          selected: true,
        };
        sessionCompanies.push(co);
      } else {
        co.status = 'PENDING';
        co.fit = '—';
        co.confidence = '—';
        co.selected = true;
      }
      renderSessionCompanies();

      // 2. Hide notice
      const notice = document.getElementById('addCompanyNotice');
      if (notice) notice.style.display = 'none';

      // 3. Trigger pipeline explicitly for this company with force_reprocess
      await triggerPipelineRunForCompanies([companyId], true);
    }

    async function handleAddCompany(e) {
      e.preventDefault();
      const btn = document.getElementById('addCompBtn');
      const notice = document.getElementById('addCompanyNotice');
      const name = document.getElementById('compName').value.trim();
      const website_url = document.getElementById('compUrl').value.trim();

      if (!name || !website_url) return;

      // 1. Check if duplicate in current working list
      const existingInSession = sessionCompanies.find(
        c => c.name.toLowerCase() === name.toLowerCase() || c.website_url.toLowerCase() === website_url.toLowerCase()
      );
      if (existingInSession) {
        notice.className = 'alert-box error';
        notice.innerHTML = `
          <div style="font-weight: 700; font-size: 14px; margin-bottom: 0.5rem;">${escapeHtml(existingInSession.name)} is already in the working list.</div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem;">
            <button type="button" class="btn key-btn" onclick="viewExistingCompanyResult('${existingInSession.id}')" style="background: #ffffff; color: var(--text-main); border: 1px solid var(--border); font-size: 11px; padding: 0.4rem 0.8rem;">👁 View Existing Result</button>
            <button type="button" class="btn key-btn" onclick="recomputeExistingCompany('${existingInSession.id}', '${escapeHtml(existingInSession.name)}', '${escapeHtml(existingInSession.website_url)}')" style="background: var(--accent); color: #ffffff; border: 1px solid var(--accent); font-size: 11px; padding: 0.4rem 0.8rem;">🔄 Recompute</button>
          </div>
        `;
        notice.style.display = 'block';
        return;
      }

      btn.disabled = true;
      btn.innerText = 'ADDING...';
      notice.className = 'alert-box';
      notice.style.display = 'none';

      try {
        const res = await fetch('/companies', {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ name, website_url }),
        });

        if (res.status === 401) {
          notice.className = 'alert-box error';
          notice.innerText = 'Authentication session expired or invalid. Please refresh the page.';
          notice.style.display = 'block';
          return;
        }

        const data = await res.json();
        if (res.ok) {
          sessionCompanies.push({
            id: data.id,
            name: data.name,
            website_url: data.website_url,
            domain: data.domain,
            status: data.status || 'PENDING',
            fit: '—',
            confidence: '—',
            sheet_row_id: data.sheet_row_id || 'Manual Input',
            selected: true,
          });
          renderSessionCompanies();
          notice.className = 'alert-box success';
          notice.innerText = `✓ ${data.name} added to working list`;
          notice.style.display = 'block';
          document.getElementById('addCompanyForm').reset();
        } else if (res.status === 409) {
          const errDetails = (data.error && data.error.details) || {};
          const dupId = errDetails.company_id || (data.detail && data.detail.company_id) || '';
          const dupName = errDetails.name || name;
          const dupUrl = errDetails.website_url || website_url;

          // Also add the existing record to the session working list if not already there!
          if (dupId) {
            const alreadyThere = sessionCompanies.some(c => c.id === dupId);
            if (!alreadyThere) {
              sessionCompanies.push({
                id: dupId,
                name: dupName,
                website_url: dupUrl,
                status: (errDetails.status || (data.detail && data.detail.status) || 'PENDING'),
                fit: (data.detail && data.detail.latest_verdict && data.detail.latest_verdict.fit) || '—',
                confidence: (data.detail && data.detail.latest_verdict && data.detail.latest_verdict.confidence !== null) ? `${Math.round(data.detail.latest_verdict.confidence * 100)}%` : '—',
                sheet_row_id: 'Manual Input',
                selected: true,
              });
              renderSessionCompanies();
            }
          }

          notice.className = 'alert-box error';
          notice.innerHTML = `
            <div style="font-weight: 700; font-size: 14px; margin-bottom: 0.5rem;">${escapeHtml(dupName)} already exists in database. Staged in working list.</div>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem;">
              <button type="button" class="btn key-btn" onclick="viewExistingCompanyResult('${dupId}')" style="background: #ffffff; color: var(--text-main); border: 1px solid var(--border); font-size: 11px; padding: 0.4rem 0.8rem;">👁 View Existing Result</button>
              <button type="button" class="btn key-btn" onclick="recomputeExistingCompany('${dupId}', '${escapeHtml(dupName)}', '${escapeHtml(dupUrl)}')" style="background: var(--accent); color: #ffffff; border: 1px solid var(--accent); font-size: 11px; padding: 0.4rem 0.8rem;">🔄 Recompute</button>
            </div>
          `;
          notice.style.display = 'block';
        } else {
          notice.className = 'alert-box error';
          notice.innerText = `Error adding company: ${data.detail || (data.error && data.error.message) || 'Request rejected'}`;
          notice.style.display = 'block';
        }
      } catch (err) {
        notice.className = 'alert-box error';
        notice.innerText = `Network error: ${err.message}`;
        notice.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.innerText = 'ADD COMPANY';
      }
    }

    async function triggerPipelineRunForCompanies(companyIds, forceReprocess = false) {
      const btn = document.getElementById('runPipelineBtn');
      btn.disabled = true;
      btn.innerText = 'DISPATCHING...';

      const monitor = document.getElementById('pipelineMonitor');
      monitor.style.display = 'block';
      document.getElementById('syncConfirmationBanner').style.display = 'none';
      document.getElementById('runStatusBadge').className = 'monitor-status status-running';
      document.getElementById('runStatusBadge').innerText = 'STARTING...';
      document.getElementById('runIdDisplay').innerText = `Initializing run for ${companyIds.length} company/companies...`;

      setStageState('stageDiscovery', 'active');
      setStageState('stageEnrichment', '');
      setStageState('stageJudgment', '');
      setStageState('stagePersistence', '');
      setStageState('stageSync', '');

      try {
        const res = await fetch('/pipeline/run', {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
            company_ids: companyIds,
            sync_to_sheets: true,
            force_reprocess: forceReprocess,
          }),
        });

        if (res.status === 401) {
          alert('Authentication session expired or invalid. Please refresh the page.');
          btn.disabled = false;
          btn.innerText = 'RUN PIPELINE';
          monitor.style.display = 'none';
          return;
        }

        const data = await res.json();
        if (res.ok && data.run_id) {
          document.getElementById('runIdDisplay').innerText = `RUN ID: ${data.run_id}`;
          startRunPolling(data.run_id);
        } else {
          document.getElementById('runStatusBadge').className = 'monitor-status status-failed';
          document.getElementById('runStatusBadge').innerText = 'DISPATCH FAILED';
          document.getElementById('runIdDisplay').innerText = data.detail || (data.error && data.error.message) || 'Failed to start run';
          btn.disabled = false;
          btn.innerText = 'RUN PIPELINE';
        }
      } catch (err) {
        document.getElementById('runStatusBadge').className = 'monitor-status status-failed';
        document.getElementById('runStatusBadge').innerText = 'ERROR';
        document.getElementById('runIdDisplay').innerText = err.message;
        btn.disabled = false;
        btn.innerText = 'RUN PIPELINE';
      }
    }

    async function triggerPipelineRun() {
      const forceReprocess = document.getElementById('forceReprocessCheckbox').checked;
      const targetCompanies = sessionCompanies.filter(c => c.selected !== false);

      if (sessionCompanies.length === 0) {
        const monitor = document.getElementById('pipelineMonitor');
        monitor.style.display = 'block';
        document.getElementById('syncConfirmationBanner').style.display = 'none';
        document.getElementById('runStatusBadge').className = 'monitor-status status-failed';
        document.getElementById('runStatusBadge').innerText = 'NO COMPANIES';
        document.getElementById('runIdDisplay').innerText = 'No companies added to the current working list.';
        document.getElementById('metricDiscovered').innerText = 0;
        document.getElementById('metricProcessed').innerText = 0;
        document.getElementById('metricSuccess').innerText = 0;
        document.getElementById('metricSynced').innerText = 0;
        document.getElementById('metricDecisions').innerText = '—';
        renderLatestRunResults([], { processed_count: 0 });
        return;
      }

      if (targetCompanies.length === 0) {
        alert('No companies selected in the working list. Check the box next to the companies you wish to evaluate.');
        return;
      }

      await triggerPipelineRunForCompanies(targetCompanies.map(c => c.id), forceReprocess);
    }

    function setStageState(elementId, state) {
      const el = document.getElementById(elementId);
      if (!el) return;
      el.className = 'stage-item ' + state;
      const icon = el.querySelector('.stage-icon');
      if (state === 'done') {
        icon.innerHTML = '&check;';
      } else if (state === 'active') {
        icon.innerHTML = '&bull;';
      } else {
        icon.innerHTML = '&bull;';
      }
    }

    function startRunPolling(runId) {
      if (activePollingInterval) clearInterval(activePollingInterval);

      const poll = async () => {
        try {
          const res = await fetch(`/runs/${runId}`, { headers: getHeaders() });
          if (!res.ok) return;

          const data = await res.json();
          const status = data.status;
          const metrics = data.metrics || {};
          const summary = data.summary || {};

          document.getElementById('metricDiscovered').innerText = metrics.total_companies_discovered ?? 0;
          document.getElementById('metricProcessed').innerText = metrics.processed_count ?? 0;
          document.getElementById('metricSuccess').innerText = metrics.success_count ?? 0;
          document.getElementById('metricSynced').innerText = metrics.synced_to_sheet_count ?? 0;

          if (summary.fit_yes !== undefined) {
            document.getElementById('metricDecisions').innerText = `Y:${summary.fit_yes} N:${summary.fit_no} ?:${summary.fit_uncertain}`;
          }

          if (status === 'RUNNING') {
            document.getElementById('runStatusBadge').className = 'monitor-status status-running';
            document.getElementById('runStatusBadge').innerText = 'RUNNING';

            const processed = metrics.processed_count || 0;
            const total = metrics.total_companies_discovered || 0;

            setStageState('stageDiscovery', 'done');
            if (processed > 0) {
              setStageState('stageEnrichment', 'done');
              setStageState('stageJudgment', 'done');
              setStageState('stagePersistence', 'active');
            } else {
              setStageState('stageEnrichment', 'active');
              setStageState('stageJudgment', 'active');
            }
          } else if (status === 'COMPLETED' || status === 'PARTIAL_FAILURE') {
            clearInterval(activePollingInterval);
            document.getElementById('runStatusBadge').className = 'monitor-status status-completed';
            document.getElementById('runStatusBadge').innerText = status;

            setStageState('stageDiscovery', 'done');
            setStageState('stageEnrichment', 'done');
            setStageState('stageJudgment', 'done');
            setStageState('stagePersistence', 'done');
            setStageState('stageSync', 'done');

            if (metrics.synced_to_sheet_count > 0 || metrics.success_count > 0) {
              const banner = document.getElementById('syncConfirmationBanner');
              banner.innerHTML = `&check; DATABASE UPDATED (${metrics.success_count} PERSISTED) &nbsp;&bull;&nbsp; &check; GOOGLE SHEET SYNCED (${metrics.synced_to_sheet_count} ROWS)`;
              banner.style.display = 'block';
            }

            document.getElementById('runPipelineBtn').disabled = false;
            document.getElementById('runPipelineBtn').innerText = 'RUN PIPELINE';

            // Update session working list with latest results
            const results = data.company_results || [];
            for (const r of results) {
              const co = sessionCompanies.find(c => c.id === r.company_id || c.name.toLowerCase() === r.company_name.toLowerCase());
              if (co) {
                co.status = (r.status || '').replace('CompanyStatus.', '');
                co.fit = (r.fit || '—').replace('FitDecision.', '');
                co.confidence = (r.confidence !== null && r.confidence !== undefined) ? `${Math.round(r.confidence * 100)}%` : '—';
                co.is_synced = r.is_synced;
              }
            }
            renderSessionCompanies();

            // Render run-specific results exclusively
            renderLatestRunResults(results, metrics);
          } else if (status === 'FAILED') {
            clearInterval(activePollingInterval);
            document.getElementById('runStatusBadge').className = 'monitor-status status-failed';
            document.getElementById('runStatusBadge').innerText = 'FAILED';

            document.getElementById('runPipelineBtn').disabled = false;
            document.getElementById('runPipelineBtn').innerText = 'RUN PIPELINE';

            const results = data.company_results || [];
            for (const r of results) {
              const co = sessionCompanies.find(c => c.id === r.company_id || c.name.toLowerCase() === r.company_name.toLowerCase());
              if (co) {
                co.status = r.status;
              }
            }
            renderSessionCompanies();

            renderLatestRunResults(results, metrics);
          }
        } catch (err) {
          console.warn('Polling error', err);
        }
      };

      // Poll immediately and then every 2 seconds
      poll();
      activePollingInterval = setInterval(poll, 2000);
    }

    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    // Initialize on page load
    document.addEventListener('DOMContentLoaded', () => {
      checkHealth();
      renderSessionCompanies();
    });
  </script>
</body>
</html>
"""


@router.get(
    "/",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Company Intelligence Agent Landing Page",
    include_in_schema=False,
)
async def landing_page() -> HTMLResponse:
    """Render public HTML landing page and issue secure dashboard session cookie."""
    settings = get_settings()
    session_token = create_session_token(settings)
    is_prod = settings.app_env == "production"

    response = HTMLResponse(content=LANDING_PAGE_HTML, status_code=status.HTTP_200_OK)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )
    return response
