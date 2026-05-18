# SKILL: ai_narrative_rotation_radar

> Read-only AI market narrative intelligence terminal.
> Detects theme leadership rotation, breadth expansion/narrowing, and capital flow transitions.
> Never trades. Never generates buy/sell signals.

---

## Purpose

Monitor AI-related equity themes via a sensor-based watchlist. Deliver structured
Telegram intelligence summaries on schedule. Identify narrative rotations and
breadth changes before they are widely recognized.

---

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Watchlist (core + secondary) | YAML config | `config.yaml` | yes |
| Theme buckets | YAML config | `config.yaml` | yes |
| Price history | yfinance API | public, free | yes |
| Telegram credentials | env | `.env` | yes |
| LLM API keys | env | `.env` | no (V1 template-only) |

---

## Outputs

| Output | Type | Schedule |
|--------|------|----------|
| Daily close summary | Telegram | 16:30 ET Mon–Fri |
| Rotation alert | Telegram | event-driven, throttled |
| Weekly narrative review | Telegram | 10:00 ET Saturday |
| Daily snapshots | SQLite + CSV | on each daily run |

---

## LLM Routing (AGENTS.md compliance)

| Task | Tier | Rationale |
|------|------|-----------|
| Price fetch, RS compute, breadth, rotation | RULE | deterministic math only |
| Alert throttle | RULE | state machine, no LLM |
| Alert / report formatting (V1) | RULE | template-based, no LLM needed |
| Telegram formatting enrichment | QWEN | future: when `llm_enrichment.enabled=true` |
| Weekly narrative interpretation | CC | future: when `llm_enrichment.enabled=true` |

CC retains override authority on all routing decisions.

---

## Workflow

```
Scheduler (APScheduler, America/New_York):
  ├── Mon-Fri 16:30 ET → run_daily_close()
  │     1. build_snapshot(cfg, prior_snapshot)    ← RULE
  │        ├── fetch_price_history()              ← yfinance
  │        ├── compute_ticker_metrics()           ← RULE
  │        ├── compute_theme_breadth()            ← RULE
  │        └── detect_rotation()                 ← RULE
  │     2. db.save_snapshot()                     ← SQLite
  │     3. db.export_csv()                        ← CSV
  │     4. alert.send(format_daily_summary())     ← Telegram
  │     5. maybe_send_rotation_alert()            ← throttled
  │
  └── Saturday 10:00 ET → run_weekly_review()
        1. build_snapshot()
        2. alert.send(format_weekly_review())
```

---

## Theme Buckets

| Key | Name | Tickers |
|-----|------|---------|
| ai_compute_asic | AI Compute / ASIC | AVGO, MRVL, ALAB, NBIS |
| hbm_memory | HBM / Memory | MU, MRVL |
| ai_networking | AI Networking / Connectivity | CRDO, ALAB, APH, ASTS |
| optical_photonics | Optical / Photonics | COHR, AAOI, MTSI, POET, LWLG |
| datacenter_power | Datacenter Power / Cooling | VRT, FLNC, APLD, STRL, PRIM |
| cloud_platforms | Cloud Platforms | MSFT, GOOGL, AMZN, AAPL, CRM, SNOW, NOW, DOCN |
| cybersecurity | Cybersecurity | FTNT, NET, ZETA, FSLY |
| ai_defense_satellite | AI Defense / Satellite | BKSY, ASTS, LDOS |
| crypto_trading_infra | Crypto / Trading Infrastructure | IBKR, HOOD, CLSK, IREN |
| frontier_speculation | Frontier Speculation | OKLO, RGTI, LAES, AXSM |
| legacy_saas | Legacy SaaS / Workflow | INTC, TOST, CRM, SNOW |

---

## Key Metrics

- **RS vs SPY/QQQ/SOXX**: 1D / 5D / 1M excess return
- **Breadth**: % of theme tickers with positive RS vs SPY 1M
- **MA structure**: above/below 20/50/200DMA + slope
- **Volume ratio**: current / 20D average
- **Theme signal**: STRONG / BROADENING / NEUTRAL / NARROWING / WEAK
- **Rotation**: 5D RS delta across themes, confidence 0–100

---

## Storage

```
data/ai_narrative_rotation_radar/
├── radar.db              ← SQLite (daily_snapshots, theme_scores, signal_events)
└── csv/
    ├── snapshots_YYYY-MM-DD.csv
    └── themes_YYYY-MM-DD.csv

logs/ai_narrative_rotation_radar/
├── main.log
├── ai_narrative_rotation_radar.pid
└── alert_state.json
```

---

## Start Command

```bash
cd agents/ai_narrative_rotation_radar
cp .env.example .env   # fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
python -m venv .venv && .venv/bin/pip install -r requirements.txt
nohup .venv/bin/python main.py \
  > ../../logs/ai_narrative_rotation_radar/stdout.log 2>&1 \
  & echo $! > ../../logs/ai_narrative_rotation_radar/ai_narrative_rotation_radar.pid
```

---

## Constraints (hard)

- READ-ONLY. No trading, no brokerage API, no order placement.
- Never expose API keys in logs.
- Alert throttle: max 5/day, 4h cooldown per type.
- `defensive_excluded` theme never influences trend scoring.
- Telegram token and chat ID must come from `.env` only.
