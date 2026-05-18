"""Madrid News 模块主入口：串联 fetch → dedup → parse → analyze → translate → save。"""

from src.core import config
from src.core.logger import get_logger
from src.core.storage import load_state, save_state, save_raw, save_processed
from src.core.utils import run_id, today_str
from src.modules.madrid_news.fetcher import fetch_article_list
from src.modules.madrid_news.parser import enrich_articles
from src.modules.madrid_news.deduper import filter_new, commit_seen
from src.modules.madrid_news.analyzer import analyze_article
from src.modules.madrid_news.translator import translate_article
from src.modules.madrid_news.highlight_manager import tag_highlights, update_highlight_store
from src.modules.madrid_news.area_tagger import tag_area

log = get_logger(__name__)


def run() -> dict:
    """
    执行一次完整的 Madrid News 抓取流程。
    返回 {"new_count": int, "articles": list, "errors": list}
    """
    rid = run_id()
    errors = []
    log.info(f"[madrid_news] === 开始运行 run_id={rid} ===")

    # 1. 抓取列表
    try:
        raw_articles = fetch_article_list()
    except Exception as e:
        msg = f"列表页抓取失败: {e}"
        log.error(f"[madrid_news] {msg}")
        return {"new_count": 0, "articles": [], "errors": [msg]}

    save_raw("madrid_news", raw_articles, rid)

    # 2. 去重
    state = load_state()
    new_articles, skipped = filter_new(raw_articles, state)

    if not new_articles:
        log.info("[madrid_news] 无新增新闻，任务结束")
        return {"new_count": 0, "articles": [], "errors": [], "skipped": skipped}

    # 3. 抓取正文
    new_articles = enrich_articles(new_articles)

    # 4. 分析 + 翻译（单条失败不影响整体）
    processed = []
    for art in new_articles:
        try:
            art = analyze_article(art)
            art = translate_article(art)
            art = tag_area(art)
            processed.append(art)
        except Exception as e:
            errors.append(f"处理失败 [{art.get('title', '')[:40]}]: {e}")
            log.warning(f"[madrid_news] {errors[-1]}")
            art.setdefault("labels", ["低相关/仅归档"])
            art.setdefault("importance", "C")
            art.setdefault("zh", {"chinese_title": art.get("title", ""), "one_line_summary": ""})
            art.setdefault("area_label", "Madrid")
            art.setdefault("area_district", None)
            art.setdefault("area_type", "unknown")
            processed.append(art)

    # 4b. 标记重点关注并持久化到 store
    tag_highlights(processed)
    update_highlight_store(processed)

    # 5. 持久化去重状态
    commit_seen(processed, state)
    state["last_run"]["madrid_news"] = {"run_id": rid, "date": today_str(), "count": len(processed)}
    save_state(state)

    # 6. 保存处理结果
    save_processed("madrid_news", processed, rid)

    log.info(f"[madrid_news] === 完成 新增:{len(processed)} 跳过:{skipped} 错误:{len(errors)} ===")
    return {"new_count": len(processed), "articles": processed, "errors": errors, "skipped": skipped}
