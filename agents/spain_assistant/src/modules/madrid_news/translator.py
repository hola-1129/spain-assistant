"""用 LLM 生成每条新闻的中文解读（游客视角 + 定居者视角 + 日历 + 地点）。"""

import json
from openai import OpenAI
from src.core import config
from src.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """你是马德里本地生活顾问，专门为在西班牙生活或旅游的华人解读公共信息。

请根据提供的西班牙语新闻，生成以下结构化内容（全部中文）。

严格输出 JSON，字段如下：
{
  "chinese_title": "简洁有力的中文标题（不超过30字）",
  "one_line_summary": "一句话说明这条新闻对普通读者的实际意义（不超过50字）",
  "professional_overview": "从与这条新闻领域最相关的专业人士视角（如城市规划师、教育专家、医疗顾问、交通工程师等），专业归纳新闻的核心要点、背景脉络和潜在影响。（3-4句，专业且易懂，点明行业背景）",
  "key_points": {
    "time": "时间（原文未说明写'原文未说明'）",
    "location": "地点（原文未说明写'原文未说明'）",
    "audience": "涉及人群",
    "change": "具体变化或内容",
    "practical": "费用/报名/开放时间等（无则写'原文未说明'）"
  },
  "local_perspective": "从马德里本地居民视角解读这条新闻（3-4句：这在本地日常生活里意味着什么、是否是常规活动、本地人通常如何参与、有无需要注意的点）",
  "tourist_advice": "给华人游客的具体建议，每条以'-'开头换行（涉及：是否值得游客关注、是否适合短期行程安排、是否需要提前预约、是否可能影响交通、是否适合带孩子去体验）",
  "resident_advice": "给本地华人定居者的具体建议，每条以'-'开头换行（涉及：是否影响日常出行、是否适合周末家庭活动、是否涉及孩子/学校/社区资源、是否值得加入日历提醒、是否需要提前报名或办理手续）",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "event": {
    "has_event": false,
    "title": "",
    "start_date": "",
    "end_date": "",
    "start_time": "",
    "end_time": "",
    "location": "",
    "description": ""
  },
  "location_info": {
    "name": "",
    "address": "",
    "district": "",
    "google_maps_query": ""
  }
}

字段规则：
- event.has_event：只有原文有明确日期/时间的活动时才为 true
- event.start_date / end_date：格式 YYYY-MM-DD，单日活动 end_date 与 start_date 相同
- event.start_time / end_time：24小时制 HH:MM，无则为空字符串
- location_info.google_maps_query：适合在 Google Maps 搜索、能精确找到地点的字符串。优先级：① 场馆名 + 完整街道地址（如 "Palacio de Cibeles, Plaza de Cibeles 1, Madrid"）② 场馆名 + 行政区 + Madrid（如 "Estadio Wanda Metropolitano, San Blas, Madrid"）③ 仅场馆名 + Madrid（如 "Parque del Retiro Madrid"）。地点不明确时写空字符串，不要只写 "Madrid" 或 "España"
- tourist_advice 和 resident_advice：必须具体，结合新闻实际内容，不能泛泛而谈
- 所有字段不得留空：不确定的信息写"原文未说明"
- 只输出 JSON，不要任何其他文字"""

_FALLBACK = {
    "chinese_title": "",
    "one_line_summary": "原文内容获取受限，请查看原文链接了解详情。",
    "professional_overview": "",
    "key_points": {
        "time": "原文未说明",
        "location": "原文未说明",
        "audience": "原文未说明",
        "change": "原文未说明",
        "practical": "原文未说明",
    },
    "local_perspective": "当前暂时无法生成本地视角解读，请参阅原文。",
    "tourist_advice": "- 请直接查看原文获取详情。",
    "resident_advice": "- 请直接查看原文获取详情。",
    "keywords": [],
    "event": {
        "has_event": False, "title": "", "start_date": "", "end_date": "",
        "start_time": "", "end_time": "", "location": "", "description": "",
    },
    "location_info": {"name": "", "address": "", "district": "", "google_maps_query": ""},
}


def _build_client() -> OpenAI:
    base_url = config.env(config.get("llm.base_url_env", "LLM_BASE_URL"))
    api_key = config.env(config.get("llm.api_key_env", "LLM_API_KEY"), "placeholder")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _call_llm(client: OpenAI, source_text: str, model: str, max_tokens: int) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": source_text},
        ],
        temperature=config.get("llm.temperature", 0.3),
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _normalize_zh(zh: dict) -> dict:
    """确保文本字段始终是字符串，防止 LLM 返回列表导致模板崩溃。"""
    for key in ("local_perspective", "tourist_advice", "resident_advice", "professional_overview"):
        val = zh.get(key, "")
        if isinstance(val, list):
            zh[key] = "\n".join(str(v) for v in val if v)
        elif not isinstance(val, str):
            zh[key] = str(val) if val else ""
    return zh


def translate_article(article: dict) -> dict:
    source_text = (
        f"标题（西语）：{article.get('title', '')}\n"
        f"摘要：{article.get('summary', '')}\n"
        f"正文：{article.get('content', '')[:3000]}\n"
        f"分类：{article.get('category', '')}\n"
        f"区域：{article.get('district', '')}\n"
        f"发布日期：{article.get('date', '')}"
    )

    client = _build_client()
    model = config.get("llm.model_translate", "qwen-plus")

    # 第一次尝试：完整输出
    try:
        raw = _call_llm(client, source_text, model, max_tokens=4000)
        zh = _normalize_zh(json.loads(raw))
        zh["chinese_title"] = zh.get("chinese_title") or article.get("title", "")
        article["zh"] = zh
        log.info(f"[translator] 生成完成: {zh.get('chinese_title', '')[:45]}")
        return article
    except json.JSONDecodeError as e:
        log.warning(f"[translator] JSON 解析失败，重试: {e}")

    # 第二次尝试：提高 max_tokens
    try:
        raw = _call_llm(client, source_text, model, max_tokens=6000)
        zh = _normalize_zh(json.loads(raw))
        zh["chinese_title"] = zh.get("chinese_title") or article.get("title", "")
        article["zh"] = zh
        log.info(f"[translator] 重试成功: {zh.get('chinese_title', '')[:45]}")
        return article
    except Exception as e:
        log.warning(f"[translator] 两次尝试均失败，使用 fallback: {e}")

    fallback = dict(_FALLBACK)
    fallback["chinese_title"] = article.get("title", "")
    article["zh"] = fallback
    return article
