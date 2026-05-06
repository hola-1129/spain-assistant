# Workspace Workflow

## 启动流程

每次会话开始时，按顺序读取：
1. `/Volumes/AI_DISK/ai_workspace/CLAUDE.md` — 工作区总览
2. `/Volumes/AI_DISK/ai_workspace/README_WORKFLOW.md` — 本文件，工作流规范

## 任务上下文加载规则

### Finance 相关任务
先读取系统文档，再读取具体任务文件：
```
specs/finance/current_system_v1.md       ← 当前系统状态
tasks/finance/macro_upgrade_v1.md        ← 宏观升级任务
tasks/finance/signal_layer_v1.md         ← 信号层任务
tasks/finance/asia_scanner_v1.md         ← 亚洲市场扫描任务
tasks/finance/europe_scanner_v1.md       ← 欧洲市场扫描任务
```

### Web3 相关任务
```
specs/web3/                              ← Web3 策略参考资料
tasks/finance/tasks.md                   ← 当前任务列表
```

## 执行规范

### 标准流程（所有代码修改必须遵循）

```
Analyze First → Plan → Confirm → Execute
```

1. **Analyze**：分析当前系统，读取相关文件
2. **Plan**：给出修改方案 + 列出会影响的文件
3. **Confirm**：等待用户确认后再动手
4. **Execute**：增量执行，逐步验证

### 硬性约束

| 规则 | 说明 |
|------|------|
| 增量修改 | 每次只改必要的部分，不做大重构 |
| 不改无关文件 | 严格限制修改范围在任务涉及的文件内 |
| 不重构大模块 | 保持现有架构，在其上扩展 |
| Telegram 稳定 | 不修改 `alerts/telegram_alert.py` 的核心逻辑 |
| 禁止暴露敏感信息 | `.env` 内容不得出现在任何输出或文件中 |
| 先分析再动手 | 任何修改前必须先完成 Analyze + Plan 步骤 |

## 目录速查

```
ai_workspace/
├── agents/finance_bot/     PID 93232，运行中
├── agents/web3_monitor/    PID 96683，运行中
├── specs/finance/          个股研究、市场展望、系统文档
├── specs/web3/             DeFi 策略资料
├── tasks/finance/          Finance 任务追踪
├── tasks/personal/         个人任务
├── data/market_data/       SQLite DB + CSV
└── logs/                   finance_bot/ | web3_monitor/
```
