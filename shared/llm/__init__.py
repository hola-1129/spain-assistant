"""
Northstar SignalOS — Unified LLM Layer

Primary entry point:
    from shared.llm.gateway import LLMGateway
    from shared.llm.model_router import TaskType, ModelTier

Output types:
    from shared.llm.interface import DraftOutput, ValidatedOutput
"""
# Core types — always safe to import (no SDK dependencies)
from .interface import DraftOutput, ValidatedOutput
from .model_router import ModelTier, TaskType, route

# LLMGateway is imported lazily by callers to avoid pulling in SDK dependencies
# at module load time in agents that only have partial SDK installs.
# Usage: from shared.llm.gateway import LLMGateway

__all__ = [
    "DraftOutput",
    "ValidatedOutput",
    "ModelTier",
    "TaskType",
    "route",
]
