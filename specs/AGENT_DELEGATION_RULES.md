# Agent 委派规则 V1

> Claude Code (CC) 是唯一的调度者。Qwen 和 Codex 不自我调度，不互相调用。

---

## CC → Qwen 委派协议

### 何时委派给 Qwen

满足以下**全部**条件才委派：

1. 任务类型属于 `MODEL_GOVERNANCE.md` Qwen 许可清单
2. 输入数据不包含任何禁止字段（API key、钱包、持仓金额、姓名）
3. 输出是草稿性质，不直接作为最终决策或 Telegram 正文
4. 任务可容忍失败（Qwen 故障时系统使用原始消息降级）

### 委派流程

```
CC 确认任务类型 ∈ Qwen 许可清单
    ↓
CC 构造 system_prompt + user_prompt
    ↓  [禁止在 prompt 里包含敏感数据]
QwenClient.complete(system, user)   ← DashScope 直连
    ↓
DraftOutput(text, source="qwen", validated=False)
    ↓
OutputGate.validate(draft, task_type)
    ↓ 通过              ↓ 拒绝
ValidatedOutput     返回 None / 原始消息
    ↓
允许进入 Telegram / 报告
```

### 失败降级规则

- Qwen 超时 / 报错 → 返回 `None`，调用方使用原始消息
- OutputGate 拒绝 → 同上
- **任何情况下都不阻断消息推送**

### Qwen Prompt 构造规范

```
system_prompt 必须包含：
  - 明确的任务说明（摘要 / 翻译 / 解释）
  - 输出格式约束（长度、语言、不含敏感词）
  - "你只能分析，不能给出交易建议"（涉及金融时）

user_prompt 只允许传入：
  ✅ 百分比变化（+3.2%）
  ✅ 资产代号（BTC, ETH）
  ✅ 事件摘要文字
  ✅ 公开新闻标题
  ❌ 美元金额
  ❌ 持仓数量
  ❌ 个人姓名
  ❌ API key / token
  ❌ 钱包地址
```

---

## CC → Codex 委派协议

### 何时委派给 Codex

满足以下条件时创建 Codex Handoff Task：

1. 任务属于纯工程执行（功能实现 / 测试 / 格式化）
2. 任务范围明确，目标文件已知，不涉及治理文件
3. CC 已理解需求，可写出完整的任务说明
4. 任务不涉及 `.env`、secrets、trading signal 逻辑、CC-exclusive 文件

### Codex 任务生命周期

```
阶段 1：CC 创建任务
    CC 填写 CODEX_HANDOFF_TEMPLATE.md：
    - 目标 / 约束 / 允许文件 / 禁止文件 / 测试命令 / 回滚方式
    - 输出 Markdown 任务卡

阶段 2：用户执行
    用户在本地运行 Codex（VS Code / CLI）
    Codex 按任务卡修改代码
    用户运行测试命令确认通过

阶段 3：CC 审查
    用户将 git diff 粘贴给 CC
    CC 按审查清单逐项检查（见模板第 9 节）
    CC 给出明确结论：APPROVED / REJECTED / NEEDS_REVISION

阶段 4：合并
    CC APPROVED 后用户执行 git add / commit / merge
    CC REJECTED 时用户 git checkout -- 还原，重新讨论
```

### Codex 审查清单（CC 必须逐项确认）

- [ ] diff 范围在「允许修改文件」之内
- [ ] 未动任何「禁止修改文件」
- [ ] 未引入硬编码 secrets / print 敏感信息
- [ ] 未修改交易信号评分逻辑
- [ ] 未修改 Telegram 推送逻辑（除非任务明确针对此）
- [ ] 所有现有测试仍通过（用户确认）
- [ ] 新代码逻辑正确，无明显安全漏洞

### CC-Exclusive 文件（Codex 永远不可修改）

```
shared/llm/model_router.py
shared/llm/gateway.py
shared/llm/governance/
specs/MODEL_GOVERNANCE.md
specs/AGENT_DELEGATION_RULES.md
specs/MCP_GOVERNANCE.md
任意 .env / secrets 文件
```

---

## 委派决策矩阵

| 任务类型 | 委派给 | 自动执行 | 人工确认 |
|---------|-------|---------|---------|
| 架构设计 / 治理 / 安全审查 | CC 直接处理 | — | — |
| 信号最终判断 | RULE tier（纯代码） | ✅ | — |
| 文本摘要 / 翻译 / 草稿 | Qwen | ✅ | OutputGate 验证 |
| 功能实现 / 测试 / 格式化 | Codex handoff | ❌ | CC 审查 diff |
| .env / secrets 操作 | 禁止 | ❌ | ❌ |

---

## 升级路径（Phase 2 评估，不在当前）

| 项目 | 当前 | Phase 2 候选 |
|------|------|------------|
| Qwen provider | DashScope 直连 | OpenRouter 抽象层 |
| Codex 执行 | 手工 handoff | 半自动 API 调用 |
| 多模型 fallback | 无 | Qwen → CC 上行链 |
| MCP 工具调用 | CC 独占 | 受限委派 |
