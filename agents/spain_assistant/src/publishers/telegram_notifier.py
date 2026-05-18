"""Telegram 通知推送。只发摘要，不推送完整长文。"""

import asyncio
import os
import re
from datetime import date
from telegram import Bot
from telegram.constants import ParseMode

from src.core import config
from src.core.logger import get_logger
from src.core.utils import now_madrid, today_str

log = get_logger(__name__)

_IMP_RANK = {"S": 0, "A": 1}


def _date_desc_key(art: dict) -> int:
    s = (art.get("date") or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return -date.fromisoformat(m.group(1)).toordinal()
        except ValueError:
            pass
    return 0


def _get_bot() -> Bot | None:
    token = os.getenv(config.get("telegram.bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    if not token:
        log.warning("[telegram] Bot token 未配置，跳过推送")
        return None
    return Bot(token=token)


def _get_chat_id() -> str:
    return os.getenv(config.get("telegram.chat_id_env", "TELEGRAM_CHAT_ID"), "")


async def _send(text: str):
    bot = _get_bot()
    chat_id = _get_chat_id()
    if not bot or not chat_id:
        return
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.error(f"[telegram] 发送失败: {e}")


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, coro).result()
        else:
            loop.run_until_complete(coro)
    except Exception as e:
        log.error(f"[telegram] 事件循环错误: {e}")


def notify_success(module: str, result: dict, pages_url: str = ""):
    if not config.get("telegram.enabled") or not config.get("telegram.notify_on_success"):
        return

    max_items = config.get("telegram.max_items", 5)
    articles = result.get("articles", [])
    new_count = result.get("new_count", 0)

    today_arts = [a for a in articles if a.get("is_today", True)]
    top = sorted(
        [a for a in today_arts if a.get("importance") in ("S", "A")],
        key=lambda a: (_IMP_RANK.get(a.get("importance", "A"), 1), _date_desc_key(a))
    )[:max_items]
    family = [a for a in today_arts if any(t in a.get("labels", []) for t in ("亲子", "教育"))]
    culture = [a for a in today_arts if any(t in a.get("labels", []) for t in ("文化", "艺术", "体育", "节日"))]

    lines = [
        "🇪🇸 <b>Spain Assistant 更新完成</b>",
        f"日期：{today_str()}",
        f"今日新闻：{len(today_arts)} 条",
    ]
    if top:
        lines.append(f"重点新闻：{len(top)} 条")
    if family or culture:
        extra = []
        if family:
            extra.append(f"亲子/教育 {len(family)} 条")
        if culture:
            extra.append(f"文化/艺术/体育 {len(culture)} 条")
        lines.append("·".join(extra))

    if top:
        lines.append("\n⭐ <b>今日最值得看：</b>")
        for i, art in enumerate(top, 1):
            zh = art.get("zh", {})
            title = zh.get("chinese_title") or art.get("title", "")
            summary = zh.get("one_line_summary", "")
            imp = art.get("importance", "")
            lines.append(f"{i}. [{imp}] {title}")
            if summary:
                lines.append(f"   <i>{summary}</i>")

    if pages_url:
        lines.append(f"\n📖 <b>完整阅读：</b>\n{pages_url}")

    _run(_send("\n".join(lines)))


def notify_error(module: str, stage: str, error: str):
    if not config.get("telegram.enabled") or not config.get("telegram.notify_on_error"):
        return
    ts = now_madrid().strftime("%Y-%m-%d %H:%M")
    text = (
        f"⚠️ <b>Spain Assistant 运行异常</b>\n"
        f"模块：{module}\n阶段：{stage}\n错误：{error}\n时间：{ts}\n请检查日志。"
    )
    _run(_send(text))


def notify_test():
    ts = now_madrid().strftime("%Y-%m-%d %H:%M")
    _run(_send(f"✅ Spain Assistant Telegram 通知测试成功\n时间：{ts}"))
    log.info("[telegram] 测试消息已发送")
