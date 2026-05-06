"""下载（或读取）主 PDF 中的每个链接，抽取文本。

- 优先把 URL 解析为 PDF 直链：响应 Content-Type 必须是 application/pdf；否则标记需手动下载
- 缓存到 <cache_dir>/<sha1(url)>.pdf；下次跳过下载
- 失败原因写到返回结果里供 processing_log 使用
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import requests

from utils.logger import setup_logger

logger = setup_logger("linked_pdf_fetcher")

_GDRIVE_FILE_RE = re.compile(r"https?://drive\.google\.com/file/d/([A-Za-z0-9_-]+)")
_GDRIVE_OPEN_RE = re.compile(r"https?://drive\.google\.com/open\?id=([A-Za-z0-9_-]+)")


def rewrite_url(url: str) -> str:
    """把 Google Drive 浏览页 URL 改成可直接下载的 URL。"""
    m = _GDRIVE_FILE_RE.search(url) or _GDRIVE_OPEN_RE.search(url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


@dataclass
class FetchResult:
    url: str
    status: str                       # "ok" | "non_pdf" | "http_error" | "parse_error" | "download_error"
    cache_path: str | None = None
    text: str = ""
    http_status: int | None = None
    error: str = ""
    extra: dict = field(default_factory=dict)


def _hash_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class LinkedPdfFetcher:
    def __init__(self, cache_dir: Path, cfg: dict):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fetch_cfg = cfg.get("fetch", {}) if cfg else {}
        self.user_agent  = fetch_cfg.get("user_agent", "Mozilla/5.0 (compatible; SchoolHelper/1.0)")
        self.timeout     = fetch_cfg.get("request_timeout_s", 30)
        self.max_retries = fetch_cfg.get("max_retries", 2)

    def fetch(self, url: str) -> FetchResult:
        # 缓存 key 用原始 url（保证主 PDF 中链接不变 → 缓存命中稳定）
        cache_path = self.cache_dir / f"{_hash_url(url)}.pdf"
        download_url = rewrite_url(url)

        # 命中缓存
        if cache_path.exists() and cache_path.stat().st_size > 0:
            text = self._extract_text(cache_path)
            if text is not None:
                return FetchResult(url=url, status="ok", cache_path=str(cache_path), text=text,
                                   extra={"cached": True})

        # 下载
        last_err = ""
        last_status = None
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = requests.get(
                    download_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                last_status = resp.status_code
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    continue
                ctype = resp.headers.get("Content-Type", "").lower()
                if "pdf" not in ctype and not resp.content[:4].startswith(b"%PDF"):
                    return FetchResult(
                        url=url, status="non_pdf",
                        http_status=resp.status_code,
                        error=f"Content-Type={ctype} 非 PDF（可能是网页/重定向到登录），需手动下载",
                    )
                cache_path.write_bytes(resp.content)
                text = self._extract_text(cache_path)
                if text is None:
                    return FetchResult(url=url, status="parse_error",
                                       cache_path=str(cache_path),
                                       http_status=resp.status_code,
                                       error="PDF 已下载但解析失败")
                return FetchResult(url=url, status="ok", cache_path=str(cache_path), text=text,
                                   http_status=resp.status_code)
            except requests.RequestException as e:
                last_err = str(e)
                logger.warning(f"下载失败 attempt={attempt} url={url} err={e}")

        return FetchResult(url=url, status="download_error", http_status=last_status, error=last_err)

    @staticmethod
    def _extract_text(pdf_path: Path) -> str | None:
        try:
            doc = fitz.open(pdf_path)
            parts = [p.get_text() for p in doc]
            doc.close()
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"PyMuPDF 解析失败 {pdf_path}: {e}")
            return None
