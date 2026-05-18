"""Runtime state helpers."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def data_path(root: Path, cfg: dict[str, Any], key: str, default_rel: str) -> Path:
    rel = cfg.get("logging", {}).get(key, default_rel)
    p = Path(rel)
    if not p.is_absolute():
        p = (root / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_runtime_state(root: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    p = data_path(root, cfg, "runtime_state_path", "data/runtime_state.json")
    if not p.exists():
        return {"pm_state": {}, "alert_state": {}}
    try:
        with p.open("r") as f:
            data = json.load(f) or {}
    except Exception as e:
        logging.getLogger("web3_monitor.state").warning("runtime state load failed: %s", e)
        return {"pm_state": {}, "alert_state": {}}
    return {
        "pm_state": data.get("pm_state") or {},
        "alert_state": data.get("alert_state") or {},
    }


def save_runtime_state(root: Path, cfg: dict[str, Any], pm_state: dict, alert_state: dict[str, float]) -> None:
    p = data_path(root, cfg, "runtime_state_path", "data/runtime_state.json")
    tmp = p.with_suffix(".json.tmp")
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pm_state": pm_state,
        "alert_state": alert_state,
    }
    with tmp.open("w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)
