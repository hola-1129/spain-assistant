# Northstar SignalOS — 模型治理规范 V1

> 本文档由 Claude Code (CC) 维护。修改需在 CC 会话中完成并经用户确认。
> 详细委派规则见 `AGENT_DELEGATION_RULES.md`。

---

## 三层角色定义

| 角色 | 当前接入方式 | 职责范围 | 硬性限制 |
|------|------------|---------|---------|
| **Claude Code (CC)** | CLI 直接 | 架构决策、任务分解、治理、代码审查、Codex/Qwen 调度 | 不自动执行 Codex 任务；不绕过 OutputGate |
| **Qwen** | DashScope 直连（`QwenClient`） | 摘要、翻译、Telegram 草稿、信号解释、分类、日志压缩、学校通知 | 不做最终交易决策；不接收敏感数据（见下） |
| **Codex** | 人工 handoff（V1） | 功能实现、测试、格式化、样板代码 | 不自动执行；输出必须经 CC 审查后合并 |

> Phase 2 评估：provider 抽象层（OpenRouter / fallback chain）。当前阶段不需要。

---

## V1 硬约束

1. **Qwen 使用 DashScope 直连**（`QWEN_API_KEY`）。OpenRouter 不在 V1 范围内。
2. **Codex V1 为纯手工 handoff**，不存在自动 API 调用路径。
3. **所有交易信号的最终判断为 `RULE` tier**，不经任何 LLM。
4. **Qwen 禁止接收：**
   - API key / token / Bearer / secret
   - 钱包地址（`0x…`）
   - 持仓美元金额
   - 个人身份信息（姓名、孩子、学校、联系方式）
5. **Codex 输出必须经 CC diff 审查后方可合并**，禁止直接 push。
6. **不修改 `.env`、secrets、Telegram token、wallet 相关文件**（任何模型均不可）。
7. **OutputGate 不可被任何模型绕过**，所有 Qwen 输出在到达 Telegram/报告前必须经过验证。

---

## 任务路由

```
任务进来
  │
  ├─ CC 专属（架构 / 安全 / 治理 / 信号最终裁决）
  │     └─→ CC 直接处理
  │
  ├─ 低风险文本分析（摘要 / 翻译 / 草稿 / 分类）
  │     └─→ CC 调用 summarizer / explainer
  │              → QwenClient (DashScope)
  │              → OutputGate 验证
  │              → DraftOutput → ValidatedOutput
  │
  ├─ 工程执行（功能 / 测试 / 格式化）
  │     └─→ CC 生成 Codex Handoff Task（见 CODEX_HANDOFF_TEMPLATE.md）
  │              → 用户手动运行 Codex
  │              → 用户粘贴 diff → CC 审查 → 确认后合并
  │
  └─ 规则计算（信号评分 / 告警限流 / 数据拉取）
        └─→ 纯代码，不调用任何 LLM
```

---

## Qwen 许可任务清单

| TaskType | 用途 |
|---------|------|
| `SUMMARIZE_BULK` | 新闻列表 / 数据批量摘要 |
| `TRANSLATE` | ZH / EN / ES 互译 |
| `TELEGRAM_DRAFT` | 日报 / 周报消息草稿 |
| `CLASSIFY_LOW_RISK` | 情绪分类、主题标签 |
| `LOG_COMPRESS` | 错误日志摘要 |
| `SIGNAL_EXPLAIN` | DEX+Polymarket 信号纯文字解释（无决策） |
| `SCHOOL_EXTRACT` | 学校通知 PDF/OCR 内容摘要 |
| `REPORT_DRAFT` | 日报 / 组合报告的自然语言段落 |

---

## 相关文档索引

| 文档 | 内容 |
|------|------|
| `AGENT_DELEGATION_RULES.md` | CC 如何调度 Qwen 和 Codex 的详细协议 |
| `CODEX_HANDOFF_TEMPLATE.md` | Codex 任务标准模板 |
| `TELEGRAM_PIPELINE_GOVERNANCE.md` | Telegram 输出管线治理 |
| `SCHOOL_AGENT_GOVERNANCE.md` | 学校 Agent 数据隐私与 Qwen 使用规范 |
| `MCP_GOVERNANCE.md` | MCP 工具访问控制规则 |

---

## Tool Permission Layer (V2)

全面的工具权限管理层，防止 Qwen 等低成本模型产生不可控的工具调用和费用爆炸。

### 架构层次

```
Planner Layer    → Claude (CC)       — 推理、规划、分解、决策
Worker Layer     → Qwen              — 确定性执行（single-shot）
Executor Layer   → 独立工具执行
Tool Governance  → 权限 + 限速 + 预算保护
```

### 核心原则

- **Default-deny**: 所有工具默认禁用，只有白名单中的工具才能执行
- **Qwen = 零工具**: `max_iterations=1`，`allowed_tools=[]`，单次执行
- **Intersection rule**: 工具必须同时在 model 白名单 AND agent 白名单中才允许

### 新增文件

| 文件 | 作用 |
|------|------|
| `shared/configs/tool_permissions.yaml` | 权限配置（CC 专属，不得自动修改） |
| `shared/llm/governance/tool_permissions.py` | 权限检查 + 预算跟踪 |
| `shared/llm/governance/cost_tracker.py` | Token 计费 + 每日聚合 |
| `shared/reporting/cost_report.py` | 每日成本报告生成器 |

### Observability 字段（audit.jsonl + cost_log.jsonl）

每条 LLM 调用记录包含：`agent`, `model_id`, `task_type`, `input_tokens`, `output_tokens`,
`latency_ms`, `tool_calls`, `cost_usd`, `retries`, `gate_passed`

### 生成每日成本报告

```bash
python -m shared.reporting.cost_report              # 今天
python -m shared.reporting.cost_report 2026-05-18   # 指定日期
python -m shared.reporting.cost_report --all        # 全部日期
```

### 在 Agent 代码中使用 Tool Permission

```python
from shared.llm.governance import ToolPermissionChecker, AgentBudget

checker = ToolPermissionChecker.load()
budget  = AgentBudget(agent="finance_bot", model_tier="cc", checker=checker)

budget.tick_iteration()            # 每次 LLM 调用前计数
output = gateway.complete(task_type, system, user, agent_name="finance_bot")

budget.use_tool("stock_api")       # 外部工具调用前检查权限
result = stock_api.fetch(symbol)
```

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V2.0 | 2026-05-18 | Tool Permission Layer + Cost Tracker + Daily Cost Report |
| V1.1 | 2026-05-11 | 明确 provider 为 DashScope 直连；移除 OpenRouter 引用；补充相关文档索引 |
| V1.0 | 2026-05-11 | 初版，确立 CC/Qwen/Codex 三层分工 |
