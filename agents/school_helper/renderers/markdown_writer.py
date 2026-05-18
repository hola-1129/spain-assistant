"""中文家长版周报 weekly_briefing_cn.md。

按用户指定的【】结构输出每个事项；顶部高亮家长重点关注的年级。
"""

from datetime import datetime
from pathlib import Path

from analyzer.extractor import (CATEGORY_GENERAL, CATEGORY_INFANTIL, CATEGORY_PRIMARIA,
                                CATEGORY_PREPARATORY, CATEGORY_ESO, CATEGORY_BACHILLERATO,
                                CATEGORY_IBDP, CATEGORY_PARENT_ACTION, CATEGORY_INFO_ONLY,
                                ALL_CATEGORIES)


def _fmt_event(idx: int, ev: dict, fetch: dict) -> str:
    title_cn = ev.get("title_cn") or fetch.get("title") or "(无中文标题)"
    title_es = ev.get("title_es") or fetch.get("title", "")
    audience_es = ev.get("audience_es") or fetch.get("stage", "")
    audience_cn = ev.get("audience_cn") or "(原文未说明)"

    date = ev.get("date") or "(原文未说明)"
    t_start = ev.get("time_start", "")
    t_end   = ev.get("time_end", "")
    time_str = ""
    if t_start and t_end:
        time_str = f"{t_start} – {t_end}"
    elif t_start:
        time_str = t_start
    weather = ev.get("weather", "")
    key_time = date + (f"  {time_str}" if time_str else "") + (f"  {weather}" if weather else "")

    location_cn = ev.get("location_cn", "") or "(原文未说明)"
    location_es = ev.get("location_es", "")
    location = location_cn + (f"  /  {location_es}" if location_es and location_es != location_cn else "")

    parent_action = ev.get("parent_action") or "(无具体行动)"
    student_prepare = ev.get("student_prepare") or "(原文未说明)"

    signup = ev.get("signup_required") or "原文未说明"
    if ev.get("signup_method"):
        signup += f"；方式：{ev['signup_method']}"
    if ev.get("payment_required"):
        signup += f"；付款：{ev['payment_required']}"
    if ev.get("cost"):
        signup += f"；费用：{ev['cost']}"

    notes = ev.get("notes", "")
    notes_line = f"⚠️ 注意：{notes}" if notes else "无"

    keywords = ev.get("keywords_es") or []
    kw_str = ", ".join(keywords) if keywords else (title_es or "(无)")
    if ev.get("deadline"):
        kw_str += f"  | deadline: {ev['deadline']}"

    parts = [
        f"### {idx}. 【{title_cn}】",
        f"- **适用对象**: {audience_cn}（原文 {audience_es}）",
        f"- **中文说明**: {ev.get('title_cn','') or '(无补充说明)'}",
        f"- **关键时间**: {key_time}",
        f"- **地点**: {location}",
        f"- **家长需要做什么**: {parent_action}",
        f"- **孩子需要准备什么**: {student_prepare}",
        f"- **是否需要报名/付款**: {signup}",
        f"- **注意事项**: {notes_line}",
        f"- **西语/英语原文关键词**: {kw_str}",
        f"- **学校原文链接**: {fetch.get('url','')}",
    ]
    if fetch.get("status") != "ok":
        parts.append(f"- ⚠️ **链接处理状态**: {fetch.get('status')} — {fetch.get('error','')}")
    if ev.get("school_intent_cn"):
        parts.append(f"\n💡 **学校视角**：{ev['school_intent_cn']}")
    if ev.get("raw_excerpt"):
        parts.append(f"\n> 原文摘录: {ev['raw_excerpt']}")
    return "\n".join(parts)


def _fmt_failed_event(idx: int, fetch: dict) -> str:
    title = fetch.get("title") or "(无标题)"
    return "\n".join([
        f"### {idx}. 【{title}】（⚠️ 链接无法解析）",
        f"- **适用对象**: {fetch.get('stage','')}",
        f"- **状态**: {fetch.get('status','')}（{fetch.get('error','')}）",
        f"- **学校原文链接**: {fetch.get('url','')}",
        f"- **建议**: 链接无法自动获取，请手动打开浏览器查看",
    ])


def _category_section(name: str, events: list[tuple[int, dict]]) -> str:
    if not events:
        return ""
    lines = [f"## {name}\n"]
    for idx, e in events:
        if e.get("fields"):
            lines.append(_fmt_event(idx, e["fields"], e["fetch"]))
        else:
            lines.append(_fmt_failed_event(idx, e["fetch"]))
        lines.append("")
    return "\n".join(lines)


def _is_priority(e: dict, priority_grades: list[str]) -> bool:
    fld = e.get("fields") or {}
    txt = (fld.get("audience_es", "") + " " + fld.get("audience_cn", "")
           + " " + e["fetch"].get("stage", "")).upper()
    for g in priority_grades:
        if g.upper() in txt:
            return True
    return False


def write_markdown(out_path: Path, *, week_label: str, week_iso: str,
                   events: list[dict], priority_grades: list[str]) -> None:
    # 给每个事项编号
    indexed = list(enumerate(events, 1))

    # 我家孩子相关（高亮区）
    family_priority = [(i, e) for i, e in indexed if _is_priority(e, priority_grades)]

    # 时间线（按日期排序）
    timeline_rows = []
    for i, e in indexed:
        fld = e.get("fields") or {}
        if fld.get("date"):
            timeline_rows.append((fld["date"], fld.get("time_start", ""), i, fld, e["fetch"]))
    timeline_rows.sort(key=lambda r: (r[0], r[1] or ""))

    # 各分类
    by_cat: dict[str, list[tuple[int, dict]]] = {c: [] for c in ALL_CATEGORIES}
    for i, e in indexed:
        cats = e.get("categories") or []
        for c in cats:
            by_cat[c].append((i, e))
        if e.get("parent_action_needed"):
            by_cat[CATEGORY_PARENT_ACTION].append((i, e))

    # 去重 (CATEGORY_PARENT_ACTION 可能与年级重叠)
    for c, lst in by_cat.items():
        seen = set()
        unique = []
        for i, e in lst:
            if i in seen:
                continue
            seen.add(i)
            unique.append((i, e))
        by_cat[c] = unique

    out: list[str] = []
    out.append(f"# 学校周通知中文家长版")
    out.append(f"")
    out.append(f"- **周次**: {week_label or '(未识别)'}  ({week_iso})")
    out.append(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out.append(f"- **事项数量**: {len(events)}")
    out.append(f"")

    # 顶部：家长重点关注
    if family_priority:
        out.append(f"## 👨‍👩‍👧‍👦 我家孩子相关（{', '.join(priority_grades)}）")
        out.append("")
        for idx, e in family_priority:
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
            date = fld.get("date") or "(原文未说明日期)"
            out.append(f"- **#{idx} 【{title}】** — {date}  /  {fld.get('audience_es') or e['fetch'].get('stage','')}")
        out.append("")

    # 本周重要时间线
    out.append("## 🗓 本周重要时间线")
    out.append("")
    if timeline_rows:
        for date, t_start, idx, fld, fetch in timeline_rows:
            title = fld.get("title_cn") or fetch.get("title") or "(无标题)"
            t = f" {t_start}" if t_start else ""
            flag = " ⚠️ 家长需提前处理" if (fld.get("deadline") or fld.get("signup_required") == "是") else ""
            out.append(f"- **{date}{t}** — #{idx} {title}{flag}")
    else:
        out.append("- (本周通知中未抽到明确日期)")
    out.append("")

    # 分类输出
    for cat in ALL_CATEGORIES:
        section = _category_section(cat, by_cat.get(cat, []))
        if section:
            out.append(section)

    out.append("")
    out.append("---")
    out.append("> 本文由 school_helper agent 自动生成。如发现与学校原文不一致，以学校原文为准。")
    out_path.write_text("\n".join(out))
