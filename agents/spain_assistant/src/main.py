"""Spain Assistant CLI 入口。

用法：
  python src/main.py run madrid_news   # 执行单次抓取+生成
  python src/main.py run-all           # 执行所有启用模块
  python src/main.py render            # 仅重新渲染最近一批数据
  python src/main.py notify-test       # 发送 Telegram 测试消息
  python src/main.py publish           # 发布 public/ 到 GitHub Pages
  python src/main.py schedule          # 启动定时调度器（常驻进程）
"""

import sys
import json
import glob
from pathlib import Path

# 确保 src/ 在 import 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import config
from src.core.logger import get_logger
from src.core.utils import today_str
from src.core.storage import purge_old_files

log = get_logger(__name__)

# 已注册模块：name → run 函数
_MODULES: dict = {}


def _register_modules():
    if config.get("modules.madrid_news.enabled", True):
        from src.modules.madrid_news.module import run as madrid_run
        _MODULES["madrid_news"] = madrid_run

    if config.get("modules.lamoncloa_news.enabled", False):
        from src.modules.lamoncloa_news.module import run as lamoncloa_run
        _MODULES["lamoncloa_news"] = lamoncloa_run

    if config.get("modules.esmadrid_agenda.enabled", False):
        from src.modules.esmadrid_agenda.module import run as esmadrid_run
        _MODULES["esmadrid_agenda"] = esmadrid_run

    # 扩展点：新增模块在此注册
    # if config.get("modules.school_notice.enabled"):
    #     from src.modules.school_notice.module import run as school_run
    #     _MODULES["school_notice"] = school_run


def _run_module(name: str):
    fn = _MODULES.get(name)
    if not fn:
        log.error(f"未找到模块: {name}（已注册: {list(_MODULES.keys())}）")
        sys.exit(1)

    from src.publishers.telegram_notifier import notify_success, notify_error

    log.info(f"=== 运行模块: {name} ===")
    try:
        result = fn()
    except Exception as e:
        log.error(f"模块 {name} 运行异常: {e}")
        notify_error(name, "run", str(e))
        sys.exit(1)

    if result.get("new_count", 0) > 0:
        _render(result["articles"], source_module=name)
        from src.publishers.github_publisher import publish
        publish()
        pages_url = _build_pages_url()
        notify_success(name, result, pages_url)
    else:
        log.info(f"[{name}] 无新内容，跳过渲染和通知")

    _cleanup()


def _render(articles: list | None = None, source_module: str = "madrid_news"):
    """渲染 HTML 页面。合并今日所有批次数据，避免多次运行时新批次覆盖旧批次。"""
    from src.modules.madrid_news.renderer import render_all

    madrid_arts = _load_today_processed("madrid_news")
    national_arts = _load_today_processed("lamoncloa_news")
    agenda_arts = _load_today_processed("esmadrid_agenda")

    if not madrid_arts and not national_arts and not agenda_arts:
        log.warning("[render] 无数据可渲染")
        return

    render_all(madrid_arts or [], national_arts or [], agenda_arts or [])


def _load_today_processed(module: str = "madrid_news") -> list:
    """加载今日所有批次的处理结果，按 hash_id 合并去重；若今日无数据则回退到最新文件。"""
    processed_dir = config.processed_dir / module
    if not processed_dir.exists():
        return []

    today_prefix = today_str().replace("-", "")  # e.g. "20260530"
    today_files = sorted(processed_dir.glob(f"{today_prefix}_*.json"))

    if today_files:
        merged: dict = {}
        for f in today_files:
            try:
                arts = json.loads(f.read_text(encoding="utf-8"))
                for art in arts:
                    hid = art.get("hash_id")
                    if hid:
                        merged[hid] = art
            except Exception as e:
                log.error(f"加载数据失败 ({module}, {f.name}): {e}")
        log.info(f"[render] {module} 今日共 {len(today_files)} 批次，合并后 {len(merged)} 条")
        return list(merged.values())

    # 今日无数据，回退到最新文件（跨日数据，如 lamoncloa/esmadrid 不一定每天运行）
    files = sorted(processed_dir.glob("*.json"), reverse=True)
    if not files:
        return []
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"加载数据失败 ({module}): {e}")
        return []


def _build_pages_url() -> str:
    repo = config.get("github.repo", "")
    if not repo:
        return ""
    parts = repo.split("/")
    if len(parts) == 2:
        return f"https://{parts[0]}.github.io/{parts[1]}/"
    return ""


def _cleanup():
    purge_old_files(config.raw_dir, config.get("retention.raw_data_days", 180))
    # HTML 清理留给 GitHub 侧策略，本地 public/ 不主动删除


def cmd_run(args: list):
    _register_modules()
    name = args[0] if args else "madrid_news"
    _run_module(name)


def cmd_run_all():
    _register_modules()
    for name in _MODULES:
        _run_module(name)


def cmd_render():
    _register_modules()
    _render()


def cmd_notify_test():
    from src.publishers.telegram_notifier import notify_test
    notify_test()


def cmd_publish():
    from src.publishers.github_publisher import publish
    ok = publish()
    sys.exit(0 if ok else 1)


def cmd_schedule():
    _register_modules()
    from src.core.scheduler import register_module, run_loop

    for name, fn in _MODULES.items():
        times = config.get(f"modules.{name}.fetch_times", ["08:30", "13:30", "18:30"])

        def make_runner(n, f):
            def runner():
                log.info(f"[scheduler] 触发模块: {n}")
                from src.publishers.telegram_notifier import notify_success, notify_error
                try:
                    result = f()
                    if result.get("new_count", 0) > 0:
                        _render(result["articles"])
                        notify_success(n, result, _build_pages_url())
                        from src.publishers.github_publisher import publish
                        publish()
                except Exception as e:
                    log.error(f"[scheduler] {n} 运行异常: {e}")
                    notify_error(n, "scheduler", str(e))
            return runner

        register_module(name, make_runner(name, fn), times)

    run_loop()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    dispatch = {
        "run": lambda: cmd_run(args),
        "run-all": cmd_run_all,
        "render": cmd_render,
        "notify-test": cmd_notify_test,
        "publish": cmd_publish,
        "schedule": cmd_schedule,
    }

    fn = dispatch.get(cmd)
    if not fn:
        log.error(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)

    fn()


if __name__ == "__main__":
    main()
