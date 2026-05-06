"""主 PDF 解析：抽取周次/日期、每行标题与年级，以及链接注释 (URI annotations)。

输出结构：
{
  "week_label": "Semana: 4 de MAYO 2026",   # 原文
  "week_iso":   "2026-W19",                  # 推断的 ISO 周（best-effort）
  "items": [
    {"title": "...", "stage": "GENERAL", "url": "https://..."},
    ...
  ],
  "raw_text": "..."
}

链接抽取走 PyMuPDF 的 page.get_links()，匹配每条链接矩形所在的文字行。
"""

import re
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

from utils.logger import setup_logger

logger = setup_logger("pdf_reader")

_WEEK_RE = re.compile(r"Semana[:：]?\s*([0-9]+)\s*de\s*([A-Za-záéíóúÁÉÍÓÚ]+)\s*([0-9]{4})", re.IGNORECASE)

_MONTH_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _iso_week_from_label(week_label: str) -> str | None:
    m = _WEEK_RE.search(week_label or "")
    if not m:
        return None
    day, month_es, year = m.group(1), m.group(2).lower(), m.group(3)
    month = _MONTH_ES.get(month_es)
    if not month:
        return None
    try:
        d = date(int(year), month, int(day))
        iso = d.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    except ValueError:
        return None


def _line_text_for_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    """找到与给定矩形重叠的文本行内容（用于把链接关联到标题）。"""
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            line_rect = fitz.Rect(line["bbox"])
            if line_rect.intersects(rect):
                return "".join(span.get("text", "") for span in line.get("spans", [])).strip()
    return ""


def _stage_for_title_row(page: fitz.Page, link_rect: fitz.Rect) -> str:
    """同一行最右侧（'Etapa / Curso' 列）的文本作为年级/阶段。"""
    text_dict = page.get_text("dict")
    candidates: list[tuple[fitz.Rect, str]] = []
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            lrect = fitz.Rect(line["bbox"])
            # 与链接行水平重叠（y 区间相近），但 x 在右侧
            if abs((lrect.y0 + lrect.y1) / 2 - (link_rect.y0 + link_rect.y1) / 2) < 6 \
               and lrect.x0 > link_rect.x1 - 5:
                txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                if txt:
                    candidates.append((lrect, txt))
    if not candidates:
        return ""
    # 取最右侧
    candidates.sort(key=lambda x: -x[0].x1)
    return candidates[0][1]


def parse_main_pdf(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    raw_text_parts: list[str] = []
    items: list[dict] = []
    seen_urls: set[str] = set()

    week_label = ""

    for page_idx, page in enumerate(doc):
        ptext = page.get_text()
        raw_text_parts.append(ptext)

        if not week_label:
            m = _WEEK_RE.search(ptext)
            if m:
                week_label = m.group(0).strip()

        for link in page.get_links():
            uri = link.get("uri")
            if not uri:
                continue
            rect = fitz.Rect(link.get("from"))
            title = _line_text_for_rect(page, rect)
            stage = _stage_for_title_row(page, rect)

            # 同一 URI 多个矩形（多行链接）合并：保留第一个非空 title
            if uri in seen_urls:
                # 已有；尝试补齐空字段
                for it in items:
                    if it["url"] == uri:
                        if not it.get("title") and title:
                            it["title"] = title
                        if not it.get("stage") and stage:
                            it["stage"] = stage
                        break
                continue
            seen_urls.add(uri)

            items.append({
                "title":   title,
                "stage":   stage,
                "url":     uri,
                "page":    page_idx + 1,
            })

    doc.close()

    week_iso = _iso_week_from_label(week_label) if week_label else None
    logger.info(f"主 PDF 解析完成: week='{week_label}' iso='{week_iso}' 链接={len(items)}")

    return {
        "week_label": week_label,
        "week_iso":   week_iso,
        "items":      items,
        "raw_text":   "\n".join(raw_text_parts),
    }
