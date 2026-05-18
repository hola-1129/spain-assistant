# Holaflow Dashboard

Personal read-only dashboard for Web3 Monitor v2.

## Local Run

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/web3_monitor
.venv/bin/python dashboard/app.py
```

Open:

```text
http://127.0.0.1:8787/
```

The dashboard reads:

```text
data/web3_monitor.db
```

It does not expose `.env`, Telegram tokens, private keys, or any trading action.

## iOS / Mobile

- Mobile-first responsive layout
- 44px touch controls
- Dark mode and light mode
- PWA manifest for "Add to Home Screen"

## Domain: holaflow.xyz

Recommended personal setup:

1. Put the domain on Cloudflare DNS.
2. Run this dashboard locally on `127.0.0.1:8787`.
3. Create a Cloudflare Tunnel from `holaflow.xyz` or `monitor.holaflow.xyz` to `http://127.0.0.1:8787`.
4. Set `DASHBOARD_PASSWORD` in `.env` before exposing it beyond localhost.
5. Optionally add Cloudflare Access for email-based login.

For 24/7 uptime, move the whole `web3_monitor` directory to a small VPS and point
`holaflow.xyz` to the VPS with HTTPS.

## Environment

```bash
DASHBOARD_USERNAME=holaflow
DASHBOARD_PASSWORD=
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8787
```

If `DASHBOARD_PASSWORD` is empty, the server only allows localhost clients.
