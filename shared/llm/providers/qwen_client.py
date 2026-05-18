"""
Qwen/DashScope provider client for Northstar SignalOS.

Tier: QWEN (ModelTier.QWEN)
Used for: summarization, translation, telegram drafts, school extraction,
          signal explanations, report drafts — ALL outputs are DraftOutput.

Security constraints (enforced here and by OutputGate):
  - Qwen never receives secrets, credentials, or wallet data
  - Qwen never receives school child names or PII beyond classification text
  - All outputs tagged source="qwen", validated=False
  - Max output 2048 tokens — anomalies logged

Provider: Alibaba Cloud DashScope (OpenAI-compatible endpoint)
Dependency: openai>=1.0  (pip install openai)

Config keys:
  qwen_api_key       — required (or DASHSCOPE_API_KEY env var)
  llm.qwen_model     — default qwen-plus
  llm.qwen_max_tokens — default 2048
  llm.temperature    — default 0.3
  llm.request_timeout_s — default 30
  llm.max_retries    — default 3
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from shared.llm.interface import DraftOutput

logger = logging.getLogger("signalos.llm.qwen")

_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class QwenConfig:
    api_key: str
    model: str = "qwen-plus"
    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_cfg(cls, cfg: dict) -> "QwenConfig":
        llm = cfg.get("llm", {})
        api_key = cfg.get("qwen_api_key", "")
        if not api_key:
            raise ValueError("qwen_api_key not set in config")
        return cls(
            api_key=api_key,
            model=llm.get("qwen_model", "qwen-plus"),
            max_tokens=llm.get("qwen_max_tokens", 2048),
            temperature=llm.get("temperature", 0.3),
            timeout=llm.get("request_timeout_s", 30.0),
            max_retries=llm.get("max_retries", 3),
        )


class QwenClient:
    def __init__(self, cfg: QwenConfig):
        self._cfg = cfg
        # Import lazily so agents without openai installed don't fail at import time
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("openai package required for QwenClient: pip install openai") from e
        self._client = OpenAI(
            api_key=cfg.api_key,
            base_url=_DASHSCOPE_BASE_URL,
            timeout=cfg.timeout,
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
                        {"role": "user",   "content": user},
                    ],
                )
                text = (resp.choices[0].message.content or "").strip()
                if len(text) > self._cfg.max_tokens * 4:
                    logger.warning("Qwen output unusually long (%d chars) — truncating", len(text))
                usage = getattr(resp, "usage", None)
                return DraftOutput(
                    text=text, source="qwen", model=self._cfg.model,
                    metadata={
                        "input_tokens":  int(getattr(usage, "prompt_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                        "attempt":       attempt,
                    },
                )
            except Exception as e:
                last_err = e
                logger.warning("Qwen call failed attempt=%d/%d: %s", attempt, self._cfg.max_retries, e)
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Qwen failed after {self._cfg.max_retries} attempts: {last_err}")

    def complete_json(self, system: str, user: str) -> dict:
        system_json = system + "\n\nRespond with valid JSON only. No markdown fences."
        draft = self.complete(system_json, user)
        text = draft.text.strip()
        # Strip fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Qwen JSON parse failed: {e}; raw[:200]={draft.text[:200]!r}") from e

    def complete_with_tool(
        self,
        system: str,
        user: str,
        *,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        """Structured output via OpenAI-compatible function calling (DashScope supported)."""
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
                        {"role": "user",   "content": user},
                    ],
                    tools=[tool_def],
                    tool_choice={"type": "function", "function": {"name": tool_name}},
                )
                for choice in resp.choices:
                    if choice.message.tool_calls:
                        for tc in choice.message.tool_calls:
                            if tc.function.name == tool_name:
                                return json.loads(tc.function.arguments)
                raise ValueError(f"Function call '{tool_name}' not found in Qwen response")
            except Exception as e:
                last_err = e
                logger.warning("Qwen tool call failed attempt=%d/%d: %s", attempt, self._cfg.max_retries, e)
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Qwen tool call failed after {self._cfg.max_retries} attempts: {last_err}")
