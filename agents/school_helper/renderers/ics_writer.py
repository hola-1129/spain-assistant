"""生成 school_events.ics。

使用 ics 库；为每个事件加默认提前 1 天 + 提前 2 小时双重提醒（VALARM DISPLAY）。
没有具体时间的事项作为全天事件（all-day）。
"""

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from ics import Calendar, DisplayAlarm, Event

from analyzer.extractor import event_from_dict, parse_event_datetime


def _build_description(ev_dict: dict, fetch: dict) -> str:
    fld = ev_dict
    parts = []
    aud = fld.get("audience_cn") or fld.get("audience_es") or fetch.get("stage", "")
    if aud:
        parts.append(f"适用: {aud}")
    if fld.get("parent_action"):
        parts.append(f"家长: {fld['parent_action']}")
    if fld.get("student_prepare"):
        parts.append(f"孩子准备: {fld['student_prepare']}")
    if fld.get("signup_required"):
        parts.append(f"报名: {fld['signup_required']}")
    if fld.get("payment_required"):
        parts.append(f"付款: {fld['payment_required']}")
    if fld.get("cost"):
        parts.append(f"费用: {fld['cost']}")
    if fld.get("deadline"):
        parts.append(f"截止: {fld['deadline']}")
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


def write_ics(out_path: Path, *, week_iso: str, events: list[dict],
              calendar_cfg: dict) -> int:
    cal = Calendar()
    tz_name = calendar_cfg.get("timezone", "Europe/Madrid")
    reminders = calendar_cfg.get("default_reminders", [])

    written = 0
    for idx, e in enumerate(events, 1):
        fld = e.get("fields")
        if not fld or not fld.get("date"):
            continue
        ev = event_from_dict(fld)
        begin, end, all_day = parse_event_datetime(ev, tz_name)
        if not begin:
            continue

        title_cn = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
        title_es = fld.get("title_es") or e["fetch"].get("title", "")
        name = title_cn if title_cn == title_es or not title_es else f"{title_cn} / {title_es}"

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

        for a in _alarms(reminders):
            ie.alarms.append(a)

        cal.events.add(ie)
        written += 1

    out_path.write_text(cal.serialize())
    return written
