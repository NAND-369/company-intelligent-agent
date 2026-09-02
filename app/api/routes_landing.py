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
      --surface: #FFFFFF;
      --text-main: #141414;
      --text-secondary: #444343;
      --text-muted: #7A7A7A;
      --border: #C7C7C7;
      --border-dark: #141414;
      --accent: #1351AA;
      --accent-hover: #0E3D82;
      --accent-light: #EFF6FF;
      --green: #10B981;
      --green-light: #ECFDF5;
      --green-dark: #065F46;
      --red: #DC2626;
      --red-light: #FEF2F2;
      --red-dark: #991B1B;
      --amber: #D97706;
      --amber-light: #FFFBEB;
      --amber-dark: #92400E;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; border-radius: 0 !important; }
    body { background-color: var(--bg); color: var(--text-main); font-family: var(--font-sans); line-height: 1.5; -webkit-font-smoothing: antialiased; overflow-x: hidden; width: 100%; }
    a { color: inherit; text-decoration: none; }
    a:focus-visible, button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    /* Mathematically Centered Page Container */
    .container { max-width: 1200px; width: 100%; margin-left: auto; margin-right: auto; padding-left: 2rem; padding-right: 2rem; }

    /* Typography */
    .label-meta { font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--text-muted); line-height: 1.6; }
    .label-accent { color: var(--accent); }
    .mono-text { font-family: var(--font-mono); }

    /* Navigation */
    nav { position: sticky; top: 0; z-index: 100; background-color: var(--bg); border-bottom: 1px solid var(--border); height: 72px; display: flex; align-items: center; width: 100%; }
    .nav-inner { display: flex; justify-content: space-between; align-items: center; width: 100%; }
    .nav-brand { display: flex; align-items: center; gap: 1rem; }
    .nav-title { font-size: 14px; font-weight: 800; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-main); }
    .nav-status { display: flex; align-items: center; gap: 0.5rem; font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-secondary); background: rgba(255,255,255,0.6); border: 1px solid var(--border); padding: 0.3rem 0.65rem; }
    .status-dot { display: inline-block; width: 7px; height: 7px; background-color: var(--green); animation: pulseGreen 2s infinite ease-in-out; }
    @keyframes pulseGreen { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    .nav-links { display: flex; align-items: center; gap: 1.25rem; }
    .nav-link { font-family: var(--font-mono); font-size: 12px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-secondary); transition: color 0.2s ease; cursor: pointer; }
    .nav-link:hover { color: var(--accent); }

    .key-btn { font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; padding: 0.45rem 0.85rem; background: #ffffff; border: 1px solid var(--border); color: var(--text-secondary); cursor: pointer; transition: all 0.2s ease; min-height: 36px; display: inline-flex; align-items: center; justify-content: center; }
    .key-btn:hover { border-color: var(--text-main); color: var(--text-main); background-color: #FAFAFA; }

    /* Hero Section */
    .hero-section { padding: 4rem 0 3.5rem 0; border-bottom: 1px solid var(--border); width: 100%; }
    .hero-kicker { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
    .hero-headline { font-size: clamp(2.4rem, 5.5vw, 4.5rem); font-weight: 900; line-height: 0.98; letter-spacing: -0.035em; text-transform: uppercase; color: var(--text-main); margin-bottom: 1.5rem; }
    .hero-headline .accent-word { color: var(--accent); }
    .hero-description { font-size: 17px; line-height: 1.6; color: var(--text-secondary); max-width: 820px; margin-bottom: 2rem; }
    .hero-actions { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }

    /* Buttons */
    .btn { display: inline-flex; align-items: center; justify-content: center; padding: 0.85rem 1.75rem; font-family: var(--font-mono); font-size: 12px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; border: 1px solid transparent; cursor: pointer; min-height: 44px; transition: background-color 0.2s ease, color 0.2s ease; user-select: none; }
    .btn:disabled { opacity: 0.6; cursor: not-allowed !important; }
    .btn-primary { background-color: var(--accent); color: #ffffff; border-color: var(--accent); }
    .btn-primary:hover:not(:disabled) { background-color: var(--accent-hover); border-color: var(--accent-hover); }
    .btn-secondary { background-color: var(--text-main); color: #ffffff; border-color: var(--text-main); }
    .btn-secondary:hover:not(:disabled) { background-color: #2B2A2A; border-color: #2B2A2A; }
    .btn-outline { background-color: transparent; color: var(--text-main); border-color: var(--text-main); }
    .btn-outline:hover:not(:disabled) { background-color: var(--text-main); color: #ffffff; }

    /* Live System Strip */
    .system-strip { border-bottom: 1px solid var(--border); background-color: var(--bg); width: 100%; }
    .strip-grid { display: grid; grid-template-columns: repeat(5, 1fr); }
    .strip-item { padding: 1.15rem 1.25rem; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 0.35rem; }
    .strip-item:last-child { border-right: none; }
    .strip-item .strip-val { font-family: var(--font-mono); font-size: 13px; font-weight: 700; letter-spacing: 0.1em; color: var(--text-main); }

    /* Section Structure */
    .section-wrap { padding: 3.5rem 0; border-bottom: 1px solid var(--border); width: 100%; }
    .section-kicker { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
    .section-heading-large { font-size: clamp(1.9rem, 3.5vw, 2.75rem); font-weight: 900; line-height: 1.05; letter-spacing: -0.03em; text-transform: uppercase; margin-bottom: 0.75rem; }
    .section-subtext { font-size: 15px; color: var(--text-secondary); max-width: 800px; margin-bottom: 1.75rem; line-height: 1.6; }

    /* Form Controls */
    .form-group { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1.15rem; }
    .form-label { font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-secondary); }
    .form-input { font-family: var(--font-mono); font-size: 14px; padding: 0.75rem 1rem; min-height: 44px; background-color: #ffffff; border: 1px solid var(--border); color: var(--text-main); outline: none; transition: border-color 0.2s ease; width: 100%; }
    .form-input:focus { border-color: var(--accent); }

    /* Dual Input Source Grid */
    .source-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    .source-card { border: 1px solid var(--border); background-color: var(--surface); padding: 1.75rem; display: flex; flex-direction: column; justify-content: space-between; min-height: 380px; }
    .source-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border); }
    .source-badge { font-family: var(--font-mono); font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; padding: 0.25rem 0.5rem; border: 1px solid var(--border); background: var(--bg); }

    /* Alert / Notification Box */
    .alert-box { padding: 0.9rem 1.15rem; border: 1px solid var(--border); background-color: #ffffff; font-family: var(--font-mono); font-size: 12px; line-height: 1.5; margin-top: 1rem; display: none; }
    .alert-box.success { display: block; border-color: var(--green); color: var(--green-dark); background-color: var(--green-light); }
    .alert-box.error { display: block; border-color: var(--red); color: var(--red-dark); background-color: var(--red-light); }

    /* Working List Table Container */
    .table-container { border: 1px solid var(--border); background-color: var(--surface); overflow-x: auto; margin-top: 1.25rem; width: 100%; -webkit-overflow-scrolling: touch; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; min-width: 720px; }
    th { font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-muted); padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); background-color: var(--bg); white-space: nowrap; }
    td { padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); color: var(--text-main); vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background-color: #FAFAFA; }

    /* Badges */
    .badge { display: inline-block; font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.1em; padding: 0.25rem 0.6rem; text-transform: uppercase; border: 1px solid var(--border); white-space: nowrap; }
    .badge-yes { background-color: var(--green-light); color: var(--green-dark); border-color: #A7F3D0; }
    .badge-no { background-color: var(--red-light); color: var(--red-dark); border-color: #FECACA; }
    .badge-uncertain { background-color: var(--amber-light); color: var(--amber-dark); border-color: #FDE68A; }
    .badge-synced { background-color: var(--accent-light); color: #1E40AF; border-color: #BFDBFE; }
    .badge-pending { background-color: #F3F4F6; color: #374151; border-color: #E5E7EB; }
    .badge-failed { background-color: var(--red-light); color: var(--red-dark); border-color: #FECACA; }

    /* Interactive Pipeline Running Monitor */
    .monitor-box { border: 1px solid var(--border-dark); background-color: var(--surface); padding: 1.75rem; margin-top: 1.5rem; display: none; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
    .monitor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
    .monitor-title { font-family: var(--font-mono); font-size: 13px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; display: flex; align-items: center; gap: 0.6rem; }
    .monitor-status { font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.1em; padding: 0.35rem 0.85rem; border: 1px solid var(--border); }
    .status-running { background-color: var(--accent-light); color: #1E40AF; border-color: #BFDBFE; animation: pulseRunning 2s infinite ease-in-out; }
    @keyframes pulseRunning { 0%, 100% { border-color: #BFDBFE; } 50% { border-color: var(--accent); } }
    .status-completed { background-color: var(--green-light); color: var(--green-dark); border-color: #A7F3D0; }
    .status-failed { background-color: var(--red-light); color: var(--red-dark); border-color: #FECACA; }

    /* Polished Pipeline Stepper Nodes */
    .pipeline-stepper { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.75rem; margin: 1.25rem 0 1.75rem 0; position: relative; }
    .stepper-node { border: 1px solid var(--border); background-color: var(--bg); padding: 0.9rem 0.75rem; display: flex; flex-direction: column; gap: 0.35rem; transition: all 0.3s ease; position: relative; }
    .stepper-node.active { border-color: var(--accent); background-color: #ffffff; box-shadow: 0 0 0 1px var(--accent); }
    .stepper-node.active .stepper-node-dot { color: var(--accent); font-weight: 800; }
    .stepper-node.done { border-color: var(--green); background-color: #ffffff; }
    .stepper-node.done .stepper-node-dot { color: var(--green); font-weight: 800; }
    .stepper-node-dot { font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: var(--text-muted); display: flex; align-items: center; justify-content: space-between; }
    .stepper-node-label { font-size: 11px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-main); line-height: 1.3; }

    .node-pulse-indicator { display: inline-block; width: 6px; height: 6px; background-color: var(--accent); animation: pulseDot 1.2s infinite ease-in-out; }
    @keyframes pulseDot { 0%, 100% { opacity: 1; transform: scale(1.3); } 50% { opacity: 0.3; transform: scale(0.7); } }

    /* Progress Bar */
    .progress-bar-container { margin: 1.25rem 0 1.5rem 0; padding: 1rem; background: var(--bg); border: 1px solid var(--border); }
    .progress-bar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
    .progress-bar-track { width: 100%; height: 8px; background-color: #d6d5d1; border: 1px solid var(--border); overflow: hidden; }
    .progress-bar-fill { height: 100%; width: 0%; background-color: var(--accent); transition: width 0.4s ease; }
    .progress-bar-fill.done { background-color: var(--green); }

    /* Company Evaluation Live Feed */
    .pipeline-live-feed { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border); }
    .feed-item { display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0.85rem; background: #ffffff; border: 1px solid var(--border); font-family: var(--font-mono); font-size: 12px; }

    /* Metrics Grid */
    .metrics-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1rem; margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid var(--border); }
    .metric-cell { display: flex; flex-direction: column; gap: 0.25rem; }
    .metric-label { font-family: var(--font-mono); font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-muted); }
    .metric-val { font-family: var(--font-mono); font-size: 18px; font-weight: 800; color: var(--text-main); }

    /* Verdict Result Cards */
    .verdicts-list { display: flex; flex-direction: column; gap: 1.25rem; margin-top: 1.25rem; }
    .verdict-card { border: 1px solid var(--border); background-color: var(--surface); padding: 1.75rem; display: flex; flex-direction: column; gap: 1rem; animation: revealCard 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
    @keyframes revealCard { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .verdict-top { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border); padding-bottom: 0.75rem; }
    .verdict-co-name { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.01em; text-transform: uppercase; }
    .verdict-co-url { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); margin-left: 0.75rem; }
    .verdict-decision-grid { display: grid; grid-template-columns: 140px 140px 1fr; gap: 1.25rem; padding: 0.5rem 0; }
    .verdict-block-title { font-family: var(--font-mono); font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.35rem; }
    .reasoning-list { margin-top: 0.35rem; padding-left: 1.25rem; color: var(--text-secondary); font-size: 14px; line-height: 1.6; }
    .reasoning-list li { margin-bottom: 0.35rem; }
    .followup-box { margin-top: 0.5rem; padding: 0.85rem 1rem; background-color: var(--bg); border-left: 3px solid var(--accent); font-size: 13.5px; color: var(--text-main); line-height: 1.5; }

    /* Pipeline Sequence Section */
    .pipeline-container { display: flex; flex-direction: column; border-top: 1px solid var(--border); }
    .pipeline-row { display: grid; grid-template-columns: 80px 1fr 1fr; align-items: baseline; padding: 1.15rem 0; border-bottom: 1px solid var(--border); }
    .pipeline-num { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--accent); letter-spacing: 0.1em; }
    .pipeline-name { font-size: 15px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
    .pipeline-desc { font-size: 14px; color: var(--text-secondary); }

    /* Footer */
    footer { padding: 3.5rem 0; background-color: var(--bg); border-top: 1px solid var(--border); width: 100%; }
    .footer-grid { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1.5rem; font-family: var(--font-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-muted); }
    .footer-brand { color: var(--text-main); }

    /* Responsive Breakpoints */
    @media (max-width: 1024px) {
      .strip-grid { grid-template-columns: repeat(2, 1fr); }
      .strip-item:nth-child(2n) { border-right: none; }
      .strip-item { border-bottom: 1px solid var(--border); }
      .pipeline-stepper { grid-template-columns: repeat(3, 1fr); }
      .source-grid { grid-template-columns: 1fr; }
      .verdict-decision-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 768px) {
      .container { padding-left: 1.25rem; padding-right: 1.25rem; }
      nav { height: auto; padding: 0.85rem 0; }
      .nav-inner { flex-direction: column; gap: 0.75rem; align-items: flex-start; }
      .nav-brand { width: 100%; justify-content: space-between; }
      .nav-links { width: 100%; justify-content: flex-start; padding-top: 0.5rem; border-top: 1px solid rgba(0,0,0,0.08); }
      .hero-section { padding: 3rem 0 2.5rem 0; }
      .hero-headline { font-size: clamp(2.2rem, 8vw, 3.4rem); }
      .hero-actions { flex-direction: column; align-items: stretch; }
      .hero-actions .btn { width: 100%; }
      .section-wrap { padding: 2.5rem 0; }
      .source-card { padding: 1.25rem; min-height: auto; }
      .pipeline-stepper { grid-template-columns: 1fr; gap: 0.5rem; }
      .pipeline-row { grid-template-columns: 50px 1fr; gap: 0.5rem; }
      .pipeline-desc { grid-column: span 2; margin-top: 0.25rem; }
      .footer-grid { flex-direction: column; align-items: flex-start; gap: 1rem; }
      .verdict-top { flex-direction: column; align-items: flex-start; gap: 0.35rem; }
      .verdict-co-url { margin-left: 0; }
      .pipeline-controls-bar { flex-direction: column; align-items: stretch !important; }
      .pipeline-controls-bar button { width: 100%; }
    }
    @media (max-width: 480px) {
      .container { padding-left: 1rem; padding-right: 1rem; }
      .strip-grid { grid-template-columns: 1fr; }
      .strip-item { border-right: none; }
      .hero-headline { font-size: 2.1rem; }
      .section-heading-large { font-size: 1.75rem; }
      .verdict-card { padding: 1.25rem; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, ::before, ::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
      .status-dot, .node-pulse-indicator, .status-running { animation: none !important; }
    }
  </style>
</head>
<body>

  <!-- Navigation Bar -->
  <nav>
    <div class="container nav-inner">
      <div class="nav-brand">
        <div class="nav-title">Company Intelligence Agent</div>
        <div class="nav-status">
          <span class="status-dot"></span>
          Production &bull; Online
        </div>
      </div>
      <div class="nav-links">
        <a href="/docs" class="nav-link">Docs</a>
        <a href="/health" class="nav-link">Health</a>
      </div>
    </div>
  </nav>

  <!-- HERO SECTION -->
  <header class="hero-section">
    <div class="container">
      <div class="hero-kicker">
        <span class="label-meta">00 / INTELLIGENCE SYSTEM</span>
        <span class="label-meta label-accent">AUTONOMOUS DISCOVERY &amp; EVALUATION</span>
      </div>
      <h1 class="hero-headline">
        COMPANIES IN.<br>
        <span class="accent-word">JUDGMENT</span> OUT.
      </h1>
      <p class="hero-description">
        An autonomous company-intelligence pipeline that collects multi-source independent evidence, evaluates it with Gemini 3.1 Flash-Lite, persists verdicts in PostgreSQL, and synchronizes decisions back to Google Sheets.
      </p>
      <div class="hero-actions">
        <button class="btn btn-primary" onclick="triggerPipelineRun()">RUN PIPELINE NOW</button>
        <button class="btn btn-secondary" onclick="syncFromGoogleSheet()">SYNC FROM SHEET</button>
        <a href="/docs" class="btn btn-outline">EXPLORE API</a>
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
          <span class="label-meta">LLM PROVIDER</span>
          <span class="strip-val" id="stripLlm">CONFIGURED</span>
        </div>
        <div class="strip-item">
          <span class="label-meta">GOOGLE SHEETS</span>
          <span class="strip-val" id="stripSheets">CONNECTED</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 01 / INPUT SOURCES SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="section-kicker">
        <span class="label-meta">01 / INPUT SOURCES</span>
        <span class="label-meta label-accent">DUAL INGESTION PIPELINE</span>
      </div>
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
            <h3 style="font-size: 17px; font-weight: 800; margin-bottom: 0.5rem; text-transform: uppercase;">ADD COMPANY MANUALLY</h3>
            <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1.25rem; line-height: 1.5;">
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
              <span class="source-badge" style="background: #EFF6FF; color: #1E40AF; border-color: #BFDBFE;">CONNECTED: &check;</span>
            </div>
            <h3 style="font-size: 17px; font-weight: 800; margin-bottom: 0.5rem; text-transform: uppercase;">SYNC FROM GOOGLE SHEETS</h3>
            <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1.25rem; line-height: 1.5;">
              Pull new or updated company rows from the configured worksheet into the working list.
            </p>
            <div style="background: var(--bg); border: 1px solid var(--border); padding: 0.9rem; margin-bottom: 1.15rem;">
              <div class="label-meta" style="margin-bottom: 0.25rem;">TARGET WORKSHEET</div>
              <div style="font-family: var(--font-mono); font-size: 13.5px; font-weight: 700;">
                Companies &bull; <span style="color: var(--green);">&bull; ONLINE</span>
              </div>
            </div>
            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem; line-height: 1.5;">
              Preserves existing row associations and prepares queued companies for pipeline judgment.
            </p>
            <button id="syncSheetBtn" class="btn btn-secondary" onclick="syncFromGoogleSheet()" style="width: 100%;">SYNC FROM GOOGLE SHEETS</button>
          </div>
          <div id="sheetSyncNotice" class="alert-box"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- 02 / CURRENT WORKING LIST & EXECUTION SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="section-kicker">
        <span class="label-meta">02 / WORKING LIST &amp; EXECUTION</span>
        <span class="label-meta label-accent">PERSISTED DATABASE STATE</span>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 1rem;">
        <div>
          <h2 class="section-heading-large" style="margin-bottom: 0.25rem;">CURRENT WORKING LIST</h2>
          <div class="mono-text" style="font-size: 13px; color: var(--text-muted);">
            <span id="workingListCountBadge" class="badge badge-synced" style="font-size: 11px; margin-right: 0.5rem;">0 COMPANIES</span>
            Staged companies showing real-time PostgreSQL persisted verdict and sync status.
          </div>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="key-btn" onclick="loadPersistedCompanies(true)">↻ REFRESH DB</button>
          <button class="key-btn" onclick="clearSessionCompanies()">CLEAR LIST</button>
        </div>
      </div>

      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th style="width: 44px; text-align: center;"><input type="checkbox" id="selectAllCheckbox" onchange="toggleSelectAll(event)" checked /></th>
              <th>Company &bull; Domain</th>
              <th>Source / Row ID</th>
              <th>Evaluation Decision</th>
              <th>Google Sheets Sync</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="companiesTableBody">
            <tr>
              <td colspan="6" class="mono-text" style="text-align: center; color: var(--text-muted); padding: 2rem;">No companies added yet. Add a company manually or click "SYNC FROM GOOGLE SHEETS" above.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pipeline Execution Trigger Controls -->
      <div class="pipeline-controls-bar" style="margin-top: 1.5rem; display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap; background: #ffffff; border: 1px solid var(--border); padding: 1.5rem;">
        <button id="runPipelineBtn" class="btn btn-primary" onclick="triggerPipelineRun()" style="padding: 0.95rem 2.25rem; font-size: 13px;">RUN PIPELINE</button>
        <label class="mono-text" style="font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 0.5rem; cursor: pointer; user-select: none;">
          <input type="checkbox" id="forceReprocessCheckbox" /> Force reprocess already evaluated companies
        </label>
      </div>

      <!-- Interactive Pipeline Running Monitor -->
      <div id="pipelineMonitor" class="monitor-box">
        <div class="monitor-header">
          <div>
            <div class="monitor-title">
              <span class="node-pulse-indicator" id="monitorPulseDot"></span>
              <span id="monitorStatusText">PIPELINE RUNNING</span>
            </div>
            <div class="mono-text" id="runIdDisplay" style="font-size: 11.5px; color: var(--text-muted); margin-top: 0.35rem;"></div>
          </div>
          <div id="runStatusBadge" class="monitor-status status-running">INITIALIZING</div>
        </div>

        <!-- Connected Stepper Nodes -->
        <div class="pipeline-stepper">
          <div id="stepDiscovery" class="stepper-node">
            <div class="stepper-node-dot">
              <span>01</span>
              <span class="step-icon">&bull;</span>
            </div>
            <div class="stepper-node-label">DISCOVERY</div>
          </div>
          <div id="stepResearch" class="stepper-node">
            <div class="stepper-node-dot">
              <span>02</span>
              <span class="step-icon">&bull;</span>
            </div>
            <div class="stepper-node-label">RESEARCH</div>
          </div>
          <div id="stepSignals" class="stepper-node">
            <div class="stepper-node-dot">
              <span>03</span>
              <span class="step-icon">&bull;</span>
            </div>
            <div class="stepper-node-label">SIGNALS</div>
          </div>
          <div id="stepJudge" class="stepper-node">
            <div class="stepper-node-dot">
              <span>04</span>
              <span class="step-icon">&bull;</span>
            </div>
            <div class="stepper-node-label">AI JUDGE</div>
          </div>
          <div id="stepSync" class="stepper-node">
            <div class="stepper-node-dot">
              <span>05</span>
              <span class="step-icon">&bull;</span>
            </div>
            <div class="stepper-node-label">SHEET SYNC</div>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="progress-bar-container">
          <div class="progress-bar-header">
            <span class="mono-text" id="progressStatusText" style="font-size: 11.5px; font-weight: 700; color: var(--text-main);">
              ANALYZING COMPANIES...
            </span>
            <span class="mono-text" id="progressFractionText" style="font-size: 12px; font-weight: 800; color: var(--accent);">
              0 / 0 EVALUATED
            </span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" id="pipelineProgressBarFill"></div>
          </div>
        </div>

        <!-- Live Company Evaluation Progress Feed -->
        <div id="pipelineCompanyLiveFeed" class="pipeline-live-feed" style="display: none;"></div>

        <!-- Metrics Summary Grid -->
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
  </section>

  <!-- 05 / LATEST RUN RESULTS SECTION -->
  <section class="section-wrap">
    <div class="container">
      <div class="section-kicker">
        <span class="label-meta">05 / RESULTS AUDIT</span>
        <span class="label-meta label-accent">DETAILED EVIDENCE REASONING</span>
      </div>
      <h2 class="section-heading-large">LATEST RUN RESULTS</h2>
      <p class="section-subtext">
        Verdicts and evidence evaluated specifically during the active/most recent pipeline execution.
      </p>

      <div id="latestRunVerdictsList" class="verdicts-list">
        <div class="mono-text" style="color: var(--text-muted); padding: 1.5rem 0;">No pipeline run has been executed in this session yet. Select companies above and click "RUN PIPELINE".</div>
      </div>
    </div>
  </section>

  <!-- 06 / SYSTEM ARCHITECTURE & SEQUENCE -->
  <section class="section-wrap">
    <div class="container">
      <div class="section-kicker">
        <span class="label-meta">06 / PIPELINE SEQUENCE</span>
        <span class="label-meta label-accent">AUTONOMOUS PIPELINE ARCHITECTURE</span>
      </div>
      <h2 class="section-heading-large">THE PIPELINE</h2>
      <div class="pipeline-container">
        <div class="pipeline-row">
          <span class="pipeline-num">01</span>
          <span class="pipeline-name">GOOGLE SHEETS</span>
          <span class="pipeline-desc">Source company rows from spreadsheet</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">02</span>
          <span class="pipeline-name">INGESTION</span>
          <span class="pipeline-desc">Normalize domain and persist entity</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">03</span>
          <span class="pipeline-name">ENRICHMENT</span>
          <span class="pipeline-desc">Multi-source independent signals &amp; metadata</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">04</span>
          <span class="pipeline-name">BROWSER AUTOMATION</span>
          <span class="pipeline-desc">Playwright-rendered web evidence extraction</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">05</span>
          <span class="pipeline-name">LLM JUDGMENT</span>
          <span class="pipeline-desc">Gemini 3.1 Flash-Lite precedence-enforced verdict</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">06</span>
          <span class="pipeline-name">POSTGRESQL</span>
          <span class="pipeline-desc">Atomic persistence and lease management</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-num">07</span>
          <span class="pipeline-name">SHEET SYNC</span>
          <span class="pipeline-desc">Structured write-back to spreadsheet row</span>
        </div>
      </div>
    </div>
  </section>

  <!-- EXISTING RESULT MODAL -->
  <div id="existingResultModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 1000; align-items: center; justify-content: center; padding: 1.5rem;">
    <div style="background: var(--bg); border: 2px solid var(--text-main); max-width: 820px; width: 100%; max-height: 90vh; overflow-y: auto; padding: 2rem; position: relative;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">
        <div>
          <div class="label-meta label-accent">PERSISTED EVALUATION RECORD</div>
          <h3 id="modalCoName" style="font-size: 22px; font-weight: 900; text-transform: uppercase; margin-top: 0.25rem;">Company Name</h3>
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

    async function loadPersistedCompanies(showToast = false) {
      try {
        const res = await fetch('/companies?limit=100', { headers: getHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        const items = data.items || [];

        for (const item of items) {
          const existingIdx = sessionCompanies.findIndex(
            c => c.id === item.id || (item.domain && c.domain && c.domain === item.domain) || c.name.toLowerCase() === item.name.toLowerCase()
          );

          const fitVal = item.latest_verdict && item.latest_verdict.fit ? item.latest_verdict.fit.replace('FitDecision.', '').toUpperCase() : null;
          const confVal = item.latest_verdict && item.latest_verdict.confidence !== null ? item.latest_verdict.confidence : null;
          const isSynced = item.status === 'SYNCED';

          const coObj = {
            id: item.id,
            name: item.name,
            website_url: item.website_url,
            domain: item.domain,
            sheet_row_id: item.sheet_row_id || 'Manual Input',
            status: item.status || 'PENDING',
            fit: fitVal || '—',
            confidence: confVal !== null ? `${Math.round(confVal * 100)}%` : '—',
            is_synced: isSynced,
            selected: true,
          };

          if (existingIdx >= 0) {
            sessionCompanies[existingIdx] = { ...sessionCompanies[existingIdx], ...coObj };
          } else {
            sessionCompanies.push(coObj);
          }
        }

        renderSessionCompanies();

        if (showToast) {
          const notice = document.getElementById('sheetSyncNotice');
          if (notice) {
            notice.className = 'alert-box success';
            notice.innerText = `✓ Refreshed ${items.length} company records directly from PostgreSQL database.`;
            notice.style.display = 'block';
            setTimeout(() => { notice.style.display = 'none'; }, 3000);
          }
        }
      } catch (err) {
        console.warn('Failed to load persisted companies:', err);
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

    function getCompanyBadges(c) {
      // 1. If currently actively processing in the active run
      if (c.run_state === 'PROCESSING') {
        return {
          verdictBadge: `<span class="badge badge-pending"><span class="node-pulse-indicator"></span> PROCESSING...</span>`,
          syncBadge: `<span class="badge badge-pending">—</span>`,
        };
      }
      if (c.run_state === 'QUEUED') {
        return {
          verdictBadge: `<span class="badge badge-pending">○ QUEUED</span>`,
          syncBadge: `<span class="badge badge-pending">—</span>`,
        };
      }

      // 2. Persisted Verdict
      const fit = (c.fit && c.fit !== '—' && c.fit !== 'None') ? c.fit.replace('FitDecision.', '').toUpperCase() : null;
      const conf = (c.confidence && c.confidence !== '—') ? (typeof c.confidence === 'number' ? `${Math.round(c.confidence * 100)}%` : c.confidence) : null;
      const confStr = conf ? ` &bull; ${conf}` : '';

      let verdictBadge = '';
      if (fit === 'YES') {
        verdictBadge = `<span class="badge badge-yes">&check; YES${confStr}</span>`;
      } else if (fit === 'NO') {
        verdictBadge = `<span class="badge badge-no">&check; NO${confStr}</span>`;
      } else if (fit === 'UNCERTAIN') {
        verdictBadge = `<span class="badge badge-uncertain">! UNCERTAIN${confStr}</span>`;
      } else if (c.status === 'FAILED') {
        verdictBadge = `<span class="badge badge-failed">! FAILED</span>`;
      } else {
        verdictBadge = `<span class="badge badge-pending">○ NOT PROCESSED</span>`;
      }

      // 3. Google Sheets Sync State
      let syncBadge = '';
      if (c.is_synced || c.status === 'SYNCED') {
        syncBadge = `<span class="badge badge-synced">SYNCED TO SHEET</span>`;
      } else if (fit) {
        syncBadge = `<span class="badge badge-pending" style="color:var(--text-muted);">NOT SYNCED</span>`;
      } else {
        syncBadge = `<span class="badge badge-pending">—</span>`;
      }

      return { verdictBadge, syncBadge };
    }

    function renderSessionCompanies() {
      const tbody = document.getElementById('companiesTableBody');
      const countBadge = document.getElementById('workingListCountBadge');
      if (countBadge) {
        countBadge.innerText = `${sessionCompanies.length} COMPANIES`;
      }

      if (sessionCompanies.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="mono-text" style="text-align: center; color: var(--text-muted); padding: 2rem;">No companies added yet. Add a company manually or click "SYNC FROM GOOGLE SHEETS" above.</td></tr>`;
        return;
      }

      tbody.innerHTML = sessionCompanies.map(c => {
        const { verdictBadge, syncBadge } = getCompanyBadges(c);
        const sheetRow = c.sheet_row_id || 'Manual Input';
        const isChecked = c.selected !== false;
        const hasVerdict = (c.fit && c.fit !== '—' && c.fit !== 'None');

        return `
          <tr>
            <td style="text-align: center;">
              <input type="checkbox" onchange="toggleSelectCompany('${c.id}')" ${isChecked ? 'checked' : ''} />
            </td>
            <td>
              <div style="font-weight: 800; font-size: 14.5px; text-transform: uppercase;">${escapeHtml(c.name)}</div>
              <a href="${escapeHtml(c.website_url)}" target="_blank" class="mono-text" style="font-size:12px; color:var(--text-muted); text-decoration: underline; display: inline-block; margin-top: 2px;">
                ${escapeHtml(c.domain || c.website_url || '—')}
              </a>
            </td>
            <td class="mono-text" style="font-size:12px;">${escapeHtml(sheetRow)}</td>
            <td>${verdictBadge}</td>
            <td>${syncBadge}</td>
            <td style="text-align: right;">
              ${hasVerdict ? `
                <button type="button" class="key-btn" onclick="viewExistingCompanyResult('${c.id}')" style="font-size: 10.5px; padding: 0.35rem 0.65rem;">👁 VIEW</button>
              ` : `
                <span class="mono-text" style="font-size:11px; color:var(--text-muted);">—</span>
              `}
            </td>
          </tr>
        `;
      }).join('');
    }

    function renderLatestRunResults(companyResults, runMetrics) {
      const container = document.getElementById('latestRunVerdictsList');
      if (!companyResults || companyResults.length === 0 || (runMetrics && runMetrics.processed_count === 0)) {
        container.innerHTML = `<div class="mono-text" style="color: var(--text-muted); padding: 1.5rem 0;">No companies were evaluated in this run (0 discovered / all companies already evaluated).</div>`;
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
          let fitBadge = `<span class="badge badge-uncertain" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: UNCERTAIN</span>`;
          if (fit === 'YES') fitBadge = `<span class="badge badge-yes" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: YES</span>`;
          else if (fit === 'NO') fitBadge = `<span class="badge badge-no" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: NO</span>`;

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
      btn.innerHTML = '↻ SYNCING...';
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
              is_synced: item.is_synced || item.status === 'SYNCED',
              selected: true,
            };
            if (existingIdx >= 0) {
              sessionCompanies[existingIdx] = { ...sessionCompanies[existingIdx], ...coObj };
            } else {
              sessionCompanies.push(coObj);
            }
          }
          renderSessionCompanies();

          btn.innerHTML = '&check; SYNCED';
          notice.className = 'alert-box success';
          notice.innerText = `✓ Synced from Google Sheets: ${data.rows_read} rows read, ${data.companies_created} created, ${data.companies_updated} updated. Staged ${sessionCompanies.length} companies in working list.`;
          notice.style.display = 'block';

          setTimeout(() => {
            btn.disabled = false;
            btn.innerText = 'SYNC FROM GOOGLE SHEETS';
          }, 2000);
        } else {
          notice.className = 'alert-box error';
          notice.innerText = `Sync failed: ${data.errors ? data.errors.join(', ') : (data.detail || 'Unknown error')}`;
          notice.style.display = 'block';
          btn.disabled = false;
          btn.innerText = 'SYNC FROM GOOGLE SHEETS';
        }
      } catch (err) {
        notice.className = 'alert-box error';
        notice.innerText = `Network error during sync: ${err.message}`;
        notice.style.display = 'block';
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
      modalContent.innerHTML = `<div class="mono-text" style="color: var(--text-muted); padding: 2rem 0; text-align: center;">Loading persisted company evaluation...</div>`;

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
        let fitBadge = `<span class="badge badge-uncertain" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: UNCERTAIN</span>`;
        if (fit === 'YES') fitBadge = `<span class="badge badge-yes" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: YES</span>`;
        else if (fit === 'NO') fitBadge = `<span class="badge badge-no" style="font-size:13px; padding:0.35rem 0.75rem;">FIT: NO</span>`;

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
          is_synced: false,
          selected: true,
        };
        sessionCompanies.push(co);
      } else {
        co.selected = true;
      }
      renderSessionCompanies();

      const notice = document.getElementById('addCompanyNotice');
      if (notice) notice.style.display = 'none';

      await triggerPipelineRunForCompanies([companyId], true);
    }

    async function handleAddCompany(e) {
      e.preventDefault();
      const btn = document.getElementById('addCompBtn');
      const notice = document.getElementById('addCompanyNotice');
      const name = document.getElementById('compName').value.trim();
      const website_url = document.getElementById('compUrl').value.trim();

      if (!name || !website_url) return;

      const existingInSession = sessionCompanies.find(
        c => c.name.toLowerCase() === name.toLowerCase() || c.website_url.toLowerCase() === website_url.toLowerCase()
      );
      if (existingInSession) {
        notice.className = 'alert-box error';
        notice.innerHTML = `
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 0.5rem;">${escapeHtml(existingInSession.name)} is already in the working list.</div>
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
            is_synced: false,
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

          if (dupId) {
            const alreadyThere = sessionCompanies.some(c => c.id === dupId);
            if (!alreadyThere) {
              const dFit = (data.detail && data.detail.latest_verdict && data.detail.latest_verdict.fit) || '—';
              const dConf = (data.detail && data.detail.latest_verdict && data.detail.latest_verdict.confidence !== null) ? `${Math.round(data.detail.latest_verdict.confidence * 100)}%` : '—';
              const dStatus = (errDetails.status || (data.detail && data.detail.status) || 'PENDING');
              sessionCompanies.push({
                id: dupId,
                name: dupName,
                website_url: dupUrl,
                status: dStatus,
                fit: dFit,
                confidence: dConf,
                sheet_row_id: 'Manual Input',
                is_synced: dStatus === 'SYNCED',
                selected: true,
              });
              renderSessionCompanies();
            }
          }

          notice.className = 'alert-box error';
          notice.innerHTML = `
            <div style="font-weight: 700; font-size: 13px; margin-bottom: 0.5rem;">${escapeHtml(dupName)} already exists in database. Staged in working list.</div>
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

    function setStepperNodeState(nodeId, state) {
      const node = document.getElementById(nodeId);
      if (!node) return;
      node.className = 'stepper-node ' + state;
      const icon = node.querySelector('.step-icon');
      if (state === 'done') {
        icon.innerHTML = '&check;';
        icon.style.color = 'var(--green)';
      } else if (state === 'active') {
        icon.innerHTML = '<span class="node-pulse-indicator"></span>';
      } else {
        icon.innerHTML = '&bull;';
        icon.style.color = 'var(--text-muted)';
      }
    }

    async function triggerPipelineRunForCompanies(companyIds, forceReprocess = false) {
      const btn = document.getElementById('runPipelineBtn');
      btn.disabled = true;
      btn.innerHTML = '<span class="node-pulse-indicator"></span> RUNNING PIPELINE...';

      const monitor = document.getElementById('pipelineMonitor');
      monitor.style.display = 'block';
      document.getElementById('syncConfirmationBanner').style.display = 'none';
      document.getElementById('runStatusBadge').className = 'monitor-status status-running';
      document.getElementById('runStatusBadge').innerText = 'STARTING...';
      document.getElementById('monitorStatusText').innerText = 'PIPELINE RUNNING';
      document.getElementById('runIdDisplay').innerText = `Initializing run for ${companyIds.length} company/companies...`;

      document.getElementById('progressStatusText').innerText = `DISPATCHING PIPELINE (0 / ${companyIds.length} EVALUATED)...`;
      document.getElementById('progressFractionText').innerText = `0 / ${companyIds.length} EVALUATED`;
      const fill = document.getElementById('pipelineProgressBarFill');
      fill.className = 'progress-bar-fill';
      fill.style.width = '0%';

      setStepperNodeState('stepDiscovery', 'active');
      setStepperNodeState('stepResearch', '');
      setStepperNodeState('stepSignals', '');
      setStepperNodeState('stepJudge', '');
      setStepperNodeState('stepSync', '');

      // Mark running companies in session
      for (const co of sessionCompanies) {
        if (companyIds.includes(co.id)) {
          if (forceReprocess || !co.fit || co.fit === '—') {
            co.run_state = 'QUEUED';
          }
        }
      }
      renderSessionCompanies();

      // Render initial live feed
      const feed = document.getElementById('pipelineCompanyLiveFeed');
      const targetCos = sessionCompanies.filter(c => companyIds.includes(c.id));
      if (targetCos.length > 0) {
        feed.style.display = 'flex';
        feed.innerHTML = targetCos.map(c => {
          const isPendingEval = forceReprocess || !c.fit || c.fit === '—';
          let initialBadge = `<span class="badge badge-pending" id="feedBadge_${c.id}">○ QUEUED</span>`;
          if (!isPendingEval) {
            const fit = (c.fit || '').toUpperCase();
            const fitClass = fit === 'YES' ? 'badge-yes' : (fit === 'NO' ? 'badge-no' : 'badge-uncertain');
            initialBadge = `<span class="badge ${fitClass}" id="feedBadge_${c.id}">&check; ${fit} (${c.confidence || '—'}) &bull; PERSISTED</span>`;
          }
          return `
            <div class="feed-item" id="feedItem_${c.id}">
              <span><strong>${escapeHtml(c.name)}</strong> <span class="mono-text" style="color:var(--text-muted); font-size:11px;">(${escapeHtml(c.domain || c.website_url)})</span></span>
              ${initialBadge}
            </div>
          `;
        }).join('');
      }

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
          startRunPolling(data.run_id, companyIds.length);
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
        document.getElementById('runIdDisplay').innerText = 'No companies in the working list.';
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

    function startRunPolling(runId, totalTargetCount) {
      if (activePollingInterval) clearInterval(activePollingInterval);

      const poll = async () => {
        try {
          const res = await fetch(`/runs/${runId}`, { headers: getHeaders() });
          if (!res.ok) return;

          const data = await res.json();
          const status = data.status;
          const metrics = data.metrics || {};
          const summary = data.summary || {};

          const discovered = metrics.total_companies_discovered ?? totalTargetCount ?? 0;
          const processed = metrics.processed_count ?? 0;
          const synced = metrics.synced_to_sheet_count ?? 0;
          const success = metrics.success_count ?? 0;

          document.getElementById('metricDiscovered').innerText = discovered;
          document.getElementById('metricProcessed').innerText = processed;
          document.getElementById('metricSuccess').innerText = success;
          document.getElementById('metricSynced').innerText = synced;

          if (summary.fit_yes !== undefined) {
            document.getElementById('metricDecisions').innerText = `Y:${summary.fit_yes} N:${summary.fit_no} ?:${summary.fit_uncertain}`;
          }

          // Progress calculation
          const totalExpected = discovered > 0 ? discovered : totalTargetCount;
          const percent = totalExpected > 0 ? Math.min(100, Math.round((processed / totalExpected) * 100)) : 0;
          const fill = document.getElementById('pipelineProgressBarFill');
          fill.style.width = `${percent}%`;

          document.getElementById('progressStatusText').innerText = `ANALYZING (${processed} OF ${totalExpected} EVALUATED)...`;
          document.getElementById('progressFractionText').innerText = `${processed} / ${totalExpected} EVALUATED (${percent}%)`;

          // Update feed item badges & session companies
          const results = data.company_results || [];
          for (const r of results) {
            const badge = document.getElementById(`feedBadge_${r.company_id}`);
            if (badge) {
              const fit = (r.fit || 'UNCERTAIN').replace('FitDecision.', '');
              const conf = r.confidence !== null ? `${Math.round(r.confidence * 100)}%` : '—';
              const syncTxt = r.is_synced ? ' &bull; SYNCED TO SHEET' : '';
              if (fit === 'YES') {
                badge.className = 'badge badge-yes';
                badge.innerHTML = `&check; FIT: YES (${conf})${syncTxt}`;
              } else if (fit === 'NO') {
                badge.className = 'badge badge-no';
                badge.innerHTML = `&check; FIT: NO (${conf})${syncTxt}`;
              } else {
                badge.className = 'badge badge-uncertain';
                badge.innerHTML = `! FIT: UNCERTAIN (${conf})${syncTxt}`;
              }
            }

            const co = sessionCompanies.find(c => c.id === r.company_id || c.name.toLowerCase() === r.company_name.toLowerCase());
            if (co) {
              co.run_state = null;
              co.status = (r.status || '').replace('CompanyStatus.', '');
              co.fit = (r.fit || '—').replace('FitDecision.', '');
              co.confidence = (r.confidence !== null && r.confidence !== undefined) ? `${Math.round(r.confidence * 100)}%` : '—';
              co.is_synced = r.is_synced;
            }
          }

          if (status === 'RUNNING') {
            document.getElementById('runStatusBadge').className = 'monitor-status status-running';
            document.getElementById('runStatusBadge').innerText = 'RUNNING';

            setStepperNodeState('stepDiscovery', 'done');
            if (processed > 0) {
              setStepperNodeState('stepResearch', 'done');
              setStepperNodeState('stepSignals', 'done');
              setStepperNodeState('stepJudge', 'done');
              setStepperNodeState('stepSync', 'active');
            } else {
              setStepperNodeState('stepResearch', 'active');
              setStepperNodeState('stepSignals', 'active');
              setStepperNodeState('stepJudge', 'active');
            }
          } else if (status === 'COMPLETED' || status === 'PARTIAL_FAILURE') {
            clearInterval(activePollingInterval);
            document.getElementById('runStatusBadge').className = 'monitor-status status-completed';
            document.getElementById('runStatusBadge').innerText = '✓ COMPLETED';
            document.getElementById('monitorStatusText').innerText = '✓ PIPELINE COMPLETE';

            setStepperNodeState('stepDiscovery', 'done');
            setStepperNodeState('stepResearch', 'done');
            setStepperNodeState('stepSignals', 'done');
            setStepperNodeState('stepJudge', 'done');
            setStepperNodeState('stepSync', 'done');

            fill.style.width = '100%';
            fill.className = 'progress-bar-fill done';
            document.getElementById('progressStatusText').innerText = `✓ PIPELINE EXECUTION COMPLETED (${processed} EVALUATED, ${synced} SYNCED)`;
            document.getElementById('progressFractionText').innerText = `100% COMPLETE`;

            if (synced > 0 || success > 0) {
              const banner = document.getElementById('syncConfirmationBanner');
              banner.innerHTML = `&check; ${success} COMPANIES PERSISTED IN POSTGRESQL &nbsp;&bull;&nbsp; &check; ${synced} ROWS SYNCHRONIZED TO GOOGLE SHEETS`;
              banner.style.display = 'block';
            }

            const btn = document.getElementById('runPipelineBtn');
            btn.innerHTML = '&check; PIPELINE COMPLETE';
            setTimeout(() => {
              btn.disabled = false;
              btn.innerText = 'RUN PIPELINE';
            }, 3000);

            // Clean any remaining temporary run_state
            for (const co of sessionCompanies) {
              co.run_state = null;
            }

            // Authoritative reload from database
            await loadPersistedCompanies(false);
            renderLatestRunResults(results, metrics);
          } else if (status === 'FAILED') {
            clearInterval(activePollingInterval);
            document.getElementById('runStatusBadge').className = 'monitor-status status-failed';
            document.getElementById('runStatusBadge').innerText = 'FAILED';
            document.getElementById('monitorStatusText').innerText = '⚠ PIPELINE FAILED';

            const btn = document.getElementById('runPipelineBtn');
            btn.disabled = false;
            btn.innerText = 'RUN PIPELINE';

            for (const co of sessionCompanies) {
              co.run_state = null;
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
      loadPersistedCompanies(false);
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
