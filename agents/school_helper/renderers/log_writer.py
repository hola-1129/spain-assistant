"""写 extracted_links.json + processing_log.txt"""

import json
from datetime import datetime
from pathlib import Path


def write_links_json(out_path: Path, week_label: str, week_iso: str, events: list[dict]) -> None:
    rows = []
    for e in events:
        f = e["fetch"]
        rows.append({
            "title":       f.get("title", ""),
            "stage":       f.get("stage", ""),
            "url":         f.get("url", ""),
            "status":      f.get("status", ""),
            "http_status": f.get("http_status"),
            "cache_path":  f.get("cache_path"),
            "error":       f.get("error", ""),
            "categories":  e.get("categories", []),
            "parent_action_needed": e.get("parent_action_needed", False),
            "extracted":   e.get("fields") is not None,
        })
    out_path.write_text(json.dumps(
        {"week_label": week_label, "week_iso": week_iso, "items": rows},
        ensure_ascii=False, indent=2,
    ))


def write_processing_log(out_path: Path, week_label: str, week_iso: str,
                         input_pdf: str, events: list[dict]) -> None:
    lines: list[str] = []
    lines.append(f"School Helper 处理日志")
    lines.append(f"生成时间: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"周次:     {week_label or '(未识别)'}  ({week_iso})")
    lines.append(f"输入 PDF: {input_pdf}")
    lines.append("")

    ok = sum(1 for e in events if e["fetch"]["status"] == "ok")
    failed = len(events) - ok
    extracted = sum(1 for e in events if e.get("fields"))
    lines.append(f"链接总数:   {len(events)}")
    lines.append(f"  下载成功: {ok}")
    lines.append(f"  失败/跳过: {failed}")
    lines.append(f"LLM 抽取成功: {extracted}")
    lines.append("")
    lines.append("-" * 70)

    for idx, e in enumerate(events, 1):
        f = e["fetch"]
        title = f.get("title") or "(无标题)"
        lines.append(f"[{idx}] {title}")
        lines.append(f"    stage:  {f.get('stage','')}")
        lines.append(f"    url:    {f.get('url','')}")
        lines.append(f"    status: {f.get('status','')} (http={f.get('http_status')})")
        if f.get("error"):
            lines.append(f"    error:  {f['error']}")
        if f.get("status") == "non_pdf":
            lines.append(f"    ⚠️  链接非 PDF，需手动下载")
        elif f.get("status") in {"http_error", "download_error"}:
            lines.append(f"    ⚠️  链接无法访问，需手动确认")
        lines.append(f"    分类:   {' / '.join(e.get('categories', []))}")
        if e.get("fields"):
            fld = e["fields"]
            lines.append(f"    日期:   {fld.get('date','') or '(原文未说明)'}")
            lines.append(f"    报名:   {fld.get('signup_required','')}")
        lines.append("")

    out_path.write_text("\n".join(lines))
