"""End-of-day Market Movers Summary (US stocks + Crypto + Asia + Macro)."""
from scanner.universe import SECTORS, SECTOR_LABELS, SYMBOL_SECTOR, ASIA_MARKETS, ASIA_NAMES


def _top_n(lst, n, key="daily_change_pct", desc=True):
    return sorted(lst, key=lambda x: x.get(key) or 0, reverse=desc)[:n]


# ── US section ────────────────────────────────────────────────────────────────

def format_daily_summary(
    stock_results: list,
    crypto_results: list,
    scan_date: str,
    asia_results: dict = None,   # {market_key: [results]}
    macro_snapshot: list = None,
) -> str:
    lines = [f"📊 *今日 Market Movers Summary*", f"日期: {scan_date}", ""]

    # ── US Stocks / ETFs ──────────────────────────────────────────────────
    if stock_results:
        for title, desc, lst in [
            ("🏆 最强 美股/ETF  Top 10", True,  _top_n(stock_results, 10)),
            ("💀 最弱 美股/ETF  Top 10", False, _top_n(stock_results, 10, desc=False)),
        ]:
            lines.append(f"*{title}*")
            for i, r in enumerate(lst, 1):
                chg = r["daily_change_pct"]
                em  = "📈" if chg > 0 else "📉"
                lines.append(f"  {i}. *{r['symbol']}*  {chg:+.1f}%  {em}")
            lines.append("")

        # Sector
        lines.append("🏭 *美股行业*")
        perf: dict = {}
        for r in stock_results:
            sec = SYMBOL_SECTOR.get(r["symbol"])
            if sec:
                perf.setdefault(sec, []).append(r["daily_change_pct"])
        for sec, vals in sorted(perf.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
            avg = sum(vals) / len(vals)
            lines.append(f"  {'🟢' if avg>0 else '🔴'} {SECTOR_LABELS.get(sec,sec)}: {avg:+.2f}%")
        lines.append("")

    # ── Crypto ────────────────────────────────────────────────────────────
    if crypto_results:
        for title, lst in [
            ("🚀 最强 Crypto  Top 10", _top_n(crypto_results, 10)),
            ("📉 最弱 Crypto  Top 10", _top_n(crypto_results, 10, desc=False)),
        ]:
            lines.append(f"*{title}*")
            for i, r in enumerate(lst, 1):
                chg = r["daily_change_pct"]
                lines.append(f"  {i}. *{r['symbol']}*  {chg:+.1f}%")
            lines.append("")

    # ── Asia markets ──────────────────────────────────────────────────────
    if asia_results:
        for mkey, results in asia_results.items():
            if not results:
                continue
            info  = ASIA_MARKETS[mkey]
            flag, label = info["flag"], info["label"]
            lines.append(f"*{flag} {label} Top 5 / Bottom 5*")
            tops = _top_n(results, 5)
            bots = _top_n(results, 5, desc=False)
            lines.append("  📈 最强: " + "  ".join(
                f"{r.get('name', r['symbol'])} {r['daily_change_pct']:+.1f}%" for r in tops))
            lines.append("  📉 最弱: " + "  ".join(
                f"{r.get('name', r['symbol'])} {r['daily_change_pct']:+.1f}%" for r in bots))
            lines.append("")

    # ── Macro snapshot ────────────────────────────────────────────────────
    if macro_snapshot:
        # Show only instruments with notable moves
        notable = [r for r in macro_snapshot
                   if r.get("daily_change_pct") is not None and abs(r["daily_change_pct"]) >= 0.5]
        notable.sort(key=lambda x: abs(x["daily_change_pct"]), reverse=True)
        if notable:
            lines.append("🌐 *宏观亮点*")
            for r in notable[:8]:
                chg = r["daily_change_pct"]
                em  = "📈" if chg > 0 else "📉"
                lines.append(f"  {em} {r['name']}: {chg:+.2f}%")
            lines.append("")

    # ── Hot themes ────────────────────────────────────────────────────────
    lines.append("🔥 *热门主题*")
    sd = {r["symbol"]: r["daily_change_pct"] for r in stock_results}
    themes = {
        "AI/半导体": SECTORS["ai_semiconductor"],
        "软件/云":   SECTORS["software"],
        "生物科技":  SECTORS["biotech"],
        "金融科技":  SECTORS["fintech"],
        "成长股":    SECTORS["growth"],
    }
    for theme, syms in themes.items():
        hits = [(s, sd[s]) for s in syms if s in sd]
        if not hits:
            continue
        avg    = sum(v for _, v in hits) / len(hits)
        hotstr = "  ".join(f"{s} {v:+.1f}%" for s, v in
                           sorted(hits, key=lambda x: abs(x[1]), reverse=True)[:3])
        lines.append(f"  {'🟢' if avg>0 else '🔴'} {theme} ({avg:+.1f}%): {hotstr}")

    if crypto_results:
        c_avg = sum(r["daily_change_pct"] for r in crypto_results) / len(crypto_results)
        c_top = _top_n(crypto_results, 3)
        lines.append(f"  {'🟢' if c_avg>0 else '🔴'} Crypto ({c_avg:+.1f}%): " +
                     "  ".join(f"{r['symbol']} {r['daily_change_pct']:+.1f}%" for r in c_top))

    return "\n".join(lines)
