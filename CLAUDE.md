# AI Workspace

个人 AI 工作区，统一管理所有 agent、任务、资料和日志。

## 目录约定

```
ai_workspace/
├── agents/          # 各 agent 的代码和配置
├── data/            # agent 产生或消费的数据（DB、CSV）
├── logs/            # 运行日志，按 agent 分子目录
├── specs/           # 参考资料、需求文档，按领域分类
├── tasks/           # 任务追踪（Markdown），按领域分类
├── shared/          # 跨 agent 共用资源（prompts、utils、templates）
└── sandbox/         # 临时实验，随时可清理
```

## 当前 Agents

| Agent | 路径 | 状态 | 启动命令 |
|-------|------|------|---------|
| finance_bot | `agents/finance_bot/` | 运行中 | `cd agents/finance_bot && nohup .venv/bin/python main.py > ../../logs/finance_bot/stdout.log 2>&1 &` |
| travel_assistant | `agents/travel_assistant/` | 待建 | — |
| school_helper | `agents/school_helper/` | 可用（一次性 CLI） | `cd agents/school_helper && .venv/bin/python main.py` |
| web3_monitor | `agents/web3_monitor/` | 已构建，待配置 .env 后启动 | `cd agents/web3_monitor && nohup .venv/bin/python main.py > ../../logs/web3_monitor/stdout.log 2>&1 &` |

## 参考资料索引

| 领域 | 路径 | 内容 |
|------|------|------|
| 金融研究 | `specs/finance/research/` | 市场展望、投资方法论 PDF |
| 个股资料 | `specs/finance/stocks/` | hims / oscar / pl 财报 |
| Web3 | `specs/web3/` | DeFi 研究报告、任务追踪 CSV |

## 开发约定

- 每个 agent 在自己目录内维护 `.venv/`，不共用
- 新 agent 同步在 `tasks/`、`specs/` 下建对应领域子目录
- 日志写入 `logs/<agent_name>/`，保留 30 天
- 敏感信息（API key、token）放 `.env`，不提交
