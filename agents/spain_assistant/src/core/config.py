"""全局配置加载器。统一读取 config.yaml + .env，对外暴露 cfg 单例。"""

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = _ROOT / ".env"
_CONFIG_FILE = _ROOT / "config.yaml"


def _load() -> dict:
    load_dotenv(_ENV_FILE, override=False)
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_raw: dict = _load()


def get(key_path: str, default=None):
    """点分路径取值，如 get('telegram.enabled')。"""
    parts = key_path.split(".")
    node = _raw
    for p in parts:
        if not isinstance(node, dict):
            return default
        node = node.get(p)
        if node is None:
            return default
    return node


def env(key: str, default: str = "") -> str:
    """读取环境变量，支持 config 中定义的 *_env 间接引用。"""
    return os.getenv(key, default)


def secret(env_key_name: str) -> str:
    """通过 config 中 *_env 字段读取对应环境变量值。"""
    key = get(env_key_name, "")
    return os.getenv(key, "") if key else ""


root_dir = _ROOT
data_dir = _ROOT / "data"
public_dir = _ROOT / get("output.dir", "public")
logs_dir = _ROOT / "logs"
raw_dir = data_dir / "raw"
processed_dir = data_dir / "processed"
state_file = data_dir / "state.json"
