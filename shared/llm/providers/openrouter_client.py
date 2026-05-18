"""
OpenRouter provider client for Northstar SignalOS.

OpenRouter is a unified OpenAI-compatible gateway that routes to Claude,
Qwen, GPT-4o, and other models via a single API key and SDK.

Why this exists:
  - One `openai` SDK + one OPENROUTER_API_KEY covers all three tiers
  - Model switching is a config string change, no code change required
  - OutputGate and governance still apply to every response

Tier assignment:
  - CC tier    → anthropic/claude-sonnet-4-6  (or openrouter_cc_model)
  - Qwen tier  → qwen/qwen-plus               (or openrouter_qwen_model)
  - Codex tier → openai/gpt-4o                (or openrouter_codex_model)

Direct provider keys (anthropic_api_key, qwen_api_key, openai_api_key) take
priority over OpenRouter — OpenRouter only fills tiers that have no direct key.

Config keys:
  openrouter_api_key          — required (or env OPENROUTER_API_KEY)
  llm.openrouter_cc_model     — default anthropic/claude-sonnet-4-6
  llm.openrouter_qwen_model   — default qwen/qwen-plus
  llm.openrouter_codex_model  — default openai/gpt-4o
  llm.max_tokens              — default 2048
  llm.temperature             — default 0.3
  llm.request_timeout_s       — default 30
  llm.max_retries             — default 3

Dependency: openai>=1.0  (pip install openai)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

from shared.llm.interface import DraftOutput

logger = logging.getLogger("signalos.llm.openrouter")

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_SourceTag = Literal["qwen", "codex", "claude", "rule"]


def _source_from_model(model: str) -> _SourceTag:
    """Map OpenRouter model string to DraftOutput source tag."""
    m = model.lower()
    if m.startswith("anthropic/") or "claude" in m:
        return "claude"
    if m.startswith("qwen/") or "qwen" in m:
        return "qwen"
    if m.startswith("openai/") or m.startswith("gpt") or "codex" in m:
        return "codex"
    return "claude"  # safe default — CC governance rules applied


@dataclass
class OpenRouterConfig:
    api_key: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = 30.0
    max_retries: int = 3
    app_name: str = "Northstar-SignalOS"
    site_url: str = ""

    @classmethod
    def from_cfg(cls, cfg: dict, model: str) -> "OpenRouterConfig":
        llm = cfg.get("llm", {})
        api_key = cfg.get("openrouter_api_key", "")
        if not api_key:
            raise ValueError("openrouter_api_key not set in config")
        return cls(
            api_key=api_key,
            model=model,
            max_tokens=llm.get("max_tokens", 2048),
            temperature=llm.get("temperature", 0.3),
            timeout=llm.get("request_timeout_s", 30.0),
            max_retries=llm.get("max_retries", 3),
        )


class OpenRouterClient:
    def __init__(self, cfg: OpenRouterConfig):
        self._cfg = cfg
        self._source: _SourceTag = _source_from_model(cfg.model)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "openai package required for OpenRouterClient: pip install openai"
            ) from e
        extra_headers: dict[str, str] = {"X-Title": cfg.app_name}
        if cfg.site_url:
            extra_headers["HTTP-Referer"] = cfg.site_url
        self._client = OpenAI(
            api_key=cfg.api_key,
            base_url=_OPENROUTER_BASE_URL,
            timeout=cfg.timeout,
            default_headers=extra_headers,
        )

    def complete(self, system: str, user: str) -> DraftOutput:
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    temperature=self._cfg.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                text = (resp.choices[0].message.content or "").strip()
                return DraftOutput(text=text, source=self._source, model=self._cfg.model)
            except Exception as e:
                last_err = e
                logger.warning(
                    "OpenRouter call failed attempt=%d/%d model=%s: %s",
                    attempt, self._cfg.max_retries, self._cfg.model, e,
                )
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(
            f"OpenRouter failed after {self._cfg.max_retries} attempts "
            f"(model={self._cfg.model}): {last_err}"
        )

    def complete_json(self, system: str, user: str) -> dict:
        system_json = system + "\n\nRespond with valid JSON only. No markdown fences."
        draft = self.complete(system_json, user)
        text = draft.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"OpenRouter JSON parse failed: {e}; raw[:200]={draft.text[:200]!r}"
            ) from e

    def complete_with_tool(
        self,
        system: str,
        user: str,
        *,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        """Structured output via OpenAI-compatible function calling."""
        tool_def = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": input_schema,
            },
        }
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    temperature=self._cfg.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    tools=[tool_def],
                    tool_choice={"type": "function", "function": {"name": tool_name}},
                )
                for choice in resp.choices:
                    if choice.message.tool_calls:
                        for tc in choice.message.tool_calls:
                            if tc.function.name == tool_name:
                                return json.loads(tc.function.arguments)
                raise ValueError(f"Function call '{tool_name}' not found in response")
            except Exception as e:
                last_err = e
                logger.warning(
                    "OpenRouter tool call failed attempt=%d/%d: %s",
                    attempt, self._cfg.max_retries, e,
                )
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(
            f"OpenRouter tool call failed after {self._cfg.max_retries} attempts: {last_err}"
        )
