"""Shared JSON-style models for MCP-ready tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "data": self.data,
            "signals": self.signals,
            "errors": self.errors,
            "meta": self.meta,
        }


@dataclass
class ToolContext:
    root: Path
    config: dict[str, Any]
    services: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)

    def service(self, name: str) -> Any:
        return self.services[name]
