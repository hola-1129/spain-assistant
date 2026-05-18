# Spain Assistant — Claude 工作上下文

## 项目定位

**Spain Assistant** 是面向"在西班牙生活的华人家庭"的长期生活助手系统。

核心不是"翻译新闻"，而是：
> 把马德里本地公共信息，转化成华人家庭真正看得懂、用得上的生活情报。

## 当前 V1 状态

仅实现第一个模块：**Madrid Local News Assistant**（马德里本地新闻解读）。

## 架构原则

- 每个模块在 `src/modules/<name>/` 下，暴露 `module.py::run() -> dict`
- 核心基础设施在 `src/core/`（config、logger、storage、scheduler）
- 发布层在 `src/publishers/`（Telegram 通知 + GitHub Pages）
- Telegram 只做通知入口，不推送完整长文
- GitHub Pages 是主要阅读入口
- 所有敏感信息通过 `.env` 注入，不硬编码

## 修改原则

1. 新增模块：只在 `src/modules/` 下新建目录 + 在 `src/main.py` 注册
2. 不要修改 `src/core/` 的接口，只扩展
3. 抓取失败、LLM 失败：记录日志，跳过单条，不中断整体
4. GitHub 推送失败：保留本地 public/，不影响主流程
5. 不编造信息：LLM prompt 已强制要求，不确定写"原文未说明"

## 运行方式

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/spain_assistant
python src/main.py run madrid_news   # 单次运行
python src/main.py schedule          # 启动定时调度（常驻）
```

## 扩展模块注册流程

1. 创建 `src/modules/<name>/module.py`，实现 `run() -> dict`
2. 在 `config.yaml` 的 `modules:` 下添加配置
3. 在 `src/main.py::_register_modules()` 中注册
4. 更新 `src/modules/future_modules/README.md`
