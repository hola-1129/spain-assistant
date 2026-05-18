# 策略：风险过滤

## 目标

在评分汇总后、推送 Telegram 前，做最后一道安全检查。
v1 实现保守版本：只用免费 API 能获得的字段，做粗筛。

## 检查项

| 项 | 数据来源 | 默认行为（config.yaml.risk_filter） |
|----|---------|-------------|
| 流动性 < `min_liquidity_usd` | DexScreener / GeckoTerminal | `reject_low_liquidity: true` → 拒绝推送 |
| 合约未验证 | 链上 RPC 或 Explorer API（v1 占位） | `reject_unknown_contract: true` → 拒绝 |
| 蜜罐 / 不可卖 | Honeypot.is（v2 接入） | `reject_honeypot_if_detected: true` |
| 高税率（buy/sell > 10%） | DexScreener 字段 / GoPlus（v2） | `reject_high_tax_if_detected: true` |
| 单钱包持仓 > 30% | GoPlus / Etherscan API（v2） | `reject_holder_concentration_if_detected: true` |

## v1 实施范围

- ✅ 流动性下限（DexScreener 已返回）
- ⚠️ 合约验证、蜜罐、税率、持仓集中度：第一版**仅记录占位字段**，不阻断推送，避免误杀  
  实际接入留到 v2

## 输出

`risk_filter` 返回结构：

```python
{
    "passed": True,
    "penalty": 3,          # 0–15，影响 D 段分数
    "reasons": ["low_liquidity_warn"]
}
```

`passed=False` → cross_signal_engine 直接丢弃，不推送、不落盘 HIGH/MEDIUM。
`passed=True, penalty>0` → 落盘并按规则扣分。

## Polymarket 事件的风险过滤

- 24h volume < 5000 USD → 视为噪音事件，扣分
- 标题命中"假新闻"关键词（spam、joke 等）→ 拒绝
- 事件已结算（closed=true）→ 跳过
