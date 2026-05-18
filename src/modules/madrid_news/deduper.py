"""去重：通过 title+date hash 过滤已处理过的新闻。"""

from src.core.storage import compute_hash, is_seen, mark_seen
from src.core.logger import get_logger

log = get_logger(__name__)


def filter_new(articles: list[dict], state: dict) -> tuple[list[dict], int]:
    """返回 (新文章列表, 跳过数量)。同时把 hash_id 写入每条新文章。"""
    new_articles = []
    skipped = 0

    for art in articles:
        h = compute_hash(art.get("title", ""), art.get("date", ""))
        art["hash_id"] = h

        if is_seen(h, state):
            skipped += 1
        else:
            new_articles.append(art)

    log.info(f"[deduper] 新增: {len(new_articles)} 条，跳过（已处理）: {skipped} 条")
    return new_articles, skipped


def commit_seen(articles: list[dict], state: dict):
    """将本批新文章标记为已处理。"""
    for art in articles:
        h = art.get("hash_id", "")
        if h:
            mark_seen(h, state, meta={"title": art.get("title", ""), "date": art.get("date", "")})
