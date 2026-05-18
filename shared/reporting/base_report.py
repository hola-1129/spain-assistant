"""Core data model for the unified reporting layer.

All agents build a ReportData and hand it to the shared rendering pipeline.
Nothing in here depends on any agent-specific code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

RiskLevel = Literal["low", "medium", "high", "critical"]
OpportunityLevel = Literal["none", "low", "medium", "high"]


@dataclass
class ReportMeta:
    """Frontmatter fields — extracted by index_builder without parsing body."""
    agent: str                          # e.g. "finance_bot"
    date: str                           # YYYY-MM-DD
    generated_at: str = ""              # ISO-8601 UTC
    version: int = 1
    summary: str = ""                   # ≤80 chars, for index page & Telegram
    risk_level: RiskLevel = "low"
    opportunity_level: OpportunityLevel = "low"
    report_url: str = ""                # filled in by paths.py after file is written

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_frontmatter(self) -> str:
        return (
            "---\n"
            f"agent: {self.agent}\n"
            f"date: \"{self.date}\"\n"
            f"generated_at: \"{self.generated_at}\"\n"
            f"version: {self.version}\n"
            f"summary: \"{self.summary}\"\n"
            f"risk_level: {self.risk_level}\n"
            f"opportunity_level: {self.opportunity_level}\n"
            f"report_url: \"{self.report_url}\"\n"
            "---\n"
        )


@dataclass
class ChartDataset:
    label: str
    data: List[float]
    color: Optional[str] = None         # hex or rgba; auto-assigned if None


@dataclass
class ChartSpec:
    """Minimal Chart.js config embedded as JSON in the HTML."""
    chart_type: Literal["line", "bar", "doughnut", "radar"] = "bar"
    labels: List[str] = field(default_factory=list)
    datasets: List[ChartDataset] = field(default_factory=list)
    title: str = ""
    y_suffix: str = ""                  # e.g. "%" or "$"
    height_px: int = 200


@dataclass
class ReportSection:
    title: str
    content: str                        # Markdown body (tables, bullets, prose)
    collapsed: bool = False             # default-collapsed in HTML
    chart: Optional[ChartSpec] = None   # if set, renders a Chart.js block
    section_id: str = ""               # auto-set from title if empty

    def __post_init__(self) -> None:
        if not self.section_id:
            self.section_id = (
                self.title.lower()
                .replace(" ", "-")
                .replace("/", "-")
                .strip("-")
            )


@dataclass
class ReportData:
    meta: ReportMeta
    sections: List[ReportSection] = field(default_factory=list)
    # Extra structured data passed through to templates (agent-specific dicts).
    # Agents may put anything here; templates that don't know it just ignore it.
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_agent(
        cls,
        agent: str,
        date: str,
        summary: str = "",
        risk_level: RiskLevel = "low",
        opportunity_level: OpportunityLevel = "low",
    ) -> "ReportData":
        return cls(
            meta=ReportMeta(
                agent=agent,
                date=date,
                summary=summary,
                risk_level=risk_level,
                opportunity_level=opportunity_level,
            )
        )

    def add_section(
        self,
        title: str,
        content: str,
        collapsed: bool = False,
        chart: Optional[ChartSpec] = None,
    ) -> "ReportData":
        """Fluent builder helper."""
        self.sections.append(ReportSection(title=title, content=content, collapsed=collapsed, chart=chart))
        return self
