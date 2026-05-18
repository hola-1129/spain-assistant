"""Write ReportData to a Markdown file and parse frontmatter back out.

Markdown is the source of truth. This module handles:
- Serialising ReportData → .md with YAML frontmatter
- Parsing frontmatter from existing .md files (for index_builder)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import yaml

from .base_report import ReportData
from .paths import agent_md_path, agent_report_url

logger = logging.getLogger("reporting.md_writer")

_SEPARATOR = "\n---\n\n"  # frontmatter fence (already included in to_frontmatter)


def write_report(report: ReportData) -> Path:
    """Serialise report to Markdown, return the written path."""
    date = report.meta.date
    agent = report.meta.agent

    # Inject URL before writing
    if not report.meta.report_url:
        report.meta.report_url = agent_report_url(date, agent)

    path = agent_md_path(date, agent)
    body = _build_body(report)
    path.write_text(report.meta.to_frontmatter() + "\n" + body, encoding="utf-8")
    logger.info("Report written: %s", path)
    return path


def _build_body(report: ReportData) -> str:
    agent_title = report.meta.agent.replace("_", " ").title()
    lines = [f"# {agent_title} Daily Report — {report.meta.date}", ""]

    if report.meta.summary:
        lines += [f"> {report.meta.summary}", ""]

    for section in report.sections:
        lines += [f"## {section.title}", ""]
        lines += [section.content.strip(), ""]

    return "\n".join(lines)


# ── Frontmatter parser (used by index_builder) ────────────────────────────────

def parse_frontmatter(path: Path) -> Optional[Dict]:
    """Return frontmatter dict from a .md file, or None if missing/malformed."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not text.startswith("---"):
        return None

    # Find closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return None

    try:
        return yaml.safe_load(text[3:end])
    except yaml.YAMLError as exc:
        logger.warning("Bad frontmatter in %s: %s", path, exc)
        return None
