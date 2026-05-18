"""
Weekly narrative review — deeper theme analysis.
RULE tier structure; optionally enriched by CC via llm/narrative.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from core.theme_scorer import RadarSnapshot

_EMOJI = {
    "STRONG":    "🟢",
    "BROADENING": "🔵",
    "NEUTRAL":   "⚪",
    "NARROWING": "🟡",
    "WEAK":      "🔴",
}


def format_weekly_review(
    current: RadarSnapshot,
    prior: Optional[RadarSnapshot],
) -> str:
    today = date.today().isoformat()
    lines = [
        f"📋 *AI Narrative Radar — Weekly Review*",
        f"_Week ending {today}_",
        "",
        "*THEME LEADERSHIP*",
        "",
    ]

    sorted_themes = sorted(
        current.theme_breadths.values(),
        key=lambda b: b.avg_rs_spy_1m,
        reverse=True,
    )

    for b in sorted_themes:
        emoji = _EMOJI.get(b.signal, "⚪")
        delta_str = ""
        if prior and b.theme_key in prior.theme_breadths:
            prev  = prior.theme_breadths[b.theme_key]
            delta = b.avg_rs_spy_1m - prev.avg_rs_spy_1m
            arrow = "↑" if delta > 0 else "↓"
            delta_str = f" {arrow}{abs(delta):.1f}%"

        leaders_str = " / ".join(b.leaders[:2]) if b.leaders else "—"
        lines.append(
            f"{emoji} *{b.theme_name}*{delta_str}\n"
            f"  RS {b.avg_rs_spy_1m:+.1f}% | Breadth {b.breadth_rs*100:.0f}% | "
            f"Vol {b.avg_volume_ratio:.1f}x | Leaders: {leaders_str}"
        )

    lines.append("")
    lines.append("*STRUCTURAL OBSERVATIONS*")

    strong = [b for b in sorted_themes if b.signal in ("STRONG", "BROADENING")]
    weak   = [b for b in sorted_themes if b.signal in ("WEAK", "NARROWING")]

    if strong:
        lines.append(f"• Leadership concentrated in: {', '.join(b.theme_name for b in strong[:3])}")
    if weak:
        lines.append(f"• Deteriorating participation: {', '.join(b.theme_name for b in weak[:3])}")

    rot = current.rotation_signal
    if rot and rot.detected:
        lines.append(f"• Rotation: {rot.description} (confidence {rot.confidence}/100)")

    # Breadth health summary
    avg_breadth = (
        sum(b.breadth_rs for b in sorted_themes) / len(sorted_themes)
        if sorted_themes else 0
    )
    market_str = (
        "BROAD" if avg_breadth >= 0.6
        else "NARROW" if avg_breadth <= 0.35
        else "MIXED"
    )
    lines.append(f"• Market breadth: {market_str} ({avg_breadth*100:.0f}% avg theme participation)")

    # LEAPS candidates summary
    leaps = [c for c in current.leaps_candidates if c.leaps_score >= 75]
    if leaps:
        lines.append("")
        lines.append("*📘 LEAPS CALL CANDIDATES THIS WEEK*")
        for c in leaps[:5]:
            signal_label = {
                "LEAPS_CALL_CANDIDATE":        "✅ Candidate",
                "LEAPS_SETUP_PULLBACK":        "📉 Pullback Setup",
                "LEAPS_RESEARCH_ONLY":         "🔍 Research Only",
                "LEAPS_HIGH_RISK_SPECULATIVE": "⚠️ High Risk",
            }.get(c.signal_type, c.signal_type)
            opt_str = (
                f"Options: {c.options_quality} (exp {c.nearest_leaps_expiry})"
                if c.has_leaps else "No options data"
            )
            lines.append(
                f"{signal_label} *{c.ticker}* — {c.theme_name}\n"
                f"  Score: {c.leaps_score:.0f}/100 | {opt_str}"
            )
        lines.append("_All LEAPS signals require manual review._")

    lines.append("")
    lines.append(
        "_Read-only market intelligence. "
        "Not a trading signal. Manual review required._"
    )
    return "\n".join(lines)
