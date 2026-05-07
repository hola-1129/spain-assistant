"""Anthropic Claude 调用封装。

- 统一处理 model/temperature/timeout/重试
- 提供 complete() 返回纯文本，complete_json() 强制返回 JSON dict
- 失败重试不掩盖最终异常，由调用方决定是否降级
"""

import json
import re
import time

from anthropic import Anthropic, APIError

from utils.logger import setup_logger

logger = setup_logger("llm_client")


class LLMClient:
    def __init__(self, cfg: dict):
        llm_cfg = cfg.get("llm", {})
        api_key = cfg.get("anthropic_api_key", "")
        if not api_key:
            raise ValueError("anthropic_api_key 未设置")

        self.model       = llm_cfg.get("model", "claude-sonnet-4-6")
        self.max_tokens  = llm_cfg.get("max_tokens", 4096)
        self.temperature = llm_cfg.get("temperature", 0)
        self.timeout     = llm_cfg.get("request_timeout_s", 60)
        self.max_retries = llm_cfg.get("max_retries", 3)

        self.client = Anthropic(api_key=api_key, timeout=self.timeout)

    def complete(self, system: str, user: str) -> str:
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
                return "".join(parts).strip()
            except APIError as e:
                last_err = e
                logger.warning(f"Anthropic 调用失败 attempt={attempt}/{self.max_retries}: {e}")
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"LLM 调用失败超过 {self.max_retries} 次: {last_err}")

    def complete_json(self, system: str, user: str) -> dict:
        """要求模型只返回 JSON。如果模型在外面包了```json``` 代码块也能解析。"""
        raw = self.complete(system, user)
        return _extract_json(raw)

    def complete_with_tool(self, system: str, user: str, *,
                           tool_name: str, tool_description: str,
                           input_schema: dict) -> dict:
        """走 tool_use 强制结构化输出；规避 LLM 裸吐 JSON 时未转义引号等问题。"""
        tool_def = {
            "name":         tool_name,
            "description":  tool_description,
            "input_schema": input_schema,
        }
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    tools=[tool_def],
                    tool_choice={"type": "tool", "name": tool_name},
                )
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                        return dict(block.input)
                raise ValueError(f"未在响应中找到 tool_use({tool_name})")
            except APIError as e:
                last_err = e
                logger.warning(f"Anthropic tool 调用失败 attempt={attempt}/{self.max_retries}: {e}")
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"LLM tool 调用失败超过 {self.max_retries} 次: {last_err}")


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    if not text:
        raise ValueError("LLM 返回为空")
    # 优先匹配代码块
    m = _FENCE_RE.search(text)
    candidate = m.group(1) if m else text
    # 再剥首尾非 JSON 部分
    candidate = candidate.strip()
    first = min((candidate.find("{"), candidate.find("[")), key=lambda v: (v < 0, v))
    if first >= 0:
        candidate = candidate[first:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析 JSON: {e}; 原文前 200 字: {text[:200]!r}") from e
