"""Build index pages from existing report files.

daily index   — reads frontmatter from each agent's .md for a given date,
                enriches with section previews and 7-day history chart data.
monthly index — aggregates all daily indexes for a given month.
nav index     — reports/daily/index.html listing recent dates with per-date metadata.
cross brief   — builds the combined Telegram message after all agents have reported.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from .md_writer import parse_frontmatter
from .paths import (
    REPORTS_BASE_DIR,
    daily_dir,
    daily_index_path,
    daily_index_url,
    daily_nav_index_path,
    monthly_dir,
    monthly_index_path,
)

logger = logging.getLogger("reporting.index_builder")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

_KNOWN_AGENTS = [
    "finance_bot",
    "ai_narrative_rotation_radar",
    "polymarket_intelligence",
    "web3_monitor",
]

_AGENT_EMOJI = {
    "finance_bot":                 "📈",
    "ai_narrative_rotation_radar": "🧭",
    "polymarket_intelligence":     "🎯",
    "web3_monitor":                "⛓",
}

_AGENT_LABEL = {
    "finance_bot":                 "Finance Bot",
    "ai_narrative_rotation_radar": "AI Narrative Radar",
    "polymarket_intelligence":     "Polymarket Intelligence",
    "web3_monitor":                "Web3 Monitor",
}

_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_OPP_ORDER  = {"none": 0, "low": 1, "medium": 2, "high": 3}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _risk_num(level: str) -> int:
    return _RISK_ORDER.get(str(level).lower(), 1)


def _opp_num(level: str) -> int:
    return _OPP_ORDER.get(str(level).lower(), 0)


def _highest_risk(entries: List[Dict]) -> str:
    """Return the most severe risk_level among a list of frontmatter dicts."""
    best = "low"
    for e in entries:
        r = str(e.get("risk_level") or "low").lower()
        if _risk_num(r) > _risk_num(best):
            best = r
    return best


def _highest_opp(entries: List[Dict]) -> str:
    """Return the highest opportunity_level among entries."""
    best = "none"
    for e in entries:
        o = str(e.get("opportunity_level") or "none").lower()
        if _opp_num(o) > _opp_num(best):
            best = o
    return best


def _read_section_preview(md_path: Path, max_chars: int = 200) -> str:
    """Extract a short preview from the first markdown section body.

    Skips frontmatter and the section heading line; strips table/markdown
    syntax; returns plain text up to max_chars.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---\n", 3)
        if end != -1:
            text = text[end + 5:]

    # Find first ## heading then take the content after it
    m = re.search(r"^## .+\n", text, re.MULTILINE)
    if not m:
        body = text.strip()
    else:
        body = text[m.end():].strip()

    # Strip markdown table rows (lines starting with |)
    lines = [l for l in body.splitlines() if not l.startswith("|") and not l.startswith("---")]
    cleaned = " ".join(" ".join(lines).split())  # normalise whitespace

    # Remove markdown bold/italic markers
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)

    return (cleaned[:max_chars] + "…") if len(cleaned) > max_chars else cleaned


def _read_agents_for_date(date: str) -> List[Dict]:
    """Return a list of enriched frontmatter dicts for all agents that reported on date."""
    date_dir = daily_dir(date)
    entries: List[Dict] = []
    for agent in _KNOWN_AGENTS:
        md_path = date_dir / f"{agent}.md"
        if not md_path.exists():
            entries.append({
                "agent":             agent,
                "present":           False,
                "risk_level":        "low",
                "opportunity_level": "none",
                "summary":           "",
                "preview":           "",
                "emoji":             _AGENT_EMOJI.get(agent, "•"),
                "label":             _AGENT_LABEL.get(agent, agent),
                "risk_num":          1,
                "opp_num":           0,
            })
            continue
        fm = parse_frontmatter(md_path) or {}
        fm["agent"]    = fm.get("agent", agent)
        fm["present"]  = True
        fm["emoji"]    = _AGENT_EMOJI.get(agent, "•")
        fm["label"]    = _AGENT_LABEL.get(agent, agent)
        fm["preview"]  = _read_section_preview(md_path)
        fm["risk_num"] = _risk_num(str(fm.get("risk_level") or "low"))
        fm["opp_num"]  = _opp_num(str(fm.get("opportunity_level") or "none"))
        entries.append(fm)
    return entries


def _load_history(nav_dates: List[str], limit: int = 7) -> List[Dict]:
    """For each date in nav_dates (up to limit), load per-agent risk/opp numbers.

    Returns list of {"date": str, "risk": {agent: int}, "opp": {agent: int}}.
    """
    history: List[Dict] = []
    for date in nav_dates[-limit:]:
        date_dir = daily_dir(date)
        risk_map: Dict[str, int] = {}
        opp_map:  Dict[str, int] = {}
        for agent in _KNOWN_AGENTS:
            md_path = date_dir / f"{agent}.md"
            if not md_path.exists():
                continue
            fm = parse_frontmatter(md_path) or {}
            risk_map[agent] = _risk_num(str(fm.get("risk_level") or "low"))
            opp_map[agent]  = _opp_num(str(fm.get("opportunity_level") or "none"))
        if risk_map:
            history.append({"date": date, "risk": risk_map, "opp": opp_map})
    return history


# ── Public builders ───────────────────────────────────────────────────────────

def build_daily_index(date: str, nav_dates: Optional[List[str]] = None) -> Optional[Path]:
    """Build the cross-agent index.html for a given date.

    Reads frontmatter + section preview for each agent.
    Includes 7-day history chart data (from nav_dates if provided).
    """
    entries = _read_agents_for_date(date)
    present = [e for e in entries if e.get("present")]
    if not present:
        logger.warning("No reports found for %s, skipping index build", date)
        return None

    effective_nav = nav_dates or []
    # If nav_dates provided, use last 7 for history; else just today
    history = _load_history(effective_nav) if effective_nav else []

    max_risk = _highest_risk(present)
    max_opp  = _highest_opp(present)

    # Serialise history for Chart.js
    history_json = json.dumps(history)

    template = _jinja.get_template("daily_index.html.j2")
    html = template.render(
        date=date,
        entries=entries,
        present=present,
        nav_dates=effective_nav,
        history=history,
        history_json=history_json,
        max_risk=max_risk,
        max_opp=max_opp,
        known_agents=_KNOWN_AGENTS,
        agent_label=_AGENT_LABEL,
        agent_emoji=_AGENT_EMOJI,
    )
    path = daily_index_path(date)
    path.write_text(html, encoding="utf-8")
    logger.info("Daily index written: %s  risk=%s  opp=%s", path, max_risk, max_opp)
    return path


def build_nav_index(limit: int = 30) -> Path:
    """Rebuild reports/daily/index.html with the most recent dates.

    Each date card shows per-agent availability dots and highest risk badge.
    """
    daily_root = REPORTS_BASE_DIR / "daily"
    raw_dates = sorted(
        (d.name for d in daily_root.iterdir() if d.is_dir() and not d.name.endswith(".html")),
        reverse=True,
    )[:limit]

    date_cards: List[Dict] = []
    for date in raw_dates:
        entries = _read_agents_for_date(date)
        present = [e for e in entries if e.get("present")]
        date_cards.append({
            "date":     date,
            "entries":  entries,
            "present":  present,
            "max_risk": _highest_risk(present) if present else "low",
            "max_opp":  _highest_opp(present) if present else "none",
            "count":    len(present),
        })

    template = _jinja.get_template("nav_index.html.j2")
    html = template.render(
        date_cards=date_cards,
        known_agents=_KNOWN_AGENTS,
        agent_emoji=_AGENT_EMOJI,
        agent_label=_AGENT_LABEL,
    )
    path = daily_nav_index_path()
    path.write_text(html, encoding="utf-8")
    logger.info("Nav index written: %s  (%d dates)", path, len(date_cards))
    return path


def build_monthly_index(year_month: str) -> Optional[Path]:
    """Aggregate all daily indexes for a month into a monthly summary page.

    Renders a risk-heatmap table (dates × agents) with colour-coded cells.
    """
    daily_root = REPORTS_BASE_DIR / "daily"
    day_dirs = sorted(
        (d for d in daily_root.iterdir() if d.is_dir() and d.name.startswith(year_month)),
        key=lambda d: d.name,
        reverse=True,
    )
    if not day_dirs:
        return None

    month_days: List[Dict] = []
    for date_dir in day_dirs:
        date = date_dir.name
        entries = _read_agents_for_date(date)
        present = [e for e in entries if e.get("present")]
        if not present:
            continue
        month_days.append({
            "date":    date,
            "entries": entries,
            "max_risk": _highest_risk(present),
        })

    if not month_days:
        return None

    template = _jinja.get_template("monthly_index.html.j2")
    html = template.render(
        year_month=year_month,
        month_days=month_days,
        known_agents=_KNOWN_AGENTS,
        agent_emoji=_AGENT_EMOJI,
        agent_label=_AGENT_LABEL,
    )
    path = monthly_index_path(year_month)
    path.write_text(html, encoding="utf-8")
    logger.info("Monthly index written: %s", path)
    return path


def build_cross_brief(date: str) -> str:
    """Build a cross-agent Telegram brief for a date.

    Reads frontmatter from all available agents.  Returns a ≤900-char
    Markdown string suitable for a single daily Telegram send.
    """
    entries = [e for e in _read_agents_for_date(date) if e.get("present")]
    if not entries:
        return f"📊 *Daily Brief｜{date}*\n今日暂无报告。"

    max_risk = _highest_risk(entries)
    max_opp  = _highest_opp(entries)

    _RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    _OPP_EMOJI  = {"none": "", "low": "", "medium": " 💡", "high": " 💡💡"}
    _SEP = "━" * 28

    lines = [
        f"📊 *Daily Intelligence Brief｜{date}*",
        _SEP,
    ]

    # Combined risk line
    risk_e = _RISK_EMOJI.get(max_risk, "")
    opp_e  = _OPP_EMOJI.get(max_opp, "")
    lines.append(f"综合风险：{risk_e} {max_risk.upper()}  机会：{max_opp.upper()}{opp_e}")
    lines.append("")

    for e in entries:
        emoji   = e.get("emoji", "•")
        label   = str(e.get("agent", "")).replace("_", "\\_")
        summary = (e.get("summary") or "—")[:80]
        r_e     = _RISK_EMOJI.get(str(e.get("risk_level") or "low"), "")
        o_e     = _OPP_EMOJI.get(str(e.get("opportunity_level") or "none"), "")
        lines.append(f"{emoji} *{label}*：{summary} {r_e}{o_e}")

    lines += ["", f"👉 [完整日报]({daily_index_url(date)})"]
    return "\n".join(lines)
