#!/usr/bin/env python3
"""Personal read-only Web3 Monitor dashboard.

Serves a small responsive UI and read-only JSON APIs backed by SQLite.
No trading, signing, or secret-returning endpoints are implemented.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(ROOT / "scripts"))

from storage import SignalStore, resolve_db_path  # noqa: E402


def _load_config() -> dict:
    with (ROOT / "config.yaml").open("r") as f:
        return yaml.safe_load(f) or {}


def _json_default(value):
    return str(value)


class DashboardServer(BaseHTTPRequestHandler):
    server_version = "Web3Dashboard/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}")

    @property
    def store(self) -> SignalStore:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def password(self) -> str:
        return self.server.password  # type: ignore[attr-defined]

    @property
    def username(self) -> str:
        return self.server.username  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        if not self.password:
            return self.client_address[0] in {"127.0.0.1", "::1"}
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        user, _, pwd = raw.partition(":")
        return user == self.username and pwd == self.password

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Web3 Monitor"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authentication required")
        return False

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_static(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._send_static(STATIC_DIR / "app.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_static(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/manifest.json":
            self._send_static(STATIC_DIR / "manifest.json", "application/manifest+json; charset=utf-8")
            return
        if path == "/icon.svg":
            self._send_static(STATIC_DIR / "icon.svg", "image/svg+xml")
            return
        if path == "/api/health":
            self._send_json({
                "ok": True,
                "mode": "read_only",
                "db_path": str(self.store.db_path),
                "domain_hint": "holaflow.xyz",
            })
            return
        if path == "/api/summary":
            self._send_json(self.store.get_score_summary())
            return
        if path == "/api/signals/recent":
            query = parse_qs(parsed.query)
            try:
                limit = min(max(int(query.get("limit", ["50"])[0]), 1), 200)
            except ValueError:
                limit = 50
            self._send_json({"signals": self.store.get_recent_signals(limit=limit)})
            return
        if path.startswith("/api/signals/"):
            try:
                signal_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                self._send_json({"error": "invalid signal id"}, status=400)
                return
            row = self.store.get_signal_by_id(signal_id)
            if not row:
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_json(row)
            return
        self.send_error(404)


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    load_dotenv(ROOT / ".env")
    cfg = _load_config()
    store = SignalStore(resolve_db_path(ROOT, cfg))
    server = ThreadingHTTPServer((host, port), DashboardServer)
    server.store = store  # type: ignore[attr-defined]
    server.username = os.environ.get("DASHBOARD_USERNAME", "holaflow")  # type: ignore[attr-defined]
    server.password = os.environ.get("DASHBOARD_PASSWORD", "")  # type: ignore[attr-defined]
    if not server.password:
        print("DASHBOARD_PASSWORD not set; dashboard is localhost-only.")
    print(f"Web3 Dashboard listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("DASHBOARD_PORT", "8787"))
    run(host, port)
