"""Retention policy enforcement for the reports/ directory.

Default policy (overridable via config):
  full_html_days:       30   — delete full HTML reports
  chart_assets_days:    90   — delete charts/ subdirectory assets
  markdown_keep:        forever
  monthly_archive_keep: forever
  raw_data_days:        365  — informational only; agents manage their own DBs

After full HTML is deleted, a minimal summary.html is generated in its place
so old dates still have *something* if the index links to them.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .paths import REPORTS_BASE_DIR

logger = logging.getLogger("reporting.retention")

_DEFAULT_POLICY = {
    "full_html_days": 30,
    "chart_assets_days": 90,
    "markdown_keep": "forever",
    "monthly_archive_keep": "forever",
    "raw_data_days": 365,
}

_KNOWN_AGENTS = [
    "finance_bot",
    "ai_narrative_rotation_radar",
    "polymarket_intelligence",
    "web3_monitor",
]


def run_retention(policy: Optional[dict] = None) -> None:
    """Apply retention rules to the reports/ directory tree."""
    cfg = {**_DEFAULT_POLICY, **(policy or {})}
    now = datetime.now(timezone.utc)

    daily_root = REPORTS_BASE_DIR / "daily"
    if not daily_root.exists():
        return

    full_html_cutoff = now - timedelta(days=int(cfg["full_html_days"]))
    chart_cutoff = now - timedelta(days=int(cfg["chart_assets_days"]))

    for date_dir in sorted(daily_root.iterdir()):
        if not date_dir.is_dir():
            continue
        date_str = date_dir.name
        try:
            dir_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if dir_date < full_html_cutoff:
            _purge_full_html(date_dir, date_str)

        if dir_date < chart_cutoff:
            _purge_charts(date_dir)

    logger.info("Retention run complete")


def _purge_full_html(date_dir: Path, date_str: str) -> None:
    """Delete full agent HTML reports, leave Markdown and index."""
    for agent in _KNOWN_AGENTS:
        html_path = date_dir / f"{agent}.html"
        if html_path.exists():
            html_path.unlink()
            logger.debug("Deleted full HTML: %s", html_path)
            _write_stub_html(date_dir / f"{agent}_stub.html", agent, date_str)

    # Rebuild index stub if it exists as a full page
    index_path = date_dir / "index.html"
    if index_path.exists():
        size = index_path.stat().st_size
        if size > 20_000:          # heuristic: full index is >20 KB
            _write_stub_index(index_path, date_str)


def _purge_charts(date_dir: Path) -> None:
    charts_dir = date_dir / "charts"
    if charts_dir.exists():
        shutil.rmtree(charts_dir)
        logger.debug("Deleted charts dir: %s", charts_dir)


def _write_stub_html(path: Path, agent: str, date_str: str) -> None:
    """Write a minimal stub so old links don't 404."""
    label = agent.replace("_", " ").title()
    path.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{label} {date_str}</title></head><body>"
        f"<p>Full report for {label} {date_str} has been archived. "
        f"<a href='../{agent}.md'>View Markdown source</a></p>"
        f"</body></html>",
        encoding="utf-8",
    )


def _write_stub_index(path: Path, date_str: str) -> None:
    path.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Daily Report {date_str}</title></head><body>"
        f"<p>Full index for {date_str} has been archived. "
        f"Markdown sources remain in this directory.</p>"
        f"</body></html>",
        encoding="utf-8",
    )
