import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.channel_library import ChannelLibrary
from app.services.radio_service import RadioService
from app.services.telegram_notifier import (
    notify_error,
    notify_info,
    notify_warning,
)
from app.services.event_log import add_event
from app.services.error_advisor import analyze_error, format_advice
from app.services.preflight_manager import assert_preflight_ok
from app.services.metadata_manager import pick_stream_metadata
from app.services.ffmpeg_analyzer import format_ffmpeg_analysis
from app.services.maintenance_manager import (
    active_ffmpeg_processes,
    format_cleanup_report,
    run_cycle_maintenance,
)
from app.youtube.live_stream import YouTubeLiveStream
from app.youtube.publish import Publisher


LOG_FILE = PROJECT_ROOT / "logs" / "live_worker.log"
RUNTIME_DIR = PROJECT_ROOT / "runtime"

MAX_AUTO_RECOVERY_ATTEMPTS = 3
AUTO_RECOVERY_DELAY_SECONDS = 15
START_CONFIRM_SECONDS = 20
CYCLE_BARRIER_TIMEOUT_SECONDS = 180
CYCLE_BARRIER_POLL_SECONDS = 2
RESTORE_STATUS_RETRY_SECONDS = 45
RESTORE_STATUS_POLL_SECONDS = 3


def log(message):
    print(message, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(message + "\n")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def get_cycle_deadline(started_at, duration_hours):
    started = parse_iso(started_at)
    if started is None:
        return None
    return started + timedelta(hours=int(duration_hours))


def get_remaining_seconds(started_at, duration_hours):
    deadline = get_cycle_deadline(started_at, duration_hours)
    if deadline is None:
        return 0
    return max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))


def event(channel, level, message, data=None):
    add_event(
        channel=channel,
        level=level,
        message=message,
        data=data or {},
    )


def set_state(channel, **kwargs):
    library = ChannelLibrary(channel)
    state = library.get_state()
    state.update(kwargs)
    library.save_state(state)


def clear_event_state(channel):
    set_state(
        channel,
        broadcast_id="",
        stream_id="",
        rtmp_url="",
        stream_key="",
    )


def reset_state(channel):
    set_state(
        channel,
        running=False,
        watch_url="",
        started_at="",
        current_track="",
        track_index=0,
    )


def safe_runtime_name(channel):
    return str(channel).replace("/", "_")


def cycle_waiting_marker(channel):
    return RUNTIME_DIR / f"{safe_runtime_name(channel)}.cycle_waiting"


def clear_cycle_marker(channel):
    try:
        cycle_waiting_marker(channel).unlink()
    except FileNotFoundError:
        pass


def pause_channel(channel, error):
    flag = RUNTIME_DIR / f"{channel}.running"
    if flag.exists():
        flag.unlink()

    clear_cycle_marker(channel)
    set_state(
        channel,
        running=False,
        paused=True,
        watch_url="",
        started_at="",
        current_track="",
        track_index=0,
        last_error=error[-2000:],
    )

    if "автоматические попытки исчерпаны" in error.lower():
        notify_error(
            channel,
            "Автоматические попытки восстановления исчерпаны.\n\n"
            "Канал остановлен и больше не создаёт новые трансляции.\n\n"
            "Требуется ручная проверка причины в панели управления.\n\n"
            f"Технические детали:\n{error[-1200:]}",
        )
        return

    advice_text = format_advice(error)
    notify_error(
        channel,
        "Канал остановлен и ожидает вашего вмешательства.\n\n"
        f"{advice_text}\n\n"
        f"Технические детали:\n{error[-1200:]}",
    )


def clear_pause(channel):
    set_state(channel, paused=False, last_error="")


def active_channel_names():
    return sorted(
        path.name[:-len(".running")]
        for path in RUNTIME_DIR.glob("*.running")
    )


def all_active_channels_waiting():
    active = active_channel_names()
    if not active:
        return True
    return all(cycle_waiting_marker(name).exists() for name in active)


def wait_for_cycle_barrier(channel):
    marker = cycle_waiting_marker(channel)
    marker.write_text(now_iso(), encoding="utf-8")
    deadline = time.monotonic() + CYCLE_BARRIER_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if all_active_channels_waiting():
            return {"ok": True, "timed_out": False}
        time.sleep(CYCLE_BARRIER_POLL_SECONDS)

    if not active_ffmpeg_processes():
        return {"ok": True, "timed_out": True}

    return {"ok": False, "timed_out": True}


def run_between_streams_maintenance(channel):
    barrier = wait_for_cycle_barrier(channel)

    if not barrier.get("ok"):
        clear_cycle_marker(channel)
        event(
            channel,
            "warning",
            "Очистка между эфирами пропущена: другой канал ещё транслирует",
            barrier,
        )
        return {
            "ok": False,
            "skipped": True,
            "reason": "Другой канал ещё транслирует.",
        }

    result = run_cycle_maintenance()
    event(
        channel,
        "info",
        "Очистка между 12-часовыми эфирами завершена",
        result,
    )

    if not result.get("skipped"):
        notify_info(
            channel,
            format_cleanup_report(result)
            + "\n\nПосле очистки будет создан следующий эфир.",
        )

    clear_cycle_marker(channel)
    return result


def confirm_ffmpeg_started(ffmpeg_process, flag):
    deadline = time.monotonic() + START_CONFIRM_SECONDS
    while time.monotonic() < deadline:
        if not flag.exists() or not ffmpeg_process.is_running():
            return False
        time.sleep(1)
    return ffmpeg_process.is_running()


def persist_event_state(channel, stream_event, started_at=None):
    values = {
        "broadcast_id": stream_event.get("broadcast_id", ""),
        "stream_id": stream_event.get("stream_id", ""),
        "rtmp_url": stream_event.get("rtmp_url", ""),
        "stream_key": stream_event.get("stream_key", ""),
        "watch_url": stream_event.get("watch_url", ""),
    }

    if started_at is not None:
        values["started_at"] = started_at

    set_state(channel, **values)


def load_persisted_event(channel):
    state = ChannelLibrary(channel).get_state()
    required = (
        "broadcast_id",
        "stream_id",
        "rtmp_url",
        "stream_key",
        "watch_url",
        "started_at",
    )

    if not all(state.get(key) for key in required):
        return None

    return {
        "broadcast_id": state["broadcast_id"],
        "stream_id": state["stream_id"],
        "rtmp_url": state["rtmp_url"],
        "stream_key": state["stream_key"],
        "watch_url": state["watch_url"],
        "thumbnail_path": state.get("thumbnail_path", ""),
    }


def wait_until_event_reusable(channel, broadcast_id, stop_flag):
    live = YouTubeLiveStream(channel)
    deadline = time.monotonic() + RESTORE_STATUS_RETRY_SECONDS
    last_status = ""

    while stop_flag.exists() and time.monotonic() < deadline:
        try:
            last_status = live.get_lifecycle_status(broadcast_id)
            if last_status in {
                "created",
                "ready",
                "testing",
                "testStarting",
                "liveStarting",
                "live",
            }:
                return True, last_status
        except Exception:
            last_status = "api_error"

        time.sleep(RESTORE_STATUS_POLL_SECONDS)

    return False, last_status


def finish_youtube_event(channel, stream_event):
    if not stream_event:
        return None

    broadcast_id = stream_event.get(
        "broadcast_id",
        "",
    )

    if not broadcast_id:
        return None

    try:
        result = (
            YouTubeLiveStream(channel)
            .finish_broadcast(broadcast_id)
        )

        event(
            channel,
            "info",
            "YouTube-трансляция корректно завершена",
            {
                "broadcast_id": broadcast_id,
                "result": result,
            },
        )

        return result

    except Exception as exc:
        event(
            channel,
            "warning",
            "Не удалось завершить YouTube-трансляцию",
            {
                "broadcast_id": broadcast_id,
                "error": str(exc),
            },
        )

        return None


def cleanup_upcoming_event(channel, stream_event):
    if not stream_event or not stream_event.get("broadcast_id"):
        return None

    try:
        result = YouTubeLiveStream(channel).delete_if_upcoming(
            stream_event["broadcast_id"]
        )
        event(
            channel,
            "info",
            "Проверка незапущенной YouTube-трансляции",
            result,
        )
        return result
    except Exception as exc:
        event(
            channel,
            "warning",
            "Не удалось удалить незапущенную YouTube-трансляцию",
            {
                "broadcast_id": stream_event.get("broadcast_id", ""),
                "error": str(exc),
            },
        )
        return None


def run(channel):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    flag = RUNTIME_DIR / f"{channel}.running"

    log(f"===== Radio Worker started: {channel} =====")
    event(channel, "info", "Воркер запущен")
    clear_pause(channel)

    library = ChannelLibrary(channel)
    radio = RadioService(channel)
    publisher = Publisher()
    live = YouTubeLiveStream(channel)

    while flag.exists():
        stream_event = None

        try:
            config = library.get_config()
            duration_hours = int(config.get("stream_duration_hours", 12))

            set_state(
                channel,
                running=True,
                stream_duration_hours=duration_hours,
                last_error="",
            )

            event(channel, "info", "Preflight Check перед запуском")
            assert_preflight_ok(channel)
            event(channel, "success", "Preflight Check пройден")

            event(channel, "info", "Сборка плейлиста")
            playlist = radio.build_playlist()
            event(
                channel,
                "info",
                "Плейлист готов",
                {
                    "tracks": len(playlist.get("tracks", [])),
                    "total_seconds": playlist.get("total_seconds", 0),
                    "target_seconds": playlist.get("target_seconds", 0),
                },
            )

            state = library.get_state()
            started_at = state.get("started_at", "")
            stream_event = load_persisted_event(channel)
            restored_existing_event = stream_event is not None

            if stream_event and get_remaining_seconds(started_at, duration_hours) <= 0:
                finish_youtube_event(channel, stream_event)
                reset_state(channel)
                clear_event_state(channel)
                stream_event = None
                started_at = ""
                event(
                    channel,
                    "info",
                    "Срок текущего эфира истёк. YouTube-трансляция завершена",
                )
                run_between_streams_maintenance(channel)
                if not flag.exists():
                    break

            if stream_event:
                reusable, lifecycle_status = wait_until_event_reusable(
                    channel,
                    stream_event["broadcast_id"],
                    flag,
                )

                if not reusable:
                    event(
                        channel,
                        "warning",
                        "Сохранённая YouTube-трансляция недоступна для восстановления",
                        {
                            "broadcast_id": stream_event["broadcast_id"],
                            "lifecycle_status": lifecycle_status,
                            "started_at": started_at,
                        },
                    )
                    clear_event_state(channel)
                    reset_state(channel)
                    stream_event = None
                    started_at = ""
                else:
                    event(
                        channel,
                        "info",
                        "Восстановление существующей YouTube-трансляции после рестарта worker",
                        {
                            "broadcast_id": stream_event["broadcast_id"],
                            "watch_url": stream_event["watch_url"],
                            "started_at": started_at,
                            "lifecycle_status": lifecycle_status,
                        },
                    )

            if not stream_event:
                metadata = pick_stream_metadata(channel)
                title = metadata["title"]
                description = metadata["description"]

                event(
                    channel,
                    "info",
                    "Создание единственной YouTube-трансляции текущего цикла",
                    {"title": title},
                )

                stream_event = publisher.create_radio_event(
                    channel_name=channel,
                    title=title,
                    description=description,
                )
                restored_existing_event = False
                started_at = now_iso()
                persist_event_state(
                    channel,
                    stream_event,
                    started_at=started_at,
                )

            auto_recovery_attempt = 0
            first_start = not restored_existing_event

            while flag.exists():
                remaining_seconds = get_remaining_seconds(
                    started_at,
                    duration_hours,
                )

                if remaining_seconds <= 0:
                    finish_youtube_event(channel, stream_event)
                    reset_state(channel)
                    clear_event_state(channel)
                    stream_event = None
                    event(
                        channel,
                        "info",
                        "12-часовой эфир завершён по deadline",
                    )
                    run_between_streams_maintenance(channel)
                    if flag.exists():
                        time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                    break

                cycle_playlist = dict(playlist)
                cycle_playlist["target_seconds"] = remaining_seconds

                result = publisher.start_radio_ffmpeg(
                    channel_name=channel,
                    playlist=cycle_playlist,
                    event=stream_event,
                )

                engine = result["ffmpeg_engine"]
                ffmpeg_process = result["ffmpeg_process"]
                confirmed = confirm_ffmpeg_started(ffmpeg_process, flag)

                if confirmed:
                    set_state(
                        channel,
                        running=True,
                        paused=False,
                        watch_url=stream_event["watch_url"],
                        current_track=playlist["tracks"][0]["title"],
                        track_index=1,
                        last_error="",
                    )

                    if first_start:
                        notify_info(
                            channel,
                            "✅ Эфир успешно запущен и стабильно работает.\n\n"
                            f"{stream_event['watch_url']}",
                        )
                    else:
                        notify_info(
                            channel,
                            "✅ RTMP-поток восстановлен в той же трансляции.\n\n"
                            "Новая YouTube-трансляция не создавалась.\n\n"
                            f"{stream_event['watch_url']}",
                        )

                    event(
                        channel,
                        "success",
                        (
                            "Эфир стабильно запущен"
                            if first_start
                            else "RTMP восстановлен в существующей трансляции"
                        ),
                        {
                            "broadcast_id": stream_event["broadcast_id"],
                            "watch_url": stream_event["watch_url"],
                            "attempt": auto_recovery_attempt,
                        },
                    )
                    first_start = False

                ffmpeg_result = engine.wait_until_finished_or_flag_removed(
                    ffmpeg_process,
                    flag,
                    tick_seconds=1,
                )

                event(
                    channel,
                    "info" if ffmpeg_result.ok else "warning",
                    "FFmpeg завершил работу",
                    {
                        "ok": ffmpeg_result.ok,
                        "returncode": ffmpeg_result.returncode,
                        "duration_seconds": ffmpeg_result.duration_seconds,
                        "analysis": ffmpeg_result.analysis,
                        "ffmpeg_log": ffmpeg_result.log_paths,
                        "broadcast_id": stream_event["broadcast_id"],
                    },
                )

                if not flag.exists():
                    set_state(
                        channel,
                        running=False,
                        current_track="",
                        track_index=0,
                    )
                    clear_cycle_marker(channel)
                    event(
                        channel,
                        "info",
                        "Воркер остановлен. Данные текущей YouTube-трансляции сохранены",
                        {
                            "broadcast_id": stream_event.get("broadcast_id", ""),
                            "started_at": started_at,
                        },
                    )
                    break

                analysis = ffmpeg_result.analysis or {}
                action = analysis.get("action", "need_user")

                if ffmpeg_result.ok:
                    finish_youtube_event(channel, stream_event)
                    reset_state(channel)
                    clear_event_state(channel)
                    stream_event = None
                    event(
                        channel,
                        "info",
                        "12-часовой эфир завершён. Ожидание остальных каналов и очистка",
                    )
                    run_between_streams_maintenance(channel)
                    if not flag.exists():
                        break
                    event(
                        channel,
                        "info",
                        "Очистка завершена. Создаётся следующий эфир",
                    )
                    time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                    break

                if action == "stop":
                    finish_youtube_event(channel, stream_event)
                    reset_state(channel)
                    clear_cycle_marker(channel)
                    clear_event_state(channel)
                    event(channel, "info", "FFmpeg остановлен штатно")
                    break

                if action == "restart_broadcast":
                    auto_recovery_attempt += 1

                    if auto_recovery_attempt > MAX_AUTO_RECOVERY_ATTEMPTS:
                        cleanup_upcoming_event(channel, stream_event)
                        clear_event_state(channel)
                        raise RuntimeError(
                            "Автоматические попытки исчерпаны.\n\n"
                            + format_ffmpeg_analysis(analysis)
                            + "\n\nFFmpeg log: "
                            + str(ffmpeg_result.log_paths.get("latest"))
                        )

                    if not live.is_event_reusable(stream_event["broadcast_id"]):
                        cleanup_upcoming_event(channel, stream_event)
                        clear_event_state(channel)
                        raise RuntimeError(
                            "Автоматические попытки исчерпаны: существующая "
                            "YouTube-трансляция больше не допускает повторное "
                            "подключение.\n\n"
                            + format_ffmpeg_analysis(analysis)
                        )

                    set_state(channel, paused=False, last_error="")
                    event(
                        channel,
                        "warning",
                        "Повторный запуск FFmpeg в той же YouTube-трансляции",
                        {
                            "attempt": auto_recovery_attempt,
                            "max_attempts": MAX_AUTO_RECOVERY_ATTEMPTS,
                            "broadcast_id": stream_event["broadcast_id"],
                            "watch_url": stream_event["watch_url"],
                            "analysis": analysis,
                        },
                    )
                    notify_warning(
                        channel,
                        analysis.get(
                            "title",
                            "Соединение с YouTube прервано",
                        )
                        + ".\n\n"
                        + analysis.get("what_happened", "")
                        + "\n\nСистема повторно подключает FFmpeg к той же "
                        + "YouTube-трансляции.\nНовая трансляция не создаётся.\n"
                        + f"Попытка {auto_recovery_attempt} "
                        + f"из {MAX_AUTO_RECOVERY_ATTEMPTS}.",
                    )
                    time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                    continue

                cleanup_upcoming_event(channel, stream_event)
                clear_event_state(channel)
                raise RuntimeError(
                    "FFmpeg failed\n\n"
                    + format_ffmpeg_analysis(analysis)
                    + "\n\nFFmpeg log: "
                    + str(ffmpeg_result.log_paths.get("latest"))
                )

            if not flag.exists():
                break

            if stream_event is None:
                continue

            break

        except Exception:
            error = traceback.format_exc()
            log(error)

            cleanup_upcoming_event(channel, stream_event)
            clear_event_state(channel)

            advice = analyze_error(error)
            event(
                channel,
                "error",
                "Критическая ошибка. Канал переведён в режим ожидания",
                {
                    "error_title": advice["title"],
                    "what_happened": advice["what_happened"],
                    "recommended_actions": advice["recommended_actions"],
                    "error": error[-2000:],
                },
            )
            pause_channel(channel, error)
            log(
                f"[{channel}] Critical error. "
                "Channel paused. Waiting for manual restart."
            )
            break

    set_state(
        channel,
        running=False,
        current_track="",
        track_index=0,
    )
    clear_cycle_marker(channel)
    event(channel, "info", "Воркер остановлен")
    log(f"===== Radio Worker stopped: {channel} =====")


if __name__ == "__main__":
    run(sys.argv[1])
