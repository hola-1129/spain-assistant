"""esmadrid Agenda Madrid 模块：抓取 → 去重 → 详情 → 分析 → 区域标注 → 保存。"""

import time
from datetime import datetime

from src.core import config
from src.core.logger import get_logger
from src.core.storage import load_state, save_state, save_raw, save_processed
from src.core.utils import run_id, today_str
from src.core.calendar_generator import build_maps_info
from src.modules.esmadrid_agenda.fetcher import fetch_event_list, fetch_event_detail
from src.modules.esmadrid_agenda.analyzer import classify_event_tags, calculate_event_expiry
from src.modules.madrid_news.area_tagger import tag_area
from src.modules.madrid_news.highlight_manager import update_highlight_store

log = get_logger(__name__)

_STATE_KEY = "esmadrid_seen"


def _filter_new(events: list, state: dict) -> tuple[list, int]:
    seen = state.get(_STATE_KEY, {})
    new, skipped = [], 0
    for ev in events:
        if ev["hash_id"] in seen:
            skipped += 1
        else:
            new.append(ev)
    return new, skipped


def _commit_seen(events: list, state: dict):
    seen = state.setdefault(_STATE_KEY, {})
    for ev in events:
        hid = ev.get("hash_id", "")
        if hid:
            seen[hid] = {"seen_at": datetime.now().isoformat(), "title": ev.get("title", "")[:60]}


def _normalize_for_area_tagger(event: dict) -> dict:
    """把活动数据包装成 area_tagger 期望的 {zh.location_info} 格式。"""
    event["zh"] = event.get("zh") or {}
    loc_name = event.get("location_name", "")
    address = event.get("address", "")
    query = loc_name + " Madrid" if loc_name else ""
    event["zh"]["location_info"] = {
        "name": loc_name,
        "address": address,
        "district": "",
        "google_maps_query": query,
    }
    return event


def _build_maps_url(event: dict) -> dict:
    """计算 maps_url / maps_url_type。"""
    loc = event.get("zh", {}).get("location_info", {})
    maps = build_maps_info(loc) if loc else {"url": "", "type": "none"}
    event["maps_url"] = maps["url"]
    event["maps_url_type"] = maps["type"]
    return event


def run() -> dict:
    """执行一次 esmadrid Agenda 抓取流程。"""
    rid = run_id()
    errors = []
    log.info(f"[esmadrid] === 开始运行 run_id={rid} ===")

    # 1. 抓取列表
    try:
        raw_events = fetch_event_list()
    except Exception as e:
        msg = f"列表页抓取失败: {e}"
        log.error(f"[esmadrid] {msg}")
        return {"new_count": 0, "articles": [], "errors": [msg]}

    save_raw("esmadrid_agenda", raw_events, rid)

    # 2. 去重
    state = load_state()
    new_events, skipped = _filter_new(raw_events, state)

    if not new_events:
        log.info("[esmadrid] 无新增活动，任务结束")
        return {"new_count": 0, "articles": [], "errors": [], "skipped": skipped}

    # 3. 抓取详情页
    max_detail = config.get("modules.esmadrid_agenda.max_detail_fetch", 15)
    for i, ev in enumerate(new_events[:max_detail]):
        try:
            detail = fetch_event_detail(ev["url"])
            ev.update({k: v for k, v in detail.items() if v})  # 只覆盖非空字段
            if i < len(new_events) - 1:
                time.sleep(1)
        except Exception as e:
            log.warning(f"[esmadrid] 详情抓取失败 ({ev.get('title','')[:30]}): {e}")

    # 4. LLM 分类 + 区域标注 + 有效期计算
    processed = []
    for ev in new_events:
        try:
            ev = classify_event_tags(ev)
            ev = _normalize_for_area_tagger(ev)
            ev = tag_area(ev)
            ev = _build_maps_url(ev)
            is_hl, vf, vu, reason = calculate_event_expiry(ev)
            ev["is_highlight"] = is_hl
            ev["valid_from"] = vf
            ev["valid_until"] = vu
            ev["expiry_reason"] = reason
            processed.append(ev)
        except Exception as e:
            errors.append(f"处理失败 [{ev.get('title','')[:40]}]: {e}")
            log.warning(f"[esmadrid] {errors[-1]}")
            ev.setdefault("tags", ["艺术"])
            ev.setdefault("importance", "B")
            ev.setdefault("audience", [])
            ev.setdefault("area_label", "Madrid")
            ev.setdefault("area_district", None)
            ev.setdefault("area_type", "unknown")
            ev.setdefault("maps_url", "")
            ev.setdefault("maps_url_type", "none")
            ev.setdefault("is_highlight", False)
            ev.setdefault("valid_from", "")
            ev.setdefault("valid_until", "")
            ev.setdefault("expiry_reason", "")
            ev.setdefault("zh", {"chinese_title": ev.get("title", ""), "one_line_summary": ""})
            processed.append(ev)

    # 5. S 级活动进 highlight store
    highlights = [e for e in processed if e.get("is_highlight")]
    if highlights:
        update_highlight_store(highlights)

    # 6. 持久化
    _commit_seen(processed, state)
    state["last_run"]["esmadrid_agenda"] = {"run_id": rid, "date": today_str(), "count": len(processed)}
    save_state(state)
    save_processed("esmadrid_agenda", processed, rid)

    s_count = sum(1 for e in processed if e.get("importance") == "S")
    a_count = sum(1 for e in processed if e.get("importance") == "A")
    log.info(f"[esmadrid] === 完成 新增:{len(processed)} (S:{s_count} A:{a_count}) 跳过:{skipped} 错误:{len(errors)} ===")
    return {"new_count": len(processed), "articles": processed, "errors": errors, "skipped": skipped}
