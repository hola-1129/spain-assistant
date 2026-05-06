# School Helper — Agent 定义

把学校每周下发的西/英语 *Briefing Semanal* PDF 翻成中文家长版周报，输出可发布到 GitHub Pages 的静态站点 + 手机日历。

## 流水线

| 步骤 | 模块 | 输入 → 输出 |
|------|------|-------------|
| 1. 解析主 PDF | `parsers/pdf_reader.py` | Briefing PDF → 周次/日期 + (标题, 阶段, URL) 列表 |
| 2. 下载链接 PDF | `parsers/linked_pdf_fetcher.py` | URL → 缓存到 `output/cache/` 并抽取文本 |
| 3. 结构化抽取 | `analyzer/extractor.py` + `analyzer/llm_client.py` | 单 PDF 文本 → 结构化字段（日期/地点/费用/家长行动…） |
| 4. 渲染 | `renderers/*` | 字段集合 → `index.html` / `*.ics` / `*.md` / `*.txt` / `*.json` / `processing_log.txt` |

## 路径

| 资源 | 路径 |
|------|------|
| 代码 | `/Volumes/AI_DISK/ai_workspace/agents/school_helper/` |
| 输入 PDF | `input/` |
| 输出（GitHub Pages 源） | `output/` |
| 缓存（不发布） | `output/cache/` |
| 归档 | `output/archive/<YYYY-Www>/` |
| 日志 | `/Volumes/AI_DISK/ai_workspace/logs/school_helper/` |
| 配置 | `config.yaml` / `.env` |

## 生命周期

```bash
# 安装（首次）
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env  # 填 ANTHROPIC_API_KEY

# 每周运行（手动）
cp ~/Downloads/Briefing_*.pdf input/
.venv/bin/python main.py

# 查看日志
tail -f /Volumes/AI_DISK/ai_workspace/logs/school_helper/main.log
```

## LLM 调用

| 项 | 值 |
|-----|------|
| 默认 model | `claude-sonnet-4-6` |
| temperature | 0（要求事实性提取） |
| max_tokens | 4096 |
| 重试 | 指数退避，最多 3 次 |
| 输入 | 单条事项 PDF 全文（>12K 字符首尾截断） |
| 输出 | 严格 JSON（schema 见 `analyzer/extractor.py`） |

## 数据来源

| 数据 | 来源 |
|------|------|
| 主 PDF | 学校邮件附件，手动放到 `input/` |
| 子 PDF | 主 PDF 链接注释（点击会跳转的 URL） |

## 扩展指南

- **新增分类桶**：改 `analyzer/extractor.py` 的 `CATEGORY_*` 常量 + `classify_audience()`
- **改高亮年级**：改 `config.yaml` 的 `family.priority_grades`
- **改日历时区/提醒**：改 `config.yaml` 的 `calendar`
- **换 model**：改 `config.yaml` 的 `llm.model`
- **改 HTML 样式**：编辑 `renderers/html_writer.py` 顶部的 `_CSS`
- **每周自动跑**：将来需要 cron 化时，可加 `scheduler.py`（参考 `web3_monitor/scheduler.py`）

## 不做的事

- 不编造原文未提及的字段（LLM prompt 中明确禁止）
- 不把本地路径写进发布产物（HTML/ICS/markdown/json 都用相对路径或文件名）
- 不发邮件（家长一律通过 GitHub Pages URL 自取）
