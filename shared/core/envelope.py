"""Unified tool I/O envelope. Every tool consumes args via ToolInput and returns ToolOutput."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolError(BaseModel):
    code: str
    message: str
    retriable: bool = False


class ToolInput(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    caller: str | None = None


class ToolOutput(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(cls, data: dict[str, Any], **meta: Any) -> "ToolOutput":
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str, retriable: bool = False, **meta: Any) -> "ToolOutput":
        return cls(
            ok=False,
            error=ToolError(code=code, message=message, retriable=retriable),
            meta=meta,
        )
