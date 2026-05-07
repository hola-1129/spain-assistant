#!/usr/bin/env python3
"""School Helper — 处理学校周通知 PDF，输出 GitHub Pages 静态站点。

每次运行：
  1. 解析 input/ 下最新的 Briefing 主 PDF
  2. 下载并解析每个链接对应的事项 PDF（缓存在 output/cache/，不发布）
  3. 调 LLM 把每条事项抽成结构化字段
  4. 若 output/ 已有上一周内容（week_iso 不同），先归档到 output/archive/<prev>/
  5. 在 output/ 顶层写 index.html / school_events.ics / events/*.ics / md / txt / log
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from analyzer.almanac import fetch_week_almanac
from analyzer.extractor import (classify_audience, event_to_dict, extract_event,
                                needs_parent_action)
from analyzer.llm_client import LLMClient
from analyzer.weather import WeatherForecast
from config import load_config
from parsers.linked_pdf_fetcher import LinkedPdfFetcher
from parsers.pdf_reader import parse_main_pdf
from renderers.html_writer import write_html
from renderers.ics_writer import write_ics, write_per_event_ics
from renderers.log_writer import write_links_json, write_processing_log
from renderers.markdown_writer import write_markdown
from renderers.summary_writer import write_summary
from utils.logger import setup_logger

logger = setup_logger("main")

# 顶层产物（每次运行覆盖；先归档旧版本）
TOP_LEVEL_FILES = [
    "index.html",
    "school_events.ics",
    "weekly_briefing_cn.md",
    "weekly_briefing_summary.txt",
    "extracted_links.json",
    "processing_log.txt",
]


def find_latest_pdf(input_dir: Path) -> Path | None:
    pdfs = [p for p in input_dir.glob("*.pdf") if not p.name.startswith("._")]
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="school_helper",
        description="处理学校 Briefing Semanal PDF，生成 GitHub Pages 站点 + ICS 日历",
    )
    p.add_argument("--input", type=Path, help="主 PDF 路径，默认取 input/ 下最新")
    p.add_argument("--week-label", help="覆盖周标签（如 2026-W19）；默认从 PDF 抽取")
    p.add_argument("--no-llm", action="store_true", help="跳过 LLM 调用，仅做 PDF/链接提取")
    return p.parse_args()


def archive_previous(output_dir: Path, current_week_iso: str) -> str | None:
    """如果 output/ 已存在上一周内容（week_iso 与本次不同），归档到 archive/<prev>/。"""
    links_path = output_dir / "extracted_links.json"
    if not links_path.exists():
        return None
    try:
        prev = json.loads(links_path.read_text())
        prev_iso = prev.get("week_iso")
    except (json.JSONDecodeError, OSError):
        return None
    if not prev_iso or prev_iso == current_week_iso:
        return None

    archive_dir = output_dir / "archive" / prev_iso
    archive_dir.mkdir(parents=True, exist_ok=True)

    for fname in TOP_LEVEL_FILES:
        src = output_dir / fname
        if src.exists():
            shutil.move(str(src), str(archive_dir / fname))

    events_src = output_dir / "events"
    if events_src.exists():
        events_dst = archive_dir / "events"
        if events_dst.exists():
            shutil.rmtree(events_dst)
        shutil.move(str(events_src), str(events_dst))

    return prev_iso


def main() -> int:
    args = parse_args()

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"配置加载失败: {e}")
        return 1

    input_dir = Path(cfg["paths"]["input_dir"])
    pdf_path = args.input or find_latest_pdf(input_dir)
    if not pdf_path or not pdf_path.exists():
        logger.error(f"未找到输入 PDF（input_dir={input_dir}）")
        return 1

    logger.info(f"输入 PDF: {pdf_path}")

    # ========== Step 1: 解析主 PDF ==========
    parsed = parse_main_pdf(pdf_path)
    week_iso = args.week_label or parsed.get("week_iso") \
        or f"unknown-{datetime.now().strftime('%Y%m%d')}"

    output_dir = Path(cfg["paths"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / cfg.get("fetch", {}).get("cache_subdir", "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"周次={parsed.get('week_label') or '?'}  "
        f"链接数={len(parsed['items'])}  输出={output_dir}"
    )

    # 归档上一周
    archived = archive_previous(output_dir, week_iso)
    if archived:
        logger.info(f"上一周（{archived}）内容已归档到 archive/{archived}/")

    # ========== Step 2: 下载并解析每个链接 ==========
    fetcher = LinkedPdfFetcher(cache_dir, cfg)
    fetched: list[dict] = []
    for idx, item in enumerate(parsed["items"], 1):
        logger.info(
            f"[{idx}/{len(parsed['items'])}] {item.get('title','(无标题)')[:40]} "
            f"← {item['url'][:70]}"
        )
        res = fetcher.fetch(item["url"])
        fetched.append({
            "title":       item.get("title", ""),
            "stage":       item.get("stage", ""),
            "url":         item["url"],
            "status":      res.status,
            "http_status": res.http_status,
            "cache_path":  res.cache_path,  # 内部用，写公开文件时会过滤
            "error":       res.error,
            "text_length": len(res.text or ""),
            "_text":       res.text,
        })

    if args.no_llm:
        logger.info("--no-llm 已设置，跳过 LLM 阶段。")
        events: list[dict] = [
            {"fetch": fr, "categories": classify_audience(fr.get("stage", "")),
             "parent_action_needed": False, "fields": None}
            for fr in fetched
        ]
    else:
        # ========== Step 3: LLM 结构化抽取 ==========
        llm = LLMClient(cfg)
        events = []
        for idx, fr in enumerate(fetched, 1):
            if fr["status"] != "ok":
                logger.warning(
                    f"[{idx}/{len(fetched)}] 跳过抽取（{fr['status']}）: {fr.get('title','')}"
                )
                events.append({
                    "fetch":      fr,
                    "categories": classify_audience(fr.get("stage", "")),
                    "parent_action_needed": False,
                    "fields":     None,
                })
                continue

            logger.info(f"[{idx}/{len(fetched)}] LLM 抽取中: {fr.get('title','')[:50]}")
            ev = extract_event(
                llm,
                briefing_title=fr.get("title", ""),
                briefing_stage=fr.get("stage", ""),
                pdf_text=fr["_text"],
            )
            cats = classify_audience(ev.audience_es or fr.get("stage", ""), ev.audience_cn)
            events.append({
                "fetch":      fr,
                "categories": cats,
                "parent_action_needed": needs_parent_action(ev),
                "fields":     event_to_dict(ev),
            })

    # ========== Step 3.5: 给有日期的事件查天气（Open-Meteo, 默认 Madrid） ==========
    weather_cfg = cfg.get("weather", {}) or {}
    if not args.no_llm and weather_cfg.get("enabled", True):
        forecast = WeatherForecast(
            latitude      = weather_cfg.get("latitude", 40.52),
            longitude     = weather_cfg.get("longitude", -3.63),
            timezone      = cfg.get("calendar", {}).get("timezone", "Europe/Madrid"),
            forecast_days = int(weather_cfg.get("forecast_days", 16)),
        )
        for ev_wrap in events:
            fld = ev_wrap.get("fields")
            if fld and fld.get("date"):
                fld["weather"] = forecast.lookup(fld["date"])

    # ========== Step 3.6: 黄历 + 三地节假日 ==========
    almanac_data: dict = {}
    if not args.no_llm:
        try:
            almanac_data = fetch_week_almanac(llm, week_iso=week_iso)
        except Exception as e:
            logger.warning(f"黄历获取异常，跳过: {e}")

    # ========== Step 4: renderers ==========
    week_label = parsed.get("week_label", "")
    priority_grades = cfg.get("family", {}).get("priority_grades", [])

    md_path      = output_dir / "weekly_briefing_cn.md"
    summary_path = output_dir / "weekly_briefing_summary.txt"
    ics_path     = output_dir / "school_events.ics"
    events_dir   = output_dir / "events"
    links_path   = output_dir / "extracted_links.json"
    log_path     = output_dir / "processing_log.txt"
    html_path    = output_dir / "index.html"

    write_markdown(md_path, week_label=week_label, week_iso=week_iso,
                   events=events, priority_grades=priority_grades)
    write_summary(summary_path, week_label=week_label, week_iso=week_iso,
                  events=events, priority_grades=priority_grades)
    n_ics = write_ics(ics_path, week_iso=week_iso, events=events,
                      calendar_cfg=cfg.get("calendar", {}))
    ics_filenames = write_per_event_ics(events_dir, week_iso=week_iso, events=events,
                                        calendar_cfg=cfg.get("calendar", {}))
    write_links_json(links_path, week_label=week_label, week_iso=week_iso, events=events)
    write_processing_log(log_path, week_label=week_label, week_iso=week_iso,
                         input_pdf_name=Path(pdf_path).name, events=events)
    write_html(html_path, week_label=week_label, week_iso=week_iso,
               events=events, priority_grades=priority_grades,
               ics_filenames=ics_filenames, almanac_data=almanac_data)

    logger.info(f"输出文件:")
    logger.info(f"  {html_path}")
    logger.info(f"  {ics_path}  ({n_ics} 事件)")
    logger.info(f"  {events_dir}/  ({len(ics_filenames)} 单独 .ics)")
    logger.info(f"  {md_path}")
    logger.info(f"  {summary_path}")
    logger.info(f"  {links_path}")
    logger.info(f"  {log_path}")
    if archived:
        logger.info(f"  归档: {output_dir / 'archive' / archived}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
