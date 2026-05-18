"""Telegram message formatters for portfolio reports and risk alerts."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from monitors.portfolio_monitor import PositionResult

_ET = ZoneInfo("America/New_York")

_ACCOUNT_ORDER = ["IBKR", "FUTU", "moomoo"]


def _pnl_emoji(pct: Optional[float]) -> str:
    if pct is None:
        return "–"
    if pct >= 200:
        return "🚀"
    if pct >= 50:
        return "📈"
    if pct >= 0:
        return "🟢"
    if pct >= -15:
        return "🟡"
    return "🔴"


def _day_emoji(pct: float) -> str:
    if pct >= 3:
        return "🔥"
    if pct >= 1:
        return "📈"
    if pct >= -1:
        return "➡️"
    if pct >= -3:
        return "📉"
    return "💥"


def _fmt_usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"${val/1_000:.1f}K"
    return f"${val:.0f}"


def format_daily_portfolio_report(
    results: List[PositionResult],
    nav_base: float,
    date_str: Optional[str] = None,
) -> str:
    """Full daily portfolio snapshot for Telegram."""
    if date_str is None:
        date_str = datetime.now(_ET).strftime("%Y-%m-%d")

    # ── Aggregates ────────────────────────────────────────────────────────
    total_mv   = sum(r.market_value for r in results)
    total_upnl: Optional[float] = None
    for r in results:
        if r.unrealized_pnl is not None:
            total_upnl = (total_upnl or 0) + r.unrealized_pnl

    # Overall day change (market-value weighted)
    prev_mv = sum(r.prev_close * r.shares for r in results)
    overall_day_pct = (total_mv - prev_mv) / prev_mv * 100 if prev_mv else 0
    overall_day_usd = total_mv - prev_mv

    lines = [
        f"📊 *Portfolio Daily Report*",
        f"日期: {date_str}  |  NAV 基数: {_fmt_usd(nav_base)}",
        "",
    ]

    # ── Position table grouped by broker ──────────────────────────────────
    by_account: Dict[str, List[PositionResult]] = defaultdict(list)
    for r in results:
        by_account[r.account].append(r)

    ordered_accounts = [a for a in _ACCOUNT_ORDER if a in by_account]
    ordered_accounts += [a for a in by_account if a not in _ACCOUNT_ORDER]

    for account in ordered_accounts:
        group = by_account[account]
        acct_mv = sum(r.market_value for r in group)
        lines.append(f"*🏦 {account}*  ({_fmt_usd(acct_mv)})")
        for r in group:
            arrow   = "↑" if r.day_change_pct >= 0 else "↓"
            pnl_str = (
                f"  {_pnl_emoji(r.pnl_pct)} {r.pnl_pct:+.1f}%"
                if r.pnl_pct is not None
                else ""
            )
            day_str = f"{_day_emoji(r.day_change_pct)} {r.day_change_pct:+.1f}%"
            house   = " 🏠" if r.rule_5a_done else ""
            loss    = " ❌" if (r.pnl_pct is not None and r.pnl_pct < -15) else ""
            lines.append(
                f"  `{r.label:<10}` {arrow}${r.current_price:.2f}"
                f"  {r.shares:,}股  {_fmt_usd(r.market_value)}"
                f"  {day_str}{pnl_str}{house}{loss}"
            )
        lines.append("")

    # ── Totals ────────────────────────────────────────────────────────────
    day_arrow  = "↑" if overall_day_pct >= 0 else "↓"
    day_emoji  = _day_emoji(overall_day_pct)
    lines.append(f"合计市值: {_fmt_usd(total_mv)}")
    lines.append(
        f"今日整体: {day_arrow}{day_emoji} {overall_day_pct:+.2f}%  "
        f"({'+' if overall_day_usd >= 0 else ''}{_fmt_usd(overall_day_usd)})"
    )
    if total_upnl is not None:
        upnl_pct = total_upnl / (total_mv - total_upnl) * 100 if total_mv != total_upnl else 0
        lines.append(f"累计浮盈: {_fmt_usd(total_upnl)} ({upnl_pct:+.1f}%)")
    lines.append("")

    # ── Risk alerts ───────────────────────────────────────────────────────
    flagged = [r for r in results if r.risk_flags]
    if flagged:
        lines.append("⚠️ *风险提示*")
        for r in flagged:
            for flag in r.risk_flags:
                lines.append(f"  • [{r.label}] {flag}")
        lines.append("")

    # ── House money summary ───────────────────────────────────────────────
    house_positions = [r for r in results if r.rule_5a_done and r.unrealized_pnl]
    if house_positions:
        house_mv = sum(r.market_value for r in house_positions)
        lines.append(f"🏠 *House Money 仓位* ({len(house_positions)} 个): {_fmt_usd(house_mv)}")
        for r in house_positions:
            if r.pnl_pct:
                lines.append(f"  {r.label}: {r.pnl_pct:+.0f}% / {_fmt_usd(r.unrealized_pnl)}")
        lines.append("")

    return "\n".join(lines)


def format_premarket_report(
    results: List[PositionResult],
    nav_base: float,
    date_str: Optional[str] = None,
) -> str:
    """Pre-market portfolio brief: positions at last close, grouped by broker."""
    if date_str is None:
        date_str = datetime.now(_ET).strftime("%Y-%m-%d")

    total_mv = sum(r.market_value for r in results)
    total_upnl: Optional[float] = None
    for r in results:
        if r.unrealized_pnl is not None:
            total_upnl = (total_upnl or 0) + r.unrealized_pnl

    lines = [
        f"🌅 *盘前快报*",
        f"日期: {date_str}  |  NAV 基数: {_fmt_usd(nav_base)}",
        "",
    ]

    by_account: Dict[str, List[PositionResult]] = defaultdict(list)
    for r in results:
        by_account[r.account].append(r)

    ordered_accounts = [a for a in _ACCOUNT_ORDER if a in by_account]
    ordered_accounts += [a for a in by_account if a not in _ACCOUNT_ORDER]

    for account in ordered_accounts:
        group = by_account[account]
        acct_mv = sum(r.market_value for r in group)
        lines.append(f"*🏦 {account}*  ({_fmt_usd(acct_mv)})")
        for r in group:
            pnl_str = (
                f"  {_pnl_emoji(r.pnl_pct)} {r.pnl_pct:+.1f}%"
                if r.pnl_pct is not None
                else ""
            )
            house = " 🏠" if r.rule_5a_done else ""
            loss  = " ❌" if (r.pnl_pct is not None and r.pnl_pct < -15) else ""
            lines.append(
                f"  `{r.label:<10}` ${r.current_price:.2f}"
                f"  {r.shares:,}股  {_fmt_usd(r.market_value)}{pnl_str}{house}{loss}"
            )
        lines.append("")

    lines.append(f"合计持仓: {_fmt_usd(total_mv)}")
    if total_upnl is not None:
        upnl_pct = total_upnl / (total_mv - total_upnl) * 100 if total_mv != total_upnl else 0
        lines.append(f"累计浮盈: {_fmt_usd(total_upnl)} ({upnl_pct:+.1f}%)")
    lines.append("")

    flagged = [r for r in results if r.risk_flags]
    if flagged:
        lines.append("⚠️ *持仓风险提示*")
        for r in flagged:
            for flag in r.risk_flags:
                lines.append(f"  • [{r.label}] {flag}")
        lines.append("")

    return "\n".join(lines)


def format_portfolio_risk_alert(
    results: List[PositionResult],
    nav_base: float,
) -> Optional[str]:
    """Return a risk-alert message if any position has active flags, else None."""
    flagged = [r for r in results if r.risk_flags]
    if not flagged:
        return None

    lines = ["🚨 *Portfolio Risk Alert*", ""]
    for r in flagged:
        lines.append(f"*{r.label}* — ${r.current_price:.2f}  {r.day_change_pct:+.1f}%今日  {r.nav_pct:.1%} NAV")
        for flag in r.risk_flags:
            lines.append(f"  {flag}")
    lines.append("")
    lines.append(f"NAV 基数: {_fmt_usd(nav_base)}")
    return "\n".join(lines)


def format_position_spike_alert(r: PositionResult, spike_pct: float) -> str:
    """Alert when a held position moves sharply intraday."""
    direction = "急涨" if spike_pct > 0 else "急跌"
    emoji     = "🚀" if spike_pct > 0 else "💥"
    lines = [
        f"{emoji} *持仓异动: {r.label}*",
        f"日内 {direction}: {spike_pct:+.1f}%",
        f"当前: ${r.current_price:.2f}  市值: {_fmt_usd(r.market_value)}  {r.nav_pct:.1%} NAV",
    ]
    if r.unrealized_pnl is not None:
        lines.append(f"总浮盈: {_fmt_usd(r.unrealized_pnl)} ({r.pnl_pct:+.1f}%)")
    if r.rule_5a_done:
        lines.append("🏠 House Money — 心理成本零")
    return "\n".join(lines)
