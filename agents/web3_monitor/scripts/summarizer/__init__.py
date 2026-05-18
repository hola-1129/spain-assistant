"""
Web3 monitor summarizer — optional Qwen enrichment layer.

Enabled via config.yaml:
  llm_enrichment:
    enabled: true
    signal_explain: true   # Qwen plain-language explanation for cross-signals
    project_screen: false  # Qwen new pool pre-screening (future wiring)

Falls back to original behavior silently on any error.
"""
