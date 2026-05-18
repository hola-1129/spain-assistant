"""Unified reporting layer — Markdown → HTML → Telegram brief."""
from .base_report import ReportData, ReportMeta, ReportSection
from .md_writer import write_report
from .html_renderer import render_html
from .telegram_summary import build_brief, send_brief
from .retention import run_retention
from .index_builder import build_cross_brief, build_daily_index, build_monthly_index

__all__ = [
    "ReportData", "ReportMeta", "ReportSection",
    "write_report", "render_html",
    "build_brief", "send_brief",
    "run_retention",
    "build_daily_index", "build_monthly_index", "build_cross_brief",
]
