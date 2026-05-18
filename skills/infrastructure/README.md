# Infrastructure Domain

Covers: agent lifecycle, service auto-start, log rotation, workspace tooling, macOS system config.

## Operational Rules

1. **No destructive actions** (rm -rf, force push, branch -D, drop table) without explicit user confirmation.
2. **launchd / plist changes** require confirmation — they affect system boot behavior.
3. **macOS TCC constraint**: launchd agents cannot `open()` files on external drives (AI_DISK) without Full Disk Access granted to the shell binary. Prefer `nohup` when TCC permission is not granted.
4. **Python venvs are per-agent** — each agent maintains its own `.venv/`; never share.
5. **Log rotation**: retain 30 days minimum; `logs/` is git-ignored.
6. **PID files**: every long-running agent writes `logs/<agent>/<agent>.pid`.

## macOS TCC Workaround

launchd agents on AI_DISK (external drive) will hit PermissionError unless `/bin/bash` (or the shell binary) has Full Disk Access:

```
System Settings → Privacy & Security → Full Disk Access → Add /bin/bash
```

Fallback (no TCC): run via nohup from terminal:
```bash
cd /Volumes/AI_DISK/ai_workspace/agents/<agent>
nohup .venv/bin/python main.py > ../../logs/<agent>/stdout.log 2>&1 &
echo $! > ../../logs/<agent>/<agent>.pid
```

## Agent Start Commands

See `CLAUDE.md` → Current Agents table for canonical start commands per agent.

## launchd Plist Locations

```
~/Library/LaunchAgents/com.leslie.<agent>.plist
```

Logs from plist go to: `~/Library/Logs/<agent>/` (internal disk, always writable).

## Health Check

```bash
# Check PID
cat logs/<agent>/<agent>.pid
ps aux | grep <agent>

# Check launchd
launchctl list | grep <agent>
```

## Key Paths

| Resource | Path |
|----------|------|
| Agent code | `/Volumes/AI_DISK/ai_workspace/agents/<name>/` |
| Logs | `/Volumes/AI_DISK/ai_workspace/logs/<name>/` |
| Data / DB | `/Volumes/AI_DISK/ai_workspace/data/` |
| launchd plists | `~/Library/LaunchAgents/` |
| launchd logs | `~/Library/Logs/<agent>/` |
