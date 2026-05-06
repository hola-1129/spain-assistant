#!/usr/bin/env python3
"""School Helper — 处理学校周通知 PDF，输出中文家长版周报 + 日历文件。"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from analyzer.extractor import (classify_audience, event_to_dict, extract_event,
                                needs_parent_action)
from analyzer.llm_client import LLMClient
from config import load_config
from parsers.linked_pdf_fetcher import LinkedPdfFetcher
from parsers.pdf_reader import parse_main_pdf
from utils.logger import setup_logger

logger = setup_logger("main")


def find_latest_pdf(input_dir: Path) -> Path | None:
    pdfs = [p for p in input_dir.glob("*.pdf") if not p.name.startswith("._")]
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="school_helper",
        description="处理学校 Briefing Semanal PDF，生成中文家长周报 + ICS 日历",
    )
    p.add_argument("--input", type=Path, help="主 PDF 路径，默认取 input/ 下最新")
    p.add_argument("--week-label", help="覆盖周标签（如 2026-W19）；默认从 PDF 抽取")
    p.add_argument("--no-llm", action="store_true", help="跳过 LLM 调用，仅做 PDF/链接提取")
    return p.parse_args()


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

    output_root = Path(cfg["paths"]["output_dir"]) / week_iso
    cache_dir = output_root / cfg.get("fetch", {}).get("cache_subdir", "cache")
    output_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"周次={parsed.get('week_label') or '?'}  "
        f"链接数={len(parsed['items'])}  输出目录={output_root}"
    )

    # ========== Step 2: 下载并解析每个链接 ==========
    fetcher = LinkedPdfFetcher(cache_dir, cfg)
    fetched: list[dict] = []
    for idx, item in enumerate(parsed["items"], 1):
        logger.info(f"[{idx}/{len(parsed['items'])}] {item.get('title','(无标题)')[:40]} ← {item['url'][:70]}")
        res = fetcher.fetch(item["url"])
        fetched.append({
            "title":       item.get("title", ""),
            "stage":       item.get("stage", ""),
            "url":         item["url"],
            "status":      res.status,
            "http_status": res.http_status,
            "cache_path":  res.cache_path,
            "error":       res.error,
            "text_length": len(res.text or ""),
            "_text":       res.text,  # batch③ 会用，最终写文件时会剔除
        })

    # 中间产物：方便 batch③/④ 调试
    debug_path = output_root / "_parsed_links.json"
    debug_path.write_text(
        json.dumps(
            {
                "week_label": parsed.get("week_label"),
                "week_iso":   week_iso,
                "items":      [{k: v for k, v in r.items() if k != "_text"} for r in fetched],
            },
            ensure_ascii=False, indent=2,
        )
    )
    logger.info(f"链接抽取摘要 → {debug_path}")

    if args.no_llm:
        logger.info("--no-llm 已设置，仅完成 parser 阶段。")
        return 0

    # ========== Step 3: LLM 结构化抽取 ==========
    llm = LLMClient(cfg)
    events: list[dict] = []
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

    debug_events_path = output_root / "_events.json"
    debug_events_path.write_text(json.dumps(
        [{**e, "fetch": {k: v for k, v in e["fetch"].items() if k != "_text"}}
         for e in events],
        ensure_ascii=False, indent=2,
    ))
    logger.info(f"事项结构化结果 → {debug_events_path}")

    logger.info("TODO(batch④): renderers 尚未接入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
