#!/bin/bash
# Wait for the external volume to be mounted (up to 60s at boot)
for i in $(seq 1 12); do
    [ -d /Volumes/AI_DISK/ai_workspace ] && break
    sleep 5
done

if [ ! -d /Volumes/AI_DISK/ai_workspace ]; then
    echo "$(date) ERROR: /Volumes/AI_DISK not mounted, aborting" >&2
    exit 1
fi

cd /Volumes/AI_DISK/ai_workspace/agents/ai_narrative_rotation_radar
exec .venv/bin/python main.py
