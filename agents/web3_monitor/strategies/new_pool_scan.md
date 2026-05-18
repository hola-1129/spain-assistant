# 策略：新池子 / 新币扫描

## 目标

发现 24h–72h 内新建的池子，识别可能的早期机会与潜在风险。

## 数据源

- GeckoTerminal `new_pools`（每条链）
- DexScreener token-profiles / boost 接口（聚合趋势）

## 流程

```
拉取每条链的 new_pools
  ↓
基础过滤：
  ├─ pool_created_at 在 72h 内
  ├─ liquidity_usd >= min_liquidity_usd
  └─ 24h volume > 0
  ↓
风险预筛（与 risk_filter 对接）：
  ├─ contract verified
  ├─ holder concentration < 阈值
  └─ buy/sell tax < 阈值
  ↓
评分（独立体系，最高 30）：
  ├─ 流动性增长曲线  10
  ├─ 成交量爬升       10
  ├─ 持有人增长       5
  └─ 跨池/跨链同名同步 5
  ↓
score >= 阈值 → 写 signal_log，type="new_pool"
```

## 第一版策略

仅记录到 `signal_log.jsonl`，**不直接推送 Telegram**（噪音多，等观察一段时间再调阈值）。

## 输出字段

```json
{
  "type": "new_pool",
  "chain": "base",
  "pool": "0x...",
  "token_symbol": "FOO",
  "token_address": "0x...",
  "age_hours": 18,
  "liquidity_usd": 120000,
  "volume_24h_usd": 350000,
  "holder_count": 420,
  "new_pool_score": 22
}
```

## 注意

- 新币噪音极高，**v1 默认不推送**，仅落盘
- `risk_filter` 对未验证合约直接拒绝
- 后续版本可考虑加 contract security API（Honeypot.is、GoPlus）二次校验
