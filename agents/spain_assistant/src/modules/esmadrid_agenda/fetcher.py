"""从 esmadrid.com/agenda-madrid 抓取活动列表和详情。"""

import re
import json
import html as html_lib
import requests

from src.core.logger import get_logger
from src.core.storage import compute_hash

log = get_logger(__name__)

_BASE = "https://www.esmadrid.com"
_LIST_URL = f"{_BASE}/agenda-madrid"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
}


def _clean(text: str) -> str:
    text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', text))
    return re.sub(r'\s+', ' ', text).strip()


def fetch_event_list() -> list[dict]:
    """抓取列表页，返回去重的事件基础数据（含 URL/标题/图/摘要）。"""
    try:
        resp = requests.get(_LIST_URL, headers=_HEADERS, timeout=25)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"[esmadrid/fetcher] 列表页失败: {e}")
        raise

    raw = resp.text
    seen_paths: set[str] = set()
    events: list[dict] = []

    # 所有 view-mode 变体都含 node-event
    for about_path, block in re.findall(
        r'about=\"(/agenda/[^\"]+)\"[^>]*class=\"[^\"]*node-event[^\"]*\"[^>]*>(.*?)(?=about=\"/agenda/|<div\s+class=\"view-footer|<div\s+id=\"block-|<div\s+class=\"footer)',
        raw, re.DOTALL
    ):
        if about_path in seen_paths:
            continue
        seen_paths.add(about_path)

        url = _BASE + about_path

        # 标题
        title_m = re.search(
            r'field-name-title-field[^>]*>.*?<div[^>]*property[^>]*>([^<]+)', block, re.DOTALL
        )
        title = html_lib.unescape(title_m.group(1).strip()) if title_m else ""

        # 图片（优先 data-src）
        img_m = re.search(r'data-src="(https://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', block, re.I)
        if not img_m:
            img_m = re.search(r'src="(https://estaticos[^"]+\.(?:jpg|jpeg|png)[^"]*)"', block, re.I)
        image_url = img_m.group(1).split('?')[0] if img_m else ""

        # 摘要
        sum_m = re.search(r'field-name-resumen.*?<p[^>]*>(.*?)</p>', block, re.DOTALL)
        summary = _clean(sum_m.group(1)) if sum_m else ""

        hash_id = compute_hash(title or about_path, about_path)
        events.append({
            "hash_id": hash_id,
            "source_id": "esmadrid_agenda",
            "scope": "madrid_local_life",
            "title": title,
            "summary": summary,
            "image_url": image_url,
            "url": url,
            "original_url": url,
            # fields filled by detail fetch
            "category": "",
            "date_start": "",
            "date_end": "",
            "location_name": "",
            "address": "",
            "price_info": "",
            "audience": [],
            "tags": [],
        })

    log.info(f"[esmadrid/fetcher] 列表页找到 {len(events)} 个活动")
    return events


def fetch_event_detail(url: str) -> dict:
    """
    抓取活动详情页，返回 JSON-LD 结构化数据 + HTML 补充字段。

    返回: {date_start, date_end, location_name, address, category, body_text, image_url}
    """
    result = {
        "date_start": "", "date_end": "",
        "location_name": "", "address": "",
        "category": "", "body_text": "", "image_url": "",
    }
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        raw = resp.text

        # --- JSON-LD (dates, location, image) ---
        ld_m = re.search(r'application/ld\+json[^>]*>(.*?)</script>', raw, re.DOTALL)
        if ld_m:
            try:
                data = json.loads(ld_m.group(1))
                graph = data.get("@graph", [data]) if isinstance(data, dict) else data
                for node in (graph if isinstance(graph, list) else [graph]):
                    if node.get("@type") == "Event":
                        result["date_start"] = _iso_to_date(node.get("startDate", ""))
                        result["date_end"] = _iso_to_date(node.get("endDate", ""))

                        loc = node.get("location", {})
                        result["location_name"] = loc.get("name", "").strip()
                        addr = loc.get("address", {})
                        street = addr.get("streetAddress", "").strip()
                        locality = addr.get("addressLocality", "").strip()
                        result["address"] = ", ".join(p for p in [street, locality] if p)

                        img = node.get("image", {})
                        if isinstance(img, dict):
                            result["image_url"] = img.get("url", "")
                        elif isinstance(img, list):
                            result["image_url"] = img[0] if img else ""
                        break
            except Exception as e:
                log.debug(f"[esmadrid/fetcher] JSON-LD 解析失败: {e}")

        # --- HTML field补充 ---
        # 地点名（field-when: "Dónde <name> Dirección"）
        if not result["location_name"]:
            when_m = re.search(r'field-name-field-when[^>]*>(.*?)</div>\s*</div>\s*</div>', raw, re.DOTALL)
            if when_m:
                when_text = _clean(when_m.group(1))
                donde_m = re.search(r'D[oó]nde\s+(.+?)(?:Direcci[oó]n|$)', when_text, re.I)
                if donde_m:
                    result["location_name"] = donde_m.group(1).strip()

        # 地址补充（field-address + field-postal-code）
        if not result["address"]:
            addr_m = re.search(r'field-name-field-address[^>]*>.*?field-item[^>]*>(.*?)</div>', raw, re.DOTALL)
            postal_m = re.search(r'field-name-field-postal-code[^>]*>.*?field-item[^>]*>(.*?)</div>', raw, re.DOTALL)
            street = _clean(addr_m.group(1)) if addr_m else ""
            postal = _clean(postal_m.group(1)) if postal_m else ""
            if street:
                result["address"] = f"{street}, Madrid {postal}".strip(", ")

        # 分类（field-categoria: "Tipo Deporte, Hípica ..."）
        cat_m = re.search(r'field-name-field-categoria[^>]*>(.*?)</div>\s*</div>\s*</div>', raw, re.DOTALL)
        if cat_m:
            cat_text = _clean(cat_m.group(1))
            tipo_m = re.search(r'Tipo\s+(.+?)(?:https?://|$)', cat_text, re.I)
            result["category"] = tipo_m.group(1).strip(" ,") if tipo_m else cat_text[:60]

        # 正文（field-body: first 1500 chars）
        body_m = re.search(r'field-name-body[^>]*>.*?field-item[^>]*>(.*?)</div>\s*</div>\s*</div>', raw, re.DOTALL)
        if body_m:
            result["body_text"] = _clean(body_m.group(1))[:1500]

    except Exception as e:
        log.warning(f"[esmadrid/fetcher] 详情页失败 ({url[:60]}): {e}")

    return result


def _iso_to_date(iso: str) -> str:
    """'2026-05-17T00:00:00+0200' → '2026-05-17'"""
    m = re.match(r'(\d{4}-\d{2}-\d{2})', iso or "")
    return m.group(1) if m else ""
