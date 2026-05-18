"""LLM 对 La Moncloa 新闻做标签分类、重要性评级和中文摘要。"""

import json
from openai import OpenAI
from src.core import config
from src.core.logger import get_logger

log = get_logger(__name__)

_TAGS = [
    "政治", "经济", "商贸", "交通", "教育", "移民", "医疗",
    "住房", "科技", "能源", "文化", "旅游", "安全", "农业", "欧盟事务",
]

_SYSTEM_PROMPT = f"""你是西班牙政府新闻分析专家，专门为在西班牙生活的华人解读官方政策信息。

请分析下面的西班牙语政府新闻，严格输出 JSON：

{{
  "tags": ["标签"],
  "importance": "A",
  "importance_reason": "一句话理由",
  "chinese_title": "中文标题（不超过30字）",
  "one_line_summary": "一句话说明对华人的实际影响（不超过60字）",
  "professional_overview": "从政策分析师或相关领域专家（法律、经济、社会政策、移民事务等）视角，专业归纳这条政府新闻的核心内容、政策意图和实际影响。（3-4句，专业扼要，点明政策背景）",
  "local_perspective": "西班牙本地人视角：这条政策/新闻在西班牙社会语境下意味着什么？本地民众如何看待？是否引发争议？有何历史背景或社会意义？对马德里普通居民的日常影响是什么？（3-5句，有温度和场景感）",
  "china_resident_angle": "对在西班牙华人（移民/留学生/经商者/定居者）的具体影响：是否需要采取行动？有无时间节点？哪些人群受影响？（3-4句，具体）",
  "deadline_date": "申请截止/活动结束/政策生效日，格式 YYYY-MM-DD；不明确写空字符串"
}}

可选标签（可多选，1-3个）：{json.dumps(_TAGS, ensure_ascii=False)}

重要性规则：
- S：全国政策/法律变化、税务、移民、教育改革、医疗政策、住房法规、重大交通/安全事件（直接影响居民权益）
- A：补贴申请开放、公共服务变化、安全提醒、对企业/居民有明显影响的措施
- B：普通部委动态、国际会议、纯外交/宣传类新闻（对普通居民无直接影响）

判断时重点考虑：① 是否影响华人日常生活 ② 是否需要主动行动 ③ 是否有时间限制

仅输出 JSON，不要其他内容。"""

_FALLBACK_ZH = {
    "chinese_title": "",
    "one_line_summary": "请查阅原文了解详情。",
    "professional_overview": "",
    "china_resident_angle": "请直接查阅西语原文。",
}


def _build_client() -> OpenAI:
    base_url = config.env(config.get("llm.base_url_env", "LLM_BASE_URL"))
    api_key = config.env(config.get("llm.api_key_env", "LLM_API_KEY"), "placeholder")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def analyze_article(article: dict) -> dict:
    """调用 LLM 分析文章，写入 tags / importance / zh / deadline_date。"""
    source_text = (
        f"部委：{article.get('department', '')}\n"
        f"标题：{article.get('title', '')}\n"
        f"摘要：{article.get('summary', '')}\n"
        f"正文：{article.get('content', '')[:2000]}"
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
            max_tokens=1100,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)

        article["tags"] = result.get("tags") or ["政治"]
        article["importance"] = result.get("importance", "B")
        article["importance_reason"] = result.get("importance_reason", "")
        article["deadline_date"] = (result.get("deadline_date") or "").strip()
        article["zh"] = {
            "chinese_title": result.get("chinese_title") or article.get("title", ""),
            "one_line_summary": result.get("one_line_summary", ""),
            "professional_overview": result.get("professional_overview", ""),
            "local_perspective": result.get("local_perspective", ""),
            "china_resident_angle": result.get("china_resident_angle", ""),
        }
        log.info(f"[lamoncloa/analyzer] [{article['importance']}] {article['title'][:45]}")
    except Exception as e:
        log.warning(f"[lamoncloa/analyzer] 分析失败（使用默认值）: {e}")
        article.setdefault("tags", ["政治"])
        article.setdefault("importance", "B")
        article.setdefault("importance_reason", "")
        article.setdefault("deadline_date", "")
        fb = dict(_FALLBACK_ZH)
        fb["chinese_title"] = article.get("title", "")
        article.setdefault("zh", fb)
    return article
