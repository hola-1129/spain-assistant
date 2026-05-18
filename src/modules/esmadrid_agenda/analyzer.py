"""
LLM 对 esmadrid 活动做分类、重要性评级和中文摘要。
同时提供不依赖 LLM 的纯规则 calculateEventExpiry()。
"""

import json
from datetime import date, timedelta

from openai import OpenAI
from src.core import config
from src.core.logger import get_logger
from src.core.utils import today_str

log = get_logger(__name__)

_TAGS = [
    "展览", "艺术", "音乐", "戏剧", "亲子", "节庆", "美食",
    "购物", "市集", "体育", "旅游", "周末", "免费活动",
]

_AUDIENCE = [
    "华人家庭", "游客", "长期定居", "孩子", "艺术爱好者", "购物", "年轻人",
]

_SYSTEM_PROMPT = f"""你是马德里本地活动专家，专门为在马德里生活或旅游的华人筛选并解读活动信息。

请分析下面的西班牙语活动信息，严格输出 JSON：

{{
  "tags": ["标签1", "标签2"],
  "importance": "A",
  "audience": ["适合人群1", "适合人群2"],
  "chinese_title": "中文活动标题（不超过30字）",
  "one_line_summary": "一句话说明活动亮点及对华人的实际价值（不超过60字）",
  "price_info": "价格信息（免费/需购票/价格区间，原文未提及写'原文未说明'）",
  "professional_overview": "从文化/艺术/活动策划专家视角，归纳此活动的文化定位、艺术价值、策划亮点或社区意义。（2-3句，专业扼要，点明活动在马德里文化版图中的位置）",
  "local_perspective": "马德里本地人视角：这个活动在马德里文化/社区生活中意味着什么？本地人如何看待/参与？有什么不为外地人所知的本地知识或传统背景？（2-3句，有生活气息）",
  "tourist_advice": "给游客的建议（bullet list，每条一行，'-'开头）：\\n- 是否值得专程前往\\n- 是否需要提前购票/预约\\n- 最佳观看/参与时间\\n- 是否有语言障碍\\n- 交通提示",
  "resident_advice": "给在马德里长居华人的建议（bullet list，每条一行，'-'开头）：\\n- 是否影响出行/交通\\n- 是否适合带孩子\\n- 是否值得加入日历\\n- 是否有华人社区参与机会\\n- 其他实用提示"
}}

可选标签（可多选，1-4个）：{json.dumps(_TAGS, ensure_ascii=False)}
可选适合人群（可多选，1-4个）：{json.dumps(_AUDIENCE, ensure_ascii=False)}

重要性规则：
- S：城市级节庆（San Isidro等）、全国知名大型活动、高价值免费展览、官方重点亲子活动
- A：普通展览/演出/市集/周末活动、值得关注的付费活动
- B：小型商业宣传、重复性日常活动、内容一般的活动

判断标准：
- 是否免费且质量高 → 倾向 S/A
- 是否适合家庭携孩子 → 倾向 S/A
- 是否只是商业推广 → 倾向 B
- 活动规模是否城市级别 → 倾向 S

仅输出 JSON。"""


def _build_client() -> OpenAI:
    base_url = config.env(config.get("llm.base_url_env", "LLM_BASE_URL"))
    api_key = config.env(config.get("llm.api_key_env", "LLM_API_KEY"), "placeholder")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def classify_event_tags(event: dict) -> dict:
    """LLM 分类：写入 tags / importance / audience / zh / price_info。"""
    source_text = (
        f"活动标题：{event.get('title', '')}\n"
        f"分类：{event.get('category', '')}\n"
        f"日期：{event.get('date_start', '')} → {event.get('date_end', '')}\n"
        f"地点：{event.get('location_name', '')}（{event.get('address', '')}）\n"
        f"摘要：{event.get('summary', '')}\n"
        f"正文：{event.get('body_text', '')[:1000]}"
    )
    try:
        client = _build_client()
        resp = client.chat.completions.create(
            model=config.get("llm.model_extract", "qwen-plus"),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": source_text},
            ],
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        event["tags"] = result.get("tags") or ["艺术"]
        event["importance"] = result.get("importance", "B")
        event["audience"] = result.get("audience") or []
        event["price_info"] = result.get("price_info", "原文未说明")
        event["zh"] = {
            "chinese_title": result.get("chinese_title") or event.get("title", ""),
            "one_line_summary": result.get("one_line_summary", ""),
            "professional_overview": result.get("professional_overview", ""),
            "local_perspective": result.get("local_perspective", ""),
            "tourist_advice": result.get("tourist_advice", ""),
            "resident_advice": result.get("resident_advice", ""),
        }
        log.info(f"[esmadrid/analyzer] [{event['importance']}] {event['title'][:45]}")
    except Exception as e:
        log.warning(f"[esmadrid/analyzer] 分析失败（默认值）: {e}")
        event.setdefault("tags", ["艺术"])
        event.setdefault("importance", "B")
        event.setdefault("audience", [])
        event.setdefault("price_info", "原文未说明")
        event.setdefault("zh", {
            "chinese_title": event.get("title", ""),
            "one_line_summary": "",
            "professional_overview": "",
            "local_perspective": "",
            "tourist_advice": "",
            "resident_advice": "",
        })
    return event


def calculate_event_expiry(event: dict) -> tuple[bool, str, str, str]:
    """
    纯规则计算有效期，不依赖 LLM。

    返回: (is_highlight, valid_from, valid_until, expiry_reason)
    - is_highlight: 仅 S 级活动进入跨日 highlight store
    """
    today = today_str()
    importance = event.get("importance", "B")
    date_end = (event.get("date_end") or "").strip()
    date_start = (event.get("date_start") or "").strip()

    if date_end and date_end >= today:
        valid_until = date_end
        reason = "event_end_date"
    elif date_start and date_start >= today:
        valid_until = date_start
        reason = "event_start_date"
    else:
        valid_until = (date.fromisoformat(today) + timedelta(days=3)).isoformat()
        reason = "default_3_days"

    is_highlight = importance == "S"
    valid_from = today if is_highlight else ""
    return is_highlight, valid_from, valid_until, reason
