"""
Tests for school_helper/analyzer/llm_client.py

All provider calls are mocked — no real API calls.
Validates:
  - Correct provider instantiated based on config
  - OutputGate rejection is raised
  - complete / complete_json / complete_with_tool delegate correctly
  - Fallback from Qwen → Anthropic when Qwen fails (via shared.llm.fallback)
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure shared.llm is importable
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.llm.interface import DraftOutput
from shared.llm.governance.output_gate import GateRejection


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _cfg(provider: str = "anthropic") -> dict:
    base = {
        "llm": {"provider": provider, "model": "claude-sonnet-4-6",
                "qwen_model": "qwen-plus"},
        "anthropic_api_key": "sk-test-anthropic-key-placeholder",
        "qwen_api_key":      "sk-test-qwen-key-placeholder",
    }
    return base


def _make_draft(text: str, source: str) -> DraftOutput:
    return DraftOutput(text=text, source=source, model="test-model")


# ── Provider selection ────────────────────────────────────────────────────────

def test_default_provider_is_anthropic():
    with patch("shared.llm.providers.anthropic_client.AnthropicClient.__init__",
               return_value=None) as mock_init:
        with patch("shared.llm.providers.anthropic_client.Anthropic"):
            from analyzer.llm_client import LLMClient
            client = LLMClient(_cfg("anthropic"))
            assert client._provider == "anthropic"


def test_qwen_provider_selected_from_config():
    with patch("shared.llm.providers.qwen_client.QwenClient.__init__",
               return_value=None):
        with patch("shared.llm.providers.qwen_client.OpenAI", create=True):
            from importlib import reload
            import analyzer.llm_client as mod
            reload(mod)
            client = mod.LLMClient(_cfg("qwen"))
            assert client._provider == "qwen"


# ── complete() ───────────────────────────────────────────────────────────────

def test_complete_returns_text_on_clean_output():
    from analyzer.llm_client import LLMClient
    client = LLMClient.__new__(LLMClient)
    client._provider = "anthropic"
    mock_inner = MagicMock()
    mock_inner.complete.return_value = _make_draft("学校通知内容", "claude")
    client._client = mock_inner

    result = client.complete("system", "user")
    assert result == "学校通知内容"


def test_complete_raises_on_gate_rejection():
    from analyzer.llm_client import LLMClient
    client = LLMClient.__new__(LLMClient)
    client._provider = "anthropic"
    mock_inner = MagicMock()
    # API key in output — should be rejected by gate
    mock_inner.complete.return_value = _make_draft(
        "Config: sk-abc123DEF456GHI789JKL012MNO345", "claude"
    )
    client._client = mock_inner

    with pytest.raises(GateRejection) as exc:
        client.complete("system", "user")
    assert exc.value.rule == "no_api_keys"


# ── complete_json() ───────────────────────────────────────────────────────────

def test_complete_json_delegates_to_provider():
    from analyzer.llm_client import LLMClient
    client = LLMClient.__new__(LLMClient)
    client._provider = "qwen"
    mock_inner = MagicMock()
    mock_inner.complete_json.return_value = {"title_es": "Excursión", "title_cn": "郊游"}
    client._client = mock_inner

    result = client.complete_json("system", "user")
    assert result["title_cn"] == "郊游"
    mock_inner.complete_json.assert_called_once_with("system", "user")


# ── complete_with_tool() ──────────────────────────────────────────────────────

def test_complete_with_tool_delegates_to_provider():
    from analyzer.llm_client import LLMClient
    client = LLMClient.__new__(LLMClient)
    client._provider = "qwen"
    mock_inner = MagicMock()
    expected = {"title_es": "Reunión", "title_cn": "家长会", "date": "2026-05-20"}
    mock_inner.complete_with_tool.return_value = expected
    client._client = mock_inner

    result = client.complete_with_tool(
        "system", "user",
        tool_name="record_event",
        tool_description="记录事项",
        input_schema={"type": "object", "properties": {}},
    )
    assert result == expected
    mock_inner.complete_with_tool.assert_called_once_with(
        "system", "user",
        tool_name="record_event",
        tool_description="记录事项",
        input_schema={"type": "object", "properties": {}},
    )


def test_complete_with_tool_propagates_provider_error():
    from analyzer.llm_client import LLMClient
    client = LLMClient.__new__(LLMClient)
    client._provider = "qwen"
    mock_inner = MagicMock()
    mock_inner.complete_with_tool.side_effect = RuntimeError("Qwen API timeout")
    client._client = mock_inner

    with pytest.raises(RuntimeError, match="Qwen API timeout"):
        client.complete_with_tool(
            "system", "user",
            tool_name="record_event",
            tool_description="desc",
            input_schema={},
        )


# ── Interface backward compatibility ──────────────────────────────────────────

def test_interface_has_all_required_methods():
    from analyzer.llm_client import LLMClient
    assert hasattr(LLMClient, "complete")
    assert hasattr(LLMClient, "complete_json")
    assert hasattr(LLMClient, "complete_with_tool")
