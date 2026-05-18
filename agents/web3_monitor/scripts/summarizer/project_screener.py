"""
Project screener — Qwen risk pre-screening for new DEX liquidity pools.

WIRING STATUS: Not wired in Phase 3.
New pools are currently persisted but not notified. Pre-screening adds value
when pool-based Telegram alerts are introduced in a future phase.

To wire in the future:
  1. Set llm_enrichment.project_screen: true in config.yaml
  2. In agent_orchestrator._score_cross_signals or scan_new_pools handler,
     call screener.screen(pool_data) and add result to pool record.
  3. CC review required before wiring into any delivery path.

Security constraints:
  - Only token symbol, chain, and % metrics sent to Qwen
  - No raw wallet addresses, no contract addresses (potential PII/deanonymization)
  - All outputs pass OutputGate
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

logger = logging.getLogger("web3_monitor.summarizer.screener")

_SYSTEM = (
    "你是 DeFi 流动性池风险预筛助手。根据以下新上线流动性池链上指标，"
    "给出一句风险特征摘要（≤60字）。只描述可观察到的数据特征，不含任何投资建议。"
)


class ProjectScreener:
    """Pre-screens new DEX pools with Qwen risk summaries. NOT wired in Phase 3."""

    def __init__(self, qwen_client):
        self._qwen = qwen_client

    @classmethod
    def from_cfg(cls, cfg: dict) -> "ProjectScreener":
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

    def screen(self, pool: dict) -> Optional[str]:
        """
        Generate a risk summary for a new pool. Returns None on any error.
        Output is advisory only — does NOT affect storage or delivery.
        """
        try:
            user = self._build_prompt(pool)
            if not user:
                return None
            draft = DraftOutput(
                text=self._qwen.complete(system=_SYSTEM, user=user).text,
                source="qwen",
                model="qwen",
            )
            result = validate_safe(draft, TaskType.CLASSIFY_LOW_RISK)
            if not result.passed:
                logger.warning("OutputGate rejected pool screen: %s", result.rejection_reason)
                return None
            return result.output.text.strip() or None  # type: ignore[union-attr]
        except Exception as e:
            logger.debug("project screen failed for %s: %s", pool.get("asset"), e)
            return None

    def _build_prompt(self, pool: dict) -> str:
        lines = [
            f"代币: {pool.get('asset', '?')} | 网络: {pool.get('chain', '?')}",
        ]
        if "liquidity_usd" in pool:
            liq = pool["liquidity_usd"]
            lines.append(f"初始流动性: ${liq:,.0f}" if liq < 1_000_000 else f"初始流动性: >${liq / 1_000_000:.1f}M")
        if "price_change_1h_pct" in pool:
            lines.append(f"1h价格变化: {pool['price_change_1h_pct']:+.1f}%")
        if "volume_change_1h_pct" in pool:
            lines.append(f"1h成交量变化: {pool['volume_change_1h_pct']:+.0f}%")
        risk = pool.get("risk") or {}
        if risk.get("reasons"):
            lines.append(f"风险标记: {', '.join(risk['reasons'][:3])}")
        lines.append("请给出一句链上风险特征摘要。")
        return "\n".join(lines)
