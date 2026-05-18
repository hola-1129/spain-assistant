"""
Daily report drafter — Qwen + Claude enrichment for portfolio reports.

Qwen (NEWS_CURATION):  新闻精选，客观陈述，无投资建议
Claude (FINANCIAL_ADVICE): 持仓分析与行动提示，CC exclusive

All dollar values excluded from LLM prompts (privacy: % changes + symbols only).
OutputGate validates all drafts before returning.
Falls back gracefully on any error — Telegram delivery is never blocked.

Python 3.9 compatible.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Ensure shared.llm is importable
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.llm.governance.output_gate import validate_safe
from shared.llm.interface import DraftOutput
from shared.llm.model_router import TaskType

logger = logging.getLogger("summarizer.drafter")

_TELEGRAM_LIMIT = 4096


# ── System prompts ────────────────────────────────────────────────────────────

_DAILY_SYSTEM = (
    "你是市场数据助手。根据今日市场数据摘要，写一句中文市场氛围总结（≤80字）。"
    "只描述客观数据事实，不含任何投资建议或买卖推荐。直接输出文本，不加任何前缀。"
)

_PORTFOLIO_SYSTEM = (
    "你是投资组合助手。根据今日持仓变动数据，写一句中文组合概况（≤60字）。"
    "只描述客观数据事实，不含任何投资建议或买卖推荐。直接输出文本，不加任何前缀。"
)

_NEWS_SYSTEM = (
    "你是财经新闻编辑。从用户提供的个股新闻标题列表中，筛选出对股价或投资逻辑有实质影响的要闻。"
    "无论原始标题是英文还是中文，摘要必须用中文撰写，禁止保留英文标题原文。"
    "每条格式：`标的` — 要闻摘要（≤30字中文）。最多输出6条，按重要性降序排列。"
    "只输出新闻条目，不加任何前缀或总结。"
)

_ADVICE_CLOSE_SYSTEM = (
    "你是机构投资组合分析师，专注美股成长股。根据今日收盘数据对持仓进行客观分析，"
    "指出需要关注的风险点和机会点，给出简洁的行动提示（持有/观察/需复盘）。"
    "用中文输出，风格专业简洁，总长度≤600字。"
    "严禁使用「建议买入/卖出」等直接交易指令。"
)

_ADVICE_PREMARKET_SYSTEM = (
    "你是机构投资组合分析师。根据盘前持仓状态和今日市场焦点，给出开盘前的关注重点。"
    "包括：今日需重点跟踪的标的、潜在催化剂、需要设置止损或关注的风险。"
    "用中文输出，总长度≤400字。严禁使用「建议买入/卖出」等直接交易指令。"
)

_BREAKING_NEWS_SYSTEM = (
    "你是实时财经监控编辑。从以下新闻标题中，仅筛选出可能对持仓价格产生立即（今日内）重大影响的突发要闻。"
    "判断标准：盈利预警/大幅超预期、重大监管行动、并购、CEO变动、黑天鹅事件、重大政策转向。"
    "如没有符合标准的新闻，输出空白（不输出任何内容）。"
    "如有，每条格式：`标的` — 要闻摘要（≤25字中文）。最多3条，按紧急程度降序。"
    "无论原始标题是英文还是中文，摘要必须用中文。只输出新闻条目，不加前缀。"
)

_US_MARKET_OUTLOOK_SYSTEM = (
    "你是美股市场策略师。根据提供的今日开盘前市场数据，用中文写一份美股开盘动向观察（≤350字）。"
    "结构：① 宏观环境（大盘/VIX/美元/黄金信号）；② 今日需关注的个股或板块催化剂；③ 整体开盘倾向（谨慎/中性/积极）及一句行动提示。"
    "不含任何买卖建议。直接输出分析，不加标题前缀。"
)

_ASTOCK_OUTLOOK_SYSTEM = (
    "你是A股市场策略师。根据提供的前日收盘信号和今日参考指标，用中文写一份A股开盘前动向观察（≤280字）。"
    "结构：① 前日收盘主要信号（科技/消费/金融板块分化）；② 今日开盘前需关注的催化剂或风险（政策/外资/汇率）；③ 整体开盘倾向及关注重点。"
    "不含任何买卖建议。直接输出分析，不加标题前缀。"
)

_CHINA_ADVICE_SYSTEM = (
    "你是专注中国市场的机构投资组合分析师，覆盖A股、QDII基金、黄金、债券。"
    "根据今日持仓结构和市场表现，指出主要机会点和风险点，给出简洁的行动建议（持有/观察/需复盘）。"
    "重点关注：板块轮动信号、QDII美股暴露集中度、A股科技与消费分化、跨账户重叠风险、黄金配置逻辑。"
    "用中文输出，风格专业简洁，总长度≤500字。"
    "严禁使用「建议买入/卖出」等直接交易指令。"
)

_CHINA_NEWS_SYSTEM = (
    "你是中国市场财经新闻编辑。从用户提供的市场相关标题中，筛选对A股、QDII基金、中国宏观经济、黄金或亚太市场有实质影响的要闻。"
    "无论原始标题是英文还是中文，摘要必须用中文撰写，禁止保留英文原文标题。"
    "每条格式：`板块/标的` — 要闻摘要（≤30字中文）。最多输出6条，按重要性降序排列。"
    "只输出新闻条目，不加任何前缀或总结。"
)

_CRYPTO_ADVICE_SYSTEM = (
    "你是加密资产投资组合分析师，覆盖 BTC、ETH 和主流山寨币。"
    "根据今日持仓数据，分析宏观加密市场环境和个别代币表现，指出主要机会点和风险点。"
    "关注点：BTC 市场主导权变化、ETH/质押资产动向、山寨季信号、高亏损仓位处理、流动性风险。"
    "用中文输出，风格专业简洁，总长度≤400字。"
    "严禁使用「建议买入/卖出」等直接交易指令。"
)


class DailyReportDrafter:
    """Enriches portfolio reports with Qwen news curation and Claude analysis."""

    def __init__(self, qwen_client, claude_client=None,
                 qwen_model: str = "qwen-plus",
                 claude_model: str = "claude-sonnet-4-6"):
        self._qwen         = qwen_client
        self._claude       = claude_client
        self._qwen_tag     = f"_[{qwen_model}]_"
        self._claude_tag   = f"_[{claude_model}]_"

    @classmethod
    def from_cfg(cls, cfg: dict) -> "DailyReportDrafter":
        from shared.llm.providers.qwen_client import QwenClient, QwenConfig

        enrich_cfg = cfg.get("llm_enrichment", {})
        qwen_cfg_overlay = {
            "qwen_api_key": cfg.get("qwen_api_key", ""),
            "llm": {
                "qwen_model":      enrich_cfg.get("qwen_model", "qwen-plus"),
                "qwen_max_tokens": enrich_cfg.get("max_tokens", 512),
                "temperature":     0.3,
                "request_timeout_s": 20.0,
                "max_retries":     2,
            },
        }
        qwen_model  = enrich_cfg.get("qwen_model", "qwen-plus")
        qwen_client = QwenClient(QwenConfig.from_cfg(qwen_cfg_overlay))

        claude_model  = "claude-sonnet-4-6"
        claude_client = None
        if cfg.get("anthropic_api_key"):
            try:
                from shared.llm.providers.anthropic_client import AnthropicClient, AnthropicConfig
                claude_cfg = {
                    "anthropic_api_key": cfg["anthropic_api_key"],
                    "llm": {"model": claude_model, "max_tokens": 1024,
                            "temperature": 0, "request_timeout_s": 30.0, "max_retries": 2},
                }
                claude_client = AnthropicClient(AnthropicConfig.from_cfg(claude_cfg))
                logger.info("Claude client initialised for FINANCIAL_ADVICE")
            except Exception as e:
                logger.warning("Claude client init failed: %s", e)

        return cls(qwen_client, claude_client,
                   qwen_model=qwen_model, claude_model=claude_model)

    # ── Public API ─────────────────────────────────────────────────────────────

    def enrich_daily_summary(
        self,
        original_msg: str,
        stock_results: list,
        macro_snapshot: Optional[list] = None,
        date_str: str = "",
    ) -> str:
        """
        Generate a Qwen narrative snippet and prepend to the existing formatted message.
        Returns original_msg unchanged on any error.
        """
        try:
            snippet = self._draft_daily_narrative(stock_results, macro_snapshot, date_str)
            if not snippet:
                return original_msg
            enriched = f"{snippet}\n\n{original_msg}"
            if len(enriched) > _TELEGRAM_LIMIT:
                logger.debug("Enriched daily_summary exceeds limit, skipping enrichment")
                return original_msg
            return enriched
        except Exception as e:
            logger.warning("daily_summary enrichment failed, using original: %s", e)
            return original_msg

    def enrich_portfolio_report(
        self,
        original_msg: str,
        results: list,
        date_str: str = "",
    ) -> str:
        """
        Generate a Qwen narrative snippet and prepend to the existing portfolio report.
        Returns original_msg unchanged on any error.
        """
        try:
            snippet = self._draft_portfolio_narrative(results, date_str)
            if not snippet:
                return original_msg
            enriched = f"{snippet}\n\n{original_msg}"
            if len(enriched) > _TELEGRAM_LIMIT:
                return original_msg
            return enriched
        except Exception as e:
            logger.warning("portfolio_report enrichment failed, using original: %s", e)
            return original_msg

    def build_news_section(self, symbols: List[str]) -> str:
        """Fetch news via yfinance and curate with Qwen. Returns formatted section or ''."""
        try:
            import yfinance as yf
            raw: List[str] = []
            for sym in symbols:
                try:
                    news = yf.Ticker(sym).news or []
                    for n in news[:3]:
                        title = n.get("content", {}).get("title", "")
                        if title:
                            raw.append(f"{sym}|{title}")
                    time.sleep(0.15)
                except Exception:
                    pass
            if not raw:
                return ""

            user = "以下是各持仓标的的最新新闻标题，格式为「标的|标题」：\n" + "\n".join(raw[:40])
            logger.info("[QWEN] calling: task=NEWS_CURATION symbols=%d raw_items=%d", len(symbols), len(raw))
            draft = DraftOutput(
                text=self._qwen.complete(system=_NEWS_SYSTEM, user=user).text,
                source="qwen", model="qwen",
            )
            result = validate_safe(draft, TaskType.NEWS_CURATION)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected news: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[QWEN] success: fn=news_curation gate=passed len=%d", len(text))
            return f"📰 *今日要闻*  {self._qwen_tag}\n{text}"
        except Exception as e:
            logger.warning("build_news_section failed: %s", e)
            return ""

    def build_advice_close(self, results: list, date_str: str) -> str:
        """Generate Claude portfolio close analysis. Returns formatted section or ''."""
        if not self._claude:
            logger.info("[CC] Claude client not available, skipping advice")
            return ""
        try:
            lines = [f"日期: {date_str}（收盘）"]
            for r in results:
                day   = getattr(r, "day_change_pct", None)
                pnl   = getattr(r, "pnl_pct", None)
                nav   = getattr(r, "nav_pct", None)
                acct  = getattr(r, "account", "")
                flags = getattr(r, "risk_flags", [])
                if day is not None:
                    parts = [f"{r.label}({acct}): 今日{day:+.1f}%"]
                    if pnl is not None:
                        parts.append(f"总盈亏{pnl:+.1f}%")
                    if nav is not None:
                        parts.append(f"仓位{nav:.1%}")
                    if flags:
                        parts.append(f"[{'; '.join(flags)}]")
                    lines.append("  " + "  ".join(parts))

            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=close_advice date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_ADVICE_CLOSE_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected close advice: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=close_advice gate=passed len=%d", len(text))
            return f"🧠 *收盘分析*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_advice_close failed: %s", e)
            return ""

    def build_advice_premarket(self, results: list, date_str: str) -> str:
        """Generate Claude pre-market focus briefing. Returns formatted section or ''."""
        if not self._claude:
            return ""
        try:
            lines = [f"日期: {date_str}（盘前）"]
            for r in results:
                pnl   = getattr(r, "pnl_pct", None)
                nav   = getattr(r, "nav_pct", None)
                acct  = getattr(r, "account", "")
                flags = getattr(r, "risk_flags", [])
                parts = [f"{r.label}({acct})"]
                if pnl is not None:
                    parts.append(f"持仓盈亏{pnl:+.1f}%")
                if nav is not None:
                    parts.append(f"仓位{nav:.1%}")
                if flags:
                    parts.append(f"[{'; '.join(flags)}]")
                lines.append("  " + "  ".join(parts))

            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=premarket_advice date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_ADVICE_PREMARKET_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected premarket advice: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=premarket_advice gate=passed len=%d", len(text))
            return f"🎯 *今日开盘关注*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_advice_premarket failed: %s", e)
            return ""


    def curate_breaking_news(self, raw_headlines: List[str], market: str = "us") -> str:
        """Curate pre-fetched new headlines with Qwen. Returns push-ready string or ''."""
        try:
            label = "中国市场" if market == "china" else "美股"
            user = f"以下是最新{label}新闻标题（格式：标的|标题）：\n" + "\n".join(raw_headlines[:30])
            logger.info("[QWEN] calling: task=NEWS_CURATION fn=breaking_news market=%s items=%d", market, len(raw_headlines))
            draft = DraftOutput(
                text=self._qwen.complete(system=_BREAKING_NEWS_SYSTEM, user=user).text,
                source="qwen", model="qwen",
            )
            result = validate_safe(draft, TaskType.NEWS_CURATION)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected breaking_news: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            if not text:
                return ""
            emoji = "🏮" if market == "china" else "🚨"
            logger.info("[QWEN] success: fn=breaking_news gate=passed len=%d", len(text))
            return f"{emoji} *突发要闻*  {self._qwen_tag}\n{text}"
        except Exception as e:
            logger.warning("curate_breaking_news failed: %s", e)
            return ""

    def build_us_market_outlook(self, macro_data: list, portfolio_results: list, date_str: str) -> str:
        """Generate Claude US market opening outlook at 08:30 ET."""
        if not self._claude:
            return ""
        try:
            lines = [f"日期: {date_str}（美股开盘前 08:30 ET）", "宏观指标（昨日收盘）:"]
            for item in macro_data:
                pct = item.get("daily_change_pct")
                if pct is not None:
                    lines.append(f"  {item.get('name', item.get('symbol','?'))}: {pct:+.2f}%")
            if portfolio_results:
                sorted_r = sorted(portfolio_results, key=lambda r: getattr(r, "day_change_pct", 0), reverse=True)
                lines.append("持仓昨日涨幅 Top 3:")
                for r in sorted_r[:3]:
                    d = getattr(r, "day_change_pct", 0)
                    lines.append(f"  {r.label}: {d:+.1f}%  仓位{getattr(r,'nav_pct',0):.1%}")
                lines.append("持仓昨日跌幅 Top 3:")
                for r in sorted_r[-3:]:
                    d = getattr(r, "day_change_pct", 0)
                    lines.append(f"  {r.label}: {d:+.1f}%  仓位{getattr(r,'nav_pct',0):.1%}")

            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=us_market_outlook date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_US_MARKET_OUTLOOK_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected us_market_outlook: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=us_market_outlook gate=passed len=%d", len(text))
            return f"🌏 *今日美股开盘观察*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_us_market_outlook failed: %s", e)
            return ""

    def build_astock_outlook(self, china_proxy_data: list, nav_summary: dict, date_str: str) -> str:
        """Generate Claude A-share opening outlook at 09:00 CST."""
        if not self._claude:
            return ""
        try:
            lines = [f"日期: {date_str}（A股开盘前 09:00 CST）", "中国相关ETF昨日表现（美股上市）:"]
            for item in china_proxy_data:
                pct = item.get("daily_change_pct")
                sym = item.get("symbol", "")
                if pct is not None:
                    lines.append(f"  {sym}: {pct:+.2f}%")
            if nav_summary:
                lines.append("A股/QDII持仓昨日加权涨跌:")
                for mkt, pct in nav_summary.items():
                    lines.append(f"  {mkt}: {pct:+.2f}%")
            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=astock_outlook date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_ASTOCK_OUTLOOK_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected astock_outlook: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=astock_outlook gate=passed len=%d", len(text))
            return f"🏮 *今日A股开盘观察*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_astock_outlook failed: %s", e)
            return ""

    def build_china_news_section(self) -> str:
        """Fetch China-relevant market news via yfinance proxies and curate with Qwen."""
        try:
            import yfinance as yf
            # US-listed proxies for China A-stock, gold, Asia-Pacific markets
            proxies = ["KWEB", "MCHI", "FXI", "BABA", "PDD", "GLD", "AAXJ", "EWJ"]
            raw: List[str] = []
            for sym in proxies:
                try:
                    news = yf.Ticker(sym).news or []
                    for n in news[:3]:
                        title = n.get("content", {}).get("title", "")
                        if title:
                            raw.append(f"{sym}|{title}")
                    time.sleep(0.15)
                except Exception:
                    pass
            if not raw:
                return ""
            user = "以下是中国市场相关标的的最新新闻标题，格式为「标的|标题」：\n" + "\n".join(raw[:40])
            logger.info("[QWEN] calling: task=NEWS_CURATION fn=china_news raw_items=%d", len(raw))
            draft = DraftOutput(
                text=self._qwen.complete(system=_CHINA_NEWS_SYSTEM, user=user).text,
                source="qwen", model="qwen",
            )
            result = validate_safe(draft, TaskType.NEWS_CURATION)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected china_news: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[QWEN] success: fn=china_news gate=passed len=%d", len(text))
            return f"📰 *中国市场要闻*  {self._qwen_tag}\n{text}"
        except Exception as e:
            logger.warning("build_china_news_section failed: %s", e)
            return ""

    def build_china_advice(self, holdings: list, navs: dict, date_str: str) -> str:
        """Generate Claude professional analysis for China fund portfolio."""
        if not self._claude:
            return ""
        try:
            from collections import defaultdict
            # Aggregate by market type — no dollar amounts, only % and structure
            mkt_mv: dict = defaultdict(float)
            mkt_pnl_lines: list = []
            total_mv = 0.0
            for h in holdings:
                mv   = float(h.get("market_value_cny") or 0)
                cost = float(h.get("cost_basis_cny") or 0)
                mkt  = h.get("underlying_market", "OTHER")
                mkt_mv[mkt] += mv
                total_mv    += mv

            lines = [f"日期: {date_str}（A股/QDII收盘）", "持仓结构（按市值占比）:"]
            for mkt, mv in sorted(mkt_mv.items(), key=lambda x: -x[1]):
                pct = mv / total_mv * 100 if total_mv else 0
                # Aggregate today's change for this market type
                w_num = w_den = 0.0
                for h in holdings:
                    if h.get("underlying_market") != mkt:
                        continue
                    hmv     = float(h.get("market_value_cny") or 0)
                    nav_obj = navs.get(h.get("fund_code", ""))
                    if nav_obj and hmv:
                        w_num += hmv * nav_obj.daily_change_pct
                        w_den += hmv
                day_str = f"今日{w_num/w_den:+.2f}%" if w_den else ""
                lines.append(f"  {mkt}: {pct:.1f}%  {day_str}")

            # Loss positions (>5% loss)
            losers = []
            for h in holdings:
                mv   = float(h.get("market_value_cny") or 0)
                cost = float(h.get("cost_basis_cny") or 0)
                if cost > 0 and (mv - cost) / cost * 100 < -5:
                    pnl_pct = (mv - cost) / cost * 100
                    losers.append(f"{h.get('fund_name','?')[:8]}({pnl_pct:+.1f}%)")
            if losers:
                lines.append(f"亏损超5%持仓: {', '.join(losers[:5])}")

            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=china_advice date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_CHINA_ADVICE_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected china_advice: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=china_advice gate=passed len=%d", len(text))
            return f"🧠 *中国资产分析*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_china_advice failed: %s", e)
            return ""

    def build_crypto_news_section(self) -> str:
        """Fetch crypto news via yfinance and curate with Qwen. Returns formatted section or ''."""
        try:
            import yfinance as yf
            crypto_syms = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "WLD-USD"]
            raw: List[str] = []
            for sym in crypto_syms:
                try:
                    news = yf.Ticker(sym).news or []
                    for n in news[:3]:
                        title = n.get("content", {}).get("title", "")
                        if title:
                            raw.append(f"{sym.replace('-USD','')}|{title}")
                    time.sleep(0.15)
                except Exception:
                    pass
            if not raw:
                return ""
            user = "以下是加密货币市场最新新闻标题，格式为「标的|标题」：\n" + "\n".join(raw[:30])
            logger.info("[QWEN] calling: task=NEWS_CURATION fn=crypto_news raw_items=%d", len(raw))
            draft = DraftOutput(
                text=self._qwen.complete(system=_BREAKING_NEWS_SYSTEM, user=user).text,
                source="qwen", model="qwen",
            )
            result = validate_safe(draft, TaskType.NEWS_CURATION)
            if not result.passed:
                logger.warning("[QWEN] OutputGate rejected crypto_news: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            if not text:
                return ""
            logger.info("[QWEN] success: fn=crypto_news gate=passed len=%d", len(text))
            return f"📰 *加密要闻*  {self._qwen_tag}\n{text}"
        except Exception as e:
            logger.warning("build_crypto_news_section failed: %s", e)
            return ""

    def build_crypto_advice(self, positions_data: list, date_str: str) -> str:
        """Generate Claude crypto portfolio analysis. Returns formatted section or ''."""
        if not self._claude:
            logger.info("[CC] Claude client not available, skipping crypto_advice")
            return ""
        try:
            lines = [f"日期: {date_str}（加密持仓）", "持仓状况（按市值降序，不含金额）:"]
            for p in sorted(positions_data, key=lambda x: x.get("market_value", 0), reverse=True):
                sym  = p["symbol"]
                chg  = p.get("change_24h")
                pnl  = p.get("pnl_pct")
                parts = [sym]
                if chg is not None:
                    parts.append(f"今日{chg:+.2f}%")
                if pnl is not None:
                    parts.append(f"浮{pnl:+.1f}%")
                lines.append("  " + "  ".join(parts))

            user = "\n".join(lines)
            logger.info("[CC] calling: task=FINANCIAL_ADVICE fn=crypto_advice date=%s", date_str)
            draft = DraftOutput(
                text=self._claude.complete(system=_CRYPTO_ADVICE_SYSTEM, user=user).text,
                source="claude", model="claude-sonnet-4-6",
            )
            result = validate_safe(draft, TaskType.FINANCIAL_ADVICE)
            if not result.passed:
                logger.warning("[CC] OutputGate rejected crypto_advice: %s", result.rejection_reason)
                return ""
            text = result.output.text.strip()  # type: ignore[union-attr]
            logger.info("[CC] success: fn=crypto_advice gate=passed len=%d", len(text))
            return f"🧠 *加密资产分析*  {self._claude_tag}\n{text}"
        except Exception as e:
            logger.warning("build_crypto_advice failed: %s", e)
            return ""

    # ── Internal ───────────────────────────────────────────────────────────────

    def _draft_daily_narrative(
        self,
        stock_results: list,
        macro_snapshot: Optional[list],
        date_str: str,
    ) -> str:
        tops = sorted(stock_results, key=lambda x: x.get("daily_change_pct") or 0, reverse=True)[:3]
        bots = sorted(stock_results, key=lambda x: x.get("daily_change_pct") or 0)[:3]

        top_str  = "  ".join(f"{r['symbol']} {r['daily_change_pct']:+.1f}%" for r in tops)
        bot_str  = "  ".join(f"{r['symbol']} {r['daily_change_pct']:+.1f}%" for r in bots)

        macro_str = ""
        if macro_snapshot:
            notable = sorted(
                [r for r in macro_snapshot if r.get("daily_change_pct") is not None],
                key=lambda x: abs(x["daily_change_pct"]), reverse=True,
            )[:3]
            macro_str = "  ".join(f"{r['name']} {r['daily_change_pct']:+.2f}%" for r in notable)

        user = (
            f"日期: {date_str}\n"
            f"今日美股最强: {top_str}\n"
            f"今日美股最弱: {bot_str}\n"
        )
        if macro_str:
            user += f"宏观亮点: {macro_str}\n"

        logger.info("[QWEN] calling: task=REPORT_DRAFT fn=daily_narrative date=%s", date_str)
        draft = DraftOutput(
            text=self._qwen.complete(system=_DAILY_SYSTEM, user=user).text,
            source="qwen",
            model="qwen",
        )
        result = validate_safe(draft, TaskType.REPORT_DRAFT)
        if not result.passed:
            logger.warning("[QWEN] OutputGate rejected daily_summary snippet: %s", result.rejection_reason)
            return ""
        text = result.output.text.strip()  # type: ignore[union-attr]
        logger.info("[QWEN] success: fn=daily_narrative gate=passed len=%d", len(text))
        return text

    def _draft_portfolio_narrative(self, results: list, date_str: str) -> str:
        # Only pass % changes and labels — no dollar amounts to Qwen
        lines = []
        for r in results:
            label = getattr(r, "label", "?")
            day_pct = getattr(r, "day_change_pct", None)
            nav_pct = getattr(r, "nav_pct", None)
            if day_pct is not None:
                nav_str = f" ({nav_pct:.1%} NAV)" if nav_pct is not None else ""
                lines.append(f"{label}{nav_str}: {day_pct:+.1f}%")

        if not lines:
            return ""

        user = f"日期: {date_str}\n持仓当日变动:\n" + "\n".join(lines)

        logger.info("[QWEN] calling: task=REPORT_DRAFT fn=portfolio_narrative date=%s", date_str)
        draft = DraftOutput(
            text=self._qwen.complete(system=_PORTFOLIO_SYSTEM, user=user).text,
            source="qwen",
            model="qwen",
        )
        result = validate_safe(draft, TaskType.REPORT_DRAFT)
        if not result.passed:
            logger.warning("[QWEN] OutputGate rejected portfolio_report snippet: %s", result.rejection_reason)
            return ""
        text = result.output.text.strip()  # type: ignore[union-attr]
        logger.info("[QWEN] success: fn=portfolio_narrative gate=passed len=%d", len(text))
        return text
