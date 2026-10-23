"""Static presentation only; repository and model text never become HTML here."""

STYLE = """
<style>
  :root { --rl-ink: #1c2637; --rl-muted: #627084; --rl-line: #e1e6ed; }
  [data-testid="stAppViewContainer"] { background: #f5f6f8; }
  .stMainBlockContainer, .block-container {
    max-width: 1360px; padding-top: 4.5rem; padding-bottom: 2rem;
  }
  .rl-brand { display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid var(--rl-line); padding-bottom: 22px; margin-bottom: 20px; }
  .rl-wordmark { color: var(--rl-ink); font-size: 27px; font-weight: 750;
    letter-spacing: -1px; }
  .rl-wordmark span { color: #385ed7; }
  .rl-version { font-size: 10px; color: var(--rl-muted); border: 1px solid #dce2eb;
    border-radius: 5px; padding: 3px 6px; margin-left: 10px; vertical-align: middle;
    font-weight: 500; letter-spacing: 0; }
  .rl-local { color: #546478; font-size: 12px; }
  .rl-intro h1 { font-size: 29px; color: var(--rl-ink); letter-spacing: -.8px;
    line-height: 1.25; margin: 0 0 8px; padding: 0; }
  .rl-intro p { font-size: 14px; color: var(--rl-muted); margin: 0 0 22px; }
  .st-key-ingestion-panel, .st-key-answer-panel {
    background: #fff; border-radius: 14px; padding: 22px;
    border: 1px solid var(--rl-line); box-shadow: 0 3px 14px #24385704;
  }
  .rl-eyebrow { text-transform: uppercase; letter-spacing: 1.3px; color: #728098;
    font-weight: 650; font-size: 10px; margin-bottom: 6px; }
  .rl-panel-description { color: var(--rl-muted); font-size: 12px; margin: 0 0 10px; }
  .st-key-ingestion-panel h2, .st-key-answer-panel h2 {
    font-size: 20px; letter-spacing: -.4px; padding-top: 0; padding-bottom: 5px;
  }
  .st-key-ingestion-panel h3, .st-key-answer-panel h3 { font-size: 17px; }
  .st-key-ingestion-panel label p, .st-key-answer-panel label p { font-size: 12px; }
  .st-key-folder-control input { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px; }
  .st-key-folder-control input:disabled { -webkit-text-fill-color: #52627b; color: #52627b; }
  .rl-browse-spacer { height: 10px; }
  .st-key-folder-control button { width: 100%; white-space: nowrap;
    min-width: 78px; padding-left: 8px; padding-right: 8px; }
  .st-key-folder-control button p { font-size: 12px; }
  .st-key-build-slot .st-key-build-action,
  .st-key-build-slot [data-testid="stButton"],
  .st-key-build-slot button { width: 100%; }
  .st-key-ingestion-panel [data-testid="stVerticalBlock"],
  .st-key-answer-panel [data-testid="stVerticalBlock"] { gap: .65rem; }
  .rl-index { background: #f2f9f6; border: 1px solid #dceee5;
    border-radius: 9px; padding: 15px; margin: 7px 0 4px; color: var(--rl-ink); }
  .rl-index-header { display: flex; align-items: center; justify-content: space-between;
    gap: 10px; font-size: 12px; font-weight: 650; }
  .rl-index-name { overflow-wrap: anywhere; min-width: 0; }
  .rl-badge { color: #16664a; background: #dfefe7; border: 1px solid #cce4d7;
    border-radius: 20px; padding: 3px 8px; font-size: 10px; white-space: nowrap; }
  .rl-index p { font-size: 11px; color: #567566; margin: 10px 0 0; }
  .rl-index.stale { background: #fff9ee; border-color: #f0e0bf; }
  .rl-index.stale .rl-badge { color: #866017; background: #f9edce;
    border-color: #eddbaf; }
  .rl-index.stale p { color: #886e42; }
  .rl-index.missing, .rl-index.failed { background: #f6f7fa; border-color: #e1e6ed; }
  .rl-index.missing .rl-badge, .rl-index.failed .rl-badge {
    color: #627084; background: #e9edf3; border-color: #dce2eb; }
  .rl-index.missing p, .rl-index.failed p { color: #6f7c8e; }
  .rl-counts { display: flex; gap: 28px; padding-top: 12px; margin-top: 14px;
    border-top: 1px solid #dfede5; }
  .rl-counts strong { display: block; font-size: 23px; font-weight: 650; line-height: 1.2; }
  .rl-counts small { font-size: 10px; color: #668071; }
  .st-key-answer-panel textarea { background: #fcfdff; border-radius: 8px;
    font-size: 14px; line-height: 1.6; }
  .st-key-answer-panel [data-testid="stText"] {
    white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit;
    font-size: 14px; line-height: 1.85; color: #42516a;
  }
  .rl-empty { border: 1px dashed #d8e1ef; border-radius: 9px;
    background: #fafbfd; text-align: center; padding: 30px 20px; margin-top: 12px; }
  .rl-empty strong { color: #34425a; font-size: 14px; }
  .rl-empty p { color: #7a879a; font-size: 12px; margin: 7px 0 0; }
  .rl-footer { color: #7b8798; font-size: 11px; margin-top: 24px; }
  @media (max-width: 850px) {
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]
      .st-key-ingestion-panel) { flex-direction: column; }
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]
      .st-key-ingestion-panel) > [data-testid="stColumn"] {
      width: 100%; flex: 1 1 100%; min-width: 0;
    }
    .stMainBlockContainer, .block-container { padding-left: 1rem; padding-right: 1rem; }
    .st-key-ingestion-panel, .st-key-answer-panel { padding: 18px; }
    .rl-intro h1 { font-size: 25px; }
  }
  @media (max-width: 480px) {
    .rl-local { font-size: 10px; }
    .st-key-ingestion-panel [data-testid="stHorizontalBlock"] {
      flex-wrap: nowrap; gap: 8px;
    }
    .st-key-ingestion-panel [data-testid="stHorizontalBlock"]
      > [data-testid="stColumn"] { min-width: 0; }
  }
</style>
"""

HEADER = """
<div class="rl-brand">
  <div class="rl-wordmark">Repo<span>Lens</span><small class="rl-version">v0.1</small></div>
  <div class="rl-local">Local workspace</div>
</div>
<div class="rl-intro">
  <h1>Understand your repository.</h1>
  <p>Build an index. Ask a question. Follow the source.</p>
</div>
"""
