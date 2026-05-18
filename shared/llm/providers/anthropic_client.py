"""
Anthropic/Claude provider client for Northstar SignalOS.

Tier: CC (ModelTier.CC)
Used for: architecture-tier tasks, governance gate, school_extract fallback,
          any task routed to CC by model_router.py.

Config keys (from agent cfg dict):
  anthropic_api_key  — required
  llm.model          — default claude-sonnet-4-6
  llm.max_tokens     — default 4096
  llm.temperature    — default 0
  llm.request_timeout_s — default 60
  llm.max_retries    — default 3
"""
from __future__ import annotations

import json
import re
import time
import logging
from dataclasses import dataclass

from anthropic import Anthropic, APIError

from shared.llm.interface import DraftOutput

logger = logging.getLogger("signalos.llm.anthropic")

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


@dataclass
class AnthropicConfig:
    api_key: str
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0
    timeout: float = 60.0
    max_retries: int = 3

    @classmethod
    def from_cfg(cls, cfg: dict) -> "AnthropicConfig":
        llm = cfg.get("llm", {})
        api_key = cfg.get("anthropic_api_key", "")
        if not api_key:
            raise ValueError("anthropic_api_key not set in config")
        return cls(
            api_key=api_key,
            model=llm.get("model", "claude-sonnet-4-6"),
            max_tokens=llm.get("max_tokens", 4096),
            temperature=llm.get("temperature", 0),
            timeout=llm.get("request_timeout_s", 60.0),
            max_retries=llm.get("max_retries", 3),
        )


class AnthropicClient:
    def __init__(self, cfg: AnthropicConfig):
        self._cfg = cfg
        self._client = Anthropic(api_key=cfg.api_key, timeout=cfg.timeout)

    def complete(self, system: str, user: str) -> DraftOutput:
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.messages.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    temperature=self._cfg.temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
                text = "".join(parts).strip()
                usage = resp.usage
                return DraftOutput(
                    text=text, source="claude", model=self._cfg.model,
                    metadata={
                        "input_tokens":  int(getattr(usage, "input_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                        "attempt":       attempt,
                    },
                )
            except APIError as e:
                last_err = e
                logger.warning("Anthropic call failed attempt=%d/%d: %s", attempt, self._cfg.max_retries, e)
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"Anthropic failed after {self._cfg.max_retries} attempts: {last_err}")

    def complete_json(self, system: str, user: str) -> dict:
        draft = self.complete(system, user)
        return _extract_json(draft.text)

    def complete_with_tool(
        self,
        system: str,
        user: str,
        *,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        tool_def = {"name": tool_name, "description": tool_description, "input_schema": input_schema}
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.messages.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    temperature=self._cfg.temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    tools=[tool_def],
                    tool_choice={"type": "tool", "name": tool_name},
                )
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                        return dict(block.input)
                raise ValueError(f"tool_use({tool_name}) not found in response")
            except APIError as e:
                last_err = e
                logger.warning("Anthropic tool call failed attempt=%d/%d: %s", attempt, self._cfg.max_retries, e)
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"Anthropic tool call failed after {self._cfg.max_retries} attempts: {last_err}")


def _extract_json(text: str) -> dict:
    if not text:
        raise ValueError("LLM returned empty response")
    m = _FENCE_RE.search(text)
    candidate = m.group(1) if m else text.strip()
    first = min((candidate.find("{"), candidate.find("[")), key=lambda v: (v < 0, v))
    if first >= 0:
        candidate = candidate[first:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"Cannot parse JSON: {e}; raw[:200]={text[:200]!r}") from e
