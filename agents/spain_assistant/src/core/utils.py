"""通用工具函数。"""

import re
import unicodedata
from datetime import datetime
import pytz
from src.core import config


def now_madrid() -> datetime:
    tz = pytz.timezone(config.get("app.timezone", "Europe/Madrid"))
    return datetime.now(tz)


def run_id() -> str:
    return now_madrid().strftime("%Y%m%d_%H%M%S")


def today_str() -> str:
    return now_madrid().strftime("%Y-%m-%d")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")[:80]


def truncate(text: str, max_len: int = 200) -> str:
    return text[:max_len].rstrip() + "…" if len(text) > max_len else text


def safe_strip(val) -> str:
    return str(val).strip() if val else ""
