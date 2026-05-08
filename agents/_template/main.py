"""Agent entry point. Hard limit: only load config, wire deps, run. No business logic."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = Path(__file__).resolve().parent
for _p in (WORKSPACE, TEMPLATE_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from shared.core import REGISTRY  # noqa: E402

from agent import Orchestrator, Step, Task  # noqa: E402
import tools  # noqa: F401,E402  -- side-effect: register tools


async def main() -> None:
    orch = Orchestrator(REGISTRY, agent_name="template")
    task = Task(name="demo", steps=[Step(tool="echo", args={"message": "hello mcp world"})])
    for r in await orch.run(task):
        print(r.model_dump_json())


if __name__ == "__main__":
    asyncio.run(main())
