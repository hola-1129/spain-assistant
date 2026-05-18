"""持久化层：state.json（去重记录）+ raw/processed JSON 存储。"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core import config
from src.core.logger import get_logger

log = get_logger(__name__)


def compute_hash(title: str, date: str) -> str:
    raw = f"{title.strip()}{date.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_state() -> dict:
    sf = config.state_file
    if sf.exists():
        try:
            return json.loads(sf.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"读取 state.json 失败，重新初始化: {e}")
    return {"seen_hashes": {}, "last_run": {}}


def save_state(state: dict):
    config.state_file.parent.mkdir(parents=True, exist_ok=True)
    config.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_seen(hash_id: str, state: dict) -> bool:
    return hash_id in state.get("seen_hashes", {})


def mark_seen(hash_id: str, state: dict, meta: Optional[dict] = None):
    state.setdefault("seen_hashes", {})[hash_id] = {
        "seen_at": datetime.now().isoformat(),
        **(meta or {}),
    }


def save_raw(module: str, articles: list, run_id: str):
    out_dir = config.raw_dir / module
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[storage] 原始数据已保存: {path}")


def save_processed(module: str, articles: list, run_id: str):
    out_dir = config.processed_dir / module
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[storage] 处理数据已保存: {path}")


def purge_old_files(base_dir: Path, days: int):
    """清理超过保留期的文件。"""
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for f in base_dir.rglob("*.json"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            removed += 1
    if removed:
        log.info(f"[storage] 已清理 {removed} 个过期文件（{base_dir}）")
