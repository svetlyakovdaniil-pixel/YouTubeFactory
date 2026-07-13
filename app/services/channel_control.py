import subprocess
from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.services.channel_status import service_name
from app.youtube.api_retry import safe_execute
from app.youtube.auth import get_youtube_service
from app.youtube.live_stream import YouTubeLiveStream


PROJECT_ROOT = Path("/opt/youtubefactory")
RUNTIME_DIR = PROJECT_ROOT / "runtime"


def _run_systemctl(*args):
    result = subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _remove_runtime_flags(channel):
    paths = [
        RUNTIME_DIR / f"{channel}.running",
        RUNTIME_DIR / f"{channel}.cycle_waiting",
    ]

    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _list_active_broadcast_ids(channel):
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
            f"Поиск активных трансляций канала {channel}"
        ),
    )

    return [
        item.get("id", "")
        for item in response.get("items", [])
        if item.get("id")
    ]


def _collect_broadcast_ids(channel, state):
    broadcast_ids = []

    state_broadcast_id = state.get("broadcast_id", "")
    if state_broadcast_id:
        broadcast_ids.append(state_broadcast_id)

    for broadcast_id in _list_active_broadcast_ids(channel):
        if broadcast_id not in broadcast_ids:
            broadcast_ids.append(broadcast_id)

    return broadcast_ids


def _reset_stopped_state(channel, clear_event=True):
    library = ChannelLibrary(channel)
    state = library.get_state()

    state.update({
        "running": False,
        "paused": False,
        "watch_url": "",
        "started_at": "",
        "current_track": "",
        "track_index": 0,
        "last_error": "",
    })

    if clear_event:
        state.update({
            "broadcast_id": "",
            "stream_id": "",
            "rtmp_url": "",
            "stream_key": "",
        })

    library.save_state(state)


def stop_channel_fully(channel):
    """
    Полностью останавливает канал:

    1. Останавливает systemd и FFmpeg.
    2. Удаляет runtime-флаги.
    3. Находит активные YouTube broadcast.
    4. Завершает их через YouTube API.
    5. Снимает аварийную паузу и очищает state.
    """
    stop_result = _run_systemctl(
        "stop",
        service_name(channel),
    )

    _remove_runtime_flags(channel)

    library = ChannelLibrary(channel)
    state = library.get_state()

    finished = []
    errors = []

    try:
        broadcast_ids = _collect_broadcast_ids(
            channel,
            state,
        )
    except Exception as exc:
        broadcast_ids = []

        state_broadcast_id = state.get(
            "broadcast_id",
            "",
        )

        if state_broadcast_id:
            broadcast_ids.append(
                state_broadcast_id
            )

        errors.append(
            f"Не удалось получить список активных "
            f"трансляций: {exc}"
        )

    live = YouTubeLiveStream(channel)

    for broadcast_id in broadcast_ids:
        try:
            result = live.finish_broadcast(
                broadcast_id
            )

            finished.append({
                "broadcast_id": broadcast_id,
                "action": result.get(
                    "action",
                    "nothing",
                ),
                "status": result.get(
                    "status",
                    "",
                ),
            })

        except Exception as exc:
            errors.append(
                f"{broadcast_id}: {exc}"
            )

    clear_event = len(errors) == 0

    _reset_stopped_state(
        channel,
        clear_event=clear_event,
    )

    if stop_result["code"] != 0:
        errors.append(
            stop_result["stderr"]
            or stop_result["stdout"]
            or "systemctl stop завершился с ошибкой"
        )

    if errors:
        return {
            "ok": False,
            "code": 1,
            "stdout": "",
            "stderr": "\n".join(errors),
            "finished": finished,
        }

    finished_count = len(finished)

    return {
        "ok": True,
        "code": 0,
        "stdout": (
            "Канал полностью остановлен. "
            f"Завершено YouTube-трансляций: "
            f"{finished_count}."
        ),
        "stderr": "",
        "finished": finished,
    }
