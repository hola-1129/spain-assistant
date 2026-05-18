"""Telegram message formatter for China fund daily close report."""

import re
from typing import Dict, List, Optional

from china_fund_engine.reconciliation_engine import AccountSummary

_ACCOUNT_ORDER = ["支付宝", "交通银行", "招商银行", "中信银行", "DBS_China"]

_MARKET_LABEL = {
    "US_TECH":       "美科QDII",
    "US_TECH_INDEX": "纳指QDII",
    "US_BROAD":      "标普QDII",
    "GLOBAL_MULTI":  "全球配置",
    "ASIA_PACIFIC":  "亚太",
    "A_STOCK":       "A股",
    "GOLD":          "黄金",
    "CASH":          "货币",
    "FIXED_INCOME":  "债券",
}


def _cny(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"¥{val/1_000_000:.2f}M"
    return f"¥{val/1_000:.1f}K"


def _usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    return f"${val/1_000:.1f}K"


def _pnl_emoji(pct: float) -> str:
    if pct >= 20:   return "🚀"
    if pct >= 5:    return "📈"
    if pct >= 0:    return "🟢"
    if pct >= -5:   return "🟡"
    return "🔴"


def _day_emoji(pct: Optional[float]) -> str:
    if pct is None:  return "–"
    if pct >= 2:     return "🔥"
    if pct >= 0.5:   return "📈"
    if pct >= -0.5:  return "➡️"
    if pct >= -2:    return "📉"
    return "💥"


def _shorten(name: str) -> str:
    """Strip noisy fund-name suffixes; keep core brand ≤12 chars."""
    for s in [
        "ETF发起式联接", "ETF联接", "ETF指数联接", "指数增强联接",
        "发起式联接", "联接", "(QDII-LOF)", "(QDII-FOF)", "(QDII-ETF)",
        "(LOF)", "(QDII)", "QDII",
    ]:
        name = name.replace(s, "")
    name = re.sub(r'\([A-Z]+\)$', "", name.strip())
    name = re.sub(r'[ABCE]类?$', "", name.strip())
    return name.strip()[:12]


def _pos_pnl(mv: float, cost: float) -> Optional[float]:
    if cost > 0:
        return (mv - cost) / cost * 100
    return None


def format_china_close_report(
    summaries:    Dict[str, AccountSummary],
    navs:         dict,
    reconc:       dict,
    qdii_report:  Optional[dict] = None,
    usd_cny_rate: float = 7.24,
    scan_date:    str = "",
) -> str:
    # ── Weighted overall day change ────────────────────────────────────────
    w_num = w_den = 0.0
    for s in summaries.values():
        for h in s.positions:
            nav_obj = navs.get(h.get("fund_code", ""))
            mv = float(h.get("market_value_cny") or 0)
            if nav_obj and mv and h.get("code_status") == "VERIFIED":
                w_num += mv * nav_obj.daily_change_pct
                w_den += mv
    overall_day_pct = w_num / w_den if w_den else None

    total_mv  = reconc["total_mv_cny"]
    total_pnl = reconc["total_pnl_cny"]
    pnl_pct   = reconc["pnl_pct"]
    total_usd = total_mv / usd_cny_rate

    lines = [
        "🇨🇳 *中国资产日报*",
        f"日期: {scan_date}  |  USD/CNY {usd_cny_rate:.4f}（实时）",
        "",
        "*总资产概览*",
        f"  总市值：{_cny(total_mv)}（≈ {_usd(total_usd)}）",
        f"  总浮盈：{_cny(total_pnl)}（{pnl_pct:+.1f}%）{_pnl_emoji(pnl_pct)}",
    ]
    if overall_day_pct is not None:
        day_arrow = "↑" if overall_day_pct >= 0 else "↓"
        lines.append(
            f"  今日整体：{day_arrow}{_day_emoji(overall_day_pct)} {overall_day_pct:+.2f}%"
        )
    lines.append("")

    # ── Per-account with per-holding detail ────────────────────────────────
    ordered = [a for a in _ACCOUNT_ORDER if a in summaries]
    ordered += [a for a in summaries if a not in _ACCOUNT_ORDER]

    for acct in ordered:
        s = summaries[acct]
        pct = s.pnl_pct
        lines.append(
            f"*🏦 {acct}*  {_cny(s.total_mv_cny)}"
            f"  {_pnl_emoji(pct)} {pct:+.1f}%  浮盈 {_cny(s.unrealized_pnl)}"
        )

        positions = sorted(
            s.positions,
            key=lambda h: float(h.get("market_value_cny") or 0),
            reverse=True,
        )
        for h in positions:
            code   = h.get("fund_code", "")
            mv     = float(h.get("market_value_cny") or 0)
            cost   = float(h.get("cost_basis_cny") or 0)
            name   = _shorten(h.get("fund_name", code))
            mkt    = _MARKET_LABEL.get(h.get("underlying_market", ""), "")
            status = h.get("code_status", "")

            nav_obj = navs.get(code)
            if nav_obj and status == "VERIFIED":
                day_pct = nav_obj.daily_change_pct
                day_str = f"{_day_emoji(day_pct)} {day_pct:+.2f}%"
            else:
                day_str = "–"

            pos_pnl = _pos_pnl(mv, cost)
            pnl_str = f"  {_pnl_emoji(pos_pnl)} {pos_pnl:+.1f}%" if pos_pnl is not None else ""

            mkt_tag = f"[{mkt}]" if mkt else ""
            lines.append(f"  {name}{mkt_tag} {day_str}  {_cny(mv)}{pnl_str}")
        lines.append("")

    # ── QDII exposure ──────────────────────────────────────────────────────
    if qdii_report:
        us_cny  = qdii_report["us_tech_qdii_cny"]
        us_usd  = qdii_report["us_tech_qdii_usd"]
        combined = qdii_report.get("combined_us_total_usd")
        overlaps = qdii_report.get("overlap_risks", [])
        lines += [
            "*QDII 美股暴露*",
            f"  QDII 合计：{_cny(us_cny)} ≈ {_usd(us_usd)}",
        ]
        if combined:
            lines.append(f"  含直接持股：{_usd(combined)}")
        if overlaps:
            lines.append(f"  ⚠️ 跨账户同策略重叠：{len(overlaps)} 只")
        lines.append("")

    # ── Reconciliation alerts ──────────────────────────────────────────────
    discr = reconc.get("discrepancy_alerts", [])
    dups  = reconc.get("duplicate_alerts", [])
    if discr or dups:
        lines.append("⚠️ *核查提醒*")
        for a in discr:
            lines.append(
                f"  🔴 {a.account}  {_cny(a.system_mv)} vs {_cny(a.reference_mv)}"
                f"  偏差 {a.diff_pct:.1f}%"
            )
        if dups:
            lines.append(f"  🟡 {len(dups)} 只基金跨账户持有（注意集中度）")
        lines.append("")

    lines.append("_数据：AKShare + Yahoo Finance（实时汇率）_")
    return "\n".join(lines)
