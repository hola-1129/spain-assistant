"""
Tests for OpenRouter provider client and gateway integration.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.llm.providers.openrouter_client import (
    OpenRouterClient,
    OpenRouterConfig,
    _source_from_model,
)
from shared.llm.interface import DraftOutput


# ── _source_from_model ────────────────────────────────────────────────────────

def test_source_from_model_anthropic():
    assert _source_from_model("anthropic/claude-sonnet-4-6") == "claude"

def test_source_from_model_claude_bare():
    assert _source_from_model("claude-3-opus") == "claude"

def test_source_from_model_qwen():
    assert _source_from_model("qwen/qwen-plus") == "qwen"

def test_source_from_model_openai():
    assert _source_from_model("openai/gpt-4o") == "codex"

def test_source_from_model_gpt_bare():
    assert _source_from_model("gpt-4o") == "codex"

def test_source_from_model_unknown_defaults_to_claude():
    assert _source_from_model("some-unknown-model") == "claude"


# ── OpenRouterClient ──────────────────────────────────────────────────────────

def _make_openai_mock(text: str = "test response"):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    return mock_client


def _make_client(model: str = "qwen/qwen-plus", mock_openai=None) -> OpenRouterClient:
    cfg = OpenRouterConfig(api_key="sk-or-test", model=model)
    client = object.__new__(OpenRouterClient)
    client._cfg = cfg
    from shared.llm.providers.openrouter_client import _source_from_model
    client._source = _source_from_model(model)
    client._client = mock_openai or _make_openai_mock()
    return client


def test_complete_returns_draft_output():
    client = _make_client("qwen/qwen-plus", _make_openai_mock("good output"))
    result = client.complete("system", "user")
    assert isinstance(result, DraftOutput)
    assert result.text == "good output"
    assert result.source == "qwen"
    assert result.model == "qwen/qwen-plus"


def test_complete_source_tag_claude_for_anthropic_model():
    client = _make_client("anthropic/claude-sonnet-4-6", _make_openai_mock("ok"))
    result = client.complete("s", "u")
    assert result.source == "claude"


def test_complete_raises_after_retries():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("timeout")
    cfg = OpenRouterConfig(api_key="sk-or-test", model="qwen/qwen-plus", max_retries=2)
    client = object.__new__(OpenRouterClient)
    client._cfg = cfg
    client._source = "qwen"
    client._client = mock_client
    with patch("time.sleep"):
        with pytest.raises(RuntimeError, match="OpenRouter failed after 2 attempts"):
            client.complete("s", "u")
    assert mock_client.chat.completions.create.call_count == 2


def test_complete_json_parses_valid_json():
    client = _make_client("openai/gpt-4o", _make_openai_mock('{"key": "value"}'))
    result = client.complete_json("system", "user")
    assert result == {"key": "value"}


def test_complete_json_raises_on_invalid_json():
    client = _make_client("openai/gpt-4o", _make_openai_mock("not json at all"))
    with pytest.raises(ValueError, match="JSON parse failed"):
        client.complete_json("system", "user")


# ── Gateway integration ───────────────────────────────────────────────────────
# OpenAI is lazy-imported inside OpenRouterClient.__init__, so we patch at the
# sys.modules level to avoid AttributeError on the module's namespace.

def test_gateway_uses_openrouter_for_qwen_only():
    # V1 governance: OpenRouter fills ONLY the Qwen tier.
    # CC and Codex must NOT be wired through OpenRouter.
    cfg = {"openrouter_api_key": "sk-or-test"}
    fake_openai = MagicMock()
    fake_openai.OpenAI.return_value = _make_openai_mock()
    with patch.dict(sys.modules, {"openai": fake_openai}):
        from shared.llm.gateway import LLMGateway
        from shared.llm.model_router import ModelTier
        gw = LLMGateway.from_cfg(cfg)
        assert gw._providers.get(ModelTier.QWEN) is not None, "Qwen tier should be wired"
        assert gw._providers.get(ModelTier.CC) is None, "CC must NOT use OpenRouter (V1)"
        assert gw._providers.get(ModelTier.CODEX) is None, "Codex must NOT use OpenRouter (V1)"


def test_direct_provider_takes_priority_over_openrouter():
    """If anthropic_api_key is set, OpenRouter must NOT override the CC tier."""
    cfg = {
        "anthropic_api_key": "sk-ant-test",
        "openrouter_api_key": "sk-or-test",
    }
    fake_openai = MagicMock()
    fake_openai.OpenAI.return_value = _make_openai_mock()
    mock_anthropic_cls = MagicMock()

    with patch("shared.llm.providers.anthropic_client.Anthropic", mock_anthropic_cls), \
         patch.dict(sys.modules, {"openai": fake_openai}):
        from shared.llm.gateway import LLMGateway
        from shared.llm.model_router import ModelTier
        from shared.llm.providers.anthropic_client import AnthropicClient
        gw = LLMGateway.from_cfg(cfg)
        cc_provider = gw._providers.get(ModelTier.CC)
        assert isinstance(cc_provider, AnthropicClient), (
            "CC tier should be AnthropicClient, not OpenRouterClient"
        )
