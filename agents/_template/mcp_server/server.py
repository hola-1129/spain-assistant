"""Expose registered tools over MCP. Lazy import — agent runs fine without `mcp` installed.

Same registry, same schemas, same handler functions. The MCP layer is only an adapter.
"""
from __future__ import annotations

from shared.core import REGISTRY


def build_server(name: str = "agent-template"):
    """Build an MCP Server proxying every registered tool. Requires `pip install mcp`."""
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError as e:
        raise RuntimeError(
            "mcp package not installed; run `pip install mcp` to enable MCP server"
        ) from e

    srv = Server(name)

    @srv.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.args_schema.model_json_schema(),
            )
            for spec in REGISTRY.all()
        ]

    @srv.call_tool()
    async def _call_tool(tool_name: str, arguments: dict) -> list[TextContent]:
        out = await REGISTRY.call(tool_name, arguments, caller="mcp")
        return [TextContent(type="text", text=out.model_dump_json())]

    return srv
