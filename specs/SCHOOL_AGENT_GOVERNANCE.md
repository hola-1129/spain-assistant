# School Agent 治理规范 V1

> 学校 Agent 处理家庭敏感数据。Qwen 接触范围受严格限制。

---

## 数据分类

| 类别 | 示例 | 允许传给 Qwen |
|------|------|------------|
| 公开内容 | 学校通知标题、活动日期、课程名称 | ✅ |
| 半公开内容 | 年级名称、作业要求、活动描述 | ✅（不含姓名） |
| 家庭私有数据 | 孩子姓名、家长联系方式、家庭地址 | ❌ |
| 系统凭证 | IMAP 密码、`ANTHROPIC_API_KEY`、日历 URL | ❌ |

---

## 当前架构（V1）

```
school_helper/
├── analyzer/
│   ├── llm_client.py       ← 薄包装层，默认 provider=anthropic
│   ├── extractor.py        ← 调用 llm_client，结构化提取
│   └── summarizer.py       ← 调用 llm_client，生成摘要
├── fetchers/               ← Email / Web / PDF 获取，无 LLM
├── parsers/                ← OCR / ICS / PDF 解析，无 LLM
└── main.py                 ← CLI 入口，CC 调度
```

**当前 LLM provider：Anthropic（`claude-sonnet-4-6`），直连。**

Qwen 的角色：`config.yaml` 已添加 `provider: qwen` 选项，但**当前未启用**。
如需启用，设置 `llm.provider: qwen` 并配置 `QWEN_API_KEY`。

---

## Qwen 可用范围（仅当 provider=qwen 时生效）

### 允许

| 任务 | 说明 |
|------|------|
| 通知摘要 | 将通知正文压缩为 2-3 句摘要 |
| 语言翻译 | ES → ZH / EN 互译 |
| 日程摘要 | 将多条日程事件合并为一段描述 |
| 内容分类 | 将通知分为「重要 / 一般 / 可忽略」 |

### 禁止

| 禁止事项 | 原因 |
|---------|------|
| 传入孩子姓名 | 家庭隐私 |
| 传入学校名称（完整正式名） | 结合日期可定位 |
| 传入家庭联系方式 | 家庭隐私 |
| 传入日历 URL / IMAP 凭证 | 系统凭证 |
| 要求 Qwen 判断「这件事重要吗」| 主观判断应由规则或 CC 负责 |

---

## Prompt 脱敏规范

传给 Qwen 的内容必须经过以下处理：

```python
# 传入前替换孩子姓名为占位符
text = text.replace(child_name, "[STUDENT]")

# 不传入完整学校名，只传年级
# 错误: "Colegio San Agustín, 4º Primaria"
# 正确: "4º Primaria"
```

---

## Codex 在 School Agent 中的角色（V1 handoff only）

Codex 可以承接的任务（通过 handoff）：

| 任务 | 说明 |
|------|------|
| 改进 PDF/OCR 解析器 | `parsers/pdf_parser.py` |
| 改进 ICS 日历渲染 | `parsers/ics_parser.py` |
| 改进 Telegram 格式化 | `formatter/telegram.py` |
| 补充单元测试 | `tests/` |

Codex 禁止触碰：

```
school_helper/analyzer/llm_client.py   ← CC-managed
school_helper/.env
```

---

## 隐私升级路径（Phase 2 评估）

| 项目 | 当前 | Phase 2 候选 |
|------|------|------------|
| 孩子姓名 | 不传 Qwen | 本地 NER 脱敏后可传 |
| 学校名称 | 不传 Qwen | 哈希映射后可传 |
| 日历数据 | Anthropic 处理 | 评估 Qwen 成本收益 |
