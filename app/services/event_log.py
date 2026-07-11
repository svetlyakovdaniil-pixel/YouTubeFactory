import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
EVENTS_ROOT = PROJECT_ROOT / "logs" / "events"


def event_log_path(channel):
    safe_name = channel.replace("/", "_")
    return EVENTS_ROOT / f"{safe_name}.jsonl"


def add_event(channel, level, message, data=None):
    EVENTS_ROOT.mkdir(parents=True, exist_ok=True)

    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "level": level,
        "message": message,
        "data": data or {},
    }

    with open(event_log_path(channel), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def read_events(channel, limit=120):
    path = event_log_path(channel)

    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    events = []

    for line in lines[-limit:]:
        line = line.strip()

        if not line:
            continue

        try:
            events.append(json.loads(line))
        except Exception:
            events.append(
                {
                    "time": "",
                    "channel": channel,
                    "level": "raw",
                    "message": line,
                    "data": {},
                }
            )

    return events


def clear_events(channel):
    path = event_log_path(channel)

    if path.exists():
        path.unlink()
