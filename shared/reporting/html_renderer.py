"""Render a ReportData (or a Markdown file) to an HTML file.

Pipeline:
  ReportData.sections[*].content  → markdown-it-py → HTML fragments
  Jinja2 template                 → full page HTML
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader
from markdown_it import MarkdownIt

from .base_report import ChartSpec, ReportData, ReportSection
from .paths import agent_html_path, daily_index_path

logger = logging.getLogger("reporting.html_renderer")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_md = MarkdownIt("commonmark", {"typographer": True}).enable("table")
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Public API ────────────────────────────────────────────────────────────────

def render_html(report: ReportData, nav_dates: Optional[List[str]] = None) -> Path:
    """Render a single agent report to HTML. Returns the written path."""
    sections_html = [_render_section(s) for s in report.sections]
    template = _jinja.get_template("agent_report.html.j2")
    html = template.render(
        meta=report.meta,
        sections=report.sections,
        sections_html=sections_html,
        nav_dates=nav_dates or [],
        extra=report.extra,
    )
    path = agent_html_path(report.meta.date, report.meta.agent)
    path.write_text(html, encoding="utf-8")
    logger.info("HTML written: %s", path)
    return path


def render_daily_index(
    date: str,
    agent_reports: List[ReportData],
    nav_dates: Optional[List[str]] = None,
) -> Path:
    """Render the cross-agent daily index page."""
    template = _jinja.get_template("daily_index.html.j2")
    html = template.render(
        date=date,
        reports=agent_reports,
        nav_dates=nav_dates or [],
    )
    path = daily_index_path(date)
    path.write_text(html, encoding="utf-8")
    logger.info("Daily index written: %s", path)
    return path


# ── Internal helpers ──────────────────────────────────────────────────────────

def _render_section(section: ReportSection) -> dict:
    """Return a dict with rendered HTML body + chart JSON for template use."""
    html_body = _md.render(section.content) if section.content.strip() else ""
    chart_json = _chart_to_json(section.chart) if section.chart else None
    return {
        "section": section,
        "html_body": html_body,
        "chart_json": chart_json,
    }


_PALETTE = [
    "#60a5fa", "#34d399", "#f97316", "#a78bfa",
    "#f472b6", "#facc15", "#22d3ee", "#fb7185",
]


def _chart_to_json(chart: ChartSpec) -> str:
    """Serialise a ChartSpec to the Chart.js config JSON string."""
    datasets = []
    for i, ds in enumerate(chart.datasets):
        color = ds.color or _PALETTE[i % len(_PALETTE)]
        datasets.append({
            "label": ds.label,
            "data": ds.data,
            "borderColor": color,
            "backgroundColor": color + "33",  # 20% opacity fill
            "tension": 0.3,
            "fill": chart.chart_type == "line",
        })

    cfg: dict = {
        "type": chart.chart_type,
        "data": {"labels": chart.labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"labels": {"color": "#94a3b8"}},
                "title": {
                    "display": bool(chart.title),
                    "text": chart.title,
                    "color": "#e2e8f0",
                },
            },
            "scales": {
                "x": {"ticks": {"color": "#94a3b8"}, "grid": {"color": "#2d3148"}},
                "y": {
                    "ticks": {
                        "color": "#94a3b8",
                        "callback": f"function(v){{return v+'{chart.y_suffix}'}}",
                    },
                    "grid": {"color": "#2d3148"},
                },
            },
        },
    }
    # y-axis tick callback contains JS — can't JSON-encode it cleanly,
    # so we inject it as a raw string placeholder and swap post-encode.
    raw = json.dumps(cfg, ensure_ascii=False)
    # Replace the stringified callback with a real JS function
    placeholder = f'"function(v){{return v+\'{chart.y_suffix}\'}}"'
    real_fn = f"function(v){{return v+'{chart.y_suffix}'}}"
    return raw.replace(placeholder, real_fn)
