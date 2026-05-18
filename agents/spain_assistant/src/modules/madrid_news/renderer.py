"""渲染静态 HTML 页面到 public/，生成 ICS 日历文件。"""

import json
import re
import shutil
from pathlib import Path
from datetime import date, datetime
from jinja2 import Environment, FileSystemLoader

from src.core import config
from src.core.logger import get_logger
from src.core.utils import today_str, slugify, now_madrid
from src.core.calendar_generator import build_google_calendar_url, build_ics_content, build_maps_info
from src.modules.madrid_news.highlight_manager import load_active_highlights

log = get_logger(__name__)

_TEMPLATES_DIR = config.root_dir / "src" / "templates"
_ASSETS_SRC = config.root_dir / "assets"


def _jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    env.globals["today"] = today_str()
    env.globals["now"] = now_madrid().strftime("%Y-%m-%d %H:%M")
    return env


def _copy_assets():
    dst = config.public_dir / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    for f in _ASSETS_SRC.glob("*"):
        if not f.name.startswith("._"):
            shutil.copy2(f, dst / f.name)


def _importance_order(art: dict) -> int:
    return {"S": 0, "A": 1, "B": 2, "C": 3}.get(art.get("importance", "C"), 3)


def _date_desc_key(art: dict) -> int:
    """同重要性级别内按发布日期从新到旧排序的次键（值越小越新）。"""
    s = (art.get("date") or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return -date.fromisoformat(m.group(1)).toordinal()
        except ValueError:
            pass
    return 0


def _normalize_text_fields(zh: dict) -> dict:
    """将 LLM 可能返回列表的文本字段统一转成字符串。"""
    for key in ("local_perspective", "tourist_advice", "resident_advice", "china_resident_angle", "professional_overview"):
        val = zh.get(key, "")
        if isinstance(val, list):
            zh[key] = "\n".join(str(v) for v in val if v)
        elif not isinstance(val, str):
            zh[key] = str(val) if val else ""
    return zh


def _enrich_computed_fields(art: dict) -> dict:
    """计算 maps_url、calendar URL、ICS 路径等派生字段。"""
    hash_id = art.get("hash_id", slugify(art.get("title", "unknown")))
    zh = _normalize_text_fields(art.get("zh", {}))

    # Google Maps
    loc = zh.get("location_info", {})
    maps = build_maps_info(loc) if loc else {"url": "", "type": "none"}
    art["maps_url"] = maps["url"]
    art["maps_url_type"] = maps["type"]

    # Calendar
    event = zh.get("event", {})
    if event and event.get("has_event") and event.get("start_date"):
        art["google_calendar_url"] = build_google_calendar_url(event)
        ics_content = build_ics_content(event, art.get("url", ""), hash_id)
        if ics_content:
            ics_dir = config.public_dir / "ics"
            ics_dir.mkdir(parents=True, exist_ok=True)
            ics_path = ics_dir / f"{hash_id}.ics"
            ics_path.write_text(ics_content, encoding="utf-8")
            art["ics_path"] = f"ics/{hash_id}.ics"
        else:
            art["google_calendar_url"] = ""
            art["ics_path"] = ""
    else:
        art["google_calendar_url"] = ""
        art["ics_path"] = ""

    # 首图：images[0] 或 thumbnail 作为卡片封面
    images = art.get("images", [])
    thumb = art.get("thumbnail", "")
    if images:
        art["cover_image"] = images[0]["url"]
    elif thumb:
        art["cover_image"] = thumb
    else:
        art["cover_image"] = ""

    return art


def render_all(articles: list[dict], national_articles: list[dict] | None = None, agenda_articles: list[dict] | None = None) -> list[dict]:
    config.public_dir.mkdir(parents=True, exist_ok=True)
    for d in ["archive", "articles", "data", "ics"]:
        (config.public_dir / d).mkdir(exist_ok=True)

    _copy_assets()
    jenv = _jinja_env()

    today = today_str()
    sorted_articles = sorted(articles, key=lambda a: (_importance_order(a), _date_desc_key(a)))

    # 计算派生字段并写单篇页
    for art in sorted_articles:
        art = _enrich_computed_fields(art)
        hash_id = art.get("hash_id", slugify(art.get("title", "unknown")))
        art["article_url"] = f"articles/{hash_id}.html"

        tmpl = jenv.get_template("article.html.j2")
        out = config.public_dir / "articles" / f"{hash_id}.html"
        out.write_text(tmpl.render(article=art), encoding="utf-8")

    # 按今日 / 历史分组
    today_articles = [a for a in sorted_articles if a.get("is_today", True)]
    past_articles = [a for a in sorted_articles if not a.get("is_today", True)]

    top_articles = [a for a in today_articles if a.get("importance") in ("S", "A")]

    # 跨日有效期内的重点关注（今日文章已在 top_articles 中展示，此处排除）
    today_hashes = {a.get("hash_id") for a in sorted_articles}
    persistent_highlights = [
        a for a in load_active_highlights(today)
        if a.get("hash_id") not in today_hashes
    ]
    # highlight store 保存时不含 article_url 和 cover_image，渲染时重建
    for art in persistent_highlights:
        if not art.get("article_url") and art.get("hash_id"):
            art["article_url"] = f"articles/{art['hash_id']}.html"
        if not art.get("cover_image"):
            images = art.get("images", [])
            thumb = art.get("thumbnail", "")
            img_url = art.get("image_url", "")
            if images:
                first = images[0]
                art["cover_image"] = first["url"] if isinstance(first, dict) else first
            elif thumb:
                art["cover_image"] = thumb
            elif img_url:
                art["cover_image"] = img_url if isinstance(img_url, str) else (img_url[0] if img_url else "")

    imp_order = {"S": 0, "A": 1, "B": 2}

    # 为全国新闻生成本地详情页，设置 article_url
    for art in (national_articles or []):
        hash_id = art.get("hash_id", slugify(art.get("title", "unknown")))
        art["article_url"] = f"articles/{hash_id}.html"
        out = config.public_dir / "articles" / f"{hash_id}.html"
        out.write_text(jenv.get_template("article_lamoncloa.html.j2").render(article=art), encoding="utf-8")

    # 为 Agenda 活动生成本地详情页，设置 article_url + ICS 日历
    ics_dir = config.public_dir / "ics"
    ics_dir.mkdir(parents=True, exist_ok=True)
    for ev in (agenda_articles or []):
        hash_id = ev.get("hash_id", slugify(ev.get("title", "unknown")))
        ev["article_url"] = f"articles/{hash_id}.html"
        ev["zh"] = _normalize_text_fields(ev.get("zh", {}))

        # 多天活动 ICS（无具体时间，全天事件）
        zh_ev = ev.get("zh", {})
        if ev.get("date_start"):
            cal_event = {
                "title": zh_ev.get("chinese_title") or ev.get("title", ""),
                "start_date": ev.get("date_start", ""),
                "end_date": ev.get("date_end", "") or ev.get("date_start", ""),
                "start_time": "",
                "end_time": "",
                "location": ev.get("location_name", ""),
                "description": zh_ev.get("one_line_summary", ""),
                "has_event": True,
            }
            ev["google_calendar_url"] = build_google_calendar_url(cal_event)
            ics_content = build_ics_content(cal_event, ev.get("url", ""), hash_id)
            if ics_content:
                ics_path = ics_dir / f"{hash_id}.ics"
                ics_path.write_text(ics_content, encoding="utf-8")
                ev["ics_path"] = f"ics/{hash_id}.ics"
            else:
                ev["ics_path"] = ""
        else:
            ev["google_calendar_url"] = ""
            ev["ics_path"] = ""

        out = config.public_dir / "articles" / f"{hash_id}.html"
        out.write_text(jenv.get_template("article_esmadrid.html.j2").render(article=ev), encoding="utf-8")

    # 全国重点：S/A 优先，最多展示 display_max 条
    national_display = []
    if national_articles:
        national_display = sorted(
            national_articles,
            key=lambda a: (imp_order.get(a.get("importance", "B"), 2), _date_desc_key(a))
        )[:config.get("modules.lamoncloa_news.display_max", 5)]

    # Agenda Madrid：活动按有效期和重要性排序，最多展示 display_max 条
    agenda_display = []
    if agenda_articles:
        today_d = today_str()
        valid_agenda = [
            e for e in agenda_articles
            if not e.get("valid_until") or e.get("valid_until", "") >= today_d
        ]
        agenda_display = sorted(
            valid_agenda,
            key=lambda e: (imp_order.get(e.get("importance", "B"), 2), e.get("date_start", ""))
        )[:config.get("modules.esmadrid_agenda.display_max", 5)]

    # 统计分类数量（用于 hero）—— 合并三个来源的展示内容
    all_displayed = today_articles + national_display + agenda_display
    stats = {
        "total": len(all_displayed),
        "important": sum(1 for a in all_displayed if a.get("importance") in ("S", "A")),
        "family": sum(
            1 for a in all_displayed
            if any(t in a.get("labels", a.get("tags", [])) for t in ("亲子", "教育"))
        ),
        "culture_art": sum(
            1 for a in all_displayed
            if any(t in a.get("labels", a.get("tags", [])) for t in ("文化", "艺术", "体育", "节日", "展览", "音乐", "戏剧", "节庆"))
        ),
    }

    # 首页
    index_html = config.public_dir / "index.html"
    index_html.write_text(
        jenv.get_template("index.html.j2").render(
            articles=today_articles,
            top_articles=top_articles,
            persistent_highlights=persistent_highlights,
            national_articles=national_display,
            agenda_articles=agenda_display,
            today=today,
            stats=stats,
        ),
        encoding="utf-8",
    )

    # 归档页（今日）
    archive_path = config.public_dir / "archive" / f"{today}.html"
    archive_path.write_text(
        jenv.get_template("archive.html.j2").render(articles=today_articles, date=today),
        encoding="utf-8",
    )

    # public/data/
    _write_json(config.public_dir / "data" / "latest.json", sorted_articles)
    _update_archive_index(today, sorted_articles)

    log.info(f"[renderer] 渲染完成：今日 {len(today_articles)} 条，历史 {len(past_articles)} 条")
    return sorted_articles


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_archive_index(today: str, articles: list):
    archive_json = config.public_dir / "data" / "archive.json"
    data = {}
    if archive_json.exists():
        try:
            data = json.loads(archive_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[today] = [a.get("hash_id") for a in articles]
    _write_json(archive_json, data)
