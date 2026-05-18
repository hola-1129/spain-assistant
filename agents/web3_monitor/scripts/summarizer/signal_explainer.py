"""
Signal explainer — Qwen plain-language explanations for Web3 cross-signals.

Adds a brief Chinese-language explanation to qualifying cross-signals
(DEX + Polymarket pairs that score above threshold).

Security constraints:
  - Only percentage changes, scores, and token symbols are sent to Qwen
  - No wallet addresses, no dollar amounts > $1M, no API keys
  - All outputs pass OutputGate before use
  - NEVER influences signal score or delivery decision — explanation only

Wired into: _score_cross_signals in agent_orchestrator.py
NOT wired into: market movers, raw DEX scans, pool storage

Python 3.14 compatible (shared.llm uses from __future__ import annotations).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.llm.governance.output_gate import validate_safe
from shared.llm.interface import DraftOutput
from shared.llm.model_router import TaskType

logger = logging.getLogger("web3_monitor.summarizer.explainer")

_SYSTEM = (
    "你是 DeFi/Web3 市场信号分析助手。用简洁中文（≤60字）解释以下量化信号所揭示的市场状况。"
    "只描述客观链上数据特征，不含任何交易建议或买卖推荐。直接输出文本，不加任何前缀。"
)


class SignalExplainer:
    """Generates Chinese plain-language explanations for Web3 cross-signals."""

    def __init__(self, qwen_client):
        self._qwen = qwen_client

    @classmethod
    def from_cfg(cls, cfg: dict) -> "SignalExplainer":
        from shared.llm.providers.qwen_client import QwenClient, QwenConfig

        enrich_cfg = cfg.get("llm_enrichment", {})
        qwen_cfg = {
            "qwen_api_key": cfg.get("qwen_api_key", ""),
            "llm": {
                "qwen_model":       enrich_cfg.get("qwen_model", "qwen-plus"),
                "qwen_max_tokens":  enrich_cfg.get("max_tokens", 128),
                "temperature":      0.2,
                "request_timeout_s": 15.0,
                "max_retries":       2,
            },
        }
        return cls(QwenClient(QwenConfig.from_cfg(qwen_cfg)))

    def explain(self, signal: dict) -> Optional[str]:
        """
        Explain a cross-signal in plain Chinese. Returns None on any error.
        NEVER called for signals that haven't passed the score threshold.
        """
        try:
            user = self._build_prompt(signal)
            if not user:
                return None
            asset = signal.get("asset", "?")
            score = signal.get("score", 0)
            logger.info("[QWEN] calling: task=SIGNAL_EXPLAIN asset=%s score=%s", asset, score)
            draft = DraftOutput(
                text=self._qwen.complete(system=_SYSTEM, user=user).text,
                source="qwen",
                model="qwen",
            )
            result = validate_safe(draft, TaskType.SIGNAL_EXPLAIN)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected signal explanation: %s", result.rejection_reason)
                return None
            text = result.output.text.strip()  # type: ignore[union-attr]
            if text:
                logger.info("[QWEN] success: asset=%s gate=passed len=%d", asset, len(text))
            return text if text else None
        except Exception as e:
            logger.warning("[QWEN] failed: asset=%s error=%s", signal.get("asset"), e)
            return None

    def explain_mover(self, mover: dict) -> Optional[str]:
        """Explain a market-mover signal in plain Chinese. Returns None on any error."""
        try:
            user = self._build_mover_prompt(mover)
            if not user:
                return None
            asset = mover.get("asset", "?")
            score = mover.get("score", 0)
            logger.info("[QWEN] calling: task=MARKET_MOVER_EXPLAIN asset=%s score=%s", asset, score)
            draft = DraftOutput(
                text=self._qwen.complete(system=_SYSTEM, user=user).text,
                source="qwen",
                model="qwen",
            )
            result = validate_safe(draft, TaskType.SIGNAL_EXPLAIN)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected mover explanation: %s", result.rejection_reason)
                return None
            text = result.output.text.strip()  # type: ignore[union-attr]
            return text if text else None
        except Exception as e:
            logger.warning("[QWEN] mover explain failed: asset=%s error=%s", mover.get("asset"), e)
            return None

    def _build_mover_prompt(self, mover: dict) -> str:
        asset   = mover.get("asset", "?")
        score   = mover.get("score", 0)
        chg     = mover.get("price_change_24h_pct", 0)
        turnover = mover.get("turnover_ratio", 0)
        alpha   = mover.get("alpha_7d_vs_btc_pct", 0)
        interp  = mover.get("interpretation", "")

        lines = [
            f"资产: {asset} | 得分: {score}/100",
            f"24h价格变化: {float(chg):+.2f}%",
            f"换手率: {float(turnover):.1f}x 基准",
            f"7日相对BTC超额收益: {float(alpha):+.1f}%",
        ]
        if interp:
            lines.append(f"触发原因: {interp}")
        lines.append("请用一句话解释此市场异动的特征。")
        return "\n".join(lines)

    def _build_prompt(self, signal: dict) -> str:
        asset       = signal.get("asset", "?")
        chain       = signal.get("chain", "?")
        score       = signal.get("score", 0)
        sig_type    = signal.get("type", "cross")
        interp      = signal.get("interpretation", "")

        dex = signal.get("dex") or {}
        pm  = signal.get("polymarket") or {}

        lines = [
            f"资产: {asset} | 网络: {chain}",
            f"信号类型: {sig_type} | 得分: {score}/100",
        ]

        if dex:
            if "price_change_1h_pct" in dex:
                lines.append(f"DEX 1h价格变化: {dex['price_change_1h_pct']:+.1f}%")
            if "volume_change_1h_pct" in dex:
                lines.append(f"DEX 1h成交量变化: {dex['volume_change_1h_pct']:+.0f}%")

        if pm:
            if "probability_change_pct" in pm:
                lines.append(f"Polymarket概率变化: {pm['probability_change_pct']:+.0f}%")
            if "title" in pm:
                title = str(pm["title"])[:60]
                lines.append(f"预测市场事件: {title}")

        if interp:
            lines.append(f"触发原因: {interp}")

        lines.append("请用一句话解释此信号的市场含义。")
        return "\n".join(lines)
