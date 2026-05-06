from dataclasses import dataclass, field


@dataclass
class Signal:
    symbol:    str
    kind:      str    # e.g. 'rsi_oversold', 'volume_spike', 'death_cross'
    direction: str    # 'bullish' | 'bearish' | 'neutral'
    strength:  float  # 0.0–1.0
    label:     str    # 短标签，用于 Telegram
    detail:    str    # 一行说明
    value:     float = 0.0  # 触发时的实际数值


@dataclass
class InflectionEvent:
    symbol:    str
    score:     float          # 0–10 合力得分
    direction: str            # 'bullish' | 'bearish' | 'mixed'
    signals:   list = field(default_factory=list)

    def format_message(self) -> str:
        filled = min(int(self.score), 10)
        bar    = "●" * filled + "○" * (10 - filled)
        emoji  = "📈" if self.direction == "bullish" else (
                 "📉" if self.direction == "bearish" else "🔀")
        lines  = [f"{emoji} *{self.symbol}* 拐点  {bar}  {self.score:.1f}/10"]
        for s in self.signals:
            arrow = "↑" if s.direction == "bullish" else (
                    "↓" if s.direction == "bearish" else "→")
            lines.append(f"  {arrow} {s.label}: {s.detail}")
        return "\n".join(lines)
