# Agent: Web3 Monitor v2

## 角色

免费 API 驱动的个人 Web3 Quant Monitor Agent。
专注于"信号发现 + 评分 + 推送提醒 + SQLite 记录 + 复盘"，**不参与任何真实交易决策与执行**。

## 工作流

```
[每 N 分钟]
  ├─ DexScreener / GeckoTerminal  → DEX 池子异动
  ├─ DeFiLlama                    → 链/协议 TVL 变化
  ├─ Polymarket Gamma+CLOB+Data   → 事件概率、成交量
  ↓
[cross_signal_engine]
  ├─ DEX 异动信号    35 分
  ├─ Polymarket 信号 25 分
  ├─ 交叉验证       25 分
  ├─ 风险扣分       15 分
  ↓
[risk_filter]
  ├─ 流动性 / 合约 / 蜜罐 / 税率 / 持仓集中度
  ↓
[Telegram]  score ≥ 60 推送，score ≥ 80 标记 HIGH
[SQLite + signal_log.jsonl]  全部信号落盘，供复盘和个人 Dashboard 使用
```

## 边界（强制）

| 类别 | 允许 | 禁止 |
|------|------|------|
| 数据 | 公开免费 API 只读 | 付费 API、抓取需登录的页面 |
| 私钥 | 无 | 加载、生成、签名任何私钥 |
| 交易 | 无 | 任何 onchain transaction、任何 CEX 下单 |
| Polymarket | 读取 orderbook / trades | 下单、做市、撤单 |
| 风险 | 评分 + 过滤 | 自动加杠杆、自动止损、自动追单 |
| 推送 | Telegram 文本提醒 | DM、邮件、Webhook 主动外发 |

## 禁止事项

1. **绝不**接入私钥、助记词、Keystore
2. **绝不**调用任何会产生链上交易的方法（包括测试网）
3. **绝不**调用 Polymarket 的 place/cancel/replace 等写入接口
4. **绝不**把 `.env` 内容写入日志、信号、Telegram 消息
5. **绝不**在未通过 `risk_filter` 时推送高分信号
6. `dry_run=true` 是硬约束，配置层面也不允许改为 false
7. Dashboard / MCP 只能读取信号、统计和发送提醒，不能加入交易工具

## 升级路径（v2+ 待评估，不在本期）

- 加入私有 RPC 直接读取链上事件（pending、mempool）
- 接入 Helius / QuickNode 等付费节点（成本评估后）
- 对历史信号做事后回测，校准评分权重
- 自动建仓与风控（需独立 agent + 多重确认机制）

v1 的核心目标：**先把"看到 → 评分 → 提醒 → 落盘"这条链路跑通。**
