"""
Finance bot summarizer — optional Qwen enrichment layer.

Enabled via config.yaml:
  llm_enrichment:
    enabled: true
    daily_summary: true
    portfolio_report: true
    signal_alerts: false   # must remain false — trading signals are rule-based only

If Qwen is unavailable or fails, all methods fall back to original messages silently.
"""
