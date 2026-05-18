# 策略：Polymarket 事件信号

## 目标

捕捉 Polymarket 上 crypto / macro / regulation 等相关事件的概率异动，
作为 100 分模型中 **B 部分（25 分）** 的输入。

## 数据源

- Gamma API：发现 events、markets、tags、series（活跃市场列表）
- CLOB API：读取 orderbook、prices、spreads（实时价格 = 概率）
- Data API：读取 trades、市场成交、仓位（验证流动性）

## 关注分类（config.yaml）

`crypto`, `macro`, `fed`, `etf`, `regulation`, `ai`, `election`, `sports`

## 触发条件

| 维度 | 阈值 | 评分 |
|------|------|------|
| 概率短期变化 | `polymarket_probability_change_pct >= 8`（短窗口 1h–6h） | 0–10 |
| 成交量/流动性提升 | `polymarket_volume_change_pct >= 100` | 0–5 |
| 事件临近度 | `end_date - now` ≤ 14 天 | 0–5 |
| 与 crypto/macro 相关性 | tag/title 命中关键词 | 0–5 |

## 评分公式（B 段最高 25）

```
B_score = clamp(prob_change_score, 0, 10)
       + clamp(volume_change_score, 0, 5)
       + clamp(time_proximity_score, 0, 5)
       + clamp(relevance_score, 0, 5)
```

## 流程

```
GET gamma-api: events?closed=false&limit=200
  ↓ 过滤 active=true、volume > 阈值、tag 命中
GET clob: book / prices-history（短窗口）
GET data:  trades（最近 24h）
  ↓
计算 prob_change、volume_change、time_to_close、tag_match
  ↓
B_score → cross_signal_engine
```

## 输出字段

```json
{
  "type": "polymarket",
  "event_id": "...",
  "title": "Solana ETF approval by ...",
  "tag": "etf",
  "probability_now": 0.41,
  "probability_prev": 0.28,
  "probability_change_pct": 13,
  "volume_24h_usd": 1800000,
  "volume_change_pct": 180,
  "days_to_resolve": 21,
  "polymarket_score": 22
}
```

## 边界

- **只读取**，绝不调用下单 / 撤单 / 改单接口
- 失败时跳过本市场，不阻塞其他市场
