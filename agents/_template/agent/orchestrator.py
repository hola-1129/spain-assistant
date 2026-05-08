"""Pure orchestration: plan → dispatch → compose. Zero business logic lives here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.core import Registry, ToolOutput, gen_trace_id


@dataclass
class Step:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    name: str
    steps: list[Step]


class Orchestrator:
    def __init__(self, registry: Registry, *, agent_name: str = "template") -> None:
        self.registry = registry
        self.agent_name = agent_name

    async def run(self, task: Task) -> list[ToolOutput]:
        trace_id = gen_trace_id()
        results: list[ToolOutput] = []
        for step in task.steps:
            out = await self.registry.call(
                step.tool, step.args, trace_id=trace_id, caller=self.agent_name
            )
            results.append(out)
            if not out.ok:
                break
        return results
