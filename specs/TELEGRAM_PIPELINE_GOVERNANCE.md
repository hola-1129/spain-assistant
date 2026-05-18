# Telegram 推送管线治理 V1

> Telegram 是系统唯一的对外输出通道。所有到达 Telegram 的内容必须经过验证。

---

## 管线架构

```
数据源（DEX / Polymarket / CoinGecko / 财报）
    ↓
规则引擎（信号评分 / 阈值 / 限流）     ← RULE tier，无 LLM
    ↓
可选：Qwen 草稿富化                    ← 仅当 llm_enrichment.enabled=true
    │   QwenClient.complete()
    │   OutputGate.validate()
    │   通过 → DraftOutput 附加到信号 dict
    │   失败 → 跳过，继续用原始内容
    ↓
format_signal_alert(signal)             ← 格式化，不含决策逻辑
    ↓
TelegramNotifier.send()                 ← 唯一推送入口
```

---

## 写入权限

| 主体 | 可以写入 Telegram | 说明 |
|------|----------------|------|
| Agent 代码（finance_bot / web3_monitor / school_helper） | ✅ | 通过 `TelegramNotifier` |
| Qwen | ❌ 直接禁止 | 只能产出 `DraftOutput`，由 agent 代码决定是否附加 |
| Codex | ❌ | 不参与运行时推送逻辑 |
| CC | ❌ | 不直接调用 Telegram API |

---

## Qwen 在 Telegram 管线中的位置

Qwen **只能** 做以下事情：
- 生成附加解释段落（`qwen_explanation` 字段）
- 生成摘要草稿（`DraftOutput`，附加到报告正文前）

Qwen **不可以**：
- 决定是否推送
- 修改信号的 `score`、`level`、`asset`、`chain` 字段
- 构造完整的 Telegram 消息（格式由 `format_signal_alert` 负责）
- 替代 `TelegramNotifier`

---

## OutputGate 验证规则（Qwen 输出进入 Telegram 前）

| 规则 | 触发条件 | 行为 |
|------|---------|------|
| API key / token 泄露检测 | 包含 `sk-`、`Bearer`、`token=` 等 | 拒绝，不附加 |
| 钱包地址检测 | 包含 `0x[0-9a-fA-F]{40}` | 拒绝 |
| 金融建议检测 | 包含「you should buy/sell」等 | 拒绝 |
| 超长输出 | > 4096 字符 | 拒绝 |
| 空输出 | 空字符串 | 不附加（静默跳过） |

OutputGate 拒绝 → Qwen 字段为空，推送使用纯规则生成的原始消息，**推送不中断**。

---

## 格式化规范

`format_signal_alert(signal: dict) -> str` 是唯一的 Telegram 消息格式化函数：

- 位置：`agents/web3_monitor/scripts/telegram_notify.py`（web3_monitor）
- Qwen 内容以 `\n💡 <qwen_explanation>` 追加，位于消息末尾
- Qwen 内容缺失时消息格式与 V1 之前完全相同（向后兼容）
- 不在 `format_signal_alert` 里加任何决策逻辑

### finance_bot 的推送格式

- 日报消息：Qwen 草稿附加在 `daily_summary` 正文之前（`enrich_daily_summary`）
- 持仓报告：Qwen 草稿附加在持仓段之前（`enrich_portfolio_report`）
- 推送触发逻辑：`scheduler.py` 负责，不经 Qwen 判断

---

## 配置开关

所有 Qwen 富化功能默认关闭，按 agent 独立控制：

```yaml
# finance_bot/config.yaml
llm_enrichment:
  enabled: false          # 主开关
  daily_summary: false
  portfolio_report: false
  signal_alerts: false    # 永远 false，不可改

# web3_monitor/config.yaml
llm_enrichment:
  enabled: false          # 主开关
  signal_explain: false
  project_screen: false   # 未接线，留 Phase 3+
```

启用步骤：
1. 在 `.env` 设置 `QWEN_API_KEY`
2. `config.yaml` 改 `enabled: true` 及对应子开关
3. 重启 agent

---

## 禁止事项

- 不允许在 `format_signal_alert` 里调用任何 LLM
- 不允许 Qwen 控制推送频率 / 限流逻辑
- 不允许 Qwen 修改信号 dict 的评分字段
- 不允许跳过 OutputGate 直接将 Qwen 文本写入 Telegram
