def check_price_rules(symbol: str, data: dict, rules_cfg: list) -> list:
    """Price breaks + daily % change. Returns list of alert strings."""
    if not data or data.get("price") is None:
        return []

    price      = data["price"]
    prev_close = data.get("prev_close")
    chg_24h    = data.get("change_24h_pct")  # crypto only
    alerts     = []

    for rule in rules_cfg:
        if rule.get("symbol") != symbol:
            continue

        if rule.get("price_above") and price >= rule["price_above"]:
            alerts.append(
                f"📈 *{symbol}* 突破 ${rule['price_above']:,}\n"
                f"当前: ${price:,.2f}"
            )

        if rule.get("price_below") and price <= rule["price_below"]:
            alerts.append(
                f"📉 *{symbol}* 跌破 ${rule['price_below']:,}\n"
                f"当前: ${price:,.2f}"
            )

        threshold = rule.get("daily_change_pct")
        if threshold:
            pct = None
            if chg_24h is not None:
                pct = chg_24h
            elif prev_close and prev_close > 0:
                pct = (price - prev_close) / prev_close * 100

            if pct is not None and abs(pct) >= threshold:
                emoji = "🚀" if pct > 0 else "💥"
                alerts.append(
                    f"{emoji} *{symbol}* 单日波动 {pct:+.2f}%\n"
                    f"当前: ${price:,.2f}"
                )

    return alerts
