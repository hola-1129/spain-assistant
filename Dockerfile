FROM python:3.12-slim

# System deps:
#   supervisor  — multi-process manager (runs all agents)
#   libssl3 + ca-certificates — required by curl_cffi (spain_assistant)
#   tzdata — timezone database
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    ca-certificates \
    libssl3 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ─────────────────────────────────────────────────────
# Copy requirements first to maximise layer cache reuse.
# Install shared/ requirements before agents to resolve constraints early.
COPY shared/reporting/requirements.txt requirements/shared_reporting.txt
COPY agents/finance_bot/requirements.txt requirements/finance_bot.txt
COPY agents/web3_monitor/requirements.txt requirements/web3_monitor.txt
COPY agents/ai_narrative_rotation_radar/requirements.txt requirements/ai_narrative_rotation_radar.txt
COPY agents/polymarket_intelligence/requirements.txt requirements/polymarket_intelligence.txt
COPY agents/spain_assistant/requirements.txt requirements/spain_assistant.txt

RUN pip install --no-cache-dir \
    -r requirements/shared_reporting.txt \
    -r requirements/finance_bot.txt \
    -r requirements/web3_monitor.txt \
    -r requirements/ai_narrative_rotation_radar.txt \
    -r requirements/polymarket_intelligence.txt \
    -r requirements/spain_assistant.txt

# ── Application code ────────────────────────────────────────────────────────
# shared/ is imported by all agents via sys.path (WORKSPACE_ROOT auto-detection)
COPY shared/ shared/

COPY agents/finance_bot/               agents/finance_bot/
COPY agents/web3_monitor/              agents/web3_monitor/
COPY agents/ai_narrative_rotation_radar/ agents/ai_narrative_rotation_radar/
COPY agents/polymarket_intelligence/   agents/polymarket_intelligence/
COPY agents/spain_assistant/           agents/spain_assistant/

# ── Persistent directory stubs ───────────────────────────────────────────────
# Volumes will overlay these at runtime; stubs ensure paths exist on first boot.
RUN mkdir -p \
    agents/finance_bot/logs \
    agents/web3_monitor/logs \
    agents/web3_monitor/data \
    agents/ai_narrative_rotation_radar/logs \
    agents/polymarket_intelligence/logs \
    agents/polymarket_intelligence/storage \
    agents/spain_assistant/logs \
    agents/spain_assistant/data/raw \
    agents/spain_assistant/data/processed \
    agents/spain_assistant/public \
    reports/daily \
    /var/log/supervisor

# ── Supervisor ───────────────────────────────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/ai_workspace.conf

# PYTHONPATH=/app lets every agent resolve `from shared.xxx import ...`
ENV PYTHONPATH=/app

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
