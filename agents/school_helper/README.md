# School Helper

把学校发来的西/英语 *Briefing Semanal* PDF 自动整理成中文家长周报 + 手机日历 + 静态网页。
不是常驻服务，是一次性 CLI：把 PDF 放到 `input/`，跑一次，`output/` 即生成静态站点。

## 输出

`output/` 目录直接发布到 GitHub Pages（详见 [deploy_to_github_pages.md](./deploy_to_github_pages.md)）。

| 文件 | 用途 |
|------|------|
| `index.html` | 家长访问入口（自包含、无 JS 依赖） |
| `school_events.ics` | 本周全部活动；点击可一键导入手机日历 |
| `events/NN-slug.ics` | 每个事项单独的 .ics，便于逐条添加 |
| `weekly_briefing_cn.md` | 中文家长版详细 markdown |
| `weekly_briefing_summary.txt` | 微信群转发版（短、emoji 多） |
| `extracted_links.json` | 主 PDF 抽到的所有链接和处理状态 |
| `processing_log.txt` | 处理日志（成功/失败/链接失效） |
| `archive/<YYYY-Www>/` | 上一周内容（每次运行自动归档） |
| `cache/` | 已下载的事项 PDF（**git-ignored，不发布**） |

## 安装

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # 填入 ANTHROPIC_API_KEY
```

## 运行

```bash
# 1. 把学校 Briefing PDF 放到 input/
cp ~/Downloads/Briefing_simple.pdf input/

# 2. 跑一次
.venv/bin/python main.py

# 调试用：跳过 LLM 调用
.venv/bin/python main.py --no-llm

# 指定输入或周标签
.venv/bin/python main.py --input input/Briefing_simple.pdf --week-label 2026-W19
```

## 配置

- **`config.yaml`**：模型、关注年级、日历时区、提醒规则、输出选项
- **`.env`**：`ANTHROPIC_API_KEY`（必填），`TELEGRAM_BOT_TOKEN/CHAT_ID`（可选）

家长重点关注的年级在 `family.priority_grades` 里改。默认是：
```
1º Primaria, 4º Primaria, Primaria, Infantil-Primaria, General
```

## 模块结构

```
school_helper/
├── main.py                 一次性 CLI 入口
├── config.py / config.yaml 配置
├── parsers/
│   ├── pdf_reader.py        主 PDF：文字 + 链接注释（PyMuPDF）
│   └── linked_pdf_fetcher.py 下载 + 解析子 PDF（带缓存、失败重试）
├── analyzer/
│   ├── llm_client.py        Anthropic Claude 封装
│   └── extractor.py         单事项结构化抽取 + 分类 + 时间解析
├── renderers/
│   ├── html_writer.py       index.html
│   ├── markdown_writer.py   weekly_briefing_cn.md
│   ├── summary_writer.py    weekly_briefing_summary.txt
│   ├── ics_writer.py        school_events.ics + events/*.ics
│   └── log_writer.py        extracted_links.json + processing_log.txt
└── utils/logger.py          沿用 web3_monitor 的日志方案
```

## 设计原则

- **不编造**：LLM 提取严格要求"原文未说明"留空，不猜日期/费用/报名要求
- **可复跑**：链接 PDF 缓存到 `output/cache/`，重跑只调 LLM、不重复下载
- **不暴露本地路径**：发布到 GitHub Pages 的所有文件不含 `/Volumes/...` 路径
- **archive 自动归档**：检测到上周 `extracted_links.json` 的 `week_iso` 与本次不同，先归档再覆盖

## 限制 / 已知坑

- 链接如果指向网页（非 PDF 直链），会标记 `non_pdf` 并提示需手动下载
- 如果 PDF 没有可点击注释链接，主 PDF 解析会拿不到 URL（学校如果改版需要重做 `pdf_reader`）
- 日期/时间用西语正则识别，最终依赖 LLM 把字段抽成 `YYYY-MM-DD / HH:MM`
