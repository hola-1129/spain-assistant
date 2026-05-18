# 策略：综合评分引擎

## 目标

汇总 DEX、Polymarket、跨源、风险扣分，计算 100 分综合分数，决定是否推送。

## 100 分模型

```
A. DEX 异动信号        35 分
   ├─ 价格 1h/24h 异动        10
   ├─ 成交量放大              10
   ├─ 流动性质量              10
   └─ 多池同步异动             5

B. Polymarket 事件信号  25 分
   ├─ 事件概率短期变化         10
   ├─ 事件成交量/流动性提升     5
   ├─ 事件临近程度             5
   └─ 事件与 crypto/macro 相关性 5

C. 交叉验证信号         25 分
   ├─ Polymarket 概率变化与链上价格同步  10
   ├─ DEX 成交量与事件热度同步           5
   ├─ 多链/多交易所同步                  5
   └─ 巨鲸/聪明钱线索                    5

D. 风险过滤             15 分（扣分项）
   ├─ 流动性不足                         扣分
   ├─ 合约风险（未验证、可铸造）          扣分
   ├─ 交易税/貔貅盘风险                   扣分
   ├─ 单一钱包持仓过高                    扣分
   └─ 假新闻/噪音事件                     扣分
```

## 等级

| 分数 | 等级 | 行为 |
|------|------|------|
| ≥ 80 | HIGH | Telegram 推送 + 落盘 |
| 60–79 | MEDIUM | Telegram 推送 + 落盘 |
| < 60 | LOW | 只落盘 `signal_log.jsonl`，不推送 |

阈值在 `config.yaml.thresholds.min_signal_score` / `high_signal_score`。

## 交叉验证（C 段）

| 信号 | 判定 | 分数 |
|------|------|------|
| Polymarket prob ↑ 且 同 asset DEX 价格 ↑ | 方向同向且 |Δprob| 与 |Δprice| 都过阈值 | +10 |
| DEX volume ↑ 与事件 volume ↑ 同窗口 | 同 1h/4h 窗口都放大 | +5 |
| 多链同 token 同方向异动 | ≥2 条链同向 | +5 |
| 巨鲸/聪明钱线索（占位） | v1 仅记录大额 swap，不参与评分 | 0–5 |

## 风险扣分（D 段，从 15 分扣）

```
risk_penalty = 0
- 流动性 < min_liquidity_usd          → -5
- 合约未验证                          → -5
- buy/sell tax 异常                   → -3
- 单钱包持有 > 30%                    → -2
- 事件无近期成交（噪音）              → -3

D_score = max(0, 15 - risk_penalty)
```

## 总分

```
total = A_score + B_score + C_score + D_score    # 上限 100
```

## 输出（写入 signal_log.jsonl）

```json
{
  "ts": "2026-05-07T12:34:56Z",
  "type": "cross",
  "asset": "SOL",
  "chain": "solana",
  "level": "HIGH",
  "score": 82,
  "components": {"A": 28, "B": 22, "C": 20, "D": 12},
  "dex": {...},
  "polymarket": {...},
  "interpretation": "Polymarket 概率快速上升，同时 SOL 链上交易量和价格同步放大..."
}
```
