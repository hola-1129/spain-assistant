"""
OpenAI/Codex provider client for Northstar SignalOS.

Tier: CODEX (ModelTier.CODEX)
Used for: engineering execution tasks assigned by CC (feature_impl, bug_fix,
          test_creation, formatter_impl, boilerplate).

Codex outputs are DraftOutput(source="codex"). They pass through OutputGate
before any delivery. Codex clients must never make architecture decisions.

Uses the OpenAI Responses API (client.responses.create).
Dependency: openai>=2.0  (pip install "openai>=2.0")

Config keys:
  openai_api_key        — required
  llm.codex_model       — default codex-mini-latest
  llm.max_output_tokens — default 4096
  llm.request_timeout_s — default 120
  llm.max_retries       — default 3
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from shared.llm.interface import DraftOutput

logger = logging.getLogger("signalos.llm.codex")


@dataclass
class CodexConfig:
    api_key: str
    model: str = "codex-mini-latest"
    max_output_tokens: int = 4096
    timeout: float = 120.0
    max_retries: int = 3

    @classmethod
    def from_cfg(cls, cfg: dict) -> "CodexConfig":
        llm = cfg.get("llm", {})
        api_key = cfg.get("openai_api_key", "")
        if not api_key:
            raise ValueError("openai_api_key not set in config")
        return cls(
            api_key=api_key,
            model=llm.get("codex_model", "codex-mini-latest"),
            max_output_tokens=llm.get("max_output_tokens", 4096),
            timeout=llm.get("request_timeout_s", 120.0),
            max_retries=llm.get("max_retries", 3),
        )


class CodexClient:
    def __init__(self, cfg: CodexConfig):
        self._cfg = cfg
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("openai>=2.0 required for CodexClient: pip install 'openai>=2.0'") from e
        self._client = OpenAI(api_key=cfg.api_key, timeout=cfg.timeout)

    def complete(self, system: str, user: str) -> DraftOutput:
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.responses.create(
                    model=self._cfg.model,
                    instructions=system,
                    input=user,
                    max_output_tokens=self._cfg.max_output_tokens,
                )
                text = (resp.output_text or "").strip()
                return DraftOutput(text=text, source="codex", model=self._cfg.model)
            except Exception as e:
                last_err = e
                logger.warning("Codex call failed attempt=%d/%d: %s", attempt, self._cfg.max_retries, e)
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"Codex failed after {self._cfg.max_retries} attempts: {last_err}")

    def complete_json(self, system: str, user: str) -> dict:
        system_json = system + "\n\nRespond with valid JSON only."
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
            raise ValueError(f"Codex JSON parse failed: {e}; raw[:200]={draft.text[:200]!r}") from e
