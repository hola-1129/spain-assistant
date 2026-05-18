"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

Protocols and data types for the Northstar SignalOS unified LLM layer.

All model outputs are typed. DraftOutput travels from provider → gate.
ValidatedOutput is the only type that may reach Telegram or other delivery systems.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


SourceTag = Literal["qwen", "codex", "claude", "rule"]


@dataclass
class DraftOutput:
    """Raw output from any model provider. NOT safe for direct delivery."""
    text: str
    source: SourceTag
    model: str
    validated: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class ValidatedOutput:
    """Output that has passed OutputGate. Safe for delivery pipelines."""
    text: str
    source: SourceTag
    model: str
    validated: bool = True
    gate_passed: bool = True
    metadata: dict = field(default_factory=dict)


class LLMClient(Protocol):
    """Protocol all provider clients must satisfy."""
    def complete(self, system: str, user: str) -> DraftOutput: ...
    def complete_json(self, system: str, user: str) -> dict: ...
