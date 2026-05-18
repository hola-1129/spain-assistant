"""生成 GitHub Pages 主页 index.html。

要求：
- 自包含、纯静态、无 JS 依赖
- 所有链接相对路径，不含本地绝对路径
- 标题: Brains School Weekly Briefing 中文家长版
- 区块顺序: 本周重点 → 家长操作 → 按年级 → 时间线 → 日历区 → 原文链接区
- iOS 友好（点击 .ics 触发"加入日历"）
"""

import html
import urllib.parse
from datetime import datetime
from pathlib import Path

from analyzer.extractor import (ALL_CATEGORIES, CATEGORY_INFO_ONLY, CATEGORY_PARENT_ACTION,
                                 CATEGORY_GENERAL, CATEGORY_INFANTIL, CATEGORY_PRIMARIA,
                                 CATEGORY_PREPARATORY, CATEGORY_ESO, CATEGORY_BACHILLERATO,
                                 CATEGORY_IBDP)


_CSS = """
:root { --fg:#1a1a1a; --muted:#6b6b6b; --bg:#fff; --card:#f6f7f9;
        --accent:#0b66c2; --accent-hover:#084d92; --warn:#b54708;
        --border:#e1e4e8; --pill:#eef2f7; }
* { box-sizing: border-box; }
body { margin:0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
       "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif;
       color:var(--fg); background:var(--bg); line-height:1.55;
       -webkit-font-smoothing: antialiased; }
.container { max-width: 820px; margin: 0 auto; padding: 1.25rem 1rem 4rem; }
header { padding: 1.5rem 0 1rem; border-bottom: 2px solid var(--border); margin-bottom: 1.25rem; display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap; }
header .logo-wrap { flex-shrink: 0; }
header .logo-wrap img { height: 52px; width: auto; display: block; }
header .header-text { flex: 1; min-width: 0; }
header h1 { margin: 0 0 .25rem; font-size: 1.35rem; line-height: 1.25; font-weight: 700; letter-spacing: -.01em; }
header .meta { color: var(--muted); font-size: .88rem; margin: 0 0 .75rem; }
h2 { font-size:1.2rem; margin: 1.6rem 0 .6rem; padding-top:.6rem; border-top: 1px solid var(--border); }
h3 { font-size:1.05rem; margin: 1.2rem 0 .4rem; color: var(--accent); }
h4 { font-size:1rem; margin: 0 0 .35rem; }
ul { padding-left: 1.2rem; }
li { margin: .15rem 0; }
.btn { display: inline-block; padding: .55rem .9rem; border-radius: 6px;
       background: var(--accent); color: #fff; text-decoration: none; font-weight: 600;
       margin: .25rem .25rem .25rem 0; font-size: .92rem; }
.btn:hover { background: var(--accent-hover); }
.btn-ghost { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
.btn-ghost:hover { background: var(--accent); color:#fff; }
.btn-maps { background: #1a73e8; }
.btn-maps:hover { background: #1557b0; }
/* 年级配色 */
.grade-general      { --grade: #7c3aed; }
.grade-infantil     { --grade: #db2777; }
.grade-primaria     { --grade: #0b66c2; }
.grade-preparatory  { --grade: #0891b2; }
.grade-eso          { --grade: #16a34a; }
.grade-bachillerato { --grade: #d97706; }
.grade-ibdp         { --grade: #dc2626; }
.grade-pill { display: inline-block; background: var(--grade, #6b6b6b); color: #fff;
              padding: .12rem .6rem; border-radius: 999px; font-size: .78rem;
              font-weight: 600; margin-right: .4rem; vertical-align: middle; }
h3.grade-h { color: var(--grade, var(--accent));
             border-left: 4px solid var(--grade, var(--accent));
             padding-left: .6rem; }
.event.has-grade { border-left: 4px solid var(--grade, var(--border)); }
.priority-grid .grade-pill { color: #fff; background: var(--grade, var(--pill)); }
.event { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
         padding: .8rem 1rem; margin: .8rem 0; }
.event h4 .es { color: var(--muted); font-weight: 400; font-size: .9rem; margin-left: .5rem; }
.event .pill { display: inline-block; background: var(--pill); color: var(--muted);
               padding: .1rem .55rem; border-radius: 999px; font-size: .8rem; margin-right: .35rem; }
.event dl { display: grid; grid-template-columns: max-content 1fr; gap: .25rem .75rem;
            margin: .35rem 0 .5rem; font-size: .92rem; }
.event dt { color: var(--muted); }
.event dd { margin: 0; }
.event .raw { color: var(--muted); font-size: .85rem; border-left: 3px solid var(--border);
              padding: .25rem .6rem; margin-top: .5rem; }
.event .warn { color: var(--warn); font-weight: 600; }
.timeline { list-style: none; padding-left: 0; }
.timeline li { padding: .35rem 0; border-bottom: 1px dashed var(--border); font-size: .95rem; }
.timeline .date { display: inline-block; min-width: 7rem; color: var(--accent); font-weight: 600; }
.priority-grid { display: grid; gap: .5rem; }
footer { color: var(--muted); font-size: .85rem; margin-top: 2.5rem; padding-top: 1rem;
         border-top: 1px solid var(--border); }
@media (max-width: 480px) {
  .event dl { grid-template-columns: 1fr; gap: .1rem 0; }
  .event dt { margin-top: .4rem; }
}
"""


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


_GRADE_CLASS = {
    CATEGORY_GENERAL:      "grade-general",
    CATEGORY_INFANTIL:     "grade-infantil",
    CATEGORY_PRIMARIA:     "grade-primaria",
    CATEGORY_PREPARATORY:  "grade-preparatory",
    CATEGORY_ESO:          "grade-eso",
    CATEGORY_BACHILLERATO: "grade-bachillerato",
    CATEGORY_IBDP:         "grade-ibdp",
}


def _grade_class(cat: str) -> str:
    return _GRADE_CLASS.get(cat, "")


def _maps_url(location: str) -> str:
    if not location or location == "(原文未说明)":
        return ""
    q = urllib.parse.quote_plus(location + " Madrid")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def _is_priority(e: dict, priority_grades: list[str]) -> bool:
    fld = e.get("fields") or {}
    txt = (fld.get("audience_es", "") + " " + fld.get("audience_cn", "")
           + " " + e["fetch"].get("stage", "")).upper()
    return any(g.upper() in txt for g in priority_grades)


def _event_card(idx: int, e: dict, ics_filename: str | None, primary_cat: str = "") -> str:
    fld = e.get("fields") or {}
    fetch = e["fetch"]
    gc = _grade_class(primary_cat)

    title_cn = fld.get("title_cn") or "(无中文标题)"
    title_es = fld.get("title_es") or fetch.get("title", "")
    audience_es = fld.get("audience_es") or fetch.get("stage", "")
    audience_cn = fld.get("audience_cn", "")
    audience_str = audience_cn + (f"（{audience_es}）" if audience_es and audience_es != audience_cn else "")
    if not audience_str:
        audience_str = audience_es or "(原文未说明)"

    date = fld.get("date") or "(原文未说明)"
    t_start, t_end = fld.get("time_start", ""), fld.get("time_end", "")
    if t_start and t_end:
        time_str = f"{t_start} – {t_end}"
    elif t_start:
        time_str = t_start
    else:
        time_str = ""
    weather = fld.get("weather", "")
    when = date + (f"  {time_str}" if time_str else "") + (f"   {weather}" if weather else "")

    location_cn = fld.get("location_cn", "")
    location_es = fld.get("location_es", "")
    if location_cn and location_es and location_cn != location_es:
        location = f"{location_cn} / {location_es}"
    else:
        location = location_cn or location_es or "(原文未说明)"

    parent_action = fld.get("parent_action") or "(无具体行动)"
    student_prepare = fld.get("student_prepare") or "(原文未说明)"

    signup_bits = []
    if fld.get("signup_required"):
        signup_bits.append(f"报名 {fld['signup_required']}")
    if fld.get("signup_method"):
        signup_bits.append(fld["signup_method"])
    if fld.get("payment_required"):
        signup_bits.append(f"付款 {fld['payment_required']}")
    if fld.get("cost"):
        signup_bits.append(f"费用 {fld['cost']}")
    signup_str = "；".join(signup_bits) or "原文未说明"

    notes = fld.get("notes", "")
    keywords = fld.get("keywords_es") or []
    raw_excerpt = fld.get("raw_excerpt", "")

    grade_classes = f" has-grade {gc}" if gc else ""
    parts = [f'<article class="event{grade_classes}">']
    if gc:
        parts.append(f'<span class="grade-pill {gc}">{_esc(primary_cat)}</span>')
    parts.append(
        f'<h4>#{idx} 【{_esc(title_cn)}】'
        + (f'<span class="es">{_esc(title_es)}</span>' if title_es and title_es != title_cn else "")
        + '</h4>'
    )
    cats = e.get("categories") or []
    if cats:
        parts.append("<div>" + "".join(f'<span class="pill">{_esc(c)}</span>' for c in cats) + "</div>")

    parts.append("<dl>")
    parts.append(f"<dt>适用对象</dt><dd>{_esc(audience_str)}</dd>")
    parts.append(f"<dt>关键时间</dt><dd>{_esc(when)}</dd>")
    parts.append(f"<dt>地点</dt><dd>{_esc(location)}</dd>")
    parts.append(f"<dt>家长需要做</dt><dd>{_esc(parent_action)}</dd>")
    parts.append(f"<dt>孩子需要准备</dt><dd>{_esc(student_prepare)}</dd>")
    parts.append(f"<dt>报名/付款</dt><dd>{_esc(signup_str)}</dd>")
    if fld.get("deadline"):
        parts.append(f'<dt>截止日期</dt><dd class="warn">{_esc(fld["deadline"])}</dd>')
    if notes:
        parts.append(f'<dt>注意事项</dt><dd class="warn">⚠️ {_esc(notes)}</dd>')
    if keywords:
        parts.append(f"<dt>原文关键词</dt><dd>{_esc(', '.join(keywords))}</dd>")
    parts.append("</dl>")

    if raw_excerpt:
        parts.append(f'<div class="raw">原文摘录：{_esc(raw_excerpt)}</div>')

    # 按钮区
    btn_row = []
    if ics_filename:
        btn_row.append(f'<a class="btn" href="./events/{_esc(ics_filename)}">📅 加到手机日历</a>')
    maps_link = _maps_url(location_cn or location_es)
    if maps_link:
        btn_row.append(f'<a class="btn btn-maps" href="{_esc(maps_link)}" target="_blank" rel="noopener">📍 Google Maps</a>')
    if fetch.get("url"):
        btn_row.append(f'<a class="btn btn-ghost" href="{_esc(fetch["url"])}" target="_blank" rel="noopener">查看学校原文</a>')
    if fetch.get("status") != "ok":
        btn_row.append(f'<span class="warn">⚠️ 链接处理状态: {_esc(fetch.get("status",""))}</span>')
    if btn_row:
        parts.append('<div>' + " ".join(btn_row) + '</div>')

    parts.append("</article>")
    return "\n".join(parts)


def _failed_card(idx: int, e: dict) -> str:
    f = e["fetch"]
    title = f.get("title") or "(无标题)"
    parts = [
        '<article class="event">',
        f'<h4>#{idx} 【{_esc(title)}】 <span class="warn">⚠️ 链接无法解析</span></h4>',
        f'<dl><dt>适用对象</dt><dd>{_esc(f.get("stage",""))}</dd>',
        f'<dt>状态</dt><dd>{_esc(f.get("status",""))} — {_esc(f.get("error",""))}</dd></dl>',
    ]
    if f.get("url"):
        parts.append(
            f'<a class="btn btn-ghost" href="{_esc(f["url"])}" target="_blank" rel="noopener">'
            f'尝试打开学校原文</a>'
        )
    parts.append("</article>")
    return "\n".join(parts)


_WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}



def write_html(out_path: Path, *, week_label: str, week_iso: str,
               events: list[dict], priority_grades: list[str],
               ics_filenames: dict[int, str],
               almanac_data: dict | None = None) -> None:
    indexed = list(enumerate(events, 1))

    # 索引：分类
    by_cat: dict[str, list[tuple[int, dict]]] = {c: [] for c in ALL_CATEGORIES}
    for i, e in indexed:
        for c in (e.get("categories") or []):
            by_cat[c].append((i, e))
        if e.get("parent_action_needed"):
            by_cat[CATEGORY_PARENT_ACTION].append((i, e))
    for c in by_cat:
        seen = set()
        out = []
        for i, e in by_cat[c]:
            if i in seen:
                continue
            seen.add(i)
            out.append((i, e))
        by_cat[c] = out

    # 本周重点：家长重点关注的 + 需要操作的
    priority_items = [(i, e) for i, e in indexed
                      if _is_priority(e, priority_grades) or e.get("parent_action_needed")]

    # 时间线
    timeline = []
    for i, e in indexed:
        fld = e.get("fields") or {}
        if fld.get("date"):
            timeline.append((fld["date"], fld.get("time_start", ""), i, e))
    timeline.sort(key=lambda r: (r[0], r[1] or ""))

    # ─── 渲染 ───
    body: list[str] = []

    body.append('<div class="container">')

    # Header
    body.append("<header>")
    body.append('<div class="logo-wrap"><img src="./logo_brains.png" alt="Brains School"></div>')
    body.append('<div class="header-text">')
    body.append('<h1>Weekly Briefing · 中文家长版</h1>')
    body.append(
        f'<p class="meta">{_esc(week_label or week_iso)} · 共 {len(events)} 个事项 · '
        f'生成于 {_esc(datetime.now().strftime("%Y-%m-%d %H:%M"))}</p>'
    )
    body.append('</div>')
    body.append("</header>")

    # 1. 本周重点
    body.append('<section><h2>⭐ 本周重点</h2>')
    if priority_items:
        body.append('<div class="priority-grid">')
        for i, e in priority_items[:8]:
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or "(无中文标题)"
            date  = fld.get("date") or "日期待定"
            tag   = ' <span class="warn">✍️ 需要操作</span>' if e.get("parent_action_needed") else ""
            primary_cat = (e.get("categories") or [""])[0]
            gc = _grade_class(primary_cat)
            pill = (f'<span class="grade-pill {gc}">{_esc(primary_cat)}</span> '
                    if gc else "")
            body.append(
                f'<div>• {pill}<a href="#event-{i}"><strong>{_esc(title)}</strong></a>'
                f' — {_esc(date)}{tag}</div>'
            )
        body.append('</div>')
    else:
        body.append('<p>本周无家长重点关注事项。</p>')
    body.append('</section>')

    # 2. 家长需要操作
    body.append('<section><h2>✍️ 家长需要操作</h2>')
    actions = [(i, e) for i, e in indexed if e.get("parent_action_needed")]
    if actions:
        body.append("<ul>")
        for i, e in actions:
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or "(无中文标题)"
            todo  = fld.get("parent_action") or "查看通知详情"
            ddl   = f'（截止 <strong>{_esc(fld.get("deadline"))}</strong>）' if fld.get("deadline") else ""
            primary_cat = (e.get("categories") or [""])[0]
            gc = _grade_class(primary_cat)
            pill = (f'<span class="grade-pill {gc}">{_esc(primary_cat)}</span> '
                    if gc else "")
            body.append(f'<li>{pill}<a href="#event-{i}"><strong>{_esc(title)}</strong></a>{ddl}：{_esc(todo)}</li>')
        body.append("</ul>")
    else:
        body.append("<p>本周无明确需要家长行动的事项。</p>")
    body.append("</section>")

    # 3. 重要时间线
    body.append('<section><h2>🗓 重要时间线</h2>')
    if timeline:
        body.append('<ol class="timeline">')
        for date, t, i, e in timeline:
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or "(无中文标题)"
            t_str = f" {t}" if t else ""
            flag = ' <span class="warn">⚠️ 家长需提前处理</span>' if (
                fld.get("deadline") or fld.get("signup_required") == "是") else ""
            body.append(
                f'<li><span class="date">{_esc(date)}{_esc(t_str)}</span>'
                f' <a href="#event-{i}">{_esc(title)}</a>{flag}</li>'
            )
        body.append("</ol>")
    else:
        body.append("<p>本周通知中未抽到明确日期。</p>")
    body.append("</section>")

    # 4. 按年级分类
    body.append('<section><h2>🎓 按年级分类</h2>')
    rendered_indices: set[int] = set()
    for cat in ALL_CATEGORIES:
        if cat == CATEGORY_INFO_ONLY:
            continue  # 留到最后
        items = by_cat.get(cat, [])
        if not items:
            continue
        gc = _grade_class(cat)
        h3_cls = f' class="grade-h {gc}"' if gc else ""
        body.append(f'<h3{h3_cls}>{_esc(cat)}</h3>')
        for i, e in items:
            rendered_indices.add(i)
            body.append(f'<div id="event-{i}">')
            if e.get("fields"):
                body.append(_event_card(i, e, ics_filenames.get(i), primary_cat=cat))
            else:
                body.append(_failed_card(i, e))
            body.append("</div>")
    info_only = [(i, e) for i, e in indexed if i not in rendered_indices]
    if info_only:
        body.append(f'<h3>{_esc(CATEGORY_INFO_ONLY)}</h3>')
        for i, e in info_only:
            body.append(f'<div id="event-{i}">')
            if e.get("fields"):
                body.append(_event_card(i, e, ics_filenames.get(i)))
            else:
                body.append(_failed_card(i, e))
            body.append("</div>")
    body.append("</section>")

    # 5. 日历添加区
    body.append('<section><h2>📅 日历添加区</h2>')
    body.append('<p>iOS 用户：点击下方按钮，Safari 会弹出"加入日历"对话框。Android 用户会下载 .ics 文件，再用日历 app 打开导入。</p>')
    body.append('<p><a class="btn" href="./school_events.ics">添加全部本周日历</a></p>')
    if ics_filenames:
        body.append('<p>单独添加某个事项：</p><ul>')
        for i, e in indexed:
            if i not in ics_filenames:
                continue
            fld = e.get("fields") or {}
            title_cn = fld.get("title_cn") or "(无中文标题)"
            title_es = fld.get("title_es") or e["fetch"].get("title") or ""
            label = title_cn + (f" / {title_es}" if title_es and title_es != title_cn else "")
            body.append(
                f'<li><a href="./events/{_esc(ics_filenames[i])}">'
                f'📅 {_esc(label)}</a></li>'
            )
        body.append("</ul>")
    body.append("</section>")

    # 6. 原文 PDF 链接区
    body.append('<section><h2>🔗 学校原文 PDF 链接</h2><ul>')
    for i, e in indexed:
        f = e["fetch"]
        fld = e.get("fields") or {}
        title_cn = fld.get("title_cn") or ""
        title_es = fld.get("title_es") or f.get("title") or "(无标题)"
        display = (f"{title_cn} / {title_es}") if title_cn else title_es
        url = f.get("url", "")
        status = f.get("status", "")
        warn = "" if status == "ok" else f' <span class="warn">⚠️ {_esc(status)}</span>'
        if url:
            body.append(
                f'<li>#{i} {_esc(display)} '
                f'<a href="{_esc(url)}" target="_blank" rel="noopener">原文</a>{warn}</li>'
            )
        else:
            body.append(f'<li>#{i} {_esc(display)}{warn}</li>')
    body.append("</ul></section>")

    # Footer
    body.append("<footer>")
    body.append("<p>本页由 school_helper agent 自动生成。如发现与学校原文不一致，以学校原文为准。</p>")
    body.append("<p>历史归档（如有）位于 <code>./archive/&lt;YYYY-Www&gt;/index.html</code></p>")
    body.append("</footer>")
    body.append("</div>")  # /.container

    html_doc = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="referrer" content="no-referrer">\n'
        "<title>Brains School Weekly Briefing 中文家长版</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )
    out_path.write_text(html_doc)
