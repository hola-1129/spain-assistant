"""每周黄历（宜/忌）+ 西/中/台节假日。

一次 LLM tool_use 调用覆盖整周，结构化输出，避免裸 JSON 解析失败。
失败时 fetch_week_almanac() 返回空 dict，主流程继续，HTML 渲染时跳过该区段。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from utils.logger import setup_logger

logger = setup_logger("almanac")


_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "almanac_days": {
            "type": "array",
            "description": "本周 7 天每天的黄历宜忌",
            "items": {
                "type": "object",
                "properties": {
                    "date":    {"type": "string", "description": "YYYY-MM-DD"},
                    "weekday": {"type": "string", "description": "周一/周二/.../周日"},
                    "lunar":   {"type": "string", "description": "农历日期，如 '三月廿九'"},
                    "yi":      {"type": "array", "items": {"type": "string"},
                                "description": "宜（3-5 项；传统表达，如「祭祀」「嫁娶」「出行」「修造」）"},
                    "ji":      {"type": "array", "items": {"type": "string"},
                                "description": "忌（3-5 项；传统表达）"},
                },
                "required": ["date", "weekday", "yi", "ji"],
            },
        },
        "holidays_spain": {
            "type": "array",
            "description": "本周内的西班牙官方/马德里地区节假日；如无则空数组",
            "items": {
                "type": "object",
                "properties": {
                    "date":    {"type": "string"},
                    "name_es": {"type": "string", "description": "西语名称"},
                    "name_cn": {"type": "string", "description": "中文名称"},
                    "scope":   {"type": "string", "description": "全国 / 马德里大区 / 其他"},
                },
                "required": ["date", "name_es", "name_cn"],
            },
        },
        "holidays_china": {
            "type": "array",
            "description": "本周内的中国大陆法定节假日；如无则空数组",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["date", "name"],
            },
        },
        "holidays_taiwan": {
            "type": "array",
            "description": "本周内的台湾国定假日；如无则空数组",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["date", "name"],
            },
        },
    },
    "required": ["almanac_days", "holidays_spain", "holidays_china", "holidays_taiwan"],
}


_SYSTEM = """你是中国传统黄历（宜忌）+ 公历节日查询助手。
给定一周（周一到周日）的日期范围，调 record_almanac 工具填写：

1. 每天的农历日期 + 宜/忌（每项 3-5 个，使用传统表达，如「祭祀」「嫁娶」「出行」「修造」「动土」「安葬」「祈福」）
2. 该周内**西班牙**（含 Madrid 大区）的官方/法定假日（含西语原名 + 中文译名）
3. 该周内**中国大陆**的法定节假日
4. 该周内**台湾**的国定假日

硬性要求：
- 不得编造没有的假日。某地本周无假日就给空数组。
- 日期严格 YYYY-MM-DD。
- 黄历宜忌按通行《通胜》传统体系给出常见项即可，不要给玄学解释。
"""


def fetch_week_almanac(llm, *, week_iso: str) -> dict[str, Any]:
    """调一次 LLM 拿整周黄历 + 三地节假日。
    week_iso 形如 'YYYY-Www'。失败返回空 dict（调用方决定是否渲染）。"""
    week_start = _parse_iso_week_monday(week_iso)
    if week_start is None:
        logger.warning(f"week_iso={week_iso!r} 无法解析，跳过黄历")
        return {}
    week_end = week_start + timedelta(days=6)

    user_prompt = (
        f"周次范围: {week_start.isoformat()}（周一）至 {week_end.isoformat()}（周日）\n"
        f"请按 record_almanac 工具填写完整的 7 天黄历 + 西班牙/中国/台湾本周节假日。"
    )

    try:
        data = llm.complete_with_tool(
            _SYSTEM, user_prompt,
            tool_name="record_almanac",
            tool_description="记录一周黄历宜忌 + 西/中/台三地节假日",
            input_schema=_TOOL_SCHEMA,
        )
    except Exception as e:
        logger.warning(f"黄历查询失败: {e}")
        return {}

    # 防御性过滤：LLM 偶尔会给周边界外的节假日（如把"上周末"的算进来）
    def _in_week(d_str: str) -> bool:
        try:
            return week_start <= date.fromisoformat(d_str) <= week_end
        except (ValueError, TypeError):
            return False

    for key in ("almanac_days", "holidays_spain", "holidays_china", "holidays_taiwan"):
        items = data.get(key, []) or []
        filtered = [it for it in items if _in_week(it.get("date", ""))]
        dropped = len(items) - len(filtered)
        if dropped:
            logger.info(f"{key}: 丢弃 {dropped} 个超出周范围 ({week_start} ~ {week_end}) 的条目")
        data[key] = filtered

    logger.info(
        f"已加载黄历: {len(data.get('almanac_days', []))} 天 / "
        f"ES={len(data.get('holidays_spain', []))} "
        f"CN={len(data.get('holidays_china', []))} "
        f"TW={len(data.get('holidays_taiwan', []))}"
    )
    return data


def _parse_iso_week_monday(week_iso: str) -> date | None:
    """'2026-W19' → 该周周一日期。"""
    if not week_iso or "-W" not in week_iso:
        return None
    try:
        year_s, week_s = week_iso.split("-W", 1)
        return date.fromisocalendar(int(year_s), int(week_s), 1)
    except (ValueError, TypeError):
        return None
