"""从 fetcher 原始数据中补全字段（content / images / category / district）。"""

import time
from src.modules.madrid_news.fetcher import fetch_article_content
from src.core.logger import get_logger
from src.core.utils import safe_strip

log = get_logger(__name__)


def enrich_articles(articles: list[dict]) -> list[dict]:
    """对列表中每条新闻抓取正文，单条失败不中断整体。"""
    enriched = []
    for i, art in enumerate(articles):
        try:
            detail = fetch_article_content(art["url"])
            art["content"] = safe_strip(detail.get("content", ""))
            art["images"] = detail.get("images", [])
            art["category"] = safe_strip(detail.get("category", art.get("category", "")))
            art["district"] = safe_strip(detail.get("district", art.get("district", "")))
            enriched.append(art)
            if i < len(articles) - 1:
                time.sleep(1)
        except Exception as e:
            log.warning(f"[parser] 正文抓取失败，使用列表页数据（{art.get('title', '')[:40]}）: {e}")
            art.setdefault("content", "")
            art.setdefault("images", [])
            art.setdefault("category", "")
            art.setdefault("district", "")
            enriched.append(art)
    return enriched
