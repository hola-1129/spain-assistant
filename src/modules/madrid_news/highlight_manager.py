"""重点关注新闻的生命周期管理：标记、持久化、过期清理。"""

import json
from datetime import date, timedelta

from src.core import config
from src.core.logger import get_logger
from src.core.utils import today_str

log = get_logger(__name__)

_STORE_FILE = config.data_dir / "active_highlights.json"
_DEFAULT_TTL_DAYS = 3


def _load_store() -> dict:
    if _STORE_FILE.exists():
        try:
            return json.loads(_STORE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[highlight] 读取 active_highlights.json 失败: {e}")
    return {}


def _save_store(store: dict):
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STORE_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _compute_validity(article: dict) -> tuple[str, str, str]:
    """返回 (valid_from, valid_until, expiry_reason)。"""
    today = today_str()
    event = article.get("zh", {}).get("event", {})

    if event.get("has_event"):
        end = (event.get("end_date") or "").strip()
        start = (event.get("start_date") or "").strip()
        if end and end >= today:
            reason = "event_end_date" if end != start else "event_start_date"
            return today, end, reason
        if start and start >= today:
            return today, start, "event_start_date"

    default_until = (date.fromisoformat(today) + timedelta(days=_DEFAULT_TTL_DAYS)).isoformat()
    return today, default_until, "default_3_days"


def tag_highlights(articles: list[dict]) -> list[dict]:
    """标记 S/A 级新闻为重点关注，写入有效期字段。"""
    for art in articles:
        if art.get("importance") in ("S", "A"):
            valid_from, valid_until, reason = _compute_validity(art)
            art["is_highlight"] = True
            art["valid_from"] = valid_from
            art["valid_until"] = valid_until
            art["expiry_reason"] = reason
        else:
            art["is_highlight"] = False
            art["valid_from"] = ""
            art["valid_until"] = ""
            art["expiry_reason"] = ""
    return articles


def update_highlight_store(articles: list[dict]):
    """合并新 highlights 到持久化 store，清理已过期条目。"""
    store = _load_store()
    today = today_str()

    for art in articles:
        if art.get("is_highlight") and art.get("hash_id"):
            store[art["hash_id"]] = art

    before = len(store)
    store = {hid: a for hid, a in store.items() if a.get("valid_until", "") >= today}
    pruned = before - len(store)
    if pruned:
        log.info(f"[highlight] 清理过期重点关注: {pruned} 条")

    _save_store(store)
    log.info(f"[highlight] 活跃重点关注: {len(store)} 条")


def load_active_highlights(today: str = "") -> list[dict]:
    """返回所有仍在有效期内的重点关注新闻，按重要性排序。"""
    today = today or today_str()
    store = _load_store()
    imp_order = {"S": 0, "A": 1}
    active = [a for a in store.values() if a.get("valid_until", "") >= today]
    return sorted(active, key=lambda a: (imp_order.get(a.get("importance", "C"), 2), a.get("valid_from", "")))
