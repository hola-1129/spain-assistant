# Codex Handoff Task

> 使用方法：CC 填写此模板 → 用户在本地运行 Codex → 粘贴 diff 给 CC → CC 审查 → 确认后合并。
> Codex 不自动执行，不直接 push，不修改 .env 或 secrets。

---

## 任务信息

| 字段 | 值 |
|------|---|
| 任务名 | _(填写)_ |
| TaskType | _(FEATURE_IMPL / BUG_FIX / TEST_CREATION / FORMATTER_IMPL / BOILERPLATE)_ |
| 创建时间 | _(填写)_ |
| 预计影响范围 | _(小 / 中 / 大)_ |

---

## 1. 目标

> 用 1-3 句话说明这个任务要达成什么。不要描述过程，只描述预期结果。

_(填写)_

---

## 2. 背景与约束

> 说明相关上下文：为什么要做、当前代码是什么样的、有哪些依赖。

_(填写)_

---

## 3. 允许修改的文件

```
agents/<agent_name>/path/to/file.py
agents/<agent_name>/tests/test_xxx.py
```

> 只列你明确授权的文件。Codex 不应修改此列表之外的文件。

---

## 4. 禁止修改的文件（任何情况）

```
.env
*.env.*
secrets.*
**/telegram_notify.py        # 除非本任务明确针对此文件
**/agent_orchestrator.py     # 除非本任务明确针对此文件
shared/llm/model_router.py   # CC-exclusive
shared/llm/gateway.py        # CC-exclusive
shared/llm/governance/       # CC-exclusive
```

---

## 5. 期望输出

> 描述完成后代码应具备的行为，包括：函数签名、返回类型、边界条件。

_(填写)_

**示例（如有）：**

```python
# 示例调用
result = new_function(input_data)
assert result == expected_output
```

---

## 6. 测试命令

> Codex 完成后必须运行以下命令，确保全部通过才能提交 diff。

```bash
# 运行相关测试
cd /Volumes/AI_DISK/ai_workspace
PYTHONPATH=. agents/<agent>/.venv/bin/pytest agents/<agent>/tests/test_xxx.py -v

# 如有集成测试
PYTHONPATH=. agents/<agent>/.venv/bin/pytest agents/<agent>/tests/ -v
```

---

## 7. 不可修改的行为（回归检查）

> 以下行为在任务完成后必须保持不变，Codex 和 CC 均需验证。

- [ ] Telegram 推送格式不变
- [ ] 交易信号评分逻辑不变
- [ ] 所有现有测试仍通过
- [ ] _(其他具体检查项)_

---

## 8. 回滚方式

```bash
# 查看 diff
git diff HEAD

# 还原单个文件
git checkout -- path/to/file.py

# 还原全部修改（谨慎）
git checkout -- .
```

---

## 9. CC 审查清单

> 用户粘贴 Codex diff 后，CC 按以下清单审查：

- [ ] diff 范围在「允许修改的文件」之内
- [ ] 没有动「禁止修改的文件」
- [ ] 没有引入 secrets、硬编码 key、print 敏感信息
- [ ] 没有修改信号评分逻辑
- [ ] 测试命令全部通过（用户确认）
- [ ] 代码逻辑符合任务目标
- [ ] 无明显安全漏洞（SQL 注入 / XSS / 命令注入等）

---

## 10. 状态

- [ ] CC 已填写任务
- [ ] 用户已运行 Codex
- [ ] 用户已粘贴 diff
- [ ] CC 已审查
- [ ] 已合并

---

## 附：任务示例

<details>
<summary>示例：为 web3_monitor 新增 DEX 数据格式化函数</summary>

**目标：** 在 `dexscreener_monitor.py` 中新增 `format_pool_summary(pool: dict) -> str` 函数，返回适合 Telegram 显示的单行摘要。

**允许修改：**
- `agents/web3_monitor/scripts/dexscreener_monitor.py`
- `agents/web3_monitor/scripts/tests/test_dexscreener.py`

**期望输出：**
```python
format_pool_summary({"asset": "BTC", "chain": "ethereum", "volume_1h_usd": 123456})
# → "BTC/ETH | Vol 1h: $123,456 | Chain: ethereum"
```

**测试命令：**
```bash
PYTHONPATH=. agents/web3_monitor/.venv/bin/pytest agents/web3_monitor/scripts/tests/test_dexscreener.py -v
```

</details>
