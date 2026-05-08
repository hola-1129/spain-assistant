"""Echo tool unit test. Demonstrates per-tool isolation: no agent, no MCP, just registry."""
from __future__ import annotations

import asyncio

from shared.core import REGISTRY
import tools  # noqa: F401  -- triggers @tool registration


def test_echo_success():
    out = asyncio.run(REGISTRY.call("echo", {"message": "hi"}))
    assert out.ok
    assert out.data == {"echoed": "hi", "length": 2}
    assert out.meta["tool"] == "echo"
    assert out.meta["tool_version"] == "1.0.0"


def test_echo_invalid_args():
    out = asyncio.run(REGISTRY.call("echo", {}))
    assert not out.ok
    assert out.error.code == "INVALID_ARGS"


def test_unknown_tool():
    out = asyncio.run(REGISTRY.call("nonexistent", {}))
    assert not out.ok
    assert out.error.code == "UNKNOWN_TOOL"
