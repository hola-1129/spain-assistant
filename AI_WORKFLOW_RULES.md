# AI_WORKFLOW_RULES

> Multi-LLM 协同工作流与工程规范。每次会话开始由 Claude 按 `CLAUDE.md` 启动列表加载。

## 目标

建立多 AI 协同工作流：

- **Claude** = 高级架构与 reasoning
- **Codex** = 后台执行与长任务
- **Qwen** = 低成本执行层

总目标：

- 降低 Claude token 消耗
- 提高 Agent 开发效率
- 保持系统结构清晰
- 为未来 MCP / 多 Agent 协作做准备

---

## 1. Claude 的职责（高价值任务）

Claude 主要作为：

- AI 系统架构师
- Principal Engineer
- Workflow Orchestrator
- MCP / Agent Designer
- Final Reviewer

Claude 负责：

1. 系统架构设计
2. MCP / Tool 设计
3. Agent orchestration
4. 多文件 refactor
5. Debug 复杂问题
6. 长上下文 reasoning
7. 最终代码 review
8. Workflow 规划
9. Runtime 设计
10. Security / Risk Review

Claude **不应**浪费 context 在：

- README
- JSON schema
- config boilerplate
- Telegram formatting
- 重复 CRUD
- 小型 wrapper
- 文档整理
- 简单 API glue code

对于低价值重复任务，Claude 应：

1. 标记 **"建议转交 Qwen/Codex"**
2. 自动生成适合低成本模型执行的 Prompt
3. 尽量减少 Claude context 消耗

Claude 应优先：思考 / 设计 / 审核 / orchestration —— 而不是低价值重复编码。

---

## 2. Codex / GPT 的职责（Runtime Worker）

Codex 主要作为：

- Runtime Worker
- Background Executor
- Batch Processing Agent
- Long-running Task Worker

适合处理：

1. README
2. JSON schema
3. config generation
4. Telegram formatting
5. boilerplate
6. CRUD
7. wrapper code
8. MCP tool templates
9. data cleanup
10. repetitive code generation
11. batch modifications
12. lint / formatting
13. auto testing
14. long-running tasks

避免负责：

- 系统架构
- MCP 核心设计
- 高级 reasoning
- 多 Agent orchestration
- 长上下文系统分析
- 核心 workflow 决策

复杂任务：返回 Claude Review，或请求 Claude 做架构决策。

---

## 3. Qwen 的职责（低成本执行层）

Qwen 主要作为：

- Low-cost Execution Layer
- Cheap Coding Worker
- Structured Output Generator

优先用于：

- README / JSON / schema / config
- Telegram formatting
- MCP boilerplate
- OCR 后处理
- 数据整理 / 配置生成
- 小型工具函数 / 重复性代码

避免：

- 高级架构
- 长上下文 reasoning
- 复杂 debug
- 多 Agent 推理

---

## 4. Token 与成本优化原则

- 不要使用 Claude 处理低价值重复工作
- Claude token 应优先保留给：reasoning / architecture / orchestration / review
- 低复杂度任务：优先 Qwen 或 Codex
- 复杂任务：使用 Claude

---

## 5. 安全规则（非常重要）

**禁止：**

- API key 写入代码
- token 上传 GitHub
- secrets commit 到 repo

**必须：**

- 使用 `.env`
- 使用 `.gitignore`
- secrets 永不进入 public repo

`.gitignore` 至少包含：

```
.env
.env.*
logs/
*.log
processing_log.txt
secrets/
*.pem
*.key
```

---

## 6. 日志规则

日志中**禁止**记录：

- API key
- Authorization
- Bearer token
- webhook
- cookie
- secrets

日志必须：

- URL 自动脱敏
- 长 query 自动截断
- token 自动 mask

`logs/` 默认 git ignore。

---

## 7. Repo 规则

当前项目默认视为 **"家庭私有 AI Agent 项目"**。

默认：

- Private repo
- 不公开学校数据
- 不公开儿童信息
- 不公开 Google Drive 私有链接

---

## 8. MCP / Future Compatibility

所有核心功能必须模块化：

- Tool-based design
- JSON structured I/O
- Low coupling
- 可独立测试
- 可未来封装为 MCP tools

避免：

- 巨型 `main.py`
- 强耦合结构
- 硬编码 workflow

---

## 9. 推荐目录结构

```
project/
├── agents/
├── tools/
├── workflows/
├── data/
├── logs/
├── output/
├── config/
└── docs/
```

---

## 10. AI Routing 原则

| 角色 | 负责 |
|------|------|
| **Claude** | 思考 / 架构 / orchestration |
| **Qwen**   | 廉价执行 / structured output |
| **Codex**  | 后台自动执行 / 长任务 |

目标：建立 Multi-LLM Workflow + AI Orchestration + Future MCP-ready System。
