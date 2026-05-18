"""从 La Moncloa 官方网站抓取政府新闻列表和详情正文。"""

import re
import time
import html as html_lib
import requests

from src.core.logger import get_logger
from src.core.storage import compute_hash

log = get_logger(__name__)

_BASE = "https://www.lamoncloa.gob.es"
_LIST_URL = f"{_BASE}/serviciosdeprensa/notasprensa/Paginas/index.aspx"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_NOISE_PHRASES = {"cookie", "Complejo de la Moncloa", "Avda. Puerta de Hierro", "sitio web utiliza"}


def _clean(text: str) -> str:
    text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', text))
    return re.sub(r'\s+', ' ', text).strip()


def fetch_article_list(max_items: int = 20) -> list[dict]:
    """抓取列表页，返回文章基础数据列表。"""
    try:
        resp = requests.get(_LIST_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"[lamoncloa/fetcher] 列表页失败: {e}")
        raise

    raw = resp.text
    items = re.findall(r'<li[^>]+class="advanced-new"[^>]*>(.*?)</li>', raw, re.DOTALL)
    log.info(f"[lamoncloa/fetcher] 列表页找到 {len(items)} 条")

    articles = []
    for item in items[:max_items]:
        try:
            articles.append(_parse_item(item))
        except Exception as e:
            log.warning(f"[lamoncloa/fetcher] 条目解析跳过: {e}")

    return [a for a in articles if a]


def _parse_item(item: str) -> dict | None:
    # URL + 标题
    title_m = re.search(
        r'class="title-advanced-news"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>',
        item, re.DOTALL
    )
    if not title_m:
        return None
    url_path = title_m.group(1).strip()
    title = _clean(title_m.group(2))
    if not title:
        return None

    # 部委
    dept_m = re.search(r'class="sitedate"[^>]*>.*?<a[^>]+title="([^"]+)"', item, re.DOTALL)
    department = dept_m.group(1).strip() if dept_m else ""

    # 日期 DD.M.YYYY → YYYY-MM-DD
    date_m = re.search(r'<span class="date">(\d{1,2})\.(\d{1,2})\.(\d{4})</span>', item)
    if date_m:
        d, m, y = date_m.groups()
        date_str = f"{y}-{int(m):02d}-{int(d):02d}"
    else:
        date_str = ""

    # 摘要（最后一个 <p><span>…</span> 块）
    summary_m = re.search(r'</p>\s*<p>\s*<span>(.*?)</span>', item, re.DOTALL)
    summary = _clean(summary_m.group(1)) if summary_m else ""

    # 缩略图
    img_m = re.search(r'<img[^>]+src="([^"?]+)', item)
    thumbnail = (_BASE + img_m.group(1)) if img_m else ""

    url = _BASE + url_path
    hash_id = compute_hash(title, date_str)

    return {
        "hash_id": hash_id,
        "source_id": "lamoncloa",
        "scope": "spain_national",
        "title": title,
        "summary": summary,
        "department": department,
        "date": date_str,
        "url": url,
        "thumbnail": thumbnail,
        "content": "",
    }


def fetch_article_content(url: str, timeout: int = 20) -> str:
    """抓取文章详情页正文段落，合并为纯文本。"""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        paras = re.findall(r'<p[^>]*>(.*?)</p>', resp.text, re.DOTALL)
        lines = []
        for p in paras:
            text = _clean(p)
            if len(text) > 60 and not any(n in text for n in _NOISE_PHRASES):
                lines.append(text)
        return "\n\n".join(lines[:25])
    except Exception as e:
        log.warning(f"[lamoncloa/fetcher] 正文抓取失败 ({url[:60]}): {e}")
        return ""
