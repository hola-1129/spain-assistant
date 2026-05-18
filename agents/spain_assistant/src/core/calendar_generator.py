"""生成 ICS 文件内容和 Google Calendar / Apple Calendar 链接。"""

import urllib.parse
from datetime import date, datetime, timedelta


def build_google_calendar_url(event: dict) -> str:
    title = event.get("title", "")
    start_date = event.get("start_date", "")
    if not start_date or not title:
        return ""

    end_date = event.get("end_date", "") or start_date
    start_time = event.get("start_time", "")
    end_time = event.get("end_time", "")
    location = event.get("location", "")
    description = event.get("description", "")

    if start_time:
        s = start_date.replace("-", "") + "T" + start_time.replace(":", "") + "00"
        if end_time:
            e = end_date.replace("-", "") + "T" + end_time.replace(":", "") + "00"
        else:
            t = datetime.strptime(start_time, "%H:%M")
            t_end = t.replace(hour=min(t.hour + 1, 23), minute=0)
            e = end_date.replace("-", "") + "T" + t_end.strftime("%H%M") + "00"
        dates = f"{s}/{e}"
    else:
        try:
            end_d = date.fromisoformat(end_date) + timedelta(days=1)
        except Exception:
            end_d = date.fromisoformat(start_date) + timedelta(days=1)
        dates = f"{start_date.replace('-', '')}/{end_d.strftime('%Y%m%d')}"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
        "details": description,
        "location": location,
        "ctz": "Europe/Madrid",
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


def build_ics_content(event: dict, article_url: str = "", hash_id: str = "") -> str:
    title = event.get("title", "")
    start_date = event.get("start_date", "")
    if not start_date or not title:
        return ""

    end_date = event.get("end_date", "") or start_date
    start_time = event.get("start_time", "")
    end_time = event.get("end_time", "")
    location = event.get("location", "")
    description = event.get("description", "")

    uid = f"{hash_id or 'evt'}@spain-assistant.madrid"
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    if start_time:
        dt_start = f"DTSTART;TZID=Europe/Madrid:{start_date.replace('-','')}T{start_time.replace(':','')}00"
        if end_time:
            dt_end = f"DTEND;TZID=Europe/Madrid:{end_date.replace('-','')}T{end_time.replace(':','')}00"
        else:
            t = datetime.strptime(start_time, "%H:%M")
            t_end = t.replace(hour=min(t.hour + 1, 23), minute=0)
            dt_end = f"DTEND;TZID=Europe/Madrid:{end_date.replace('-','')}T{t_end.strftime('%H%M')}00"
    else:
        try:
            end_d = date.fromisoformat(end_date) + timedelta(days=1)
        except Exception:
            end_d = date.fromisoformat(start_date) + timedelta(days=1)
        dt_start = f"DTSTART;VALUE=DATE:{start_date.replace('-','')}"
        dt_end = f"DTEND;VALUE=DATE:{end_d.strftime('%Y%m%d')}"

    desc = description.replace("\n", "\\n")
    if article_url:
        desc += f"\\n\\n原文链接：{article_url}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Spain Assistant//Madrid Local Briefing//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        dt_start,
        dt_end,
        f"SUMMARY:{_fold(title)}",
        f"DESCRIPTION:{_fold(desc)}",
        f"LOCATION:{_fold(location)}",
        f"URL:{article_url}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def build_google_maps_url(location_info: dict) -> str:
    query = location_info.get("google_maps_query", "").strip()
    if not query:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)


_VAGUE_VALUES = {"原文未说明", "madrid", "spain", "españa", ""}


def build_maps_info(location_info: dict) -> dict:
    """返回 {"url": str, "type": "specific"|"search"|"none"}。

    - specific: 场馆名或街道地址已知，搜索结果可精确定位
    - search:   只有模糊查询词，显示为"地图搜索"
    - none:     地点信息不足，不显示地图按钮
    """
    name = (location_info.get("name") or "").strip()
    address = (location_info.get("address") or "").strip()
    query = (location_info.get("google_maps_query") or "").strip()

    if not query or query.lower() in _VAGUE_VALUES:
        return {"url": "", "type": "none"}

    url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)

    name_ok = name and name.lower() not in _VAGUE_VALUES
    addr_ok = address and address.lower() not in _VAGUE_VALUES

    if name_ok or addr_ok:
        return {"url": url, "type": "specific"}

    return {"url": url, "type": "search"}


def _fold(text: str, limit: int = 70) -> str:
    """ICS line folding（简单截断，不影响功能）。"""
    if len(text) <= limit:
        return text
    return text[:limit]
