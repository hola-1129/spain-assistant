# Polymarket Intelligence Monitor

Read-only Polymarket intelligence radar. Monitors prediction markets, detects rapid probability repricing and liquidity spikes, scores signals, and sends Telegram alerts.

---

## What this does

- Fetches active Polymarket markets every N seconds (default: 120s)
- Filters markets by volume, liquidity, and keyword rules
- Saves price/liquidity snapshots to SQLite for backtesting
- Detects: rapid probability moves (5m / 15m / 60m) and liquidity spikes
- Scores each signal 0–100 based on magnitude, keywords, volume, and spread
- Sends Telegram alerts for signals scoring ≥ threshold (default: 75)

## What this does NOT do

- No wallet connection
- No private keys or secrets beyond Telegram credentials
- No trades, orders, or any write interaction with Polymarket
- No authenticated API calls

---

## Setup

```bash
cd agents/polymarket_intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configure .env

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Get a bot token from [@BotFather](https://t.me/BotFather). Get your chat ID by messaging your bot and calling `getUpdates`.

---

## How to run

**Foreground:**
```bash
cd agents/polymarket_intelligence
.venv/bin/python main.py
```

**Background (production):**
```bash
cd agents/polymarket_intelligence
nohup .venv/bin/python main.py \
  > ../../logs/polymarket_intelligence/stdout.log 2>&1 \
  & echo $! > ../../logs/polymarket_intelligence/polymarket_intelligence.pid
```

**Stop:**
```bash
kill $(cat ../../logs/polymarket_intelligence/polymarket_intelligence.pid)
```

---

## Test Telegram

Set `dry_run: false` in `config.yaml` temporarily and run one cycle. The alert will be sent on the first signal that exceeds the score threshold.

To force-test the formatter without waiting for a real signal, run:

```python
from modules.telegram import send_alert
signal = {
    "signal_type": "rapid_reprice_15m",
    "probability_before": 0.42,
    "probability_after": 0.56,
    "probability_delta": 0.14,
    "window_minutes": 15,
    "liquidity_delta": None,
    "reason": "Test alert — rapid 15m move threshold exceeded.",
}
market = {
    "id": "test-market",
    "question": "Will the Fed cut rates in June?",
    "event_title": "Fed / Macro",
    "volume": 420000,
    "liquidity": 96000,
    "url": "https://polymarket.com/event/test",
}
send_alert(signal, market, 84, "YOUR_TOKEN", "YOUR_CHAT_ID", dry_run=False)
```

---

## Signal scoring

| Component | Points |
|-----------|--------|
| Rapid 5m reprice (≥5%) | +35 |
| Rapid 15m reprice (≥8%) | +30 |
| Rapid 60m reprice (≥12%) | +25 |
| Liquidity spike (≥1.5× and +$10k) | +20 |
| Priority keyword match | +20 |
| Volume > $250k | +10 |
| Liquidity > $100k | +10 |
| Spread ≤ 0.04 | +10 |
| Spread > max_spread (0.08) | −20 |
| Volume < $50k | −20 |
| Closing within 6 hours | −15 |

Score is capped at 100. Alerts fire when score ≥ `signal_alert_threshold` (default 75).

Markets matching `ignored_keywords` (NBA, NFL, etc.) are skipped entirely before scoring.

---

## SQLite schema

**`markets`** — one row per market, upserted each cycle. Tracks metadata.

**`market_snapshots`** — append-only price/liquidity snapshot per market per cycle. Used for signal detection and backtesting.

**`signal_events`** — one row per detected signal. Includes score, delta, reason, and market URL. Also mirrored to `logs/signal_events.csv`.

Database path: `storage/intelligence.db`

---

## Config reference

Key settings in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval_seconds` | 120 | Seconds between cycles |
| `min_market_volume` | 50000 | Skip markets with volume below this |
| `min_market_liquidity` | 25000 | Skip markets with liquidity below this |
| `max_spread` | 0.08 | Spread above this reduces score |
| `signal_alert_threshold` | 75 | Minimum score to send Telegram alert |
| `runtime.dry_run` | true | `true` = log alerts, never send to Telegram |

---

## Known limitations

- CLOB orderbook data may be unavailable for some markets; the system falls back to Gamma prices (spread will show N/A)
- Price history is only as deep as the local snapshot history — signals won't fire on the first cycle
- Polymarket API response shape may change; field names are mapped by convention
- No deduplication of repeated signals across cycles for the same market

## Roadmap (V2 ideas)

- Cross-market correlation detection (e.g., BTC + ETH + Fed markets moving together)
- Alert deduplication / cooldown per market
- Web dashboard for browsing signal history
- Backtest mode: replay stored snapshots through signal engine
- Slack / Discord delivery in addition to Telegram
