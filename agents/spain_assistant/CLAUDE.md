# Spain Assistant — Claude 工作上下文

## 项目定位

**Spain Assistant** 是面向"在西班牙生活的华人家庭"的长期生活助手系统。

核心不是"翻译新闻"，而是：
> 把马德里本地公共信息，转化成华人家庭真正看得懂、用得上的生活情报。

---

## 当前模块状态（V1）

| 模块 | 状态 | 新闻源 | 抓取时间 |
|------|------|--------|---------|
| madrid_news | ✅ 运行中 | `https://diario.madrid.es/blog/notas-de-prensa/` | 09:00 / 13:30 / 18:30 |
| lamoncloa_news | ✅ 运行中 | `https://www.lamoncloa.gob.es/serviciosdeprensa/notasprensa/` | 09:00 / 13:30 / 18:30 |
| esmadrid_agenda | ✅ 运行中 | `https://www.esmadrid.com/agenda-madrid` | 09:00 / 13:30 / 18:30 |

---

## 核心数据流

```
fetch_article_list()
  ↓ 分页抓取（最多 max_pages 页，遇到非今日文章停止翻页）
deduper.filter_new()
  ↓ 按 md5(title + date) 去重，跳过已处理文章
enrich_articles() → analyze_article() → translate_article() → tag_area()
  ↓ 正文抓取 + LLM 分析 + LLM 翻译
save_processed(module, articles, run_id)
  ↓ 写入 data/processed/<module>/YYYYMMDD_HHMMSS.json
_load_today_processed(module)
  ↓ 加载当日所有批次文件，按 hash_id 合并去重（多次运行不覆盖）
render_all() → public/ → GitHub Pages + Telegram 通知
```

## 关键设计决策

### 日期解析（fetcher.py）
diario.madrid.es 的日期在 `.post-author strong` 里，格式为 `DD/MM/YYYY`。
解析优先级：`DD/MM/YYYY` → ISO `YYYY-MM-DD` → 西班牙文格式。
**日期为空时默认 `is_today=True`（保守策略，宁可多展示）。**

### 多批次合并（main.py）
`_load_today_processed()` 按当日前缀（`YYYYMMDD_*.json`）加载所有批次，
按 `hash_id` 合并，后批次覆盖前批次同一篇文章（用于内容更新）。
若当日无数据，回退到最新文件（保证 lamoncloa/esmadrid 跨日也能渲染）。

### 去重策略（deduper.py）
hash = `md5(title.strip() + date.strip())`，写入 `data/state.json`。
同一标题+日期只处理一次，跨日同标题视为新文章。

### 重点关注生命周期（highlight_manager.py）
- S/A 级文章标记 `is_highlight=True`，写入 `data/active_highlights.json`
- 有活动日期：持续到 `event.end_date`
- 无活动日期：默认 3 天 TTL
- 每次运行自动清理过期条目

---

## 关键文件路径

```
data/
  state.json                    # 全局去重状态（seen_hashes）
  active_highlights.json        # 跨日有效重点关注
  raw/<module>/YYYYMMDD_HHMMSS.json      # 原始抓取数据（保留 180 天）
  processed/<module>/YYYYMMDD_HHMMSS.json  # 处理后数据（永久保留）

public/                         # GitHub Pages 输出
  index.html                    # 首页
  archive/YYYY-MM-DD.html       # 每日归档页
  articles/<hash_id>.html       # 单篇详情页
  data/latest.json              # 最新批次 JSON
  data/archive.json             # 历史索引
  ics/<hash_id>.ics             # 活动日历文件
```

---

## 服务管理

```bash
# 状态查看
launchctl list | grep spain

# 重启
launchctl stop com.leslie.spain_assistant
launchctl start com.leslie.spain_assistant

# 手动运行（调试）
cd /Volumes/AI_DISK/ai_workspace/agents/spain_assistant
python src/main.py run madrid_news      # 单次运行指定模块
python src/main.py run-all             # 运行所有模块
python src/main.py render              # 仅重新渲染（不抓取）
python src/main.py publish             # 仅推送 GitHub Pages

# 日志
tail -f logs/spain_assistant.log
```

---

## LLM 配置

| 用途 | 模型 |
|------|------|
| 轻量提取 / 翻译 | `qwen-plus` |
| 重要性判断 / 家庭建议 | `gpt-4.1` |

API key 通过 `.env` 注入：`LLM_API_KEY` / `LLM_BASE_URL`

---

## 架构原则

1. 新增模块：只在 `src/modules/` 下新建目录 + 在 `src/main.py` 注册
2. 不要修改 `src/core/` 的接口，只扩展
3. 抓取失败、LLM 失败：记录日志，跳过单条，不中断整体
4. GitHub 推送失败：保留本地 `public/`，不影响主流程
5. 不编造信息：LLM prompt 已强制要求，不确定写"原文未说明"
6. Telegram 只做通知入口，不推送完整长文
7. 敏感信息（token、key）只走 `.env`，不硬编码，不提交

## 扩展模块注册流程

1. 创建 `src/modules/<name>/module.py`，实现 `run() -> dict`
2. 在 `config.yaml` 的 `modules:` 下添加配置
3. 在 `src/main.py::_register_modules()` 中注册
4. 更新 `src/modules/future_modules/README.md`
