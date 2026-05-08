"""Tool registry. Each tool registers via @tool decorator and is invoked via REGISTRY.call(name, args).

The registry is the single integration point: agents call it, tests call it,
the MCP server proxies through it. Tools never know who called them.
"""
from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from .envelope import ToolOutput
from .tracing import gen_trace_id, log_event


@dataclass
class ToolSpec:
    name: str
    version: str
    description: str
    args_schema: Type[BaseModel]
    data_schema: Type[BaseModel]
    side_effects: bool
    fn: Callable[..., Any]

    def to_mcp_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.args_schema.model_json_schema(),
        }


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    async def call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        trace_id: str | None = None,
        caller: str | None = None,
    ) -> ToolOutput:
        trace_id = trace_id or gen_trace_id()
        meta_base = {"trace_id": trace_id, "tool": name}

        try:
            spec = self.get(name)
        except KeyError as e:
            return ToolOutput.fail("UNKNOWN_TOOL", str(e), **meta_base)

        try:
            parsed = spec.args_schema.model_validate(args or {})
        except ValidationError as e:
            return ToolOutput.fail("INVALID_ARGS", str(e), **meta_base)

        log_event("tool.start", caller=caller, **meta_base)
        t0 = time.perf_counter()
        try:
            result = spec.fn(parsed)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log_event("tool.error", error=repr(e), latency_ms=latency_ms, **meta_base)
            return ToolOutput.fail("TOOL_EXCEPTION", repr(e), latency_ms=latency_ms, **meta_base)

        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            data = result if isinstance(result, dict) else result.model_dump()
            spec.data_schema.model_validate(data)
        except (ValidationError, AttributeError) as e:
            log_event("tool.bad_output", error=str(e), latency_ms=latency_ms, **meta_base)
            return ToolOutput.fail("INVALID_OUTPUT", str(e), latency_ms=latency_ms, **meta_base)

        log_event("tool.ok", latency_ms=latency_ms, **meta_base)
        return ToolOutput(
            ok=True,
            data=data,
            meta={**meta_base, "latency_ms": latency_ms, "tool_version": spec.version},
        )


REGISTRY = Registry()


def tool(
    *,
    name: str,
    version: str,
    description: str,
    args_schema: Type[BaseModel],
    data_schema: Type[BaseModel],
    side_effects: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = ToolSpec(
            name=name,
            version=version,
            description=description,
            args_schema=args_schema,
            data_schema=data_schema,
            side_effects=side_effects,
            fn=fn,
        )
        REGISTRY.register(spec)
        fn.__tool_spec__ = spec  # type: ignore[attr-defined]
        return fn

    return decorator
