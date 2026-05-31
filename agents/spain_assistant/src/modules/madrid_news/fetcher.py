"""抓取 diario.madrid.es 新闻列表及单篇正文。

使用 curl-cffi 以 Chrome TLS 指纹绕过 Akamai bot 检测。
支持分页抓取、OG 图片提取、西语日期解析。
"""

import re
import time
from datetime import date, datetime
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from src.core import config
from src.core.logger import get_logger
from src.core.utils import safe_strip, now_madrid

log = get_logger(__name__)

_BASE_URL = "https://diario.madrid.es"
_SOURCE_URL = config.get("modules.madrid_news.source_url", "https://diario.madrid.es/blog/notas-de-prensa/")
_TIMEOUT = config.get("modules.madrid_news.request_timeout", 30)
_RETRIES = config.get("modules.madrid_news.retry_attempts", 3)
_RETRY_DELAY = config.get("modules.madrid_news.retry_delay", 5)
_IMPERSONATE = "chrome124"

_BAD_IMG_PATTERNS = ("logo", "icon", "avatar", "social", "share", "emoji",
                     "spinner", "loading", "placeholder", "blank", "pixel",
                     ".svg", ".gif", "gravatar")

_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _get(url: str) -> cffi_requests.Response:
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = cffi_requests.get(url, impersonate=_IMPERSONATE, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"[fetcher] 第{attempt}次请求失败 {url}: {e}")
            if attempt < _RETRIES:
                time.sleep(_RETRY_DELAY)
    raise RuntimeError(f"请求失败（{_RETRIES}次）: {url}")


def _parse_article_date(date_str: str) -> date | None:
    if not date_str:
        return None
    s = date_str.strip()
    # DD/MM/YYYY — diario.madrid.es .post-author format
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except Exception:
            pass
    # ISO datetime: 2026-05-14T...
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except Exception:
            pass
    # "14 de mayo de 2026" or "14 mayo 2026"
    m = re.search(r"(\d{1,2})\s+(?:de\s+)?(\w+)(?:\s+de)?\s+(\d{4})", s.lower())
    if m:
        day, month_str, year = m.group(1), m.group(2), m.group(3)
        month = _SPANISH_MONTHS.get(month_str)
        if month:
            try:
                return date(int(year), month, int(day))
            except Exception:
                pass
    return None


def _parse_list_page(soup) -> list[dict]:
    articles = []
    for item in soup.select("article"):
        try:
            title_el = item.select_one("h2 a, h1 a, .entry-title a")
            if not title_el:
                continue
            title = safe_strip(title_el.get_text())
            url = safe_strip(title_el.get("href", ""))
            if not url or not title:
                continue

            date_el = item.select_one("time, .entry-date, .post-date, .post-author")
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or safe_strip(date_el.get_text())

            summary_el = item.select_one(".entry-summary, .excerpt, p")
            summary = safe_strip(summary_el.get_text()) if summary_el else ""

            # 列表页缩略图
            img_url = ""
            for img_el in item.select("img"):
                src = img_el.get("src") or img_el.get("data-src") or ""
                if src and not any(p in src.lower() for p in _BAD_IMG_PATTERNS):
                    img_url = src
                    break

            articles.append({
                "title": title,
                "url": url,
                "date": date_str,
                "summary": summary,
                "thumbnail": img_url,
                "source": _SOURCE_URL,
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            })
        except Exception as e:
            log.warning(f"[fetcher] 解析列表项失败（跳过）: {e}")
    return articles


def fetch_article_list() -> list[dict]:
    """抓取列表页（含分页），返回所有新闻（含今日判断字段）。"""
    today = now_madrid().date()
    all_articles: list[dict] = []
    page = 1
    max_pages = config.get("modules.madrid_news.max_pages", 5)

    while page <= max_pages:
        url = _SOURCE_URL if page == 1 else f"{_SOURCE_URL}page/{page}/"
        log.info(f"[fetcher] 抓取列表页 {page}: {url}")
        try:
            resp = _get(url)
        except Exception as e:
            log.warning(f"[fetcher] 列表页 {page} 请求失败，停止分页: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        page_articles = _parse_list_page(soup)
        if not page_articles:
            break

        # 标记今日文章
        has_older = False
        for art in page_articles:
            art_date = _parse_article_date(art.get("date", ""))
            art["is_today"] = (art_date == today) if art_date else True  # 无法解析视为今日
            if art_date and art_date < today:
                has_older = True
            all_articles.append(art)

        # 如果当前页已有早于今天的文章，不继续翻页
        if has_older:
            break

        # 检查是否还有下一页
        next_link = soup.select_one("a.next, a.next-posts-link, .nav-previous a, [class*='next'] a")
        if not next_link:
            break

        page += 1
        time.sleep(1)

    log.info(f"[fetcher] 列表页抓取完成，共 {len(all_articles)} 条（今日: {sum(1 for a in all_articles if a.get('is_today'))} 条）")
    return all_articles


def _extract_images(soup) -> list[dict]:
    images = []
    seen_urls: set[str] = set()

    def _add(src: str, alt: str = ""):
        src = src.strip()
        if not src or src in seen_urls:
            return
        if any(p in src.lower() for p in _BAD_IMG_PATTERNS):
            return
        if src.startswith("data:"):
            return
        seen_urls.add(src)
        images.append({"url": src, "alt": alt or "", "source": "diario.madrid.es"})

    # 1. OG 图（最可靠）
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        _add(og["content"])

    # 2. Featured image / 正文图片（需满足最小尺寸要求）
    content_el = soup.select_one(".entry-content, .post-content, article .content, article")
    if content_el:
        for img in content_el.find_all("img", limit=8):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            alt = img.get("alt", "")
            # 跳过 HTML 属性显示过小的图（logo/stamp 通常 < 250px）
            try:
                w = int(img.get("width", 0))
                h = int(img.get("height", 0))
                if (w and w < 250) or (h and h < 200):
                    continue
            except (ValueError, TypeError):
                pass
            _add(src, alt)
            if len(images) >= 2:
                break

    return images[:2]


def fetch_article_content(url: str) -> dict:
    """抓取单篇正文，返回 content + images + category + district。"""
    result = {"content": "", "images": [], "category": "", "district": ""}
    try:
        resp = _get(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # 内容：移除噪声元素后提取正文
        for noise in soup.select("nav, header, footer, aside, .sidebar, .comments, .related, .share"):
            noise.decompose()

        content_el = soup.select_one(".entry-content, .post-content, article .content, article")
        if content_el:
            result["content"] = safe_strip(content_el.get_text(separator="\n"))[:5000]

        # OG description 作为内容兜底
        if len(result["content"]) < 100:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                result["content"] = safe_strip(og_desc["content"])

        # 图片
        result["images"] = _extract_images(soup)

        # 分类 / 区域
        cat_els = soup.select(".cat-links a, .category a, .tag a")
        result["category"] = ", ".join(safe_strip(el.get_text()) for el in cat_els)

        dist_el = soup.select_one(".district, .location, [class*='district']")
        result["district"] = safe_strip(dist_el.get_text()) if dist_el else ""

    except Exception as e:
        log.warning(f"[fetcher] 正文抓取失败 {url}: {e}")
    return result
