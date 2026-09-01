"""Public root landing and status page for Company Intelligence Agent."""

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse

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

    /* Dividers */
    .section-divider {
      border-bottom: 1px solid var(--border);
    }

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
      background-color: #10B981;
    }

    .nav-links {
      display: flex;
      gap: 2rem;
    }

    .nav-link {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-secondary);
      transition: color 0.2s ease;
    }

    .nav-link:hover {
      color: var(--accent);
    }

    /* Hero Section */
    .hero-section {
      padding: 6rem 0 5rem 0;
      min-height: calc(85vh - 76px);
      display: flex;
      flex-direction: column;
      justify-content: center;
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
      font-size: clamp(3.2rem, 7vw, 6.2rem);
      font-weight: 900;
      line-height: 0.95;
      letter-spacing: -0.04em;
      text-transform: uppercase;
      color: var(--text-main);
      margin-bottom: 2rem;
    }

    .hero-headline .accent-word {
      color: var(--accent);
    }

    .hero-description {
      font-size: 19px;
      line-height: 1.55;
      color: var(--text-secondary);
      max-width: 760px;
      margin-bottom: 2.5rem;
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
      padding: 1rem 2.25rem;
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      border: 1px solid transparent;
      cursor: pointer;
      transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
    }

    .btn-primary {
      background-color: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }

    .btn-primary:hover {
      background-color: #0E3D82;
      border-color: #0E3D82;
    }

    .btn-secondary {
      background-color: var(--text-main);
      color: #ffffff;
      border-color: var(--text-main);
    }

    .btn-secondary:hover {
      background-color: #2B2A2A;
      border-color: #2B2A2A;
    }

    /* Live System Strip */
    .system-strip {
      border-top: 1px solid var(--border);
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
      padding: 5.5rem 0;
      border-bottom: 1px solid var(--border);
    }

    .section-heading-large {
      font-size: clamp(2.4rem, 4.5vw, 4rem);
      font-weight: 900;
      line-height: 1.0;
      letter-spacing: -0.03em;
      text-transform: uppercase;
      margin-bottom: 2.5rem;
    }

    /* Section 02 / System Pipeline */
    .pipeline-container {
      display: flex;
      flex-direction: column;
      border-top: 1px solid var(--border);
    }

    .pipeline-row {
      display: grid;
      grid-template-columns: 80px 1fr 1fr;
      align-items: baseline;
      padding: 1.4rem 0;
      border-bottom: 1px solid var(--border);
      transition: background-color 0.2s ease;
    }

    .pipeline-row:hover {
      background-color: rgba(0, 0, 0, 0.02);
    }

    .pipeline-num {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--accent);
      letter-spacing: 0.1em;
    }

    .pipeline-name {
      font-size: 16px;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--text-main);
    }

    .pipeline-desc {
      font-size: 15px;
      color: var(--text-secondary);
    }

    /* Section 03 / Why Different */
    .diff-list {
      display: flex;
      flex-direction: column;
    }

    .diff-item {
      padding: 1.75rem 0;
      border-top: 1px solid var(--border);
      display: flex;
      align-items: baseline;
      gap: 2rem;
      cursor: default;
    }

    .diff-item:last-child {
      border-bottom: 1px solid var(--border);
    }

    .diff-idx {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.15em;
      min-width: 30px;
    }

    .diff-title {
      font-size: clamp(1.4rem, 2.5vw, 2.2rem);
      font-weight: 800;
      letter-spacing: -0.02em;
      text-transform: uppercase;
      color: var(--text-main);
      transition: color 0.2s ease, transform 0.2s ease;
    }

    .diff-item:hover .diff-title {
      color: var(--accent);
      transform: translateX(4px);
    }

    /* Section 04 / Verdict Output */
    .verdict-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      border-top: 1px solid var(--border);
      border-left: 1px solid var(--border);
    }

    .verdict-cell {
      border-right: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      padding: 2.25rem 2rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      background-color: var(--bg);
    }

    .verdict-header {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .verdict-value {
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -0.01em;
      text-transform: uppercase;
      color: var(--text-main);
    }

    .verdict-desc {
      font-size: 15px;
      color: var(--text-secondary);
      line-height: 1.5;
    }

    /* Section 05 / Autonomous */
    .auto-desc {
      font-size: 18px;
      line-height: 1.6;
      color: var(--text-secondary);
      max-width: 680px;
      margin-bottom: 2.5rem;
    }

    .auto-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      border-top: 1px solid var(--border);
      border-left: 1px solid var(--border);
    }

    .auto-cell {
      border-right: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      padding: 2rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .auto-cell-label {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .auto-cell-val {
      font-family: var(--font-mono);
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
    }

    /* Section 06 / Access CTA */
    .access-desc {
      font-size: 19px;
      color: var(--text-secondary);
      max-width: 650px;
      margin-bottom: 2.5rem;
      line-height: 1.55;
    }

    .access-actions {
      display: flex;
      align-items: center;
      gap: 2.5rem;
      flex-wrap: wrap;
    }

    .link-secondary {
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--text-main);
      border-bottom: 1px solid var(--text-main);
      padding-bottom: 2px;
      transition: color 0.2s ease, border-color 0.2s ease;
    }

    .link-secondary:hover {
      color: var(--accent);
      border-color: var(--accent);
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
      .auto-grid {
        grid-template-columns: 1fr;
      }
      .verdict-grid {
        grid-template-columns: 1fr;
      }
      .pipeline-row {
        grid-template-columns: 60px 1fr;
        row-gap: 0.4rem;
      }
      .pipeline-desc {
        grid-column: 2 / span 1;
      }
    }

    @media (max-width: 640px) {
      .container { padding: 0 1.25rem; }
      nav { height: auto; padding: 1rem 0; }
      .nav-inner { flex-direction: column; gap: 1rem; align-items: flex-start; }
      .nav-links { width: 100%; justify-content: flex-start; }
      .strip-grid { grid-template-columns: 1fr; }
      .strip-item { border-right: none; }
      .hero-headline { font-size: 2.8rem; }
      .hero-section { padding: 4rem 0 3rem 0; min-height: auto; }
      .section-wrap { padding: 3.5rem 0; }
      .diff-item { flex-direction: column; gap: 0.5rem; }
      .footer-grid { flex-direction: column; align-items: flex-start; }
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

  <!-- 01 / HERO SECTION -->
  <header class="container hero-section">
    <div class="grid-12">
      <div class="col-span-3 hero-meta-block">
        <div class="label-meta">01 / INTELLIGENCE SYSTEM</div>
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
          <a href="/docs" class="btn btn-primary">EXPLORE API</a>
          <a href="/health" class="btn btn-secondary">SYSTEM STATUS</a>
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
          <span class="strip-val">ONLINE</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">DATABASE</span>
          <span class="strip-val">CONNECTED</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">BROWSER ENGINE</span>
          <span class="strip-val">READY</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">LLM</span>
          <span class="strip-val">CONFIGURED</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">SHEETS</span>
          <span class="strip-val">CONNECTED</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 02 / SYSTEM PIPELINE SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">02 / SYSTEM</div>
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
    </div>
  </section>

  <!-- 03 / WHY THIS IS DIFFERENT -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">03 / WHY DIFFERENT</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">
            NOT A SUMMARY.<br>
            A JUDGMENT.
          </h2>
          <div class="diff-list">
            <div class="diff-item">
              <span class="diff-idx">01</span>
              <span class="diff-title">INDEPENDENT SIGNALS</span>
            </div>
            <div class="diff-item">
              <span class="diff-idx">02</span>
              <span class="diff-title">REAL BROWSER EVIDENCE</span>
            </div>
            <div class="diff-item">
              <span class="diff-idx">03</span>
              <span class="diff-title">PERSISTENT STATE</span>
            </div>
            <div class="diff-item">
              <span class="diff-idx">04</span>
              <span class="diff-title">STRUCTURED LLM VERDICT</span>
            </div>
            <div class="diff-item">
              <span class="diff-idx">05</span>
              <span class="diff-title">AUTOMATED EXECUTION</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 04 / VERDICT OUTPUT SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">04 / OUTPUT</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">
            FROM EVIDENCE<br>
            TO DECISION.
          </h2>
          <div class="verdict-grid">
            <div class="verdict-cell">
              <span class="verdict-header">FIT</span>
              <span class="verdict-value">YES / NO / UNCERTAIN</span>
              <span class="verdict-desc">Deterministic qualification classification based on strict rubric evaluation.</span>
            </div>
            <div class="verdict-cell">
              <span class="verdict-header">CONFIDENCE</span>
              <span class="verdict-value">0.00 &mdash; 1.00</span>
              <span class="verdict-desc">Calibrated statistical certainty score derived from collected evidence density.</span>
            </div>
            <div class="verdict-cell">
              <span class="verdict-header">REASONING</span>
              <span class="verdict-value">EVIDENCE-BASED</span>
              <span class="verdict-desc">Concise, verifiable rationale citing specific signals extracted from primary sources.</span>
            </div>
            <div class="verdict-cell">
              <span class="verdict-header">FOLLOW-UP</span>
              <span class="verdict-value">DISCOVERY QUESTION</span>
              <span class="verdict-desc">Targeted question generated from the evidence to resolve key qualification ambiguities.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 05 / AUTONOMOUS SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">05 / AUTONOMOUS</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">
            IT KEEPS<br>
            RUNNING.
          </h2>
          <p class="auto-desc">
            The production pipeline can be triggered on demand and automatically through scheduled GitHub Actions execution.
          </p>
          <div class="auto-grid">
            <div class="auto-cell">
              <span class="auto-cell-label">ON DEMAND</span>
              <span class="auto-cell-val">POST /pipeline/run</span>
            </div>
            <div class="auto-cell">
              <span class="auto-cell-label">SCHEDULED</span>
              <span class="auto-cell-val">GitHub Actions</span>
            </div>
            <div class="auto-cell">
              <span class="auto-cell-label">QUERYABLE</span>
              <span class="auto-cell-val">GET /runs/{run_id}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 06 / ACCESS / CTA SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="grid-12">
        <div class="col-span-3">
          <div class="label-meta">06 / ACCESS</div>
        </div>
        <div class="col-span-9">
          <h2 class="section-heading-large">
            START<br>
            EXPLORING.
          </h2>
          <p class="access-desc">
            Inspect the production API, verify system health, and explore the pipeline interface.
          </p>
          <div class="access-actions">
            <a href="/docs" class="btn btn-primary">OPEN API DOCS</a>
            <a href="/health" class="link-secondary">VIEW SYSTEM HEALTH</a>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- FOOTER -->
  <footer>
    <div class="container footer-grid">
      <div class="footer-brand">COMPANY INTELLIGENCE AGENT</div>
      <div>FASTAPI / POSTGRESQL / PLAYWRIGHT / GEMINI</div>
      <div>RAILWAY / GITHUB ACTIONS</div>
    </div>
  </footer>

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
    """Render public HTML landing page for the deployed agent."""
    return HTMLResponse(content=LANDING_PAGE_HTML, status_code=status.HTTP_200_OK)
