"""
Daily AI Infrastructure Cost Report.

Reads logs/llm_audit/cost_log.jsonl and outputs an aggregated daily summary.
Report is written to logs/llm_audit/daily_report_YYYY-MM-DD.txt and printed to stdout.

Usage:
    python -m shared.reporting.cost_report              # today
    python -m shared.reporting.cost_report 2026-05-18   # specific date
    python -m shared.reporting.cost_report --all         # all dates in log
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_COST_LOG = Path("/Volumes/AI_DISK/ai_workspace/logs/llm_audit/cost_log.jsonl")
_AUDIT_LOG = Path("/Volumes/AI_DISK/ai_workspace/logs/llm_audit/audit.jsonl")
_REPORT_DIR = Path("/Volumes/AI_DISK/ai_workspace/logs/llm_audit")


def _load_records(date_str: str | None) -> list[dict]:
    """Load cost_log records, optionally filtered to a single date."""
    records: list[dict] = []
    for path in (_COST_LOG, _AUDIT_LOG):
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if date_str and rec.get("ts", "")[:10] != date_str:
                    continue
                records.append(rec)
        break  # prefer cost_log; fall back to audit_log only if cost_log missing
    return records


def _aggregate(records: list[dict]) -> dict:
    agg: dict = {
        "total_calls":         0,
        "total_input_tokens":  0,
        "total_output_tokens": 0,
        "total_tool_calls":    0,
        "total_cost_usd":      0.0,
        "total_latency_ms":    0.0,
        "total_retries":       0,
        "by_model":            defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}),
        "by_agent":            defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "tool_calls": 0}),
        "by_task":             defaultdict(lambda: {"calls": 0, "cost_usd": 0.0}),
    }
    for rec in records:
        agg["total_calls"]         += 1
        agg["total_input_tokens"]  += rec.get("input_tokens",  0)
        agg["total_output_tokens"] += rec.get("output_tokens", 0)
        agg["total_tool_calls"]    += rec.get("tool_calls",    0)
        agg["total_cost_usd"]      += rec.get("cost_usd",      0.0)
        agg["total_latency_ms"]    += rec.get("latency_ms",    0.0) or 0.0
        agg["total_retries"]       += rec.get("retries",       0)

        m = rec.get("model_id", "unknown")
        agg["by_model"][m]["calls"]         += 1
        agg["by_model"][m]["input_tokens"]  += rec.get("input_tokens", 0)
        agg["by_model"][m]["output_tokens"] += rec.get("output_tokens", 0)
        agg["by_model"][m]["cost_usd"]      += rec.get("cost_usd", 0.0)

        a = rec.get("agent", "unknown")
        agg["by_agent"][a]["calls"]         += 1
        agg["by_agent"][a]["input_tokens"]  += rec.get("input_tokens", 0)
        agg["by_agent"][a]["output_tokens"] += rec.get("output_tokens", 0)
        agg["by_agent"][a]["cost_usd"]      += rec.get("cost_usd", 0.0)
        agg["by_agent"][a]["tool_calls"]    += rec.get("tool_calls", 0)

        t = rec.get("task_type", "unknown")
        agg["by_task"][t]["calls"]    += 1
        agg["by_task"][t]["cost_usd"] += rec.get("cost_usd", 0.0)

    return agg


def _format_report(date_str: str, agg: dict) -> str:
    lines: list[str] = []
    sep = "=" * 60

    avg_latency = (
        agg["total_latency_ms"] / agg["total_calls"]
        if agg["total_calls"] > 0 else 0.0
    )

    lines += [
        sep,
        f"  AI INFRASTRUCTURE COST REPORT — {date_str}",
        sep,
        "",
        "── SUMMARY ──────────────────────────────────────────────",
        f"  Total LLM calls   : {agg['total_calls']:>8}",
        f"  Input tokens      : {agg['total_input_tokens']:>8,}",
        f"  Output tokens     : {agg['total_output_tokens']:>8,}",
        f"  Tool calls        : {agg['total_tool_calls']:>8}",
        f"  Retries           : {agg['total_retries']:>8}",
        f"  Avg latency       : {avg_latency:>7.0f} ms",
        f"  Estimated cost    : ${agg['total_cost_usd']:>9.6f} USD",
        "",
    ]

    if agg["by_model"]:
        lines.append("── BY MODEL ─────────────────────────────────────────────")
        for model, s in sorted(agg["by_model"].items(), key=lambda x: -x[1]["cost_usd"]):
            lines.append(
                f"  {model:<30}  calls={s['calls']:>4}  "
                f"in={s['input_tokens']:>7,}  out={s['output_tokens']:>7,}  "
                f"${s['cost_usd']:.6f}"
            )
        lines.append("")

    if agg["by_agent"]:
        lines.append("── BY AGENT ─────────────────────────────────────────────")
        for agent, s in sorted(agg["by_agent"].items(), key=lambda x: -x[1]["cost_usd"]):
            lines.append(
                f"  {agent:<28}  calls={s['calls']:>4}  "
                f"tools={s['tool_calls']:>3}  "
                f"${s['cost_usd']:.6f}"
            )
        lines.append("")

    if agg["by_task"]:
        lines.append("── BY TASK TYPE ─────────────────────────────────────────")
        for task, s in sorted(agg["by_task"].items(), key=lambda x: -x[1]["calls"]):
            lines.append(
                f"  {task:<30}  calls={s['calls']:>4}  ${s['cost_usd']:.6f}"
            )
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


def generate_report(date_str: str | None = None, save: bool = True) -> str:
    """Generate and optionally save the daily cost report. Returns the report text."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).date().isoformat()

    records = _load_records(date_str)
    agg = _aggregate(records)
    report = _format_report(date_str, agg)

    if save:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _REPORT_DIR / f"daily_report_{date_str}.txt"
        out_path.write_text(report, encoding="utf-8")

    return report


def _list_dates() -> list[str]:
    """Return all unique dates present in the cost log."""
    dates: set[str] = set()
    if _COST_LOG.exists():
        with open(_COST_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    d = rec.get("ts", "")[:10]
                    if d:
                        dates.add(d)
                except json.JSONDecodeError:
                    pass
    return sorted(dates)


def main() -> None:
    args = sys.argv[1:]

    if "--all" in args:
        for d in _list_dates():
            print(generate_report(d, save=True))
        return

    date_str = args[0] if args else None
    print(generate_report(date_str, save=True))


if __name__ == "__main__":
    main()
