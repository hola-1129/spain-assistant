#!/usr/bin/env python3
"""Web3 Monitor entrypoint.

Business capabilities live in MCP-ready tool functions. The agent orchestrator
only schedules and composes those tools.
"""
from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from agent_orchestrator import Web3MonitorAgent  # noqa: E402


def parse_args() -> object:
    parser = ArgumentParser(description="Web3 Monitor v2 MCP-ready read-only agent")
    parser.add_argument("--once", action="store_true", help="run one monitor cycle and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent = Web3MonitorAgent(_HERE.parent)
    if args.once:
        agent.run_once()
        return 0
    return agent.run_forever()


if __name__ == "__main__":
    sys.exit(main())
