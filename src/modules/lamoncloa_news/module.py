"""La Moncloa 国家新闻模块：抓取 → 去重 → 分析 → 有效期标注 → 保存。"""

import time
from datetime import date, timedelta, datetime

from src.core import config
from src.core.logger import get_logger
from src.core.storage import load_state, save_state, save_raw, save_processed
from src.core.utils import run_id, today_str
from src.modules.lamoncloa_news.fetcher import fetch_article_list, fetch_article_content
from src.modules.lamoncloa_news.analyzer import analyze_article
from src.modules.madrid_news.highlight_manager import update_highlight_store

log = get_logger(__name__)

_STATE_KEY = "lamoncloa_seen"

# 按重要性的默认保留天数
_RETENTION_DAYS = {"S": 7, "A": 3, "B": 1}


def _filter_new(articles: list, state: dict) -> tuple[list, int]:
    seen = state.get(_STATE_KEY, {})
    new, skipped = [], 0
    for art in articles:
        if art["hash_id"] in seen:
            skipped += 1
        else:
            new.append(art)
    return new, skipped


def _commit_seen(articles: list, state: dict):
    seen = state.setdefault(_STATE_KEY, {})
    for art in articles:
        hid = art.get("hash_id", "")
        if hid:
            seen[hid] = {
                "seen_at": datetime.now().isoformat(),
                "title": art.get("title", "")[:60],
            }


def _compute_validity(article: dict) -> tuple[bool, str, str, str]:
    """返回 (is_highlight, valid_from, valid_until, expiry_reason)。B 级不标记 highlight。"""
    importance = article.get("importance", "B")
    today = today_str()

    if importance == "B":
        return False, "", "", ""

    # 优先使用 LLM 提取的截止日期
    deadline = (article.get("deadline_date") or "").strip()
    if deadline and deadline >= today:
        return True, today, deadline, "deadline_date"

    # 按重要性默认保留
    ttl = _RETENTION_DAYS.get(importance, 3)
    valid_until = (date.fromisoformat(today) + timedelta(days=ttl)).isoformat()
    return True, today, valid_until, f"default_{ttl}_days"


def run() -> dict:
    """执行一次 La Moncloa 新闻抓取流程。"""
    rid = run_id()
    errors = []
    log.info(f"[lamoncloa] === 开始运行 run_id={rid} ===")

    # 1. 抓取列表
    try:
        raw_articles = fetch_article_list(
            max_items=config.get("modules.lamoncloa_news.max_articles_per_run", 20)
        )
    except Exception as e:
        msg = f"列表页抓取失败: {e}"
        log.error(f"[lamoncloa] {msg}")
        return {"new_count": 0, "articles": [], "errors": [msg]}

    save_raw("lamoncloa_news", raw_articles, rid)

    # 2. 去重
    state = load_state()
    new_articles, skipped = _filter_new(raw_articles, state)

    if not new_articles:
        log.info("[lamoncloa] 无新增新闻，任务结束")
        return {"new_count": 0, "articles": [], "errors": [], "skipped": skipped}

    # 3. 抓取正文（单条失败不中断）
    for i, art in enumerate(new_articles):
        try:
            art["content"] = fetch_article_content(art["url"])
            if i < len(new_articles) - 1:
                time.sleep(1)
        except Exception as e:
            log.warning(f"[lamoncloa] 正文抓取失败: {e}")
            art.setdefault("content", "")

    # 4. 分析 + 有效期标注
    processed = []
    for art in new_articles:
        try:
            art = analyze_article(art)
            is_hl, vf, vu, reason = _compute_validity(art)
            art["is_highlight"] = is_hl
            art["valid_from"] = vf
            art["valid_until"] = vu
            art["expiry_reason"] = reason
            processed.append(art)
        except Exception as e:
            errors.append(f"处理失败 [{art.get('title', '')[:40]}]: {e}")
            log.warning(f"[lamoncloa] {errors[-1]}")
            art.setdefault("tags", ["政治"])
            art.setdefault("importance", "B")
            art.setdefault("is_highlight", False)
            art.setdefault("valid_from", "")
            art.setdefault("valid_until", "")
            art.setdefault("expiry_reason", "")
            art.setdefault("zh", {"chinese_title": art.get("title", ""), "one_line_summary": "", "china_resident_angle": ""})
            processed.append(art)

    # 5. 持久化 S/A highlights 到跨日 store
    highlights = [a for a in processed if a.get("is_highlight")]
    if highlights:
        update_highlight_store(highlights)

    # 6. 持久化去重状态
    _commit_seen(processed, state)
    state["last_run"]["lamoncloa_news"] = {"run_id": rid, "date": today_str(), "count": len(processed)}
    save_state(state)
    save_processed("lamoncloa_news", processed, rid)

    s_count = sum(1 for a in processed if a.get("importance") == "S")
    a_count = sum(1 for a in processed if a.get("importance") == "A")
    log.info(f"[lamoncloa] === 完成 新增:{len(processed)} (S:{s_count} A:{a_count}) 跳过:{skipped} 错误:{len(errors)} ===")
    return {"new_count": len(processed), "articles": processed, "errors": errors, "skipped": skipped}
