from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

AGENT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = AGENT_ROOT.parent.parent
LOG_DIR = WORKSPACE_ROOT / "logs" / "polymarket_intelligence"


def load_config(path: str | None = None) -> dict:
    config_path = Path(path) if path else AGENT_ROOT / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)
