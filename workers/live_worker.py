import sys
import time
import traceback
from datetime import datetime, timezone
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
from app.youtube.publish import Publisher


LOG_FILE = PROJECT_ROOT / "logs" / "live_worker.log"
RUNTIME_DIR = PROJECT_ROOT / "runtime"

MAX_AUTO_RECOVERY_ATTEMPTS = 3
AUTO_RECOVERY_DELAY_SECONDS = 15
STABLE_STREAM_SECONDS = 300
CYCLE_BARRIER_TIMEOUT_SECONDS = 180
CYCLE_BARRIER_POLL_SECONDS = 2


def log(message):
    print(message, flush=True)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(message + "\n")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def reset_state(channel):
    set_state(
        channel,
        running=False,
        watch_url="",
        started_at="",
        current_track="",
        track_index=0,
    )


def pause_channel(channel, error):
    flag = RUNTIME_DIR / f"{channel}.running"

    if flag.exists():
        flag.unlink()

    waiting_marker = cycle_waiting_marker(channel)

    if waiting_marker.exists():
        waiting_marker.unlink()

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

    advice_text = format_advice(error)

    notify_error(
        channel,
        "Канал остановлен и ожидает вашего вмешательства.\n\n"
        f"{advice_text}\n\n"
        f"Технические детали:\n{error[-1200:]}",
    )


def clear_pause(channel):
    set_state(
        channel,
        paused=False,
        last_error="",
    )


def safe_runtime_name(channel):
    return str(channel).replace("/", "_")


def cycle_waiting_marker(channel):
    return (
        RUNTIME_DIR
        / f"{safe_runtime_name(channel)}.cycle_waiting"
    )


def active_channel_names():
    names = []

    for path in RUNTIME_DIR.glob("*.running"):
        names.append(path.name[:-len(".running")])

    return sorted(names)


def all_active_channels_waiting():
    active = active_channel_names()

    if not active:
        return True

    for channel in active:
        if not cycle_waiting_marker(channel).exists():
            return False

    return True


def wait_for_cycle_barrier(channel):
    marker = cycle_waiting_marker(channel)
    marker.write_text(now_iso(), encoding="utf-8")

    deadline = time.monotonic() + CYCLE_BARRIER_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if all_active_channels_waiting():
            return {
                "ok": True,
                "timed_out": False,
            }

        time.sleep(CYCLE_BARRIER_POLL_SECONDS)

    if not active_ffmpeg_processes():
        return {
            "ok": True,
            "timed_out": True,
        }

    return {
        "ok": False,
        "timed_out": True,
    }


def clear_cycle_marker(channel):
    marker = cycle_waiting_marker(channel)

    try:
        marker.unlink()
    except FileNotFoundError:
        pass


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
            + "\n\n"
            "После очистки будет создан следующий эфир.",
        )

    clear_cycle_marker(channel)

    return result


def run(channel):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    flag = RUNTIME_DIR / f"{channel}.running"

    log(f"===== Radio Worker started: {channel} =====")
    event(channel, "info", "Воркер запущен")
    clear_pause(channel)

    library = ChannelLibrary(channel)
    radio = RadioService(channel)
    publisher = Publisher()

    auto_recovery_attempt = 0
    recovering = False

    while flag.exists():
        try:
            config = library.get_config()

            duration_hours = int(
                config.get(
                    "stream_duration_hours",
                    12,
                )
            )

            set_state(
                channel,
                running=True,
                stream_duration_hours=duration_hours,
                last_error="",
            )

            event(
                channel,
                "info",
                "Preflight Check перед запуском",
            )

            assert_preflight_ok(channel)

            event(
                channel,
                "success",
                "Preflight Check пройден",
            )

            event(
                channel,
                "info",
                "Сборка плейлиста",
            )

            playlist = radio.build_playlist()

            event(
                channel,
                "info",
                "Плейлист готов",
                {
                    "tracks": len(
                        playlist.get("tracks", [])
                    ),
                    "total_seconds": playlist.get(
                        "total_seconds",
                        0,
                    ),
                    "target_seconds": playlist.get(
                        "target_seconds",
                        0,
                    ),
                },
            )

            metadata = pick_stream_metadata(channel)
            title = metadata["title"]
            description = metadata["description"]

            event(
                channel,
                "info",
                "Выбраны название и описание эфира",
                {
                    "title": title,
                    "description": description,
                },
            )

            event(
                channel,
                "info",
                (
                    "Создание YouTube Live после автовосстановления"
                    if recovering
                    else "Создание YouTube Live"
                ),
                {
                    "recovery_attempt": (
                        auto_recovery_attempt
                        if recovering
                        else 0
                    )
                },
            )

            result = publisher.publish_radio(
                channel_name=channel,
                playlist=playlist,
                title=title,
                description=description,
            )

            set_state(
                channel,
                running=True,
                paused=False,
                watch_url=result["watch_url"],
                started_at=now_iso(),
                current_track=playlist["tracks"][0]["title"],
                track_index=1,
                last_error="",
            )

            event(
                channel,
                "success",
                (
                    "Эфир автоматически восстановлен"
                    if recovering
                    else "Эфир успешно запущен"
                ),
                {
                    "watch_url": result["watch_url"],
                    "current_track": playlist["tracks"][0]["title"],
                    "thumbnail_path": result.get(
                        "thumbnail_path",
                        "",
                    ),
                    "duration_seconds": result.get(
                        "duration_seconds",
                        0,
                    ),
                    "recovery_attempt": (
                        auto_recovery_attempt
                        if recovering
                        else 0
                    ),
                },
            )

            if recovering:
                notify_info(
                    channel,
                    "✅ Трансляция автоматически восстановлена.\n\n"
                    "Ваше участие не потребовалось.\n\n"
                    f"{result['watch_url']}",
                )
                recovering = False
            else:
                notify_info(
                    channel,
                    "✅ Эфир успешно запущен.\n\n"
                    f"{result['watch_url']}",
                )

            engine = result["ffmpeg_engine"]
            ffmpeg_process = result["ffmpeg_process"]

            ffmpeg_result = (
                engine.wait_until_finished_or_flag_removed(
                    ffmpeg_process,
                    flag,
                    tick_seconds=1,
                )
            )

            event(
                channel,
                (
                    "info"
                    if ffmpeg_result.ok
                    else "warning"
                ),
                "FFmpeg завершил работу",
                {
                    "ok": ffmpeg_result.ok,
                    "returncode": ffmpeg_result.returncode,
                    "duration_seconds": (
                        ffmpeg_result.duration_seconds
                    ),
                    "analysis": ffmpeg_result.analysis,
                    "ffmpeg_log": ffmpeg_result.log_paths,
                },
            )

            if not flag.exists():
                reset_state(channel)
                clear_cycle_marker(channel)

                event(
                    channel,
                    "info",
                    "Эфир остановлен пользователем",
                )
                break

            analysis = ffmpeg_result.analysis or {}
            action = analysis.get(
                "action",
                "need_user",
            )

            if (
                ffmpeg_result.duration_seconds
                >= STABLE_STREAM_SECONDS
            ):
                auto_recovery_attempt = 0

            if ffmpeg_result.ok:
                reset_state(channel)

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

                recovering = False
                time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                continue

            if action == "stop":
                reset_state(channel)
                clear_cycle_marker(channel)

                event(
                    channel,
                    "info",
                    "FFmpeg остановлен штатно",
                )
                break

            if action == "restart_broadcast":
                auto_recovery_attempt += 1

                if (
                    auto_recovery_attempt
                    > MAX_AUTO_RECOVERY_ATTEMPTS
                ):
                    raise RuntimeError(
                        "Автоматическое восстановление не удалось после "
                        f"{MAX_AUTO_RECOVERY_ATTEMPTS} попыток.\n\n"
                        + format_ffmpeg_analysis(analysis)
                        + "\n\n"
                        + (
                            "FFmpeg log: "
                            f"{ffmpeg_result.log_paths.get('latest')}"
                        )
                    )

                reset_state(channel)

                set_state(
                    channel,
                    paused=False,
                    last_error="",
                )

                event(
                    channel,
                    "warning",
                    "Запущено автоматическое восстановление эфира",
                    {
                        "attempt": auto_recovery_attempt,
                        "max_attempts": (
                            MAX_AUTO_RECOVERY_ATTEMPTS
                        ),
                        "analysis": analysis,
                        "ffmpeg_log": ffmpeg_result.log_paths,
                    },
                )

                notify_warning(
                    channel,
                    (
                        analysis.get(
                            "title",
                            "Соединение с YouTube прервано",
                        )
                    )
                    + ".\n\n"
                    + analysis.get(
                        "what_happened",
                        "",
                    )
                    + "\n\n"
                    + "Система уже создаёт новый эфир автоматически.\n"
                    + (
                        f"Попытка {auto_recovery_attempt} "
                        f"из {MAX_AUTO_RECOVERY_ATTEMPTS}.\n\n"
                    )
                    + "Ничего делать не нужно.",
                )

                recovering = True
                time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                continue

            raise RuntimeError(
                "FFmpeg failed\n\n"
                + format_ffmpeg_analysis(analysis)
                + "\n\n"
                + (
                    "FFmpeg log: "
                    f"{ffmpeg_result.log_paths.get('latest')}"
                )
            )

        except Exception:
            error = traceback.format_exc()
            log(error)

            advice = analyze_error(error)

            event(
                channel,
                "error",
                "Критическая ошибка. Канал переведён в режим ожидания",
                {
                    "error_title": advice["title"],
                    "what_happened": advice["what_happened"],
                    "recommended_actions": advice[
                        "recommended_actions"
                    ],
                    "error": error[-2000:],
                },
            )

            pause_channel(channel, error)

            log(
                f"[{channel}] Critical error. "
                "Channel paused. Waiting for manual restart."
            )
            break

    reset_state(channel)
    clear_cycle_marker(channel)

    event(
        channel,
        "info",
        "Воркер остановлен",
    )

    log(f"===== Radio Worker stopped: {channel} =====")


if __name__ == "__main__":
    run(sys.argv[1])
