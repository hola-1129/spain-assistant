# MCP 工具治理规范 V1

> MCP（Model Context Protocol）是 agent 调用外部工具的接口。
> V1 阶段，MCP 工具调用权限归 CC 独占，Qwen 和 Codex 不可直接调用。

---

## 工具分类

### 类型 A：只读查询（Read-Only）

| 工具 | 功能 | 调用权限 |
|------|------|---------|
| `scan_dex_anomalies` | 读取 DEX 数据 | Agent 代码（自动） |
| `scan_market_movers` | 读取市场数据 | Agent 代码（自动） |
| `scan_new_pools` | 读取新流动性池 | Agent 代码（自动） |
| `scan_prediction_markets` | 读取 Polymarket | Agent 代码（自动） |
| `get_macro_snapshot` | 读取宏观数据 | Agent 代码（自动） |

### 类型 B：状态写入（State-Changing）

| 工具 | 功能 | 调用权限 |
|------|------|---------|
| `send_telegram_alert` | 推送 Telegram 消息 | Agent 代码（经规则 + OutputGate） |
| `persist_signal` | 写入信号数据库 | Agent 代码（自动） |

### 类型 C：高权限操作（CC 独占）

| 工具 | 功能 | 调用权限 |
|------|------|---------|
| 文件修改 / 创建 | 修改 agent 代码 | CC 仅在用户确认后 |
| git 操作 | commit / push | CC 仅在用户确认后 |
| .env 修改 | 修改密钥 | 禁止（任何模型） |
| 进程管理 | 启动 / 停止 agent | CC 仅在用户确认后 |
| MCP server 配置 | 修改工具定义 | CC 仅在 CC 会话中 |

---

## 访问控制矩阵

| 工具类型 | Claude Code | Qwen | Codex | Agent 代码 |
|---------|------------|------|-------|-----------|
| A 只读查询 | ✅ | ❌ | ❌ | ✅（自动） |
| B 状态写入 | ✅（审查后）| ❌ | ❌ | ✅（经验证）|
| C 高权限 | ✅（用户确认）| ❌ | ❌ | ❌ |

**Qwen 和 Codex 均不可直接调用任何 MCP 工具。**

---

## Qwen 与 MCP 的关系

Qwen 只处理文本，不调用工具：

```
MCP 工具返回数据
    ↓
Agent 代码处理 / 评分
    ↓  [可选：数据脱敏后]
Qwen 生成文字解释
    ↓
OutputGate
    ↓
附加到推送消息
```

Qwen 不知道 MCP 工具的存在，也不能请求调用任何工具。

---

## V1 MCP 现状

web3_monitor 的 MCP 工具位于：

```
agents/web3_monitor/scripts/mcp_tools/
├── market_tools.py     类型 A（只读）
├── notify_tools.py     类型 B（Telegram 推送）
└── signal_tools.py     类型 B（信号持久化）
```

当前所有工具由 `Web3MonitorAgent` 直接调用，无 LLM 参与路由。

---

## Phase 2 评估项（当前不实施）

| 项目 | 描述 | 风险 |
|------|------|------|
| CC 通过 MCP 调用只读工具 | CC 辅助数据查询 | 低 |
| 受限 Qwen MCP 代理 | Qwen 请求 CC 调用工具 | 中（需严格授权链）|
| Codex MCP 工具生成 | Codex 通过 handoff 新增工具 | 低（需 CC 审查）|
| 自动 MCP 工具注册 | 工具自描述注册 | 高（推迟）|

---

## MCP Server 设计约束（未来）

当设计 MCP server 时，CC 必须：

1. 明确每个工具的权限等级（A / B / C）
2. 在工具 schema 中标注 `requires_confirmation: true/false`
3. 拒绝将类型 C 工具暴露给非 CC 模型
4. 每个工具调用写入 `audit_log`

MCP server 设计文档由 CC 起草，不委派给 Qwen 或 Codex。
