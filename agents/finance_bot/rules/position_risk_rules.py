def check_position_risk_rules(
    latest_prices: dict,
    portfolio_cfg: dict,
    cfg: dict,
) -> list:
    if not portfolio_cfg:
        return []

    positions  = portfolio_cfg.get("positions", {})
    cash       = float(portfolio_cfg.get("cash", 0))
    alerts     = []

    crypto_value = 0.0
    pos_values   = {}

    for sym, pos in positions.items():
        price = (latest_prices.get(sym) or {}).get("price") or pos.get("avg_cost", 0)
        units = float(pos.get("shares") or pos.get("units") or 0)
        val   = price * units
        pos_values[sym] = val
        if pos.get("asset_type") == "crypto":
            crypto_value += val

    total = sum(pos_values.values()) + cash
    if total <= 0:
        return []

    max_single  = cfg.get("single_asset_max_pct", 25.0)
    max_crypto  = cfg.get("crypto_max_pct", 30.0)
    min_cash    = cfg.get("cash_min_pct", 5.0)

    for sym, val in pos_values.items():
        pct = val / total * 100
        if pct >= max_single:
            alerts.append(
                f"⚖️ *{sym}* 集中度过高: {pct:.1f}%（上限 {max_single}%）\n"
                f"市值: ${val:,.0f}"
            )

    crypto_pct = crypto_value / total * 100
    if crypto_pct >= max_crypto:
        alerts.append(
            f"🔐 加密货币占比 {crypto_pct:.1f}%（上限 {max_crypto}%）\n"
            f"加密市值: ${crypto_value:,.0f}"
        )

    cash_pct = cash / total * 100
    if cash_pct < min_cash:
        alerts.append(
            f"💵 现金比例不足: {cash_pct:.1f}%（最低 {min_cash}%）\n"
            f"现金: ${cash:,.0f}"
        )

    return alerts
