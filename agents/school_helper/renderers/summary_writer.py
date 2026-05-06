"""微信群转发版 weekly_briefing_summary.txt。简短、有 emoji、保留西语关键词。"""

from pathlib import Path


def _is_priority(e: dict, priority_grades: list[str]) -> bool:
    fld = e.get("fields") or {}
    txt = (fld.get("audience_es", "") + " " + fld.get("audience_cn", "")
           + " " + e["fetch"].get("stage", "")).upper()
    return any(g.upper() in txt for g in priority_grades)


def write_summary(out_path: Path, *, week_label: str, week_iso: str,
                  events: list[dict], priority_grades: list[str]) -> None:
    lines: list[str] = []
    lines.append(f"📚 Brains 学校周通知（{week_label or week_iso}）")
    lines.append("")

    # ─── 本周重点（家长关注 + 需要行动） ───
    priority = [(i, e) for i, e in enumerate(events, 1)
                if _is_priority(e, priority_grades) or e.get("parent_action_needed")]

    if priority:
        lines.append("⭐ 本周重点：")
        for idx, e in priority[:8]:  # 最多 8 条
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
            stage = fld.get("audience_es") or e["fetch"].get("stage", "")
            date = fld.get("date") or "日期待定"
            tag = " ✍️" if e.get("parent_action_needed") else ""
            lines.append(f"  • {title} ({stage}) — {date}{tag}")
        lines.append("")

    # ─── 需要家长操作 ───
    actions = [(i, e) for i, e in enumerate(events, 1) if e.get("parent_action_needed")]
    if actions:
        lines.append("✍️ 需要家长操作：")
        for idx, e in actions:
            fld = e.get("fields") or {}
            title = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
            todo = fld.get("parent_action") or "查看通知详情"
            ddl = f"（截止 {fld.get('deadline')}）" if fld.get("deadline") else ""
            lines.append(f"  • {title}{ddl}：{todo}")
        lines.append("")

    # ─── 各年级一句话摘要 ───
    by_stage: dict[str, list[str]] = {}
    for e in events:
        fld = e.get("fields") or {}
        stage = fld.get("audience_es") or e["fetch"].get("stage", "") or "其他"
        title = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
        date = fld.get("date") or ""
        line = f"{title}" + (f" — {date}" if date else "")
        by_stage.setdefault(stage, []).append(line)

    if by_stage:
        lines.append("🎓 各年级事项：")
        for stage, titles in by_stage.items():
            lines.append(f"  [{stage}]")
            for t in titles:
                lines.append(f"    - {t}")
        lines.append("")

    # ─── 时间节点 ───
    timeline = []
    for i, e in enumerate(events, 1):
        fld = e.get("fields") or {}
        if fld.get("date"):
            title = fld.get("title_cn") or e["fetch"].get("title") or "(无标题)"
            t_start = fld.get("time_start", "")
            timeline.append((fld["date"], t_start, title))
    timeline.sort()

    if timeline:
        lines.append("🗓 时间节点：")
        for date, t, title in timeline:
            t_str = f" {t}" if t else ""
            lines.append(f"  {date}{t_str} — {title}")
        lines.append("")

    lines.append("ℹ️ 详细中文版见 weekly_briefing_cn.md，日历可导入 school_events.ics。")
    out_path.write_text("\n".join(lines))
