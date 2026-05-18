# 🇪🇸 Spain Assistant — 西班牙生活助手

面向**在西班牙生活的华人家庭**的长期生活助手系统。

核心目标：
> 把马德里本地公共信息，转化成华人家庭真正看得懂、用得上的生活情报。

---

## 当前 V1：Madrid Local News Assistant

每天自动抓取马德里市政府新闻，经过分类、重要性评级、中文解读后，生成美观的静态网页并发布到 GitHub Pages，同时通过 Telegram 推送摘要通知。

### 功能概览

| 功能 | 说明 |
|------|------|
| 自动抓取 | 每天 08:30 / 13:30 / 18:30 抓取 [diario.madrid.es](https://diario.madrid.es/blog/notas-de-prensa/) |
| 智能去重 | Title + Date hash，只处理新增新闻 |
| 重要性评级 | S/A/B/C 四级，S=必须关注，C=仅归档 |
| 标签分类 | 亲子、学校、交通、文化等 16 类标签 |
| 中文解读 | 本地视角解读 + 华人家庭专属建议 |
| 静态网页 | 卡片式布局，支持筛选，手机友好 |
| GitHub Pages | 自动发布，保留历史归档 |
| Telegram 通知 | 仅推送摘要和链接，不推送完整长文 |

### 未来扩展模块（规划中）

- 学校通知解读
- 马德里亲子活动推荐
- 节日活动提醒
- 医疗/公共服务提醒
- 西语生活短句助手
- 区域生活情报（Madrid Norte / SSReyes）
- 快递/餐厅/物业沟通场景
- 日历 ICS 事件生成

---

## 安装

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/spain_assistant
pip install -r requirements.txt
```

---

## 配置 .env

```bash
cp .env.example .env
```

编辑 `.env`，填写以下内容：

```env
# LLM（OpenAI 或 Qwen，兼容 OpenAI 格式）
LLM_API_KEY=your_api_key
LLM_BASE_URL=                    # Qwen 填写 https://dashscope.aliyuncs.com/compatible-mode/v1

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# GitHub Pages（可选）
GITHUB_TOKEN=your_github_token
```

编辑 `config.yaml`，设置 GitHub 仓库：

```yaml
github:
  enabled: true
  repo: "your-username/spain-assistant"
```

---

## 运行

### 单次手动运行

```bash
python src/main.py run madrid_news
```

流程：抓取 → 去重 → 提取正文 → 分析分类 → 中文解读 → 渲染网页 → Telegram 通知 → GitHub 发布

### 运行所有模块

```bash
python src/main.py run-all
```

### 仅重新渲染（不抓取）

```bash
python src/main.py render
```

### 发布到 GitHub Pages

```bash
python src/main.py publish
```

### 测试 Telegram 通知

```bash
python src/main.py notify-test
```

### 启动定时调度（常驻进程）

```bash
python src/main.py schedule
```

默认在 08:30 / 13:30 / 18:30（马德里时间）自动执行，可在 `config.yaml` 的 `fetch_times` 修改。

---

## 生成的网页结构

```
public/
├── index.html              # 今日首页（重点 + 全部新闻）
├── archive/
│   └── YYYY-MM-DD.html     # 按日期归档页
├── articles/
│   └── <hash_id>.html      # 单篇详情页
├── data/
│   ├── latest.json         # 最新一批数据
│   └── archive.json        # 历史索引
└── assets/
    └── style.css           # 样式
```

---

## Telegram 通知格式

### 成功通知

```
🇪🇸 Madrid Local News 更新完成
今日新增：8 条
重点新闻（S/A 级）：2 条
亲子/家庭相关：3 条

⭐ 今日最值得关注：
1. [A] Retiro 公园周末儿童活动
   适合3-10岁孩子的免费户外活动
2. [S] 市中心交通管制提醒
   ...

📖 完整阅读：
https://username.github.io/spain-assistant/
```

### 错误告警

```
⚠️ Spain Assistant 运行异常
模块：madrid_news
阶段：fetch
错误：页面抓取失败
时间：2026-05-14 08:30
请检查日志。
```

---

## 查看日志

```bash
tail -f logs/spain_assistant.log
```

---

## 运行测试

```bash
python tests/test_deduper.py
python tests/test_renderer.py
```

---

## 项目结构

```
spain_assistant/
├── src/
│   ├── core/               # 基础设施（配置、日志、存储、调度）
│   ├── modules/
│   │   ├── madrid_news/    # V1 新闻模块
│   │   └── future_modules/ # 扩展模块占位
│   ├── publishers/         # Telegram + GitHub 发布
│   ├── templates/          # Jinja2 HTML 模板
│   └── main.py             # CLI 入口
├── assets/style.css        # 全局样式
├── data/                   # 原始 + 处理后数据（不提交 Git）
├── public/                 # 生成的静态网页（不提交 Git）
├── logs/                   # 运行日志（不提交 Git）
├── tests/                  # 测试
├── config.yaml             # 主配置
├── .env.example            # 环境变量模板
└── requirements.txt        # 依赖
```

---

## 新增模块（开发者文档）

1. 创建 `src/modules/<name>/module.py`，实现 `run() -> dict`
2. 在 `config.yaml` 的 `modules:` 下添加配置项
3. 在 `src/main.py::_register_modules()` 中注册
4. 参见 `src/modules/future_modules/README.md` 了解接口规范
