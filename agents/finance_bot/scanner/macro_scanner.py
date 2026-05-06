"""
Macro scanner — Signal-driven Trading Dashboard.
Architecture: Universe → Snapshot (price + MA) → generate_market_signals → format.
Data: yfinance only. No extra API keys.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from utils.logger import setup_logger

logger = setup_logger("macro_scanner")
_ET = ZoneInfo("America/New_York")

# ═══════════════════════════════════════════════════════════════════════════════
# Universe
# ═══════════════════════════════════════════════════════════════════════════════

FUTURES: dict[str, dict] = {
    "ES=F":  {"name": "ES",  "group": "equity_futures"},
    "NQ=F":  {"name": "NQ",  "group": "equity_futures"},
    "RTY=F": {"name": "RTY", "group": "equity_futures"},
}

RATES_VOL: dict[str, dict] = {
    "^TNX": {"name": "US10Y", "group": "rates_vol", "is_yield": True},
    "^FVX": {"name": "US5Y",  "group": "rates_vol", "is_yield": True},
    "^VIX": {"name": "VIX",   "group": "rates_vol"},
}

METALS: dict[str, dict] = {
    "GC=F": {"name": "Gold",   "group": "metals"},
    "SI=F": {"name": "Silver", "group": "metals"},
}

ENERGY: dict[str, dict] = {
    "CL=F": {"name": "WTI",    "group": "energy"},
    "BZ=F": {"name": "Brent",  "group": "energy"},
    "NG=F": {"name": "NatGas", "group": "energy"},
}

AGRI: dict[str, dict] = {
    "ZC=F": {"name": "Corn",   "group": "agri"},
    "ZW=F": {"name": "Wheat",  "group": "agri"},
    "KC=F": {"name": "Coffee", "group": "agri"},
}

CRYPTO: dict[str, dict] = {
    "BTC-USD": {"name": "BTC", "group": "crypto"},
    "ETH-USD": {"name": "ETH", "group": "crypto"},
}

FX: dict[str, dict] = {
    "DX-Y.NYB": {"name": "DXY",     "group": "fx"},
    "EURUSD=X": {"name": "EUR/USD", "group": "fx"},
    "GBPUSD=X": {"name": "GBP/USD", "group": "fx"},
    "USDJPY=X": {"name": "USD/JPY", "group": "fx"},
    "USDCNY=X": {"name": "USD/CNY", "group": "fx"},
}

ALL_MACRO: dict[str, dict] = {
    **FUTURES, **RATES_VOL, **METALS, **ENERGY, **AGRI, **CRYPTO, **FX
}

# ═══════════════════════════════════════════════════════════════════════════════
# Signal thresholds — all constants, never inline magic numbers
# ═══════════════════════════════════════════════════════════════════════════════

# Risk ON/OFF
_RISK_FUTURES_NEEDED    = 2     # how many of ES/NQ/RTY must move same direction
_RISK_ON_VIX_PCT_MAX    = 0.0   # VIX must be falling (any decline)
_RISK_ON_US10Y_BP_MAX   = 5.0
_RISK_ON_DXY_PCT_MAX    = 0.3
_RISK_OFF_VIX_PCT_MIN   = 5.0
_RISK_OFF_US10Y_BP_MIN  = 8.0
_RISK_OFF_DXY_PCT_MIN   = 0.5

# VIX level buckets
_VIX_LOW    = 15.0
_VIX_NORMAL = 20.0
_VIX_HIGH   = 25.0

# Rate signals (in bp)
_RATES_SHOCK_BP = 8.0
_RATES_HAVEN_BP = -8.0

# Alert triggers
_ALERT_VIX_LEVEL    = 25.0
_ALERT_VIX_PCT      = 10.0
_ALERT_US10Y_BP     = 10.0
_ALERT_DXY_PCT      = 0.7
_ALERT_ES_DROP_PCT  = -1.0
_ALERT_NQ_DROP_PCT  = -1.0
_ALERT_GOLD_SURGE   = 2.0
_ALERT_OIL_MOVE     = 3.0
_ALERT_COFFEE_PCT   = 3.0
_ALERT_CRYPTO_MOVE  = 5.0

# scan_unusual thresholds (% move per group)
_THRESHOLDS: dict[str, float] = {
    "equity_futures": 1.0,
    "rates_vol":      5.0,
    "metals":         1.5,
    "energy":         3.0,
    "agri":           2.5,
    "crypto":         5.0,
    "fx":             0.5,
}

# Groups that receive full MA20/50/200 history
_FULL_MA_GROUPS = {"equity_futures", "metals", "crypto"}

# Trend-layer targets: MA crossovers and key-level breaks
_TREND_TARGETS: dict[str, dict] = {
    "DX-Y.NYB": {"name_en": "DXY",    "name_zh": "美元指数", "check": "ma20", "group_emoji": "💱"},
    "GC=F":     {"name_en": "Gold",   "name_zh": "黄金",     "check": "ma50", "group_emoji": "🥇"},
    "^TNX":     {"name_en": "US10Y",  "name_zh": "美债10年", "check": "levels",
                 "levels": [4.0, 4.5], "group_emoji": "📈"},
    "^VIX":     {"name_en": "VIX",    "name_zh": "恐慌指数", "check": "levels",
                 "levels": [15.0, 20.0, 30.0], "group_emoji": "😱"},
    "CL=F":     {"name_en": "WTI",    "name_zh": "原油",     "check": "ma50", "group_emoji": "⛽"},
}

# Group labels and icons
_GROUP_META: dict[str, dict] = {
    "equity_futures": {"zh": "股指期货",   "icon": "📊"},
    "rates_vol":      {"zh": "利率/波动率","icon": "📈"},
    "metals":         {"zh": "贵金属",     "icon": "🥇"},
    "energy":         {"zh": "能源",       "icon": "⛽"},
    "agri":           {"zh": "农产品",     "icon": "🌾"},
    "crypto":         {"zh": "加密货币",   "icon": "₿"},
    "fx":             {"zh": "外汇",       "icon": "💱"},
}

# English instrument name → (Chinese label, symbol)
_NAME_ZH: dict[str, tuple] = {
    "ES":      ("标普期货",    ""),
    "NQ":      ("纳指期货",    ""),
    "RTY":     ("罗素期货",    ""),
    "US10Y":   ("美债10年",    ""),
    "VIX":     ("恐慌指数",    "😱"),
    "Gold":    ("黄金",        "🥇"),
    "Silver":  ("白银",        "🥈"),
    "WTI":     ("原油",        "⛽"),
    "Brent":   ("布油",        "⛽"),
    "NatGas":  ("天然气",      "🔥"),
    "Corn":    ("玉米",        "🌽"),
    "Wheat":   ("小麦",        "🌾"),
    "Coffee":  ("咖啡",        "☕"),
    "BTC":     ("比特币",      "₿"),
    "ETH":     ("以太坊",      "Ξ"),
    "DXY":     ("美元指数",    "💵"),
    "EUR/USD": ("欧元",        "€"),
    "GBP/USD": ("英镑",        "£"),
    "USD/JPY": ("美元/日元",   "¥"),
    "USD/CNY": ("美元/人民币", "¥"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Internal MA helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_trend(price: float, ma20, ma50, ma200) -> str | None:
    if ma20 is None:
        return None
    if ma50 is None:
        return "Bullish" if price > ma20 else "Bearish"
    if ma200 is None:
        if price > ma20 > ma50:
            return "Bullish"
        if price < ma20 < ma50:
            return "Bearish"
        return "Mixed"
    if price > ma20 > ma50 > ma200:
        return "Bullish"
    if price < ma20 < ma50 < ma200:
        return "Bearish"
    return "Mixed"


def _ma_position(r: dict) -> str:
    """Compact MA position string without raw values, e.g. 'Above MA20/50/200'."""
    price = r["price"]
    above, below = [], []
    for num, val in [("20", r.get("ma20")), ("50", r.get("ma50")), ("200", r.get("ma200"))]:
        if val is None:
            continue
        (above if price > val else below).append(num)
    parts = []
    if above:
        parts.append(f"Above MA{'/'.join(above)}")
    if below:
        parts.append(f"Below MA{'/'.join(below)}")
    return " ".join(parts)


def _fetch_ma_history(symbols: list[str]) -> dict[str, pd.Series]:
    result: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="1y", auto_adjust=True)
            if not hist.empty and "Close" in hist.columns:
                s = hist["Close"].dropna()
                if not s.empty:
                    result[sym] = s
        except Exception as e:
            logger.debug(f"MA history {sym}: {e}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Signal helpers
# ═══════════════════════════════════════════════════════════════════════════════

_TREND_CN: dict[str, str] = {
    "Bullish": "多头",
    "Bearish": "空头",
    "Mixed":   "震荡",
}

_CRYPTO_SIGNAL_CN: dict[str, str] = {
    "Strong Bull": "强势多头",
    "Bull":        "多头",
    "Weak":        "偏弱",
    "Risk":        "风险 ⚠️",
}


def _chg(r: dict | None) -> float:
    return (r.get("daily_change_pct") or 0.0) if r else 0.0


def _bp(r: dict | None) -> float:
    """Yield change in basis points (for ^TNX where price = yield%)."""
    if not r or not r.get("prev_close"):
        return 0.0
    return (r["price"] - r["prev_close"]) * 100


def _dot(chg: float | None) -> str:
    if chg is None:
        return "⬜"
    if chg > 0:
        return "🟢"
    if chg < 0:
        return "🔴"
    return "🟡"


def _equity_trend_detail(r: dict) -> str:
    p, ma20, ma50, ma200 = r["price"], r.get("ma20"), r.get("ma50"), r.get("ma200")
    if ma20 is None:
        return "N/A"
    if ma200 is not None and p > ma20 and ma20 > ma50 and ma50 > ma200:
        return "Strong Uptrend"
    if ma50 is not None and p > ma20 and p > ma50:
        return "Uptrend"
    if p < ma20:
        return "Downtrend" if (ma50 is not None and p < ma50) else "Weakening"
    return "Uptrend"


def _equity_trend_cn(r: dict) -> str:
    detail = _equity_trend_detail(r)
    return {"Strong Uptrend": "强多头", "Uptrend": "多头",
            "Weakening": "转弱", "Downtrend": "空头"}.get(detail, "")


def _crypto_signal(r: dict) -> str:
    chg_val = _chg(r)
    if chg_val <= -3:
        return "Risk"
    p, ma20, ma50 = r["price"], r.get("ma20"), r.get("ma50")
    if ma20 and ma50 and p > ma20 > ma50:
        return "Strong Bull"
    if ma20 and p > ma20:
        return "Bull"
    return "Weak"


# ═══════════════════════════════════════════════════════════════════════════════
# generate_market_signals — public API
# ═══════════════════════════════════════════════════════════════════════════════

def generate_market_signals(snapshot: list) -> dict:
    """
    Core signal engine. Takes a snapshot list, returns a structured signals dict.
    All logic is threshold-driven; no predictions, only state classification.
    """
    by_sym = {r["symbol"]: r for r in snapshot}

    es  = by_sym.get("ES=F")
    nq  = by_sym.get("NQ=F")
    rty = by_sym.get("RTY=F")
    vix = by_sym.get("^VIX")
    tnx = by_sym.get("^TNX")
    dxy = by_sym.get("DX-Y.NYB")
    btc = by_sym.get("BTC-USD")
    eth = by_sym.get("ETH-USD")
    gld = by_sym.get("GC=F")
    wti = by_sym.get("CL=F")
    cof = by_sym.get("KC=F")

    vix_chg  = _chg(vix)
    us10y_bp = _bp(tnx)
    dxy_chg  = _chg(dxy)

    # ── Risk ON / OFF ──────────────────────────────────────────────────────
    futures_up   = sum(1 for r in [es, nq, rty] if _chg(r) > 0)
    futures_down = sum(1 for r in [es, nq, rty] if _chg(r) < 0)

    on_score, off_score = 0, 0
    if futures_up   >= _RISK_FUTURES_NEEDED: on_score  += 1
    if futures_down >= _RISK_FUTURES_NEEDED: off_score += 1
    if vix_chg  <  _RISK_ON_VIX_PCT_MAX:    on_score  += 1
    if vix_chg  >  _RISK_OFF_VIX_PCT_MIN:   off_score += 1
    if us10y_bp <= _RISK_ON_US10Y_BP_MAX:   on_score  += 1
    if us10y_bp >  _RISK_OFF_US10Y_BP_MIN:  off_score += 1
    if dxy_chg  <  _RISK_ON_DXY_PCT_MAX:    on_score  += 1
    if dxy_chg  >  _RISK_OFF_DXY_PCT_MIN:   off_score += 1

    if on_score >= 3 and off_score == 0:
        risk_regime = "Risk ON 🟢"
    elif off_score >= 2:
        risk_regime = "Risk OFF 🔴"
    else:
        risk_regime = "Neutral 🟡"

    # ── VIX regime ────────────────────────────────────────────────────────
    vix_level = vix["price"] if vix else None
    if vix_level is None:
        vix_regime = "N/A"
    elif vix_level < _VIX_LOW:
        vix_regime = "低波动"
    elif vix_level < _VIX_NORMAL:
        vix_regime = "正常"
    elif vix_level < _VIX_HIGH:
        vix_regime = "风险升温"
    else:
        vix_regime = "极度恐慌 🚨"

    # ── Rates signal ──────────────────────────────────────────────────────
    if us10y_bp > _RATES_SHOCK_BP:
        rates_signal = "利率冲击 🚨"
    elif us10y_bp < _RATES_HAVEN_BP:
        rates_signal = "避险走势"
    else:
        rates_signal = "中性"

    # ── Gold signal ───────────────────────────────────────────────────────
    gold_above_ma50 = bool(gld and gld.get("ma50") and gld["price"] > gld["ma50"])
    if gold_above_ma50 and dxy_chg < 0:
        gold_signal = "偏强"
    elif not gold_above_ma50 and dxy_chg > 0:
        gold_signal = "承压"
    else:
        gold_signal = "中性"

    # ── Alerts (priority-sorted, max 3 displayed) ─────────────────────────
    raw_alerts: list[tuple[int, str]] = []

    if vix_level and vix_level > _ALERT_VIX_LEVEL:
        raw_alerts.append((1, f"VIX {vix_level:.1f} — 极度恐慌，市场大跌模式"))
    elif vix_chg > _ALERT_VIX_PCT:
        raw_alerts.append((2, f"VIX {vix_chg:+.1f}% — 恐慌指数急升"))

    if us10y_bp > _ALERT_US10Y_BP:
        raw_alerts.append((1, f"US10Y +{us10y_bp:.0f}bp — 利率冲击"))

    if dxy and abs(dxy_chg) > _ALERT_DXY_PCT:
        raw_alerts.append((2, f"DXY {dxy_chg:+.2f}% — 美元异动"))

    if es and _chg(es) < _ALERT_ES_DROP_PCT:
        raw_alerts.append((1, f"ES {_chg(es):+.1f}% — 美股期货大跌"))
    elif nq and _chg(nq) < _ALERT_NQ_DROP_PCT:
        raw_alerts.append((1, f"NQ {_chg(nq):+.1f}% — 纳指期货大跌"))

    if gld and _chg(gld) > _ALERT_GOLD_SURGE:
        raw_alerts.append((2, f"Gold {_chg(gld):+.2f}% — 黄金急涨（避险信号）"))

    if wti and abs(_chg(wti)) > _ALERT_OIL_MOVE:
        raw_alerts.append((3, f"WTI {_chg(wti):+.1f}% — 原油异动"))

    if cof and _chg(cof) > _ALERT_COFFEE_PCT:
        raw_alerts.append((3, f"Coffee {_chg(cof):+.1f}% — 咖啡期货急涨"))

    for r in [btc, eth]:
        if r and abs(_chg(r)) > _ALERT_CRYPTO_MOVE:
            direction = "急涨" if _chg(r) > 0 else "急跌"
            raw_alerts.append((2, f"{r['name']} {_chg(r):+.1f}% — {direction}"))

    raw_alerts.sort(key=lambda x: x[0])
    alerts = [msg for _, msg in raw_alerts[:3]]

    # ── Top signals (priority order per spec) ─────────────────────────────
    top_candidates: list[tuple[int, str]] = []

    if vix:
        top_candidates.append((1, f"VIX {vix['price']:.1f}（{vix_chg:+.1f}%）→ {vix_regime}"))

    if tnx:
        top_candidates.append((2, f"US10Y {tnx['price']:.2f}%（{us10y_bp:+.0f}bp）→ {rates_signal}"))

    if dxy and abs(dxy_chg) > 0.15:
        top_candidates.append((3, f"DXY {dxy['price']:.2f}（{dxy_chg:+.2f}%）→ 美元{'走强' if dxy_chg > 0 else '走弱'}"))

    if nq and abs(_chg(nq)) > 0.3:
        top_candidates.append((4, f"NQ {nq['price']:,.0f}（{_chg(nq):+.1f}%）→ {_equity_trend_cn(nq)}"))

    if btc and abs(_chg(btc)) > 0.5:
        top_candidates.append((5, f"BTC {btc['price']:,.0f}（{_chg(btc):+.1f}%）→ {_CRYPTO_SIGNAL_CN.get(_crypto_signal(btc), '')}"))

    if gld and abs(_chg(gld)) > 0.3:
        top_candidates.append((6, f"Gold {gld['price']:,.0f}（{_chg(gld):+.2f}%）→ {gold_signal}"))

    if wti and abs(_chg(wti)) > 1.0:
        top_candidates.append((7, f"WTI {wti['price']:.1f}（{_chg(wti):+.1f}%）→ {'走强' if _chg(wti) > 0 else '走弱'}"))

    if cof and abs(_chg(cof)) > 1.0:
        top_candidates.append((8, f"Coffee {cof['price']:.0f}（{_chg(cof):+.1f}%）→ {'走强' if _chg(cof) > 0 else '走弱'}"))

    top_candidates.sort(key=lambda x: x[0])
    top_signals = [msg for _, msg in top_candidates[:3]]

    # ── Market regime ─────────────────────────────────────────────────────
    oil_surge  = wti is not None and _chg(wti) > 1.0
    gold_surge = gld is not None and _chg(gld) > 1.0
    if off_score >= 2 and vix_level and vix_level > _VIX_NORMAL:
        regime = "Defensive Risk-Off"
    elif oil_surge and gold_surge and dxy_chg > 0.3:
        regime = "Inflation Trade"
    elif dxy_chg > 0.5 and us10y_bp > 5:
        regime = "Dollar Tightening"
    elif on_score >= 3:
        regime = "Growth Risk-On"
    else:
        regime = "Mixed / Transitional"

    # ── Cross-asset validation ────────────────────────────────────────────
    def _cross(cond: bool, yes: str, no: str) -> str:
        return f"✅ {yes}" if cond else f"⚠️ {no}"

    stocks_up = _chg(es) > 0 if es else None
    cross_vix = _cross(
        stocks_up is not None and ((stocks_up and vix_chg < 0) or (not stocks_up and vix_chg > 0)),
        "确认", "背离"
    ) if (es and vix) else "N/A"

    cross_btc = _cross(
        bool(btc and ((_chg(es) > 0 and _chg(btc) > 0) or (_chg(es) < 0 and _chg(btc) < 0))),
        "确认", "背离"
    ) if (es and btc) else "N/A"

    cross_gold = _cross(
        bool(gld and ((_chg(gld) > 0 and dxy_chg < 0) or (_chg(gld) < 0 and dxy_chg > 0))),
        "确认", "背离"
    ) if (gld and dxy) else "N/A"

    cross_rates = _cross(
        us10y_bp <= _RATES_SHOCK_BP,
        "友好", "压力"
    ) if tnx else "N/A"

    cross_lines = [
        f"美股↔VIX：{cross_vix}  美股↔BTC：{cross_btc}",
        f"黄金↔DXY：{cross_gold}  利率↔股市：{cross_rates}",
    ]

    # ── Action mode ───────────────────────────────────────────────────────
    if vix_level and (vix_level > _VIX_HIGH or vix_chg > _ALERT_VIX_PCT):
        action_mode = "🔴 高风险"
        action_tip  = "大幅减仓，等待市场稳定"
    elif off_score >= 2 or us10y_bp > _RATES_SHOCK_BP:
        action_mode = "🟠 防守"
        action_tip  = "降低风险敞口，增持避险资产"
    elif on_score >= 3:
        action_mode = "🟢 进攻"
        action_tip  = "延续多头，关注动量强标的"
    else:
        action_mode = "🟡 观察"
        action_tip  = "保持仓位，等待方向确认"

    # ── Market summary (one sentence) ─────────────────────────────────────
    if "Risk ON" in risk_regime and vix_regime == "低波动":
        summary = "风险偏好回升，低波动做多环境"
    elif "Risk OFF" in risk_regime:
        summary = "避险情绪主导，关注防守资产"
    elif rates_signal == "利率冲击 🚨":
        summary = "利率上行冲击估值，关注债券与股票互动"
    elif gold_signal == "偏强" and "Risk ON" not in risk_regime:
        summary = "避险需求支撑黄金，等待风险信号"
    elif regime == "Inflation Trade":
        summary = "通胀交易主导：油金双涨，关注利率走向"
    else:
        summary = "市场方向分歧，等待关键数据确认"

    return {
        "risk_regime":    risk_regime,
        "regime":         regime,
        "vix_regime":     vix_regime,
        "rates_signal":   rates_signal,
        "gold_signal":    gold_signal,
        "alerts":         alerts,
        "top_signals":    top_signals,
        "cross_lines":    cross_lines,
        "action_mode":    action_mode,
        "action_tip":     action_tip,
        "market_summary": summary,
        # raw values reused by formatter
        "_by_sym":        by_sym,
        "_us10y_bp":      us10y_bp,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Scanner class — snapshot + scan_unusual (unchanged interface)
# ═══════════════════════════════════════════════════════════════════════════════

class MacroScanner:

    def snapshot(self) -> list:
        """Current prices + MA enrichment for all macro instruments."""
        ma_syms = [s for s, m in ALL_MACRO.items() if m["group"] in _FULL_MA_GROUPS]
        hist_data = _fetch_ma_history(ma_syms)

        results: list[dict] = []
        for sym, meta in ALL_MACRO.items():
            try:
                fi   = yf.Ticker(sym).fast_info
                p    = fi.last_price
                prev = fi.previous_close
                if not p:
                    continue
                chg_pct = (p - prev) / prev * 100 if prev else None

                item: dict = {
                    "symbol":           sym,
                    "name":             meta["name"],
                    "group":            meta["group"],
                    "price":            p,
                    "prev_close":       prev,
                    "daily_change_pct": chg_pct,
                    "is_yield":         meta.get("is_yield", False),
                    "ma20":  None,
                    "ma50":  None,
                    "ma200": None,
                    "trend": None,
                }

                if sym in hist_data:
                    closes = hist_data[sym]
                    n = len(closes)
                    if n >= 20:
                        item["ma20"]  = float(closes.rolling(20).mean().iloc[-1])
                    if n >= 50:
                        item["ma50"]  = float(closes.rolling(50).mean().iloc[-1])
                    if n >= 200:
                        item["ma200"] = float(closes.rolling(200).mean().iloc[-1])
                    item["trend"] = _calc_trend(p, item["ma20"], item["ma50"], item["ma200"])

                results.append(item)
            except Exception as e:
                logger.debug(f"{sym}: {e}")

        return results

    def scan_unusual(self, snapshot: list | None = None) -> list:
        """Return instruments that moved beyond their group threshold."""
        if snapshot is None:
            snapshot = self.snapshot()
        alerts: list[dict] = []
        for r in snapshot:
            chg = r.get("daily_change_pct")
            if chg is None:
                continue
            threshold = _THRESHOLDS.get(r["group"], 2.0)
            if abs(chg) >= threshold:
                alerts.append({**r, "threshold": threshold})
        alerts.sort(key=lambda x: abs(x["daily_change_pct"]), reverse=True)
        return alerts

    def scan_trend(self, snapshot: list | None = None) -> list:
        """Detect MA crossovers and key-level breaks for 5 macro indicators."""
        if snapshot is None:
            snapshot = self.snapshot()
        snap = {r["symbol"]: r for r in snapshot}

        # Fetch MA history for symbols not already covered by _FULL_MA_GROUPS
        need_ma = [s for s in _TREND_TARGETS if snap.get(s, {}).get("ma50") is None]
        extra   = _fetch_ma_history(need_ma)

        alerts = []
        for sym, cfg in _TREND_TARGETS.items():
            item = snap.get(sym)
            if not item:
                continue
            price = item["price"]
            prev  = item.get("prev_close") or price

            # Resolve MA values
            ma20 = item.get("ma20")
            ma50 = item.get("ma50")
            if sym in extra:
                closes = extra[sym]
                if ma20 is None and len(closes) >= 20:
                    ma20 = float(closes.rolling(20).mean().iloc[-1])
                if ma50 is None and len(closes) >= 50:
                    ma50 = float(closes.rolling(50).mean().iloc[-1])

            direction = signal = detail_zh = detail_en = None

            if cfg["check"] == "ma20" and ma20:
                if price > ma20 * 1.01 and prev <= ma20 * 1.01:
                    direction = "bullish"
                    signal    = f"上穿 MA20 · Breaks Above MA20"
                    detail_zh = f"{cfg['name_zh']}确认上行趋势，关注突破持续性"
                    detail_en = f"{cfg['name_en']} reclaims MA20, uptrend confirmed"
                elif price < ma20 * 0.99 and prev >= ma20 * 0.99:
                    direction = "bearish"
                    signal    = f"跌破 MA20 · Breaks Below MA20"
                    detail_zh = f"{cfg['name_zh']}失守 MA20，短期趋势转弱"
                    detail_en = f"{cfg['name_en']} loses MA20 support, trend weakening"

            elif cfg["check"] == "ma50" and ma50:
                if price > ma50 * 1.01 and prev <= ma50 * 1.01:
                    direction = "bullish"
                    signal    = f"上穿 MA50 · Breaks Above MA50"
                    detail_zh = f"{cfg['name_zh']}站上 MA50，中期趋势转多"
                    detail_en = f"{cfg['name_en']} reclaims MA50, medium-term trend bullish"
                elif price < ma50 * 0.99 and prev >= ma50 * 0.99:
                    direction = "bearish"
                    signal    = f"跌破 MA50 · Breaks Below MA50"
                    detail_zh = f"{cfg['name_zh']}跌破 MA50，中期趋势转空"
                    detail_en = f"{cfg['name_en']} loses MA50, medium-term trend bearish"

            elif cfg["check"] == "levels":
                for level in cfg["levels"]:
                    crossed_up   = prev < level <= price
                    crossed_down = prev > level >= price
                    if crossed_up or crossed_down:
                        direction = "bearish" if sym == "^VIX" and crossed_up else \
                                    "bullish" if sym == "^VIX" and crossed_down else \
                                    ("bullish" if crossed_up else "bearish")
                        signal    = f"突破关键位 {level} · Crosses Key Level {level}"
                        if sym == "^VIX":
                            detail_zh = f"VIX 穿越 {level}，{'恐慌情绪上升' if crossed_up else '市场情绪缓和'}"
                            detail_en = f"VIX crosses {level}, {'fear rising' if crossed_up else 'fear receding'}"
                        else:
                            detail_zh = f"US10Y {'突破' if crossed_up else '跌破'} {level}%，{'加息预期升温' if crossed_up else '降息预期升温'}"
                            detail_en = f"US10Y {'breaks above' if crossed_up else 'breaks below'} {level}%, {'rate hike pressure' if crossed_up else 'rate cut expectations'}"
                        break

            if direction:
                alerts.append({
                    **item,
                    "name_en":    cfg["name_en"],
                    "name_zh":    cfg["name_zh"],
                    "group_emoji": cfg["group_emoji"],
                    "trend_direction": direction,
                    "trend_signal":    signal,
                    "trend_detail_zh": detail_zh,
                    "trend_detail_en": detail_en,
                    "ma20": ma20,
                    "ma50": ma50,
                })
        # 5Y-10Y yield curve spread (cross-symbol inversion alert)
        tnx_item = snap.get("^TNX")
        fvx_item = snap.get("^FVX")
        if tnx_item and fvx_item:
            spread = fvx_item["price"] - tnx_item["price"]   # positive = 5Y > 10Y = inverted
            prev_tnx = tnx_item.get("prev_close") or tnx_item["price"]
            prev_fvx = fvx_item.get("prev_close") or fvx_item["price"]
            prev_spread = prev_fvx - prev_tnx
            if spread > 0 and prev_spread <= 0:              # fresh inversion today
                alerts.append({
                    **tnx_item,
                    "symbol":          "5Y-10Y",
                    "name_en":         "Yield Curve",
                    "name_zh":         "收益率曲线",
                    "group_emoji":     "📈",
                    "trend_direction": "bearish",
                    "trend_signal":    "收益率曲线倒挂",
                    "trend_detail_zh": f"5Y {fvx_item['price']:.2f}% > 10Y {tnx_item['price']:.2f}%，历史衰退预警信号",
                    "trend_detail_en": f"Yield curve inverted: 5Y {fvx_item['price']:.2f}% > 10Y {tnx_item['price']:.2f}%",
                    "ma20": None,
                    "ma50": None,
                })
        return alerts

    def get_history(self, symbols: list | None = None, period: str = "3mo") -> dict:
        if symbols is None:
            symbols = list(ALL_MACRO.keys())
        result: dict = {}
        for sym in symbols:
            try:
                hist = yf.Ticker(sym).history(period=period)
                if not hist.empty:
                    result[sym] = hist
            except Exception as e:
                logger.debug(f"{sym} history: {e}")
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════════════

_SEP = "─" * 30


def format_macro_snapshot(snapshot: list) -> str:
    """
    Signal-driven Trading Dashboard for Telegram.
    Target: ≤ 45 lines.
    """
    sig  = generate_market_signals(snapshot)
    now  = datetime.now(_ET).strftime("%d-%b %H:%M ET")
    bsym = sig["_by_sym"]

    lines: list[str] = []

    def L(s: str = "") -> None:
        lines.append(s)

    def SEP() -> None:
        lines.append(_SEP)

    # ── Header ────────────────────────────────────────────────────────────
    L("🌍 *宏观快照 Macro Snapshot*")
    L(f"🕒 {now}")
    L(f"🧠 今日市场：{sig['market_summary']}")
    SEP()

    # ── Regime + Top Signals ──────────────────────────────────────────────
    L(f"🧭 市场结构：{sig['regime']}  ｜  {sig['risk_regime']}")
    if sig["top_signals"]:
        L("⭐ *今日重点*")
        for s in sig["top_signals"]:
            L(f"• {s}")
    SEP()

    # ── Alerts ────────────────────────────────────────────────────────────
    if sig["alerts"]:
        L("🚨 *异常提醒*")
        for a in sig["alerts"]:
            L(f"• {a}")
    else:
        L("🚨 无异常提醒")
    SEP()

    # ── Cross-asset validation ────────────────────────────────────────────
    for cl in sig["cross_lines"]:
        L(f"🔗 {cl}" if cl == sig["cross_lines"][0] else f"   {cl}")
    SEP()

    # ── Action ────────────────────────────────────────────────────────────
    L(f"🧑‍💼 动作：{sig['action_mode']}  ｜  {sig['action_tip']}")
    SEP()

    # ── Equity Futures ────────────────────────────────────────────────────
    L("📈 *美股期货*")
    _ef_order = {"ES": 0, "NQ": 1, "RTY": 2}
    ef_items = sorted(
        [r for r in snapshot if r["group"] == "equity_futures"],
        key=lambda x: _ef_order.get(x["name"], 9)
    )
    for r in ef_items:
        chg = r["daily_change_pct"]
        if chg is None:
            continue
        trend_cn = _equity_trend_cn(r)
        ma_pos   = _ma_position(r)
        suffix   = f"｜{trend_cn}" if trend_cn else ""
        if ma_pos:
            suffix += f"｜{ma_pos}"
        L(f"{_dot(chg)} {r['name']}：{r['price']:,.0f}（{chg:+.1f}%）{suffix}")
    SEP()

    # ── Rates & Vol ───────────────────────────────────────────────────────
    L("📊 *利率 & 波动率*")
    tnx = bsym.get("^TNX")
    fvx = bsym.get("^FVX")
    vix = bsym.get("^VIX")
    if tnx:
        us10y_bp = sig["_us10y_bp"]
        rates_lbl = sig["rates_signal"]
        L(f"US10Y：{tnx['price']:.2f}%（{us10y_bp:+.0f}bp）｜{rates_lbl}")
    if tnx and fvx:
        spread = fvx["price"] - tnx["price"]
        curve_lbl = "⚠️ 倒挂" if spread > 0 else "正常"
        L(f"5Y-10Y利差：{spread:+.2f}%  ｜{curve_lbl}")
    if vix:
        vix_lbl = sig["vix_regime"]
        L(f"VIX：{vix['price']:.1f}（{_chg(vix):+.1f}%）｜{vix_lbl}")
    SEP()

    # ── Metals ────────────────────────────────────────────────────────────
    L("🥇 *贵金属*")
    _metal_order = {"Gold": 0, "Silver": 1}
    for r in sorted(
        [r for r in snapshot if r["group"] == "metals"],
        key=lambda x: _metal_order.get(x["name"], 9)
    ):
        chg = r["daily_change_pct"]
        if chg is None:
            continue
        ma_pos = _ma_position(r)
        signal = sig["gold_signal"] if r["name"] == "Gold" else (_TREND_CN.get(r.get("trend") or "", "") or "震荡")
        suffix = f"｜{signal}"
        if ma_pos:
            suffix += f"｜{ma_pos}"
        L(f"{_dot(chg)} {r['name']}：{r['price']:,.1f}（{chg:+.2f}%）{suffix}")
    SEP()

    # ── Energy (compact) ──────────────────────────────────────────────────
    _e_order = {"WTI": 0, "Brent": 1, "NatGas": 2}
    energy_parts = []
    for r in sorted(
        [r for r in snapshot if r["group"] == "energy"],
        key=lambda x: _e_order.get(x["name"], 9)
    ):
        chg = r["daily_change_pct"]
        if chg is not None:
            energy_parts.append(f"{r['name']}：{r['price']:.2f}（{chg:+.1f}%）")
    if energy_parts:
        L("🛢️ " + "  ".join(energy_parts))

    # ── Agri (compact) ────────────────────────────────────────────────────
    _a_order = {"Corn": 0, "Wheat": 1, "Coffee": 2}
    agri_parts = []
    for r in sorted(
        [r for r in snapshot if r["group"] == "agri"],
        key=lambda x: _a_order.get(x["name"], 9)
    ):
        chg = r["daily_change_pct"]
        if chg is not None:
            name = "☕" + r["name"] if r["name"] == "Coffee" else r["name"]
            agri_parts.append(f"{name}：{r['price']:.0f}（{chg:+.1f}%）")
    if agri_parts:
        L("🌽 " + "  ".join(agri_parts))

    if energy_parts or agri_parts:
        SEP()

    # ── Crypto ────────────────────────────────────────────────────────────
    crypto_items = [r for r in snapshot if r["group"] == "crypto"]
    if crypto_items:
        L("₿ *加密资产*")
        _c_order = {"BTC": 0, "ETH": 1}
        for r in sorted(crypto_items, key=lambda x: _c_order.get(x["name"], 9)):
            chg = r["daily_change_pct"]
            if chg is None:
                continue
            cs     = _crypto_signal(r)
            cs_cn  = _CRYPTO_SIGNAL_CN.get(cs, cs)
            ma_pos = _ma_position(r)
            suffix = f"｜{cs_cn}"
            if ma_pos:
                suffix += f"｜{ma_pos}"
            L(f"{_dot(chg)} {r['name']}：{r['price']:,.0f}（{chg:+.1f}%）{suffix}")
        SEP()

    # ── FX ────────────────────────────────────────────────────────────────
    L("💱 *外汇*")
    _fx_order = {"DXY": 0, "EUR/USD": 1, "GBP/USD": 2, "USD/JPY": 3, "USD/CNY": 4}
    fx_items = sorted(
        [r for r in snapshot if r["group"] == "fx"],
        key=lambda x: _fx_order.get(x["name"], 9)
    )
    # 3 per row
    fx_parts: list[str] = []
    for r in fx_items:
        chg = r["daily_change_pct"]
        if chg is None:
            continue
        fx_parts.append(f"{r['name']}：{r['price']:.4g}（{chg:+.2f}%）")
    for i in range(0, len(fx_parts), 3):
        L("  ".join(fx_parts[i : i + 3]))

    return "\n".join(lines).rstrip()


def format_macro_alert(r: dict) -> str:
    chg         = r["daily_change_pct"]
    threshold   = r.get("threshold", 1.0)
    zh, sym     = _NAME_ZH.get(r["name"], ("", ""))
    name_str    = f"{r['name']} {zh} {sym}".strip()
    gm          = _GROUP_META.get(r["group"], {"zh": r["group"], "icon": "📊"})
    severity    = "🚨" if abs(chg) >= threshold * 2 else "⚡"
    dir_emoji   = "🟢" if chg > 0 else "🔴"
    arrow       = "📈" if chg > 0 else "📉"
    return (
        f"{severity} *{name_str}*  异动提醒\n"
        f"{gm['icon']} {gm['zh']}\n"
        f"{'─' * 24}\n"
        f"{dir_emoji} {chg:+.2f}%  {arrow}  {r['price']:,.4g}\n"
        f"阈值 ±{threshold}%"
    )


def format_trend_alert(r: dict) -> str:
    dir_emoji   = "🟢" if r["trend_direction"] == "bullish" else "🔴"
    chg         = r.get("daily_change_pct") or 0
    chg_str     = f"{chg:+.2f}%" if chg else "—"
    name_str    = f"{r['name_en']} {r['name_zh']} {r['group_emoji']}".strip()
    signal_zh   = r["trend_signal"].split(" · ")[0]
    ma_line     = ""
    if r.get("ma50"):
        ma_line = f"📐 MA50: {r['ma50']:,.4g}\n"
    elif r.get("ma20"):
        ma_line = f"📐 MA20: {r['ma20']:,.4g}\n"
    return (
        f"{dir_emoji} *{name_str}*  {signal_zh}\n"
        f"{'─' * 24}\n"
        f"💵 价格: {r['price']:,.4g}  ({chg_str})\n"
        f"{ma_line}"
        f"{r['trend_detail_zh']}"
    )
