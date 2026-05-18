"""
Daily close summary — RULE tier template formatting.
No LLM required; clean, readable Telegram output.
"""
from __future__ import annotations

from core.leaps_signal import LEAPSCandidate
from core.theme_scorer import RadarSnapshot

_EMOJI = {
    "STRONG":    "🟢",
    "BROADENING": "🔵",
    "NEUTRAL":   "⚪",
    "NARROWING": "🟡",
    "WEAK":      "🔴",
}


def format_daily_summary(snapshot: RadarSnapshot) -> str:
    today = snapshot.as_of.isoformat()
    lines = [
        f"📊 *AI Narrative Radar — Daily Close*",
        f"_{today}_",
        "",
    ]

    sorted_themes = sorted(
        snapshot.theme_breadths.values(),
        key=lambda b: b.avg_rs_spy_1m,
        reverse=True,
    )

    # Benchmark context
    bench_parts = []
    for b_ticker in ("SPY", "QQQ", "SOXX"):
        bm = snapshot.benchmark_metrics.get(b_ticker)
        if bm:
            bench_parts.append(f"{b_ticker} {bm.ret_1d:+.1f}%")
    if bench_parts:
        lines.append(f"*Benchmarks (1D):* {' | '.join(bench_parts)}")
        lines.append("")

    # Leading themes
    strong = [b for b in sorted_themes if b.signal in ("STRONG", "BROADENING")][:3]
    if strong:
        lines.append("*🔥 Leading Themes*")
        for b in strong:
            leaders_str = " / ".join(b.leaders[:2]) if b.leaders else "—"
            lines.append(
                f"{_EMOJI[b.signal]} {b.theme_name}: "
                f"RS {b.avg_rs_spy_1m:+.1f}% | Breadth {b.breadth_rs*100:.0f}% | "
                f"Vol {b.avg_volume_ratio:.1f}x | {leaders_str}"
            )
        lines.append("")

    # Weakening themes
    weak = [b for b in sorted_themes if b.signal in ("WEAK", "NARROWING")]
    if weak:
        lines.append("*❄️ Weakening Themes*")
        for b in weak[:3]:
            lines.append(
                f"{_EMOJI[b.signal]} {b.theme_name}: "
                f"RS {b.avg_rs_spy_1m:+.1f}% | Breadth {b.breadth_rs*100:.0f}%"
            )
        lines.append("")

    # Rotation
    rot = snapshot.rotation_signal
    if rot and rot.detected:
        lines.append("*🔄 Rotation Signal*")
        lines.append(rot.description)
        lines.append(f"Confidence: {rot.confidence}/100")
        lines.append("")

    # Top individual leaders
    top = sorted(
        snapshot.ticker_metrics.values(),
        key=lambda m: m.composite_score,
        reverse=True,
    )[:5]
    if top:
        lines.append("*⭐ Individual Leaders*")
        for m in top:
            ma_str = ("↑" if m.above_20dma else "↓") + "20D"
            lines.append(
                f"  {m.ticker}: RS {m.rs_vs_spy_1m:+.1f}% 1M | "
                f"Vol {m.volume_ratio_20d:.1f}x | {ma_str}"
            )
        lines.append("")

    # LEAPS candidates (top 3, score >= 75)
    leaps = [c for c in snapshot.leaps_candidates if c.leaps_score >= 75][:3]
    if leaps:
        lines.append("*📘 LEAPS Call Candidates*")
        for c in leaps:
            opt_str = f"Options: {c.options_quality}" if c.has_leaps else "Options: check manually"
            signal_label = {
                "LEAPS_CALL_CANDIDATE":        "Candidate",
                "LEAPS_SETUP_PULLBACK":        "Pullback Setup",
                "LEAPS_RESEARCH_ONLY":         "Research Only",
                "LEAPS_HIGH_RISK_SPECULATIVE": "High Risk",
            }.get(c.signal_type, c.signal_type)
            lines.append(
                f"  {c.ticker} [{signal_label}] Score {c.leaps_score:.0f}/100 | "
                f"{c.theme_name} | {opt_str}"
            )
        lines.append("_LEAPS signals require manual review. See full alert._")
        lines.append("")

    lines.append("_Read-only intelligence. Not a trading signal._")
    return "\n".join(lines)


def format_leaps_alert(c: LEAPSCandidate, strong_threshold: float = 85.0) -> str:
    """Format a standalone LEAPS candidate Telegram alert."""
    label = (
        "STRONG LEAPS CANDIDATE 强力长期期权候选" if c.leaps_score >= strong_threshold
        else "LEAPS RESEARCH CANDIDATE 长期期权研究候选"
    )
    if c.signal_type == "LEAPS_SETUP_PULLBACK":
        label = "LEAPS PULLBACK SETUP 回调建仓机会"
    elif c.signal_type == "LEAPS_HIGH_RISK_SPECULATIVE":
        label = "LEAPS HIGH RISK — SPECULATIVE 高风险投机"
    elif c.signal_type == "LEAPS_RESEARCH_ONLY":
        label = "LEAPS RESEARCH ONLY 仅供研究（无期权数据）"

    trigger_str = "\n".join(f"- {t}" for t in c.triggers) if c.triggers else "- Threshold met"
    risk_str    = "\n".join(f"- {r}" for r in c.risk_notes) if c.risk_notes else "- None flagged"

    opt_line = (
        f"LEAPS available (expiry: {c.nearest_leaps_expiry}) — liquidity {c.options_quality}"
        if c.has_leaps
        else "No LEAPS data — verify options availability manually 无期权数据，需手动确认"
    )

    return (
        f"📘 *{label}*\n\n"
        f"*Ticker 标的：* {c.ticker}\n"
        f"*Theme 主题：* {c.theme_name}\n"
        f"*LEAPS Candidate Score 候选评分：* {c.leaps_score:.0f}/100\n\n"
        f"*Why it triggered 触发原因：*\n{trigger_str}\n\n"
        f"*Options 期权信息：* {opt_line}\n\n"
        f"*Preferred Review 建议方向：* Look at 9–24 month LEAPS calls 关注 9–24 个月的长期看涨期权。\n\n"
        f"*Risk Notes 风险提示：*\n{risk_str}\n"
        f"- Check IV level before entry 入场前检查隐含波动率\n"
        f"- Avoid chasing if stock is too extended 股价超涨时不追高\n"
        f"- Manual review required 需人工复核\n\n"
        f"_This is NOT an automatic buy signal. 本信号不构成自动买入指令。_"
    )
