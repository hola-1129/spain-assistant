"""单条事项的结构化抽取 + 全局分类。

- extract_event(): 给定一个链接 PDF 的文本，返回结构化字段字典
- classify_audience(): 把抽取出的 audience 标签归到固定分类桶
- iso_event_dt(): 把抽取的日期+时间合成可写入 ICS 的 datetime
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Any

from utils.logger import setup_logger

logger = setup_logger("extractor")


# ---------- schema ----------

@dataclass
class EventFields:
    title_es:           str = ""
    title_cn:           str = ""
    audience_es:        str = ""        # 西/英原文（如 "1º PRIMARIA"）
    audience_cn:        str = ""        # 中文（如 "一年级"）
    date:               str = ""        # YYYY-MM-DD（原文未说明留空）
    time_start:         str = ""        # HH:MM
    time_end:           str = ""        # HH:MM
    location_es:        str = ""
    location_cn:        str = ""
    cost:               str = ""        # 原文费用描述；不确定写空
    materials_es:       str = ""
    materials_cn:       str = ""
    deadline:           str = ""        # YYYY-MM-DD
    signup_required:    str = ""        # "是" / "否" / "原文未说明"
    signup_method:      str = ""        # 报名方式（中西双语，必要时拼接）
    payment_required:   str = ""
    parents_can_attend: str = ""        # "是" / "否" / "原文未说明"
    student_prepare:    str = ""
    parent_action:      str = ""        # 家长需要做什么
    notes:              str = ""        # ⚠️ 注意事项
    keywords_es:        list[str] = field(default_factory=list)
    raw_excerpt:        str = ""        # 原文关键句（最多 ~300 字）


# ---------- LLM 抽取 ----------

_SYSTEM_PROMPT = """你是中国家长的西班牙学校通知翻译/解读助手。
你会拿到一份学校具体事项 PDF 的纯文本（西/英语），以及主 briefing 中的标题与适用阶段。
任务：抽取家长行动决策所需的关键信息，调用 record_event 工具填写各字段。

硬性要求：
1. 不准编造。原文没说明的字段一律留空（空字符串或空列表），不要猜。
2. 日期一律 YYYY-MM-DD；时间一律 HH:MM（24h）。日期范围只取首日。
3. signup_required / payment_required / parents_can_attend 取值固定：
   "是" / "否" / "原文未说明"（任选其一，留空也可）
4. 中文表达自然，不要机器翻译腔；技术名词保留西/英语原文括注。
5. raw_excerpt 必须从原文里截最相关的一句或一段（≤300 字），不得改写。
6. keywords_es 列出 3–6 个西语/英语关键词，方便家长对照原文。
"""

_EXTRACT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title_es":           {"type": "string", "description": "原文标题（西/英语）"},
        "title_cn":           {"type": "string", "description": "中文标题"},
        "audience_es":        {"type": "string", "description": "适用对象原文，如 '4º PRIMARIA'"},
        "audience_cn":        {"type": "string", "description": "适用对象中文翻译"},
        "date":               {"type": "string", "description": "YYYY-MM-DD；范围只取首日；不确定留空"},
        "time_start":         {"type": "string", "description": "HH:MM 24h；不确定留空"},
        "time_end":           {"type": "string", "description": "HH:MM 24h；不确定留空"},
        "location_es":        {"type": "string"},
        "location_cn":        {"type": "string"},
        "cost":               {"type": "string", "description": "费用说明，原文未提则留空"},
        "materials_es":       {"type": "string"},
        "materials_cn":       {"type": "string"},
        "deadline":           {"type": "string", "description": "YYYY-MM-DD"},
        "signup_required":    {"type": "string", "description": "是 / 否 / 原文未说明"},
        "signup_method":      {"type": "string"},
        "payment_required":   {"type": "string", "description": "是 / 否 / 原文未说明"},
        "parents_can_attend": {"type": "string", "description": "是 / 否 / 原文未说明"},
        "student_prepare":    {"type": "string"},
        "parent_action":      {"type": "string", "description": "家长需要做的具体事项；中文表达"},
        "notes":              {"type": "string", "description": "重要注意事项；用 ⚠️ 提示"},
        "keywords_es":        {"type": "array", "items": {"type": "string"},
                               "description": "3–6 个西语/英语关键词"},
        "raw_excerpt":        {"type": "string", "description": "原文摘录（≤300 字），原样不改写"},
    },
    "required": ["title_es", "title_cn"],
}


def extract_event(llm, *, briefing_title: str, briefing_stage: str,
                  pdf_text: str, max_chars: int = 12000) -> EventFields:
    """调 LLM 把单个 PDF 抽成结构化字段。"""
    if not pdf_text.strip():
        return EventFields(title_es=briefing_title, audience_es=briefing_stage,
                           notes="链接 PDF 内容为空")

    # 控制 token：超长截断，但保留首尾
    if len(pdf_text) > max_chars:
        head = pdf_text[: max_chars - 1500]
        tail = pdf_text[-1500:]
        pdf_text = head + "\n...[中间省略]...\n" + tail

    user_prompt = (
        f"[主 briefing 中的标题]\n{briefing_title}\n\n"
        f"[适用阶段（原文）]\n{briefing_stage}\n\n"
        f"[事项 PDF 全文]\n{pdf_text}\n\n"
        f"请调用 record_event 工具填写抽取结果。"
    )

    try:
        data = llm.complete_with_tool(
            _SYSTEM_PROMPT, user_prompt,
            tool_name="record_event",
            tool_description="记录事项的结构化字段，所有字段都符合 system 中的硬性要求",
            input_schema=_EXTRACT_TOOL_SCHEMA,
        )
    except Exception as e:
        logger.error(f"LLM 抽取失败: {e}")
        return EventFields(
            title_es=briefing_title,
            audience_es=briefing_stage,
            notes=f"LLM 抽取失败：{e}",
        )

    # 转 dataclass，过滤未知字段
    valid_keys = {f for f in EventFields.__dataclass_fields__}
    cleaned = {k: v for k, v in data.items() if k in valid_keys}
    if isinstance(cleaned.get("keywords_es"), str):
        cleaned["keywords_es"] = [s.strip() for s in cleaned["keywords_es"].split(",") if s.strip()]
    return EventFields(**cleaned)


# ---------- 分类 ----------

CATEGORY_GENERAL          = "全校通用通知"
CATEGORY_INFANTIL         = "Infantil / 幼儿园"
CATEGORY_PRIMARIA         = "Primaria / 小学"
CATEGORY_PREPARATORY      = "Preparatory"
CATEGORY_ESO              = "ESO / 中学"
CATEGORY_BACHILLERATO     = "Bachillerato / 高中"
CATEGORY_IBDP             = "IBDP"
CATEGORY_PARENT_ACTION    = "家长需要行动的事项"
CATEGORY_INFO_ONLY        = "仅供了解的信息"

ALL_CATEGORIES = [
    CATEGORY_GENERAL,
    CATEGORY_INFANTIL,
    CATEGORY_PRIMARIA,
    CATEGORY_PREPARATORY,
    CATEGORY_ESO,
    CATEGORY_BACHILLERATO,
    CATEGORY_IBDP,
    CATEGORY_PARENT_ACTION,
    CATEGORY_INFO_ONLY,
]


def classify_audience(audience_es: str, audience_cn: str = "") -> list[str]:
    """根据 audience 字段返回该事项归属的分类列表（一个事项可同时进多个）。"""
    txt = f"{audience_es} {audience_cn}".upper()
    cats: list[str] = []

    if "GENERAL" in txt or "全校" in txt:
        cats.append(CATEGORY_GENERAL)
    if "INFANTIL" in txt or "幼儿" in txt:
        cats.append(CATEGORY_INFANTIL)
    if "PRIMARIA" in txt or "小学" in txt:
        cats.append(CATEGORY_PRIMARIA)
    if "PREPARATORY" in txt:
        cats.append(CATEGORY_PREPARATORY)
    if "ESO" in txt or "中学" in txt:
        cats.append(CATEGORY_ESO)
    if "BACHILLERATO" in txt or "高中" in txt:
        cats.append(CATEGORY_BACHILLERATO)
    if "IBDP" in txt or "IB DP" in txt:
        cats.append(CATEGORY_IBDP)

    if not cats:
        cats.append(CATEGORY_INFO_ONLY)
    return cats


def needs_parent_action(ev: EventFields) -> bool:
    if ev.parent_action.strip():
        return True
    if ev.signup_required == "是" or ev.payment_required == "是":
        return True
    if ev.deadline.strip():
        return True
    return False


# ---------- 时间 ----------

def parse_event_datetime(ev: EventFields, tz_name: str) -> tuple[datetime | None, datetime | None, bool]:
    """返回 (begin, end, all_day)。失败返回 (None, None, False)。"""
    if not ev.date:
        return None, None, False
    try:
        d = datetime.strptime(ev.date, "%Y-%m-%d").date()
    except ValueError:
        return None, None, False

    t_start = _parse_hhmm(ev.time_start)
    t_end   = _parse_hhmm(ev.time_end)

    if t_start is None:
        # 全天事件
        begin = datetime.combine(d, time(0, 0))
        end   = datetime.combine(d, time(23, 59))
        return begin, end, True

    begin = datetime.combine(d, t_start)
    end   = datetime.combine(d, t_end) if t_end else begin
    return begin, end, False


def _parse_hhmm(s: str) -> time | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%H:%M", "%H.%M", "%H%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


# ---------- 序列化 ----------

def event_to_dict(ev: EventFields) -> dict[str, Any]:
    return asdict(ev)


def event_from_dict(d: dict[str, Any]) -> EventFields:
    valid = {k: v for k, v in d.items() if k in EventFields.__dataclass_fields__}
    return EventFields(**valid)


__all__ = [
    "EventFields", "extract_event",
    "classify_audience", "needs_parent_action", "parse_event_datetime",
    "event_to_dict", "event_from_dict",
    "CATEGORY_GENERAL", "CATEGORY_INFANTIL", "CATEGORY_PRIMARIA",
    "CATEGORY_PREPARATORY", "CATEGORY_ESO", "CATEGORY_BACHILLERATO",
    "CATEGORY_IBDP", "CATEGORY_PARENT_ACTION", "CATEGORY_INFO_ONLY",
    "ALL_CATEGORIES",
]
