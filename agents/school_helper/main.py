#!/usr/bin/env python3
"""School Helper — 处理学校周通知 PDF，输出中文家长版周报 + 日历文件。"""

import argparse
import sys
from pathlib import Path

from config import load_config
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
    logger.info(f"骨架阶段：尚未接入 parser/analyzer/renderer，本次仅校验配置和路径。")
    # TODO(batch②): parsers.pdf_reader + parsers.linked_pdf_fetcher
    # TODO(batch③): analyzer.extractor (LLM)
    # TODO(batch④): renderers.markdown / summary / ics / log
    return 0


if __name__ == "__main__":
    sys.exit(main())
