"""生成 ICS 日历文件。

- write_ics(): 单个文件包含本周所有事件
- write_per_event_ics(): 为每个事件单独生成 .ics 文件，便于在 HTML 上做「加到手机日历」按钮
"""

import hashlib
import re
import unicodedata
from datetime import timedelta
from pathlib import Path

from ics import Calendar, DisplayAlarm, Event

from analyzer.extractor import event_from_dict, parse_event_datetime


def slugify(text: str, max_length: int = 40) -> str:
    """ASCII slug：去重音 → 丢非 ASCII → 小写 → 非字母数字替换为 -"""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_only = ascii_only.encode("ascii", "ignore").decode("ascii")
    s = ascii_only.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_length].rstrip("-")


def _build_description(ev_dict: dict, fetch: dict) -> str:
    parts = []
    aud = ev_dict.get("audience_cn") or ev_dict.get("audience_es") or fetch.get("stage", "")
    if aud:
        parts.append(f"适用: {aud}")
    if ev_dict.get("parent_action"):
        parts.append(f"家长: {ev_dict['parent_action']}")
    if ev_dict.get("student_prepare"):
        parts.append(f"孩子准备: {ev_dict['student_prepare']}")
    if ev_dict.get("signup_required"):
        parts.append(f"报名: {ev_dict['signup_required']}")
    if ev_dict.get("payment_required"):
        parts.append(f"付款: {ev_dict['payment_required']}")
    if ev_dict.get("cost"):
        parts.append(f"费用: {ev_dict['cost']}")
    if ev_dict.get("deadline"):
        parts.append(f"截止: {ev_dict['deadline']}")
    if fetch.get("url"):
        parts.append(f"原文: {fetch['url']}")
    return "\n".join(parts)


def _uid_for(week_iso: str, idx: int, ev_dict: dict, fetch: dict) -> str:
    base = f"{week_iso}|{idx}|{fetch.get('url','')}|{ev_dict.get('date','')}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"{h}@school_helper"


def _alarms(reminders: list[dict]) -> list[DisplayAlarm]:
    alarms: list[DisplayAlarm] = []
    for r in reminders or []:
        delta = timedelta()
        if "days" in r:
            delta += timedelta(days=int(r["days"]))
        if "hours" in r:
            delta += timedelta(hours=int(r["hours"]))
        if "minutes" in r:
            delta += timedelta(minutes=int(r["minutes"]))
        if delta.total_seconds() > 0:
            alarms.append(DisplayAlarm(trigger=-delta, display_text="School Helper 提醒"))
    return alarms


def _build_event(*, idx: int, e: dict, fld: dict, week_iso: str,
                 calendar_cfg: dict) -> Event | None:
    """从已抽取的字段构造 ics.Event；无日期返回 None。"""
    ev = event_from_dict(fld)
    tz_name = calendar_cfg.get("timezone", "Europe/Madrid")
    begin, end, all_day = parse_event_datetime(ev, tz_name)
    if not begin:
        return None

    title_cn = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
    title_es = fld.get("title_es") or e["fetch"].get("title", "")
    name = title_cn if (not title_es or title_es == title_cn) else f"{title_cn} / {title_es}"

    ie = Event(
        name=name,
        begin=begin,
        end=end,
        location=fld.get("location_es") or fld.get("location_cn") or "",
        description=_build_description(fld, e["fetch"]),
        uid=_uid_for(week_iso, idx, fld, e["fetch"]),
    )
    if all_day:
        ie.make_all_day()
    for a in _alarms(calendar_cfg.get("default_reminders", [])):
        ie.alarms.append(a)
    return ie


def write_ics(out_path: Path, *, week_iso: str, events: list[dict],
              calendar_cfg: dict) -> int:
    cal = Calendar()
    written = 0
    for idx, e in enumerate(events, 1):
        fld = e.get("fields")
        if not fld:
            continue
        ie = _build_event(idx=idx, e=e, fld=fld, week_iso=week_iso, calendar_cfg=calendar_cfg)
        if ie is None:
            continue
        cal.events.add(ie)
        written += 1
    out_path.write_text(cal.serialize())
    return written


def write_per_event_ics(events_dir: Path, *, week_iso: str, events: list[dict],
                        calendar_cfg: dict) -> dict[int, str]:
    """为每个有日期的事项写一份 .ics。返回 {idx: 相对文件名}。"""
    events_dir.mkdir(parents=True, exist_ok=True)
    # 清空旧的，避免上一轮残留
    for old in events_dir.glob("*.ics"):
        old.unlink()

    mapping: dict[int, str] = {}
    used_slugs: set[str] = set()
    for idx, e in enumerate(events, 1):
        fld = e.get("fields")
        if not fld:
            continue
        ie = _build_event(idx=idx, e=e, fld=fld, week_iso=week_iso, calendar_cfg=calendar_cfg)
        if ie is None:
            continue

        # slug 来源：title_es → fetch.title → "event"（不使用中文）
        slug_src = fld.get("title_es") or e["fetch"].get("title", "") or "event"
        slug = slugify(slug_src) or f"event-{idx}"
        filename = f"{idx:02d}-{slug}.ics"
        # 极小概率重名：再追加 idx
        if filename in used_slugs:
            filename = f"{idx:02d}-{slug}-{idx}.ics"
        used_slugs.add(filename)

        cal = Calendar()
        cal.events.add(ie)
        (events_dir / filename).write_text(cal.serialize())
        mapping[idx] = filename

    return mapping
