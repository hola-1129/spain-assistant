"""Trace id generation + minimal structured logging (stderr JSON lines)."""
from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any


def gen_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def log_event(event: str, **fields: Any) -> None:
    record = {"ts": time.time(), "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stderr)
