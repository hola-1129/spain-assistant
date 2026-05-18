# 策略：DEX 异动信号

## 目标

捕捉单池 / 单 token 的短期异动，作为 100 分模型中 **A 部分（35 分）** 的输入。

## 数据源

- DexScreener：跨链聚合 DEX 数据，更新快
- GeckoTerminal：多链 DEX OHLCV 与流动性，作为 DexScreener 的交叉验证

## 触发条件（任一即评分）

| 维度 | 阈值（默认，可在 config.yaml 调整） | 评分 |
|------|------|------|
| 价格 1h 变化 | `price_change_1h_pct >= 8` | 0–10 |
| 价格 24h 变化 | `price_change_24h_pct >= 20` | 0–10（与 1h 取较高权重） |
| 成交量 1h 放大 | `volume_change_1h_pct >= 80` | 0–10 |
| 流动性质量 | `liquidity_usd >= min_liquidity_usd` 且 24h 流入 > 0 | 0–10 |
| 多池同步异动 | 同一 token 在 ≥2 个池子同方向异动 | 0–5 |

## 评分公式（A 段最高 35）

```
A_score = clamp(price_score, 0, 10)
       + clamp(volume_score, 0, 10)
       + clamp(liquidity_score, 0, 10)
       + clamp(multi_pool_score, 0, 5)
```

## 输出字段（写入 signal_log.jsonl）

```json
{
  "type": "dex",
  "asset": "SOL",
  "chain": "solana",
  "pool": "0x...",
  "price_change_1h_pct": 9.8,
  "volume_change_1h_pct": 145,
  "liquidity_usd": 3200000,
  "multi_pool": true,
  "dex_score": 28
}
```

## 边界

- 流动性 < `min_liquidity_usd` 直接降权（不加分）
- 数据源失败仅记录日志，不阻塞其他源
