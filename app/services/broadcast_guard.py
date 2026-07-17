import sys
import time
from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.youtube.api_retry import safe_execute
from app.youtube.auth import get_youtube_service
from app.youtube.live_stream import YouTubeLiveStream


PROJECT_ROOT = Path("/opt/youtubefactory")
RUNTIME_DIR = PROJECT_ROOT / "runtime"


def list_active_broadcast_ids(channel):
    youtube = get_youtube_service(channel)

    request = youtube.liveBroadcasts().list(
        part="id,snippet,status",
        broadcastStatus="active",
        broadcastType="all",
        maxResults=50,
    )

    response = safe_execute(
        request,
        operation_name=(
            f"Проверка активных трансляций перед запуском: "
            f"{channel}"
        ),
    )

    return [
        item["id"]
        for item in response.get("items", [])
        if item.get("id")
    ]


def clear_local_event_state(channel):
    library = ChannelLibrary(channel)
    state = library.get_state()

    state.update(
        {
            "running": False,
            "watch_url": "",
            "started_at": "",
            "current_track": "",
            "track_index": 0,
            "broadcast_id": "",
            "stream_id": "",
            "rtmp_url": "",
            "stream_key": "",
        }
    )

    library.save_state(state)


def has_complete_persisted_event(state):
    required = (
        "broadcast_id",
        "stream_id",
        "rtmp_url",
        "stream_key",
        "watch_url",
        "started_at",
    )
    return all(state.get(key) for key in required)


def finish_broadcast_ids(channel, broadcast_ids):
    live = YouTubeLiveStream(channel)
    results = []

    for broadcast_id in broadcast_ids:
        result = live.finish_broadcast(broadcast_id)

        results.append(
            {
                "broadcast_id": broadcast_id,
                "action": result.get("action", "nothing"),
                "status": result.get("status", ""),
            }
        )

    return results


def prepare_for_worker_start(channel):
    library = ChannelLibrary(channel)
    state = library.get_state()
    active_ids = list_active_broadcast_ids(channel)

    preserved_id = ""
    if has_complete_persisted_event(state):
        preserved_id = state.get("broadcast_id", "")

    ids_to_finish = [
        broadcast_id
        for broadcast_id in active_ids
        if broadcast_id != preserved_id
    ]

    results = finish_broadcast_ids(channel, ids_to_finish)

    if preserved_id:
        state.update(
            {
                "running": False,
                "current_track": "",
                "track_index": 0,
                "last_error": "",
            }
        )
        library.save_state(state)
    else:
        clear_local_event_state(channel)

    return {
        "preserved_broadcast_id": preserved_id,
        "closed": results,
    }

def remove_runtime_flags(channel):
    for suffix in (
        "running",
        "cycle_waiting",
    ):
        path = RUNTIME_DIR / f"{channel}.{suffix}"

        try:
            path.unlink()
        except FileNotFoundError:
            pass


def process_exists(pid):
    if pid <= 0:
        return False

    return Path(f"/proc/{pid}").exists()


def graceful_stop(channel, main_pid, timeout=75):
    remove_runtime_flags(channel)

    deadline = time.monotonic() + timeout

    while process_exists(main_pid) and time.monotonic() < deadline:
        time.sleep(1)

    if process_exists(main_pid):
        print(
            f"[{channel}] Worker did not exit "
            f"within {timeout} seconds.",
            flush=True,
        )
        return 1

    print(
        f"[{channel}] Worker stopped gracefully. "
        "YouTube event state preserved.",
        flush=True,
    )
    return 0


def prestart_guard(channel):
    result = prepare_for_worker_start(channel)

    remove_runtime_flags(channel)

    preserved_id = result["preserved_broadcast_id"]
    closed = result["closed"]

    print(
        f"[{channel}] Pre-start guard finished. "
        f"Preserved broadcast: {preserved_id or 'none'}. "
        f"Closed duplicate broadcasts: {len(closed)}.",
        flush=True,
    )

    for item in closed:
        print(
            f"[{channel}] "
            f"{item['broadcast_id']} | "
            f"{item['action']} | "
            f"{item['status']}",
            flush=True,
        )

    return 0


def main():
    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: broadcast_guard.py "
            "<prestart|stop> <channel> [main_pid]"
        )

    action = sys.argv[1]
    channel = sys.argv[2]

    if action == "prestart":
        raise SystemExit(prestart_guard(channel))

    if action == "stop":
        main_pid = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
        raise SystemExit(graceful_stop(channel, main_pid))

    raise SystemExit(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
