"""Path conventions for the reporting layer.

All paths derived from REPORTS_BASE_DIR (default: ai_workspace/reports/).
Override via env var REPORTS_BASE_DIR or reporting.base_dir in config.
"""
from __future__ import annotations

import os
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REPORTS_DIR = _WORKSPACE_ROOT / "reports"

# Override with env var if set
REPORTS_BASE_DIR = Path(os.environ.get("REPORTS_BASE_DIR", str(_DEFAULT_REPORTS_DIR)))

# Base URL used in Telegram links — override via env var or config
_DEFAULT_BASE_URL = f"file://{REPORTS_BASE_DIR}"
REPORTS_BASE_URL = os.environ.get("REPORTS_BASE_URL", _DEFAULT_BASE_URL)


def daily_dir(date: str) -> Path:
    """Return (and create) the directory for a given date's reports."""
    d = REPORTS_BASE_DIR / "daily" / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def monthly_dir(year_month: str) -> Path:
    """Return (and create) the directory for a given month's archive."""
    d = REPORTS_BASE_DIR / "monthly" / year_month
    d.mkdir(parents=True, exist_ok=True)
    return d


def agent_md_path(date: str, agent: str) -> Path:
    return daily_dir(date) / f"{agent}.md"


def agent_html_path(date: str, agent: str) -> Path:
    return daily_dir(date) / f"{agent}.html"


def daily_index_path(date: str) -> Path:
    return daily_dir(date) / "index.html"


def daily_nav_index_path() -> Path:
    p = REPORTS_BASE_DIR / "daily" / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def monthly_index_path(year_month: str) -> Path:
    return monthly_dir(year_month) / "index.html"


def agent_report_url(date: str, agent: str) -> str:
    return f"{REPORTS_BASE_URL}/daily/{date}/{agent}.html"


def daily_index_url(date: str) -> str:
    return f"{REPORTS_BASE_URL}/daily/{date}/index.html"
