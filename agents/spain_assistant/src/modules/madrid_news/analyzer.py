"""用 LLM 对每条新闻进行标签分类和重要性评级。"""

import json
from openai import OpenAI
from src.core import config
from src.core.logger import get_logger
from src.core.utils import safe_strip

log = get_logger(__name__)

_LABELS = [
    "亲子", "教育", "交通", "市政", "医疗",
    "文化", "艺术", "体育", "节日", "公园",
    "治安", "就业", "城市建设",
    "游客相关", "本地定居者相关", "低相关",
]

_SYSTEM_PROMPT = f"""你是马德里本地生活专家，为在西班牙生活的华人筛选新闻。

请分析下面的新闻，完成两件事：

1. 从以下标签中选1-3个最合适的：
{json.dumps(_LABELS, ensure_ascii=False)}

2. 给出重要性等级（只选一个）：
- S：必须关注，直接影响日常安排或重要权益
- A：值得关注，适合华人家庭生活决策
- B：有用信息，可参考但不紧急
- C：普通市政/行政新闻，与家庭生活无直接关系

判断标准：
- 涉及孩子/学校/家庭/出行/健康且华人能直接参与 → S 或 A
- 文化/体育/节日活动，华人可选择参与 → A 或 B
- 纯行政/政治/商业，与普通居民无关 → C
- 有明确日期的活动，extra +1级别
- 游客相关：适合旅游者参与的加 "游客相关" 标签
- 长期居住者关注的生活事项加 "本地定居者相关" 标签

严格输出 JSON：
{{
  "labels": ["标签1"],
  "importance": "A",
  "reason": "一句话理由"
}}"""


def _build_client() -> OpenAI:
    base_url = config.env(config.get("llm.base_url_env", "LLM_BASE_URL"))
    api_key = config.env(config.get("llm.api_key_env", "LLM_API_KEY"), "placeholder")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def analyze_article(article: dict) -> dict:
    text = (
        f"标题：{article.get('title', '')}\n"
        f"摘要：{article.get('summary', '')}\n"
        f"正文片段：{article.get('content', '')[:600]}"
    )
    try:
        client = _build_client()
        resp = client.chat.completions.create(
            model=config.get("llm.model_extract", "qwen-plus"),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        article["labels"] = result.get("labels", ["低相关"])
        article["importance"] = result.get("importance", "C")
        article["importance_reason"] = safe_strip(result.get("reason", ""))
        log.info(f"[analyzer] {article['title'][:40]} → {article['importance']}")
    except Exception as e:
        log.warning(f"[analyzer] 分析失败（使用默认值）: {e}")
        article.setdefault("labels", ["低相关"])
        article.setdefault("importance", "C")
        article.setdefault("importance_reason", "")
    return article
