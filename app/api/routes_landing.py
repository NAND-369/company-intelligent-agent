"""Public root landing and status page for Company Intelligence Agent."""

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Landing"])

LANDING_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Company Intelligence Agent</title>
  <style>
    :root {
      --bg-primary: #0a0e17;
      --bg-secondary: #111827;
      --bg-card: #161f30;
      --bg-card-hover: #1c283f;
      --border-color: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(99, 102, 241, 0.3);
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-indigo: #6366f1;
      --accent-blue: #38bdf8;
      --accent-green: #10b981;
      --accent-purple: #a855f7;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-primary);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .container {
      max-width: 1080px;
      margin: 0 auto;
      padding: 3rem 1.5rem;
      width: 100%;
    }

    /* Hero Section */
    .hero {
      text-align: center;
      margin-bottom: 3.5rem;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.35rem 1rem;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 9999px;
      font-size: 0.875rem;
      font-weight: 600;
      color: var(--accent-green);
      margin-bottom: 1.5rem;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      background-color: var(--accent-green);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--accent-green);
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }

    h1 {
      font-size: 2.75rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 1rem;
    }

    .subtitle {
      font-size: 1.2rem;
      color: var(--text-secondary);
      max-width: 650px;
      margin: 0 auto 1.5rem;
    }

    .summary-text {
      font-size: 1rem;
      color: var(--text-muted);
      max-width: 760px;
      margin: 0 auto;
      line-height: 1.7;
    }

    /* Section Styles */
    .section-title {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text-primary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .section {
      margin-bottom: 3.5rem;
    }

    /* Pipeline Visualization */
    .pipeline-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 0.75rem;
      align-items: center;
      margin-top: 1rem;
    }

    .pipeline-step {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 1.1rem 0.75rem;
      text-align: center;
      position: relative;
      transition: all 0.2s ease;
    }

    .pipeline-step:hover {
      border-color: var(--accent-indigo);
      transform: translateY(-2px);
      box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15);
    }

    .step-num {
      display: inline-block;
      width: 22px;
      height: 22px;
      line-height: 22px;
      background: rgba(99, 102, 241, 0.15);
      color: var(--accent-indigo);
      border-radius: 50%;
      font-size: 0.75rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
    }

    .step-name {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1.3;
    }

    /* What the agent produces (Output Cards) */
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }

    .card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 1.25rem;
      transition: all 0.2s ease;
    }

    .card:hover {
      border-color: var(--border-accent);
      transform: translateY(-2px);
      background: var(--bg-card-hover);
    }

    .card-label {
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--accent-blue);
      text-transform: uppercase;
      margin-bottom: 0.5rem;
    }

    .card-value {
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 0.25rem;
    }

    .card-desc {
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    /* Explore the API */
    .api-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1rem;
    }

    .api-btn {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      text-decoration: none;
      color: var(--text-primary);
      transition: all 0.2s ease;
    }

    .api-btn:hover {
      border-color: var(--accent-indigo);
      background: var(--bg-card-hover);
      transform: translateY(-2px);
      box-shadow: 0 4px 15px rgba(99, 102, 241, 0.15);
    }

    .api-btn-title {
      font-size: 1rem;
      font-weight: 700;
      margin-bottom: 0.25rem;
    }

    .api-btn-path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.8rem;
      color: var(--accent-indigo);
    }

    .arrow-icon {
      font-size: 1.25rem;
      color: var(--text-muted);
      transition: transform 0.2s ease;
    }

    .api-btn:hover .arrow-icon {
      transform: translateX(4px);
      color: var(--text-primary);
    }

    /* Built With Chips */
    .tech-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
    }

    .tech-chip {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 0.45rem 0.9rem;
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--text-secondary);
      transition: border-color 0.2s ease;
    }

    .tech-chip:hover {
      border-color: var(--border-accent);
      color: var(--text-primary);
    }

    /* Footer */
    footer {
      margin-top: auto;
      border-top: 1px solid var(--border-color);
      padding: 1.5rem;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    @media (max-width: 640px) {
      h1 { font-size: 2rem; }
      .pipeline-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Hero Header -->
    <header class="hero">
      <div class="status-badge">
        <span class="status-dot"></span>
        Production System Online
      </div>
      <h1>Company Intelligence Agent</h1>
      <p class="subtitle">Automated company research, evidence-based evaluation, and intelligent fit decisions.</p>
      <p class="summary-text">
        Companies enter through Google Sheets. The agent collects independent company signals, including browser-rendered web data, evaluates the evidence with an LLM, persists the results in PostgreSQL, and synchronizes the structured verdict back to the Sheet.
      </p>
    </header>

    <!-- Pipeline Section -->
    <section class="section">
      <h2 class="section-title">Autonomous Execution Pipeline</h2>
      <div class="pipeline-grid">
        <div class="pipeline-step">
          <span class="step-num">1</span>
          <div class="step-name">Google Sheets</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">2</span>
          <div class="step-name">Company Ingestion</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">3</span>
          <div class="step-name">Independent Enrichment</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">4</span>
          <div class="step-name">Browser Automation</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">5</span>
          <div class="step-name">LLM Evidence-Based Judgment</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">6</span>
          <div class="step-name">PostgreSQL Persistence</div>
        </div>
        <div class="pipeline-step">
          <span class="step-num">7</span>
          <div class="step-name">Google Sheets Sync</div>
        </div>
      </div>
    </section>

    <!-- Verdict Output Cards -->
    <section class="section">
      <h2 class="section-title">What the Agent Produces</h2>
      <div class="cards-grid">
        <div class="card">
          <div class="card-label">Verdict Decision</div>
          <div class="card-value">FIT</div>
          <div class="card-desc">YES / NO / UNCERTAIN</div>
        </div>
        <div class="card">
          <div class="card-label">Statistical Calibration</div>
          <div class="card-value">CONFIDENCE</div>
          <div class="card-desc">0.00 – 1.00</div>
        </div>
        <div class="card">
          <div class="card-label">Qualitative Synthesis</div>
          <div class="card-value">REASONING</div>
          <div class="card-desc">Evidence-based explanation</div>
        </div>
        <div class="card">
          <div class="card-label">Human Review Action</div>
          <div class="card-value">FOLLOW-UP</div>
          <div class="card-desc">A question generated from the evidence</div>
        </div>
      </div>
    </section>

    <!-- Explore the API -->
    <section class="section">
      <h2 class="section-title">Explore the API</h2>
      <div class="api-grid">
        <a href="/docs" class="api-btn">
          <div>
            <div class="api-btn-title">Interactive API Docs</div>
            <div class="api-btn-path">/docs</div>
          </div>
          <span class="arrow-icon">→</span>
        </a>
        <a href="/health" class="api-btn">
          <div>
            <div class="api-btn-title">Health Check</div>
            <div class="api-btn-path">/health</div>
          </div>
          <span class="arrow-icon">→</span>
        </a>
      </div>
    </section>

    <!-- Built With -->
    <section class="section">
      <h2 class="section-title">Built With</h2>
      <div class="tech-grid">
        <div class="tech-chip">FastAPI</div>
        <div class="tech-chip">PostgreSQL</div>
        <div class="tech-chip">Playwright / Chromium</div>
        <div class="tech-chip">Google Sheets</div>
        <div class="tech-chip">Gemini</div>
        <div class="tech-chip">Docker</div>
        <div class="tech-chip">GitHub Actions</div>
        <div class="tech-chip">Railway</div>
      </div>
    </section>
  </div>

  <footer>
    Company Intelligence Agent &bull; Autonomous Signal Extraction &amp; Fit Judgment
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
